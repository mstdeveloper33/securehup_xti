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
                [str(PROJECT_ROOT / "setup")],
                cwd=temp_dir,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("XTI kullanıma hazır", first.stdout)
            self.assertTrue((data_dir / "xti.db").is_file())

            second = subprocess.run(
                [str(PROJECT_ROOT / "setup")],
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


if __name__ == "__main__":
    unittest.main()
