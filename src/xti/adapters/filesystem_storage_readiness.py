"""Bounded, no-follow filesystem inspection for local recovery readiness."""

from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import stat

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.storage_readiness import StorageReadinessSnapshot


_MAX_SCANNED_FILES = 10_000
_MAX_BACKUPS = 1_000


def _timestamp(value: float) -> str:
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError) as error:
        raise StorageError("Dosya zamanı desteklenen aralığın dışında.") from error


class FileSystemStorageReadinessRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path).expanduser().absolute()
        self.data_directory = self.database_path.parent

    @staticmethod
    def _tree_usage(root: Path) -> tuple[int, int, int, bool]:
        total = files = ignored = 0
        complete = True
        stack = [root]
        try:
            while stack:
                directory = stack.pop()
                with os.scandir(directory) as entries:
                    for entry in entries:
                        details = entry.stat(follow_symlinks=False)
                        if stat.S_ISLNK(details.st_mode):
                            ignored += 1
                        elif stat.S_ISDIR(details.st_mode):
                            stack.append(Path(entry.path))
                        elif stat.S_ISREG(details.st_mode):
                            files += 1
                            total += details.st_size
                            if files >= _MAX_SCANNED_FILES:
                                complete = False
                                stack.clear()
                                break
                        else:
                            ignored += 1
        except (OSError, PermissionError) as error:
            raise StorageError("Kayıt klasörünün disk kullanımı okunamadı.") from error
        return total, files, ignored, complete

    @staticmethod
    def _backup_files(directory: Path) -> tuple[list[tuple[Path, os.stat_result]], int, bool]:
        if not directory.exists() and not directory.is_symlink():
            return [], 0, True
        try:
            root = directory.lstat()
            if not stat.S_ISDIR(root.st_mode) or stat.S_ISLNK(root.st_mode):
                raise StorageError("Yedek klasörü güvenli bir yerel klasör değil.")
            items = []
            ignored = 0
            complete = True
            with os.scandir(directory) as entries:
                for entry in entries:
                    details = entry.stat(follow_symlinks=False)
                    if (
                        stat.S_ISREG(details.st_mode)
                        and not stat.S_ISLNK(details.st_mode)
                        and entry.name.endswith(".db")
                    ):
                        if len(items) >= _MAX_BACKUPS:
                            complete = False
                            break
                        items.append((Path(entry.path), details))
                    else:
                        ignored += 1
            return items, ignored, complete
        except StorageError:
            raise
        except (OSError, PermissionError) as error:
            raise StorageError("Yedek klasörü okunamadı.") from error

    @staticmethod
    def _verify(path: Path) -> tuple[bool, int | None, str | None]:
        repository = SQLiteAssetRepository(path)
        try:
            with repository._connection(readonly=True, allow_legacy=True) as connection:
                version = repository._validate_schema(connection, allow_legacy=True)
                repository._check_integrity(connection)
            return True, version, None
        except StorageError as error:
            return False, None, str(error)

    def snapshot(self) -> StorageReadinessSnapshot:
        if self.data_directory.is_symlink() or not self.data_directory.is_dir():
            raise StorageError("Kayıt klasörü bulunamadı veya güvenli bir klasör değil.")
        data_bytes, scanned_files, ignored, tree_complete = self._tree_usage(
            self.data_directory,
        )
        backup_directory = self.data_directory / "backups"
        backups, backup_ignored, backup_complete = self._backup_files(backup_directory)
        ignored += backup_ignored
        backup_bytes = sum(details.st_size for _, details in backups)
        latest = max(backups, key=lambda item: (item[1].st_mtime_ns, item[0].name), default=None)
        latest_path = latest_bytes = latest_modified = latest_valid = None
        latest_version = latest_error = None
        if latest is not None:
            latest_path = str(latest[0].absolute())
            latest_bytes = latest[1].st_size
            latest_modified = _timestamp(latest[1].st_mtime)
            latest_valid, latest_version, latest_error = self._verify(latest[0])
        try:
            disk = shutil.disk_usage(self.data_directory)
        except OSError as error:
            raise StorageError("Kayıt diskinin kapasitesi okunamadı.") from error
        return StorageReadinessSnapshot(
            str(self.data_directory), str(self.database_path), data_bytes,
            backup_bytes, scanned_files, ignored,
            tree_complete and backup_complete,
            disk.total, disk.free, len(backups), latest_path, latest_bytes,
            latest_modified, latest_valid, latest_version, latest_error,
        )
