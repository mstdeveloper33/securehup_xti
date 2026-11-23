"""P12 terminal, engine and company JSON boundary acceptance."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from xti.adapters.company_workspaces import provision_company_workspace
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.domain.engine import EngineContractError, parse_engine_request
from xti.domain.platform_engine import parse_platform_request
from xti.domain.telemetry import TelemetryError
from xti.interfaces.cli import main
from xti.interfaces.platform_engine import execute_platform_request


def record(native_id="sensor:one"):
    return {
        "native_id": native_id, "kind": "dns_query",
        "event_at": "2026-11-23T08:00:00+00:00",
        "summary": "Authorized sinkhole observed contract.example",
        "outcome": "observed", "src_ip": "192.0.2.10", "dst_ip": "192.0.2.53",
        "src_port": 53000, "dst_port": 53, "protocol": "udp",
        "domain": "contract.example", "url": None, "hashes": {},
        "indicators": [{"type": "domain", "value": "contract.example"}],
        "attributes": [{"name": "query_type", "value": "A"}], "tags": ["p12"],
    }


class TelemetryContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.alpha = provision_company_workspace(self.root / "companies", "alpha")
        self.beta = provision_company_workspace(self.root / "companies", "beta")
        for context in (self.alpha, self.beta):
            SQLiteAssetRepository(context.database).initialize()
        self.alpha_org = SQLiteOrganizationRepository(self.alpha.database).add(
            name_key="alpha", display_name="Alpha",
            reason="P12 alpha scope", recorded_at="2026-11-23T07:50:00+00:00",
        ).organization
        self.beta_org = SQLiteOrganizationRepository(self.beta.database).add(
            name_key="beta", display_name="Beta",
            reason="P12 beta scope", recorded_at="2026-11-23T07:50:00+00:00",
        ).organization

    @staticmethod
    def request(operation, parameters, request_id="p12:request"):
        return {"contract_version": 1, "request_id": request_id,
                "operation": operation, "parameters": parameters}

    def test_platform_writes_and_engine_reads_are_company_isolated(self):
        wrong = parse_platform_request(self.request("telemetry.source.add", {
            "name": "Alpha sensor", "organization_id": self.alpha_org.id,
            "source_kind": "sinkhole", "input_format": "xti-sensor-v1",
            "description": "P12 company contract", "idempotency_key": "source-alpha",
            "expected_workspace_id": self.beta.workspace_id,
        }))
        with self.assertRaisesRegex(EngineContractError, "güncel firma"):
            execute_platform_request(self.alpha, wrong)

        add = parse_platform_request(self.request("telemetry.source.add", {
            "name": "Alpha sensor", "organization_id": self.alpha_org.id,
            "source_kind": "sinkhole", "input_format": "xti-sensor-v1",
            "description": "P12 company contract", "idempotency_key": "source-alpha",
            "expected_workspace_id": self.alpha.workspace_id,
        }))
        source = execute_platform_request(self.alpha, add)["source"]
        ingest = parse_platform_request(self.request("telemetry.ingest", {
            "source_id": source["id"], "expected_revision": 1,
            "records": [record()], "idempotency_key": "ingest-alpha",
            "expected_workspace_id": self.alpha.workspace_id,
        }))
        completed = execute_platform_request(self.alpha, ingest)
        self.assertEqual((completed["status"], completed["added_count"]), ("complete", 1))

        listing = parse_engine_request(self.request(
            "telemetry.records", {"organization_id": self.alpha_org.id, "limit": 50},
        ))
        alpha_records = execute_platform_request(self.alpha, listing)
        self.assertEqual(len(alpha_records["items"]), 1)
        with self.assertRaises(TelemetryError) as missing:
            execute_platform_request(
                self.beta,
                parse_engine_request(self.request("telemetry.source.get", {"identifier": source["id"]})),
            )
        self.assertEqual(missing.exception.code, "not_found")

        reference = {
            "kind": "telemetry", "record_type": "dns_query",
            "namespace": "local-telemetry", "record_id": alpha_records["items"][0]["id"],
        }
        detail = execute_platform_request(
            self.alpha,
            parse_engine_request(self.request("record.get", {"reference": reference})),
        )
        self.assertEqual(detail["record"]["organization_id"], self.alpha_org.id)
        with self.assertRaises(EngineContractError) as absent:
            execute_platform_request(
                self.beta,
                parse_engine_request(self.request("record.get", {"reference": reference})),
            )
        self.assertEqual(absent.exception.code, "not_found")

    def test_terminal_capabilities_are_json_and_do_not_contact_network(self):
        data = self.root / "local-data"
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(data), "--json", "telemetry", "capabilities"])
        response = json.loads(output.getvalue())
        self.assertEqual((code, error.getvalue(), response["ok"]), (0, "", True))
        self.assertIn("cowrie-jsonl", response["data"]["input_formats"])
        self.assertIn("passwords", response["data"]["never_stored"])
        self.assertFalse(data.exists())

    def test_terminal_preview_import_and_idempotent_replay_use_the_public_file_flow(self):
        data = self.root / "local-file-flow"
        database = data / "xti.db"
        SQLiteAssetRepository(database).initialize()
        organization = SQLiteOrganizationRepository(database).add(
            name_key="local p12", display_name="Local P12",
            reason="P12 terminal file acceptance",
            recorded_at="2026-11-23T07:50:00+00:00",
        ).organization

        def cli(*arguments):
            output, error = StringIO(), StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                code = main(["--data-dir", str(data), "--json", "telemetry", *arguments])
            self.assertEqual((code, error.getvalue()), (0, ""))
            response = json.loads(output.getvalue())
            self.assertTrue(response["ok"])
            return response["data"]

        source = cli(
            "source-add", "--organization", organization.id,
            "--name", "Local authorized sinkhole", "--kind", "sinkhole",
            "--format", "xti-sensor-v1", "--description", "P12 local file flow",
            "--idempotency-key", "cli:p12:source",
        )["source"]
        input_file = self.root / "sensor.jsonl"
        input_file.write_text(json.dumps({
            "format": "xti-sensor-record", "version": 1, "record": record(),
        }) + "\n", encoding="utf-8")
        preview = cli("preview", str(input_file), "--format", "xti-sensor-v1")
        imported = cli(
            "import", source["id"], str(input_file), "--format", "xti-sensor-v1",
            "--expected-revision", "1", "--expected-content-sha256", preview["content_sha256"],
            "--idempotency-key", "cli:p12:import",
        )
        replayed = cli(
            "import", source["id"], str(input_file), "--format", "xti-sensor-v1",
            "--expected-revision", "1", "--expected-content-sha256", preview["content_sha256"],
            "--idempotency-key", "cli:p12:import",
        )
        self.assertEqual((imported["status"], imported["added_count"]), ("complete", 1))
        self.assertEqual((replayed["id"], replayed["replayed"]), (imported["id"], True))
        self.assertEqual(len(cli("records", "--organization", organization.id)["items"]), 1)

    def test_contract_rejects_file_paths_unknown_fields_and_oversized_inline_batches(self):
        invalid = (
            {"source_id": "x", "expected_revision": 1, "records": [record()],
             "idempotency_key": "x", "path": "/tmp/report.json",
             "expected_workspace_id": self.alpha.workspace_id},
            {"source_id": self.alpha_org.id, "expected_revision": 1,
             "records": [record(str(index)) for index in range(1001)],
             "idempotency_key": "x", "expected_workspace_id": self.alpha.workspace_id},
        )
        for parameters in invalid:
            with self.subTest(size=len(parameters.get("records", []))), self.assertRaises(EngineContractError):
                parse_platform_request(self.request("telemetry.ingest", parameters))


if __name__ == "__main__":
    unittest.main()
