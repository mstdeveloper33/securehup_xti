"""Readiness must preserve source evidence and never write or contact a source."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path
import shlex
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.source_readiness import (
    LocalSourceInstallationInspector,
    SQLiteSourceReadinessRepository,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_brand_username_watches import SQLiteBrandUsernameWatchRepository
from xti.adapters.sqlite_cooldowns import SQLiteCooldownRepository
from xti.adapters.sqlite_cti_feeds import SQLiteCtiFeedRepository
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.application.brand_username_watches import BrandUsernameWatchService
from xti.domain.assets import ValidationError
from xti.domain.cti_feeds import CtiFeedSnapshot, FEODO_SOURCE, FEODO_URL
from xti.domain.discovery import QueryResult, ScanResult
from xti.domain.findings import ImportSummary
from xti.domain.surface import SurfaceDiscoveryRunRequest
from xti.interfaces.cli import build_parser
from xti.ports.discovery import SourceError
from tests.test_brand_username_watches import FakeSource, FakeSherlockSource
from tests.test_mitre_attack import snapshot as attack_snapshot


NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


class SourceReadinessAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.repository = SQLiteSourceReadinessRepository(self.path, self.root / "project")

    def rows(self, domain=None):
        with patch("socket.create_connection", side_effect=AssertionError("network")), \
             patch("subprocess.run", side_effect=AssertionError("process")):
            return {item.identifier: item for item in self.repository.snapshot(domain=domain).sources}

    def scan(self, provider, domain, status):
        repository = SQLiteJobRepository(self.path)
        job = repository.create((domain,), False, provider, "fixture-v1")
        attempt = repository.start(job.id)
        if status == "failed":
            return repository.finish(attempt.id, "failed", error="Source timeout")
        query = QueryResult(domain, "https://crt.sh/", "complete", 0, 0, None, ())
        return repository.finish(attempt.id, "complete", result=ScanResult(
            (domain,), NOW.isoformat(), (NOW + timedelta(seconds=1)).isoformat(),
            "complete", (query,), ImportSummary(0, 0, 0, 0, 0), (),
        ))

    def test_missing_database_and_tools_are_reported_without_creating_paths(self):
        result = self.repository.snapshot()
        self.assertEqual(result.storage_state, "not_initialized")
        self.assertEqual(len({source.identifier for source in result.sources}), len(result.sources))
        self.assertTrue({'enrichment:circl', 'enrichment:urlscan'}.issubset(
            {source.identifier for source in result.sources}))
        self.assertFalse(self.path.parent.exists())
        self.assertFalse((self.root / "project").exists())
        rows = self.rows()
        self.assertEqual({key for key in rows if key.startswith("warninglist:")},
                         {"warninglist:cloudflare", "warninglist:rfc1918", "warninglist:rfc3849", "warninglist:rfc6761"})
        for key in ("social:maigret", "social:sherlock", "surface:theharvester"):
            self.assertEqual(rows[key].installation, "missing")
        self.assertEqual(rows["cti:attack"].latest_status, "unknown")
        self.assertIsNone(rows["cti:attack"].last_success_at)

    def test_scan_source_domain_and_previous_success_stay_separate(self):
        self.storage.initialize()
        self.storage.add("example.com")
        self.storage.add("example.net")
        success = self.scan("crt.sh", "example.com", "complete")
        failure = self.scan("crt.sh", "example.com", "failed")
        self.scan("urlscan", "example.com", "complete")
        self.scan("crt.sh", "example.net", "complete")
        before = self.path.read_bytes()
        global_rows = self.rows()
        scoped = self.rows("example.com")
        self.assertEqual(global_rows["scan:crt.sh"].latest_status, "complete")
        self.assertIn("example.net", global_rows["scan:crt.sh"].scope)
        self.assertEqual(scoped["scan:crt.sh"].latest_status, "failed")
        self.assertEqual(scoped["scan:crt.sh"].last_attempt_at, failure.started_at)
        self.assertEqual(scoped["scan:crt.sh"].last_success_at, success.finished_at)
        self.assertEqual(scoped["scan:urlscan"].latest_status, "complete")
        self.assertEqual(scoped["scan:urlscan"].record_count, 0)
        self.assertEqual(scoped["surface:crt.sh"].latest_status, "never")
        self.assertEqual(self.path.read_bytes(), before)

    def test_surface_failed_source_does_not_hide_completed_empty_result(self):
        self.storage.initialize()
        asset, _ = self.storage.add("example.com")
        repository = SQLiteSurfaceCandidateRepository(self.path)
        for provider, status in (("crt.sh", "complete"), ("theharvester", "failed")):
            repository.record_discovery(asset.id, asset.value, (), SurfaceDiscoveryRunRequest(
                status, "https://crt.sh/", NOW.isoformat(),
                (NOW + timedelta(seconds=1)).isoformat(), 0, 0, 0, (), 0,
                "Archive error" if status == "failed" else None, provider,
            ))
        rows = self.rows("example.com")
        self.assertEqual(rows["surface:crt.sh"].latest_status, "complete")
        self.assertEqual(rows["surface:crt.sh"].record_count, 0)
        self.assertEqual(rows["surface:theharvester"].latest_status, "failed")
        self.assertEqual(rows["surface:theharvester"].installation, "missing")
        self.assertEqual(rows["surface:theharvester"].next_command, "./scripts/setup-harvester")

    def test_global_previous_success_never_leaks_across_domain_or_watch_scope(self):
        self.storage.initialize()
        asset_a, _ = self.storage.add("example.com")
        asset_b, _ = self.storage.add("example.net")
        self.scan("crt.sh", asset_a.value, "complete")
        self.scan("crt.sh", asset_b.value, "failed")
        surface = SQLiteSurfaceCandidateRepository(self.path)
        for asset, status in ((asset_a, "complete"), (asset_b, "failed")):
            surface.record_discovery(asset.id, asset.value, (), SurfaceDiscoveryRunRequest(
                status, "https://crt.sh/", NOW.isoformat(),
                (NOW + timedelta(seconds=1)).isoformat(), 0, 0, 0, (), 0,
                "Source timeout" if status == "failed" else None, "crt.sh",
            ))
        brand = BrandUsernameWatchService(
            SQLiteBrandUsernameWatchRepository(self.path),
            FakeSource({}, SourceError("Source unavailable")), clock=lambda: NOW,
        )
        first = brand.add("first brand", "firstbrand", platforms=("GitHub",)).watch
        second = brand.add("second brand", "secondbrand", platforms=("GitHub",)).watch
        brand.run(first.id)
        brand.run(second.id)
        rows = self.rows()
        for key in ("scan:crt.sh", "surface:crt.sh", "social:maigret"):
            self.assertEqual(rows[key].latest_status, "failed")
            self.assertIsNone(rows[key].last_success_at)

    def test_never_run_social_command_is_actionable_and_all_cli_suggestions_parse(self):
        self.storage.initialize()
        brand = BrandUsernameWatchService(
            SQLiteBrandUsernameWatchRepository(self.path), FakeSource({}), clock=lambda: NOW,
        )
        with patch.object(self.repository.installations, "inspect", return_value=("ready", None)):
            rows = self.rows()
            self.assertEqual(rows["social:maigret"].next_command, "./xti brand watch-add --help")
            parser = build_parser()
            for row in rows.values():
                command = shlex.split(row.next_command)
                if command[0] != "./xti":
                    continue
                with redirect_stdout(StringIO()):
                    if "--help" in command:
                        with self.assertRaises(SystemExit) as caught:
                            parser.parse_args(command[1:])
                        self.assertEqual(caught.exception.code, 0)
                    else:
                        parser.parse_args(command[1:])
            watch = brand.add("first brand", "firstbrand", platforms=("GitHub",)).watch
            self.assertEqual(self.rows()["social:maigret"].next_command,
                             f"./xti brand watch-run {watch.id}")

    def test_feed_previous_success_survives_more_than_recent_run_limit(self):
        self.storage.initialize()
        feed = SQLiteCtiFeedRepository(self.path)
        success = feed.apply(CtiFeedSnapshot(
            FEODO_SOURCE, FEODO_URL, "a" * 64, 0, (),
        ), started_at=NOW.isoformat(), finished_at=(NOW + timedelta(seconds=1)).isoformat())
        for index in range(101):
            started = NOW + timedelta(minutes=index + 1)
            feed.record_failure(started_at=started.isoformat(),
                                finished_at=(started + timedelta(seconds=1)).isoformat(),
                                error="Source temporarily unavailable")
        before = self.path.read_bytes()
        rows = self.rows()
        self.assertEqual(rows["ioc:feodo"].latest_status, "failed")
        self.assertEqual(rows["ioc:feodo"].last_success_at, success.finished_at)
        self.assertEqual(rows["ioc:certpl"].latest_status, "never")
        self.assertEqual(self.path.read_bytes(), before)

    def test_social_watch_sources_keep_independent_status_and_uncertainty(self):
        self.storage.initialize()
        for key, source_type, platform in (
            ("maigret", FakeSource, "GitHub"), ("sherlock", FakeSherlockSource, "Carrd"),
        ):
            service = BrandUsernameWatchService(
                SQLiteBrandUsernameWatchRepository(self.path), source_type({}),
                clock=lambda: NOW,
            )
            watch = service.add(f"test {key}", "testbrand", platforms=(platform,), source_key=key).watch
            service.run(watch.id)
        rows = self.rows()
        for key in ("social:maigret", "social:sherlock"):
            self.assertEqual(rows[key].latest_status, "complete")
            self.assertEqual(rows[key].record_count, 0)
            self.assertIn("hesap yokluğu anlamına gelmez", " ".join(rows[key].notes))

    def test_claim_sources_keep_failures_separate_and_attack_has_no_attempt_history(self):
        self.storage.initialize()
        SQLiteRansomwareClaimRepository(self.path).record_failure(
            started_at=NOW.isoformat(), finished_at=(NOW + timedelta(seconds=1)).isoformat(),
            error="ThreatCluster unavailable",
        )
        rows = self.rows()
        self.assertEqual(rows["ransomware:threatcluster"].latest_status, "failed")
        self.assertEqual(rows["ransomware:ransomlook"].latest_status, "never")
        SQLiteCtiKnowledgeRepository(self.path).sync_attack_snapshot(
            attack_snapshot(), recorded_at=NOW.isoformat(),
        )
        rows = self.rows()
        self.assertEqual(rows["cti:attack"].latest_status, "unknown")
        self.assertEqual(rows["cti:attack"].last_success_at, NOW.isoformat())
        self.assertIsNone(rows["cti:attack"].last_attempt_at)

    def test_cooldown_is_preserved_without_network_or_write(self):
        self.storage.initialize()
        deadline = (NOW + timedelta(hours=1)).isoformat()
        SQLiteCooldownRepository(self.path).extend("crt.sh", deadline, NOW.isoformat(), "rate_limit")
        before = self.path.read_bytes()
        rows = self.rows()
        self.assertEqual(rows["scan:crt.sh"].cooldown_until, deadline)
        self.assertEqual(rows["surface:crt.sh"].cooldown_until, deadline)
        self.assertIsNone(rows["scan:urlscan"].cooldown_until)
        self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_history_unknown_domain_and_symlink_fail_without_repair(self):
        self.storage.initialize()
        with self.assertRaises(ValidationError):
            self.rows("missing.example")
        self.storage.add("example.com")
        self.scan("crt.sh", "example.com", "complete")
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute("UPDATE scan_attempts SET queries='invalid'")
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.rows()
        self.assertEqual(self.path.read_bytes(), before)
        alias = self.root / "alias.db"
        alias.symlink_to(self.path)
        with self.assertRaises(StorageError):
            SQLiteSourceReadinessRepository(alias, self.root).snapshot()


class SourceInstallationInspectorTests(unittest.TestCase):
    def test_metadata_catalog_and_commit_are_checked_without_executing_tool(self):
        from xti.adapters.source_readiness import MAIGRET_COMMIT, MAIGRET_VERSION
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            venv = project / ".venv"
            site = venv / "lib" / "python3.13" / "site-packages"
            catalog = site / "maigret" / "resources" / "data.json"
            catalog.parent.mkdir(parents=True)
            payload = b"x" * 3_329_634
            catalog.write_bytes(payload)
            (venv / "bin").mkdir()
            for name in ("python", "maigret"):
                executable = venv / "bin" / name
                executable.write_text("fixture")
                executable.chmod(0o700)

            class Installed:
                metadata = {"Name": "maigret"}
                version = MAIGRET_VERSION
                commit = MAIGRET_COMMIT
                def locate_file(self, value):
                    return site / value
                def read_text(self, _name):
                    return json.dumps({"url": "https://github.com/soxoj/maigret.git", "vcs_info": {
                        "vcs": "git", "commit_id": self.commit, "requested_revision": self.commit,
                    }})

            installed = Installed()
            inspector = LocalSourceInstallationInspector(project)
            with patch("xti.adapters.source_readiness.distributions", return_value=(installed,)), \
                 patch("xti.adapters.source_readiness.MAIGRET_SHA", hashlib.sha256(payload).hexdigest()), \
                 patch("subprocess.run", side_effect=AssertionError("tool executed")):
                self.assertEqual(inspector.inspect("maigret"), ("ready", None))
                installed.commit = "0" * 40
                self.assertEqual(inspector.inspect("maigret")[0], "invalid")
                installed.commit = MAIGRET_COMMIT
                catalog.write_bytes(payload[:-1])
                self.assertEqual(inspector.inspect("maigret")[0], "invalid")


if __name__ == "__main__":
    unittest.main()
