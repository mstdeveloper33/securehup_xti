"""Select a runtime only while its managed environment is protected."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

from xti.adapters.tool_installation import (
    ToolInstallationError, brand_installation_lock, brand_installation_pending,
)


PROJECT = Path(__file__).resolve().parents[1]


def managed_path(path: Path, project: Path = PROJECT) -> bool:
    for value in (path.absolute(), path.resolve()):
        try:
            first = value.relative_to(project.resolve()).parts[0]
        except (ValueError, IndexError):
            continue
        if first == ".venv" or first.startswith((".venv-backup", ".venv-candidate", ".venv-failed")):
            return True
    return False


def supported(executable: str, descriptor: int, *, isolated: bool = False) -> bool:
    try:
        result = subprocess.run(
            [executable, *(["-I", "-S"] if isolated else []), "-c",
             "import sys; raise SystemExit(sys.version_info < (3, 11))"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=10, pass_fds=(descriptor,), check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def main() -> int:
    try:
        with brand_installation_lock(PROJECT, exclusive=False) as descriptor:
            venv = PROJECT / ".venv"
            invalid = venv.is_symlink() or (os.path.lexists(venv) and not venv.is_dir())
            pending = brand_installation_pending(PROJECT) or invalid
            caller_path = os.environ.pop("XTI_RUNTIME_PYTHONPATH", "")
            os.environ["PYTHONPATH"] = str(PROJECT / "src")
            if caller_path and not pending:
                os.environ["PYTHONPATH"] += os.pathsep + caller_path
            override = os.environ.get("XTI_PYTHON")
            if override:
                selected = shutil.which(override)
                if selected is None:
                    raise ToolInstallationError("XTI_PYTHON çalıştırıcısı bulunamadı.")
                selected = str(Path(selected).absolute())
                if pending and managed_path(Path(selected)):
                    if invalid:
                        raise ToolInstallationError("Proje .venv ortamı gerçek bir dizin olmalı; değiştirilmedi.")
                    raise ToolInstallationError(
                        "Marka ortamı kurtarma bekliyor; ./scripts/setup-brand --recover çalıştır."
                    )
                if not supported(selected, descriptor, isolated=pending):
                    raise ToolInstallationError("XTI_PYTHON, Python 3.11 veya daha yeni bir sürümü göstermeli.")
            else:
                candidate = PROJECT / ".venv/bin/python"
                selected = sys.executable
                if not pending and candidate.is_file() and os.access(candidate, os.X_OK):
                    if supported(str(candidate), descriptor):
                        selected = str(candidate)
            # Exec keeps the same open file description. Do not unlock before it.
            os.set_inheritable(descriptor, True)
            os.execv(selected, [selected, *(["-S"] if pending else []), *sys.argv[1:]])
    except (ToolInstallationError, OSError) as error:
        print("XTI başlatılamadı: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
