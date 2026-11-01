"""Atomically publish a STIX JSON bundle without replacing existing evidence."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile

from xti.domain.assets import ValidationError


MAX_STIX_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class StixArtifact:
    destination: str
    byte_count: int
    sha256: str


def write_stix_bundle(bundle: dict, destination: Path) -> StixArtifact:
    payload = (
        json.dumps(bundle, ensure_ascii=True, allow_nan=False, indent=2) + "\n"
    ).encode("utf-8")
    if len(payload) > MAX_STIX_BYTES:
        raise ValidationError(
            "STIX paketi 32 MiB sınırını aşıyor; tür filtresiyle ayrı paketler üret."
        )
    destination = destination.expanduser().absolute()
    if os.path.lexists(destination):
        raise ValidationError(
            "STIX çıktı konumu zaten var; farklı bir dosya adı seç."
        )
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=".xti-stix-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return StixArtifact(
        destination=str(destination), byte_count=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )
