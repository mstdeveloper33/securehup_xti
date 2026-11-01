"""Explicit webhook queueing, signing and delivery orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import hmac
from uuid import uuid4

from xti.domain.assets import ValidationError
from xti.domain.inbox import InboxDetails
from xti.domain.webhooks import (
    MAX_WEBHOOK_ATTEMPTS,
    WEBHOOK_DELIVERY_STATUSES,
    WebhookDelivery,
    WebhookDeliveryDetails,
    WebhookDeliveryPage,
    WebhookDeliveryResult,
    WebhookDestination,
    WebhookDestinationMutation,
    canonical_webhook_payload,
    normalize_webhook_name,
    normalize_webhook_url,
    webhook_name_key,
)
from xti.ports.inbox import NotificationRepository
from xti.ports.webhooks import WebhookRepository, WebhookSender


def _identifier(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > 64
        or not value.isprintable() or value.isspace()
    ):
        raise ValidationError(f"Geçerli bir {label} kimliği gerekli.")
    return value


class WebhookService:
    def __init__(
        self, repository: WebhookRepository, inbox: NotificationRepository,
        sender: WebhookSender,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.inbox = inbox
        self.sender = sender
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        try:
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("timezone required")
            return value.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Webhook işlemi için saat dilimi belli geçerli zaman gerekli.") from error

    @staticmethod
    def _secret(value: object) -> bytes:
        if (
            not isinstance(value, bytes) or not 32 <= len(value) <= 128
            or any(byte < 0x21 or byte > 0x7E for byte in value)
        ):
            raise ValidationError(
                "Webhook gizli anahtarı 32–128 karakterlik tek bir yazdırılabilir ASCII satırı olmalı."
            )
        return value

    def add_destination(self, name: str, url: str, secret: bytes) -> WebhookDestinationMutation:
        display_name = normalize_webhook_name(name)
        canonical_url, endpoint = normalize_webhook_url(url)
        secret = self._secret(secret)
        now = self._now()
        return self.repository.add_destination(
            id=str(uuid4()), display_name=display_name,
            name_key=webhook_name_key(display_name), url=canonical_url,
            endpoint=endpoint, secret=secret, recorded_at=now,
        )

    def list_destinations(self, *, active_only: bool = True, limit: int = 50) -> tuple[WebhookDestination, ...]:
        if type(active_only) is not bool:
            raise ValidationError("Webhook hedef etkinlik seçimi doğru veya yanlış olmalı.")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("Webhook hedef liste sınırı 1–100 arasında olmalı.")
        return self.repository.list_destinations(active_only=active_only, limit=limit)

    def show_destination(self, destination_id: str) -> WebhookDestination:
        return self.repository.get_destination(_identifier(destination_id, label="webhook hedefi"))

    def revoke_destination(self, destination_id: str) -> WebhookDestinationMutation:
        return self.repository.revoke_destination(
            destination_id=_identifier(destination_id, label="webhook hedefi"),
            recorded_at=self._now(), id=str(uuid4()),
        )

    def rotate_secret(self, destination_id: str, secret: bytes) -> WebhookDestinationMutation:
        return self.repository.rotate_secret(
            destination_id=_identifier(destination_id, label="webhook hedefi"),
            secret=self._secret(secret), recorded_at=self._now(), id=str(uuid4()),
        )

    def queue(self, destination_id: str, notification_id: str) -> tuple[WebhookDelivery, bool]:
        destination_id = _identifier(destination_id, label="webhook hedefi")
        notification_id = _identifier(notification_id, label="bildirim")
        details: InboxDetails = self.inbox.get(notification_id)
        delivery_id, now = str(uuid4()), self._now()
        event = {
            "schema": "xti.webhook.v1",
            "id": delivery_id,
            "event_type": details.notification.event_type,
            "event_created_at": details.notification.created_at,
            "queued_at": now,
            "data": asdict(details),
        }
        payload_json, payload_sha256 = canonical_webhook_payload(event)
        return self.repository.queue(
            id=delivery_id, destination_id=destination_id,
            notification_id=notification_id,
            event_type=details.notification.event_type,
            payload_json=payload_json, payload_sha256=payload_sha256,
            recorded_at=now,
        )

    def list_deliveries(self, *, status: str = "all", limit: int = 50) -> WebhookDeliveryPage:
        if status != "all" and status not in WEBHOOK_DELIVERY_STATUSES:
            raise ValidationError("Webhook teslim durumu all, queued, retryable, failed veya delivered olmalı.")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("Webhook teslim liste sınırı 1–100 arasında olmalı.")
        return self.repository.list_deliveries(status=status, limit=limit)

    def show_delivery(self, delivery_id: str, *, attempt_limit: int = 50) -> WebhookDeliveryDetails:
        delivery_id = _identifier(delivery_id, label="webhook teslimi")
        if type(attempt_limit) is not int or not 1 <= attempt_limit <= 100:
            raise ValidationError("Webhook deneme geçmişi sınırı 1–100 arasında olmalı.")
        return self.repository.get_delivery(delivery_id, attempt_limit=attempt_limit)

    def deliver(self, delivery_id: str) -> WebhookDeliveryResult:
        delivery_id = _identifier(delivery_id, label="webhook teslimi")
        target = self.repository.delivery_target(delivery_id)
        if target.delivery.status == "delivered":
            raise ValidationError("Webhook teslimi daha önce başarıyla tamamlandı; tekrar gönderilmedi.")
        if target.delivery.attempt_count >= MAX_WEBHOOK_ATTEMPTS:
            raise ValidationError("Webhook teslimi 100 deneme güvenli sınırına ulaştı.")
        attempted_at = self._now()
        signature_input = attempted_at.encode("ascii") + b"." + target.payload
        signature = hmac.new(target.secret, signature_input, hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "XTI-webhook/1",
            "X-XTI-Delivery": target.delivery.id,
            "X-XTI-Event": target.delivery.event_type,
            "X-XTI-Timestamp": attempted_at,
            "X-XTI-Signature-256": "sha256=" + signature,
        }
        result = self.sender.send(target.url, target.payload, headers, timeout=10.0)
        delivery, attempt = self.repository.record_attempt(
            delivery_id, expected_attempt_count=target.delivery.attempt_count,
            result=result, attempted_at=attempted_at,
        )
        return WebhookDeliveryResult(delivery, attempt)
