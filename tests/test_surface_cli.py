"""Terminal workflow for explicitly approved DNS/TLS surface baselines."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.worker_lock import LocalExecutionLock
from xti.domain.enrichment import ProbeResult
from xti.domain.cname import CNAME_POLICY_VERSION, CnameDnsResult, CnameHop
from xti.domain.mail import MailDnsResult
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


def checked(address="93.184.216.34", *, errors=()):
    now = datetime.now(timezone.utc).isoformat()
    return ProbeResult(
        domain="example.com", started_at=now, finished_at=now,
        policy_version="surface-cli-test-v1", dns_status="resolved", addresses=(address,),
        tls_status="valid", http_status="responded" if not errors else "failed",
        http_status_code=200 if not errors else None, connected_address=address,
        errors=errors, notes=("Yalnız kontrollü HEAD isteği.",),
    )


def mail_checked(*, dmarc=("v=DMARC1; p=reject",), spf=("v=spf1 -all",),
                 errors=()):
    now = datetime.now(timezone.utc).isoformat()
    spf_status = "failed" if any(item.startswith("SPF:") for item in errors) else (
        "present" if spf else "missing"
    )
    return MailDnsResult(
        domain="example.com", started_at=now, finished_at=now,
        policy_version="mail-cli-test-v1",
        mx_status="present", mx_records=("10 mail.example.com",),
        spf_status=spf_status, spf_records=spf,
        dmarc_status="present" if dmarc else "missing", dmarc_records=dmarc,
        errors=errors, notes=("DKIM seçicisi tahmin edilmez.",),
    )


class FakeProbe:
    def __init__(self):
        self.results = [checked(), checked(), checked("93.184.216.35")]
        self.calls = []

    def check(self, domain):
        self.calls.append(domain)
        return self.results.pop(0)


class FakeMailProbe:
    def __init__(self):
        self.results = [
            mail_checked(), mail_checked(),
            mail_checked(dmarc=("v=DMARC1; p=quarantine",)),
        ]
        self.calls = []

    def check(self, domain):
        self.calls.append(domain)
        return self.results.pop(0)


class FakeCnameProbe:
    def __init__(self):
        now = datetime.now(timezone.utc).isoformat()
        self.results = [CnameDnsResult(
            "example.com", now, now, CNAME_POLICY_VERSION,
            "present", (CnameHop("example.com", "missing.vendor.example"),),
            "missing.vendor.example", "nxdomain", (), (),
            ("Yalnız genel DNS kanıtı.",),
        )]
        self.calls = []

    def check(self, domain):
        self.calls.append(domain)
        return self.results.pop(0)


class FakePassiveSource:
    def __init__(self, provider="crt.sh"):
        self.provider = provider
        self.calls = []
        self.error = None

    def search_url(self, pattern):
        return "https://crt.sh/?q=" + pattern

    def search(self, pattern):
        self.calls.append(pattern)
        if self.error is not None:
            raise self.error
        documents = []
        for number, domain in ((1, "api.example.com"), (2, "vpn.example.com")):
            digest = hashlib.sha256(f"cert-{number}".encode()).hexdigest()
            documents.append(ImportDocument(
                f"https://crt.sh/?id={number}", digest,
                (DomainInput(domain, domain, 1, "2026-10-01T00:00:00+00:00"),),
            ))
        return SourceBatch(tuple(documents), 0, 2)


class SurfaceCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "local data"
        self.database = self.data / "xti.db"
        self.probe = FakeProbe()
        self.mail_probe = FakeMailProbe()
        self.cname_probe = FakeCnameProbe()
        self.passive_source = FakePassiveSource()
        self.harvester_source = FakePassiveSource("theharvester")
        self.ok("init")
        self.ok("assets", "add", "example.com")

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with (
            patch("xti.interfaces.cli.HttpsTargetProbe", return_value=self.probe),
            patch("xti.interfaces.cli.GoogleMailDnsProbe", return_value=self.mail_probe),
            patch("xti.interfaces.cli.GoogleCnameDnsProbe", return_value=self.cname_probe),
            patch("xti.interfaces.cli.CrtShSource", return_value=self.passive_source),
            patch(
                "xti.interfaces.cli.TheHarvesterArchiveSource",
                return_value=self.harvester_source,
            ),
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def ok(self, *arguments):
        code, stdout, stderr = self.invoke(*arguments)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        return payload["data"]

    def error(self, *arguments, code=2):
        actual, stdout, stderr = self.invoke(*arguments)
        self.assertEqual(actual, code, stderr)
        self.assertEqual(stdout, "")
        return json.loads(stderr)

    def test_approve_check_repeat_change_and_read_only_views(self):
        approved = self.ok(
            "surface", "approve", "example.com", "--reason", "Kendi alan adım",
        )
        self.assertTrue(approved["scope"]["active"])
        first = self.ok("surface", "check", "example.com")["check"]
        second = self.ok("surface", "check", "example.com")["check"]
        third = self.ok("surface", "check", "example.com")["check"]
        self.assertEqual(
            [first["change"]["kind"], second["change"]["kind"], third["change"]["kind"]],
            ["baseline", "unchanged", "changed"],
        )
        before = self.database.read_bytes()
        listed = self.ok("surface", "list")
        shown = self.ok("surface", "show", "example.com", "--history-limit", "2")
        self.assertEqual(listed["items"][0]["check_count"], 3)
        self.assertEqual(shown["total_check_count"], 3)
        self.assertEqual(len(shown["checks"]), 2)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.probe.calls, ["example.com"] * 3)

    def test_scope_is_required_and_revocation_blocks_network(self):
        self.error("surface", "check", "example.com")
        self.assertEqual(self.probe.calls, [])
        self.ok("surface", "approve", "example.com", "--reason", "Yetkili kapsam")
        self.ok("surface", "revoke", "example.com", "--reason", "Yetki geri çekildi")
        self.error("surface", "check", "example.com")
        all_items = self.ok("surface", "list", "--all")["items"]
        self.assertFalse(all_items[0]["scope"]["active"])
        self.assertEqual(self.ok("surface", "list")["items"], [])
        self.assertEqual(self.probe.calls, [])

    def test_mail_baseline_change_and_read_only_history(self):
        self.ok("surface", "approve", "example.com", "--reason", "Yetkili kapsam")
        first = self.ok("surface", "mail", "check", "example.com")["check"]
        second = self.ok("surface", "mail", "check", "example.com")["check"]
        third = self.ok("surface", "mail", "check", "example.com")["check"]
        self.assertEqual(
            [item["change"]["kind"] for item in (first, second, third)],
            ["baseline", "unchanged", "changed"],
        )
        self.assertEqual(third["change"]["changed_fields"], ["dmarc"])
        before = self.database.read_bytes()
        shown = self.ok(
            "surface", "mail", "show", "example.com", "--history-limit", "2",
        )
        self.assertEqual(shown["total_check_count"], 3)
        self.assertEqual(len(shown["checks"]), 2)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.mail_probe.calls, ["example.com"] * 3)
        self.assertEqual(self.probe.calls, [])

    def test_mail_scope_and_shared_worker_lock_block_network(self):
        self.error("surface", "mail", "check", "example.com")
        self.assertEqual(self.mail_probe.calls, [])
        self.ok("surface", "approve", "example.com", "--reason", "Yetkili kapsam")
        with LocalExecutionLock(self.database).acquire():
            payload = self.error(
                "surface", "mail", "check", "example.com", code=4,
            )
        self.assertEqual(payload["error"]["code"], "worker_busy")
        self.assertEqual(self.mail_probe.calls, [])
        self.assertEqual(
            self.ok("surface", "mail", "show", "example.com")["checks"], [],
        )
        self.ok("surface", "revoke", "example.com", "--reason", "Yetki geri çekildi")
        self.error("surface", "mail", "check", "example.com")
        self.assertEqual(self.mail_probe.calls, [])

    def test_cname_check_history_and_exposure_candidate_are_bounded(self):
        self.error("surface", "cname", "check", "example.com")
        self.assertEqual(self.cname_probe.calls, [])
        self.ok("surface", "approve", "example.com", "--reason", "Yetkili tam adres")
        with LocalExecutionLock(self.database).acquire():
            payload = self.error(
                "surface", "cname", "check", "example.com", code=4,
            )
        self.assertEqual(payload["error"]["code"], "worker_busy")
        self.assertEqual(self.cname_probe.calls, [])
        checked = self.ok("surface", "cname", "check", "example.com")
        self.assertEqual(checked["status"], "complete")
        self.assertEqual(checked["check"]["result"]["target_status"], "nxdomain")
        before = self.database.read_bytes()
        shown = self.ok("surface", "cname", "show", "example.com")
        self.assertEqual(shown["total_check_count"], 1)
        exposure = self.ok("surface", "exposures", "example.com")
        self.assertEqual(exposure["candidate_count"], 1)
        self.assertEqual(
            exposure["candidates"][0]["candidate_type"],
            "dangling_cname_target_nxdomain",
        )
        self.assertEqual(exposure["coverage"][4]["status"], "current")
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.cname_probe.calls, ["example.com"])

        code, stdout, stderr = self.invoke(
            "surface", "cname", "show", "example.com", as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("CNAME kanıt geçmişi: example.com", stdout)
        self.assertIn("alınabilir olduğunu kanıtlamaz", stdout)

    def test_partial_mail_query_is_saved_visible_and_nonzero(self):
        self.mail_probe.results[0] = mail_checked(
            spf=(), errors=("SPF: sorgu tamamlanamadı.",),
        )
        self.ok("surface", "approve", "example.com", "--reason", "Yetkili kapsam")
        code, stdout, stderr = self.invoke(
            "surface", "mail", "check", "example.com", as_json=False,
        )
        self.assertEqual(code, 3)
        self.assertEqual(
            stderr, "Yetkili MX/SPF/DMARC kontrolü: example.com\n",
        )
        self.assertIn("Eksik sorgu", stdout)
        shown = self.ok("surface", "mail", "show", "example.com")
        self.assertEqual(shown["total_check_count"], 1)
        self.assertEqual(shown["checks"][0]["result"]["spf_status"], "failed")

    def test_invalid_approval_never_creates_asset_or_calls_network(self):
        before = self.database.read_bytes()
        self.error(
            "surface", "approve", "not-example.com", "--reason", "Bana ait",
        )
        self.error("surface", "approve", "example.com", "--reason", "  ")
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.probe.calls, [])

    def test_busy_worker_prevents_surface_connection_and_evidence(self):
        self.ok("surface", "approve", "example.com", "--reason", "Yetkili kapsam")
        with LocalExecutionLock(self.database).acquire():
            payload = self.error("surface", "check", "example.com", code=4)
        self.assertEqual(payload["error"]["code"], "worker_busy")
        self.assertEqual(self.probe.calls, [])
        self.assertEqual(self.ok("surface", "show", "example.com")["checks"], [])

    def test_partial_result_is_saved_but_exit_is_nonzero_and_terminal_is_safe(self):
        self.probe.results[0] = checked(errors=("Uzak hata\x1b[31m",))
        self.ok("surface", "approve", "example.com", "--reason", "Yetkili kapsam")
        code, stdout, stderr = self.invoke("surface", "check", "example.com", as_json=False)
        self.assertEqual(code, 3, stderr)
        self.assertEqual(stderr, "Yetkili DNS/TLS dış yüzey kontrolü: example.com\n")
        self.assertNotIn("\x1b", stdout + stderr)
        self.assertIn("Eksik kontrol", stdout)
        details = self.ok("surface", "show", "example.com")
        self.assertEqual(details["total_check_count"], 1)

    def test_passive_discovery_review_and_decision_never_start_active_probe(self):
        discovered = self.ok("surface", "discover", "example.com")
        self.assertEqual(discovered["status"], "complete")
        self.assertEqual(discovered["candidates_created"], 2)
        self.assertEqual(self.passive_source.calls, ["%.example.com"])
        self.assertEqual(self.probe.calls, [])
        self.assertIsNotNone(discovered["run_id"])
        runs = self.ok("surface", "runs", "example.com")["runs"]
        self.assertEqual([item["id"] for item in runs], [discovered["run_id"]])
        self.assertEqual(self.ok("surface", "run", discovered["run_id"])["status"], "complete")
        notices = self.ok("inbox", "list", "--status", "all")
        self.assertEqual(notices["total_count"], 2)
        self.assertTrue(all(item["candidate"] is not None for item in notices["items"]))

        before = self.database.read_bytes()
        listed = self.ok("surface", "candidates", "example.com")
        self.assertEqual([item["domain"] for item in listed["items"]], [
            "api.example.com", "vpn.example.com",
        ])
        candidate_id = listed["items"][0]["id"]
        shown = self.ok("surface", "candidate", "show", candidate_id)
        self.assertEqual(shown["candidate"]["domain"], "api.example.com")
        self.assertEqual(len(shown["sources"]), 1)
        self.assertEqual(self.database.read_bytes(), before)

        decision = self.ok(
            "surface", "candidate", "decide", candidate_id,
            "--status", "owned", "--reason", "Kurumsal API adresim",
        )
        self.assertTrue(decision["changed"])
        self.assertEqual(decision["candidate"]["status"], "owned")
        self.assertEqual(self.ok("surface", "candidates", "example.com")["items"], [
            listed["items"][1],
        ])
        self.assertEqual(
            [item["value"] for item in self.ok("assets", "list")["assets"]], ["example.com"],
        )
        self.assertEqual(self.ok("surface", "list")["items"], [])
        self.assertEqual(self.probe.calls, [])

    def test_overview_combines_stored_surface_evidence_without_network_or_writes(self):
        self.ok("surface", "discover", "example.com")
        self.ok("surface", "approve", "example.com", "--reason", "Yetkili kapsam")
        self.ok("surface", "check", "example.com")
        self.ok("surface", "mail", "check", "example.com")
        self.passive_source.calls.clear()
        before = self.database.read_bytes()
        overview = self.ok(
            "surface", "overview", "example.com", "--candidate-limit", "1",
        )
        self.assertTrue(overview["scope"]["active"])
        self.assertEqual(overview["candidate_counts"]["total"], 2)
        self.assertEqual(len(overview["candidates"]), 1)
        self.assertEqual(
            {item["kind"] for item in overview["relations"]},
            {"discovered_subdomain", "resolves_to", "uses_mail_exchange"},
        )
        code, stdout, stderr = self.invoke(
            "surface", "overview", "example.com", "--candidate-limit", "1",
            as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Dış yüzey genel görünümü: example.com", stdout)
        self.assertIn("Kanıtlı ilişkiler (3):", stdout)
        self.assertIn("Bu görünüm yalnız kayıtlı kanıtı birleştirir", stdout)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.passive_source.calls, [])
        self.assertEqual(self.probe.calls, ["example.com"])
        self.assertEqual(self.mail_probe.calls, ["example.com"])

    def test_freshness_combines_evidence_age_without_network_or_writes(self):
        self.ok("surface", "approve", "example.com", "--reason", "Yetkili kapsam")
        self.ok("surface", "check", "example.com")
        self.ok("surface", "mail", "check", "example.com")
        before = self.database.read_bytes()
        report = self.ok(
            "surface", "freshness", "example.com", "--stale-after-hours", "24",
        )
        self.assertEqual(report["scope_status"], "active")
        self.assertEqual(
            (report["current_count"], report["stale_count"], report["never_count"]),
            (2, 0, 1),
        )
        self.assertEqual(
            [item["check_type"] for item in report["items"]],
            ["web", "mail", "services"],
        )
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.probe.calls, ["example.com"])
        self.assertEqual(self.mail_probe.calls, ["example.com"])

        code, stdout, stderr = self.invoke(
            "surface", "freshness", "example.com", as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Dış yüzey kanıt güncelliği: example.com", stdout)
        self.assertIn("Sınırlı TCP servisleri: Henüz kontrol edilmedi", stdout)
        self.assertIn("internete bağlanmaz", stdout)
        self.assertEqual(self.database.read_bytes(), before)

    def test_exposures_explain_candidates_and_unsupported_coverage_read_only(self):
        self.mail_probe.results[0] = mail_checked(dmarc=())
        self.ok("surface", "approve", "example.com", "--reason", "Yetkili kapsam")
        self.ok("surface", "check", "example.com")
        self.ok("surface", "mail", "check", "example.com")
        before = self.database.read_bytes()

        report = self.ok(
            "surface", "exposures", "example.com", "--stale-after-hours", "24",
        )
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["candidates"][0]["candidate_type"], "mail_dmarc_missing")
        self.assertEqual(
            [item["status"] for item in report["coverage"]],
            [
                "not_checked", "current", "current", "not_checked",
                "not_checked", "unsupported",
            ],
        )
        self.assertEqual(
            (report["current_coverage_count"], report["attention_coverage_count"]),
            (2, 3),
        )
        self.assertEqual(
            report["coverage"][0]["next_command"],
            "./xti surface discover example.com",
        )
        code, stdout, stderr = self.invoke(
            "surface", "exposures", "example.com", as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Dış yüzey maruziyet adayları: example.com", stdout)
        self.assertIn("DMARC kaydı eksikliği adayı", stdout)
        self.assertIn("Pasif alt alan adı keşfi: Kontrol edilmedi", stdout)
        self.assertIn("./xti surface discover example.com", stdout)
        self.assertIn("Henüz desteklenmiyor", stdout)
        self.assertIn("doğrulanmış zafiyet", stdout)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.probe.calls, ["example.com"])
        self.assertEqual(self.mail_probe.calls, ["example.com"])

    def test_inventory_keeps_candidate_registration_and_scope_layers_separate(self):
        self.ok("surface", "discover", "example.com")
        candidates = self.ok(
            "surface", "candidates", "example.com", "--status", "all",
        )["items"]
        api = next(item for item in candidates if item["domain"] == "api.example.com")
        self.ok(
            "surface", "candidate", "decide", api["id"],
            "--status", "owned", "--reason", "Kurumsal API adresim",
        )
        self.ok("assets", "add", "api.example.com")
        self.ok(
            "surface", "approve", "api.example.com", "--reason", "Yetkili adresim",
        )
        self.passive_source.calls.clear()
        before = self.database.read_bytes()

        report = self.ok("surface", "inventory", "example.com")
        items = {item["domain"]: item for item in report["items"]}
        self.assertEqual(report["candidate_counts"]["total"], 2)
        self.assertEqual((report["registered_count"], report["active_scope_count"]), (1, 1))
        self.assertEqual(
            (
                items["api.example.com"]["candidate_status"],
                items["api.example.com"]["registration_status"],
                items["api.example.com"]["scope_status"],
            ),
            ("owned", "registered", "active"),
        )
        self.assertEqual(
            (
                items["vpn.example.com"]["candidate_status"],
                items["vpn.example.com"]["registration_status"],
                items["vpn.example.com"]["scope_status"],
            ),
            ("pending", "unregistered", "not_applicable"),
        )

        code, stdout, stderr = self.invoke(
            "surface", "inventory", "example.com", "--status", "owned",
            as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Dış yüzey varlık sınıflandırması: example.com", stdout)
        self.assertIn("api.example.com | Bana ait", stdout)
        self.assertIn("Kayıtlı varlık | Aktif kontrol kapsamı", stdout)
        self.assertIn("otomatik varlık kaydı veya bağlantı yetkisi oluşturmaz", stdout)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.passive_source.calls, [])
        self.assertEqual(self.probe.calls, [])
        self.assertEqual(self.mail_probe.calls, [])

    def test_passive_source_failure_is_visible_and_does_not_create_candidate(self):
        self.passive_source.error = SourceError("Kaynak geçici olarak yanıt vermedi.")
        code, stdout, stderr = self.invoke("surface", "discover", "example.com")
        self.assertEqual((code, stderr), (3, ""))
        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["data"]["status"], "failed")
        self.assertEqual(payload["data"]["error"], "Kaynak geçici olarak yanıt vermedi.")
        run = self.ok("surface", "run", payload["data"]["run_id"])
        self.assertEqual(run["status"], "failed")
        self.assertEqual(self.ok("surface", "candidates", "example.com", "--status", "all")["items"], [])
        self.assertEqual(self.ok("inbox", "list", "--status", "all")["total_count"], 0)
        self.assertEqual(self.probe.calls, [])

        self.passive_source.calls.clear()
        before = self.database.read_bytes()
        status = self.ok("surface", "discovery-status", "example.com")
        self.assertEqual(
            (status["source_status"], status["result_status"], status["outcome"]),
            ("unavailable", "unknown", "failed"),
        )
        self.assertFalse(status["empty_result_confirmed"])
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.passive_source.calls, [])

    def test_discovery_status_distinguishes_no_run_from_completed_result_read_only(self):
        before = self.database.read_bytes()
        never = self.ok("surface", "discovery-status", "example.com")
        self.assertEqual(
            (never["source_status"], never["result_status"], never["outcome"]),
            ("never", "unknown", "never"),
        )
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.passive_source.calls, [])

        self.ok("surface", "discover", "example.com")
        self.passive_source.calls.clear()
        before = self.database.read_bytes()
        report = self.ok(
            "surface", "discovery-status", "example.com", "--stale-after-hours", "24",
        )
        self.assertEqual(
            (report["source_status"], report["result_status"], report["outcome"]),
            ("available", "candidates_observed", "complete_found"),
        )
        self.assertTrue(report["coverage_complete"])

        code, stdout, stderr = self.invoke(
            "surface", "discovery-status", "example.com", as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Pasif keşif kaynak durumu: example.com", stdout)
        self.assertIn("Kaynak: Kaynak çalıştı", stdout)
        self.assertIn("Veri sonucu: Aday bulundu", stdout)
        self.assertIn("Kısmi ya da başarısız çalışma boş sonuç sayılmaz", stdout)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.passive_source.calls, [])

    def test_unknown_passive_root_is_rejected_before_source_or_probe(self):
        self.error("surface", "discover", "unknown.example")
        self.assertEqual(self.passive_source.calls, [])
        self.assertEqual(self.probe.calls, [])

    def test_one_cycle_passive_watch_records_history_without_active_probe(self):
        watched = self.ok(
            "surface", "watch", "example.com", "--cycles", "1",
            "--interval", "300", "--duration", "60",
        )
        self.assertEqual((watched["completed_cycles"], watched["complete"]), (1, 1))
        self.assertEqual(watched["stop_reason"], "cycles")
        self.assertEqual(self.passive_source.calls, ["%.example.com"])
        self.assertEqual(len(self.ok("surface", "runs", "example.com")["runs"]), 1)
        self.assertEqual(self.ok("inbox", "list", "--status", "all")["total_count"], 2)
        self.assertEqual(self.probe.calls, [])

    def test_theharvester_source_uses_same_candidate_and_history_workflow(self):
        discovered = self.ok(
            "surface", "discover", "example.com", "--source", "theharvester",
        )
        self.assertEqual((discovered["status"], discovered["provider"]), (
            "complete", "theharvester",
        ))
        self.assertEqual(self.harvester_source.calls, ["%.example.com"])
        self.assertEqual(self.passive_source.calls, [])
        run = self.ok("surface", "run", discovered["run_id"])
        self.assertEqual(run["provider"], "theharvester")
        candidates = self.ok(
            "surface", "candidates", "example.com", "--status", "all",
        )["items"]
        self.assertEqual(len(candidates), 2)
        self.assertEqual(self.probe.calls, [])

    def test_invalid_watch_limits_and_unknown_root_do_not_access_source(self):
        self.error(
            "surface", "watch", "example.com", "--cycles", "0",
            "--interval", "300", "--duration", "60",
        )
        self.error(
            "surface", "watch", "unknown.example", "--cycles", "1",
            "--interval", "300", "--duration", "60",
        )
        self.assertEqual(self.passive_source.calls, [])
        self.assertEqual(self.probe.calls, [])


if __name__ == "__main__":
    unittest.main()
