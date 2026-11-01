"""Provider waits survive new adapters and interrupted retry/body handling."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

from xti.adapters.crtsh import CrtShSource
from xti.adapters.source_cooldown import SourceCooldownGate
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cooldowns import SQLiteCooldownRepository
from xti.adapters.urlscan import UrlscanSource
from xti.domain.operations import SourceCooldown
from xti.ports.discovery import SourceError
from tests.test_crtsh import Response as CrtResponse
from tests.test_urlscan import Response as UrlResponse, body


class Clocks:
    def __init__(self):
        self.monotonic = 10.0
        self.utc = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
        self.waits = []

    def clock(self):
        return self.monotonic

    def wall(self):
        return self.utc

    def advance(self, seconds):
        self.monotonic += seconds
        self.utc += timedelta(seconds=seconds)

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.advance(seconds)


class PersistentSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "xti.db"
        SQLiteAssetRepository(self.database).initialize()
        self.clocks = Clocks()

    def repository(self):
        return SQLiteCooldownRepository(self.database)

    def source(self, provider, opener, **overrides):
        options = dict(opener=opener, cooldowns=self.repository(), clock=self.clocks.clock,
                       wall_clock=self.clocks.wall, sleep=self.clocks.sleep)
        options.update(overrides)
        cls = CrtShSource if provider == "crt.sh" else UrlscanSource
        return cls(**options)

    @staticmethod
    def pattern(provider):
        return "example%" if provider == "crt.sh" else "example*"

    @staticmethod
    def response(provider, headers=None):
        return CrtResponse(b"[]", headers=headers) if provider == "crt.sh" else UrlResponse(body(), headers=headers)

    def test_long_provider_wait_survives_new_adapter_and_database_connection(self):
        for provider in ("crt.sh", "urlscan"):
            with self.subTest(provider=provider):
                opener = Mock(side_effect=HTTPError("https://source/", 503, "busy", {"Retry-After": "120"}, None))
                with self.assertRaises(SourceError):
                    self.source(provider, opener).search(self.pattern(provider))
                saved = self.repository().get(provider)
                self.assertEqual(datetime.fromisoformat(saved.not_before), self.clocks.utc + timedelta(seconds=120))
                restarted = Mock(return_value=self.response(provider))
                with self.assertRaisesRegex(SourceError, "yeni istek gönderilmedi"):
                    self.source(provider, restarted).search(self.pattern(provider))
                restarted.assert_not_called()
                self.clocks.advance(120)
                self.source(provider, restarted).search(self.pattern(provider))
                restarted.assert_called_once()

    def test_minimum_request_spacing_survives_adapter_restart_and_precedes_open(self):
        for provider, interval in (("crt.sh", 1), ("urlscan", 2)):
            with self.subTest(provider=provider):
                recorded_at_open = []

                def open_response(*args, **kwargs):
                    saved = self.repository().get(provider)
                    recorded_at_open.append(saved)
                    self.assertEqual(datetime.fromisoformat(saved.not_before),
                                     self.clocks.utc + timedelta(seconds=interval))
                    return self.response(provider)

                self.source(provider, Mock(side_effect=open_response)).search(self.pattern(provider))
                prior = list(self.clocks.waits)
                self.source(provider, Mock(side_effect=open_response)).search(self.pattern(provider))
                self.assertEqual(self.clocks.waits[len(prior):], [float(interval)])
                self.assertEqual(len(recorded_at_open), 2)
                self.assertTrue(all(item.reason == "request_spacing" for item in recorded_at_open))

    def test_short_retry_is_saved_before_interruption_then_new_process_waits_remaining(self):
        for provider in ("crt.sh", "urlscan"):
            with self.subTest(provider=provider):
                opener = Mock(side_effect=HTTPError("https://source/", 503, "busy", {"Retry-After": "3"}, None))
                interrupted_sleep = Mock(side_effect=KeyboardInterrupt())
                with self.assertRaises(KeyboardInterrupt):
                    self.source(provider, opener, sleep=interrupted_sleep).search(self.pattern(provider))
                self.assertEqual(datetime.fromisoformat(self.repository().get(provider).not_before),
                                 self.clocks.utc + timedelta(seconds=3))
                opener.assert_called_once()
                self.clocks.advance(1)
                restarted = Mock(return_value=self.response(provider))
                self.source(provider, restarted).search(self.pattern(provider))
                self.assertEqual(self.clocks.waits[-1], 2.0)
                restarted.assert_called_once()

    def test_429_without_header_persists_sixty_seconds_before_any_retry(self):
        for provider in ("crt.sh", "urlscan"):
            with self.subTest(provider=provider):
                opener = Mock(side_effect=HTTPError("https://source/", 429, "busy", {}, None))
                with self.assertRaises(SourceError):
                    self.source(provider, opener).search(self.pattern(provider))
                opener.assert_called_once()
                self.assertEqual(datetime.fromisoformat(self.repository().get(provider).not_before),
                                 self.clocks.utc + timedelta(seconds=60))
        self.assertEqual(self.clocks.waits, [])

    def test_malformed_provider_delay_is_saved_as_conservative_wait(self):
        for provider in ("crt.sh", "urlscan"):
            with self.subTest(provider=provider):
                opener = Mock(side_effect=HTTPError("https://source/", 503, "busy", {"Retry-After": "bad"}, None))
                with self.assertRaises(SourceError):
                    self.source(provider, opener).search(self.pattern(provider))
                self.assertEqual(datetime.fromisoformat(self.repository().get(provider).not_before),
                                 self.clocks.utc + timedelta(seconds=60))
                opener.assert_called_once()

    def test_success_headers_persist_wait_before_bad_or_interrupted_body(self):
        for provider in ("crt.sh", "urlscan"):
            for failure in (TimeoutError(), KeyboardInterrupt()):
                with self.subTest(provider=provider, failure=type(failure).__name__):
                    self.clocks.advance(200)
                    headers = {"Retry-After": "120"} if provider == "crt.sh" else {
                        "X-Rate-Limit-Remaining": "0", "X-Rate-Limit-Reset-After": "120",
                    }
                    response = self.response(provider, headers)
                    response.read1 = Mock(side_effect=failure)
                    opener = Mock(return_value=response)
                    with self.assertRaises((SourceError, KeyboardInterrupt)):
                        self.source(provider, opener).search(self.pattern(provider))
                    saved = self.repository().get(provider)
                    self.assertGreaterEqual(datetime.fromisoformat(saved.not_before), self.clocks.utc + timedelta(seconds=119))
                    opener.assert_called_once()
                    restarted = Mock()
                    with self.assertRaisesRegex(SourceError, "bekleme süresi"):
                        self.source(provider, restarted).search(self.pattern(provider))
                    restarted.assert_not_called()

    def test_nonretryable_error_preserves_provider_wait(self):
        for provider in ("crt.sh", "urlscan"):
            with self.subTest(provider=provider):
                headers = {"Retry-After": "120"} if provider == "crt.sh" else {
                    "X-Rate-Limit-Remaining": "0", "X-Rate-Limit-Reset-After": "120",
                }
                opener = Mock(side_effect=HTTPError("https://source/", 403, "denied", headers, None))
                with self.assertRaises(SourceError):
                    self.source(provider, opener).search(self.pattern(provider))
                self.assertEqual(datetime.fromisoformat(self.repository().get(provider).not_before),
                                 self.clocks.utc + timedelta(seconds=120))
                opener.assert_called_once()

    def test_http_and_reset_dates_use_injected_utc_clock(self):
        for provider, headers in (
            ("crt.sh", {"Retry-After": "Wed, 28 Oct 2026 12:02:00 GMT"}),
            ("urlscan", {"X-Rate-Limit-Remaining": "0", "X-Rate-Limit-Reset": "2026-10-28T15:02:00+03:00"}),
        ):
            with self.subTest(provider=provider):
                opener = Mock(side_effect=HTTPError("https://source/", 429, "busy", headers, None))
                with self.assertRaises(SourceError):
                    self.source(provider, opener).search(self.pattern(provider))
                self.assertEqual(self.repository().get(provider).not_before, "2026-10-28T12:02:00+00:00")

    def test_huge_delay_is_saved_as_latest_calendar_date_without_sleep(self):
        for provider in ("crt.sh", "urlscan"):
            with self.subTest(provider=provider):
                opener = Mock(side_effect=HTTPError("https://source/", 429, "busy",
                                                   {"Retry-After": "9" * 40}, None))
                with self.assertRaises(SourceError):
                    self.source(provider, opener).search(self.pattern(provider))
                self.assertEqual(self.repository().get(provider).not_before,
                                 datetime.max.replace(tzinfo=timezone.utc).isoformat())
                opener.assert_called_once()
        self.assertEqual(self.clocks.waits, [])

    def test_provider_wait_does_not_block_other_provider(self):
        opener = Mock(side_effect=HTTPError("https://source/", 429, "busy", {"Retry-After": "120"}, None))
        with self.assertRaises(SourceError):
            self.source("crt.sh", opener).search("example%")
        other = Mock(return_value=self.response("urlscan"))
        self.source("urlscan", other).search("example*")
        other.assert_called_once()

    def test_new_longer_wait_during_request_is_reloaded_before_retry(self):
        for provider in ("crt.sh", "urlscan"):
            with self.subTest(provider=provider):
                def externally_extended(*args, **kwargs):
                    self.repository().extend(provider, (self.clocks.utc + timedelta(seconds=120)).isoformat(),
                                             self.clocks.utc.isoformat(), "provider_wait")
                    raise TimeoutError()

                opener = Mock(side_effect=externally_extended)
                with self.assertRaisesRegex(SourceError, "bekleme süresi"):
                    self.source(provider, opener).search(self.pattern(provider))
                opener.assert_called_once()

    def test_storage_read_or_pacing_write_failure_sends_no_request(self):
        for provider in ("crt.sh", "urlscan"):
            for method in ("get", "extend"):
                with self.subTest(provider=provider, method=method):
                    repository = Mock(wraps=self.repository())
                    getattr(repository, method).side_effect = StorageError("Bekleme kaydı okunamadı.")
                    opener = Mock()
                    with self.assertRaises(StorageError):
                        self.source(provider, opener, cooldowns=repository).search(self.pattern(provider))
                    opener.assert_not_called()

    def test_header_write_failure_stops_before_response_body_or_retry(self):
        for provider in ("crt.sh", "urlscan"):
            with self.subTest(provider=provider):
                repository = Mock(wraps=self.repository())
                original = self.repository().extend

                def extend(provider, until, recorded_at, reason):
                    if reason != "request_spacing":
                        raise StorageError("Bekleme kaydı yazılamadı.")
                    return original(provider, until, recorded_at, reason)

                repository.extend.side_effect = extend
                response = self.response(provider, {"Retry-After": "120"})
                response.read1 = Mock()
                opener = Mock(return_value=response)
                with self.assertRaises(StorageError):
                    self.source(provider, opener, cooldowns=repository).search(self.pattern(provider))
                response.read1.assert_not_called()
                opener.assert_called_once()


class CooldownGateClockTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clocks()
        self.store = Mock()
        self.store.get.return_value = None
        self.store.extend.side_effect = lambda provider, not_before, recorded_at, reason: SourceCooldown(
            provider, not_before, recorded_at, reason,
        )
        self.gate = SourceCooldownGate("crt.sh", self.store, clock=self.clock.clock,
                                       wall_clock=self.clock.wall, sleep=self.clock.sleep)

    def test_forward_wall_clock_jump_does_not_shorten_already_seen_process_wait(self):
        self.gate.record(120, "retry_after")
        self.clock.utc += timedelta(days=1)
        with self.assertRaisesRegex(SourceError, "bekleme süresi"):
            self.gate.before_request(1)
        self.assertEqual(self.clock.waits, [])

    def test_incomplete_sleep_does_not_send_early_or_loop_forever(self):
        self.store.get.return_value = SourceCooldown(
            "crt.sh", (self.clock.utc + timedelta(seconds=3)).isoformat(),
            self.clock.utc.isoformat(), "retry_after",
        )
        self.gate.sleep = Mock()
        with self.assertRaisesRegex(SourceError, "bekleme süresi"):
            self.gate.before_request(1)
        self.gate.sleep.assert_called_once_with(3.0)
        self.store.extend.assert_not_called()

    def test_invalid_naive_wall_clock_prevents_reservation(self):
        self.gate.wall_clock = lambda: datetime(2026, 10, 28)
        with self.assertRaisesRegex(SourceError, "saat dilimi"):
            self.gate.before_request(1)
        self.store.extend.assert_not_called()

    def test_longer_wait_returned_by_atomic_reservation_prevents_open(self):
        self.store.extend.side_effect = lambda provider, not_before, recorded_at, reason: SourceCooldown(
            provider, (self.clock.utc + timedelta(seconds=120)).isoformat(), recorded_at, "retry_after",
        )
        with self.assertRaisesRegex(SourceError, "bekleme süresi"):
            self.gate.before_request(1)
        self.store.extend.assert_called_once()


if __name__ == "__main__":
    unittest.main()
