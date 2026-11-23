"""P08 retention policy, holds, archive, restore, audit and migration acceptance."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.adapters.sqlite_data_retention import SQLiteDataRetentionRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_unified_monitoring import SQLiteUnifiedMonitoringRepository
from xti.adapters.schema import SCHEMA_VERSION
from xti.adapters.unified_monitoring_inputs import SQLiteUnifiedMonitoringInputs
from xti.application.cases import CaseEvidenceResolverService, CaseService
from xti.application.data_retention import DataRetentionService
from xti.application.unified_monitoring import UnifiedMonitoringService
from xti.domain.data_retention import FAMILY, PREFIX, RetentionError
from xti.domain.organizations import normalize_organization_target
from xti.domain.unified_monitoring import PREFIX as MONITORING_PREFIX


class Clock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self):
        return self.value.isoformat()

    def advance(self, seconds=600):
        self.value += timedelta(seconds=seconds)


class DataRetentionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "xti.db"
        self.storage = SQLiteAssetRepository(self.path); self.storage.initialize()
        self.storage.add("example.com")
        for index in range(80):
            self.storage.add(f"example.com-{index}.test")
        organizations = SQLiteOrganizationRepository(self.path)
        self.organization = organizations.add(
            name_key="example corp", display_name="Example Corp",
            reason="P08 controlled organization", recorded_at="2026-01-01T08:00:00+00:00",
        ).organization
        organizations.link(
            self.organization.id, normalize_organization_target("domain", "example.com"),
            reason="P08 exact organization scope", recorded_at="2026-01-01T08:01:00+00:00",
        )
        self.monitor_clock = Clock(datetime(2026, 1, 2, 9, tzinfo=timezone.utc))
        self.monitor_repository = SQLiteUnifiedMonitoringRepository(self.path)
        self.monitoring = UnifiedMonitoringService(
            self.monitor_repository, SQLiteUnifiedMonitoringInputs(self.path),
            now=self.monitor_clock,
        )
        self.monitor_policy = self.monitoring.execute(
            MONITORING_PREFIX + "policy.add", name="Retention source watch",
            organization_id=self.organization.id,
            subjects=[{"kind": "domain", "value": "example.com"}],
            record_kinds=["domain"], match_modes=["exact", "prefix"],
            notify_on=["added", "updated"], minimum_change_count=1,
            priority="high", interval_seconds=300, max_matches=200,
            actor="monitor@example.test", reason="P08 için büyük ve sıkıştırılabilir kanıt.",
            idempotency_key="p08-monitor-policy",
        )
        self.baseline = self._monitor_run("p08-baseline")
        self.unchanged = self._monitor_run("p08-unchanged", force=True)
        self.storage.add("example.com-new.test")
        self.changed = self._monitor_run("p08-changed", force=True)
        self.assertIsNotNone(self.changed["alert_id"], self.changed)

        case_service = CaseService(
            SQLiteCaseRepository(self.path),
            CaseEvidenceResolverService(SQLiteCaseEvidenceSourceRepository(self.path)),
            clock=lambda: self.monitor_clock.value,
        )
        case = case_service.create(
            "Protected monitoring alert", summary="P08 automatic case protection fixture.",
            priority="high", reason="Active case evidence must never be archived.",
        ).case
        case_service.add_evidence(
            case.id, "unified_monitoring", self.changed["alert_id"],
            reason="P08 case-linked evidence protection.",
        )

        self.retention_clock = Clock(datetime(2026, 11, 22, 10, tzinfo=timezone.utc))
        self.repository = SQLiteDataRetentionRepository(self.path)
        self.retention = DataRetentionService(self.repository, now=self.retention_clock)
        self.policy = self.retention.execute(
            PREFIX + "policy.add", name="Example retention",
            organization_id=self.organization.id, families=[FAMILY],
            archive_after_days=90, batch_limit=100,
            purpose="Security monitoring evidence lifecycle",
            retention_basis="Organization-approved test policy",
            actor="privacy@example.test", reason="P08 policy acceptance.",
            idempotency_key="p08-policy",
        )

    def _monitor_run(self, key, *, force=False):
        self.monitor_clock.advance()
        return self.monitoring.execute(
            MONITORING_PREFIX + "run", identifier=self.monitor_policy["id"],
            expected_revision=self.monitor_policy["revision"], force=force,
            idempotency_key=key,
        )

    def test_archive_is_lossless_case_aware_idempotent_and_restorable(self):
        hold = self.retention.execute(
            PREFIX + "hold.add", organization_id=self.organization.id,
            family=FAMILY, record_id=self.unchanged["id"], kind="investigation",
            actor="analyst@example.test", reason="Unchanged run remains hot during review.",
            idempotency_key="p08-hold-unchanged",
        )
        self.assertTrue(hold["active"])
        before = self.monitoring.execute(
            MONITORING_PREFIX + "run.show", identifier=self.baseline["id"],
        )
        dependent_before = self.monitoring.execute(
            MONITORING_PREFIX + "run.show", identifier=self.unchanged["id"],
        )
        plan = self.retention.execute(PREFIX + "plan", identifier=self.policy["id"])
        self.assertEqual(plan["case_protected_count"], 1)
        self.assertEqual(plan["explicit_hold_count"], 1)
        self.assertGreaterEqual(plan["selected_count"], 1)
        applied = self.retention.execute(
            PREFIX + "apply", identifier=self.policy["id"],
            expected_revision=self.policy["revision"], token=plan["token"],
            actor="privacy@example.test", reason="Approved lossless hot-payload archive.",
            idempotency_key="p08-apply",
        )
        self.assertEqual(applied["status"], "complete")
        self.assertGreaterEqual(applied["receipt"]["changed_count"], 1)
        self.assertFalse(applied["receipt"]["logical_record_delete"])
        self.assertTrue((self.path.parent / "backups" / applied["receipt"]["backup_name"]).is_file())
        self.assertEqual(
            self.monitoring.execute(MONITORING_PREFIX + "run.show", identifier=self.baseline["id"]),
            before,
        )
        self.assertEqual(
            self.monitoring.execute(MONITORING_PREFIX + "run.show", identifier=self.unchanged["id"]),
            dependent_before,
        )
        with self.storage._connection() as connection:
            archived = connection.execute(
                "SELECT id,report_body FROM retention_archive_items WHERE active=1 ORDER BY sequence LIMIT 1"
            ).fetchone()
            connection.execute(
                "UPDATE retention_archive_items SET report_body=? WHERE id=?",
                (archived[1] + b"tampered", archived[0]),
            )
            connection.commit()
        with self.assertRaisesRegex(Exception, "çalışma kaydı bozuk"):
            self.monitoring.execute(MONITORING_PREFIX + "run.show", identifier=self.baseline["id"])
        with self.storage._connection() as connection:
            connection.execute(
                "UPDATE retention_archive_items SET report_body=? WHERE id=?",
                (archived[1], archived[0]),
            )
            connection.commit()
        replay = self.retention.execute(
            PREFIX + "apply", identifier=self.policy["id"],
            expected_revision=self.policy["revision"], token=plan["token"],
            actor="privacy@example.test", reason="Approved lossless hot-payload archive.",
            idempotency_key="p08-apply",
        )
        self.assertTrue(replay["replayed"])

        restored = self.retention.execute(
            PREFIX + "restore", identifier=applied["id"], actor="privacy@example.test",
            reason="Restore hot payloads for controlled acceptance.",
            idempotency_key="p08-restore",
        )
        self.assertEqual((restored["status"], restored["receipt"]["changed_count"]),
                         ("complete", applied["receipt"]["changed_count"]))
        self.assertEqual(
            self.monitoring.execute(MONITORING_PREFIX + "run.show", identifier=self.baseline["id"]),
            before,
        )
        with self.storage._connection(readonly=True) as connection:
            marker_count = connection.execute(
                "SELECT COUNT(*) FROM monitoring_runs WHERE report_json LIKE 'XTI-RETENTION-V1:%'"
            ).fetchone()[0]
            active_count = connection.execute(
                "SELECT COUNT(*) FROM retention_archive_items WHERE active=1"
            ).fetchone()[0]
        self.assertEqual((marker_count, active_count), (0, 0))
        with self.assertRaisesRegex(RetentionError, "geri alınabilir"):
            self.retention.execute(
                PREFIX + "restore", identifier=applied["id"], actor="privacy@example.test",
                reason="A second restore must not create an empty operation.",
                idempotency_key="p08-restore-again",
            )

    def test_policy_lifecycle_and_cursor_pages_are_explicit(self):
        updated = self.retention.execute(
            PREFIX + "policy.update", identifier=self.policy["id"], expected_revision=1,
            archive_after_days=120, batch_limit=10, actor="privacy@example.test",
            reason="Approved policy revision.", idempotency_key="p08-policy-update",
        )
        self.assertEqual((updated["revision"], updated["definition"]["batch_limit"]), (2, 10))
        page = self.retention.execute(
            PREFIX + "policies", organization_id=self.organization.id, after=0, limit=1,
        )
        self.assertEqual((len(page["items"]), page["total_count"]), (1, 1))
        self.assertIsNotNone(page["next_after"])
        self.assertEqual(self.retention.execute(
            PREFIX + "policies", organization_id=self.organization.id,
            after=page["next_after"], limit=1,
        )["items"], [])
        disabled = self.retention.execute(
            PREFIX + "policy.disable", identifier=updated["id"], expected_revision=2,
            actor="privacy@example.test", reason="Approved temporary suspension.",
            idempotency_key="p08-policy-disable",
        )
        self.assertFalse(disabled["enabled"])
        with self.assertRaisesRegex(RetentionError, "Etkin olmayan"):
            self.retention.execute(PREFIX + "plan", identifier=disabled["id"])
        enabled = self.retention.execute(
            PREFIX + "policy.update", identifier=disabled["id"], expected_revision=3,
            enabled=True, actor="privacy@example.test", reason="Approved reactivation.",
            idempotency_key="p08-policy-reactivate",
        )
        self.assertTrue(enabled["enabled"])
        self.assertEqual(enabled["event"]["action"], "reactivated")

    def test_policy_hold_release_audit_and_tamper_fail_closed(self):
        replay = self.retention.execute(
            PREFIX + "policy.add", name="Example retention",
            organization_id=self.organization.id, families=[FAMILY],
            archive_after_days=90, batch_limit=100,
            purpose="Security monitoring evidence lifecycle",
            retention_basis="Organization-approved test policy",
            actor="privacy@example.test", reason="P08 policy acceptance.",
            idempotency_key="p08-policy",
        )
        self.assertTrue(replay["replayed"])
        hold = self.retention.execute(
            PREFIX + "hold.add", organization_id=self.organization.id,
            family=FAMILY, kind="legal", actor="legal@example.test",
            reason="Organization-wide legal preservation.", idempotency_key="p08-global-hold",
        )
        investigation_hold = self.retention.execute(
            PREFIX + "hold.add", organization_id=self.organization.id,
            family=FAMILY, kind="investigation", actor="analyst@example.test",
            reason="Independent investigation preservation.",
            idempotency_key="p08-global-investigation-hold",
        )
        self.assertNotEqual(hold["id"], investigation_hold["id"])
        plan = self.retention.execute(PREFIX + "plan", identifier=self.policy["id"])
        self.assertEqual(plan["selected_count"], 0)
        released = self.retention.execute(
            PREFIX + "hold.release", identifier=hold["id"], expected_revision=1,
            actor="legal@example.test", reason="Preservation instruction ended.",
            idempotency_key="p08-release-hold",
        )
        self.assertFalse(released["active"])
        self.assertEqual(
            self.retention.execute(PREFIX + "plan", identifier=self.policy["id"])["selected_count"],
            0,
        )
        released_investigation = self.retention.execute(
            PREFIX + "hold.release", identifier=investigation_hold["id"], expected_revision=1,
            actor="analyst@example.test", reason="Investigation preservation ended.",
            idempotency_key="p08-release-investigation-hold",
        )
        self.assertFalse(released_investigation["active"])
        self.assertGreater(
            self.retention.execute(PREFIX + "plan", identifier=self.policy["id"])["selected_count"],
            0,
        )
        audit = self.retention.execute(
            PREFIX + "audit", organization_id=self.organization.id, after=0, limit=100,
        )
        self.assertGreaterEqual(audit["total_count"], 3)
        with self.storage._connection() as connection, connection:
            connection.execute(
                "UPDATE retention_audit_events SET chain_sha256=? WHERE sequence=1", ("0" * 64,),
            )
        with self.assertRaisesRegex(Exception, "denetim zinciri"):
            self.retention.execute(PREFIX + "catalog")

    def test_recovery_marks_only_running_policy_work_interrupted(self):
        plan = self.retention.execute(PREFIX + "plan", identifier=self.policy["id"])
        values = {
            "identifier": self.policy["id"], "expected_revision": self.policy["revision"],
            "token": plan["token"], "actor": "operator@example.test",
            "reason": "Reserve then simulate process stop.", "idempotency_key": "p08-reserved",
        }
        reserved, replayed = self.repository.reserve_archive(values, plan, self.retention_clock())
        self.assertFalse(replayed)
        self.assertEqual(reserved["status"], "running")
        recovered = self.retention.execute(
            PREFIX + "recover", identifier=self.policy["id"], actor="operator@example.test",
            reason="Interrupted process explicitly closed.", idempotency_key="p08-recover",
        )
        self.assertEqual((recovered["recovered_count"], recovered["run_ids"]),
                         (1, [reserved["id"]]))
        shown = self.retention.execute(PREFIX + "run.show", identifier=reserved["id"])
        self.assertEqual(shown["status"], "interrupted")

    def test_invalid_scope_revision_and_unknown_family_fail_before_mutation(self):
        with self.assertRaisesRegex(Exception, "veri ailesi"):
            self.retention.execute(
                PREFIX + "hold.add", organization_id=self.organization.id,
                family="all_tables", kind="legal", actor="legal@example.test",
                reason="Unknown family must fail closed.", idempotency_key="bad-family",
            )
        with self.assertRaisesRegex(RetentionError, "değişti"):
            self.retention.execute(
                PREFIX + "policy.disable", identifier=self.policy["id"], expected_revision=99,
                actor="privacy@example.test", reason="Stale revision.",
                idempotency_key="bad-revision",
            )
        with self.storage._connection(readonly=True) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM retention_policy_events WHERE policy_id=?",
                (self.policy["id"],),
            ).fetchone()[0], 1)


class DataRetentionMigrationTests(unittest.TestCase):
    def test_schema96_migrates_with_backup_and_empty_p08_p12_tables(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "legacy.db"
        storage = SQLiteAssetRepository(path); storage.initialize(); storage.add("example.com")
        with storage._connection() as connection:
            connection.execute("PRAGMA foreign_keys=OFF")
            from tests.case_evidence_v96_fixture import case_evidence_layout_v96
            case_evidence_layout_v96(connection)
            connection.execute("PRAGMA user_version=96")
            connection.commit()
        report = storage.migrate()
        self.assertEqual((report["from_version"], report["to_version"]), (96, SCHEMA_VERSION))
        self.assertTrue(Path(report["backup"]).is_file())
        with storage._connection(readonly=True) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION,
            )
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM retention_policies"
            ).fetchone()[0], 0)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM telemetry_records"
            ).fetchone()[0], 0)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM assets WHERE value='example.com'"
            ).fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
