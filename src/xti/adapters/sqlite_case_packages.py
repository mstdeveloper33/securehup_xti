"""Complete bounded SQLite snapshots for immutable case evidence packages."""

from dataclasses import asdict
import json
from pathlib import Path

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cases import SQLiteCaseRepository, read_case_evidence_links
from xti.domain.assets import ValidationError
from xti.domain.cases import canonical_snapshot, normalize_case_id


_EVIDENCE = (
    "id,case_id,evidence_type,evidence_id,display_value,source_reference,"
    "snapshot_json,snapshot_sha256,active,added_reason,added_at,updated_at,"
    "removed_reason,removed_at"
)
_TASK = "id,case_id,title,status,due_at,reason,created_at,updated_at"
_ACTIVITY = (
    "sequence,id,case_id,activity_type,reference_id,summary,reason,"
    "snapshot_json,snapshot_sha256,recorded_at"
)


class SQLiteCasePackageReader:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    def snapshot(self, case_id: str) -> dict:
        case_id = normalize_case_id(case_id)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            case = SQLiteCaseRepository._get_case(connection, case_id)
            counts = {
                "evidence": connection.execute(
                    "SELECT COUNT(*) FROM case_evidence WHERE case_id=?", (case_id,),
                ).fetchone()[0],
                "tasks": connection.execute(
                    "SELECT COUNT(*) FROM case_tasks WHERE case_id=?", (case_id,),
                ).fetchone()[0],
                "activities": connection.execute(
                    "SELECT COUNT(*) FROM case_activities WHERE case_id=?", (case_id,),
                ).fetchone()[0],
            }
            limits = {"evidence": 50_000, "tasks": 50_000, "activities": 100_000}
            for name, count in counts.items():
                if count > limits[name]:
                    raise ValidationError(
                        f"Vaka paketi {name} için {limits[name]:,} kayıt sınırını aşıyor; kısmi paket üretilmedi."
                    )
            evidence_rows = connection.execute(
                f"SELECT {_EVIDENCE} FROM case_evidence WHERE case_id=? ORDER BY id",
                (case_id,),
            ).fetchall()
            task_rows = connection.execute(
                f"SELECT {_TASK} FROM case_tasks WHERE case_id=? ORDER BY id", (case_id,),
            ).fetchall()
            activity_rows = connection.execute(
                f"SELECT {_ACTIVITY} FROM case_activities WHERE case_id=? ORDER BY sequence",
                (case_id,),
            ).fetchall()
            # This replay verifies that mutable link rows still agree with their immutable events.
            links = {item.id: item for item in read_case_evidence_links(connection) if item.case_id == case_id}
            connection.rollback()
        evidence = tuple(SQLiteCaseRepository._evidence(row) for row in evidence_rows)
        tasks = tuple(SQLiteCaseRepository._task(row) for row in task_rows)
        activities = tuple(SQLiteCaseRepository._activity(row) for row in activity_rows)
        if len(links) != len(evidence) or any(links.get(item.id) != item for item in evidence):
            raise StorageError("Vaka paketi kanıt olay zinciriyle uyuşmuyor.")
        if any(item.case_id != case_id for item in (*evidence, *tasks, *activities)):
            raise StorageError("Vaka paketi başka vakaya ait kayıt içeriyor.")
        if not activities or activities[0].activity_type != "case_created":
            raise StorageError("Vaka paketi başlangıç olayı eksik.")
        lifecycle_rows = [
            row for row in activity_rows
            if row[3] in {"case_created", "case_updated", "status_changed"}
        ]
        expected_case, _ = canonical_snapshot(SQLiteCaseRepository._case_payload(case))
        if not lifecycle_rows or lifecycle_rows[-1][7] != expected_case:
            raise StorageError("Vaka paketi güncel vaka durumu ile olay zincirini eşleştiremedi.")
        evidence_payload = []
        for item in evidence:
            row = asdict(item)
            row["snapshot"] = json.loads(row.pop("snapshot_json"))
            evidence_payload.append(row)
        activity_payload = []
        for item, raw in zip(activities, activity_rows, strict=True):
            row = asdict(item)
            row["snapshot"] = json.loads(raw[7])
            activity_payload.append(row)
        return {
            "kind": "xti_case_snapshot", "version": 1,
            "case": asdict(case), "evidence": evidence_payload,
            "tasks": [asdict(item) for item in tasks],
            "activities": activity_payload,
            "counts": counts,
            "limitations": [
                "Kaynak iddiaları doğrulanmış saldırı veya ihlal hükmü değildir.",
                "Bu görünüm yalnız yerel vaka ve donmuş kanıt kayıtlarını kapsar.",
            ],
        }
