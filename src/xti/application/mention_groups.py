"""Explicit grouped collection with durable query reservations and local notices."""

from datetime import datetime, timedelta, timezone
from collections.abc import Callable
from dataclasses import replace

from xti.domain.assets import ValidationError
from xti.domain.mentions import MentionRequest, mention_uuid, request_key, validate_response
from xti.domain.mention_groups import (
    MentionGroupDefinition, validate_definition, normalize_group_name, validate_requests,
)
from xti.domain.scheduling import ScheduleSpec, normalize_schedule, normalize_retention
from xti.ports.discovery import SourceError
from xti.ports.mention_groups import MentionGroupRepository
from xti.ports.mentions import MentionRepository, MentionSource
from xti.ports.mention_targets import MentionTargetRepository
from xti.ports.mention_notifications import MentionNotificationBridge
from xti.ports.mention_group_scheduling import MentionScheduleFiles
from xti.ports.jobs import ExecutionLock
from xti.ports.scheduling import ScheduledBackupStore


class MentionGroupService:
    """Own the shared writer lock; delegated repositories never acquire it again."""

    def __init__(self, repository: MentionGroupRepository, mentions: MentionRepository,
                 targets: MentionTargetRepository, lock: ExecutionLock, *,
                 notifications: MentionNotificationBridge | None = None,
                 source_factory: Callable[[], MentionSource] | None = None,
                 files: MentionScheduleFiles | None = None,
                 backups: ScheduledBackupStore | None = None, clock=None):
        self.repository, self.mentions, self.targets, self.lock = repository, mentions, targets, lock
        self.notifications, self.source_factory = notifications, source_factory
        self.files, self.backups = files, backups
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self):
        at = self.clock()
        if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
            raise ValidationError("İzleme grubu zamanı saat dilimi içermeli.")
        try:
            return at.astimezone(timezone.utc).isoformat()
        except (ValueError, OverflowError) as error:
            raise ValidationError("İzleme grubu zamanı geçersiz.") from error

    @staticmethod
    def _page(offset, limit):
        if (type(offset) is not int or not 0 <= offset <= 1_000_000
                or type(limit) is not int or not 1 <= limit <= 500):
            raise ValidationError("Başlangıç 0–1.000.000, görünüm sınırı 1–500 olmalı.")

    def _requests(self, definition):
        definition = validate_definition(definition)
        selected = (("organization", definition.organization_id), *(
            ("supplier", identifier) for identifier in definition.supplier_ids))
        requests = []
        for kind, identifier in selected:
            target = self.targets.resolve(kind, identifier)
            if (target.kind, target.id) != (kind, identifier):
                raise ValidationError("İzleme grubunun hedefi seçilen kayıtla uyuşmuyor.")
            request = MentionRequest(target, definition.topic, definition.max_results)
            request_key(request)
            requests.append(request)
        return validate_requests(definition, tuple(requests))

    def save(self, name, definition):
        if (isinstance(definition, MentionGroupDefinition) and isinstance(definition.supplier_ids, tuple)
                and all(isinstance(value, str) for value in definition.supplier_ids)):
            definition = replace(definition, supplier_ids=tuple(sorted(definition.supplier_ids)))
        name, definition = normalize_group_name(name), validate_definition(definition)
        with self.lock.acquire():
            self._requests(definition)
            return self.repository.save(name, definition, recorded_at=self._now())

    def disable(self, identifier, *, reason):
        mention_uuid(identifier)
        with self.lock.acquire():
            return self.repository.disable(identifier, reason=reason, recorded_at=self._now())

    def list(self, *, active_only=True, offset=0, limit=20):
        self._page(offset, limit)
        if type(active_only) is not bool:
            raise ValidationError("Etkin grup seçimi doğru/yanlış olmalı.")
        groups = self.repository.list(active_only=active_only)
        return {"groups": groups[offset:offset + limit], "total_count": len(groups),
                "offset": offset, "has_more": offset + limit < len(groups)}

    def show(self, identifier):
        mention_uuid(identifier)
        group = self.repository.get(identifier)
        runs = self.repository.runs(identifier)
        return {"group": group, "budget": self.repository.budget(identifier, at=self._now()),
                "latest_run": runs[-1] if runs else None, "run_count": len(runs)}

    def runs(self, identifier, *, offset=0, limit=20):
        mention_uuid(identifier)
        self._page(offset, limit)
        runs = tuple(reversed(self.repository.runs(identifier)))
        return {"runs": runs[offset:offset + limit], "total_count": len(runs),
                "offset": offset, "has_more": offset + limit < len(runs)}

    def _plan(self, identifier, at):
        group = self.repository.get(identifier)
        if not group.active:
            raise ValidationError("İzleme grubu kapalı; yeni arama için yeniden kaydedin.")
        requests = self._requests(group.definition)
        history = self.repository.runs(identifier)
        latest = history[-1] if history else None
        observed = [group.updated_at]
        if latest is not None:
            observed.extend((latest.started_at, latest.finished_at or latest.started_at))
        if any(datetime.fromisoformat(at) < datetime.fromisoformat(previous) for previous in observed):
            raise ValidationError("İzleme saati kayıtlı geçmişten geriye gitti; işlem durduruldu.")
        next_due = (datetime.fromisoformat(latest.started_at) +
                    timedelta(hours=group.definition.interval_hours)).isoformat() if latest else None
        budget = self.repository.budget(identifier, at=at)
        reason = None
        if latest is not None and latest.status == "running":
            reason = "unfinished_run"
        elif next_due is not None and datetime.fromisoformat(at) < datetime.fromisoformat(next_due):
            reason = "not_due"
        elif budget.remaining_queries < len(requests):
            reason = "daily_budget"
        return {"group": group, "requests": requests, "planned_queries": len(requests),
                "budget": budget, "next_due_at": next_due, "ready": reason is None,
                "reason": reason, "unfinished_run_id": latest.id if reason == "unfinished_run" else None}

    def plan(self, identifier):
        mention_uuid(identifier)
        return self._plan(identifier, self._now())

    def _result(self, run, *, reason=None):
        budget = self.repository.budget(run.group_id, at=self._now())
        group = self.repository.get(run.group_id)
        latest = self.repository.runs(run.group_id)[-1]
        next_due = (datetime.fromisoformat(latest.started_at) +
                    timedelta(hours=group.definition.interval_hours)).isoformat()
        return {"status": run.status, "reason": reason, "run": run,
                "daily_queries_used": budget.used_queries, "budget": budget,
                "next_due_at": next_due}

    def _notify(self, run, attempt):
        if self.notifications is None:
            raise ValidationError("İzleme grubunun yerel bildirim bağlantısı yapılandırılmalı.")
        source_run = self.mentions.run_show(attempt.result_run_id)
        if source_run.status != "complete" or request_key(source_run.request) != request_key(attempt.request):
            raise ValidationError("Bildirim için kaynak kanıtı seçilen grup isteğiyle uyuşmuyor.")
        report = self.notifications.notify(group_id=run.group_id, request=attempt.request,
            mention_run_id=attempt.result_run_id, operation_id=attempt.id, executed_at=self._now())
        return self.repository.record_notification(run.id, attempt.index,
            notification_run_id=report.run.id, recorded_at=self._now())

    def run(self, identifier, *, request_id=None):
        mention_uuid(identifier)
        if request_id is not None:
            mention_uuid(request_id)
        with self.lock.acquire():
            if request_id is not None:
                previous = self.repository.find_run(request_id)
                if previous is not None:
                    if previous.group_id != identifier:
                        raise ValidationError("İstek kimliği başka bir izleme grubuna ait.")
                    return self._result(previous, reason="replayed")
            plan = self._plan(identifier, self._now())
            if not plan["ready"]:
                return {"status": "skipped", "reason": plan["reason"], "run": None,
                        "next_due_at": plan["next_due_at"], "budget": plan["budget"],
                        "daily_queries_used": plan["budget"].used_queries,
                        "unfinished_run_id": plan["unfinished_run_id"]}
            if self.source_factory is None or self.notifications is None:
                raise ValidationError("Grup araması için kaynak ve bildirim bağlantısı gerekli.")
            self.mentions.validate(max_results=plan["group"].definition.max_results,
                                   pending_runs=len(plan["requests"]))
            self.notifications.validate(group_id=identifier, requests=plan["requests"])
            # Missing/invalid credentials stop before a durable query reservation exists.
            source = self.source_factory()
            run = self.repository.begin(identifier, plan["requests"], started_at=self._now(),
                                        request_id=request_id)
            return self._execute(run, source=source)

    def resume(self, run_id):
        mention_uuid(run_id)
        with self.lock.acquire():
            run = self.repository.run_show(run_id)
            if run.status != "running":
                return self._result(run, reason="replayed")
            # A reservation without a result is ambiguous, never permission to repeat HTTP.
            run = self.repository.recover(run_id, recorded_at=self._now())
            return self._execute(run)

    def _execute(self, run, *, source=None):
        group = self.repository.get(run.group_id)
        pending = tuple(attempt for attempt in run.attempts if attempt.status == "pending")
        if pending:
            reason = None
            if not group.active:
                reason = "group_disabled"
            elif group.revision != run.group_revision:
                reason = "definition_changed"
            else:
                # Never silently collect a renamed, revoked or replaced entity after interruption.
                try:
                    current = self._requests(run.definition)
                    if tuple(map(request_key, current)) != tuple(request_key(a.request) for a in run.attempts):
                        reason = "target_changed"
                except ValidationError:
                    reason = "target_changed"
            if reason:
                run = self.repository.skip_pending(run.id, reason=reason, recorded_at=self._now())
        for index in range(len(run.attempts)):
            attempt = self.repository.run_show(run.id).attempts[index]
            if attempt.status == "complete":
                if attempt.notification_run_id is None:
                    run = self._notify(run, attempt)
                continue
            if attempt.status != "pending":
                continue
            at = self._now()
            if self.repository.budget(run.group_id, at=at).remaining_queries < 1:
                run = self.repository.skip_pending(run.id, reason="daily_budget", recorded_at=at)
                break
            self.mentions.validate(max_results=attempt.request.max_results)
            if self.notifications is None:
                raise ValidationError("Grup araması için bildirim bağlantısı gerekli.")
            self.notifications.validate(group_id=run.group_id, requests=(attempt.request,))
            if source is None:
                if self.source_factory is None:
                    raise ValidationError("Devam etmek için Tavily kaynağı gerekli.")
                source = self.source_factory()
            operation = self.repository.reserve_attempt(run.id, index, started_at=self._now())
            attempt = self.repository.run_show(run.id).attempts[index]
            try:
                response = source.fetch(attempt.request)
                try:
                    validate_response(response, attempt.request)
                except ValidationError:
                    raise SourceError("Tavily yanıtı beklenen grup arama kapsamıyla uyuşmuyor.") from None
            except SourceError as error:
                self.mentions.record_failure(attempt.request, error=str(error), started_at=attempt.started_at,
                                             finished_at=self._now(), operation=operation)
                # A source outage should not consume the entire group's remaining query budget.
                run = self.repository.skip_pending(run.id, reason="source_failed", recorded_at=self._now())
                break
            self.mentions.apply(attempt.request, response, started_at=attempt.started_at,
                                finished_at=self._now(), operation=operation)
            run = self.repository.run_show(run.id)
            self._notify(run, run.attempts[index])
        return self._result(self.repository.finish(run.id, finished_at=self._now()))

    def run_show(self, run_id):
        mention_uuid(run_id)
        run = self.repository.run_show(run_id)
        # Source details stay available through their immutable ordinary mentions run IDs.
        return self._result(run)

    def generate(self, identifier, *, output, at, timezone="UTC", weekday=None, keep=7, api_key_file=None):
        mention_uuid(identifier)
        if self.files is None:
            raise ValidationError("Linux zamanlama dosyası yazıcısı yapılandırılmalı.")
        spec = normalize_schedule(ScheduleSpec(at, timezone, weekday, keep))
        plan = self.plan(identifier)
        return self.files.publish(plan["group"], output=output, spec=spec, api_key_file=api_key_file)

    def prepare(self, identifier, *, keep=7, calendar_hours=None):
        mention_uuid(identifier)
        keep = normalize_retention(keep)
        if calendar_hours is not None and (type(calendar_hours) is not int or calendar_hours not in {24, 168}):
            raise ValidationError("Takvim dönemi günlük 24 veya haftalık 168 saat olmalı.")
        if self.backups is None:
            raise ValidationError("Zamanlanmış yedek deposu yapılandırılmalı.")
        with self.lock.acquire():
            plan = self._plan(identifier, self._now())
            if calendar_hours is not None and plan["group"].definition.interval_hours >= calendar_hours:
                raise ValidationError("Grup aralığı zamanlayıcının takvim döneminden kısa olmalı; grup tanımını ve zamanlamayı güncelleyin.")
            if plan["reason"] == "unfinished_run":
                raise ValidationError("Kesilmiş grup çalışması var; önce mentions groups resume ile inceleyip tamamlayın.")
            self.backups.preflight(keep=keep)
            backup = self.backups.backup_and_prune(profile_id=identifier, recorded_at=self._now(), keep=keep)
            return {"group": plan["group"], "backup": backup}
