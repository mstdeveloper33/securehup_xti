"""Offline comparison of the latest independently stored ransomware snapshots."""

from xti.domain.assets import ValidationError
from xti.domain.ransomware_source_comparison import (
    RansomwareSourceComparison,
    RansomwareSourceComparisonEvidence,
    RansomwareSourceComparisonReport,
    compare_ransomware_source_claims,
    normalize_ransomware_source_comparison_id,
    ransomware_source_text_key,
)
from xti.ports.ransomlook_ransomware import RansomLookClaimRepository
from xti.ports.ransomware_claims import RansomwareClaimRepository


_MAX_CANDIDATE_REFERENCES = 100_000
_MAX_COMPARISONS = 50_000
_BASIS_ORDER = {
    "organization_group_time": 0,
    "organization_group": 1,
    "organization_time": 2,
}


class RansomwareSourceComparisonService:
    """Compare latest local snapshots without network access or persistence."""

    def __init__(
        self,
        threatcluster_repository: RansomwareClaimRepository,
        ransomlook_repository: RansomLookClaimRepository,
    ) -> None:
        self.threatcluster_repository = threatcluster_repository
        self.ransomlook_repository = ransomlook_repository

    @staticmethod
    def _limit(value: int) -> int:
        if type(value) is not int or not 1 <= value <= 500:
            raise ValidationError(
                "Kaynak karşılaştırma görünüm sınırı 1–500 arasında olmalı."
            )
        return value

    def _build(self):
        threatcluster = self.threatcluster_repository.latest_snapshot()
        ransomlook = self.ransomlook_repository.latest_snapshot()

        by_organization_group: dict[tuple[str, str], list] = {}
        by_organization_time: dict[tuple[str, str], list] = {}
        for claim in ransomlook.claims:
            organization = ransomware_source_text_key(claim.victim)
            group = ransomware_source_text_key(claim.group)
            by_organization_group.setdefault((organization, group), []).append(claim)
            by_organization_time.setdefault(
                (organization, claim.discovered_at), []
            ).append(claim)

        comparisons: list[RansomwareSourceComparison] = []
        seen_pairs: set[tuple[str, str]] = set()
        candidate_references = 0
        for claim in threatcluster.claims:
            organization = ransomware_source_text_key(claim.victim)
            group_candidates = by_organization_group.get(
                (organization, ransomware_source_text_key(claim.group)), ()
            )
            time_candidates = by_organization_time.get(
                (organization, claim.discovered_at), ()
            )
            candidate_references += len(group_candidates) + len(time_candidates)
            if candidate_references > _MAX_CANDIDATE_REFERENCES:
                raise ValidationError(
                    "Kaynak karşılaştırması güvenli aday sınırını aştı; "
                    "snapshot kapsamını küçültün."
                )
            for candidate in (*group_candidates, *time_candidates):
                pair = (claim.id, candidate.id)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                comparison = compare_ransomware_source_claims(claim, candidate)
                if comparison is None:
                    continue
                comparisons.append(comparison)
                if len(comparisons) > _MAX_COMPARISONS:
                    raise ValidationError(
                        "Kaynak karşılaştırması güvenli sonuç sınırını aştı; "
                        "snapshot kapsamını küçültün."
                    )

        comparisons.sort(key=lambda value: (
            _BASIS_ORDER[value.basis],
            ransomware_source_text_key(value.threatcluster_claim.victim),
            ransomware_source_text_key(value.threatcluster_claim.group),
            value.threatcluster_claim.discovered_at,
            value.threatcluster_claim.id,
            value.ransomlook_claim.id,
        ))
        return threatcluster, ransomlook, tuple(comparisons)

    def compare(self, *, limit: int = 100) -> RansomwareSourceComparisonReport:
        limit = self._limit(limit)
        threatcluster, ransomlook, comparisons = self._build()
        selected = tuple(comparisons[:limit])
        return RansomwareSourceComparisonReport(
            threatcluster_run=threatcluster.run,
            ransomlook_run=ransomlook.run,
            threatcluster_claim_count=len(threatcluster.claims),
            ransomlook_claim_count=len(ransomlook.claims),
            total_comparison_count=len(comparisons),
            displayed_count=len(selected),
            has_more=len(comparisons) > len(selected),
            comparisons=selected,
            notes=(
                "Karşılaştırma yalnız iki kaynağın son başarılı yerel snapshot'ını "
                "kullanır.",
                "Kuruluş adı tam normalleştirilmiş eşleşmeli; ayrıca grup adı veya "
                "kaynak keşif zamanı da aynı olmalıdır.",
                "Yaklaşık ad benzerliği, domain, ülke, sektör veya kaynakta bulunmayan "
                "başka alanlar kullanılmaz.",
                "Sonuçlar kaynak kayıtlarını birleştirmez, alarm üretmez ve doğrulanmış "
                "aynı olay ya da gerçekleşmiş ihlal kararı değildir.",
                "Komut internet kullanmaz ve yerel kayıtlara yazmaz.",
            ),
        )

    def find(self, comparison_id: str) -> RansomwareSourceComparisonEvidence:
        comparison_id = normalize_ransomware_source_comparison_id(comparison_id)
        threatcluster, ransomlook, comparisons = self._build()
        comparison = next(
            (value for value in comparisons if value.id == comparison_id), None,
        )
        if comparison is None:
            raise ValidationError(
                "Karşılaştırma son başarılı iki yerel snapshot içinde bulunamadı."
            )
        return RansomwareSourceComparisonEvidence(
            comparison=comparison,
            threatcluster_run_id=threatcluster.run.id,
            ransomlook_run_id=ransomlook.run.id,
        )
