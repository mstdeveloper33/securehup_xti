"""P07 unified policy, alert, inbox, case and migration acceptance."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL
from xti.adapters.darkweb_monitoring_schema import CASE_EVIDENCE_DDL as V95_CASE_DDL
from xti.adapters.sqlite import SCHEMA_VERSION, SQLiteAssetRepository
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_unified_monitoring import SQLiteUnifiedMonitoringRepository, company_in
from xti.adapters.unified_monitoring_inputs import SQLiteUnifiedMonitoringInputs
from xti.adapters.unified_monitoring_schema import DEFINITIONS
from xti.application.cases import CaseEvidenceResolverService, CaseService
from xti.application.inbox import InboxService
from xti.application.unified_monitoring import UnifiedMonitoringService
from xti.domain.assets import ValidationError
from xti.domain.content_monitoring import canonical, digest
from xti.domain.organizations import normalize_organization_target
from xti.domain.unified_monitoring import MonitoringError, PREFIX, policy_definition


class Clock:
    def __init__(self):
        self.value = datetime(2026, 11, 22, 9, tzinfo=timezone.utc)

    def __call__(self):
        return self.value.isoformat()

    def advance(self, seconds=600):
        self.value += timedelta(seconds=seconds)


class UnifiedMonitoringTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "xti.db"
        self.storage = SQLiteAssetRepository(self.path); self.storage.initialize()
        self.storage.add("example.com")
        organizations = SQLiteOrganizationRepository(self.path)
        self.organization = organizations.add(
            name_key="example corp", display_name="Example Corp",
            reason="P07 controlled scope", recorded_at="2026-11-22T08:00:00+00:00",
        ).organization
        organizations.link(
            self.organization.id, normalize_organization_target("domain", "example.com"),
            reason="P07 exact domain", recorded_at="2026-11-22T08:01:00+00:00",
        )
        self.clock = Clock()
        self.repository = SQLiteUnifiedMonitoringRepository(self.path)
        self.service = UnifiedMonitoringService(
            self.repository, SQLiteUnifiedMonitoringInputs(self.path), now=self.clock,
        )

    def add_policy(self, key="policy-one"):
        return self.service.execute(
            PREFIX + "policy.add", name="Example unified watch",
            organization_id=self.organization.id,
            subjects=[{"kind": "domain", "value": "example.com"},
                      {"kind": "brand", "value": "Example Corp"}],
            record_kinds=["domain", "organization"], match_modes=["exact", "prefix"],
            notify_on=["added", "updated"], minimum_change_count=1,
            priority="high", interval_seconds=300, max_matches=100,
            actor="analyst@example.test", reason="Kuruluş için birleşik izleme politikası oluşturuldu.",
            idempotency_key=key,
        )

    def run_policy(self, policy, key, *, force=False):
        self.clock.advance()
        return self.service.execute(
            PREFIX + "run", identifier=policy["id"],
            expected_revision=policy["revision"], force=force,
            idempotency_key=key,
        )

    def test_policy_validation_requires_explicit_link_and_canonical_subjects(self):
        definition = policy_definition({
            "name": "Canonical", "organization_id": self.organization.id,
            "subjects": [{"kind": "ip", "value": "2001:0db8::1"},
                         {"kind": "brand", "value": "Example Corp"}],
        })
        self.assertEqual(definition["subjects"][1]["value"], "2001:db8::1")
        with self.assertRaisesRegex(MonitoringError, "önce etkin kuruluşa"):
            self.service.execute(
                PREFIX + "policy.add", name="Unlinked", organization_id=self.organization.id,
                subjects=[{"kind": "domain", "value": "unlinked.example"}],
                actor="analyst", reason="Kapsam doğrulaması deneniyor.", idempotency_key="unlinked",
            )

    def test_baseline_change_alert_review_inbox_and_case_are_consistent(self):
        policy = self.add_policy()
        replay = self.add_policy()
        self.assertEqual(policy["id"], replay["id"])
        self.assertTrue(replay["replayed"])
        baseline = self.run_policy(policy, "baseline")
        self.assertTrue(baseline["report"]["silent_baseline"])
        self.assertFalse(baseline["report"]["alert_required"])
        self.assertIsNone(baseline["alert_id"])

        self.storage.add("example.com.tr")
        changed = self.run_policy(policy, "change")
        self.assertFalse(changed["report"]["silent_baseline"])
        self.assertEqual(changed["report"]["counts"]["added"], 1)
        self.assertEqual(changed["report"]["changes_total"], 1)
        self.assertFalse(changed["report"]["changes_truncated"])
        self.assertIsNotNone(changed["alert_id"])
        changes = self.service.execute(
            PREFIX + "run.changes", identifier=changed["id"], offset=0, limit=100,
        )
        self.assertEqual((changes["total_count"], changes["items"][0]["action"]), (1, "added"))

        alert = self.service.execute(PREFIX + "alert.show", identifier=changed["alert_id"])
        self.assertEqual(alert["priority"], "high")
        self.assertEqual(alert["review_revision"], 0)
        review = self.service.execute(
            PREFIX + "alert.review", identifier=alert["id"], expected_revision=0,
            decision="useful", reason="Yeni prefix domain kaydı analist incelemesine değer.",
            actor="analyst@example.test", idempotency_key="review-one",
        )
        self.assertEqual((review["decision"], review["revision"]), ("useful", 1))

        inbox = InboxService(SQLiteInboxRepository(self.path))
        page = inbox.list()
        self.assertEqual(page.total_count, 1)
        self.assertEqual(page.items[0].notification.monitoring_alert_id, alert["id"])
        self.assertEqual(page.items[0].monitoring_change["id"], alert["id"])
        self.assertEqual(inbox.show(alert["id"]).monitoring_change["review"]["decision"], "useful")

        cases = CaseService(
            SQLiteCaseRepository(self.path),
            CaseEvidenceResolverService(SQLiteCaseEvidenceSourceRepository(self.path)),
            clock=lambda: self.clock.value,
        )
        case = cases.create(
            "Birleşik izleme değişikliği", summary="Yeni kayıt insan incelemesine bağlanıyor.",
            priority="high", reason="P07 alarmı için vaka açıldı.",
        ).case
        evidence = cases.add_evidence(
            case.id, "unified_monitoring", alert["id"],
            reason="Dondurulmuş P07 alarm kanıtı bağlandı.",
        ).evidence
        self.assertEqual(evidence.evidence_type, "unified_monitoring")
        self.assertEqual(cases.show(case.id).active_evidence_count, 1)

    def test_policy_revision_resets_baseline_due_plan_and_recovery_are_explicit(self):
        policy = self.add_policy()
        first = self.run_policy(policy, "run-one")
        plan = self.service.execute(PREFIX + "plan", identifier=policy["id"])
        self.assertFalse(plan["collection"]["network_access"])
        self.assertFalse(plan["schedule"]["due"])
        due = self.service.execute(PREFIX + "due", at=plan["schedule"]["due_at"], limit=10)
        self.assertEqual(due["items"][0]["id"], policy["id"])
        updated = self.service.execute(
            PREFIX + "policy.update", identifier=policy["id"],
            expected_revision=policy["revision"], priority="critical",
            actor="lead@example.test", reason="Kuruluş politikası kritik olarak güncellendi.",
            idempotency_key="policy-update",
        )
        self.assertEqual(updated["revision"], 2)
        second = self.run_policy(updated, "run-two")
        self.assertTrue(second["report"]["silent_baseline"])
        with self.storage._connection() as connection, connection:
            connection.execute(
                "INSERT INTO monitoring_runs (id,policy_id,policy_event_id,request_key,request_sha256,"
                "previous_run_id,status,snapshot_json,snapshot_sha256,report_json,report_sha256,error_code,"
                "error_message,started_at,finished_at) VALUES (?,?,?,?,?,?,'running',NULL,NULL,NULL,NULL,NULL,NULL,?,NULL)",
                ("10000000-0000-4000-8000-000000000001", updated["id"],
                 self.repository._policy(connection, updated["id"])["event"]["id"],
                 "manual-interrupted", "a" * 64, second["id"], self.clock()),
            )
        recovered = self.service.execute(
            PREFIX + "recover", identifier=updated["id"],
            reason="Kesilen yerel işlem operatör tarafından kapatıldı.", actor="operator",
            idempotency_key="recover-one",
        )
        self.assertEqual(recovered["recovered_count"], 1)
        self.assertEqual(self.service.execute(
            PREFIX + "run.show", identifier=recovered["run_ids"][0],
        )["status"], "interrupted")

    def test_company_projection_and_storage_statistics_are_bounded(self):
        policy = self.add_policy()
        with self.storage._connection(readonly=True) as connection:
            projection = company_in(connection, self.organization.id)
        self.assertEqual(projection["items"][0]["id"], policy["id"])
        self.assertTrue(projection["stored_evidence_only"])
        status = self.storage.inspect()
        self.assertEqual(status["monitoring_policy_count"], 1)
        self.assertEqual(status["active_monitoring_policy_count"], 1)

    def test_alert_filters_count_the_filtered_set_and_tampering_fails_closed(self):
        policy = self.add_policy()
        self.run_policy(policy, "filter-baseline")
        self.storage.add("example.com.tr")
        changed = self.run_policy(policy, "filter-change")
        reviewed = self.service.execute(
            PREFIX + "alert.review", identifier=changed["alert_id"], expected_revision=0,
            decision="useful", reason="Filtre sözleşmesi için insan incelemesi.",
            actor="analyst@example.test", idempotency_key="filter-review",
        )
        page = self.service.execute(
            PREFIX + "alerts", decision=reviewed["decision"], priority="high",
            read_state="unread", after=0, limit=1,
        )
        self.assertEqual((len(page["items"]), page["total_count"]), (1, 1))
        empty = self.service.execute(
            PREFIX + "alerts", decision="not_useful", read_state="all", after=0, limit=20,
        )
        self.assertEqual((empty["items"], empty["total_count"]), ([], 0))
        with self.storage._connection() as connection, connection:
            raw = connection.execute(
                "SELECT report_json FROM monitoring_runs WHERE id=?", (changed["id"],),
            ).fetchone()[0]
            tampered = json.loads(raw)
            tampered["priority"] = "low"
            connection.execute(
                "UPDATE monitoring_runs SET report_json=?,report_sha256=? WHERE id=?",
                (canonical(tampered), digest(tampered), changed["id"]),
            )
        with self.assertRaisesRegex(Exception, "bozuk"):
            self.service.execute(PREFIX + "run.show", identifier=changed["id"])

    def test_idempotency_conflict_and_due_limit_are_explicit(self):
        first = self.add_policy("idempotency-policy")
        with self.assertRaisesRegex(MonitoringError, "farklı bir işleme"):
            self.service.execute(
                PREFIX + "policy.add", name="Different policy", organization_id=self.organization.id,
                subjects=[{"kind": "brand", "value": "Different Brand"}],
                actor="analyst", reason="Aynı anahtar farklı içerikle deneniyor.",
                idempotency_key="idempotency-policy",
            )
        second = self.service.execute(
            PREFIX + "policy.add", name="Second watch", organization_id=self.organization.id,
            subjects=[{"kind": "brand", "value": "Another Brand"}],
            actor="analyst", reason="Due sayfası sınırı doğrulanıyor.",
            idempotency_key="second-policy",
        )
        due = self.service.execute(PREFIX + "due", at=self.clock(), limit=1)
        self.assertEqual(due["count"], 1)
        self.assertEqual(due["total_due_count"], 2)
        self.assertTrue(due["truncated"])
        self.assertIn(due["items"][0]["id"], {first["id"], second["id"]})

    def test_unchanged_runs_reference_one_frozen_snapshot_without_copying_it(self):
        policy = self.add_policy("deduplicated-policy")
        baseline = self.run_policy(policy, "deduplicated-baseline")
        unchanged = self.run_policy(policy, "deduplicated-unchanged")
        self.assertEqual(unchanged["snapshot_sha256"], baseline["snapshot_sha256"])
        self.assertEqual(unchanged["report"]["counts"]["unchanged"], 2)
        self.assertEqual(baseline["report"]["changes_total"], 2)
        self.assertTrue(baseline["report"]["changes_truncated"])
        with self.storage._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT id,snapshot_json,snapshot_sha256 FROM monitoring_runs "
                "WHERE policy_id=? ORDER BY sequence", (policy["id"],),
            ).fetchall()
        self.assertIsNotNone(rows[0][1])
        self.assertIsNone(rows[1][1])
        self.assertEqual(rows[0][2], rows[1][2])
        self.assertEqual(
            self.service.execute(PREFIX + "run.show", identifier=unchanged["id"])["snapshot"],
            baseline["snapshot"],
        )
        matches = self.service.execute(
            PREFIX + "run.matches", identifier=unchanged["id"], offset=0, limit=1,
        )
        coverage = self.service.execute(
            PREFIX + "run.coverage", identifier=unchanged["id"], offset=0, limit=1,
        )
        self.assertEqual((len(matches["items"]), matches["total_count"]), (1, 2))
        self.assertEqual(set(matches["items"][0]), {
            "key", "subject", "identity_sha256", "state_sha256", "record",
        })
        self.assertNotIn("semantic_json", matches["items"][0])
        self.assertGreaterEqual(coverage["total_count"], 1)

    def test_large_diff_is_sampled_and_the_complete_diff_remains_paginated(self):
        policy = self.service.execute(
            PREFIX + "policy.add", name="Large diff watch",
            organization_id=self.organization.id,
            subjects=[{"kind": "brand", "value": "new-example-"}],
            record_kinds=["domain"], match_modes=["prefix"],
            notify_on=["added"], minimum_change_count=1, priority="medium",
            interval_seconds=300, max_matches=200, actor="capacity-analyst",
            reason="Büyük farkın sınırlı rapor ve sayfalı kanıt davranışı doğrulanıyor.",
            idempotency_key="large-diff-policy",
        )
        baseline = self.run_policy(policy, "large-diff-baseline")
        self.assertEqual(baseline["report"]["total_matches"], 0)
        for index in range(105):
            self.storage.add(f"new-example-{index:03d}.test")
        changed = self.run_policy(policy, "large-diff-change")
        self.assertEqual(changed["report"]["changes_total"], 105)
        self.assertEqual(len(changed["report"]["changes"]), 100)
        self.assertTrue(changed["report"]["changes_truncated"])
        first = self.service.execute(
            PREFIX + "run.changes", identifier=changed["id"], offset=0, limit=100,
        )
        second = self.service.execute(
            PREFIX + "run.changes", identifier=changed["id"], offset=100, limit=100,
        )
        self.assertEqual((len(first["items"]), first["total_count"], first["has_more"]),
                         (100, 105, True))
        self.assertEqual((len(second["items"]), second["total_count"], second["has_more"]),
                         (5, 105, False))

    def test_backup_restore_preserves_policy_and_deduplicated_run(self):
        policy = self.add_policy("backup-policy")
        baseline = self.run_policy(policy, "backup-baseline")
        unchanged = self.run_policy(policy, "backup-unchanged")
        backup = self.path.parent / "backup" / "p07.db"
        self.storage.backup(backup)
        restored_path = self.path.parent / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored_path)
        restored = UnifiedMonitoringService(
            SQLiteUnifiedMonitoringRepository(restored_path),
            SQLiteUnifiedMonitoringInputs(restored_path), now=self.clock,
        )
        restored_policy = restored.execute(PREFIX + "policy.show", identifier=policy["id"])
        restored_run = restored.execute(PREFIX + "run.show", identifier=unchanged["id"])
        self.assertEqual(restored_policy["definition_sha256"], policy["definition_sha256"])
        self.assertEqual(restored_run["snapshot"], baseline["snapshot"])
        self.assertEqual(restored_run["snapshot_sha256"], baseline["snapshot_sha256"])


class UnifiedMonitoringMigrationTests(unittest.TestCase):
    def test_schema95_migrates_with_backup_and_preserves_empty_case_table(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "xti.db"
        storage = SQLiteAssetRepository(path); storage.initialize()
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute("BEGIN")
            from tests.case_evidence_v95_fixture import case_evidence_layout_v95
            case_evidence_layout_v95(connection)
            connection.execute("PRAGMA user_version=95")
            connection.commit()
        finally:
            connection.close()
        result = storage.migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (95, SCHEMA_VERSION))
        self.assertTrue(Path(result["backup"]).is_file())
        self.assertEqual(storage.inspect()["schema_version"], SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
