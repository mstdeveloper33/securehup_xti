"""Bounded monitoring sessions; a local owner persists work before executing it."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
import time

from xti.application.foreground_monitor import MonotonicBudget, monotonic_value
from xti.application.jobs import JobService, RECOVERY_REASON
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.monitoring import (
    MonitorDetails, MonitorReport, MonitorRun, MonitorSourceSummary, MonitorSpec,
)
from xti.ports.monitoring import MonitorRepository


PROVIDERS = frozenset({"crt.sh", "urlscan"})
TERMINAL_ATTEMPTS = frozenset({"complete", "partial", "failed", "interrupted"})


class MonitorService:
    def __init__(
        self, repository: MonitorRepository, jobs: JobService | None = None, *,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.repository = repository
        self.jobs = jobs
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic
        self.sleeper = sleeper

    @staticmethod
    def validate_spec(spec: MonitorSpec) -> MonitorSpec:
        if not isinstance(spec, MonitorSpec):
            raise ValidationError("Geçerli izleme ayarları gerekli.")
        if not isinstance(spec.targets, tuple) or not 1 <= len(spec.targets) <= 5:
            raise ValidationError("İzleme için 1–5 kayıtlı adres gerekli.")
        targets = tuple(normalize_domain(value) for value in spec.targets)
        if len(set(targets)) != len(targets):
            raise ValidationError("İzlenecek adresler tekrar etmemeli.")
        if (
            not isinstance(spec.providers, tuple) or not 1 <= len(spec.providers) <= 2
            or any(not isinstance(provider, str) or provider not in PROVIDERS for provider in spec.providers)
            or len(set(spec.providers)) != len(spec.providers)
        ):
            raise ValidationError("İzleme kaynakları crt.sh ve/veya urlscan olmalı; tekrar etmemeli.")
        if type(spec.typos) is not bool:
            raise ValidationError("Ek yazım araması seçimi doğru veya yanlış olmalı.")
        if (
            not isinstance(spec.rule_version, str) or not spec.rule_version.strip()
            or len(spec.rule_version) > 512 or not spec.rule_version.isprintable()
        ):
            raise ValidationError("Geçerli bir izleme kural sürümü gerekli.")
        for value, minimum, maximum, message in (
            (spec.max_cycles, 1, 1000, "İzleme tur sayısı 1–1000 arasında olmalı."),
            (spec.interval_seconds, 300, 86400, "İzleme aralığı 300–86400 saniye arasında olmalı."),
            (spec.max_duration_seconds, 1, 604800, "İzleme süresi 1–604800 saniye arasında olmalı."),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValidationError(message)
        return replace(spec, targets=targets)

    @staticmethod
    def _validate_id(run_id: str) -> None:
        if (
            not isinstance(run_id, str) or not run_id or len(run_id) > 64
            or not run_id.isprintable() or run_id.isspace()
        ):
            raise ValidationError("Geçerli bir izleme kimliği gerekli.")

    def _now(self) -> str:
        now = self.clock()
        try:
            if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
                raise ValidationError("İzleme için saat dilimi belli bir zaman gerekli.")
            return now.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("İzleme zamanı geçersiz veya desteklenen aralığın dışında.") from error

    def _runner(self) -> JobService:
        if self.jobs is None:
            raise ValidationError("İzleme başlatmak veya kurtarmak için çalıştırıcı bağlantısı gerekli.")
        return self.jobs

    def start(
        self, spec: MonitorSpec, *, progress: Callable[[str], None] | None = None,
    ) -> MonitorReport:
        spec = self.validate_spec(spec)
        jobs = self._runner()
        for provider in spec.providers:
            discovery = jobs.discoveries.get(provider)
            if discovery is None or discovery.matcher.rule_version != spec.rule_version:
                raise ValidationError("İzleme kaynağı veya kural sürümü çalıştırıcıyla uyuşmuyor.")
            if discovery.validate_targets(spec.targets, typos=spec.typos) != spec.targets:
                raise ValidationError("İzlenecek adresler çalıştırıcının seçimiyle uyuşmuyor.")
        # Fail bad clocks before taking ownership or creating a session.
        self._now()
        monotonic_value(
            self.monotonic,
            error_message="İzleme süresini ölçen saat geçersiz.",
        )
        with jobs.lock.acquire():
            self.repository.recover(self._now())
            jobs.jobs.recover_interrupted(RECOVERY_REASON)
            budget = MonotonicBudget(
                self.monotonic,
                invalid_message="İzleme süresini ölçen saat geçersiz.",
                rollback_message=(
                    "İzleme süresini ölçen saat geriye gitti; deneme durduruldu."
                ),
            )
            budget.start()
            run = self.repository.create(spec, self._now())
            elapsed = budget.elapsed

            def finish(reason: str) -> MonitorReport:
                self.repository.finish(run.id, "completed", reason, self._now(), elapsed())
                return self.show(run.id)

            try:
                if progress:
                    progress(f"İzleme kimliği: {run.id}")
                for cycle in range(1, spec.max_cycles + 1):
                    for provider in spec.providers:
                        if elapsed() >= spec.max_duration_seconds:
                            return finish("duration")
                        job = self.repository.enqueue(run.id, cycle, provider, self._now())
                        if progress:
                            progress(f"İzleme turu {cycle}/{spec.max_cycles}; kaynak: {provider}")
                        if elapsed() >= spec.max_duration_seconds:
                            return finish("duration")
                        if jobs.run_owned(job.id, monitor_id=run.id, progress=progress) is None:
                            raise RuntimeError("İzleme işi başlatılamadı.")
                    if progress:
                        progress(f"İzleme turu {cycle}/{spec.max_cycles} tamamlandı.")
                    if cycle == spec.max_cycles:
                        return finish("cycles")
                    wait_until = min(elapsed() + spec.interval_seconds, spec.max_duration_seconds)
                    if progress:
                        progress("Sonraki izleme turu bekleniyor. Durdurmak için Ctrl+C.")
                    while True:
                        remaining = wait_until - elapsed()
                        if remaining <= 0:
                            break
                        self.sleeper(min(1.0, remaining))
                raise RuntimeError("İzleme tur sınırı uygulanamadı.")
            except BaseException as error:
                interrupted = isinstance(error, (KeyboardInterrupt, SystemExit))
                try:
                    try:
                        duration = elapsed()
                    except Exception:
                        duration = None
                    self.repository.finish(
                        run.id, "interrupted" if interrupted else "failed",
                        "cancelled" if interrupted else "error", self._now(), duration,
                    )
                except Exception:
                    # Preserve the original error; a later explicit recovery owns
                    # the remaining running record if storage or its clock failed.
                    pass
                raise

    def recover(self) -> int:
        jobs = self._runner()
        with jobs.lock.acquire():
            return self.repository.recover(self._now())

    def list(self, limit: int = 20) -> tuple[MonitorRun, ...]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("İzleme listesi sınırı 1–100 arasında olmalı.")
        return self.repository.list(limit)

    def details(self, run_id: str) -> MonitorDetails:
        self._validate_id(run_id)
        return self.repository.get(run_id)

    def show(self, run_id: str) -> MonitorReport:
        return self.summarize(self.details(run_id))

    @staticmethod
    def summarize(details: MonitorDetails) -> MonitorReport:
        run = details.run
        sources = []
        cycles: dict[int, set[str]] = {}
        for entry in details.entries:
            if entry.attempt is not None and entry.attempt.status in TERMINAL_ATTEMPTS:
                cycles.setdefault(entry.cycle, set()).add(entry.provider)
        for provider in run.spec.providers:
            entries = tuple(item for item in details.entries if item.provider == provider)
            attempts = tuple(item.attempt for item in entries if item.attempt is not None)
            statuses = {state: sum(item.status == state for item in attempts)
                        for state in (*sorted(TERMINAL_ATTEMPTS), "running")}
            summaries = tuple(item.summary for item in attempts if item.summary is not None)
            sources.append(MonitorSourceSummary(
                provider=provider, planned_runs=run.spec.max_cycles,
                scheduled_jobs=len(entries), started_attempts=len(attempts),
                complete=statuses["complete"], partial=statuses["partial"],
                failed=statuses["failed"], interrupted=statuses["interrupted"], running=statuses["running"],
                not_started=run.spec.max_cycles - len(attempts),
                query_count=sum(item.query_count for item in attempts),
                failed_queries=sum(item.failed_queries for item in attempts),
                partial_queries=sum(item.partial_queries for item in attempts),
                observations_created=sum(item.observations_created for item in summaries),
                findings_created=sum(item.findings_created for item in summaries),
                unknown_result_count=sum(item.summary is None for item in attempts),
                findings_suppressed=sum(item.findings_suppressed for item in summaries),
            ))
        if run.status in {"running", "interrupted", "failed"}:
            outcome = run.status
        else:
            started_attempts = tuple(item.attempt for item in details.entries if item.attempt is not None)
            outcome = "complete" if started_attempts and all(
                attempt.status == "complete" for attempt in started_attempts
            ) else "partial"
        return MonitorReport(
            run=run, sources=tuple(sources),
            completed_cycles=sum(set(run.spec.providers) <= providers for providers in cycles.values()),
            outcome=outcome,
            notes=(
                "Süre sınırı yeni kaynak işi başlatmayı durdurur; başlamış arama kendi sorgu ve zaman sınırlarıyla tamamlanır, toplam süre aşılabilir.",
                "Tur aralığı tamamlanan turdan sonraki beklemedir; arama süresi buna eklenir.",
                "Planlanan ama başlamayan çalışmalar, başarısız kaynak yanıtı sayılmaz.",
                "Tamamlanan tur, bütün kaynak denemelerinin bitmesidir; hepsinin başarılı olduğu anlamına gelmez.",
                "Yeni gözlem/bulgu toplamları yalnız sonuç özeti kayıtlı denemeleri kapsar; sonucu eksik denemeler ayrıca sayılır.",
                "Sorgu sayıları kayıtlı mantıksal sorgulardır; HTTP istek sayısı veya kaynak erişilebilirlik oranı değildir.",
                "Bu rapor oturuma bağlanan ilk denemeleri kullanır; sonraki tekrarlar eski ölçümü değiştirmez.",
                "Kısa veya sentetik denemeler uzun süreli canlı çalışma ya da büyük ölçek kanıtı değildir.",
            ),
        )
