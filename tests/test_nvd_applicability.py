"""Read-only NVD CPE applicability context without exposure claims."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.nvd_cve import NvdCveSource
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_nvd import SQLiteNvdRepository
from xti.adapters.sqlite_nvd_applicability import SQLiteNvdApplicabilityRepository
from xti.application.vulnerability import NvdApplicabilityService
from xti.domain.vulnerability import NVD_CVE_SOURCE, NvdCve, NvdCveSnapshot, nvd_cve_url
from xti.interfaces.cli import main


CVE = "CVE-2026-2001"
UUIDS = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
    "44444444-4444-4444-8444-444444444444",
)


def configurations():
    return [
        {
            "operator": "OR", "negate": False,
            "nodes": [{
                "operator": "OR", "negate": False,
                "cpeMatch": [
                    {
                        "vulnerable": True,
                        "criteria": "cpe:2.3:a:acme:server:*:*:*:*:*:*:*:*",
                        "matchCriteriaId": UUIDS[0],
                        "versionStartIncluding": "1.0",
                        "versionEndExcluding": "2.0",
                    },
                    {
                        "vulnerable": True,
                        "criteria": "cpe:2.3:a:acme:agent:1.0\\(lts\\):*:*:*:*:*:*:*",
                        "matchCriteriaId": UUIDS[1],
                    },
                ],
            }],
        },
        {
            "operator": "AND",
            "nodes": [
                {
                    "operator": "OR", "cpeMatch": [{
                        "vulnerable": True,
                        "criteria": "cpe:2.3:o:acme:device_firmware:3.0:*:*:*:*:*:*:*",
                        "matchCriteriaId": UUIDS[2],
                    }],
                },
                {
                    "operator": "OR", "cpeMatch": [{
                        "vulnerable": False,
                        "criteria": "cpe:2.3:h:acme:device:-:*:*:*:*:*:*:*",
                        "matchCriteriaId": UUIDS[3],
                    }],
                },
            ],
        },
    ]


def snapshot(configs) -> NvdCveSnapshot:
    record = NvdCve(
        CVE, "security@example.com", "2026-01-01T00:00:00+00:00",
        "2026-10-29T00:00:00+00:00", "Analyzed", "Description",
        (), (), 0,
    )
    raw = json.dumps(
        {"id": CVE, **({"configurations": configs} if configs is not None else {})},
        ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    )
    return NvdCveSnapshot(
        NVD_CVE_SOURCE, nvd_cve_url(CVE), "2.0", "2026-10-29T11:00:00+00:00",
        hashlib.sha256(raw.encode()).hexdigest(), raw, record,
    )


class NvdApplicabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        SQLiteAssetRepository(self.path).initialize()

    def store(self, configs):
        SQLiteNvdRepository(self.path).apply(
            snapshot(configs), started_at="2026-10-29T11:00:00+00:00",
            finished_at="2026-10-29T11:00:01+00:00",
        )

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_preserves_groups_ranges_environment_and_cpe_escaping(self):
        self.store(configurations())
        before = self.path.read_bytes()
        report = NvdApplicabilityService(
            SQLiteNvdApplicabilityRepository(self.path),
        ).show(CVE, limit=10)
        self.assertEqual(report.total_match_count, 4)
        self.assertEqual(report.vulnerable_match_count, 3)
        self.assertEqual(report.environmental_match_count, 1)
        self.assertFalse(report.truncated)
        self.assertEqual(report.matches[0].version_start_including, "1.0")
        self.assertEqual(report.matches[0].version_end_excluding, "2.0")
        self.assertEqual(report.matches[1].version, "1.0(lts)")
        self.assertEqual(report.matches[2].configuration_operator, "AND")
        self.assertFalse(report.matches[3].vulnerable)
        self.assertEqual(report.matches[3].part, "h")
        self.assertEqual(self.path.read_bytes(), before)

    def test_limit_truncates_display_but_counts_and_validates_every_match(self):
        self.store(configurations())
        report = SQLiteNvdApplicabilityRepository(self.path).show(CVE, limit=2)
        self.assertEqual(len(report.matches), 2)
        self.assertEqual(report.total_match_count, 4)
        self.assertTrue(report.truncated)

    def test_missing_configurations_is_honest_empty_not_safe_claim(self):
        self.store(None)
        report = SQLiteNvdApplicabilityRepository(self.path).show(CVE, limit=50)
        self.assertEqual(report.total_match_count, 0)
        self.assertEqual(report.matches, ())
        self.assertFalse(report.truncated)

    def test_malformed_stored_applicability_fails_closed_without_writes(self):
        malformed = configurations()
        malformed[0]["nodes"][0]["cpeMatch"][0]["versionStartExcluding"] = "1.1"
        self.store(malformed)
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            SQLiteNvdApplicabilityRepository(self.path).show(CVE, limit=50)
        self.assertEqual(self.path.read_bytes(), before)

    def test_terminal_and_json_views_are_offline_read_only_and_explain_limits(self):
        self.store(configurations())
        before = self.path.read_bytes()
        with patch.object(NvdCveSource, "fetch") as fetch:
            code, stdout, stderr = self.invoke(
                "vuln", "applicability", CVE, "--limit", "2", as_json=False,
            )
            self.assertEqual((code, stderr), (0, ""))
            self.assertIn("AND/OR", stdout)
            self.assertIn("varlıkta ürün/sürüm", stdout)
            self.assertIn("İlk 2 koşul", stdout)
            code, stdout, stderr = self.invoke(
                "vuln", "applicability", CVE, "--limit", "2",
            )
            self.assertEqual((code, stderr), (0, ""))
            data = json.loads(stdout)["data"]
            self.assertEqual(data["total_match_count"], 4)
            self.assertTrue(data["truncated"])
            fetch.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
