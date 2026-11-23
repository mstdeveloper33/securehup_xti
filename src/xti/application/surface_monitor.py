"""Bounded terminal-open orchestration for approved surface checks."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import time

from xti.application.foreground_monitor import MonotonicBudget, utc_now
from xti.application.mail import SurfaceMailService
from xti.application.services import SurfaceServiceScanService
from xti.application.surface import SurfaceService
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.surface import (
    SurfaceMonitorOutcome,
    SurfaceMonitorReport,
    SurfaceMonitorStep,
)
from xti.ports.surface_monitor import SurfaceMonitorRunner


MONITOR_CHECK_TYPES = ("web", "mail", "services")


class WebSurfaceMonitorRunner:
    name = "web"

    def __init__(self, service: SurfaceService) -> None:
        self.service = service

    def prepare(self, asset_value: str) -> str:
        return self.service.scope_for_check(asset_value).asset_value

    def check(self, asset_value: str) -> SurfaceMonitorOutcome:
        check = self.service.check(asset_value)
        failed = check.result.dns_status in {"failed", "blocked"}
        status = "failed" if failed else "partial" if check.result.errors else "complete"
        return SurfaceMonitorOutcome(
            self.name, status, check.id, check.change.kind, check.recorded_at,
        )


class MailSurfaceMonitorRunner:
    name = "mail"

    def __init__(self, service: SurfaceMailService) -> None:
        self.service = service

    def prepare(self, asset_value: str) -> str:
        return self.service.prepare(asset_value).asset_value

    def check(self, asset_value: str) -> SurfaceMonitorOutcome:
        check = self.service.check(asset_value)
        statuses = (
            check.result.mx_status,
            check.result.spf_status,
            check.result.dmarc_status,
        )
        status = (
            "failed" if all(item == "failed" for item in statuses)
            else "partial" if check.result.errors else "complete"
        )
        return SurfaceMonitorOutcome(
            self.name, status, check.id, check.change.kind, check.recorded_at,
        )


class ServiceSurfaceMonitorRunner:
    name = "services"

    def __init__(
        self, service: SurfaceServiceScanService, requested_address: str,
        authorization_reason: str,
    ) -> None:
        self.service = service
        self.requested_address = requested_address
        self.authorization_reason = authorization_reason

    def prepare(self, asset_value: str) -> str:
        scope, address, reason = self.service.prepare(
            asset_value, self.requested_address, self.authorization_reason,
        )
        self.requested_address = address
        self.authorization_reason = reason
        return scope.asset_value

    def check(self, asset_value: str) -> SurfaceMonitorOutcome:
        check = self.service.check(
            asset_value, self.requested_address, self.authorization_reason,
        )
        status = (
            "failed" if check.result.dns_status != "resolved"
            else "partial" if any(item.state == "unknown" for item in check.result.ports)
            else "complete"
        )
        return SurfaceMonitorOutcome(
            self.name, status, check.id, check.change.kind, check.recorded_at,
        )


class SurfaceMonitorService:
    """Repeat selected bounded checks while this foreground command remains open."""

    def __init__(
        self, runners: Sequence[SurfaceMonitorRunner], *,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.runners = tuple(runners)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic
        self.sleeper = sleeper

    @staticmethod
    def validate_limits(
        max_cycles: int, interval_seconds: int, max_duration_seconds: int,
    ) -> None:
        for value, minimum, maximum, message in (
            (max_cycles, 1, 1000, "Dış yüzey izleme tur sayısı 1–1000 arasında olmalı."),
            (interval_seconds, 300, 86400,
             "Dış yüzey izleme aralığı 300–86400 saniye arasında olmalı."),
            (max_duration_seconds, 1, 604800,
             "Dış yüzey izleme süresi 1–604800 saniye arasında olmalı."),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValidationError(message)

    def prepare(self, asset_value: str) -> str:
        if not 1 <= len(self.runners) <= len(MONITOR_CHECK_TYPES):
            raise ValidationError("Dış yüzey izleme için en az bir kontrol seçilmeli.")
        names = tuple(runner.name for runner in self.runners)
        if (
            any(not isinstance(name, str) for name in names)
            or len(set(names)) != len(names)
            or any(name not in MONITOR_CHECK_TYPES for name in names)
        ):
            raise ValidationError("Dış yüzey izleme kontrolleri geçersiz veya tekrarlı.")
        normalized = normalize_domain(asset_value)
        prepared = tuple(runner.prepare(normalized) for runner in self.runners)
        if any(value != normalized for value in prepared):
            raise ValidationError("Dış yüzey izleme kapsamları aynı kök adresle eşleşmiyor.")
        return normalized

    def _now(self) -> str:
        return utc_now(self.clock, error_message="Dış yüzey izleme zamanı geçersiz.")

    @staticmethod
    def _validated_step(
        cycle: int, runner_name: str, outcome: SurfaceMonitorOutcome,
    ) -> SurfaceMonitorStep:
        if (
            not isinstance(outcome, SurfaceMonitorOutcome)
            or outcome.check_type != runner_name
            or outcome.status not in {"complete", "partial", "failed"}
            or outcome.change_kind not in {"baseline", "unchanged", "changed"}
            or not isinstance(outcome.evidence_id, str)
            or not 1 <= len(outcome.evidence_id) <= 128
            or not outcome.evidence_id.isprintable()
            or not isinstance(outcome.recorded_at, str)
            or not 1 <= len(outcome.recorded_at) <= 64
            or not outcome.recorded_at.isprintable()
        ):
            raise ValidationError("Dış yüzey izleme kontrolü geçersiz sonuç verdi.")
        try:
            recorded = datetime.fromisoformat(outcome.recorded_at)
            if recorded.tzinfo is None or recorded.utcoffset() is None:
                raise ValueError("timezone required")
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Dış yüzey izleme kanıt zamanı geçersiz.") from error
        return SurfaceMonitorStep(
            cycle=cycle, check_type=outcome.check_type, status=outcome.status,
            evidence_id=outcome.evidence_id, change_kind=outcome.change_kind,
            notification_created=outcome.change_kind == "changed",
            recorded_at=outcome.recorded_at,
        )

    def run(
        self, asset_value: str, *, max_cycles: int = 3,
        interval_seconds: int = 3600, max_duration_seconds: int = 86400,
        progress: Callable[[str], None] | None = None,
    ) -> SurfaceMonitorReport:
        self.validate_limits(max_cycles, interval_seconds, max_duration_seconds)
        normalized = self.prepare(asset_value)
        started_at = self._now()
        budget = MonotonicBudget(
            self.monotonic,
            invalid_message="Dış yüzey izleme süresini ölçen saat geçersiz.",
            rollback_message=(
                "Dış yüzey izleme süresini ölçen saat geriye gitti; "
                "izleme durduruldu."
            ),
        )
        budget.start()
        steps: list[SurfaceMonitorStep] = []
        completed_cycles = 0
        elapsed = budget.elapsed

        stop_reason = "cycles"
        for cycle in range(1, max_cycles + 1):
            cycle_complete = True
            for runner in self.runners:
                if elapsed() >= max_duration_seconds:
                    stop_reason = "duration"
                    cycle_complete = False
                    break
                if progress:
                    progress(
                        f"Dış yüzey izleme {cycle}/{max_cycles}: "
                        f"{runner.name} kontrolü başlıyor."
                    )
                step = self._validated_step(cycle, runner.name, runner.check(normalized))
                steps.append(step)
                if progress:
                    progress(
                        f"Dış yüzey izleme {cycle}/{max_cycles}: "
                        f"{runner.name} kontrolü {step.status}."
                    )
            if not cycle_complete:
                break
            completed_cycles += 1
            if cycle == max_cycles:
                break
            wait_started = elapsed()
            if wait_started >= max_duration_seconds:
                stop_reason = "duration"
                break
            wait_until = min(wait_started + interval_seconds, max_duration_seconds)
            if progress:
                progress("Sonraki dış yüzey turu bekleniyor. Durdurmak için Ctrl+C.")
            while True:
                remaining = wait_until - elapsed()
                if remaining <= 0:
                    break
                self.sleeper(min(1.0, remaining))
            if elapsed() >= max_duration_seconds:
                stop_reason = "duration"
                break

        duration = elapsed()
        statuses = tuple(step.status for step in steps)
        return SurfaceMonitorReport(
            asset_value=normalized,
            checks=tuple(runner.name for runner in self.runners),
            planned_cycles=max_cycles,
            completed_cycles=completed_cycles,
            completed_checks=len(steps),
            complete_checks=statuses.count("complete"),
            partial_checks=statuses.count("partial"),
            failed_checks=statuses.count("failed"),
            notifications_created=sum(step.notification_created for step in steps),
            started_at=started_at,
            finished_at=self._now(),
            elapsed_seconds=duration,
            stop_reason=stop_reason,
            steps=tuple(steps),
            notes=(
                "Her tamamlanan kontrol kendi kalıcı kanıt kaydını oluşturur.",
                "Yalnız gerçek değişiklik yerel gelen kutusuna bildirim ekler.",
                "Bu oturum yalnız terminal açıkken çalışır; arka plan servisi değildir.",
                "Süre sınırı yeni kontrol başlatmayı durdurur; başlamış kontrol tamamlanabilir.",
            ),
        )
