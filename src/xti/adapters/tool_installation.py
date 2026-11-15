"""Coordinate managed tool installation and its running processes.

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
BRAND_LOCK_NAME = '.brand-install.lock'
BRAND_JOURNAL_NAME = '.brand-install.json'


class ToolInstallationError(Exception):
    pass


def pending_installation(parent: Path, *, journal_name: str = JOURNAL_NAME) -> bool:
    # Broken links and malformed journals must also block use, never imply ready.
    return os.path.lexists(Path(parent) / journal_name)


def brand_installation_pending(project: Path) -> bool:
    """Legacy artifacts have no ownership journal and must remain untouched."""
    project = Path(project)
    return any(os.path.lexists(project / name) for name in (
        BRAND_JOURNAL_NAME, '.venv-install.lock', '.venv-backup',
        '.venv/.xti-installing',
    ))


def brand_installation_lock(project: Path, *, exclusive: bool, create: bool = True):
    return tool_installation_lock(
        project, exclusive=exclusive, create=create,
        lock_name=BRAND_LOCK_NAME, label='Marka araçları',
    )


@contextmanager
def tool_installation_lock(parent: Path, *, exclusive: bool,
                           create: bool = True, lock_name: str = LOCK_NAME,
                           label: str = 'theHarvester') -> Iterator[int | None]:
    """Fail promptly on contention; metadata reads may avoid creating a file.

    With create=False a missing lock yields None. This mode is only for
    advisory metadata observations, not worker execution or installation.
    """
    descriptor = None
    try:
        if not isinstance(lock_name, str) or not lock_name or lock_name in {'.', '..'} or Path(lock_name).name != lock_name:
            raise ToolInstallationError('Kurulum kilidi adı tek bir dosya adı olmalı.')
        parent = Path(parent)
        if parent.is_symlink() or not parent.is_dir():
            raise ToolInstallationError(f'{label} araç klasörü gerçek bir dizin olmalı.')
        path = parent.resolve(strict=True) / lock_name
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
                raise ToolInstallationError(f'{label} kilidi tek bağlantılı normal dosya olmalı.')
            try:
                operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in {errno.EAGAIN, errno.EACCES}:
                    raise ToolInstallationError(
                        f'{label} kurulumu veya araç çalışması sürüyor; tamamlanmasını bekle.'
                    ) from error
                raise
    except BaseException as error:
        if descriptor is not None:
            os.close(descriptor)
        if isinstance(error, OSError):
            raise ToolInstallationError(f'{label} kurulum kilidine erişilemedi.') from error
        raise
    try:
        yield descriptor
    finally:
        # Do not LOCK_UN explicitly: a child may still own this open description.
        if descriptor is not None:
            os.close(descriptor)
