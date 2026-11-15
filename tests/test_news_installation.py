"""Pinned optional reader, managed-environment verification and CI installation."""

from io import BytesIO
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("news_installation_verifier", PROJECT / "scripts/verify_brand_install.py")
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class NewsInstallationTests(unittest.TestCase):
    def test_optional_extra_constraints_and_hashed_ci_wheels_agree(self):
        with (PROJECT / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)["project"]
        expected = [f"{name}=={version}" for name, version, _ in VERIFIER.NEWS_PACKAGES]
        self.assertEqual(project["dependencies"], [])
        self.assertEqual(project["optional-dependencies"]["news"], expected)
        requirements = (PROJECT / "requirements/news.txt").read_text()
        entries = [line for line in requirements.splitlines() if line and not line.startswith("#")]
        self.assertEqual([line.split()[0] for line in entries], expected)
        self.assertTrue(all(re.fullmatch(r"[^ ]+ --hash=sha256:[a-f0-9]{64}", line) for line in entries))
        constraints = (PROJECT / "constraints/brand.txt").read_text().splitlines()
        self.assertTrue(all(line in constraints for line in expected))

    def test_absent_wrong_version_and_external_distribution_stop_before_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix = Path(temporary)
            for installed in (
                VERIFIER.PackageNotFoundError("feedparser"),
                SimpleNamespace(version="wrong", locate_file=lambda value: prefix),
                SimpleNamespace(version="6.0.14", locate_file=lambda value: prefix.parent),
            ):
                with self.subTest(installed=installed), \
                     patch.object(VERIFIER, "distribution", side_effect=(
                         installed if isinstance(installed, Exception) else lambda name: installed)), \
                     patch.object(VERIFIER.importlib, "import_module") as imported:
                    with self.assertRaises(VERIFIER.VerificationError):
                        VERIFIER._verify_news_runtime(prefix)
                    imported.assert_not_called()

    def test_external_module_and_broken_import_are_controlled_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix = Path(temporary)
            installed = SimpleNamespace(version="6.0.14", locate_file=lambda value: prefix)
            for outcome in (ImportError("broken parser"), SimpleNamespace(__file__=str(prefix.parent / "parser.py"))):
                with self.subTest(outcome=outcome), patch.object(VERIFIER, "distribution", return_value=installed), \
                     patch.object(VERIFIER.importlib, "import_module", side_effect=(
                         outcome if isinstance(outcome, Exception) else lambda name: outcome)):
                    with self.assertRaises(VERIFIER.VerificationError):
                        VERIFIER._verify_news_runtime(prefix)

    def test_real_pinned_reader_parses_both_formats_from_memory_without_network(self):
        import feedparser

        real_parse = feedparser.parse
        formats = []

        def parse(stream):
            self.assertIsInstance(stream, BytesIO)
            result = real_parse(stream)
            formats.append(result.version)
            return result

        with patch.object(feedparser, "parse", side_effect=parse), \
             patch("feedparser.http.get", side_effect=AssertionError("network used")):
            VERIFIER._verify_news_runtime(Path(sys.prefix))
        self.assertEqual(formats, ["rss20", "atom10"])
        with patch.object(feedparser, "parse", return_value=SimpleNamespace(bozo=False, entries=[])):
            with self.assertRaisesRegex(VERIFIER.VerificationError, "RSS/Atom"):
                VERIFIER._verify_news_runtime(Path(sys.prefix))

    def test_offline_test_gates_install_only_the_reviewed_wheels_before_testing(self):
        for workflow in ("check.yml", "full-check.yml", "stabilization.yml", "brand-install.yml", "harvester-install.yml"):
            with self.subTest(workflow=workflow):
                text = (PROJECT / ".github/workflows" / workflow).read_text()
                self.assertIn("--only-binary=:all: --require-hashes", text)
                self.assertIn("-r requirements/news.txt", text)


if __name__ == "__main__":
    unittest.main()
