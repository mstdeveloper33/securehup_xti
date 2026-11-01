"""The first supported asset type: an explicitly supplied ASCII DNS domain."""

from dataclasses import dataclass
import ipaddress
import re


class ValidationError(ValueError):
    """A user's asset value does not satisfy the current domain contract."""


@dataclass(frozen=True, slots=True)
class Asset:
    """A saved asset; registration does not establish existence or ownership."""

    id: str
    value: str
    created_at: str


_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.ASCII)


def normalize_domain(value: str) -> str:
    """Validate a DNS-style ASCII name without making any network request.

    Unicode input is not silently converted here.  The dedicated, versioned
    IDNA profile converts external U-labels before this canonical validator;
    saved watched assets remain ordinary ASCII names in the current release.
    """
    if not isinstance(value, str):
        raise ValidationError("Alan adı metin olarak verilmelidir.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValidationError("Alan adı kontrol karakteri içeremez.")
    if not value.isascii():
        raise ValidationError("Bu sürümde yalnız ASCII alan adları destekleniyor.")
    normalized = value.strip().lower()
    if normalized.endswith("."):
        normalized = normalized[:-1]
    if not normalized or len(normalized) > 253:
        raise ValidationError("Alan adı 1–253 karakter uzunluğunda olmalıdır.")
    try:
        ipaddress.ip_address(normalized)
    except ValueError:
        pass
    else:
        raise ValidationError("Bu komut IP adresi yerine alan adı bekliyor.")
    labels = normalized.split(".")
    if len(labels) < 2 or any(_LABEL.fullmatch(label) is None for label in labels):
        raise ValidationError(
            "Geçerli bir alan adı girin: example.com. "
            "Adresin başına https://, sonuna yol veya port eklemeyin."
        )
    if labels[-1].isdigit():
        raise ValidationError("Alan adının son bölümü yalnız rakamlardan oluşamaz.")
    return normalized
