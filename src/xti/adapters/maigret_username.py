"""Safe, optional subprocess adapter for the upstream Maigret CLI."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib.resources import files
import json
import math
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Callable
from urllib.parse import urlsplit

from xti.domain.brand_username import (
    PLATFORM_HOSTS,
    BrandProfileMatch,
    BrandUsernamePreview,
)
from xti.ports.discovery import SourceError


SOURCE_NAME = "Maigret"
SOURCE_VERSION = "0.6.6"
REVIEWED_UPSTREAM_COMMIT = "b8747b98820f4df9d1baf23235db7b2cb55d0198"
INTEGRATION_PROFILE = f"maigret-{SOURCE_VERSION}-{REVIEWED_UPSTREAM_COMMIT[:12]}-safe-v1"
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_LINE_BYTES = 128 * 1024
MAX_PROCESS_OUTPUT = 64 * 1024
MAX_DATABASE_BYTES = 4 * 1024 * 1024
REVIEWED_DATABASE_SHA256 = (
    "8dd404e6b3012f01fd467c154b5159386d1362587070c661c2565ec8fa649899"
)

def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _safe_text(value: object, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise SourceError("Maigret beklenmeyen sonuç üretti; sonuç gösterilmedi.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise SourceError("Maigret beklenmeyen sonuç üretti; sonuç gösterilmedi.")
    return value


def _validate_profile_url(platform: str, value: object) -> str:
    url = _safe_text(value)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise SourceError("Maigret güvenli olmayan profil adresi üretti.")
    hostname = parsed.hostname.rstrip(".").lower()
    allowed = PLATFORM_HOSTS[platform]
    if not any(hostname == item or hostname.endswith(f".{item}") for item in allowed):
        raise SourceError("Maigret platformla uyuşmayan profil adresi üretti.")
    return url


def parse_maigret_ndjson(
    payload: bytes,
    *,
    username: str,
    platforms: tuple[str, ...],
) -> tuple[BrandProfileMatch, ...]:
    if len(payload) > MAX_REPORT_BYTES:
        raise SourceError("Maigret sonuç dosyası güvenli boyut sınırını aştı.")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceError("Maigret sonucu UTF-8 değil; sonuç gösterilmedi.") from error
    matches: dict[str, BrandProfileMatch] = {}
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        if len(raw_line.encode("utf-8")) > MAX_LINE_BYTES:
            raise SourceError("Maigret sonuç satırı güvenli boyut sınırını aştı.")
        try:
            item = json.loads(raw_line, object_pairs_hook=_no_duplicate_keys)
        except (ValueError, json.JSONDecodeError) as error:
            raise SourceError("Maigret bozuk NDJSON üretti; sonuç gösterilmedi.") from error
        if not isinstance(item, dict):
            raise SourceError("Maigret beklenmeyen sonuç üretti; sonuç gösterilmedi.")
        platform = _safe_text(item.get("sitename"), maximum=80)
        if platform not in platforms or platform in matches:
            raise SourceError("Maigret seçilmeyen veya yinelenen platform sonucu üretti.")
        if item.get("username") != username:
            raise SourceError("Maigret sonucu istenen kullanıcı adıyla uyuşmuyor.")
        status = item.get("status")
        if not isinstance(status, dict):
            raise SourceError("Maigret sonuç durumu eksik; sonuç gösterilmedi.")
        profile_url = _validate_profile_url(platform, item.get("url_user"))
        if (
            status.get("username") != username
            or status.get("site_name") != platform
            or status.get("url") != profile_url
            or status.get("status") != "Claimed"
        ):
            raise SourceError("Maigret sonuç kanıtı kendi içinde tutarsız.")
        matches[platform] = BrandProfileMatch(
            platform=platform,
            profile_url=profile_url,
            status="found_unverified",
        )
    return tuple(matches[item] for item in platforms if item in matches)


def _write_scoped_database(
    source: Path,
    target: Path,
    *,
    platforms: tuple[str, ...],
    expected_sha256: str,
) -> None:
    try:
        metadata = source.lstat()
    except FileNotFoundError as error:
        raise SourceError("Maigret site veritabanı bulunamadı.") from error
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise SourceError("Maigret site veritabanı güvenli bir dosya değil.")
    with source.open("rb") as stream:
        payload = stream.read(MAX_DATABASE_BYTES + 1)
    if len(payload) > MAX_DATABASE_BYTES:
        raise SourceError("Maigret site veritabanı güvenli boyut sınırını aştı.")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise SourceError("Maigret site veritabanı incelenen sürümle uyuşmuyor.")
    try:
        database = json.loads(payload, object_pairs_hook=_no_duplicate_keys)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise SourceError("Maigret site veritabanı bozuk.") from error
    if not isinstance(database, dict):
        raise SourceError("Maigret site veritabanı beklenen yapıda değil.")
    sites = database.get("sites")
    if not isinstance(sites, dict):
        raise SourceError("Maigret site veritabanında platformlar eksik.")
    scoped_sites = {}
    for platform in platforms:
        site = sites.get(platform)
        if not isinstance(site, dict) or site.get("source"):
            raise SourceError(f"Maigret {platform} tanımı güvenli biçimde seçilemedi.")
        for field in ("url", "urlMain", "urlProbe"):
            value = site.get(field)
            if value is None:
                continue
            if not isinstance(value, str):
                raise SourceError(f"Maigret {platform} adresi beklenen yapıda değil.")
            candidate = value.replace("{username}", "xti-preview")
            parsed = urlsplit(candidate)
            hostname = parsed.hostname.rstrip(".").lower() if parsed.hostname else ""
            if parsed.scheme != "https" or not any(
                hostname == allowed or hostname.endswith(f".{allowed}")
                for allowed in PLATFORM_HOSTS[platform]
            ):
                raise SourceError(f"Maigret {platform} adresi izinli platform dışında.")
        scoped_sites[platform] = site
    scoped = {
        "sites": scoped_sites,
        "engines": database.get("engines", {}),
        "tags": database.get("tags", []),
    }
    target.write_text(
        json.dumps(scoped, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    target.chmod(0o600)


class MaigretUsernameSource:
    source_name = SOURCE_NAME
    source_version = SOURCE_VERSION
    integration_profile = INTEGRATION_PROFILE

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        executable_locator: Callable[[], str | None] | None = None,
        database_locator: Callable[[], Path | None] | None = None,
        database_sha256: str = REVIEWED_DATABASE_SHA256,
        clock: Callable[[], datetime] | None = None,
    ):
        self._runner = runner or subprocess.run
        self._executable_locator = executable_locator or self._locate_executable
        self._database_locator = database_locator or self._locate_database
        self._database_sha256 = database_sha256
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _locate_executable() -> str | None:
        # Keep the virtual-environment path. Resolving its Python symlink would
        # incorrectly look beside the system interpreter instead of .venv/bin.
        adjacent = Path(sys.executable).parent / "maigret"
        if adjacent.is_file() and os.access(adjacent, os.X_OK):
            return str(adjacent)
        return shutil.which("maigret")

    @staticmethod
    def _locate_database() -> Path | None:
        try:
            database = files("maigret").joinpath("resources", "data.json")
        except (ModuleNotFoundError, TypeError):
            return None
        path = Path(str(database))
        return path if path.is_file() else None

    @staticmethod
    def _safe_environment(directory: str) -> dict[str, str]:
        environment = dict(os.environ)
        for name in (
            "ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "OPENAI_API_KEY",
            "all_proxy", "https_proxy", "http_proxy",
        ):
            environment.pop(name, None)
        environment.update({
            "HOME": directory,
            "NO_PROXY": "*",
            "no_proxy": "*",
            "PYTHONIOENCODING": "utf-8",
        })
        return environment

    @staticmethod
    def _write_safe_settings(directory: Path) -> None:
        settings = {
            "retries_count": 0,
            "timeout": 10,
            "max_connections": 4,
            "recursive_search": False,
            "info_extracting": False,
            "cookie_jar_file": None,
            "proxy_url": None,
            "tor_proxy_url": None,
            "i2p_proxy_url": None,
            "domain_search": False,
            "scan_all_sites": False,
            "scan_disabled_sites": False,
            "scan_sites_list": [],
            "print_not_found": False,
            "print_check_errors": False,
            "colored_print": False,
            "show_progressbar": False,
            "json_report_type": "",
            "no_autoupdate": True,
            "cloudflare_bypass": {"enabled": False, "modules": []},
        }
        (directory / "settings.json").write_text(
            json.dumps(settings, ensure_ascii=True, separators=(",", ":")),
            encoding="utf-8",
        )

    def _run(self, command: list[str], *, cwd: str, timeout: int):
        try:
            result = self._runner(
                command,
                cwd=cwd,
                env=self._safe_environment(cwd),
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as error:
            raise SourceError("Maigret süre sınırında tamamlanamadı.") from error
        except OSError as error:
            raise SourceError("Maigret çalıştırılamadı; sonuç üretilmedi.") from error
        if (
            len(result.stdout.encode("utf-8", errors="replace")) > MAX_PROCESS_OUTPUT
            or len(result.stderr.encode("utf-8", errors="replace")) > MAX_PROCESS_OUTPUT
        ):
            raise SourceError("Maigret işlem çıktısı güvenli boyut sınırını aştı.")
        return result

    def preview(
        self,
        username: str,
        *,
        platforms: tuple[str, ...],
        request_timeout: int,
    ) -> BrandUsernamePreview:
        executable = self._executable_locator()
        if not executable:
            raise SourceError(
                "Maigret kurulu değil. Bir kez ./scripts/setup-brand çalıştır."
            )
        database = self._database_locator()
        if database is None:
            raise SourceError("Maigret site veritabanı bulunamadı; kurulum eksik.")
        with tempfile.TemporaryDirectory(prefix="xti-maigret-") as temporary:
            directory = Path(temporary)
            self._write_safe_settings(directory)
            version = self._run(
                [executable, "--version"], cwd=temporary, timeout=15,
            )
            first_line = version.stdout.splitlines()[0] if version.stdout else ""
            if version.returncode != 0 or first_line != f"maigret {SOURCE_VERSION}":
                raise SourceError(
                    f"Maigret {SOURCE_VERSION} gerekiyor; farklı sürüm çalıştırılmadı."
                )
            scoped_database = directory / "scoped-sites.json"
            _write_scoped_database(
                database,
                scoped_database,
                platforms=platforms,
                expected_sha256=self._database_sha256,
            )
            command = [
                executable,
                username,
                "--db", str(scoped_database),
                "--json", "ndjson",
                "--folderoutput", "reports",
                "--no-recursion",
                "--no-extracting",
                "--no-autoupdate",
                "--timeout", str(request_timeout),
                "--retries", "0",
                "--max-connections", "4",
                "--no-color",
                "--no-progressbar",
            ]
            for platform in platforms:
                command.extend(("--site", platform))
            process_timeout = min(
                120,
                request_timeout * math.ceil(len(platforms) / 4) + 20,
            )
            result = self._run(
                command, cwd=temporary, timeout=process_timeout,
            )
            if result.returncode != 0:
                raise SourceError("Maigret taraması tamamlanamadı; sonuç üretilmedi.")
            report = directory / "reports" / f"report_{username}_ndjson.json"
            try:
                metadata = report.lstat()
            except FileNotFoundError as error:
                raise SourceError("Maigret sonuç dosyası üretmedi.") from error
            if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise SourceError("Maigret güvenli bir sonuç dosyası üretmedi.")
            with report.open("rb") as stream:
                payload = stream.read(MAX_REPORT_BYTES + 1)
            matches = parse_maigret_ndjson(
                payload,
                username=username,
                platforms=platforms,
            )
        matched = {item.platform for item in matches}
        return BrandUsernamePreview(
            username=username,
            source=SOURCE_NAME,
            source_version=SOURCE_VERSION,
            integration_profile=INTEGRATION_PROFILE,
            checked_at=self._clock().isoformat(),
            requested_platforms=platforms,
            matches=matches,
            unreported_platforms=tuple(
                platform for platform in platforms if platform not in matched
            ),
            notes=(
                "Yalnız seçili herkese açık profil kontrolleri çalıştırıldı.",
                "Raporlanmayan platform; hesap yok, kaynak engeli veya kontrol hatası "
                "anlamlarından hangisi olduğunu tek başına göstermez.",
                "Bulunan aynı kullanıcı adı, hesabın aynı kişi/marka veya taklit "
                "olduğunu kanıtlamaz; insan incelemesi gerekir.",
                "Sonuç yazılmadı; Tor/proxy, otomatik güncelleme, profil çıkarımı, "
                "özyineleme, domain arama, Cloudflare aşma ve yapay zekâ kapalıydı.",
            ),
        )
