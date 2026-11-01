"""Pinned, offline coverage gate for a second social username source."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
from importlib.resources import files
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from xti.application.brand_source_coverage import BrandSourceCoverageService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main


def profile_payload() -> bytes:
    return files("xti").joinpath("data").joinpath(
        "brand_social_source_coverage_v1.json"
    ).read_bytes()


class BrandSourceCoverageTests(unittest.TestCase):
    def test_gate_measures_candidate_contribution_and_accepts_only_limited_adapter(self):
        report = BrandSourceCoverageService().report()

        self.assertEqual(report.profile_version, "free-social-source-coverage-gate-v2")
        self.assertEqual(report.decision, "accepted_for_limited_adapter")
        self.assertEqual(
            [(source.label, source.version) for source in report.sources],
            [("Maigret", "0.6.6"), ("Sherlock", "0.16.2")],
        )
        self.assertEqual(
            (
                report.comparison.shared_candidate_entries,
                report.comparison.candidate_unmatched_entries,
                report.comparison.candidate_unmatched_distinct_hosts,
                report.comparison.candidate_unmatched_distinct_registrable_domains,
            ),
            (352, 103, 102, 101),
        )
        self.assertEqual(report.comparison.current_primary_only, ("Facebook",))
        self.assertEqual(report.comparison.current_candidate_only, ())
        self.assertTrue(all(item.passed for item in report.criteria if item.required))
        current_gain = next(
            item for item in report.criteria if item.key == "current_allowlist_gain"
        )
        self.assertFalse(current_gain.required)
        self.assertFalse(current_gain.passed)
        self.assertEqual(len(report.shortlist), 8)

    def test_profile_digest_and_cross_count_invariants_fail_closed(self):
        payload = profile_payload()
        corrupted = payload.replace(b'"catalog_entries": 481', b'"catalog_entries": 482')
        with self.assertRaisesRegex(ValidationError, "uyuşmuyor"):
            BrandSourceCoverageService(lambda: corrupted).report()

        raw = json.loads(payload)
        raw["comparison"]["candidate_unmatched_entries"] = 104
        inconsistent = json.dumps(raw, ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(inconsistent).hexdigest()
        with self.assertRaisesRegex(ValidationError, "aday toplamı tutarsız"):
            BrandSourceCoverageService(
                lambda: inconsistent,
                expected_sha256=digest,
            ).report()

    def test_duplicate_keys_and_unsafe_reference_fail_closed(self):
        payload = profile_payload()
        duplicate = payload.replace(
            b'{\n  "schema_version": 1,',
            b'{\n  "schema_version": 1,\n  "schema_version": 1,',
        )
        digest = hashlib.sha256(duplicate).hexdigest()
        with self.assertRaisesRegex(ValidationError, "gecerli JSON|geçerli JSON"):
            BrandSourceCoverageService(
                lambda: duplicate,
                expected_sha256=digest,
            ).report()

        raw = json.loads(payload)
        raw["reference_urls"][0] = "http://example.test/profile"
        unsafe = json.dumps(raw, ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(unsafe).hexdigest()
        with self.assertRaisesRegex(ValidationError, "başvuru adresi bozuk"):
            BrandSourceCoverageService(
                lambda: unsafe,
                expected_sha256=digest,
            ).report()

    def test_terminal_and_json_are_offline_and_do_not_create_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "not-created"
            for as_json in (False, True):
                argv = ["--data-dir", str(data)]
                if as_json:
                    argv.append("--json")
                stdout, stderr = StringIO(), StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main([*argv, "brand", "source-coverage"])
                self.assertEqual((code, stderr.getvalue()), (0, ""))
                if as_json:
                    result = json.loads(stdout.getvalue())
                    self.assertTrue(result["ok"])
                    self.assertEqual(
                        result["data"]["decision"],
                        "accepted_for_limited_adapter",
                    )
                    self.assertEqual(
                        result["data"]["comparison"][
                            "candidate_unmatched_distinct_registrable_domains"
                        ],
                        101,
                    )
                else:
                    self.assertIn(
                        "Aday kaynağa özgü ölçülen kapsam: 102 host / 101 kayıt kökü",
                        stdout.getvalue(),
                    )
                    self.assertIn(
                        "Karar: Sherlock yalnız sınırlı adaptör için kabul edildi.",
                        stdout.getvalue(),
                    )
            self.assertFalse(data.exists())


if __name__ == "__main__":
    unittest.main()
