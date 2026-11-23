"""Component inventory reports reviewed installation facts without running tools."""

import builtins
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.components import ManagedComponentInstallationInspector
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.theharvester_archive import (
    DEFAULT_RESULT_LIMIT, MAX_RESULT_LIMIT, SOURCES, TheHarvesterArchiveSource,
)
from xti.application.brand_username import (
    BrandUsernamePreviewService, SELECTION_PROFILES, SherlockUsernamePreviewService,
)
from xti.application.components import ComponentCatalogService
from xti.domain.assets import ValidationError
from xti.domain.component_pins import MAIGRET_PIN
from xti.domain.components import ComponentInstallation
from xti.interfaces.cli import main
from tests.test_brand_username_watches import FakeSherlockSource, FakeSource


NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
TOOL_IDS = {"maigret", "sherlock", "theharvester", "betterleaks"}


class FakeInspector:
    def __init__(self, states=None):
        self.states = states or {
            "maigret": ComponentInstallation("ready", None),
            "betterleaks": ComponentInstallation("ready", None),
            "sherlock": ComponentInstallation("missing", "Sherlock kurulmamış."),
            "theharvester": ComponentInstallation("invalid", "Kaynak commit'i uyuşmuyor."),
        }
        self.calls = []

    def inspect(self, identifier):
        self.calls.append(identifier)
        return self.states[identifier]


class ComponentCatalogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.missing_data = self.root / "no data area"
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Inventory must stay offline")))
        self.enterContext(patch("socket.create_connection", side_effect=AssertionError("Inventory must stay offline")))
        self.enterContext(patch("subprocess.run", side_effect=AssertionError("Inventory must not run tools")))
        self.enterContext(patch("subprocess.Popen", side_effect=AssertionError("Inventory must not start processes")))
        real_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name.split(".")[0].lower() in {"maigret", "sherlock_project", "theharvester"}:
                raise AssertionError("Inventory imported third-party tool code")
            return real_import(name, *args, **kwargs)

        self.enterContext(patch("builtins.__import__", side_effect=guarded_import))

    def files(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    @staticmethod
    def request(parameters=None, operation="components.list"):
        return {"contract_version": 1, "request_id": "component-test:1",
                "operation": operation, "parameters": {} if parameters is None else parameters}

    def invoke(self, *arguments, request=None, data_dir=None):
        stdout, stderr = StringIO(), StringIO()
        stdin = StringIO(json.dumps(self.request() if request is None else request))
        with patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--data-dir", str(data_dir or self.missing_data), *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_catalog_separates_reviewed_pin_from_installation_and_source_health(self):
        inspector = FakeInspector()
        service = ComponentCatalogService(inspector, clock=lambda: NOW)
        with patch("sqlite3.connect", side_effect=AssertionError("Inventory must not open evidence database")):
            report = service.list()
        self.assertEqual(report["catalog_version"], 1)
        self.assertEqual(report["observed_at"], NOW.isoformat())
        self.assertEqual(report["scope"], "project-managed-tools")
        self.assertEqual(set(inspector.calls), TOOL_IDS)
        self.assertEqual(len(inspector.calls), 4)
        rows = {row["identifier"]: row for row in report["components"]}
        self.assertEqual(set(rows), TOOL_IDS)
        self.assertEqual(rows["maigret"]["expected"]["version"], "0.6.6")
        self.assertEqual(rows["sherlock"]["expected"]["version"], "0.16.2")
        self.assertEqual(rows["maigret"]["installation"]["state"], "ready")
        self.assertEqual(rows["sherlock"]["installation"]["state"], "missing")
        self.assertEqual(rows["theharvester"]["installation"]["state"], "invalid")
        for row in rows.values():
            with self.subTest(component=row["identifier"]):
                self.assertRegex(row["expected"]["commit"], r"^[0-9a-f]{40}$")
                self.assertTrue(row["expected"]["repository"].startswith("https://"))
                self.assertTrue(row["expected"]["integration_profile"])
                self.assertTrue(row["license"]["spdx"])
                self.assertTrue(row["license"]["reference_url"].startswith("https://"))
                self.assertEqual(row["installation"]["scope"], "project-managed")
                self.assertEqual(row["installation"]["verification"], "metadata_only")
                self.assertIs(row["installation"]["execution_tested"], False)
                self.assertNotIn("observed_version", row["installation"])
                self.assertNotIn("latest_status", row["installation"])
                self.assertNotIn("last_success_at", row["installation"])
                if row['identifier'] == 'betterleaks':
                    self.assertEqual(row['source_status_ids'], [])  # Offline detector, not a network source.
                    self.assertFalse(row['configuration']['validation'])
                else:
                    self.assertTrue(row["source_status_ids"])
                self.assertTrue(row["runtime"]["python_requirement"])
                self.assertTrue(row["runtime"]["deployment"])
                self.assertTrue(row["configuration"])
                self.assertTrue(row["setup_command"])
                self.assertTrue(row["notes"])
        self.assertTrue(report["notes"])
        self.assertEqual(self.files(), {})

    def test_missing_installation_still_exposes_pinned_configuration_and_license(self):
        missing = {identifier: ComponentInstallation("missing", "Kurulum yok.") for identifier in TOOL_IDS}
        report = ComponentCatalogService(FakeInspector(missing), clock=lambda: NOW).list()
        for row in report["components"]:
            with self.subTest(component=row["identifier"]):
                self.assertEqual(row["installation"]["state"], "missing")
                self.assertTrue(row["expected"]["commit"])
                self.assertTrue(row["configuration"])
                self.assertTrue(row["license"]["spdx"])
                self.assertNotIn("installed_version", row)
                self.assertNotIn("observed_version", row)

    def test_real_missing_project_inspection_does_not_create_paths(self):
        project = self.root / "missing project"
        inspector = ManagedComponentInstallationInspector(project)
        with patch("sqlite3.connect", side_effect=AssertionError("No evidence access")):
            report = ComponentCatalogService(inspector, clock=lambda: NOW).list()
        self.assertEqual({item["installation"]["state"] for item in report["components"]}, {"missing"})
        self.assertFalse(project.exists())
        self.assertEqual(self.files(), {})

    def test_invalid_inspection_state_cannot_be_reported_as_ready(self):
        invalid = {identifier: ComponentInstallation("live_available", None) for identifier in TOOL_IDS}
        with self.assertRaises((ValidationError, ValueError)):
            ComponentCatalogService(FakeInspector(invalid), clock=lambda: NOW).list()

    def test_naive_clock_is_rejected_before_installation_inspection(self):
        inspector = FakeInspector()
        with self.assertRaises((ValidationError, ValueError)):
            ComponentCatalogService(inspector, clock=lambda: datetime(2026, 11, 15)).list()
        self.assertEqual(inspector.calls, [])

    def test_new_component_requires_explicit_configuration_before_inspection(self):
        inspector = FakeInspector()
        future_pin = replace(MAIGRET_PIN, identifier="future-tool")
        with patch("xti.application.components.REVIEWED_COMPONENT_PINS", (future_pin,)), \
                self.assertRaises(ValidationError):
            ComponentCatalogService(inspector, clock=lambda: NOW).list()
        self.assertEqual(inspector.calls, [])

    def test_username_configuration_profiles_match_actual_default_and_extended_calls(self):
        rows = {row["identifier"]: row for row in
                ComponentCatalogService(FakeInspector(), clock=lambda: NOW).list()["components"]}
        integrations = (("maigret", BrandUsernamePreviewService, FakeSource),
                        ("sherlock", SherlockUsernamePreviewService, FakeSherlockSource))
        for identifier, service_type, source_type in integrations:
            with self.subTest(component=identifier):
                configuration = rows[identifier]["configuration"]
                profiles = {item["name"]: tuple(item["platforms"])
                            for item in configuration["selection_profiles"]}
                self.assertEqual(set(profiles), set(SELECTION_PROFILES))
                source = source_type({}, {}, {}, {})
                service = service_type(source)
                service.preview("samplebrand")
                self.assertEqual(source.calls[-1], (
                    "samplebrand", profiles[configuration["default_profile"]],
                    configuration["request_timeout_seconds"]["default"],
                ))
                for profile, platforms in profiles.items():
                    service.preview("samplebrand", profile=profile)
                    self.assertEqual(source.calls[-1][1], platforms)
                self.assertEqual(configuration["custom_selection"], "subset_of_extended")
                selection = profiles["extended"][:2]
                service.preview("samplebrand", platforms=selection)
                self.assertEqual(source.calls[-1][1], selection)
                before = len(source.calls)
                with self.assertRaises(ValidationError):
                    service.preview("samplebrand", platforms=("unreviewed-site",))
                self.assertEqual(len(source.calls), before)

    def test_username_configuration_timeout_bounds_match_service_validation(self):
        rows = {row["identifier"]: row for row in
                ComponentCatalogService(FakeInspector(), clock=lambda: NOW).list()["components"]}
        integrations = (("maigret", BrandUsernamePreviewService, FakeSource),
                        ("sherlock", SherlockUsernamePreviewService, FakeSherlockSource))
        for identifier, service_type, source_type in integrations:
            with self.subTest(component=identifier):
                limits = rows[identifier]["configuration"]["request_timeout_seconds"]
                source = source_type({}, {})
                service = service_type(source)
                for timeout in (limits["minimum"], limits["maximum"]):
                    service.preview("samplebrand", request_timeout=timeout)
                    self.assertEqual(source.calls[-1][2], timeout)
                for timeout in (limits["minimum"] - 1, limits["maximum"] + 1):
                    with self.assertRaises(ValidationError):
                        service.preview("samplebrand", request_timeout=timeout)
                self.assertEqual(len(source.calls), 2)

    def test_archive_configuration_matches_adapter_sources_and_result_bounds(self):
        rows = {row["identifier"]: row for row in
                ComponentCatalogService(FakeInspector(), clock=lambda: NOW).list()["components"]}
        configuration = rows["theharvester"]["configuration"]
        self.assertEqual(tuple(configuration["sources"]), SOURCES)
        self.assertIs(configuration["active_target_checks"], False)
        limits = configuration["result_limit"]
        self.assertEqual(limits["default"], DEFAULT_RESULT_LIMIT)
        self.assertEqual(limits["default"], TheHarvesterArchiveSource().result_limit)
        self.assertEqual(limits["maximum"], MAX_RESULT_LIMIT)
        self.assertEqual(TheHarvesterArchiveSource(result_limit=limits["maximum"]).result_limit,
                         limits["maximum"])
        with self.assertRaises(ValueError):
            TheHarvesterArchiveSource(result_limit=limits["maximum"] + 1)

    def test_cli_json_and_engine_use_same_component_data_without_database(self):
        inspector = FakeInspector()
        with patch.object(ManagedComponentInstallationInspector, "inspect", side_effect=inspector.inspect), \
                patch("sqlite3.connect", side_effect=AssertionError("Inventory must not open database")), \
                patch.object(SQLiteAssetRepository, "initialize", side_effect=AssertionError("No initialization")):
            code, output, error = self.invoke("--json", "components")
            self.assertEqual((code, error), (0, ""))
            cli = json.loads(output)
            self.assertEqual(set(cli), {"ok", "data"})
            self.assertIs(cli["ok"], True)
            code, output, error = self.invoke("engine")
            self.assertEqual((code, error), (0, ""))
            engine = json.loads(output)
            self.assertEqual(engine["contract_version"], 1)
            self.assertEqual(engine["operation"], "components.list")
            self.assertEqual(engine["request_id"], "component-test:1")
            self.assertEqual(engine["status"], "complete")
            self.assertIsNone(engine["error"])
        self.assertEqual(cli["data"]["components"], engine["data"]["components"])
        self.assertEqual(cli["data"]["scope"], engine["data"]["scope"])
        self.assertFalse(self.missing_data.exists())
        self.assertEqual(self.files(), {})

    def test_human_terminal_escapes_installation_errors_without_starting_tools(self):
        message = "metadata\x1b[31m\rbroken"
        with patch.object(ManagedComponentInstallationInspector, "inspect",
                          return_value=ComponentInstallation("invalid", message)):
            code, output, error = self.invoke("components")
        self.assertEqual((code, error), (0, ""))
        self.assertNotIn("\x1b", output)
        self.assertNotIn("\r", output)
        self.assertIn("Maigret", output)
        self.assertIn("Sherlock", output)
        self.assertIn("theHarvester", output)
        self.assertFalse(self.missing_data.exists())

    def test_unknown_component_parameters_are_rejected_before_inspection(self):
        options = ({"path": "/private"}, {"data_dir": "/private"},
                   {"install": True}, {"upgrade": True}, {"tenant_id": "other"},
                   {"command": "collect example.com"}, {"identifier": "unreviewed-tool"})
        with patch.object(ManagedComponentInstallationInspector, "inspect") as inspect, \
                patch("sqlite3.connect", side_effect=AssertionError("Invalid request must not open database")):
            for parameters in options:
                with self.subTest(parameters=parameters):
                    code, output, error = self.invoke("engine", request=self.request(parameters))
                    self.assertEqual((code, error), (2, ""))
                    response = json.loads(output)
                    self.assertEqual(response["status"], "error")
                    self.assertIsNone(response["data"])
                    self.assertEqual(response["error"]["code"], "invalid_parameters")
            inspect.assert_not_called()
        self.assertFalse(self.missing_data.exists())

    def test_engine_manifest_advertises_added_operation_and_keeps_prior_operations(self):
        with patch.object(ManagedComponentInstallationInspector, "inspect") as inspect, \
                patch("sqlite3.connect", side_effect=AssertionError("Describe must not open database")):
            code, output, error = self.invoke("engine", "--describe")
            self.assertEqual((code, error), (0, ""))
            response = json.loads(output)
            self.assertEqual(response["contract_version"], 1)
            self.assertGreaterEqual(set(response["data"]["operations"]),
                                    {"search", "record.get", "sources.status", "components.list"})
            inspect.assert_not_called()
        self.assertFalse(self.missing_data.exists())

    def test_unavailable_tools_do_not_block_old_engine_evidence_reads(self):
        data = self.root / "existing evidence"
        repository = SQLiteAssetRepository(data / "xti.db")
        repository.initialize()
        asset, _ = repository.add("example.com")
        before = self.files()
        with patch.object(ManagedComponentInstallationInspector, "inspect",
                          return_value=ComponentInstallation("missing", "Araç kurulmamış.")), \
                patch.object(SQLiteAssetRepository, "initialize", side_effect=AssertionError("No initialization")):
            code, output, error = self.invoke("engine", data_dir=data)
            self.assertEqual((code, error), (0, ""))
            self.assertEqual({row["installation"]["state"] for row in json.loads(output)["data"]["components"]}, {"missing"})
            code, output, error = self.invoke("engine", data_dir=data,
                request=self.request({"query": "example.com", "kinds": ["domain"]}, operation="search"))
            self.assertEqual((code, error), (0, ""))
            result = json.loads(output)["data"]
            self.assertEqual(result["total_match_count"], 1)
            reference = result["results"][0]["reference"]
            self.assertEqual(reference["record_id"], asset.id)
            code, output, error = self.invoke("engine", data_dir=data,
                request=self.request({"reference": reference}, operation="record.get"))
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(json.loads(output)["data"]["record"]["value"], "example.com")
        self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
