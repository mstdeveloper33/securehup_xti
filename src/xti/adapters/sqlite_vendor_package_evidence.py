"""Atomic structured evidence for a selected exact Red Hat RPM/VEX relation."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.packages import normalize_package_id
from xti.domain.vendor_advisory import normalize_vendor_product_id
from xti.domain.vendor_package_evidence import (
    VENDOR_PACKAGE_EVIDENCE_ACTIONS,
    VendorPackageEvidence,
    VendorPackageEvidenceDetails,
    VendorPackageEvidenceEvent,
    VendorPackageEvidenceMutation,
    normalize_match_kind,
    normalize_vendor_document_version,
    normalize_vendor_evidence_summary,
    normalize_vendor_identifier,
    normalize_vendor_package_evidence_id,
    normalize_vendor_sha256,
    normalize_vendor_status,
    normalize_vendor_timestamp,
    validate_vendor_evidence_keys,
    validate_vendor_source_url,
)
from xti.domain.packages import normalize_redhat_distribution_cpe
from xti.domain.vulnerability_exposures import normalize_exposure_id


_SELECT = (
    "id, exposure_id, asset_package_id, provider, cve_id, source_url, source_sha256, "
    "document_version, current_release_at, vendor_status, match_kind, vex_product_id, "
    "component_product_id, component_purl, context_product_id, context_cpe, "
    "package_updated_at, summary, active, created_at, updated_at"
)
_MAX_EVENTS = 10_000


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid UUID")
    normalized = str(UUID(value))
    if value != normalized:
        raise ValueError("Non-canonical UUID")
    return normalized


def _timestamp(value: object, field: str = "Kayıt zamanı") -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid timestamp")
    return normalize_vendor_timestamp(value, field=field)


class SQLiteVendorPackageEvidenceRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _record(row) -> VendorPackageEvidence:
        try:
            exposure_id, package_id, cve_id = validate_vendor_evidence_keys(
                row[1], row[2], row[4],
            )
            if row[3] != "redhat":
                raise ValueError("Invalid provider")
            record = VendorPackageEvidence(
                id=_uuid(row[0]), exposure_id=exposure_id,
                asset_package_id=package_id, provider=row[3], cve_id=cve_id,
                source_url=validate_vendor_source_url(row[5], cve_id=cve_id),
                source_sha256=normalize_vendor_sha256(row[6]),
                document_version=normalize_vendor_document_version(row[7]),
                current_release_at=_timestamp(row[8], "VEX güncel yayım zamanı"),
                vendor_status=normalize_vendor_status(row[9]),
                match_kind=normalize_match_kind(row[10]),
                vex_product_id=normalize_vendor_product_id(row[11], field="VEX ürün kimliği"),
                component_product_id=normalize_vendor_product_id(
                    row[12], field="VEX bileşen kimliği",
                ),
                component_purl=normalize_vendor_identifier(row[13], field="VEX bileşen PURL"),
                context_product_id=normalize_vendor_product_id(
                    row[14], field="VEX bağlam ürün kimliği",
                ),
                context_cpe=normalize_redhat_distribution_cpe(row[15]),
                package_updated_at=_timestamp(row[16], "RPM kanıt zamanı"),
                summary=normalize_vendor_evidence_summary(row[17]),
                active=bool(row[18]), created_at=_timestamp(row[19]),
                updated_at=_timestamp(row[20]),
            )
            if type(row[18]) is not int or row[18] not in {0, 1}:
                raise ValueError("Invalid active state")
            if datetime.fromisoformat(record.updated_at) < datetime.fromisoformat(record.created_at):
                raise ValueError("Reversed evidence time")
            return record
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Kesin üretici paket kanıtı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _event(row) -> VendorPackageEvidenceEvent:
        try:
            event = VendorPackageEvidenceEvent(
                id=_uuid(row[0]), evidence_id=_uuid(row[1]), action=row[2],
                summary=normalize_vendor_evidence_summary(row[3]),
                recorded_at=_timestamp(row[4]),
            )
            if event.action not in VENDOR_PACKAGE_EVIDENCE_ACTIONS:
                raise ValueError("Invalid action")
            return event
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Kesin üretici paket kanıt geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _select(connection, evidence_id: str):
        return connection.execute(
            f"SELECT {_SELECT} FROM vulnerability_vendor_package_evidence WHERE id = ?",
            (evidence_id,),
        ).fetchone()

    @staticmethod
    def _validate_write(**values) -> dict[str, str]:
        try:
            exposure_id, package_id, cve_id = validate_vendor_evidence_keys(
                values["exposure_id"], values["asset_package_id"], values["cve_id"],
            )
            if values["provider"] != "redhat":
                raise ValidationError("Kesin üretici kanıtı şimdilik yalnız Red Hat olabilir.")
            return {
                "exposure_id": exposure_id,
                "asset_package_id": package_id,
                "provider": "redhat",
                "cve_id": cve_id,
                "source_url": validate_vendor_source_url(values["source_url"], cve_id=cve_id),
                "source_sha256": normalize_vendor_sha256(values["source_sha256"]),
                "document_version": normalize_vendor_document_version(values["document_version"]),
                "current_release_at": _timestamp(
                    values["current_release_at"], "VEX güncel yayım zamanı",
                ),
                "vendor_status": normalize_vendor_status(values["vendor_status"]),
                "match_kind": normalize_match_kind(values["match_kind"]),
                "vex_product_id": normalize_vendor_product_id(
                    values["vex_product_id"], field="VEX ürün kimliği",
                ),
                "component_product_id": normalize_vendor_product_id(
                    values["component_product_id"], field="VEX bileşen kimliği",
                ),
                "component_purl": normalize_vendor_identifier(
                    values["component_purl"], field="VEX bileşen PURL",
                ),
                "context_product_id": normalize_vendor_product_id(
                    values["context_product_id"], field="VEX bağlam ürün kimliği",
                ),
                "context_cpe": normalize_redhat_distribution_cpe(values["context_cpe"]),
                "package_updated_at": _timestamp(values["package_updated_at"], "RPM kanıt zamanı"),
                "summary": normalize_vendor_evidence_summary(values["summary"]),
                "recorded_at": _timestamp(values["recorded_at"]),
            }
        except (TypeError, ValueError, KeyError, ValidationError, OverflowError) as error:
            raise ValidationError("Kesin üretici paket kanıtı alanları geçersiz.") from error

    def add(self, **values) -> VendorPackageEvidenceMutation:
        data = self._validate_write(**values)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                exposure = connection.execute(
                    "SELECT ve.cve_id, ap.asset_id FROM vulnerability_exposures ve "
                    "JOIN asset_products ap ON ap.id = ve.asset_product_id WHERE ve.id = ?",
                    (data["exposure_id"],),
                ).fetchone()
                if exposure is None:
                    raise ValidationError("Zafiyet maruziyet incelemesi bulunamadı.")
                package = connection.execute(
                    "SELECT asset_id, active, updated_at FROM asset_packages WHERE id = ?",
                    (data["asset_package_id"],),
                ).fetchone()
                if package is None:
                    raise ValidationError("RPM paket kanıtı bulunamadı.")
                if exposure[0] != data["cve_id"] or exposure[1] != package[0]:
                    raise ValidationError("Maruziyet, CVE ve RPM aynı varlık bağlamında olmalı.")
                if package[1] != 1 or _timestamp(package[2], "RPM kanıt zamanı") != data["package_updated_at"]:
                    raise ValidationError(
                        "RPM kanıtı seçimden sonra değişti veya kaldırıldı; eşleşmeyi yeniden çalıştırın."
                    )
                row = connection.execute(
                    f"SELECT {_SELECT} FROM vulnerability_vendor_package_evidence "
                    "WHERE exposure_id = ? AND asset_package_id = ? AND source_sha256 = ? "
                    "AND vex_product_id = ? AND vendor_status = ? AND package_updated_at = ?",
                    (data["exposure_id"], data["asset_package_id"], data["source_sha256"],
                     data["vex_product_id"], data["vendor_status"],
                     data["package_updated_at"]),
                ).fetchone()
                immutable = (
                    data["provider"], data["cve_id"], data["source_url"],
                    data["source_sha256"], data["document_version"],
                    data["current_release_at"], data["vendor_status"], data["match_kind"],
                    data["vex_product_id"], data["component_product_id"],
                    data["component_purl"], data["context_product_id"], data["context_cpe"],
                    data["package_updated_at"],
                )
                if row is None:
                    evidence_id, action = str(uuid4()), "added"
                    connection.execute(
                        "INSERT INTO vulnerability_vendor_package_evidence "
                        "(id, exposure_id, asset_package_id, provider, cve_id, source_url, "
                        "source_sha256, document_version, current_release_at, vendor_status, "
                        "match_kind, vex_product_id, component_product_id, component_purl, "
                        "context_product_id, context_cpe, package_updated_at, summary, active, "
                        "created_at, updated_at) VALUES "
                        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                        (evidence_id, data["exposure_id"], data["asset_package_id"], *immutable,
                         data["summary"], data["recorded_at"], data["recorded_at"]),
                    )
                else:
                    current = self._record(row)
                    evidence_id = current.id
                    current_immutable = (
                        current.provider, current.cve_id, current.source_url,
                        current.source_sha256, current.document_version,
                        current.current_release_at, current.vendor_status, current.match_kind,
                        current.vex_product_id, current.component_product_id,
                        current.component_purl, current.context_product_id, current.context_cpe,
                        current.package_updated_at,
                    )
                    if current_immutable != immutable:
                        raise StorageError("Kesin üretici kanıtı tekillik kaydı çelişkili.")
                    if current.active and current.summary == data["summary"]:
                        connection.rollback()
                        return VendorPackageEvidenceMutation("unchanged", current)
                    action = "updated" if current.active else "reactivated"
                    updated_at = max(
                        datetime.fromisoformat(current.updated_at),
                        datetime.fromisoformat(data["recorded_at"]),
                    ).isoformat()
                    connection.execute(
                        "UPDATE vulnerability_vendor_package_evidence SET summary = ?, active = 1, "
                        "updated_at = ? WHERE id = ?",
                        (data["summary"], updated_at, evidence_id),
                    )
                connection.execute(
                    "INSERT INTO vulnerability_vendor_package_evidence_events "
                    "(id, evidence_id, action, summary, recorded_at) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid4()), evidence_id, action, data["summary"], data["recorded_at"]),
                )
                result = self._record(self._select(connection, evidence_id))
                connection.commit()
                return VendorPackageEvidenceMutation(action, result)
            except BaseException:
                connection.rollback()
                raise

    def revoke(
        self, evidence_id: str, *, reason: str, recorded_at: str,
    ) -> VendorPackageEvidenceMutation:
        evidence_id = normalize_vendor_package_evidence_id(evidence_id)
        reason = normalize_vendor_evidence_summary(reason)
        recorded_at = _timestamp(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._select(connection, evidence_id)
                if row is None:
                    raise ValidationError("Kesin üretici paket kanıtı bulunamadı.")
                current = self._record(row)
                if not current.active:
                    connection.rollback()
                    return VendorPackageEvidenceMutation("unchanged", current)
                updated_at = max(
                    datetime.fromisoformat(current.updated_at),
                    datetime.fromisoformat(recorded_at),
                ).isoformat()
                connection.execute(
                    "UPDATE vulnerability_vendor_package_evidence SET active = 0, "
                    "updated_at = ? WHERE id = ?", (updated_at, evidence_id),
                )
                connection.execute(
                    "INSERT INTO vulnerability_vendor_package_evidence_events "
                    "(id, evidence_id, action, summary, recorded_at) "
                    "VALUES (?, ?, 'revoked', ?, ?)",
                    (str(uuid4()), evidence_id, reason, recorded_at),
                )
                result = self._record(self._select(connection, evidence_id))
                connection.commit()
                return VendorPackageEvidenceMutation("revoked", result)
            except BaseException:
                connection.rollback()
                raise

    def list(
        self, *, exposure_id: str, active_only: bool, limit: int,
    ) -> tuple[VendorPackageEvidence, ...]:
        exposure_id = normalize_exposure_id(exposure_id)
        if type(active_only) is not bool or type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Kesin üretici kanıtı liste isteği geçersiz.")
        with self._storage._connection(readonly=True) as connection:
            if connection.execute(
                "SELECT 1 FROM vulnerability_exposures WHERE id = ?", (exposure_id,),
            ).fetchone() is None:
                raise ValidationError("Zafiyet maruziyet incelemesi bulunamadı.")
            active = "AND active = 1" if active_only else ""
            rows = connection.execute(
                f"SELECT {_SELECT} FROM vulnerability_vendor_package_evidence "
                f"WHERE exposure_id = ? {active} ORDER BY created_at, id LIMIT ?",
                (exposure_id, limit),
            ).fetchall()
        return tuple(self._record(row) for row in rows)

    def details(
        self, evidence_id: str, *, event_limit: int,
    ) -> VendorPackageEvidenceDetails:
        evidence_id = normalize_vendor_package_evidence_id(evidence_id)
        if type(event_limit) is not int or not 1 <= event_limit <= 100:
            raise ValidationError("Kesin üretici kanıt geçmiş sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = self._select(connection, evidence_id)
            if row is None:
                raise ValidationError("Kesin üretici paket kanıtı bulunamadı.")
            event_rows = connection.execute(
                "SELECT id, evidence_id, action, summary, recorded_at "
                "FROM vulnerability_vendor_package_evidence_events WHERE evidence_id = ? "
                "ORDER BY rowid DESC LIMIT ?", (evidence_id, _MAX_EVENTS + 1),
            ).fetchall()
            connection.rollback()
        if len(event_rows) > _MAX_EVENTS:
            raise StorageError("Kesin üretici paket kanıt geçmişi 10.000 olayı aşıyor.")
        record = self._record(row)
        events = tuple(self._event(event) for event in event_rows)
        if any(event.evidence_id != record.id for event in events):
            raise StorageError("Kesin üretici paket kanıt geçmişi yanlış kayda bağlı.")
        return VendorPackageEvidenceDetails(record, events[:event_limit], len(events))
