"""Durable, source-bound collection sessions and explicit incomplete-work retry."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from xti.application.collection import CollectionService
from xti.application.collection_profiles import collection_options
from xti.domain.analysis import UnifiedAnalysisReport
from xti.domain.assets import ValidationError
from xti.domain.collection import (
    COLLECTION_TASK_IDS, DEFAULT_COLLECTION_TASKS, CollectionPlan, CollectionResult,
    CollectionRansomwareResult, CollectionStep,
)
from xti.domain.collection_history import (
    CollectionFrozenPlan, CollectionFrozenUnit, CollectionOperationToken,
    CollectionResumePlan, CollectionSessionDetails, CollectionSessionPage,
    freeze_collection_plan, username_contract,
)
from xti.domain.collection_profiles import (
    CollectionProfile, CollectionProfileDefinition, normalize_profile_definition,
)
from xti.domain.public_notices import HIBP_CONTRACT_VERSION
from xti.domain.news import NEWS_POLICY
from xti.domain.global_saved_searches import GLOBAL_SEARCH_WATCH_VERSION
from xti.ports.collection_history import CollectionHistoryRepository
from xti.ports.jobs import ExecutionLock


@dataclass(frozen=True, slots=True)
class CollectionResumeResult:
    history: CollectionSessionDetails
    analysis: UnifiedAnalysisReport
    notes: tuple[str, ...] = (
        "Tamamlanan kaynak kayıtları eski yürütmeden korunur; yalnız eksik işler yeniden çalıştırılır.",
        "Analiz şimdiki yerel kayıtlardan üretilir; eski oturumun analiz snapshot'ı değildir.",
    )


class CollectionHistoryService:
    def __init__(
        self, repository: CollectionHistoryRepository,
        collection_factory: Callable[[CollectionProfileDefinition], CollectionService],
        lock: ExecutionLock, *, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.collection_factory = collection_factory
        self.lock = lock
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Toplama zamanı saat dilimi bilgili olmalı.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _definition(domain: str, **options) -> CollectionProfileDefinition:
        tasks = options.pop("tasks", None)
        return normalize_profile_definition(CollectionProfileDefinition(
            asset_value=domain,
            task_ids=DEFAULT_COLLECTION_TASKS if tasks is None else tasks,
            **options,
        ))

    @staticmethod
    def _contracts(collection: CollectionService, plan: CollectionPlan) -> dict[str, str]:
        contracts = {}
        for task in plan.tasks:
            if task.kind == "scan":
                contract = collection.jobs.discoveries[task.source].matcher.rule_version
            elif task.kind == "username_watch":
                source = collection.watch_collection.username.sources[task.source]
                contract = username_contract(source.source_version, source.integration_profile)
            elif task.kind == "public_notice":
                contract = HIBP_CONTRACT_VERSION
            elif task.kind == "news_refresh":
                contract = NEWS_POLICY
            elif task.kind == "search_watch":
                contract = GLOBAL_SEARCH_WATCH_VERSION
            else:
                contract = f"collection-source-v1:{task.kind}:{task.source}"
            contracts[task.id] = contract
        return contracts

    @staticmethod
    def _recorded_plan(plan: CollectionPlan) -> CollectionPlan:
        notes = tuple(note for note in plan.notes if "ayrı oturum kaydı" not in note)
        return replace(plan, notes=notes + (
            "Kaynak çalışmaları birleşik oturumda kimlikleriyle saklanır; eksik işler açık seçimle tekrar denenebilir.",
        ))

    def plan(self, domain: str, **options) -> CollectionPlan:
        definition = self._definition(domain, **options)
        collection = self.collection_factory(definition)
        return self._recorded_plan(collection.plan(domain, **collection_options(definition)))

    def list(self, *, limit: int = 50, before: int | None = None) -> CollectionSessionPage:
        return self.repository.list(limit=limit, before=before)

    def show(self, session_id: str) -> CollectionSessionDetails:
        return self.repository.get(session_id)

    def recover(self) -> tuple[str, ...]:
        self.repository.list(limit=1)
        with self.lock.acquire():
            return self.repository.recover_interrupted(recorded_at=self._now())

    def run(
        self, domain: str, *, tasks: Sequence[str] | None = None,
        typos: bool = False, stale_after_hours: int = 24, finding_limit: int = 10,
        username_watch_ids: Sequence[str] = (), ransomware_watch_ids: Sequence[str] = (),
        ransomlook_watch_ids: Sequence[str] = (), watch_item_limit: int = 100,
        news_sources: Sequence[str] = (), search_watch_ids: Sequence[str] = (),
        progress: Callable[[str], None] | None = None,
        preflight: Callable[[], None] | None = None,
        profile: CollectionProfile | None = None,
    ) -> CollectionResult:
        definition = self._definition(
            domain, tasks=tasks, typos=typos, stale_after_hours=stale_after_hours,
            finding_limit=finding_limit, username_watch_ids=username_watch_ids,
            ransomware_watch_ids=ransomware_watch_ids, ransomlook_watch_ids=ransomlook_watch_ids,
            watch_item_limit=watch_item_limit,
            news_sources=news_sources, search_watch_ids=search_watch_ids,
        )
        if profile is not None and profile.definition != definition:
            raise ValidationError("Toplama seçimi kaynak profille uyuşmuyor.")
        if preflight is not None:
            preflight()
        self.repository.list(limit=1)
        collection = self.collection_factory(definition)
        collection.plan(definition.asset_value, **collection_options(definition))
        with self.lock.acquire():
            if preflight is not None:
                preflight()
            plan = self._recorded_plan(collection.plan(definition.asset_value, **collection_options(definition)))
            origin = self.repository.profile_origin(profile) if profile is not None else None
            frozen = freeze_collection_plan(
                definition, plan, contracts=self._contracts(collection, plan), origin=origin,
            )
            self.repository.recover_interrupted(recorded_at=self._now())
            details, steps, analysis = self._execute(collection, plan, frozen, progress=progress)
        return CollectionResult(
            plan, details.session.started_at, details.session.finished_at,
            details.session.status, steps, analysis, session_id=details.session.id,
        )

    @staticmethod
    def _selection_for_units(
        definition: CollectionProfileDefinition, units: tuple[CollectionFrozenUnit, ...],
    ) -> CollectionProfileDefinition:
        tasks = tuple(unit.step_key for unit in units if unit.step_key in COLLECTION_TASK_IDS)
        ids = lambda kind, source=None: tuple(
            unit.watch.watch_id for unit in units
            if unit.kind == kind and unit.watch is not None and (source is None or unit.source == source)
        )
        return replace(
            definition, task_ids=tasks,
            typos=definition.typos and any(task.startswith("scan-") for task in tasks),
            username_watch_ids=ids("username_watch"),
            ransomware_watch_ids=ids("ransomware_watch", "threatcluster"),
            ransomlook_watch_ids=ids("ransomware_watch", "ransomlook"),
            news_sources=tuple(unit.source for unit in units if unit.kind == "news_refresh"),
            search_watch_ids=ids("search_watch"),
        )

    def _resume_context(self, resume: CollectionResumePlan):
        partial = self._selection_for_units(resume.parent.plan.definition, resume.units)
        collection = self.collection_factory(partial)
        plan = collection.plan(partial.asset_value, allow_empty_base=True, **collection_options(partial))
        contracts = self._contracts(collection, plan)
        current = {}
        for task in plan.tasks:
            if task.kind == "ransomware":
                key = f"ransomware-refresh:{task.source}"
                current[key] = CollectionFrozenUnit(key, "ransomware_refresh", task.source, plan.asset_value, None, contracts[task.id])
                for watch in task.watches:
                    key = f"ransomware-watch:{task.source}:{watch.watch_id}"
                    current[key] = CollectionFrozenUnit(key, "ransomware_watch", task.source, plan.asset_value, watch, contracts[task.id])
            else:
                current[task.id] = CollectionFrozenUnit(
                    task.id, task.kind, task.source, plan.asset_value,
                    task.watches[0] if task.watches else None, contracts[task.id],
                )
        if tuple(current.values()) != resume.units:
            raise ValidationError("Eksik işlerin tanımı veya kaynak sürümü değişmiş; güncel seçimle yeni toplama başlatın.")
        return collection, self._recorded_plan(plan)

    def resume_plan(self, session_id: str) -> CollectionResumePlan:
        resume = self.repository.resume_plan(session_id)
        self._resume_context(resume)
        return resume

    def resume(
        self, session_id: str, *, progress: Callable[[str], None] | None = None,
    ) -> CollectionResumeResult:
        self.repository.get(session_id)
        with self.lock.acquire():
            self.repository.recover_interrupted(recorded_at=self._now())
            resume = self.repository.resume_plan(session_id)
            collection, plan = self._resume_context(resume)
            details, _, analysis = self._execute(
                collection, plan, resume.parent.plan, parent_id=session_id, progress=progress,
            )
        return CollectionResumeResult(details, analysis)

    def _execute(
        self, collection: CollectionService, plan: CollectionPlan, frozen: CollectionFrozenPlan, *,
        parent_id: str | None = None, progress: Callable[[str], None] | None = None,
    ) -> tuple[CollectionSessionDetails, tuple[CollectionStep, ...], UnifiedAnalysisReport]:
        details = self.repository.begin(frozen, started_at=self._now(), parent_id=parent_id)
        session_id = details.session.id
        steps = []
        refreshes = {}
        watch_reports = {}
        skipped = {}
        analyzing = False
        try:
            if progress:
                progress(f"Toplama oturumu: {session_id}")
            units = {unit.step_key: unit for unit in frozen.units}
            tasks = {task.id: task for task in plan.tasks}
            ransomware_tasks = {task.source: task for task in plan.tasks if task.kind == "ransomware"}
            for stored_step in details.steps:
                unit = units[stored_step.step_key]
                if unit.kind == "search_watch":
                    token = CollectionOperationToken(
                        session_id, stored_step.id, stored_step.target_sha256, stored_step.depends_on_step_id,
                    )
                    if collection.news_searches is None:
                        raise ValidationError("Kayıtlı haber araması bağlantısı yapılandırılmamış.")
                    if not collection.news_searches.ready(token):
                        self.repository.stop_step_without_result(
                            token, status="skipped", error_code="dependency_failed", finished_at=self._now(),
                        )
                        steps.append(CollectionStep(tasks[unit.step_key], "skipped"))
                        continue
                if unit.kind == "ransomware_watch" and refreshes[unit.source].run.status != "complete":
                    token = CollectionOperationToken(
                        session_id, stored_step.id, stored_step.target_sha256, stored_step.depends_on_step_id,
                    )
                    self.repository.stop_step_without_result(
                        token, status="skipped", error_code="dependency_failed", finished_at=self._now(),
                    )
                    skipped.setdefault(unit.source, []).append(unit.watch.watch_id)
                    continue
                token = self.repository.start_step(session_id, stored_step.id, started_at=self._now())
                if progress:
                    progress(f"Toplama: {unit.step_key}")
                if unit.kind in {"scan", "discovery", "ioc", "public_notice", "news_refresh", "search_watch"}:
                    steps.append(collection._collect(tasks[unit.step_key], plan, progress, operation=token))
                elif unit.kind == "username_watch":
                    task = tasks[unit.step_key]
                    report = collection.watch_collection.run_username(task, item_limit=plan.watch_item_limit, operation=token)
                    steps.append(CollectionStep(task, report.run.status, username=report))
                elif unit.kind == "ransomware_refresh":
                    refreshes[unit.source] = collection.watch_collection.refresh(
                        ransomware_tasks[unit.source], item_limit=plan.watch_item_limit, operation=token,
                    )
                else:
                    report = collection.watch_collection.run_ransomware_watch(
                        ransomware_tasks[unit.source], unit.watch, refreshes[unit.source].run.id,
                        item_limit=plan.watch_item_limit, operation=token,
                    )
                    watch_reports.setdefault(unit.source, []).append(report)
            for source, task in ransomware_tasks.items():
                refresh = refreshes[source]
                steps.append(CollectionStep(
                    task, refresh.run.status, ransomware=CollectionRansomwareResult(
                        refresh, tuple(watch_reports.get(source, ())), tuple(skipped.get(source, ())),
                    ),
                ))
            analyzing = True
            analysis = collection.analysis.show(
                frozen.definition.asset_value, stale_after_hours=frozen.definition.stale_after_hours,
                finding_limit=frozen.definition.finding_limit,
            )
            if analysis.asset_value != frozen.definition.asset_value:
                raise ValidationError("Toplama sonrası analiz seçilen domainle uyuşmuyor.")
            details = self.repository.finish_session(session_id, analysis_status="complete", finished_at=self._now())
            return details, tuple(steps), analysis
        except BaseException as error:
            reason = "interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit)) else (
                "analysis_failed" if analyzing else "execution_failed"
            )
            try:
                self.repository.finish_session(
                    session_id, analysis_status="failed" if analyzing else "pending",
                    finished_at=self._now(), stop_reason=reason,
                )
            except Exception:
                # If storage itself is unavailable, the next locked recovery
                # preserves all already committed source receipts.
                pass
            raise
