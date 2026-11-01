"""Exact, user-verified Red Hat RPM inventory evidence."""

from dataclasses import dataclass
import re
from urllib.parse import quote
from uuid import UUID

from xti.domain.assets import ValidationError


PACKAGE_PROVIDERS = {"redhat"}
PACKAGE_ECOSYSTEMS = {"rpm"}
PACKAGE_EVIDENCE_TYPES = {"user_verified"}

_RPM_NAME = re.compile(r"[a-z0-9][a-z0-9+._-]{0,254}", re.ASCII)
_RPM_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+~^]{0,254}", re.ASCII)
_RPM_ARCH = re.compile(r"[a-z0-9][a-z0-9_]{0,31}", re.ASCII)
_REDHAT_CPE = re.compile(
    r"cpe:/o:redhat:enterprise_linux:[a-z0-9][a-z0-9._-]{0,63}"
    r"(?:::[a-z0-9][a-z0-9._-]{0,63})?",
    re.ASCII,
)


def normalize_package_provider(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Paket sağlayıcısı gerekli.")
    normalized = value.strip().lower()
    if normalized not in PACKAGE_PROVIDERS:
        raise ValidationError("Paket sağlayıcısı şimdilik yalnız 'redhat' olabilir.")
    return normalized


def normalize_package_ecosystem(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Paket ekosistemi gerekli.")
    normalized = value.strip().lower()
    if normalized not in PACKAGE_ECOSYSTEMS:
        raise ValidationError("Paket ekosistemi şimdilik yalnız 'rpm' olabilir.")
    return normalized


def normalize_rpm_name(value: str, *, field: str = "RPM paket adı") -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} gerekli.")
    normalized = value.strip().lower()
    if _RPM_NAME.fullmatch(normalized) is None:
        raise ValidationError(
            f"{field} küçük harf, sayı, nokta, artı, alt çizgi ve tire içeren kanonik ad olmalı."
        )
    return normalized


def normalize_rpm_epoch(value: int | str) -> int:
    if isinstance(value, bool):
        raise ValidationError("RPM epoch değeri 0–2147483647 arasında tam sayı olmalı.")
    try:
        normalized = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError("RPM epoch değeri 0–2147483647 arasında tam sayı olmalı.") from error
    if isinstance(value, str) and value != str(normalized):
        raise ValidationError("RPM epoch değeri başında sıfır olmayan kanonik tam sayı olmalı.")
    if not 0 <= normalized <= 2_147_483_647:
        raise ValidationError("RPM epoch değeri 0–2147483647 arasında tam sayı olmalı.")
    return normalized


def _rpm_value(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} gerekli.")
    normalized = value.strip()
    if _RPM_VALUE.fullmatch(normalized) is None:
        raise ValidationError(
            f"{field} 1–255 karakterlik kanonik RPM değeri olmalı; boşluk veya adres işareti içeremez."
        )
    return normalized


def normalize_rpm_version(value: str) -> str:
    return _rpm_value(value, field="RPM sürümü")


def normalize_rpm_release(value: str) -> str:
    return _rpm_value(value, field="RPM release değeri")


def normalize_rpm_architecture(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("RPM mimarisi gerekli.")
    normalized = value.strip().lower()
    if _RPM_ARCH.fullmatch(normalized) is None:
        raise ValidationError("RPM mimarisi küçük harf, sayı ve alt çizgiden oluşmalı.")
    return normalized


def normalize_redhat_distribution_cpe(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Red Hat dağıtım CPE kimliği gerekli.")
    normalized = value.strip().lower()
    if _REDHAT_CPE.fullmatch(normalized) is None:
        raise ValidationError(
            "Dağıtım CPE kimliği 'cpe:/o:redhat:enterprise_linux:SURUM' "
            "veya ürün eki taşıyan kesin Red Hat biçiminde olmalı."
        )
    return normalized


def normalize_source_rpm(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError("Kaynak RPM adı geçersiz.")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 800 or "/" in normalized or not normalized.endswith(".src.rpm"):
        raise ValidationError("Kaynak RPM, dizin içermeyen tam bir '.src.rpm' dosya adı olmalı.")
    body = normalized[:-8]
    try:
        name, version, release = body.rsplit("-", 2)
    except ValueError as error:
        raise ValidationError("Kaynak RPM adı paket-sürüm-release.src.rpm biçiminde olmalı.") from error
    canonical = (
        f"{normalize_rpm_name(name, field='Kaynak RPM paket adı')}-"
        f"{normalize_rpm_version(version)}-{normalize_rpm_release(release)}.src.rpm"
    )
    if canonical != normalized:
        raise ValidationError("Kaynak RPM adı kanonik biçimde olmalı.")
    return canonical


def source_rpm_parts(value: str | None) -> tuple[str, str, str] | None:
    normalized = normalize_source_rpm(value)
    if normalized is None:
        return None
    return tuple(normalized[:-8].rsplit("-", 2))  # type: ignore[return-value]


def redhat_rpm_purl(
    *, name: str, version: str, release: str, architecture: str,
) -> str:
    package = normalize_rpm_name(name)
    version = normalize_rpm_version(version)
    release = normalize_rpm_release(release)
    architecture = normalize_rpm_architecture(architecture)
    encoded_version = quote(f"{version}-{release}", safe="._+~^-")
    return f"pkg:rpm/redhat/{package}@{encoded_version}?arch={architecture}"


def redhat_source_purl(name: str) -> str:
    return f"pkg:rpm/redhat/{normalize_rpm_name(name, field='Kaynak RPM paket adı')}?arch=src"


def rpm_nevra(
    *, name: str, epoch: int | str, version: str, release: str, architecture: str,
) -> str:
    return (
        f"{normalize_rpm_name(name)}-{normalize_rpm_epoch(epoch)}:"
        f"{normalize_rpm_version(version)}-{normalize_rpm_release(release)}."
        f"{normalize_rpm_architecture(architecture)}"
    )


def normalize_package_evidence(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Paket doğrulama kanıtı gerekli.")
    normalized = " ".join(value.strip().split())
    if not 5 <= len(normalized) <= 1000 or any(not character.isprintable() for character in normalized):
        raise ValidationError("Paket doğrulama kanıtı 5–1000 güvenli karakter arasında olmalı.")
    return normalized


def normalize_package_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Geçerli bir paket kanıtı kimliği gerekli.")
    try:
        normalized = str(UUID(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError("Geçerli bir paket kanıtı kimliği gerekli.") from error
    if value != normalized:
        raise ValidationError("Paket kanıtı kimliği kanonik UUID biçiminde olmalı.")
    return normalized


@dataclass(frozen=True, slots=True)
class AssetPackageEvidence:
    id: str
    asset_id: str
    asset_value: str
    provider: str
    ecosystem: str
    name: str
    epoch: int
    version: str
    release: str
    architecture: str
    source_rpm: str | None
    distribution_cpe: str
    purl: str
    active: bool
    evidence_type: str
    evidence: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AssetPackageEvent:
    id: str
    asset_package_id: str
    action: str
    source_rpm: str | None
    evidence_type: str
    evidence: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class AssetPackageMutation:
    action: str
    record: AssetPackageEvidence


@dataclass(frozen=True, slots=True)
class AssetPackageDetails:
    record: AssetPackageEvidence
    events: tuple[AssetPackageEvent, ...]
    total_event_count: int
