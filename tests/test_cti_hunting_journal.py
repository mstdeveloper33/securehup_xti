"""Saved CTI searches keep sourced runs separate from append-only analyst work."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_hunting_journal import SQLiteCtiHuntingJournalRepository
from xti.adapters.sqlite_cti_saved_searches import SQLiteCtiSavedSearchRepository
from xti.application.cti_hunting_journal import CtiHuntingJournalService
from xti.application.cti_saved_searches import CtiSavedSearchService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)


class CtiHuntingJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.clock_value = NOW
        self.saved = CtiSavedSearchService(
            SQLiteCtiSavedSearchRepository(self.path), clock=lambda: self.clock_value,
        )
        self.journal = CtiHuntingJournalService(
            SQLiteCtiHuntingJournalRepository(self.path), clock=lambda: self.clock_value,
        )

    def advance(self):
        self.clock_value += timedelta(minutes=1)

    def test_tag_lifecycle_is_idempotent_reversible_and_append_only(self):
        watch = self.saved.add("Example watch", "Example")
        added = self.journal.add_tag(watch.saved_search.id, "priority:high")
        repeated = self.journal.add_tag(watch.saved_search.id, "priority:high")
        self.advance()
        updated = self.journal.add_tag(watch.saved_search.id, "Priority:High")
        self.advance()
        removed = self.journal.remove_tag(watch.saved_search.id, "priority:high")
        repeated_remove = self.journal.remove_tag(watch.saved_search.id, "priority:high")
        self.advance()
        reactivated = self.journal.add_tag(watch.saved_search.id, "priority:high")

        self.assertEqual(
            [added.action, repeated.action, updated.action, removed.action,
             repeated_remove.action, reactivated.action],
            ["added", "unchanged", "updated", "removed", "unchanged", "reactivated"],
        )
        report = self.journal.journal(watch.saved_search.id)
        self.assertEqual([tag.display_tag for tag in report.tags], ["priority:high"])
        self.assertEqual(
            [event.action for event in reversed(report.tag_events)],
            ["added", "updated", "removed", "reactivated"],
        )

    def test_general_and_run_notes_keep_search_binding_and_do_not_reset_diff_baseline(self):
        watch = self.saved.add("Example watch", "Example")
        other = self.saved.add("Other watch", "Other")
        first = self.saved.run(watch.saved_search.id)
        other_run = self.saved.run(other.saved_search.id)
        self.advance()
        general = self.journal.add_note(
            watch.saved_search.id, "No current match; retain for periodic review.",
            note_kind="observation",
        )
        linked = self.journal.add_note(
            watch.saved_search.id, "Baseline reviewed and accepted.",
            note_kind="conclusion", run_id=first.run.id,
        )
        with self.assertRaisesRegex(ValidationError, "bu kayıtlı aramaya ait değil"):
            self.journal.add_note(
                watch.saved_search.id, "Wrong evidence link.", run_id=other_run.run.id,
            )
        second = self.saved.run(watch.saved_search.id)

        self.assertIsNone(general.run_id)
        self.assertEqual(linked.run_id, first.run.id)
        self.assertEqual(second.run.previous_run_id, first.run.id)
        report = self.journal.journal(watch.saved_search.id, note_limit=1)
        self.assertEqual((report.total_note_count, len(report.notes)), (2, 1))
        self.assertEqual(report.notes[0].id, linked.id)

    def test_invalid_values_and_missing_records_do_not_write(self):
        watch = self.saved.add("Example watch", "Example")
        before = self.path.read_bytes()
        for call in (
            lambda: self.journal.add_tag(watch.saved_search.id, "bad tag"),
            lambda: self.journal.add_note(watch.saved_search.id, "x"),
            lambda: self.journal.journal(watch.saved_search.id, note_limit=0),
            lambda: self.journal.remove_tag(watch.saved_search.id, "missing"),
        ):
            with self.assertRaises(ValidationError):
                call()
        self.assertEqual(self.path.read_bytes(), before)

    def test_hidden_corrupt_note_or_tag_history_fails_closed_without_repair(self):
        watch = self.saved.add("Example watch", "Example")
        self.journal.add_tag(watch.saved_search.id, "priority:high")
        note = self.journal.add_note(watch.saved_search.id, "Review this evidence later.")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE cti_saved_search_notes SET body=? WHERE id=?", ("x", note.id),
            )
        corrupt = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "avcılık notu bozuk"):
            self.journal.journal(watch.saved_search.id)
        self.assertEqual(self.path.read_bytes(), corrupt)

    def test_backup_restore_and_inspection_preserve_journal(self):
        watch = self.saved.add("Example watch", "Example")
        self.journal.add_tag(watch.saved_search.id, "campaign:example")
        self.journal.add_note(watch.saved_search.id, "Initial hunting hypothesis.",
                              note_kind="hypothesis")
        counts = SQLiteAssetRepository(self.path).inspect()
        self.assertEqual(
            (counts["cti_saved_search_tag_count"],
             counts["active_cti_saved_search_tag_count"],
             counts["cti_saved_search_note_count"]),
            (1, 1, 1),
        )
        backup = Path(self.temp.name) / "journal-backup.db"
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository(self.path).backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        report = CtiHuntingJournalService(
            SQLiteCtiHuntingJournalRepository(restored),
        ).journal(watch.saved_search.id)
        self.assertEqual((report.tags[0].display_tag, report.total_note_count),
                         ("campaign:example", 1))

    def call_cli(self, *arguments):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_tag_note_and_journal_flow(self):
        self.clock_value = datetime.now(timezone.utc)
        watch = self.saved.add("Example watch", "Example")
        code, output, error = self.call_cli(
            "cti", "watch-tag-add", watch.saved_search.id, "priority:high",
        )
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(json.loads(output)["data"]["action"], "added")
        code, output, error = self.call_cli(
            "cti", "watch-note-add", watch.saved_search.id,
            "--kind", "hypothesis", "--text", "Possible campaign relationship.",
        )
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(json.loads(output)["data"]["note_kind"], "hypothesis")
        code, output, error = self.call_cli(
            "cti", "watch-journal", watch.saved_search.id,
        )
        self.assertEqual((code, error), (0, ""))
        data = json.loads(output)["data"]
        self.assertEqual((data["total_tag_count"], data["total_note_count"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
