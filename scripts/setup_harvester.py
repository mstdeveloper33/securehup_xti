#!/usr/bin/env python3
"""Install the reviewed Harvester checkout without losing an earlier installation.

The venv is built at its final location because entry-point shebangs are absolute.
A durable, identity-checked journal covers every rename. Old checkouts and failed
candidates are retained; recovery never recursively deletes user content.
"""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

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


class SetupInterrupted(ToolInstallationError):
    pass


class ProcessCleanupError(ToolInstallationError):
    """Do not restore directories while an unconfirmed child may still write."""


@contextmanager
def interruption_handlers():
    def interrupted(number, _frame):
        raise SetupInterrupted(f"Kurulum sinyal nedeniyle kesildi ({number}).")

    previous = {}
    try:
        for number in (signal.SIGTERM, signal.SIGHUP):
            previous[number] = signal.signal(number, interrupted)
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def identity(path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(metadata.st_mode):
        raise ToolInstallationError(f"Gerçek dizin bekleniyor: {path.name}; değiştirilmedi.")
    return [metadata.st_dev, metadata.st_ino]


def journal_paths(parent, transaction):
    return {
        "canonical": parent / "theharvester",
        "backup": parent / f".theharvester-backup-{transaction}",
        "candidate": parent / f".theharvester-candidate-{transaction}",
        "failed": parent / f".theharvester-failed-{transaction}",
    }


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def load_journal(parent):
    try:
        descriptor = os.open(parent / JOURNAL_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError("not a private regular journal")
            payload = stream.read(16385)
        if len(payload) > 16384:
            raise ValueError("journal too large")
        data = json.loads(payload, object_pairs_hook=unique_fields)
        if not isinstance(data, dict) or set(data) != {"version", "transaction", "phase", "old", "new"}:
            raise ValueError("unknown journal fields")
        if type(data["version"]) is not int or data["version"] != 1:
            raise ValueError("unsupported journal version")
        transaction = data["transaction"]
        if not isinstance(transaction, str) or str(uuid.UUID(transaction)) != transaction:
            raise ValueError("invalid transaction")
        if data["phase"] not in ("prepared", "committed"):
            raise ValueError("unknown phase")
        for field in ("old", "new"):
            value = data[field]
            if field == "old" and value is None:
                continue
            if not isinstance(value, list) or len(value) != 2 or any(
                type(item) is not int or item < 0 for item in value
            ):
                raise ValueError("invalid directory identity")
        if data["old"] == data["new"]:
            raise ValueError("duplicate directory identity")
        return data
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        raise ToolInstallationError(
            "Kurulum günlüğü güvenle okunamadı; dosyalara dokunulmadı. "
            "Elle inceleme gerekiyor: .tools/" + JOURNAL_NAME
        ) from error


def write_journal(parent, data, *, initial=False):
    journal = parent / JOURNAL_NAME
    temporary = parent / f".theharvester-journal-{uuid.uuid4()}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if initial:
            # All cooperating writers hold the persistent exclusive lock.
            # Atomic publication leaves either no journal or a complete one.
            if os.path.lexists(journal):
                raise ToolInstallationError("Kurulum günlüğü zaten var; üzerine yazılmadı.")
            os.replace(temporary, journal)
        else:
            existing = load_journal(parent)
            if existing != dict(data, phase="prepared"):
                raise ToolInstallationError("Kurulum günlüğü değişmiş; üzerine yazılmadı.")
            os.replace(temporary, journal)
        sync_directory(parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def clear_journal(parent, expected):
    if load_journal(parent) != expected:
        raise ToolInstallationError("Kurulum günlüğü değişmiş; silinmedi.")
    (parent / JOURNAL_NAME).unlink()
    sync_directory(parent)


def move_directory(source, destination, expected):
    if identity(source) != expected or os.path.lexists(destination):
        raise ToolInstallationError("Kurulum dizininin kimliği veya hedefi değişmiş; işlem durduruldu.")
    os.rename(source, destination)
    sync_directory(source.parent)


def recover(parent):
    """Recover only recognized transaction directories, including partial rollback."""
    data = load_journal(parent)
    paths = journal_paths(parent, data["transaction"])
    observed = {name: identity(path) for name, path in paths.items()}
    old, new = data["old"], data["new"]
    for name, actual in observed.items():
        allowed = {"canonical": (old, new), "backup": (old,), "candidate": (new,), "failed": (new,)}[name]
        if actual is not None and actual not in allowed:
            raise ToolInstallationError("Kurtarma yolunda tanınmayan dizin var; hiçbir dizin taşınmadı.")
    new_locations = [name for name, actual in observed.items() if actual == new]
    old_locations = [name for name, actual in observed.items() if old is not None and actual == old]
    if len(new_locations) != 1 or (old is not None and len(old_locations) != 1):
        raise ToolInstallationError("Kurtarma dizinlerinin kimliği eksik veya çakışıyor; değiştirilmedi.")
    if data["phase"] == "committed":
        if new_locations != ["canonical"] or (old is not None and old_locations != ["backup"]):
            raise ToolInstallationError("Tamamlanmış kurulumun dizin düzeni değişmiş; değiştirilmedi.")
        clear_journal(parent, data)
        print("Tamamlanmış kurulumun günlüğü temizlendi; mevcut kurulum korundu.")
        return
    location = new_locations[0]
    if location not in ("canonical", "candidate", "failed"):
        raise ToolInstallationError("Aday kurulum beklenmeyen yerde; değiştirilmedi.")
    if old is not None and old_locations[0] not in ("canonical", "backup"):
        raise ToolInstallationError("Önceki kurulum beklenmeyen yerde; değiştirilmedi.")
    if location != "failed":
        move_directory(paths[location], paths["failed"], new)
    if old is not None and old_locations == ["backup"]:
        move_directory(paths["backup"], paths["canonical"], old)
    clear_journal(parent, data)
    print("Yarım kalan kurulum geri alındı; önceki kurulum varsa aynı konumuna döndürüldü.")
    print(f"Başarısız aday korundu: {paths['failed']}")


def terminate_group(process):
    # A second Ctrl-C/TERM must not interrupt shutdown and let recovery race
    # with a child still writing into the canonical installation directory.
    previous = {number: signal.signal(number, signal.SIG_IGN)
                for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    try:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        # The leader can exit before its children. Kill the owned group too.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    except OSError as error:
        raise ProcessCleanupError(
            "Araç alt süreçleri güvenle durdurulamadı; otomatik geri dönüş yapılmadı. "
            "Süreçler tamamlandıktan sonra ./scripts/setup-harvester --recover çalıştır."
        ) from error
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def run_command(arguments, *, cwd, lock_fd, timeout, environment=None):
    with tempfile.TemporaryFile() as output:
        process = None
        try:
            process = subprocess.Popen(
                [str(item) for item in arguments], cwd=cwd, env=environment,
                stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                pass_fds=(lock_fd,), start_new_session=True,
            )
            deadline = time.monotonic() + timeout
            while True:
                if os.fstat(output.fileno()).st_size > OUTPUT_LIMIT:
                    raise ToolInstallationError("Araç yanıtı boyut sınırını aştı.")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(arguments, timeout)
                try:
                    process.wait(timeout=min(0.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            # Keep normal cleanup in this try: interruption between leader exit
            # and cleanup must not let a background descendant race with rollback.
            terminate_group(process)
        except ProcessCleanupError:
            raise
        except BaseException as error:
            if process is None:
                if isinstance(error, (SetupInterrupted, KeyboardInterrupt)):
                    # Popen may already have spawned the child before returning
                    # its handle. Its inherited lock must gate later recovery.
                    raise ProcessCleanupError(
                        "Araç başlatılırken kesinti oldu; alt süreç durumu doğrulanamadı. "
                        "Süreçler tamamlandıktan sonra ./scripts/setup-harvester --recover çalıştır."
                    ) from error
            else:
                terminate_group(process)
            raise
        if process.returncode:
            raise ToolInstallationError(f"{Path(arguments[0]).name} komutu başarısız (çıkış {process.returncode}).")
        if output.tell() > OUTPUT_LIMIT:
            raise ToolInstallationError("Araç yanıtı boyut sınırını aştı.")
        output.seek(0)
        return output.read().decode("utf-8", errors="strict").strip()


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
    old = identity(checkout)
    transaction = str(uuid.uuid4())
    paths = journal_paths(parent, transaction)
    if any(os.path.lexists(paths[name]) for name in ("backup", "candidate", "failed")):
        raise ToolInstallationError("Yeni işlem için ayrılan dizin zaten var; değiştirilmedi.")
    paths["candidate"].mkdir(mode=0o700)
    sync_directory(parent)
    data = {"version": 1, "transaction": transaction, "phase": "prepared",
            "old": old, "new": identity(paths["candidate"])}
    write_journal(parent, data, initial=True)
    try:
        if old is not None:
            move_directory(checkout, paths["backup"], old)
        move_directory(paths["candidate"], checkout, data["new"])
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
        committed = dict(data, phase="committed")
        write_journal(parent, committed)
        clear_journal(parent, committed)
    except ProcessCleanupError:
        # The journal and inherited lock keep runtime/recovery out until the
        # remaining child has actually stopped. Never rename its writable cwd.
        raise
    except BaseException:
        # Even if commit was written, recovery knows it must retain the new venv.
        if pending_installation(parent):
            recover(parent)
        raise
    if old is not None:
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
