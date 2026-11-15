"""STB-03: mixed evidence recovery and actual process-death acceptance.

Coverage: all ten engine search families, finding/social human reviews, case
links, organization links, inbox read state, collection/scan history. This is
not a claim that every optional legacy module or hardware failure was tested.
"""

from contextlib import closing
import json
import os
from pathlib import Path
import select
import signal
import sqlite3
import subprocess
import sys
import unittest

from xti.domain.global_search import GLOBAL_SEARCH_KINDS
from tests import test_collection_watch_cli as watch_fixtures
from tests import test_engine_records as record_fixtures
from tests import test_global_search as search_fixtures
from tests.stabilization_fixture import database_snapshot


PROJECT = Path(__file__).resolve().parents[1]


class StabilizationDataTests(unittest.TestCase):
    invoke = watch_fixtures.CollectionWatchCLITests.invoke
    result = watch_fixtures.CollectionWatchCLITests.result
    files = watch_fixtures.CollectionWatchCLITests.files
    add_social = watch_fixtures.CollectionWatchCLITests.add_social
    collect = search_fixtures.GlobalSearchTests.collect
    notice = search_fixtures.GlobalSearchTests.notice
    save_notices = search_fixtures.GlobalSearchTests.save_notices
    save_claims = search_fixtures.GlobalSearchTests.save_claims
    entity = search_fixtures.GlobalSearchTests.entity
    ioc = search_fixtures.GlobalSearchTests.ioc
    supplier = search_fixtures.GlobalSearchTests.supplier
    create_case = search_fixtures.GlobalSearchTests.create_case
    seed_all = record_fixtures.EngineRecordTests.seed_all

    def setUp(self):
        search_fixtures.GlobalSearchTests.setUp(self)
        self.environment = dict(os.environ, PYTHONPATH=os.pathsep.join((str(PROJECT / "src"), str(PROJECT))),
                                PYTHONDONTWRITEBYTECODE="1")
        # Each test owns a fresh TemporaryDirectory from the existing fixture.
        self.root = self.data.parent

    def command(self, *arguments, data=None, phase="normal", payload=None, expected=0):
        process = subprocess.run(
            [sys.executable, "-m", "tests.stabilization_fixture", str(data or self.data), phase, *arguments],
            cwd=PROJECT, env=self.environment, input=payload or "", text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45,
        )
        self.assertEqual(process.returncode, expected, process.stdout + process.stderr)
        if expected == 0:
            self.assertEqual(process.stderr, "")
        return json.loads(process.stdout or process.stderr)

    def engine(self, operation, parameters, *, data=None, expected=0):
        request = {"contract_version": 1, "request_id": "stabilization:1",
                   "operation": operation, "parameters": parameters}
        response = self.command("engine", payload=json.dumps(request), data=data, expected=expected)
        self.assertEqual(response["status"], "complete" if expected == 0 else "error")
        return response

    def richer_seed(self):
        self.seed_all()
        finding = self.result("findings", "list")["findings"][0]
        self.result("findings", "review", finding["id"], "--decision", "uncertain", "--reason", "Recovery acceptance decision.")
        case = self.create_case("Example linked recovery case")
        self.result("cases", "evidence-add", case.id, "--type", "finding", "--evidence-id", finding["id"], "--reason", "Recovery evidence link.")
        organization = self.result("organizations", "add", "Example linked organization")["organization"]
        self.result("organizations", "link", organization["id"], "--kind", "domain", "--value", "example.com")
        notice = self.result("inbox", "list", "--status", "all")["items"][0]["notification"]
        self.result("inbox", "read", notice["id"])
        social = self.result("brand", "watch-list")["records"][0]["watch"]
        self.result("brand", "watch-review", social["id"], "GitHub", "--decision", "possible_impersonation", "--reason", "Recovery social decision.")
        return case.id

    def test_mixed_ten_families_restore_all_rows_and_engine_records_in_real_cli_processes(self):
        self.richer_seed()
        before = database_snapshot(self.database)
        source_bytes = self.database.read_bytes()
        search = self.engine("search", {"query": "example", "limit": 100})["data"]
        self.assertEqual({hit["reference"]["kind"] for hit in search["results"]}, set(GLOBAL_SEARCH_KINDS))
        references = [hit["reference"] for hit in search["results"]]
        original = [self.engine("record.get", {"reference": ref})["data"] for ref in references]
        backup = self.root / "mixed.db"
        self.command("backup", "--output", str(backup))
        restored = self.root / "restored"
        self.command("restore", str(backup), data=restored)
        self.assertEqual(database_snapshot(restored / "xti.db"), before)
        restored_search = self.engine("search", {"query": "example", "limit": 100}, data=restored)["data"]
        self.assertEqual([hit["reference"] for hit in restored_search["results"]], references)
        for reference, expected in zip(references, original):
            with self.subTest(reference=reference):
                self.assertEqual(self.engine("record.get", {"reference": reference}, data=restored)["data"], expected)
        self.assertEqual(database_snapshot(self.database), before)
        self.assertEqual(self.database.read_bytes(), source_bytes)
        # A second restore cannot overwrite the recovered evidence.
        self.command("restore", str(backup), data=restored, expected=1)
        self.assertEqual(database_snapshot(restored / "xti.db"), before)

    def test_corrupt_backup_and_evidence_do_not_overwrite_sound_data(self):
        case_id = self.richer_seed()
        before = database_snapshot(self.database)
        backup = self.root / "sound.db"
        self.command("backup", "--output", str(backup))
        backup_bytes = backup.read_bytes()
        self.command("backup", "--output", str(backup), expected=1)
        self.assertEqual(backup.read_bytes(), backup_bytes)
        corrupt = self.root / "corrupt.db"
        corrupt.write_bytes(b"incomplete backup fixture")
        destination = self.root / "failed-restore"
        self.command("restore", str(corrupt), data=destination, expected=1)
        self.assertFalse((destination / "xti.db").exists())
        damaged = self.root / "damaged"
        self.command("restore", str(backup), data=damaged)
        with closing(sqlite3.connect(damaged / "xti.db")) as connection, connection:
            connection.execute("UPDATE case_evidence SET snapshot_sha256=? WHERE case_id=?", ("0" * 64, case_id))
        damaged_bytes = (damaged / "xti.db").read_bytes()
        reference = {"kind": "case", "record_type": "case", "namespace": "local-case-management", "record_id": case_id}
        self.engine("record.get", {"reference": reference}, data=damaged, expected=1)
        self.command("cases", "show", case_id, data=damaged, expected=1)
        self.assertEqual((damaged / "xti.db").read_bytes(), damaged_bytes)
        self.assertEqual(database_snapshot(self.database), before)
        self.assertEqual(backup.read_bytes(), backup_bytes)
        recovered = self.root / "recovered"
        self.command("restore", str(backup), data=recovered)
        self.assertEqual(database_snapshot(recovered / "xti.db"), before)

    def start_paused_collection(self, phase):
        child = subprocess.Popen(
            [sys.executable, "-m", "tests.stabilization_fixture", str(self.data), phase,
             "collect", "example.com", "--task", "scan-crtsh", "--task", "discover-crtsh"],
            cwd=PROJECT, env=self.environment, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

        def cleanup():
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)

        self.addCleanup(cleanup)
        ready, _, _ = select.select([child.stdout], [], [], 30)
        self.assertTrue(ready, "Collection fixture did not reach its crash boundary")
        line = child.stdout.readline()
        if line != "READY\n":
            child.kill()
            output, errors = child.communicate(timeout=10)
            self.fail(line + output + errors)
        return child

    def calls(self):
        path = self.root / "source-calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_real_process_death_before_commit_retains_only_missing_work(self):
        self.exercise_crash("before_source", {"scan-crtsh", "discover-crtsh"})

    def test_real_process_death_after_source_receipt_retains_exact_committed_evidence(self):
        self.exercise_crash("after_receipt", {"discover-crtsh"})

    def test_real_process_death_before_outer_finish_reuses_all_source_results(self):
        self.exercise_crash("before_session_finish", set())

    def exercise_crash(self, phase, expected_units):
        child = self.start_paused_collection(phase)
        running = self.command("collections", "list")["data"]["sessions"][0]
        self.assertEqual(running["status"], "running")
        identifier = running["id"]
        at_pause = database_snapshot(self.database)
        # Every competing mutator runs in another actual process.
        for arguments in (("collections", "recover"), ("collections", "resume", identifier),
                          ("collect", "example.com", "--task", "scan-crtsh")):
            self.command(*arguments, expected=4)
            self.assertEqual(database_snapshot(self.database), at_pause)
        # SQLite backup is deliberately allowed: a consistent snapshot can be read
        # while collection holds its ownership lock outside a write transaction.
        backup = self.root / "paused.db"
        self.command("backup", "--output", str(backup))
        self.assertEqual(database_snapshot(backup), at_pause)
        child.kill()
        child.communicate(timeout=10)
        self.assertEqual(child.returncode, -signal.SIGKILL)
        calls_before = self.calls()
        recovered = self.command("collections", "recover")["data"]
        self.assertEqual(recovered["recovered_session_ids"], [identifier])
        self.assertEqual(self.command("collections", "recover")["data"]["recovered_session_ids"], [])
        history = self.command("collections", "show", identifier)["data"]
        plan = self.command("collections", "resume", identifier, "--plan")["data"]
        self.assertEqual({unit["step_key"] for unit in plan["units"]}, expected_units)
        resumed = self.command("collections", "resume", identifier)["data"]["history"]
        self.assertEqual(resumed["session"]["status"], "complete")
        self.assertEqual(resumed["session"]["parent_id"], identifier)
        self.assertEqual({step["step_key"] for step in resumed["steps"]}, expected_units)
        self.assertEqual(resumed["retained"], plan["retained"])
        self.assertEqual(self.command("collections", "show", identifier)["data"], history)
        expected_calls = [] if not expected_units else (["%.example.com"] if phase == "after_receipt" else ["%example%", "example%", "%.example.com"])
        self.assertEqual(self.calls()[len(calls_before):], expected_calls)
        self.assertEqual(len(self.command("findings", "list")["data"]["findings"]), 2)
        notices = self.command("inbox", "list", "--status", "all")["data"]
        self.assertEqual(notices["total_count"], 3)  # Two findings and one discovered subdomain.
        after = database_snapshot(self.database)
        if phase != "before_source":
            for table in ("findings", "observations", "finding_observations", "notifications"):
                with self.subTest(preserved_source_table=table):
                    self.assertEqual(after[1][table], at_pause[1][table])
        self.command("collections", "resume", identifier, expected=2)
        self.assertEqual(database_snapshot(self.database), after)
        self.assertEqual(self.calls(), calls_before + expected_calls)


if __name__ == "__main__":
    unittest.main()
