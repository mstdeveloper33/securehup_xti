"""Explicit saved-watch selection for one foreground collection.

This service does not infer watch ownership from a domain, acquire a lock, or
replace source histories. Its caller owns the shared execution lock.
"""

from collections.abc import Mapping, Sequence

from xti.application.brand_username_watches import BrandUsernameWatchService
from xti.application.ransomlook_ransomware import RansomLookClaimHistoryService
from xti.application.ransomlook_watches import RansomLookWatchService
from xti.application.ransomware_claims import RansomwareClaimHistoryService
from xti.application.ransomware_watches import RansomwareWatchService
from xti.domain.assets import ValidationError
from xti.domain.brand_username import BRAND_USERNAME_SOURCE_NAMES
from xti.domain.brand_username_watches import (
    BrandUsernameWatch, BrandUsernameWatchRunReport,
)
from xti.domain.collection import (
    CollectionRansomwareResult, CollectionStep, CollectionTask, CollectionWatchTarget,
)
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.ransomlook_ransomware import (
    RANSOMLOOK_SOURCE_NAME, RANSOMLOOK_SOURCE_URL, RansomLookClaimRunReport,
)
from xti.domain.ransomlook_watches import RansomLookWatch, RansomLookWatchRunReport
from xti.domain.ransomware_claims import (
    RANSOMWARE_SOURCE_NAME, RANSOMWARE_SOURCE_URL, RansomwareClaimRunReport,
)
from xti.domain.ransomware_watches import RansomwareWatch, RansomwareWatchRunReport


MAX_COLLECTION_WATCHES = 50
_RANSOMWARE = {
    "threatcluster": (RANSOMWARE_SOURCE_NAME, RANSOMWARE_SOURCE_URL),
    "ransomlook": (RANSOMLOOK_SOURCE_NAME, RANSOMLOOK_SOURCE_URL),
}


class CollectionWatchService:
    def __init__(
        self, username: BrandUsernameWatchService | None = None,
        ransomware_histories: Mapping[
            str, RansomwareClaimHistoryService | RansomLookClaimHistoryService
        ] | None = None,
        ransomware_watches: Mapping[
            str, RansomwareWatchService | RansomLookWatchService
        ] | None = None,
    ) -> None:
        self.username = username
        self.ransomware_histories = dict(ransomware_histories or {})
        self.ransomware_watches = dict(ransomware_watches or {})

    @staticmethod
    def _limit(item_limit: int) -> None:
        if type(item_limit) is not int or not 1 <= item_limit <= 500:
            raise ValidationError("Toplama izleme sonuç sınırı 1–500 arasında olmalı.")

    @staticmethod
    def _ids(values: Sequence[str]) -> tuple[str, ...]:
        if (
            not isinstance(values, Sequence) or isinstance(values, (str, bytes))
            or len(values) > MAX_COLLECTION_WATCHES
        ):
            raise ValidationError("Toplamada en fazla 50 açık izleme kimliği seçilebilir.")
        ids = tuple(normalize_knowledge_id(value, field="toplama izleme kimliği") for value in values)
        if len(set(ids)) != len(ids):
            raise ValidationError("Aynı kaynağın toplama izleme kimlikleri tekrarlı olamaz.")
        return tuple(sorted(ids))

    @staticmethod
    def _username_target(watch: BrandUsernameWatch) -> CollectionWatchTarget:
        if not isinstance(watch, BrandUsernameWatch) or not watch.active:
            raise ValidationError("Toplama için etkin sosyal kullanıcı adı izlemesi gerekli.")
        return CollectionWatchTarget(
            watch.id, watch.display_name, watch.username, "username", "exact", watch.platforms,
        )

    @staticmethod
    def _ransomware_target(
        source: str, watch: RansomwareWatch | RansomLookWatch,
    ) -> CollectionWatchTarget:
        expected = RansomwareWatch if source == "threatcluster" else RansomLookWatch
        if not isinstance(watch, expected) or not watch.active:
            raise ValidationError("Toplama için seçilen kaynağa ait etkin ransomware izlemesi gerekli.")
        return CollectionWatchTarget(
            watch.id, watch.display_name, watch.query,
            watch.kind if source == "threatcluster" else "organization", watch.match_mode,
        )

    def _username_task(self, watch_id: str) -> CollectionTask:
        if self.username is None:
            raise ValidationError("Sosyal kullanıcı adı izleme servisi yapılandırılmamış.")
        watch = self.username.show(watch_id, event_limit=1, run_limit=1).watch
        target = self._username_target(watch)
        if watch.id != watch_id:
            raise ValidationError("Sosyal izleme kaydı seçilen kimlikle uyuşmuyor.")
        source = self.username.sources.get(watch.source_key)
        if source is None or source.source_name != BRAND_USERNAME_SOURCE_NAMES.get(watch.source_key):
            raise ValidationError("Seçilen sosyal izleme kaynağı yapılandırılmamış.")
        return CollectionTask(
            f"username-watch:{watch_id}", "username_watch", watch.source_key,
            f"{BRAND_USERNAME_SOURCE_NAMES[watch.source_key]} kullanıcı adı izlemesi", (target,),
        )

    def _ransomware_task(self, source: str, ids: tuple[str, ...]) -> CollectionTask:
        if source not in _RANSOMWARE:
            raise ValidationError("Toplama ransomware kaynağı desteklenmiyor.")
        history = self.ransomware_histories.get(source)
        watches = self.ransomware_watches.get(source)
        history_type = RansomwareClaimHistoryService if source == "threatcluster" else RansomLookClaimHistoryService
        watch_type = RansomwareWatchService if source == "threatcluster" else RansomLookWatchService
        if (
            not isinstance(history, history_type) or history.source is None
            or not isinstance(watches, watch_type)
        ):
            raise ValidationError("Seçilen ransomware kaynağı ve izleme servisi yapılandırılmamış.")
        history.status(run_limit=1)
        targets = []
        for watch_id in ids:
            watch = watches.show(watch_id, event_limit=1, run_limit=1).watch
            target = self._ransomware_target(source, watch)
            if watch.id != watch_id:
                raise ValidationError("Ransomware izleme kaydı seçilen kimlikle uyuşmuyor.")
            targets.append(target)
        label = "ThreatCluster" if source == "threatcluster" else "RansomLook"
        return CollectionTask(
            f"ransomware-{source}", "ransomware", source,
            f"{label} kaynak yenilemesi ve seçilen izlemeler", tuple(targets),
        )

    @staticmethod
    def validate_selection(
        *, username_watch_ids: Sequence[str] = (),
        ransomware_watch_ids: Sequence[str] = (), ransomlook_watch_ids: Sequence[str] = (),
        item_limit: int = 100,
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        CollectionWatchService._limit(item_limit)
        username_ids, threatcluster_ids, ransomlook_ids = (
            CollectionWatchService._ids(ids)
            for ids in (username_watch_ids, ransomware_watch_ids, ransomlook_watch_ids)
        )
        if sum(map(len, (username_ids, threatcluster_ids, ransomlook_ids))) > MAX_COLLECTION_WATCHES:
            raise ValidationError("Toplamada en fazla 50 açık izleme kimliği seçilebilir.")
        return username_ids, threatcluster_ids, ransomlook_ids

    def plan(
        self, *, username_watch_ids: Sequence[str] = (),
        ransomware_watch_ids: Sequence[str] = (), ransomlook_watch_ids: Sequence[str] = (),
        item_limit: int = 100,
    ) -> tuple[CollectionTask, ...]:
        username_ids, threatcluster_ids, ransomlook_ids = self.validate_selection(
            username_watch_ids=username_watch_ids, ransomware_watch_ids=ransomware_watch_ids,
            ransomlook_watch_ids=ransomlook_watch_ids, item_limit=item_limit,
        )
        tasks = [self._username_task(watch_id) for watch_id in username_ids]
        for source, ids in (("threatcluster", threatcluster_ids), ("ransomlook", ransomlook_ids)):
            if ids:
                tasks.append(self._ransomware_task(source, ids))
        return tuple(tasks)

    def _check_task(self, task: CollectionTask, item_limit: int) -> None:
        self._limit(item_limit)
        if (
            not isinstance(task, CollectionTask) or not isinstance(task.watches, tuple)
            or not task.watches or any(not isinstance(item, CollectionWatchTarget) for item in task.watches)
        ):
            raise ValidationError("Toplama izleme görevi geçersiz.")
        ids = self._ids(tuple(item.watch_id for item in task.watches))
        if task.kind == "username_watch" and len(ids) == 1:
            current = self.plan(username_watch_ids=ids, item_limit=item_limit)
        elif task.kind == "ransomware" and task.source in _RANSOMWARE:
            current = self.plan(
                ransomware_watch_ids=ids if task.source == "threatcluster" else (),
                ransomlook_watch_ids=ids if task.source == "ransomlook" else (),
                item_limit=item_limit,
            )
        else:
            raise ValidationError("Toplama izleme görev türü veya kaynağı geçersiz.")
        if current != (task,):
            raise ValidationError("Toplama izleme tanımı plandan sonra değişti; çalışma başlatılmadı.")

    def run(self, task: CollectionTask, *, item_limit: int = 100) -> CollectionStep:
        self._check_task(task, item_limit)
        if task.kind == "username_watch":
            target = task.watches[0]
            report = self.username.run(target.watch_id, item_limit=item_limit)
            if (
                not isinstance(report, BrandUsernameWatchRunReport)
                or self._username_target(report.watch) != target
                or report.watch.source_key != task.source
                or report.run.watch_id != target.watch_id
                or report.run.username != target.query or report.run.platforms != target.platforms
                or report.run.source_name != BRAND_USERNAME_SOURCE_NAMES[task.source]
                or report.run.status not in {"complete", "failed"}
            ):
                raise ValidationError("Sosyal izleme geçersiz toplama sonucu üretti.")
            normalize_knowledge_id(report.run.id, field="sosyal toplama çalışma kimliği")
            return CollectionStep(task, report.run.status, username=report)

        history = self.ransomware_histories[task.source]
        watches = self.ransomware_watches[task.source]
        refresh = history.refresh(item_limit=item_limit)
        expected_report = RansomwareClaimRunReport if task.source == "threatcluster" else RansomLookClaimRunReport
        expected_watch_report = RansomwareWatchRunReport if task.source == "threatcluster" else RansomLookWatchRunReport
        if (
            not isinstance(refresh, expected_report)
            or (refresh.run.source_name, refresh.run.source_url) != _RANSOMWARE[task.source]
            or refresh.run.status not in {"complete", "failed"}
        ):
            raise ValidationError("Ransomware kaynağı geçersiz toplama sonucu üretti.")
        normalize_knowledge_id(refresh.run.id, field="ransomware toplama kaynak çalışma kimliği")
        if refresh.run.status == "failed":
            return CollectionStep(
                task, "failed", ransomware=CollectionRansomwareResult(
                    refresh, (), tuple(item.watch_id for item in task.watches),
                ),
            )
        reports = []
        for target in task.watches:
            current = watches.show(target.watch_id, event_limit=1, run_limit=1).watch
            if self._ransomware_target(task.source, current) != target:
                raise ValidationError("Ransomware izleme tanımı kaynak yenilenirken değişti.")
            report = watches.run(
                target.watch_id, item_limit=item_limit, expected_source_run_id=refresh.run.id,
            )
            if (
                not isinstance(report, expected_watch_report)
                or self._ransomware_target(task.source, report.watch) != target
                or report.run.watch_id != target.watch_id
                or report.run.source_run_id != refresh.run.id
            ):
                raise ValidationError("Ransomware izlemesi seçilen tanım ve kaynak yenilemesiyle uyuşmuyor.")
            normalize_knowledge_id(report.run.id, field="ransomware toplama izleme çalışma kimliği")
            reports.append(report)
        return CollectionStep(
            task, "complete", ransomware=CollectionRansomwareResult(refresh, tuple(reports), ()),
        )
