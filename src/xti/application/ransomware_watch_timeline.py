"""Offline claim timeline for one current organization/domain watch definition."""

from xti.domain.assets import ValidationError
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.ransomware_watches import (
    RansomwareWatchTimelineEvent,
    RansomwareWatchTimelineReport,
    match_ransomware_claim,
)
from xti.ports.ransomware_claims import RansomwareClaimRepository
from xti.ports.ransomware_watches import RansomwareWatchRepository


class RansomwareWatchTimelineService:
    def __init__(
        self,
        watch_repository: RansomwareWatchRepository,
        claim_repository: RansomwareClaimRepository,
    ) -> None:
        self.watch_repository = watch_repository
        self.claim_repository = claim_repository

    @staticmethod
    def _limit(value: int) -> int:
        if type(value) is not int or not 1 <= value <= 500:
            raise ValidationError("Zaman çizelgesi olay sınırı 1–500 arasında olmalı.")
        return value

    def show(
        self, watch_id: str, *, event_limit: int = 100,
    ) -> RansomwareWatchTimelineReport:
        watch_id = normalize_knowledge_id(
            watch_id, field="ransomware izleme kimliği",
        )
        event_limit = self._limit(event_limit)
        watch = self.watch_repository.details(
            watch_id, event_limit=1, run_limit=1,
        ).watch
        history = self.claim_repository.history()
        by_run = {run.id: [] for run in history.runs}
        for item in history.items:
            by_run[item.run_id].append(item)

        current = {}
        current_matches = {}
        ever_matched: set[str] = set()
        events: list[RansomwareWatchTimelineEvent] = []
        repeat_observations = 0
        complete_runs = []
        failed_run_count = 0

        def matched(claim):
            return match_ransomware_claim(
                claim, kind=watch.kind, query_key=watch.query_key,
                match_mode=watch.match_mode,
            )

        def append_event(run, action, claim, match) -> None:
            events.append(RansomwareWatchTimelineEvent(
                source_sequence=run.sequence,
                source_run_id=run.id,
                observed_at=run.finished_at,
                action=action,
                claim=claim,
                matched_field=match.matched_field,
                matched_value=match.matched_value,
                match_type=match.match_type,
            ))

        for run in history.runs:
            if run.status == "failed":
                failed_run_count += 1
                continue
            complete_runs.append(run)
            touched: set[str] = set()
            for item in by_run[run.id]:
                claim_id = item.claim.id
                touched.add(claim_id)
                old_claim = current.get(claim_id)
                old_match = current_matches.get(claim_id)
                if item.action == "added":
                    current[claim_id] = item.claim
                    new_match = matched(item.claim)
                    if new_match is not None:
                        action = "reappeared" if claim_id in ever_matched else "first_seen"
                        append_event(run, action, item.claim, new_match)
                        ever_matched.add(claim_id)
                        current_matches[claim_id] = new_match
                elif item.action == "updated":
                    current[claim_id] = item.claim
                    new_match = matched(item.claim)
                    if old_match is not None and new_match is not None:
                        append_event(run, "updated", item.claim, new_match)
                        current_matches[claim_id] = new_match
                    elif old_match is not None:
                        append_event(run, "match_ended", item.claim, old_match)
                        current_matches.pop(claim_id, None)
                    elif new_match is not None:
                        append_event(run, "match_started", item.claim, new_match)
                        ever_matched.add(claim_id)
                        current_matches[claim_id] = new_match
                elif item.action == "removed":
                    if old_match is not None:
                        append_event(run, "removed", old_claim, old_match)
                    current.pop(claim_id, None)
                    current_matches.pop(claim_id, None)
            repeat_observations += len(current_matches) - sum(
                claim_id in current_matches for claim_id in touched
            )

        selected = tuple(events[-event_limit:])
        return RansomwareWatchTimelineReport(
            watch=watch,
            complete_source_run_count=len(complete_runs),
            failed_source_run_count=failed_run_count,
            first_complete_at=complete_runs[0].finished_at if complete_runs else None,
            last_complete_at=complete_runs[-1].finished_at if complete_runs else None,
            distinct_claim_count=len(ever_matched),
            active_claim_count=len(current_matches),
            repeat_observation_count=repeat_observations,
            reappearance_count=sum(item.action == "reappeared" for item in events),
            total_event_count=len(events), events=selected,
            notes=(
                "Zaman çizelgesi güncel izleme tanımını kayıtlı kaynak geçmişine uygular.",
                "Aynı grup, kuruluş ve kaynak keşif zamanına sahip iddia aynı kimliktir; "
                "değişmeden yeniden görülmesi yeni olay değildir.",
                "Kaynak grup, kuruluş veya keşif zamanını değiştirirse aynı gerçek olay "
                "ayrı kimlik gibi görünebilir; otomatik birleştirme yapılmaz.",
                "Pencereden çıkan aynı kimliğin geri gelmesi yeni iddia değil, yeniden "
                "görünme olayıdır.",
                "Kapsam yalnız yerelde saklanan snapshot dönemidir; daha eski kaynak "
                "geçmişinin yokluğunu kanıtlamaz.",
                "Kaynak penceresinden çıkış, iddianın yanlışlandığını veya olayın "
                "çözüldüğünü kanıtlamaz.",
                "Kayıtlar doğrulanmış ihlal değil, kamuya açık grup iddialarıdır.",
            ),
        )
