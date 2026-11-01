"""Strict read-only view of NVD CPE applicability statements."""

import json
from pathlib import Path
from uuid import UUID

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_nvd import SQLiteNvdRepository
from xti.domain.assets import ValidationError
from xti.domain.vulnerability import (
    NvdApplicabilityReport,
    NvdCpeApplicabilityMatch,
    normalize_cve_id,
)


MAX_CONFIGURATIONS = 2_000
MAX_NODES = 10_000
MAX_MATCHES = 20_000
MAX_CPE_LENGTH = 2_048


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite JSON number")


def _text(value: object, *, maximum: int, empty: bool = False) -> str:
    if (
        not isinstance(value, str) or len(value) > maximum
        or (not empty and not value)
        or any(not character.isprintable() for character in value)
    ):
        raise ValueError("Invalid applicability text")
    return value


def _optional_text(item: dict, field: str) -> str | None:
    if field not in item:
        return None
    return _text(item[field], maximum=255)


def _operator(item: dict, *, required: bool) -> str | None:
    if "operator" not in item:
        if required:
            raise ValueError("Missing applicability operator")
        return None
    value = item["operator"]
    if value not in {"AND", "OR"}:
        raise ValueError("Invalid applicability operator")
    return value


def _optional_bool(item: dict, field: str) -> bool | None:
    if field not in item:
        return None
    value = item[field]
    if type(value) is not bool:
        raise ValueError("Invalid applicability boolean")
    return value


def _uuid(value: object) -> str:
    text = _text(value, maximum=36)
    try:
        normalized = str(UUID(text)).upper()
    except (TypeError, ValueError, AttributeError) as error:
        raise ValueError("Invalid match criteria UUID") from error
    if text.upper() != normalized:
        raise ValueError("Non-canonical match criteria UUID")
    return normalized


def _cpe_components(value: object) -> tuple[str, ...]:
    criteria = _text(value, maximum=MAX_CPE_LENGTH)
    if any(ord(character) > 127 for character in criteria):
        raise ValueError("CPE must be ASCII")
    parts: list[str] = []
    current: list[str] = []
    escaped = False
    for character in criteria:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            parts.append("".join(current))
            current = []
        else:
            current.append(character)
    if escaped:
        raise ValueError("Incomplete CPE escape")
    parts.append("".join(current))
    if (
        len(parts) != 13 or parts[0] != "cpe" or parts[1] != "2.3"
        or parts[2] not in {"a", "h", "o"}
        or any(not part or len(part) > 255 for part in parts[2:])
    ):
        raise ValueError("Invalid CPE 2.3 formatted string")
    return tuple(parts)


def parse_nvd_applicability(
    record_json: str, *, cve_id: str, source_record_sha256: str, limit: int,
) -> NvdApplicabilityReport:
    try:
        raw = json.loads(record_json, object_pairs_hook=_object, parse_constant=_constant)
        configurations = raw.get("configurations", ())
        if not isinstance(configurations, (list, tuple)) or len(configurations) > MAX_CONFIGURATIONS:
            raise ValueError("Invalid configurations")
        matches: list[NvdCpeApplicabilityMatch] = []
        total_nodes = 0
        total_matches = 0
        vulnerable_count = 0
        environmental_count = 0
        for configuration_index, configuration in enumerate(configurations, start=1):
            if not isinstance(configuration, dict):
                raise ValueError("Invalid configuration")
            configuration_operator = _operator(configuration, required=False)
            configuration_negate = _optional_bool(configuration, "negate")
            nodes = configuration.get("nodes")
            if not isinstance(nodes, list):
                raise ValueError("Invalid configuration nodes")
            total_nodes += len(nodes)
            if total_nodes > MAX_NODES:
                raise ValueError("Too many applicability nodes")
            for node_index, node in enumerate(nodes, start=1):
                if not isinstance(node, dict):
                    raise ValueError("Invalid applicability node")
                node_operator = _operator(node, required=True)
                node_negate = _optional_bool(node, "negate")
                cpe_matches = node.get("cpeMatch")
                if not isinstance(cpe_matches, list):
                    raise ValueError("Invalid CPE match list")
                total_matches += len(cpe_matches)
                if total_matches > MAX_MATCHES:
                    raise ValueError("Too many CPE matches")
                for match_index, item in enumerate(cpe_matches, start=1):
                    if not isinstance(item, dict) or type(item.get("vulnerable")) is not bool:
                        raise ValueError("Invalid CPE match")
                    components = _cpe_components(item.get("criteria"))
                    start_including = _optional_text(item, "versionStartIncluding")
                    start_excluding = _optional_text(item, "versionStartExcluding")
                    end_including = _optional_text(item, "versionEndIncluding")
                    end_excluding = _optional_text(item, "versionEndExcluding")
                    if (
                        start_including is not None and start_excluding is not None
                    ) or (end_including is not None and end_excluding is not None):
                        raise ValueError("Conflicting CPE version bounds")
                    vulnerable = item["vulnerable"]
                    vulnerable_count += int(vulnerable)
                    environmental_count += int(not vulnerable)
                    if len(matches) < limit:
                        matches.append(NvdCpeApplicabilityMatch(
                            configuration_index=configuration_index,
                            node_index=node_index,
                            match_index=match_index,
                            configuration_operator=configuration_operator,
                            configuration_negate=configuration_negate,
                            node_operator=node_operator,
                            node_negate=node_negate,
                            vulnerable=vulnerable,
                            match_criteria_id=_uuid(item.get("matchCriteriaId")),
                            criteria=item["criteria"],
                            part=components[2],
                            vendor=components[3],
                            product=components[4],
                            version=components[5],
                            version_start_including=start_including,
                            version_start_excluding=start_excluding,
                            version_end_including=end_including,
                            version_end_excluding=end_excluding,
                        ))
        return NvdApplicabilityReport(
            cve_id=cve_id,
            source_record_sha256=source_record_sha256,
            total_match_count=total_matches,
            vulnerable_match_count=vulnerable_count,
            environmental_match_count=environmental_count,
            matches=tuple(matches),
            truncated=total_matches > len(matches),
        )
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise StorageError(
            "NVD ürün uygulanabilirlik kanıtı bozuk; görünüm durduruldu."
        ) from error


class SQLiteNvdApplicabilityRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    def show(self, cve_id: str, *, limit: int) -> NvdApplicabilityReport:
        cve_id = normalize_cve_id(cve_id)
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("NVD ürün koşulu sınırı 1–500 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            row = connection.execute(
                "SELECT cve_id, state, record_json, state_sha256, first_seen_at, "
                "last_seen_at, updated_at, latest_run_id FROM nvd_cve_records "
                "WHERE cve_id = ?", (cve_id,),
            ).fetchone()
        if row is None:
            raise ValidationError(
                "CVE, yerel NVD kaydında bulunamadı. Önce NVD eşitlemesi yapın."
            )
        stored = SQLiteNvdRepository._stored(row)
        return parse_nvd_applicability(
            row[2], cve_id=cve_id, source_record_sha256=stored.state_sha256, limit=limit,
        )
