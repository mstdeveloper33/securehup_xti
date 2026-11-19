"""Fail-closed verification for the optional Maigret/Sherlock toolchain."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib
from importlib.metadata import PackageNotFoundError, distribution
from importlib.resources import files
from io import BytesIO
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

from xti.adapters.maigret_username import (
    _write_scoped_database as write_maigret_database,
)
from xti.adapters.sherlock_username import (
    _write_scoped_database as write_sherlock_database,
)
from xti.application.brand_username import (
    EXTENDED_PLATFORMS,
    SHERLOCK_EXTENDED_PLATFORMS,
)
from xti.domain.component_pins import MAIGRET_PIN, SHERLOCK_PIN
from xti.adapters.tool_installation import (
    BRAND_LOCK_NAME, ToolInstallationError,
    brand_installation_lock, brand_installation_pending,
)


MAIGRET_DATABASE_SHA256 = MAIGRET_PIN.catalog_sha256
MAIGRET_COMMIT = MAIGRET_PIN.commit
MAIGRET_VERSION = MAIGRET_PIN.version
SHERLOCK_DATABASE_SHA256 = SHERLOCK_PIN.catalog_sha256
SHERLOCK_COMMIT = SHERLOCK_PIN.commit
SHERLOCK_VERSION = SHERLOCK_PIN.version

TOOLS = tuple(
    {
        "name": pin.label,
        "distribution": pin.distribution,
        "version": pin.version,
        "repository": pin.repository,
        "commit": pin.commit,
        "package": pin.package,
        "catalog_size": pin.catalog_size,
        "catalog_sha256": pin.catalog_sha256,
    } for pin in (MAIGRET_PIN, SHERLOCK_PIN)
)

NEWS_PACKAGES = (("feedparser", "6.0.14", "feedparser"),
                 ("feedparser-sgmllib", "2.1.0", "feedparser_sgmllib"))


class VerificationError(RuntimeError):
    """The installed toolchain differs from the reviewed build contract."""


CONSTRAINTS = Path(__file__).resolve().parents[1] / "constraints" / "brand.txt"
PROJECT = Path(__file__).resolve().parents[1]


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError(f"yinelenen JSON alanı: {key}")
        result[key] = value
    return result


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _catalog_sha256(path: Path, expected_size: int) -> str:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise VerificationError(f"site kataloğu bulunamadı: {path}") from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_size != expected_size
    ):
        raise VerificationError(f"site kataloğu boyutu/türü uyuşmuyor: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(128 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


_CONSTRAINT = re.compile(
    r"(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"==(?P<version>[0-9]+(?:\.[0-9]+)*(?:\.post[0-9]+)?)"
    r"(?:\s*;\s*python_version\s*(?P<operator><|>=)\s*"
    r"(?P<quote>['\"])(?P<major>[0-9]{1,2})\.(?P<minor>[0-9]{1,2})(?P=quote))?"
)


def _constraint_pin(value: str, python_version: tuple[int, int]) -> tuple[str, str] | None:
    """Only our reviewed exact pins and two numeric Python marker operators.

    This is deliberately not a general PEP 508 evaluator. Unsupported syntax,
    including in an inactive branch, must be reviewed instead of skipped.
    """
    match = _CONSTRAINT.fullmatch(value)
    if match is None:
        raise VerificationError(f"geçersiz bağımlılık kısıtı: {value}")
    operator = match["operator"]
    if operator:
        boundary = (int(match["major"]), int(match["minor"]))
        active = python_version < boundary if operator == "<" else python_version >= boundary
        if not active:
            return None
    return match["name"], match["version"]


def _verify_constraints(path: Path, *, python_version: tuple[int, int] | None = None) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise VerificationError("bağımlılık sürüm kısıtları okunamadı") from error
    seen = set()
    current_python = tuple(sys.version_info[:2]) if python_version is None else python_version
    for line in lines:
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        pin = _constraint_pin(value, current_python)
        if pin is None:
            continue
        name, expected = pin
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key in seen:
            raise VerificationError(f"yinelenen bağımlılık kısıtı: {name}")
        seen.add(key)
        try:
            actual = distribution(name).version
        except PackageNotFoundError:
            # Constraints do not force platform-conditional dependencies.
            continue
        if actual != expected:
            raise VerificationError(
                f"{name} sürümü uyuşmuyor: {actual} != {expected}"
            )


def _verify_distribution(tool: dict[str, object], prefix: Path) -> None:
    name = str(tool["name"])
    try:
        installed = distribution(str(tool["distribution"]))
    except PackageNotFoundError as error:
        raise VerificationError(f"{name} paketi kurulu değil") from error
    if installed.version != tool["version"]:
        raise VerificationError(
            f"{name} sürümü uyuşmuyor: {installed.version} != {tool['version']}"
        )
    location = Path(installed.locate_file(""))
    if not _inside(location, prefix):
        raise VerificationError(f"{name} proje sanal ortamının dışında bulundu")

    direct_url_text = installed.read_text("direct_url.json")
    if direct_url_text is None:
        raise VerificationError(f"{name} Git kaynak kaydı bulunamadı")
    try:
        direct_url = json.loads(direct_url_text, object_pairs_hook=_json_object)
    except (ValueError, json.JSONDecodeError) as error:
        raise VerificationError(f"{name} Git kaynak kaydı bozuk") from error
    vcs = direct_url.get("vcs_info") if isinstance(direct_url, dict) else None
    if (
        not isinstance(direct_url, dict)
        or direct_url.get("url") != tool["repository"]
        or not isinstance(vcs, dict)
        or vcs.get("vcs") != "git"
        or vcs.get("commit_id") != tool["commit"]
        or vcs.get("requested_revision") != tool["commit"]
    ):
        raise VerificationError(f"{name} incelenen Git commit'inden kurulmamış")

    catalog = Path(str(files(str(tool["package"])).joinpath("resources", "data.json")))
    if not _inside(catalog, prefix):
        raise VerificationError(f"{name} kataloğu proje sanal ortamının dışında")
    digest = _catalog_sha256(catalog, int(tool["catalog_size"]))
    if digest != tool["catalog_sha256"]:
        raise VerificationError(f"{name} site kataloğu özeti uyuşmuyor")


def _verify_news_runtime(prefix: Path) -> None:
    """Require the optional reader in this environment, with a local format smoke test."""
    for name, expected, module_name in NEWS_PACKAGES:
        try:
            installed = distribution(name)
        except PackageNotFoundError as error:
            raise VerificationError(f"{name} paketi eksik; ./scripts/setup-brand çalıştır") from error
        if installed.version != expected:
            raise VerificationError(f"{name} sürümü uyuşmuyor: {installed.version} != {expected}")
        if not _inside(Path(installed.locate_file("")), prefix):
            raise VerificationError(f"{name} proje sanal ortamının dışında bulundu")
        try:
            module = importlib.import_module(module_name)
        except ImportError as error:
            raise VerificationError(f"{name} modülü yüklenemedi") from error
        filename = getattr(module, "__file__", None)
        if not isinstance(filename, str) or not _inside(Path(filename), prefix):
            raise VerificationError(f"{name} modülü proje sanal ortamının dışında bulundu")
    parser = importlib.import_module("feedparser")
    for content in (
        b'<rss version="2.0"><channel><title>XTI test</title><link>https://example.com/</link>'
        b'<description>Local fixture</description><item><guid>urn:xti:test</guid>'
        b'<title>Local test</title><link>https://example.com/item</link></item></channel></rss>',
        b'<feed xmlns="http://www.w3.org/2005/Atom"><id>urn:xti:feed</id><title>XTI test</title>'
        b'<updated>2026-01-01T00:00:00Z</updated><entry><id>urn:xti:test</id><title>Local test</title>'
        b'<updated>2026-01-01T00:00:00Z</updated><link href="https://example.com/item"/></entry></feed>',
    ):
        try:
            result = parser.parse(BytesIO(content))
            valid = (not result.bozo and len(result.entries) == 1
                     and result.entries[0].id == "urn:xti:test"
                     and result.entries[0].link == "https://example.com/item")
        except (AttributeError, TypeError, ValueError, IndexError) as error:
            raise VerificationError("RSS/Atom okuyucusu yerel örnekleri okuyamadı") from error
        if not valid:
            raise VerificationError("RSS/Atom okuyucusu yerel örneklerle uyuşmuyor")


def verify(prefix: Path, *, installation_lock_fd: int | None = None) -> None:
    if installation_lock_fd is not None:
        _validate_installation_lock(installation_lock_fd)
        _verify_locked(prefix, installation_lock_fd)
        return
    with brand_installation_lock(PROJECT, exclusive=False) as descriptor:
        if brand_installation_pending(PROJECT):
            raise VerificationError("Marka ortamı kurtarma bekliyor; ./scripts/setup-brand --recover çalıştır.")
        _verify_locked(prefix, descriptor)


def _validate_installation_lock(descriptor: int) -> None:
    if type(descriptor) is not int or not 0 <= descriptor <= 2**31 - 1:
        raise VerificationError("Kurulum kilidi descriptor'ı doğrulanamadı.")
    try:
        metadata = os.fstat(descriptor)
        expected = (PROJECT / BRAND_LOCK_NAME).lstat()
        if (
            not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
            or not stat.S_ISREG(expected.st_mode) or expected.st_nlink != 1
            or (metadata.st_dev, metadata.st_ino) != (expected.st_dev, expected.st_ino)
        ):
            raise VerificationError("Kurulum kilidi descriptor'ı doğrulanamadı.")
        # Same open description as the installer; never acquire another SH
        # descriptor or downgrade/unlock the installer's exclusive lock.
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        raise VerificationError("Kurulum kilidi descriptor'ı doğrulanamadı.") from error


def _verify_pdf_runtime(prefix: Path) -> None:
    try:
        installed = distribution('pypdf')
        if installed.version != '7.1.1' or not _inside(Path(installed.locate_file('')), prefix):
            raise VerificationError('PDF paketi sürümü veya kurulum konumu uyuşmuyor.')
        module = importlib.import_module('pypdf')
        if not _inside(Path(module.__file__), prefix):
            raise VerificationError('PDF modülü proje sanal ortamının dışında.')
        stream = BytesIO()
        writer = module.PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(stream); stream.seek(0)
        if len(module.PdfReader(stream, strict=True).pages) != 1:
            raise VerificationError('PDF okuyucusu yerel dosyayı doğrulayamadı.')
    except (PackageNotFoundError, ImportError, AttributeError, TypeError, ValueError) as error:
        raise VerificationError('PDF okuyucusu eksik veya bozuk; ./scripts/setup-brand çalıştır.') from error


def _verify_locked(prefix: Path, descriptor: int) -> None:
    if sys.version_info < (3, 11):
        raise VerificationError("Python 3.11 veya daha yeni bir sürüm gerekiyor")
    if Path(sys.prefix).resolve() != prefix.resolve():
        raise VerificationError("doğrulayıcı hedef sanal ortamdan çalıştırılmadı")
    _verify_constraints(CONSTRAINTS)
    _verify_news_runtime(prefix)
    _verify_pdf_runtime(prefix)
    for tool in TOOLS:
        _verify_distribution(tool, prefix)

    with tempfile.TemporaryDirectory(prefix="xti-brand-scope-") as directory:
        root = Path(directory)
        write_maigret_database(
            Path(str(files("maigret").joinpath("resources", "data.json"))),
            root / "maigret.json",
            platforms=EXTENDED_PLATFORMS,
            expected_sha256=MAIGRET_DATABASE_SHA256,
        )
        write_sherlock_database(
            Path(str(files("sherlock_project").joinpath("resources", "data.json"))),
            root / "sherlock.json",
            platforms=SHERLOCK_EXTENDED_PLATFORMS,
            expected_sha256=SHERLOCK_DATABASE_SHA256,
        )

    executable = prefix / "bin" / "maigret"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise VerificationError("Maigret çalıştırıcısı bulunamadı")
    with tempfile.TemporaryDirectory(prefix="xti-brand-verify-") as home:
        environment = dict(os.environ)
        for key in (
            "ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "OPENAI_API_KEY",
            "all_proxy", "https_proxy", "http_proxy",
        ):
            environment.pop(key, None)
        environment.update({"HOME": home, "NO_PROXY": "*", "no_proxy": "*"})
        try:
            result = subprocess.run(
                [str(executable), "--version"],
                cwd=home,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
                pass_fds=(descriptor,),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise VerificationError("Maigret sürüm kontrolü çalıştırılamadı") from error
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    if result.returncode != 0 or first_line != f"maigret {MAIGRET_VERSION}":
        raise VerificationError("Maigret çalıştırıcı sürümü uyuşmuyor")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--installation-lock-fd", type=int)
    args = parser.parse_args(argv)
    try:
        if args.installation_lock_fd is None:
            verify(args.prefix)
        else:
            verify(args.prefix, installation_lock_fd=args.installation_lock_fd)
    except (VerificationError, ToolInstallationError) as error:
        print(f"Marka araçları doğrulanamadı: {error}", file=sys.stderr)
        return 1
    print(
        f"Marka araçları doğrulandı: Maigret {MAIGRET_VERSION}, "
        f"Sherlock {SHERLOCK_VERSION}; RSS/Atom feedparser {NEWS_PACKAGES[0][1]}; PDF pypdf 7.1.1."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
