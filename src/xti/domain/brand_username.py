"""Minimal, source-preserving social username preview models."""

from dataclasses import dataclass
import re

from xti.domain.assets import ValidationError


USERNAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{1,63}")
MAIGRET_PLATFORM_HOSTS = {
    "Behance": ("behance.net",),
    "BitBucket": ("bitbucket.org",),
    "Bluesky": ("bsky.app",),
    "BuyMeACoffee": ("buymeacoff.ee", "buymeacoffee.com"),
    "Codepen": ("codepen.io",),
    "Facebook": ("facebook.com",),
    "Flickr": ("flickr.com",),
    "GitHub": ("github.com",),
    "GitLab": ("gitlab.com",),
    "HackerNews": ("ycombinator.com", "firebaseio.com"),
    "HuggingFace": ("huggingface.co",),
    "Instagram": ("instagram.com",),
    "Kaggle": ("kaggle.com",),
    "Keybase": ("keybase.io",),
    "LinkedIn": ("linkedin.com",),
    "Medium": ("medium.com",),
    "Patreon": ("patreon.com",),
    "Pinterest": ("pinterest.com",),
    "ProductHunt": ("producthunt.com",),
    "Reddit": ("reddit.com",),
    "Replit": ("replit.com",),
    "SoundCloud": ("soundcloud.com",),
    "Steam": ("steamcommunity.com",),
    "Telegram": ("t.me",),
    "Threads": ("threads.com",),
    "TikTok": ("tiktok.com",),
    "Twitter": ("twitter.com", "x.com"),
    "Vimeo": ("vimeo.com",),
    "WordPress": ("wordpress.com",),
    "YouTube": ("youtube.com",),
}
SHERLOCK_PLATFORM_HOSTS = {
    "Behance": ("behance.net",),
    "BitBucket": ("bitbucket.org",),
    "Bluesky": ("bsky.app",),
    "BuyMeACoffee": ("buymeacoff.ee", "buymeacoffee.com"),
    "Carrd": ("carrd.co",),
    "CashApp": ("cash.app",),
    "Codeberg": ("codeberg.org",),
    "Codepen": ("codepen.io",),
    "CodeSandbox": ("codesandbox.io",),
    "Flickr": ("flickr.com",),
    "GitBook": ("gitbook.com", "gitbook.io"),
    "HackerNews": ("ycombinator.com",),
    "Kaggle": ("kaggle.com",),
    "Linktree": ("linktr.ee",),
    "Medium": ("medium.com",),
    "Patreon": ("patreon.com",),
    "Pinterest": ("pinterest.com",),
    "ProductHunt": ("producthunt.com",),
    "ResearchGate": ("researchgate.net",),
    "Rumble": ("rumble.com",),
    "SoundCloud": ("soundcloud.com",),
    "Strava": ("strava.com",),
    "Telegram": ("t.me",),
    "Twitch": ("twitch.tv",),
    "Vimeo": ("vimeo.com",),
    "Weebly": ("weebly.com",),
}
# Backward-compatible Maigret alias. Persistent validation uses the union below.
PLATFORM_HOSTS = MAIGRET_PLATFORM_HOSTS
ALL_PLATFORM_HOSTS = {
    **MAIGRET_PLATFORM_HOSTS,
    **SHERLOCK_PLATFORM_HOSTS,
}
BRAND_USERNAME_SOURCE_NAMES = {
    "maigret": "Maigret",
    "sherlock": "Sherlock",
}


def normalize_brand_username(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Kullanıcı adı metin olmalı.")
    normalized = value.strip()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise ValidationError(
            "Kullanıcı adı 2–64 karakter olmalı; harf/rakamla başlamalı ve yalnız "
            "harf, rakam, nokta, alt çizgi veya tire içermeli."
        )
    return normalized


@dataclass(frozen=True, slots=True)
class BrandProfileMatch:
    platform: str
    profile_url: str
    status: str


@dataclass(frozen=True, slots=True)
class BrandUsernamePreview:
    username: str
    source: str
    source_version: str
    integration_profile: str
    checked_at: str
    requested_platforms: tuple[str, ...]
    matches: tuple[BrandProfileMatch, ...]
    unreported_platforms: tuple[str, ...]
    notes: tuple[str, ...]
    selection_profile: str = "custom"
