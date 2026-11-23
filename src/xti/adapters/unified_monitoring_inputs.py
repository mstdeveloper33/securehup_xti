"""Single-snapshot reader for P07 policies over already stored XTI evidence."""

from __future__ import annotations

import json
from pathlib import Path

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_global_search import read_global_search_snapshot
from xti.domain.content_monitoring import canonical, digest
from xti.domain.global_saved_searches import make_match
from xti.domain.unified_monitoring import MAX_MATCHES, MonitoringError, POLICY, policy_definition


class SQLiteUnifiedMonitoringInputs:
    def __init__(self, path: Path) -> None:
        self.storage = SQLiteAssetRepository(path)

    def capture(self, plan: dict, at: str) -> dict:
        definition = policy_definition(plan["definition"])
        matches = []
        coverage = []
        seen = set()
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            organization = connection.execute(
                "SELECT id,display_name,active FROM organizations WHERE id=?",
                (definition["organization_id"],),
            ).fetchone()
            if organization is None or organization[2] != 1:
                raise MonitoringError(
                    "organization_inactive", "Birleşik izleme kuruluşu bulunamadı veya etkin değil."
                )
            # Domain subjects are not merely free text: they must remain active
            # members of the selected organization at the exact capture moment.
            linked_domains = {
                row[0] for row in connection.execute(
                    "SELECT target_value FROM organization_links WHERE organization_id=? "
                    "AND target_kind='domain' AND active=1 ORDER BY target_value",
                    (organization[0],),
                ).fetchall()
            }
            for selected in definition["subjects"]:
                if selected["kind"] == "domain" and selected["value"] not in linked_domains:
                    raise MonitoringError(
                        "scope_changed",
                        "Politikadaki domain artık kuruluşun etkin kapsamına bağlı değil; politika güncellenmeli.",
                    )
                reader = read_global_search_snapshot(
                    connection, self.storage.path, selected["value"],
                    kinds=tuple(definition["record_kinds"]),
                    include_inactive=definition["include_inactive"], checked_at=at,
                    tracking=True,
                )
                accepted = []
                for result, identity, semantic in reader.observations:
                    if result.match_type not in definition["match_modes"]:
                        continue
                    flattened = tuple(value for key in sorted(identity) for value in (key, identity[key]))
                    match = make_match(result, flattened, semantic)
                    key = digest({"subject": selected, "match_key": match.key})
                    if key in seen:
                        raise StorageError("Birleşik izleme kanıt kimliği yinelendi; kısmi sonuç yazılmadı.")
                    seen.add(key)
                    matches.append({
                        "key": key, "subject": dict(selected),
                        "identity_sha256": match.key, "state_sha256": match.state_sha256,
                        "record": {field: getattr(result, field) for field in (
                            "kind", "record_type", "record_id", "display_value", "matched_field",
                            "matched_value", "match_type", "status", "current", "recorded_at",
                            "source", "source_run_id",
                        )},
                    })
                    accepted.append(result)
                    if len(matches) > definition["max_matches"] or len(matches) > MAX_MATCHES:
                        raise MonitoringError(
                            "match_limit", "Birleşik izleme eşleşmeleri politika sınırını aştı; kapsamı daraltın."
                        )
                coverage_by_kind = {}
                for item in reader.coverage:
                    coverage_by_kind.setdefault(item.kind, []).append(item)
                for item in reader.coverage:
                    same_kind = [record for record in accepted if record.kind == item.kind]
                    if len(coverage_by_kind[item.kind]) == 1:
                        accepted_count = len(same_kind)
                    else:
                        accepted_count = sum(record.source == item.source for record in same_kind)
                    coverage.append({
                        "subject": dict(selected), "kind": item.kind, "source": item.source,
                        "examined_count": item.examined_count,
                        "query_match_count": item.matched_count,
                        "accepted_match_count": accepted_count,
                        "latest_run_id": item.latest_run_id,
                        "latest_run_status": item.latest_run_status,
                        "latest_run_at": item.latest_run_at,
                        "latest_success_run_id": item.latest_success_run_id,
                        "latest_success_at": item.latest_success_at,
                        "notes": list(item.notes),
                    })
            connection.rollback()
        snapshot = {
            "policy": POLICY, "policy_id": plan["id"],
            "policy_revision": plan["revision"],
            "organization": {"id": organization[0], "display_name": organization[1]},
            "definition_sha256": digest(definition),
            "subjects": definition["subjects"],
            "matches": sorted(matches, key=lambda item: item["key"]),
            "coverage": sorted(coverage, key=lambda item: (
                item["subject"]["kind"], item["subject"]["value"], item["kind"], item["source"]
            )),
        }
        # Force tuples and dataclasses through the exact persisted JSON shape.
        return json.loads(canonical(snapshot))
