"""Review feedback stays read-only, consistent and distinct from ground truth."""

from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_feedback import SQLiteFeedbackRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.application.assets import AssetService
from xti.application.feedback import FeedbackService
from xti.application.findings import DomainImportService, FindingService
from xti.domain.feedback import FeedbackError, FeedbackSnapshot, RuleFeedback
from xti.interfaces.cli import main, make_domain_matcher

from tests.test_discovery import document


def feedback_snapshot() -> FeedbackSnapshot:
    return FeedbackSnapshot(
        finding_counts={"new": 1, "suspicious": 0, "dismissed": 1, "uncertain": 1},
        review_event_count=2,
        revisited_finding_count=0,
        rules=(
            RuleFeedback("rule-v1", 2, 1, 1, 0, 1, 0),
            RuleFeedback("rule-v2", 1, 1, 0, 0, 0, 1),
        ),
    )


class FeedbackServiceTests(unittest.TestCase):
    def test_report_exposes_review_coverage_without_quality_claim(self):
        repository = Mock(spec=["snapshot"])
        repository.snapshot.return_value = feedback_snapshot()
        report = FeedbackService(repository).show()
        self.assertEqual((report.total_findings, report.reviewed_findings), (3, 2))
        self.assertEqual(report.review_coverage_percent, 66.67)
        self.assertEqual(report.decision_counts, {
            "suspicious": 0, "dismissed": 1, "uncertain": 1,
        })
        self.assertTrue(any("doğrulanmış tehdit" in note for note in report.notes))
        repository.snapshot.assert_called_once_with()

    def test_empty_snapshot_is_a_valid_zero_coverage_report(self):
        repository = Mock(spec=["snapshot"])
        repository.snapshot.return_value = FeedbackSnapshot(
            {name: 0 for name in ("new", "suspicious", "dismissed", "uncertain")},
            0, 0, (),
        )
        report = FeedbackService(repository).show()
        self.assertEqual(report.total_findings, 0)
        self.assertEqual(report.review_coverage_percent, 0.0)

    def test_contradictory_or_unsorted_snapshot_is_rejected(self):
        valid = feedback_snapshot()
        cases = (
            replace(valid, finding_counts={**valid.finding_counts, "new": -1}),
            replace(valid, review_event_count=1),
            replace(valid, revisited_finding_count=3),
            replace(valid, rules=tuple(reversed(valid.rules))),
            replace(valid, rules=(replace(valid.rules[0], reviewed_findings=2), valid.rules[1])),
        )
        for current in cases:
            with self.subTest(current=current):
                repository = Mock(spec=["snapshot"])
                repository.snapshot.return_value = current
                with self.assertRaises(FeedbackError):
                    FeedbackService(repository).show()


class FeedbackStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "xti.db"
        self.assets = SQLiteAssetRepository(self.database)
        self.assets.initialize()
        AssetService(self.assets).add("example.com")
        self.findings = SQLiteFindingRepository(self.database)
        self.importer = DomainImportService(self.assets, self.findings, make_domain_matcher())

    def test_snapshot_groups_current_decisions_and_counts_revisits(self):
        for number, domain in enumerate(
            ("example-support.net", "exampleshop.net", "exampel-login.net"), start=1,
        ):
            self.importer.import_document(document(domain, number))
        saved = {item.domain: item for item in self.findings.list_findings()}
        service = FindingService(self.findings)
        service.review(saved["example-support.net"].id, "dismissed", "İlk karar.")
        service.review(saved["example-support.net"].id, "suspicious", "Yeni kanıtla değişti.")
        service.review(saved["exampleshop.net"].id, "uncertain", "Bağlam gerekli.")

        before = self.database.read_bytes()
        report = FeedbackService(SQLiteFeedbackRepository(self.database)).show()
        self.assertEqual((report.total_findings, report.reviewed_findings), (3, 2))
        self.assertEqual(report.decision_counts, {
            "suspicious": 1, "dismissed": 0, "uncertain": 1,
        })
        self.assertEqual((report.review_event_count, report.revisited_finding_count), (3, 1))
        by_version = {item.rule_version.split("/")[0]: item for item in report.rules}
        self.assertEqual((by_version["domain-rules-v1"].total_findings,
                          by_version["domain-rules-v1"].suspicious), (1, 1))
        self.assertEqual((by_version["domain-rules-v2"].total_findings,
                          by_version["domain-rules-v2"].uncertain,
                          by_version["domain-rules-v2"].unreviewed_findings), (2, 1, 1))
        self.assertEqual(self.database.read_bytes(), before)

    def test_missing_database_read_has_no_side_effect(self):
        missing = Path(self.temp.name) / "missing" / "xti.db"
        with self.assertRaises(StorageError):
            SQLiteFeedbackRepository(missing).snapshot()
        self.assertFalse(missing.parent.exists())

    def test_status_without_matching_review_fails_closed(self):
        self.importer.import_document(document("example-support.net"))
        finding = self.findings.list_findings()[0]
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE findings SET status = 'suspicious' WHERE id = ?", (finding.id,))
            connection.commit()
        with self.assertRaisesRegex(StorageError, "son inceleme"):
            SQLiteFeedbackRepository(self.database).snapshot()


class FeedbackCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "feedback data"

    def invoke(self, *arguments, as_json=True):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([
                "--data-dir", str(self.data), *( ["--json"] if as_json else []), *arguments,
            ])
        return code, stdout.getvalue(), stderr.getvalue()

    def success(self, *arguments, as_json=True):
        code, stdout, stderr = self.invoke(*arguments, as_json=as_json)
        self.assertEqual((code, stderr), (0, ""))
        return json.loads(stdout)["data"] if as_json else stdout

    def test_empty_feedback_is_read_only_and_explains_limits(self):
        self.success("init")
        before = (self.data / "xti.db").read_bytes()
        report = self.success("feedback")
        self.assertEqual(report["total_findings"], 0)
        self.assertEqual(report["rules"], [])
        self.assertEqual((self.data / "xti.db").read_bytes(), before)
        text = self.success("feedback", as_json=False)
        self.assertIn("yalnız kayıtlı kullanıcı kararları", text)
        self.assertIn("doğrulanmış tehdit etiketi değildir", text)

    def test_public_flow_reports_latest_decision_and_not_a_truth_metric(self):
        self.success("init")
        self.success("assets", "add", "example.com")
        source = self.root / "domains.txt"
        source.write_text("example-support.net\nexampleshop.net\n", encoding="utf-8")
        self.success("import", "domains", str(source))
        findings = self.success("findings", "list")["findings"]
        by_domain = {item["domain"]: item for item in findings}
        identifier = by_domain["example-support.net"]["id"]
        self.success("findings", "review", identifier,
                     "--decision", "dismissed", "--reason", "Bilinen adres.")
        self.success("findings", "review", identifier,
                     "--decision", "suspicious", "--reason", "Yeni bağlam.")
        report = self.success("feedback")
        self.assertEqual((report["total_findings"], report["reviewed_findings"]), (2, 1))
        self.assertEqual(report["decision_counts"]["suspicious"], 1)
        self.assertEqual((report["review_event_count"], report["revisited_finding_count"]), (2, 1))
        self.assertTrue(any("otomatik phishing sayılmaz" in note for note in report["notes"]))

    def test_missing_feedback_database_is_an_error_without_creation(self):
        code, stdout, stderr = self.invoke("feedback")
        self.assertEqual((code, stdout), (1, ""))
        self.assertEqual(json.loads(stderr)["error"]["code"], "storage_error")
        self.assertFalse(self.data.exists())


if __name__ == "__main__":
    unittest.main()
