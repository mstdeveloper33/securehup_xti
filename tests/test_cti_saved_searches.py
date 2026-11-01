"""Durable CTI searches preserve definitions and complete difference snapshots."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.adapters.sqlite_cti_saved_searches import SQLiteCtiSavedSearchRepository
from xti.application.cti_indicators import CtiIndicatorService
from xti.application.cti_knowledge import CtiKnowledgeService
from xti.application.cti_saved_searches import CtiSavedSearchService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 30, 15, tzinfo=timezone.utc)


class CtiSavedSearchTests(unittest.TestCase):
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
        self.knowledge = CtiKnowledgeService(
            SQLiteCtiKnowledgeRepository(self.path), clock=lambda: self.clock_value,
        )
        self.indicators = CtiIndicatorService(
            SQLiteCtiIndicatorRepository(self.path), clock=lambda: self.clock_value,
        )

    def advance(self):
        self.clock_value += timedelta(minutes=1)

    def entity(self, name="Example RAT", *, source="source-a", reference="local:a"):
        return self.knowledge.add_entity(
            "malware", name, aliases=("Example Loader",), source_name=source,
            source_reference=reference, confidence=75,
            description="Kaynaklı kayıtlı CTI arama kabul testi örneği.",
        )

    def test_definition_lifecycle_is_idempotent_reversible_and_audited(self):
        added = self.saved.add("Example watch", "Example", kind="entity")
        repeated = self.saved.add("Example watch", "Example", kind="entity")
        self.assertEqual((added.action, repeated.action), ("added", "unchanged"))
        self.assertEqual(added.saved_search.id, repeated.saved_search.id)
        self.advance()
        changed = self.saved.add("Example watch", "Loader", kind="entity")
        self.assertEqual(changed.action, "updated")
        self.advance()
        revoked = self.saved.revoke(
            added.saved_search.id, reason="Bu arama artık kişisel izleme kapsamında değil.",
        )
        self.assertEqual((revoked.action, revoked.saved_search.active), ("revoked", False))
        self.assertEqual(self.saved.list(), ())
        self.assertEqual(len(self.saved.list(active_only=False)), 1)
        self.advance()
        reactivated = self.saved.add("Example watch", "Example", kind="entity")
        self.assertEqual((reactivated.action, reactivated.saved_search.active),
                         ("reactivated", True))
        details = self.saved.show(added.saved_search.id)
        self.assertEqual(details.total_event_count, 4)
        self.assertEqual(
            [event.action for event in reversed(details.events)],
            ["added", "updated", "revoked", "reactivated"],
        )

    def test_runs_classify_added_updated_unchanged_and_removed(self):
        watch = self.saved.add("Example watch", "Example")
        entity = self.entity()
        first = self.saved.run(watch.saved_search.id)
        self.assertEqual((first.run.added_count, first.run.total_count), (1, 1))
        second = self.saved.run(watch.saved_search.id)
        self.assertEqual((second.run.unchanged_count, second.run.previous_run_id),
                         (1, first.run.id))

        self.advance()
        another = self.entity(source="source-b", reference="local:b")
        self.assertEqual(another.entity.id, entity.entity.id)
        changed = self.saved.run(watch.saved_search.id)
        self.assertEqual((changed.run.updated_count, changed.run.total_count), (1, 1))

        self.advance()
        self.knowledge.revoke_entity(
            entity.assertion.id, reason="İlk kaynak bu iddiayı geri çekti.",
        )
        self.knowledge.revoke_entity(
            another.assertion.id, reason="İkinci kaynak bu iddiayı geri çekti.",
        )
        removed = self.saved.run(watch.saved_search.id)
        self.assertEqual(
            (removed.run.total_count, removed.run.removed_count,
             removed.items[0].action, removed.items[0].record_id),
            (0, 1, "removed", entity.entity.id),
        )
        shown = self.saved.show_run(removed.run.id)
        self.assertEqual(shown, removed)

    def test_ioc_results_and_changed_definition_reset_the_baseline(self):
        self.indicators.add(
            "domain", "example-c2.net", source_name="manual",
            source_reference="local:example-c2", confidence=70,
            description="Kayıtlı arama için kaynaklı örnek IOC kaydı.",
        )
        watch = self.saved.add("C2 watch", "example", kind="indicator")
        first = self.saved.run(watch.saved_search.id)
        self.assertEqual(first.run.added_count, 1)
        self.advance()
        updated = self.saved.add("C2 watch", "c2", kind="indicator")
        changed = self.saved.run(updated.saved_search.id)
        self.assertEqual((changed.run.added_count, changed.run.previous_run_id), (1, None))
        self.advance()
        reverted = self.saved.add("C2 watch", "example", kind="indicator")
        reset = self.saved.run(reverted.saved_search.id)
        self.assertEqual((reset.run.added_count, reset.run.previous_run_id), (1, None))

    def test_invalid_requests_and_inactive_run_do_not_write(self):
        before = self.path.read_bytes()
        for call in (
            lambda: self.saved.add("x", "Example"),
            lambda: self.saved.add("Valid name", "Example", kind="entity",
                                   indicator_type="domain"),
            lambda: self.saved.list(limit=0),
        ):
            with self.assertRaises(ValidationError):
                call()
        self.assertEqual(self.path.read_bytes(), before)
        watch = self.saved.add("Example watch", "Example")
        self.advance()
        self.saved.revoke(watch.saved_search.id, reason="İzleme artık gerekli değil.")
        stopped = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.saved.run(watch.saved_search.id)
        self.assertEqual(self.path.read_bytes(), stopped)

    def test_hidden_history_corruption_fails_closed_without_repairing_it(self):
        watch = self.saved.add("Example watch", "Example")
        self.entity()
        run = self.saved.run(watch.saved_search.id)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE cti_saved_search_run_items SET state_sha256=? WHERE run_id=?",
                ("f" * 64, run.run.id),
            )
        corrupt = self.path.read_bytes()
        for call in (
            lambda: self.saved.list(),
            lambda: self.saved.show(watch.saved_search.id),
            lambda: self.saved.show_run(run.run.id),
        ):
            with self.assertRaisesRegex(StorageError, "özeti bozuk"):
                call()
        self.assertEqual(self.path.read_bytes(), corrupt)

    def test_failed_item_insert_rolls_back_the_run_header(self):
        watch = self.saved.add("Example watch", "Example")
        self.entity("Example One", source="one", reference="local:one")
        self.entity("Example Two", source="two", reference="local:two")
        fixed = UUID("11111111-1111-4111-8111-111111111111")
        with patch("xti.adapters.sqlite_cti_saved_searches.uuid4", return_value=fixed):
            with self.assertRaises(StorageError):
                self.saved.run(watch.saved_search.id)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM cti_saved_search_runs"
            ).fetchone()[0], 0)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM cti_saved_search_run_items"
            ).fetchone()[0], 0)

    def test_backup_restore_and_inspection_preserve_definition_and_run(self):
        watch = self.saved.add("Example watch", "Example")
        self.entity()
        run = self.saved.run(watch.saved_search.id)
        storage = SQLiteAssetRepository(self.path)
        counts = storage.inspect()
        self.assertEqual(
            (counts["cti_saved_search_count"], counts["active_cti_saved_search_count"],
             counts["cti_saved_search_run_count"]),
            (1, 1, 1),
        )
        backup = Path(self.temp.name) / "saved-search-backup.db"
        restored = Path(self.temp.name) / "restored" / "xti.db"
        storage.backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        service = CtiSavedSearchService(SQLiteCtiSavedSearchRepository(restored))
        self.assertEqual(service.show_run(run.run.id).run.result_sha256,
                         run.run.result_sha256)

    def call_cli(self, *arguments):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_json_add_list_run_show_and_revoke(self):
        self.entity()
        code, output, error = self.call_cli(
            "cti", "watch-add", "Example watch", "Example", "--kind", "entity",
        )
        self.assertEqual((code, error), (0, ""))
        saved_id = json.loads(output)["data"]["saved_search"]["id"]
        code, output, error = self.call_cli("cti", "watch-run", saved_id)
        self.assertEqual((code, error), (0, ""))
        run_id = json.loads(output)["data"]["run"]["id"]
        code, output, error = self.call_cli("cti", "watch-run-show", run_id)
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(json.loads(output)["data"]["run"]["added_count"], 1)
        code, output, error = self.call_cli("cti", "watch-list")
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(len(json.loads(output)["data"]["records"]), 1)
        code, output, error = self.call_cli(
            "cti", "watch-revoke", saved_id, "--reason", "Bu izleme artık gerekli değil.",
        )
        self.assertEqual((code, error), (0, ""))
        self.assertFalse(json.loads(output)["data"]["saved_search"]["active"])


if __name__ == "__main__":
    unittest.main()
