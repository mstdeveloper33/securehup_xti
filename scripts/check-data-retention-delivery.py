#!/usr/bin/env python3
"""P08 accumulated lossless retention acceptance; performs no network request."""

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
from uuid import NAMESPACE_URL, uuid5


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_data_retention import SQLiteDataRetentionRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_unified_monitoring import SQLiteUnifiedMonitoringRepository
from xti.adapters.unified_monitoring_inputs import SQLiteUnifiedMonitoringInputs
from xti.application.data_retention import DataRetentionService
from xti.application.unified_monitoring import UnifiedMonitoringService
from xti.domain.data_retention import FAMILY, PREFIX
from xti.domain.unified_monitoring import PREFIX as MONITORING_PREFIX


MATCHES = 1_000
CHANGED_RUNS = 12
BATCH_LIMIT = 10


def require(value, message):
    if not value:
        raise AssertionError(message)


def peak_rss_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value.isoformat()

    def advance(self, minutes=5):
        self.value += timedelta(minutes=minutes)


def populate_assets(storage, company, at):
    with storage._connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.executemany(
            "INSERT INTO assets (id,value,created_at) VALUES (?,?,?)",
            ((str(uuid5(NAMESPACE_URL, f"p08:{company}:{index}")),
              f"capacity-{index:05d}.{company}.example", at)
             for index in range(MATCHES)),
        )
        connection.commit()


def run_company(root: Path, company: str) -> dict:
    database = root / company / "xti.db"
    storage = SQLiteAssetRepository(database)
    storage.initialize()
    monitoring_clock = Clock(datetime(2026, 1, 2, 8, tzinfo=timezone.utc))
    populate_assets(storage, company, monitoring_clock())
    organization = SQLiteOrganizationRepository(database).add(
        name_key=company.replace("-", " "), display_name=company.replace("-", " ").title(),
        reason="P08 accumulated acceptance", recorded_at=monitoring_clock(),
    ).organization
    monitoring = UnifiedMonitoringService(
        SQLiteUnifiedMonitoringRepository(database), SQLiteUnifiedMonitoringInputs(database),
        now=monitoring_clock,
    )
    monitoring_policy = monitoring.execute(
        MONITORING_PREFIX + "policy.add", name="P08 archive source",
        organization_id=organization.id,
        subjects=[{"kind": "brand", "value": "capacity-"}],
        record_kinds=["domain"], match_modes=["prefix"],
        notify_on=["added", "updated", "removed"], minimum_change_count=1,
        priority="high", interval_seconds=300, max_matches=2_000,
        actor="capacity-acceptance", reason="P08 sıkıştırılabilir kanıt geçmişi.",
        idempotency_key="monitoring-policy",
    )
    run_ids = []
    for cycle in range(CHANGED_RUNS + 1):
        if cycle:
            storage.add(f"capacity-new-{cycle:03d}.{company}.example")
        monitoring_clock.advance()
        run = monitoring.execute(
            MONITORING_PREFIX + "run", identifier=monitoring_policy["id"],
            expected_revision=monitoring_policy["revision"],
            idempotency_key=f"monitoring-run:{cycle}",
        )
        require(run["status"] == "complete", "P08 source monitoring run did not complete")
        require(run["report"]["total_matches"] == MATCHES + cycle,
                "P08 source snapshot count changed")
        run_ids.append(run["id"])

    before = {
        identifier: monitoring.execute(MONITORING_PREFIX + "run.show", identifier=identifier)
        for identifier in (run_ids[0], run_ids[BATCH_LIMIT - 1])
    }
    retention_clock = Clock(datetime(2026, 11, 22, 10, tzinfo=timezone.utc))
    retention = DataRetentionService(
        SQLiteDataRetentionRepository(database), now=retention_clock,
    )
    policy = retention.execute(
        PREFIX + "policy.add", name="P08 accumulated retention",
        organization_id=organization.id, families=[FAMILY], archive_after_days=90,
        batch_limit=BATCH_LIMIT, purpose="Lossless monitoring evidence lifecycle",
        retention_basis="Controlled P08 capacity acceptance",
        actor="capacity-privacy", reason="P08 retention capacity policy.",
        idempotency_key="retention-policy",
    )

    archive_runs, original_bytes, compressed_bytes, maximum_seconds = [], 0, 0, 0.0
    cycle = 0
    while True:
        plan = retention.execute(PREFIX + "plan", identifier=policy["id"])
        if not plan["selected_count"]:
            break
        started = time.perf_counter()
        applied = retention.execute(
            PREFIX + "apply", identifier=policy["id"],
            expected_revision=policy["revision"], token=plan["token"],
            actor="capacity-privacy", reason="Apply bounded P08 archive batch.",
            idempotency_key=f"archive:{cycle}",
        )
        maximum_seconds = max(maximum_seconds, time.perf_counter() - started)
        replay = retention.execute(
            PREFIX + "apply", identifier=policy["id"],
            expected_revision=policy["revision"], token=plan["token"],
            actor="capacity-privacy", reason="Apply bounded P08 archive batch.",
            idempotency_key=f"archive:{cycle}",
        )
        require(replay["replayed"] and replay["id"] == applied["id"],
                "P08 archive replay was not idempotent")
        require(applied["status"] == "complete", "P08 archive batch did not complete")
        archive_runs.append(applied)
        original_bytes += applied["receipt"]["original_body_bytes"]
        compressed_bytes += applied["receipt"]["compressed_body_bytes"]
        cycle += 1

    require(len(archive_runs) == 2, "P08 batch boundary did not create two archive runs")
    require(sum(item["receipt"]["changed_count"] for item in archive_runs) == len(run_ids),
            "P08 did not archive every eligible historical run")
    require(compressed_bytes < original_bytes * 0.5,
            "P08 accumulated archive did not materially reduce retained body bytes")
    for identifier, expected in before.items():
        require(monitoring.execute(MONITORING_PREFIX + "run.show", identifier=identifier) == expected,
                "P08 transparent archive read changed monitoring evidence")

    restored = retention.execute(
        PREFIX + "restore", identifier=archive_runs[0]["id"],
        actor="capacity-privacy", reason="P08 accumulated restore acceptance.",
        idempotency_key="restore:first-batch",
    )
    require(restored["status"] == "complete"
            and restored["receipt"]["changed_count"] == BATCH_LIMIT,
            "P08 accumulated restore count is inconsistent")
    for identifier, expected in before.items():
        require(monitoring.execute(MONITORING_PREFIX + "run.show", identifier=identifier) == expected,
                "P08 restored evidence changed")

    run_page = retention.execute(PREFIX + "runs", policy_id=policy["id"], after=0, limit=1)
    require(run_page["total_count"] == 3 and len(run_page["items"]) == 1
            and run_page["next_after"] is not None,
            "P08 run history pagination is inconsistent")
    audit = retention.execute(
        PREFIX + "audit", organization_id=organization.id, after=0, limit=100,
    )
    require(audit["total_count"] == 7,
            "P08 audit event count is inconsistent")
    report = storage.inspect()
    require(report["retention_policy_count"] == 1
            and report["retention_run_count"] == 3,
            "P08 storage inspection counts are inconsistent")
    return {
        "company": company, "monitoring_runs": len(run_ids),
        "archive_runs": len(archive_runs), "restore_runs": 1,
        "archived_records": len(run_ids), "restored_records": BATCH_LIMIT,
        "original_body_bytes": original_bytes,
        "compressed_body_bytes": compressed_bytes,
        "compression_ratio": round(compressed_bytes / original_bytes, 6),
        "maximum_archive_seconds": round(maximum_seconds, 6),
        "audit_events": audit["total_count"], "database_bytes": database.stat().st_size,
    }


def child(root: Path, company: str) -> int:
    with patch.object(
        socket.socket, "connect", side_effect=AssertionError("P08 acceptance cannot use network")
    ):
        result = run_company(root, company)
    result["peak_rss_mib"] = round(peak_rss_mib(), 2)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def main() -> int:
    if len(sys.argv) == 5 and sys.argv[1] == "--company" and sys.argv[3] == "--root":
        return child(Path(sys.argv[4]).resolve(), sys.argv[2])
    if len(sys.argv) != 1:
        raise SystemExit("usage: check-data-retention-delivery.py")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="xti-p08-capacity-") as temporary:
        root, results = Path(temporary), []
        for company in ("company-alpha", "company-beta"):
            process = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--company", company,
                 "--root", str(root)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=600, check=False,
            )
            require(process.returncode == 0,
                    f"P08 {company} child failed: {process.stderr[-3000:]}")
            results.append(json.loads(process.stdout))
        memory = max(item["peak_rss_mib"] for item in results)
        require(memory < 512, f"P08 peak RSS exceeded 512 MiB: {memory:.2f}")
        require(max(item["maximum_archive_seconds"] for item in results) < 30,
                "P08 archive batch exceeded 30 seconds")
        print(json.dumps({
            "ok": True, "policy": "p08-data-retention-capacity-v1",
            "companies": results, "peak_rss_mib": round(memory, 2),
            "rss_limit_mib": 512, "network_requests": 0,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
