"""Approved-scope append-only MX/SPF/DMARC baselines."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_mail import SQLiteSurfaceMailRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.application.assets import AssetService
from xti.application.mail import SurfaceMailService
from xti.application.surface import SurfaceService
from xti.domain.assets import ValidationError
from xti.domain.mail import MailDnsResult
from xti.interfaces.mail import check_lines, detail_lines


START = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


def result(*, mx=("10 mail.example.com",), spf=("v=spf1 -all",),
           dmarc=("v=DMARC1; p=reject",), errors=()):
    statuses = []
    for records, label in ((mx, "MX"), (spf, "SPF"), (dmarc, "DMARC")):
        statuses.append("failed" if any(item.startswith(label + ":") for item in errors)
                        else "present" if records else "missing")
    return MailDnsResult(
        domain="example.com", started_at=START.isoformat(),
        finished_at=(START + timedelta(seconds=1)).isoformat(),
        policy_version="mail-test-v1",
        mx_status=statuses[0], mx_records=mx,
        spf_status=statuses[1], spf_records=spf,
        dmarc_status=statuses[2], dmarc_records=dmarc,
        errors=errors, notes=("Sınırlı DNS kanıtı.",),
    )


class SequenceProbe:
    def __init__(self, values):
        self.values = list(values)
        self.calls = []

    def check(self, domain):
        self.calls.append(domain)
        return self.values.pop(0)


class MailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.asset, _ = AssetService(self.storage).add("example.com")
        self.ticks = iter(START + timedelta(minutes=index) for index in range(30))
        self.scopes = SQLiteSurfaceRepository(self.path, clock=lambda: next(self.ticks))
        self.surface = SurfaceService(
            self.storage, self.scopes, clock=lambda: next(self.ticks),
        )
        self.mail = SQLiteSurfaceMailRepository(
            self.path, clock=lambda: next(self.ticks),
        )

    def approve(self):
        self.surface.approve("example.com", "Kendi kök alan adım")

    def service(self, probe=None):
        return SurfaceMailService(self.storage, self.scopes, self.mail, probe)

    def test_baseline_repeat_and_policy_change_are_append_only(self):
        self.approve()
        changed = result(dmarc=("v=DMARC1; p=quarantine",))
        probe = SequenceProbe([result(), result(), changed])
        service = self.service(probe)
        first = service.check("EXAMPLE.COM")
        second = service.check("example.com")
        third = service.check("example.com")
        self.assertEqual([item.change.kind for item in (first, second, third)], [
            "baseline", "unchanged", "changed",
        ])
        self.assertEqual(third.change.changed_fields, ("dmarc",))
        self.assertEqual(first.state_sha256, second.state_sha256)
        self.assertNotEqual(second.state_sha256, third.state_sha256)
        details = service.show("example.com", history_limit=2)
        self.assertEqual(details.total_check_count, 3)
        self.assertEqual([item.id for item in details.checks], [second.id, third.id])
        self.assertEqual(probe.calls, ["example.com"] * 3)

    def test_missing_records_are_complete_evidence_not_a_security_verdict(self):
        self.approve()
        saved = self.service(SequenceProbe([result(mx=(), spf=(), dmarc=())])).check(
            "example.com"
        )
        self.assertEqual(
            (saved.result.mx_status, saved.result.spf_status, saved.result.dmarc_status),
            ("missing", "missing", "missing"),
        )
        rendered = "\n".join(check_lines(saved) + detail_lines(self.service().show("example.com")))
        self.assertIn("Kayıt bulunmadı", rendered)
        self.assertIn("güvenlik, teslimat veya alan adı sahipliği kararı değildir", rendered)
        self.assertIn("DKIM seçicileri tahmin edilmez", rendered)

    def test_unapproved_unknown_or_revoked_root_never_calls_probe(self):
        probe = SequenceProbe([result()])
        service = self.service(probe)
        with self.assertRaisesRegex(ValidationError, "kapsamına alınmamış"):
            service.check("example.com")
        with self.assertRaisesRegex(ValidationError, "kayıtlı değil"):
            service.check("unknown.example")
        self.approve()
        self.surface.revoke("example.com", "Yetki geri çekildi")
        with self.assertRaisesRegex(ValidationError, "etkin değil"):
            service.check("example.com")
        self.assertEqual(probe.calls, [])

    def test_revocation_during_probe_prevents_commit(self):
        self.approve()

        class RevokingProbe:
            def check(inner_self, domain):
                self.surface.revoke(domain, "Kontrol sırasında kapsam kaldırıldı")
                return result()

        with self.assertRaisesRegex(ValidationError, "kaldırılmış"):
            self.service(RevokingProbe()).check("example.com")
        self.assertEqual(self.service().show("example.com").total_check_count, 0)

    def test_corrupt_result_or_hash_fails_closed_without_rewrite(self):
        self.approve()
        self.service(SequenceProbe([result()])).check("example.com")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE surface_mail_checks SET state_sha256 = ?", ("0" * 64,),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "geçmişi bozuk"):
            self.service().show("example.com")
        self.assertEqual(self.path.read_bytes(), before)

    def test_backup_restore_preserves_checks_and_change_evidence(self):
        self.approve()
        self.service(SequenceProbe([result()])).check("example.com")
        self.service(SequenceProbe([result(spf=())])).check("example.com")
        before = self.service().show("example.com")
        backup = self.storage.backup(Path(self.temp.name) / "backups" / "mail.db")
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        after = SurfaceMailService(
            SQLiteAssetRepository(restored), SQLiteSurfaceRepository(restored),
            SQLiteSurfaceMailRepository(restored),
        ).show("example.com")
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
