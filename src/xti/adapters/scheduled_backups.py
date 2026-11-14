"""Verified SQLite backup/restore and receipt-owned retention in a dedicated folder."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.scheduling import ScheduledBackupPreflight, ScheduledBackupReport, normalize_retention


_MANIFEST = "ownership.json"
_MAX_ENTRIES = 10_000
_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_RESERVE = 64 * 1024 * 1024
_NAME = re.compile(r"scheduled-([0-9a-f-]{36})\.db\Z")


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("invalid UUID")
    return value


def _time(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("invalid timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.astimezone(timezone.utc).isoformat() != value:
        raise ValueError("noncanonical timestamp")
    return value


def _digest(path):
    """Reject links/special files and detect replacement during a bounded-stream read."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise StorageError("Zamanlanmış yedek normal bir dosya olmalı.")
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            after = os.fstat(stream.fileno())
        current = path.lstat()
        identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
        if identity(before) != identity(after) or identity(after) != identity(current) or not stat.S_ISREG(current.st_mode):
            raise StorageError("Zamanlanmış yedek okuma sırasında değişti; silme yapılmadı.")
        return digest, before.st_size, (before.st_dev, before.st_ino)
    except OSError as error:
        raise StorageError("Zamanlanmış yedek okunamadı; dosyalar korunuyor.") from error


@dataclass(frozen=True)
class _Inventory:
    entries: tuple[dict, ...]
    warnings: tuple[str, ...]
    manifest_bytes: bytes | None


class ScheduledBackupMaintenance:
    """Only the caller's shared execution lock coordinates prepare operations."""

    def __init__(self, database: Path):
        self.database = Path(database).expanduser().absolute()
        self.storage = SQLiteAssetRepository(self.database)
        self.directory = self.database.parent / "scheduled-backups"

    def _location(self):
        if self.database.is_symlink() or not self.database.is_file():
            raise StorageError("Zamanlanmış yedek için mevcut gerçek veritabanı gerekli.")
        if self.directory.is_symlink() or (self.directory.exists() and not self.directory.is_dir()):
            raise StorageError("scheduled-backups gerçek bir klasör olmalı; dosyalar korunuyor.")
        if self.directory.exists():
            info = self.directory.stat()
            if info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise StorageError("scheduled-backups kullanıcıya ait olmalı ve başkalarınca yazılamamalı.")

    def _manifest(self, entries):
        payload = {"version": 1, "database": str(self.database.parent.resolve(strict=True) / self.database.name), "entries": list(entries)}
        return _canonical({"payload": payload, "sha256": hashlib.sha256(_canonical(payload)).hexdigest()})

    def _inventory(self):
        self._location()
        if not self.directory.exists():
            return _Inventory((), (), None)
        manifest = self.directory / _MANIFEST
        entries = ()
        contents = None
        if manifest.exists() or manifest.is_symlink():
            if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > _MAX_MANIFEST_BYTES:
                raise StorageError("Zamanlanmış yedek sahiplik kaydı geçersiz; silme yapılmadı.")
            try:
                contents = manifest.read_bytes()
                outer = json.loads(contents)
                if set(outer) != {"payload", "sha256"} or _canonical(outer) != contents:
                    raise ValueError("noncanonical receipt")
                payload = outer["payload"]
                if set(payload) != {"version", "database", "entries"} or type(payload["version"]) is not int or payload["version"] != 1:
                    raise ValueError("invalid receipt")
                if outer["sha256"] != hashlib.sha256(_canonical(payload)).hexdigest():
                    raise ValueError("changed receipt")
                if payload["database"] != str(self.database.parent.resolve(strict=True) / self.database.name):
                    raise ValueError("different database")
                values = payload["entries"]
                if not isinstance(values, list) or len(values) > _MAX_ENTRIES:
                    raise ValueError("receipt size")
                ids = set()
                for sequence, entry in enumerate(values, 1):
                    if set(entry) != {"id", "file", "sha256", "size", "created_at", "profile_id", "sequence", "state"}:
                        raise ValueError("receipt fields")
                    identifier = _uuid(entry["id"]); _uuid(entry["profile_id"]); _time(entry["created_at"])
                    if (identifier in ids or entry["file"] != f"scheduled-{identifier}.db"
                            or type(entry["sequence"]) is not int or entry["sequence"] != sequence
                            or entry["state"] not in {"creating", "retained", "retired"}
                            or type(entry["size"]) is not int or not 1 <= entry["size"] <= 2**63 - 1
                            or not isinstance(entry["sha256"], str) or re.fullmatch("[0-9a-f]{64}", entry["sha256"]) is None):
                        raise ValueError("receipt value")
                    ids.add(identifier)
                entries = tuple(values)
            except (ValueError, TypeError, KeyError, OSError, OverflowError, RecursionError) as error:
                raise StorageError("Zamanlanmış yedek sahiplik kaydı eksik veya değişmiş; silme yapılmadı.") from error
        known = {entry["file"] for entry in entries}
        warnings = []
        for path in self.directory.iterdir():
            if path.name == _MANIFEST or path.name in known:
                continue
            if _NAME.fullmatch(path.name):
                raise StorageError("Sahiplik kaydı olmayan zamanlanmış yedek var; önce inceleyin, silme yapılmadı.")
            warnings.append(f"Yönetilmeyen dosya/klasör korundu: {path.name}")
        for entry in entries:
            path = self.directory / entry["file"]
            if entry["state"] in {"creating", "retired"} and not path.exists() and not path.is_symlink():
                continue
            digest, size, _ = _digest(path)
            if (digest, size) != (entry["sha256"], entry["size"]):
                raise StorageError("Zamanlanmış yedek sahiplik kanıtıyla uyuşmuyor; silme yapılmadı.")
        return _Inventory(entries, tuple(sorted(warnings)), contents)

    def preflight(self, *, keep):
        normalize_retention(keep)
        inventory = self._inventory()
        if len(inventory.entries) >= _MAX_ENTRIES:
            raise StorageError("Zamanlanmış yedek sahiplik geçmişi sınırına ulaştı; bakım gerekli.")
        with self.storage._connection(readonly=True) as connection:
            pages = connection.execute("PRAGMA page_count").fetchone()[0]
            page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        pending_size = max((entry["size"] for entry in inventory.entries if entry["state"] == "creating"), default=0)
        required = 2 * max(self.database.stat().st_size, pages * page_size, pending_size) + _RESERVE
        free = shutil.disk_usage(self.database.parent).free
        if free < required:
            raise StorageError(f"Zamanlanmış yedek ve kurtarma kontrolü için en az {required} bayt boş alan gerekli; mevcut {free}.")
        return ScheduledBackupPreflight(free, required, inventory.warnings)

    @staticmethod
    def _sync_directory(path):
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _publish_manifest(self, entries, *, expected):
        """Atomic replace of our validated ownership record; never a backup file."""
        path = self.directory / _MANIFEST
        current = path.read_bytes() if path.is_file() and not path.is_symlink() else None
        if path.is_symlink() or current != expected or (path.exists() and current is None):
            raise StorageError("Yedek sahiplik kaydı işlem sırasında değişti; silme yapılmadı.")
        content = self._manifest(entries)
        descriptor, name = tempfile.mkstemp(prefix=".ownership-", dir=self.directory)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
            if expected is None:
                os.link(temporary, path)
            else:
                os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        self._sync_directory(self.directory)
        return content

    def _recover_creating(self, inventory):
        entries = [dict(entry) for entry in inventory.entries]
        changed = False
        for entry in entries:
            if entry["state"] != "creating":
                continue
            path = self.directory / entry["file"]
            if path.exists() or path.is_symlink():
                # Only the reserved exact digest can be finalized, never an unknown file.
                if _digest(path)[:2] != (entry["sha256"], entry["size"]):
                    raise StorageError("Yarım kalan zamanlanmış yedek değişmiş; silme yapılmadı.")
                with tempfile.TemporaryDirectory(prefix=".xti-scheduled-verify-", dir=self.database.parent) as directory:
                    restored = Path(directory) / "restored.db"
                    SQLiteAssetRepository.restore(path, restored)
                    if _digest(restored)[:2] != (entry["sha256"], entry["size"]):
                        raise StorageError("Yarım kalan yedek kurtarma kontrolü başarısız.")
                entry["state"] = "retained"
            else:
                # A reservation without a published file never represented a retained backup.
                entry["state"] = "retired"
            changed = True
        if changed:
            self._publish_manifest(entries, expected=inventory.manifest_bytes)
            return self._inventory()
        return inventory

    def backup_and_prune(self, *, profile_id, recorded_at, keep):
        normalize_retention(keep)
        try:
            _uuid(profile_id); _time(recorded_at)
        except (ValueError, TypeError) as error:
            raise ValidationError("Zamanlanmış yedek profil kimliği veya zamanı geçersiz.") from error
        self.preflight(keep=keep)
        try:
            inventory = self._recover_creating(self._inventory())
            identifier = str(uuid4())
            destination = self.directory / f"scheduled-{identifier}.db"
            if any(entry["id"] == identifier for entry in inventory.entries) or destination.exists() or destination.is_symlink():
                raise StorageError("Zamanlanmış yedek kimliği zaten var; üzerine yazılmadı.")
            # Stage and restore before publishing a backup into the managed folder.
            with tempfile.TemporaryDirectory(prefix=".xti-scheduled-verify-", dir=self.database.parent) as temporary:
                temporary = Path(temporary)
                staged, restored = temporary / "backup.db", temporary / "restored.db"
                self.storage.backup(staged)
                SQLiteAssetRepository.restore(staged, restored)
                SQLiteAssetRepository(restored).inspect()
                digest, size, _ = _digest(staged)
                restored_digest, restored_size, _ = _digest(restored)
                if (digest, size) != (restored_digest, restored_size):
                    raise StorageError("Zamanlanmış yedek kurtarma kopyası doğrulanamadı.")
                was_absent = not self.directory.exists()
                self.directory.mkdir(mode=0o700, exist_ok=True)
                if was_absent:
                    self._sync_directory(self.database.parent)
                self._location()
                prior = self._inventory()
                if prior.manifest_bytes != inventory.manifest_bytes or prior.entries != inventory.entries:
                    raise StorageError("Yedek sahipliği işlem sırasında değişti; silme yapılmadı.")
                entry = {"id": identifier, "file": destination.name, "sha256": digest,
                         "size": size, "created_at": recorded_at, "profile_id": profile_id,
                         "sequence": len(inventory.entries) + 1, "state": "creating"}
                entries = [dict(item) for item in inventory.entries] + [entry]
                expected = self._publish_manifest(entries, expected=prior.manifest_bytes)
                # O_EXCL publication cannot overwrite any backup; staged inode is removed on exit.
                os.link(staged, destination)
                self._sync_directory(self.directory)
            if _digest(destination)[:2] != (digest, size):
                raise StorageError("Yeni zamanlanmış yedek yayımlanırken değişti; silme yapılmadı.")
            entry["state"] = "retained"
            expected = self._publish_manifest(entries, expected=expected)
            self._inventory()
            retained = [item for item in entries if item["state"] == "retained"]
            retire_ids = {item["id"] for item in retained[:-keep]}
            for item in entries:
                if item["id"] in retire_ids:
                    item["state"] = "retired"
            if retire_ids:
                self._publish_manifest(entries, expected=expected)
            retired_paths = []
            for item in entries:
                path = self.directory / item["file"]
                if item["state"] != "retired" or (not path.exists() and not path.is_symlink()):
                    continue
                actual, actual_size, inode = _digest(path)
                current = path.lstat()
                if ((actual, actual_size) != (item["sha256"], item["size"])
                        or inode != (current.st_dev, current.st_ino) or not stat.S_ISREG(current.st_mode)):
                    raise StorageError("Silinecek zamanlanmış yedek değişti; silme durduruldu.")
                path.unlink()
                retired_paths.append(str(path))
            if retired_paths:
                self._sync_directory(self.directory)
            return ScheduledBackupReport(str(destination), digest, size, True, tuple(retired_paths), prior.warnings)
        except OSError as error:
            raise StorageError("Zamanlanmış yedek işlemi tamamlanamadı; mevcut dosyalar korunuyor, sahiplik kaydını inceleyin.") from error
