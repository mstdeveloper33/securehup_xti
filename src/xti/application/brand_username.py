"""Bounded orchestration for a public-profile username preview."""

from dataclasses import replace

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
EXTENDED_PLATFORMS = (
    "Behance",
    "BitBucket",
    "Bluesky",
    "BuyMeACoffee",
    "Codepen",
    "Facebook",
    "Flickr",
    "GitHub",
    "GitLab",
    "HackerNews",
    "HuggingFace",
    "Instagram",
    "Kaggle",
    "Keybase",
    "LinkedIn",
    "Medium",
    "Patreon",
    "Pinterest",
    "ProductHunt",
    "Reddit",
    "Replit",
    "SoundCloud",
    "Steam",
    "Telegram",
    "Threads",
    "TikTok",
    "Twitter",
    "Vimeo",
    "WordPress",
    "YouTube",
)
SUPPORTED_PLATFORMS = (
    *EXTENDED_PLATFORMS,
)
MAX_PLATFORMS = 30
SHERLOCK_DEFAULT_PLATFORMS = (
    "Carrd",
    "CodeSandbox",
    "GitBook",
    "Rumble",
    "Weebly",
)
SHERLOCK_EXTENDED_PLATFORMS = (
    "Behance",
    "BitBucket",
    "Bluesky",
    "BuyMeACoffee",
    "Carrd",
    "CashApp",
    "Codeberg",
    "Codepen",
    "CodeSandbox",
    "Flickr",
    "GitBook",
    "HackerNews",
    "Kaggle",
    "Linktree",
    "Medium",
    "Patreon",
    "Pinterest",
    "ProductHunt",
    "ResearchGate",
    "Rumble",
    "SoundCloud",
    "Strava",
    "Telegram",
    "Twitch",
    "Vimeo",
    "Weebly",
)
SHERLOCK_SUPPORTED_PLATFORMS = (
    *SHERLOCK_EXTENDED_PLATFORMS,
)
SHERLOCK_MAX_PLATFORMS = 26
SELECTION_PROFILES = ("safe", "extended")


def resolve_username_selection(
    platforms: tuple[str, ...] | None,
    profile: str | None,
    *,
    safe: tuple[str, ...],
    extended: tuple[str, ...],
) -> tuple[tuple[str, ...], str]:
    if platforms is not None:
        if profile is not None:
            raise ValidationError("--profile ve --site birlikte kullanılamaz.")
        return platforms, "custom"
    selected_profile = "safe" if profile is None else profile
    if selected_profile not in SELECTION_PROFILES:
        raise ValidationError("Profil safe veya extended olmalı.")
    return (
        safe if selected_profile == "safe" else extended,
        selected_profile,
    )


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
        profile: str | None = None,
        request_timeout: int = 10,
    ) -> BrandUsernamePreview:
        normalized = normalize_brand_username(username)
        selected, selection_profile = resolve_username_selection(
            platforms,
            profile,
            safe=DEFAULT_PLATFORMS,
            extended=EXTENDED_PLATFORMS,
        )
        selected = validate_brand_platforms(selected)
        request_timeout = validate_brand_request_timeout(request_timeout)
        report = self.source.preview(
            normalized,
            platforms=selected,
            request_timeout=request_timeout,
        )
        return replace(report, selection_profile=selection_profile)


class SherlockUsernamePreviewService:
    def __init__(self, source: BrandUsernameSource):
        self.source = source

    def preview(
        self,
        username: str,
        *,
        platforms: tuple[str, ...] | None = None,
        profile: str | None = None,
        request_timeout: int = 10,
    ) -> BrandUsernamePreview:
        normalized = normalize_brand_username(username)
        selected, selection_profile = resolve_username_selection(
            platforms,
            profile,
            safe=SHERLOCK_DEFAULT_PLATFORMS,
            extended=SHERLOCK_EXTENDED_PLATFORMS,
        )
        selected = validate_sherlock_platforms(selected)
        request_timeout = validate_brand_request_timeout(request_timeout)
        report = self.source.preview(
            normalized,
            platforms=selected,
            request_timeout=request_timeout,
        )
        return replace(report, selection_profile=selection_profile)
