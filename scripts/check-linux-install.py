#!/usr/bin/env python3
"""Real Linux clean-install acceptance; requires a fresh, disposable checkout.

Downloads only the pinned toolchain. All engine commands use temporary local
example data; no collector or target scan is invoked. Existing .tools is refused.
"""

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile


PROJECT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def fresh_linux_checkout(project):
    require(sys.platform == "linux", "Acceptance requires a real Linux host.")
    require(not os.path.lexists(project / ".tools"),
            "Acceptance requires a disposable checkout without an existing .tools directory.")


def snapshot(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "Unexpected symlink in acceptance data.")
        if path.is_file():
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            result[str(path.relative_to(directory))] = (path.stat().st_size, digest)
    return result


def run(arguments, environment, *, payload=None, timeout=90):
    process = subprocess.Popen(arguments, cwd=PROJECT, env=environment, text=True,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        output, errors = process.communicate(payload if payload is not None else "", timeout=timeout)
    except BaseException:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise
    require(process.returncode == 0,
            f"Command failed ({process.returncode}): {' '.join(arguments)}\n"
            + (output + errors)[-6000:])
    return output


def engine(environment, operation, parameters):
    request = {"contract_version": 1, "request_id": "linux-install:1",
               "operation": operation, "parameters": parameters}
    response = json.loads(run(["./xti", "engine"], environment, payload=json.dumps(request)))
    require(response.get("status") == "complete", f"Engine {operation} did not complete.")
    return response["data"]


def local_asset(environment):
    result = engine(environment, "search", {"query": "example.com", "kinds": ["domain"]})
    require(result["total_match_count"] == 1, "Local example asset was lost or duplicated.")
    reference = result["results"][0]["reference"]
    detail = engine(environment, "record.get", {"reference": reference})
    require(detail["reference"] == reference, "Engine record reference did not round-trip.")
    require(detail["record"]["value"] == "example.com", "Wrong local domain record.")


def offline_tool_environment(directory, environment):
    """Allow only read-only Git metadata commands; refuse every uv invocation."""
    git = shutil.which("git", path=environment.get("PATH"))
    require(git is not None, "git is required for acceptance.")
    directory.mkdir()
    allowed = (("remote", "get-url", "origin"),
               ("status", "--porcelain", "--untracked-files=no"), ("rev-parse", "HEAD"))
    guard = (
        f"#!{sys.executable}\nimport os, sys\n"
        "args = sys.argv[1:]\n"
        f"allowed = {allowed!r}\n"
        "if len(args) < 3 or args[0] != '-C' or tuple(args[2:]) not in allowed:\n"
        "    sys.exit('Acceptance blocked a Git command outside local metadata reads.')\n"
        f"os.execv({git!r}, [{git!r}, *args])\n"
    )
    (directory / "git").write_text(guard, encoding="utf-8")
    (directory / "uv").write_text(
        f"#!{sys.executable}\nraise SystemExit('Acceptance blocked uv during local recheck.')\n",
        encoding="utf-8",
    )
    for name in ("git", "uv"):
        (directory / name).chmod(0o700)
    return dict(environment, PATH=str(directory) + os.pathsep + environment.get("PATH", ""),
                UV_OFFLINE="1")


def summary(message):
    print(message, flush=True)
    destination = os.environ.get("GITHUB_STEP_SUMMARY")
    if destination:
        with open(destination, "a", encoding="utf-8") as stream:
            stream.write(message + "\n")


def main():
    stage = "fresh Linux checkout guard"
    try:
        fresh_linux_checkout(PROJECT)
        summary(f"### Clean Linux acceptance ({platform.machine()}, Python {platform.python_version()})")
        with tempfile.TemporaryDirectory(prefix="xti-linux-acceptance-",
                                         dir=os.environ.get("RUNNER_TEMP")) as temporary:
            root = Path(temporary)
            data = root / "data"
            environment = dict(os.environ, XTI_DATA_DIR=str(data), XTI_PYTHON=sys.executable,
                               UV_CACHE_DIR=str(root / "uv-cache"),
                               UV_PYTHON_INSTALL_DIR=str(root / "python"),
                               UV_PYTHON_BIN_DIR=str(root / "python-bin"))
            stage = "core-only setup and local seed"
            run(["./setup", "--core-only"], environment)
            run(["./xti", "assets", "add", "example.com"], environment)
            evidence = data / "evidence" / "acceptance-marker.bin"
            evidence.parent.mkdir()
            evidence.write_bytes(b"Synthetic local evidence preservation marker.\x00\xff\n")
            before = snapshot(data)
            require("xti.db" in before, "Setup did not create the expected database.")
            summary("- PASS: core-only setup; local example.com and synthetic evidence created.")

            stage = "real pinned theHarvester installation"
            run(["./scripts/setup-harvester"], environment, timeout=1020)
            require(snapshot(data) == before, "Tool installation changed local data bytes.")
            summary("- PASS: real pinned theHarvester installation; all data file hashes preserved.")

            stage = "download-blocked check and default repeat"
            offline = offline_tool_environment(root / "offline-tools", environment)
            run(["./scripts/setup-harvester", "--check"], offline, timeout=120)
            run(["./scripts/setup-harvester"], offline, timeout=120)
            require(snapshot(data) == before, "Repeated tool verification changed local data bytes.")
            summary("- PASS: --check and default repeat with Git downloads and uv execution blocked.")

            stage = "engine, component and repeated core setup checks"
            run(["./xti", "engine", "--describe"], environment)
            local_asset(environment)
            components = json.loads(run(["./xti", "--json", "components"], environment))["data"]
            rows = {row["identifier"]: row for row in components["components"]}
            require(rows["theharvester"]["installation"]["state"] == "ready",
                    "Component inventory did not recognize the installed theHarvester pin.")
            run(["./setup", "--core-only"], environment)
            local_asset(environment)
            require(snapshot(data) == before, "Local reads or repeated setup changed local data bytes.")
            summary("- PASS: engine search/record, component inventory and repeated core setup.")

            stage = "SQLite backup and restore into a new directory"
            backup = root / "acceptance.db"
            run(["./xti", "backup", "--output", str(backup)], environment)
            restored = dict(environment, XTI_DATA_DIR=str(root / "restored"))
            run(["./xti", "restore", str(backup)], restored)
            local_asset(restored)
            require(snapshot(data) == before, "Backup/restore changed original data bytes.")
            summary("- PASS: SQLite backup restored into a new directory; local asset round-tripped.")
        summary("- RESULT: PASS for this clean-install chain; no source collection or target scan ran.")
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        summary(f"- RESULT: FAIL at {stage}: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
