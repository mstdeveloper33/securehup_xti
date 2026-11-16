"""Non-overwriting company snapshots containing core evidence and durable jobs."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
from uuid import UUID

from xti.adapters.company_workspaces import (
    CompanyWorkspace, _directory, _publish, _read_json, provision_company_workspace,
    resolve_company_workspace,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_engine_jobs import ENGINE_JOB_DATABASE_NAME, SQLiteEngineJobRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.domain.company_workspace import CompanyWorkspaceError, normalize_company_id
from xti.ports.jobs import WorkerBusyError


PLATFORM_BACKUP_MANIFEST = "manifest.json"
PLATFORM_BACKUP_VERSION = 1
MAX_MANIFEST_BYTES = 8192
_FILES = ("xti.db", ENGINE_JOB_DATABASE_NAME)
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)


def _failure(message="Firma yedeği güvenle okunamadı; dosya türünü, özel izinleri ve bütünlüğünü kontrol edin."):
    return StorageError(message)


def _path(value, *, must_exist: bool) -> Path:
    original = Path(value).expanduser()
    if ".." in original.parts:
        raise _failure("Yedek konumu üst klasör geçişi içeremez.")
    path = original.absolute()
    for ancestor in reversed((path, *path.parents)):
        try:
            info = ancestor.lstat()
        except FileNotFoundError:
            if ancestor == path and not must_exist:
                continue
            raise _failure("Yedek konumunun üst klasörleri mevcut olmalı.") from None
        if not stat.S_ISDIR(info.st_mode):
            raise _failure("Yedek konumu ve üst klasörleri gerçek klasör olmalı; bağlantı kullanılamaz.")
        if (info.st_uid not in {0, os.getuid()}
                or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX)):
            raise _failure("Yedek konumunun üst klasörleri başka kullanıcılarca değiştirilememeli.")
        if ancestor == path and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise _failure("Yedek klasörü yalnız sahibine açık olmalı.")
    return path


def _private_file(path: Path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
            or info.st_mode & 0o077):
        raise _failure("Yedek dosyaları tek bağlantılı ve yalnız sahibine açık normal dosyalar olmalı.")
    return info


def _flush_directory(path: Path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _digest_file(path: Path, *, copy_to: Path | None = None) -> dict:
    before = _private_file(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    output = None
    try:
        if _identity(before) != _identity(os.fstat(descriptor)):
            raise _failure("Yedek dosyası okuma sırasında değişti.")
        if copy_to is not None:
            output = os.open(copy_to, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        digest, size = hashlib.sha256(), 0
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
            if output is not None:
                remaining = memoryview(chunk)
                while remaining:
                    written = os.write(output, remaining)
                    if written <= 0:
                        raise _failure("Yedek kopyası tamamlanamadı.")
                    remaining = remaining[written:]
        if output is not None:
            os.fsync(output)
        if (_identity(before) != _identity(os.fstat(descriptor))
                or _identity(before) != _identity(_private_file(path)) or size != before.st_size):
            raise _failure("Yedek dosyası okuma sırasında değişti.")
        return {"sha256": digest.hexdigest(), "size": size}
    finally:
        if output is not None:
            os.close(output)
        os.close(descriptor)


def _validate_manifest(value, company_id: str) -> dict:
    if (not isinstance(value, dict)
            or set(value) != {"version", "company_id", "registry_id", "workspace_id", "files"}
            or type(value["version"]) is not int or value["version"] != PLATFORM_BACKUP_VERSION):
        raise _failure("Firma yedeği bildirimi veya sürümü geçersiz.")
    if normalize_company_id(value["company_id"]) != company_id:
        raise _failure("Yedek başka bir firmaya ait; firma değiştirerek geri yüklenemez.")
    for field in ("registry_id", "workspace_id"):
        try:
            if not isinstance(value[field], str) or str(UUID(value[field])) != value[field]:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise _failure("Yedeğin firma kayıt alanı kimlikleri geçersiz.") from None
    if not isinstance(value["files"], dict) or set(value["files"]) != set(_FILES):
        raise _failure("Firma yedeği ana kayıtları ve motor iş geçmişini birlikte içermeli.")
    for item in value["files"].values():
        if (not isinstance(item, dict) or set(item) != {"sha256", "size"}
                or not isinstance(item["sha256"], str) or _SHA256.fullmatch(item["sha256"]) is None
                or type(item["size"]) is not int or not 1 <= item["size"] <= 2**63 - 1):
            raise _failure("Yedek dosyasının boyutu veya SHA-256 bilgisi geçersiz.")
    return value


def _reject_running(jobs: SQLiteEngineJobRepository):
    if jobs.active_job() is not None:
        raise WorkerBusyError("Açık motor işi var; önce çalıştırıcıyı bitirin veya açık kurtarma uygulayın.")


def _validate_core(path: Path):
    _private_file(path)
    storage = SQLiteAssetRepository(path)
    with storage._connection(readonly=True) as connection:
        storage._check_integrity(connection)


def _runtime_files(context: CompanyWorkspace):
    for filename in _FILES:
        _private_file(context.data_dir / filename)
        for suffix in ("-journal", "-wal", "-shm", ".worker.lock"):
            path = context.data_dir / (filename + suffix)
            if path.exists() or path.is_symlink():
                _private_file(path)


def backup_platform_workspace(context: CompanyWorkspace, output: Path) -> Path:
    """Hold worker and core read locks until both databases have been captured.

    The final manifest is the completion marker. Interrupted or failed output is
    preserved for inspection but cannot be restored or silently overwritten.
    """
    try:
        if not isinstance(context, CompanyWorkspace):
            raise _failure("Doğrulanmış firma kayıt alanı gerekli.")
        verified = resolve_company_workspace(context.data_dir.parent, context.company_id)
        if verified != context:
            raise _failure("Yedek için seçilen firma kayıt alanı güncel kayıtla uyuşmuyor.")
        output = _path(output, must_exist=False)
        if output.exists() or output.is_symlink():
            raise _failure("Yedek hedefi zaten var; mevcut yedeğin üzerine yazılmaz.")
        _runtime_files(context)
        jobs_path = context.data_dir / ENGINE_JOB_DATABASE_NAME
        jobs = SQLiteEngineJobRepository(jobs_path)
        core = SQLiteAssetRepository(context.database)
        with LocalExecutionLock(jobs_path).acquire(), LocalExecutionLock(context.database).acquire():
            _runtime_files(context)
            jobs.validate()
            _reject_running(jobs)
            with core._connection(readonly=True) as connection:
                if connection.execute("PRAGMA journal_mode").fetchone()[0] not in {"delete", "truncate", "persist"}:
                    raise _failure("Birlikte yedekleme için ana veritabanı geri alma günlüğü kullanmalı.")
                connection.execute("BEGIN")
                # BEGIN alone is deferred. This read holds the rollback-journal
                # shared lock, preventing commits even from legacy core writers.
                connection.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
                core._check_integrity(connection)
                output.mkdir(mode=0o700)
                _flush_directory(output.parent)
                core.backup(output / "xti.db")
                jobs.backup(output / ENGINE_JOB_DATABASE_NAME)
                _reject_running(jobs)
                files = {name: _digest_file(output / name) for name in _FILES}
                manifest = {"version": PLATFORM_BACKUP_VERSION, "company_id": context.company_id,
                    "registry_id": context.registry_id, "workspace_id": context.workspace_id, "files": files}
                directory = _directory(output)
                try:
                    _publish(directory, PLATFORM_BACKUP_MANIFEST, manifest)
                finally:
                    os.close(directory)
                return output
    except (StorageError, WorkerBusyError):
        raise
    except (OSError, ValueError, TypeError, CompanyWorkspaceError, sqlite3.Error):
        raise _failure("Firma yedeği oluşturulamadı; mevcut veri ve yedekler değiştirilmedi.") from None


@contextmanager
def _validated_backup(source: Path, company_id: str):
    source = _path(source, must_exist=True)
    directory = _directory(source)
    try:
        if set(os.listdir(directory)) != {*_FILES, PLATFORM_BACKUP_MANIFEST}:
            raise _failure("Yedek eksik veya beklenmeyen dosya içeriyor; tamamlanma bildirimi gerekli.")
        manifest = _validate_manifest(_read_json(directory, PLATFORM_BACKUP_MANIFEST,
            maximum=MAX_MANIFEST_BYTES), company_id)
        with tempfile.TemporaryDirectory(prefix="xti-platform-restore-") as temporary:
            staging = Path(temporary)
            for name in _FILES:
                if _digest_file(source / name, copy_to=staging / name) != manifest["files"][name]:
                    raise _failure("Yedek dosyası boyut veya SHA-256 denetimini geçemedi.")
            _validate_core(staging / "xti.db")
            jobs = SQLiteEngineJobRepository(staging / ENGINE_JOB_DATABASE_NAME)
            jobs.validate()
            _reject_running(jobs)
            yield staging
    finally:
        os.close(directory)


def restore_platform_workspace(root, company_id: str, source: Path) -> CompanyWorkspace:
    """Restore verified files only to a newly registered workspace of the same company."""
    try:
        company_id = normalize_company_id(company_id)
        source = _path(source, must_exist=True)
        root = _path(root, must_exist=False)
        if root.is_relative_to(source):
            raise _failure("Geri yükleme kökü kaynak yedeğin içine yerleştirilemez; kaynak korunmalı.")
        with _validated_backup(source, company_id) as staging:
            context = provision_company_workspace(root, company_id)
            # Failed publication deliberately leaves a non-usable partial
            # workspace for explicit inspection; it is never adopted on retry.
            jobs_path = context.data_dir / ENGINE_JOB_DATABASE_NAME
            with LocalExecutionLock(jobs_path).acquire(), LocalExecutionLock(context.database).acquire():
                SQLiteEngineJobRepository.restore(staging / ENGINE_JOB_DATABASE_NAME, jobs_path)
                # The original deployment may have sent queued work after the
                # backup. Preserve its key but retire it before the workspace
                # becomes resolvable; restoring is never permission to resend.
                SQLiteEngineJobRepository(jobs_path).quarantine_restored_queue(
                    recorded_at=datetime.now(timezone.utc).isoformat())
                SQLiteAssetRepository.restore(staging / "xti.db", context.database)
                _runtime_files(context)
                return resolve_company_workspace(root, company_id)
    except (StorageError, WorkerBusyError):
        raise
    except (OSError, ValueError, TypeError, CompanyWorkspaceError, sqlite3.Error):
        raise _failure("Firma yedeği geri yüklenemedi; mevcut kayıt alanlarının üzerine yazılmadı.") from None
