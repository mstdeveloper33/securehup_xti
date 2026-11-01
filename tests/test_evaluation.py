"""Pinned, transparent quality measurement for domain matching rules."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters import evaluation_dataset as dataset_adapter
from xti.adapters.evaluation_dataset import EvaluationDataError, load_evaluation_dataset
from xti.application.evaluation import EvaluationService
from xti.domain.assets import ValidationError
from xti.domain.evaluation import EvaluationDataset
from xti.interfaces.cli import main, make_domain_matcher


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = load_evaluation_dataset()
        cls.report = EvaluationService(make_domain_matcher()).run(cls.dataset)

    def test_pinned_dataset_and_baseline_are_stable_and_fully_visible(self):
        report = self.report
        self.assertEqual(report.dataset_version, "domain-evaluation-v2")
        self.assertEqual(report.dataset_sha256, dataset_adapter.DATASET_SHA256)
        self.assertEqual(report.total, 47)
        self.assertEqual((report.expected_review, report.expected_ignore), (27, 20))
        self.assertEqual(
            (report.true_positive, report.true_negative, report.false_positive, report.false_negative),
            (27, 17, 3, 0),
        )
        self.assertEqual(
            (report.precision_percent, report.recall_percent,
             report.false_positive_rate_percent, report.accuracy_percent),
            (90.0, 100.0, 15.0, 93.62),
        )
        self.assertEqual(report.known_gap_count, 3)
        self.assertEqual(report.baseline_change_count, 0)
        self.assertEqual(report.baseline_changes, ())

    def test_known_gaps_are_not_hidden_or_misreported_as_real_threat_labels(self):
        gaps = {item.case_id: item for item in self.report.quality_gaps}
        self.assertEqual(
            set(gaps),
            {"context-gap-001", "context-gap-002", "context-gap-003"},
        )
        self.assertEqual(sum(item.false_positive for item in self.report.categories), 3)
        self.assertEqual(sum(item.false_negative for item in self.report.categories), 0)
        self.assertTrue(any("gerçek internet doğruluğu değildir" in item for item in self.report.notes))
        self.assertTrue(any("phishing" in item for item in self.report.notes))
        self.assertTrue(all(item.predicted == item.baseline for item in gaps.values()))

    def test_unicode_inputs_share_canonical_behavior_without_becoming_quality_gaps(self):
        unicode_cases = tuple(
            item for item in self.dataset.cases if item.category.startswith("unicode-")
        )
        report = EvaluationService(make_domain_matcher()).run(replace(
            self.dataset, cases=unicode_cases,
        ))
        self.assertEqual(report.total, 4)
        self.assertEqual((report.true_positive, report.true_negative), (3, 1))
        self.assertEqual(report.quality_gaps, ())
        self.assertEqual(report.baseline_change_count, 0)

    def test_baseline_change_is_separate_from_quality_gap_and_cannot_be_silent(self):
        first, *remaining = self.dataset.cases
        changed = replace(first, baseline="review")
        report = EvaluationService(make_domain_matcher()).run(replace(
            self.dataset, cases=(changed, *remaining),
        ))
        self.assertEqual(report.known_gap_count, 3)
        self.assertEqual(report.baseline_change_count, 1)
        self.assertEqual(report.baseline_changes[0].case_id, first.id)
        self.assertNotIn(first.id, {item.case_id for item in report.quality_gaps})

    def test_invalid_injected_datasets_fail_before_partial_report(self):
        first = self.dataset.cases[0]
        attempts = (
            replace(self.dataset, cases=()),
            replace(self.dataset, sha256="bad"),
            replace(self.dataset, cases=(first, first)),
            replace(self.dataset, cases=(replace(first, id=""),)),
            replace(self.dataset, cases=(replace(first, expected="threat"),)),
        )
        for dataset in attempts:
            with self.subTest(dataset=dataset), self.assertRaises(ValidationError):
                EvaluationService(make_domain_matcher()).run(dataset)

    def test_packaged_digest_mismatch_fails_closed(self):
        load_evaluation_dataset.cache_clear()
        self.addCleanup(load_evaluation_dataset.cache_clear)
        with patch.object(dataset_adapter, "DATASET_SHA256", "0" * 64):
            with self.assertRaisesRegex(EvaluationDataError, "özeti uyuşmuyor"):
                load_evaluation_dataset()

    def test_cli_runs_without_database_or_network_and_has_human_and_json_views(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "must-not-exist"
            project = Path(__file__).resolve().parents[1]
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(project / "src")
            base = [sys.executable, "-m", "xti", "--data-dir", str(data)]
            human = subprocess.run(
                [*base, "evaluate"], text=True, capture_output=True, check=False,
                timeout=15, env=environment, cwd=project,
            )
            self.assertEqual(human.returncode, 0, human.stderr)
            self.assertIn("47 sürümlü sentetik örnek", human.stdout)
            self.assertIn("Bilinen kalite açığı: 3", human.stdout)
            self.assertIn("gerçek internet doğruluğu değildir", human.stdout)
            machine = subprocess.run(
                [*base, "--json", "evaluate"], text=True, capture_output=True,
                check=False, timeout=15, env=environment, cwd=project,
            )
            self.assertEqual(machine.returncode, 0, machine.stderr)
            payload = json.loads(machine.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["data"]["false_positive"], 3)
            self.assertEqual(payload["data"]["baseline_change_count"], 0)
            self.assertFalse(data.exists())

    def test_cli_reports_bundled_data_failure_without_traceback(self):
        stdout, stderr = StringIO(), StringIO()
        with patch(
            "xti.interfaces.cli.load_evaluation_dataset",
            side_effect=EvaluationDataError("Kontrollü veri hatası."),
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--json", "evaluate"])
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "evaluation_data_error")
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
