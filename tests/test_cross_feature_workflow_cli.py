"""One offline user workflow across collection, evidence, grouping and reports."""

import unittest
from unittest.mock import patch

from xti.ports.discovery import SourceError
from tests import test_collection_watch_cli as fixtures
from tests.test_attack_catalog import parsed as attack_snapshot
from tests.test_discovery import batch, document
from tests.test_multi_source import FakeUrlscanSource, scoped_batch, urlscan_document


class CrossFeatureWorkflowCLITests(unittest.TestCase):
    invoke = fixtures.CollectionWatchCLITests.invoke
    result = fixtures.CollectionWatchCLITests.result
    files = fixtures.CollectionWatchCLITests.files
    add_rl = fixtures.CollectionWatchCLITests.add_rl

    def setUp(self):
        fixtures.CollectionWatchCLITests.setUp(self)
        self.crt.responses["%example%"] = batch(
            document("example-support.net", 1),
            document("example-login.net", 2),
        )
        self.crt.responses["%.example.com"] = batch(
            document("portal.example.com", 3),
        )
        self.urlscan = FakeUrlscanSource({
            "example*": scoped_batch(
                urlscan_document("example-support.net", "shared-result"),
                urlscan_document("example-help.net", "urlscan-result"),
            ),
        })
        self.enterContext(patch("xti.interfaces.cli.UrlscanSource", return_value=self.urlscan))
        self.attack = fixtures.ClaimSource(attack_snapshot())
        self.enterContext(patch("xti.interfaces.cli.MitreAttackSource", return_value=self.attack))
        for target in ("socket.create_connection", "socket.socket.connect_ex", "socket.getaddrinfo"):
            self.enterContext(patch(target, side_effect=AssertionError("Workflow must remain offline.")))

    def source_calls(self):
        return (
            tuple(self.crt.calls), tuple(self.urlscan.calls), self.ransomlook.calls,
            self.threatcluster.calls, tuple(self.maigret.calls), self.attack.calls,
        )

    @staticmethod
    def receipt(history, kind, *, source=None):
        matches = [item for item in history["receipts"] if item["result_kind"] == kind]
        if source is not None:
            steps = {item["id"]: item for item in history["steps"]}
            matches = [item for item in matches if steps[item["step_id"]]["source"] == source]
        assert len(matches) == 1, matches
        return matches[0]

    @staticmethod
    def domains(page):
        return {item["domain"] for item in page["items"]}

    def test_named_collection_change_failure_resume_and_local_evidence_views(self):
        watch = self.add_rl()
        organization = self.result("organizations", "add", "Örnek kuruluş")["organization"]
        for kind, value in (("domain", "example.com"), ("ransomlook-watch", watch.id)):
            self.result(
                "organizations", "link", organization["id"],
                "--kind", kind, "--value", value,
            )
        profile = self.result(
            "profiles", "save", "gunluk", "example.com", "--ransomlook-watch", watch.id,
        )["profile"]
        self.assertEqual(profile["revision"], 1)
        first = self.result("collect", "--profile", "gunluk")
        baseline = self.result("collections", "show", first["session_id"])
        self.assertEqual(baseline["session"]["status"], "complete")
        self.assertEqual(baseline["session"]["plan"]["origin"]["profile_id"], profile["id"])
        baseline_claim = self.receipt(baseline, "ransomlook_watch_run")
        before_notices = self.result("inbox", "list", "--status", "all")
        self.assertFalse(any(
            item["notification"]["ransomlook_run_id"] is not None
            for item in before_notices["items"]
        ))

        finding = next(
            item for item in self.result("findings", "list")["findings"]
            if item["domain"] == "example-support.net"
        )
        self.result(
            "findings", "review", finding["id"], "--decision", "dismissed",
            "--reason", "İnsan incelemesinde izleme kapsamı dışında bulundu.",
        )
        reviewed = self.result("findings", "show", finding["id"])

        # An independent archive fails while the selected claim watch completes.
        # Its receipt and single new notice must survive retrying the failed archive.
        working_urlscan = self.urlscan.responses["example*"]
        self.urlscan.responses["example*"] = SourceError("Kontrollü arşiv erişim hatası.")
        self.ransomlook.value = fixtures.ransomlook_feed([
            fixtures.post(), fixtures.post(group="second-group"),
        ])
        second = self.result("collect", "--profile", "gunluk", expected_code=3)
        partial = self.result("collections", "show", second["session_id"])
        self.assertEqual(partial["session"]["status"], "partial")
        changed_claim = self.receipt(partial, "ransomlook_watch_run")
        failed_scan = self.receipt(partial, "scan_attempt", source="urlscan")
        self.assertEqual(failed_scan["result_status"], "failed")
        self.assertNotEqual(changed_claim["source_run_id"], baseline_claim["source_run_id"])
        notices = self.result("inbox", "list", "--status", "all")
        self.assertEqual(notices["total_count"], before_notices["total_count"] + 1)
        claim_notices = [
            item for item in notices["items"]
            if item["notification"]["ransomlook_run_id"] is not None
        ]
        self.assertEqual(len(claim_notices), 1)
        notice = claim_notices[0]["notification"]
        detail = self.result("inbox", "show", notice["id"])
        self.assertEqual(notice["ransomlook_run_id"], changed_claim["result_id"])
        self.assertEqual(detail["ransomlook_change"]["source_run_id"], changed_claim["source_run_id"])
        self.assertEqual(detail["ransomlook_change"]["added_count"], 1)
        self.result("inbox", "read", notice["id"])
        read_notice = self.result("inbox", "show", notice["id"])["notification"]

        readonly_before = self.files()
        calls_before = self.source_calls()
        plan = self.result("collections", "resume", second["session_id"], "--plan")
        self.assertEqual([unit["step_key"] for unit in plan["units"]], ["scan-urlscan"])
        self.assertEqual(
            {item["unit"]["kind"] for item in plan["retained"]},
            {"scan", "discovery", "ransomware_watch"},
        )
        self.assertEqual(self.files(), readonly_before)
        self.assertEqual(self.source_calls(), calls_before)
        self.urlscan.responses["example*"] = working_urlscan
        resumed = self.result("collections", "resume", second["session_id"])
        history = resumed["history"]
        self.assertEqual(history["session"]["status"], "complete")
        self.assertEqual(history["session"]["parent_id"], second["session_id"])
        self.assertEqual([step["step_key"] for step in history["steps"]], ["scan-urlscan"])
        retained_claim = next(
            item for item in history["retained"]
            if item["receipt"]["result_kind"] == "ransomlook_watch_run"
        )
        self.assertEqual(retained_claim["receipt"], changed_claim)
        self.assertEqual(tuple(self.crt.calls), calls_before[0])
        self.assertEqual(self.ransomlook.calls, calls_before[2])
        self.assertEqual(len(self.urlscan.calls), len(calls_before[1]) + 1)
        self.assertEqual(self.result("collections", "show", second["session_id"]), partial)
        self.assertEqual(self.result("findings", "show", finding["id"]), reviewed)
        self.assertEqual(self.result("inbox", "show", notice["id"])["notification"], read_notice)
        self.assertEqual(self.result("inbox", "list", "--status", "all")["total_count"], notices["total_count"])

        attack = self.result("cti", "attack-sync")
        self.assertEqual(attack["catalog"]["run"]["entity_count"], 7)
        self.assertEqual(self.attack.calls, 1)
        readonly_before = self.files()
        calls_before = self.source_calls()
        self.check_period_reports(baseline_claim, changed_claim, failed_scan, watch.id)
        self.check_source_contribution(baseline, history)
        self.check_group_scope(organization["id"], watch.id)
        attack_page = self.result("cti", "attack-search", "DNS")
        self.assertEqual(
            {item["entity"]["external_id"] for item in attack_page["items"]},
            {"T1001", "T1059.001"},
        )
        attack_detail = self.result("cti", "attack-show", "T1059.001")
        self.assertEqual(attack_detail["item"]["entity"]["external_id"], "T1059.001")
        self.assertEqual(attack_detail["phases"][0]["tactic"]["external_id"], "TA0002")
        self.assertEqual(attack_detail["phases"][0]["link"]["field"], "kill_chain_phases")
        self.assertIsNone(attack_detail["cti_entity_id"])
        self.assertIsNotNone(self.result("cti", "attack-show", "G0001")["cti_entity_id"])
        self.assertEqual(self.files(), readonly_before)
        self.assertEqual(self.source_calls(), calls_before)

    def check_period_reports(self, baseline, changed, failed, watch_id):
        for days in ("1", "7"):
            report = self.result("changes", "--days", days)
            section = next(item for item in report["sections"] if item["family"] == "ransomlook")
            self.assertEqual(section["total_baseline_count"], 1)
            self.assertEqual(section["total_change_count"], 1)
            self.assertEqual(section["baselines"][0]["run_id"], baseline["result_id"])
            change = section["changes"][0]
            self.assertEqual(change["run_id"], changed["result_id"])
            self.assertEqual(change["source_run_id"], changed["source_run_id"])
            self.assertEqual(change["previous_run_id"], baseline["result_id"])
            self.assertEqual(change["watch_id"], watch_id)
            failures = [item for section in report["sections"] for item in section["failures"]]
            self.assertIn(failed["result_id"], {item["run_id"] for item in failures})
        scoped = self.result("changes", "--domain", "example.com", "--days", "7")
        self.assertEqual({section["family"] for section in scoped["sections"]}, {"brand", "surface"})

    def check_source_contribution(self, baseline, resumed):
        report = self.result("sources", "contribution", "example.com")
        brand = next(item for item in report["groups"] if item["family"] == "brand")
        expected = {"example-support.net", "example-login.net", "example-help.net"}
        self.assertEqual(self.domains(brand["union_domains"]), expected)
        self.assertEqual(self.domains(brand["overlaps"][0]["domains"]), {"example-support.net"})
        sources = {item["provider"]: item for item in brand["sources"]}
        self.assertEqual(self.domains(sources["crt.sh"]["exclusive_domains"]), {"example-login.net"})
        self.assertEqual(self.domains(sources["urlscan"]["exclusive_domains"]), {"example-help.net"})
        urlscan = sources["urlscan"]
        self.assertEqual(
            (urlscan["outcomes"]["completion_numerator"], urlscan["outcomes"]["completion_denominator"]),
            (2, 3),
        )
        self.assertEqual(urlscan["outcomes"]["failed"], 1)
        self.assertEqual(sources["crt.sh"]["outcomes"]["complete"], 2)
        urlscan_ids = {
            self.receipt(history, "scan_attempt", source="urlscan")["result_id"]
            for history in (baseline, resumed)
        }
        shared = sources["urlscan"]["shared_domains"]["items"][0]
        self.assertEqual(set(shared["evidence_ids"]), urlscan_ids)
        surface = next(item for item in report["groups"] if item["family"] == "surface")
        self.assertEqual(self.domains(surface["union_domains"]), {"portal.example.com"})
        self.assertEqual(surface["union_domains"]["items"][0]["review_statuses"], ["pending"])
        page = self.result(
            "sources", "contribution", "example.com", "--family", "brand",
            "--detail-limit", "1", "--detail-offset", "1",
        )["groups"][0]["union_domains"]
        self.assertEqual((page["total_count"], page["shown_count"]), (3, 1))
        self.assertEqual(page["items"][0]["domain"], sorted(expected)[1])
        code, output, error = self.invoke("sources", "contribution", "example.com", as_json=False)
        self.assertEqual((code, error), (0, ""))
        for value in expected | {"portal.example.com", *urlscan_ids}:
            self.assertIn(value, output)
        self.assertIn("2/3", output)

    def check_group_scope(self, organization_id, watch_id):
        organization = self.result("organizations", "show", organization_id)
        self.assertEqual(organization["total_link_count"], 2)
        self.assertEqual(
            {(item["link"]["target"]["kind"], item["link"]["target"]["value"])
             for item in organization["links"]},
            {("domain", "example.com"), ("ransomlook-watch", watch_id)},
        )
        candidates = self.result("surface", "candidates", "example.com")["items"]
        self.assertEqual([(item["domain"], item["status"]) for item in candidates], [
            ("portal.example.com", "pending"),
        ])


if __name__ == "__main__":
    unittest.main()
