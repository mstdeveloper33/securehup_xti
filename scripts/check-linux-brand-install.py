#!/usr/bin/env python3
"""Clean Ubuntu brand-tool acceptance in a disposable checkout.

Launch this script with bootstrap-python, never the managed environment launcher:
the acceptance parent must not hold the shared environment lock while installing.
All engine records are temporary; no social lookup or target collection runs.
"""

import importlib.util
import json
import os
from pathlib import Path
import platform
import stat
import sys
import tempfile


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "xti_linux_acceptance", PROJECT / "scripts/check-linux-install.py"
)
COMMON = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMMON)


def fresh_brand_checkout(project):
    COMMON.require(sys.platform == "linux", "Acceptance requires a real Linux host.")
    leftovers = tuple(project.glob(".venv*")) + tuple(
        path for path in project.glob(".brand-install.*") if path.name != ".brand-install.lock"
    )
    COMMON.require(not leftovers,
                   "Brand acceptance requires a disposable checkout without an existing environment or installation state.")
    lock = project / ".brand-install.lock"
    if os.path.lexists(lock):
        metadata = lock.lstat()
        COMMON.require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1,
                       "The existing installation lock must be a single-link regular file.")


def environment_snapshot(directory):
    """Include symlink targets and executable permissions without following links."""
    import hashlib

    metadata = directory.lstat()
    COMMON.require(stat.S_ISDIR(metadata.st_mode), "The brand environment must be a real directory.")
    identity = (metadata.st_dev, metadata.st_ino)
    result = {}
    for path in sorted(directory.rglob("*")):
        relative = str(path.relative_to(directory))
        metadata = path.lstat()
        mode = stat.S_IMODE(metadata.st_mode)
        if stat.S_ISLNK(metadata.st_mode):
            result[relative] = ("link", mode, os.readlink(path))
        elif stat.S_ISDIR(metadata.st_mode):
            result[relative] = ("directory", mode)
        elif stat.S_ISREG(metadata.st_mode):
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            result[relative] = ("file", mode, metadata.st_size, digest)
        else:
            raise RuntimeError("Unexpected special file in the brand environment.")
    return (*identity, result)


def repeat_environment(directory, environment):
    """Block Git and pip executable calls; this is not an OS network sandbox.

The installer uses python -m pip. Its no-install repeat behavior is checked by
the environment snapshot here and isolated fake-pip regression tests separately.
"""
    directory.mkdir()
    guard = f"#!{sys.executable}\nraise SystemExit('Acceptance blocked a downloader executable during repeat.')\n"
    for name in ("git", "pip", "pip3"):
        path = directory / name
        path.write_text(guard, encoding="utf-8")
        path.chmod(0o700)
    return dict(environment, PATH=str(directory) + os.pathsep + environment.get("PATH", ""))


def local_round_trip(environment, root):
    COMMON.local_asset(environment)
    backup = root / "brand-acceptance.db"
    COMMON.run(["./xti", "backup", "--output", str(backup)], environment)
    restored = dict(environment, XTI_DATA_DIR=str(root / "restored"))
    COMMON.run(["./xti", "restore", str(backup)], restored)
    COMMON.local_asset(restored)


def main():
    stage = "fresh Linux checkout guard"
    try:
        fresh_brand_checkout(PROJECT)
        COMMON.summary(f"### Clean Linux brand acceptance ({platform.machine()}, Python {platform.python_version()})")
        with tempfile.TemporaryDirectory(prefix="xti-linux-brand-", dir=os.environ.get("RUNNER_TEMP")) as temporary:
            root = Path(temporary)
            data = root / "data"
            environment = dict(os.environ, XTI_DATA_DIR=str(data), XTI_PYTHON=sys.executable,
                               PYTHONDONTWRITEBYTECODE="1")
            stage = "core seed before tool installation"
            COMMON.run(["./setup", "--core-only"], environment)
            COMMON.run(["./xti", "assets", "add", "example.com"], environment)
            evidence = data / "brand-acceptance-evidence.bin"
            evidence.write_bytes(b"Synthetic evidence retained across tool installation.\x00\xff\n")
            before = COMMON.snapshot(data)
            COMMON.require("xti.db" in before, "Core setup did not create the database.")
            COMMON.summary("- PASS: temporary example.com record and synthetic evidence created before installation.")

            stage = "real full setup with pinned brand tools"
            COMMON.run(["./setup"], environment, timeout=900)
            COMMON.require(COMMON.snapshot(data) == before, "Full setup changed existing data bytes.")
            COMMON.summary("- PASS: real full setup; original database and evidence hashes preserved.")

            # Exercise the actual default launcher selection after installation.
            environment.pop("XTI_PYTHON", None)
            stage = "managed environment and component verification"
            actual_prefix = COMMON.run(
                ["./scripts/python", "-c", "import sys; print(sys.prefix)"], environment
            ).strip()
            venv = PROJECT / ".venv"
            COMMON.require(Path(actual_prefix).resolve() == venv.resolve(),
                           "The default launcher did not select the managed environment.")
            tool_python = COMMON.run(
                ["./scripts/python", "-c", "import platform; print(platform.python_version())"], environment
            ).strip()
            COMMON.require(tuple(map(int, tool_python.split(".")[:2])) == sys.version_info[:2],
                           "The installed brand environment did not use the requested acceptance Python.")
            COMMON.summary(f"- Actual installed brand-tool Python: {tool_python}; acceptance Python: {platform.python_version()}.")
            components = json.loads(COMMON.run(["./xti", "--json", "components"], environment))["data"]
            rows = {row["identifier"]: row for row in components["components"]}
            for name in ("maigret", "sherlock"):
                COMMON.require(rows[name]["installation"]["state"] == "ready",
                               f"Component inventory did not recognize {name}.")
            installed = environment_snapshot(venv)

            stage = "local check and repeat with downloader executables blocked"
            repeat = repeat_environment(root / "repeat-guards", environment)
            for arguments in (["./scripts/setup-brand", "--check"], ["./scripts/verify-brand"],
                              ["./scripts/setup-brand"], ["./setup"]):
                COMMON.run(arguments, repeat, timeout=120)
                COMMON.require(environment_snapshot(venv) == installed,
                               "Local verification or repeat replaced or changed the installed environment.")
                COMMON.require(COMMON.snapshot(data) == before,
                               "Local verification or repeat changed original data bytes.")
            COMMON.summary("- PASS: --check, verify-brand, default tool repeat and full setup repeat; environment inode/files and data hashes unchanged.")
            COMMON.summary("- Scope: Git/pip executables were blocked; python -m pip no-install behavior is covered by offline installer regressions, not an OS network sandbox.")

            stage = "engine read and backup/restore from the managed environment"
            COMMON.run(["./xti", "engine", "--describe"], environment)
            local_round_trip(environment, root)
            COMMON.require(COMMON.snapshot(data) == before,
                           "Engine reads or backup/restore changed original data bytes.")
            COMMON.summary("- PASS: engine search/record and backup restored to a new directory using the managed environment.")
        COMMON.summary("- RESULT: PASS for this brand installation chain; no username search, source collection or active scan ran.")
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, COMMON.subprocess.TimeoutExpired) as error:
        COMMON.summary(f"- RESULT: FAIL at {stage}: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
