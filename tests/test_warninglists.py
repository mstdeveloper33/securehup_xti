"""Acquisition, persistence, provenance and company-scoped reference context."""

from contextlib import closing, redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
import json
import hashlib
from pathlib import Path
import shlex
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from uuid import uuid4

from xti.adapters.company_workspaces import resolve_company_workspace
from xti.adapters.misp_warninglists import MispWarninglistSource, REVISION_URL
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_warninglists import SQLiteWarninglistRepository
from xti.adapters.sqlite_research import SQLiteResearchRepository
from xti.application.research import ResearchService, research_data
from xti.application.warninglists import WarninglistService
from xti.domain.assets import ValidationError
from xti.domain.warninglists import POLICIES, matching_entries, parse_warninglist, source_url
from xti.interfaces.cli import main
from xti.interfaces.warninglists import warninglist_lines
from xti.ports.discovery import SourceError


NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
REVISION = "a" * 40
VALUES = {"cloudflare": ["104.16.0.0/13", "2606:4700::/32"],
          "rfc1918": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
          "rfc3849": ["2001:DB8::/32"], "rfc6761": ["example.com", "test"]}


def body(identifier, **changes):
    data = {"name": "Fixture " + identifier, "description": "Controlled reference list fixture",
            "type": POLICIES[identifier].matching_type, "version": 1, "list": VALUES[identifier],
            "category": "known" if identifier == "cloudflare" else "false_positive"}
    return json.dumps({**data, **changes}).encode()


class Source:
    def __init__(self):
        self.calls = []
        self.payloads = {key: body(key) for key in POLICIES}
        self.failure = None

    def resolve_revision(self):
        self.calls.append("revision")
        if self.failure:
            raise self.failure
        return REVISION

    def fetch(self, identifier, revision):
        self.calls.append((identifier, revision))
        result = self.payloads[identifier]
        if isinstance(result, Exception):
            raise result
        return result


class WarninglistTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.data = self.root / "selected data"
        self.path = self.data / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.repository = SQLiteWarninglistRepository(self.path)
        self.source = Source()
        self.now = NOW
        self.service = WarninglistService(self.repository, self.source, clock=lambda: self.now)
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("No unplanned network")))
        self.enterContext(patch("subprocess.Popen", side_effect=AssertionError("No subprocess")))

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def lookup(self, value="104.21.6.71", kind="ip", **options):
        return self.service.lookup(indicator_type=kind, value=value, **options)

    def invoke(self, arguments, request=None):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch("sys.stdin", StringIO(json.dumps(request))):
            code = main(arguments)
        return code, out.getvalue(), err.getvalue()

    def request(self, operation="warninglists.lookup", parameters=None):
        return {"contract_version": 1, "request_id": "warninglist-test", "operation": operation,
                "parameters": {"indicator_type": "ip", "value": "104.21.6.71"} if parameters is None else parameters}

    def test_refresh_preserves_all_receipts_and_lookup_provenance_without_writes(self):
        first = self.service.sync()
        self.assertEqual(first["status"], "complete")
        self.assertEqual(self.source.calls, ["revision", *((key, REVISION) for key in POLICIES)])
        before = self.files()
        result = self.lookup()
        self.assertEqual(result["status"], "matched")
        self.assertTrue(result["coverage_complete"])
        self.assertEqual(result["matches"][0]["matched_entries"], ["104.16.0.0/13"])
        row = result["lists"][0]
        self.assertEqual(row["revision"], REVISION)
        self.assertEqual(row["license"], "CC0-1.0")
        self.assertEqual(row["success_run_id"], result["matches"][0]["run_id"])
        self.assertEqual(self.files(), before)
        self.assertEqual(self.source.calls.count("revision"), 1)

    def test_missing_stale_empty_and_failed_have_distinct_context(self):
        self.assertEqual(self.lookup()["status"], "incomplete")
        self.service.sync()
        self.assertEqual(self.lookup("8.8.8.8")["status"], "no_match")
        self.now += timedelta(days=8)
        stale = self.lookup()
        self.assertEqual(stale["status"], "matched")
        self.assertFalse(stale["coverage_complete"])
        self.assertEqual(stale["lists"][0]["freshness"], "stale")
        self.source.payloads["cloudflare"] = SourceError("Provider timeout")
        result = self.service.sync()
        self.assertEqual(result["status"], "partial")
        failed = self.lookup()
        self.assertEqual(failed["lists"][0]["latest_status"], "failed")
        self.assertEqual(failed["lists"][0]["error"], "Provider timeout")
        self.assertEqual(failed["matches"], stale["matches"])
        self.assertFalse(failed["coverage_complete"])

    def test_update_removes_only_new_membership_and_retains_historical_payload(self):
        first = self.service.sync(["cloudflare"])["runs"][0]
        self.source.payloads["cloudflare"] = body("cloudflare", version=2, list=["203.0.113.0/24"])
        second = self.service.sync(["cloudflare"])["runs"][0]
        self.assertFalse(self.lookup()["matches"])
        self.assertEqual(self.service.show(first["id"])["entries"], VALUES["cloudflare"])
        self.assertEqual(self.service.show(second["id"])["entries"], ["203.0.113.0/24"])
        history = self.service.history("cloudflare", limit=1)
        self.assertTrue(history["has_more"])
        self.assertEqual(history["runs"][0]["id"], second["id"])

    def test_repeated_payload_deduplicated_but_each_refresh_has_receipt(self):
        self.service.sync(["cloudflare"])
        self.service.sync(["cloudflare"])
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM warninglist_snapshots").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM warninglist_runs").fetchone()[0], 2)

    def test_identical_payloads_keep_separate_list_provenance(self):
        shared = body("rfc1918")
        self.source.payloads.update(cloudflare=shared, rfc1918=shared)
        result = self.service.sync(["cloudflare", "rfc1918"])
        self.assertEqual(result["status"], "complete")
        matches = self.lookup("10.0.0.1")["matches"]
        self.assertEqual({match["list_id"] for match in matches}, {"cloudflare", "rfc1918"})
        self.assertEqual(len({match["run_id"] for match in matches}), 2)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM warninglist_snapshots").fetchone()[0], 1)

    def test_invalid_document_and_revision_rollback_preserve_previous_snapshot(self):
        self.source.payloads["cloudflare"] = body("cloudflare", version=2)
        first = self.service.sync(["cloudflare"])["runs"][0]
        for payload in (b'{"broken":true}', body("cloudflare", list=[]), body("cloudflare", version=1)):
            self.source.payloads["cloudflare"] = payload
            result = self.service.sync(["cloudflare"])
            self.assertEqual(result["status"], "failed")
            self.assertEqual(self.lookup()["matches"][0]["run_id"], first["id"])

    def test_revision_failure_records_no_success_and_fetches_no_list(self):
        self.source.failure = SourceError("Provider unavailable")
        result = self.service.sync()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.source.calls, ["revision"])
        self.assertTrue(all(run["snapshot_sha256"] is None for run in result["runs"]))

    def test_new_context_is_not_ioc_allowlist_or_threat_mutation(self):
        self.service.sync()
        with closing(sqlite3.connect(self.path)) as connection:
            for table in ("cti_indicators", "allowlist_entries", "findings", "cti_relationships"):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        graph = research_data(ResearchService(SQLiteResearchRepository(self.path), clock=lambda: NOW).show(
            indicator_type="ip", value="104.21.6.71"))
        self.assertEqual(graph["status"], "not_recorded")
        self.assertEqual(graph["edges"], [])
        self.assertTrue(graph["nodes"][0]["warninglist_matches"])
        self.assertTrue(graph["warninglists"]["coverage_complete"])

    def test_research_snapshot_guard_includes_reference_changes(self):
        service = ResearchService(SQLiteResearchRepository(self.path), clock=lambda: NOW)
        old = service.show(indicator_type="ip", value="104.21.6.71")
        self.service.sync(["cloudflare"])
        from xti.domain.research import ResearchSnapshotChanged
        with self.assertRaises(ResearchSnapshotChanged):
            service.show(indicator_type="ip", value="104.21.6.71", expected_snapshot=old.snapshot_id)

    def test_invalid_options_and_missing_db_fail_before_network(self):
        for values in ([], ["unknown"], ["cloudflare", "cloudflare"]):
            with self.assertRaises(ValidationError):
                self.service.sync(values)
        absent = self.root / "absent" / "xti.db"
        with self.assertRaises(StorageError):
            WarninglistService(SQLiteWarninglistRepository(absent), self.source).sync()
        self.assertEqual(self.source.calls, [])
        self.assertFalse(absent.parent.exists())
        for options in ({"stale_after_hours": True}, {"stale_after_hours": 0}):
            with self.assertRaises(ValidationError):
                self.lookup(**options)

    def test_corrupt_payload_or_receipt_fails_without_repair(self):
        self.service.sync()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE warninglist_snapshots SET content=?", (body("cloudflare", version=9),))
            connection.commit()
        before = self.files()
        with self.assertRaises(StorageError):
            self.lookup()
        self.assertEqual(self.files(), before)

    def test_backup_restore_preserves_payload_receipts_and_lookup(self):
        self.service.sync()
        previous = self.lookup()
        backup, target = self.root / "backup.db", self.root / "restored" / "xti.db"
        self.storage.backup(backup)
        SQLiteAssetRepository.restore(backup, target)
        restored = WarninglistService(SQLiteWarninglistRepository(target), clock=lambda: NOW)
        self.assertEqual(restored.lookup(indicator_type="ip", value="104.21.6.71"), previous)

    def test_72_migration_backs_up_and_preserves_assets(self):
        asset, _ = self.storage.add("example.com")
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("DROP TABLE warninglist_runs")
            connection.execute("DROP TABLE warninglist_snapshots")
            from tests.case_evidence_v79_fixture import case_evidence_layout_v79
            case_evidence_layout_v79(connection)
            connection.execute("PRAGMA user_version=72")
            connection.commit()
        before = self.files()
        with self.assertRaises(StorageError):
            self.repository.read()
        self.assertEqual(before, self.files())
        result = self.storage.migrate()
        from xti.adapters.schema import SCHEMA_VERSION
        self.assertEqual((result["from_version"], result["to_version"]), (72, SCHEMA_VERSION))
        with closing(sqlite3.connect(result["backup"])) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 72)
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_schema WHERE name='warninglist_runs'").fetchone())
        self.assertEqual(self.storage.list(), [asset])
        self.assertTrue(all(state.latest_run is None for state in self.repository.read()))
        self.assertFalse(self.storage.migrate()["changed"])

    def test_failed_migration_rolls_back_and_keeps_recovery_copy(self):
        with closing(sqlite3.connect(self.path)) as connection:
            from tests.case_evidence_v79_fixture import case_evidence_layout_v79
            case_evidence_layout_v79(connection)
            connection.execute("PRAGMA user_version=72")
            connection.commit()
        with patch("xti.adapters.sqlite.create_warninglist_schema", side_effect=RuntimeError("Fixture interruption")):
            with self.assertRaises(RuntimeError):
                self.storage.migrate()
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 72)
        self.assertEqual(len(list((self.data / "backups").glob("*.db"))), 1)

    def test_old_version_with_populated_future_tables_rejected(self):
        self.service.sync(["cloudflare"])
        with closing(sqlite3.connect(self.path)) as connection:
            from tests.case_evidence_v79_fixture import case_evidence_layout_v79
            case_evidence_layout_v79(connection)
            connection.execute("PRAGMA user_version=72")
            connection.commit()
        with self.assertRaises(StorageError):
            self.storage.migrate()

    def test_cli_sync_lookup_provenance_navigation_and_source_status(self):
        with patch("xti.interfaces.warninglists.make_warninglist_service", return_value=self.service):
            code, out, err = self.invoke(["--data-dir", str(self.data), "--json", "warninglists", "sync"])
        self.assertEqual((code, err), (0, ""), out)
        before = self.files()
        code, out, err = self.invoke(["--data-dir", str(self.data), "--json", "warninglists", "lookup", "104.21.6.71", "--type", "ip"])
        self.assertEqual((code, err), (0, ""), out)
        data = json.loads(out)["data"]
        for line in warninglist_lines(data, data_dir=self.data):
            if "Ayrıntı: " in line:
                command = shlex.split(line.split("Ayrıntı: ", 1)[1])[1:]
                code, text, err = self.invoke(command)
                self.assertEqual((code, err), (0, ""), text)
        code, out, err = self.invoke(["--data-dir", str(self.data), "--json", "sources", "status"])
        self.assertEqual((code, err), (0, ""), out)
        self.assertIn("warninglist:cloudflare", out)
        run = self.repository.read()[0].successful_run
        code, out, err = self.invoke(["--data-dir", str(self.data), "warninglists", "run-show", run.id])
        self.assertEqual((code, err), (0, ""), out)
        for expected in (run.snapshot_sha256, source_url("cloudflare", REVISION), "Kaynak commit", "CC0-1.0"):
            self.assertIn(expected, out)
        self.assertEqual(before, self.files())

    def test_engine_read_contract_and_input_scope_rejection(self):
        self.service.sync()
        args = ["--data-dir", str(self.data), "engine"]
        code, out, err = self.invoke(args + ["--describe"])
        self.assertEqual((code, err), (0, ""), out)
        manifest = json.loads(out)["data"]
        self.assertGreaterEqual(set(manifest["operations"]),
                                {"warninglists.status", "warninglists.lookup", "warninglists.run.get"})
        self.assertEqual(manifest["warninglists"]["refresh_via"], "operator_cli")
        for request in (self.request(), self.request("warninglists.status", {}),
                        self.request("warninglists.run.get", {"run_id": self.repository.read()[0].successful_run.id, "limit": 1})):
            code, out, err = self.invoke(args, request)
            self.assertEqual((code, err), (0, ""), out)
        for parameters in ({"indicator_type": "ip", "value": "104.21.6.71", "company": "other"},
                           {"indicator_type": "url", "value": "https://example.com"},
                           {"indicator_type": "ip", "value": "104.21.0.0/16"}):
            code, out, err = self.invoke(args, self.request(parameters=parameters))
            self.assertEqual(code, 2, out)
            self.assertEqual(json.loads(out)["error"]["code"], "invalid_parameters")
        code, out, err = self.invoke(args, self.request("warninglists.sync", {}))
        self.assertEqual(json.loads(out)["error"]["code"], "unsupported_operation")
        code, out, err = self.invoke(args, self.request("warninglists.run.get", {"run_id": str(uuid4())}))
        self.assertEqual(code, 3, out)
        self.assertEqual(json.loads(out)["error"]["code"], "not_found")

    def test_partial_sync_exit_and_last_success_source_visibility(self):
        first = self.service.sync(["cloudflare"])["runs"][0]
        self.source.payloads["cloudflare"] = SourceError("Provider timeout")
        with patch("xti.interfaces.warninglists.make_warninglist_service", return_value=self.service):
            code, out, err = self.invoke(["--data-dir", str(self.data), "--json", "warninglists", "sync"])
        self.assertEqual((code, err), (3, ""))
        data = json.loads(out)
        self.assertFalse(data["ok"])
        self.assertEqual(data["data"]["status"], "partial")
        row = self.service.status()["lists"][0]
        self.assertEqual(row["latest_status"], "failed")
        self.assertEqual(row["success_run_id"], first["id"])
        code, out, err = self.invoke(["--data-dir", str(self.data), "sources", "status"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Provider timeout", out)

    def test_company_catalogs_do_not_fallback_to_other_or_personal_storage(self):
        self.service.sync()
        root = self.root / "companies"
        for company in ("first", "second"):
            code, out, err = self.invoke(["platform", "provision", "--root", str(root), "--company", company])
            self.assertEqual((code, err), (0, ""), out)
        first = resolve_company_workspace(root, "first")
        service = WarninglistService(SQLiteWarninglistRepository(first.database), self.source, clock=lambda: NOW)
        run = service.sync(["cloudflare"])["runs"][0]
        for company, count in (("first", 1), ("second", 0)):
            code, out, err = self.invoke(["platform", "request", "--root", str(root), "--company", company], self.request())
            self.assertEqual((code, err), (0, ""), out)
            self.assertEqual(len(json.loads(out)["data"]["matches"]), count)
        code, out, err = self.invoke(["platform", "request", "--root", str(root), "--company", "second"],
                                     self.request("warninglists.run.get", {"run_id": run["id"]}))
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["error"]["code"], "not_found")
        self.assertIsNone(json.loads(out)["data"])


class WarninglistParserTests(unittest.TestCase):
    def test_ipv4_ipv6_and_hostname_label_boundaries(self):
        cloud = parse_warninglist("cloudflare", body("cloudflare"))
        self.assertTrue(matching_entries(cloud, "ipv4", "104.21.6.71"))
        self.assertTrue(matching_entries(cloud, "ipv6", "2606:4700::1"))
        self.assertFalse(matching_entries(cloud, "ipv4", "104.24.0.0"))
        special = parse_warninglist("rfc6761", body("rfc6761"))
        for value in ("example.com", "www.example.com", "demo.test"):
            self.assertTrue(matching_entries(special, "domain", value))
        for value in ("notexample.com", "example.com.evil.tested", "test.evil.com"):
            self.assertFalse(matching_entries(special, "domain", value))

    def test_malformed_bounded_complete_payload_rejection(self):
        bad = (b'{}', b'{"name":"x","name":"y"}', b'\xff', b'[' * 1500,
               body("cloudflare", version=True), body("cloudflare", list=["10.0.0.1/8"]),
               body("cloudflare", list=["10.0.0.0/8", "10.0.0.0/8"]),
               body("cloudflare", type="regex"), body("cloudflare", list=["127.0.0.1"]),
               body("cloudflare", matching_attributes=["sha256"]),
               body("cloudflare", description="terminal\x1b[31m"),
               body("cloudflare", extra="unknown"), b'x' * (1024 * 1024 + 1))
        for content in bad:
            with self.subTest(content=content[:90]), self.assertRaises(ValidationError):
                parse_warninglist("cloudflare", content)
        for hostname in ("*.example.com", "example..com", "https://example.com", "éxample.com"):
            with self.assertRaises(ValidationError):
                parse_warninglist("rfc6761", body("rfc6761", list=[hostname]))


class Response(BytesIO):
    def __init__(self, url, content, *, headers=None, status=200):
        super().__init__(content)
        self.url, self.headers, self.status = url, headers or {}, status
    def geturl(self):
        return self.url


class Opener:
    def __init__(self):
        self.calls = []
        self.response = None
    def open(self, request, timeout):
        self.calls.append((request.full_url, timeout, dict(request.header_items())))
        if self.response is not None:
            value, self.response = self.response, None
            if isinstance(value, Exception):
                raise value
            return value
        value = json.dumps({"sha": REVISION}).encode() if request.full_url == REVISION_URL else body("cloudflare")
        if request.full_url.endswith('/README.md'):
            value = b'reviewed source and terms fixture'
        return Response(request.full_url, value)


class WarninglistHttpTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch('xti.adapters.misp_warninglists.REVIEWED_README_SHA256',
                                hashlib.sha256(b'reviewed source and terms fixture').hexdigest()))

    def test_only_commit_pinned_known_urls_no_target_value_or_retry(self):
        opener = Opener()
        source = MispWarninglistSource(opener=opener)
        revision = source.resolve_revision()
        source.fetch("cloudflare", revision)
        self.assertEqual([call[0] for call in opener.calls], [REVISION_URL,
            f'https://raw.githubusercontent.com/MISP/misp-warninglists/{REVISION}/README.md', source_url("cloudflare", REVISION)])
        self.assertTrue(all(timeout <= 15 for _, timeout, _ in opener.calls))
        self.assertFalse(any("Authorization" in headers for _, _, headers in opener.calls))

    def test_redirect_bad_status_compression_size_and_short_body_rejected(self):
        for response in (Response("https://127.0.0.1/", b'{}'),
                         Response(REVISION_URL, b'{}', status=302),
                         Response(REVISION_URL, b'{}', headers={"Content-Encoding": "gzip"}),
                         Response(REVISION_URL, b'{}', headers={"Content-Length": "300000"}),
                         Response(REVISION_URL, b'{}', headers={"Content-Length": "9" * 5000}),
                         Response(REVISION_URL, b'{}', headers={"Content-Length": "²"}),
                         Response(REVISION_URL, b'{}', headers={"Content-Length": "100"}),
                         Response(REVISION_URL, b'x' * (256 * 1024 + 1)),
                         HTTPError(REVISION_URL, 429, "rate limit", {}, None)):
            opener = Opener()
            opener.response = response
            with self.assertRaises(SourceError):
                MispWarninglistSource(opener=opener).resolve_revision()
            self.assertEqual(len(opener.calls), 1)

    def test_invalid_revision_manifest_cannot_start_file_requests(self):
        for content in (b'{"sha":"main"}', b'{"sha":null}', b'[]',
                        b'{"sha":"' + REVISION.encode() + b'","sha":"' + REVISION.encode() + b'"}'):
            opener = Opener()
            opener.response = Response(REVISION_URL, content)
            with self.assertRaises(SourceError):
                MispWarninglistSource(opener=opener).resolve_revision()
            self.assertEqual(len(opener.calls), 1)

    def test_changed_source_terms_block_new_revision_before_list_fetch(self):
        opener = Opener()
        with patch('xti.adapters.misp_warninglists.REVIEWED_README_SHA256', '0' * 64), self.assertRaisesRegex(SourceError, 'incelemesi'):
            MispWarninglistSource(opener=opener).resolve_revision()
        self.assertEqual(len(opener.calls), 2)
        self.assertFalse(any('/lists/' in url for url, _, _ in opener.calls))

    def test_total_budget_and_bad_revision_stop_before_list_fetch(self):
        opener = Opener()
        now = [0]
        source = MispWarninglistSource(opener=opener, monotonic=lambda: now[0])
        source.resolve_revision()
        now[0] = 61
        with self.assertRaises(SourceError):
            source.fetch("cloudflare", REVISION)
        self.assertEqual(len(opener.calls), 2)
        for revision in ("../main", "https://private", "A" * 40):
            with self.assertRaises(ValidationError):
                source.fetch("cloudflare", revision)


if __name__ == "__main__":
    unittest.main()
