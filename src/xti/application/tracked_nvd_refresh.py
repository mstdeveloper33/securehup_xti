"""Plan and explicitly refresh official NVD records tied to local exposures."""

from collections.abc import Callable
from datetime import datetime, timezone
import time

from xti.application.vulnerability import (
    NVD_KEYLESS_MIN_INTERVAL_SECONDS,
    NvdCatalogService,
)
from xti.domain.assets import ValidationError
from xti.domain.tracked_nvd_refresh import (
    TrackedNvdRefreshPlan,
    TrackedNvdRefreshResult,
)
from xti.ports.tracked_nvd_refresh import TrackedNvdRefreshPlanRepository
from xti.ports.vulnerability import NvdRepository, NvdSource


_RESULT_NOTES = (
    "Her CVE ayrı ve atomik kaydedilir; ilk kaynak hatasında sonraki istekler başlatılmaz.",
    "Kaynak değişikliği insan kararını değiştirmez; vuln reassessment-plan ile etkisi incelenir.",
)


class TrackedNvdRefreshService:
    def __init__(
        self, plan_repository: TrackedNvdRefreshPlanRepository,
        nvd_repository: NvdRepository, source: NvdSource | None = None, *,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.plan_repository = plan_repository
        self.nvd_repository = nvd_repository
        self.source = source
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper or time.sleep

    def _now(self) -> datetime:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("İlgili NVD yenileme zamanı geçersiz.")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _options(
        stale_after_hours: int, include_closed: bool,
        include_suppressed: bool, limit: int, *, execution: bool,
    ) -> None:
        maximum = 5 if execution else 100
        if (
            type(stale_after_hours) is not int or not 1 <= stale_after_hours <= 8760
            or type(include_closed) is not bool or type(include_suppressed) is not bool
        ):
            raise ValidationError("İlgili NVD planı isteği geçersiz.")
        if type(limit) is not int or not 1 <= limit <= maximum:
            if execution:
                raise ValidationError("İlgili NVD yenileme sınırı 1–5 arasında olmalı.")
            raise ValidationError("İlgili NVD plan sınırı 1–100 arasında olmalı.")

    def plan(
        self, *, stale_after_hours: int = 168, include_closed: bool = False,
        include_suppressed: bool = False, limit: int = 20,
    ) -> TrackedNvdRefreshPlan:
        self._options(
            stale_after_hours, include_closed, include_suppressed, limit,
            execution=False,
        )
        return self.plan_repository.plan(
            stale_after_hours=stale_after_hours,
            include_closed=include_closed, include_suppressed=include_suppressed,
            limit=limit, checked_at=self._now().isoformat(),
        )

    def _pace_after(self, finished_at: str | None) -> None:
        if finished_at is None:
            return
        try:
            finished = datetime.fromisoformat(finished_at)
            if finished.tzinfo is None or finished.utcoffset() is None:
                raise ValueError("timezone required")
            finished = finished.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Son NVD çalışma zamanı geçersiz.") from error
        elapsed = (self._now() - finished).total_seconds()
        if elapsed < -1:
            raise ValidationError(
                "Sistem saati son NVD çalışmasından geride; ağ isteği başlatılmadı."
            )
        remaining = NVD_KEYLESS_MIN_INTERVAL_SECONDS - max(0.0, elapsed)
        if remaining > 0:
            self.sleeper(remaining)

    def refresh(
        self, *, stale_after_hours: int = 168, include_closed: bool = False,
        include_suppressed: bool = False, limit: int = 3,
    ) -> TrackedNvdRefreshResult:
        self._options(
            stale_after_hours, include_closed, include_suppressed, limit,
            execution=True,
        )
        if self.source is None:
            raise ValidationError("NVD yenileme kaynağı yapılandırılmamış.")
        plan = self.plan_repository.plan(
            stale_after_hours=stale_after_hours,
            include_closed=include_closed, include_suppressed=include_suppressed,
            limit=limit, checked_at=self._now().isoformat(),
        )
        candidates = tuple(item for item in plan.items if item.freshness == "stale")
        latest = self.nvd_repository.status(run_limit=1).latest_run
        last_finished = latest.finished_at if latest is not None else None
        runs = []
        catalog = NvdCatalogService(
            self.nvd_repository, self.source, clock=self.clock,
        )
        for candidate in candidates:
            self._pace_after(last_finished)
            run = catalog.sync(candidate.cve_id)
            runs.append(run)
            last_finished = run.finished_at
            if run.status == "failed":
                break
        status = "complete" if len(runs) == len(candidates) and all(
            run.status == "complete" for run in runs
        ) else "stopped"
        return TrackedNvdRefreshResult(
            status=status,
            stale_after_hours=stale_after_hours,
            include_closed=include_closed,
            include_suppressed=include_suppressed,
            limit=limit,
            minimum_interval_seconds=str(NVD_KEYLESS_MIN_INTERVAL_SECONDS),
            plan_attention_count=plan.attention_count,
            plan_refresh_due_count=plan.refresh_due_count,
            planned_candidates=candidates,
            runs=tuple(runs),
            notes=_RESULT_NOTES,
        )
