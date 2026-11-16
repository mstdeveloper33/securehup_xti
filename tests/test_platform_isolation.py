"""Actual platform CLI requests cannot cross independently provisioned companies."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from xti.adapters.company_workspaces import resolve_company_workspace, WORKSPACE_MARKER
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
from xti.adapters.sqlite_mentions import SQLiteMentionRepository
from xti.adapters.sqlite_mention_targets import SQLiteMentionTargetRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.domain.mentions import MentionHit, MentionRequest, MentionResponse, build_query
from xti.interfaces.cli import main


class PlatformIsolationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "platform"
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("offline requests")))
        self.enterContext(patch("socket.create_connection", side_effect=AssertionError("offline requests")))
        self.enterContext(patch("subprocess.run", side_effect=AssertionError("no subprocess on request")))
        self.enterContext(patch("subprocess.Popen", side_effect=AssertionError("no process on request")))
        self.contexts, self.assets, self.organizations, self.profiles = {}, {}, {}, {}
        at = datetime.now(timezone.utc).isoformat()
        for company in ("alpha", "beta"):
            code, response = self.invoke(company, action="provision")
            self.assertEqual((code, response["status"]), (0, "complete"), response)
            context = self.contexts[company] = resolve_company_workspace(self.root, company)
            self.assets[company], _ = SQLiteAssetRepository(context.database).add(company + ".example")
            self.organizations[company] = SQLiteOrganizationRepository(context.database).add(
                name_key="same display name", display_name="Same display name",
                reason="Explicit company fixture", recorded_at=at).organization
            target = SQLiteMentionTargetRepository(context.database).resolve(
                "organization", self.organizations[company].id)
            request = MentionRequest(target, "news", 10)
            hit = MentionHit("https://publisher.example/" + company,
                             "Same display name " + company + " private evidence",
                             company + " stored excerpt", "2026-11-16", .8)
            SQLiteMentionRepository(context.database).apply(request,
                MentionResponse(build_query(target), None, (hit,), 1), started_at=at, finished_at=at)
            self.profiles[company] = SQLiteCollectionProfileRepository(context.database).save(
                "Daily", CollectionProfileDefinition(company + ".example", task_ids=("ioc-feodo",)),
                recorded_at=at).profile

    @staticmethod
    def request(operation="search", parameters=None, **changes):
        return {"contract_version": 1, "request_id": "same-correlation-id", "operation": operation,
                "parameters": {"query": "example", "kinds": ["domain"]}
                if parameters is None else parameters, **changes}

    def invoke(self, company, request=None, *, raw=None, action="request", extra=(), prefix=(), root=None):
        stdout, stderr = StringIO(), StringIO()
        raw = json.dumps(self.request() if request is None else request) if raw is None else raw
        args = [*prefix, "platform", action, "--root", str(root or self.root), "--company", company, *extra]
        with patch("sys.stdin", StringIO(raw)), redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(args)
        self.assertEqual(stderr.getvalue(), "", stdout.getvalue())
        response = json.loads(stdout.getvalue())
        self.assertEqual(response["protocol"], "xti-platform")
        self.assertEqual(response["contract_version"], 1)
        return code, response

    def complete(self, company, request=None, **kwargs):
        code, response = self.invoke(company, request, **kwargs)
        self.assertEqual((code, response["status"], response["error"]), (0, "complete", None), response)
        self.assertEqual(response["scope"], self.contexts[company].scope)
        return response["data"]

    def rejected(self, company, request=None, *, error=None, **kwargs):
        code, response = self.invoke(company, request, **kwargs)
        self.assertNotEqual(code, 0, response)
        self.assertEqual((response["status"], response["data"]), ("error", None), response)
        if error:
            self.assertEqual(response["error"]["code"], error, response)
        return response

    def files(self):
        return {str(path.relative_to(self.base)): path.read_bytes()
                for path in self.base.rglob("*") if path.is_file()}

    def submit(self, company, key="same-durable-key"):
        return self.complete(company, self.request("jobs.submit", {
            "idempotency_key": key, "profile_name": "Daily",
            "profile_revision": self.profiles[company].revision,
            "expected_workspace_id": self.contexts[company].workspace_id}))

    def test_search_and_record_details_are_selected_by_company_and_reads_preserve_files(self):
        before = self.files()
        for company, other in (("alpha", "beta"), ("beta", "alpha")):
            data = self.complete(company)
            self.assertEqual(data["total_match_count"], 1)
            self.assertEqual(data["results"][0]["record_id"], self.assets[company].id)
            self.assertNotIn(other + ".example", json.dumps(data))
            reference = data["results"][0]["reference"]
            details = self.complete(company, self.request("record.get", {"reference": reference}))
            self.assertIn(company + ".example", json.dumps(details))
            rejected = self.rejected(other, self.request("record.get", {"reference": reference}), error="not_found")
            self.assertEqual(rejected["scope"], self.contexts[other].scope)
            self.assertNotIn(company + ".example", json.dumps(rejected))
        self.assertEqual(self.files(), before)

    def test_same_named_organization_content_never_crosses_company_or_source_ids(self):
        before = self.files()
        for company, other in (("alpha", "beta"), ("beta", "alpha")):
            request = self.request("organization.content", {"organization_id": self.organizations[company].id})
            content = self.complete(company, request)
            self.assertEqual(content["organization"]["id"], self.organizations[company].id)
            self.assertTrue(content["stored_data_only"])
            items = content["sections"]["content"]["items"]
            self.assertEqual([item["available_excerpt"] for item in items], [company + " stored excerpt"])
            self.assertEqual(items[0]["source_url"], "https://publisher.example/" + company)
            self.assertNotIn(other + " stored excerpt", json.dumps(content))
            self.rejected(other, request)
        self.assertEqual(self.files(), before)

    def test_identical_record_ids_in_two_databases_still_resolve_only_local_evidence(self):
        identifier = "591d7bcb-8401-493f-8528-dd783c6db8c4"
        with patch("xti.adapters.sqlite.uuid4", return_value=UUID(identifier)):
            for company in ("alpha", "beta"):
                SQLiteAssetRepository(self.contexts[company].database).add("collision-" + company + ".example")
        request = self.request("record.get", {"reference": {"kind": "domain",
            "record_type": "registered_domain", "namespace": "local-assets", "record_id": identifier}})
        before = self.files()
        for company, other in (("alpha", "beta"), ("beta", "alpha")):
            content = self.complete(company, request)
            self.assertIn("collision-" + company + ".example", json.dumps(content))
            self.assertNotIn("collision-" + other + ".example", json.dumps(content))
        self.assertEqual(self.files(), before)

    def test_profiles_with_same_name_remain_separate_and_have_scoped_ids(self):
        for company, other in (("alpha", "beta"), ("beta", "alpha")):
            profiles = self.complete(company, self.request("profiles.list", {}))
            self.assertEqual(len(profiles["profiles"]), 1)
            self.assertEqual(profiles["profiles"][0]["id"], self.profiles[company].id)
            self.assertNotIn(self.profiles[other].id, json.dumps(profiles))

    def test_content_scope_limit_is_rejected_at_contract_boundary(self):
        before = self.files()
        with patch("xti.adapters.sqlite_company_content.SQLiteCompanyContentRepository.read",
                   side_effect=AssertionError("invalid pagination reached storage")):
            self.rejected("alpha", self.request("organization.content", {
                "organization_id": self.organizations["alpha"].id, "scope_limit": 101}),
                error="invalid_parameters")
        self.assertEqual(self.files(), before)

    def test_request_cannot_select_company_path_or_override_scope(self):
        before = self.files()
        for field, value in (("company_id", "beta"), ("tenant_id", "beta"),
                             ("data_dir", str(self.contexts["beta"].data_dir)),
                             ("scope", self.contexts["beta"].scope), ("root", str(self.root))):
            with self.subTest(field=field):
                self.rejected("alpha", self.request(**{field: value}), error="invalid_request")
                self.rejected("alpha", self.request(parameters={"query": "beta", field: value}),
                              error="invalid_parameters")
        self.assertEqual(self.files(), before)

    def test_duplicate_json_and_legacy_data_directory_selector_are_rejected_without_mutation(self):
        before = self.files()
        raw = ('{"contract_version":1,"request_id":"one","operation":"search",'
               '"parameters":{"query":"alpha","query":"beta"}}')
        self.rejected("alpha", raw=raw, error="invalid_request")
        self.rejected("alpha", prefix=("--data-dir", str(self.contexts["beta"].data_dir)),
                      error="invalid_request")
        self.assertEqual(self.files(), before)

    def test_unknown_disabled_wrong_binding_or_missing_scope_never_falls_back(self):
        before = self.files()
        with patch("xti.interfaces.platform_engine.make_engine_service", side_effect=AssertionError("scope bypass")):
            self.rejected("unknown", error="scope_unavailable")
            self.rejected("alpha", root=self.base / "missing", error="scope_unavailable")
            self.rejected("../beta", error="scope_unavailable")
        self.assertEqual(self.files(), before)
        marker = self.contexts["alpha"].data_dir / WORKSPACE_MARKER
        original = marker.read_bytes()
        marker.write_bytes((self.contexts["beta"].data_dir / WORKSPACE_MARKER).read_bytes())
        try:
            self.rejected("alpha", error="scope_unavailable")
        finally:
            marker.write_bytes(original)
        self.complete("alpha", action="disable")
        before = self.files()
        self.rejected("alpha", error="scope_unavailable")
        self.rejected("alpha", extra=("--describe",), error="scope_unavailable")
        self.assertEqual(self.files(), before)
        self.complete("beta")

    def test_same_durable_key_is_independent_between_companies_and_retry_returns_own_job(self):
        alpha, beta = self.submit("alpha"), self.submit("beta")
        self.assertEqual(alpha["idempotency_key"], beta["idempotency_key"])
        self.assertNotEqual(alpha["job_id"], beta["job_id"])
        self.assertEqual(alpha["profile"]["id"], self.profiles["alpha"].id)
        self.assertEqual(beta["profile"]["id"], self.profiles["beta"].id)
        self.assertEqual(self.submit("alpha")["job_id"], alpha["job_id"])
        self.assertEqual(self.submit("beta")["job_id"], beta["job_id"])
        self.assertEqual((alpha["status"], beta["status"]), ("queued", "queued"))

    def test_foreign_workspace_assertion_cannot_submit_or_change_selected_scope(self):
        before = self.files()
        response = self.rejected("alpha", self.request("jobs.submit", {
            "idempotency_key": "wrong-workspace", "profile_name": "Daily",
            "profile_revision": self.profiles["alpha"].revision,
            "expected_workspace_id": self.contexts["beta"].workspace_id}), error="scope_mismatch")
        self.assertEqual(response["scope"], self.contexts["alpha"].scope)
        self.assertEqual(self.files(), before)

    def test_foreign_job_status_result_cancel_and_worker_cannot_read_or_mutate(self):
        beta = self.submit("beta")
        before = self.files()
        for operation in ("jobs.status", "jobs.result", "jobs.cancel"):
            with self.subTest(operation=operation):
                self.rejected("alpha", self.request(operation, {"job_id": beta["job_id"]}), error="not_found")
        self.assertEqual(self.files(), before)
        self.rejected("alpha", action="worker", extra=("--job-id", beta["job_id"]), error="not_found")
        status = self.complete("beta", self.request("jobs.status", {"job_id": beta["job_id"]}))
        self.assertEqual(status["status"], "queued")
        self.assertIsNone(status["started_at"])

    def test_cancelling_own_job_does_not_change_other_company_same_key(self):
        alpha, beta = self.submit("alpha"), self.submit("beta")
        result = self.complete("alpha", self.request("jobs.cancel", {"job_id": alpha["job_id"]}))
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(self.complete("beta", self.request("jobs.status", {"job_id": beta["job_id"]}))["status"],
                         "queued")


if __name__ == "__main__":
    unittest.main()
