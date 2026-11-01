"""Exclusive local scan execution without holding a database transaction open."""

from contextlib import contextmanager
import errno
import fcntl
import os
from pathlib import Path
import stat
from typing import Iterator

from xti.adapters.sqlite import StorageError
from xti.ports.jobs import WorkerBusyError


class LocalExecutionLock:
    """Keep one persistent lock inode beside a database on a local filesystem.

    Closing the descriptor releases the lock, including after process death.
    The file must never be unlinked on release: waiters could otherwise hold
    the old inode while a later worker acquires a replacement file.
    """

    def __init__(self, database: Path) -> None:
        self.database = Path(database).expanduser().absolute()

    def _open(self) -> int:
        descriptor: int | None = None
        try:
            # Resolve aliases of the containing directory, without creating it.
            parent = self.database.parent.resolve(strict=True)
            if not parent.is_dir() or self.database.is_symlink():
                raise StorageError("Çalıştırma kilidi için geçerli bir kayıt klasörü gerekli.")
            path = parent / (self.database.name + ".worker.lock")
            flags = os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW
            try:
                descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
                os.fchmod(descriptor, 0o600)
            except FileExistsError:
                # Existing content and permissions are preserved.
                descriptor = os.open(path, flags)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise StorageError("Çalıştırma kilidi normal bir dosya olmalı.")
            return descriptor
        except BaseException as exc:
            if descriptor is not None:
                os.close(descriptor)
            if isinstance(exc, OSError):
                raise StorageError(
                    "Çalıştırma kilidi açılamadı. Kayıt klasörünü, dosya türünü ve izinleri kontrol et."
                ) from exc
            raise

    @contextmanager
    def acquire(self) -> Iterator[None]:
        descriptor = self._open()
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EAGAIN}:
                    raise WorkerBusyError(
                        "Başka bir arama çalışıyor. Bitmesini bekle veya işi kuyruğa ekle."
                    ) from exc
                raise StorageError("Çalıştırma kilidi alınamadı.") from exc
            yield
        finally:
            # Closing a descriptor releases its flock; preserve the lock inode.
            os.close(descriptor)
