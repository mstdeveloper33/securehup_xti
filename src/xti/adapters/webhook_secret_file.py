"""Private, non-overwriting webhook shared-secret files."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import stat
import tempfile

from xti.domain.assets import ValidationError


@dataclass(frozen=True, slots=True)
class WebhookSecretArtifact:
    destination: str
    character_count: int


def _secret_line(content: bytes) -> bytes:
    if content.endswith(b"\n"):
        content = content[:-1]
    if (
        not 32 <= len(content) <= 128 or b"\n" in content or b"\r" in content
        or any(byte < 0x21 or byte > 0x7E for byte in content)
    ):
        raise ValidationError(
            "Webhook gizli anahtar dosyası 32–128 karakterlik tek bir yazdırılabilir ASCII satırı içermeli."
        )
    return content


def read_webhook_secret(path: Path) -> bytes:
    target = Path(path).expanduser().absolute()
    descriptor = None
    try:
        # Validate the opened descriptor without waiting for a FIFO writer.
        # O_NONBLOCK does not change regular-file reads; fstat rejects devices/pipes.
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(target, flags)
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ValidationError("Webhook gizli anahtarı normal bir dosya olmalı.")
        if details.st_mode & 0o077:
            raise ValidationError(
                "Webhook gizli anahtar dosyası yalnız sahibi tarafından okunabilir olmalı (chmod 600)."
            )
        if not 32 <= details.st_size <= 129:
            raise ValidationError("Webhook gizli anahtar dosyasının boyutu geçersiz.")
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = None
            content = stream.read(130)
        return _secret_line(content)
    except FileNotFoundError as error:
        raise ValidationError("Webhook gizli anahtar dosyası bulunamadı.") from error
    except OSError as error:
        raise ValidationError("Webhook gizli anahtar dosyası güvenle okunamadı.") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def generate_webhook_secret(path: Path) -> WebhookSecretArtifact:
    destination = Path(path).expanduser().absolute()
    if os.path.lexists(destination):
        raise ValidationError("Hedef gizli anahtar dosyası zaten var; üzerine yazılmadı.")
    temporary: Path | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, name = tempfile.mkstemp(
            prefix=".xti-webhook-secret-", suffix=".tmp", dir=destination.parent,
        )
        temporary = Path(name)
        secret = secrets.token_hex(32).encode("ascii")
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(secret + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.link(temporary, destination)
        return WebhookSecretArtifact(str(destination), len(secret))
    except FileExistsError as error:
        raise ValidationError("Hedef gizli anahtar dosyası zaten var; üzerine yazılmadı.") from error
    except OSError as error:
        raise ValidationError(
            "Webhook gizli anahtar dosyası oluşturulamadı; konum ve izinleri kontrol edin."
        ) from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

