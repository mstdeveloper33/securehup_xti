"""No-follow bounded reader for operator-controlled xti-ail-v1 envelopes."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from xti.domain.assets import ValidationError
from xti.domain.darkweb_source_intake import MAX_AIL_BATCH_BYTES


def read_ail_envelope(path: Path) -> dict:
    path = Path(path)
    descriptor = None
    try:
        path_metadata = os.lstat(path)
        if not stat.S_ISREG(path_metadata.st_mode):
            raise ValidationError("AIL zarfı güvenli, symlink olmayan normal dosya olmalı.")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino) != (path_metadata.st_dev, path_metadata.st_ino)
            or metadata.st_size > MAX_AIL_BATCH_BYTES
        ):
            raise ValidationError("AIL zarfı normal dosya olmalı ve 2 MiB sınırını aşmamalı.")
        chunks, size = [], 0
        while True:
            block = os.read(descriptor, min(65_536, MAX_AIL_BATCH_BYTES + 1 - size))
            if not block:
                break
            size += len(block)
            if size > MAX_AIL_BATCH_BYTES:
                raise ValidationError("AIL zarfı 2 MiB sınırını aşıyor.")
            chunks.append(block)
        if os.fstat(descriptor).st_size != metadata.st_size:
            raise ValidationError("AIL zarfı okunurken değişti; yeniden deneyin.")
        payload = b"".join(chunks)
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)),
        )
    except ValidationError:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError("AIL zarfı güvenli ve tekil alanlı JSON olarak okunamadı.") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not isinstance(value, dict):
        raise ValidationError("AIL zarfının kökü JSON nesnesi olmalı.")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result
