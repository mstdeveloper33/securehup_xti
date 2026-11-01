import os
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SetupScriptTests(unittest.TestCase):
    def test_fresh_clone_setup_initializes_local_storage_and_is_repeatable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            environment = os.environ.copy()
            environment["XTI_DATA_DIR"] = str(data_dir)

            first = subprocess.run(
                [str(PROJECT_ROOT / "setup"), "--core-only"],
                cwd=temp_dir,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("XTI kullanıma hazır", first.stdout)
            self.assertIn("Marka araçları: atlandı", first.stdout)
            self.assertTrue((data_dir / "xti.db").is_file())

            second = subprocess.run(
                [str(PROJECT_ROOT / "setup"), "--core-only"],
                cwd=temp_dir,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("XTI kullanıma hazır", second.stdout)

            doctor = subprocess.run(
                [str(PROJECT_ROOT / "xti"), "doctor"],
                cwd=temp_dir,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            self.assertIn("Kayıt alanı sağlıklı", doctor.stdout)

    def test_default_setup_runs_brand_install_before_core_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scripts = root / "scripts"
            scripts.mkdir()
            setup = root / "setup"
            setup.write_bytes((PROJECT_ROOT / "setup").read_bytes())
            setup.chmod(0o700)
            (scripts / "setup-brand").write_text(
                "#!/bin/sh\nset -eu\nprintf 'brand\\n' >> \"$XTI_ORDER\"\n",
                encoding="utf-8",
            )
            (scripts / "setup-brand").chmod(0o700)
            (root / "xti").write_text(
                "#!/bin/sh\nset -eu\nprintf 'core:%s\\n' \"$1\" >> \"$XTI_ORDER\"\n",
                encoding="utf-8",
            )
            (root / "xti").chmod(0o700)
            order = root / "order.txt"
            environment = os.environ.copy()
            environment["XTI_ORDER"] = str(order)

            result = subprocess.run(
                [str(setup)],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(order.read_text().splitlines(), ["brand", "core:init"])
            self.assertIn("Maigret ve Sherlock: doğrulandı", result.stdout)

    def test_failed_brand_reinstall_restores_previous_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scripts = root / "scripts"
            scripts.mkdir()
            setup_brand = scripts / "setup-brand"
            setup_brand.write_bytes((PROJECT_ROOT / "scripts/setup-brand").read_bytes())
            setup_brand.chmod(0o700)
            previous = root / ".venv"
            previous.mkdir()
            (previous / "sentinel").write_text("previous", encoding="utf-8")

            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            fake_python = fake_bin / "python3.14"
            fake_python.write_text(
                "#!/bin/sh\n"
                "if [ \"${1:-}\" = '-c' ]; then exit 0; fi\n"
                "if [ \"${1:-}\" = '-m' ] && [ \"${2:-}\" = 'venv' ]; then\n"
                "  mkdir -p \"$3/bin\"\n"
                "  cp \"$0\" \"$3/bin/python\"\n"
                "  chmod +x \"$3/bin/python\"\n"
                "  exit 0\n"
                "fi\n"
                "if [ \"${1:-}\" = '-m' ] && [ \"${2:-}\" = 'pip' ]; then exit 7; fi\n"
                "exit 8\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o700)
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

            result = subprocess.run(
                [str(setup_brand), "--force"],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((root / ".venv/sentinel").read_text(), "previous")
            self.assertFalse((root / ".venv-backup").exists())
            self.assertFalse((root / ".venv-install.lock").exists())


if __name__ == "__main__":
    unittest.main()
