"""Authorized Nmap target inventory and immutable dry-run plan acceptance."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.schema import SCHEMA_VERSION
from xti.adapters.sqlite_nmap_management import SQLiteNmapManagementRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.application.surface import SurfaceService
from xti.domain.assets import ValidationError
from xti.domain.nmap_management import (
    NmapTargetScope,
    build_managed_plan_definition,
    build_target_definition,
    canonical_managed_plan_json,
    canonical_target_definition_json,
    parse_managed_plan_json,
    parse_target_definition_json,
    target_addresses,
)
from xti.interfaces.cli import main


START = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


def target_scope(definition, *, active=True):
    from xti.domain.nmap_management import target_definition_sha256

    return NmapTargetScope(
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
        "example.com", "production", "Production", 1, definition,
        target_definition_sha256(definition), active, "Yönettiğim genel IP aralığı",
        START.isoformat(), START.isoformat(),
    )


class DomainTests(unittest.TestCase):
    def test_cidr_exclusions_have_exact_count_and_stable_canonical_form(self):
        definition = build_target_definition(
            "8.8.8.0/29", ("8.8.8.0", "8.8.8.6/31"),
        )
        self.assertEqual(definition.network, "8.8.8.0/29")
        self.assertEqual(definition.exclusions, ("8.8.8.0/32", "8.8.8.6/31"))
        self.assertEqual(
            target_addresses(definition),
            ("8.8.8.1", "8.8.8.2", "8.8.8.3", "8.8.8.4", "8.8.8.5"),
        )
        encoded = canonical_target_definition_json(definition)
        self.assertEqual(parse_target_definition_json(encoded), definition)

    def test_private_noncanonical_oversized_or_empty_ranges_fail_closed(self):
        for network, exclusions in (
            ("10.0.0.0/29", ()),
            ("8.8.8.1/29", ()),
            ("8.8.0.0/19", ()),
            ("8.8.8.0/29", ("8.8.8.0/29",)),
            ("8.8.8.0/29", ("1.1.1.1",)),
        ):
            with self.subTest(network=network), self.assertRaises(ValidationError):
                build_target_definition(network, exclusions)

    def test_managed_plan_freezes_limits_and_requires_range_and_wide_confirmations(self):
        small = target_scope(build_target_definition("8.8.8.0/29"))
        plan = build_managed_plan_definition(
            small, profile="custom", ports="80,443", timeout_seconds=90,
            max_rate_pps=20, max_retries=0, scan_delay_ms=25,
            max_parallelism=4, max_hostgroup=20, max_targets=8,
            max_probe_budget=16,
        )
        self.assertEqual((plan.target_count, plan.port_count, plan.probe_budget), (8, 2, 16))
        self.assertEqual(plan.max_hostgroup, 8)
        encoded = canonical_managed_plan_json(plan)
        self.assertEqual(parse_managed_plan_json(encoded), plan)
        large = target_scope(build_target_definition("8.8.8.0/27"))
        with self.assertRaisesRegex(ValidationError, "aralık taraması onayı"):
            build_managed_plan_definition(
                large, max_targets=32, max_probe_budget=1000,
            )
        with self.assertRaisesRegex(ValidationError, "confirm-wide-scan"):
            build_managed_plan_definition(
                small, profile="full", max_targets=8, max_probe_budget=2_000_000,
            )

    def test_duplicate_or_noncanonical_json_is_rejected(self):
        definition = build_target_definition("8.8.8.8")
        encoded = canonical_target_definition_json(definition)
        duplicate = encoded[:-1] + ',"network":"8.8.8.8/32"}'
        for value in (duplicate, encoded.replace('"target_count":1', '"target_count":2')):
            with self.assertRaises(ValidationError):
                parse_target_definition_json(value)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.asset, _created = self.storage.add("example.com")
        self.surface = SQLiteSurfaceRepository(self.path, clock=lambda: START)
        SurfaceService(
            self.storage, self.surface, clock=lambda: START,
        ).approve("example.com", "Kendi domainim")
        self.repository = SQLiteNmapManagementRepository(self.path)

    def save(self, second=1, **changes):
        values = {
            "asset_id": self.asset.id,
            "asset_value": "example.com",
            "display_name": "Production",
            "definition": build_target_definition("8.8.8.0/29", ("8.8.8.0",)),
            "authorization_reason": "Yönettiğim genel IP aralığı",
            "recorded_at": (START + timedelta(seconds=second)).isoformat(),
        }
        values.update(changes)
        return self.repository.save_target(**values)

    def test_target_lifecycle_and_plan_are_idempotent_and_auditable(self):
        added = self.save()
        unchanged = self.save(second=2)
        self.assertEqual((added.action, unchanged.action), ("added", "unchanged"))
        updated = self.save(
            second=3,
            definition=build_target_definition("8.8.8.0/29", ("8.8.8.0/31",)),
        )
        self.assertEqual((updated.action, updated.scope.revision), ("updated", 2))
        definition = build_managed_plan_definition(
            updated.scope, max_targets=6, max_probe_budget=120,
        )
        created = self.repository.save_plan(
            self.asset.id, "example.com", definition,
            recorded_at=(START + timedelta(seconds=4)).isoformat(),
        )
        repeated = self.repository.save_plan(
            self.asset.id, "example.com", definition,
            recorded_at=(START + timedelta(seconds=5)).isoformat(),
        )
        self.assertEqual((created.action, repeated.action), ("created", "unchanged"))
        revoked = self.repository.revoke_target(
            self.asset.id, "Production", reason="Bu aralık artık bize ait değil",
            recorded_at=(START + timedelta(seconds=6)).isoformat(),
        )
        self.assertEqual((revoked.action, revoked.scope.revision), ("revoked", 3))
        details = self.repository.target_details(self.asset.id, "Production")
        self.assertEqual((details.event_count, details.plan_count), (3, 1))
        self.assertFalse(details.scope.active)
        self.assertEqual(self.repository.get_plan(self.asset.id, created.plan.id), created.plan)
        with self.assertRaisesRegex(ValidationError, "Etkin bir Nmap hedef kapsamı"):
            build_managed_plan_definition(revoked.scope)

    def test_corrupt_plan_hash_fails_closed_without_modifying_database(self):
        target = self.save().scope
        definition = build_managed_plan_definition(
            target, max_targets=7, max_probe_budget=140,
        )
        self.repository.save_plan(
            self.asset.id, "example.com", definition,
            recorded_at=(START + timedelta(seconds=2)).isoformat(),
        )
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                "UPDATE surface_nmap_plans SET plan_sha256=?", ("0" * 64,),
            )
            connection.commit()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "plan kaydı bozuk"):
            self.repository.list_plans(self.asset.id)
        self.assertEqual(self.path.read_bytes(), before)

    def test_schema_70_migration_backs_up_and_accepts_only_empty_staged_tables(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA user_version=70")
            connection.commit()
        result = self.storage.migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (70, SCHEMA_VERSION))
        self.assertTrue(Path(result["backup"]).is_file())
        self.assertEqual(self.repository.list_targets(self.asset.id), ())


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.database = self.data / "xti.db"
        self.ok("init")
        self.ok("assets", "add", "example.com")
        self.ok("surface", "approve", "example.com", "--reason", "Kendi domainim")

    def invoke(self, *arguments):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def ok(self, *arguments):
        code, stdout, stderr = self.invoke(*arguments)
        self.assertEqual((code, stderr), (0, ""))
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        return payload["data"]

    def test_terminal_target_and_dry_run_plan_workflow(self):
        target = self.ok(
            "surface", "nmap", "targets", "save", "example.com", "production",
            "--network", "8.8.8.0/29", "--exclude", "8.8.8.0",
            "--reason", "Yönettiğim genel IP aralığı",
        )["scope"]
        self.assertEqual(target["definition"]["target_count"], 7)
        plan = self.ok(
            "surface", "nmap", "plans", "create", "example.com",
            "--target", "production", "--profile", "custom", "--ports", "80,443",
            "--max-targets", "7", "--max-probes", "28",
        )["plan"]
        self.assertEqual((plan["definition"]["port_count"], plan["definition"]["probe_budget"]), (2, 28))
        before = self.database.read_bytes()
        shown = self.ok(
            "surface", "nmap", "plans", "show", "example.com", plan["id"],
        )
        listed = self.ok("surface", "nmap", "targets", "list", "example.com")
        self.assertEqual(shown["plan_sha256"], plan["plan_sha256"])
        self.assertEqual(len(listed["targets"]), 1)
        self.assertEqual(self.database.read_bytes(), before)

    def test_private_target_and_unconfirmed_large_range_are_rejected(self):
        code, stdout, stderr = self.invoke(
            "surface", "nmap", "targets", "save", "example.com", "private",
            "--network", "10.0.0.0/29", "--reason", "Test",
        )
        self.assertEqual((code, stdout), (2, ""))
        self.assertTrue(stderr)
        self.ok(
            "surface", "nmap", "targets", "save", "example.com", "range",
            "--network", "8.8.8.0/27", "--reason", "Yönettiğim genel IP aralığı",
        )
        code, stdout, stderr = self.invoke(
            "surface", "nmap", "plans", "create", "example.com",
            "--target", "range", "--max-targets", "32", "--max-probes", "1000",
        )
        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("aralık", json.loads(stderr)["error"]["message"])


if __name__ == "__main__":
    unittest.main()
