"""SQLite webhook configuration, immutable payload queue and attempt history."""

from __future__ import annotations

import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.webhooks import (
    MAX_WEBHOOK_ATTEMPTS,
    WEBHOOK_ATTEMPT_OUTCOMES,
    WEBHOOK_DELIVERY_STATUSES,
    WebhookDelivery,
    WebhookDeliveryAttempt,
    WebhookDeliveryDetails,
    WebhookDeliveryPage,
    WebhookDestination,
    WebhookDestinationMutation,
    WebhookSendResult,
    WebhookTarget,
    canonical_webhook_payload,
    normalize_webhook_name,
    normalize_webhook_url,
    webhook_name_key,
)


_DESTINATION_SELECT = (
    "id, name_key, display_name, url, endpoint, secret_b64, active, created_at, updated_at"
)
_DELIVERY_SELECT = (
    "d.sequence, d.id, d.destination_id, w.display_name, w.endpoint, "
    "d.notification_id, d.event_type, d.status, d.payload_json, d.payload_sha256, "
    "d.attempt_count, d.created_at, d.updated_at, d.delivered_at, "
    "d.last_http_status, d.last_error"
)
_ATTEMPT_SELECT = (
    "sequence, id, delivery_id, number, outcome, http_status, error, attempted_at"
)
_MAX_DESTINATIONS = 100
_MAX_DELIVERIES = 10_000


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid uuid")
    normalized = str(UUID(value))
    if normalized != value:
        raise ValueError("non-canonical uuid")
    return normalized


def _timestamp(value: object, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid timestamp")
    normalized = normalize_cti_timestamp(value, field="webhook zamanı")
    if normalized != value:
        raise ValueError("non-canonical timestamp")
    return normalized


def _secret_encode(secret: bytes) -> str:
    if (
        not isinstance(secret, bytes) or not 32 <= len(secret) <= 128
        or any(byte < 0x21 or byte > 0x7E for byte in secret)
    ):
        raise ValidationError("Webhook gizli anahtarı geçersiz.")
    return base64.b64encode(secret).decode("ascii")


def _secret_decode(value: object) -> bytes:
    try:
        if not isinstance(value, str) or not value.isascii() or len(value) > 256:
            raise ValueError("invalid secret encoding")
        decoded = base64.b64decode(value, validate=True)
        if base64.b64encode(decoded).decode("ascii") != value:
            raise ValueError("non-canonical secret encoding")
        _secret_encode(decoded)
        return decoded
    except (ValueError, ValidationError) as error:
        raise StorageError("Webhook gizli anahtar kaydı bozuk; işlem durduruldu.") from error


def _safe_error(value: object, *, optional: bool) -> str | None:
    if value is None and optional:
        return None
    if (
        not isinstance(value, str) or not 1 <= len(value) <= 500
        or not value.isprintable() or "\n" in value or "\r" in value
    ):
        raise ValueError("invalid safe error")
    return value


class SQLiteWebhookRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _destination(row) -> tuple[WebhookDestination, str, bytes]:
        try:
            identifier = _uuid(row[0])
            display_name = normalize_webhook_name(row[2])
            if row[1] != webhook_name_key(display_name):
                raise ValueError("invalid name key")
            url, endpoint = normalize_webhook_url(row[3])
            if url != row[3] or endpoint != row[4]:
                raise ValueError("non-canonical endpoint")
            secret = _secret_decode(row[5])
            if type(row[6]) is not int or row[6] not in {0, 1}:
                raise ValueError("invalid activity")
            destination = WebhookDestination(
                identifier, display_name, endpoint, bool(row[6]),
                _timestamp(row[7]), _timestamp(row[8]),
            )
            if datetime.fromisoformat(destination.created_at) > datetime.fromisoformat(
                destination.updated_at
            ):
                raise ValueError("invalid destination times")
            return destination, url, secret
        except StorageError:
            raise
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Webhook hedef kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _validate_destination_history(connection, destination: WebhookDestination) -> None:
        rows = connection.execute(
            "SELECT sequence, id, destination_id, action, endpoint, recorded_at "
            "FROM webhook_destination_events WHERE destination_id=? ORDER BY sequence LIMIT 102",
            (destination.id,),
        ).fetchall()
        try:
            if not rows or len(rows) > 101:
                raise ValueError("invalid event count")
            actions = []
            previous = None
            for sequence, identifier, destination_id, action, endpoint, recorded_at in rows:
                if type(sequence) is not int or sequence < 1:
                    raise ValueError("invalid event sequence")
                _uuid(identifier)
                if (
                    _uuid(destination_id) != destination.id
                    or action not in {"added", "secret_rotated", "revoked"}
                    or endpoint != destination.endpoint
                ):
                    raise ValueError("invalid event")
                recorded_at = _timestamp(recorded_at)
                current = datetime.fromisoformat(recorded_at)
                if previous is not None and current < previous:
                    raise ValueError("event time regression")
                previous = current
                actions.append((action, recorded_at))
            if (
                actions[0][0] != "added" or any(action == "added" for action, _ in actions[1:])
                or any(action == "revoked" for action, _ in actions[:-1])
                or destination.active == (actions[-1][0] == "revoked")
                or actions[0][1] != destination.created_at
                or actions[-1][1] != destination.updated_at
            ):
                raise ValueError("invalid destination lifecycle")
        except (TypeError, ValueError, OverflowError) as error:
            raise StorageError("Webhook hedef geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _payload(
        payload_json: object, payload_sha256: object, *, delivery_id: str,
        notification_id: str, event_type: str, created_at: str,
    ) -> bytes:
        try:
            if not isinstance(payload_json, str) or not isinstance(payload_sha256, str):
                raise ValueError("invalid payload")
            parsed = json.loads(payload_json)
            canonical, digest = canonical_webhook_payload(parsed)
            if canonical != payload_json or digest != payload_sha256:
                raise ValueError("payload digest mismatch")
            if (
                not isinstance(parsed, dict) or parsed.get("schema") != "xti.webhook.v1"
                or parsed.get("id") != delivery_id
                or parsed.get("event_type") != event_type
                or parsed.get("queued_at") != created_at
                or not isinstance(parsed.get("data"), dict)
                or not isinstance(parsed["data"].get("notification"), dict)
                or parsed["data"]["notification"].get("id") != notification_id
                or parsed["data"]["notification"].get("event_type") != event_type
                or parsed.get("event_created_at")
                != parsed["data"]["notification"].get("created_at")
            ):
                raise ValueError("payload binding mismatch")
            return payload_json.encode("ascii")
        except (TypeError, ValueError, ValidationError, UnicodeError, json.JSONDecodeError) as error:
            raise StorageError("Webhook olay gövdesi bozuk; işlem durduruldu.") from error

    @classmethod
    def _delivery(cls, row) -> tuple[WebhookDelivery, bytes]:
        try:
            (
                sequence, identifier, destination_id, destination_name, endpoint,
                notification_id, event_type, status, payload_json, payload_sha256,
                attempt_count, created_at, updated_at, delivered_at,
                last_http_status, last_error,
            ) = row
            if type(sequence) is not int or not 1 <= sequence <= 2**63 - 1:
                raise ValueError("invalid sequence")
            identifier, destination_id = _uuid(identifier), _uuid(destination_id)
            if (
                not isinstance(notification_id, str) or not notification_id
                or len(notification_id) > 64 or not notification_id.isprintable()
                or not isinstance(event_type, str) or not 1 <= len(event_type) <= 80
                or not event_type.isascii() or not event_type.replace("_", "").isalnum()
                or status not in WEBHOOK_DELIVERY_STATUSES
                or not isinstance(payload_sha256, str) or len(payload_sha256) != 64
                or any(value not in "0123456789abcdef" for value in payload_sha256)
                or type(attempt_count) is not int
                or not 0 <= attempt_count <= MAX_WEBHOOK_ATTEMPTS
            ):
                raise ValueError("invalid delivery")
            destination_name = normalize_webhook_name(destination_name)
            created_at = _timestamp(created_at)
            updated_at = _timestamp(updated_at)
            delivered_at = _timestamp(delivered_at, optional=True)
            if datetime.fromisoformat(created_at) > datetime.fromisoformat(updated_at):
                raise ValueError("invalid delivery times")
            if delivered_at is not None and datetime.fromisoformat(delivered_at) != datetime.fromisoformat(updated_at):
                raise ValueError("invalid delivered time")
            if last_http_status is not None and (
                type(last_http_status) is not int or not 100 <= last_http_status <= 599
            ):
                raise ValueError("invalid http status")
            last_error = _safe_error(last_error, optional=True)
            if status == "queued" and (
                attempt_count != 0 or delivered_at is not None
                or last_http_status is not None or last_error is not None
            ):
                raise ValueError("invalid queued state")
            if status == "delivered" and (
                attempt_count < 1 or delivered_at is None or last_error is not None
                or last_http_status is None or not 200 <= last_http_status <= 299
            ):
                raise ValueError("invalid delivered state")
            if status in {"retryable", "failed"} and (
                attempt_count < 1 or delivered_at is not None or last_error is None
            ):
                raise ValueError("invalid failed state")
            payload = cls._payload(
                payload_json, payload_sha256, delivery_id=identifier,
                notification_id=notification_id, event_type=event_type,
                created_at=created_at,
            )
            return WebhookDelivery(
                sequence, identifier, destination_id, destination_name, endpoint,
                notification_id, event_type, status, payload_sha256, attempt_count,
                created_at, updated_at, delivered_at, last_http_status, last_error,
            ), payload
        except StorageError:
            raise
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Webhook teslim kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _attempt(row) -> WebhookDeliveryAttempt:
        try:
            sequence, identifier, delivery_id, number, outcome, status, error, attempted = row
            if (
                type(sequence) is not int or sequence < 1
                or type(number) is not int or not 1 <= number <= MAX_WEBHOOK_ATTEMPTS
                or outcome not in WEBHOOK_ATTEMPT_OUTCOMES
            ):
                raise ValueError("invalid attempt")
            identifier, delivery_id = _uuid(identifier), _uuid(delivery_id)
            if status is not None and (type(status) is not int or not 100 <= status <= 599):
                raise ValueError("invalid attempt status")
            error = _safe_error(error, optional=True)
            if outcome == "delivered" and (
                error is not None or status is None or not 200 <= status <= 299
            ):
                raise ValueError("invalid delivered attempt")
            if outcome != "delivered" and error is None:
                raise ValueError("missing attempt error")
            return WebhookDeliveryAttempt(
                sequence, identifier, delivery_id, number, outcome, status, error,
                _timestamp(attempted),
            )
        except (TypeError, ValueError, OverflowError) as error:
            raise StorageError("Webhook teslim denemesi bozuk; işlem durduruldu.") from error

    @classmethod
    def _delivery_row(cls, connection, delivery_id: str):
        row = connection.execute(
            f"SELECT {_DELIVERY_SELECT} FROM webhook_deliveries d JOIN "
            "webhook_destinations w ON w.id=d.destination_id WHERE d.id=?",
            (delivery_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("Webhook teslimi bulunamadı.")
        return row

    @classmethod
    def _attempts(cls, connection, delivery: WebhookDelivery) -> tuple[WebhookDeliveryAttempt, ...]:
        rows = connection.execute(
            f"SELECT {_ATTEMPT_SELECT} FROM webhook_delivery_attempts "
            "WHERE delivery_id=? ORDER BY number LIMIT ?",
            (delivery.id, MAX_WEBHOOK_ATTEMPTS + 1),
        ).fetchall()
        if len(rows) > MAX_WEBHOOK_ATTEMPTS:
            raise StorageError("Webhook teslim denemesi güvenli sınırı aşıyor.")
        attempts = tuple(cls._attempt(row) for row in rows)
        if (
            len(attempts) != delivery.attempt_count
            or tuple(item.number for item in attempts) != tuple(range(1, len(attempts) + 1))
            or any(item.delivery_id != delivery.id for item in attempts)
        ):
            raise StorageError("Webhook teslim denemesi geçmişi tutarsız; işlem durduruldu.")
        if attempts:
            last = attempts[-1]
            if (
                last.outcome != delivery.status or last.http_status != delivery.last_http_status
                or last.error != delivery.last_error or last.attempted_at != delivery.updated_at
            ):
                raise StorageError("Webhook teslim özeti deneme geçmişiyle uyuşmuyor.")
        return attempts

    def add_destination(self, **values) -> WebhookDestinationMutation:
        secret_b64 = _secret_encode(values["secret"])
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                count = connection.execute("SELECT COUNT(*) FROM webhook_destinations").fetchone()[0]
                if count >= _MAX_DESTINATIONS:
                    raise ValidationError("En fazla 100 webhook hedefi kaydedilebilir.")
                existing = connection.execute(
                    "SELECT id FROM webhook_destinations WHERE name_key=?",
                    (values["name_key"],),
                ).fetchone()
                if existing is not None:
                    raise ValidationError("Bu webhook hedef adı daha önce kullanılmış.")
                connection.execute(
                    "INSERT INTO webhook_destinations VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                    (
                        values["id"], values["name_key"], values["display_name"],
                        values["url"], values["endpoint"], secret_b64,
                        values["recorded_at"], values["recorded_at"],
                    ),
                )
                connection.execute(
                    "INSERT INTO webhook_destination_events "
                    "(id, destination_id, action, endpoint, recorded_at) VALUES (?, ?, 'added', ?, ?)",
                    (str(uuid4()), values["id"], values["endpoint"], values["recorded_at"]),
                )
                row = connection.execute(
                    f"SELECT {_DESTINATION_SELECT} FROM webhook_destinations WHERE id=?",
                    (values["id"],),
                ).fetchone()
                destination, _, _ = self._destination(row)
                self._validate_destination_history(connection, destination)
                connection.commit()
                return WebhookDestinationMutation("added", destination)
            except BaseException:
                connection.rollback()
                raise

    def list_destinations(self, *, active_only: bool, limit: int) -> tuple[WebhookDestination, ...]:
        clause = "WHERE active=1 " if active_only else ""
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            rows = connection.execute(
                f"SELECT {_DESTINATION_SELECT} FROM webhook_destinations {clause}"
                "ORDER BY name_key, id LIMIT ?", (limit,),
            ).fetchall()
            destinations = tuple(self._destination(row)[0] for row in rows)
            for destination in destinations:
                self._validate_destination_history(connection, destination)
            connection.rollback()
        return destinations

    def get_destination(self, destination_id: str) -> WebhookDestination:
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = connection.execute(
                f"SELECT {_DESTINATION_SELECT} FROM webhook_destinations WHERE id=?",
                (destination_id,),
            ).fetchone()
            if row is None:
                raise ValidationError("Webhook hedefi bulunamadı.")
            destination = self._destination(row)[0]
            self._validate_destination_history(connection, destination)
            connection.rollback()
        return destination

    def revoke_destination(self, **values) -> WebhookDestinationMutation:
        return self._change_destination(values, action="revoked")

    def rotate_secret(self, **values) -> WebhookDestinationMutation:
        return self._change_destination(values, action="secret_rotated")

    def _change_destination(self, values, *, action: str) -> WebhookDestinationMutation:
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    f"SELECT {_DESTINATION_SELECT} FROM webhook_destinations WHERE id=?",
                    (values["destination_id"],),
                ).fetchone()
                if row is None:
                    raise ValidationError("Webhook hedefi bulunamadı.")
                destination, _, _ = self._destination(row)
                self._validate_destination_history(connection, destination)
                if not destination.active:
                    raise ValidationError("Webhook hedefi etkin değil.")
                if action == "revoked":
                    connection.execute(
                        "UPDATE webhook_destinations SET active=0, updated_at=? WHERE id=?",
                        (values["recorded_at"], destination.id),
                    )
                else:
                    connection.execute(
                        "UPDATE webhook_destinations SET secret_b64=?, updated_at=? WHERE id=?",
                        (_secret_encode(values["secret"]), values["recorded_at"], destination.id),
                    )
                connection.execute(
                    "INSERT INTO webhook_destination_events "
                    "(id, destination_id, action, endpoint, recorded_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        values["id"], destination.id, action, destination.endpoint,
                        values["recorded_at"],
                    ),
                )
                changed = connection.execute(
                    f"SELECT {_DESTINATION_SELECT} FROM webhook_destinations WHERE id=?",
                    (destination.id,),
                ).fetchone()
                result = self._destination(changed)[0]
                self._validate_destination_history(connection, result)
                connection.commit()
                return WebhookDestinationMutation(action, result)
            except BaseException:
                connection.rollback()
                raise

    def queue(self, **values) -> tuple[WebhookDelivery, bool]:
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                destination_row = connection.execute(
                    f"SELECT {_DESTINATION_SELECT} FROM webhook_destinations WHERE id=?",
                    (values["destination_id"],),
                ).fetchone()
                if destination_row is None:
                    raise ValidationError("Webhook hedefi bulunamadı.")
                destination = self._destination(destination_row)[0]
                self._validate_destination_history(connection, destination)
                if not destination.active:
                    raise ValidationError("Webhook hedefi etkin değil.")
                existing = connection.execute(
                    "SELECT id FROM webhook_deliveries WHERE destination_id=? AND notification_id=?",
                    (destination.id, values["notification_id"]),
                ).fetchone()
                if existing is not None:
                    row = self._delivery_row(connection, existing[0])
                    delivery, _ = self._delivery(row)
                    connection.commit()
                    return delivery, False
                count = connection.execute("SELECT COUNT(*) FROM webhook_deliveries").fetchone()[0]
                if count >= _MAX_DELIVERIES:
                    raise ValidationError("Webhook teslim kuyruğu 10.000 kayıt sınırına ulaştı.")
                connection.execute(
                    "INSERT INTO webhook_deliveries "
                    "(id, destination_id, notification_id, event_type, status, payload_json, "
                    "payload_sha256, attempt_count, created_at, updated_at, delivered_at, "
                    "last_http_status, last_error) "
                    "VALUES (?, ?, ?, ?, 'queued', ?, ?, 0, ?, ?, NULL, NULL, NULL)",
                    (
                        values["id"], destination.id, values["notification_id"],
                        values["event_type"], values["payload_json"],
                        values["payload_sha256"], values["recorded_at"],
                        values["recorded_at"],
                    ),
                )
                delivery = self._delivery(self._delivery_row(connection, values["id"]))[0]
                connection.commit()
                return delivery, True
            except BaseException:
                connection.rollback()
                raise

    def list_deliveries(self, *, status: str, limit: int) -> WebhookDeliveryPage:
        where, parameters = ("", ()) if status == "all" else ("WHERE d.status=? ", (status,))
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            total = connection.execute(
                "SELECT COUNT(*) FROM webhook_deliveries d " + where, parameters,
            ).fetchone()[0]
            if total > _MAX_DELIVERIES:
                raise StorageError("Webhook teslim kuyruğu güvenli sınırı aşıyor.")
            rows = connection.execute(
                f"SELECT {_DELIVERY_SELECT} FROM webhook_deliveries d JOIN "
                "webhook_destinations w ON w.id=d.destination_id " + where
                + "ORDER BY d.sequence DESC LIMIT ?", (*parameters, limit),
            ).fetchall()
            deliveries = tuple(self._delivery(row)[0] for row in rows)
            connection.rollback()
        return WebhookDeliveryPage(deliveries, total)

    def get_delivery(self, delivery_id: str, *, attempt_limit: int) -> WebhookDeliveryDetails:
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            delivery = self._delivery(self._delivery_row(connection, delivery_id))[0]
            attempts = self._attempts(connection, delivery)
            connection.rollback()
        return WebhookDeliveryDetails(delivery, attempts[-attempt_limit:])

    def delivery_target(self, delivery_id: str) -> WebhookTarget:
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = self._delivery_row(connection, delivery_id)
            delivery, payload = self._delivery(row)
            attempts = self._attempts(connection, delivery)
            destination_row = connection.execute(
                f"SELECT {_DESTINATION_SELECT} FROM webhook_destinations WHERE id=?",
                (delivery.destination_id,),
            ).fetchone()
            destination, url, secret = self._destination(destination_row)
            self._validate_destination_history(connection, destination)
            connection.rollback()
        if not destination.active:
            raise ValidationError("Webhook hedefi etkin değil; teslim gönderilmedi.")
        if len(attempts) != delivery.attempt_count:
            raise StorageError("Webhook teslim geçmişi tutarsız; işlem durduruldu.")
        return WebhookTarget(delivery, url, secret, payload)

    def record_attempt(
        self, delivery_id: str, *, expected_attempt_count: int,
        result: WebhookSendResult, attempted_at: str,
    ) -> tuple[WebhookDelivery, WebhookDeliveryAttempt]:
        if (
            not isinstance(result, WebhookSendResult)
            or result.outcome not in WEBHOOK_ATTEMPT_OUTCOMES
            or (result.outcome == "delivered" and result.error is not None)
            or (result.outcome != "delivered" and result.error is None)
        ):
            raise ValidationError("Webhook gönderim sonucu geçersiz.")
        if result.http_status is not None and (
            type(result.http_status) is not int or not 100 <= result.http_status <= 599
        ):
            raise ValidationError("Webhook HTTP sonucu geçersiz.")
        if result.outcome == "delivered" and (
            result.http_status is None or not 200 <= result.http_status <= 299
        ):
            raise ValidationError("Başarılı webhook teslimi geçerli 2xx durumu taşımalı.")
        if result.error is not None:
            try:
                _safe_error(result.error, optional=False)
            except ValueError as error:
                raise ValidationError("Webhook gönderim hata özeti güvenli değil.") from error
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._delivery(self._delivery_row(connection, delivery_id))[0]
                self._attempts(connection, current)
                if current.status == "delivered":
                    raise ValidationError("Webhook teslimi zaten tamamlandı.")
                if current.attempt_count != expected_attempt_count:
                    raise ValidationError(
                        "Webhook teslimi başka bir işlemde değişti; yeniden inceleyin."
                    )
                number = current.attempt_count + 1
                if number > MAX_WEBHOOK_ATTEMPTS:
                    raise ValidationError("Webhook teslimi 100 deneme güvenli sınırına ulaştı.")
                attempt_id = str(uuid4())
                connection.execute(
                    "INSERT INTO webhook_delivery_attempts "
                    "(id, delivery_id, number, outcome, http_status, error, attempted_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        attempt_id, current.id, number, result.outcome,
                        result.http_status, result.error, attempted_at,
                    ),
                )
                delivered_at = attempted_at if result.outcome == "delivered" else None
                connection.execute(
                    "UPDATE webhook_deliveries SET status=?, attempt_count=?, updated_at=?, "
                    "delivered_at=?, last_http_status=?, last_error=? WHERE id=?",
                    (
                        result.outcome, number, attempted_at, delivered_at,
                        result.http_status, result.error, current.id,
                    ),
                )
                delivery = self._delivery(self._delivery_row(connection, current.id))[0]
                attempt_row = connection.execute(
                    f"SELECT {_ATTEMPT_SELECT} FROM webhook_delivery_attempts WHERE id=?",
                    (attempt_id,),
                ).fetchone()
                attempt = self._attempt(attempt_row)
                self._attempts(connection, delivery)
                connection.commit()
                return delivery, attempt
            except BaseException:
                connection.rollback()
                raise
