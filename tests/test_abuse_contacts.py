"""Persistent, reviewed abuse-contact discovery and takedown binding acceptance."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_abuse_contacts import SQLiteAbuseContactRepository
from xti.adapters.sqlite_actionability import SQLiteActionabilityRepository
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.application.abuse_contacts import AbuseContactService
from xti.application.actionability import ActionabilityService
from xti.application.cases import CaseEvidenceResolverService, CaseService
from xti.domain.abuse_contact_contract import PREFIX
from xti.domain.abuse_contacts import ContactObservation, source_outcome
from xti.domain.assets import ValidationError


NOW = datetime(2026, 11, 25, 9, tzinfo=timezone.utc)


def _candidate(*, marker: str = "first", observed_at: str = NOW.isoformat(),
               subject: str = "example-login.test"):
    return ContactObservation(
        contact_kind="registrar_abuse", channel="email",
        contact_value="abuse@registrar.example", routing_kind="registrar",
        source_key="domain_rdap",
        source_reference="https://rdap.registrar.example/domain/" + subject,
        confidence="high", observed_at=observed_at,
        evidence={
            "kind": "rdap_abuse_contact", "version": 1,
            "roles": ["abuse"], "handle": marker, "entity_path": [0],
            "response_sha256": marker.ljust(64, "0")[:64], "connector_version": 1,
        },
    )


def _success(*, marker: str = "first", observed_at: str = NOW.isoformat(),
             subject: str = "example-login.test"):
    candidate = _candidate(marker=marker, observed_at=observed_at, subject=subject)
    return (
        source_outcome(
            "domain_rdap", "complete", candidate.source_reference, observed_at,
            body=("rdap-" + marker).encode(), candidates=(candidate,),
            request_count=2, received_bytes=500, elapsed_ms=20,
        ),
        source_outcome(
            "security_txt", "empty", f"https://{subject}/.well-known/security.txt",
            observed_at, body=b"not-found", request_count=1, received_bytes=9, elapsed_ms=5,
        ),
        source_outcome(
            "whois", "skipped", "whois://" + subject, observed_at,
            error_code="fallback_not_needed", error="RDAP abuse iletişimi verdi.",
        ),
    )


def _failure(observed_at: str):
    return (
        source_outcome(
            "domain_rdap", "failed", "https://data.iana.org/rdap/dns.json",
            observed_at, error_code="timeout", error="Kaynak zamanında yanıt vermedi.",
        ),
        source_outcome(
            "security_txt", "failed", "https://example-login.test/.well-known/security.txt",
            observed_at, error_code="connection", error="Kaynak okunamadı.",
        ),
        source_outcome(
            "whois", "requirement_missing", "whois://example-login.test",
            observed_at, error_code="whois_not_installed", error="WHOIS aracı kurulu değil.",
        ),
    )


class Sources:
    def __init__(self, *batches):
        self.batches = list(batches)
        self.calls = []

    def local_capabilities(self):
        return {"whois_available": False}

    def collect(self, subject_kind, subject_value, *, include_whois, timeout_seconds):
        self.calls.append((subject_kind, subject_value, include_whois, timeout_seconds))
        if not self.batches:
            raise AssertionError("Unexpected collection")
        return self.batches.pop(0)


class AbuseContactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path); self.storage.initialize()
        resolver = CaseEvidenceResolverService(SQLiteCaseEvidenceSourceRepository(self.path))
        self.cases = CaseService(SQLiteCaseRepository(self.path), resolver, clock=lambda: NOW)
        self.case = self.cases.create(
            "Taklit domain incelemesi", summary="İnsan incelemeli takedown kabul vakası.",
            priority="high", reason="Abuse iletişim kabul vakası oluşturuldu.",
        ).case
        asset, _ = self.storage.add("example.com")
        finding_id = str(uuid4())
        with self.storage._connection() as connection, connection:
            connection.execute(
                "INSERT INTO findings (id,asset_id,asset_value,domain,rule_version,reasons,status,created_at,last_seen_at) "
                "VALUES (?,?,?,?,?,?,'suspicious',?,?)",
                (finding_id, asset.id, asset.value, "example-login.test", "contact/test",
                 json.dumps(["marka benzerliği"]), NOW.isoformat(), NOW.isoformat()),
            )
        self.evidence = self.cases.add_evidence(
            self.case.id, "finding", finding_id,
            reason="İncelenecek taklit domain kanıtı vakaya bağlandı.",
        ).evidence
        self.repository = SQLiteAbuseContactRepository(self.path)

    def _service(self, source, at=NOW + timedelta(minutes=1)):
        return AbuseContactService(self.repository, source, clock=lambda: at)

    def _watch(self, service):
        return service.execute(
            PREFIX + "watch.add", case_id=self.case.id,
            evidence_link_id=self.evidence.id, subject_kind="domain",
            subject_value="example-login.test", interval_seconds=300,
            include_whois=True, actor="analyst@example.test",
            reason="Takedown iletişim rotası pasif kaynaklarla izlenecek.",
            idempotency_key="contact-watch:1",
        )

    def test_full_reviewed_contact_lifecycle_and_takedown_binding(self):
        source = Sources(
            _success(),
            _success(marker="changed", observed_at=(NOW + timedelta(minutes=6)).isoformat()),
        )
        service = self._service(source)
        watch = self._watch(service)
        replay = self._watch(service)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["id"], watch["id"])
        with self.assertRaisesRegex(ValidationError, "farklı istek"):
            service.execute(
                PREFIX + "watch.add", case_id=self.case.id,
                evidence_link_id=self.evidence.id, subject_kind="domain",
                subject_value="example-login.test", interval_seconds=600,
                include_whois=True, actor="analyst@example.test",
                reason="Takedown iletişim rotası pasif kaynaklarla izlenecek.",
                idempotency_key="contact-watch:1",
            )

        run = service.execute(
            PREFIX + "refresh", watch_id=watch["id"], expected_revision=watch["revision"],
            force=True, timeout_seconds=60, idempotency_key="contact-refresh:1",
        )
        self.assertEqual(run["status"], "complete")
        self.assertFalse(run["report"]["automatic_submission"])
        self.assertEqual(run["candidate_count"], 1)
        replay_run = service.execute(
            PREFIX + "refresh", watch_id=watch["id"], expected_revision=watch["revision"],
            force=True, timeout_seconds=60, idempotency_key="contact-refresh:1",
        )
        self.assertTrue(replay_run["replayed"])
        self.assertEqual(len(source.calls), 1)

        candidate = service.execute(
            PREFIX + "candidates", watch_id=watch["id"], offset=0, limit=50,
        )["items"][0]
        reviewed = service.execute(
            PREFIX + "review", candidate_id=candidate["id"],
            expected_observation_revision=1, expected_review_revision=0,
            decision="approved", actor="owner@example.test",
            reason="RDAP abuse rolü ve adresi insan tarafından doğrulandı.",
            idempotency_key="contact-review:1",
        )
        self.assertTrue(reviewed["usable_for_takedown"])
        replayed_review = service.execute(
            PREFIX + "review", candidate_id=candidate["id"],
            expected_observation_revision=1, expected_review_revision=0,
            decision="approved", actor="owner@example.test",
            reason="RDAP abuse rolü ve adresi insan tarafından doğrulandı.",
            idempotency_key="contact-review:1",
        )
        self.assertTrue(replayed_review["replayed"])
        with self.assertRaisesRegex(ValidationError, "farklı istek"):
            service.execute(
                PREFIX + "review", candidate_id=candidate["id"],
                expected_observation_revision=1, expected_review_revision=0,
                decision="rejected", actor="owner@example.test",
                reason="RDAP abuse rolü ve adresi insan tarafından doğrulandı.",
                idempotency_key="contact-review:1",
            )

        actions = ActionabilityService(
            SQLiteActionabilityRepository(self.path),
            clock=lambda: NOW + timedelta(minutes=2),
        )
        draft = actions.takedown_create(
            self.case.id, self.evidence.id,
            target_kind=None, target_value=None, recipient=None,
            contact_candidate_id=candidate["id"],
            requested_action="Alan adı kötüye kullanım incelemesine alınsın.",
            grounds="İnsan tarafından doğrulanmış vaka ve iletişim rotası.",
            idempotency_key="contact-takedown:1", actor="analyst@example.test",
        )
        self.assertEqual(draft.request.recipient, "abuse@registrar.example")
        self.assertEqual(draft.request.target_kind, "registrar")
        self.assertEqual(draft.draft["version"], 2)
        self.assertEqual(draft.contact_binding["candidate_id"], candidate["id"])
        self.assertFalse(draft.draft["automatic_submission"])
        stats = self.storage.inspect()
        self.assertEqual(stats["action_contact_watch_count"], 1)
        self.assertEqual(stats["action_contact_run_count"], 1)
        self.assertEqual(stats["approved_action_contact_candidate_count"], 1)
        self.assertEqual(stats["action_contact_takedown_link_count"], 1)

        changed = service.execute(
            PREFIX + "refresh", watch_id=watch["id"], expected_revision=watch["revision"],
            force=True, timeout_seconds=60, idempotency_key="contact-refresh:2",
        )
        self.assertEqual(changed["updated_count"], 1)
        latest = service.execute(PREFIX + "candidate.show", candidate_id=candidate["id"])
        self.assertEqual(latest["review_state"], "stale")
        self.assertFalse(latest["usable_for_takedown"])
        with self.assertRaisesRegex(ValidationError, "approved insan kararı"):
            actions.takedown_transition(
                draft.request.id, action="approve", expected_revision=0,
                actor="owner@example.test", reason="Eski iletişim kararıyla onay deneniyor.",
            )

    def test_failed_refresh_preserves_last_success_and_recovery_is_idempotent(self):
        source = Sources(_success(), _failure((NOW + timedelta(minutes=6)).isoformat()))
        service = self._service(source)
        watch = self._watch(service)
        service.execute(
            PREFIX + "refresh", watch_id=watch["id"], expected_revision=1,
            force=True, timeout_seconds=60, idempotency_key="contact-refresh:good",
        )
        failed = service.execute(
            PREFIX + "refresh", watch_id=watch["id"], expected_revision=1,
            force=True, timeout_seconds=60, idempotency_key="contact-refresh:failed",
        )
        self.assertEqual(failed["status"], "failed")
        self.assertTrue(failed["report"]["old_evidence_preserved"])
        candidates = service.execute(
            PREFIX + "candidates", watch_id=watch["id"], active=True, offset=0, limit=50,
        )
        self.assertEqual(candidates["total_count"], 1)

        reserved, replayed = self.repository.reserve_run({
            "watch_id": watch["id"], "expected_revision": 1, "force": True,
            "timeout_seconds": 60, "idempotency_key": "contact-refresh:interrupted",
        }, (NOW + timedelta(minutes=7)).isoformat())
        self.assertFalse(replayed)
        recovered = service.execute(
            PREFIX + "recover", run_id=reserved["id"], actor="operator@example.test",
            reason="Kesilen worker turu güvenli şekilde kapatılıyor.",
            idempotency_key="contact-recover:1",
        )
        replay = service.execute(
            PREFIX + "recover", run_id=reserved["id"], actor="operator@example.test",
            reason="Kesilen worker turu güvenli şekilde kapatılıyor.",
            idempotency_key="contact-recover:1",
        )
        self.assertEqual(recovered["status"], "interrupted")
        self.assertTrue(replay["replayed"])
        self.assertEqual(
            service.execute(PREFIX + "candidates", watch_id=watch["id"], offset=0, limit=50)["total_count"],
            1,
        )

    def test_scope_schedule_disable_pagination_and_raw_body_minimization(self):
        service = self._service(Sources(_success()))
        plan = service.execute(
            PREFIX + "plan", case_id=self.case.id, evidence_link_id=self.evidence.id,
            subject_kind="domain", subject_value="example-login.test",
            interval_seconds=300, include_whois=False,
        )
        self.assertEqual(plan["sources"], ["domain_rdap", "security_txt"])
        with self.assertRaisesRegex(ValidationError, "uyuşmuyor"):
            service.execute(
                PREFIX + "plan", case_id=self.case.id, evidence_link_id=self.evidence.id,
                subject_kind="domain", subject_value="unrelated.example",
                interval_seconds=300, include_whois=False,
            )
        watch = self._watch(service)
        due = service.execute(PREFIX + "due", at=(NOW + timedelta(minutes=1)).isoformat(), limit=100)
        self.assertEqual([item["id"] for item in due["items"]], [watch["id"]])
        run = service.execute(
            PREFIX + "refresh", watch_id=watch["id"], expected_revision=1,
            force=True, timeout_seconds=60, idempotency_key="contact-refresh:minimized",
        )
        run_page = service.execute(PREFIX + "runs", watch_id=watch["id"], offset=0, limit=1)
        self.assertEqual(run_page["total_count"], 1)
        self.assertEqual(run_page["items"][0]["id"], run["id"])
        database = self.path.read_bytes()
        self.assertNotIn(b"rdap-first", database)
        self.assertNotIn(b"not-found", database)
        disabled = service.execute(
            PREFIX + "watch.disable", watch_id=watch["id"], expected_revision=1,
            actor="analyst@example.test", reason="İnceleme izlemesi tamamlandı.",
            idempotency_key="contact-disable:1",
        )
        self.assertFalse(disabled["enabled"])
        self.assertEqual(
            service.execute(PREFIX + "due", at=(NOW + timedelta(days=1)).isoformat(), limit=100)["count"],
            0,
        )

    def test_backup_restore_preserves_watch_run_candidate_and_review_history(self):
        service = self._service(Sources(_success()))
        watch = self._watch(service)
        service.execute(
            PREFIX + "refresh", watch_id=watch["id"], expected_revision=1,
            force=True, timeout_seconds=60, idempotency_key="contact-refresh:backup",
        )
        candidate = service.execute(
            PREFIX + "candidates", watch_id=watch["id"], offset=0, limit=50,
        )["items"][0]
        service.execute(
            PREFIX + "review", candidate_id=candidate["id"],
            expected_observation_revision=1, expected_review_revision=0,
            decision="approved", actor="owner@example.test",
            reason="Yedek kabulü için iletişim rotası doğrulandı.",
            idempotency_key="contact-review:backup",
        )
        backup = Path(self.temp.name) / "contact-backup.db"
        restored = Path(self.temp.name) / "restored" / "xti.db"
        self.storage.backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        restored_service = AbuseContactService(
            SQLiteAbuseContactRepository(restored), Sources(),
            clock=lambda: NOW + timedelta(minutes=2),
        )
        restored_watch = restored_service.execute(PREFIX + "watch.show", watch_id=watch["id"])
        restored_candidate = restored_service.execute(
            PREFIX + "candidate.show", candidate_id=candidate["id"],
        )
        restored_run = restored_service.execute(
            PREFIX + "runs", watch_id=watch["id"], offset=0, limit=50,
        )
        self.assertEqual(restored_watch["total_run_count"], 1)
        self.assertTrue(restored_candidate["usable_for_takedown"])
        self.assertEqual(restored_run["total_count"], 1)


if __name__ == "__main__":
    unittest.main()
