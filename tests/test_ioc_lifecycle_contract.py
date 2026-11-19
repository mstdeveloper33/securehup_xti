"""One lifecycle result across terminal, engine and isolated company requests."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
from xti.application.cti_indicators import CtiIndicatorService
from xti.interfaces.cli import main
from xti.interfaces.ioc_lifecycle import make_ioc_lifecycle_service
from tests import test_engine_contract as engine_fixtures
from tests import test_platform_isolation as platform_fixtures


PARAMETERS = {"indicator_type": "domain", "value": "example.com"}


def add(database, source, value="example.com"):
    return CtiIndicatorService(SQLiteCtiIndicatorRepository(database)).add(
        "domain", value, source_name=source, source_reference="https://evidence.example/" + source,
        confidence=65, description="Private analyst evidence " + source)


class IocLifecycleContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = engine_fixtures.EngineContractTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.created = add(self.fixture.database, "analyst")

    def request(self, **changes):
        return self.fixture.request("ioc.lifecycle", {**PARAMETERS, **changes})

    def test_engine_and_terminal_json_share_policy_evidence_and_snapshot_without_writes(self):
        before = self.fixture.files()
        result = self.fixture.complete(self.request())
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--data-dir", str(self.fixture.data), "--json", "ioc", "lifecycle", "domain", "example.com"])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        terminal = json.loads(stdout.getvalue())["data"]
        for field in ("policy", "input_sha256", "snapshot_id", "assessment", "total_count", "source_count"):
            self.assertEqual(result[field], terminal[field])
        self.assertEqual(result["assertions"][0]["assertion_id"], self.created.assertion.id)
        self.assertEqual(self.fixture.files(), before)

    def test_terminal_explains_unknown_time_and_managed_source_distinction(self):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--data-dir", str(self.fixture.data), "ioc", "lifecycle", "domain", "example.com"])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        self.assertIn("Sağlayıcının bildirdiği gözlem: bilinmiyor", stdout.getvalue())
        self.assertIn("güven puanları toplanmaz", stdout.getvalue())

    def test_manifest_describes_lifecycle_as_offline_and_versioned(self):
        _, response = self.fixture.invoke(arguments=("--describe",))
        manifest = response["data"]
        self.assertIn("ioc.lifecycle", manifest["operations"])
        self.assertTrue(manifest["read_only"])
        self.assertFalse(manifest["network_access"])
        self.assertEqual(manifest["ioc_lifecycle"]["policy_version"], "ioc-lifecycle-v1")

    def test_unknown_missing_and_hostile_parameters_are_contract_errors(self):
        bad = ({"path": "/tmp/another-company"}, {"company": "other"}, {"fresh_days": True},
               {"limit": False}, {"source_stale_hours": -1}, {"expected_snapshot": "x"},
               {"indicator_type": []}, {"value": {}}, {"offset": 0.5})
        for change in bad:
            with self.subTest(change=change):
                self.fixture.assert_error("invalid_parameters", request=self.request(**change))
        self.fixture.assert_error("invalid_parameters", request=self.fixture.request("ioc.lifecycle", {}))

    def test_changed_snapshot_has_explicit_error_instead_of_mixing_pages(self):
        first = self.fixture.complete(self.request())
        add(self.fixture.database, "second")
        self.fixture.assert_error("snapshot_changed", request=self.request(expected_snapshot=first["snapshot_id"]), exit_code=1)

    def test_missing_database_is_not_initialized_and_missing_indicator_is_not_recorded(self):
        before = self.fixture.files()
        self.fixture.assert_error("storage_error", request=self.request(), data_dir=self.fixture.root / "missing", exit_code=1)
        result = self.fixture.complete(self.request(value="unknown.example"))
        self.assertEqual(result["assessment"], "not_recorded")
        self.assertEqual(self.fixture.files(), before)


class IocLifecycleCompanyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = platform_fixtures.PlatformIsolationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.claims = {company: add(context.database, company + "-private")
                       for company, context in self.fixture.contexts.items()}

    def test_same_indicator_uses_only_selected_company_and_never_changes_files(self):
        before = self.fixture.files()
        request = self.fixture.request("ioc.lifecycle", PARAMETERS)
        for company, other in (("alpha", "beta"), ("beta", "alpha")):
            result = self.fixture.complete(company, request)
            self.assertEqual(result["total_count"], 1)
            self.assertEqual(result["assertions"][0]["assertion_id"], self.claims[company].assertion.id)
            self.assertNotIn(other + "-private", json.dumps(result))
            self.assertNotIn(self.claims[other].assertion.id, json.dumps(result))
        self.assertEqual(self.fixture.files(), before)

    def test_cross_company_snapshot_and_unknown_company_are_rejected(self):
        first = self.fixture.complete("alpha", self.fixture.request("ioc.lifecycle", PARAMETERS))
        self.fixture.rejected("beta", self.fixture.request("ioc.lifecycle",
            {**PARAMETERS, "expected_snapshot": first["snapshot_id"]}), error="snapshot_changed")
        self.fixture.rejected("missing", self.fixture.request("ioc.lifecycle", PARAMETERS))
        self.fixture.rejected("beta", self.fixture.request("ioc.lifecycle", {**PARAMETERS, "company": "alpha"}), error="invalid_parameters")

    def test_existing_platform_backup_restore_preserves_the_exact_evidence_inputs(self):
        context = self.fixture.contexts["alpha"]
        before = make_ioc_lifecycle_service(context.database).show(**PARAMETERS)
        backup = backup_platform_workspace(context, self.fixture.base / "backup")
        restored = restore_platform_workspace(self.fixture.base / "restored", "alpha", backup)
        after = make_ioc_lifecycle_service(restored.database).show(**PARAMETERS)
        self.assertEqual(before["input_sha256"], after["input_sha256"])
        self.assertEqual(before["indicator_id"], after["indicator_id"])
        self.assertNotEqual(context.workspace_id, restored.workspace_id)
