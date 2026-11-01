"""Offline acceptance gate for optional brand-OSINT tools."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from xti.application.brand_source_evaluation import BrandSourceEvaluationService
from xti.interfaces.cli import main


class BrandSourceEvaluationTests(unittest.TestCase):
    def test_gate_selects_limited_maigret_and_archive_domain_adapters(self):
        report = BrandSourceEvaluationService().report()
        self.assertEqual(
            report.profile_version, "free-brand-osint-tool-gate-v2",
        )
        self.assertEqual(report.selected_identifier, "maigret-limited-cli")
        selected = [
            item for item in report.candidates
            if item.decision == "selected_for_adapter"
        ]
        self.assertEqual(len(selected), 2)
        self.assertTrue(all(
            criterion.passed
            for candidate in selected
            for criterion in candidate.criteria
            if criterion.required
        ))
        candidates = {item.identifier: item for item in report.candidates}
        self.assertEqual(candidates["sherlock-cli"].decision, "deferred_duplicate")
        self.assertEqual(
            candidates["theharvester-passive-only"].decision,
            "selected_for_adapter",
        )
        self.assertEqual(
            candidates["web-check-whole-application"].decision,
            "rejected_overlap",
        )
        self.assertEqual(candidates["holehe-account-recovery"].decision, "rejected_method")
        recovery = next(
            item for item in candidates["holehe-account-recovery"].criteria
            if item.key == "no_recovery_enumeration"
        )
        self.assertFalse(recovery.passed)
        for candidate in report.candidates:
            self.assertTrue(candidate.reference_urls)
            self.assertTrue(all(
                url.startswith("https://") for url in candidate.reference_urls
            ))

    def test_terminal_and_json_are_offline_and_do_not_create_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "not-created"
            for as_json in (False, True):
                argv = ["--data-dir", str(data)]
                if as_json:
                    argv.append("--json")
                stdout, stderr = StringIO(), StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main([*argv, "brand", "source-evaluation"])
                self.assertEqual((code, stderr.getvalue()), (0, ""))
                if as_json:
                    result = json.loads(stdout.getvalue())
                    self.assertTrue(result["ok"])
                    self.assertEqual(
                        result["data"]["selected_identifier"],
                        "maigret-limited-cli",
                    )
                else:
                    self.assertIn(
                        "Maigret sınırlı CLI adaptörü | adaptör için seçildi",
                        stdout.getvalue(),
                    )
                    self.assertIn("Holehe", stdout.getvalue())
            self.assertFalse(data.exists())


if __name__ == "__main__":
    unittest.main()
