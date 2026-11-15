"""Identity-checked, durable replacement of a managed installation directory.

All callers hold their installation's exclusive lock. Every directory retained
by a transaction has a unique name; recovery never recursively removes files.
"""

import json
import os
from pathlib import Path
import stat
import uuid

from xti.adapters.tool_installation import ToolInstallationError


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def identity(path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(metadata.st_mode):
        raise ToolInstallationError(f"Gerçek dizin bekleniyor: {path.name}; değiştirilmedi.")
    return [metadata.st_dev, metadata.st_ino]


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def move_directory(source, destination, expected):
    if identity(source) != expected or os.path.lexists(destination):
        raise ToolInstallationError("Kurulum dizininin kimliği veya hedefi değişmiş; işlem durduruldu.")
    os.rename(source, destination)
    sync_directory(source.parent)


class DirectoryInstallation:
    def __init__(self, *, canonical_name, prefix, journal_name):
        for value in (canonical_name, prefix, journal_name):
            if not isinstance(value, str) or value in ("", ".", "..") or Path(value).name != value:
                raise ValueError("Installation names must be single path components.")
        self.canonical_name = canonical_name
        self.prefix = prefix
        self.journal_name = journal_name

    def paths(self, parent, transaction):
        return {
            "canonical": parent / self.canonical_name,
            "backup": parent / f"{self.prefix}-backup-{transaction}",
            "candidate": parent / f"{self.prefix}-candidate-{transaction}",
            "failed": parent / f"{self.prefix}-failed-{transaction}",
        }

    def load(self, parent):
        try:
            descriptor = os.open(parent / self.journal_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                metadata = os.fstat(stream.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                    raise ValueError("not a private regular journal")
                payload = stream.read(16385)
            if len(payload) > 16384:
                raise ValueError("journal too large")
            data = json.loads(payload, object_pairs_hook=unique_fields)
            if not isinstance(data, dict) or set(data) != {"version", "transaction", "phase", "old", "new"}:
                raise ValueError("unknown journal fields")
            if type(data["version"]) is not int or data["version"] != 1:
                raise ValueError("unsupported journal version")
            transaction = data["transaction"]
            if not isinstance(transaction, str) or str(uuid.UUID(transaction)) != transaction:
                raise ValueError("invalid transaction")
            if data["phase"] not in ("prepared", "committed"):
                raise ValueError("unknown phase")
            for field in ("old", "new"):
                value = data[field]
                if field == "old" and value is None:
                    continue
                if not isinstance(value, list) or len(value) != 2 or any(
                    type(item) is not int or item < 0 for item in value
                ):
                    raise ValueError("invalid directory identity")
            if data["old"] == data["new"]:
                raise ValueError("duplicate directory identity")
            return data
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as error:
            raise ToolInstallationError(
                "Kurulum günlüğü güvenle okunamadı; dosyalara dokunulmadı. "
                f"Elle inceleme gerekiyor: {parent / self.journal_name}"
            ) from error

    def write(self, parent, data, *, initial=False):
        journal = parent / self.journal_name
        temporary = parent / f"{self.prefix}-journal-{uuid.uuid4()}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(data, stream, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            if initial:
                # All cooperating writers hold the persistent exclusive lock.
                # Atomic publication leaves either no journal or a complete one.
                if os.path.lexists(journal):
                    raise ToolInstallationError("Kurulum günlüğü zaten var; üzerine yazılmadı.")
                os.replace(temporary, journal)
            else:
                existing = self.load(parent)
                if existing != dict(data, phase="prepared"):
                    raise ToolInstallationError("Kurulum günlüğü değişmiş; üzerine yazılmadı.")
                os.replace(temporary, journal)
            sync_directory(parent)
        finally:
            if temporary.exists():
                temporary.unlink()

    def clear(self, parent, expected):
        if self.load(parent) != expected:
            raise ToolInstallationError("Kurulum günlüğü değişmiş; silinmedi.")
        (parent / self.journal_name).unlink()
        sync_directory(parent)

    def recover(self, parent):
        """Recover only recognized transaction directories, including partial rollback."""
        data = self.load(parent)
        paths = self.paths(parent, data["transaction"])
        observed = {name: identity(path) for name, path in paths.items()}
        old, new = data["old"], data["new"]
        for name, actual in observed.items():
            allowed = {"canonical": (old, new), "backup": (old,), "candidate": (new,), "failed": (new,)}[name]
            if actual is not None and actual not in allowed:
                raise ToolInstallationError("Kurtarma yolunda tanınmayan dizin var; hiçbir dizin taşınmadı.")
        new_locations = [name for name, actual in observed.items() if actual == new]
        old_locations = [name for name, actual in observed.items() if old is not None and actual == old]
        if len(new_locations) != 1 or (old is not None and len(old_locations) != 1):
            raise ToolInstallationError("Kurtarma dizinlerinin kimliği eksik veya çakışıyor; değiştirilmedi.")
        if data["phase"] == "committed":
            if new_locations != ["canonical"] or (old is not None and old_locations != ["backup"]):
                raise ToolInstallationError("Tamamlanmış kurulumun dizin düzeni değişmiş; değiştirilmedi.")
            self.clear(parent, data)
            print("Tamamlanmış kurulumun günlüğü temizlendi; mevcut kurulum korundu.")
            return
        location = new_locations[0]
        if location not in ("canonical", "candidate", "failed"):
            raise ToolInstallationError("Aday kurulum beklenmeyen yerde; değiştirilmedi.")
        if old is not None and old_locations[0] not in ("canonical", "backup"):
            raise ToolInstallationError("Önceki kurulum beklenmeyen yerde; değiştirilmedi.")
        if location != "failed":
            move_directory(paths[location], paths["failed"], new)
        if old is not None and old_locations == ["backup"]:
            move_directory(paths["backup"], paths["canonical"], old)
        self.clear(parent, data)
        print("Yarım kalan kurulum geri alındı; önceki kurulum varsa aynı konumuna döndürüldü.")
        print(f"Başarısız aday korundu: {paths['failed']}")

    def prepare(self, parent):
        old = identity(parent / self.canonical_name)
        transaction = str(uuid.uuid4())
        paths = self.paths(parent, transaction)
        if any(os.path.lexists(paths[name]) for name in ("backup", "candidate", "failed")):
            raise ToolInstallationError("Yeni işlem için ayrılan dizin zaten var; değiştirilmedi.")
        paths["candidate"].mkdir(mode=0o700)
        sync_directory(parent)
        data = {"version": 1, "transaction": transaction, "phase": "prepared",
                "old": old, "new": identity(paths["candidate"])}
        self.write(parent, data, initial=True)
        return data

    def activate(self, parent, data):
        paths = self.paths(parent, data["transaction"])
        if data["old"] is not None:
            move_directory(paths["canonical"], paths["backup"], data["old"])
        move_directory(paths["candidate"], paths["canonical"], data["new"])

    def commit(self, parent, data):
        committed = dict(data, phase="committed")
        self.write(parent, committed)
        self.clear(parent, committed)
