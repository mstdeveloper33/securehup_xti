"""P05 source claims, credential privacy, persistence and durable work tests."""

from contextlib import closing, redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO, StringIO
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from xti.adapters.darkweb_monitoring_schema import (
    DEFINITIONS as DARKWEB_DEFINITIONS,
    PREVIOUS_CASE_DDL,
    V93_DDL,
)
from xti.adapters.xposedornot_credentials import XposedOrNotCredentialStore
from xti.adapters.xposedornot_domain_exposure import (
    BASE as XON_DOMAIN_BASE,
    XposedOrNotDomainError,
    XposedOrNotDomainExposureSource,
)
from xti.adapters.xposedornot_passwords import (
    BASE as XON_PASSWORD_BASE,
    XposedOrNotPasswordSource,
    keccak_512,
    password_prefix,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.adapters.sqlite_darkweb_monitoring import (
    SQLiteDarkwebRepository,
    case_snapshot,
    company_in,
)
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.application.darkweb_monitoring import DarkwebService
from xti.application.inbox import InboxService
from xti.application.cases import CaseEvidenceResolverService, CaseService
from xti.domain.assets import ValidationError
from xti.domain.darkweb_monitoring import (
    DarkwebError,
    PREFIX,
    analyse,
    digest,
    profile_definition,
    sanitize_credential_accounts,
)
from xti.domain.organizations import normalize_organization_target
from xti.interfaces.platform_jobs import initialize_jobs, make_job_service
from xti.interfaces.source_jobs import make_source_job_service
from xti.interfaces.cli import main


AT = datetime(2026, 11, 21, 12, tzinfo=timezone.utc).isoformat()


class FrozenInputs:
    def __init__(self):
        self.group = "group-one"

    def capture(self, plan, at):
        profile = plan["profile"]
        record = {
            "id": "ransomlook-post-one",
            "title": "Example Corp",
            "domain": None,
            "group": self.group,
            "discovered_at": "2026-11-20T12:00:00+00:00",
            "last_seen_at": None,
            "status": "source_claim",
            "state_sha256": digest({"group": self.group}),
        }
        sources = []
        if "ransomlook" in profile["definition"]["sources"]:
            sources.append({
                "key": "ransomlook",
                "name": "RansomLook",
                "url": "https://www.ransomlook.io/",
                "license": "Source terms apply",
                "run_id": "10000000-0000-4000-8000-000000000001",
                "fetched_at": "2026-11-20T12:00:00+00:00",
                "latest_status": "complete",
                "latest_attempt_at": "2026-11-20T12:00:00+00:00",
                "successful_snapshot_available": True,
                "records": [record],
            })
        if "xposedornot_domain" in profile["definition"]["sources"]:
            sources.append({
                "key": "xposedornot_domain", "name": "XposedOrNot verified domain",
                "url": XON_DOMAIN_BASE,
                "license": "XposedOrNot terms apply", "run_id": None, "fetched_at": None,
                "latest_status": "not_checked", "latest_attempt_at": None,
                "successful_snapshot_available": False, "records": [],
            })
        return {
            "policy": "darkweb-monitoring-v1",
            "captured_at": at,
            "profile_id": profile["id"],
            "profile_revision": profile["revision"],
            "definition": deepcopy(profile["definition"]),
            "organization": {
                "id": profile["organization_id"],
                "display_name": "Example Corp",
                "domains": ["example.com"],
            },
            "targets": [{
                "kind": "organization",
                "id": profile["organization_id"],
                "label": "Example Corp",
                "aliases": [],
                "domains": ["example.com"],
                "criticality": "high",
            }],
            "sources": sorted(sources, key=lambda item: item["key"]),
        }


class CredentialSource:
    def __init__(self):
        self.calls = 0
        self.accounts = {"alice.private": ["ExampleBreach"]}
        self.error = None

    def fetch(self, domain, api_key):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return {
            "provider": "xposedornot_domain",
            "domain": domain,
            "source_url": XON_DOMAIN_BASE,
            "fetched_at": AT,
            "content_sha256": digest(self.accounts),
            "accounts": deepcopy(self.accounts),
        }


class Secrets:
    api_key_value = "a" * 32
    identity_key_value = b"i" * 32

    def api_key(self):
        return self.api_key_value

    def identity_key(self, organization_id):
        return self.identity_key_value


class Response(BytesIO):
    def __init__(self, body, *, code=200, url=None, headers=None):
        super().__init__(body)
        self.code = code
        self.url = url or XON_DOMAIN_BASE
        self.headers = headers or {
            "Content-Type": "application/json", "Content-Length": str(len(body)),
        }

    def getcode(self):
        return self.code

    def geturl(self):
        return self.url


class DarkwebRuleTests(unittest.TestCase):
    def test_legacy_hibp_sources_cannot_be_added_to_new_profiles(self):
        for source in ("hibp_public", "hibp_domain"):
            with self.subTest(source=source), self.assertRaisesRegex(
                ValidationError, "yeni profillerde devre dışıdır",
            ):
                profile_definition({
                    "name": "Legacy source must be rejected",
                    "organization_id": "30000000-0000-4000-8000-000000000001",
                    "sources": [source],
                })

    def test_exact_matching_is_candidate_only_and_near_name_is_not_matched(self):
        inputs = FrozenInputs()
        profile = {"id": "20000000-0000-4000-8000-000000000001", "revision": 1,
                   "organization_id": "30000000-0000-4000-8000-000000000001",
                   "definition": profile_definition({
                       "name": "Dark web", "organization_id": "30000000-0000-4000-8000-000000000001",
                       "sources": ["ransomlook"],
                   })}
        snapshot = inputs.capture({"profile": profile}, AT)
        result = analyse(snapshot)
        self.assertEqual(result["counts"]["ransomware_claim"], 1)
        candidate = result["candidates"][0]["body"]
        self.assertFalse(candidate["automatic_verdict"])
        self.assertIn("doğrulanmış ihlal", candidate["limitations"][0])
        snapshot["sources"][0]["records"][0]["title"] = "Example Corp Support"
        self.assertEqual(analyse(snapshot)["candidates"], [])

    def test_commercial_threatcluster_requires_written_provider_decision(self):
        with self.assertRaisesRegex(ValidationError, "yazılı sağlayıcı"):
            profile_definition({
                "name": "Commercial", "organization_id": "30000000-0000-4000-8000-000000000001",
                "sources": ["threatcluster"], "usage_mode": "commercial",
            })

    def test_credential_aliases_are_masked_and_pseudonymized_deterministically(self):
        records = sanitize_credential_accounts(
            {"alice.private": ["BreachB", "BreachA"]}, "example.com", b"s" * 32,
        )
        self.assertEqual(len(records), 1)
        encoded = json.dumps(records)
        self.assertNotIn("alice.private", encoded)
        self.assertEqual(records[0]["masked_account"], "a******e@example.com")
        self.assertEqual(records[0]["breaches"], ["BreachA", "BreachB"])
        self.assertEqual(
            records,
            sanitize_credential_accounts(
                {"alice.private": ["BreachB", "BreachA"]}, "example.com", b"s" * 32,
            ),
        )


class XposedOrNotCredentialBoundaryTests(unittest.TestCase):
    def test_bounded_https_source_uses_explicit_auth_and_exact_domain_filter(self):
        body = json.dumps({
            "status": "success",
            "metrics": {
                "Domain_Summary": {"example.com": 1, "other.example": 1},
                "Breaches_Details": [
                    {"email": "alice.private@example.com", "domain": "example.com",
                     "breach": "ExampleBreach"},
                    {"email": "unrelated-provider-shape", "domain": "other.example",
                     "breach": {"private": "must not cross scope"}},
                ],
            },
        }).encode()
        opener = Mock()
        opener.open.return_value = Response(body)
        source = XposedOrNotDomainExposureSource(
            opener=opener, now=lambda: datetime(2026, 11, 21, 12, tzinfo=timezone.utc),
            monotonic=Mock(return_value=0),
        )
        result = source.fetch("example.com", "x" * 32)
        self.assertEqual(result["accounts"], {"alice.private": ["ExampleBreach"]})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, XON_DOMAIN_BASE)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.headers["X-api-key"], "x" * 32)
        self.assertNotIn("alice.private", request.full_url)
        alternate = json.loads(body)
        alternate["metrics"]["Breaches_Details"][1]["email"] = "different@other.example"
        second = Mock()
        second.open.return_value = Response(json.dumps(alternate).encode())
        second_result = XposedOrNotDomainExposureSource(
            opener=second, now=lambda: datetime(2026, 11, 21, 12, tzinfo=timezone.utc),
            monotonic=Mock(return_value=0),
        ).fetch("example.com", "x" * 32)
        self.assertEqual(result["content_sha256"], second_result["content_sha256"])

    def test_malformed_cross_domain_or_unverified_results_fail_closed(self):
        invalid = Mock()
        invalid.open.return_value = Response(b'{"a":["one"],"a":["two"]}')
        with self.assertRaises(XposedOrNotDomainError) as malformed:
            XposedOrNotDomainExposureSource(opener=invalid).fetch("example.com", "x" * 32)
        self.assertEqual(malformed.exception.code, "source_invalid")
        mismatch = Mock()
        mismatch.open.return_value = Response(json.dumps({
            "status": "success", "metrics": {
                "Domain_Summary": {"example.com": 1},
                "Breaches_Details": [{
                    "email": "a@evil.example", "domain": "example.com", "breach": "Mismatch",
                }],
            },
        }).encode())
        with self.assertRaises(XposedOrNotDomainError) as crossed:
            XposedOrNotDomainExposureSource(opener=mismatch).fetch("example.com", "x" * 32)
        self.assertEqual(crossed.exception.code, "source_invalid")
        forbidden = Mock()
        forbidden.open.side_effect = HTTPError(
            XON_DOMAIN_BASE, 401, "private upstream detail", {}, None,
        )
        with self.assertRaises(XposedOrNotDomainError) as unverified:
            XposedOrNotDomainExposureSource(opener=forbidden).fetch("example.com", "x" * 32)
        self.assertEqual(unverified.exception.code, "missing_or_invalid_key")
        self.assertNotIn("private upstream detail", str(unverified.exception))

    def test_secret_store_is_owner_only_non_overwriting_and_never_returns_values_in_status(self):
        organization_id = "30000000-0000-4000-8000-000000000001"
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "secure-config"
            store = XposedOrNotCredentialStore(directory)
            key_path = store.save_api_key("XON-test-key-123456789")
            identity_path = store.create_identity_key(organization_id)
            self.assertEqual(key_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(identity_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
            self.assertEqual(store.readiness(organization_id), {
                "api_key": "configured", "identity_key": "configured", "ready": True,
            })
            with self.assertRaisesRegex(ValidationError, "üzerine yazılmadı"):
                store.save_api_key("XON-second-key-123456")
            self.assertEqual(store.api_key(), "XON-test-key-123456789")

    def test_secret_store_rejects_symlink_and_open_permissions_with_safe_guidance(self):
        organization_id = "30000000-0000-4000-8000-000000000001"
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "secure-config"
            directory.mkdir(mode=0o700)
            target = Path(temporary) / "outside.key"
            target.write_text("x" * 32 + "\n")
            target.chmod(0o600)
            (directory / "xposedornot.key").symlink_to(target)
            store = XposedOrNotCredentialStore(directory)
            with self.assertRaisesRegex(ValidationError, "güvenle okunamadı"):
                store.api_key()
            with self.assertRaisesRegex(ValidationError, "xposedornot-identity-create"):
                store.identity_key(organization_id)
            (directory / "xposedornot.key").unlink()
            (directory / "xposedornot.key").write_text("x" * 32 + "\n")
            (directory / "xposedornot.key").chmod(0o644)
            with self.assertRaisesRegex(ValidationError, "yalnız sahibine açık"):
                store.api_key()


class XposedOrNotPasswordBoundaryTests(unittest.TestCase):
    def test_official_keccak_vectors_and_prefix_are_exact(self):
        self.assertEqual(
            keccak_512(b"test").hex(),
            "1e2e9fc2002b002d75198b7503210c05a1baac4560916a3c6d93bcce3a50d7f"
            "00fd395bf1647b9abb8d1afcc9c76c289b0c9383ba386a956da4b38934417789e",
        )
        self.assertEqual(
            keccak_512(b"pass").hex(),
            "adf34f3e63a8e0bd2938f3e09ddc161125a031c3c86d06ec59574a5c723e7fd"
            "be04c2c15d9171e05e90a9c822936185f12b9d7384b2bedb02e75c4c5fe89e4d4",
        )
        self.assertEqual(password_prefix("test"), "1e2e9fc200")

    def test_only_prefix_is_requested_and_secret_metadata_is_discarded(self):
        body = json.dumps({"SearchPassAnon": {
            "anon": "1e2e9fc200", "char": "D:0;A:4;S:0;L:4",
            "count": "42", "wordlist": 1,
        }}).encode()
        opener = Mock()
        opener.open.return_value = Response(body, url=XON_PASSWORD_BASE + "1e2e9fc200")
        source = XposedOrNotPasswordSource(
            opener=opener, now=lambda: datetime(2026, 11, 21, 12, tzinfo=timezone.utc),
            monotonic=Mock(return_value=0),
        )
        result = source.check_password("test")
        self.assertEqual((result["exposed"], result["exposure_count"]), (True, 42))
        self.assertEqual(opener.open.call_args.args[0].full_url,
                         XON_PASSWORD_BASE + "1e2e9fc200")
        encoded = json.dumps(result)
        self.assertNotIn("test", encoded)
        self.assertNotIn("1e2e9fc200", encoded)
        self.assertNotIn("D:0", encoded)
        self.assertFalse(result["stored"])

    def test_not_found_is_not_reported_as_safe(self):
        opener = Mock()
        opener.open.side_effect = HTTPError(
            XON_PASSWORD_BASE + "1e2e9fc200", 404, "not found", {}, None,
        )
        result = XposedOrNotPasswordSource(
            opener=opener, now=lambda: datetime(2026, 11, 21, 12, tzinfo=timezone.utc),
        ).check_password("test")
        self.assertFalse(result["exposed"])
        self.assertIn("kanıtlamaz", result["limitations"][1])


class DarkwebStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.storage.add("example.com")
        organizations = SQLiteOrganizationRepository(self.path)
        self.organization = organizations.add(
            name_key="example corp", display_name="Example Corp",
            reason="Explicit P05 scope", recorded_at=AT,
        ).organization
        organizations.link(
            self.organization.id, normalize_organization_target("domain", "example.com"),
            reason="Explicit P05 domain", recorded_at=AT,
        )
        self.inputs = FrozenInputs()
        self.credential_source = CredentialSource()
        self.service = DarkwebService(
            SQLiteDarkwebRepository(self.path), self.inputs,
            self.credential_source, Secrets(), now=lambda: AT,
        )

    def profile(self, *, credential=False):
        return self.service.execute(
            PREFIX + "profile.add", name="Example dark web",
            organization_id=self.organization.id,
            sources=["ransomlook", "xposedornot_domain"] if credential else ["ransomlook"],
            interval_seconds=900, idempotency_key="profile-credential" if credential else "profile",
        )

    def run_profile(self, profile, key, *, force=True):
        return self.service.execute(
            PREFIX + "run", identifier=profile["id"],
            expected_revision=profile["revision"], force=force, idempotency_key=key,
        )

    def test_baseline_change_review_company_case_and_notification_are_consistent(self):
        profile = self.profile()
        baseline = self.run_profile(profile, "baseline")
        self.assertTrue(baseline["report"]["silent_baseline"])
        self.assertEqual(baseline["report"]["notifications"], 0)
        finding = self.service.execute(PREFIX + "findings", profile_id=profile["id"])["items"][0]
        self.inputs.group = "group-two"
        changed = self.run_profile(profile, "changed")
        self.assertFalse(changed["report"]["silent_baseline"])
        self.assertEqual(changed["report"]["notifications"], 1)
        inbox = InboxService(
            SQLiteInboxRepository(self.path),
            clock=lambda: datetime(2026, 11, 21, 12, tzinfo=timezone.utc),
        )
        page = inbox.list()
        notice = page.items[0]
        self.assertIsNotNone(notice.darkweb_change)
        details = inbox.show(notice.notification.id)
        self.assertEqual(details.darkweb_change["change"]["kind"], "changed")
        inbox.mark([notice.notification.id], read=True)
        current = self.service.execute(PREFIX + "finding.show", identifier=finding["id"])
        review = self.service.execute(
            PREFIX + "review", identifier=current["id"], evidence_id=current["evidence_id"],
            expected_revision=0, expected_observation_revision=2,
            decision="uncertain", reason="Kaynak iddiası insan incelemesi bekliyor.",
            idempotency_key="review",
        )
        self.assertEqual(review["decision"], "uncertain")
        with self.storage._connection(readonly=True) as connection:
            company = company_in(connection, self.organization.id)
            frozen = case_snapshot(connection, current["id"])
        self.assertEqual(company["state"], "recorded")
        self.assertEqual(company["items"][0]["review"]["decision"], "uncertain")
        self.assertEqual(frozen.evidence_type, "darkweb_monitoring")
        cases = CaseService(
            SQLiteCaseRepository(self.path),
            CaseEvidenceResolverService(SQLiteCaseEvidenceSourceRepository(self.path)),
            clock=lambda: datetime(2026, 11, 21, 12, tzinfo=timezone.utc),
        )
        case = cases.create(
            "Dark web claim review", summary="Source claim requires analyst review.",
            priority="high", reason="P05 candidate triage.",
        ).case
        linked = cases.add_evidence(
            case.id, "darkweb_monitoring", current["id"],
            reason="Freeze exact source-qualified claim evidence.",
        )
        self.assertEqual(linked.evidence.evidence_type, "darkweb_monitoring")
        self.assertIn('"automatic_verdict":false', linked.evidence.snapshot_json)

    def test_credential_refresh_never_persists_raw_alias_or_secret_and_replay_is_free(self):
        profile = self.profile(credential=True)
        run = self.service.execute(
            PREFIX + "credential.refresh", identifier=profile["id"],
            domain="example.com", idempotency_key="credential-one",
        )
        self.assertEqual((run["status"], run["account_count"], self.credential_source.calls),
                         ("complete", 1, 1))
        replay = self.service.execute(
            PREFIX + "credential.refresh", identifier=profile["id"],
            domain="example.com", idempotency_key="credential-one",
        )
        self.assertTrue(replay["replayed"])
        self.assertEqual(self.credential_source.calls, 1)
        database = self.path.read_bytes()
        self.assertNotIn(b"alice.private", database)
        self.assertNotIn(("a" * 32).encode(), database)
        self.assertIn(b"a******e@example.com", database)

    def test_password_cli_uses_hidden_input_and_persists_nothing(self):
        before = self.path.read_bytes()
        result = {
            "provider": "xposedornot_passwords", "checked_at": AT,
            "exposed": True, "exposure_count": 7, "wordlist": False,
            "stored": False, "plaintext_transmitted": False,
            "full_hash_transmitted": False, "prefix_characters_transmitted": 10,
            "limitations": ["prefix disclosure", "Bulunmaması güvenliği kanıtlamaz."],
        }
        output, error = StringIO(), StringIO()
        with patch("getpass.getpass", return_value="private-cli-password"), patch(
            "xti.adapters.xposedornot_passwords.XposedOrNotPasswordSource.check_password",
            return_value=result,
        ) as checked, redirect_stdout(output), redirect_stderr(error):
            code = main([
                "--data-dir", str(self.root), "--json", "darkweb", "password-check",
            ])
        self.assertEqual((code, error.getvalue()), (0, ""))
        checked.assert_called_once_with("private-cli-password")
        rendered = output.getvalue()
        self.assertNotIn("private-cli-password", rendered)
        self.assertEqual(json.loads(rendered)["data"]["exposure_count"], 7)
        self.assertEqual(self.path.read_bytes(), before)

    def test_source_failure_is_safe_recoverable_and_does_not_replace_prior_snapshot(self):
        profile = self.profile(credential=True)
        complete = self.service.execute(
            PREFIX + "credential.refresh", identifier=profile["id"],
            domain="example.com", idempotency_key="success",
        )
        self.credential_source.error = XposedOrNotDomainError(
            "domain_not_verified", "Domain doğrulanmadı; private-provider-detail gösterilmez.",
        )
        with self.assertRaises(DarkwebError) as caught:
            self.service.execute(
                PREFIX + "credential.refresh", identifier=profile["id"],
                domain="example.com", idempotency_key="failed",
            )
        self.assertEqual(caught.exception.code, "domain_not_verified")
        runs = self.service.execute(PREFIX + "credential.runs", profile_id=profile["id"])["items"]
        self.assertEqual([row["status"] for row in runs], ["complete", "failed"])
        self.assertEqual(runs[0]["id"], complete["id"])
        self.assertNotIn(b"private-provider-detail", self.path.read_bytes())

    def test_explicit_recovery_closes_interrupted_analysis_without_losing_prior_evidence(self):
        profile = self.profile()
        complete = self.run_profile(profile, "complete")
        plan = self.service.repository.plan(profile["id"])
        snapshot = self.inputs.capture(plan, AT)
        running, replayed = self.service.repository.reserve({
            "identifier": profile["id"], "expected_revision": profile["revision"],
            "force": True, "idempotency_key": "interrupted",
        }, snapshot, AT)
        self.assertFalse(replayed)
        recovered = self.service.execute(
            PREFIX + "recover", identifier=running["id"], idempotency_key="recover",
        )
        self.assertEqual(recovered["status"], "interrupted")
        self.assertTrue(recovered["report"]["old_evidence_preserved"])
        findings = self.service.execute(PREFIX + "findings", profile_id=profile["id"])
        self.assertEqual(findings["total_count"], 1)
        self.assertEqual(findings["items"][0]["last_run_id"], complete["id"])

    def test_credential_chain_detects_run_and_change_tampering(self):
        profile = self.profile(credential=True)
        run = self.service.execute(
            PREFIX + "credential.refresh", identifier=profile["id"],
            domain="example.com", idempotency_key="chain",
        )
        with self.storage._connection() as connection, connection:
            connection.execute(
                "UPDATE darkweb_credential_runs SET account_count=2 WHERE id=?", (run["id"],),
            )
        with self.assertRaisesRegex(StorageError, "bütünlük zinciri"):
            self.service.execute(PREFIX + "credential.run.show", identifier=run["id"])

    def test_durable_source_job_freezes_scope_and_uses_zero_http_requests(self):
        profile = self.profile()
        context = SimpleNamespace(data_dir=self.root, database=self.path)
        initialize_jobs(context)
        plan = self.service.execute(PREFIX + "plan", identifier=profile["id"])
        source = make_source_job_service(context)
        options = {
            "indicator_type": "sha256", "value": plan["queue_scope_sha256"],
            "sources": ["darkweb-monitor"], "darkweb_profile_id": profile["id"],
            "darkweb_profile_revision": profile["revision"], "darkweb_force": True,
        }
        admission = source.plan(**options)
        self.assertEqual(admission["maximum_external_requests"], 0)
        self.assertFalse(admission["disclosure"][0]["target_sent"])
        job = source.submit(
            **admission["plan"], plan_sha256=admission["plan_sha256"],
            idempotency_key="darkweb-job",
        )
        done = make_job_service(context).work_one(job.id)
        self.assertEqual(done.status, "complete")
        self.assertEqual(done.to_dict()["execution"]["requests"]["attempts"], 0)
        receipt = done.steps[0]["receipt"]
        self.assertEqual(receipt["kind"], "darkweb_monitor_run")
        stored = self.service.execute(PREFIX + "run.show", identifier=receipt["run_id"])
        self.assertEqual(stored["status"], "complete")

    def test_engine_read_contract_is_local_bounded_and_read_only(self):
        profile = self.profile()
        self.run_profile(profile, "engine-visible")
        from xti.domain.engine import parse_engine_request
        from xti.interfaces.engine import make_engine_service
        before = self.path.read_bytes()
        request = parse_engine_request({
            "contract_version": 1, "request_id": "p05-engine",
            "operation": "darkweb.findings",
            "parameters": {"profile_id": profile["id"], "limit": 10},
        })
        with patch("socket.socket.connect", side_effect=AssertionError("Engine read is offline")):
            result = make_engine_service(
                self.path, operation=request.operation,
            ).execute(request)
        self.assertEqual(result["total_count"], 1)
        self.assertEqual(result["items"][0]["kind"], "ransomware_claim")
        self.assertEqual(self.path.read_bytes(), before)


class DarkwebMigrationTests(unittest.TestCase):
    def test_schema92_to_94_is_atomic_and_recoverable(self):
        from xti.adapters.darkweb_monitoring_schema import create
        from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_INDEX_DDL
        from xti.adapters.schema import SCHEMA_VERSION, validate_schema
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "data" / "xti.db"
            storage = SQLiteAssetRepository(path)
            storage.initialize()
            with closing(sqlite3.connect(path)) as connection, connection:
                from tests.case_evidence_v94_fixture import case_evidence_layout_v94
                case_evidence_layout_v94(connection)
                connection.execute("DROP INDEX case_evidence_case_active_updated")
                connection.execute("DROP TABLE case_evidence")
                connection.execute(PREVIOUS_CASE_DDL)
                connection.execute(CASE_EVIDENCE_INDEX_DDL)
                for table in reversed(tuple(DARKWEB_DEFINITIONS)):
                    connection.execute("DROP TABLE " + table)
                connection.execute("PRAGMA user_version=92")
                self.assertEqual(validate_schema(connection, allow_legacy=True), 92)
            before = path.read_bytes()

            def interrupted(connection):
                create(connection)
                raise KeyboardInterrupt("controlled P05 schema94 migration interruption")

            with patch("xti.adapters.sqlite.create_darkweb_monitoring_schema", side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    storage.migrate()
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(list((path.parent / "backups").glob("*.db"))), 1)
            self.assertEqual(storage.migrate()["to_version"], SCHEMA_VERSION)
            with storage._connection(readonly=True) as connection:
                self.assertEqual(validate_schema(connection), SCHEMA_VERSION)

    def test_schema93_to_94_preserves_legacy_provider_and_is_atomic(self):
        from xti.adapters.darkweb_monitoring_schema import migrate_xposedornot
        from xti.adapters.schema import SCHEMA_VERSION, validate_schema
        from xti.domain.content_monitoring import canonical
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "data" / "xti.db"
            storage = SQLiteAssetRepository(path)
            storage.initialize()
            organization = SQLiteOrganizationRepository(path).add(
                name_key="legacy", display_name="Legacy",
                reason="schema93 fixture", recorded_at=AT,
            ).organization
            profile_id = "40000000-0000-4000-8000-000000000001"
            run_id = "50000000-0000-4000-8000-000000000001"
            definition = profile_definition({
                "name": "Legacy profile", "organization_id": organization.id,
                "sources": ["hibp_domain"], "interval_seconds": 900,
            }, allow_legacy=True)
            with closing(sqlite3.connect(path)) as connection, connection:
                from tests.case_evidence_v94_fixture import case_evidence_layout_v94
                case_evidence_layout_v94(connection)
                for table in DARKWEB_DEFINITIONS:
                    columns = ["sequence", *(name for name, _ in DARKWEB_DEFINITIONS[table])]
                    names = ",".join(columns)
                    connection.execute(
                        f"CREATE TEMP TABLE old_{table} AS SELECT {names} FROM {table} ORDER BY sequence"
                    )
                for table in reversed(tuple(DARKWEB_DEFINITIONS)):
                    connection.execute("DROP TABLE " + table)
                for statement in V93_DDL:
                    connection.execute(statement)
                for table in DARKWEB_DEFINITIONS:
                    columns = ["sequence", *(name for name, _ in DARKWEB_DEFINITIONS[table])]
                    names = ",".join(columns)
                    connection.execute(
                        f"INSERT INTO {table} ({names}) SELECT {names} FROM old_{table} "
                        "ORDER BY sequence"
                    )
                encoded = canonical(definition)
                connection.execute(
                    "INSERT INTO darkweb_profiles "
                    "(id,organization_id,name_key,revision,enabled,definition_json,definition_sha256,"
                    "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (profile_id, organization.id, "legacy profile", 1, 1, encoded,
                     digest(definition), AT, AT),
                )
                request = digest({"legacy": True})
                connection.execute(
                    "INSERT INTO darkweb_credential_runs "
                    "(id,profile_id,organization_id,domain,provider,request_key,request_sha256,"
                    "source_url,status,account_count,added_count,updated_count,unchanged_count,"
                    "removed_count,started_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (run_id, profile_id, organization.id, "example.com", "hibp_domain",
                     "legacy-request", request,
                     "https://haveibeenpwned.com/api/v3/breachedDomain/{verified-domain}",
                     "running", 0, 0, 0, 0, 0, AT),
                )
                connection.execute(
                    "UPDATE sqlite_sequence SET seq=41 WHERE name='darkweb_credential_runs'"
                )
                connection.execute("PRAGMA user_version=93")
                self.assertEqual(validate_schema(connection, allow_legacy=True), 93)
            before = path.read_bytes()

            def interrupted(connection):
                migrate_xposedornot(connection)
                raise KeyboardInterrupt("controlled schema93 to schema94 interruption")

            with patch(
                "xti.adapters.sqlite.migrate_darkweb_xposedornot_schema",
                side_effect=interrupted,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    storage.migrate()
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(storage.migrate()["to_version"], SCHEMA_VERSION)
            with storage._connection(readonly=True) as connection:
                self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
                row = connection.execute(
                    "SELECT sequence,provider,status FROM darkweb_credential_runs WHERE id=?",
                    (run_id,),
                ).fetchone()
                self.assertEqual(row, (1, "hibp_domain", "running"))
                self.assertEqual(connection.execute(
                    "SELECT seq FROM sqlite_sequence WHERE name='darkweb_credential_runs'"
                ).fetchone()[0], 41)
            repository = SQLiteDarkwebRepository(path)
            legacy = repository.read(PREFIX + "profile.show", {"identifier": profile_id})
            self.assertEqual(legacy["binding_state"], "source_retired")
            with self.assertRaisesRegex(DarkwebError, "devre dışı bırakılmış HIBP"):
                repository.plan(profile_id)


if __name__ == "__main__":
    unittest.main()
