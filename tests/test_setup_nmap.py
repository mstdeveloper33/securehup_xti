"""Host Nmap installer contract without installing a system package."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = PROJECT_ROOT / "scripts" / "setup-nmap"


class NmapSetupTests(unittest.TestCase):
    @staticmethod
    def _command(directory: Path, name: str, body: str) -> Path:
        path = directory / name
        path.write_text(f"#!/bin/sh\nset -eu\n{body}\n", encoding="utf-8")
        path.chmod(0o700)
        return path

    @staticmethod
    def _run(path: Path, *arguments: str, extra_environment=None):
        environment = os.environ.copy()
        environment["PATH"] = str(path)
        if extra_environment:
            environment.update(extra_environment)
        return subprocess.run(
            [str(INSTALLER), *arguments], cwd=PROJECT_ROOT, env=environment,
            capture_output=True, text=True, check=False,
        )

    def test_help_unknown_and_extra_arguments_never_inspect_or_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            commands = Path(temporary)
            marker = commands / "called"
            self._command(commands, "nmap", f"touch '{marker}'")
            help_result = self._run(commands, "--help")
            self.assertEqual(help_result.returncode, 0)
            self.assertIn("--check", help_result.stdout)
            unknown = self._run(commands, "--unsafe")
            self.assertEqual(unknown.returncode, 2)
            extra = self._run(commands, "--check", "extra")
            self.assertEqual(extra.returncode, 2)
            self.assertFalse(marker.exists())

    def test_check_is_read_only_and_existing_nmap_uses_only_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            commands = Path(temporary)
            missing = self._run(commands, "--check")
            self.assertEqual(missing.returncode, 1)
            self.assertIn("kurulu değil", missing.stderr)
            log = commands / "nmap-arguments"
            self._command(
                commands, "nmap",
                f"printf '%s\\n' \"$*\" > '{log}'\nprintf 'Nmap version 7.95\\n'",
            )
            ready = self._run(commands, "--check")
            self.assertEqual(ready.returncode, 0, ready.stderr)
            self.assertIn("Nmap version 7.95", ready.stdout)
            self.assertEqual(log.read_text(encoding="utf-8"), "--version\n")

    def test_macos_install_uses_only_brew_install_nmap(self):
        with tempfile.TemporaryDirectory() as temporary:
            commands = Path(temporary)
            log = commands / "brew-arguments"
            self._command(commands, "uname", "printf 'Darwin\\n'")
            self._command(commands, "brew", f"printf '%s\\n' \"$*\" > '{log}'")
            result = self._run(commands)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(log.read_text(encoding="utf-8"), "install nmap\n")

    def test_linux_non_root_install_has_fixed_sudo_package_arguments(self):
        with tempfile.TemporaryDirectory() as temporary:
            commands = Path(temporary)
            log = commands / "sudo-arguments"
            self._command(commands, "uname", "printf 'Linux\\n'")
            self._command(commands, "id", "printf '1000\\n'")
            self._command(commands, "apt-get", "exit 99")
            self._command(commands, "sudo", f"printf '%s\\n' \"$*\" > '{log}'")
            result = self._run(commands)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                log.read_text(encoding="utf-8"), "apt-get install -y nmap\n",
            )


if __name__ == "__main__":
    unittest.main()
