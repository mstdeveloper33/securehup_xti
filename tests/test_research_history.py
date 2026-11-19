"""Frozen evidence, conservative deltas, atomic replay and company isolation."""

from contextlib import closing
from copy import deepcopy
from datetime import timedelta
import json
import shlex
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.company_workspaces import provision_company_workspace, disable_company_workspace
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_research_history import SQLiteResearchHistoryRepository, FIELDS
from xti.application.research import priority_data
from xti.application.research_history import ResearchHistoryService
from xti.domain.assets import ValidationError
from xti.domain.research import identity
from xti.domain.research_history import ResearchHistoryError, capture_scope, compare, decode, digest, encode, freeze
from xti.interfaces.research_history import make_history_service, history_lines
from tests.test_research import ResearchFixture, NOW, IP


class ResearchHistoryTests(ResearchFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.repository = SQLiteResearchHistoryRepository(self.path)
        self.history = ResearchHistoryService(self.repository, self.service)

    def record(self, value="example.com", kind="domain", key=None, **options):
        return self.history.record(indicator_type=kind, value=value, idempotency_key=key, **options)

    def detail(self, record, **options):
        return self.history.show(record["review"]["id"], **options)

    def request(self, operation="research.history", **parameters):
        return {"contract_version": 1, "request_id": "review:1", "operation": operation,
                "parameters": parameters}

    def sql(self, statement, args=()):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            return connection.execute(statement, args).fetchall()

    def company(self, root, name):
        from xti.interfaces.platform_jobs import initialize_jobs
        context = provision_company_workspace(root, name)
        SQLiteAssetRepository(context.database).initialize()
        initialize_jobs(context)
        return context

    def test_first_capture_freezes_all_items_not_only_first_page(self):
        self.dns()
        ioc = self.ioc()
        for index in range(12):
            self.relation(self.entity(f"Actor {index}"), indicator=ioc)
        first = self.record()
        self.assertEqual(first["review"]["comparison"]["state"], "baseline")
        self.assertEqual(first["review"]["sequence"], 1)
        self.assertIsNone(first["review"]["previous_id"])
        self.assertEqual(self.detail(first)["changes"], [])
        page = self.detail(first, view="items", limit=10)
        self.assertGreater(page["total_count"], 20)
        pages = [self.detail(first, view="items", offset=start, limit=10)["evaluation"]["items"]
                 for start in range(0, page["total_count"], 10)]
        self.assertEqual(len({row["id"] for rows in pages for row in rows}), page["total_count"])
        self.assertEqual(sum(page["evaluation"]["priority_counts"].values()), page["total_count"])

    def test_time_only_changes_preserve_original_review_and_evidence(self):
        self.dns()
        self.ioc()
        first = self.record()
        original = self.detail(first, view="items")
        self.at += timedelta(days=2)
        second = self.record()
        changes = self.detail(second)["changes"]
        self.assertTrue(changes)
        self.assertEqual({row["origin"] for row in changes}, {"time_only"})
        self.assertTrue(any(row["before"]["priority"] == "review_first" and row["after"]["priority"] == "verify" for row in changes))
        self.assertEqual(original, self.detail(first, view="items"))
        self.assertEqual(second["review"]["previous_id"], first["review"]["id"])

    def test_expiry_is_time_not_withdrawal(self):
        self.ioc(valid_until=(NOW + timedelta(hours=1)).isoformat())
        self.record(IP, "ip")
        self.at += timedelta(hours=2)
        result = self.detail(self.record(IP, "ipv4"))
        self.assertEqual(len(result["changes"]), 1)
        self.assertEqual(result["changes"][0]["origin"], "time_only")
        self.assertEqual(result["changes"][0]["withdrawn_assertion_ids"], [])

    def test_explicit_revocation_identifies_original_assertion(self):
        ioc = self.ioc()
        self.record(IP, "ip")
        self.iocs.revoke(ioc.assertion.id, reason="Controlled withdrawal")
        result = self.detail(self.record(IP, "ip"))
        change = result["changes"][0]
        self.assertEqual(change["withdrawn_assertion_ids"], [ioc.assertion.id])
        self.assertEqual(change["origin"], "evidence_or_mixed")

    def test_source_addition_and_failure_are_not_clock_only(self):
        self.dns()
        self.record()
        self.at += timedelta(days=2)
        self.ioc()
        self.dns(failed=True)
        changes = self.detail(self.record())["changes"]
        self.assertTrue(any(row["origin"] == "evidence_or_mixed" for row in changes))
        self.assertTrue(any("latest_check_failed" in row["after"]["reason_codes"] for row in changes))

    def test_new_relationship_context_is_evidence_change_not_clock_only(self):
        self.record(IP, "ip")
        self.dns()
        result = self.detail(self.record(IP, "ip"))
        changed = [row for row in result["changes"] if row["kind"] == "changed"]
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]["origin"], "evidence_or_mixed")
        self.assertEqual(changed[0]["before"]["reason_codes"], ["evidence_missing"])
        self.assertEqual(changed[0]["after"]["reason_codes"], ["relationship_context_only"])

    def test_partial_visibility_loss_is_not_withdrawal_or_resolution(self):
        self.dns("old.example")
        self.dns("new.example")
        self.record(IP, "ip")
        with patch("xti.adapters.sqlite_research.MAX_DNS_CHECKS", 1):
            second = self.record(IP, "ip")
        data = self.detail(second)
        missing = [row for row in data["changes"] if row["kind"] == "not_in_current_view"]
        self.assertTrue(missing)
        self.assertTrue(second["review"]["comparison"]["coverage_limited"])
        self.assertTrue(all(not row["withdrawn_assertion_ids"] for row in missing))
        self.assertIn("tehdit çözüldü", " ".join(data["notes"]))

    def test_same_scope_normalizes_root_but_different_bounds_start_baseline(self):
        first = self.record("EXAMPLE.COM.")
        second = self.record()
        self.assertEqual(second["review"]["comparison"]["state"], "unchanged")
        self.assertEqual(second["review"]["sequence"], 2)
        narrow = self.record(max_hops=1)
        self.assertEqual(narrow["review"]["comparison"]["state"], "baseline")
        self.assertEqual(narrow["review"]["sequence"], 1)
        self.assertNotEqual(first["review"]["scope_key"], narrow["review"]["scope_key"])
        self.assertEqual(self.history.history(indicator_type="domain", value="example.com")["total_count"], 3)

    def test_policy_change_starts_baseline_without_reinterpreting_old_result(self):
        first = self.record()
        stored = self.repository.show(first["review"]["id"])
        snapshot = deepcopy(stored.snapshot)
        snapshot["policy_version"] = "research-priority-v999"
        second, _ = self.repository.append(stored.header.scope, snapshot, "next-policy", stored.header.id)
        self.assertEqual(second.comparison["state"], "policy_baseline")
        self.assertFalse(second.comparison["changes"])
        self.assertEqual(self.repository.show(stored.header.id), stored)

    def test_explicit_key_replay_does_not_recompute_or_write(self):
        first = self.record(key="capture:one")
        before = self.files()
        with patch.object(self.service, "full_priorities", side_effect=AssertionError("Replay must not recalculate")):
            repeat = self.record("EXAMPLE.COM", key="capture:one")
        self.assertTrue(repeat["replayed"])
        self.assertEqual(first["review"], repeat["review"])
        self.assertEqual(before, self.files())
        with self.assertRaisesRegex(ResearchHistoryError, "başka inceleme"):
            self.record(key="capture:one", stale_after_hours=48)
        self.assertEqual(before, self.files())

    def test_concurrent_capture_cannot_append_to_unexpected_parent(self):
        first = self.record()
        original = self.repository.show(first["review"]["id"])
        self.record(key="winner")
        with self.assertRaises(ResearchHistoryError) as error:
            self.repository.append(original.header.scope, original.snapshot, "loser", original.header.id)
        self.assertEqual(error.exception.code, "review_changed")
        self.assertIsNone(self.repository.find_key("loser"))
        replay, repeated = self.repository.append(original.header.scope, original.snapshot, "winner", original.header.id)
        self.assertTrue(repeated)
        self.assertEqual(replay.header.sequence, 2)

    def test_interrupted_append_rolls_back_then_retries_once(self):
        before = self.files()
        with patch("xti.adapters.sqlite_research_history._load", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.record(key="interrupted")
        self.assertEqual(before, self.files())
        self.assertEqual(self.record(key="interrupted")["review"]["sequence"], 1)
        self.assertTrue(self.record(key="interrupted")["replayed"])

    def test_clock_regression_fails_without_mutation(self):
        self.record()
        before = self.files()
        self.at -= timedelta(minutes=1)
        with self.assertRaises(ResearchHistoryError) as error:
            self.record()
        self.assertEqual(error.exception.code, "clock_regression")
        self.assertEqual(before, self.files())

    def test_history_page_guard_and_frozen_item_pages(self):
        self.dns()
        first = self.record()
        self.record()
        page = self.history.history(indicator_type="domain", value="example.com", limit=1)
        next_page = self.history.history(indicator_type="domain", value="example.com", limit=1,
            offset=1, expected_snapshot=page["snapshot_id"])
        self.assertEqual(next_page["records"][0]["id"], first["review"]["id"])
        frozen_page = self.detail(first, view="items", offset=1, limit=1)
        self.record()
        with self.assertRaises(ResearchHistoryError) as error:
            self.history.history(indicator_type="domain", value="example.com", offset=1, expected_snapshot=page["snapshot_id"])
        self.assertEqual(error.exception.code, "snapshot_changed")
        self.assertEqual(frozen_page, self.detail(first, view="items", offset=1, limit=1))

    def test_corrupt_body_fails_read_replay_and_followup_but_metadata_is_explicit(self):
        first = self.record(key="one")
        self.sql("UPDATE research_reviews SET snapshot_json='{}'")
        for action in (lambda: self.detail(first), lambda: self.record(key="one"), lambda: self.record()):
            with self.subTest(action=action), self.assertRaises(StorageError):
                action()
        listed = self.history.history(indicator_type="domain", value="example.com")
        self.assertEqual(listed["integrity_check"], "metadata_and_parent_links")
        self.assertEqual(listed["total_count"], 1)

    def test_header_corruption_and_missing_parent_fail_closed(self):
        first = self.record()
        second = self.record()
        self.sql("UPDATE research_reviews SET sequence=9 WHERE id=?", (second["review"]["id"],))
        with self.assertRaises(StorageError):
            self.history.history(indicator_type="domain", value="example.com")
        self.sql("UPDATE research_reviews SET sequence=2 WHERE id=?", (second["review"]["id"],))
        self.sql("DELETE FROM research_reviews WHERE id=?", (first["review"]["id"],))
        with self.assertRaises(StorageError):
            self.detail(second)

    def test_semantically_changed_comparison_with_recomputed_hash_is_rejected(self):
        first = self.record()
        self.record()
        data = deepcopy(self.repository.show(first["review"]["id"]).comparison)
        data["changes"] = [{"fake": True}]
        body = encode(data)
        self.sql("UPDATE research_reviews SET comparison_json=?,comparison_sha256=? WHERE id=?", (body, digest(body), first["review"]["id"]))
        row = self.sql(f"SELECT {FIELDS} FROM research_reviews WHERE id=?", (first["review"]["id"],))[0]
        self.sql("UPDATE research_reviews SET header_sha256=? WHERE id=?", (identity(*row[:-1]), first["review"]["id"]))
        with self.assertRaises(StorageError):
            self.detail(first)

    def test_large_or_invalid_json_records_fail_with_controlled_error(self):
        first = self.record()
        self.sql("UPDATE research_reviews SET snapshot_json=?", ("x" * (8 * 1024 * 1024 + 1),))
        with self.assertRaises(StorageError):
            self.detail(first)
        for body in ('{"a":1,"a":1}', '{"a":NaN}', '{ "a":1}'):
            with self.subTest(body=body), self.assertRaises(ValidationError):
                decode(body, digest(body))
        with self.assertRaises(ValidationError):
            encode({"large": "a" * 50}, limit=10)

    def test_readonly_commands_do_not_initialize_missing_database(self):
        missing = self.root / "missing"
        code, _, err = self.invoke(["--data-dir", str(missing), "--json", "research-history", "list", "example.com", "--type", "domain"])
        self.assertNotEqual(code, 0)
        self.assertFalse(missing.exists())
        self.assertIn("storage_error", err)
        before = self.files()
        self.history.history(indicator_type="domain", value="example.com")
        with self.assertRaises(ResearchHistoryError):
            self.history.show(str(uuid4()))
        self.assertEqual(before, self.files())

    def test_backup_restore_preserves_frozen_results_and_replay_keys(self):
        self.dns()
        first = self.record(key="first")
        self.ioc()
        second = self.record(key="second")
        backup, restored = self.root / "backup.db", self.root / "restored" / "xti.db"
        SQLiteAssetRepository(self.path).backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        service = make_history_service(restored)
        for record in (first, second):
            self.assertEqual(service.show(record["review"]["id"], view="items"), self.detail(record, view="items"))
        self.assertTrue(service.record(indicator_type="domain", value="example.com", idempotency_key="first")["replayed"])

    def test_schema74_requires_explicit_backed_up_migration(self):
        asset, _ = SQLiteAssetRepository(self.path).add("example.com")
        self.sql("DROP TABLE research_reviews")
        self.sql("PRAGMA user_version=74")
        before = self.files()
        with self.assertRaises(StorageError):
            self.record()
        self.assertEqual(before, self.files())
        migration = SQLiteAssetRepository(self.path).migrate()
        self.assertEqual((migration["from_version"], migration["to_version"]), (74, 79))
        self.assertEqual(SQLiteAssetRepository(self.path).list(), [asset])
        with closing(sqlite3.connect(migration["backup"])) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 74)
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_schema WHERE name='research_reviews'").fetchone())
        self.assertEqual(self.record()["review"]["comparison"]["state"], "baseline")

    def test_migration_interruption_preserves_old_schema_and_backup(self):
        self.sql("DROP TABLE research_reviews")
        self.sql("PRAGMA user_version=74")
        with patch("xti.adapters.sqlite.create_research_history_schema", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                SQLiteAssetRepository(self.path).migrate()
        self.assertEqual(self.sql("PRAGMA user_version"), [(74,)])
        self.assertFalse(self.sql("SELECT name FROM sqlite_schema WHERE name='research_reviews'"))
        self.assertEqual(len(list((self.data / "backups").glob("*.db"))), 1)
        self.assertTrue(SQLiteAssetRepository(self.path).migrate()["changed"])

    def test_populated_future_table_cannot_masquerade_as_schema74(self):
        self.record()
        self.sql("PRAGMA user_version=74")
        with self.assertRaises(StorageError):
            SQLiteAssetRepository(self.path).migrate()

    def test_cli_and_engine_pages_remain_selected_and_offline(self):
        code, out, err = self.invoke(["--data-dir", str(self.data), "--json", "research-history", "record", "example.com", "--type", "domain", "--idempotency-key", "cli"])
        self.assertEqual((code, err), (0, ""), out)
        identifier = json.loads(out)["data"]["review"]["id"]
        before = self.files()
        for request in (self.request(indicator_type="domain", value="example.com"),
                        self.request("research.review.get", review_id=identifier, view="items")):
            code, out, err = self.invoke(["--data-dir", str(self.data), "engine"], request)
            self.assertEqual((code, err), (0, ""), out)
            self.assertEqual(json.loads(out)["status"], "complete")
        data = self.history.history(indicator_type="domain", value="example.com")
        command = next(line.split("Ayrıntı: ", 1)[1] for line in history_lines(data, data_dir=self.data) if "Ayrıntı: " in line)
        arguments = shlex.split(command)[1:]
        self.assertIn(str(self.data), arguments)
        self.assertEqual(self.invoke(arguments)[0], 0)
        self.assertEqual(before, self.files())

    def test_engine_cannot_capture_and_strict_parameters_are_enforced(self):
        before = self.files()
        requests = [self.request("research.review.record", indicator_type="domain", value="example.com")]
        for options in ({"offset": True}, {"limit": 101}, {"path": "/tmp/other"}, {"expected_snapshot": "bad"}):
            requests.append(self.request(indicator_type="domain", value="example.com", **options))
        requests.append(self.request("research.review.get", review_id=str(uuid4()), view=[]))
        for request in requests:
            with self.subTest(request=request):
                code, out, err = self.invoke(["--data-dir", str(self.data), "engine"], request)
                self.assertEqual((code, err), (2, ""), out)
                self.assertEqual(json.loads(out)["status"], "error")
        self.assertEqual(before, self.files())

    def test_platform_capture_replay_fence_and_company_isolation(self):
        root = self.root / "companies"
        first = self.company(root, "first")
        second = self.company(root, "second")
        self.record(key="personal")
        def request(company, operation, **parameters):
            code, out, err = self.invoke(["platform", "request", "--root", str(root), "--company", company], self.request(operation, **parameters))
            self.assertEqual(err, "")
            return code, json.loads(out)
        parameters = dict(indicator_type="domain", value="example.com", idempotency_key="same-key", expected_workspace_id=first.workspace_id)
        code, response = request("first", "research.review.record", **parameters)
        self.assertEqual(code, 0, response)
        identifier = response["data"]["review"]["id"]
        self.assertTrue(request("first", "research.review.record", **parameters)[1]["data"]["replayed"])
        self.assertEqual(request("second", "research.review.record", **parameters)[1]["error"]["code"], "scope_mismatch")
        self.assertEqual(request("second", "research.review.get", review_id=identifier)[1]["error"]["code"], "not_found")
        self.assertEqual(request("second", "research.history", indicator_type="domain", value="example.com")[1]["data"]["total_count"], 0)
        parameters["expected_workspace_id"] = second.workspace_id
        other = request("second", "research.review.record", **parameters)[1]["data"]
        self.assertNotEqual(other["review"]["id"], identifier)
        self.assertEqual(other["review"]["sequence"], 1)
        disable_company_workspace(root, "second")
        for company in ("unknown", "second"):
            self.assertNotEqual(request(company, "research.history", indicator_type="domain", value="example.com")[0], 0)

    def test_platform_capture_requires_key_and_fence_and_rejects_scope_injection(self):
        root = self.root / "companies"
        context = self.company(root, "first")
        base = dict(indicator_type="domain", value="example.com", idempotency_key="test", expected_workspace_id=context.workspace_id)
        invalid = [{key: value for key, value in base.items() if key != removed} for removed in ("idempotency_key", "expected_workspace_id")]
        invalid += [{**base, "company": "second"}, {**base, "max_hops": True}, {**base, "idempotency_key": None}]
        before = self.files()
        for parameters in invalid:
            with self.subTest(parameters=parameters):
                code, out, err = self.invoke(["platform", "request", "--root", str(root), "--company", "first"], self.request("research.review.record", **parameters))
                self.assertEqual((code, err), (2, ""), out)
                self.assertEqual(json.loads(out)["error"]["code"], "invalid_parameters")
        self.assertEqual(before, self.files())

    def test_archive_refresh_matches_bindings_not_ephemeral_receipt_ids(self):
        from xti.adapters.sqlite_enrichment import SQLiteEnrichmentRepository
        from xti.application.indicator_enrichment import EnrichmentService
        from tests.test_indicator_enrichment import Source, url_body, URL
        source = Source()
        source.content = url_body()
        enrichment = EnrichmentService(SQLiteEnrichmentRepository(self.path), source, clock=lambda: self.at)
        enrichment.refresh(indicator_type="url", value=URL)
        first = self.record(URL, "url")
        self.at += timedelta(hours=1)
        enrichment.refresh(indicator_type="url", value=URL)
        second = self.record(URL, "url")
        changes = self.detail(second)["changes"]
        bindings = [row for row in changes if row["subject_id"].startswith("binding:")]
        self.assertTrue(bindings)
        self.assertTrue(all(row["kind"] == "changed" for row in bindings))
        self.assertTrue(all(row["origin"] == "evidence_or_mixed" for row in bindings))
        self.assertTrue(any(row["before"]["item_ids"] != row["after"]["item_ids"] for row in bindings))
        self.assertEqual(first["review"]["id"], second["review"]["previous_id"])

    def test_warninglist_aging_is_clock_only_but_new_source_run_is_not(self):
        from xti.adapters.sqlite_warninglists import SQLiteWarninglistRepository
        from xti.application.warninglists import WarninglistService
        from tests.test_warninglists import Source
        warnings = WarninglistService(SQLiteWarninglistRepository(self.path), Source(), clock=lambda: self.at)
        warnings.sync()
        self.record()
        self.at += timedelta(days=8)
        aged = self.record()["review"]["comparison"]
        self.assertTrue(aged["context_changed"])
        self.assertEqual(aged["context_origin"], "time_only")
        warnings.sync()
        refreshed = self.record()["review"]["comparison"]
        self.assertTrue(refreshed["context_changed"])
        self.assertEqual(refreshed["context_origin"], "evidence_or_mixed")

    def test_restored_company_retains_history_but_rejects_old_fence_even_on_replay(self):
        from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
        from xti.domain.engine import EngineContractError
        from xti.interfaces.research_history import execute_platform_record
        original = self.company(self.root / "companies", "first")
        parameters = dict(indicator_type="domain", value="example.com", idempotency_key="original",
                          expected_workspace_id=original.workspace_id)
        saved = execute_platform_record(original, parameters)
        backup = self.root / "company-backup"
        backup_platform_workspace(original, backup)
        restored = restore_platform_workspace(self.root / "company-restored", "first", backup)
        with self.assertRaises(EngineContractError) as error:
            execute_platform_record(restored, parameters)
        self.assertEqual(error.exception.code, "scope_mismatch")
        replay = execute_platform_record(restored, {**parameters, "expected_workspace_id": restored.workspace_id})
        self.assertTrue(replay["replayed"])
        self.assertEqual(saved["review"], replay["review"])

    def test_terminal_escapes_external_labels_and_preserves_selected_continuation(self):
        self.dns()
        record = self.record()
        data = self.detail(record, view="items", limit=1)
        data["evaluation"]["items"][0]["label"] = "bad\x1b[2J\nInjected"
        rendered = history_lines(data, data_dir=self.data)
        self.assertFalse(any("\x1b" in line or "\n" in line for line in rendered))
        command = next(line.split(": ", 1)[1] for line in rendered if line.startswith("Sonraki sayfa:"))
        arguments = shlex.split(command)[1:]
        self.assertEqual(arguments[arguments.index("--view") + 1], "items")
        self.assertIn(str(self.data), arguments)
        self.assertEqual(self.invoke(arguments)[0], 0)

    def test_malformed_frozen_model_rejected_before_persistence(self):
        self.dns()
        valid = freeze(priority_data(self.service.full_priorities(indicator_type="domain", value="example.com")))
        for field, value in (("enrichment", []), ("references", None), ("related_item_ids", ["missing"]), ("priority", "severe")):
            with self.subTest(field=field):
                snapshot = deepcopy(valid)
                snapshot["items"][0][field] = value
                with self.assertRaises(ValidationError):
                    self.repository.append(capture_scope(indicator_type="domain", value="example.com"), snapshot, "invalid", None)
        self.assertIsNone(self.repository.find_key("invalid"))


if __name__ == "__main__":
    unittest.main()
