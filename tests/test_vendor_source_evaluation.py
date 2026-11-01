"""Versioned, offline gate for additional official vulnerability sources."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from xti.application.vendor_source_evaluation import VendorSourceEvaluationService
from xti.interfaces.cli import main


class VendorSourceEvaluationTests(unittest.TestCase):
    def test_gate_selects_only_ubuntu_and_records_other_blockers(self):
        report = VendorSourceEvaluationService().report()
        self.assertEqual(report.profile_version, "official-vendor-source-gate-v1")
        self.assertEqual(report.selected_identifier, "canonical-ubuntu-osv")
        selected = [item for item in report.candidates if item.decision == "selected"]
        self.assertEqual(len(selected), 1)
        self.assertTrue(all(
            criterion.passed
            for criterion in selected[0].criteria
            if criterion.required
        ))
        candidates = {item.identifier: item for item in report.candidates}
        self.assertEqual(candidates["microsoft-msrc-cvrf"].decision, "deferred")
        self.assertEqual(candidates["debian-security-tracker"].decision, "deferred")
        cisco = candidates["cisco-openvuln"]
        self.assertEqual(cisco.decision, "rejected_for_free_profile")
        authentication = next(
            item for item in cisco.criteria if item.key == "unauthenticated_free"
        )
        self.assertFalse(authentication.passed)
        for candidate in report.candidates:
            self.assertTrue(candidate.reference_urls)
            self.assertTrue(all(url.startswith("https://") for url in candidate.reference_urls))

    def test_terminal_and_json_are_offline_and_do_not_create_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "missing"
            for as_json in (False, True):
                argv = ["--data-dir", str(data)]
                if as_json:
                    argv.append("--json")
                stdout, stderr = StringIO(), StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main([*argv, "vuln", "source-evaluation"])
                self.assertEqual((code, stderr.getvalue()), (0, ""))
                if as_json:
                    result = json.loads(stdout.getvalue())
                    self.assertTrue(result["ok"])
                    self.assertEqual(
                        result["data"]["selected_identifier"], "canonical-ubuntu-osv",
                    )
                else:
                    self.assertIn("Canonical Ubuntu OSV | seçildi", stdout.getvalue())
                    self.assertIn("Cisco PSIRT", stdout.getvalue())
            self.assertFalse(data.exists())


if __name__ == "__main__":
    unittest.main()
