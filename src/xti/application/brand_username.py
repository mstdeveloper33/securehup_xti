"""Bounded orchestration for a public-profile username preview."""

from xti.domain.assets import ValidationError
from xti.domain.brand_username import BrandUsernamePreview, normalize_brand_username
from xti.ports.brand_username import BrandUsernameSource


DEFAULT_PLATFORMS = (
    "GitHub",
    "GitLab",
    "Reddit",
    "Instagram",
    "TikTok",
    "YouTube",
)
SUPPORTED_PLATFORMS = (
    "Facebook",
    "GitHub",
    "GitLab",
    "Instagram",
    "Keybase",
    "LinkedIn",
    "Reddit",
    "TikTok",
    "Twitter",
    "YouTube",
)
MAX_PLATFORMS = 10
SHERLOCK_DEFAULT_PLATFORMS = (
    "Carrd",
    "CodeSandbox",
    "GitBook",
    "Rumble",
    "Weebly",
)
SHERLOCK_SUPPORTED_PLATFORMS = (
    "Carrd",
    "CashApp",
    "CodeSandbox",
    "GitBook",
    "ResearchGate",
    "Rumble",
    "Strava",
    "Weebly",
)
SHERLOCK_MAX_PLATFORMS = 8


def validate_brand_platforms(platforms: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(platforms, tuple) or not platforms:
        raise ValidationError("En az bir platform seçilmeli.")
    if len(platforms) > MAX_PLATFORMS:
        raise ValidationError(f"En fazla {MAX_PLATFORMS} platform seçilebilir.")
    if len(set(platforms)) != len(platforms):
        raise ValidationError("Aynı platform birden fazla kez seçilemez.")
    unknown = [item for item in platforms if item not in SUPPORTED_PLATFORMS]
    if unknown:
        raise ValidationError(f"Desteklenmeyen platform: {unknown[0]}")
    return platforms


def validate_sherlock_platforms(platforms: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(platforms, tuple) or not platforms:
        raise ValidationError("En az bir Sherlock platformu seçilmeli.")
    if len(platforms) > SHERLOCK_MAX_PLATFORMS:
        raise ValidationError(
            f"En fazla {SHERLOCK_MAX_PLATFORMS} Sherlock platformu seçilebilir."
        )
    if len(set(platforms)) != len(platforms):
        raise ValidationError("Aynı Sherlock platformu birden fazla kez seçilemez.")
    unknown = [
        item for item in platforms if item not in SHERLOCK_SUPPORTED_PLATFORMS
    ]
    if unknown:
        raise ValidationError(f"Desteklenmeyen Sherlock platformu: {unknown[0]}")
    return platforms


def validate_brand_request_timeout(value: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 5 <= value <= 30
    ):
        raise ValidationError("Platform istek süresi 5–30 saniye olmalı.")
    return value


class BrandUsernamePreviewService:
    def __init__(self, source: BrandUsernameSource):
        self.source = source

    def preview(
        self,
        username: str,
        *,
        platforms: tuple[str, ...] | None = None,
        request_timeout: int = 10,
    ) -> BrandUsernamePreview:
        normalized = normalize_brand_username(username)
        selected = DEFAULT_PLATFORMS if platforms is None else platforms
        selected = validate_brand_platforms(selected)
        request_timeout = validate_brand_request_timeout(request_timeout)
        return self.source.preview(
            normalized,
            platforms=selected,
            request_timeout=request_timeout,
        )


class SherlockUsernamePreviewService:
    def __init__(self, source: BrandUsernameSource):
        self.source = source

    def preview(
        self,
        username: str,
        *,
        platforms: tuple[str, ...] | None = None,
        request_timeout: int = 10,
    ) -> BrandUsernamePreview:
        normalized = normalize_brand_username(username)
        selected = SHERLOCK_DEFAULT_PLATFORMS if platforms is None else platforms
        selected = validate_sherlock_platforms(selected)
        request_timeout = validate_brand_request_timeout(request_timeout)
        return self.source.preview(
            normalized,
            platforms=selected,
            request_timeout=request_timeout,
        )
