"""Publish a complete local JSON report without overwriting an existing path."""

import json
import os
from pathlib import Path
import tempfile

from xti.domain.assets import ValidationError


MAX_REPORT_BYTES = 8 * 1024 * 1024


def write_report(report: dict, destination: Path) -> Path:
    payload = (json.dumps(report, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_REPORT_BYTES:
        raise ValidationError("Rapor 8 MiB sınırını aşıyor; veritabanı yedeğini kullan.")
    destination = destination.expanduser().absolute()
    if os.path.lexists(destination):
        raise ValidationError("Rapor konumu zaten var; farklı bir dosya adı seç.")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=".xti-report-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Same-directory link publishes atomically and refuses concurrent overwrite.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
