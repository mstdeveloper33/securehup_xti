"""Offline planning and bounded bulk checks for selected Ubuntu evidence."""

from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone

from xti.application.ubuntu_evidence_check import UbuntuEvidenceCheckService
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.ubuntu_evidence import (
    UbuntuEvidencePlanItem,
    UbuntuEvidencePlanReport,
    parse_ubuntu_evidence_reference,
    ubuntu_package_snapshot_sha256,
)
from xti.domain.ubuntu_evidence_check import UbuntuEvidenceScanReport
from xti.ports.osv_advisory import OsvAdvisorySource
from xti.ports.ubuntu_evidence import UbuntuExposureEvidenceRepository
from xti.ports.ubuntu_packages import UbuntuAssetPackageRepository
from xti.ports.vulnerability_exposures import VulnerabilityExposureRepository


class UbuntuEvidencePlanService:
    def __init__(
        self, evidence_repository: UbuntuExposureEvidenceRepository,
        exposure_repository: VulnerabilityExposureRepository,
        package_repository: UbuntuAssetPackageRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.evidence_repository = evidence_repository
        self.exposure_repository = exposure_repository
        self.package_repository = package_repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def plan(
        self, *, asset_value: str | None = None, limit: int = 50,
    ) -> UbuntuEvidencePlanReport:
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Ubuntu kanıt planı görünüm sınırı 1–500 arasında olmalı.")
        asset_value = normalize_domain(asset_value) if asset_value is not None else None
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("Ubuntu kanıt planı zamanı geçersiz.")
        checked_at = now.astimezone(timezone.utc).isoformat()
        records = self.evidence_repository.active_ubuntu_evidence(
            asset_value=asset_value,
        )
        items = []
        for evidence in records:
            stored = parse_ubuntu_evidence_reference(evidence.source_reference)
            package = self.package_repository.details(
                stored.package_id, event_limit=1,
            ).record
            exposure = self.exposure_repository.details(
                evidence.exposure_id, event_limit=1, checked_at=checked_at,
            ).view
            if (
                exposure.exposure.cve_id != stored.cve_id
                or exposure.product.asset_id != package.asset_id
            ):
                raise ValidationError(
                    "Ubuntu kanıtı maruziyetin CVE veya varlık bağıyla uyuşmuyor."
                )
            if not package.active:
                local_state = "package_inactive"
            elif ubuntu_package_snapshot_sha256(package) != stored.package_snapshot_sha256:
                local_state = "package_snapshot_changed"
            else:
                local_state = "local_current"
            items.append(UbuntuEvidencePlanItem(
                evidence=evidence, stored_reference=stored,
                package=package, local_state=local_state,
            ))
        priority = {
            "package_inactive": 0,
            "package_snapshot_changed": 1,
            "local_current": 2,
        }
        items.sort(key=lambda item: (
            priority[item.local_state], item.package.asset_value,
            item.stored_reference.cve_id, item.evidence.id,
        ))
        counts = Counter(item.local_state for item in items)
        return UbuntuEvidencePlanReport(
            asset_value=asset_value, total_active_evidence_count=len(items),
            displayed_count=min(len(items), limit),
            local_current_count=counts["local_current"],
            package_snapshot_changed_count=counts["package_snapshot_changed"],
            package_inactive_count=counts["package_inactive"],
            items=tuple(items[:limit]), truncated=len(items) > limit,
            notes=(
                "Plan yalnız yerel kanıtları okur; Canonical kaynağı çağrılmaz.",
                "Yerel olarak güncel görünmek, Canonical kaydının değişmediğini kanıtlamaz.",
            ),
        )


class _CachingOsvSource:
    def __init__(self, source: OsvAdvisorySource) -> None:
        self.source = source
        self.cache = {}
        self.request_count = 0

    def fetch(self, cve_id: str):
        if cve_id not in self.cache:
            self.cache[cve_id] = self.source.fetch(cve_id)
            self.request_count += 1
        return self.cache[cve_id]


class UbuntuEvidenceScanService:
    def __init__(
        self, evidence_repository: UbuntuExposureEvidenceRepository,
        exposure_repository: VulnerabilityExposureRepository,
        package_repository: UbuntuAssetPackageRepository,
        source: OsvAdvisorySource, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.evidence_repository = evidence_repository
        self.exposure_repository = exposure_repository
        self.package_repository = package_repository
        self.source = source
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def scan(
        self, *, asset_value: str | None = None, limit: int = 10,
    ) -> UbuntuEvidenceScanReport:
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValidationError("Ubuntu kanıt tarama sınırı 1–20 arasında olmalı.")
        plan = UbuntuEvidencePlanService(
            self.evidence_repository, self.exposure_repository,
            self.package_repository, clock=self.clock,
        ).plan(asset_value=asset_value, limit=limit)
        cached_source = _CachingOsvSource(self.source)
        checker = UbuntuEvidenceCheckService(
            self.evidence_repository, self.exposure_repository,
            self.package_repository, cached_source, clock=self.clock,
        )
        results = tuple(checker.check(item.evidence.id) for item in plan.items)
        current_count = sum(result.state == "current" for result in results)
        skipped = sum(not result.source_checked for result in results)
        return UbuntuEvidenceScanReport(
            plan=plan, selected_count=len(results),
            source_request_count=cached_source.request_count,
            current_count=current_count,
            changed_count=sum(
                result.source_checked and result.state != "current"
                for result in results
            ),
            skipped_source_count=skipped, results=results,
            truncated=plan.total_active_evidence_count > len(results),
            notes=(
                "Aynı CVE'ye bağlı seçili kanıtlar tek Canonical kaynak çağrısını paylaşır.",
                "Tarama salt okunurdur; değişen sonucu kalıcılaştırmak için açık insan seçimi gerekir.",
            ),
        )
