"""Application service for atomic IOC bulk preview/import/export."""

from collections.abc import Callable
from datetime import datetime, timezone
import json

from xti.application.stix_export import StixExportService
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_indicator_type
from xti.domain.ioc_bulk import (
    BulkIocExportBuild, BulkIocImportResult, BulkIocPreview, BulkIocRecord,
    csv_payload, json_payload, preview,
)
from xti.ports.cti_indicators import CtiIndicatorRepository


class IocBulkService:
    def __init__(
        self, repository: CtiIndicatorRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("IOC toplu işlem zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    def preview(self, payload: bytes, *, format: str) -> BulkIocPreview:
        return preview(payload, format)

    def import_payload(
        self, payload: bytes, *, format: str, expected_content_sha256: str,
        idempotency_key: str, import_source_name: str,
        import_source_reference: str,
    ) -> BulkIocImportResult:
        result = preview(payload, format)
        if result.content_sha256 != expected_content_sha256:
            raise ValidationError("IOC dosyası önizlemeden sonra değişmiş; yeniden önizleyin.")
        return self.repository.add_assertions_batch(
            result, idempotency_key=idempotency_key,
            import_source_name=import_source_name,
            import_source_reference=import_source_reference,
            recorded_at=self._now(),
        )

    def build_export(
        self, *, format: str, indicator_type: str | None = None,
    ) -> BulkIocExportBuild:
        if format not in {"csv", "json", "stix"}:
            raise ValidationError("IOC dışa aktarma biçimi csv, json veya stix olmalı.")
        if indicator_type is not None:
            indicator_type = normalize_indicator_type(indicator_type)
        generated_at = self._now()
        if format == "stix":
            build = StixExportService(
                self.repository,
                clock=lambda: datetime.fromisoformat(generated_at),
            ).build(indicator_type=indicator_type)
            payload = (json.dumps(
                build.bundle, ensure_ascii=True, allow_nan=False, indent=2,
            ) + "\n").encode("ascii")
            return BulkIocExportBuild(
                format, generated_at, indicator_type, build.indicator_count, payload,
            )
        snapshot = self.repository.export_snapshot(
            indicator_type=indicator_type, checked_at=generated_at,
        )
        records = tuple(sorted((
            BulkIocRecord(
                item.indicator.indicator_type, item.indicator.value,
                assertion.source_name, assertion.source_reference,
                assertion.confidence, assertion.valid_from, assertion.valid_until,
                assertion.description, assertion.last_seen_at,
            )
            for item in snapshot.items for assertion in item.current_assertions
        ), key=lambda item: (
            item.indicator_type, item.value, item.source_name, item.source_reference,
        )))
        payload = csv_payload(records) if format == "csv" else json_payload(records)
        return BulkIocExportBuild(
            format, generated_at, indicator_type, len(records), payload,
        )
