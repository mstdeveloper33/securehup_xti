"""P09 source-governance contract, terminal and integration acceptance."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from xti.application.source_governance import (
    PROVENANCE_FIELDS,
    SourceGovernanceError,
    SourceGovernanceService,
)
from xti.domain.assets import ValidationError
from xti.domain.engine import ENGINE_OPERATIONS, EngineContractError, parse_engine_request
from xti.domain.platform_engine import PLATFORM_OPERATIONS
from xti.interfaces.cli import main
from xti.interfaces.entrypoint import main as entrypoint_main


class SourceGovernanceServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = SourceGovernanceService()

    def test_catalog_is_complete_deterministic_and_explicit_about_gates(self):
        result = self.service.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["source_count"], 53)
        self.assertEqual(sum(result["integration_states"].values()), 53)
        self.assertEqual(result["required_provenance_fields"], list(PROVENANCE_FIELDS))
        identifiers = [item.identifier for item in self.service.manifests]
        self.assertEqual(identifiers, sorted(identifiers))
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(len(result["catalog_sha256"]), 64)

        by_id = {item.identifier: item for item in self.service.manifests}
        self.assertEqual(by_id["brand:brightdata-linkedin"].integration_state, "conditional")
        self.assertEqual(by_id["brand:brightdata-linkedin"].cost_model, "paid")
        self.assertTrue(by_id["brand:brightdata-linkedin"].prerequisites)
        self.assertEqual(by_id["credential:xposedornot-domain"].credential_mode, "required")
        self.assertEqual(by_id["content:bluesky-public-search"].integration_state, "active")
        self.assertEqual(by_id["content:bluesky-public-search"].retention_policy, "review_required")
        self.assertEqual(by_id["credential:xposedornot-password"].retention_policy, "not_enabled")
        self.assertEqual(by_id["cisa-kev"].integration_state, "disabled")
        self.assertEqual(by_id["surface:nmap"].target_contact, "direct_authorized")
        self.assertIn("probe", by_id["surface:nmap"].quota_policy)
        self.assertEqual(by_id["credential:xposedornot-password"].retry_policy, "explicit_only")
        self.assertEqual(by_id["telemetry:xti-sensor-v1"].integration_state, "active")
        self.assertEqual(by_id["telemetry:cowrie-jsonl"].integration_state, "conditional")
        self.assertEqual(by_id["telemetry:cape-report-v1"].integration_state, "conditional")
        self.assertEqual(by_id["telemetry:cape-report-v1"].target_contact, "none")

    def test_every_source_has_normalization_provenance_rights_and_operating_policy(self):
        for item in self.service.manifests:
            with self.subTest(item.identifier):
                self.assertEqual(item.provenance_fields, PROVENANCE_FIELDS)
                self.assertTrue(item.normalized_record_types)
                self.assertTrue(item.languages)
                self.assertTrue(item.regions)
                self.assertTrue(item.commands)
                self.assertTrue(item.limits)
                self.assertTrue(item.health_command)
                self.assertTrue(item.quota_policy)
                self.assertTrue(item.reference_url.startswith("https://"))
                if item.integration_state == "conditional":
                    self.assertTrue(item.prerequisites)
                if item.credential_mode == "required":
                    self.assertNotEqual(item.integration_state, "active")

    def test_filters_pagination_and_hash_are_stable(self):
        first = self.service.catalog(integration_state="conditional", offset=0, limit=3)
        second = self.service.catalog(integration_state="conditional", offset=3, limit=3)
        repeated = self.service.catalog(integration_state="conditional", offset=0, limit=3)
        self.assertEqual(first, repeated)
        self.assertEqual(first["catalog_sha256"], second["catalog_sha256"])
        self.assertEqual(first["next_offset"], 3)
        self.assertTrue(first["has_more"])
        self.assertFalse(
            {item["identifier"] for item in first["sources"]}
            & {item["identifier"] for item in second["sources"]}
        )
        languages = self.service.catalog(language="fr")
        self.assertEqual([item["identifier"] for item in languages["sources"]], ["news:cert-fr"])

    def test_registry_accepts_reviewed_extension_without_changing_service_logic(self):
        base = self.service.manifests[0]
        extension = replace(
            base,
            identifier="zz:test-source",
            label="Test source",
            manifest_version=2,
        )
        service = SourceGovernanceService((*self.service.manifests, extension))
        self.assertEqual(service.get(identifier="zz:test-source")["manifest_version"], 2)
        with self.assertRaises(ValidationError):
            SourceGovernanceService((extension, *self.service.manifests))
        with self.assertRaises(ValidationError):
            SourceGovernanceService((*self.service.manifests, self.service.manifests[-1]))

    def test_manifest_rejects_missing_provenance_invalid_date_and_unsafe_reference(self):
        base = self.service.manifests[0]
        invalid = (
            replace(base, provenance_fields=tuple(
                field for field in PROVENANCE_FIELDS if field != "observed_at"
            )),
            replace(base, terms_reviewed_at="2026-19-39"),
            replace(base, reference_url="https://user:secret@example.com/source"),
            replace(base, reference_url="https:///missing-host"),
        )
        for manifest in invalid:
            with self.subTest(manifest=manifest), self.assertRaises(ValidationError):
                SourceGovernanceService((manifest,))

    def test_unknown_and_invalid_queries_fail_before_any_health_read(self):
        with self.assertRaises(SourceGovernanceError) as missing:
            self.service.get(identifier="missing")
        self.assertEqual(missing.exception.code, "not_found")
        for call in (
            lambda: self.service.catalog(limit=0),
            lambda: self.service.catalog(offset=-1),
            lambda: self.service.catalog(integration_state="enabled"),
            lambda: self.service.catalog(domain="example.com"),
            lambda: self.service.get(identifier="../secret"),
        ):
            with self.subTest(call=call), self.assertRaises(ValidationError):
                call()

    def test_recorded_health_is_opt_in_and_kept_separate_from_manifest(self):
        evidence = SimpleNamespace(
            identifier="social:maigret", latest_status="complete", installation="ready",
            last_attempt_at="2026-11-23T00:00:00+00:00",
            last_success_at="2026-11-23T00:00:00+00:00", record_count=4,
            cooldown_until=None,
        )
        row = SimpleNamespace(
            evidence=evidence, freshness="fresh", needs_attention=False,
        )
        readiness = SimpleNamespace(show=lambda **_: SimpleNamespace(
            observed_at="2026-11-23T01:00:00+00:00", storage_state="ready",
            stale_after_hours=24, sources=(row,),
        ))
        service = SourceGovernanceService(readiness=readiness)
        plain = service.get(identifier="brand:maigret")
        enriched = service.get(identifier="brand:maigret", include_health=True)
        self.assertNotIn("health", plain)
        self.assertEqual(enriched["health"]["state"], "ready")
        self.assertEqual(enriched["health"]["evidence"][0]["record_count"], 4)
        self.assertEqual(enriched["health_snapshot"]["consistency"], "independent_source_reads")


class SourceGovernanceInterfaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.data = self.root / "missing-data"
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("No network")))
        self.enterContext(patch("socket.create_connection", side_effect=AssertionError("No network")))

    def invoke_cli(self, *arguments):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            with patch("subprocess.run", side_effect=AssertionError("No tools")), \
                    patch("subprocess.Popen", side_effect=AssertionError("No tools")):
                code = main(["--data-dir", str(self.data), "--json", "sources", *arguments])
        payload = stdout.getvalue() or stderr.getvalue()
        return code, json.loads(payload)

    def invoke_engine(self, operation, parameters):
        request = {
            "contract_version": 1,
            "request_id": "p09:test",
            "operation": operation,
            "parameters": parameters,
        }
        stdout, stderr = StringIO(), StringIO()
        with patch("sys.stdin", StringIO(json.dumps(request))), \
                redirect_stdout(stdout), redirect_stderr(stderr), \
                patch("subprocess.run", side_effect=AssertionError("No tools")), \
                patch("subprocess.Popen", side_effect=AssertionError("No tools")):
            code = main(["--data-dir", str(self.data), "engine"])
        self.assertEqual(stderr.getvalue(), "")
        return code, json.loads(stdout.getvalue())

    def test_terminal_catalog_show_validate_are_offline_and_do_not_create_storage(self):
        code, bare = self.invoke_cli()
        self.assertEqual(code, 0)
        code, explicit = self.invoke_cli("catalog")
        self.assertEqual(code, 0)
        self.assertEqual(bare, explicit)
        code, catalog = self.invoke_cli("catalog", "--state", "conditional", "--limit", "2")
        self.assertEqual(code, 0)
        self.assertEqual(len(catalog["data"]["sources"]), 2)
        code, detail = self.invoke_cli("show", "credential:xposedornot-domain")
        self.assertEqual((code, detail["data"]["integration_state"]), (0, "conditional"))
        code, validation = self.invoke_cli("validate")
        self.assertEqual((code, validation["data"]["valid"]), (0, True))
        self.assertFalse(self.data.exists())

    def test_terminal_unknown_source_has_stable_not_found_error(self):
        code, response = self.invoke_cli("show", "missing")
        self.assertEqual((code, response["ok"], response["error"]["code"]),
                         (3, False, "not_found"))

    def test_engine_operations_are_bounded_offline_and_machine_readable(self):
        self.assertTrue({"sources.catalog", "sources.get", "sources.validate"} <= set(ENGINE_OPERATIONS))
        code, catalog = self.invoke_engine("sources.catalog", {"kind": "code_repository", "limit": 2})
        self.assertEqual((code, catalog["status"]), (0, "complete"))
        self.assertEqual(len(catalog["data"]["sources"]), 2)
        code, detail = self.invoke_engine("sources.get", {"identifier": "code:github-repositories"})
        self.assertEqual((code, detail["data"]["identifier"]), (0, "code:github-repositories"))
        code, validation = self.invoke_engine("sources.validate", {})
        self.assertEqual((code, validation["data"]["valid"]), (0, True))
        self.assertFalse(self.data.exists())

    def test_engine_validation_rejects_scope_injection_and_unknown_source(self):
        with self.assertRaises(EngineContractError) as rejected:
            parse_engine_request({
                "contract_version": 1, "request_id": "p09:bad",
                "operation": "sources.catalog",
                "parameters": {"data_dir": "/private"},
            })
        self.assertEqual(rejected.exception.code, "invalid_parameters")
        code, response = self.invoke_engine("sources.get", {"identifier": "missing"})
        self.assertEqual((code, response["error"]["code"]), (3, "not_found"))

    def test_company_platform_exposes_same_catalog_in_company_scope(self):
        platform_root = self.root / "platform"
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = entrypoint_main([
                "platform", "provision", "--root", str(platform_root), "--company", "firma-a",
            ])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        request = {
            "contract_version": 1, "request_id": "p09:platform",
            "operation": "sources.catalog", "parameters": {"limit": 1},
        }
        stdout, stderr = StringIO(), StringIO()
        with patch("sys.stdin", StringIO(json.dumps(request))), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = entrypoint_main([
                "platform", "request", "--root", str(platform_root), "--company", "firma-a",
            ])
        response = json.loads(stdout.getvalue())
        self.assertEqual((code, stderr.getvalue(), response["status"]), (0, "", "complete"))
        self.assertEqual(response["scope"]["mode"], "company-workspace")
        self.assertEqual(len(response["data"]["sources"]), 1)
        self.assertIn("sources.catalog", PLATFORM_OPERATIONS)


if __name__ == "__main__":
    unittest.main()
