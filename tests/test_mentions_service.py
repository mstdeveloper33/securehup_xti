"""Metered searches validate scope and storage under lock before any provider use."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import getpass
from io import StringIO
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from xti.adapters.sqlite import StorageError
from xti.application.mentions import MentionService
from xti.domain.assets import ValidationError
from xti.domain.mentions import (
    MentionCatalog, MentionHit, MentionRequest, MentionResponse, MentionRun,
    MentionTarget, build_query, company_target,
)
from xti.interfaces.mentions import configure_mentions
from xti.ports.discovery import SourceError


NOW = datetime(2026, 11, 15, 17, tzinfo=timezone.utc)
ORG_ID = "11111111-1111-4111-8111-111111111111"
OTHER_ID = "22222222-2222-4222-8222-222222222222"
TARGET = MentionTarget("organization", ORG_ID, "Example Company", ("example.com",))
REQUEST = MentionRequest(TARGET, "general", 10)
HIT = MentionHit("https://publisher.example/one", "Example Company news", "A short report", None, 0.8)
RESPONSE = MentionResponse(build_query(TARGET), "provider-request", (HIT,), 1)


class TrackingLock:
    def __init__(self, events):
        self.events, self.held, self.entered = events, False, 0

    @contextmanager
    def acquire(self):
        self.entered += 1
        self.events.append("lock")
        self.held = True
        try:
            yield
        finally:
            self.held = False
            self.events.append("unlock")


class MentionServiceContractTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.lock = TrackingLock(self.events)
        self.repo, self.targets, self.source = Mock(), Mock(), Mock()
        self.repo.validate.side_effect = self.record("validate")
        self.targets.resolve.side_effect = self.record("resolve", TARGET)
        self.source.fetch.side_effect = self.record("fetch", RESPONSE)
        self.repo.apply.side_effect = self.record("apply", "saved-run")
        self.repo.record_failure.side_effect = self.record("failure", "failed-run")
        self.service = MentionService(self.repo, self.targets, self.source, self.lock,
                                      clock=self.record("clock", NOW))

    def record(self, event, value=None):
        def call(*args, **kwargs):
            self.assertTrue(self.lock.held, event)
            self.events.append(event)
            return value
        return call

    def test_scope_storage_and_clock_are_validated_under_lock_before_provider(self):
        self.assertEqual(self.service.search(organization_id=ORG_ID), "saved-run")
        self.assertEqual(self.events, ["lock", "validate", "resolve", "clock", "fetch", "clock", "apply", "unlock"])
        self.source.fetch.assert_called_once_with(REQUEST)
        self.repo.apply.assert_called_once_with(REQUEST, RESPONSE,
            started_at=NOW.isoformat(), finished_at=NOW.isoformat())
        self.repo.record_failure.assert_not_called()
        self.assertFalse(self.lock.held)

    def test_corrupt_or_full_storage_stops_before_target_key_or_source_read(self):
        self.repo.validate.side_effect = StorageError("Corrupt history")
        with self.assertRaises(StorageError):
            self.service.search(organization_id=ORG_ID)
        self.targets.resolve.assert_not_called()
        self.source.fetch.assert_not_called()
        self.repo.apply.assert_not_called()
        self.repo.record_failure.assert_not_called()
        self.assertFalse(self.lock.held)

    def test_invalid_selection_stops_before_lock_and_provider(self):
        invalid = [dict(), dict(name="Example", supplier_id=ORG_ID),
            dict(organization_id="not-an-id"), dict(name="Example", max_results=21),
            dict(name="Example", max_results=True), dict(name="Example", topic="other"),
            dict(supplier_id=ORG_ID, domains=("example.com",)), dict(name="x")]
        for arguments in invalid:
            with self.subTest(arguments=arguments), self.assertRaises(ValidationError):
                self.service.search(**arguments)
        self.assertEqual(self.lock.entered, 0)
        self.repo.validate.assert_not_called()
        self.targets.resolve.assert_not_called()
        self.source.fetch.assert_not_called()

    def test_missing_source_or_lock_does_not_read_storage_or_target(self):
        for source, lock in ((None, self.lock), (self.source, None)):
            with self.subTest(source=source is None), self.assertRaises(ValidationError):
                MentionService(self.repo, self.targets, source, lock).search(organization_id=ORG_ID)
        self.repo.validate.assert_not_called()
        self.targets.resolve.assert_not_called()
        self.source.fetch.assert_not_called()

    def test_inactive_or_missing_target_stops_before_provider(self):
        self.targets.resolve.side_effect = ValidationError("Target inactive")
        with self.assertRaises(ValidationError):
            self.service.search(supplier_id=ORG_ID)
        self.source.fetch.assert_not_called()
        self.repo.record_failure.assert_not_called()
        self.assertFalse(self.lock.held)

    def test_resolver_cannot_substitute_another_valid_target_identity(self):
        for target in (replace(TARGET, id=OTHER_ID), replace(TARGET, kind="supplier")):
            self.targets.resolve.side_effect = None
            self.targets.resolve.return_value = target
            with self.subTest(target=target), self.assertRaises(ValidationError):
                self.service.search(organization_id=ORG_ID)
        self.source.fetch.assert_not_called()
        self.repo.apply.assert_not_called()
        self.repo.record_failure.assert_not_called()

    def test_invalid_clock_fails_before_network_and_releases_lock(self):
        self.service.clock = lambda: datetime(2026, 11, 15)
        with self.assertRaises(ValidationError):
            self.service.search(organization_id=ORG_ID)
        self.source.fetch.assert_not_called()
        self.repo.apply.assert_not_called()
        self.assertFalse(self.lock.held)

    def test_response_for_another_scope_is_failed_evidence_not_success(self):
        self.source.fetch.side_effect = self.record("fetch", replace(RESPONSE, query='"Other Company"'))
        self.assertEqual(self.service.search(organization_id=ORG_ID), "failed-run")
        self.repo.apply.assert_not_called()
        self.assertEqual(self.repo.record_failure.call_args.args, (REQUEST,))
        self.assertIn("kapsamıyla", self.repo.record_failure.call_args.kwargs["error"])
        self.assertNotIn("Other Company", self.repo.record_failure.call_args.kwargs["error"])
        self.assertFalse(self.lock.held)

    def test_invalid_response_shape_and_duplicates_preserve_failure_boundary(self):
        for response in (None, replace(RESPONSE, hits=(HIT, HIT)), replace(RESPONSE, credits=True)):
            self.source.fetch.side_effect = self.record("fetch", response)
            with self.subTest(response=response):
                self.assertEqual(self.service.search(organization_id=ORG_ID), "failed-run")
        self.repo.apply.assert_not_called()
        self.assertEqual(self.repo.record_failure.call_count, 3)

    def test_missing_credentials_are_configuration_errors_without_failure_writes(self):
        self.source.fetch.side_effect = ValidationError("Tavily key is missing")
        with self.assertRaises(ValidationError):
            self.service.search(organization_id=ORG_ID)
        self.repo.apply.assert_not_called()
        self.repo.record_failure.assert_not_called()
        self.assertFalse(self.lock.held)

    def test_source_outage_is_recorded_once_without_retry(self):
        self.source.fetch.side_effect = SourceError("Tavily istek sınırına ulaştı.")
        self.assertEqual(self.service.search(organization_id=ORG_ID), "failed-run")
        self.source.fetch.assert_called_once_with(REQUEST)
        self.repo.apply.assert_not_called()
        self.repo.record_failure.assert_called_once()

    def test_company_plan_is_offline_and_does_not_read_storage(self):
        planned = self.service.plan(name="Example Company", domains=("example.com",))
        self.assertEqual(planned.target, company_target("Example Company", ("example.com",)))
        self.assertEqual(self.events, [])
        self.repo.validate.assert_not_called()
        self.targets.resolve.assert_not_called()
        self.source.fetch.assert_not_called()

    def test_invalid_read_windows_and_references_fail_before_catalog(self):
        for method in (self.service.list, self.service.status):
            for params in (dict(limit=0), dict(limit=True), dict(offset=-1), dict(topic="invalid"),
                           dict(organization_id=ORG_ID, supplier_id=OTHER_ID), dict(supplier_id="invalid")):
                with self.subTest(method=method.__name__, params=params), self.assertRaises(ValidationError):
                    method(**params)
        with self.assertRaises(ValidationError):
            self.service.show("bad")
        with self.assertRaises(ValidationError):
            self.service.run_show("bad")
        self.repo.catalog.assert_not_called()

    def test_history_reconstruction_ignores_future_and_other_target_results(self):
        request = REQUEST
        other_request = replace(request, target=replace(TARGET, id=OTHER_ID))
        corrected = replace(HIT, title="Example Company correction")
        later = replace(HIT, title="A future headline")
        def run(number, scope, hit, *, added=0, updated=0):
            response = MentionResponse(build_query(scope.target), f"req-{number}", (hit,), 1)
            return MentionRun(number, f"{number:08d}-1111-4111-8111-111111111111", scope, "complete",
                              NOW.isoformat(), NOW.isoformat(), response, None, added, updated, 0)
        first = run(1, request, HIT, added=1)
        other = run(2, other_request, replace(HIT, title="Other target copy"), added=1)
        selected = run(3, request, corrected, updated=1)
        future = run(4, request, later, updated=1)
        self.repo.catalog.return_value = MentionCatalog((), (first, other, selected, future))
        report = self.service.run_show(selected.id)
        self.assertEqual(report["run"], selected)
        self.assertEqual(report["results"][0]["before"], HIT)
        self.assertEqual(report["results"][0]["after"], corrected)
        self.assertEqual(report["results"][0]["action"], "updated")
        self.targets.resolve.assert_not_called()
        self.source.fetch.assert_not_called()


class MentionConfigureContractTests(unittest.TestCase):
    def test_real_getpass_fallback_warning_stops_before_echo_read_or_save(self):
        stdin = Mock(spec=StringIO)
        stdin.isatty.return_value = True
        stdin.readline.side_effect = AssertionError("Secret must not be read with echo")
        with patch("sys.stdin", stdin), patch("getpass.getpass", getpass.fallback_getpass), \
             patch("xti.adapters.tavily_search.save_tavily_api_key") as save, \
             self.assertRaisesRegex(ValidationError, "gizli girişi desteklemiyor"):
            configure_mentions(SimpleNamespace(api_key_file=None))
        stdin.readline.assert_not_called()
        save.assert_not_called()

    def test_getpass_eof_and_nontty_never_save_a_key(self):
        for isatty in (True, False):
            with self.subTest(isatty=isatty), patch("sys.stdin.isatty", return_value=isatty), \
                 patch("getpass.getpass", side_effect=EOFError) as get_key, \
                 patch("xti.adapters.tavily_search.save_tavily_api_key") as save, \
                 self.assertRaises(ValidationError):
                configure_mentions(SimpleNamespace(api_key_file=None))
            save.assert_not_called()
            self.assertEqual(get_key.call_count, int(isatty))


if __name__ == "__main__":
    unittest.main()
