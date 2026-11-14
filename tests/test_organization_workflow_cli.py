"""Offline acceptance of the composed organization workflow and public feed CLI."""

from dataclasses import replace
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import patch

from xti.domain.public_notices import HIBP_ATTRIBUTION, HIBP_LICENSE
from xti.interfaces.cli import build_parser
from xti.ports.discovery import SourceError
from tests import test_organization_report as fixtures
from tests.test_collection_watch_cli import ClaimSource, github
from tests.test_public_notices import feed, item


class OrganizationWorkflowCLITests(unittest.TestCase):
    invoke = fixtures.OrganizationReportTests.invoke
    result = fixtures.OrganizationReportTests.result
    files = fixtures.OrganizationReportTests.files
    add_social = fixtures.OrganizationReportTests.add_social
    add_tc = fixtures.OrganizationReportTests.add_tc
    add_rl = fixtures.OrganizationReportTests.add_rl
    link = fixtures.OrganizationReportTests.link
    collect = fixtures.OrganizationReportTests.collect

    def setUp(self):
        fixtures.OrganizationReportTests.setUp(self)
        self.notice_source = ClaimSource(self.catalog(item(), item("Other", "other.example")))
        self.factory = self.enterContext(patch("xti.interfaces.cli.HibpPublicNoticeSource", return_value=self.notice_source))

    @staticmethod
    def catalog(*records):
        return replace(feed(*records), fetched_at=datetime.now(timezone.utc).isoformat())

    def test_report_changes_contribution_context_and_public_notices_work_together(self):
        self.link()
        social, tc, rl = self.add_social(), self.add_tc(), self.add_rl()
        for kind, watch in (("username-watch", social), ("ransomware-watch", tc), ("ransomlook-watch", rl)):
            self.link(kind, watch.id)
        self.maigret.responses.append({"GitHub": github()})
        self.collect("--username-watch", social.id, "--ransomware-watch", tc.id, "--ransomlook-watch", rl.id)
        first = self.result("notices", "refresh", "--limit", "1")
        self.assertTrue(first["is_baseline"])
        self.assertEqual((first["total_change_count"], len(first["changes"])), (2, 1))
        self.notice_source.value = self.catalog(item(PwnCount=54321), item("Other", "other.example"))
        updated = self.result("notices", "refresh")
        self.assertEqual(updated["run"]["updated_count"], 1)
        self.result("ioc", "add", "domain", "example.com", "--source", "manual",
                    "--reference", "local:test", "--confidence", "50", "--description", "Sentetik test kaydı.")
        self.factory.reset_mock()
        before = self.files()
        identifier = self.organization["id"]
        report = self.result("organizations", "report", identifier, "--item-limit", "1")
        self.assertEqual(report["total_target_count"], 4)
        domain = next(target for target in report["targets"] if target["membership"]["link"]["target"]["kind"] == "domain")
        notices = next(section for section in domain["sections"] if section["kind"] == "public_notices")
        self.assertEqual(notices["total_count"], 1)
        self.assertEqual(notices["items"][0]["public_notice"]["pwn_count"], 54321)
        self.assertNotIn("other.example", json.dumps(report))
        for target in report["targets"]:
            navigations = list(target["navigation"])
            for section in target["sections"]:
                for record in section["items"]:
                    navigations.extend(record["navigation"])
            for navigation in navigations:
                with self.subTest(command=navigation["arguments"]):
                    build_parser().parse_args(navigation["arguments"])
        changes = self.result("changes", "--organization", identifier, "--days", "7")
        public = next(section for section in changes["sections"] if section["family"] == "notices")
        self.assertEqual((public["total_baseline_count"], public["total_change_count"]), (1, 1))
        self.assertIn({"field": "pwn_count", "before": 12345, "after": 54321}, public["changes"][0]["value_changes"])
        sources = self.result("sources", "contribution", "--organization", identifier)
        self.assertEqual(sources["total_domain_count"], 1)
        context = self.result("cti", "context", "--type", "domain", "--value", "example.com")
        self.assertIsNotNone(context["root"])
        self.assertEqual(self.result("notices", "search", "--domain", "example.com")["matched_count"], 1)
        code, output, error = self.invoke("organizations", "report", identifier, as_json=False)
        self.assertEqual((code, error), (0, ""))
        for value in (HIBP_ATTRIBUTION, HIBP_LICENSE, "example.com"):
            self.assertIn(value, output)
        self.assertEqual(self.files(), before)
        self.factory.assert_not_called()

    def test_failed_refresh_retains_last_catalog_and_is_not_successful_json(self):
        success = self.result("notices", "refresh")
        self.notice_source.value = SourceError("Kaynak HTTP 429 verdi.")
        failed = self.result("notices", "refresh", expected_code=3)
        self.assertEqual(failed["run"]["status"], "failed")
        search = self.result("notices", "search", "--domain", "example.com")
        self.assertEqual(search["matched_count"], 1)
        self.assertEqual(search["latest_complete_run"]["id"], success["run"]["id"])
        self.assertEqual(search["latest_run"]["id"], failed["run"]["id"])
        code, output, _ = self.invoke("notices", "search", "--domain", "example.com", as_json=False)
        self.assertEqual(code, 0)
        self.assertIn("önceki başarılı katalog", output)
        self.assertIn("HTTP 429", output)

    def test_historical_removed_record_is_readable_without_current_record_navigation(self):
        self.result("notices", "refresh")
        self.notice_source.value = self.catalog(item("Other", "other.example"))
        removed = self.result("notices", "refresh")
        code, output, error = self.invoke("notices", "run-show", removed["run"]["id"], as_json=False)
        self.assertEqual((code, error), (0, ""))
        self.assertIn("removed", output)
        self.assertIn("12345", output)
        self.assertNotIn("./xti notices show Example", output)
        self.assertEqual(self.result("notices", "search", "--domain", "example.com")["matched_count"], 0)

    def test_not_initialized_and_invalid_refresh_do_not_contact_source(self):
        status = self.result("notices", "status")
        self.assertIsNone(status["latest_complete_run"])
        before = self.files()
        code, _, _ = self.invoke("notices", "refresh", "--limit", "0")
        self.assertEqual(code, 2)
        self.assertEqual(self.notice_source.calls, 0)
        # A lock file may be created; the database and evidence are unchanged.
        self.assertEqual(self.database.read_bytes(), before["xti.db"])
        code, _, _ = self.invoke("changes", "--domain", "example.com", "--organization", self.organization["id"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
