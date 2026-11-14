"""No-network tests for public metadata validation, persistence and local lookup."""

from contextlib import closing
from dataclasses import asdict, replace
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from xti.adapters.hibp_public_notices import HibpPublicNoticeSource, MAX_RESPONSE_BYTES, parse_hibp_public_notices_response
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.application.public_notices import PublicNoticeService
from xti.domain.assets import ValidationError
from xti.domain.public_notices import HIBP_ATTRIBUTION, HIBP_SOURCE_URL
from xti.ports.discovery import SourceError


NOW = datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)


def item(name="Example", domain="example.com", **updates):
    record = {
        "Name": name, "Title": name, "Domain": domain, "BreachDate": "2025-01-02",
        "AddedDate": "2025-02-03T04:05:00Z", "ModifiedDate": "2025-02-03T04:05:00Z",
        "PwnCount": 12345, "DataClasses": ["Email addresses", "Passwords"],
        "IsVerified": True, "IsFabricated": False, "IsSensitive": False,
        "IsRetired": False, "IsSpamList": False, "IsMalware": False,
        "IsStealerLog": False, "Attribution": "Public contributor",
        "Description": "<a href='https://private.invalid'>RAW-MARKER</a>",
        "LogoPath": "http://127.0.0.1/logo.png", "DisclosureUrl": "http://127.0.0.1/report",
    }
    record.update(updates)
    return record


def feed(*records):
    return parse_hibp_public_notices_response(json.dumps(records or [item()]).encode(), fetched_at=NOW)


class Response(BytesIO):
    def __init__(self, body, *, headers=None, url=HIBP_SOURCE_URL, code=200):
        super().__init__(body)
        self.headers = headers if headers is not None else {"Content-Type": "application/json", "Content-Length": str(len(body))}
        self.url, self.code = url, code

    def geturl(self):
        return self.url

    def getcode(self):
        return self.code


class PublicNoticeSourceTests(unittest.TestCase):
    def test_live_contract_allows_future_metadata_but_never_retains_raw_fields(self):
        result = feed(item(FutureUnknown={"secret": "RAW-MARKER"}))
        self.assertEqual(result.notices[0].id, "Example")
        self.assertEqual(result.attribution, HIBP_ATTRIBUTION)
        self.assertNotIn("RAW-MARKER", json.dumps(asdict(result)))
        self.assertNotIn("127.0.0.1", json.dumps(asdict(result)))
        self.assertEqual(result.notices[0].source_url, "https://haveibeenpwned.com/api/v3/breach/Example")

    def test_source_flags_and_empty_domain_are_preserved_without_inference(self):
        result = feed(item(domain="", IsVerified=False, IsFabricated=True,
                           IsSpamList=True, IsMalware=True, IsRetired=True, IsStealerLog=True))
        notice = result.notices[0]
        self.assertIsNone(notice.domain)
        self.assertFalse(notice.is_verified)
        self.assertTrue(all((notice.is_fabricated, notice.is_spam_list, notice.is_malware,
                             notice.is_retired, notice.is_stealer_log)))

    def test_incomplete_invalid_duplicate_and_future_catalogs_fail_closed(self):
        invalid = [[], [item(), item()], {}, [item(Name="../secret")],
                   [item(IsVerified=1)], [item(DataClasses="Passwords")],
                   [item(PwnCount=True)], [item(Title="bad\x1b[0m")],
                   [item(ModifiedDate="2027-01-01T00:00:00Z")],
                   [item(AddedDate="2025-01-01")], [item(BreachDate="not-a-date")],
                   [item(DataClasses=["Passwords", "Passwords"])]]
        missing = item(); del missing["IsVerified"]; invalid.append([missing])
        for records in invalid:
            with self.subTest(records=records):
                with self.assertRaises(SourceError):
                    parse_hibp_public_notices_response(json.dumps(records).encode(), fetched_at=NOW)
        with self.assertRaises(SourceError):
            parse_hibp_public_notices_response(b'[{"Name":"One","Name":"Two"}]', fetched_at=NOW)
        with self.assertRaises(SourceError):
            parse_hibp_public_notices_response(b"[NaN]", fetched_at=NOW)

    def test_fixed_documented_endpoint_truthful_agent_without_auth_or_target_queries(self):
        opener = Mock(return_value=Response(json.dumps([item()]).encode()))
        result = HibpPublicNoticeSource(opener=opener, clock=lambda: NOW).fetch()
        self.assertEqual(len(result.notices), 1)
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, HIBP_SOURCE_URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertIn("XTI/", request.headers["User-agent"])
        self.assertNotIn("Hibp-api-key", request.headers)
        self.assertEqual(opener.call_count, 1)

    def test_redirect_html_truncated_compressed_and_oversized_responses_fail(self):
        body = json.dumps([item()]).encode()
        responses = [Response(body, url="https://example.com"), Response(body, code=302),
                     Response(body, headers={"Content-Type": "text/html"}),
                     Response(body, headers={"Content-Type": "application/json", "Content-Encoding": "gzip"}),
                     Response(body, headers={"Content-Type": "application/json", "Content-Length": str(len(body) + 1)}),
                     Response(body, headers={"Content-Type": "application/json", "Content-Length": str(MAX_RESPONSE_BYTES + 1)})]
        for response in responses:
            with self.subTest(response=response.headers):
                with self.assertRaises(SourceError):
                    HibpPublicNoticeSource(opener=Mock(return_value=response), clock=lambda: NOW).fetch()

    def test_network_error_429_and_read_deadline_do_not_retry_or_expose_response_body(self):
        for error in [URLError("private credentials"), HTTPError(HIBP_SOURCE_URL, 429, "private credentials", {}, None)]:
            opener = Mock(side_effect=error)
            with self.assertRaises(SourceError) as caught:
                HibpPublicNoticeSource(opener=opener).fetch()
            self.assertNotIn("private credentials", str(caught.exception))
            self.assertEqual(opener.call_count, 1)
        with self.assertRaisesRegex(SourceError, "süresi"):
            HibpPublicNoticeSource(opener=Mock(return_value=Response(b"[]")),
                                  monotonic=Mock(side_effect=[0, 100])).fetch()


class PublicNoticeStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.repo = SQLitePublicNoticeRepository(self.path)

    def apply(self, value=None, **kwargs):
        return self.repo.apply(value or feed(), started_at=NOW.isoformat(), finished_at=NOW.isoformat(), **kwargs)

    def rows(self, table):
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()

    def test_baseline_repeat_change_remove_and_reappear_keep_compact_auditable_history(self):
        baseline = self.apply(feed(item(), item("Second", "second.example")))
        self.assertTrue(baseline.is_baseline)
        self.assertEqual(baseline.run.added_count, 2)
        repeat = self.apply(feed(item(), item("Second", "second.example")))
        self.assertFalse(repeat.is_baseline)
        self.assertEqual((repeat.run.unchanged_count, repeat.changes), (2, ()))
        changed = self.apply(feed(item(Title="Example new title", ModifiedDate="2025-02-04T01:00:00Z")))
        self.assertEqual((changed.run.updated_count, changed.run.removed_count), (1, 1))
        reappear = self.apply(feed(item(Title="Example new title", ModifiedDate="2025-02-04T01:00:00Z"), item("Second", "second.example")))
        self.assertEqual(reappear.run.added_count, 1)
        self.assertEqual(len(self.rows("public_notice_changes")), 5)
        self.assertEqual(len(self.repo.latest_snapshot().notices), 2)
        self.assertEqual(self.repo.run_show(changed.run.id).run, changed.run)

    def test_failure_preserves_last_success_and_is_visible_in_search_and_status(self):
        baseline = self.apply()
        failure = self.repo.record_failure(started_at=NOW.isoformat(), finished_at=NOW.isoformat(), error="Kaynak HTTP 429 verdi.")
        status = self.repo.status()
        self.assertEqual(status.latest_complete_run.id, baseline.run.id)
        self.assertEqual(status.latest_run, failure)
        result = PublicNoticeService(self.repo).search("Example")
        self.assertEqual((result.matched_count, result.latest_run.status), (1, "failed"))
        self.assertEqual(len(self.rows("public_notice_changes")), 1)
        self.assertEqual(self.repo.run_show(failure.id).changes, ())

    def test_first_failure_is_not_empty_success_and_offline_reads_never_create_data(self):
        service = PublicNoticeService(self.repo, Mock(fetch=Mock(side_effect=SourceError("Kaynak bağlantısı tamamlanamadı."))), clock=lambda: NOW)
        result = service.refresh()
        self.assertEqual(result.run.status, "failed")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValidationError, "notices refresh"):
            service.search("Example")
        self.assertIsNone(service.status().latest_complete_run)
        self.assertEqual(self.path.read_bytes(), before)

    def test_local_search_exact_domain_text_offset_and_attribution(self):
        self.apply(feed(item("One", "example.com"), item("Two", "sub.example.com"), item("Three", "notexample.com")))
        source = Mock()
        service = PublicNoticeService(self.repo, source)
        before = self.path.read_bytes()
        self.assertEqual(service.search(domain="EXAMPLE.COM").matched_count, 1)
        self.assertEqual(service.search("example.com").matched_count, 3)
        first = service.search(limit=2)
        second = service.search(limit=2, offset=2)
        self.assertTrue(first.has_more)
        self.assertFalse(second.has_more)
        self.assertEqual(len({notice.id for notice in first.notices + second.notices}), 3)
        self.assertEqual(service.show("One").notice.domain, "example.com")
        self.assertIn("https://haveibeenpwned.com", json.dumps(asdict(first)))
        self.assertEqual(self.path.read_bytes(), before)
        source.fetch.assert_not_called()

    def test_run_and_status_pagination_and_limits_do_not_truncate_collection(self):
        first = self.apply(feed(item("One"), item("Two"), item("Three")), item_limit=1)
        self.assertEqual((len(first.changes), first.total_change_count, first.run.notice_count), (1, 3, 3))
        self.assertEqual(len(self.repo.run_show(first.run.id, offset=1).changes), 2)
        self.apply()
        status = self.repo.status(run_limit=1, offset=1)
        self.assertEqual((status.total_run_count, status.recent_runs[0].id), (2, first.run.id))

    def test_invalid_arguments_do_not_touch_network_or_storage(self):
        source = Mock()
        service = PublicNoticeService(self.repo, source)
        before = self.path.read_bytes()
        for method in [lambda: service.search(""), lambda: service.search("foo\nbar"),
                       lambda: service.search(offset=-1), lambda: service.search(limit=True),
                       lambda: service.search(domain="https://example.com"),
                       lambda: service.show("../x"), lambda: service.run_show("invalid"),
                       lambda: service.refresh(item_limit=0)]:
            with self.assertRaises(ValidationError):
                method()
        self.assertEqual(self.path.read_bytes(), before)
        source.fetch.assert_not_called()

    def test_missing_or_corrupt_database_preflight_blocks_network(self):
        source = Mock()
        missing = self.path.parent / "missing.db"
        with self.assertRaises(StorageError):
            PublicNoticeService(SQLitePublicNoticeRepository(missing), source).refresh()
        self.assertFalse(missing.exists())
        self.apply()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DELETE FROM public_notice_changes")
        with self.assertRaises(StorageError):
            PublicNoticeService(self.repo, source).refresh()
        source.fetch.assert_not_called()

    def test_empty_snapshot_is_typed_and_failure_only_remains_distinct(self):
        snapshot = self.repo.latest_snapshot()
        self.assertEqual(snapshot.notices, ())
        self.assertIsNone(snapshot.latest_run)
        failed = self.repo.record_failure(started_at=NOW.isoformat(), finished_at=NOW.isoformat(), error="Kaynak bağlantısı tamamlanamadı.")
        snapshot = self.repo.latest_snapshot()
        self.assertEqual(snapshot.notices, ())
        self.assertEqual(snapshot.latest_run, failed)
        self.assertIsNone(snapshot.latest_complete_run)

    def test_failure_during_transaction_rolls_back_source_run_and_all_changes(self):
        self.apply()
        before_runs, before_changes = self.rows("public_notice_runs"), self.rows("public_notice_changes")
        insert = self.repo._insert
        def fail(*args):
            insert(*args)
            raise sqlite3.OperationalError("controlled persistence failure")
        with patch.object(self.repo, "_insert", side_effect=fail):
            with self.assertRaises(StorageError):
                self.apply(feed(item("Second", "second.example")))
        self.assertEqual(self.rows("public_notice_runs"), before_runs)
        self.assertEqual(self.rows("public_notice_changes"), before_changes)

    def test_corrupt_hash_counter_item_deletion_or_failure_metadata_fail_closed(self):
        corruptions = ["UPDATE public_notice_changes SET state_sha256='" + "a"*64 + "'",
                       "DELETE FROM public_notice_changes",
                       "UPDATE public_notice_runs SET snapshot_sha256='" + "b"*64 + "'",
                       "UPDATE public_notice_runs SET content_sha256='" + "c"*64 + "'"]
        for sql in corruptions:
            with self.subTest(sql=sql):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "corrupt.db"; SQLiteAssetRepository(path).initialize()
                    repo = SQLitePublicNoticeRepository(path)
                    repo.apply(feed(), started_at=NOW.isoformat(), finished_at=NOW.isoformat())
                    with closing(sqlite3.connect(path)) as connection, connection:
                        connection.execute(sql)
                    before = path.read_bytes()
                    with self.assertRaises(StorageError): repo.latest_snapshot()
                    with self.assertRaises(StorageError): repo.status()
                    with self.assertRaises(StorageError): repo.apply(feed(), started_at=NOW.isoformat(), finished_at=NOW.isoformat())
                    self.assertEqual(path.read_bytes(), before)

    def test_invalid_feed_and_empty_global_catalog_never_erase_prior_snapshot(self):
        self.apply()
        before = self.path.read_bytes()
        for value in [replace(feed(), notices=()), replace(feed(), notices=(feed().notices[0],)*2),
                      replace(feed(), source_url="http://localhost"),
                      replace(feed(), notices=(replace(feed().notices[0], is_verified=1),))]:
            with self.assertRaises(ValidationError): self.apply(value)
        self.assertEqual(self.path.read_bytes(), before)

    def test_backup_restore_preserves_catalog_and_run_evidence(self):
        first = self.apply()
        backup, restored = self.path.parent / "backup.db", self.path.parent / "restored.db"
        self.storage.backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        copy = SQLitePublicNoticeRepository(restored)
        self.assertEqual(copy.latest_snapshot(), self.repo.latest_snapshot())
        self.assertEqual(copy.run_show(first.run.id), first)
        with self.assertRaises(StorageError): SQLiteAssetRepository.restore(backup, restored)
