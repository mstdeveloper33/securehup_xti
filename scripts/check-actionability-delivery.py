#!/usr/bin/env python3
"""P06 accumulated local capacity acceptance; performs no network request."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import resource
import socket
import sys
import tempfile
import time
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from xti.adapters.case_package_files import AtomicCasePackagePublisher
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_actionability import SQLiteActionabilityRepository
from xti.adapters.sqlite_case_packages import SQLiteCasePackageReader
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.application.actionability import ActionabilityService
from xti.application.case_packages import CasePackageService
from xti.application.ioc_bulk import IocBulkService
from xti.domain.ioc_bulk import preview


IOC_RECORDS = 20_000
CASE_TASKS = 5_000


def require(value, message):
    if not value:
        raise AssertionError(message)


def peak_rss_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


def build_ioc_payload(observed_at: str) -> bytes:
    records = [{
        "indicator_type": "domain", "value": f"ioc-{index:05d}.example",
        "source_name": "p06-capacity", "source_reference": f"fixture:{index:05d}",
        "confidence": 70, "valid_from": None, "valid_until": None,
        "description": "Synthetic, non-routable P06 capacity assertion.",
        "observed_at": observed_at,
    } for index in range(IOC_RECORDS)]
    return (json.dumps({
        "format": "xti-ioc-assertions", "version": 1, "records": records,
    }, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")


def populate_case_history(repository: SQLiteCaseRepository, case_id: str, at: str) -> None:
    storage = repository._storage
    with storage._connection() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            for index in range(CASE_TASKS):
                task_id = str(uuid5(NAMESPACE_URL, f"p06-capacity-task:{index}"))
                title = f"Synthetic defensive task {index:05d}"
                connection.execute(
                    "INSERT INTO case_tasks "
                    "(id,case_id,title,status,due_at,reason,created_at,updated_at) "
                    "VALUES (?, ?, ?, 'done', NULL, ?, ?, ?)",
                    (task_id, case_id, title, "P06 capacity acceptance.", at, at),
                )
                repository._insert_activity(
                    connection, case_id=case_id, activity_type="task_added",
                    reference_id=task_id, summary=title,
                    reason="P06 capacity acceptance.",
                    payload={
                        "kind": "case_task", "id": task_id, "title": title,
                        "status": "done", "due_at": None,
                    }, recorded_at=at,
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def main() -> int:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="xti-p06-capacity-") as temporary, patch.object(
        socket.socket, "connect", side_effect=AssertionError("P06 capacity acceptance cannot use network")
    ):
        root = Path(temporary)
        database = root / "data" / "xti.db"
        storage = SQLiteAssetRepository(database)
        storage.initialize()
        base = datetime.now(timezone.utc) - timedelta(days=1)

        case_repository = SQLiteCaseRepository(database)
        case = case_repository.create(
            title="P06 accumulated case", summary="Large local case package acceptance.",
            priority="high", reason="P06 capacity acceptance.",
            recorded_at=base.isoformat(),
        ).case
        history_started = time.perf_counter()
        populate_case_history(case_repository, case.id, base.isoformat())
        history_seconds = time.perf_counter() - history_started

        action_service = ActionabilityService(
            SQLiteActionabilityRepository(database),
            clock=lambda: base + timedelta(hours=1),
        )
        plan = action_service.runbook_plan(case.id)
        applied = action_service.runbook_apply(
            case.id, expected_plan_sha256=plan.plan_sha256,
            idempotency_key="p06-capacity-runbook",
            reason="Apply the deterministic defensive runbook.",
        )
        replay = action_service.runbook_apply(
            case.id, expected_plan_sha256=plan.plan_sha256,
            idempotency_key="p06-capacity-runbook",
            reason="Apply the deterministic defensive runbook.",
        )
        require(replay.replayed and replay.created_task_ids == applied.created_task_ids,
                "P06 runbook replay was not idempotent")

        package_destination = root / "case-package"
        package_service = CasePackageService(
            SQLiteCasePackageReader(database), AtomicCasePackagePublisher(),
            clock=lambda: base + timedelta(hours=2),
        )
        package_started = time.perf_counter()
        artifact = package_service.create(case.id, package_destination)
        verified = package_service.verify(package_destination)
        package_seconds = time.perf_counter() - package_started
        require(verified.manifest_sha256 == artifact.manifest_sha256,
                "P06 package verification did not preserve the manifest digest")

        payload = build_ioc_payload(base.isoformat())
        ioc_service = IocBulkService(
            SQLiteCtiIndicatorRepository(database),
            clock=lambda: base + timedelta(hours=3),
        )
        import_started = time.perf_counter()
        planned = preview(payload, "json")
        imported = ioc_service.import_payload(
            payload, format="json", expected_content_sha256=planned.content_sha256,
            idempotency_key="p06-capacity-ioc", import_source_name="capacity-fixture",
            import_source_reference="p06-capacity.json",
        )
        replayed = ioc_service.import_payload(
            payload, format="json", expected_content_sha256=planned.content_sha256,
            idempotency_key="p06-capacity-ioc", import_source_name="capacity-fixture",
            import_source_reference="p06-capacity.json",
        )
        import_seconds = time.perf_counter() - import_started
        require(imported.added_count == IOC_RECORDS and replayed.replayed,
                "P06 IOC import/replay counts are inconsistent")
        export_started = time.perf_counter()
        exported = ioc_service.build_export(format="stix")
        export_seconds = time.perf_counter() - export_started
        require(exported.record_count == IOC_RECORDS,
                "P06 STIX export record count is inconsistent")

        report = storage.inspect()
        require(report["action_runbook_count"] == 1, "P06 runbook receipt count")
        require(report["action_ioc_import_run_count"] == 1, "P06 IOC receipt count")
        memory = peak_rss_mib()
        require(memory < 512, f"P06 peak RSS exceeded 512 MiB: {memory:.2f}")
        require(package_seconds < 30, f"P06 package exceeded 30 seconds: {package_seconds:.3f}")
        require(import_seconds < 120, f"P06 IOC import exceeded 120 seconds: {import_seconds:.3f}")
        print(json.dumps({
            "ok": True, "policy": "p06-actionability-capacity-v1",
            "case_tasks_before_runbook": CASE_TASKS,
            "case_activities_before_runbook": CASE_TASKS + 1,
            "runbook_steps": len(plan.steps), "runbook_replay_created_tasks": 0,
            "ioc_records": IOC_RECORDS, "ioc_replay_created_records": 0,
            "stix_export_records": exported.record_count,
            "package_bytes": sum(
                item.stat().st_size for item in package_destination.iterdir()
            ),
            "database_bytes": database.stat().st_size,
            "seconds": {
                "history_population": round(history_seconds, 3),
                "package_create_and_verify": round(package_seconds, 3),
                "ioc_import_and_replay": round(import_seconds, 3),
                "stix_export": round(export_seconds, 3),
                "total": round(time.monotonic() - started, 3),
            },
            "peak_rss_mib": round(memory, 2), "rss_limit_mib": 512,
            "network_requests": 0,
        }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
