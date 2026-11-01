"""Consistent SQLite snapshot of findings and append-only human reviews."""

from pathlib import Path

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.feedback import FeedbackSnapshot, RuleFeedback


_STATUSES = ("new", "suspicious", "dismissed", "uncertain")
_MAX_RULE_GROUPS = 100


class SQLiteFeedbackRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _valid_rule_version(value: object) -> bool:
        return (
            isinstance(value, str) and value == value.strip() and bool(value)
            and len(value) <= 512 and value.isprintable()
        )

    def snapshot(self) -> FeedbackSnapshot:
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            try:
                counts = dict.fromkeys(_STATUSES, 0)
                grouped: dict[str, dict[str, int]] = {}
                for rule_version, status, count in connection.execute(
                    "SELECT rule_version, status, COUNT(*) FROM findings "
                    "GROUP BY rule_version, status ORDER BY rule_version, status"
                ):
                    if (
                        not self._valid_rule_version(rule_version) or status not in counts
                        or type(count) is not int or count < 1
                    ):
                        raise StorageError("Geri bildirim kaydında geçersiz bulgu grubu var.")
                    current = grouped.setdefault(rule_version, dict.fromkeys(_STATUSES, 0))
                    current[status] = count
                    counts[status] += count
                if len(grouped) > _MAX_RULE_GROUPS:
                    raise StorageError("Geri bildirim için beklenenden fazla kural sürümü bulundu.")

                # The materialized finding status must equal the last append-only
                # review.  Otherwise a summary could hide corrupt history.
                inconsistent = connection.execute(
                    "SELECT COUNT(*) FROM findings f LEFT JOIN reviews r ON r.rowid = ("
                    "SELECT MAX(last.rowid) FROM reviews last WHERE last.finding_id = f.id) "
                    "WHERE (f.status = 'new' AND r.id IS NOT NULL) OR "
                    "(f.status != 'new' AND (r.id IS NULL OR r.decision != f.status))"
                ).fetchone()[0]
                if inconsistent:
                    raise StorageError("Bulgu durumu ile son inceleme kararı uyuşmuyor.")
                orphaned = connection.execute(
                    "SELECT COUNT(*) FROM reviews r LEFT JOIN findings f ON f.id = r.finding_id "
                    "WHERE f.id IS NULL"
                ).fetchone()[0]
                if orphaned:
                    raise StorageError("İnceleme geçmişinde bulgusuz karar kaydı var.")

                review_event_count = 0
                for decision, count in connection.execute(
                    "SELECT decision, COUNT(*) FROM reviews GROUP BY decision"
                ):
                    if decision not in counts or decision == "new" or type(count) is not int:
                        raise StorageError("İnceleme geçmişinde geçersiz karar kaydı var.")
                    review_event_count += count
                revisited = connection.execute(
                    "SELECT COUNT(*) FROM (SELECT finding_id FROM reviews "
                    "GROUP BY finding_id HAVING COUNT(*) > 1)"
                ).fetchone()[0]
                rules = tuple(
                    RuleFeedback(
                        rule_version=version,
                        total_findings=sum(rule_counts.values()),
                        reviewed_findings=sum(
                            rule_counts[name] for name in ("suspicious", "dismissed", "uncertain")
                        ),
                        unreviewed_findings=rule_counts["new"],
                        suspicious=rule_counts["suspicious"],
                        dismissed=rule_counts["dismissed"],
                        uncertain=rule_counts["uncertain"],
                    )
                    for version, rule_counts in sorted(grouped.items())
                )
            finally:
                connection.rollback()
        return FeedbackSnapshot(counts, review_event_count, revisited, rules)
