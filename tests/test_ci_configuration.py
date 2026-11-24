from pathlib import Path
from fnmatch import fnmatchcase
import importlib.util
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def linux_acceptance():
    spec = importlib.util.spec_from_file_location(
        "linux_acceptance", PROJECT_ROOT / "scripts/check-linux-install.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def brand_acceptance():
    spec = importlib.util.spec_from_file_location(
        "brand_acceptance", PROJECT_ROOT / "scripts/check-linux-brand-install.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CiConfigurationTests(unittest.TestCase):
    def test_job_history_acceptance_covers_queue_and_conflict_changes_on_both_events(self):
        workflow = (PROJECT_ROOT / '.github/workflows/job-history.yml').read_text()
        critical = ('pyproject.toml', 'src/xti/adapters/engine_job_catalog.py',
                    'src/xti/adapters/sqlite_engine_jobs.py', 'src/xti/domain/source_conflicts.py',
                    'src/xti/interfaces/platform_engine.py', 'scripts/check-job-history.py',
                    'tests/test_job_history.py', 'tests/test_job_history_conflict_platform.py',
                    'tests/test_source_conflicts.py', 'tests/test_ci_configuration.py')
        for event in ('push', 'pull_request'):
            block = re.search(rf'(?ms)^  {event}:\n(.*?)(?=^  [a-z_]+:|\Z)', workflow)
            self.assertIsNotNone(block)
            paths = re.findall(r'^      - "([^"\n]+)"$', block.group(1), re.MULTILINE)
            for path in critical:
                with self.subTest(event=event, path=path):
                    self.assertTrue(any(fnmatchcase(path, pattern) for pattern in paths))
            self.assertFalse(any(fnmatchcase('docs/DAILY_USE.md', pattern) for pattern in paths))
        self.assertIn('fetch-depth: 0', workflow)  # Actual old producer must be available.
        self.assertIn('persist-credentials: false', workflow)
        self.assertIn('python: ["3.11", "3.13"]', workflow)
        self.assertIn('scripts/check-job-history.py --output', workflow)
        for module in ('test_job_history', 'test_source_conflicts', 'test_job_history_conflict_platform'):
            self.assertIn('tests.' + module, workflow)
            self.assertIn('tests/' + module + '.py', (PROJECT_ROOT / 'scripts/check-fast').read_text())

    def test_every_push_runs_only_the_fast_offline_gate(self) -> None:
        workflow = (PROJECT_ROOT / ".github/workflows/check.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("name: XTI quick checks", workflow)
        self.assertIn("run: ./scripts/check-fast", workflow)
        self.assertNotIn("run: ./scripts/check\n", workflow)
        self.assertNotIn("setup-brand --check", workflow)
        self.assertIn('shard: [1, 2]', workflow)
        self.assertIn('XTI_CHECK_SHARD: ${{ matrix.shard }}/2', workflow)
        self.assertIn('fail-fast: false', workflow)

    def test_fast_gate_shards_preserve_the_complete_existing_module_list(self):
        spec = importlib.util.spec_from_file_location('check_test_shard', PROJECT_ROOT / 'scripts/check-test-shard.py')
        runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
        modules = re.findall(r'tests/[a-z0-9_]+\.py', (PROJECT_ROOT / 'scripts/check-fast').read_text())
        self.assertGreater(len(modules), 20)
        first = runner.select_modules(modules, '1/2')
        second = runner.select_modules(modules, '2/2')
        self.assertFalse(set(first) & set(second))
        self.assertEqual(sorted(first + second), sorted(modules))
        self.assertEqual(runner.select_modules(modules, None), modules)
        for shard in ('0/2', '3/2', '1/0', 'all'):
            with self.subTest(shard=shard), self.assertRaises(ValueError):
                runner.select_modules(modules, shard)
        with self.assertRaises(ValueError): runner.select_modules(modules + modules[:1], None)
        with self.assertRaises(ValueError): runner.select_modules([], None)

    def test_brand_install_is_path_scoped_and_rechecks_without_download(self) -> None:
        workflow = (
            PROJECT_ROOT / ".github/workflows/brand-install.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('      - "constraints/brand.txt"', workflow)
        self.assertIn('      - "scripts/setup-brand"', workflow)
        self.assertIn("run: ./scripts/bootstrap-python scripts/check-linux-brand-install.py", workflow)
        self.assertIn("timeout-minutes: 20", workflow)
        self.assertIn("GITHUB_STEP_SUMMARY", workflow)
        self.assertIn("tests/test_setup_brand.py", workflow)
        self.assertIn("tests/test_brand_runtime.py", workflow)
        self.assertIn("XTI_BROWSER_SANDBOX_MODE: trusted_ci_fixture", workflow)
        self.assertIn("python -m playwright install-deps chromium", workflow)
        protection = (PROJECT_ROOT / ".github/workflows/brand-protection.yml").read_text(encoding="utf-8")
        self.assertIn("XTI_BROWSER_SANDBOX_MODE: trusted_ci_fixture", protection)

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
            "scripts/bootstrap-python", "scripts/run_python.py", "scripts/setup_brand.py",
            "scripts/check-linux-brand-install.py", "scripts/check-linux-install.py",
            "src/xti/adapters/tool_installation.py",
            "src/xti/adapters/installation_process.py", "src/xti/adapters/installation_transaction.py",
            "src/xti/adapters/source_readiness.py",
            "tests/test_setup_brand.py", "tests/test_brand_runtime.py", "tests/test_ci_configuration.py",
            "tests/test_component_pins.py", "tests/test_maigret_username.py", "tests/test_sherlock_username.py",
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
            "tests/test_social_discovery.py",
            "tests/test_public_profile_pages.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(selected.count(path), 1)
                self.assertTrue((PROJECT_ROOT / path).is_file())

    def test_linux_acceptance_tracks_installer_and_shared_runtime_changes(self) -> None:
        workflow = (PROJECT_ROOT / ".github/workflows/harvester-install.yml").read_text(encoding="utf-8")
        critical_paths = (
            ".github/workflows/harvester-install.yml", "setup", "xti", "scripts/python",
            "scripts/check-linux-install.py", "scripts/setup-harvester", "scripts/setup_harvester.py",
            "src/xti/domain/component_pins.py", "src/xti/adapters/tool_installation.py",
            "src/xti/adapters/theharvester_archive.py", "src/xti/adapters/source_readiness.py",
            "tests/test_setup_harvester.py", "tests/test_tool_installation.py",
            "tests/test_component_pins.py", "tests/test_theharvester_archive.py",
            "tests/test_theharvester_archive_repeats.py", "tests/test_source_readiness_adapter.py",
            "tests/test_ci_configuration.py",
            "scripts/bootstrap-python", "scripts/run_python.py",
            "src/xti/adapters/installation_process.py", "src/xti/adapters/installation_transaction.py",
        )
        for event in ("push", "pull_request"):
            block = re.search(rf"(?ms)^  {event}:\n(.*?)(?=^  [a-z_]+:|\Z)", workflow)
            self.assertIsNotNone(block)
            paths = re.findall(r'^      - "([^"\n]+)"$', block.group(1), re.MULTILINE)
            for path in critical_paths:
                with self.subTest(event=event, path=path):
                    self.assertTrue(any(fnmatchcase(path, pattern) for pattern in paths))
            self.assertFalse(any(fnmatchcase("docs/DAILY_USE.md", pattern) for pattern in paths))
        self.assertIn("contents: read", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertIn("timeout-minutes: 20", workflow)
        self.assertIn("cancel-in-progress: true", workflow)
        self.assertIn("uv==0.13.8", workflow)
        self.assertIn('python-version: "3.11"', workflow)
        self.assertIn("run: ./scripts/python scripts/check-linux-install.py", workflow)
        self.assertIn("GITHUB_STEP_SUMMARY", workflow)
        self.assertNotIn("setup-brand", workflow)
        for path in critical_paths:
            if path.startswith("tests/"):
                self.assertIn(path, workflow.split("steps:", 1)[1])

    def test_linux_acceptance_refuses_wrong_host_and_existing_tools_without_mutation(self) -> None:
        helper = linux_acceptance()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(helper.sys, "platform", "darwin"):
                with self.assertRaisesRegex(RuntimeError, "real Linux"):
                    helper.fresh_linux_checkout(root)
            self.assertEqual(list(root.iterdir()), [])
            with patch.object(helper.sys, "platform", "linux"):
                helper.fresh_linux_checkout(root)
                (root / ".tools").symlink_to(root / "missing")
                with self.assertRaisesRegex(RuntimeError, "disposable checkout"):
                    helper.fresh_linux_checkout(root)
                self.assertTrue((root / ".tools").is_symlink())

    def test_linux_offline_recheck_guards_refuse_download_commands(self) -> None:
        helper = linux_acceptance()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            git = fake_bin / "git"
            git.write_text(f"#!{sys.executable}\nprint('local-metadata')\n", encoding="utf-8")
            git.chmod(0o700)
            environment = helper.offline_tool_environment(root / "guards", dict(os.environ, PATH=str(fake_bin)))
            result = subprocess.run([str(root / "guards/git"), "-C", str(root), "rev-parse", "HEAD"],
                                    env=environment, text=True, capture_output=True, timeout=10)
            self.assertEqual((result.returncode, result.stdout.strip()), (0, "local-metadata"))
            for arguments in (("git", "clone", "https://example.invalid/repo"),
                              ("git", "-C", str(root), "fetch", "origin"), ("uv", "sync")):
                result = subprocess.run([str(root / "guards" / arguments[0]), *arguments[1:]],
                                        env=environment, text=True, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("blocked", result.stderr)

    def test_linux_local_smoke_preserves_bytes_and_restores_real_engine_records(self) -> None:
        helper = linux_acceptance()
        brand = brand_acceptance()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            environment = dict(os.environ, XTI_DATA_DIR=str(data), XTI_PYTHON=sys.executable)
            helper.run(["./setup", "--core-only"], environment)
            helper.run(["./xti", "assets", "add", "example.com"], environment)
            marker = data / "evidence.bin"
            marker.write_bytes(b"original")
            before = helper.snapshot(data)
            helper.local_asset(environment)
            helper.run(["./setup", "--core-only"], environment)
            brand.local_round_trip(environment, root)
            self.assertEqual(helper.snapshot(data), before)
            marker.write_bytes(b"modified")
            self.assertNotEqual(helper.snapshot(data), before)

    def test_brand_acceptance_refuses_existing_state_but_preserves_valid_persistent_lock(self) -> None:
        helper = brand_acceptance()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(helper.sys, "platform", "darwin"):
                with self.assertRaisesRegex(RuntimeError, "real Linux"):
                    helper.fresh_brand_checkout(root)
            self.assertEqual(list(root.iterdir()), [])
            with patch.object(helper.sys, "platform", "linux"):
                helper.fresh_brand_checkout(root)
                lock = root / ".brand-install.lock"
                lock.write_bytes(b"preserved lock contents")
                identity = lock.stat().st_ino
                helper.fresh_brand_checkout(root)
                self.assertEqual(lock.stat().st_ino, identity)
                self.assertEqual(lock.read_bytes(), b"preserved lock contents")
                alias = root / "lock-alias"
                os.link(lock, alias)
                with self.assertRaisesRegex(RuntimeError, "single-link regular"):
                    helper.fresh_brand_checkout(root)
                alias.unlink()
                for name in (".venv", ".venv-backup", ".venv-install.lock", ".brand-install.json"):
                    with self.subTest(name=name):
                        path = root / name
                        path.symlink_to(root / "missing")
                        with self.assertRaisesRegex(RuntimeError, "disposable checkout"):
                            helper.fresh_brand_checkout(root)
                        self.assertTrue(path.is_symlink())
                        path.unlink()
                lock.unlink()
                lock.symlink_to(root / "missing")
                with self.assertRaisesRegex(RuntimeError, "single-link regular"):
                    helper.fresh_brand_checkout(root)

    def test_brand_environment_snapshot_detects_changed_bytes_mode_identity_and_links(self) -> None:
        helper = brand_acceptance()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            venv = root / ".venv"
            venv.mkdir()
            executable = venv / "launcher"
            executable.write_bytes(b"original")
            outside = root / "outside"
            outside.write_bytes(b"not followed")
            link = venv / "python"
            link.symlink_to(outside)
            original = helper.environment_snapshot(venv)
            outside.write_bytes(b"still not followed")
            self.assertEqual(helper.environment_snapshot(venv), original)
            link.unlink()
            link.symlink_to(root / "different-target")
            self.assertNotEqual(helper.environment_snapshot(venv), original)
            link.unlink()
            link.symlink_to(outside)
            executable.write_bytes(b"modified")
            self.assertNotEqual(helper.environment_snapshot(venv), original)
            executable.write_bytes(b"original")
            executable.chmod(0o700)
            self.assertNotEqual(helper.environment_snapshot(venv), original)
            alias = root / "alias"
            alias.symlink_to(venv, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "real directory"):
                helper.environment_snapshot(alias)
            saved = root / "saved"
            venv.rename(saved)
            venv.mkdir()
            self.assertNotEqual(helper.environment_snapshot(venv)[:2], original[:2])

    def test_brand_repeat_guard_blocks_downloader_executables_without_touching_environment(self) -> None:
        helper = brand_acceptance()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = helper.repeat_environment(root / "guards", dict(os.environ))
            for name in ("git", "pip", "pip3"):
                result = subprocess.run([str(root / "guards" / name), "install"], env=environment,
                                        text=True, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("blocked a downloader", result.stderr)
            self.assertEqual(sorted(path.name for path in root.iterdir()), ["guards"])


if __name__ == "__main__":
    unittest.main()
