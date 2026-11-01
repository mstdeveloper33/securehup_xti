"""Atomic verified product evidence and append-only lifecycle history."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.products import (
    PRODUCT_EVIDENCE_TYPES,
    AssetProductDetails,
    AssetProductEvent,
    AssetProductEvidence,
    AssetProductMutation,
    normalize_cpe_token,
    normalize_product_evidence,
    normalize_product_id,
    normalize_product_part,
    normalize_product_version,
)


_ACTIONS = {"added", "updated", "reactivated", "revoked"}


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid UUID")
    normalized = str(UUID(value))
    if value != normalized:
        raise ValueError("Non-canonical UUID")
    return normalized


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError("Invalid timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timezone required")
    return parsed.astimezone(timezone.utc).isoformat()


def _evidence_type(value: object) -> str:
    if value not in PRODUCT_EVIDENCE_TYPES:
        raise ValueError("Invalid evidence type")
    return value


class SQLiteAssetProductRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _record(row) -> AssetProductEvidence:
        try:
            asset_value = normalize_domain(row[2])
            if row[2] != asset_value:
                raise ValueError("Non-canonical asset value")
            record = AssetProductEvidence(
                id=_uuid(row[0]), asset_id=_uuid(row[1]), asset_value=asset_value,
                part=normalize_product_part(row[3]),
                vendor=normalize_cpe_token(row[4], field="Üretici"),
                product=normalize_cpe_token(row[5], field="Ürün"),
                version=normalize_product_version(row[6]), active=bool(row[7]),
                evidence_type=_evidence_type(row[8]),
                evidence=normalize_product_evidence(row[9]),
                created_at=_timestamp(row[10]), updated_at=_timestamp(row[11]),
            )
            if type(row[7]) is not int or row[7] not in {0, 1}:
                raise ValueError("Invalid active state")
            if datetime.fromisoformat(record.updated_at) < datetime.fromisoformat(record.created_at):
                raise ValueError("Reversed product evidence time")
            return record
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Varlık ürün kanıtı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _event(row) -> AssetProductEvent:
        try:
            event = AssetProductEvent(
                id=_uuid(row[0]), asset_product_id=_uuid(row[1]), action=row[2],
                evidence_type=_evidence_type(row[3]),
                evidence=normalize_product_evidence(row[4]),
                recorded_at=_timestamp(row[5]),
            )
            if event.action not in _ACTIONS:
                raise ValueError("Invalid product event action")
            return event
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Varlık ürün kanıt geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _select_record(connection, product_id: str):
        return connection.execute(
            "SELECT id, asset_id, asset_value, part, vendor, product, version, active, "
            "evidence_type, evidence, created_at, updated_at FROM asset_products WHERE id = ?",
            (product_id,),
        ).fetchone()

    @staticmethod
    def _validate_input(
        *, part: str, vendor: str, product: str, version: str,
        evidence_type: str, evidence: str, recorded_at: str,
    ) -> tuple[str, str, str, str, str, str, str]:
        try:
            return (
                normalize_product_part(part),
                normalize_cpe_token(vendor, field="Üretici"),
                normalize_cpe_token(product, field="Ürün"),
                normalize_product_version(version),
                _evidence_type(evidence_type),
                normalize_product_evidence(evidence),
                _timestamp(recorded_at),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("Ürün kanıtı kaydedilemedi; alanları kontrol edin.") from error

    @staticmethod
    def _validate_event_input(
        *, evidence_type: str, evidence: str, recorded_at: str,
    ) -> tuple[str, str, str]:
        try:
            return (
                _evidence_type(evidence_type),
                normalize_product_evidence(evidence),
                _timestamp(recorded_at),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("Ürün kanıtı işlemi kaydedilemedi; alanları kontrol edin.") from error

    def add(
        self, *, asset_value: str, part: str, vendor: str, product: str, version: str,
        evidence_type: str, evidence: str, recorded_at: str,
    ) -> AssetProductMutation:
        part, vendor, product, version, evidence_type, evidence, recorded_at = (
            self._validate_input(
                part=part, vendor=vendor, product=product, version=version,
                evidence_type=evidence_type, evidence=evidence, recorded_at=recorded_at,
            )
        )
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                asset = connection.execute(
                    "SELECT id, value FROM assets WHERE value = ?", (asset_value,),
                ).fetchone()
                if asset is None:
                    raise ValidationError(
                        "Ürün kanıtı için adres önce './xti assets add' ile kaydedilmeli."
                    )
                row = connection.execute(
                    "SELECT id, asset_id, asset_value, part, vendor, product, version, active, "
                    "evidence_type, evidence, created_at, updated_at FROM asset_products "
                    "WHERE asset_id = ? AND part = ? AND vendor = ? AND product = ? AND version = ?",
                    (asset[0], part, vendor, product, version),
                ).fetchone()
                if row is None:
                    product_id = str(uuid4())
                    connection.execute(
                        "INSERT INTO asset_products "
                        "(id, asset_id, asset_value, part, vendor, product, version, active, "
                        "evidence_type, evidence, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                        (product_id, asset[0], asset[1], part, vendor, product, version,
                         evidence_type, evidence, recorded_at, recorded_at),
                    )
                    action = "added"
                else:
                    current = self._record(row)
                    product_id = current.id
                    if current.active and (
                        current.evidence_type, current.evidence
                    ) == (evidence_type, evidence):
                        connection.rollback()
                        return AssetProductMutation("unchanged", current)
                    action = "updated" if current.active else "reactivated"
                    effective_updated_at = max(
                        datetime.fromisoformat(current.updated_at),
                        datetime.fromisoformat(recorded_at),
                    ).isoformat()
                    connection.execute(
                        "UPDATE asset_products SET active = 1, evidence_type = ?, evidence = ?, "
                        "updated_at = ? WHERE id = ?",
                        (evidence_type, evidence, effective_updated_at, product_id),
                    )
                connection.execute(
                    "INSERT INTO asset_product_events "
                    "(id, asset_product_id, action, evidence_type, evidence, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid4()), product_id, action, evidence_type, evidence, recorded_at),
                )
                result = self._record(self._select_record(connection, product_id))
                connection.commit()
                return AssetProductMutation(action, result)
            except BaseException:
                connection.rollback()
                raise

    def revoke(
        self, product_id: str, *, evidence_type: str, evidence: str, recorded_at: str,
    ) -> AssetProductMutation:
        product_id = normalize_product_id(product_id)
        evidence_type, evidence, recorded_at = self._validate_event_input(
            evidence_type=evidence_type, evidence=evidence, recorded_at=recorded_at,
        )
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._select_record(connection, product_id)
                if row is None:
                    raise ValidationError("Ürün kanıtı bulunamadı.")
                current = self._record(row)
                if not current.active:
                    connection.rollback()
                    return AssetProductMutation("unchanged", current)
                effective_updated_at = max(
                    datetime.fromisoformat(current.updated_at),
                    datetime.fromisoformat(recorded_at),
                ).isoformat()
                connection.execute(
                    "UPDATE asset_products SET active = 0, updated_at = ? WHERE id = ?",
                    (effective_updated_at, product_id),
                )
                connection.execute(
                    "INSERT INTO asset_product_events "
                    "(id, asset_product_id, action, evidence_type, evidence, recorded_at) "
                    "VALUES (?, ?, 'revoked', ?, ?, ?)",
                    (str(uuid4()), product_id, evidence_type, evidence, recorded_at),
                )
                result = self._record(self._select_record(connection, product_id))
                connection.commit()
                return AssetProductMutation("revoked", result)
            except BaseException:
                connection.rollback()
                raise

    def list(
        self, *, asset_value: str | None, active_only: bool, limit: int,
    ) -> tuple[AssetProductEvidence, ...]:
        if type(active_only) is not bool or type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Ürün kanıtı liste isteği geçersiz.")
        clauses, values = [], []
        if asset_value is not None:
            clauses.append("asset_value = ?")
            values.append(asset_value)
        if active_only:
            clauses.append("active = 1")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT id, asset_id, asset_value, part, vendor, product, version, active, "
                "evidence_type, evidence, created_at, updated_at FROM asset_products "
                f"{where} ORDER BY asset_value, part, vendor, product, version, id LIMIT ?",
                (*values, limit),
            ).fetchall()
        return tuple(self._record(row) for row in rows)

    def details(self, product_id: str, *, event_limit: int) -> AssetProductDetails:
        product_id = normalize_product_id(product_id)
        if type(event_limit) is not int or not 1 <= event_limit <= 100:
            raise ValidationError("Ürün kanıt geçmişi sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = self._select_record(connection, product_id)
            if row is None:
                raise ValidationError("Ürün kanıtı bulunamadı.")
            total = connection.execute(
                "SELECT COUNT(*) FROM asset_product_events WHERE asset_product_id = ?",
                (product_id,),
            ).fetchone()[0]
            event_rows = connection.execute(
                "SELECT id, asset_product_id, action, evidence_type, evidence, recorded_at "
                "FROM asset_product_events WHERE asset_product_id = ? "
                "ORDER BY rowid DESC LIMIT ?", (product_id, event_limit),
            ).fetchall()
            connection.rollback()
        record = self._record(row)
        events = tuple(self._event(event) for event in event_rows)
        if any(event.asset_product_id != record.id for event in events):
            raise StorageError("Ürün kanıt geçmişi yanlış kayda bağlı; işlem durduruldu.")
        return AssetProductDetails(record, events, total)
