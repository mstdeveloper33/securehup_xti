"""Explicit admission/worker/recovery with per-target durable at-most-once dispatch."""

from datetime import datetime, timezone
import time
from uuid import uuid4

from xti.domain.assets import ValidationError
from xti.domain.engine_jobs import job_time, request_key
from xti.domain.nmap_execution import empty_result, validate_result
from xti.domain.nmap_management import target_addresses
from xti.domain.nmap_options import NmapExecutionOptions
from xti.ports.nmap_execution import ManagedNmapRunner, NmapWorkRepository


class NmapExecutionService:
    def __init__(self, management, repository: NmapWorkRepository, lock,
                 runner: ManagedNmapRunner | None = None, *, clock=None, monotonic=None):
        self.management, self.repository, self.lock, self.runner = management, repository, lock, runner
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic

    def _now(self):
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValidationError("Nmap çalışma saati saat dilimi bilgili olmalı.")
        return job_time(value.astimezone(timezone.utc).isoformat())

    def _asset(self, domain):
        return self.management._asset(domain)

    def _authorized(self, plan):
        asset = self._asset(plan.asset_value)
        self.management._scope(asset, require_active=True)
        target = self.management.repository.get_target(asset.id, plan.target_scope_name)
        if (not target.active or target.id != plan.definition.target_scope_id
                or target.revision != plan.definition.target_scope_revision
                or target.definition_sha256 != plan.definition.target_definition_sha256):
            raise ValidationError("Nmap hedef yetkisi/sürümü değişti; güncel hedefle yeni plan oluşturun.")

    def submit(self, domain, plan_id, key):
        request_key(key)
        asset = self._asset(domain)
        previous = self.repository.find_request(asset.id, key)
        if previous:
            if previous.plan.id != plan_id:
                raise ValidationError("Tekrar önleme anahtarı başka Nmap planına bağlı.")
            return previous
        with self.lock.acquire():
            plan = self.management.show_plan(domain, plan_id)
            self._authorized(plan)
            return self.repository.create(plan, key, self._now())

    def show(self, domain, job_id):
        return self.repository.get(self._asset(domain).id, job_id)

    def list(self, domain, *, limit=20, offset=0):
        return self.repository.list(self._asset(domain).id, limit=limit, offset=offset)

    def cancel(self, domain, job_id):
        work = self.show(domain, job_id)
        return self.repository.append(work, "cancel", {}, self._now(), token=None)

    def resume(self, domain, job_id):
        with self.lock.acquire():
            work = self.show(domain, job_id)
            self.repository.check_binding(work)
            self._authorized(work.plan)
            return self.repository.append(work, "resumed", {}, self._now(), token=None)

    def _close(self, work, status):
        return self.repository.append(work, "finished", {"status": status}, self._now(), token=work.token)

    def _interrupt(self, work):
        work = self.repository.get(work.plan.asset_id, work.id)
        if work.status != "running":
            return work
        if work.started_count > len(work.results):
            address = target_addresses(work.plan.definition.target_definition)[len(work.results)]
            work = self.repository.append(work, "target_finished", {"result": empty_result(
                address, "interrupted", "İş kesildi; hedef sonucu belirsiz ve otomatik tekrar edilmeyecek.")},
                self._now(), token=work.token)
        return self._close(work, "cancelled" if work.cancel_requested else "interrupted")

    def recover(self, domain, job_id):
        # The process inherits this lock. A surviving Nmap child blocks recovery.
        with self.lock.acquire():
            return self._interrupt(self.show(domain, job_id))

    def work(self, domain, job_id):
        if self.runner is None:
            raise ValidationError("Nmap çalıştırıcısı yapılandırılmadı.")
        with self.lock.acquire() as lock_fd:
            work = self.show(domain, job_id)
            if work.status != "queued":
                raise ValidationError("Yalnız kuyruktaki Nmap işi çalıştırılabilir.")
            self.repository.check_binding(work)
            self._authorized(work.plan)
            self.runner.readiness(work.plan)
            work = self.repository.append(work, "claimed", {}, self._now(), token=str(uuid4()))
            options = work.plan.definition.options or NmapExecutionOptions()
            deadline = self.monotonic() + options.max_duration_seconds
            try:
                addresses = target_addresses(work.plan.definition.target_definition)
                for index in range(work.started_count, len(addresses)):
                    if self.repository.cancelled(work.plan.asset_id, work.id):
                        return self._close(work, "cancelled")
                    remaining = deadline - self.monotonic()
                    if remaining <= 0:
                        return self._close(work, "interrupted")
                    self._authorized(work.plan)
                    address = addresses[index]
                    work = self.repository.append(work, "target_started", {"index": index, "address": address},
                                                  self._now(), token=work.token)
                    result = self.runner.run(work.plan, address, lock_fd=lock_fd,
                        duration_seconds=remaining,
                        should_stop=lambda: self.repository.cancelled(work.plan.asset_id, work.id))
                    validate_result(result, work.plan, address)
                    work = self.repository.append(work, "target_finished", {"result": result}, self._now(), token=work.token)
                    if work.cancel_requested:
                        return self._close(work, "cancelled")
                status = "complete" if all(r["status"] == "complete" for r in work.results) else "partial"
                if all(r["status"] not in {"complete", "partial"} for r in work.results):
                    status = "failed"
                return self._close(work, status)
            except BaseException:
                # Never turn uncertain delivery into an automatic retry.
                try:
                    self._interrupt(work)
                except Exception:
                    pass  # The persistent running state remains explicitly recoverable.
                raise
