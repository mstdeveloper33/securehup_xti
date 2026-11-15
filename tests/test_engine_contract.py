"""Read-only engine protocol acceptance with real local evidence and hostile input."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO, TextIOWrapper
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti import __version__
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.interfaces.cli import main
from tests import test_public_notices as notice_fixtures


class EngineContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "engine evidence"
        self.database = self.data / "xti.db"
        self.assets = SQLiteAssetRepository(self.database)
        self.assets.initialize()
        self.asset, _ = self.assets.add("example.com")
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Engine reads must stay offline")))
        self.enterContext(patch("socket.create_connection", side_effect=AssertionError("Engine reads must stay offline")))
        self.enterContext(patch("subprocess.run", side_effect=AssertionError("Engine reads must not run tools")))
        self.enterContext(patch("subprocess.Popen", side_effect=AssertionError("Engine reads must not start processes")))

    @staticmethod
    def request(operation="search", parameters=None, **changes):
        request = {
            "contract_version": 1,
            "request_id": "test-request:1",
            "operation": operation,
            "parameters": {"query": "example"} if parameters is None else parameters,
        }
        return {**request, **changes}

    def files(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def invoke(self, request=None, *, raw=None, data_dir=None, arguments=()):
        if raw is None:
            raw = json.dumps(self.request() if request is None else request, ensure_ascii=True)
        stream = TextIOWrapper(BytesIO(raw), encoding="utf-8") if isinstance(raw, bytes) else StringIO(raw)
        stdout, stderr = StringIO(), StringIO()
        with patch("sys.stdin", stream), redirect_stdout(stdout), redirect_stderr(stderr), \
                patch.object(SQLiteAssetRepository, "initialize", side_effect=AssertionError("Read must not initialize")):
            code = main(["--data-dir", str(data_dir or self.data), "engine", *arguments])
        output = stdout.getvalue()
        self.assertEqual(stderr.getvalue(), "", output)
        try:
            response = json.loads(output)
        except (ValueError, TypeError) as error:
            self.fail(f"Engine must emit exactly one JSON response, got {output!r}: {error}")
        self.assertIsInstance(response, dict)
        self.assertTrue({"contract_version", "engine_version", "request_id", "operation", "status",
                         "scope", "data", "error"}.issubset(response), response)
        self.assertEqual(response["contract_version"], 1)
        self.assertEqual(response["engine_version"], __version__)
        self.assertEqual(response["scope"], {"mode": "local-workspace"})
        return code, response

    def complete(self, request=None, **options):
        request = self.request() if request is None else request
        code, response = self.invoke(request, **options)
        self.assertEqual((code, response["status"], response["error"]), (0, "complete", None), response)
        self.assertEqual(response["request_id"], request["request_id"])
        self.assertEqual(response["operation"], request["operation"])
        return response["data"]

    def assert_error(self, expected, *, request=None, raw=None, exit_code=2, **options):
        code, response = self.invoke(request, raw=raw, **options)
        self.assertEqual((code, response["status"], response["data"]), (exit_code, "error", None), response)
        self.assertEqual(response["error"]["code"], expected, response)
        self.assertIsInstance(response["error"]["message"], str)
        self.assertTrue(response["error"]["message"])
        self.assertIs(type(response["error"]["retryable"]), bool)
        return response

    def save_notice_and_failure(self):
        now = datetime.now(timezone.utc)
        at = (now - timedelta(days=2)).isoformat()
        notices = SQLitePublicNoticeRepository(self.database)
        feed = replace(notice_fixtures.feed(), fetched_at=at)
        success = notices.apply(feed, started_at=at, finished_at=at).run
        later = (now - timedelta(hours=1)).isoformat()
        failed = notices.record_failure(started_at=later, finished_at=later,
                                        error="Recorded source timeout; retained earlier evidence.")
        return success, failed

    def test_search_returns_stable_reference_and_keeps_exact_match_metadata(self):
        before = self.files()
        result = self.complete(self.request(parameters={"query": "example.com", "kinds": ["domain"]}))
        self.assertEqual(result["consistency"], "single_read_snapshot")
        self.assertEqual((result["query"], result["kinds"], result["total_match_count"]),
                         ("example.com", ["domain"], 1))
        self.assertEqual((result["offset"], result["limit"], result["has_more"]), (0, 50, False))
        record = result["results"][0]
        self.assertEqual(record["reference"], {
            "kind": "domain", "record_type": "registered_domain",
            "namespace": "local-assets", "record_id": self.asset.id,
        })
        self.assertEqual((record["match_type"], record["matched_field"], record["matched_value"]),
                         ("exact", "domain", "example.com"))
        self.assertNotIn("navigation", record)
        self.assertEqual(self.files(), before)

    def test_search_reference_can_be_read_without_new_collection_or_file_changes(self):
        result = self.complete(self.request(parameters={"query": "example.com", "kinds": ["domain"]}))
        reference = result["results"][0]["reference"]
        before = self.files()
        detail = self.complete(self.request("record.get", {"reference": reference}))
        self.assertEqual(detail["reference"], reference)
        self.assertIn("example.com", json.dumps(detail))
        self.assertEqual(self.files(), before)

    def test_pages_have_global_totals_no_overlap_and_explicit_end(self):
        for domain in ("a.example.com", "b.example.com"):
            self.assets.add(domain)
        before = self.files()
        pages = [self.complete(self.request(parameters={"query": "example", "kinds": ["domain"],
                                                       "limit": 1, "offset": offset}))
                 for offset in range(4)]
        self.assertEqual([page["total_match_count"] for page in pages], [3] * 4)
        self.assertEqual([page["has_more"] for page in pages], [True, True, False, False])
        identifiers = [page["results"][0]["reference"]["record_id"] for page in pages[:3]]
        self.assertEqual(len(set(identifiers)), 3)
        self.assertEqual(pages[3]["results"], [])
        self.assertEqual(self.files(), before)

    def test_successful_empty_search_has_coverage_and_is_not_a_source_failure(self):
        result = self.complete(self.request(parameters={"query": "unmatched", "kinds": ["domain"]}))
        self.assertEqual((result["total_match_count"], result["results"], result["has_more"]), (0, [], False))
        self.assertTrue(result["coverage"])
        self.assertTrue(result["notes"])

    def test_search_keeps_last_success_when_latest_source_attempt_failed(self):
        success, failed = self.save_notice_and_failure()
        before = self.files()
        result = self.complete(self.request(parameters={"query": "example", "kinds": ["public-notice"]}))
        self.assertEqual(result["total_match_count"], 1)
        scope = result["coverage"][0]
        self.assertEqual((scope["latest_run_id"], scope["latest_run_status"], scope["latest_success_run_id"]),
                         (failed.id, "failed", success.id))
        record = result["results"][0]
        self.assertEqual(record["source_run_id"], success.id)
        self.assertEqual(record["reference"]["namespace"], "hibp")
        self.assertEqual(self.files(), before)

    def test_source_status_read_completes_while_failed_stale_source_stays_visible(self):
        success, failed = self.save_notice_and_failure()
        before = self.files()
        data = self.complete(self.request("sources.status", {"domain": "example.com", "stale_after_hours": 1}))
        self.assertEqual(data["consistency"], "independent_source_reads")
        source = next(row for row in data["sources"] if row["identifier"] == "notices:hibp")
        self.assertEqual(source["latest_status"], "failed")
        self.assertEqual(source["last_attempt_at"], failed.started_at)
        self.assertEqual(source["last_success_at"], success.finished_at)
        self.assertEqual(source["freshness"], "stale")
        self.assertTrue(source["needs_attention"])
        self.assertEqual(self.files(), before)

    def test_source_status_not_initialized_is_reported_without_creating_storage(self):
        missing = self.root / "not initialized"
        data = self.complete(self.request("sources.status", {}), data_dir=missing)
        self.assertEqual(data["storage_state"], "not_initialized")
        self.assertFalse(missing.exists())

    def test_missing_database_search_is_machine_error_and_does_not_create_it(self):
        missing = self.root / "missing"
        self.assert_error("storage_error", exit_code=1, data_dir=missing)
        self.assertFalse(missing.exists())

    def test_known_record_type_missing_identifier_returns_not_found(self):
        reference = {"kind": "domain", "record_type": "registered_domain",
                     "namespace": "local-assets", "record_id": str(uuid4())}
        self.assert_error("not_found", request=self.request("record.get", {"reference": reference}), exit_code=3)

    def test_request_schema_rejects_missing_unknown_or_wrong_typed_fields_before_storage(self):
        malformed = []
        for field in ("contract_version", "request_id", "operation", "parameters"):
            value = self.request()
            del value[field]
            malformed.append(value)
        malformed.extend((self.request(extra=True), self.request(parameters=[]),
                          self.request(operation=1),
                          self.request(contract_version=True), self.request(contract_version=1.0),
                          self.request(contract_version="1")))
        malformed.append({**self.request(), "parameters": None})
        with patch("sqlite3.connect", side_effect=AssertionError("Invalid request must not read storage")):
            for value in malformed:
                with self.subTest(value=value):
                    self.assert_error("invalid_request", request=value)

    def test_unknown_version_and_operation_have_distinct_errors(self):
        with patch("sqlite3.connect", side_effect=AssertionError("Unsupported operation must not read storage")):
            self.assert_error("unsupported_version", request=self.request(contract_version=2))
            self.assert_error("unsupported_operation", request=self.request(operation="collect"))
            self.assert_error("unsupported_operation", request=self.request(operation="__dict__"))

    def test_request_identifier_is_ascii_bounded_and_echoed_without_rewriting(self):
        for identifier in ("", None, 1, "_bad", "ş-request", "a\nrequest", "a" * 129):
            with self.subTest(identifier=identifier):
                self.assert_error("invalid_request", request=self.request(request_id=identifier))
        valid = "A" + "a._:-" * 25 + "12"
        self.assertEqual(len(valid), 128)
        self.complete(self.request(request_id=valid))

    def test_json_syntax_duplicates_nonfinite_values_and_surrogates_fail_cleanly(self):
        valid = json.dumps(self.request())
        malformed = ["", "   ", "[]", "null", "false", "{", valid + valid,
                     valid[:-1] + ',"operation":"sources.status"}',
                     valid.replace('"example"', 'NaN'), valid.replace('"example"', 'Infinity'),
                     valid.replace('"example"', '1e999'),
                     valid.replace('"example"', '"\\ud800"'),
                     valid.replace('"query": "example"', '"query":"example","query":"other"')]
        with patch("sqlite3.connect", side_effect=AssertionError("Malformed JSON must not read storage")):
            for raw in malformed:
                with self.subTest(raw=raw[:120]):
                    self.assert_error("invalid_request", raw=raw)

    def test_input_byte_limit_depth_and_invalid_utf8_are_rejected(self):
        too_many_bytes = json.dumps(self.request(parameters={"query": "é" * 33_000}), ensure_ascii=False)
        self.assertLess(len(too_many_bytes), 65_536)
        self.assertGreater(len(too_many_bytes.encode("utf-8")), 65_536)
        deep = "[" * 18 + "0" + "]" * 18
        for raw in (too_many_bytes, deep, b"{\xff}"):
            with self.subTest(size=len(raw)):
                self.assert_error("invalid_request", raw=raw)

    def test_valid_request_at_exact_input_limit_and_error_correlation(self):
        encoded = json.dumps(self.request()).encode("utf-8")
        padded = encoded + b" " * (65_536 - len(encoded))
        code, response = self.invoke(raw=padded)
        self.assertEqual((code, response["status"], response["request_id"]),
                         (0, "complete", "test-request:1"))
        invalid = self.request(parameters={"query": "example", "limit": 0}, request_id="integration:retry-42")
        response = self.assert_error("invalid_parameters", request=invalid)
        self.assertEqual((response["request_id"], response["operation"]), ("integration:retry-42", "search"))

    def test_invalid_search_parameters_cannot_select_scope_paths_or_execute_operations(self):
        invalid = [{}, {"query": "x"}, {"query": "bad\nquery"}, {"query": 123},
                   {"query": "example", "offset": True}, {"query": "example", "offset": -1},
                   {"query": "example", "offset": 1_000_001}, {"query": "example", "limit": False},
                   {"query": "example", "limit": 0}, {"query": "example", "limit": 501},
                   {"query": "example", "include_inactive": 1}, {"query": "example", "kinds": "domain"},
                   {"query": "example", "kinds": []}, {"query": "example", "kinds": ["missing"]},
                   {"query": "example", "data_dir": "/private"}, {"query": "example", "tenant_id": "other"},
                   {"query": "example", "command": "collect example.com"}]
        with patch("sqlite3.connect", side_effect=AssertionError("Invalid parameters must not read storage")):
            for parameters in invalid:
                with self.subTest(parameters=parameters):
                    self.assert_error("invalid_parameters", request=self.request(parameters=parameters))

    def test_source_parameters_reject_invalid_freshness_and_false_authorization_scope(self):
        invalid = [{"stale_after_hours": True}, {"stale_after_hours": 0}, {"stale_after_hours": 8761},
                   {"domain": "https://example.com"}, {"domain": 1},
                   {"tenant_id": "other"}, {"organization": str(uuid4())}]
        with patch("sqlite3.connect", side_effect=AssertionError("Invalid source request must not read storage")):
            for parameters in invalid:
                with self.subTest(parameters=parameters):
                    self.assert_error("invalid_parameters", request=self.request("sources.status", parameters))

    def test_record_reference_rejects_unknown_namespace_type_and_path_fields(self):
        reference = {"kind": "domain", "record_type": "registered_domain",
                     "namespace": "local-assets", "record_id": self.asset.id}
        invalid = [{}, {"reference": "../private"}, {"reference": {**reference, "namespace": "other-tenant"}},
                   {"reference": {**reference, "record_type": "__class__"}},
                   {"reference": {**reference, "path": "/private/file"}},
                   {"reference": reference, "offset": True}, {"reference": reference, "limit": 501}]
        with patch("sqlite3.connect", side_effect=AssertionError("Invalid reference must not read storage")):
            for parameters in invalid:
                with self.subTest(parameters=parameters):
                    self.assert_error("invalid_parameters", request=self.request("record.get", parameters))

    def test_describe_is_valid_machine_output_and_needs_no_data_directory(self):
        missing = self.root / "manifest has no database"
        before = self.files()
        code, response = self.invoke(raw="not JSON and must not be read", data_dir=missing, arguments=("--describe",))
        self.assertEqual((code, response["status"], response["operation"], response["request_id"]),
                         (0, "complete", "describe", None))
        manifest = response["data"]
        self.assertIn("operations", manifest)
        for operation in ("search", "record.get", "sources.status"):
            self.assertIn(operation, json.dumps(manifest["operations"]))
        self.assertFalse(missing.exists())
        self.assertEqual(self.files(), before)

    def test_unexpected_failure_is_single_safe_error_without_exception_details(self):
        with patch("xti.application.engine.EngineReadService.execute", side_effect=RuntimeError("SECRET-TRACE /private/key")):
            response = self.assert_error("internal_error", exit_code=1)
        self.assertNotIn("SECRET-TRACE", json.dumps(response))
        self.assertNotIn("/private/key", json.dumps(response))

    def test_interrupt_is_single_machine_response(self):
        with patch("xti.application.engine.EngineReadService.execute", side_effect=KeyboardInterrupt):
            self.assert_error("interrupted", exit_code=130)

    def test_output_cap_reports_error_without_partial_json_or_file_mutation(self):
        before = self.files()
        with patch("xti.interfaces.engine.MAX_RESPONSE_BYTES", 1024):
            self.assert_error("response_too_large", request=self.request("sources.status", {}), exit_code=1)
        self.assertEqual(self.files(), before)

    def test_existing_json_cli_keeps_original_envelope_and_error_stream(self):
        before = self.files()
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--data-dir", str(self.data), "--json", "search", "example", "--kind", "domain"])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        original = json.loads(stdout.getvalue())
        self.assertEqual(set(original), {"ok", "data"})
        self.assertTrue(original["ok"])
        self.assertNotIn("reference", original["data"]["results"][0])
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--data-dir", str(self.data), "--json", "search", "x"])
        self.assertEqual((code, stdout.getvalue()), (2, ""))
        self.assertEqual(json.loads(stderr.getvalue())["error"]["code"], "validation_error")
        self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
