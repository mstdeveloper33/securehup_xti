#!/usr/bin/env python3
"""P11 two-company accumulated source acceptance; performs no network request."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import socket
import sqlite3
import sys
import tempfile
import time
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from xti.adapters.darkweb_monitoring_inputs import SQLiteDarkwebInputs
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_darkweb_monitoring import SQLiteDarkwebRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.application.darkweb_monitoring import DarkwebService
from xti.domain.darkweb_monitoring import PREFIX
from xti.domain.organizations import normalize_organization_target


AT = datetime(2026, 11, 24, 12, tzinfo=timezone.utc).isoformat()
RECORDS = 1_000


def require(value, message):
    if not value:
        raise AssertionError(message)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


class NoCredentialSource:
    def fetch(self, domain, api_key):
        raise AssertionError("P11 capacity acceptance cannot call a credential provider")


class NoSecrets:
    def api_key(self):
        raise AssertionError("P11 capacity acceptance cannot read an API key")

    def identity_key(self, organization_id):
        raise AssertionError("P11 capacity acceptance cannot read a pseudonym key")


def envelope(domain: str, changed: bool = False) -> dict:
    rows = []
    for index in range(RECORDS):
        evidence = f"{domain}:evidence:{index}:" + ("changed" if changed and index == 0 else "v1")
        rows.append({
            "object_reference_sha256": sha(f"{domain}:object:{index}"),
            "evidence_sha256": sha(evidence),
            "object_type": "item", "object_subtype": "paste",
            "network": "tor", "observed_at": AT,
            "match_kind": "domain", "match_value": domain,
            "claim_type": "data_leak",
        })
    return {
        "contract_version": 1, "source": "ail-framework", "ail_version": "7.1",
        "ail_commit": "4b94304bcd4d3d08b9e0c0772be4773e6bbbd350",
        "connector_version": "xti-ail-1", "records": rows,
    }


def pages(service: DarkwebService, operation: str, **parameters) -> tuple[int, int]:
    after, total, page_count = 0, 0, 0
    while True:
        result = service.execute(operation, after=after, limit=100, **parameters)
        total += len(result["items"])
        page_count += 1
        if result["next_after"] is None:
            require(total == result["total_count"], "P11 page count and total count differ")
            return total, page_count
        after = result["next_after"]


def run_company(base: Path, company: str) -> dict:
    database = base / company / "xti.db"
    assets = SQLiteAssetRepository(database)
    assets.initialize()
    domain = company + ".example"
    assets.add(domain)
    organizations = SQLiteOrganizationRepository(database)
    organization_name = company.replace("-", " ")
    organization = organizations.add(
        name_key=organization_name, display_name=organization_name.title(),
        reason="P11 capacity organization", recorded_at=AT,
    ).organization
    organizations.link(
        organization.id, normalize_organization_target("domain", domain),
        reason="P11 capacity exact domain", recorded_at=AT,
    )
    repository = SQLiteDarkwebRepository(database)
    service = DarkwebService(
        repository, SQLiteDarkwebInputs(database), NoCredentialSource(), NoSecrets(),
        now=lambda: AT,
    )
    profile = service.execute(
        PREFIX + "profile.add", name="P11 capacity", organization_id=organization.id,
        sources=["ail_tracker"], max_findings=RECORDS, interval_seconds=900,
        idempotency_key="profile",
    )

    durations = []
    receipts = []
    for label, batch in (("initial", envelope(domain)), ("unchanged", envelope(domain)),
                         ("changed", envelope(domain, changed=True))):
        preview = service.execute(PREFIX + "ail.preview", identifier=profile["id"], batch=batch)
        started = time.perf_counter()
        receipt = service.execute(
            PREFIX + "ail.import", identifier=profile["id"], expected_revision=1,
            expected_content_sha256=preview["content_sha256"], batch=batch,
            idempotency_key="import:" + label,
        )
        durations.append(time.perf_counter() - started)
        receipts.append(receipt)
    require(
        (receipts[0]["added_count"], receipts[1]["unchanged_count"],
         receipts[2]["updated_count"], receipts[2]["unchanged_count"])
        == (RECORDS, RECORDS, 1, RECORDS - 1),
        "P11 added/unchanged/changed counts are inconsistent",
    )
    replay = service.execute(
        PREFIX + "ail.import", identifier=profile["id"], expected_revision=1,
        expected_content_sha256=service.execute(
            PREFIX + "ail.preview", identifier=profile["id"], batch=envelope(domain, changed=True),
        )["content_sha256"], batch=envelope(domain, changed=True),
        idempotency_key="import:changed",
    )
    require(replay["replayed"] is True, "P11 idempotent replay did not reuse receipt")

    started = time.perf_counter()
    analysis = service.execute(
        PREFIX + "run", identifier=profile["id"], expected_revision=1, force=True,
        idempotency_key="analysis",
    )
    analysis_seconds = time.perf_counter() - started
    require(analysis["report"]["counts"]["underground_mention"] == RECORDS,
            "P11 analysis did not consume the complete source snapshot")
    source_total, source_pages = pages(
        service, PREFIX + "source.records", profile_id=profile["id"], provider="ail_tracker",
    )
    finding_total, finding_pages = pages(
        service, PREFIX + "findings", profile_id=profile["id"],
    )
    require((source_total, finding_total) == (RECORDS, RECORDS),
            "P11 accumulated records or findings were lost")
    with closing(sqlite3.connect(database)) as connection:
        counts = {
            table: connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
            for table in ("darkweb_source_runs", "darkweb_source_records",
                          "darkweb_source_changes", "darkweb_findings")
        }
    require(counts == {
        "darkweb_source_runs": 3, "darkweb_source_records": RECORDS,
        "darkweb_source_changes": RECORDS + 1, "darkweb_findings": RECORDS,
    }, "P11 persistent counts are inconsistent")
    return {
        "company": company, "records": RECORDS, "imports": 3,
        "first_added": RECORDS, "unchanged_second_import": RECORDS,
        "third_import_updated": 1, "idempotent_replay": True,
        "source_pages": source_pages, "finding_pages": finding_pages,
        "maximum_import_seconds": round(max(durations), 6),
        "analysis_seconds": round(analysis_seconds, 6),
        "database_bytes": database.stat().st_size,
    }


def peak_rss_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


def main() -> int:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="xti-p11-capacity-") as temporary, patch.object(
        socket.socket, "connect", side_effect=AssertionError(
            "P11 capacity acceptance cannot use network"
        ),
    ):
        results = [run_company(Path(temporary), company)
                   for company in ("company-alpha", "company-beta")]
        maximum_import = max(item["maximum_import_seconds"] for item in results)
        maximum_analysis = max(item["analysis_seconds"] for item in results)
        memory = peak_rss_mib()
        require(maximum_import < 15, "P11 import exceeded 15 seconds")
        require(maximum_analysis < 15, "P11 analysis exceeded 15 seconds")
        require(memory < 512, "P11 peak RSS exceeded 512 MiB")
        print(json.dumps({
            "ok": True, "policy": "p11-source-capacity-v1", "companies": results,
            "maximum_import_limit_seconds": 15,
            "maximum_analysis_limit_seconds": 15,
            "peak_rss_mib": round(memory, 2), "rss_limit_mib": 512,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "network_requests": 0,
        }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
