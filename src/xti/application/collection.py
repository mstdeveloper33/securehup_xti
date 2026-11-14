"""Collect selected passive evidence through existing independent workflows."""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone

from xti.application.analysis import UnifiedAnalysisService
from xti.application.collection_watches import CollectionWatchService
from xti.application.cti_feeds import CtiFeedService
from xti.application.jobs import JobService
from xti.application.public_notices import PublicNoticeService
from xti.application.surface import SurfaceDiscoveryService
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.collection import (
    COLLECTION_TASKS,
    COLLECTION_TASK_IDS,
    DEFAULT_COLLECTION_TASKS,
    CollectionPlan,
    CollectionResult,
    CollectionStep,
    CollectionTask,
)
from xti.domain.cti_feeds import CTI_FEED_POLICIES, CtiFeedRun
from xti.domain.collection_history import CollectionOperationToken
from xti.domain.jobs import ScanAttempt
from xti.domain.public_notices import (
    HIBP_ATTRIBUTION, HIBP_LICENSE, HIBP_SOURCE_NAME, HIBP_SOURCE_URL,
    PublicNoticeRefreshReport, PublicNoticeStatus,
)
from xti.domain.surface import SurfaceDiscoveryResult


class CollectionService:
    """One explicit collection with each existing source run retained separately.

    Source failures are returned by the existing services and do not suppress
    independent work. Storage, contract and programming errors propagate;
    previously committed source evidence remains available in its own history.
    """

    def __init__(
        self, jobs: JobService,
        discoveries: Mapping[str, SurfaceDiscoveryService],
        feeds: Mapping[str, CtiFeedService],
        analysis: UnifiedAnalysisService,
        *, watch_collection: CollectionWatchService | None = None,
        public_notices: PublicNoticeService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.jobs = jobs
        self.discoveries = dict(discoveries)
        self.feeds = dict(feeds)
        self.analysis = analysis
        self.watch_collection = watch_collection or CollectionWatchService()
        self.public_notices = public_notices
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Toplama zamanı saat dilimi bilgili olmalı.")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _selection(tasks: Sequence[str] | None, *, allow_empty_base: bool = False) -> tuple[CollectionTask, ...]:
        if type(allow_empty_base) is not bool:
            raise ValidationError("Toplama planı seçim türü geçersiz.")
        if allow_empty_base and tasks == ():
            return ()
        if tasks is None:
            tasks = DEFAULT_COLLECTION_TASKS
        if (
            not isinstance(tasks, Sequence) or isinstance(tasks, (str, bytes))
            or not 1 <= len(tasks) <= len(COLLECTION_TASKS)
            or any(not isinstance(task, str) or task not in COLLECTION_TASK_IDS for task in tasks)
        ):
            raise ValidationError(f"Toplama için desteklenen 1–{len(COLLECTION_TASKS)} görev seçilmeli.")
        if len(set(tasks)) != len(tasks):
            raise ValidationError("Toplama görevleri tekrarlı olamaz.")
        selected = set(tasks)
        return tuple(task for task in COLLECTION_TASKS if task.id in selected)

    def plan(
        self, domain: str, *, tasks: Sequence[str] | None = None,
        typos: bool = False, stale_after_hours: int = 24, finding_limit: int = 10,
        username_watch_ids: Sequence[str] = (),
        ransomware_watch_ids: Sequence[str] = (),
        ransomlook_watch_ids: Sequence[str] = (),
        watch_item_limit: int = 100, allow_empty_base: bool = False,
    ) -> CollectionPlan:
        username_ids, ransomware_ids, ransomlook_ids = CollectionWatchService.validate_selection(
            username_watch_ids=username_watch_ids,
            ransomware_watch_ids=ransomware_watch_ids,
            ransomlook_watch_ids=ransomlook_watch_ids,
            item_limit=watch_item_limit,
        )
        selected = self._selection(tasks, allow_empty_base=allow_empty_base)
        if type(typos) is not bool:
            raise ValidationError("Yazım varyasyonu seçimi doğru/yanlış olmalı.")
        if typos and not any(task.kind == "scan" for task in selected):
            raise ValidationError("Yazım varyasyonu yalnız marka aramasıyla kullanılabilir.")
        if type(stale_after_hours) is not int or not 1 <= stale_after_hours <= 8760:
            raise ValidationError("Güncellik eşiği 1–8760 saat arasında olmalı.")
        if type(finding_limit) is not int or not 1 <= finding_limit <= 50:
            raise ValidationError("Birleşik analiz bulgu sınırı 1–50 arasında olmalı.")
        value = normalize_domain(domain)

        # Validate the complete stored report first. This checks registration,
        # schema and evidence integrity without creating storage or collecting.
        report = self.analysis.show(
            value, stale_after_hours=stale_after_hours, finding_limit=finding_limit,
        )
        if report.asset_value != value:
            raise ValidationError("Toplama analizi seçilen domainle uyuşmuyor.")

        # All selected workflows must pass preflight before any enqueue, lock
        # or request. Nonselected sources are never inspected or executed.
        for task in selected:
            if task.kind == "scan":
                discovery = self.jobs.discoveries.get(task.source)
                if discovery is None:
                    raise ValidationError("Seçilen marka araması yapılandırılmamış.")
                targets = discovery.validate_targets((value,), typos=typos)
                if targets != (value,):
                    raise ValidationError("Marka araması seçilen domainle uyuşmuyor.")
            elif task.kind == "discovery":
                discovery = self.discoveries.get(task.source)
                if discovery is None or discovery.source is None:
                    raise ValidationError("Seçilen pasif keşif kaynağı yapılandırılmamış.")
                if getattr(discovery.source, "provider", "crt.sh") != task.source:
                    raise ValidationError("Pasif keşif kaynağı seçilen görevle uyuşmuyor.")
                discovery.list(value, status=None, limit=1)
            elif task.kind == "public_notice":
                if self.public_notices is None or self.public_notices.source is None:
                    raise ValidationError("Seçilen kamu olay kaynağı yapılandırılmamış.")
                status = self.public_notices.status(run_limit=1)
                if (not isinstance(status, PublicNoticeStatus)
                        or status.source_name != HIBP_SOURCE_NAME or status.source_url != HIBP_SOURCE_URL
                        or status.attribution != HIBP_ATTRIBUTION or status.license != HIBP_LICENSE):
                    raise ValidationError("Kamu olay kaynağı seçilen görevle uyuşmuyor.")
            else:
                feed = self.feeds.get(task.source)
                if feed is None or feed.source is None:
                    raise ValidationError("Seçilen IOC kaynağı yapılandırılmamış.")
                status = feed.status(run_limit=1)
                if status.source_name != CTI_FEED_POLICIES[task.source].source_name:
                    raise ValidationError("IOC kaynağı seçilen görevle uyuşmuyor.")

        watch_tasks = self.watch_collection.plan(
            username_watch_ids=username_ids,
            ransomware_watch_ids=ransomware_ids,
            ransomlook_watch_ids=ransomlook_ids,
            item_limit=watch_item_limit,
        )
        return CollectionPlan(
            asset_value=value, typos=typos, tasks=selected + watch_tasks,
            watch_item_limit=watch_item_limit,
            notes=(
                "Seçilen arşivler, açık kaynak listeleri ve seçili kullanıcı adı platformları sorgulanır; hedefte aktif test yapılmaz.",
                "IOC yenilemesi seçilirse liste tüm yerel IOC kataloğunda güncellenir; yalnız bu domaine ait değildir.",
                "Kaynak hatası diğer kaynakların sonucunu silmez; başarısız veya kısmi toplama boş başarı sayılmaz.",
                "Her adım kendi kalıcı geçmişini tutar; birleşik sonuç için ayrı oturum kaydı veya otomatik devam yoktur.",
            ) + ((
                "HIBP yenilemesi ortak kamu olay kataloğunu günceller; katalog sayıları seçilen domainin bulgu sayısı değildir.",
                "HIBP yalnız kamu olay metaverisidir; e-posta, hesap veya parola sorgusu yapılmaz.",
                "Açık kuruluş kamu olay izlemeleri bu ortak yenilemede değerlendirilir; seçilen domainle sınırlanmaz.",
                HIBP_ATTRIBUTION, HIBP_LICENSE,
            ) if any(task.kind == "public_notice" for task in selected) else ()) + ((
                "İzlemeler açık kimlik seçiminizle çalışır; domainle sahiplik veya kuruluş ilişkisi otomatik kurulmaz.",
                "Her ransomware kaynağı bir kez yenilenir; yenileme başarısızsa o kaynağın seçilen izlemeleri çalıştırılmaz.",
                "İlk izleme ölçümü başlangıç kaydıdır; yeni tehdit veya doğrulanmış ihlal anlamına gelmez.",
                "İzleme sonuçları aşağıdaki domain analizinden ayrıdır; kaynaklar ve örtüşen izlemeler tekil bulgu toplamına eklenmez.",
            ) if watch_tasks else ()),
        )

    def _collect(
        self, task: CollectionTask, plan: CollectionPlan,
        progress: Callable[[str], None] | None,
        operation: CollectionOperationToken | None = None,
    ) -> CollectionStep:
        kwargs = {"operation": operation} if operation is not None else {}
        if task.kind in {"username_watch", "ransomware"}:
            if operation is not None:
                raise ValidationError("İzleme oturumu tek kaynak birimiyle çalıştırılmalı.")
            result = self.watch_collection.run(task, item_limit=plan.watch_item_limit)
            if (
                not isinstance(result, CollectionStep) or result.task != task
                or result.status not in {"complete", "failed"}
            ):
                raise ValidationError("İzleme geçersiz toplama sonucu üretti.")
            return result
        if task.kind == "scan":
            job = self.jobs.enqueue(
                (plan.asset_value,), typos=plan.typos, provider=task.source, **kwargs,
            )
            attempt = self.jobs.run_owned(job.id, progress=progress, **kwargs)
            if (
                not isinstance(attempt, ScanAttempt) or attempt.job_id != job.id
                or attempt.status not in {"complete", "partial", "failed"}
                or attempt.result is None or attempt.result.status != attempt.status
                or attempt.result.targets != (plan.asset_value,)
            ):
                raise ValidationError("Marka araması geçersiz toplama sonucu üretti.")
            return CollectionStep(task=task, status=attempt.status, attempt=attempt)
        if task.kind == "discovery":
            result = self.discoveries[task.source].discover(plan.asset_value, **kwargs)
            if (
                not isinstance(result, SurfaceDiscoveryResult)
                or result.status not in {"complete", "partial", "failed"}
                or result.provider != task.source or result.asset_value != plan.asset_value
                or not result.run_id
            ):
                raise ValidationError("Pasif keşif geçersiz toplama sonucu üretti.")
            return CollectionStep(task=task, status=result.status, discovery=result)
        if task.kind == "public_notice":
            if self.public_notices is None:
                raise ValidationError("Seçilen kamu olay kaynağı yapılandırılmamış.")
            result = self.public_notices.refresh(**kwargs)
            if (not isinstance(result, PublicNoticeRefreshReport)
                    or result.run.status not in {"complete", "failed"}
                    or result.source_name != HIBP_SOURCE_NAME or result.source_url != HIBP_SOURCE_URL
                    or result.attribution != HIBP_ATTRIBUTION or result.license != HIBP_LICENSE):
                raise ValidationError("Kamu olay yenilemesi geçersiz toplama sonucu üretti.")
            return CollectionStep(task=task, status=result.run.status, public_notices=result)
        result = self.feeds[task.source].sync(**kwargs)
        if (
            not isinstance(result, CtiFeedRun) or result.status not in {"complete", "failed"}
            or result.source_name != CTI_FEED_POLICIES[task.source].source_name
        ):
            raise ValidationError("IOC yenilemesi geçersiz toplama sonucu üretti.")
        return CollectionStep(task=task, status=result.status, feed=result)

    def run(
        self, domain: str, *, tasks: Sequence[str] | None = None,
        typos: bool = False, stale_after_hours: int = 24, finding_limit: int = 10,
        username_watch_ids: Sequence[str] = (),
        ransomware_watch_ids: Sequence[str] = (),
        ransomlook_watch_ids: Sequence[str] = (),
        watch_item_limit: int = 100,
        progress: Callable[[str], None] | None = None,
        preflight: Callable[[], None] | None = None,
    ) -> CollectionResult:
        if preflight is not None:
            preflight()
        plan = self.plan(
            domain, tasks=tasks, typos=typos,
            stale_after_hours=stale_after_hours, finding_limit=finding_limit,
            username_watch_ids=username_watch_ids,
            ransomware_watch_ids=ransomware_watch_ids,
            ransomlook_watch_ids=ransomlook_watch_ids,
            watch_item_limit=watch_item_limit,
        )
        started = self._now()
        with self.jobs.lock.acquire():
            if preflight is not None:
                preflight()
            # Another writer may have changed local evidence since preflight.
            # Recheck under the shared lock before the first persistent action.
            plan = self.plan(
                plan.asset_value,
                tasks=tuple(task.id for task in plan.tasks if task.id in COLLECTION_TASK_IDS),
                typos=typos,
                stale_after_hours=stale_after_hours, finding_limit=finding_limit,
                username_watch_ids=tuple(
                    watch.watch_id for task in plan.tasks if task.kind == "username_watch"
                    for watch in task.watches
                ),
                ransomware_watch_ids=tuple(
                    watch.watch_id for task in plan.tasks if task.kind == "ransomware"
                    and task.source == "threatcluster" for watch in task.watches
                ),
                ransomlook_watch_ids=tuple(
                    watch.watch_id for task in plan.tasks if task.kind == "ransomware"
                    and task.source == "ransomlook" for watch in task.watches
                ),
                watch_item_limit=watch_item_limit,
            )
            steps: list[CollectionStep] = []
            for task in plan.tasks:
                if progress:
                    progress(f"Toplama: {task.label}")
                steps.append(self._collect(task, plan, progress))
            report = self.analysis.show(
                plan.asset_value,
                stale_after_hours=stale_after_hours, finding_limit=finding_limit,
            )
            if report.asset_value != plan.asset_value:
                raise ValidationError("Toplama sonrası analiz seçilen domainle uyuşmuyor.")
            finished = self._now()
            if finished < started:
                raise ValidationError("Toplama bitiş zamanı başlangıçtan önce olamaz.")
        statuses = tuple(step.status for step in steps)
        status = (
            "complete" if all(item == "complete" for item in statuses)
            else "failed" if all(item == "failed" for item in statuses)
            else "partial"
        )
        return CollectionResult(
            plan=plan, started_at=started.isoformat(), finished_at=finished.isoformat(),
            status=status, steps=tuple(steps), analysis=report,
        )
