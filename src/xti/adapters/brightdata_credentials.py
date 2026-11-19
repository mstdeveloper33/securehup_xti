"""Local operator credentials; never stored in a company database or request JSON."""
import os
from pathlib import Path
import re
import secrets
import stat

from xti.domain.assets import ValidationError


def validate_key(value):
    if not isinstance(value, str) or re.fullmatch(r'[A-Za-z0-9._~+/=-]{16,512}', value) is None:
        raise ValidationError('Bright Data API anahtarı eksik veya geçersiz.')
    return value


def key_path():
    root = os.environ.get('XDG_CONFIG_HOME', '')
    return (Path(root) if Path(root).is_absolute() else Path.home() / '.config') / 'xti' / 'brightdata.key'


def load_key(path=None):
    if path is None and 'BRIGHTDATA_API_KEY' in os.environ:
        return validate_key(os.environ['BRIGHTDATA_API_KEY'])
    descriptor = None
    try:
        descriptor = os.open(path or key_path(), os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                or info.st_uid != os.getuid() or not 16 <= info.st_size <= 513):
            raise ValidationError('Bright Data anahtar dosyası size ait, normal ve yalnız sahibine açık (600) olmalı.')
        with os.fdopen(descriptor, 'rb') as stream:
            descriptor = None
            content = stream.read(514)
        return validate_key(content.removesuffix(b'\n').decode('ascii'))
    except FileNotFoundError:
        raise ValidationError('Bright Data anahtarı yok; ./xti brand brightdata configure veya BRIGHTDATA_API_KEY kullanın.') from None
    except (OSError, UnicodeError):
        raise ValidationError('Bright Data anahtarı güvenle okunamadı.') from None
    finally:
        if descriptor is not None: os.close(descriptor)


def save_key(value, path=None):
    content = (validate_key(value) + '\n').encode('ascii')
    destination = Path(path or key_path()).expanduser().absolute()
    parent = descriptor = None
    temporary = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        parent = os.open(destination.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0))
        info = os.fstat(parent)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise ValidationError('Bright Data anahtar klasörü size ait ve başkalarınca yazılamaz olmalı.')
        candidate = '.brightdata-' + secrets.token_hex(12)
        descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600, dir_fd=parent)
        temporary = candidate  # Cleanup only a file created by this invocation.
        with os.fdopen(descriptor, 'wb') as stream:
            descriptor = None
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, destination.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        os.fsync(parent)
        return destination
    except FileExistsError:
        raise ValidationError('Bright Data anahtar dosyası zaten var; üzerine yazılmadı.') from None
    except OSError:
        raise ValidationError('Bright Data anahtarı güvenle kaydedilemedi.') from None
    finally:
        if descriptor is not None: os.close(descriptor)
        if parent is not None:
            if temporary:
                try: os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError: pass
            os.close(parent)


def daily_limit():
    value = os.environ.get('XTI_BRIGHTDATA_DAILY_PROFILE_LIMIT', '50')
    if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 50_000:
        raise ValidationError('XTI_BRIGHTDATA_DAILY_PROFILE_LIMIT 1–50000 arasında olmalı.')
    return int(value)
