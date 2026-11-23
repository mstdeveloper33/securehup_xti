"""P06 runbooks, evidence packages and human-approved takedown acceptance."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.case_package_files import AtomicCasePackagePublisher
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_actionability import SQLiteActionabilityRepository
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_case_packages import SQLiteCasePackageReader
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.application.actionability import ActionabilityService
from xti.application.case_packages import CasePackageService
from xti.application.cases import CaseEvidenceResolverService, CaseService
from xti.domain.assets import ValidationError


NOW = datetime(2026, 11, 22, 8, tzinfo=timezone.utc)


class ActionabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path); self.storage.initialize()
        resolver = CaseEvidenceResolverService(SQLiteCaseEvidenceSourceRepository(self.path))
        self.cases = CaseService(SQLiteCaseRepository(self.path), resolver, clock=lambda: NOW)
        self.case = self.cases.create(
            "<script>alert(1)</script> marka olayı",
            summary="Şüpheli marka alan adı insan tarafından incelenecek.",
            priority="high", reason="P06 kabul vakası oluşturuldu.",
        ).case
        asset, _ = self.storage.add("example.com")
        self.finding_id = str(uuid4())
        with self.storage._connection() as connection, connection:
            connection.execute(
                "INSERT INTO findings (id,asset_id,asset_value,domain,rule_version,reasons,status,created_at,last_seen_at) "
                "VALUES (?,?,?,?,?,?,'suspicious',?,?)",
                (self.finding_id, asset.id, asset.value, "example-login.test", "p06/test",
                 json.dumps(["marka benzerliği"]), NOW.isoformat(), NOW.isoformat()),
            )
        self.evidence = self.cases.add_evidence(
            self.case.id, "finding", self.finding_id,
            reason="İnsan incelemesi için domain kanıtı bağlandı.",
        ).evidence
        self.service = ActionabilityService(
            SQLiteActionabilityRepository(self.path),
            clock=lambda: NOW + timedelta(minutes=1),
        )

    def test_runbook_plan_apply_is_deterministic_atomic_and_idempotent(self):
        first = self.service.runbook_plan(self.case.id)
        second = self.service.runbook_plan(self.case.id)
        self.assertEqual(first, second)
        self.assertIn("domain-context", [item.code for item in first.steps])
        applied = self.service.runbook_apply(
            self.case.id, expected_plan_sha256=first.plan_sha256,
            idempotency_key="runbook:acceptance:1",
            reason="Savunma görevleri insan incelemesine açılıyor.",
        )
        replay = self.service.runbook_apply(
            self.case.id, expected_plan_sha256=first.plan_sha256,
            idempotency_key="runbook:acceptance:1",
            reason="Savunma görevleri insan incelemesine açılıyor.",
        )
        self.assertFalse(applied.replayed); self.assertTrue(replay.replayed)
        self.assertEqual(applied.created_task_ids, replay.created_task_ids)
        details = self.cases.show(self.case.id, task_limit=500, activity_limit=1000)
        self.assertEqual(details.total_task_count, len(first.steps))
        self.assertEqual(len(set(applied.created_task_ids)), len(first.steps))
        self.cases.update(
            self.case.id, summary="Runbook uygulamasından sonra vaka kapsamı değişti.",
            reason="Başarılı isteğin tekrar makbuzu sınanıyor.",
        )
        later_replay = self.service.runbook_apply(
            self.case.id, expected_plan_sha256=first.plan_sha256,
            idempotency_key="runbook:acceptance:1",
            reason="Savunma görevleri insan incelemesine açılıyor.",
        )
        self.assertTrue(later_replay.replayed)
        self.assertEqual(later_replay.created_task_ids, applied.created_task_ids)
        with self.assertRaisesRegex(ValidationError, "farklı bir istek"):
            self.service.repository.apply_runbook(
                self.case.id, expected_plan_sha256=first.plan_sha256,
                idempotency_key="runbook:acceptance:1",
                reason="Farklı tekrar isteği kabul edilmemeli.",
                recorded_at=(NOW + timedelta(minutes=2)).isoformat(),
            )

    def test_stale_runbook_plan_is_rejected_before_tasks_are_written(self):
        plan = self.service.runbook_plan(self.case.id)
        self.cases.update(
            self.case.id, summary="Vaka özeti yeni kanıtla değiştirildi.",
            reason="Plan sonrası vaka kapsamı değişti.",
        )
        before = self.cases.show(self.case.id).total_task_count
        with self.assertRaisesRegex(ValidationError, "planı değişmiş"):
            self.service.runbook_apply(
                self.case.id, expected_plan_sha256=plan.plan_sha256,
                idempotency_key="runbook:stale", reason="Eski plan deneniyor.",
            )
        self.assertEqual(self.cases.show(self.case.id).total_task_count, before)

    def test_takedown_requires_human_approval_and_never_submits_automatically(self):
        draft = self.service.takedown_create(
            self.case.id, self.evidence.id, target_kind="registrar",
            target_value="example-login.test", recipient="abuse@example-registrar.test",
            requested_action="Alan adı kötüye kullanım incelemesine alınsın.",
            grounds="Marka sahibi tarafından doğrulanmış şüpheli taklit adayı.",
            idempotency_key="takedown:1", actor="analyst@example.test",
        )
        self.assertEqual(draft.request.state, "draft")
        self.assertFalse(draft.draft["automatic_submission"])
        with self.assertRaises(ValidationError):
            self.service.takedown_transition(
                draft.request.id, action="submit", expected_revision=0,
                actor="analyst@example.test", reason="Onaysız gönderim deneniyor.",
                external_reference="ticket:invalid",
            )
        approved = self.service.takedown_transition(
            draft.request.id, action="approve", expected_revision=0,
            actor="owner@example.test", reason="Kanıt ve marka yetkisi insan tarafından doğrulandı.",
        )
        submitted = self.service.takedown_transition(
            draft.request.id, action="submit", expected_revision=1,
            actor="owner@example.test", reason="Başvuru sağlayıcı portalında insan tarafından yapıldı.",
            external_reference="registrar-ticket:12345",
        )
        resolved = self.service.takedown_transition(
            draft.request.id, action="resolve", expected_revision=2,
            actor="analyst@example.test", reason="Hedefin erişilemediği bağımsız yeniden kontrolde görüldü.",
        )
        self.assertEqual((approved.request.state, submitted.request.state, resolved.request.state),
                         ("approved", "submitted", "resolved"))
        self.assertEqual([item.action for item in resolved.events], ["draft", "approve", "submit", "resolve"])
        self.assertEqual(resolved.request.external_reference, "registrar-ticket:12345")
        report = self.storage.inspect()
        self.assertEqual(report["action_takedown_count"], 1)
        self.assertEqual(report["open_action_takedown_count"], 0)

    def test_takedown_create_replay_survives_case_change_but_new_approval_does_not(self):
        options = {
            "target_kind": "registrar",
            "target_value": "example-login.test",
            "recipient": "abuse@example-registrar.test",
            "requested_action": "Alan adı kötüye kullanım incelemesine alınsın.",
            "grounds": "İnsan incelemesine hazırlanmış savunma amaçlı taslak.",
            "idempotency_key": "takedown:closed-replay",
            "actor": "analyst@example.test",
        }
        draft = self.service.takedown_create(
            self.case.id, self.evidence.id, **options,
        )
        self.cases.set_status(
            self.case.id, "closed", reason="Acceptance vakası kapatılıyor.",
            resolution="Takedown taslağı gönderilmeden vaka kapatıldı.",
        )
        replay = self.service.takedown_create(
            self.case.id, self.evidence.id, **options,
        )
        self.assertEqual(replay.request.id, draft.request.id)
        self.assertEqual(replay.request.state, "draft")
        with self.assertRaisesRegex(ValidationError, "Kapalı vakada"):
            self.service.takedown_transition(
                draft.request.id, action="approve", expected_revision=0,
                actor="owner@example.test", reason="Kapalı vaka onayı deneniyor.",
            )

    def test_takedown_approval_requires_still_active_evidence(self):
        draft = self.service.takedown_create(
            self.case.id, self.evidence.id, target_kind="registrar",
            target_value="example-login.test", recipient="abuse@example-registrar.test",
            requested_action="Alan adı kötüye kullanım incelemesine alınsın.",
            grounds="Etkin vaka kanıtından hazırlanmış savunma amaçlı taslak.",
            idempotency_key="takedown:withdrawn-evidence",
            actor="analyst@example.test",
        )
        self.cases.remove_evidence(
            self.case.id, self.evidence.id,
            reason="Kanıt analist incelemesinde geri çekildi.",
        )
        with self.assertRaisesRegex(ValidationError, "artık etkin"):
            self.service.takedown_transition(
                draft.request.id, action="approve", expected_revision=0,
                actor="owner@example.test", reason="Geri çekilmiş kanıtla onay deneniyor.",
            )

    def test_takedown_listing_fails_closed_on_event_audit_tampering(self):
        draft = self.service.takedown_create(
            self.case.id, self.evidence.id, target_kind="registrar",
            target_value="example-login.test", recipient="abuse@example-registrar.test",
            requested_action="Alan adı kötüye kullanım incelemesine alınsın.",
            grounds="İnsan incelemesine gönderilen savunma amaçlı taslak.",
            idempotency_key="takedown:corruption", actor="analyst@example.test",
        )
        self.service.takedown_transition(
            draft.request.id, action="approve", expected_revision=0,
            actor="owner@example.test", reason="Yetkili insan onayı.",
        )
        with self.storage._connection() as connection, connection:
            connection.execute(
                "UPDATE action_takedown_events SET reason='Değiştirilmiş denetim gerekçesi.' "
                "WHERE request_id=? AND revision=1", (draft.request.id,),
            )
        with self.assertRaisesRegex(StorageError, "anlık görüntüsü"):
            self.service.takedown_show(draft.request.id)
        with self.assertRaisesRegex(StorageError, "anlık görüntüsü"):
            self.service.takedown_list(case_id=self.case.id)

    def test_case_package_is_exclusive_escaped_and_self_verifying(self):
        destination = Path(self.temp.name) / "case-package"
        packages = CasePackageService(
            SQLiteCasePackageReader(self.path), AtomicCasePackagePublisher(),
            clock=lambda: NOW + timedelta(minutes=2),
        )
        fake_pdf = b"%PDF-1.7\nP06 offline fixture\n%%EOF\n"
        with patch("xti.adapters.case_package_files.render_pdf", return_value=fake_pdf):
            artifact = packages.create(self.case.id, destination, include_pdf=True)
        self.assertTrue(artifact.pdf_included)
        html = (destination / "executive.html").read_text()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertEqual(packages.verify(destination).manifest_sha256, artifact.manifest_sha256)
        with self.assertRaisesRegex(ValidationError, "zaten var"):
            packages.create(self.case.id, destination)
        with (destination / "evidence.csv").open("ab") as stream:
            stream.write(b"tamper")
        with self.assertRaisesRegex(ValidationError, "bütünlüğü"):
            packages.verify(destination)

    def test_case_package_verifier_never_follows_artifact_symlinks(self):
        destination = Path(self.temp.name) / "linked-package"
        packages = CasePackageService(
            SQLiteCasePackageReader(self.path), AtomicCasePackagePublisher(),
            clock=lambda: NOW + timedelta(minutes=2),
        )
        packages.create(self.case.id, destination)
        outside = Path(self.temp.name) / "outside.html"
        outside.write_text("<p>outside</p>")
        html = destination / "executive.html"
        html.unlink()
        html.symlink_to(outside)
        with self.assertRaisesRegex(ValidationError, "gerçek dosya"):
            packages.verify(destination)


if __name__ == "__main__":
    unittest.main()
