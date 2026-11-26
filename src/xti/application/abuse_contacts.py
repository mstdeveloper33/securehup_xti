"""Application orchestration for passive, human-reviewed abuse contacts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.abuse_contact_contract import PREFIX, READS, parameters
from xti.domain.abuse_contacts import AbuseContactError
from xti.domain.assets import ValidationError
from xti.ports.abuse_contacts import AbuseContactRepository, AbuseContactSource


class AbuseContactService:
    def __init__(
        self, repository: AbuseContactRepository, source: AbuseContactSource,
        *, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.source = source
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Abuse iletişim işlem saati geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    def capabilities(self) -> dict:
        local = self.source.local_capabilities()
        return {
            "contract_version": 1,
            "sources": {
                "domain_rdap": {"selected": True, "cost": "free", "role": "registrar abuse contact"},
                "ip_rdap": {"selected": True, "cost": "free", "role": "network abuse contact"},
                "security_txt": {"selected": True, "cost": "free", "role": "auxiliary security contact", "trust": "low"},
                "whois": {
                    "selected": True, "cost": "local_tool", "role": "fallback_only",
                    "required": False, "available": local["whois_available"],
                },
                "abuseipdb": {"selected": False, "reason": "reputation source, not authoritative contact directory"},
            },
            "persistence": {
                "runs": True, "source_receipts": True, "candidate_history": True,
                "review_history": True, "failed_run_preserves_last_success": True,
            },
            "review": {"required_for_takedown": True, "stale_after_candidate_change": True},
            "monitoring": {"saved_watch": True, "due_query": True, "bounded_terminal_monitor": True},
            "automatic_submission": False,
            "raw_provider_response_persisted": False,
            "registrant_personal_data_collected": False,
        }

    def execute(self, operation: str, **values) -> dict:
        values = parameters(operation, values)
        if operation == PREFIX + "capabilities":
            return self.capabilities()
        at = self._now()
        if operation in READS:
            return self.repository.read(operation, values, at)
        if operation != PREFIX + "refresh":
            return self.repository.mutate(operation, values, at)
        reservation, replayed = self.repository.reserve_run(values, at)
        if replayed:
            return {**reservation, "replayed": True}
        run_id, watch = reservation["id"], reservation["watch"]
        try:
            outcomes = self.source.collect(
                watch["subject_kind"], watch["subject_value"],
                include_whois=watch["include_whois"],
                timeout_seconds=reservation["timeout_seconds"],
            )
            return {**self.repository.finish_run(run_id, outcomes, self._now()), "replayed": False}
        except Exception as error:
            if isinstance(error, AbuseContactError):
                code, message = error.code, error.message
            elif isinstance(error, ValidationError):
                code, message = "validation_error", str(error)
            else:
                code = "collection_failed"
                message = "Abuse iletişim kaynakları güvenli biçimde tamamlanamadı; önceki kanıt korundu."
            self.repository.fail_run(run_id, code, message, self._now())
            if not isinstance(error, AbuseContactError):
                raise AbuseContactError(code, message) from error
            raise
