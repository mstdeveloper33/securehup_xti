"""Coordinate the managed Harvester installer and its running workers.

The lock inode is persistent. Children inherit its descriptor so a killed
launcher cannot release an installation still being changed by a child.
Only local POSIX filesystems are supported, matching the existing engine.
"""

from contextlib import contextmanager
import errno
import fcntl
import os
from pathlib import Path
import stat
from typing import Iterator


LOCK_NAME = '.theharvester.lock'
JOURNAL_NAME = '.theharvester-install.json'


class ToolInstallationError(Exception):
    pass


def pending_installation(parent: Path) -> bool:
    # Broken links and malformed journals must also block use, never imply ready.
    return os.path.lexists(Path(parent) / JOURNAL_NAME)


@contextmanager
def tool_installation_lock(parent: Path, *, exclusive: bool,
                           create: bool = True) -> Iterator[int | None]:
    """Fail promptly on contention; metadata reads may avoid creating a file.

    With create=False a missing lock yields None. This mode is only for
    advisory metadata observations, not worker execution or installation.
    """
    descriptor = None
    try:
        parent = Path(parent)
        if parent.is_symlink() or not parent.is_dir():
            raise ToolInstallationError('theHarvester araç klasörü gerçek bir dizin olmalı.')
        path = parent.resolve(strict=True) / LOCK_NAME
        flags = (os.O_RDWR if create else os.O_RDONLY) | os.O_NONBLOCK | os.O_NOFOLLOW
        if create:
            try:
                descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
                os.fchmod(descriptor, 0o600)
            except FileExistsError:
                descriptor = os.open(path, flags)
        else:
            try:
                descriptor = os.open(path, flags)
            except FileNotFoundError:
                descriptor = None
        if descriptor is not None:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ToolInstallationError('theHarvester kilidi tek bağlantılı normal dosya olmalı.')
            try:
                operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in {errno.EAGAIN, errno.EACCES}:
                    raise ToolInstallationError(
                        'theHarvester kurulumu veya araç çalışması sürüyor; tamamlanmasını bekle.'
                    ) from error
                raise
    except BaseException as error:
        if descriptor is not None:
            os.close(descriptor)
        if isinstance(error, OSError):
            raise ToolInstallationError('theHarvester kurulum kilidine erişilemedi.') from error
        raise
    try:
        yield descriptor
    finally:
        # Do not LOCK_UN explicitly: a child may still own this open description.
        if descriptor is not None:
            os.close(descriptor)
