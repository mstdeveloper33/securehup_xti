"""Frozen, network-free P04 inputs from source-preserving local records."""

from dataclasses import asdict
import json
from pathlib import Path

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.attack_catalog import parse_record
from xti.domain.cti_analysis import CtiAnalysisError, profile_definition
from xti.domain.cti_knowledge import aliases_from_json


ATTACK_ENTITY_LIMIT = 50_000
ATTACK_RELATIONSHIP_LIMIT = 100_000
ATTACK_PHASE_LIMIT = 100_000


class SQLiteCtiAnalysisInputs:
    def __init__(self, path: Path) -> None:
        self.storage = SQLiteAssetRepository(path)

    @staticmethod
    def _assertion(row, *, aliases: bool = False) -> dict:
        result = {
            "id": row[0], "source_name": row[1], "source_reference": row[2],
            "confidence": row[3], "description": row[5] if aliases else row[4],
            "last_seen_at": row[7] if aliases else row[5],
        }
        if aliases:
            result["aliases"] = list(aliases_from_json(row[4]))
        return result

    @staticmethod
    def _bounded(rows, maximum: int, message: str):
        rows = list(rows)
        if len(rows) > maximum:
            raise CtiAnalysisError("scope_too_large", message)
        return rows

    @staticmethod
    def _scoped_rows(connection, *, table: str, owner: str, columns: str,
                     identifiers: set[str], maximum: int, order: str,
                     message: str) -> list:
        """Read only assertions owned by the frozen records, under one total cap.

        A global LIMIT before owner filtering can starve selected records when the
        database also contains unrelated CTI.  Batch the selected identifiers and
        enforce the limit after combining the scoped rows instead.
        """
        rows = []
        ordered = sorted(identifiers)
        for start in range(0, len(ordered), 400):
            batch = ordered[start:start + 400]
            placeholders = ",".join("?" for _ in batch)
            remaining = maximum + 1 - len(rows)
            rows.extend(connection.execute(
                f"SELECT {columns} FROM {table} WHERE active=1 "
                f"AND {owner} IN ({placeholders}) ORDER BY {order} LIMIT ?",
                (*batch, remaining),
            ).fetchall())
            if len(rows) > maximum:
                raise CtiAnalysisError("scope_too_large", message)
        rows.sort(key=lambda row: tuple(row[index] for index in range(len(row))))
        return rows

    def capture(self, profile: dict, accepted_identity_links: list[dict], at: str) -> dict:
        definition = profile_definition(profile["definition"])
        if profile["organization"]["id"] != definition["organization_id"]:
            raise StorageError("CTI analiz profili kuruluş kapsamıyla uyuşmuyor.")
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            organization = connection.execute(
                "SELECT id,display_name,active FROM organizations WHERE id=?",
                (definition["organization_id"],),
            ).fetchone()
            if organization is None or organization[2] != 1:
                raise CtiAnalysisError("organization_unavailable", "CTI analiz kuruluşu bulunamadı veya etkin değil.")
            domains = [row[0] for row in connection.execute(
                "SELECT target_value FROM organization_links WHERE organization_id=? "
                "AND active=1 AND target_kind='domain' ORDER BY target_value",
                (organization[0],),
            )]

            entity_rows = self._bounded(connection.execute(
                "SELECT DISTINCT e.id,e.entity_type,e.display_name FROM cti_entities e "
                "JOIN cti_entity_assertions a ON a.entity_id=e.id AND a.active=1 "
                "ORDER BY e.entity_type,e.name_key,e.id LIMIT ?",
                (definition["max_entities"] + 1,),
            ), definition["max_entities"], "CTI varlık sayısı profil sınırını aşıyor; kapsamı bölün.")
            entity_ids = {row[0] for row in entity_rows}
            assertions_by_entity: dict[str, list[dict]] = {value: [] for value in entity_ids}
            assertion_limit = min(200_000, max(1, definition["max_entities"] * 50))
            assertion_rows = self._scoped_rows(connection,
                table="cti_entity_assertions", owner="entity_id",
                columns="id,entity_id,source_name,source_reference,confidence,aliases_json,description,last_seen_at",
                identifiers=entity_ids, maximum=assertion_limit,
                order="entity_id,source_name,source_reference,id",
                message="CTI varlık kaynak iddiası sayısı güvenli analiz sınırını aşıyor.")
            for row in assertion_rows:
                if row[1] in assertions_by_entity:
                    assertions_by_entity[row[1]].append(self._assertion(
                        (row[0], row[2], row[3], row[4], row[5], row[6], None, row[7]), aliases=True,
                    ))
            entities = [{"id": row[0], "entity_type": row[1], "display_name": row[2],
                         "assertions": assertions_by_entity[row[0]]} for row in entity_rows]

            relationship_rows = self._bounded(connection.execute(
                "SELECT DISTINCT r.id,r.source_entity_id,r.relationship_type,r.target_kind,"
                "r.target_entity_id,r.target_indicator_id FROM cti_relationships r "
                "JOIN cti_relationship_assertions a ON a.relationship_id=r.id AND a.active=1 "
                "ORDER BY r.source_entity_id,r.relationship_type,r.target_key,r.id LIMIT ?",
                (definition["max_relationships"] + 1,),
            ), definition["max_relationships"], "CTI ilişki sayısı profil sınırını aşıyor; kapsamı bölün.")
            relationship_rows = [row for row in relationship_rows if row[1] in entity_ids
                                 and (row[3] == "indicator" or row[4] in entity_ids)]
            relation_ids = {row[0] for row in relationship_rows}
            assertions_by_relation: dict[str, list[dict]] = {value: [] for value in relation_ids}
            relation_assertion_limit = min(500_000, max(1, definition["max_relationships"] * 50))
            relation_assertions = self._scoped_rows(connection,
                table="cti_relationship_assertions", owner="relationship_id",
                columns="id,relationship_id,source_name,source_reference,confidence,description,last_seen_at",
                identifiers=relation_ids, maximum=relation_assertion_limit,
                order="relationship_id,source_name,source_reference,id",
                message="CTI ilişki kaynak iddiası sayısı güvenli analiz sınırını aşıyor.")
            for row in relation_assertions:
                if row[1] in assertions_by_relation:
                    assertions_by_relation[row[1]].append(self._assertion(
                        (row[0], row[2], row[3], row[4], row[5], row[6]), aliases=False,
                    ))
            relationships = [{"id": row[0], "source_entity_id": row[1], "relationship_type": row[2],
                "target_kind": row[3], "target_id": row[4] if row[3] == "entity" else row[5],
                "assertions": assertions_by_relation[row[0]]} for row in relationship_rows]

            indicator_ids = sorted({row[5] for row in relationship_rows if row[3] == "indicator"})
            indicator_records = {}
            for start in range(0, len(indicator_ids), 500):
                batch = indicator_ids[start:start + 500]
                placeholders = ",".join("?" for _ in batch)
                records = connection.execute(
                    f"SELECT id,indicator_type,value FROM cti_indicators WHERE id IN ({placeholders}) ORDER BY id",
                    batch,
                ).fetchall() if batch else []
                indicator_records.update({row[0]: (row[1], row[2]) for row in records})
            if set(indicator_records) != set(indicator_ids):
                raise StorageError("CTI analiz ilişkisinin IOC hedefi bulunamadı.")
            assertions_by_indicator: dict[str, list[dict]] = {value: [] for value in indicator_ids}
            indicator_assertion_limit = min(500_000, max(1, len(indicator_ids) * 50))
            indicator_assertions = self._scoped_rows(connection,
                table="cti_indicator_assertions", owner="indicator_id",
                columns="id,indicator_id,source_name,source_reference,confidence,description,last_seen_at",
                identifiers=set(indicator_ids), maximum=indicator_assertion_limit,
                order="indicator_id,source_name,source_reference,id",
                message="IOC kaynak iddiası sayısı güvenli analiz sınırını aşıyor.")
            for row in indicator_assertions:
                values = assertions_by_indicator[row[1]]
                if len(values) >= 500:
                    raise CtiAnalysisError("scope_too_large", "Tek IOC için kaynak iddiası sınırı aşıldı.")
                values.append(self._assertion((row[0], row[2], row[3], row[4], row[5], row[6])))
            indicators = [{"id": identifier,
                "indicator_type": indicator_records[identifier][0],
                "value": indicator_records[identifier][1],
                "assertions": assertions_by_indicator[identifier]} for identifier in indicator_ids]

            latest = connection.execute(
                "SELECT id,version,content_sha256 FROM attack_catalog_runs ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            attack = {"run_id": None, "version": None, "content_sha256": None,
                      "entities": [], "relationships": [], "phases": []}
            if latest is not None:
                attack.update(run_id=latest[0], version=latest[1], content_sha256=latest[2])
                for kind, table, maximum in (
                    ("entity", "attack_catalog_entities", ATTACK_ENTITY_LIMIT),
                    ("relationship", "attack_catalog_relationships", ATTACK_RELATIONSHIP_LIMIT),
                    ("phase", "attack_catalog_phases", ATTACK_PHASE_LIMIT),
                ):
                    rows = connection.execute(
                        f"SELECT record_json FROM {table} WHERE active=1 ORDER BY "
                        + ("external_id" if kind == "entity" else "stix_id" if kind == "relationship" else "id")
                        + " LIMIT ?", (maximum + 1,),
                    ).fetchall()
                    if len(rows) > maximum:
                        raise CtiAnalysisError(
                            "scope_too_large",
                            "Yerel MITRE ATT&CK kataloğu güvenli CTI analiz sınırını aşıyor; "
                            "katalog kapsamını bölün.",
                        )
                    attack[kind + "s"] = [asdict(parse_record(kind, row[0])) for row in rows]

            snapshot = {
                "policy": "cti-analysis-v1", "captured_at": at,
                "profile_id": profile["profile"]["id"],
                "profile_revision": profile["profile"]["revision"],
                "definition": definition,
                "organization": {"id": organization[0], "display_name": organization[1], "domains": domains},
                "entities": entities, "relationships": relationships, "indicators": indicators,
                "attack": attack, "accepted_identity_links": accepted_identity_links,
            }
            # A canonical encode here rejects unexpected non-JSON values before reservation.
            json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
            return snapshot
