"""Read-only, bounded selection of local CVEs missing NVD context."""

from pathlib import Path

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_epss import SQLiteEpssRepository
from xti.adapters.sqlite_vulnerability import SQLiteKevRepository
from xti.domain.vulnerability import (
    NvdEnrichmentCandidate,
    NvdEnrichmentPlan,
    normalize_probability,
)


_KEV_COLUMNS = (
    "cve_id, state, state_sha256, active, first_seen_at, last_seen_at, "
    "updated_at, latest_run_id"
)
_EPSS_COLUMNS = (
    "cve_id, epss, percentile, state_sha256, active, model_version, score_date, "
    "first_seen_at, last_seen_at, updated_at, latest_run_id"
)
_EPSS_KEY_SQL = (
    "CASE e.epss WHEN '1' THEN '1000000000000000000' "
    "WHEN '0' THEN '0000000000000000000' ELSE '0' || "
    "substr(substr(e.epss, 3) || '000000000000000000', 1, 18) END"
)


def _probability_key(value: str) -> str:
    normalized = normalize_probability(value, field="plan eşiği")
    if normalized != value:
        raise ValueError("Non-canonical probability threshold")
    if normalized == "1":
        return "1" + "0" * 18
    if normalized == "0":
        return "0" * 19
    return "0" + normalized[2:].ljust(18, "0")


class SQLiteNvdEnrichmentPlanRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    def plan(self, *, min_epss: str, limit: int) -> NvdEnrichmentPlan:
        threshold_key = _probability_key(min_epss)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            missing_kev = connection.execute(
                "SELECT COUNT(*) FROM kev_entries AS k WHERE k.active = 1 AND NOT EXISTS "
                "(SELECT 1 FROM nvd_cve_records AS n WHERE n.cve_id = k.cve_id)"
            ).fetchone()[0]
            missing_epss = connection.execute(
                "SELECT COUNT(*) FROM epss_scores AS e WHERE e.active = 1 "
                f"AND {_EPSS_KEY_SQL} >= ? AND NOT EXISTS "
                "(SELECT 1 FROM nvd_cve_records AS n WHERE n.cve_id = e.cve_id)",
                (threshold_key,),
            ).fetchone()[0]
            eligible = connection.execute(
                "SELECT COUNT(*) FROM ("
                "SELECT k.cve_id FROM kev_entries AS k WHERE k.active = 1 AND NOT EXISTS "
                "(SELECT 1 FROM nvd_cve_records AS n WHERE n.cve_id = k.cve_id) UNION "
                "SELECT e.cve_id FROM epss_scores AS e WHERE e.active = 1 "
                f"AND {_EPSS_KEY_SQL} >= ? AND NOT EXISTS "
                "(SELECT 1 FROM nvd_cve_records AS n WHERE n.cve_id = e.cve_id))",
                (threshold_key,),
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT candidates.cve_id FROM ("
                "SELECT k.cve_id FROM kev_entries AS k WHERE k.active = 1 AND NOT EXISTS "
                "(SELECT 1 FROM nvd_cve_records AS n WHERE n.cve_id = k.cve_id) UNION "
                "SELECT e.cve_id FROM epss_scores AS e WHERE e.active = 1 "
                f"AND {_EPSS_KEY_SQL} >= ? AND NOT EXISTS "
                "(SELECT 1 FROM nvd_cve_records AS n WHERE n.cve_id = e.cve_id)) candidates "
                "LEFT JOIN kev_entries AS k ON k.cve_id = candidates.cve_id AND k.active = 1 "
                "LEFT JOIN epss_scores AS e ON e.cve_id = candidates.cve_id AND e.active = 1 "
                f"ORDER BY (k.cve_id IS NOT NULL) DESC, {_EPSS_KEY_SQL} "
                "DESC, candidates.cve_id LIMIT ?",
                (threshold_key, limit),
            ).fetchall()

            candidates: list[NvdEnrichmentCandidate] = []
            for row in rows:
                cve_id = row[0]
                kev_row = connection.execute(
                    f"SELECT {_KEV_COLUMNS} FROM kev_entries WHERE cve_id = ? AND active = 1",
                    (cve_id,),
                ).fetchone()
                epss_row = connection.execute(
                    f"SELECT {_EPSS_COLUMNS} FROM epss_scores WHERE cve_id = ? AND active = 1",
                    (cve_id,),
                ).fetchone()
                kev = SQLiteKevRepository._stored(kev_row) if kev_row is not None else None
                epss = SQLiteEpssRepository._stored(epss_row) if epss_row is not None else None
                high_epss = epss is not None and _probability_key(epss.score.epss) >= threshold_key
                reasons = (
                    *(("active_kev",) if kev is not None else ()),
                    *(("epss_at_or_above_threshold",) if high_epss else ()),
                )
                candidates.append(NvdEnrichmentCandidate(
                    cve_id=cve_id,
                    active_kev=kev is not None,
                    kev_date_added=kev.entry.date_added if kev is not None else None,
                    epss=epss.score.epss if epss is not None else None,
                    epss_percentile=epss.score.percentile if epss is not None else None,
                    epss_score_date=epss.score_date if epss is not None else None,
                    selection_reasons=reasons,
                ))
            connection.rollback()

        return NvdEnrichmentPlan(
            min_epss=min_epss,
            limit=limit,
            eligible_count=eligible,
            missing_active_kev_count=missing_kev,
            missing_high_epss_count=missing_epss,
            candidates=tuple(candidates),
        )
