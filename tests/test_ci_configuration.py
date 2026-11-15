from pathlib import Path
from fnmatch import fnmatchcase
import re
import stat
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CiConfigurationTests(unittest.TestCase):
    def test_every_push_runs_only_the_fast_offline_gate(self) -> None:
        workflow = (PROJECT_ROOT / ".github/workflows/check.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("name: XTI quick checks", workflow)
        self.assertIn("run: ./scripts/check-fast", workflow)
        self.assertNotIn("run: ./scripts/check\n", workflow)
        self.assertNotIn("setup-brand --check", workflow)

    def test_brand_install_is_path_scoped_and_rechecks_without_download(self) -> None:
        workflow = (
            PROJECT_ROOT / ".github/workflows/brand-install.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('      - "constraints/brand.txt"', workflow)
        self.assertIn('      - "scripts/setup-brand"', workflow)
        self.assertIn("run: ./setup", workflow)
        self.assertIn("run: ./scripts/setup-brand --check", workflow)

    def test_release_requires_the_complete_suite(self) -> None:
        workflow = (PROJECT_ROOT / ".github/workflows/full-check.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn('      - "v*"', workflow)
        self.assertIn("run: ./scripts/check", workflow)
        self.assertIn("needs: test", workflow)
        self.assertIn("gh release create", workflow)

    def test_brand_install_covers_shared_pins_and_verifier_on_both_events(self) -> None:
        workflow = (
            PROJECT_ROOT / ".github/workflows/brand-install.yml"
        ).read_text(encoding="utf-8")
        critical_paths = (
            "src/xti/domain/component_pins.py",
            "scripts/verify_brand_install.py",
            "scripts/setup-brand",
            "constraints/brand.txt",
            "xti",
        )
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                block = re.search(
                    rf"(?ms)^  {event}:\n(.*?)(?=^  [a-z_]+:|\Z)", workflow
                )
                self.assertIsNotNone(block)
                paths = re.findall(r'^      - "([^"\n]+)"$', block.group(1), re.MULTILINE)
                self.assertTrue(paths)
                for path in critical_paths:
                    self.assertTrue(
                        any(fnmatchcase(path, pattern) for pattern in paths),
                        f"{event} does not verify a change to {path}",
                    )
                self.assertFalse(any(fnmatchcase("docs/DAILY_USE.md", pattern) for pattern in paths))

    def test_fast_check_is_executable_and_keeps_core_regression_files(self) -> None:
        path = PROJECT_ROOT / "scripts/check-fast"
        mode = path.stat().st_mode
        content = path.read_text(encoding="utf-8")

        self.assertTrue(mode & stat.S_IXUSR)
        self.assertIn("tests/test_architecture.py", content)
        self.assertIn("tests/test_setup.py", content)
        self.assertIn("tests/test_maigret_username.py", content)
        self.assertIn("tests/test_sherlock_username.py", content)

    def test_fast_gate_keeps_engine_and_component_contract_regressions(self) -> None:
        content = (PROJECT_ROOT / "scripts/check-fast").read_text(encoding="utf-8")
        selected = re.findall(r"(?m)^    (tests/test_[a-z_]+\.py)(?: \\)?$", content)
        for path in (
            "tests/test_engine_contract.py",
            "tests/test_engine_records.py",
            "tests/test_components.py",
            "tests/test_component_pins.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(selected.count(path), 1)
                self.assertTrue((PROJECT_ROOT / path).is_file())


if __name__ == "__main__":
    unittest.main()
