"""Atomic Ubuntu package inventory evidence with append-only history."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.ubuntu_packages import (
    UBUNTU_PACKAGE_EVIDENCE_TYPES,
    UbuntuAssetPackageDetails,
    UbuntuAssetPackageEvent,
    UbuntuAssetPackageEvidence,
    UbuntuAssetPackageMutation,
    normalize_ubuntu_package_evidence,
    normalize_ubuntu_package_fields,
    normalize_ubuntu_package_id,
)


_ACTIONS = {"added", "updated", "reactivated", "revoked"}
_MAX_ACTIVE_INVENTORY = 10_000
_MAX_ACTIVE_INVENTORY_EVENTS = 100_000
_SELECT = (
    "id, asset_id, asset_value, ecosystem, binary_name, binary_version, architecture, "
    "source_name, source_version, active, evidence_type, evidence, created_at, updated_at"
)


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
    if value not in UBUNTU_PACKAGE_EVIDENCE_TYPES:
        raise ValueError("Invalid evidence type")
    return value


class SQLiteUbuntuAssetPackageRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _record(row) -> UbuntuAssetPackageEvidence:
        try:
            asset_value = normalize_domain(row[2])
            if row[2] != asset_value:
                raise ValueError("Non-canonical asset")
            (
                ecosystem, binary_name, binary_version, architecture,
                source_name, source_version,
            ) = normalize_ubuntu_package_fields(
                ecosystem=row[3], binary_name=row[4], binary_version=row[5],
                architecture=row[6], source_name=row[7], source_version=row[8],
            )
            if (row[3], row[4], row[5], row[6], row[7], row[8]) != (
                ecosystem, binary_name, binary_version, architecture,
                source_name, source_version,
            ):
                raise ValueError("Non-canonical Ubuntu package")
            if type(row[9]) is not int or row[9] not in {0, 1}:
                raise ValueError("Invalid active state")
            record = UbuntuAssetPackageEvidence(
                id=_uuid(row[0]), asset_id=_uuid(row[1]), asset_value=asset_value,
                ecosystem=ecosystem, binary_name=binary_name,
                binary_version=binary_version, architecture=architecture,
                source_name=source_name, source_version=source_version,
                active=bool(row[9]), evidence_type=_evidence_type(row[10]),
                evidence=normalize_ubuntu_package_evidence(row[11]),
                created_at=_timestamp(row[12]), updated_at=_timestamp(row[13]),
            )
            if datetime.fromisoformat(record.updated_at) < datetime.fromisoformat(
                record.created_at
            ):
                raise ValueError("Reversed time")
            return record
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Ubuntu paket kanıtı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _event(row) -> UbuntuAssetPackageEvent:
        try:
            event = UbuntuAssetPackageEvent(
                id=_uuid(row[0]), ubuntu_package_id=_uuid(row[1]), action=row[2],
                evidence_type=_evidence_type(row[3]),
                evidence=normalize_ubuntu_package_evidence(row[4]),
                recorded_at=_timestamp(row[5]),
            )
            if event.action not in _ACTIONS:
                raise ValueError("Invalid action")
            return event
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Ubuntu paket kanıt geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _select_record(connection, package_id: str):
        return connection.execute(
            f"SELECT {_SELECT} FROM ubuntu_asset_packages WHERE id = ?", (package_id,),
        ).fetchone()

    @staticmethod
    def _validate_input(
        *, ecosystem: str, binary_name: str, binary_version: str,
        architecture: str, source_name: str, source_version: str,
        evidence_type: str, evidence: str, recorded_at: str,
    ) -> tuple:
        try:
            fields = normalize_ubuntu_package_fields(
                ecosystem=ecosystem, binary_name=binary_name,
                binary_version=binary_version, architecture=architecture,
                source_name=source_name, source_version=source_version,
            )
            return (
                *fields, _evidence_type(evidence_type),
                normalize_ubuntu_package_evidence(evidence), _timestamp(recorded_at),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError(
                "Ubuntu paket kanıtı kaydedilemedi; alanları kontrol edin."
            ) from error

    @staticmethod
    def _validate_event_input(
        *, evidence_type: str, evidence: str, recorded_at: str,
    ) -> tuple[str, str, str]:
        try:
            return (
                _evidence_type(evidence_type),
                normalize_ubuntu_package_evidence(evidence), _timestamp(recorded_at),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("Ubuntu paket kanıtı işlemi kaydedilemedi.") from error

    def add(
        self, *, asset_value: str, ecosystem: str, binary_name: str,
        binary_version: str, architecture: str, source_name: str,
        source_version: str, evidence_type: str, evidence: str, recorded_at: str,
    ) -> UbuntuAssetPackageMutation:
        (
            ecosystem, binary_name, binary_version, architecture,
            source_name, source_version, evidence_type, evidence, recorded_at,
        ) = self._validate_input(
            ecosystem=ecosystem, binary_name=binary_name,
            binary_version=binary_version, architecture=architecture,
            source_name=source_name, source_version=source_version,
            evidence_type=evidence_type, evidence=evidence, recorded_at=recorded_at,
        )
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                asset = connection.execute(
                    "SELECT id, value FROM assets WHERE value = ?", (asset_value,),
                ).fetchone()
                if asset is None:
                    raise ValidationError(
                        "Ubuntu paket kanıtı için adres önce './xti assets add' ile kaydedilmeli."
                    )
                row = connection.execute(
                    f"SELECT {_SELECT} FROM ubuntu_asset_packages WHERE asset_id = ? "
                    "AND ecosystem = ? AND binary_name = ? AND binary_version = ? "
                    "AND architecture = ? AND source_name = ? AND source_version = ?",
                    (asset[0], ecosystem, binary_name, binary_version, architecture,
                     source_name, source_version),
                ).fetchone()
                if row is None:
                    package_id = str(uuid4())
                    connection.execute(
                        "INSERT INTO ubuntu_asset_packages "
                        "(id, asset_id, asset_value, ecosystem, binary_name, binary_version, "
                        "architecture, source_name, source_version, active, evidence_type, "
                        "evidence, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                        (package_id, asset[0], asset[1], ecosystem, binary_name,
                         binary_version, architecture, source_name, source_version,
                         evidence_type, evidence, recorded_at, recorded_at),
                    )
                    action = "added"
                else:
                    current = self._record(row)
                    package_id = current.id
                    if current.active and (
                        current.evidence_type, current.evidence
                    ) == (evidence_type, evidence):
                        connection.rollback()
                        return UbuntuAssetPackageMutation("unchanged", current)
                    action = "updated" if current.active else "reactivated"
                    effective_time = max(
                        datetime.fromisoformat(current.updated_at),
                        datetime.fromisoformat(recorded_at),
                    ).isoformat()
                    connection.execute(
                        "UPDATE ubuntu_asset_packages SET active = 1, evidence_type = ?, "
                        "evidence = ?, updated_at = ? WHERE id = ?",
                        (evidence_type, evidence, effective_time, package_id),
                    )
                connection.execute(
                    "INSERT INTO ubuntu_asset_package_events "
                    "(id, ubuntu_package_id, action, evidence_type, evidence, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid4()), package_id, action, evidence_type, evidence, recorded_at),
                )
                result = self._record(self._select_record(connection, package_id))
                connection.commit()
                return UbuntuAssetPackageMutation(action, result)
            except BaseException:
                connection.rollback()
                raise

    def revoke(
        self, package_id: str, *, evidence_type: str, evidence: str, recorded_at: str,
    ) -> UbuntuAssetPackageMutation:
        package_id = normalize_ubuntu_package_id(package_id)
        evidence_type, evidence, recorded_at = self._validate_event_input(
            evidence_type=evidence_type, evidence=evidence, recorded_at=recorded_at,
        )
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._select_record(connection, package_id)
                if row is None:
                    raise ValidationError("Ubuntu paket kanıtı bulunamadı.")
                current = self._record(row)
                if not current.active:
                    connection.rollback()
                    return UbuntuAssetPackageMutation("unchanged", current)
                effective_time = max(
                    datetime.fromisoformat(current.updated_at),
                    datetime.fromisoformat(recorded_at),
                ).isoformat()
                connection.execute(
                    "UPDATE ubuntu_asset_packages SET active = 0, updated_at = ? WHERE id = ?",
                    (effective_time, package_id),
                )
                connection.execute(
                    "INSERT INTO ubuntu_asset_package_events "
                    "(id, ubuntu_package_id, action, evidence_type, evidence, recorded_at) "
                    "VALUES (?, ?, 'revoked', ?, ?, ?)",
                    (str(uuid4()), package_id, evidence_type, evidence, recorded_at),
                )
                result = self._record(self._select_record(connection, package_id))
                connection.commit()
                return UbuntuAssetPackageMutation("revoked", result)
            except BaseException:
                connection.rollback()
                raise

    def list(
        self, *, asset_value: str | None, active_only: bool, limit: int,
    ) -> tuple[UbuntuAssetPackageEvidence, ...]:
        if type(active_only) is not bool or type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Ubuntu paket kanıtı liste isteği geçersiz.")
        clauses, values = [], []
        if asset_value is not None:
            clauses.append("asset_value = ?")
            values.append(asset_value)
        if active_only:
            clauses.append("active = 1")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                f"SELECT {_SELECT} FROM ubuntu_asset_packages {where} "
                "ORDER BY asset_value, ecosystem, binary_name, architecture, "
                "binary_version, source_name, source_version, id LIMIT ?",
                (*values, limit),
            ).fetchall()
        return tuple(self._record(row) for row in rows)

    def details(self, package_id: str, *, event_limit: int) -> UbuntuAssetPackageDetails:
        package_id = normalize_ubuntu_package_id(package_id)
        if type(event_limit) is not int or not 1 <= event_limit <= 100:
            raise ValidationError("Ubuntu paket kanıt geçmişi sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = self._select_record(connection, package_id)
            if row is None:
                raise ValidationError("Ubuntu paket kanıtı bulunamadı.")
            total = connection.execute(
                "SELECT COUNT(*) FROM ubuntu_asset_package_events "
                "WHERE ubuntu_package_id = ?", (package_id,),
            ).fetchone()[0]
            if total > 10_000:
                raise StorageError("Ubuntu paket kanıt geçmişi güvenli sınırı aştı.")
            event_rows = connection.execute(
                "SELECT id, ubuntu_package_id, action, evidence_type, evidence, recorded_at "
                "FROM ubuntu_asset_package_events WHERE ubuntu_package_id = ? "
                "ORDER BY rowid DESC LIMIT 10001", (package_id,),
            ).fetchall()
            connection.rollback()
        if len(event_rows) != total:
            raise StorageError("Ubuntu paket kanıt geçmişi sayımı tutarsız.")
        record = self._record(row)
        all_events = tuple(self._event(event) for event in event_rows)
        if any(event.ubuntu_package_id != record.id for event in all_events):
            raise StorageError("Ubuntu paket kanıt geçmişi yanlış kayda bağlı.")
        return UbuntuAssetPackageDetails(record, all_events[:event_limit], total)

    def active_inventory(
        self, *, asset_value: str | None,
    ) -> tuple[UbuntuAssetPackageEvidence, ...]:
        if asset_value is not None:
            asset_value = normalize_domain(asset_value)
        where = "AND asset_value = ?" if asset_value is not None else ""
        values = (asset_value,) if asset_value is not None else ()
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            if asset_value is not None and connection.execute(
                "SELECT 1 FROM assets WHERE value = ?", (asset_value,),
            ).fetchone() is None:
                connection.rollback()
                raise ValidationError("Kayıtlı varlık bulunamadı.")
            rows = connection.execute(
                f"SELECT {_SELECT} FROM ubuntu_asset_packages WHERE active = 1 {where} "
                "ORDER BY asset_value, ecosystem, source_name, source_version, "
                "binary_name, architecture, binary_version, id LIMIT ?",
                (*values, _MAX_ACTIVE_INVENTORY + 1),
            ).fetchall()
            event_rows = connection.execute(
                "SELECT e.id, e.ubuntu_package_id, e.action, e.evidence_type, "
                "e.evidence, e.recorded_at FROM ubuntu_asset_package_events e "
                "JOIN ubuntu_asset_packages p ON p.id = e.ubuntu_package_id "
                f"WHERE p.active = 1 {where} ORDER BY e.rowid "
                "LIMIT ?",
                (*values, _MAX_ACTIVE_INVENTORY_EVENTS + 1),
            ).fetchall()
            connection.rollback()
        if len(rows) > _MAX_ACTIVE_INVENTORY:
            raise StorageError(
                "Etkin Ubuntu paket envanteri 10.000 kayıt sınırını aşıyor; "
                "varlık filtresi kullanın."
            )
        if len(event_rows) > _MAX_ACTIVE_INVENTORY_EVENTS:
            raise StorageError(
                "Etkin Ubuntu paket kanıt geçmişi 100.000 olay sınırını aşıyor; "
                "varlık filtresi kullanın."
            )
        records = tuple(self._record(row) for row in rows)
        record_ids = {record.id for record in records}
        events = tuple(self._event(row) for row in event_rows)
        event_package_ids = {event.ubuntu_package_id for event in events}
        if any(event.ubuntu_package_id not in record_ids for event in events):
            raise StorageError("Ubuntu paket kanıt geçmişi yanlış etkin kayda bağlı.")
        if record_ids != event_package_ids:
            raise StorageError("Etkin Ubuntu paket kanıt geçmişi eksik; işlem durduruldu.")
        return records
