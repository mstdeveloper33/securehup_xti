"""Atomic exact package evidence and append-only lifecycle history."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.packages import (
    PACKAGE_EVIDENCE_TYPES,
    AssetPackageDetails,
    AssetPackageEvent,
    AssetPackageEvidence,
    AssetPackageMutation,
    normalize_package_ecosystem,
    normalize_package_evidence,
    normalize_package_id,
    normalize_package_provider,
    normalize_redhat_distribution_cpe,
    normalize_rpm_architecture,
    normalize_rpm_epoch,
    normalize_rpm_name,
    normalize_rpm_release,
    normalize_rpm_version,
    normalize_source_rpm,
    redhat_rpm_purl,
)


_ACTIONS = {"added", "updated", "reactivated", "revoked"}
_SELECT = (
    "id, asset_id, asset_value, provider, ecosystem, name, epoch, version, release, "
    "architecture, source_rpm, distribution_cpe, purl, active, evidence_type, evidence, "
    "created_at, updated_at"
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
    if value not in PACKAGE_EVIDENCE_TYPES:
        raise ValueError("Invalid evidence type")
    return value


class SQLiteAssetPackageRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _record(row) -> AssetPackageEvidence:
        try:
            asset_value = normalize_domain(row[2])
            if row[2] != asset_value:
                raise ValueError("Non-canonical asset value")
            provider = normalize_package_provider(row[3])
            ecosystem = normalize_package_ecosystem(row[4])
            name = normalize_rpm_name(row[5])
            epoch = normalize_rpm_epoch(row[6])
            version = normalize_rpm_version(row[7])
            release = normalize_rpm_release(row[8])
            architecture = normalize_rpm_architecture(row[9])
            source_rpm = normalize_source_rpm(row[10])
            distribution_cpe = normalize_redhat_distribution_cpe(row[11])
            expected_purl = redhat_rpm_purl(
                name=name, version=version, release=release, architecture=architecture,
            )
            if row[12] != expected_purl:
                raise ValueError("Non-canonical package URL")
            if type(row[13]) is not int or row[13] not in {0, 1}:
                raise ValueError("Invalid active state")
            record = AssetPackageEvidence(
                id=_uuid(row[0]), asset_id=_uuid(row[1]), asset_value=asset_value,
                provider=provider, ecosystem=ecosystem, name=name, epoch=epoch,
                version=version, release=release, architecture=architecture,
                source_rpm=source_rpm, distribution_cpe=distribution_cpe,
                purl=expected_purl, active=bool(row[13]),
                evidence_type=_evidence_type(row[14]),
                evidence=normalize_package_evidence(row[15]),
                created_at=_timestamp(row[16]), updated_at=_timestamp(row[17]),
            )
            if datetime.fromisoformat(record.updated_at) < datetime.fromisoformat(record.created_at):
                raise ValueError("Reversed package evidence time")
            return record
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("RPM paket kanıtı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _event(row) -> AssetPackageEvent:
        try:
            event = AssetPackageEvent(
                id=_uuid(row[0]), asset_package_id=_uuid(row[1]), action=row[2],
                source_rpm=normalize_source_rpm(row[3]),
                evidence_type=_evidence_type(row[4]),
                evidence=normalize_package_evidence(row[5]),
                recorded_at=_timestamp(row[6]),
            )
            if event.action not in _ACTIONS:
                raise ValueError("Invalid package event action")
            return event
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("RPM paket kanıt geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _select_record(connection, package_id: str):
        return connection.execute(
            f"SELECT {_SELECT} FROM asset_packages WHERE id = ?", (package_id,),
        ).fetchone()

    @staticmethod
    def _validate_input(
        *, provider: str, ecosystem: str, name: str, epoch: int, version: str,
        release: str, architecture: str, source_rpm: str | None,
        distribution_cpe: str, purl: str, evidence_type: str, evidence: str,
        recorded_at: str,
    ) -> tuple:
        try:
            provider = normalize_package_provider(provider)
            ecosystem = normalize_package_ecosystem(ecosystem)
            name = normalize_rpm_name(name)
            epoch = normalize_rpm_epoch(epoch)
            version = normalize_rpm_version(version)
            release = normalize_rpm_release(release)
            architecture = normalize_rpm_architecture(architecture)
            source_rpm = normalize_source_rpm(source_rpm)
            distribution_cpe = normalize_redhat_distribution_cpe(distribution_cpe)
            expected_purl = redhat_rpm_purl(
                name=name, version=version, release=release, architecture=architecture,
            )
            if purl != expected_purl:
                raise ValueError("Non-canonical package URL")
            return (
                provider, ecosystem, name, epoch, version, release, architecture,
                source_rpm, distribution_cpe, expected_purl, _evidence_type(evidence_type),
                normalize_package_evidence(evidence), _timestamp(recorded_at),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("RPM paket kanıtı kaydedilemedi; alanları kontrol edin.") from error

    @staticmethod
    def _validate_event_input(
        *, evidence_type: str, evidence: str, recorded_at: str,
    ) -> tuple[str, str, str]:
        try:
            return (
                _evidence_type(evidence_type), normalize_package_evidence(evidence),
                _timestamp(recorded_at),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("RPM paket kanıtı işlemi kaydedilemedi; alanları kontrol edin.") from error

    def add(
        self, *, asset_value: str, provider: str, ecosystem: str, name: str, epoch: int,
        version: str, release: str, architecture: str, source_rpm: str | None,
        distribution_cpe: str, purl: str, evidence_type: str, evidence: str,
        recorded_at: str,
    ) -> AssetPackageMutation:
        (
            provider, ecosystem, name, epoch, version, release, architecture,
            source_rpm, distribution_cpe, purl, evidence_type, evidence, recorded_at,
        ) = self._validate_input(
            provider=provider, ecosystem=ecosystem, name=name, epoch=epoch,
            version=version, release=release, architecture=architecture,
            source_rpm=source_rpm, distribution_cpe=distribution_cpe, purl=purl,
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
                        "Paket kanıtı için adres önce './xti assets add' ile kaydedilmeli."
                    )
                row = connection.execute(
                    f"SELECT {_SELECT} FROM asset_packages WHERE asset_id = ? AND provider = ? "
                    "AND ecosystem = ? AND name = ? AND epoch = ? AND version = ? "
                    "AND release = ? AND architecture = ? AND distribution_cpe = ?",
                    (asset[0], provider, ecosystem, name, epoch, version, release,
                     architecture, distribution_cpe),
                ).fetchone()
                if row is None:
                    package_id = str(uuid4())
                    connection.execute(
                        "INSERT INTO asset_packages "
                        "(id, asset_id, asset_value, provider, ecosystem, name, epoch, version, "
                        "release, architecture, source_rpm, distribution_cpe, purl, active, "
                        "evidence_type, evidence, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                        (package_id, asset[0], asset[1], provider, ecosystem, name, epoch,
                         version, release, architecture, source_rpm, distribution_cpe, purl,
                         evidence_type, evidence, recorded_at, recorded_at),
                    )
                    action = "added"
                else:
                    current = self._record(row)
                    package_id = current.id
                    if current.active and (
                        current.source_rpm, current.evidence_type, current.evidence
                    ) == (source_rpm, evidence_type, evidence):
                        connection.rollback()
                        return AssetPackageMutation("unchanged", current)
                    action = "updated" if current.active else "reactivated"
                    effective_updated_at = max(
                        datetime.fromisoformat(current.updated_at),
                        datetime.fromisoformat(recorded_at),
                    ).isoformat()
                    connection.execute(
                        "UPDATE asset_packages SET active = 1, source_rpm = ?, "
                        "evidence_type = ?, evidence = ?, updated_at = ? WHERE id = ?",
                        (source_rpm, evidence_type, evidence, effective_updated_at, package_id),
                    )
                connection.execute(
                    "INSERT INTO asset_package_events "
                    "(id, asset_package_id, action, source_rpm, evidence_type, evidence, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid4()), package_id, action, source_rpm, evidence_type, evidence,
                     recorded_at),
                )
                result = self._record(self._select_record(connection, package_id))
                connection.commit()
                return AssetPackageMutation(action, result)
            except BaseException:
                connection.rollback()
                raise

    def revoke(
        self, package_id: str, *, evidence_type: str, evidence: str, recorded_at: str,
    ) -> AssetPackageMutation:
        package_id = normalize_package_id(package_id)
        evidence_type, evidence, recorded_at = self._validate_event_input(
            evidence_type=evidence_type, evidence=evidence, recorded_at=recorded_at,
        )
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._select_record(connection, package_id)
                if row is None:
                    raise ValidationError("RPM paket kanıtı bulunamadı.")
                current = self._record(row)
                if not current.active:
                    connection.rollback()
                    return AssetPackageMutation("unchanged", current)
                effective_updated_at = max(
                    datetime.fromisoformat(current.updated_at),
                    datetime.fromisoformat(recorded_at),
                ).isoformat()
                connection.execute(
                    "UPDATE asset_packages SET active = 0, updated_at = ? WHERE id = ?",
                    (effective_updated_at, package_id),
                )
                connection.execute(
                    "INSERT INTO asset_package_events "
                    "(id, asset_package_id, action, source_rpm, evidence_type, evidence, recorded_at) "
                    "VALUES (?, ?, 'revoked', ?, ?, ?, ?)",
                    (str(uuid4()), package_id, current.source_rpm, evidence_type, evidence,
                     recorded_at),
                )
                result = self._record(self._select_record(connection, package_id))
                connection.commit()
                return AssetPackageMutation("revoked", result)
            except BaseException:
                connection.rollback()
                raise

    def list(
        self, *, asset_value: str | None, active_only: bool, limit: int,
    ) -> tuple[AssetPackageEvidence, ...]:
        if type(active_only) is not bool or type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("RPM paket kanıtı liste isteği geçersiz.")
        clauses, values = [], []
        if asset_value is not None:
            clauses.append("asset_value = ?")
            values.append(asset_value)
        if active_only:
            clauses.append("active = 1")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                f"SELECT {_SELECT} FROM asset_packages {where} "
                "ORDER BY asset_value, provider, name, epoch, version, release, architecture, id "
                "LIMIT ?", (*values, limit),
            ).fetchall()
        return tuple(self._record(row) for row in rows)

    def details(self, package_id: str, *, event_limit: int) -> AssetPackageDetails:
        package_id = normalize_package_id(package_id)
        if type(event_limit) is not int or not 1 <= event_limit <= 100:
            raise ValidationError("RPM paket kanıt geçmişi sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = self._select_record(connection, package_id)
            if row is None:
                raise ValidationError("RPM paket kanıtı bulunamadı.")
            total = connection.execute(
                "SELECT COUNT(*) FROM asset_package_events WHERE asset_package_id = ?",
                (package_id,),
            ).fetchone()[0]
            event_rows = connection.execute(
                "SELECT id, asset_package_id, action, source_rpm, evidence_type, evidence, "
                "recorded_at FROM asset_package_events WHERE asset_package_id = ? "
                "ORDER BY rowid DESC LIMIT ?", (package_id, event_limit),
            ).fetchall()
            connection.rollback()
        record = self._record(row)
        events = tuple(self._event(event) for event in event_rows)
        if any(event.asset_package_id != record.id for event in events):
            raise StorageError("RPM paket kanıt geçmişi yanlış kayda bağlı; işlem durduruldu.")
        return AssetPackageDetails(record, events, total)
