"""Shared P05 service for terminal, engine, company platform and source jobs."""

from __future__ import annotations

from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.darkweb_monitoring import (
    DarkwebError,
    PREFIX,
    READS,
    analyse,
    parameters,
    sanitize_credential_accounts,
)
from xti.ports.darkweb_monitoring import (
    CredentialDomainSource,
    CredentialSecrets,
    DarkwebInputs,
    DarkwebRepository,
    PasswordExposureSource,
)


class DarkwebService:
    def __init__(self, repository: DarkwebRepository, inputs: DarkwebInputs,
                 credential_source: CredentialDomainSource,
                 credential_secrets: CredentialSecrets,
                 password_source: PasswordExposureSource | None = None, *, now=None) -> None:
        self.repository = repository
        self.inputs = inputs
        self.credential_source = credential_source
        self.credential_secrets = credential_secrets
        self.password_source = password_source
        self.now = now or (lambda: datetime.now(timezone.utc).isoformat())

    def execute(self, operation: str, **values) -> dict:
        values = parameters(operation, values)
        if operation in READS:
            return self.repository.read(operation, values)
        if operation == PREFIX + "credential.refresh":
            return self._credential_refresh(values)
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

    def _credential_refresh(self, values: dict) -> dict:
        plan = self.repository.credential_plan(values["identifier"], values["domain"])
        replay = self.repository.credential_replay(plan, values["idempotency_key"])
        if replay is not None:
            return {**replay, "replayed": True}
        # Read secrets before reservation; missing configuration performs no paid request
        # and does not leave a durable running receipt.
        api_key = self.credential_secrets.api_key()
        identity_key = self.credential_secrets.identity_key(plan["organization"]["id"])
        run, replayed = self.repository.reserve_credentials(
            plan, values["idempotency_key"], self.now(),
        )
        if replayed:
            return {**run, "replayed": True}
        try:
            response = self.credential_source.fetch(plan["domain"], api_key)
            # This is the only raw-alias boundary.  The raw object is discarded
            # before any repository, JSON response or log receives the value.
            records = sanitize_credential_accounts(
                response.pop("accounts"), plan["domain"], identity_key,
            )
            return self.repository.finish_credentials(run["id"], response, records, self.now())
        except BaseException as error:
            code = getattr(error, "code", "credential_refresh_failed")
            provider_messages = {
                "missing_or_invalid_key": (
                    "XposedOrNot API anahtarı eksik/geçersiz veya doğrulanmış domain kapsamı yok."
                ),
                "domain_not_verified": (
                    "Domain bu XposedOrNot anahtarının doğrulanmış kapsamında değil."
                ),
                "rate_limited": "XposedOrNot istek sınırına ulaşıldı; daha sonra yeniden deneyin.",
                "source_unavailable": (
                    "XposedOrNot domain kaynağına güvenli bağlantı tamamlanamadı; "
                    "önceki kanıt korunuyor."
                ),
                "source_unexpected": "XposedOrNot beklenen sabit HTTPS yanıtını vermedi.",
                "source_invalid": (
                    "XposedOrNot domain yanıtı geçersiz veya güvenli sınırları aşıyor."
                ),
                "source_too_large": "XposedOrNot domain yanıtı güvenli boyut sınırını aşıyor.",
                "source_timeout": "XposedOrNot domain yanıtı okuma süresini aştı.",
                "clock_error": "XposedOrNot kaynak zamanı doğrulanamadı.",
            }
            if isinstance(error, DarkwebError):
                message = error.message
            elif str(code) in provider_messages:
                message = provider_messages[str(code)]
            elif isinstance(error, ValidationError):
                message = str(error)
            else:
                message = "Credential kaynağı güvenle tamamlanamadı; önceki kanıt korunuyor."
            self.repository.fail_credentials(
                run["id"], code, message, self.now(),
            )
            if isinstance(error, Exception) and not isinstance(error, DarkwebError):
                raise DarkwebError(str(code)[:80], str(message)[:500]) from error
            raise

    def check_password(self, password: str) -> dict:
        """Perform one non-persistent local-hash password check."""
        if self.password_source is None:
            raise DarkwebError(
                "source_unavailable", "XposedOrNot parola kaynağı yapılandırılmamış."
            )
        try:
            return self.password_source.check_password(password)
        except Exception as error:
            code = str(getattr(error, "code", "password_check_failed"))[:80]
            messages = {
                "rate_limited": "XposedOrNot parola istek sınırına ulaşıldı.",
                "source_unavailable": (
                    "XposedOrNot parola kaynağına güvenli bağlantı tamamlanamadı."
                ),
                "source_unexpected": "XposedOrNot beklenen sabit HTTPS yanıtını vermedi.",
                "source_invalid": "XposedOrNot parola yanıtı güvenli biçimde doğrulanamadı.",
                "source_too_large": "XposedOrNot parola yanıtı güvenli boyut sınırını aşıyor.",
                "source_timeout": "XposedOrNot parola yanıtı okuma süresini aştı.",
                "clock_error": "XposedOrNot parola kontrol zamanı doğrulanamadı.",
            }
            if isinstance(error, ValidationError):
                message = str(error)
            else:
                message = messages.get(code, "Parola maruziyet kontrolü güvenle tamamlanamadı.")
            raise DarkwebError(code, message) from error
