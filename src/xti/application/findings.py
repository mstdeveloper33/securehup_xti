"""Offline analysis and review use cases, independent of terminal and database."""

from dataclasses import replace
from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.findings import Finding, FindingDetails, ImportDocument, ImportSummary
from xti.domain.matching import DomainMatcher
from xti.ports.assets import AssetRepository
from xti.ports.allowlist import AllowlistRepository
from xti.ports.findings import FindingRepository


REVIEW_DECISIONS = frozenset({"suspicious", "dismissed", "uncertain"})
FINDING_STATUSES = REVIEW_DECISIONS | {"new"}
MAX_COMPARISONS = 250_000


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DomainImportService:
    def __init__(
        self, assets: AssetRepository, findings: FindingRepository, matcher: DomainMatcher,
        allowlist: AllowlistRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.assets = assets
        self.findings = findings
        self.matcher = matcher
        self.allowlist = allowlist
        self.clock = clock or _utc_now

    def _policy_time(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("İstisna değerlendirme zamanı saat dilimi bilgili olmalı.")
        return value.astimezone(timezone.utc).isoformat()

    def import_document(self, document: ImportDocument) -> ImportSummary:
        assets = self.assets.list()
        if not assets:
            raise ValidationError("Önce izlenecek bir adres ekle: ./xti assets add example.com")
        domains = sorted({record.domain for record in document.records})
        if len(domains) * len(assets) > MAX_COMPARISONS:
            raise ValidationError("Bu liste çok fazla karşılaştırma gerektiriyor; dosyayı küçült.")
        known_roots = set()
        for asset in assets:
            parts = self.matcher.resolver.parts(asset.value)
            if parts.registrable_domain is None:
                raise ValidationError(
                    "İzlenen kayıt yalnız bir alan adı uzantısı içeriyor; tam bir adres gerekli."
                )
            known_roots.add(parts.registrable_domain)
        candidates = []
        for domain in domains:
            parts = self.matcher.resolver.parts(domain)
            if parts.registrable_domain in known_roots:
                continue
            for asset in assets:
                candidate = self.matcher.match(asset, domain)
                if candidate is not None:
                    candidates.append(candidate)
        suppressed: set[tuple[str, str]] = set()
        if self.allowlist is not None and candidates:
            active = self.allowlist.active_pairs(
                tuple(item.asset_id for item in candidates), self._policy_time(),
            )
            kept = []
            for candidate in candidates:
                pair = (candidate.asset_id, candidate.domain)
                if pair in active:
                    suppressed.add(pair)
                else:
                    kept.append(candidate)
            candidates = kept
        # No write happens until the entire input and analysis have succeeded.
        summary = self.findings.save_import(document, candidates)
        return replace(
            summary,
            findings_suppressed=summary.findings_suppressed + len(suppressed),
        )


class FindingService:
    def __init__(self, repository: FindingRepository) -> None:
        self.repository = repository

    def list(self, status: str | None = None) -> list[Finding]:
        if status is not None and status not in FINDING_STATUSES:
            raise ValidationError("Geçersiz bulgu durumu.")
        return self.repository.list_findings(status)

    @staticmethod
    def _validate_id(finding_id: str) -> None:
        if not finding_id or len(finding_id) > 64 or not finding_id.isprintable():
            raise ValidationError("Geçerli bir bulgu kimliği gerekli.")

    def show(self, finding_id: str) -> FindingDetails:
        self._validate_id(finding_id)
        return self.repository.get_finding(finding_id)

    def review(self, finding_id: str, decision: str, reason: str) -> Finding:
        self._validate_id(finding_id)
        if decision not in REVIEW_DECISIONS:
            raise ValidationError("Karar suspicious, dismissed veya uncertain olmalı.")
        reason = reason.strip()
        if not reason or len(reason) > 1000 or not reason.isprintable():
            raise ValidationError("Karar gerekçesi 1–1000 görünür karakter içermeli.")
        return self.repository.review_finding(finding_id, decision, reason)

