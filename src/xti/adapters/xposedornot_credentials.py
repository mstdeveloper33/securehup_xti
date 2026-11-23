"""Owner-only XposedOrNot API and per-organization pseudonym keys."""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import stat

from xti.domain.assets import ValidationError
from xti.domain.mentions import mention_uuid


MIN_API_KEY_BYTES = 8
MAX_API_KEY_BYTES = 512


def _root(directory: Path | None = None) -> Path:
    if directory is not None:
        return Path(directory)
    configured = os.environ.get("XDG_CONFIG_HOME", "")
    return (Path(configured) if configured and Path(configured).is_absolute()
            else Path.home() / ".config") / "xti"


def api_key_path(directory: Path | None = None) -> Path:
    return _root(directory) / "xposedornot.key"


def identity_key_path(organization_id: str, directory: Path | None = None) -> Path:
    return _root(directory) / ("xposedornot-identity-" + mention_uuid(organization_id) + ".key")


def validate_api_key(value: object) -> str:
    if not isinstance(value, str):
        raise ValidationError("XposedOrNot API anahtarı metin olmalı; değer gösterilmiyor.")
    try:
        encoded = value.encode("ascii")
    except UnicodeError:
        raise ValidationError(
            "XposedOrNot API anahtarı görünür ASCII olmalı; değer gösterilmiyor."
        ) from None
    if (not MIN_API_KEY_BYTES <= len(encoded) <= MAX_API_KEY_BYTES
            or value != value.strip()
            or any(character.isspace() or not character.isprintable() for character in value)):
        raise ValidationError(
            "XposedOrNot API anahtarı güvenli uzunluk ve karakter sınırlarında değil; "
            "değer gösterilmiyor."
        )
    return value


def _open_parent(path: Path, label: str) -> int:
    try:
        descriptor = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except FileNotFoundError:
        raise
    except OSError:
        raise ValidationError(label + " klasörü güvenle açılamadı.") from None
    info = os.fstat(descriptor)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o022):
        os.close(descriptor)
        raise ValidationError(label + " klasörü size ait ve başkalarınca yazılamaz olmalı.")
    return descriptor


def _read(path: Path, *, minimum: int, maximum: int, label: str, missing_hint: str) -> bytes:
    parent = descriptor = None
    try:
        parent = _open_parent(path, label)
        descriptor = os.open(
            path.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent,
        )
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or not minimum <= info.st_size <= maximum + 1):
            raise ValidationError(label + " dosyası yalnız sahibine açık normal dosya olmalı.")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            value = stream.read(maximum + 2)
        value = value.removesuffix(b"\n")
        if not minimum <= len(value) <= maximum:
            raise ValidationError(label + " güvenli uzunluk sınırlarında değil.")
        return value
    except FileNotFoundError:
        raise ValidationError(label + " bulunamadı; " + missing_hint + " çalıştırın.") from None
    except ValidationError:
        raise
    except OSError:
        raise ValidationError(label + " güvenle okunamadı; içerik gösterilmiyor.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent is not None:
            os.close(parent)


def _write(path: Path, content: bytes, *, label: str) -> Path:
    parent = descriptor = None
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        parent = _open_parent(path, label)
        temporary = ".xposedornot-" + secrets.token_hex(12)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent,
        )
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(content + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(
            temporary,
            path.name,
            src_dir_fd=parent,
            dst_dir_fd=parent,
            follow_symlinks=False,
        )
        os.fsync(parent)
        return path
    except FileExistsError:
        raise ValidationError(label + " zaten var; üzerine yazılmadı.") from None
    except ValidationError:
        raise
    except OSError:
        raise ValidationError(label + " güvenle kaydedilemedi; üzerine yazılmadı.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent is not None:
            if temporary is not None:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass
            os.close(parent)


def load_api_key(directory: Path | None = None) -> str:
    if "XON_API_KEY" in os.environ:
        return validate_api_key(os.environ["XON_API_KEY"])
    try:
        return validate_api_key(_read(
            api_key_path(directory),
            minimum=MIN_API_KEY_BYTES,
            maximum=MAX_API_KEY_BYTES,
            label="XposedOrNot API anahtarı",
            missing_hint="darkweb xposedornot-configure",
        ).decode("ascii"))
    except UnicodeError:
        raise ValidationError(
            "XposedOrNot API anahtarı güvenle okunamadı; değer gösterilmiyor."
        ) from None


def load_identity_key(organization_id: str, directory: Path | None = None) -> bytes:
    value = _read(
        identity_key_path(organization_id, directory),
        minimum=64,
        maximum=64,
        label="XposedOrNot kuruluş pseudonym anahtarı",
        missing_hint="darkweb xposedornot-identity-create " + mention_uuid(organization_id),
    )
    try:
        key = bytes.fromhex(value.decode("ascii"))
    except (UnicodeError, ValueError):
        raise ValidationError(
            "XposedOrNot kuruluş pseudonym anahtarı geçersiz; değer gösterilmiyor."
        ) from None
    if len(key) != 32:
        raise ValidationError(
            "XposedOrNot kuruluş pseudonym anahtarı geçersiz; değer gösterilmiyor."
        )
    return key


def save_api_key(value: str, directory: Path | None = None) -> Path:
    return _write(
        api_key_path(directory), validate_api_key(value).encode("ascii"),
        label="XposedOrNot API anahtarı",
    )


def create_identity_key(organization_id: str, directory: Path | None = None) -> Path:
    return _write(
        identity_key_path(organization_id, directory),
        secrets.token_bytes(32).hex().encode("ascii"),
        label="XposedOrNot kuruluş pseudonym anahtarı",
    )


def readiness(organization_id: str, directory: Path | None = None) -> dict:
    result = {"api_key": "missing", "identity_key": "missing", "ready": False}
    try:
        load_api_key(directory)
        result["api_key"] = "configured"
    except ValidationError:
        pass
    try:
        load_identity_key(organization_id, directory)
        result["identity_key"] = "configured"
    except ValidationError:
        pass
    result["ready"] = result["api_key"] == result["identity_key"] == "configured"
    return result


class XposedOrNotCredentialStore:
    """Injectable secret facade; returned values must never enter logs or SQLite."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory

    def readiness(self, organization_id: str) -> dict:
        return readiness(organization_id, self.directory)

    def api_key(self) -> str:
        return load_api_key(self.directory)

    def identity_key(self, organization_id: str) -> bytes:
        return load_identity_key(organization_id, self.directory)

    def save_api_key(self, value: str) -> Path:
        return save_api_key(value, self.directory)

    def create_identity_key(self, organization_id: str) -> Path:
        return create_identity_key(organization_id, self.directory)
