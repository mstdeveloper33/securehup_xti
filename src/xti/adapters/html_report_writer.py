"""Publish a private UTF-8 report atomically without following or replacing paths."""

from collections.abc import Iterable
import errno
import hashlib
import os
from pathlib import Path
import sys
from uuid import uuid4

from xti.domain.assets import ValidationError
from xti.domain.organization_export import OrganizationExportFile, OrganizationExportPublicationError


def _open_parent(destination: str) -> tuple[Path, int]:
    if (not isinstance(destination, str) or not destination.strip()
            or any(not character.isprintable() for character in destination)):
        raise ValidationError("HTML raporu için geçerli yeni dosya yolu gerekli.")
    path = Path(os.path.abspath(os.path.expanduser(destination)))
    if path.suffix.lower() not in {".html", ".htm"}:
        raise ValidationError("Rapor dosyasının uzantısı .html veya .htm olmalı.")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(path.anchor, flags)
    try:
        for part in path.parent.parts[1:]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return path, descriptor
    except OSError as error:
        os.close(descriptor)
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValidationError("Raporun klasör yolu sembolik bağlantı içermeyen gerçek klasörlerden oluşmalı.") from error
        raise


def _remove_own_file(parent: int, name: str, identity: tuple[int, int]) -> None:
    """Best-effort cleanup of the private staging name, never the public output."""
    try:
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (current.st_dev, current.st_ino) == identity:
            os.unlink(name, dir_fd=parent)
    except FileNotFoundError:
        pass


class AtomicHtmlReportWriter:
    def write_new(self, destination: str, chunks: Iterable[str], *,
                  max_bytes: int) -> OrganizationExportFile:
        if type(max_bytes) is not int or max_bytes < 1:
            raise ValidationError("Rapor dosyası boyut sınırı pozitif olmalı.")
        path, parent = _open_parent(destination)
        temporary = ".xti-report-" + uuid4().hex + ".tmp"
        identity: tuple[int, int] | None = None
        try:
            try:
                os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValidationError("Çıktı yolu zaten var; yeni bir HTML dosya adı seçin.")
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=parent)
            with os.fdopen(descriptor, "wb") as output:
                info = os.fstat(output.fileno())
                identity = (info.st_dev, info.st_ino)
                size, digest = 0, hashlib.sha256()
                for chunk in chunks:
                    if not isinstance(chunk, str):
                        raise ValidationError("HTML rapor çizimi geçerli metin üretmedi; dosya yazılmadı.")
                    encoded = chunk.encode("utf-8")
                    size += len(encoded)
                    if size > max_bytes:
                        raise ValidationError(f"HTML raporu {max_bytes} bayt sınırını aşıyor; dosya yazılmadı.")
                    output.write(encoded)
                    digest.update(encoded)
                output.flush()
                os.fsync(output.fileno())
                try:
                    os.link(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent,
                            follow_symlinks=False)
                except FileExistsError as error:
                    raise ValidationError("Çıktı yolu başka bir işlem tarafından oluşturuldu; üzerine yazılmadı.") from error
                # The public name may now be replaced by another writer. Never
                # unlink it during cleanup. A directory-sync failure can leave
                # this complete, file-synced output alongside the reported error.
                try:
                    os.unlink(temporary, dir_fd=parent)
                    os.fsync(parent)
                except OSError as error:
                    raise OrganizationExportPublicationError(str(path)) from error
            return OrganizationExportFile(str(path), size, digest.hexdigest())
        finally:
            primary_error = sys.exc_info()[0] is not None
            cleanup_error: OSError | None = None
            try:
                if identity is not None:
                    _remove_own_file(parent, temporary, identity)
            except OSError as error:
                cleanup_error = error
            try:
                os.close(parent)
            except OSError as error:
                cleanup_error = cleanup_error or error
            if cleanup_error is not None and not primary_error:
                raise cleanup_error
