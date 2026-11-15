#!/usr/bin/env python3
"""Install the reviewed brand toolchain while retaining every previous environment."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from xti.adapters.installation_process import (
    ProcessCleanupError, SetupInterrupted, interruption_handlers,
    run_command as _run_command,
)
from xti.adapters.installation_transaction import DirectoryInstallation, identity
from xti.adapters.tool_installation import (
    BRAND_JOURNAL_NAME, ToolInstallationError,
    brand_installation_lock, brand_installation_pending,
)


PROJECT = Path(__file__).resolve().parents[1]
TRANSACTION = DirectoryInstallation(canonical_name=".venv", prefix=".venv",
                                    journal_name=BRAND_JOURNAL_NAME)
RECOVERY_COMMAND = "./scripts/setup-brand --recover"
VENV_TIMEOUT = 180
INSTALL_TIMEOUT = 900
VERIFY_TIMEOUT = 90


def run_command(arguments, *, cwd, lock_fd, timeout, environment=None, stage="araç komutu"):
    try:
        return _run_command(arguments, cwd=cwd, lock_fd=lock_fd, timeout=timeout,
                            environment=environment, recovery_command=RECOVERY_COMMAND)
    except (ProcessCleanupError, SetupInterrupted):
        # Their types control rollback and retry safety; never wrap these.
        raise
    except ToolInstallationError as error:
        # Static stage labels explain the failure without exposing child logs.
        raise ToolInstallationError(f"{stage}: {error}") from error


def stable_bootstrap(project):
    """The installer must never move the environment hosting its own interpreter."""
    for path in (Path(sys.prefix), Path(sys.executable).absolute()):
        for candidate in (path, path.resolve()):
            try:
                first = candidate.relative_to(project).parts[0]
            except (ValueError, IndexError):
                continue
            if first == ".venv" or first.startswith((".venv-backup", ".venv-failed", ".venv-candidate")):
                raise ToolInstallationError(
                    "Kurulum yönetilen .venv dışındaki Python ile başlatılmalı; ./scripts/setup-brand kullan."
                )
    if sys.version_info < (3, 11):
        raise ToolInstallationError("Python 3.11 veya daha yeni bir sürüm gerekiyor.")
    return Path(sys.executable).absolute()


def clean_environment(home, *, project=None):
    environment = dict(os.environ)
    for name in tuple(environment):
        if name.startswith(("GIT_", "PIP_")) or name in (
            "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE", "VIRTUAL_ENV",
        ):
            environment.pop(name, None)
    environment.update(
        HOME=str(home), XDG_CONFIG_HOME=str(home / "config"),
        XDG_CACHE_HOME=str(home / "cache"), XDG_DATA_HOME=str(home / "data"),
        PYTHONNOUSERSITE="1", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0", PIP_CONFIG_FILE=os.devnull,
        PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_INPUT="1",
    )
    if project is not None:
        environment["PYTHONPATH"] = str(project / "src")
    return environment


def verify(project, lock_fd):
    refuse_legacy(project)
    venv = project / ".venv"
    if identity(venv) is None:
        raise ToolInstallationError("Marka araç ortamı yok; önce ./scripts/setup-brand çalıştır.")
    python = venv / "bin/python"
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ToolInstallationError("Marka araç Python ortamı eksik veya çalıştırılamıyor.")
    with tempfile.TemporaryDirectory(prefix="xti-brand-check-") as temporary:
        environment = clean_environment(Path(temporary), project=project)
        run_command([python, "-m", "pip", "--isolated", "check"], cwd=temporary,
                    lock_fd=lock_fd, timeout=VERIFY_TIMEOUT, environment=environment,
                    stage="Bağımlılık kontrolü")
        result = run_command(
            [python, project / "scripts/verify_brand_install.py", "--prefix", venv,
             "--installation-lock-fd", str(lock_fd)], cwd=temporary,
            lock_fd=lock_fd, timeout=VERIFY_TIMEOUT, environment=environment,
            stage="Araç kimliği ve katalog doğrulaması",
        )
    if result:
        print(result)


def install(project, bootstrap, lock_fd):
    refuse_legacy(project)
    data = TRANSACTION.prepare(project)
    paths = TRANSACTION.paths(project, data["transaction"])
    venv = paths["canonical"]
    try:
        TRANSACTION.activate(project, data)
        with tempfile.TemporaryDirectory(prefix="xti-brand-install-") as temporary:
            environment = clean_environment(Path(temporary))
            run_command([bootstrap, "-m", "venv", venv], cwd=project,
                        lock_fd=lock_fd, timeout=VENV_TIMEOUT, environment=environment,
                        stage="Python ortamı oluşturma")
            python = venv / "bin/python"
            run_command(
                [python, "-m", "pip", "--isolated", "--disable-pip-version-check", "--no-input",
                 "--cache-dir", str(Path(temporary) / "pip-cache"), "install",
                 "--index-url", "https://pypi.org/simple",
                 "--constraint", project / "constraints/brand.txt", f"{project}[brand]"],
                cwd=project, lock_fd=lock_fd, timeout=INSTALL_TIMEOUT, environment=environment,
                stage="Paket kurulumu",
            )
        verify(project, lock_fd)
        refuse_legacy(project)
        TRANSACTION.commit(project, data)
    except ProcessCleanupError:
        # A living child retains the lock; do not move its writable directory.
        raise
    except BaseException:
        refuse_legacy(project)
        if os.path.lexists(project / BRAND_JOURNAL_NAME):
            TRANSACTION.recover(project)
        raise
    if data["old"] is not None:
        print(f"Önceki marka araç ortamı korundu: {paths['backup']}")


def legacy_error():
    return ToolInstallationError(
        "Eski kurulumdan kalan .venv-install.lock, .venv-backup veya .xti-installing bulundu. "
        "Kimlik günlüğü olmadığından otomatik silme/geri dönüş yapılmadı; elle inceleme gerekiyor."
    )


def refuse_legacy(project):
    if any(os.path.lexists(path) for path in (
        project / ".venv-install.lock", project / ".venv-backup",
        project / ".venv/.xti-installing",
    )):
        raise legacy_error()


def main(arguments=None):
    parser = argparse.ArgumentParser(description="İncelenen Maigret ve Sherlock ortamını kur veya kurtar.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Mevcut ortamı indirmeden doğrula; yeniden kurma.")
    mode.add_argument("--force", action="store_true", help="Önceki ortamı koruyarak aynı sabit sürümleri yeniden kur.")
    mode.add_argument("--recover", action="store_true", help="Yalnız yarım işlemi kurtar; indirme veya kurma.")
    options = parser.parse_args(arguments)
    try:
        with interruption_handlers():
            bootstrap = stable_bootstrap(PROJECT)
            # Keep relative PATH entries anchored to the caller's directory.
            os.environ["PATH"] = os.pathsep.join(
                str(Path(item or os.curdir).resolve())
                for item in os.environ.get("PATH", os.defpath).split(os.pathsep)
            )
            git = shutil.which("git")
            with brand_installation_lock(PROJECT, exclusive=True) as lock_fd:
                os.chdir(PROJECT)
                refuse_legacy(PROJECT)
                if options.recover:
                    if os.path.lexists(PROJECT / BRAND_JOURNAL_NAME):
                        TRANSACTION.recover(PROJECT)
                    elif brand_installation_pending(PROJECT):
                        raise legacy_error()
                    else:
                        print("Kurtarılacak yarım marka kurulumu yok.")
                    return 0
                if os.path.lexists(PROJECT / BRAND_JOURNAL_NAME):
                    raise ToolInstallationError("Yarım marka kurulumu var; önce ./scripts/setup-brand --recover çalıştır.")
                if brand_installation_pending(PROJECT):
                    raise legacy_error()
                existing = identity(PROJECT / ".venv")
                if existing is not None and not options.force:
                    try:
                        verify(PROJECT, lock_fd)
                    except (SetupInterrupted, ProcessCleanupError):
                        raise
                    except ToolInstallationError:
                        if options.check:
                            raise
                    else:
                        print("Marka araç kurulumu zaten güncel; indirme yapılmadı.")
                        return 0
                elif options.check:
                    raise ToolInstallationError("Marka araç ortamı yok; önce ./scripts/setup-brand çalıştır.")
                if git is None:
                    raise ToolInstallationError("Sabit Git commit'lerinden kurulum için git gerekiyor.")
                print("Maigret ve Sherlock incelenmiş sürümlerden kuruluyor...", flush=True)
                install(PROJECT, bootstrap, lock_fd)
                print("Maigret ve Sherlock doğrulanarak kuruldu.")
                return 0
    except (ToolInstallationError, OSError, UnicodeError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        if isinstance(error, subprocess.TimeoutExpired):
            explanation = "Araç süre sınırını aştı; süreçler durduruldu."
        elif isinstance(error, KeyboardInterrupt):
            explanation = "Kurulum kullanıcı tarafından kesildi."
        else:
            explanation = str(error)
        print("Marka araç kurulumu tamamlanamadı: " + explanation, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
