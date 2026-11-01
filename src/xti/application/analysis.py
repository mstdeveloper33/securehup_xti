"""Compose existing stored evidence into one user-facing external-risk report."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
import ipaddress

from xti.application.surface import SurfaceOverviewService
from xti.application.cti_feeds import CtiFeedService
from xti.application.surface_discovery_status import SurfaceDiscoveryStatusService
from xti.application.surface_exposure import SurfaceExposureService
from xti.application.surface_freshness import SurfaceFreshnessService
from xti.domain.analysis import (
    AnalysisFindingSample,
    AnalysisFindingSummary,
    AnalysisIocMatch,
    UnifiedAnalysisReport,
    UnifiedAnalysisRefreshResult,
)
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_indicator_value
from xti.ports.cti_indicators import CtiIndicatorRepository
from xti.ports.findings import FindingRepository


class UnifiedAnalysisService:
    """Read already stored evidence; never start collection or infer products/CVEs."""

    def __init__(
        self,
        overview: SurfaceOverviewService,
        freshness: SurfaceFreshnessService,
        discovery: SurfaceDiscoveryStatusService,
        exposures: SurfaceExposureService,
        findings: FindingRepository,
        indicators: CtiIndicatorRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.overview = overview
        self.freshness = freshness
        self.discovery = discovery
        self.exposures = exposures
        self.findings = findings
        self.indicators = indicators
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Birleşik analiz zamanı geçersiz.")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _finding_summary(asset_id: str, repository: FindingRepository, limit: int):
        records = [item for item in repository.list_findings(None) if item.asset_id == asset_id]
        priority = {"suspicious": 0, "new": 1, "uncertain": 2, "dismissed": 3}
        records.sort(key=lambda item: (priority[item.status], item.domain, item.id))
        selected = records[:limit]
        summary = AnalysisFindingSummary(
            total=len(records),
            new=sum(item.status == "new" for item in records),
            suspicious=sum(item.status == "suspicious" for item in records),
            uncertain=sum(item.status == "uncertain" for item in records),
            dismissed=sum(item.status == "dismissed" for item in records),
            samples=tuple(AnalysisFindingSample(
                item.id, item.domain, item.status, item.reasons, item.last_seen_at,
            ) for item in selected),
            has_more=len(records) > len(selected),
        )
        # IOC scope is independent from the display limit: every stored brand candidate
        # for this asset is checked, including reviewed records.
        return summary, tuple(item.domain for item in records)

    @staticmethod
    def _ioc_targets(
        overview, finding_domains: tuple[str, ...],
    ) -> tuple[tuple[str, str], ...]:
        targets: list[tuple[str, str]] = [("domain", overview.asset_value)]
        targets.extend(("domain", value) for value in finding_domains)
        check = overview.latest_check
        if check is not None:
            for value in check.result.addresses:
                address = ipaddress.ip_address(value)
                targets.append(("ipv4" if address.version == 4 else "ipv6", address.compressed))
        service = overview.latest_service_check
        if service is not None and service.result.checked_address is not None:
            address = ipaddress.ip_address(service.result.checked_address)
            targets.append(("ipv4" if address.version == 4 else "ipv6", address.compressed))
        return tuple(dict.fromkeys(targets))

    @staticmethod
    def _next_steps(report) -> tuple[str, ...]:
        domain = report.overview.asset_value
        steps: list[str] = []
        if report.discovery.outcome == "never" or report.discovery.freshness != "current":
            steps.append(f"Pasif alt alan adı keşfini yenile: ./xti surface discover {domain}")
        if report.freshness.scope_status != "active":
            steps.append(
                f"Yetkin varsa aktif kapsamı aç: ./xti surface approve {domain} --reason \"Yetkili adresim\""
            )
        else:
            by_type = {item.check_type: item for item in report.freshness.items}
            if by_type["web"].freshness != "current":
                steps.append(f"Web kanıtını yenile: ./xti surface check {domain}")
            if by_type["mail"].freshness != "current":
                steps.append(f"E-posta DNS kanıtını yenile: ./xti surface mail check {domain}")
            if by_type["services"].freshness != "current":
                steps.append(
                    "Port kontrolü isteğe bağlıdır; yalnız sana ait, DNS ile eşleşen kesin genel IP ile çalıştır."
                )
        if report.ioc_catalog_status == "empty":
            steps.append(
                "IOC kataloğu boş; domain listesi için ./xti ioc sync --source certpl, "
                "C2 IP listesi için ./xti ioc sync --source feodo kullan."
            )
        if report.findings.new or report.findings.suspicious or report.findings.uncertain:
            steps.append("Açık marka adaylarını incele: ./xti triage")
        return tuple(steps) or ("Kayıtlı kanıtlar güncel; açık bir sonraki adım yok.",)

    def show(
        self, asset_value: str, *, stale_after_hours: int = 24,
        finding_limit: int = 10,
    ) -> UnifiedAnalysisReport:
        if type(finding_limit) is not int or not 1 <= finding_limit <= 50:
            raise ValidationError("Birleşik analiz bulgu sınırı 1–50 arasında olmalı.")
        now = self._now()
        overview = self.overview.show(asset_value, candidate_limit=20)
        freshness = self.freshness.show(
            overview.asset_value, freshness_hours=stale_after_hours,
        )
        discovery = self.discovery.show(
            overview.asset_value, freshness_hours=stale_after_hours,
        )
        exposures = self.exposures.show(
            overview.asset_value, stale_after_hours=stale_after_hours,
        )
        findings, finding_domains = self._finding_summary(
            overview.asset_id, self.findings, finding_limit,
        )

        checked_at = now.isoformat()
        catalog_available = bool(self.indicators.list(
            indicator_type=None, active_only=True, checked_at=checked_at, limit=1,
        ))
        targets = self._ioc_targets(overview, finding_domains)
        matches = []
        if catalog_available:
            for indicator_type, value in targets:
                summary = self.indicators.current_summary(
                    indicator_type, normalize_indicator_value(indicator_type, value),
                    checked_at=checked_at,
                )
                if summary is not None:
                    matches.append(AnalysisIocMatch(
                        summary.indicator.id, summary.indicator.indicator_type,
                        summary.indicator.value, summary.current_assertion_count,
                        summary.max_current_confidence,
                    ))

        draft = UnifiedAnalysisReport(
            asset_id=overview.asset_id,
            asset_value=overview.asset_value,
            observed_at=checked_at,
            stored_data_only=True,
            vulnerability_scope="disabled",
            overview=overview,
            freshness=freshness,
            discovery=discovery,
            exposures=exposures,
            findings=findings,
            ioc_catalog_status="available" if catalog_available else "empty",
            ioc_checked_values=tuple(value for _, value in targets),
            ioc_matches=tuple(matches),
            next_steps=(),
            notes=(
                "Bu komut yalnız kayıtlı kanıtı okur; internete bağlanmaz ve veri değiştirmez.",
                "IOC eşleşmesi kaynak iddiasıdır; tek başına zararlılık veya etkilenme kararı değildir.",
                "Ürün, sürüm, paket ve CVE analizi etkin ürün kapsamının dışındadır.",
            ),
        )
        return replace(draft, next_steps=self._next_steps(draft))


class UnifiedAnalysisRefreshService:
    """Refresh an explicitly selected IOC feed, then re-read the full report."""

    def __init__(
        self, analysis: UnifiedAnalysisService, feed: CtiFeedService, *, source: str,
    ) -> None:
        if source not in {"feodo", "certpl"}:
            raise ValidationError("Birleşik analiz IOC kaynağı desteklenmiyor.")
        self.analysis = analysis
        self.feed = feed
        self.source = source

    def run(
        self, asset_value: str, *, stale_after_hours: int = 24,
        finding_limit: int = 10,
    ) -> UnifiedAnalysisRefreshResult:
        # Validate the complete local view before any external request or write.
        self.analysis.show(
            asset_value, stale_after_hours=stale_after_hours,
            finding_limit=finding_limit,
        )
        refresh = self.feed.sync()
        report = self.analysis.show(
            asset_value, stale_after_hours=stale_after_hours,
            finding_limit=finding_limit,
        )
        return UnifiedAnalysisRefreshResult(
            refresh_source=self.source, refresh=refresh, report=report,
        )
