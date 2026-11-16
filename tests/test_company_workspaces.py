"""Company selection fails closed, preserves evidence and never adopts local data."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.company_workspaces import (
    MAX_REGISTRY_BYTES, REGISTRY_FILE, REGISTRY_LOCK, WORKSPACE_MARKER,
    disable_company_workspace, provision_company_workspace, resolve_company_workspace,
)
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.domain.company_workspace import CompanyWorkspaceError, normalize_company_id
from xti.ports.jobs import WorkerBusyError


class CompanyWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "platform"

    def provision(self, company="alpha", *, root=None):
        context = provision_company_workspace(root or self.root, company)
        SQLiteAssetRepository(context.database).initialize()
        return context

    def registry(self):
        return json.loads((self.root / REGISTRY_FILE).read_text())

    def change_registry(self, registry):
        (self.root / REGISTRY_FILE).write_text(json.dumps(registry))

    def files(self):
        return {str(path.relative_to(self.base)): path.read_bytes()
                for path in self.base.rglob("*") if path.is_file() and not path.is_symlink()}

    def test_provision_creates_private_explicit_binding_without_database(self):
        context = provision_company_workspace(self.root, "alpha_01")
        self.assertEqual(context.data_dir, self.root / "alpha_01")
        self.assertEqual(context.database, context.data_dir / "xti.db")
        self.assertEqual(context.lock_directory, context.data_dir)
        self.assertFalse(context.database.exists())
        self.assertEqual(context.scope, {"mode": "company-workspace", "company_id": "alpha_01",
            "registry_id": context.registry_id, "workspace_id": context.workspace_id})
        self.assertEqual(self.registry()["companies"], [{"company_id": "alpha_01",
            "workspace_id": context.workspace_id, "enabled": True}])
        for path in (self.root, context.data_dir):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        for path in (self.root / REGISTRY_FILE, self.root / REGISTRY_LOCK,
                     context.data_dir / WORKSPACE_MARKER):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(CompanyWorkspaceError):
            resolve_company_workspace(self.root, "alpha_01")

    def test_read_only_resolution_and_unknown_company_have_no_file_side_effects(self):
        context = self.provision()
        before = self.files()
        self.assertEqual(resolve_company_workspace(self.root, "alpha"), context)
        with self.assertRaises(CompanyWorkspaceError):
            resolve_company_workspace(self.root, "missing")
        self.assertEqual(self.files(), before)
        self.assertFalse((self.root / "missing").exists())

    def test_missing_root_and_invalid_identifiers_never_create_or_fall_back(self):
        with self.assertRaises(CompanyWorkspaceError):
            resolve_company_workspace(self.root, "alpha")
        for value in (None, True, 42, "", ".", "..", "../alpha", "/alpha", "alpha/beta",
                      "Alpha", " alpha", "alpha ", "a\\b", "fırma", "a\n", "a" * 65,
                      "$(secret)", "-alpha", "_alpha"):
            with self.subTest(value=value), self.assertRaises(CompanyWorkspaceError):
                provision_company_workspace(self.root, value)
        self.assertFalse(self.root.exists())
        self.assertEqual(normalize_company_id("a" * 64), "a" * 64)

    def test_existing_workspace_is_not_adopted_or_overwritten(self):
        context = self.provision()
        SQLiteAssetRepository(context.database).add("alpha.example")
        orphan = self.root / "orphan"
        orphan.mkdir(mode=0o700)
        (orphan / "evidence.txt").write_text("do not adopt")
        before = self.files()
        for company in ("alpha", "orphan"):
            with self.subTest(company=company), self.assertRaises(CompanyWorkspaceError):
                provision_company_workspace(self.root, company)
        self.assertEqual(self.files(), before)

    def test_existing_local_data_root_cannot_be_bound_implicitly(self):
        self.root.mkdir(mode=0o700)
        database = self.root / "xti.db"
        SQLiteAssetRepository(database).initialize()
        before = self.files()
        with self.assertRaises(CompanyWorkspaceError):
            provision_company_workspace(self.root, "alpha")
        self.assertEqual(self.files(), before)
        self.assertFalse((self.root / REGISTRY_LOCK).exists())

    def test_company_and_registry_markers_are_required_exact_bindings(self):
        alpha = self.provision("alpha")
        beta = self.provision("beta")
        other = self.provision("alpha", root=self.base / "other")
        marker = alpha.data_dir / WORKSPACE_MARKER
        original = marker.read_bytes()
        for replacement in ((beta.data_dir / WORKSPACE_MARKER).read_bytes(),
                            (other.data_dir / WORKSPACE_MARKER).read_bytes(), b"{}"):
            marker.write_bytes(replacement)
            with self.assertRaises(CompanyWorkspaceError):
                resolve_company_workspace(self.root, "alpha")
        marker.write_bytes(original)
        marker.unlink()
        with self.assertRaises(CompanyWorkspaceError):
            resolve_company_workspace(self.root, "alpha")

    def test_database_hardlink_and_symlink_cannot_cross_company_boundaries(self):
        alpha = self.provision("alpha")
        beta = self.provision("beta")
        original = alpha.database.read_bytes()
        alpha.database.unlink()
        alpha.database.symlink_to(beta.database)
        with self.assertRaises(CompanyWorkspaceError):
            resolve_company_workspace(self.root, "alpha")
        alpha.database.unlink()
        os.link(beta.database, alpha.database)
        for company in ("alpha", "beta"):
            with self.assertRaises(CompanyWorkspaceError):
                resolve_company_workspace(self.root, company)
        alpha.database.unlink()
        alpha.database.write_bytes(original)
        alpha.database.chmod(0o600)
        self.assertEqual(resolve_company_workspace(self.root, "alpha"), alpha)

    def test_directory_alias_and_nested_roots_are_rejected(self):
        alpha = self.provision()
        alias = self.base / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        for path in (alias, alias / "nested", self.root / "nested", alpha.data_dir / "nested",
                     self.root / ".." / "platform"):
            with self.subTest(path=path), self.assertRaises(CompanyWorkspaceError):
                provision_company_workspace(path, "beta")
        moved = self.root / "moved"
        alpha.data_dir.rename(moved)
        alpha.data_dir.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(CompanyWorkspaceError):
            resolve_company_workspace(self.root, "alpha")

    def test_private_permissions_are_enforced_on_every_boundary_file(self):
        context = self.provision()
        for path in (self.root, context.data_dir, self.root / REGISTRY_LOCK,
                     self.root / REGISTRY_FILE, context.data_dir / WORKSPACE_MARKER,
                     context.database):
            original = path.stat().st_mode & 0o777
            path.chmod(original | 0o040)
            try:
                with self.subTest(path=path), self.assertRaises(CompanyWorkspaceError):
                    resolve_company_workspace(self.root, "alpha")
            finally:
                path.chmod(original)

    def test_wrong_owner_is_rejected(self):
        self.provision()
        with patch("xti.adapters.company_workspaces.os.getuid", return_value=os.getuid() + 1):
            with self.assertRaises(CompanyWorkspaceError):
                resolve_company_workspace(self.root, "alpha")

    def test_untrusted_writable_ancestor_is_rejected_but_trusted_sticky_parent_is_allowed(self):
        self.provision()
        original = self.base.stat().st_mode & 0o7777
        try:
            for permissions in (0o770, 0o777):
                self.base.chmod(permissions)
                with self.subTest(permissions=permissions), self.assertRaises(CompanyWorkspaceError):
                    resolve_company_workspace(self.root, "alpha")
                with self.assertRaises(CompanyWorkspaceError):
                    provision_company_workspace(self.base / "new-root", "beta")
                self.assertFalse((self.base / "new-root").exists())
            self.base.chmod(0o1777)
            self.assertEqual(resolve_company_workspace(self.root, "alpha").company_id, "alpha")
        finally:
            self.base.chmod(original)

    def test_registry_and_marker_links_or_special_files_are_rejected_without_blocking(self):
        context = self.provision()
        for path in (self.root / REGISTRY_FILE, self.root / REGISTRY_LOCK,
                     context.data_dir / WORKSPACE_MARKER, context.database):
            original = path.read_bytes()
            saved = self.base / "saved"
            path.rename(saved)
            try:
                path.symlink_to(saved)
                with self.assertRaises(CompanyWorkspaceError):
                    resolve_company_workspace(self.root, "alpha")
                path.unlink()
                os.link(saved, path)
                with self.assertRaises(CompanyWorkspaceError):
                    resolve_company_workspace(self.root, "alpha")
                path.unlink()
                os.mkfifo(path, 0o600)
                with self.assertRaises(CompanyWorkspaceError):
                    resolve_company_workspace(self.root, "alpha")
                path.unlink()
            finally:
                saved.rename(path)
            self.assertEqual(path.read_bytes(), original)

    def test_hostile_registry_json_cannot_redirect_paths_or_duplicate_scope(self):
        self.provision()
        original = self.registry()
        entry = original["companies"][0]
        invalid = [
            {**original, "version": True}, {**original, "registry_id": "bad"},
            {**original, "extra": "/private"},
            {**original, "companies": [entry, entry]},
            {**original, "companies": [entry, {**entry, "company_id": "beta"}]},
            {**original, "companies": [{**entry, "company_id": "../beta"}]},
            {**original, "companies": [{**entry, "data_dir": "/private"}]},
            {**original, "companies": [{**entry, "enabled": 1}]},
            {**original, "companies": [None]},
        ]
        for registry in invalid:
            self.change_registry(registry)
            with self.subTest(registry=registry), self.assertRaises(CompanyWorkspaceError):
                resolve_company_workspace(self.root, "alpha")
        path = self.root / REGISTRY_FILE
        for payload in (b'{"version":1,"version":1}', b"\xff", b"NaN", b"[]",
                        b"{" * 20, b" " * (MAX_REGISTRY_BYTES + 1)):
            path.write_bytes(payload)
            with self.assertRaises(CompanyWorkspaceError):
                resolve_company_workspace(self.root, "alpha")

    def test_disabled_company_fails_closed_and_evidence_is_preserved(self):
        context = self.provision()
        asset, _ = SQLiteAssetRepository(context.database).add("alpha.example")
        database = context.database.read_bytes()
        result = disable_company_workspace(self.root, "alpha")
        self.assertFalse(result.enabled)
        self.assertEqual(result.workspace_id, context.workspace_id)
        before = self.files()
        self.assertEqual(disable_company_workspace(self.root, "alpha"), result)
        self.assertEqual(self.files(), before)
        with self.assertRaises(CompanyWorkspaceError):
            resolve_company_workspace(self.root, "alpha")
        with self.assertRaises(CompanyWorkspaceError):
            provision_company_workspace(self.root, "alpha")
        self.assertEqual(context.database.read_bytes(), database)
        self.assertEqual(SQLiteAssetRepository(context.database).list()[0].id, asset.id)

    def test_partial_initialization_can_be_disabled_but_not_silently_repaired(self):
        context = provision_company_workspace(self.root, "alpha")
        with self.assertRaises(CompanyWorkspaceError):
            resolve_company_workspace(self.root, "alpha")
        with self.assertRaises(CompanyWorkspaceError):
            provision_company_workspace(self.root, "alpha")
        self.assertFalse(disable_company_workspace(self.root, "alpha").enabled)
        self.assertFalse(context.database.exists())

    def test_failed_registration_preserves_orphan_and_later_call_does_not_adopt(self):
        self.provision("alpha")
        original = self.registry()
        from xti.adapters import company_workspaces as adapter
        publish = adapter._publish

        def interrupted(directory, filename, value, **kwargs):
            if filename == REGISTRY_FILE:
                raise OSError("simulated interruption")
            return publish(directory, filename, value, **kwargs)

        with patch.object(adapter, "_publish", side_effect=interrupted):
            with self.assertRaises(CompanyWorkspaceError):
                provision_company_workspace(self.root, "beta")
        self.assertEqual(self.registry(), original)
        self.assertTrue((self.root / "beta" / WORKSPACE_MARKER).is_file())
        before = self.files()
        with self.assertRaises(CompanyWorkspaceError):
            provision_company_workspace(self.root, "beta")
        self.assertEqual(self.files(), before)
        with self.assertRaises(CompanyWorkspaceError):
            resolve_company_workspace(self.root, "beta")

    def test_concurrent_provisions_do_not_lose_registration_or_rebind_same_key(self):
        with ThreadPoolExecutor(max_workers=4) as executor:
            contexts = list(executor.map(lambda key: provision_company_workspace(self.root, key),
                                         ("alpha", "beta", "gamma", "delta")))
        self.assertEqual({entry["company_id"] for entry in self.registry()["companies"]},
                         {context.company_id for context in contexts})
        self.assertEqual(len({context.registry_id for context in contexts}), 1)
        self.assertEqual(len({context.workspace_id for context in contexts}), 4)

        def same_key(_):
            try:
                return provision_company_workspace(self.root, "same")
            except CompanyWorkspaceError:
                return None

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(same_key, range(4)))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(sum(entry["company_id"] == "same" for entry in self.registry()["companies"]), 1)

    def test_existing_worker_lock_is_shared_within_company_and_independent_between_companies(self):
        alpha = self.provision("alpha")
        beta = self.provision("beta")
        with LocalExecutionLock(alpha.database).acquire():
            with self.assertRaises(WorkerBusyError):
                with LocalExecutionLock(resolve_company_workspace(self.root, "alpha").database).acquire():
                    self.fail("second writer entered same company")
            with LocalExecutionLock(resolve_company_workspace(self.root, "beta").database).acquire():
                pass


if __name__ == "__main__":
    unittest.main()
