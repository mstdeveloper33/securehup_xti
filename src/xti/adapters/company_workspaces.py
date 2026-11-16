"""Private per-company workspaces selected only by a trusted operating-system launcher.

The registry and binding detect accidental or request-driven workspace confusion.
They are not authentication, encryption or protection against a process that can
modify these files as their owner. In particular, copying another database over a
correctly bound workspace is outside this filesystem trust boundary.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from xti.domain.company_workspace import (
    CompanyWorkspaceError, MAX_COMPANIES, normalize_company_id, validate_registry,
    validate_workspace_binding,
)


REGISTRY_FILE = "company-registry.json"
REGISTRY_LOCK = ".company-registry.lock"
WORKSPACE_MARKER = ".company-workspace.json"
MAX_REGISTRY_BYTES = 2 * 1024 * 1024
MAX_MARKER_BYTES = 2048


@dataclass(frozen=True, slots=True)
class CompanyWorkspace:
    company_id: str
    registry_id: str
    workspace_id: str
    data_dir: Path
    enabled: bool = True

    @property
    def database(self) -> Path:
        return self.data_dir / "xti.db"

    @property
    def lock_directory(self) -> Path:
        return self.data_dir

    @property
    def scope(self) -> dict:
        return {"mode": "company-workspace", "company_id": self.company_id,
                "registry_id": self.registry_id, "workspace_id": self.workspace_id}


def _failure(message="Firma kayıt alanı güvenle açılamadı; konum, sahiplik ve özel izinleri kontrol edin."):
    return CompanyWorkspaceError(message)


def _private(info, *, directory=False):
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if (not expected(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077 or (not directory and info.st_nlink != 1)):
        raise _failure()


def _root_path(root) -> Path:
    try:
        original = Path(root).expanduser()
        if ".." in original.parts:
            raise _failure("Firma kayıt kökü üst klasör geçişi içeremez.")
        path = original.absolute()
        for ancestor in reversed((path, *path.parents)):
            try:
                info = ancestor.lstat()
            except FileNotFoundError:
                if ancestor != path:
                    raise _failure("Firma kayıt kökünün üst klasörü mevcut olmalı.")
                continue
            if not stat.S_ISDIR(info.st_mode):
                raise _failure("Firma kayıt kökü ve üst klasörleri gerçek klasör olmalı; bağlantı kullanılamaz.")
            if (info.st_uid not in {0, os.getuid()}
                    or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX)):
                raise _failure("Firma kayıt kökünün üst klasörleri güvenilen hesaba ait olmalı; "
                               "başkaları klasörün yerini değiştirememeli.")
            if ancestor != path and (
                    (ancestor / REGISTRY_FILE).exists() or (ancestor / REGISTRY_FILE).is_symlink()
                    or (ancestor / WORKSPACE_MARKER).exists() or (ancestor / WORKSPACE_MARKER).is_symlink()):
                raise _failure("Firma kayıt kökleri veya firma alanları iç içe yerleştirilemez.")
        return path
    except CompanyWorkspaceError:
        raise
    except (OSError, TypeError, ValueError, RuntimeError):
        raise _failure() from None


def _directory(path: Path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _private(os.fstat(descriptor), directory=True)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise _failure("Firma kayıt dosyasında yinelenen JSON alanı var.")
        value[key] = item
    return value


def _read_json(directory, filename, *, maximum):
    descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        before = os.fstat(descriptor)
        _private(before)
        if not 1 <= before.st_size <= maximum:
            raise _failure("Firma kayıt dosyası izin verilen boyutta değil.")
        chunks, remaining = [], maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        current = os.stat(filename, dir_fd=directory, follow_symlinks=False)
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity(before) != identity(after) or identity(after) != identity(current):
            raise _failure("Firma kayıt dosyası okuma sırasında değişti.")
        raw = b"".join(chunks)
        if len(raw) > maximum:
            raise _failure("Firma kayıt dosyası izin verilen boyutta değil.")
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (ValueError, UnicodeError, RecursionError):
        raise _failure("Firma kayıt dosyası geçerli ve tekil UTF-8 JSON olmalı.") from None
    finally:
        os.close(descriptor)


def _publish(directory, filename, value, *, replace=False):
    """Publish complete JSON; only an already verified registry may be replaced."""
    content = (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    temporary = ".company-new-" + uuid4().hex
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, filename, src_dir_fd=directory, dst_dir_fd=directory)
        else:
            os.link(temporary, filename, src_dir_fd=directory, dst_dir_fd=directory,
                    follow_symlinks=False)
            os.unlink(temporary, dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


@contextmanager
def _registry(root, *, write=False, create=False):
    path = _root_path(root)
    directory = lock = None
    try:
        if create:
            try:
                path.mkdir(mode=0o700)
            except FileExistsError:
                pass
        directory = _directory(path)
        if create:
            names = set(os.listdir(directory))
            if REGISTRY_FILE not in names and REGISTRY_LOCK not in names and names:
                raise _failure("Mevcut dosyalar firma kayıt dizinine otomatik olarak bağlanmaz.")
        flags = os.O_RDWR if write else os.O_RDONLY
        flags |= os.O_NOFOLLOW | os.O_NONBLOCK
        if create:
            try:
                lock = os.open(REGISTRY_LOCK, flags | os.O_CREAT | os.O_EXCL,
                               0o600, dir_fd=directory)
            except FileExistsError:
                lock = os.open(REGISTRY_LOCK, flags, dir_fd=directory)
        else:
            lock = os.open(REGISTRY_LOCK, flags, dir_fd=directory)
        _private(os.fstat(lock))
        fcntl.flock(lock, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
        try:
            registry = validate_registry(_read_json(directory, REGISTRY_FILE, maximum=MAX_REGISTRY_BYTES))
        except FileNotFoundError:
            if not create or set(os.listdir(directory)) != {REGISTRY_LOCK}:
                raise _failure("Firma kayıt dizini eksik; mevcut dosyalar otomatik olarak bağlanmaz.") from None
            registry = {"version": 1, "registry_id": str(uuid4()), "companies": []}
            _publish(directory, REGISTRY_FILE, registry)
        yield path, directory, registry
    except CompanyWorkspaceError:
        raise
    except OSError:
        raise _failure() from None
    finally:
        if lock is not None:
            os.close(lock)
        if directory is not None:
            os.close(directory)


def _entry(registry, company_id, *, allow_disabled=False):
    entry = next((item for item in registry["companies"] if item["company_id"] == company_id), None)
    if entry is None or (not allow_disabled and not entry["enabled"]):
        raise _failure("Firma kayıtlı ve etkin değil; başka kayıt alanına geçilmedi.")
    return entry


def _workspace(path, registry, entry, *, require_database):
    data_dir = path / entry["company_id"]
    descriptor = _directory(data_dir)
    try:
        validate_workspace_binding(_read_json(descriptor, WORKSPACE_MARKER, maximum=MAX_MARKER_BYTES),
            registry_id=registry["registry_id"], company_id=entry["company_id"],
            workspace_id=entry["workspace_id"])
        if require_database:
            database = os.open("xti.db", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
            try:
                _private(os.fstat(database))
            finally:
                os.close(database)
        return CompanyWorkspace(entry["company_id"], registry["registry_id"],
                                entry["workspace_id"], data_dir, entry["enabled"])
    finally:
        os.close(descriptor)


def provision_company_workspace(root, company_id: str) -> CompanyWorkspace:
    """Register a new private empty workspace; the caller explicitly initializes its DB.

    A failed or interrupted provision may leave unregistered files. They are
    deliberately preserved and never adopted or overwritten by a later call.
    """
    company_id = normalize_company_id(company_id)
    with _registry(root, write=True, create=True) as (path, directory, registry):
        if any(item["company_id"] == company_id for item in registry["companies"]):
            raise _failure("Firma kimliği zaten kayıtlı; mevcut alan değiştirilmedi.")
        if len(registry["companies"]) >= MAX_COMPANIES:
            raise _failure("Firma kayıt dizini kapasite sınırına ulaştı.")
        entry = {"company_id": company_id, "workspace_id": str(uuid4()), "enabled": True}
        os.mkdir(company_id, mode=0o700, dir_fd=directory)
        workspace = _directory(path / company_id)
        try:
            _publish(workspace, WORKSPACE_MARKER, {"version": 1,
                "registry_id": registry["registry_id"], "company_id": company_id,
                "workspace_id": entry["workspace_id"]})
        finally:
            os.close(workspace)
        os.fsync(directory)
        registry["companies"].append(entry)
        _publish(directory, REGISTRY_FILE, registry, replace=True)
        return _workspace(path, registry, entry, require_database=False)


def resolve_company_workspace(root, company_id: str) -> CompanyWorkspace:
    """Resolve one enabled registered workspace without creating or repairing files."""
    company_id = normalize_company_id(company_id)
    with _registry(root) as (path, _directory_fd, registry):
        return _workspace(path, registry, _entry(registry, company_id), require_database=True)


def disable_company_workspace(root, company_id: str) -> CompanyWorkspace:
    """Disable future selection while preserving its database, evidence and identity."""
    company_id = normalize_company_id(company_id)
    with _registry(root, write=True) as (path, directory, registry):
        entry = _entry(registry, company_id, allow_disabled=True)
        context = _workspace(path, registry, entry, require_database=False)
        if entry["enabled"]:
            entry["enabled"] = False
            _publish(directory, REGISTRY_FILE, registry, replace=True)
        return CompanyWorkspace(context.company_id, context.registry_id, context.workspace_id,
                                context.data_dir, False)
