#!/usr/bin/env python3
"""P08/P12 two-company telemetry archive capacity acceptance; no network."""

from datetime import datetime, timezone
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
from xti.adapters.sqlite_data_retention import SQLiteDataRetentionRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_telemetry import SQLiteTelemetryRepository
from xti.application.data_retention import DataRetentionService
from xti.application.telemetry import TelemetryService
from xti.domain.data_retention import PREFIX as RETENTION_PREFIX, TELEMETRY_FAMILY
from xti.domain.telemetry import PREFIX as TELEMETRY_PREFIX, preview_from_records


RECORDS = 1_000
BATCH = 250


def require(value, message):
    if not value:
        raise AssertionError(message)


def peak_rss_mib():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value.isoformat()


def telemetry_record(company, index):
    domain = f"retention-{index:05d}.{company}.example"
    return {
        "native_id": f"{company}:retention:{index:05d}", "kind": "dns_query",
        "event_at": "2026-01-01T07:59:00+00:00",
        "summary": f"Authorized retention observation for {domain}",
        "outcome": "observed", "src_ip": "192.0.2.25", "dst_ip": "192.0.2.53",
        "src_port": 5353, "dst_port": 53, "protocol": "udp", "domain": domain,
        "url": None, "hashes": {},
        "indicators": [{"type": "domain", "value": domain}],
        "attributes": [
            {"name": "sensor_name", "value": "authorized-retention-sensor-" * 12}
            for _item in range(24)
        ],
        "tags": ["p08-p12-capacity"],
    }


def run_company(root, company):
    database = root / company / "xti.db"
    storage = SQLiteAssetRepository(database); storage.initialize()
    telemetry_clock = Clock(datetime(2026, 1, 1, 8, tzinfo=timezone.utc))
    organization = SQLiteOrganizationRepository(database).add(
        name_key=company.replace("-", " "), display_name=company.replace("-", " ").title(),
        reason="P08/P12 capacity organization", recorded_at=telemetry_clock(),
    ).organization
    telemetry = TelemetryService(SQLiteTelemetryRepository(database), now=telemetry_clock)
    source = telemetry.execute(
        TELEMETRY_PREFIX + "source.add", name="Authorized retention sensor",
        organization_id=organization.id, source_kind="sinkhole",
        input_format="xti-sensor-v1", description="Offline retention capacity source",
        idempotency_key="source",
    )["source"]
    preview = preview_from_records([telemetry_record(company, index) for index in range(RECORDS)])
    imported = telemetry.import_preview(
        source_id=source["id"], expected_revision=1, preview=preview,
        idempotency_key="initial",
    )
    require(imported["added_count"] == RECORDS, "telemetry seed count")
    first_id = telemetry.execute(
        TELEMETRY_PREFIX + "records", organization_id=organization.id, after=0, limit=1,
    )["items"][0]["id"]
    first_before = telemetry.execute(TELEMETRY_PREFIX + "record.get", identifier=first_id)

    retention_clock = Clock(datetime(2026, 11, 23, 10, tzinfo=timezone.utc))
    retention = DataRetentionService(
        SQLiteDataRetentionRepository(database), now=retention_clock,
    )
    policy = retention.execute(
        RETENTION_PREFIX + "policy.add", name="Telemetry capacity retention",
        organization_id=organization.id, families=[TELEMETRY_FAMILY],
        archive_after_days=90, batch_limit=BATCH,
        purpose="Normalized telemetry capacity lifecycle",
        retention_basis="Controlled offline capacity acceptance",
        actor="capacity", reason="P08/P12 capacity policy.",
        idempotency_key="policy",
    )
    runs = []
    original = compressed = 0
    maximum_seconds = 0.0
    while True:
        plan = retention.execute(RETENTION_PREFIX + "plan", identifier=policy["id"])
        if not plan["selected_count"]:
            break
        started = time.perf_counter()
        applied = retention.execute(
            RETENTION_PREFIX + "apply", identifier=policy["id"],
            expected_revision=policy["revision"], token=plan["token"],
            actor="capacity", reason="Bounded telemetry archive batch.",
            idempotency_key=f"archive:{len(runs)}",
        )
        maximum_seconds = max(maximum_seconds, time.perf_counter() - started)
        require(applied["status"] == "complete", "archive status")
        runs.append(applied)
        original += applied["receipt"]["original_body_bytes"]
        compressed += applied["receipt"]["compressed_body_bytes"]
    require(len(runs) == RECORDS // BATCH, "archive batch count")
    require(sum(run["receipt"]["changed_count"] for run in runs) == RECORDS,
            "archived telemetry count")
    require(compressed < original * 0.5, "telemetry compression ratio")
    require(telemetry.execute(
        TELEMETRY_PREFIX + "record.get", identifier=first_id,
    ) == first_before, "transparent archived telemetry read")
    restored = retention.execute(
        RETENTION_PREFIX + "restore", identifier=runs[0]["id"],
        actor="capacity", reason="Capacity restore acceptance.",
        idempotency_key="restore:first",
    )
    require(restored["receipt"]["changed_count"] == BATCH, "restore count")
    require(telemetry.execute(
        TELEMETRY_PREFIX + "record.get", identifier=first_id,
    ) == first_before, "restored telemetry read")
    return {
        "company": company, "records": RECORDS, "archive_runs": len(runs),
        "restored_records": BATCH, "original_body_bytes": original,
        "compressed_body_bytes": compressed,
        "compression_ratio": round(compressed / original, 6),
        "maximum_archive_seconds": round(maximum_seconds, 6),
        "database_bytes": database.stat().st_size,
    }


def child(root, company):
    with patch.object(
        socket.socket, "connect",
        side_effect=AssertionError("telemetry retention acceptance cannot use network"),
    ):
        result = run_company(root, company)
    result["peak_rss_mib"] = round(peak_rss_mib(), 2)
    print(json.dumps(result, sort_keys=True))
    return 0


def main():
    if len(sys.argv) == 5 and sys.argv[1] == "--company" and sys.argv[3] == "--root":
        return child(Path(sys.argv[4]).resolve(), sys.argv[2])
    if len(sys.argv) != 1:
        raise SystemExit("usage: check-telemetry-retention-delivery.py")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="xti-p08-p12-retention-") as temporary:
        root = Path(temporary)
        companies = []
        for company in ("company-alpha", "company-beta"):
            process = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--company", company,
                 "--root", str(root)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=600, check=False,
            )
            require(process.returncode == 0, process.stderr[-3000:])
            companies.append(json.loads(process.stdout))
        peak = max(item["peak_rss_mib"] for item in companies)
        slowest = max(item["maximum_archive_seconds"] for item in companies)
        require(peak < 512, f"peak RSS exceeded: {peak}")
        require(slowest < 30, f"archive batch exceeded: {slowest}")
        print(json.dumps({
            "ok": True, "policy": "p08-p12-telemetry-retention-capacity-v1",
            "companies": companies, "records_per_company": RECORDS,
            "network_requests": 0, "peak_rss_mib": round(peak, 2),
            "rss_limit_mib": 512, "batch_limit_seconds": 30,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
