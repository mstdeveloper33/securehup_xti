"""Optional host credentials; the engine never accepts a token in company JSON."""
import os
from pathlib import Path
import re

from xti.adapters.brightdata_credentials import load_key as read_private_key, save_key as write_private_key
from xti.domain.assets import ValidationError

ENV = {'github': 'XTI_GITHUB_TOKEN', 'gitlab': 'XTI_GITLAB_TOKEN'}


def key_path(provider):
    if provider not in ENV: raise ValidationError('Anahtar kaynağı github veya gitlab olmalı.')
    root = os.environ.get('XDG_CONFIG_HOME', '')
    return (Path(root) if Path(root).is_absolute() else Path.home() / '.config') / 'xti' / (provider + '.key')


def load_key(provider):
    path = key_path(provider)
    if ENV[provider] in os.environ:
        value = os.environ[ENV[provider]]
        if re.fullmatch(r'[A-Za-z0-9._~+/=-]{16,512}', value) is None:
            raise ValidationError('Kaynak anahtarı geçersiz; değeri gösterilmiyor.')
        return value
    if not path.exists() and not path.is_symlink(): return None
    try:
        return read_private_key(path)
    except ValidationError:
        raise ValidationError('Kaynak anahtarı güvenle okunamadı; sahibini ve 600 dosya iznini kontrol edin.') from None


def save_key(provider, value):
    try:
        return write_private_key(value, key_path(provider))
    except ValidationError:
        raise ValidationError('Kaynak anahtarı kaydedilemedi; biçim/izin veya mevcut dosyayı kontrol edin. Üzerine yazılmadı.') from None
