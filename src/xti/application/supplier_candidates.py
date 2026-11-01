"""Local-only supplier suggestions from stored, validated dependency evidence."""

from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.matching import DomainResolver
from xti.domain.supplier_candidates import (
    SupplierCandidate,
    SupplierCandidateDetails,
    SupplierCandidateMutation,
    SupplierCandidateProposal,
    SupplierCandidateRefresh,
    normalize_candidate_id,
    normalize_candidate_status,
    normalize_resolution_reason,
    validate_observation,
)
from xti.domain.suppliers import normalize_supplier_id
from xti.ports.supplier_candidates import (
    SupplierCandidateRepository,
    SupplierDependencySource,
)


class SupplierCandidateService:
    def __init__(
        self, source: SupplierDependencySource,
        repository: SupplierCandidateRepository,
        resolver: DomainResolver, *, clock=None,
    ) -> None:
        self.source = source
        self.repository = repository
        self.resolver = resolver
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Tedarikçi adayı kayıt zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    def refresh(self, *, limit: int = 1000) -> SupplierCandidateRefresh:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValidationError("CNAME kanıt sınırı 1–1000 arasında olmalı.")
        observations = self.source.latest(limit=limit)
        proposals = []
        seen: set[tuple[str, str, str]] = set()
        version = getattr(self.resolver, "version", None)
        digest = getattr(self.resolver, "sha256", None)
        if not isinstance(version, str) or not isinstance(digest, str):
            raise ValidationError("Public Suffix List profili doğrulanamadı.")
        for observation in observations:
            validate_observation(observation)
            if observation.target_domain is None:
                continue
            source_parts = self.resolver.parts(observation.source_domain)
            target_parts = self.resolver.parts(observation.target_domain)
            if (
                source_parts.registrable_domain is None
                or target_parts.registrable_domain is None
                or source_parts.registrable_domain == target_parts.registrable_domain
            ):
                continue
            key = (
                observation.source_evidence_id,
                target_parts.registrable_domain,
                digest,
            )
            if key in seen:
                raise ValidationError("Aynı CNAME kanıtı birden fazla aday üretti.")
            seen.add(key)
            proposals.append(SupplierCandidateProposal(
                source_evidence_id=observation.source_evidence_id,
                asset_id=observation.asset_id,
                asset_value=observation.source_domain,
                target_domain=observation.target_domain,
                candidate_domain=target_parts.registrable_domain,
                state_sha256=observation.state_sha256,
                public_suffix_version=version,
                public_suffix_sha256=digest,
                observed_at=observation.observed_at,
            ))
        return self.repository.refresh(
            tuple(proposals), observation_count=len(observations), recorded_at=self._now(),
        )

    def list(
        self, *, status: str | None = "pending", current_only: bool = True,
        limit: int = 100,
    ) -> tuple[SupplierCandidate, ...]:
        if status is not None:
            status = normalize_candidate_status(status)
        if type(current_only) is not bool:
            raise ValidationError("Tedarikçi adayı güncellik filtresi geçersiz.")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Tedarikçi adayı liste sınırı 1–500 arasında olmalı.")
        return self.repository.list(status=status, current_only=current_only, limit=limit)

    def show(
        self, candidate_id: str, *, evidence_limit: int = 20,
        resolution_limit: int = 20,
    ) -> SupplierCandidateDetails:
        if type(evidence_limit) is not int or not 1 <= evidence_limit <= 100:
            raise ValidationError("Aday kanıt sınırı 1–100 arasında olmalı.")
        if type(resolution_limit) is not int or not 1 <= resolution_limit <= 100:
            raise ValidationError("Aday karar geçmişi sınırı 1–100 arasında olmalı.")
        return self.repository.show(
            normalize_candidate_id(candidate_id), evidence_limit=evidence_limit,
            resolution_limit=resolution_limit,
        )

    def review(
        self, candidate_id: str, *, decision: str, supplier_id: str | None,
        reason: str,
    ) -> SupplierCandidateMutation:
        decision = normalize_candidate_status(decision)
        if decision == "accepted":
            if supplier_id is None:
                raise ValidationError("Kabul kararı için --supplier gerekli.")
            supplier_id = normalize_supplier_id(supplier_id)
        elif supplier_id is not None:
            raise ValidationError("--supplier yalnız accepted kararıyla kullanılabilir.")
        return self.repository.review(
            normalize_candidate_id(candidate_id), decision=decision,
            supplier_id=supplier_id, reason=normalize_resolution_reason(reason),
            recorded_at=self._now(),
        )
