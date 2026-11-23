"""Build and verify immutable local case evidence packages."""

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from xti.domain.assets import ValidationError
from xti.domain.case_packages import CasePackageArtifact
from xti.domain.cases import normalize_case_id
from xti.ports.case_packages import CasePackagePublisher, CasePackageReader


class CasePackageService:
    def __init__(self, reader: CasePackageReader, publisher: CasePackagePublisher, *, clock: Callable[[], datetime] | None = None) -> None:
        self.reader = reader
        self.publisher = publisher
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def create(self, case_id: str, destination: Path, *, include_pdf: bool = False) -> CasePackageArtifact:
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("Vaka paketi oluşturma zamanı geçersiz.")
        snapshot = self.reader.snapshot(normalize_case_id(case_id))
        return self.publisher.publish(
            snapshot, destination, created_at=now.astimezone(timezone.utc).isoformat(),
            include_pdf=include_pdf,
        )

    def verify(self, destination: Path) -> CasePackageArtifact:
        return self.publisher.verify(destination)
