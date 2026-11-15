"""Offline process fixture for data acceptance; never used by the product.

Only source adapters and explicit crash boundaries are replaced. CLI parsing,
services, transactions, ownership locks and recovery remain the real code.
"""

from contextlib import ExitStack, closing
import json
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch

from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.interfaces.cli import main
from tests.test_discovery import batch, document


def database_snapshot(path):
    """Compare every table/column/value, including IDs and SQLite sequences."""
    with closing(sqlite3.connect(f"{Path(path).absolute().as_uri()}?mode=ro", uri=True)) as connection:
        names = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
        )]
        tables = {}
        for name in names:
            # Names are schema values, quoted as identifiers rather than interpolated SQL.
            quoted = '"' + name.replace('"', '""') + '"'
            cursor = connection.execute("SELECT * FROM " + quoted)
            tables[name] = (tuple(column[0] for column in cursor.description),
                            tuple(sorted(cursor.fetchall(), key=repr)))
        return connection.execute("PRAGMA user_version").fetchone()[0], tables


def wait_for_kill():
    print("READY", flush=True)
    sys.stdin.read()
    raise AssertionError("The controller must kill this paused fixture.")


class RecordedSource:
    def __init__(self, calls, phase):
        self.calls = calls
        self.phase = phase

    def search_url(self, pattern):
        return "https://crt.sh/?fixture=stabilization"

    def search(self, pattern):
        with self.calls.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(pattern) + "\n")
        if self.phase == "before_source":
            wait_for_kill()
        if pattern == "%.example.com":
            return batch(document("portal.example.com", 3))
        return batch(document("example-support.net", 1), document("example-help.net", 2))


def run_cli(data, phase, arguments):
    calls = Path(data).parent / "source-calls.jsonl"
    source = RecordedSource(calls, phase)
    finish = SQLiteJobRepository.finish

    def pause_after_receipt(repository, *args, **kwargs):
        result = finish(repository, *args, **kwargs)
        wait_for_kill()
        return result

    with ExitStack() as stack:
        stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Offline acceptance")))
        stack.enter_context(patch("socket.create_connection", side_effect=AssertionError("Offline acceptance")))
        stack.enter_context(patch("xti.interfaces.cli.CrtShSource", return_value=source))
        stack.enter_context(patch("xti.interfaces.cli.HttpsTargetProbe", side_effect=AssertionError("No target probes")))
        if phase == "after_receipt":
            stack.enter_context(patch.object(SQLiteJobRepository, "finish", pause_after_receipt))
        if phase == "before_session_finish":
            stack.enter_context(patch.object(SQLiteCollectionHistoryRepository, "finish_session", side_effect=lambda *a, **k: wait_for_kill()))
        return main(["--data-dir", str(data), "--json", *arguments])


if __name__ == "__main__":
    raise SystemExit(run_cli(Path(sys.argv[1]), sys.argv[2], sys.argv[3:]))
