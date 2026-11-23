#!/usr/bin/env python3
"""P05 accumulated, isolated capacity acceptance; performs no network request."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
import math
from pathlib import Path
import resource
import sqlite3
import sys
import tempfile
import time
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from xti.adapters.company_workspaces import provision_company_workspace
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_darkweb_monitoring import SQLiteDarkwebRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.application.darkweb_monitoring import DarkwebService
from xti.domain.darkweb_monitoring import PREFIX, digest
from xti.domain.organizations import normalize_organization_target
from xti.interfaces.cli import main as cli_main
from xti.interfaces.platform_jobs import initialize_jobs


FINDINGS = 10_000
UNCHANGED_RUNS = 30
READS_PER_COMPANY = 20


def require(value, message):
    if not value:
        raise AssertionError(message)


class NoCredentialSource:
    def fetch(self, domain, api_key):
        raise AssertionError("P05 capacity acceptance cannot call a credential provider")


class NoSecrets:
    def api_key(self):
        raise AssertionError("P05 capacity acceptance cannot read an API key")

    def identity_key(self, organization_id):
        raise AssertionError("P05 capacity acceptance cannot read a pseudonym key")


class Inputs:
    def __init__(self, organization_id: str, label: str, domain: str):
        self.organization_id = organization_id
        self.label = label
        self.domain = domain
        observed = datetime(2026, 11, 21, tzinfo=timezone.utc).isoformat()
        self.records = []
        for index in range(FINDINGS):
            identifier = "capacity-" + str(index)
            state = {"id": identifier, "group": "synthetic-group-" + str(index)}
            self.records.append({
                "id": identifier,
                "title": label,
                "domain": None,
                "group": state["group"],
                "discovered_at": observed,
                "last_seen_at": None,
                "status": "source_claim",
                "state_sha256": digest(state),
            })

    def capture(self, plan: dict, at: str) -> dict:
        profile = plan["profile"]
        return {
            "policy": "darkweb-monitoring-v1",
            "captured_at": at,
            "profile_id": profile["id"],
            "profile_revision": profile["revision"],
            "definition": profile["definition"],
            "organization": {
                "id": self.organization_id,
                "display_name": self.label,
                "domains": [self.domain],
            },
            "targets": [{
                "kind": "organization",
                "id": self.organization_id,
                "label": self.label,
                "aliases": [],
                "domains": [self.domain],
                "criticality": "high",
            }],
            "sources": [{
                "key": "ransomlook",
                "name": "Synthetic RansomLook acceptance source",
                "url": "https://www.ransomlook.io/",
                "license": "Synthetic acceptance only",
                "run_id": str(uuid5(NAMESPACE_URL, "p05-capacity-source:" + self.label)),
                "fetched_at": "2026-11-21T00:00:00+00:00",
                "latest_status": "complete",
                "latest_attempt_at": "2026-11-21T00:00:00+00:00",
                "successful_snapshot_available": True,
                "records": self.records,
            }],
        }

    def change(self, record_id: str) -> None:
        index = int(record_id.removeprefix("capacity-"))
        original = self.records[index]
        state = {"id": record_id, "group": original["group"] + "-changed"}
        self.records[index] = {
            **original,
            "group": state["group"],
            "state_sha256": digest(state),
        }


def platform_read(root: Path, company: str, profile_id: str, after: int) -> tuple[float, list]:
    request = {
        "contract_version": 1,
        "request_id": f"p05-capacity-{company}-{after}",
        "operation": "darkweb.findings",
        "parameters": {"profile_id": profile_id, "after": after, "limit": 100},
    }
    output, errors = StringIO(), StringIO()
    started = time.perf_counter()
    with redirect_stdout(output), redirect_stderr(errors), patch(
            "sys.stdin", StringIO(json.dumps(request))):
        code = cli_main(["platform", "request", "--root", str(root), "--company", company])
    duration = time.perf_counter() - started
    require(code == 0 and not errors.getvalue(), "P05 platform read failed: " + errors.getvalue()[:500])
    return duration, json.loads(output.getvalue())["data"]["items"]


def run_company(root: Path, company: str) -> tuple[dict, Path]:
    context = provision_company_workspace(root, company)
    SQLiteAssetRepository(context.database).initialize()
    initialize_jobs(context)
    base = datetime(2026, 11, 21, tzinfo=timezone.utc)
    clock = [base]
    label = company.replace("-", " ").title()
    organizations = SQLiteOrganizationRepository(context.database)
    organization = organizations.add(
        name_key=company.replace("-", " "), display_name=label,
        reason="P05 capacity acceptance",
        recorded_at=base.isoformat(),
    ).organization
    domain = company + ".example"
    SQLiteAssetRepository(context.database).add(domain)
    organizations.link(
        organization.id, normalize_organization_target("domain", domain),
        reason="P05 explicit capacity domain", recorded_at=base.isoformat(),
    )
    inputs = Inputs(organization.id, label, domain)
    repository = SQLiteDarkwebRepository(context.database)
    service = DarkwebService(
        repository, inputs, NoCredentialSource(), NoSecrets(),
        now=lambda: clock[0].isoformat(),
    )
    profile = service.execute(
        PREFIX + "profile.add", name="P05 capacity", organization_id=organization.id,
        sources=["ransomlook"], max_findings=FINDINGS, interval_seconds=900,
        idempotency_key="profile",
    )

    run_times = []
    for cycle in range(UNCHANGED_RUNS + 1):
        clock[0] += timedelta(minutes=15)
        started = time.perf_counter()
        run = service.execute(
            PREFIX + "run", identifier=profile["id"], expected_revision=1,
            force=True, idempotency_key="run:" + str(cycle),
        )
        run_times.append(time.perf_counter() - started)
        require(run["status"] == "complete", "P05 capacity run did not complete")
        if cycle == 0:
            require(run["report"]["new_findings"] == FINDINGS, "P05 baseline finding count")
            require(run["report"]["silent_baseline"], "P05 baseline must be silent")
            reviewed = service.execute(PREFIX + "findings", profile_id=profile["id"], limit=1)["items"][0]
            service.execute(
                PREFIX + "review", identifier=reviewed["id"], evidence_id=reviewed["evidence_id"],
                expected_revision=0, expected_observation_revision=1, decision="uncertain",
                reason="Synthetic P05 capacity review", idempotency_key="review",
            )
        else:
            require(run["report"]["new_evidence"] == 0, "Unchanged P05 run duplicated evidence")
            require(run["report"]["changed_findings"] == 0, "Unchanged P05 run changed findings")
            require(run["report"]["notifications"] == 0, "Unchanged P05 run notified")
            require(run["report"]["unchanged_findings"] == FINDINGS, "Unchanged P05 count")

    reviewed_now = service.execute(PREFIX + "finding.show", identifier=reviewed["id"])
    require(not reviewed_now["needs_review"], "Unchanged P05 evidence lost the human decision")
    inputs.change(reviewed_now["evidence"]["body"]["source"]["record_id"])
    clock[0] += timedelta(minutes=15)
    changed = service.execute(
        PREFIX + "run", identifier=profile["id"], expected_revision=1,
        force=True, idempotency_key="changed",
    )
    require(changed["report"]["new_evidence"] == 1, "P05 change did not create one evidence record")
    require(changed["report"]["changed_findings"] == 1, "P05 change did not update one finding")
    require(changed["report"]["notifications"] == 1, "P05 change did not create one notification")
    require(service.execute(PREFIX + "finding.show", identifier=reviewed["id"])["needs_review"],
            "Changed P05 evidence did not reopen review")

    samples = []
    for page in range(READS_PER_COMPANY):
        duration, items = platform_read(root, company, profile["id"], page * 100)
        samples.append(duration)
        require(len(items) == 100, "P05 platform page is incomplete")
        require(all(item["evidence"]["body"]["target"]["label"] == label for item in items),
                "P05 company isolation failed")
    with closing(sqlite3.connect(context.database)) as connection:
        counts = {
            table: connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
            for table in (
                "darkweb_findings", "darkweb_evidence", "darkweb_runs",
                "darkweb_changes", "darkweb_notifications",
            )
        }
    require(counts == {
        "darkweb_findings": FINDINGS,
        "darkweb_evidence": FINDINGS + 1,
        "darkweb_runs": UNCHANGED_RUNS + 2,
        "darkweb_changes": 1,
        "darkweb_notifications": 1,
    }, "P05 accumulated counts are inconsistent")
    return ({
        "company": company,
        "findings": FINDINGS,
        "total_runs": UNCHANGED_RUNS + 2,
        "unchanged_runs": UNCHANGED_RUNS,
        "unchanged_new_evidence": 0,
        "unchanged_changes": 0,
        "unchanged_notifications": 0,
        "changed_new_evidence": 1,
        "changed_findings": 1,
        "changed_notifications": 1,
        "human_review_preserved_then_reopened": True,
        "platform_reads": READS_PER_COMPANY,
        "read_seconds": {
            "p95": sorted(samples)[math.ceil(0.95 * len(samples)) - 1],
            "maximum": max(samples),
        },
        "run_seconds": {"maximum": max(run_times)},
        "database_bytes": context.database.stat().st_size,
    }, context.database)


def peak_rss_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


def main() -> int:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="xti-p05-capacity-") as temporary, patch(
            "socket.socket.connect", side_effect=AssertionError("P05 capacity acceptance cannot use network")):
        root = (Path(temporary) / "platform").resolve()
        results = [run_company(root, company)[0] for company in ("company-alpha", "company-beta")]
        maximum_p95 = max(item["read_seconds"]["p95"] for item in results)
        memory = peak_rss_mib()
        require(maximum_p95 < 2, f"P05 read p95 exceeded 2 seconds: {maximum_p95:.6f}")
        require(memory < 256, f"P05 peak RSS exceeded 256 MiB: {memory:.2f}")
        print(json.dumps({
            "ok": True,
            "policy": "p05-capacity-v1",
            "companies": results,
            "peak_rss_mib": round(memory, 2),
            "read_p95_limit_seconds": 2,
            "rss_limit_mib": 256,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "network_requests": 0,
        }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
