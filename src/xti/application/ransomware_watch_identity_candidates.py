"""Conservative offline identity-change candidates for ransomware claims."""

from dataclasses import dataclass
import unicodedata

from xti.domain.assets import ValidationError
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.ransomware_claims import RansomwareClaim
from xti.domain.ransomware_watches import (
    RansomwareWatchIdentityCandidate,
    RansomwareWatchIdentityCandidateReport,
    match_ransomware_claim,
    ransomware_claim_website_host,
    ransomware_identity_candidate_id,
)
from xti.ports.ransomware_claims import RansomwareClaimRepository
from xti.ports.ransomware_watches import RansomwareWatchRepository


_EVIDENCE_ORDER = ("group", "victim", "discovered_at", "website")
_IDENTITY_FIELDS = ("group", "victim", "discovered_at")


def _text_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _values(claim: RansomwareClaim) -> dict[str, str | None]:
    return {
        "group": _text_key(claim.group),
        "victim": _text_key(claim.victim),
        "discovered_at": claim.discovered_at,
        "website": ransomware_claim_website_host(claim.website),
    }


def _anchor_keys(claim: RansomwareClaim) -> tuple[tuple[str, str, str], ...]:
    values = _values(claim)
    result = [
        ("group-victim", values["group"], values["victim"]),
        ("group-discovered", values["group"], values["discovered_at"]),
        ("victim-discovered", values["victim"], values["discovered_at"]),
    ]
    website = values["website"]
    if website is not None:
        result.extend([
            ("website-group", website, values["group"]),
            ("website-victim", website, values["victim"]),
            ("website-discovered", website, values["discovered_at"]),
        ])
    return tuple(result)


def _comparison(
    older: RansomwareClaim, newer: RansomwareClaim,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    old_values, new_values = _values(older), _values(newer)
    common = tuple(
        field for field in _EVIDENCE_ORDER
        if old_values[field] is not None and old_values[field] == new_values[field]
    )
    changed = tuple(
        field for field in _IDENTITY_FIELDS
        if old_values[field] != new_values[field]
    )
    return common, changed


@dataclass(frozen=True, slots=True)
class _RetiredClaim:
    claim: RansomwareClaim
    complete_ordinal: int


class RansomwareWatchIdentityCandidateService:
    """Find explainable hand-offs without merging or changing claim identities."""

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
            raise ValidationError("Kimlik değişimi aday sınırı 1–500 arasında olmalı.")
        return value

    def show(
        self, watch_id: str, *, candidate_limit: int | None = 100,
    ) -> RansomwareWatchIdentityCandidateReport:
        watch_id = normalize_knowledge_id(
            watch_id, field="ransomware izleme kimliği",
        )
        if candidate_limit is not None:
            candidate_limit = self._limit(candidate_limit)
        watch = self.watch_repository.details(
            watch_id, event_limit=1, run_limit=1,
        ).watch
        history = self.claim_repository.history()
        by_run = {run.id: [] for run in history.runs}
        for item in history.items:
            by_run[item.run_id].append(item)

        retired_by_id: dict[str, _RetiredClaim] = {}
        retired_by_key: dict[tuple[str, str, str], dict[str, _RetiredClaim]] = {}
        retired_by_ordinal: dict[int, set[str]] = {}
        seen_pairs: set[tuple[str, str]] = set()
        candidates: list[RansomwareWatchIdentityCandidate] = []
        transition_pair_count = 0
        complete_ordinal = 0
        complete_count = 0
        failed_count = 0

        def watch_match(claim: RansomwareClaim) -> bool:
            return match_ransomware_claim(
                claim, kind=watch.kind, query_key=watch.query_key,
                match_mode=watch.match_mode,
            ) is not None

        def expire_before(minimum_ordinal: int) -> None:
            for ordinal in tuple(retired_by_ordinal):
                if ordinal >= minimum_ordinal:
                    continue
                for claim_id in retired_by_ordinal.pop(ordinal):
                    retired = retired_by_id.pop(claim_id, None)
                    if retired is None:
                        continue
                    for key in _anchor_keys(retired.claim):
                        bucket = retired_by_key.get(key)
                        if bucket is None:
                            continue
                        bucket.pop(claim_id, None)
                        if not bucket:
                            retired_by_key.pop(key, None)

        def retire(claim: RansomwareClaim) -> None:
            retired = _RetiredClaim(claim, complete_ordinal)
            retired_by_id[claim.id] = retired
            retired_by_ordinal.setdefault(complete_ordinal, set()).add(claim.id)
            for key in _anchor_keys(claim):
                retired_by_key.setdefault(key, {})[claim.id] = retired

        def unretire(claim_id: str) -> None:
            retired = retired_by_id.pop(claim_id, None)
            if retired is None:
                return
            ordinal_ids = retired_by_ordinal.get(retired.complete_ordinal)
            if ordinal_ids is not None:
                ordinal_ids.discard(claim_id)
                if not ordinal_ids:
                    retired_by_ordinal.pop(retired.complete_ordinal, None)
            for key in _anchor_keys(retired.claim):
                bucket = retired_by_key.get(key)
                if bucket is None:
                    continue
                bucket.pop(claim_id, None)
                if not bucket:
                    retired_by_key.pop(key, None)

        for run in history.runs:
            if run.status == "failed":
                failed_count += 1
                continue
            complete_count += 1
            complete_ordinal += 1
            expire_before(complete_ordinal - 1)
            items = by_run[run.id]
            for item in items:
                if item.action == "removed":
                    retire(item.claim)
            for item in items:
                if item.action != "added":
                    continue
                unretire(item.claim.id)
                possible: dict[str, _RetiredClaim] = {}
                for key in _anchor_keys(item.claim):
                    possible.update(retired_by_key.get(key, {}))
                if possible:
                    newest_retirement = max(
                        value.complete_ordinal for value in possible.values()
                    )
                    possible = {
                        claim_id: value for claim_id, value in possible.items()
                        if value.complete_ordinal == newest_retirement
                    }
                for older_id in sorted(possible):
                    older = possible[older_id]
                    if older.claim.id == item.claim.id:
                        continue
                    pair = (older.claim.id, item.claim.id)
                    if pair in seen_pairs:
                        continue
                    transition_pair_count += 1
                    older_matches = watch_match(older.claim)
                    newer_matches = watch_match(item.claim)
                    if not (older_matches or newer_matches):
                        continue
                    common, changed = _comparison(older.claim, item.claim)
                    if not changed:
                        continue
                    seen_pairs.add(pair)
                    candidates.append(RansomwareWatchIdentityCandidate(
                        id=ransomware_identity_candidate_id(
                            watch_id=watch.id,
                            older_claim_id=older.claim.id,
                            newer_claim_id=item.claim.id,
                            transition_source_run_id=run.id,
                        ),
                        older_claim=older.claim,
                        newer_claim=item.claim,
                        transition_source_sequence=run.sequence,
                        transition_source_run_id=run.id,
                        transition_observed_at=run.finished_at,
                        successful_snapshot_gap=(
                            complete_ordinal - older.complete_ordinal
                        ),
                        older_matches_watch=older_matches,
                        newer_matches_watch=newer_matches,
                        common_evidence=common,
                        changed_identity_fields=changed,
                    ))

        return RansomwareWatchIdentityCandidateReport(
            watch=watch,
            complete_source_run_count=complete_count,
            failed_source_run_count=failed_count,
            transition_pair_count=transition_pair_count,
            total_candidate_count=len(candidates),
            candidates=tuple(
                candidates if candidate_limit is None else candidates[-candidate_limit:]
            ),
            notes=(
                "Adaylar yalnız eski kimlik kaybolurken yeni kimlik aynı veya hemen "
                "sonraki başarılı snapshot'ta belirdiğinde aranır.",
                "En az iki açıklanabilir ortak alan gerekir: grup, kuruluş, kaynak "
                "keşif zamanı veya normalleştirilmiş web alanı.",
                "Birden fazla eski kayıt uyuyorsa yalnız en yakın başarılı snapshot'ta "
                "kaybolan kimlikler adaylaştırılır.",
                "Başarısız kaynak çalışmaları geçiş aralığını büyütmez ve boş "
                "snapshot sayılmaz.",
                "Aday göstermek kayıtları birleştirmez, izleme sonucunu değiştirmez "
                "ve doğrulanmış aynı olay kararı değildir.",
                "Kapsam yalnız denetlenmiş yerel snapshot geçmişidir.",
            ),
        )

    def find(
        self, watch_id: str, candidate_id: str,
    ) -> RansomwareWatchIdentityCandidate:
        watch_id = normalize_knowledge_id(
            watch_id, field="ransomware izleme kimliği",
        )
        candidate_id = normalize_knowledge_id(
            candidate_id, field="ransomware kimlik adayı kimliği",
        )
        report = self.show(watch_id, candidate_limit=None)
        for candidate in report.candidates:
            if candidate.id == candidate_id:
                return candidate
        raise ValidationError(
            "Kimlik adayı bu izlemenin denetlenmiş yerel geçmişinde bulunamadı."
        )
