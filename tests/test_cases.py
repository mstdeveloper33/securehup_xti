"""Human-managed cases, tasks, evidence links and append-only timeline."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_supplier_candidates import SQLiteSupplierCandidateRepository
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.adapters.ransomlook_ransomware import parse_ransomlook_ransomware_response
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.application.cases import CaseEvidenceResolverService, CaseService
from xti.application.supplier_risk import SupplierRiskService
from xti.application.supplier_threat_events import SupplierThreatEventService
from xti.application.suppliers import SupplierService
from xti.domain.assets import ValidationError
from xti.domain.brand_username_reviews import (
    BrandUsernameReviewCandidate,
    brand_username_review_candidate_id,
    brand_username_review_candidate_json,
    brand_username_review_candidate_sha256,
)
from xti.domain.brand_username_watches import (
    brand_watch_definition_sha256,
    brand_watch_item_state_sha256,
)
from xti.interfaces.cli import main
from tests.test_ransomlook_ransomware import content as ransomlook_content, post
from tests.test_threatcluster_ransomware import claim, content as threatcluster_content


NOW = datetime(2026, 10, 31, 15, tzinfo=timezone.utc)


class CaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        supplier_repository = SQLiteSupplierRepository(self.path)
        event_service = SupplierThreatEventService(
            supplier_repository,
            SQLiteRansomwareClaimRepository(self.path),
            SQLiteRansomLookClaimRepository(self.path),
        )
        supplier_risk = SupplierRiskService(
            supplier_repository,
            SQLiteSupplierCandidateRepository(self.path),
            event_service,
        )
        self.supplier_service = SupplierService(
            supplier_repository, clock=lambda: NOW,
        )
        resolver = CaseEvidenceResolverService(
            SQLiteCaseEvidenceSourceRepository(self.path), supplier_risk,
        )
        self.service = CaseService(
            SQLiteCaseRepository(self.path), resolver, clock=lambda: NOW,
        )

    def create_case(self):
        return self.service.create(
            "Şüpheli marka faaliyeti",
            summary="Birden çok yerel kanıtın birlikte incelenmesi gerekiyor.",
            priority="high", reason="İnsan incelemesi için vaka açıldı.",
        ).case

    def insert_finding(self):
        asset, _ = self.storage.add("example.com")
        finding_id = str(uuid4())
        with self.storage._connection() as connection, connection:
            connection.execute(
                "INSERT INTO findings "
                "(id, asset_id, asset_value, domain, rule_version, reasons, status, "
                "created_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    finding_id, asset.id, asset.value, "example-login.net", "test/v1",
                    json.dumps(["marka adı ve hizmet eki"], ensure_ascii=True),
                    "new", NOW.isoformat(), NOW.isoformat(),
                ),
            )
        return finding_id

    def test_full_lifecycle_tasks_notes_close_and_reopen_are_append_only(self):
        record = self.create_case()
        note = self.service.add_note(
            record.id, "İlk kanıt incelemesi başladı.", kind="observation",
        )
        task = self.service.add_task(
            record.id, "Kaynak kayıtlarını doğrula",
            due_at=(NOW + timedelta(days=1)).isoformat(),
            reason="Kapanıştan önce kanıtları değerlendirmek için.",
        ).task
        with self.assertRaisesRegex(ValidationError, "Açık görevleri"):
            self.service.set_status(
                record.id, "closed", reason="Erken kapatma denemesi.",
                resolution="İnceleme tamamlandı.",
            )
        self.service.update_task(
            record.id, task.id, status="done",
            reason="Kaynak kayıtları gözden geçirildi.",
        )
        closed = self.service.set_status(
            record.id, "closed", reason="Bütün görevler tamamlandı.",
            resolution="Kanıtlar incelendi ve işlem tamamlandı.",
        )
        self.assertEqual(closed.case.status, "closed")
        with self.assertRaisesRegex(ValidationError, "Kapalı vakaya görev"):
            self.service.add_task(
                record.id, "Geçersiz görev", due_at=None,
                reason="Kapalı vakada görev deneniyor.",
            )
        reopened = self.service.set_status(
            record.id, "investigating", reason="Yeni bilgi nedeniyle yeniden açıldı.",
        )
        self.assertIsNone(reopened.case.resolution)
        details = self.service.show(record.id)
        self.assertEqual(details.open_task_count, 0)
        self.assertEqual(details.total_task_count, 1)
        self.assertEqual(details.total_activity_count, 6)
        self.assertIn(note.id, [activity.id for activity in details.activities])
        self.assertEqual(details.activities[0].activity_type, "case_created")

    def test_finding_link_remove_reactivate_and_refresh_preserve_source(self):
        record, finding_id = self.create_case(), self.insert_finding()
        added = self.service.add_evidence(
            record.id, "finding", finding_id,
            reason="Domain adayı vakayla doğrudan ilgili.",
        )
        self.assertEqual(added.action, "added")
        repeated = self.service.add_evidence(
            record.id, "finding", finding_id,
            reason="Aynı kanıt tekrar seçildi.",
        )
        self.assertEqual((repeated.action, repeated.changed), ("unchanged", False))
        removed = self.service.remove_evidence(
            record.id, added.evidence.id,
            reason="Bu inceleme dalında geçici olarak kapsam dışı.",
        )
        self.assertFalse(removed.evidence.active)
        with self.storage._connection() as connection, connection:
            connection.execute(
                "UPDATE findings SET status='suspicious' WHERE id=?", (finding_id,),
            )
        reactivated = self.service.add_evidence(
            record.id, "finding", finding_id,
            reason="Yeni insan kararı sonrasında yeniden kapsama alındı.",
        )
        self.assertEqual(reactivated.action, "reactivated")
        payload = json.loads(reactivated.evidence.snapshot_json)
        self.assertEqual(payload["finding"]["status"], "suspicious")
        self.assertEqual(reactivated.evidence.id, added.evidence.id)
        self.assertEqual(self.service.show(record.id).total_activity_count, 4)

    def test_supplier_review_card_can_be_frozen_without_breach_conclusion(self):
        supplier = self.supplier_service.add(
            "Example Cloud", domain="example-cloud.com", relationship_type="cloud",
            criticality="critical", reason="İş için kullanılan kritik bulut hizmeti.",
        ).supplier
        record = self.create_case()
        result = self.service.add_evidence(
            record.id, "supplier", supplier.id,
            reason="Tedarikçi kartı insan incelemesine eklendi.",
        )
        payload = json.loads(result.evidence.snapshot_json)
        self.assertEqual(payload["kind"], "supplier_review_card")
        self.assertEqual(
            payload["details"]["card"]["attention"], "insufficient_data",
        )
        self.assertIn("doğrulanmış ihlal değildir", payload["limitations"][0])

    def test_both_ransomware_sources_remain_separate_unverified_evidence(self):
        threat_feed = parse_threatcluster_ransomware_response(
            threatcluster_content([claim(
                "Example Holding", website="www.example.com",
                discovered="2026-10-30T12:00:00+00:00",
            )]),
            fetched_at=NOW,
        )
        SQLiteRansomwareClaimRepository(self.path).apply(
            threat_feed, started_at=NOW.isoformat(),
            finished_at=(NOW + timedelta(seconds=1)).isoformat(), item_limit=100,
        )
        ransom_feed = parse_ransomlook_ransomware_response(
            ransomlook_content([post(
                "Example Holding", group="example-group",
                discovered="2026-10-30T18:00:00Z",
            )]),
            fetched_at=NOW + timedelta(minutes=1),
        )
        SQLiteRansomLookClaimRepository(self.path).apply(
            ransom_feed, started_at=(NOW + timedelta(minutes=1)).isoformat(),
            finished_at=(NOW + timedelta(minutes=1, seconds=1)).isoformat(),
            item_limit=100,
        )
        record = self.create_case()
        first = self.service.add_evidence(
            record.id, "ransomware_threatcluster", threat_feed.claims[0].id,
            reason="ThreatCluster iddiası ayrı kaynak kanıtı olarak eklendi.",
        ).evidence
        second = self.service.add_evidence(
            record.id, "ransomware_ransomlook", ransom_feed.claims[0].id,
            reason="RansomLook iddiası ayrı kaynak kanıtı olarak eklendi.",
        ).evidence
        self.assertNotEqual(first.evidence_type, second.evidence_type)
        self.assertEqual(json.loads(first.snapshot_json)["source"], "threatcluster")
        self.assertEqual(json.loads(second.snapshot_json)["source"], "ransomlook")
        self.assertIn("doğrulanmış ihlal değildir", json.loads(first.snapshot_json)["limitations"][0])

    def test_reviewed_social_profile_is_linked_by_candidate_identity(self):
        watch_id, run_id = str(uuid4()), str(uuid4())
        platforms_json = '["GitHub"]'
        definition = brand_watch_definition_sha256(
            username="examplebrand", platforms=("GitHub",),
        )
        state = brand_watch_item_state_sha256(
            platform="GitHub", status="found_unverified",
            profile_url="https://github.com/examplebrand",
        )
        result_json = json.dumps(
            [{"platform": "GitHub", "state_sha256": state}],
            ensure_ascii=True, separators=(",", ":"), sort_keys=True,
        )
        result_sha = hashlib.sha256(result_json.encode("utf-8")).hexdigest()
        candidate_id = brand_username_review_candidate_id(
            watch_id=watch_id, definition_sha256=definition,
            platform="GitHub", state_sha256=state,
        )
        candidate = BrandUsernameReviewCandidate(
            id=candidate_id, watch_id=watch_id, run_id=run_id, run_sequence=1,
            definition_sha256=definition, username="examplebrand", platform="GitHub",
            profile_url="https://github.com/examplebrand", state_sha256=state,
            observed_at=NOW.isoformat(),
        )
        candidate_json = brand_username_review_candidate_json(candidate)
        candidate_sha = brand_username_review_candidate_sha256(candidate)
        with self.storage._connection() as connection, connection:
            connection.execute(
                "INSERT INTO brand_username_watches "
                "(id, name_key, display_name, username, platforms_json, active, "
                "created_at, updated_at, source_key) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
                (
                    watch_id, "example social", "Example Social", "examplebrand",
                    platforms_json, NOW.isoformat(), NOW.isoformat(), "maigret",
                ),
            )
            connection.execute(
                "INSERT INTO brand_username_watch_events "
                "(id, watch_id, action, definition_sha256, reason, recorded_at) "
                "VALUES (?, ?, 'added', ?, ?, ?)",
                (
                    str(uuid4()), watch_id, definition, "", NOW.isoformat(),
                ),
            )
            connection.execute(
                "INSERT INTO brand_username_watch_runs "
                "(id, watch_id, status, source_name, source_version, integration_profile, "
                "username, platforms_json, definition_sha256, previous_complete_run_id, "
                "checked_at, recorded_at, platform_count, found_count, newly_found_count, "
                "changed_count, unchanged_found_count, no_longer_reported_count, "
                "unreported_count, result_sha256, error) VALUES "
                "(?, ?, 'complete', 'Maigret', 'test', 'test', ?, ?, ?, NULL, ?, ?, "
                "1, 1, 0, 0, 0, 0, 0, ?, NULL)",
                (
                    run_id, watch_id, "examplebrand", platforms_json, definition,
                    NOW.isoformat(), NOW.isoformat(), result_sha,
                ),
            )
            connection.execute(
                "INSERT INTO brand_username_watch_run_items "
                "(id, run_id, platform, profile_url, result_status, action, state_sha256) "
                "VALUES (?, ?, 'GitHub', ?, 'found_unverified', 'baseline_found', ?)",
                (
                    str(uuid4()), run_id,
                    "https://github.com/examplebrand", state,
                ),
            )
            connection.execute(
                "INSERT INTO brand_username_review_events "
                "(id, candidate_id, watch_id, run_id, platform, candidate_json, "
                "candidate_sha256, decision, reason, recorded_at, previous_event_id) "
                "VALUES (?, ?, ?, ?, 'GitHub', ?, ?, 'possible_impersonation', ?, ?, NULL)",
                (
                    str(uuid4()), candidate_id, watch_id, run_id, candidate_json,
                    candidate_sha, "Marka hesabı tanımadığını belirtti.", NOW.isoformat(),
                ),
            )
        record = self.create_case()
        evidence = self.service.add_evidence(
            record.id, "social_profile", candidate_id,
            reason="İnsan kararlı profil inceleme vakasına bağlandı.",
        ).evidence
        payload = json.loads(evidence.snapshot_json)
        self.assertEqual(payload["candidate"]["id"], candidate_id)
        self.assertEqual(payload["current_review"]["decision"], "possible_impersonation")

    def test_corrupt_snapshot_fails_closed_and_backup_restore_preserves_case(self):
        record, finding_id = self.create_case(), self.insert_finding()
        link = self.service.add_evidence(
            record.id, "finding", finding_id,
            reason="Kalıcılık testi için bağlandı.",
        ).evidence
        snapshot = Path(self.temp.name) / "case-backup.db"
        self.storage.backup(snapshot)
        restored_path = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(snapshot, restored_path)
        restored = CaseService(
            SQLiteCaseRepository(restored_path),
            CaseEvidenceResolverService(SQLiteCaseEvidenceSourceRepository(restored_path)),
            clock=lambda: NOW,
        )
        self.assertEqual(restored.show(record.id).active_evidence_count, 1)
        with closing(sqlite3.connect(restored_path)) as connection, connection:
            connection.execute(
                "UPDATE cases SET title='Zaman çizelgesiz değiştirilmiş vaka' WHERE id=?",
                (record.id,),
            )
        with self.assertRaisesRegex(StorageError, "zaman çizelgesiyle uyuşmuyor"):
            restored.show(record.id)

        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE case_evidence SET snapshot_sha256=? WHERE id=?",
                ("0" * 64, link.id),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "kanıt bağı bozuk"):
            self.service.show(record.id)
        self.assertEqual(self.path.read_bytes(), before)

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_terminal_json_report_and_read_only_views(self):
        code, stdout, stderr = self.invoke(
            "cases", "create", "CLI vaka",
            "--summary", "Terminal vaka yönetimi kabul testi.",
            "--priority", "medium", "--reason", "CLI akışını doğrulamak için.",
        )
        self.assertEqual((code, stderr), (0, ""))
        case_id = json.loads(stdout)["data"]["case"]["id"]
        before = self.path.read_bytes()
        for arguments in (
            ("cases", "list"),
            ("cases", "show", case_id),
            ("cases", "report", case_id),
        ):
            code, stdout, stderr = self.invoke(*arguments)
            self.assertEqual((code, stderr), (0, ""))
            self.assertTrue(json.loads(stdout)["ok"])
        code, stdout, stderr = self.invoke("cases", "report", case_id, as_json=False)
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Vaka raporu", stdout)
        self.assertIn("doğrulanmış olay saymaz", stdout)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

