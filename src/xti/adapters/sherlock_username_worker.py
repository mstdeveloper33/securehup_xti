"""Isolated minimal runner for the pinned Sherlock library function."""

import argparse
import json
import os
from pathlib import Path
import sys


MAX_DATABASE_BYTES = 64 * 1024
MAX_SITES = 8


def _load_database(path: Path) -> dict:
    with path.open("rb") as stream:
        payload = stream.read(MAX_DATABASE_BYTES + 1)
    if not 1 <= len(payload) <= MAX_DATABASE_BYTES:
        raise ValueError("invalid scoped database size")
    data = json.loads(payload)
    if not isinstance(data, dict) or not 1 <= len(data) <= MAX_SITES:
        raise ValueError("invalid scoped database")
    if not all(
        isinstance(key, str) and isinstance(value, dict)
        for key, value in data.items()
    ):
        raise ValueError("invalid scoped database entries")
    return data


def _write_report(path: Path, username: str, sites: dict, results: dict) -> None:
    from sherlock_project.result import QueryStatus

    if set(results) != set(sites):
        raise ValueError("incomplete Sherlock result")
    lines = []
    allowed = {
        QueryStatus.CLAIMED,
        QueryStatus.AVAILABLE,
        QueryStatus.UNKNOWN,
        QueryStatus.ILLEGAL,
        QueryStatus.WAF,
    }
    for platform in sites:
        item = results.get(platform)
        if not isinstance(item, dict):
            raise ValueError("invalid Sherlock result")
        status = item.get("status")
        if (
            status is None
            or status.status not in allowed
            or status.username != username
            or status.site_name != platform
        ):
            raise ValueError("invalid Sherlock status")
        profile_url = status.site_url_user if status.status is QueryStatus.CLAIMED else None
        lines.append(json.dumps({
            "username": username,
            "platform": platform,
            "profile_url": profile_url,
            "status": str(status.status),
        }, ensure_ascii=True, separators=(",", ":")))
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--username", required=True)
    parser.add_argument("--timeout", required=True, type=int)
    parser.add_argument("--database", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    if not 5 <= args.timeout <= 30:
        return 2
    try:
        from sherlock_project import __version__
        from sherlock_project.notify import QueryNotify
        from sherlock_project.sherlock import sherlock

        if __version__ != "0.16.2":
            return 2
        sites = _load_database(Path(args.database))
        results = sherlock(
            args.username,
            sites,
            QueryNotify(),
            dump_response=False,
            proxy=None,
            timeout=args.timeout,
        )
        _write_report(Path(args.report), args.username, sites, results)
    except Exception:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
