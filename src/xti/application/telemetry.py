"""Application service shared by terminal, engine and company JSON."""

from datetime import datetime, timezone

from xti.domain.telemetry import (
    PREFIX, READS, TelemetryPreview, normalize_import_request, parameters,
    preview_from_records, validate_preview,
)
from xti.ports.telemetry import TelemetryRepository


class TelemetryService:
    def __init__(self, repository: TelemetryRepository, *, now=None):
        self.repository = repository
        self.now = now or (lambda: datetime.now(timezone.utc).isoformat())

    def execute(self, operation: str, **values):
        values = parameters(operation, values)
        if operation in READS:
            return self.repository.read(operation, values)
        if operation == PREFIX + "ingest":
            preview = preview_from_records(values["records"], input_format="xti-sensor-v1")
            return self.import_preview(
                source_id=values["source_id"], expected_revision=values["expected_revision"],
                preview=preview, idempotency_key=values["idempotency_key"],
            )
        return self.repository.mutate(operation, values, self.now())

    def import_preview(self, *, source_id: str, expected_revision: int,
                       preview: TelemetryPreview, idempotency_key: str) -> dict:
        source_id, expected_revision, idempotency_key = normalize_import_request(
            source_id, expected_revision, idempotency_key,
        )
        preview = validate_preview(preview)
        started = self.now()
        run, replayed = self.repository.reserve(
            source_id, expected_revision, preview, idempotency_key, started,
        )
        if replayed:
            return {**run, "replayed": True}
        return self.repository.finish(run["id"], preview.records, self.now())
