#!/usr/bin/env python3
"""Install the reviewed Harvester checkout without losing an earlier installation.

The venv is built at its final location because entry-point shebangs are absolute.
A durable, identity-checked journal covers every rename. Old checkouts and failed
candidates are retained; recovery never recursively deletes user content.
"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from xti.adapters.installation_process import (
    SetupInterrupted, ProcessCleanupError, interruption_handlers,
    terminate_group as _terminate_group, run_command as _run_command,
)
from xti.adapters.installation_transaction import (
    DirectoryInstallation, identity, sync_directory, move_directory,
)

from xti.adapters.tool_installation import (
    JOURNAL_NAME,
    ToolInstallationError,
    pending_installation,
    tool_installation_lock,
)
from xti.domain.component_pins import HARVESTER_PIN


PROJECT = Path(__file__).resolve().parents[1]
GIT_TIMEOUT = 180
SYNC_TIMEOUT = 900
SMOKE_TIMEOUT = 60
OUTPUT_LIMIT = 1024 * 1024

TRANSACTION = DirectoryInstallation(canonical_name="theharvester", prefix=".theharvester",
                                    journal_name=JOURNAL_NAME)
RECOVERY_COMMAND = "./scripts/setup-harvester --recover"
journal_paths = TRANSACTION.paths
load_journal = TRANSACTION.load
write_journal = TRANSACTION.write
clear_journal = TRANSACTION.clear
recover = TRANSACTION.recover


def terminate_group(process):
    return _terminate_group(process, recovery_command=RECOVERY_COMMAND)


def run_command(arguments, *, cwd, lock_fd, timeout, environment=None):
    return _run_command(arguments, cwd=cwd, lock_fd=lock_fd, timeout=timeout,
                        environment=environment, output_limit=OUTPUT_LIMIT,
                        recovery_command=RECOVERY_COMMAND)


def executable_path(name):
    found = shutil.which(name)
    return Path(found).absolute() if found else None


def find_uv(parent, *, search_path=True):
    executable = executable_path("uv") if search_path else None
    if executable is not None:
        return executable
    local = parent / "uv/bin/uv"
    if local.is_file() and os.access(local, os.X_OK):
        return local
    raise ToolInstallationError(
        "theHarvester ayrı Python 3.14 ortamı için ücretsiz uv aracı gerekiyor. "
        "uv PATH içinde veya .tools/uv/bin/uv konumunda bulunmalı."
    )


def git_environment():
    environment = dict(os.environ)
    for name in tuple(environment):
        if name.startswith("GIT_"):
            del environment[name]
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    return environment


def git_command(git, checkout, arguments, lock_fd):
    return run_command(
        [git, "-C", checkout, *arguments], cwd=checkout.parent, lock_fd=lock_fd,
        timeout=GIT_TIMEOUT, environment=git_environment(),
    )


def validate_checkout(git, checkout, lock_fd):
    identity(checkout)
    if identity(checkout / ".git") is None:
        raise ToolInstallationError("Mevcut theHarvester dizini doğrulanabilir git deposu değil; değiştirilmedi.")
    origin = git_command(git, checkout, ["remote", "get-url", "origin"], lock_fd)
    if origin not in (HARVESTER_PIN.repository, HARVESTER_PIN.repository.removesuffix(".git")):
        raise ToolInstallationError("Mevcut theHarvester origin adresi beklenen upstream değil; değiştirilmedi.")
    changes = git_command(git, checkout, ["status", "--porcelain", "--untracked-files=no"], lock_fd)
    if changes:
        raise ToolInstallationError("Mevcut theHarvester deposunda yerel değişiklik var; üzerine yazılmadı.")


def verify(git, checkout, lock_fd):
    actual = git_command(git, checkout, ["rev-parse", "HEAD"], lock_fd)
    if actual != HARVESTER_PIN.commit:
        raise ToolInstallationError("theHarvester commit doğrulaması başarısız.")
    executable = checkout / ".venv/bin/theHarvester"
    if executable.is_symlink() or not executable.is_file() or not os.access(executable, os.X_OK):
        raise ToolInstallationError("theHarvester çalıştırıcısı eksik veya geçersiz.")
    if not executable.resolve().is_relative_to(checkout.resolve()):
        raise ToolInstallationError("theHarvester çalıştırıcısı araç dizini dışında.")
    interpreter = executable.parent / "python"
    if not interpreter.is_file() or not os.access(interpreter, os.X_OK):
        raise ToolInstallationError("theHarvester Python ortamı eksik.")
    environment = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
        environment.pop(name, None)
    environment["PYTHONNOUSERSITE"] = "1"
    with tempfile.TemporaryDirectory(prefix="xti-harvester-check-") as temporary:
        home = Path(temporary)
        environment.update(HOME=str(home), XDG_CONFIG_HOME=str(home / "config"),
                           XDG_CACHE_HOME=str(home / "cache"), XDG_DATA_HOME=str(home / "data"),
                           THEHARVESTER_RUN_DB=str(home / "harvester.sqlite3"))
        run_command([executable, "--help"], cwd=checkout.parent, lock_fd=lock_fd,
                    timeout=SMOKE_TIMEOUT, environment=environment)


def install(parent, git, uv, lock_fd):
    checkout = parent / "theharvester"
    data = TRANSACTION.prepare(parent)
    paths = TRANSACTION.paths(parent, data["transaction"])
    try:
        TRANSACTION.activate(parent, data)
        run_command(
            [git, "clone", "--filter=blob:none", "--no-checkout", HARVESTER_PIN.repository, checkout],
            cwd=parent, lock_fd=lock_fd, timeout=GIT_TIMEOUT, environment=git_environment(),
        )
        git_command(git, checkout, ["fetch", "--depth", "1", "origin", HARVESTER_PIN.commit], lock_fd)
        git_command(git, checkout, ["checkout", "--detach", HARVESTER_PIN.commit], lock_fd)
        environment = dict(os.environ)
        for name in ("UV_PROJECT", "UV_WORKING_DIR", "UV_ACTIVE", "VIRTUAL_ENV"):
            environment.pop(name, None)
        environment["UV_PROJECT_ENVIRONMENT"] = str(checkout / ".venv")
        for name, suffix in (("UV_CACHE_DIR", "uv-cache"), ("UV_PYTHON_INSTALL_DIR", "python"),
                             ("UV_PYTHON_BIN_DIR", "python-bin")):
            environment.setdefault(name, str(parent / suffix))
        run_command([uv, "sync", "--frozen", "--no-dev", "--no-editable", "--project", checkout], cwd=checkout,
                    lock_fd=lock_fd, timeout=SYNC_TIMEOUT, environment=environment)
        validate_checkout(git, checkout, lock_fd)
        verify(git, checkout, lock_fd)
        TRANSACTION.commit(parent, data)
    except ProcessCleanupError:
        # The journal and inherited lock keep runtime/recovery out until the
        # remaining child has actually stopped. Never rename its writable cwd.
        raise
    except BaseException:
        # Even if commit was written, recovery knows it must retain the new venv.
        if pending_installation(parent):
            recover(parent)
        raise
    if data["old"] is not None:
        print(f"Önceki kurulum korundu: {paths['backup']}")


def main(arguments=None):
    parser = argparse.ArgumentParser(description="Sabit theHarvester sürümünü güvenli kur veya doğrula.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Ağ kullanmadan commit ve --help doğrula; kurma.")
    mode.add_argument("--force", action="store_true", help="Önceki kurulumu koruyarak yeniden kur.")
    mode.add_argument("--recover", action="store_true", help="Yalnız yarım kalan işlemi kurtar; indirme veya kurma.")
    options = parser.parse_args(arguments)
    parent = PROJECT / ".tools"
    try:
        with interruption_handlers():
            if identity(parent) is None:
                if options.recover:
                    print("Kurtarılacak yarım kurulum yok.")
                    return 0
                if options.check:
                    raise ToolInstallationError("theHarvester kurulumu yok.")
                git = executable_path("git")
                if git is None:
                    raise ToolInstallationError("theHarvester kurulumu için git gerekiyor.")
                uv = find_uv(parent)
                parent.mkdir(mode=0o700)
            else:
                git = executable_path("git")
                uv = None
            with tool_installation_lock(parent, exclusive=True) as lock_fd:
                # The caller may have launched us from inside the old checkout.
                # Resolve relative executable paths before leaving that cwd.
                if uv is None and not options.recover:
                    uv = executable_path("uv")
                os.chdir(parent)
                if options.recover:
                    if pending_installation(parent):
                        recover(parent)
                    else:
                        print("Kurtarılacak yarım kurulum yok.")
                    return 0
                if pending_installation(parent):
                    raise ToolInstallationError("Yarım kurulum var; önce ./scripts/setup-harvester --recover çalıştır.")
                if git is None:
                    raise ToolInstallationError("theHarvester doğrulaması için git gerekiyor.")
                checkout = parent / "theharvester"
                if identity(checkout) is not None:
                    validate_checkout(git, checkout, lock_fd)
                    if not options.force:
                        try:
                            verify(git, checkout, lock_fd)
                        except (SetupInterrupted, ProcessCleanupError):
                            raise
                        except ToolInstallationError:
                            if options.check:
                                raise
                        else:
                            print(f"theHarvester hazır: {HARVESTER_PIN.commit} (yerel doğrulama; indirme yok)")
                            return 0
                elif options.check:
                    raise ToolInstallationError("theHarvester kurulumu yok.")
                if uv is None:
                    uv = find_uv(parent, search_path=False)
                install(parent, git, uv, lock_fd)
                print(f"theHarvester hazır: {HARVESTER_PIN.commit}")
                print("Yalnız XTI'ın sabit P0 commoncrawl ve waybackarchive profili kullanılacak.")
                return 0
    except (ToolInstallationError, OSError, UnicodeError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        if isinstance(error, subprocess.TimeoutExpired):
            explanation = "Araç süre sınırını aştı; süreçler durduruldu."
        elif isinstance(error, KeyboardInterrupt):
            explanation = "Kurulum kullanıcı tarafından kesildi."
        else:
            explanation = str(error)
        print("theHarvester kurulumu tamamlanamadı: " + explanation, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
