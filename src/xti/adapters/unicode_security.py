"""Load and verify the bundled Unicode 18.0 security reference data."""

from __future__ import annotations

from functools import lru_cache
import hashlib
from importlib.resources import files
import re

from xti.domain.assets import ValidationError
from xti.domain.idn import IdnaRange, UNICODE_VERSION, UnicodeSecurityProfile


CONFUSABLES_SHA256 = "6ed3ee967c9dfdf6677d563c9985182fbc50a2efb7d6059cd57b2e2ce18f5b92"
IDNA_SHA256 = "a03b1eb38032268c696406a83f0972d6a815acd2c8d4151d42ec0fda70ffced1"
_VERSION = re.compile(r"^# Version: ([0-9]+\.[0-9]+\.[0-9]+)$", re.MULTILINE)


def _read(name: str, expected_sha256: str) -> str:
    content = files("xti").joinpath("data").joinpath(name).read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise RuntimeError(f"Paketlenmiş Unicode verisinin özeti uyuşmuyor: {name}")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"Paketlenmiş Unicode verisi UTF-8 değil: {name}") from exc
    match = _VERSION.search(text)
    if match is None or match.group(1) != UNICODE_VERSION:
        raise RuntimeError(f"Paketlenmiş Unicode verisinin sürümü beklenenden farklı: {name}")
    return text


def _confusables(text: str) -> dict[int, str]:
    result: dict[int, str] = {}
    for line_number, source_line in enumerate(text.splitlines(), start=1):
        content = source_line.partition("#")[0].strip()
        if not content:
            continue
        fields = [field.strip() for field in content.split(";")]
        if len(fields) < 2:
            raise RuntimeError(f"Geçersiz confusables satırı: {line_number}")
        try:
            source = int(fields[0], 16)
            target = "".join(chr(int(item, 16)) for item in fields[1].split())
        except (ValueError, OverflowError) as exc:
            raise RuntimeError(f"Geçersiz confusables kod noktası: {line_number}") from exc
        if source in result or not target:
            raise RuntimeError(f"Tekrarlı veya boş confusables satırı: {line_number}")
        result[source] = target
    return result


def _idna_ranges(text: str) -> tuple[IdnaRange, ...]:
    result: list[IdnaRange] = []
    prior_end = -1
    for line_number, source_line in enumerate(text.splitlines(), start=1):
        content = source_line.partition("#")[0].strip()
        if not content:
            continue
        fields = [field.strip() for field in content.split(";")]
        if len(fields) < 2:
            raise RuntimeError(f"Geçersiz IDNA eşleme satırı: {line_number}")
        bounds = fields[0].split("..", 1)
        try:
            start = int(bounds[0], 16)
            end = int(bounds[-1], 16)
            mapping = "".join(chr(int(item, 16)) for item in fields[2].split()) if len(fields) > 2 else ""
        except (ValueError, OverflowError) as exc:
            raise RuntimeError(f"Geçersiz IDNA kod noktası: {line_number}") from exc
        status = fields[1]
        if start <= prior_end or end < start:
            raise RuntimeError(f"Sırasız veya örtüşen IDNA aralığı: {line_number}")
        result.append(IdnaRange(start, end, status, mapping))
        prior_end = end
    return tuple(result)


@lru_cache(maxsize=1)
def unicode_security_profile() -> UnicodeSecurityProfile:
    confusables = _read("unicode_confusables_18_0_0.dat", CONFUSABLES_SHA256)
    idna = _read("unicode_idna_mapping_18_0_0.dat", IDNA_SHA256)
    return UnicodeSecurityProfile(_confusables(confusables), _idna_ranges(idna))


def canonicalize_observed_domain(value: str) -> str:
    """Canonicalize an untrusted source value without any network lookup."""
    try:
        return unicode_security_profile().to_ascii(value)
    except (RuntimeError, ValidationError):
        raise
