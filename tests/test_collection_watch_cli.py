"""Offline CLI acceptance for explicitly selected social and claim watches."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.ransomlook_ransomware import parse_ransomlook_ransomware_response
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_brand_username_reviews import SQLiteBrandUsernameReviewRepository
from xti.adapters.sqlite_brand_username_watches import SQLiteBrandUsernameWatchRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.brand_username_reviews import BrandUsernameReviewService
from xti.application.brand_username_watches import BrandUsernameWatchService
from xti.application.ransomlook_watches import RansomLookWatchService
from xti.application.ransomware_watches import RansomwareWatchService
from xti.interfaces.cli import main
from xti.interfaces.collection import result_lines
from xti.ports.discovery import SourceError
from xti.ports.jobs import WorkerBusyError
from tests.test_brand_username_watches import FakeSherlockSource, FakeSource as UsernameSource, github, reddit
from tests.test_discovery import FakeSource as DomainSource, batch
from tests.test_ransomlook_ransomware import content as ransomlook_content, post
from tests.test_threatcluster_ransomware import claim, content as threatcluster_content


EVENT_TIME = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat()


class ClaimSource:
    def __init__(self, value):
        self.value = value
        self.calls = 0
        self.before_fetch = lambda: None

    def fetch(self):
        self.before_fetch()
        self.calls += 1
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


def threatcluster_feed(records):
    now = datetime.now(timezone.utc)
    records = [{**record, "discovered": EVENT_TIME} for record in records]
    return parse_threatcluster_ransomware_response(
        threatcluster_content(records, generated_at=(now - timedelta(minutes=30)).isoformat()),
        fetched_at=now,
    )


def ransomlook_feed(records):
    records = [{**record, "discovered": EVENT_TIME} for record in records]
    return parse_ransomlook_ransomware_response(
        ransomlook_content(records), fetched_at=datetime.now(timezone.utc),
    )


class CollectionWatchCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name) / "collection watches"
        self.database = self.data / "xti.db"
        assets = SQLiteAssetRepository(self.database)
        assets.initialize()
        assets.add("example.com")
        self.crt = DomainSource({
            "%example%": batch(), "example%": batch(), "%.example.com": batch(),
        })
        self.urlscan = DomainSource({"example*": batch()})
        self.maigret = UsernameSource()
        self.sherlock = FakeSherlockSource()
        self.threatcluster = ClaimSource(threatcluster_feed([claim()]))
        self.ransomlook = ClaimSource(ransomlook_feed([post()]))
        for name, value in (
            ("CrtShSource", self.crt), ("UrlscanSource", self.urlscan),
            ("MaigretUsernameSource", self.maigret),
            ("SherlockUsernameSource", self.sherlock),
            ("ThreatClusterRansomwareSource", self.threatcluster),
            ("RansomLookRansomwareSource", self.ransomlook),
        ):
            self.enterContext(patch(f"xti.interfaces.cli.{name}", return_value=value))
        self.enterContext(patch(
            "socket.socket.connect", side_effect=AssertionError("Acceptance must remain offline."),
        ))
        self.enterContext(patch(
            "xti.interfaces.cli.HttpsTargetProbe",
            side_effect=AssertionError("Collection must not probe target sites."),
        ))
        self.social = BrandUsernameWatchService(
            SQLiteBrandUsernameWatchRepository(self.database),
            {"maigret": self.maigret, "sherlock": self.sherlock},
        )
        self.tc_claims = SQLiteRansomwareClaimRepository(self.database)
        self.tc = RansomwareWatchService(SQLiteRansomwareWatchRepository(self.database), self.tc_claims)
        self.rl_claims = SQLiteRansomLookClaimRepository(self.database)
        self.rl = RansomLookWatchService(SQLiteRansomLookWatchRepository(self.database), self.rl_claims)

    def invoke(self, *arguments, as_json=True):
        stdout, stderr = StringIO(), StringIO()
        options = ["--data-dir", str(self.data)]
        if as_json:
            options.append("--json")
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*options, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def result(self, *arguments, expected_code=0):
        code, stdout, stderr = self.invoke(*arguments)
        self.assertEqual((code, stderr), (expected_code, ""), stdout)
        payload = json.loads(stdout)
        self.assertEqual(payload["ok"], expected_code == 0)
        return payload["data"]

    def files(self):
        return {str(path.relative_to(self.data)): path.read_bytes()
                for path in self.data.rglob("*") if path.is_file()}

    def add_social(self, name="Marka hesabı", *, source="maigret"):
        return self.social.add(
            name, "samplebrand", source_key=source,
            platforms=("GitHub", "Reddit") if source == "maigret" else ("Carrd",),
        ).watch

    def add_tc(self, name="ThreatCluster kuruluşu", query="Example Holding", *, match="exact"):
        return self.tc.add(name, query, kind="organization", match_mode=match).watch

    def add_rl(self, name="RansomLook kuruluşu", query="Example Holding", *, match="exact"):
        return self.rl.add(name, query, kind="organization", match_mode=match).watch

    @staticmethod
    def step(result, identifier):
        return next(step for step in result["steps"] if step["task"]["id"] == identifier)

    def test_default_does_not_implicitly_run_existing_watches(self):
        social = self.add_social()
        tc = self.add_tc()
        rl = self.add_rl()
        result = self.result("collect", "example.com")
        self.assertEqual([step["task"]["id"] for step in result["steps"]],
                         ["scan-crtsh", "scan-urlscan", "discover-crtsh"])
        self.assertEqual(self.maigret.calls, [])
        self.assertEqual((self.threatcluster.calls, self.ransomlook.calls), (0, 0))
        self.assertEqual(self.social.show(social.id).total_run_count, 0)
        self.assertEqual(self.tc.show(tc.id).total_run_count, 0)
        self.assertEqual(self.rl.show(rl.id).total_run_count, 0)

    def test_plan_shows_explicit_targets_without_network_lock_or_writes(self):
        social = self.add_social(source="sherlock")
        tc = self.add_tc()
        rl = self.add_rl()
        arguments = ("collect", "example.com", "--plan", "--username-watch", social.id,
                     "--ransomware-watch", tc.id, "--ransomlook-watch", rl.id)
        before = self.files()
        with patch("xti.adapters.worker_lock.LocalExecutionLock.acquire",
                   side_effect=AssertionError("Planning must not take the writing lock.")):
            plan = self.result(*arguments)
            code, output, _ = self.invoke(*arguments, as_json=False)
        self.assertEqual(code, 0)
        self.assertEqual(self.files(), before)
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.urlscan.calls, [])
        self.assertEqual(self.sherlock.calls, [])
        self.assertEqual((self.threatcluster.calls, self.ransomlook.calls), (0, 0))
        self.assertEqual(len(plan["tasks"]), 6)
        social_task = next(task for task in plan["tasks"] if task["kind"] == "username_watch")
        self.assertEqual(social_task["source"], "sherlock")
        self.assertEqual(social_task["watches"][0]["query"], "samplebrand")
        self.assertEqual(social_task["watches"][0]["platforms"], ["Carrd"])
        for value in (social.id, "samplebrand", "Carrd", "Example Holding", tc.id, rl.id):
            self.assertIn(value, output)

    def test_selected_sources_refresh_once_and_only_selected_watches_run(self):
        social = self.add_social()
        sherlock = self.add_social("İkinci kaynak", source="sherlock")
        tc = self.add_tc()
        tc_second = self.add_tc("İkinci TC izlemesi", "Example", match="contains")
        tc_unselected = self.add_tc("Seçilmeyen TC")
        rl = self.add_rl()
        rl_unselected = self.add_rl("Seçilmeyen RL")
        self.maigret.responses.append({"GitHub": github()})
        self.sherlock.responses.append({"Carrd": "https://samplebrand.carrd.co/"})
        checked_locks = []

        def check_owned_lock():
            with self.assertRaises(WorkerBusyError):
                with LocalExecutionLock(self.database).acquire():
                    self.fail("The collection lock must cover each source request.")
            checked_locks.append(True)

        self.threatcluster.before_fetch = check_owned_lock
        self.ransomlook.before_fetch = check_owned_lock
        result = self.result(
            "collect", "example.com", "--task", "discover-crtsh",
            "--username-watch", sherlock.id, "--username-watch", social.id,
            "--ransomware-watch", tc_second.id, "--ransomware-watch", tc.id,
            "--ransomlook-watch", rl.id,
        )
        self.assertEqual((self.threatcluster.calls, self.ransomlook.calls), (1, 1))
        self.assertEqual(len(checked_locks), 2)
        self.assertEqual(len(self.maigret.calls), 1)
        self.assertEqual(len(self.sherlock.calls), 1)
        self.assertEqual(len(result["steps"]), 5)
        self.assertEqual(self.tc.show(tc_unselected.id).total_run_count, 0)
        self.assertEqual(self.rl.show(rl_unselected.id).total_run_count, 0)
        username = self.step(result, f"username-watch:{social.id}")["username"]
        self.assertTrue(username["is_baseline"])
        self.assertEqual(username["attention_count"], 0)
        self.assertEqual(username["run"]["source_name"], "Maigret")
        self.assertIn(github(), [item["profile_url"] for item in username["items"]])
        for identifier, selected in (
            ("ransomware-threatcluster", {tc.id, tc_second.id}),
            ("ransomware-ransomlook", {rl.id}),
        ):
            group = self.step(result, identifier)["ransomware"]
            self.assertEqual(group["skipped_watch_ids"], [])
            self.assertEqual({report["watch"]["id"] for report in group["watches"]}, selected)
            self.assertEqual({report["run"]["source_run_id"] for report in group["watches"]},
                             {group["refresh"]["run"]["id"]})
            self.assertTrue(all(report["is_baseline"] for report in group["watches"]))
        self.assertEqual(result["analysis"]["asset_value"], "example.com")
        self.assertEqual(result["analysis"]["findings"]["total"], 0)

    def test_repeat_preserves_human_decision_and_reports_changes_per_source(self):
        social = self.add_social()
        tc = self.add_tc(query="Example", match="contains")
        rl = self.add_rl(query="Example", match="contains")
        self.maigret.responses.extend([
            {"GitHub": github()}, {"GitHub": github(), "Reddit": reddit()},
        ])
        arguments = ("collect", "example.com", "--task", "discover-crtsh",
                     "--username-watch", social.id, "--ransomware-watch", tc.id,
                     "--ransomlook-watch", rl.id)
        first = self.result(*arguments)
        reviews = BrandUsernameReviewService(SQLiteBrandUsernameReviewRepository(self.database))
        decision = reviews.decide(social.id, "GitHub", decision="known_official",
                                  reason="Kuruluşun resmi sitesinde bu profil bağlantısı bulunuyor.")
        before = reviews.show(decision.details.candidate.id)
        self.threatcluster.value = threatcluster_feed([
            claim(sector="Finance"), claim("Example Labs", group="second"),
        ])
        self.ransomlook.value = ransomlook_feed([post(), post("Example Labs", group="second")])
        repeated = self.result(*arguments)
        username = self.step(repeated, f"username-watch:{social.id}")["username"]
        self.assertFalse(username["is_baseline"])
        self.assertEqual(username["run"]["newly_found_count"], 1)
        self.assertEqual(username["run"]["previous_complete_run_id"],
                         self.step(first, f"username-watch:{social.id}")["username"]["run"]["id"])
        self.assertEqual(reviews.show(decision.details.candidate.id), before)
        tc_report = self.step(repeated, "ransomware-threatcluster")["ransomware"]["watches"][0]
        self.assertEqual((tc_report["run"]["added_count"], tc_report["run"]["updated_count"]), (1, 1))
        self.assertFalse(tc_report["is_baseline"])
        rl_report = self.step(repeated, "ransomware-ransomlook")["ransomware"]["watches"][0]
        self.assertEqual((rl_report["run"]["added_count"], rl_report["attention_count"]), (1, 1))
        self.assertFalse(rl_report["is_baseline"])

    def test_failed_refresh_skips_old_snapshot_and_other_sources_continue(self):
        social = self.add_social()
        tc = self.add_tc()
        rl = self.add_rl()
        self.maigret.responses.extend([{"GitHub": github()}, SourceError("Sosyal kaynak kesildi.")])
        arguments = ("collect", "example.com", "--task", "discover-crtsh",
                     "--username-watch", social.id, "--ransomware-watch", tc.id,
                     "--ransomlook-watch", rl.id)
        first = self.result(*arguments)
        baseline_snapshot = self.tc_claims.latest_snapshot()
        self.threatcluster.value = SourceError("İddia kaynağı kesildi.")
        failed = self.result(*arguments, expected_code=3)
        self.assertEqual(failed["status"], "partial")
        tc_step = self.step(failed, "ransomware-threatcluster")
        self.assertEqual(tc_step["status"], "failed")
        self.assertEqual(tc_step["ransomware"]["watches"], [])
        self.assertEqual(tc_step["ransomware"]["skipped_watch_ids"], [tc.id])
        self.assertEqual(self.tc.show(tc.id).total_run_count, 1)
        self.assertEqual(self.tc_claims.latest_snapshot(), baseline_snapshot)
        self.assertEqual(self.rl.show(rl.id).total_run_count, 2)
        self.assertEqual(self.step(failed, "ransomware-ransomlook")["status"], "complete")
        social_failed = self.step(failed, f"username-watch:{social.id}")["username"]
        self.assertEqual(social_failed["run"]["status"], "failed")
        self.assertEqual(self.social.show(social.id).total_run_count, 2)
        baseline = self.step(first, f"username-watch:{social.id}")["username"]["run"]["id"]
        self.assertEqual(self.social.show_run(baseline).run.found_count, 1)

    def test_invalid_or_revoked_selection_is_rejected_before_any_mutation(self):
        social = self.add_social()
        tc = self.add_tc()
        rl = self.add_rl()
        self.rl.revoke(rl.id, reason="Bu kuruluş artık kapsamda değil.")
        before = self.files()
        invalid = (
            ("--username-watch", str(uuid4())),
            ("--username-watch", "not-an-id"),
            ("--username-watch", social.id, "--username-watch", social.id),
            ("--ransomware-watch", tc.id, "--ransomware-watch", tc.id),
            ("--ransomlook-watch", rl.id),
            ("--username-watch", social.id, "--watch-item-limit", "0"),
            ("--username-watch", social.id, "--watch-item-limit", "501"),
            tuple(value for _ in range(51) for value in ("--username-watch", str(uuid4()))),
        )
        for flags in invalid:
            with self.subTest(flags=flags[:6]):
                code, stdout, stderr = self.invoke("collect", "example.com", *flags)
                self.assertEqual((code, stdout), (2, ""), stderr)
                self.assertEqual(self.files(), before)
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.urlscan.calls, [])
        self.assertEqual(self.maigret.calls, [])
        self.assertEqual((self.threatcluster.calls, self.ransomlook.calls), (0, 0))

    def test_limited_watch_output_preserves_total_and_human_baseline_context(self):
        social = self.add_social()
        tc = self.add_tc(query="Example", match="contains")
        self.maigret.responses.extend([{"GitHub": github()}, {"GitHub": github()}])
        self.threatcluster.value = threatcluster_feed([claim(), claim("Example Labs", group="second")])
        arguments = ("collect", "example.com", "--task", "discover-crtsh",
                     "--username-watch", social.id, "--ransomware-watch", tc.id,
                     "--watch-item-limit", "1")
        first = self.result(*arguments)
        social_report = self.step(first, f"username-watch:{social.id}")["username"]
        tc_report = self.step(first, "ransomware-threatcluster")["ransomware"]["watches"][0]
        self.assertEqual((len(social_report["items"]), social_report["total_item_count"]), (1, 2))
        self.assertEqual((len(tc_report["items"]), tc_report["total_item_count"]), (1, 2))
        # A fresh watch gives the terminal renderer a real baseline to label.
        fresh = self.add_tc("Yeni başlangıç", "Example", match="contains")
        code, output, _ = self.invoke(
            "collect", "example.com", "--task", "discover-crtsh", "--username-watch", social.id,
            "--ransomware-watch", fresh.id, "--watch-item-limit", "1", as_json=False,
        )
        self.assertEqual(code, 0)
        self.assertIn(github(), output)
        self.assertIn("başlangıç", output.lower())
        self.assertIn("watch-run-show", output)
        self.assertIn("2; 1 gösteriliyor", output)
        self.assertIn("1 kayıt görünüm sınırı dışında", output)
        self.assertTrue("Example Holding" in output or "Example Labs" in output)

    def test_human_source_errors_escape_controls_and_identify_skipped_watches(self):
        tc = self.add_tc()
        self.threatcluster.value = SourceError("Kaynak kesildi.")

        def render_untrusted_error(result):
            # Persistence rejects controls independently. Exercise the public
            # renderer's trust boundary using the actual failed CLI result.
            step = next(step for step in result.steps if step.ransomware is not None)
            refresh = replace(step.ransomware.refresh, run=replace(
                step.ransomware.refresh.run,
                error="Kaynak \x1b[31mkesildi\nsonraki satır",
            ))
            changed = replace(step, ransomware=replace(step.ransomware, refresh=refresh))
            return result_lines(replace(result, steps=tuple(
                changed if item is step else item for item in result.steps
            )))

        with patch("xti.interfaces.cli.collection_result_lines", side_effect=render_untrusted_error):
            code, output, _ = self.invoke(
                "collect", "example.com", "--task", "discover-crtsh",
                "--ransomware-watch", tc.id, as_json=False,
            )
        self.assertEqual(code, 3)
        self.assertNotIn("\x1b", output)
        self.assertIn("\\u001b", output)
        self.assertIn(tc.id, output)
        self.assertIn("çalıştırılmadı", output)
        self.assertEqual(self.tc.show(tc.id).total_run_count, 0)


if __name__ == "__main__":
    unittest.main()
