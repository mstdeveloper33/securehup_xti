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



if __name__ == "__main__":
    unittest.main()
