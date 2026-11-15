"""Read audited source states and frozen review evidence in one SQLite snapshot."""

from pathlib import Path

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_public_notices import read_public_notice_snapshot
from xti.adapters.sqlite_ransomware_source_reviews import SQLiteRansomwareSourceReviewRepository
from xti.domain.event_candidates import (
    MAX_EVENT_RECORDS, EventCandidateSnapshot, EventLegacyReview, EventSourceSnapshot,
)
from xti.domain.ransomlook_ransomware import ransomlook_claim_state_sha256
from xti.domain.ransomware_claims import ransomware_claim_state_sha256


class SQLiteEventCandidateRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _source(source_key, runs, snapshots) -> EventSourceSnapshot:
        successful = next((run for run in reversed(runs) if run.status == "complete"), None)
        records = snapshots[successful.id] if successful is not None else {}
        return EventSourceSnapshot(
            source_key, runs[-1] if runs else None, successful,
            tuple(records[identifier] for identifier in sorted(records)),
        )

    def read(self) -> EventCandidateSnapshot:
        try:
            with self._storage._connection(readonly=True) as connection:
                connection.execute("BEGIN")
                notices = read_public_notice_snapshot(connection)
                (
                    threatcluster_runs, ransomlook_runs,
                    threatcluster_snapshots, ransomlook_snapshots,
                    evidences, _, by_comparison,
                ) = SQLiteRansomwareSourceReviewRepository._audit(connection, compact=True)
                sources = (
                    self._source("threatcluster", threatcluster_runs, threatcluster_snapshots),
                    self._source("ransomlook", ransomlook_runs, ransomlook_snapshots),
                    EventSourceSnapshot("hibp", notices.latest_run, notices.latest_complete_run,
                                        notices.notices),
                )
                if sum(len(source.records) for source in sources) > MAX_EVENT_RECORDS:
                    raise StorageError(
                        "Olay adayı kaynakları toplam güvenli kayıt sınırını aşıyor; "
                        "kısmi sonuç üretilmedi."
                    )
                reviews = tuple(
                    EventLegacyReview(
                        SQLiteRansomwareSourceReviewRepository._state(identifier, by_comparison[identifier]),
                        ransomware_claim_state_sha256(evidences[identifier].comparison.threatcluster_claim),
                        ransomlook_claim_state_sha256(evidences[identifier].comparison.ransomlook_claim),
                    )
                    for identifier in sorted(by_comparison)
                )
                return EventCandidateSnapshot(sources, reviews)
        except (TypeError, ValueError, KeyError, IndexError, AttributeError, OverflowError) as error:
            raise StorageError(
                "Olay adayı kaynak kayıtları veya karar kanıtları bozuk; kısmi sonuç üretilmedi."
            ) from error
