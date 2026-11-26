"""Shared P05 service for terminal, engine, company platform and source jobs."""

from __future__ import annotations

from datetime import datetime, timezone

from xti.domain.darkweb_monitoring import (
    DarkwebError,
    PREFIX,
    READS,
    analyse,
    parameters,
)
from xti.ports.darkweb_monitoring import (
    DarkwebInputs,
    DarkwebRepository,
    DomainExposureSource,
)


class DarkwebService:
    def __init__(self, repository: DarkwebRepository, inputs: DarkwebInputs,
                 domain_exposure_source: DomainExposureSource | None = None, *, now=None) -> None:
        self.repository = repository
        self.inputs = inputs
        self.domain_exposure_source = domain_exposure_source
        self.now = now or (lambda: datetime.now(timezone.utc).isoformat())

    def execute(self, operation: str, **values) -> dict:
        values = parameters(operation, values)
        if operation == PREFIX + "ail.preview":
            plan = self.repository.source_plan(values["identifier"], "ail_tracker")
            from xti.domain.darkweb_source_intake import normalize_ail_batch
            normalized = normalize_ail_batch(values["batch"], plan["organization"])
            return {
                "contract_version": 1, "provider": "ail_tracker",
                "profile_id": plan["profile"]["id"],
                "profile_revision": plan["profile"]["revision"],
                "record_count": len(normalized["records"]),
                "content_sha256": normalized["content_sha256"],
                "raw_content_stored": False, "source_addresses_stored": False,
                "ready_to_import": True,
            }
        if operation in READS:
            return self.repository.read(operation, values)
        if operation == PREFIX + "lunar.refresh":
            return self._lunar_refresh(values)
        if operation == PREFIX + "ail.import":
            return self._ail_import(values)
        if operation != PREFIX + "run":
            return self.repository.mutate(operation, values, self.now())
        replay = self.repository.replay(values)
        if replay is not None:
            return {**replay, "replayed": True}
        plan = self.repository.plan(values["identifier"])
        if plan["profile"]["revision"] != values["expected_revision"]:
            from xti.domain.darkweb_monitoring import DarkwebError
            raise DarkwebError("revision_conflict", "Dark web profili değişti; planı yeniden okuyun.")
        snapshot = self.inputs.capture(plan, self.now())
        run, replayed = self.repository.reserve(values, snapshot, self.now())
        if replayed:
            return {**run, "replayed": True}
        try:
            return self.repository.finish(run["id"], analyse(snapshot), self.now())
        except BaseException as error:
            self.repository.fail(run["id"], getattr(error, "code", "analysis_failed"), self.now())
            raise
    def _lunar_refresh(self, values: dict) -> dict:
        replay = self.repository.source_replay(PREFIX + "lunar.refresh", values)
        if replay is not None:
            return {**replay, "replayed": True}
        if self.domain_exposure_source is None:
            raise DarkwebError("source_unavailable", "Lunar domain kaynağı yapılandırılmamış.")
        plan = self.repository.source_plan(values["identifier"], "lunar_domain", values["domain"])
        if plan["profile"]["revision"] != values["expected_revision"]:
            raise DarkwebError("revision_conflict", "Dark web profili değişti; planı yeniden okuyun.")
        metadata = {
            "provider": "lunar_domain", "mode": "snapshot", "target": values["domain"],
            "source_reference": "https://docs.webz.io/docs/webz/dea-introduction",
        }
        run, replayed = self.repository.reserve_source(
            PREFIX + "lunar.refresh", values, plan, metadata, self.now(),
        )
        if replayed:
            return {**run, "replayed": True}
        try:
            response = self.domain_exposure_source.fetch(values["domain"])
            if response.get("domain") != values["domain"]:
                raise DarkwebError("source_invalid", "Lunar yanıtı istenen domain kapsamıyla uyuşmuyor.")
            return self.repository.finish_source(run["id"], response, self.now())
        except BaseException as error:
            code = str(getattr(error, "code", "source_refresh_failed"))[:80]
            messages = {
                "source_not_authorized": "Lunar bu domain için toplu rapor üretimine izin vermedi.",
                "rate_limited": "Lunar kullanım sınırına ulaşıldı; daha sonra yeniden deneyin.",
                "source_unavailable": "Lunar kaynağına ulaşılamadı; önceki başarılı kanıt korunuyor.",
                "source_unexpected": "Lunar beklenen sabit HTTPS yanıtını vermedi.",
                "source_invalid": "Lunar yanıtı geçersiz veya kuruluş kapsamıyla uyuşmuyor.",
                "source_too_large": "Lunar yanıtı güvenli boyut sınırını aşıyor.",
                "source_timeout": "Lunar yanıtı süre sınırını aştı.",
                "clock_error": "Lunar kaynak zamanı doğrulanamadı.",
            }
            message = error.message if isinstance(error, DarkwebError) else messages.get(
                code, "Lunar kaynağı güvenle tamamlanamadı; önceki kanıt korunuyor."
            )
            self.repository.fail_source(run["id"], code, message, self.now())
            if isinstance(error, Exception) and not isinstance(error, DarkwebError):
                raise DarkwebError(code, message) from error
            raise
    def _ail_import(self, values: dict) -> dict:
        replay = self.repository.source_replay(PREFIX + "ail.import", values)
        if replay is not None:
            return {**replay, "replayed": True}
        plan = self.repository.source_plan(values["identifier"], "ail_tracker")
        if plan["profile"]["revision"] != values["expected_revision"]:
            raise DarkwebError("revision_conflict", "Dark web profili değişti; planı yeniden okuyun.")
        from xti.domain.darkweb_source_intake import normalize_ail_batch
        normalized = normalize_ail_batch(values["batch"], plan["organization"])
        if normalized["content_sha256"] != values["expected_content_sha256"]:
            raise DarkwebError(
                "content_changed", "AIL zarfı önizlemeden sonra değişti; yeniden önizleyin."
            )
        metadata = {
            "provider": "ail_tracker", "mode": "incremental",
            "target": plan["organization"]["organization_id"],
            "source_reference": normalized["source_reference"],
        }
        run, replayed = self.repository.reserve_source(
            PREFIX + "ail.import", values, plan, metadata, self.now(),
        )
        if replayed:
            return {**run, "replayed": True}
        response = {
            **normalized, "status": "complete", "fetched_at": self.now(),
        }
        try:
            return self.repository.finish_source(run["id"], response, self.now())
        except BaseException as error:
            code = str(getattr(error, "code", "ail_import_failed"))[:80]
            message = (
                error.message if isinstance(error, DarkwebError)
                else "AIL metadata zarfı atomik olarak içe alınamadı; önceki kanıt korunuyor."
            )
            self.repository.fail_source(run["id"], code, message, self.now())
            if isinstance(error, Exception) and not isinstance(error, DarkwebError):
                raise DarkwebError(code, message) from error
            raise
