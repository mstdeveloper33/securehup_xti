#!/usr/bin/env python3
"""Real tool upgrade and killed-installer acceptance, only in a disposable clone.

Run with bootstrap-python and --tool brand|harvester. The source checkout is
read only. The previous release and candidate use the same temporary project
path, so installed entry-point paths remain valid. No collector is invoked.
"""

import argparse
from contextlib import closing, contextmanager
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import NamedTuple


PROJECT = Path(__file__).resolve().parents[1]
BASELINE = "9cdf32c7981b87532952ec2c6b8a3fb5bb142ba8"
MAX_REVIEWED_SCHEMA = 83
OUTPUT_LIMIT = 8 * 1024 * 1024


class UnconfirmedCleanup(RuntimeError):
    """Preserve the disposable directory if an owned writer may still exist."""


@contextmanager
def disposable_workspace():
    root = Path(tempfile.mkdtemp(prefix="xti-upgrade-", dir=os.environ.get("RUNNER_TEMP"))).resolve()
    safe_to_remove = True
    try:
        yield root
    except UnconfirmedCleanup:
        safe_to_remove = False
        COMMON.summary(f"- Disposable checkout retained for process investigation: {root}")
        raise
    finally:
        if safe_to_remove:
            shutil.rmtree(root)


def load_helper(name, filename):
    spec = importlib.util.spec_from_file_location(name, PROJECT / "scripts" / filename)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


COMMON = load_helper("xti_upgrade_common", "check-linux-install.py")
BRAND = load_helper("xti_upgrade_brand", "check-linux-brand-install.py")


class ProcessIdentity(NamedTuple):
    pid: int
    parent: int
    group: int
    start: int
    state: str
    arguments: tuple


def process_identity(pid, proc_root=Path("/proc")):
    """Read Linux start time as well as PID; never signal a reused PID."""
    try:
        directory = proc_root / str(pid)
        raw = (directory / "stat").read_bytes()
        if len(raw) > 8192:
            return None
        # comm is parenthesized and may itself contain spaces or ')'.
        fields = raw[raw.rfind(b")") + 2:].split()
        if not raw.startswith(str(pid).encode() + b" (") or len(fields) < 20:
            return None
        arguments = (directory / "cmdline").read_bytes()
        if len(arguments) > 65536:
            return None
        return ProcessIdentity(pid, int(fields[1]), int(fields[2]), int(fields[19]),
                               fields[0].decode("ascii"),
                               tuple(os.fsdecode(item) for item in arguments.rstrip(b"\0").split(b"\0") if item))
    except (OSError, ValueError, UnicodeError):
        return None


def process_table(proc_root=Path("/proc")):
    return {item.pid: item for path in proc_root.iterdir()
            if path.name.isdigit() and (item := process_identity(int(path.name), proc_root)) is not None}


def same_process(expected, actual):
    return actual is not None and (expected.pid, expected.start, expected.group) == (
        actual.pid, actual.start, actual.group)


def owned_processes(owner, known=(), table=None):
    """Keep already observed descendants after their supervisor exits."""
    table = process_table() if table is None else table
    selected = {item.pid: item for item in (owner, *known)
                if same_process(item, table.get(item.pid))}
    while True:
        added = {pid: item for pid, item in table.items()
                 if pid not in selected and item.parent in selected}
        if not added:
            return tuple(selected.values())
        selected.update(added)


def signal_owned_groups(processes, number):
    """Only signal a group while a verified member still owns that group ID."""
    groups = set()
    for expected in processes:
        actual = process_identity(expected.pid)
        if (not same_process(expected, actual) or actual.state == "Z"
                or actual.group in groups):
            continue
        COMMON.require(actual.group != os.getpgrp(), "Refusing to signal the acceptance process group.")
        try:
            os.killpg(actual.group, number)
        except ProcessLookupError:
            pass
        groups.add(actual.group)


def cleanup_owned(process, owner, known, *, graceful=False):
    try:
        if owner is None:
            process.kill()
            process.wait(timeout=5)
            raise UnconfirmedCleanup("Process identity was unavailable; descendant cleanup cannot be confirmed.")
        known = owned_processes(owner, known)
        if graceful and process.poll() is None:
            signal_owned_groups((owner,), signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        signal_owned_groups(known, signal.SIGKILL)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        deadline = time.monotonic() + 10
        while any(live_identity(item) for item in known) and time.monotonic() < deadline:
            time.sleep(0.02)
        if any(live_identity(item) for item in known):
            raise UnconfirmedCleanup("Owned installation children did not stop; the disposable directory was retained.")
    except (OSError, subprocess.TimeoutExpired) as error:
        raise UnconfirmedCleanup("Owned process cleanup could not be confirmed; the disposable directory was retained.") from error


def command(arguments, environment, *, cwd=None, payload=None, timeout=90, expected=0):
    """Bound output/time; retain ownership across child process sessions."""
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen([str(item) for item in arguments], cwd=cwd or COMMON.PROJECT,
                                   env=environment, stdin=subprocess.PIPE, stdout=output,
                                   stderr=output, start_new_session=True)
        owner = process_identity(process.pid)
        known = ()
        try:
            COMMON.require(owner is not None, "Cannot establish process identity.")
            process.stdin.write((payload or "").encode())
            process.stdin.close()
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                known = owned_processes(owner, known)
                COMMON.require(os.fstat(output.fileno()).st_size <= OUTPUT_LIMIT,
                               "Acceptance command exceeded its output budget.")
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(arguments, timeout)
                time.sleep(0.05)
            COMMON.require(os.fstat(output.fileno()).st_size <= OUTPUT_LIMIT,
                           "Acceptance command exceeded its output budget.")
            output.seek(0)
            text = output.read().decode("utf-8", errors="replace")
            if expected is None:
                COMMON.require(process.returncode != 0, "Command unexpectedly succeeded.")
            else:
                COMMON.require(process.returncode == expected,
                               f"Command failed ({process.returncode}): {arguments[0]}\n{text[-6000:]}")
            return text.strip()
        finally:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
            finally:
                # Let the installer perform its own child cleanup before forcing it.
                cleanup_owned(process, owner, known, graceful=True)


def acceptance_environment(root):
    home = root / "home"
    home.mkdir()
    environment = {name: os.environ[name] for name in (
        "PATH", "LANG", "LC_ALL", "LD_LIBRARY_PATH", "SSL_CERT_FILE", "SSL_CERT_DIR",
    ) if name in os.environ}
    environment.update(HOME=str(home), XDG_CONFIG_HOME=str(home / "config"),
                       XDG_CACHE_HOME=str(home / "cache"), XDG_DATA_HOME=str(home / "data"),
                       TMPDIR=str(root), XTI_DATA_DIR=str(root / "data"),
                       XTI_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
                       GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0",
                       UV_CACHE_DIR=str(root / "uv-cache"), UV_PYTHON_INSTALL_DIR=str(root / "python"),
                       UV_PYTHON_BIN_DIR=str(root / "python-bin"))
    return environment


def checked_commit(value):
    COMMON.require(bool(re.fullmatch(r"[0-9a-f]{40}", value)), "A full commit ID is required.")
    return value


def disposable_clone(source, destination, environment):
    COMMON.require(not os.path.lexists(destination), "Acceptance clone path already exists.")
    target = checked_commit(command(["git", "rev-parse", "HEAD"], environment, cwd=source))
    checked_commit(BASELINE)
    command(["git", "cat-file", "-e", BASELINE + "^{commit}"], environment, cwd=source)
    command(["git", "merge-base", "--is-ancestor", BASELINE, target], environment, cwd=source)
    command(["git", "clone", "--no-hardlinks", "--no-checkout", "--", source, destination],
            environment, cwd=destination.parent, timeout=120)
    # No checkout/fetch ever runs against the caller's checkout.
    command(["git", "checkout", "--detach", BASELINE], environment, cwd=destination)
    return target


def tool_paths(project, tool):
    if tool == "brand":
        return (project / ".venv", project / ".brand-install.lock",
                project / ".brand-install.json", "./scripts/setup-brand")
    if tool == "harvester":
        return (project / ".tools/theharvester", project / ".tools/.theharvester.lock",
                project / ".tools/.theharvester-install.json", "./scripts/setup-harvester")
    raise RuntimeError("Unknown tool acceptance profile.")


def installer_child(identity, owner, canonical, tool):
    if identity.parent != owner.pid or identity.group != identity.pid or identity.state == "Z":
        return False
    arguments = identity.arguments
    if tool == "brand":
        return (len(arguments) > 3 and arguments[0] == str(canonical / "bin/python")
                and arguments[1:3] == ("-m", "pip") and "install" in arguments[3:])
    return (len(arguments) > 2 and Path(arguments[0]).name == "uv" and arguments[1] == "sync"
            and "--project" in arguments and arguments[arguments.index("--project") + 1:] == (str(canonical),))


def lock_held(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False
    finally:
        os.close(descriptor)


def live_identity(expected):
    actual = process_identity(expected.pid)
    return same_process(expected, actual) and actual.state != "Z"


def database_manifest(path):
    """Read all synthetic rows/rowids/DDL without creating a database."""
    path = Path(path)
    COMMON.require(path.is_file() and not path.is_symlink(), "Acceptance database is missing or linked.")
    with closing(sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("BEGIN")
        tables = {}
        for (name,) in connection.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"):
            quoted = '"' + name.replace('"', '""') + '"'
            tables[name] = (
                connection.execute(f"PRAGMA table_info({quoted})").fetchall(),
                connection.execute(f"SELECT rowid,* FROM {quoted} ORDER BY rowid").fetchall(),
                connection.execute("SELECT type,name,sql FROM sqlite_schema WHERE tbl_name=? ORDER BY name", (name,)).fetchall(),
            )
        return connection.execute("PRAGMA user_version").fetchone()[0], tables


def require_preserved_tables(before, after):
    for name, expected in before[1].items():
        actual = after[1].get(name)
        reviewed_upgrade = (
            before[0] <= 68 and 69 <= after[0] <= MAX_REVIEWED_SCHEMA
            and name in ("collection_session_steps", "collection_step_receipts")
            and _preserved_collection_upgrade(name, expected, actual)
        )
        reviewed_case_upgrade = (
            63 <= before[0] <= 79 and 80 <= after[0] <= MAX_REVIEWED_SCHEMA and name == "case_evidence"
            and _preserved_case_upgrade(expected, actual)
        )
        COMMON.require(actual == expected or reviewed_upgrade or reviewed_case_upgrade,
                       f"Schema migration changed pre-existing table/evidence: {name}.")


def _preserved_case_upgrade(expected, actual):
    """Permit only the schema80 CHECK extension; preserve every old row/rowid."""
    if actual is None or expected[1] != actual[1]:
        return False
    from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_DDL, CASE_EVIDENCE_INDEX_DDL
    from xti.adapters.relationship_notification_schema import CASE_EVIDENCE_DDL as CURRENT_DDL
    shapes = []
    for ddl in (CASE_EVIDENCE_DDL, CURRENT_DDL):
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute(ddl)
            connection.execute(CASE_EVIDENCE_INDEX_DDL)
            shapes.append((connection.execute('PRAGMA table_info(case_evidence)').fetchall(),
                connection.execute("SELECT type,name,sql FROM sqlite_schema WHERE tbl_name='case_evidence' ORDER BY name").fetchall()))
    return (expected[0], expected[2]) == shapes[0] and (actual[0], actual[2]) == shapes[1]


def _preserved_collection_upgrade(name, expected, actual):
    """Allow only reviewed DDL changes, exact old values and NULL new links."""
    if actual is None:
        return False
    from xti.adapters.collection_news_schema import (
        COLLECTION_HISTORY_DDL, COLLECTION_HISTORY_V68_DDL,
    )
    shapes = []
    for statements in (COLLECTION_HISTORY_V68_DDL, COLLECTION_HISTORY_DDL):
        with closing(sqlite3.connect(":memory:")) as connection:
            for statement in statements:
                connection.execute(statement)
            shapes.append((
                connection.execute(f"PRAGMA table_info({name})").fetchall(),
                connection.execute(
                    "SELECT type,name,sql FROM sqlite_schema WHERE tbl_name=? ORDER BY name", (name,),
                ).fetchall(),
            ))
    if (expected[0], expected[2]) != shapes[0] or (actual[0], actual[2]) != shapes[1]:
        return False
    width = len(expected[0]) + 1  # Preserve rowid in addition to every old column.
    return (
        [row[:width] for row in actual[1]] == expected[1]
        and all(value is None for row in actual[1] for value in row[width:])
    )


def migrate_acceptance_data(environment, before_files, before_database, *, target_schema=None):
    """Exercise a reviewed explicit schema64 upgrade, retaining its original backup."""
    if target_schema is None:
        from xti.adapters.schema import SCHEMA_VERSION
        target_schema = SCHEMA_VERSION
    COMMON.require(type(target_schema) is int and 65 <= target_schema <= MAX_REVIEWED_SCHEMA, "Unsupported migration target.")
    data = Path(environment["XTI_DATA_DIR"])
    error = command(["./setup", "--core-only"], environment, expected=None)
    COMMON.require("migrate" in error, "Old data was not rejected with explicit migration guidance.")
    COMMON.require(COMMON.snapshot(data) == before_files, "Failed setup changed old data.")
    response = json.loads(command(["./xti", "--json", "migrate"], environment))
    result = response["data"]
    COMMON.require(response.get("ok") is True and result.get("changed") is True,
                   "Migration did not report an explicit successful change.")
    COMMON.require((result.get("from_version"), result.get("to_version")) == (64, target_schema),
                   "Migration did not reach the reviewed target schema from schema64.")
    backup = Path(result["backup"])
    COMMON.require(backup.parent == data / "backups" and backup.is_file() and not backup.is_symlink(),
                   "Migration backup escaped the disposable data directory.")
    COMMON.require(database_manifest(backup) == before_database, "Pre-migration backup changed original evidence.")
    current = database_manifest(data / "xti.db")
    COMMON.require(current[0] == target_schema, "Candidate did not publish the reviewed schema.")
    require_preserved_tables(before_database, current)
    after_files = COMMON.snapshot(data)
    for name, value in before_files.items():
        if name != "xti.db":
            COMMON.require(after_files.get(name) == value, "Migration changed original non-database evidence.")
    repeated = json.loads(command(["./xti", "--json", "migrate"], environment))["data"]
    COMMON.require(repeated.get("changed") is False and repeated.get("backup") is None,
                   "Repeated migration was not a no-op.")
    COMMON.require(COMMON.snapshot(data) == after_files, "Repeated migration changed database or backup bytes.")
    COMMON.summary(f"- PASS: schema64 setup refused without writes; explicit schema{target_schema} migration preserved all old rows/rowids/evidence, applied reviewed schema additions through the report journal and created an unchanged schema64 backup.")
    return backup, after_files


def require_unsupported_schema_error(output):
    """Decode the pinned old CLI's JSON error before matching its diagnosis."""
    try:
        response = json.loads(output)
    except json.JSONDecodeError:
        response = None
    error = response.get("error") if isinstance(response, dict) else None
    COMMON.require(
        isinstance(response, dict) and response.get("ok") is False
        and isinstance(error, dict) and error.get("code") == "storage_error"
        and error.get("message") == (
            "Veritabanı sürümü bu uygulamayla uyumlu değil. "
            "Dosya değiştirilmedi; uygun uygulama sürümünü kullanın."
        ),
        "Old code failed for a reason other than unsupported new schema.",
    )


def restore_baseline_data(environment, backup, before_database, upgraded_files):
    """Old code rejects a newer schema; restore its schema64 backup at a new path."""
    data = Path(environment["XTI_DATA_DIR"])
    error = command(["./xti", "--json", "doctor"], environment, expected=None)
    require_unsupported_schema_error(error)
    COMMON.require(COMMON.snapshot(data) == upgraded_files, "Old code changed the upgraded database.")
    restored = dict(environment, XTI_DATA_DIR=str(data.parent / "rollback-restored"))
    target = Path(restored["XTI_DATA_DIR"]) / "xti.db"
    COMMON.require(not target.parent.exists(), "Rollback restore directory already exists.")
    command(["./xti", "restore", backup], restored)
    COMMON.require(database_manifest(target) == before_database, "Old-code restore did not preserve schema64 evidence.")
    COMMON.local_asset(restored)
    error = command(["./xti", "restore", backup], restored, expected=None)
    COMMON.require("zaten var" in error, "Repeated restore failed for a reason other than existing destination.")
    COMMON.require(database_manifest(target) == before_database, "Repeated restore overwrote recovered evidence.")
    COMMON.require(COMMON.snapshot(data) == upgraded_files, "Rollback recovery changed retained upgraded data.")
    COMMON.summary("- PASS: old code rejected the new schema; its pre-migration backup restored only into a new data directory; upgraded data retained. Later writes are outside schema64 rollback.")


def brand_tool_manifest(canonical, environment):
    """Compare the two pinned upstream tools, excluding the new optional reader."""
    script = '''import hashlib, json
from importlib.metadata import distribution
from importlib.resources import files
result = {}
for name, package in (("maigret", "maigret"), ("sherlock-project", "sherlock_project")):
    installed = distribution(name)
    catalog = files(package).joinpath("resources", "data.json").read_bytes()
    result[name] = {"version": installed.version, "origin": json.loads(installed.read_text("direct_url.json")),
                    "catalog_sha256": hashlib.sha256(catalog).hexdigest()}
print(json.dumps(result, sort_keys=True))
'''
    return json.loads(command([canonical / "bin/python", "-I", "-c", script], environment))


def require_preserved_brand_backup(project, previous, existing_backups):
    added = set(project.glob(".venv-backup-*")) - set(existing_backups)
    COMMON.require(len(added) == 1, "News dependency upgrade must preserve one unique previous environment.")
    backup = added.pop()
    COMMON.require(BRAND.environment_snapshot(backup) == previous,
                   "News dependency upgrade changed the retained previous environment.")
    return backup


def interrupt_real_install(project, tool, environment):
    canonical, lock, journal, installer = tool_paths(project, tool)
    before = BRAND.environment_snapshot(canonical)
    data_before = COMMON.snapshot(Path(environment["XTI_DATA_DIR"]))
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen([installer, "--force"], cwd=project, env=environment,
                                   stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                   start_new_session=True)
        owner = process_identity(process.pid)
        known = ()
        selected = None
        try:
            COMMON.require(owner is not None, "Cannot identify the disposable installer.")
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                known = owned_processes(owner, known)
                if process.poll() is not None:
                    raise RuntimeError("Installer exited before a real package installation could be interrupted.")
                COMMON.require(os.fstat(output.fileno()).st_size <= OUTPUT_LIMIT,
                               "Interrupted installer exceeded its output budget.")
                matches = [item for item in known if installer_child(item, owner, canonical, tool)]
                if matches:
                    selected = matches[0]
                    # Stop the actual pip/uv group, not a fake executable or a mocked installer.
                    signal_owned_groups((selected,), signal.SIGSTOP)
                    stopped = process_identity(selected.pid)
                    if same_process(selected, stopped) and stopped.state in ("T", "t"):
                        break
                    selected = None
                time.sleep(0.01)
            COMMON.require(selected is not None, "No real pip/uv installation was observed within the deadline.")
            known = owned_processes(owner, known)
            COMMON.require(journal.is_file() and lock_held(lock), "Installation transaction was not active.")
            signal_owned_groups((owner,), signal.SIGKILL)
            process.wait(timeout=10)
            COMMON.require(process.returncode == -signal.SIGKILL, "Installer did not receive the abrupt interruption.")
            COMMON.require(live_identity(selected) and lock_held(lock),
                           "Real package child did not retain the installation lock after supervisor death.")
            error = command([installer, "--recover"], environment, cwd=project, expected=None, timeout=20)
            COMMON.require("tamamlanmasını bekle" in error,
                           "Recovery failed for a reason other than the still-running child lock.")
            COMMON.require(journal.is_file(), "Busy recovery changed the transaction journal.")
            COMMON.summary(f"- PASS: real {tool} package child observed and paused; killed installer; recovery refused its inherited lock.")
        finally:
            cleanup_owned(process, owner, known)
    command([installer, "--recover"], environment, cwd=project)
    command([installer, "--recover"], environment, cwd=project)
    COMMON.require(not journal.exists(), "Recovery left an installation journal.")
    COMMON.require(BRAND.environment_snapshot(canonical) == before,
                   "Recovery changed the prior environment's identity, contents or modes.")
    command([installer, "--check"], environment, cwd=project, timeout=120)
    COMMON.local_asset(environment)
    COMMON.require(COMMON.snapshot(Path(environment["XTI_DATA_DIR"])) == data_before,
                   "Interrupted installation or recovery changed engine data.")
    COMMON.summary("- PASS: explicit recovery twice, original environment identity/content, --check and engine records preserved.")


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", required=True, choices=("brand", "harvester"))
    options = parser.parse_args(arguments)
    stage = "Linux and isolated clone guard"
    try:
        COMMON.require(sys.platform == "linux" and Path("/proc/self/stat").is_file(),
                       "Upgrade acceptance requires a real Linux host with /proc.")
        COMMON.require(shutil.which("git") is not None, "git is required.")
        if options.tool == "harvester":
            COMMON.require(shutil.which("uv") is not None, "The reviewed uv installer must be on PATH.")
        COMMON.summary(f"### Real {options.tool} upgrade/recovery ({platform.machine()}, Python {platform.python_version()})")
        with disposable_workspace() as root:
            environment = acceptance_environment(root)
            project = root / "disposable checkout"
            target = disposable_clone(PROJECT, project, environment)
            COMMON.PROJECT = project
            COMMON.run = command
            COMMON.summary(f"- Baseline: {BASELINE}; candidate: {target}; same disposable checkout path.")
            stage = "previous release, synthetic records and real tool installation"
            command(["./setup", "--core-only"], environment)
            command(["./xti", "assets", "add", "example.com"], environment)
            data = Path(environment["XTI_DATA_DIR"])
            (data / "upgrade-evidence.bin").write_bytes(b"Synthetic upgrade evidence.\x00\xff\n")
            before = COMMON.snapshot(data)
            canonical, _, _, installer = tool_paths(project, options.tool)
            command([installer], environment, timeout=1200)
            command([installer, "--check"], environment, timeout=120)
            tool_interpreter = canonical / ("bin/python" if options.tool == "brand" else ".venv/bin/python")
            tool_python = command([tool_interpreter, "-I", "-c", "import platform; print(platform.python_version())"], environment)
            COMMON.summary(f"- Actual baseline {options.tool} Python: {tool_python}; acceptance Python: {platform.python_version()}.")
            if options.tool == "brand":
                environment.pop("XTI_PYTHON", None)
            COMMON.local_asset(environment)
            reference = COMMON.engine(environment, "search", {"query": "example.com", "kinds": ["domain"]})["results"][0]["reference"]
            installed = BRAND.environment_snapshot(canonical)
            baseline_installed = installed
            baseline_tools = brand_tool_manifest(canonical, environment) if options.tool == "brand" else None
            baseline_backups = set(project.glob(".venv-backup-*"))
            retained_brand_backup = None
            before_database = database_manifest(data / "xti.db")
            COMMON.require(before_database[0] == 64, "The published baseline must use schema64.")
            COMMON.require(COMMON.snapshot(data) == before, "Baseline tool setup changed original data.")
            COMMON.summary("- PASS: previous release installed actual pinned tools; sample record and evidence preserved.")

            stage = "candidate schema compatibility"
            command(["git", "checkout", "--detach", checked_commit(target)], environment)
            target_schema = int(command(["./scripts/python", "-c", "from xti.adapters.schema import SCHEMA_VERSION; print(SCHEMA_VERSION)"], environment))
            COMMON.require(64 <= target_schema <= MAX_REVIEWED_SCHEMA, f"Only reviewed schema64–{MAX_REVIEWED_SCHEMA} candidates are supported by this acceptance.")
            backup, current_files = None, before
            if target_schema > 64:
                stage = f"explicit schema64 to schema{target_schema} migration"
                backup, current_files = migrate_acceptance_data(environment, before, before_database,
                                                               target_schema=target_schema)

            for revision, label in ((target, "upgrade"), (BASELINE, "baseline rollback"),
                                    (target, "return to candidate")):
                stage = label
                command(["git", "checkout", "--detach", checked_commit(revision)], environment)
                if revision == BASELINE and backup is not None:
                    rollback_environment = environment
                    if retained_brand_backup is not None:
                        # Old dependency pins belong to the retained old environment.
                        # Do not rebuild or move either installation for this data rollback.
                        rollback_environment = dict(environment,
                            XTI_PYTHON=str(retained_brand_backup / "bin/python"),
                            PYTHONPATH=str(project / "src"))
                    restore_baseline_data(rollback_environment, backup, before_database, current_files)
                    if retained_brand_backup is not None:
                        command([retained_brand_backup / "bin/python", "-m", "pip", "--isolated", "check"],
                                rollback_environment, timeout=120)
                        command([retained_brand_backup / "bin/python", project / "scripts/verify_brand_install.py",
                                 "--prefix", retained_brand_backup], rollback_environment, timeout=120)
                    else:
                        command([installer, "--check"], environment, timeout=120)
                    COMMON.require(BRAND.environment_snapshot(canonical) == installed,
                                   "Schema rollback changed the installed tool environment.")
                    if retained_brand_backup is not None:
                        COMMON.require(BRAND.environment_snapshot(retained_brand_backup) == baseline_installed,
                                       "Schema rollback changed the retained baseline environment.")
                    continue
                command(["./setup", "--core-only"], environment)
                command([installer], environment, timeout=1200)
                command([installer, "--check"], environment, timeout=120)
                COMMON.local_asset(environment)
                detail = COMMON.engine(environment, "record.get", {"reference": reference})
                COMMON.require(detail["reference"] == reference, "Upgrade changed the existing record identity.")
                current_environment = BRAND.environment_snapshot(canonical)
                if label == "upgrade" and options.tool == "brand" and target_schema >= 66:
                    COMMON.require(current_environment[:2] != baseline_installed[:2],
                                   "The new reader did not get a separate managed environment.")
                    retained_brand_backup = require_preserved_brand_backup(project, baseline_installed, baseline_backups)
                    COMMON.require(brand_tool_manifest(canonical, environment) == baseline_tools,
                                   "Adding the reader changed pinned upstream tool identity or catalog evidence.")
                    installed = current_environment
                    COMMON.summary("- PASS: news dependencies installed in a new managed environment; exact old environment retained; pinned social tool versions/origins/catalogs unchanged.")
                else:
                    COMMON.require(current_environment == installed,
                                   f"{label} replaced or changed the existing tool environment.")
                if retained_brand_backup is not None:
                    COMMON.require(BRAND.environment_snapshot(retained_brand_backup) == baseline_installed,
                                   "Return to candidate changed the retained baseline environment.")
                COMMON.require(COMMON.snapshot(data) == current_files, f"{label} changed existing data bytes.")
                COMMON.summary(f"- PASS: {label}; verified tool environment and preserved engine record/evidence bytes.")

            stage = "real package subprocess interruption and recovery"
            interrupt_real_install(project, options.tool, environment)
        COMMON.summary(f"- RESULT: PASS. Scope: schema64 same-schema or explicit migration through schema{MAX_REVIEWED_SCHEMA} with new-path backup recovery; pinned tools and preserved environment during reader installation; process crash, not hardware power loss; no target scan or source collection.")
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        COMMON.summary(f"- RESULT: FAIL at {stage}: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
