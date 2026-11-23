"""Private named channel credentials. No secret accepted in company JSON or command flags."""
import json
import os
from pathlib import Path
import re
import secrets
import stat

from xti.domain.assets import ValidationError


def credential_path(provider, profile, directory=None):
    if provider not in ('telegram', 'discord') or not re.fullmatch('[A-Za-z0-9_-]{1,60}', profile):
        raise ValidationError('Kanal erişim profili geçersiz.')
    if directory is not None: return Path(directory) / f'{provider}-{profile}.key'
    root = os.environ.get('XDG_CONFIG_HOME', '')
    return (Path(root) if Path(root).is_absolute() else Path.home() / '.config') / 'xti' / f'content-{provider}-{profile}.key'


def validate_credential(provider, value):
    if provider == 'discord':
        if not isinstance(value, dict) or set(value) != {'token'} or not re.fullmatch('[A-Za-z0-9_.-]{20,512}', value.get('token', '')):
            raise ValidationError('Discord anahtar biçimi geçersiz; değer gösterilmiyor.')
    elif provider == 'telegram':
        if (not isinstance(value, dict) or set(value) != {'api_id', 'api_hash', 'session'}
                or type(value.get('api_id')) is not int or not 1 <= value['api_id'] < 2**31
                or not re.fullmatch('[a-fA-F0-9]{32}', value.get('api_hash', ''))
                or not re.fullmatch('[A-Za-z0-9_=-]{100,1024}', value.get('session', ''))):
            raise ValidationError('Telegram oturum biçimi geçersiz; değer gösterilmiyor.')
    else: raise ValidationError('Kanal erişim sağlayıcısı bilinmiyor.')
    return value


def load_credential(provider, profile='default', *, directory=None):
    path = credential_path(provider, profile, directory)
    if not path.exists() and not path.is_symlink(): return None
    descriptor = parent = None
    try:
        parent = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0))
        directory_info = os.fstat(parent)
        if directory_info.st_uid != os.getuid() or directory_info.st_mode & 0o022:
            raise ValidationError('Kanal erişim klasörü güvenli değil.')
        descriptor = os.open(path.name, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0), dir_fd=parent)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid() or not 20 <= info.st_size <= 4096:
            raise ValidationError('Gizli dosya izinleri geçersiz.')
        with os.fdopen(descriptor, 'rb') as stream:
            descriptor = None
            value = json.loads(stream.read(4097))
        return validate_credential(provider, value)
    except (OSError, ValueError, TypeError, UnicodeError, ValidationError):
        raise ValidationError('Kanal erişim dosyası güvenle okunamadı; içerik gösterilmiyor.') from None
    finally:
        if descriptor is not None: os.close(descriptor)
        if parent is not None: os.close(parent)


def save_credential(provider, profile, value, *, directory=None):
    raw = json.dumps(validate_credential(provider, value), separators=(',', ':')).encode()
    destination = credential_path(provider, profile, directory)
    parent = descriptor = temporary = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        parent = os.open(destination.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0))
        info = os.fstat(parent)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise ValidationError('Kanal erişim klasörü size ait ve başkalarınca yazılamaz olmalı.')
        name = '.content-' + secrets.token_hex(12)
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600, dir_fd=parent)
        temporary = name
        with os.fdopen(descriptor, 'wb') as stream:
            descriptor = None
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, destination.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        os.fsync(parent)
        return destination
    except FileExistsError:
        raise ValidationError('Kanal erişim dosyası zaten var; üzerine yazılmadı.') from None
    except OSError:
        raise ValidationError('Kanal erişim dosyası güvenle kaydedilemedi.') from None
    finally:
        if descriptor is not None: os.close(descriptor)
        if parent is not None:
            if temporary: os.unlink(temporary, dir_fd=parent)
            os.close(parent)
