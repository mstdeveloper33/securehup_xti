"""Exercise the optional installer with isolated, network-free command doubles."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMIT = "6790b147f52309e4eee22ed941db1d285ab2ec23"
UV_VARIABLES = ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_PYTHON_BIN_DIR")


class HarvesterSetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="xti-harvester-setup-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "project with spaces"
        self.scripts = self.root / "scripts"
        self.scripts.mkdir(parents=True)
        self.installer = self.scripts / "setup-harvester"
        self.installer.write_bytes((PROJECT_ROOT / "scripts/setup-harvester").read_bytes())
        self.installer.chmod(0o700)
        self.bin = Path(temporary.name).resolve() / "fake-bin"
        self.bin.mkdir()
        for name in ("dirname", "mkdir"):
            executable = shutil.which(name)
            self.assertIsNotNone(executable)
            (self.bin / name).symlink_to(executable)
        self.git_log = self.root / "git-calls.jsonl"
        self.uv_log = self.root / "uv-call.json"
        self.environment = {
            key: value for key, value in os.environ.items()
            if key not in UV_VARIABLES
        }
        # A closed PATH cannot discover or execute the machine's real git/uv.
        self.environment["PATH"] = str(self.bin)
        self.environment["XTI_TEST_GIT_LOG"] = str(self.git_log)
        self.environment["XTI_TEST_UV_LOG"] = str(self.uv_log)
        self.write_executable(self.bin / "git", '''
import json
import os
from pathlib import Path
import sys
args = sys.argv[1:]
with Path(os.environ["XTI_TEST_GIT_LOG"]).open("a") as target:
    target.write(json.dumps(args) + "\\n")
if args[0] == "clone":
    (Path(args[-1]) / ".git").mkdir(parents=True)
elif "rev-parse" in args:
    print("6790b147f52309e4eee22ed941db1d285ab2ec23")
elif "remote" in args:
    print("https://github.com/laramies/theHarvester.git")
''')

    def write_executable(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
        path.chmod(0o700)

    def add_uv(self, path, label):
        self.write_executable(path, f'''
import json
import os
from pathlib import Path
import sys
data = {{
    "label": {label!r}, "args": sys.argv[1:], "cwd": str(Path.cwd()),
    "environment": {{name: os.environ.get(name) for name in {UV_VARIABLES!r}}},
}}
Path(os.environ["XTI_TEST_UV_LOG"]).write_text(json.dumps(data))
executable = Path.cwd() / ".venv/bin/theHarvester"
executable.parent.mkdir(parents=True, exist_ok=True)
executable.write_text("#!/bin/sh\\nexit 0\\n")
executable.chmod(0o700)
''')

    def run_installer(self):
        return subprocess.run(
            [str(self.installer)], cwd=self.root, env=self.environment,
            capture_output=True, text=True, timeout=10, check=False,
        )

    def assert_success(self, result, label):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"theHarvester hazır: {COMMIT}", result.stdout)
        call = json.loads(self.uv_log.read_text())
        self.assertEqual(call["label"], label)
        self.assertEqual(call["args"], ["sync", "--frozen", "--no-dev"])
        self.assertEqual(call["cwd"], str(self.root / ".tools/theharvester"))
        return call

    def test_project_local_uv_is_used_without_changing_path(self):
        self.add_uv(self.root / ".tools/uv/bin/uv", "project-local")
        call = self.assert_success(self.run_installer(), "project-local")
        self.assertEqual(call["environment"], {
            "UV_CACHE_DIR": str(self.root / ".tools/uv-cache"),
            "UV_PYTHON_INSTALL_DIR": str(self.root / ".tools/python"),
            "UV_PYTHON_BIN_DIR": str(self.root / ".tools/python-bin"),
        })

    def test_path_uv_has_priority_over_project_local_uv(self):
        self.add_uv(self.root / ".tools/uv/bin/uv", "project-local")
        self.add_uv(self.bin / "uv", "path")
        self.assert_success(self.run_installer(), "path")

    def test_relative_path_uv_survives_checkout_directory_change(self):
        self.add_uv(self.bin / "uv", "relative-path")
        self.environment["PATH"] = "../fake-bin"
        self.assert_success(self.run_installer(), "relative-path")

    def test_explicit_uv_directories_are_preserved(self):
        self.add_uv(self.bin / "uv", "path")
        overrides = {
            name: str(self.root / "operator choice" / name.lower())
            for name in UV_VARIABLES
        }
        self.environment.update(overrides)
        call = self.assert_success(self.run_installer(), "path")
        self.assertEqual(call["environment"], overrides)

    def test_missing_uv_stops_before_clone_or_tool_directory_creation(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertIn("uv aracı gerekiyor", result.stderr)
        self.assertIn(".tools/uv/bin/uv", result.stderr)
        self.assertFalse((self.root / ".tools").exists())
        self.assertFalse(self.git_log.exists())
        self.assertFalse(self.uv_log.exists())

    def test_non_executable_local_uv_is_rejected_without_mutation(self):
        path = self.root / ".tools/uv/bin/uv"
        self.add_uv(path, "unusable")
        path.chmod(0o600)
        before = path.read_bytes()
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.root / ".tools/theharvester").exists())
        self.assertFalse(self.git_log.exists())
        self.assertFalse(self.uv_log.exists())
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
