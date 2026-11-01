"""Approved-scope DNS/TLS baselines and change evidence."""

from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.application.assets import AssetService
from xti.application.surface import SurfaceService
from xti.domain.assets import ValidationError
from xti.domain.enrichment import CertificateEvidence, ProbeResult
from xti.interfaces.surface import check_lines


START = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


def certificate(*, fingerprint="a" * 64, expires="2026-12-31T23:59:59+00:00"):
    return CertificateEvidence(
        sha256=fingerprint, serial_number="01a2",
        not_before="2026-10-01T00:00:00+00:00", not_after=expires,
        issuer="Fixture CA", subject="example.com",
        dns_names=("*.example.com", "example.com"),
    )


def result(*, addresses=("93.184.216.34",), tls="valid", http="responded", code=200):
    return ProbeResult(
        domain="example.com", started_at=START.isoformat(),
        finished_at=(START + timedelta(seconds=1)).isoformat(),
        policy_version="surface-test-v1", dns_status="resolved", addresses=addresses,
        tls_status=tls, http_status=http, http_status_code=code,
        connected_address=addresses[0], errors=(), notes=("Sınırlı test.",),
    )


class SequenceProbe:
    def __init__(self, values):
        self.values = list(values)
        self.calls = []

    def check(self, domain):
        self.calls.append(domain)
        return self.values.pop(0)


class SurfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.assets = AssetService(self.storage)
        self.asset, _ = self.assets.add("example.com")
        self.ticks = iter(START + timedelta(minutes=index) for index in range(30))
        self.repo = SQLiteSurfaceRepository(self.path, clock=lambda: next(self.ticks))
        self.service = SurfaceService(
            self.storage, self.repo, clock=lambda: next(self.ticks),
        )

    def test_scope_lifecycle_is_idempotent_reversible_and_append_only(self):
        scope, changed = self.service.approve("EXAMPLE.COM", "Kendi alan adım")
        self.assertEqual((scope.active, changed), (True, True))
        same, changed = self.service.approve("example.com", "Kendi alan adım")
        self.assertEqual(same.asset_id, scope.asset_id)
        self.assertFalse(changed)
        updated, changed = self.service.approve("example.com", "Kurumsal ana alan adım")
        self.assertTrue(changed)
        self.assertEqual(updated.created_at, scope.created_at)
        revoked = self.service.revoke("example.com", "Geçici olarak kapsam dışı")
        self.assertFalse(revoked.active)
        restored, changed = self.service.approve("example.com", "Yeniden yetkili kapsam")
        self.assertEqual((restored.active, changed), (True, True))
        details = self.service.show("example.com")
        self.assertEqual(
            [event.action for event in details.events],
            ["approved", "updated", "revoked", "reactivated"],
        )
        self.assertEqual(details.scope.asset_id, scope.asset_id)

    def test_baseline_repeat_and_real_change_are_separate_evidence(self):
        self.service.approve("example.com", "Kendi alan adım")
        changed_result = result(addresses=("93.184.216.35",))
        probe = SequenceProbe([result(), result(), changed_result])
        service = SurfaceService(self.storage, self.repo, probe)
        first = service.check("example.com")
        second = service.check("example.com")
        third = service.check("example.com")
        self.assertEqual([first.change.kind, second.change.kind, third.change.kind], [
            "baseline", "unchanged", "changed",
        ])
        self.assertEqual(first.change.added_addresses, ("93.184.216.34",))
        self.assertEqual(second.change.added_addresses, ())
        self.assertEqual(third.change.added_addresses, ("93.184.216.35",))
        self.assertEqual(third.change.removed_addresses, ("93.184.216.34",))
        self.assertIn("connected_address", third.change.changed_fields)
        details = self.service.show("example.com")
        self.assertEqual(details.total_check_count, 3)
        self.assertEqual([item.id for item in details.checks], [first.id, second.id, third.id])
        self.assertEqual(probe.calls, ["example.com"] * 3)
        summary = self.service.list()[0]
        self.assertEqual(summary.latest_check.id, third.id)
        self.assertEqual(summary.check_count, 3)

    def test_dns_answer_order_does_not_create_a_false_change(self):
        self.service.approve("example.com", "Kendi alan adım")
        first_result = result(addresses=("1.1.1.1", "8.8.8.8"))
        reordered = replace(first_result, addresses=("8.8.8.8", "1.1.1.1"))
        service = SurfaceService(
            self.storage, self.repo, SequenceProbe([first_result, reordered]),
        )
        first = service.check("example.com")
        second = service.check("example.com")
        self.assertEqual(second.change.kind, "unchanged")
        self.assertEqual(second.state_sha256, first.state_sha256)

    def test_verified_certificate_identity_participates_in_surface_change(self):
        self.service.approve("example.com", "Kendi alan adım")
        first_result = replace(result(), certificate=certificate())
        same_result = replace(result(), certificate=certificate())
        renewed_result = replace(
            result(), certificate=certificate(
                fingerprint="b" * 64, expires="2027-12-31T23:59:59+00:00",
            ),
        )
        service = SurfaceService(
            self.storage, self.repo,
            SequenceProbe([first_result, same_result, renewed_result]),
        )
        first = service.check("example.com")
        same = service.check("example.com")
        renewed = service.check("example.com")
        self.assertEqual(same.change.kind, "unchanged")
        self.assertEqual(renewed.change.kind, "changed")
        self.assertEqual(renewed.change.changed_fields, ("certificate",))
        self.assertNotEqual(first.state_sha256, renewed.state_sha256)
        self.assertEqual(
            self.service.show("example.com").checks[-1].result.certificate.sha256, "b" * 64,
        )

    def test_terminal_warns_when_verified_certificate_nears_expiry(self):
        self.service.approve("example.com", "Kendi alan adım")
        record = replace(
            result(), certificate=certificate(expires="2026-11-10T00:00:00+00:00"),
        )
        saved = SurfaceService(
            self.storage, self.repo, SequenceProbe([record]),
        ).check("example.com")
        rendered = "\n".join(check_lines(saved, now=START))
        self.assertIn("Veren: Fixture CA", rendered)
        self.assertIn("Bitişe 12 gün kaldı", rendered)
        self.assertIn("a" * 64, rendered)

    def test_revocation_during_probe_prevents_evidence_commit(self):
        self.service.approve("example.com", "Kendi alan adım")

        class RevokingProbe:
            def check(inner_self, domain):
                self.service.revoke(domain, "Kontrol sırasında yetki geri çekildi")
                return result()

        service = SurfaceService(self.storage, self.repo, RevokingProbe())
        with self.assertRaisesRegex(ValidationError, "kaldırılmış"):
            service.check("example.com")
        details = self.service.show("example.com")
        self.assertEqual(details.total_check_count, 0)
        self.assertFalse(details.scope.active)

    def test_unapproved_or_unregistered_domain_never_calls_probe(self):
        probe = SequenceProbe([result()])
        service = SurfaceService(self.storage, self.repo, probe)
        with self.assertRaisesRegex(ValidationError, "kapsamına alınmamış"):
            service.check("example.com")
        with self.assertRaisesRegex(ValidationError, "kayıtlı değil"):
            service.check("not-example.com")
        self.assertEqual(probe.calls, [])

    def test_corrupt_state_or_change_fails_closed_without_mutation(self):
        self.service.approve("example.com", "Kendi alan adım")
        SurfaceService(self.storage, self.repo, SequenceProbe([result()])).check("example.com")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE surface_checks SET change = '{}' ")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "kontrol geçmişi bozuk"):
            self.service.show("example.com")
        self.assertEqual(self.path.read_bytes(), before)

    def test_backup_restore_preserves_scope_events_checks_and_hashes(self):
        self.service.approve("example.com", "Kendi alan adım")
        SurfaceService(self.storage, self.repo, SequenceProbe([result()])).check("example.com")
        before = self.service.show("example.com")
        backup = self.storage.backup(Path(self.temp.name) / "backups" / "surface.db")
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        restored_assets = SQLiteAssetRepository(restored)
        restored_repo = SQLiteSurfaceRepository(restored)
        after = SurfaceService(restored_assets, restored_repo).show("example.com")
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
