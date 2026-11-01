"""Safe subprocess adapter for a pinned subset of upstream Sherlock."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
import json
import os
from pathlib import Path
import math
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

from xti.domain.brand_username import (
    SHERLOCK_PLATFORM_HOSTS as PLATFORM_HOSTS,
    BrandProfileMatch,
    BrandUsernamePreview,
)
from xti.ports.discovery import SourceError


SOURCE_NAME = "Sherlock"
SOURCE_VERSION = "0.16.2"
REVIEWED_UPSTREAM_COMMIT = "a38ba54fda799cd786a2ab67a50143e1a63169e6"
INTEGRATION_PROFILE = (
    f"sherlock-{SOURCE_VERSION}-{REVIEWED_UPSTREAM_COMMIT[:12]}-safe-v1"
)
REVIEWED_DATABASE_SHA256 = (
    "3fdfc6694c5cd99798881215554b09e617c6d5284a6219fae309882566a9fb30"
)
MAX_DATABASE_BYTES = 256 * 1024
MAX_REPORT_BYTES = 256 * 1024
MAX_LINE_BYTES = 16 * 1024
MAX_PROCESS_OUTPUT = 32 * 1024
_DATABASE_FIELDS = ("url", "urlMain", "urlProbe", "errorUrl")
_RESULT_KEYS = frozenset({"username", "platform", "profile_url", "status"})
_STATUSES = frozenset({"Claimed", "Available", "Unknown", "Illegal", "WAF"})


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _safe_text(value: object, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise SourceError("Sherlock beklenmeyen sonuç üretti; sonuç gösterilmedi.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise SourceError("Sherlock beklenmeyen sonuç üretti; sonuç gösterilmedi.")
    return value


def _allowed_host(platform: str, value: str) -> bool:
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        return False
    hostname = parsed.hostname.rstrip(".").lower()
    return any(
        hostname == allowed or hostname.endswith(f".{allowed}")
        for allowed in PLATFORM_HOSTS[platform]
    )


def _validate_profile_url(platform: str, value: object) -> str:
    result = _safe_text(value)
    if not _allowed_host(platform, result):
        raise SourceError("Sherlock güvenli olmayan profil adresi üretti.")
    return result


def parse_sherlock_ndjson(
    payload: bytes,
    *,
    username: str,
    platforms: tuple[str, ...],
) -> tuple[BrandProfileMatch, ...]:
    if len(payload) > MAX_REPORT_BYTES:
        raise SourceError("Sherlock sonuç dosyası güvenli boyut sınırını aştı.")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceError("Sherlock sonucu UTF-8 değil; sonuç gösterilmedi.") from error
    results: dict[str, BrandProfileMatch | None] = {}
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        if len(raw_line.encode("utf-8")) > MAX_LINE_BYTES:
            raise SourceError("Sherlock sonuç satırı güvenli boyut sınırını aştı.")
        try:
            item = json.loads(raw_line, object_pairs_hook=_no_duplicate_keys)
        except (ValueError, json.JSONDecodeError) as error:
            raise SourceError("Sherlock bozuk NDJSON üretti; sonuç gösterilmedi.") from error
        if not isinstance(item, dict) or frozenset(item) != _RESULT_KEYS:
            raise SourceError("Sherlock beklenmeyen sonuç üretti; sonuç gösterilmedi.")
        platform = _safe_text(item["platform"], maximum=80)
        if (
            platform not in platforms
            or platform not in PLATFORM_HOSTS
            or platform in results
        ):
            raise SourceError("Sherlock seçilmeyen veya yinelenen platform sonucu üretti.")
        if (
            item["username"] != username
            or not isinstance(item["status"], str)
            or item["status"] not in _STATUSES
        ):
            raise SourceError("Sherlock sonuç kanıtı kendi içinde tutarsız.")
        profile_url = item["profile_url"]
        if item["status"] == "Claimed":
            results[platform] = BrandProfileMatch(
                platform=platform,
                profile_url=_validate_profile_url(platform, profile_url),
                status="found_unverified",
            )
        elif profile_url is not None:
            raise SourceError("Sherlock sonuç kanıtı kendi içinde tutarsız.")
        else:
            results[platform] = None
    if set(results) != set(platforms):
        raise SourceError("Sherlock bütün seçili platformların sonucunu üretmedi.")
    return tuple(
        result for platform in platforms
        if (result := results[platform]) is not None
    )


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
        raise SourceError("Sherlock site veritabanı bulunamadı.") from error
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise SourceError("Sherlock site veritabanı güvenli bir dosya değil.")
    with source.open("rb") as stream:
        payload = stream.read(MAX_DATABASE_BYTES + 1)
    if len(payload) > MAX_DATABASE_BYTES:
        raise SourceError("Sherlock site veritabanı güvenli boyut sınırını aştı.")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise SourceError("Sherlock site veritabanı incelenen sürümle uyuşmuyor.")
    try:
        database = json.loads(payload, object_pairs_hook=_no_duplicate_keys)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise SourceError("Sherlock site veritabanı bozuk.") from error
    if not isinstance(database, dict):
        raise SourceError("Sherlock site veritabanı beklenen yapıda değil.")
    scoped = {}
    for platform in platforms:
        if platform not in PLATFORM_HOSTS:
            raise SourceError(f"Sherlock {platform} platformu desteklenmiyor.")
        site = database.get(platform)
        if not isinstance(site, dict) or site.get("isNSFW", False) is not False:
            raise SourceError(f"Sherlock {platform} tanımı güvenli biçimde seçilemedi.")
        for field in _DATABASE_FIELDS:
            value = site.get(field)
            if value is None:
                continue
            if not isinstance(value, str):
                raise SourceError(f"Sherlock {platform} adresi beklenen yapıda değil.")
            candidate = value.replace("{}", "xti-preview")
            if not _allowed_host(platform, candidate):
                raise SourceError(f"Sherlock {platform} adresi izinli platform dışında.")
        scoped[platform] = site
    target.write_text(
        json.dumps(scoped, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    target.chmod(0o600)


class SherlockUsernameSource:
    source_name = SOURCE_NAME
    source_version = SOURCE_VERSION
    integration_profile = INTEGRATION_PROFILE

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        python_locator: Callable[[], str | None] | None = None,
        version_locator: Callable[[], str | None] | None = None,
        database_locator: Callable[[], Path | None] | None = None,
        database_sha256: str = REVIEWED_DATABASE_SHA256,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._runner = runner or subprocess.run
        self._python_locator = python_locator or self._locate_python
        self._version_locator = version_locator or self._installed_version
        self._database_locator = database_locator or self._locate_database
        self._database_sha256 = database_sha256
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _locate_python() -> str | None:
        executable = Path(sys.executable)
        return str(executable) if executable.is_file() and os.access(executable, os.X_OK) else None

    @staticmethod
    def _installed_version() -> str | None:
        try:
            return version("sherlock-project")
        except PackageNotFoundError:
            return None

    @staticmethod
    def _locate_database() -> Path | None:
        try:
            database = files("sherlock_project").joinpath("resources", "data.json")
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
            raise SourceError("Sherlock süre sınırında tamamlanamadı.") from error
        except OSError as error:
            raise SourceError("Sherlock çalıştırılamadı; sonuç üretilmedi.") from error
        if (
            len(result.stdout.encode("utf-8", errors="replace")) > MAX_PROCESS_OUTPUT
            or len(result.stderr.encode("utf-8", errors="replace")) > MAX_PROCESS_OUTPUT
        ):
            raise SourceError("Sherlock işlem çıktısı güvenli boyut sınırını aştı.")
        return result

    def preview(
        self,
        username: str,
        *,
        platforms: tuple[str, ...],
        request_timeout: int,
    ) -> BrandUsernamePreview:
        python = self._python_locator()
        installed_version = self._version_locator()
        if not python or installed_version is None:
            raise SourceError(
                "Sherlock kurulu değil. Bir kez ./scripts/setup-brand çalıştır."
            )
        if installed_version != SOURCE_VERSION:
            raise SourceError(
                f"Sherlock {SOURCE_VERSION} gerekiyor; farklı sürüm çalıştırılmadı."
            )
        database = self._database_locator()
        if database is None:
            raise SourceError("Sherlock site veritabanı bulunamadı; kurulum eksik.")
        with tempfile.TemporaryDirectory(prefix="xti-sherlock-") as temporary:
            directory = Path(temporary)
            scoped_database = directory / "scoped-sites.json"
            report = directory / "results.ndjson"
            _write_scoped_database(
                database,
                scoped_database,
                platforms=platforms,
                expected_sha256=self._database_sha256,
            )
            command = [
                python,
                "-m", "xti.adapters.sherlock_username_worker",
                "--username", username,
                "--timeout", str(request_timeout),
                "--database", str(scoped_database),
                "--report", str(report),
            ]
            process_timeout = min(
                100,
                request_timeout * math.ceil(len(platforms) / 20) + 25,
            )
            result = self._run(command, cwd=temporary, timeout=process_timeout)
            if result.returncode != 0:
                raise SourceError("Sherlock taraması tamamlanamadı; sonuç üretilmedi.")
            try:
                metadata = report.lstat()
            except FileNotFoundError as error:
                raise SourceError("Sherlock sonuç dosyası üretmedi.") from error
            if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise SourceError("Sherlock güvenli bir sonuç dosyası üretmedi.")
            with report.open("rb") as stream:
                payload = stream.read(MAX_REPORT_BYTES + 1)
            matches = parse_sherlock_ndjson(
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
                "Yalnız elle incelenmiş seçili herkese açık profil "
                "kontrolleri çalıştırıldı.",
                "Raporlanmayan platform; hesap yok, geçersiz ad, kaynak engeli veya "
                "kontrol hatası anlamlarından hangisi olduğunu tek başına göstermez.",
                "Bulunan aynı kullanıcı adı, hesabın aynı kişi/marka veya taklit "
                "olduğunu kanıtlamaz; insan incelemesi gerekir.",
                "Sonuç yazılmadı; Sherlock CLI, canlı katalog/exclusion, sürüm "
                "kontrolü, proxy, toplu kullanıcı adı ve geniş site taraması kullanılmadı.",
            ),
        )
