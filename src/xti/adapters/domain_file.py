"""Bounded local file reader: no network access and no partial persistence."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.findings import DomainInput, ImportDocument


MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_LINES = 5_000
MAX_LINE_BYTES = 8_192
_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})"
)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Aynı JSON alanı birden fazla kez kullanılamaz.")
        result[name] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("Geçersiz JSON sayısı.")


def _observed_at(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
        raise ValidationError(
            "observed_at saat dilimi içermeli; örnek: 2026-10-28T12:00:00Z."
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError) as exc:
        raise ValidationError("observed_at geçerli bir tarih ve saat olmalı.") from exc


def read_domain_file(path: Path) -> ImportDocument:
    """Validate all records before returning an immutable import document."""
    path = Path(path).expanduser()
    extension = path.suffix.lower()
    if extension not in {".txt", ".jsonl"}:
        raise ValidationError("Adres listesi .txt veya .jsonl dosyası olmalı.")
    # Nonblocking open lets us reject pipes/devices instead of hanging on them.
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValidationError("Adres listesi normal bir dosya olmalı.")
        content = stream.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ValidationError("Dosya en fazla 2 MiB olabilir; daha küçük listelere böl.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("Dosya UTF-8 metin biçiminde olmalı.") from exc
    lines = text.split("\n")
    if lines and not lines[-1]:
        lines.pop()
    if len(lines) > MAX_LINES:
        raise ValidationError("Dosya en fazla 5000 satır içerebilir.")
    records = []
    for line_number, original_line in enumerate(lines, start=1):
        line = original_line.removesuffix("\r")
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            raise ValidationError(f"Dosyanın {line_number}. satırı çok uzun.")
        if not line.strip() or (extension == ".txt" and line.lstrip().startswith("#")):
            continue
        try:
            if extension == ".jsonl":
                value = json.loads(
                    line, object_pairs_hook=_unique_object, parse_constant=_invalid_constant,
                )
                if not isinstance(value, dict) or "domain" not in value:
                    raise ValidationError("Her JSON kaydı domain alanı olan bir nesne olmalı.")
                if set(value) - {"domain", "observed_at"}:
                    raise ValidationError("Yalnız domain ve observed_at alanları destekleniyor.")
                raw_domain = value["domain"]
                observed_at = _observed_at(value.get("observed_at"))
            else:
                raw_domain, observed_at = line, None
            domain = normalize_domain(raw_domain)
            records.append(DomainInput(domain, raw_domain, line_number, observed_at))
        except (ValueError, TypeError, RecursionError) as exc:
            message = str(exc) if isinstance(exc, ValidationError) else "Geçersiz JSON kaydı."
            raise ValidationError(f"Dosyanın {line_number}. satırı: {message}") from exc
    if not records:
        raise ValidationError("Dosyada işlenecek bir adres bulunamadı.")
    return ImportDocument(path.name, hashlib.sha256(content).hexdigest(), tuple(records))

