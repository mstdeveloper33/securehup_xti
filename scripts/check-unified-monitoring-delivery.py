#!/usr/bin/env python3
"""P07 accumulated stored-evidence acceptance; performs no network request."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import resource
import socket
import subprocess
import sqlite3
import sys
import tempfile
import time
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_unified_monitoring import SQLiteUnifiedMonitoringRepository
from xti.adapters.unified_monitoring_inputs import SQLiteUnifiedMonitoringInputs
from xti.application.unified_monitoring import UnifiedMonitoringService
from xti.domain.unified_monitoring import PREFIX


MATCHES = 5_000
UNCHANGED_RUNS = 30


def require(value, message):
    if not value:
        raise AssertionError(message)


def peak_rss_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


class Clock:
    def __init__(self):
        self.value = datetime(2026, 11, 22, 8, tzinfo=timezone.utc)

    def __call__(self):
        return self.value.isoformat()

    def advance(self):
        self.value += timedelta(minutes=5)


def populate_assets(storage: SQLiteAssetRepository, company: str, at: str) -> None:
    with storage._connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.executemany(
            "INSERT INTO assets (id,value,created_at) VALUES (?,?,?)",
            ((str(uuid5(NAMESPACE_URL, f"p07:{company}:{index}")),
              f"capacity-{index:05d}.{company}.example", at) for index in range(MATCHES)),
        )
        connection.commit()


def run_company(root: Path, company: str) -> dict:
    database = root / company / "xti.db"
    storage = SQLiteAssetRepository(database)
    storage.initialize()
    clock = Clock()
    populate_assets(storage, company, clock())
    organizations = SQLiteOrganizationRepository(database)
    organization = organizations.add(
        name_key=company.replace("-", " "), display_name=company.replace("-", " ").title(),
        reason="P07 accumulated acceptance", recorded_at=clock(),
    ).organization
    service = UnifiedMonitoringService(
        SQLiteUnifiedMonitoringRepository(database), SQLiteUnifiedMonitoringInputs(database),
        now=clock,
    )
    policy = service.execute(
        PREFIX + "policy.add", name="P07 accumulated watch",
        organization_id=organization.id,
        subjects=[{"kind": "brand", "value": "capacity-"}],
        record_kinds=["domain"], match_modes=["prefix"],
        notify_on=["added", "updated", "removed"], minimum_change_count=1,
        priority="high", interval_seconds=300, max_matches=10_000,
        actor="capacity-acceptance", reason="Birikimli P07 davranışı ölçülüyor.",
        idempotency_key="policy",
    )
    durations = []
    for cycle in range(UNCHANGED_RUNS + 1):
        clock.advance()
        started = time.perf_counter()
        run = service.execute(
            PREFIX + "run", identifier=policy["id"], expected_revision=1,
            idempotency_key=f"run:{cycle}",
        )
        durations.append(time.perf_counter() - started)
        require(run["status"] == "complete", "P07 run did not complete")
        require(run["report"]["total_matches"] == MATCHES, "P07 match count changed")
        if cycle == 0:
            require(run["report"]["silent_baseline"], "P07 baseline was not silent")
            require(run["alert_id"] is None, "P07 baseline created an alert")
        else:
            require(run["report"]["counts"]["unchanged"] == MATCHES,
                    "P07 unchanged run changed evidence")
            require(not run["report"]["alert_required"], "P07 unchanged run alerted")

    with closing(sqlite3.connect(database)) as connection:
        stored_snapshots = connection.execute(
            "SELECT COUNT(*) FROM monitoring_runs WHERE snapshot_json IS NOT NULL"
        ).fetchone()[0]
        alerts_before = connection.execute("SELECT COUNT(*) FROM monitoring_alerts").fetchone()[0]
    require(stored_snapshots == 1, "P07 unchanged runs duplicated the frozen snapshot")
    require(alerts_before == 0, "P07 unchanged runs created alerts")

    storage.add(f"capacity-new.{company}.example")
    clock.advance()
    changed = service.execute(
        PREFIX + "run", identifier=policy["id"], expected_revision=1,
        idempotency_key="changed",
    )
    replay = service.execute(
        PREFIX + "run", identifier=policy["id"], expected_revision=1,
        idempotency_key="changed",
    )
    require(changed["report"]["counts"]["added"] == 1, "P07 one change was not isolated")
    require(changed["alert_id"] is not None, "P07 threshold change did not alert")
    require(replay["replayed"], "P07 run replay was not idempotent")
    page = service.execute(PREFIX + "alerts", after=0, limit=100, read_state="all")
    require(page["total_count"] == 1 and len(page["items"]) == 1,
            "P07 accumulated alert count is inconsistent")

    with closing(sqlite3.connect(database)) as connection:
        counts = {
            table: connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
            for table in ("monitoring_runs", "monitoring_alerts", "monitoring_alert_reviews")
        }
        stored_snapshots = connection.execute(
            "SELECT COUNT(*) FROM monitoring_runs WHERE snapshot_json IS NOT NULL"
        ).fetchone()[0]
    require(counts == {
        "monitoring_runs": UNCHANGED_RUNS + 2,
        "monitoring_alerts": 1,
        "monitoring_alert_reviews": 0,
    }, "P07 accumulated rows are inconsistent")
    require(stored_snapshots == 2, "P07 changed snapshot retention is inconsistent")
    return {
        "company": company, "matches": MATCHES,
        "runs": UNCHANGED_RUNS + 2, "unchanged_runs": UNCHANGED_RUNS,
        "stored_snapshots": stored_snapshots, "alerts": 1,
        "replay_created_runs": 0, "maximum_run_seconds": round(max(durations), 6),
        "database_bytes": database.stat().st_size,
    }


def child(root: Path, company: str) -> int:
    with patch.object(
        socket.socket, "connect", side_effect=AssertionError("P07 acceptance cannot use network")
    ):
        result = run_company(root, company)
    result["peak_rss_mib"] = round(peak_rss_mib(), 2)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def main() -> int:
    if len(sys.argv) == 5 and sys.argv[1] == "--company" and sys.argv[3] == "--root":
        return child(Path(sys.argv[4]).resolve(), sys.argv[2])
    if len(sys.argv) != 1:
        raise SystemExit("usage: check-unified-monitoring-delivery.py")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="xti-p07-capacity-") as temporary:
        root = Path(temporary)
        results = []
        for company in ("company-alpha", "company-beta"):
            process = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--company", company,
                 "--root", str(root)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=600, check=False,
            )
            require(process.returncode == 0,
                    f"P07 {company} child failed: {process.stderr[-1000:]}")
            results.append(json.loads(process.stdout))
        memory = max(item["peak_rss_mib"] for item in results)
        require(memory < 512, f"P07 peak RSS exceeded 512 MiB: {memory:.2f}")
        require(max(item["maximum_run_seconds"] for item in results) < 30,
                "P07 stored-evidence run exceeded 30 seconds")
        print(json.dumps({
            "ok": True, "policy": "p07-unified-monitoring-capacity-v1",
            "companies": results, "peak_rss_mib": round(memory, 2),
            "rss_limit_mib": 512, "network_requests": 0,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
