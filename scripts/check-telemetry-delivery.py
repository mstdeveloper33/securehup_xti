#!/usr/bin/env python3
"""P12 two-company accumulated telemetry acceptance; never uses the network."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import resource
import socket
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_telemetry import SQLiteTelemetryRepository
from xti.application.telemetry import TelemetryService
from xti.domain.telemetry import PREFIX, preview_from_records


RECORDS = 5_000
PAGE_SIZE = 500


def require(value, message):
    if not value:
        raise AssertionError(message)


def peak_rss_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


class Clock:
    def __init__(self):
        self.value = datetime(2026, 11, 23, 8, tzinfo=timezone.utc)

    def __call__(self):
        return self.value.isoformat()

    def advance(self):
        self.value += timedelta(minutes=5)


def record(company: str, index: int, *, changed: bool = False) -> dict:
    domain = f"sensor-{index:05d}.{company}.example"
    return {
        "native_id": f"{company}:dns:{index:05d}",
        "kind": "dns_query", "event_at": "2026-11-23T07:59:00+00:00",
        "summary": ("Updated " if changed else "") + f"authorized sinkhole observation {domain}",
        "outcome": "observed", "src_ip": "192.0.2.25", "dst_ip": "192.0.2.53",
        "src_port": 5353, "dst_port": 53, "protocol": "udp",
        "domain": domain, "url": None, "hashes": {},
        "indicators": [{"type": "domain", "value": domain}],
        "attributes": [{"name": "query_type", "value": "A"}],
        "tags": ["p12-capacity"],
    }


def run_company(root: Path, company: str) -> dict:
    database = root / company / "xti.db"
    storage = SQLiteAssetRepository(database)
    storage.initialize()
    clock = Clock()
    label = company.replace("-", " ").title()
    organization = SQLiteOrganizationRepository(database).add(
        name_key=label.casefold(), display_name=label,
        reason="P12 accumulated telemetry acceptance", recorded_at=clock(),
    ).organization
    service = TelemetryService(SQLiteTelemetryRepository(database), now=clock)
    source = service.execute(
        PREFIX + "source.add", name="Authorized capacity sinkhole",
        organization_id=organization.id, source_kind="sinkhole",
        input_format="xti-sensor-v1", description="P12 offline capacity source",
        idempotency_key="source",
    )["source"]

    values = [record(company, index) for index in range(RECORDS)]
    preview = preview_from_records(values)
    started = time.perf_counter()
    first = service.import_preview(
        source_id=source["id"], expected_revision=1, preview=preview,
        idempotency_key="initial",
    )
    initial_seconds = time.perf_counter() - started
    require(first["status"] == "complete" and first["added_count"] == RECORDS,
            "P12 initial batch was not stored completely")

    replay = service.import_preview(
        source_id=source["id"], expected_revision=1, preview=preview,
        idempotency_key="initial",
    )
    require(replay["replayed"] and replay["id"] == first["id"],
            "P12 idempotent replay created a second run")

    first_record = service.execute(
        PREFIX + "records", organization_id=organization.id, after=0, limit=1,
    )["items"][0]
    service.execute(
        PREFIX + "review", identifier=first_record["id"], expected_revision=1,
        decision="uncertain", reason="Synthetic capacity record reviewed.",
        actor="capacity-acceptance", idempotency_key="review",
    )

    clock.advance()
    started = time.perf_counter()
    unchanged = service.import_preview(
        source_id=source["id"], expected_revision=1, preview=preview,
        idempotency_key="unchanged",
    )
    unchanged_seconds = time.perf_counter() - started
    require(unchanged["unchanged_count"] == RECORDS
            and unchanged["added_count"] == unchanged["updated_count"] == 0,
            "P12 unchanged batch duplicated or changed evidence")
    reviewed = service.execute(PREFIX + "record.get", identifier=first_record["id"])
    require(not reviewed["needs_review"], "P12 unchanged observation invalidated review")

    clock.advance()
    changed_preview = preview_from_records([record(company, 0, changed=True)])
    changed = service.import_preview(
        source_id=source["id"], expected_revision=1, preview=changed_preview,
        idempotency_key="changed",
    )
    require(changed["updated_count"] == 1, "P12 one changed record was not isolated")
    changed_record = service.execute(PREFIX + "record.get", identifier=first_record["id"])
    require(changed_record["revision"] == 2 and changed_record["needs_review"],
            "P12 changed evidence did not reopen human review")

    observed = []
    after = 0
    while True:
        page = service.execute(
            PREFIX + "records", organization_id=organization.id,
            after=after, limit=PAGE_SIZE,
        )
        observed.extend(item["native_id"] for item in page["items"])
        if not page["has_more"]:
            break
        after = page["next_after"]
    require(len(observed) == RECORDS and len(set(observed)) == RECORDS,
            "P12 accumulated pagination lost or duplicated records")
    require(all(item.startswith(company + ":") for item in observed),
            "P12 company scope returned another company's telemetry")

    report = service.execute(PREFIX + "report", organization_id=organization.id)
    require(report["records"]["total"] == RECORDS and report["runs"]["total"] == 3,
            "P12 organization report counters are inconsistent")
    return {
        "company": company, "records": RECORDS, "pages": RECORDS // PAGE_SIZE,
        "runs": 3, "idempotent_replay_created_runs": 0,
        "unchanged_added": unchanged["added_count"],
        "unchanged_updated": unchanged["updated_count"],
        "changed_records": changed["updated_count"],
        "initial_seconds": round(initial_seconds, 6),
        "unchanged_seconds": round(unchanged_seconds, 6),
        "database_bytes": database.stat().st_size,
    }


def child(root: Path, company: str) -> int:
    with patch.object(
        socket.socket, "connect", side_effect=AssertionError("P12 capacity acceptance cannot use network"),
    ):
        result = run_company(root, company)
    result["peak_rss_mib"] = round(peak_rss_mib(), 2)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


def main() -> int:
    if len(sys.argv) == 5 and sys.argv[1] == "--company" and sys.argv[3] == "--root":
        return child(Path(sys.argv[4]).resolve(), sys.argv[2])
    if len(sys.argv) != 1:
        raise SystemExit("usage: check-telemetry-delivery.py")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="xti-p12-capacity-") as temporary:
        root = Path(temporary)
        companies = []
        for company in ("company-alpha", "company-beta"):
            process = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--company", company,
                 "--root", str(root)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=600, check=False,
            )
            require(process.returncode == 0,
                    f"P12 {company} child failed: {process.stderr[-1500:]}")
            companies.append(json.loads(process.stdout))
        peak = max(item["peak_rss_mib"] for item in companies)
        slowest = max(max(item["initial_seconds"], item["unchanged_seconds"])
                      for item in companies)
        require(peak < 512, f"P12 peak RSS exceeded 512 MiB: {peak:.2f}")
        require(slowest < 60, f"P12 5,000-record import exceeded 60 seconds: {slowest:.2f}")
        print(json.dumps({
            "ok": True, "policy": "p12-telemetry-capacity-v1",
            "companies": companies, "records_per_company": RECORDS,
            "network_requests": 0, "peak_rss_mib": round(peak, 2),
            "rss_limit_mib": 512, "batch_limit_seconds": 60,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
