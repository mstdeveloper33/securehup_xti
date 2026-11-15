#!/usr/bin/env python3
"""Bounded Linux operations acceptance; only disposable synthetic data is used.

Requires a real systemd user manager and a dedicated <=64 MiB tmpfs supplied
by CI. Never starts a manager, changes linger or mounts/fills the user's disk.
HTTP outcomes are injected at the production HIBP opener, not at real sockets.
The defaults measure 100/1,000/5,000 domains and a 600-second local soak; they
do not establish a 24/7 SLA or live-provider availability.
"""

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "src"))

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.adapters.worker_lock import LocalExecutionLock


class UnconfirmedCleanup(RuntimeError):
    """Keep the disposable workspace if real service shutdown is uncertain."""


def require(value, message):
    if not value:
        raise RuntimeError(message)


def summary(message):
    print(message, flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(message + "\n")


def run(arguments, environment, *, expected=0, payload=None, timeout=60):
    process = subprocess.Popen(arguments, cwd=PROJECT, env=environment,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        output, errors = process.communicate(payload or "", timeout=timeout)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
        raise
    require(process.returncode == expected,
            f"Command failed ({process.returncode}, wanted {expected}): {shlex.join(arguments)}\n"
            + (output + errors)[-4000:])
    return output


def mode(control, value):
    staged = control.with_suffix(".next")
    staged.write_text(json.dumps({"mode": value}), encoding="utf-8")
    staged.replace(control)


def cli(environment, *arguments, expected=0):
    output = run([sys.executable, "-m", "tests.operations_worker", "--json", *arguments],
                 environment, expected=expected)
    return json.loads(output)


def calls(control):
    path = control.with_suffix(".calls")
    return [] if not path.exists() else [json.loads(line) for line in path.read_text().splitlines()]


def environment_for(data, control):
    environment = dict(os.environ, XTI_DATA_DIR=str(data), XTI_OPERATIONS_CONTROL=str(control),
                       PYTHONPATH=os.pathsep.join((str(PROJECT / "src"), str(PROJECT))),
                       PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", XTI_PYTHON=sys.executable)
    return environment


def seed(data, control):
    data.mkdir(mode=0o700)
    repository = SQLiteAssetRepository(data / "xti.db")
    repository.initialize()
    repository.add("example.com")
    mode(control, "success")
    environment = environment_for(data, control)
    result = cli(environment, "profiles", "save", "acceptance", "example.com",
                 "--task", "notices-hibp")["data"]
    return environment, result["profile"]


def collection_states(database):
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute("SELECT id, status FROM collection_sessions ORDER BY rowid").fetchall()


def source_outages(root):
    control = root / "source-control.json"
    environment, _ = seed(root / "sources", control)
    database = Path(environment["XTI_DATA_DIR"]) / "xti.db"
    cli(environment, "collect", "--profile", "acceptance")
    repo = SQLitePublicNoticeRepository(database)
    successes = []
    for failure in ("timeout", "disconnect", "429", "503", "malformed"):
        previous = repo.status().latest_complete_run
        before_calls = len(calls(control))
        mode(control, failure)
        failed = cli(environment, "collect", "--profile", "acceptance", expected=3)["data"]
        status = repo.status()
        require(status.latest_run.status == "failed", "Source failure became success.")
        require(status.latest_complete_run == previous, "Source failure replaced previous successful evidence.")
        require(len(calls(control)) == before_calls + 1, "Source failure caused an unrequested retry.")
        parent_id = failed["session_id"]
        before_history = cli(environment, "collections", "show", parent_id)["data"]
        require(before_history["session"]["status"] in {"failed", "partial"}, "Failure history is not explicit.")
        plan = cli(environment, "collections", "resume", parent_id, "--plan")["data"]
        require([unit["step_key"] for unit in plan["units"]] == ["notices-hibp"], "Retry selected unrelated work.")
        mode(control, "success")
        resumed = cli(environment, "collections", "resume", parent_id)["data"]
        require(resumed["history"]["session"]["status"] == "complete", "Recovery did not complete.")
        require(cli(environment, "collections", "show", parent_id)["data"] == before_history,
                "Recovery changed historical failure.")
        require(len(calls(control)) == before_calls + 2, "Recovery duplicated the source call.")
        successes.append(failure)
    return {"passed_modes": successes, "transport": "controlled production HTTP opener; sockets denied",
            "one_call_per_attempt": True, "previous_success_preserved": True}


def capacity(root, sizes=(100, 1000, 5000)):
    data = root / "capacity"
    data.mkdir(mode=0o700)
    repository = SQLiteAssetRepository(data / "xti.db")
    repository.initialize()
    environment = dict(os.environ, XTI_DATA_DIR=str(data), XTI_PYTHON=sys.executable,
                       PYTHONPATH=str(PROJECT / "src"), PYTHONNOUSERSITE="1")
    measurements = []
    count = 0
    for size in sizes:
        began = time.monotonic()
        for index in range(count, size):
            repository.add(f"asset-{index:06d}.example.com")
        seed_seconds = time.monotonic() - began
        count = size
        request = {"contract_version": 1, "request_id": "capacity:1", "operation": "search",
                   "parameters": {"query": "example.com", "kinds": ["domain"], "limit": 20}}
        began = time.monotonic()
        output = run([str(PROJECT / "xti"), "engine"], environment, payload=json.dumps(request))
        search_seconds = time.monotonic() - began
        result = json.loads(output)
        require(result["status"] == "complete" and result["data"]["total_match_count"] == size,
                "Capacity search lost records or truncated the total.")
        require(len(result["data"]["results"]) == min(size, 20), "Capacity search violated page size.")
        began = time.monotonic()
        backup = root / f"capacity-{size}.db"
        repository.backup(backup)
        restored = root / f"restored-{size}.db"
        SQLiteAssetRepository.restore(backup, restored)
        backup_seconds = time.monotonic() - began
        require(SQLiteAssetRepository(restored).list() == repository.list(), "Capacity restore lost identities.")
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        rss_bytes = int(usage.ru_maxrss * (1024 if sys.platform == "linux" else 1))
        parent_usage = resource.getrusage(resource.RUSAGE_SELF)
        parent_rss_bytes = int(parent_usage.ru_maxrss * (1024 if sys.platform == "linux" else 1))
        require(search_seconds < 60 and backup_seconds < 120, "Acceptance time budget exceeded.")
        require(rss_bytes < 1024 ** 3, "Acceptance child peak memory exceeded 1 GiB.")
        measurements.append({"domains": size, "seed_seconds": seed_seconds,
                             "search_seconds": search_seconds, "backup_restore_seconds": backup_seconds,
                             "database_bytes": repository.path.stat().st_size,
                             "child_high_water_rss_bytes": rss_bytes,
                             "parent_high_water_rss_bytes": parent_rss_bytes})
    return measurements


def validate_low_disk_mount(directory):
    directory = Path(directory).resolve(strict=True)
    require(sys.platform == "linux", "The constrained filesystem acceptance requires Linux.")
    require(directory.is_dir() and os.stat(directory).st_uid == os.getuid(), "tmpfs must belong to the caller.")
    found = False
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        left, right = line.split(" - ", 1)
        target = left.split()[4].replace("\\040", " ").replace("\\134", "\\")
        if target == str(directory) and right.split()[0] == "tmpfs":
            found = True
    require(found, "Low-disk path must be an exact dedicated tmpfs mount.")
    usage = shutil.disk_usage(directory)
    require(4 * 1024 ** 2 <= usage.total <= 64 * 1024 ** 2,
            "Low-disk tmpfs size must be between 4 and 64 MiB.")
    return directory


def low_disk(directory):
    directory = validate_low_disk_mount(directory)
    with tempfile.TemporaryDirectory(prefix="xti-low-disk-", dir=directory) as temporary:
        root = Path(temporary)
        control = root / "control.json"
        environment, _ = seed(root / "data", control)
        database = root / "data/xti.db"
        before = hashlib.sha256(database.read_bytes()).hexdigest()
        measured_free = shutil.disk_usage(database.parent).free
        result = cli(environment, "schedule", "prepare", "acceptance", expected=1)
        require(not result.get("ok"), "Low-disk preflight reported success.")
        error = result.get("error", {})
        require(error.get("code") == "storage_error" and "boş alan gerekli" in error.get("message", ""),
                "Low-disk refusal was not the expected free-space preflight error.")
        require(measured_free < 64 * 1024 ** 2, "Filesystem was not below the existing 64MiB reserve.")
        require(hashlib.sha256(database.read_bytes()).hexdigest() == before, "Low-disk preflight changed records.")
        require(not (database.parent / "scheduled-backups").exists(), "Low-disk preflight published a backup.")
        require(not calls(control), "Low-disk preflight started source collection.")
        return {"filesystem": "tmpfs", "total_bytes": shutil.disk_usage(root).total,
                "measured_free_bytes": measured_free, "minimum_reserve_bytes": 64 * 1024 ** 2,
                "error_code": error["code"],
                "scope": "real low-free-space preflight; no disk filling or power-loss claim"}


def wait_until(predicate, message, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.2)
    raise RuntimeError(message)


def stop_owned_units(environment, service, timer):
    """Prove both units and their cgroup stopped before deleting any fixture."""
    try:
        # A missing unit is harmless only if the following state query proves it.
        for arguments in (("stop", timer, service), ("disable", "--runtime", timer)):
            try:
                subprocess.run(["systemctl", "--user", *arguments], env=environment,
                               capture_output=True, timeout=30, check=False)
            except (OSError, subprocess.TimeoutExpired):
                # Attempt both actions; the state/cgroup proof below decides
                # whether cleanup is safe even if a control reply was lost.
                pass
        for unit in (timer, service):
            result = subprocess.run(
                ["systemctl", "--user", "show", unit, "--property=LoadState",
                 "--property=ActiveState", "--property=ControlGroup", "--property=UnitFileState"],
                env=environment, capture_output=True, text=True, timeout=30, check=False)
            properties = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
            if (result.returncode not in {0, 1}
                    or properties.get("ActiveState") not in {"inactive", "failed"}
                    or properties.get("UnitFileState") in {"enabled", "enabled-runtime"}):
                raise UnconfirmedCleanup(f"Cannot confirm stopped/disabled acceptance unit: {unit}")
            cgroup = properties.get("ControlGroup", "")
            if cgroup:
                base = Path("/sys/fs/cgroup").resolve()
                group = (base / cgroup.lstrip("/")).resolve()
                if not group.is_relative_to(base):
                    raise UnconfirmedCleanup("Invalid acceptance cgroup path.")
                if group.exists():
                    for processes in group.rglob("cgroup.procs"):
                        if processes.read_text().strip():
                            raise UnconfirmedCleanup(f"Acceptance cgroup still contains processes: {unit}")
    except UnconfirmedCleanup:
        raise
    except BaseException as error:
        raise UnconfirmedCleanup("Acceptance service shutdown could not be verified.") from error


def systemd_acceptance(root):
    require(sys.platform == "linux", "Real systemd acceptance requires Linux.")
    control = root / "systemd-control.json"
    environment, profile = seed(root / "systemd-data", control)
    # Avoid querying the manager's full environment (it may contain secrets).
    run(["systemctl", "--user", "show", "--property=Version", "--value"], environment)
    generated = cli(environment, "schedule", "generate", "acceptance", "--output", str(root / "units"),
                    "--at", "09:00", "--timezone", "UTC", "--keep", "2")["data"]
    name = generated["unit_name"]
    runtime = Path(environment["XDG_RUNTIME_DIR"]) / "systemd/user"
    runtime.mkdir(parents=True, exist_ok=True)
    service_drop = runtime / (name + ".service.d")
    timer_drop = runtime / (name + ".timer.d")
    require(not service_drop.exists() and not timer_drop.exists(), "Acceptance unit identity already exists.")
    injection = root / "injection"
    injection.mkdir(mode=0o700)
    (injection / "sitecustomize.py").write_text(
        "import os\nfrom tests.operations_worker import install\ninstall(os.environ['XTI_OPERATIONS_CONTROL'])\n")
    service_drop.mkdir(mode=0o700)
    timer_drop.mkdir(mode=0o700)
    from xti.adapters.systemd_schedule import unit_argument
    overrides = {"XTI_OPERATIONS_CONTROL": str(control), "XTI_PYTHON": sys.executable,
                 "PYTHONPATH": os.pathsep.join((str(injection), str(PROJECT))),
                 "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    (service_drop / "acceptance.conf").write_text("[Service]\n" + "".join(
        "Environment=" + unit_argument(key + "=" + value, environment=False) + "\n"
        for key, value in overrides.items()))
    database = Path(environment["XTI_DATA_DIR"]) / "xti.db"
    ctl = lambda *args, **kw: run(["systemctl", "--user", *args], environment, **kw)
    service, timer = name + ".service", name + ".timer"
    try:
        ctl("link", "--runtime", generated["service_file"], generated["timer_file"])
        ctl("daemon-reload")
        ctl("start", service)
        require(collection_states(database)[-1][1] == "complete", "Real service collection did not complete.")
        require(len(tuple((database.parent / "scheduled-backups").glob("scheduled-*.db"))) == 1,
                "Generated service did not perform its real pre-start backup.")
        # Busy failure occurs in ExecStartPre, so no new collection can begin.
        before = collection_states(database)
        with LocalExecutionLock(database).acquire():
            ctl("start", service, expected=1)
        require(collection_states(database) == before, "Busy service created a collection.")
        ctl("reset-failed", service)
        mode(control, "503")
        ctl("start", service, expected=1)
        require(ctl("show", service, "--property=ExecMainStatus", "--value").strip() == "3",
                "Source failure exit code was hidden by systemd.")
        ctl("reset-failed", service)
        mode(control, "block")
        baseline_calls = len(calls(control))
        ctl("start", "--no-block", service)
        wait_until(lambda: len(calls(control)) > baseline_calls, "Blocking collection never started.")
        interrupted = collection_states(database)[-1][0]
        ctl("stop", service)
        mode(control, "success")
        ctl("start", service)
        states = dict(collection_states(database))
        require(states[interrupted] == "interrupted", "Pre-start recovery did not retain interrupted history.")
        require(collection_states(database)[-1][1] == "complete", "Service did not restart successfully.")
        # Two one-shot dates accelerate only the generated timer's calendar.
        # The second date elapses while disabled; Persistent=true must catch it once.
        now = datetime.now(timezone.utc).replace(microsecond=0)
        first, second = now + timedelta(seconds=8), now + timedelta(seconds=24)
        calendar = lambda when: when.strftime("%Y-%m-%d %H:%M:%S UTC")
        (timer_drop / "acceptance.conf").write_text(
            "[Timer]\nOnCalendar=\n" + "".join("OnCalendar=" + calendar(when) + "\n" for when in (first, second))
            + "RandomizedDelaySec=0\nAccuracySec=1us\n")
        ctl("daemon-reload")
        baseline = len(collection_states(database))
        ctl("enable", "--runtime", "--now", timer)
        wait_until(lambda: len(collection_states(database)) == baseline + 1
                   and collection_states(database)[-1][1] == "complete", "Timer did not trigger its first job.", timeout=20)
        ctl("stop", timer)
        wait_until(lambda: datetime.now(timezone.utc) > second + timedelta(seconds=2),
                   "Timer outage did not elapse.", timeout=25)
        require(len(collection_states(database)) == baseline + 1, "Stopped timer still launched work.")
        ctl("start", timer)
        wait_until(lambda: len(collection_states(database)) == baseline + 2
                   and collection_states(database)[-1][1] == "complete", "Persistent timer did not catch the missed event.", timeout=20)
        ctl("disable", "--runtime", "--now", timer)
        time.sleep(2)
        require(len(collection_states(database)) == baseline + 2, "Timer duplicated or continued after disable.")
        require(len(tuple((database.parent / "scheduled-backups").glob("scheduled-*.db"))) == 2,
                "Scheduled retention exceeded its configured two backups.")
        return {"real_user_manager": True, "generated_launcher": True, "stop_restart": True,
                "busy_rejected": True, "source_exit_code": 3, "missed_event_caught_once": True,
                "scope": "accelerated two-date timer; no OS reboot or linger alteration"}
    finally:
        stop_owned_units(environment, service, timer)
        subprocess.run(["systemctl", "--user", "reset-failed", service], env=environment,
                       capture_output=True, timeout=30, check=False)
        for path in (service_drop / "acceptance.conf", timer_drop / "acceptance.conf"):
            path.unlink(missing_ok=True)
        service_drop.rmdir()
        timer_drop.rmdir()
        for unit, target in ((service, generated["service_file"]), (timer, generated["timer_file"])):
            link = runtime / unit
            if link.is_symlink() and link.resolve() == Path(target).resolve():
                link.unlink()
        subprocess.run(["systemctl", "--user", "daemon-reload"], env=environment,
                       capture_output=True, timeout=30, check=False)


def endurance(root, duration):
    control = root / "endurance-control.json"
    environment, _ = seed(root / "endurance-data", control)
    database = Path(environment["XTI_DATA_DIR"]) / "xti.db"
    started = time.monotonic()
    rounds = 0
    largest_database = 0
    while time.monotonic() - started < duration or rounds < 1:
        cli(environment, "schedule", "prepare", "acceptance", "--keep", "2")
        cli(environment, "collect", "--profile", "acceptance")
        state = SQLitePublicNoticeRepository(database).status()
        require(state.latest_run.status == "complete" and state.latest_run.notice_count == 1,
                "Endurance collection lost its source evidence.")
        rounds += 1
        require(len(collection_states(database)) == rounds, "Endurance collection count diverged.")
        require(len(calls(control)) == rounds, "Endurance repeated a source unexpectedly.")
        require(len(tuple((database.parent / "scheduled-backups").glob("scheduled-*.db"))) <= 2,
                "Endurance retention grew beyond its configured limit.")
        largest_database = max(largest_database, database.stat().st_size)
        require(largest_database < 128 * 1024 ** 2, "Synthetic endurance database exceeded 128 MiB.")
        elapsed = time.monotonic() - started
        if rounds % 4 == 0:
            summary(f"- Endurance progress: {rounds} rounds, {elapsed:.1f}/{duration}s.")
        remaining = duration - elapsed
        if remaining > 0:
            time.sleep(min(10, remaining))
    with closing(sqlite3.connect(database)) as connection:
        require(connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "Endurance SQLite integrity failed.")
        require(connection.execute("SELECT COUNT(*) FROM public_notice_changes").fetchone()[0] == 1,
                "Unchanged source generated duplicate changes during endurance.")
    return {"requested_seconds": duration, "elapsed_seconds": time.monotonic() - started,
            "rounds": rounds, "largest_database_bytes": largest_database,
            "scope": "repeated bounded local subprocesses; not a 24/7 or always-resident-worker claim"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=int, default=600)
    parser.add_argument("--low-disk-directory", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    require(60 <= args.duration_seconds <= 3600, "Duration must be 60–3600 seconds.")
    require(not args.report.exists() and not args.report.is_symlink(), "Report destination must be new.")
    require(sys.platform == "linux", "This acceptance must run on real Linux.")
    report = {"platform": platform.platform(), "python": platform.python_version(),
              "budgets": {"source_or_cli_command_seconds": 60, "search_seconds": 60,
                          "backup_restore_seconds": 120, "child_peak_rss_bytes": 1024 ** 3,
                          "endurance_database_bytes": 128 * 1024 ** 2,
                          "domain_sizes": [100, 1000, 5000], "duration_seconds": args.duration_seconds},
              "status": "failed", "results": {}}
    stage = "preconditions"
    code = 1
    try:
        validate_low_disk_mount(args.low_disk_directory)
        summary(f"### Linux operations acceptance ({platform.machine()}, Python {platform.python_version()})")
        summary("- Budgets: domains 100/1000/5000; search <60s; backup/restore <120s; child high-water RSS <1GiB.")
        summary(f"- Endurance: {args.duration_seconds}s, each CLI <60s, synthetic database <128MiB, retained backups <=2.")
        root = Path(tempfile.mkdtemp(prefix="xti-linux-operations-", dir=os.environ.get("RUNNER_TEMP")))
        cleanup_confirmed = True
        try:
            for stage, operation in (("source_outages", lambda: source_outages(root)),
                                     ("capacity", lambda: capacity(root)),
                                     ("low_disk", lambda: low_disk(args.low_disk_directory)),
                                     ("systemd", lambda: systemd_acceptance(root)),
                                     ("endurance", lambda: endurance(root, args.duration_seconds))):
                report["results"][stage] = operation()
                summary(f"- PASS: {stage}")
                summary("```json\n" + json.dumps(report["results"][stage], ensure_ascii=False, indent=2) + "\n```")
        except UnconfirmedCleanup:
            cleanup_confirmed = False
            report["preserved_workspace"] = str(root)
            raise
        finally:
            if cleanup_confirmed:
                shutil.rmtree(root)
            else:
                summary(f"- Preserved acceptance workspace; shutdown unconfirmed: {root}")
        report["status"] = "passed"
        code = 0
    except (OSError, RuntimeError, ValueError, KeyError, StorageError, subprocess.TimeoutExpired) as error:
        report["error"] = {"stage": stage, "message": str(error)}
        summary(f"- FAIL: {stage}: {error}")
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
