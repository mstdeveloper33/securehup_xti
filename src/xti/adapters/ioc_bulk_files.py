"""Bounded IOC bulk file input and exclusive atomic output."""

import hashlib
import os
from pathlib import Path
import stat
import tempfile

from xti.domain.assets import ValidationError
from xti.domain.ioc_bulk import BulkIocArtifact, MAX_BULK_BYTES


def read_bulk_file(path: Path) -> bytes:
    path = path.expanduser().absolute()
    descriptor = None
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or path.is_symlink()
                or not 1 <= info.st_size <= MAX_BULK_BYTES):
            raise ValidationError("IOC girdisi 1 bayt–32 MiB arasında gerçek bir dosya olmalı.")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        if ((opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)
                or not stat.S_ISREG(opened.st_mode)
                or not 1 <= opened.st_size <= MAX_BULK_BYTES):
            raise ValidationError("IOC toplu dosyası okunurken değişti; işlem durduruldu.")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            payload = stream.read(MAX_BULK_BYTES + 1)
        if len(payload) != opened.st_size:
            raise ValidationError("IOC toplu dosyası okunurken değişti; işlem durduruldu.")
        return payload
    except ValidationError:
        raise
    except OSError as error:
        raise ValidationError("IOC toplu dosyası okunamadı.") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def write_bulk_file(
    payload: bytes, destination: Path, *, format: str, record_count: int,
) -> BulkIocArtifact:
    if not isinstance(payload, bytes) or len(payload) > MAX_BULK_BYTES:
        raise ValidationError("IOC dışa aktarma çıktısı 32 MiB sınırını aşıyor.")
    destination = destination.expanduser().absolute()
    if os.path.lexists(destination):
        raise ValidationError("IOC çıktı dosyası zaten var; farklı bir konum seçin.")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".xti-ioc-", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return BulkIocArtifact(
        str(destination), format, record_count, len(payload),
        hashlib.sha256(payload).hexdigest(),
    )
