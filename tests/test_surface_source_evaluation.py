"""Offline acceptance gate for passive surface discovery adapters."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from xti.application.surface_source_evaluation import (
    SurfaceSourceEvaluationService,
    _validate_candidates,
)
from xti.domain.surface import SURFACE_DISCOVERY_PROVIDERS
from xti.interfaces.cli import main


class SurfaceSourceEvaluationTests(unittest.TestCase):
    def test_active_adapters_pass_every_required_gate_and_match_runtime(self):
        report = SurfaceSourceEvaluationService().report()
        self.assertEqual(report.profile_version, "passive-surface-source-gate-v2")
        self.assertEqual(report.active_identifiers, SURFACE_DISCOVERY_PROVIDERS)
        active = [item for item in report.candidates if item.decision == "active"]
        self.assertEqual([item.identifier for item in active], list(SURFACE_DISCOVERY_PROVIDERS))
        self.assertTrue(all(
            criterion.passed
            for candidate in active
            for criterion in candidate.criteria
            if criterion.required
        ))
        for candidate in report.candidates:
            keys = tuple(criterion.key for criterion in candidate.criteria)
            self.assertEqual(len(keys), len(set(keys)))
            self.assertEqual(set(keys), set(report.required_criteria))
            self.assertTrue(all(criterion.required for criterion in candidate.criteria))

    def test_gate_rejects_missing_duplicate_and_failed_active_criteria(self):
        candidate = SurfaceSourceEvaluationService().report().candidates[0]
        with self.assertRaisesRegex(ValueError, "zorunlu ölçütlerle uyuşmuyor"):
            _validate_candidates((replace(candidate, criteria=candidate.criteria[:-1]),))
        with self.assertRaisesRegex(ValueError, "yinelenen ölçüt"):
            _validate_candidates((
                replace(candidate, criteria=(*candidate.criteria, candidate.criteria[0])),
            ))
        failed = replace(candidate.criteria[0], passed=False)
        with self.assertRaisesRegex(ValueError, "etkinleştirilemez"):
            _validate_candidates((replace(
                candidate,
                criteria=(failed, *candidate.criteria[1:]),
            ),))

    def test_subfinder_cli_is_deferred_on_machine_contract_and_new_coverage(self):
        report = SurfaceSourceEvaluationService().report()
        subfinder = next(
            item for item in report.candidates
            if item.identifier == "subfinder-cli-v2.17.0"
        )
        self.assertEqual(subfinder.decision, "deferred_contract")
        self.assertIn("c97f25802892093060f0fc424bfc3f39e273693a", subfinder.upstream_version)
        criteria = {item.key: item for item in subfinder.criteria}
        self.assertFalse(criteria["strict_machine_contract"].passed)
        self.assertFalse(criteria["source_outcome_separation"].passed)
        self.assertFalse(criteria["independent_coverage"].passed)
        self.assertTrue(all(url.startswith("https://") for url in subfinder.reference_urls))

    def test_terminal_and_json_are_offline_and_do_not_create_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "not-created"
            for as_json in (False, True):
                argv = ["--data-dir", str(data)]
                if as_json:
                    argv.append("--json")
                stdout, stderr = StringIO(), StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main([*argv, "surface", "source-evaluation"])
                self.assertEqual((code, stderr.getvalue()), (0, ""))
                if as_json:
                    payload = json.loads(stdout.getvalue())
                    self.assertTrue(payload["ok"])
                    self.assertEqual(
                        payload["data"]["active_identifiers"],
                        list(SURFACE_DISCOVERY_PROVIDERS),
                    )
                else:
                    self.assertIn("Pasif dış yüzey kaynak kabul kapısı", stdout.getvalue())
                    self.assertIn("Subfinder CLI v2.17.0", stdout.getvalue())
            self.assertFalse(data.exists())


if __name__ == "__main__":
    unittest.main()
