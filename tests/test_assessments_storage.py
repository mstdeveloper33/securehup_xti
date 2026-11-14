"""Persist checks without losing original evidence, reviews or legacy jobs."""

from contextlib import closing
from dataclasses import asdict, replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import (
    APPLICATION_ID, ASSETS_DDL, FINDINGS_DDL, JOBS_DDL, SCHEMA_VERSION, validate_schema,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_assessments import SQLiteAssessmentRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.domain.assets import ValidationError
from xti.domain.enrichment import CertificateEvidence, ProbeResult
from xti.domain.findings import DomainInput, ImportDocument, MatchCandidate


def checked(domain="example-support.net", **changes):
    values = dict(
        domain=domain, started_at="2026-10-28T10:00:00+00:00",
        finished_at="2026-10-28T10:00:01+00:00", policy_version="https-head-v1",
        dns_status="resolved", addresses=("93.184.215.14",), tls_status="valid",
        http_status="responded", http_status_code=301, connected_address="93.184.215.14",
        errors=(), notes=("Yönlendirme izlenmedi.",),
    )
    values.update(changes)
    return ProbeResult(**values)


class AssessmentStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        asset, _ = self.assets.add("example.com")
        self.findings = SQLiteFindingRepository(self.path)
        self.findings.save_import(
            ImportDocument("https://crt.sh/?id=42", "hash-42", (
                DomainInput("example-support.net", "EXAMPLE-SUPPORT.NET", 1, None),
            )),
            (MatchCandidate(asset.id, asset.value, "example-support.net", "rule-v1", ("Test eşleşmesi",)),),
        )
        self.finding = self.findings.list_findings()[0]
        self.repo = SQLiteAssessmentRepository(self.path)

    def test_two_checks_preserve_original_evidence_and_all_reviews(self):
        before = self.findings.get_finding(self.finding.id)
        self.findings.review_finding(self.finding.id, "suspicious", "Kullanıcı değerlendirmesi")
        first = self.repo.append(self.finding.id, checked())
        self.findings.review_finding(self.finding.id, "uncertain", "Ek kanıt gerekli")
        second = self.repo.append(self.finding.id, checked(
            started_at="2026-10-28T11:00:00+00:00", finished_at="2026-10-28T11:00:02+00:00",
            tls_status="not_checked", http_status="not_checked", http_status_code=None,
            connected_address=None, dns_status="nxdomain", addresses=(), notes=(),
        ))
        details = SQLiteAssessmentRepository(self.path).details(self.finding.id)
        self.assertEqual(details.assessments, (first, second))
        self.assertEqual(details.details.observations, before.observations)
        self.assertEqual(details.details.finding.status, "uncertain")
        self.assertEqual([review.decision for review in details.details.reviews], ["suspicious", "uncertain"])
        self.assertEqual(self.repo.latest_by_finding(), {self.finding.id: second})
        self.assertEqual(self.assets.inspect()["assessment_count"], 2)

    def test_latest_is_last_inserted_even_after_clock_regression(self):
        first = self.repo.append(self.finding.id, checked())
        second = self.repo.append(self.finding.id, checked(
            started_at="2026-10-27T10:00:00+00:00", finished_at="2026-10-27T10:00:01+00:00",
        ))
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(self.repo.list(self.finding.id), (first, second))
        self.assertEqual(self.repo.latest_by_finding()[self.finding.id], second)

    def test_identical_checks_are_separate_observations_not_overwritten(self):
        first = self.repo.append(self.finding.id, checked())
        second = self.repo.append(self.finding.id, checked())
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(first.result, second.result)
        self.assertEqual(len(self.repo.list(self.finding.id)), 2)

    def test_certificate_round_trip_and_legacy_missing_field_are_supported(self):
        certificate = CertificateEvidence(
            "a" * 64, "01a2", "2026-10-01T00:00:00+00:00",
            "2026-12-31T23:59:59+00:00", "Fixture CA", "example-support.net",
            ("*.example-support.net", "example-support.net"),
        )
        saved = self.repo.append(self.finding.id, checked(certificate=certificate))
        self.assertEqual(self.repo.list(self.finding.id)[0].result.certificate, certificate)
        legacy = asdict(saved.result)
        legacy.pop("certificate")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE finding_assessments SET result = ? WHERE id = ?",
                (json.dumps(legacy), saved.id),
            )
        self.assertIsNone(self.repo.list(self.finding.id)[0].result.certificate)

    def test_invalid_certificate_evidence_is_rejected_before_writing(self):
        base = CertificateEvidence(
            "a" * 64, "01a2", "2026-10-01T00:00:00+00:00",
            "2026-12-31T23:59:59+00:00", "Fixture CA", "example-support.net",
            ("example-support.net",),
        )
        invalid = (
            replace(base, sha256="g" * 64),
            replace(base, serial_number="not-hex"),
            replace(base, not_after="2026-01-01T00:00:00+00:00"),
            replace(base, issuer="\x1b[31m"),
            replace(base, dns_names=("bad name",)),
        )
        for certificate in invalid:
            with self.subTest(certificate=certificate), self.assertRaises(ValidationError):
                self.repo.append(self.finding.id, checked(certificate=certificate))
        self.assertEqual(self.repo.list(self.finding.id), ())

    def test_backup_restore_keeps_checks_and_decisions_without_overwriting(self):
        self.findings.review_finding(self.finding.id, "dismissed", "Sahiplik incelendi")
        first = self.repo.append(self.finding.id, checked())
        backup = self.path.parent / "backup.db"
        self.assets.backup(backup)
        self.repo.append(self.finding.id, checked(http_status_code=404))
        restored = self.path.parent / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        copied = SQLiteAssessmentRepository(restored).details(self.finding.id)
        self.assertEqual(copied.assessments, (first,))
        self.assertEqual(copied.details.finding.status, "dismissed")
        self.assertEqual(len(copied.details.reviews), 1)
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(backup, self.path)
        self.assertEqual(len(self.repo.list(self.finding.id)), 2)

    def test_missing_and_mismatched_findings_do_not_create_or_change_evidence(self):
        before = self.findings.get_finding(self.finding.id)
        for identifier, result in (("missing", checked()), (self.finding.id, checked("another.net"))):
            with self.subTest(identifier=identifier, domain=result.domain):
                with self.assertRaises(ValidationError):
                    self.repo.append(identifier, result)
        for method in (self.repo.list, self.repo.details):
            with self.assertRaises(ValidationError):
                method("missing")
        self.assertEqual(self.repo.list(self.finding.id), ())
        self.assertEqual(self.findings.get_finding(self.finding.id), before)

    def test_invalid_probe_values_are_rejected_before_writing(self):
        cases = (
            {"domain": "EXAMPLE-SUPPORT.NET"}, {"domain": "xn--exampl-gva.net"},
            {"started_at": "2026-10-28T10:00:00"}, {"finished_at": "nonsense"},
            {"policy_version": ""}, {"dns_status": "safe"}, {"tls_status": "malicious"},
            {"http_status": "success"}, {"addresses": ()},
            {"addresses": ("93.184.215.14",) * 2}, {"addresses": ("not-an-ip",)},
            {"connected_address": "8.8.8.8"}, {"http_status_code": True},
            {"http_status_code": 600}, {"http_status_code": None},
            {"http_status": "failed"}, {"tls_status": "failed"},
            {"dns_status": "blocked"}, {"connected_address": None},
            {"notes": ("n",) * 33}, {"errors": ("x" * 2049,)},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError):
                    self.repo.append(self.finding.id, checked(**changes))
                self.assertEqual(self.repo.list(self.finding.id), ())

    def test_blocked_private_address_and_tls_failures_remain_evidence(self):
        blocked = self.repo.append(self.finding.id, checked(
            dns_status="blocked", addresses=("127.0.0.1",), tls_status="not_checked",
            http_status="not_checked", http_status_code=None, connected_address=None,
            errors=("Hedef adres engellendi.",),
        ))
        failed = self.repo.append(self.finding.id, checked(
            tls_status="failed", http_status="not_checked", http_status_code=None,
            errors=("Sertifika doğrulanamadı.",),
        ))
        self.assertEqual(self.repo.list(self.finding.id), (blocked, failed))
        self.assertEqual(self.findings.get_finding(self.finding.id).finding.status, "new")

    def test_timestamp_regression_during_check_is_retained_for_priority_warning(self):
        assessment = self.repo.append(self.finding.id, checked(finished_at="2026-10-27T10:00:00+00:00"))
        self.assertEqual(self.repo.list(self.finding.id), (assessment,))

    def test_malformed_persisted_json_fails_read_without_modification(self):
        assessment = self.repo.append(self.finding.id, checked())
        valid = json.dumps(asdict(assessment.result))
        variants = (
            "{", "[]", valid[:-1] + ',"domain":"example-support.net"}',
            valid.replace('"http_status_code": 301', '"http_status_code": NaN'),
            valid.replace('"http_status_code": 301', '"http_status_code": true'),
            valid.replace('"example-support.net"', '"another.net"'),
            valid.replace('"resolved"', '"unknown"'),
            " " * (128 * 1024 + 1),
        )
        for payload in variants:
            with self.subTest(payload=payload[:80]):
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    connection.execute("UPDATE finding_assessments SET result=? WHERE id=?", (payload, assessment.id))
                before = self.path.read_bytes()
                for read in (lambda: self.repo.list(self.finding.id), self.repo.latest_by_finding,
                             lambda: self.repo.details(self.finding.id)):
                    with self.assertRaises(StorageError):
                        read()
                self.assertEqual(self.path.read_bytes(), before)

    def test_details_use_one_read_snapshot_when_concurrent_writer_commits(self):
        # WAL permits a writer to finish while the export reader holds a snapshot.
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        first = self.repo.append(self.finding.id, checked())
        original = SQLiteFindingRepository._details

        def concurrent_change(connection, finding_id):
            details = original(connection, finding_id)
            self.findings.review_finding(finding_id, "suspicious", "Eşzamanlı karar")
            self.repo.append(finding_id, checked(http_status_code=404))
            return details

        with patch.object(SQLiteFindingRepository, "_details", side_effect=concurrent_change):
            snapshot = self.repo.details(self.finding.id)
        self.assertEqual(snapshot.details.finding.status, "new")
        self.assertEqual(snapshot.details.reviews, ())
        self.assertEqual(snapshot.assessments, (first,))
        self.assertEqual(len(self.repo.details(self.finding.id).assessments), 2)
        self.assertEqual(self.repo.details(self.finding.id).details.finding.status, "suspicious")

    def test_assessment_failure_rolls_back_and_later_check_can_be_saved(self):
        first = self.repo.append(self.finding.id, checked())
        with patch("xti.adapters.sqlite_assessments.uuid4", return_value=first.id):
            with self.assertRaises(StorageError):
                self.repo.append(self.finding.id, checked(http_status_code=404))
        self.assertEqual(self.repo.list(self.finding.id), (first,))
        second = self.repo.append(self.finding.id, checked(http_status_code=404))
        self.assertEqual(self.repo.list(self.finding.id), (first, second))

    def test_missing_database_reads_do_not_initialize_a_directory(self):
        missing = self.path.parent / "absent" / "xti.db"
        repo = SQLiteAssessmentRepository(missing)
        for read in (lambda: repo.list("finding"), repo.latest_by_finding, lambda: repo.details("finding")):
            with self.assertRaises(StorageError):
                read()
        self.assertFalse(missing.parent.exists())


class AssessmentMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(ASSETS_DDL)
            for statement in FINDINGS_DDL + JOBS_DDL:
                connection.execute(statement)
            connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
            connection.execute("DROP TABLE IF EXISTS cti_saved_search_notes")
            connection.execute("DROP TABLE IF EXISTS cti_saved_search_tag_events")
            connection.execute("DROP TABLE IF EXISTS cti_saved_search_tags")
            connection.execute("DROP TABLE IF EXISTS cti_saved_search_notifications")
            connection.execute("DROP TABLE IF EXISTS cti_saved_search_run_items")
            connection.execute("DROP TABLE IF EXISTS cti_saved_search_runs")
            connection.execute("DROP TABLE IF EXISTS cti_saved_search_events")
            connection.execute("DROP TABLE IF EXISTS cti_saved_searches")
            connection.execute("DROP TABLE IF EXISTS cti_relationship_assertion_events")
            connection.execute("DROP TABLE IF EXISTS cti_relationship_assertions")
            connection.execute("DROP TABLE IF EXISTS cti_relationships")
            connection.execute("DROP TABLE IF EXISTS cti_entity_assertion_events")
            connection.execute("DROP TABLE IF EXISTS cti_entity_assertions")
            connection.execute("DROP TABLE IF EXISTS cti_entities")
            connection.execute("DROP TABLE IF EXISTS cti_feed_run_items")
            connection.execute("DROP TABLE IF EXISTS cti_feed_runs")
            connection.execute("DROP TABLE IF EXISTS cti_indicator_assertion_events")
            connection.execute("DROP TABLE IF EXISTS cti_indicator_assertions")
            connection.execute("DROP TABLE IF EXISTS cti_indicators")
            connection.execute("DROP TABLE IF EXISTS ubuntu_asset_package_events")
            connection.execute("DROP TABLE IF EXISTS ubuntu_asset_packages")
            for table in ("webhook_delivery_attempts", "webhook_deliveries", "webhook_destination_events", "webhook_destinations"):
                connection.execute(f"DROP TABLE IF EXISTS {table}")
            connection.execute("DROP TABLE IF EXISTS ransomware_monitor_cycle_watch_runs")
            connection.execute("DROP TABLE IF EXISTS ransomware_monitor_cycles")
            connection.execute("DROP TABLE IF EXISTS ransomware_identity_review_events")
            connection.execute("DROP TABLE IF EXISTS ransomware_monitor_sessions")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_notifications")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_runs")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_events")
            connection.execute("DROP TABLE IF EXISTS ransomware_watches")
            connection.execute("DROP TABLE IF EXISTS ransomware_claim_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomware_claim_runs")
            connection.execute("DROP TABLE IF EXISTS brand_username_review_notifications")
            connection.execute("DROP TABLE IF EXISTS brand_username_review_events")
            connection.execute("DROP TABLE IF EXISTS brand_username_watch_run_items")
            connection.execute("DROP TABLE IF EXISTS brand_username_watch_runs")
            connection.execute("DROP TABLE IF EXISTS brand_username_watch_events")
            connection.execute("DROP TABLE IF EXISTS brand_username_watches")
            connection.execute("DROP INDEX IF EXISTS supplier_candidate_resolutions_candidate_sequence")
            connection.execute("DROP INDEX IF EXISTS supplier_candidate_evidence_candidate_sequence")
            connection.execute("DROP INDEX IF EXISTS supplier_candidates_status_current")
            connection.execute("DROP TABLE IF EXISTS supplier_candidate_resolution_events")
            connection.execute("DROP TABLE IF EXISTS supplier_candidate_evidence")
            connection.execute("DROP TABLE IF EXISTS supplier_candidates")
            connection.execute("DROP INDEX IF EXISTS supplier_events_supplier_sequence")
            connection.execute("DROP INDEX IF EXISTS suppliers_active_name")
            connection.execute("DROP TABLE IF EXISTS supplier_events")
            connection.execute("DROP TABLE IF EXISTS suppliers")
            connection.execute("DROP TABLE IF EXISTS case_activities")
            connection.execute("DROP TABLE IF EXISTS case_tasks")
            connection.execute("DROP TABLE IF EXISTS case_evidence")
            connection.execute("DROP TABLE IF EXISTS cases")
            connection.execute("DROP TABLE IF EXISTS collection_profile_events")
            connection.execute("DROP TABLE IF EXISTS collection_profiles")
            connection.execute("DROP TABLE IF EXISTS collection_step_receipts")
            connection.execute("DROP TABLE IF EXISTS collection_session_steps")
            connection.execute("DROP TABLE IF EXISTS collection_sessions")
            connection.execute("PRAGMA user_version=3")
            connection.execute("INSERT INTO assets VALUES ('asset-1', 'example.com', '2026-01-01')")
            connection.execute(
                "INSERT INTO observations VALUES ('observation-1', 'example-support.net', "
                "'EXAMPLE-SUPPORT.NET', 'https://crt.sh/?id=42', 'source-hash', 1, NULL, '2026-01-02')"
            )
            connection.execute(
                "INSERT INTO findings VALUES ('finding-1', 'asset-1', 'example.com', "
                "'example-support.net', 'rules-v1', '[\"reason\"]', 'uncertain', '2026-01-02', '2026-01-02')"
            )
            connection.execute("INSERT INTO finding_observations VALUES ('finding-1', 'observation-1')")
            connection.execute(
                "INSERT INTO reviews VALUES ('review-1', 'finding-1', 'uncertain', 'Ek bilgi gerekli', '2026-01-03')"
            )
            connection.execute(
                "INSERT INTO scan_jobs VALUES ('job-1', '[\"example.com\"]', 0, 'crt.sh', "
                "'rules-v1', 'failed', '2026-01-01', '2026-01-01', 1)"
            )
            connection.execute(
                "INSERT INTO scan_attempts VALUES ('attempt-1', 'job-1', 1, 'failed', '2026-01-01', "
                "'2026-01-01', NULL, 'Kaynak yanıt vermedi', '[]', NULL)"
            )
        self.assets = SQLiteAssetRepository(self.path)

    @staticmethod
    def snapshot(path):
        with closing(sqlite3.connect(path)) as connection:
            return {
                table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                for table in ("assets", "observations", "findings", "finding_observations", "reviews",
                              "scan_jobs", "scan_attempts")
            }

    @staticmethod
    def version(path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def test_v3_upgrade_preserves_old_rows_and_publishes_original_version_backup(self):
        before = self.snapshot(self.path)
        result = self.assets.migrate()
        self.assertEqual(result["from_version"], 3)
        self.assertEqual(result["to_version"], SCHEMA_VERSION)
        self.assertEqual(self.snapshot(self.path), before)
        self.assertEqual(self.version(self.path), SCHEMA_VERSION)
        backup = Path(result["backup"])
        self.assertIn(f"pre-v{SCHEMA_VERSION}-", backup.name)
        self.assertEqual(self.version(backup), 3)
        self.assertEqual(self.snapshot(backup), before)
        self.assertEqual(SQLiteAssessmentRepository(self.path).list("finding-1"), ())
        self.assertEqual(SQLiteJobRepository(self.path).get("job-1").attempts[0].error, "Kaynak yanıt vermedi")
        self.assertEqual(self.assets.inspect()["assessment_count"], 0)
        after = self.path.read_bytes()
        self.assertIs(self.assets.migrate()["changed"], False)
        self.assertEqual(self.path.read_bytes(), after)
        self.assertEqual(len(list(backup.parent.glob("*.db"))), 1)

    def test_v3_read_and_init_require_explicit_migration_without_changes(self):
        before = self.path.read_bytes()
        for operation in (self.assets.initialize, self.assets.inspect, self.assets.list,
                          SQLiteAssessmentRepository(self.path).latest_by_finding):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(StorageError, "migrate"):
                    operation()
                self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "backups").exists())

    def test_v3_failed_assessment_migration_rolls_back_with_backup_available(self):
        before = self.snapshot(self.path)

        def broken(connection):
            connection.execute("CREATE TABLE finding_assessments_partial (id TEXT)")
            connection.execute("DROP TABLE IF EXISTS ubuntu_asset_package_events")
            connection.execute("DROP TABLE IF EXISTS ubuntu_asset_packages")
            connection.execute("DROP TABLE IF EXISTS ransomware_monitor_cycle_watch_runs")
            connection.execute("DROP TABLE IF EXISTS ransomware_monitor_cycles")
            connection.execute("DROP TABLE IF EXISTS ransomware_identity_review_events")
            connection.execute("DROP TABLE IF EXISTS ransomware_monitor_sessions")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_notifications")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_runs")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_events")
            connection.execute("DROP TABLE IF EXISTS ransomware_watches")
            connection.execute("DROP TABLE IF EXISTS ransomware_claim_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomware_claim_runs")
            connection.execute("DROP INDEX IF EXISTS supplier_candidate_resolutions_candidate_sequence")
            connection.execute("DROP INDEX IF EXISTS supplier_candidate_evidence_candidate_sequence")
            connection.execute("DROP INDEX IF EXISTS supplier_candidates_status_current")
            connection.execute("DROP TABLE IF EXISTS supplier_candidate_resolution_events")
            connection.execute("DROP TABLE IF EXISTS supplier_candidate_evidence")
            connection.execute("DROP TABLE IF EXISTS supplier_candidates")
            connection.execute("DROP INDEX IF EXISTS supplier_events_supplier_sequence")
            connection.execute("DROP INDEX IF EXISTS suppliers_active_name")
            connection.execute("DROP TABLE IF EXISTS supplier_events")
            connection.execute("DROP TABLE IF EXISTS suppliers")
            connection.execute("DROP TABLE IF EXISTS case_activities")
            connection.execute("DROP TABLE IF EXISTS case_tasks")
            connection.execute("DROP TABLE IF EXISTS case_evidence")
            connection.execute("DROP TABLE IF EXISTS cases")
            connection.execute("DROP TABLE IF EXISTS collection_profile_events")
            connection.execute("DROP TABLE IF EXISTS collection_profiles")
            connection.execute("DROP TABLE IF EXISTS collection_step_receipts")
            connection.execute("DROP TABLE IF EXISTS collection_session_steps")
            connection.execute("DROP TABLE IF EXISTS collection_sessions")
            connection.execute("PRAGMA user_version=4")
            raise sqlite3.OperationalError("Injected failure")

        with patch("xti.adapters.sqlite.create_assessments_schema", side_effect=broken):
            with self.assertRaises(StorageError):
                self.assets.migrate()
        self.assertEqual(self.version(self.path), 3)
        self.assertEqual(self.snapshot(self.path), before)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 3)
        backups = list((self.path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.snapshot(backups[0]), before)
        self.assertEqual(self.version(backups[0]), 3)
        self.assets.migrate()
        self.assertEqual(self.version(self.path), SCHEMA_VERSION)

    def test_v3_backup_restore_retains_format_until_explicit_migration(self):
        before = self.path.read_bytes()
        backup = self.path.parent / "legacy-backup.db"
        restored = self.path.parent / "restored" / "xti.db"
        self.assets.backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(self.version(restored), 3)
        self.assertEqual(self.snapshot(restored), self.snapshot(self.path))
        with self.assertRaisesRegex(StorageError, "migrate"):
            SQLiteAssessmentRepository(restored).details("finding-1")
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(self.version(restored), SCHEMA_VERSION)
        self.assertEqual(self.snapshot(restored), self.snapshot(self.path))
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
