"""Small persistence and HTTPS ports for explicit webhook delivery."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from xti.domain.webhooks import (
    WebhookDelivery,
    WebhookDeliveryAttempt,
    WebhookDeliveryDetails,
    WebhookDeliveryPage,
    WebhookDestination,
    WebhookDestinationMutation,
    WebhookSendResult,
    WebhookTarget,
)


class WebhookRepository(Protocol):
    def add_destination(self, **values) -> WebhookDestinationMutation: ...
    def list_destinations(self, *, active_only: bool, limit: int) -> tuple[WebhookDestination, ...]: ...
    def get_destination(self, destination_id: str) -> WebhookDestination: ...
    def revoke_destination(self, **values) -> WebhookDestinationMutation: ...
    def rotate_secret(self, **values) -> WebhookDestinationMutation: ...
    def queue(self, **values) -> tuple[WebhookDelivery, bool]: ...
    def list_deliveries(self, *, status: str, limit: int) -> WebhookDeliveryPage: ...
    def get_delivery(self, delivery_id: str, *, attempt_limit: int) -> WebhookDeliveryDetails: ...
    def delivery_target(self, delivery_id: str) -> WebhookTarget: ...
    def record_attempt(
        self, delivery_id: str, *, expected_attempt_count: int,
        result: WebhookSendResult, attempted_at: str,
    ) -> tuple[WebhookDelivery, WebhookDeliveryAttempt]: ...


class WebhookSender(Protocol):
    def send(
        self, url: str, body: bytes, headers: Mapping[str, str], *, timeout: float,
    ) -> WebhookSendResult: ...
