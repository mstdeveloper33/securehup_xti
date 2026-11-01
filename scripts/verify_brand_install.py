"""Fail-closed verification for the optional Maigret/Sherlock toolchain."""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import PackageNotFoundError, distribution
from importlib.resources import files
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

from xti.adapters.maigret_username import (
    REVIEWED_DATABASE_SHA256 as MAIGRET_DATABASE_SHA256,
    REVIEWED_UPSTREAM_COMMIT as MAIGRET_COMMIT,
    SOURCE_VERSION as MAIGRET_VERSION,
    _write_scoped_database as write_maigret_database,
)
from xti.adapters.sherlock_username import (
    REVIEWED_DATABASE_SHA256 as SHERLOCK_DATABASE_SHA256,
    REVIEWED_UPSTREAM_COMMIT as SHERLOCK_COMMIT,
    SOURCE_VERSION as SHERLOCK_VERSION,
    _write_scoped_database as write_sherlock_database,
)
from xti.application.brand_username import (
    EXTENDED_PLATFORMS,
    SHERLOCK_EXTENDED_PLATFORMS,
)


TOOLS = (
    {
        "name": "Maigret",
        "distribution": "maigret",
        "version": MAIGRET_VERSION,
        "repository": "https://github.com/soxoj/maigret.git",
        "commit": MAIGRET_COMMIT,
        "package": "maigret",
        "catalog_size": 3_329_634,
        "catalog_sha256": MAIGRET_DATABASE_SHA256,
    },
    {
        "name": "Sherlock",
        "distribution": "sherlock-project",
        "version": SHERLOCK_VERSION,
        "repository": "https://github.com/sherlock-project/sherlock.git",
        "commit": SHERLOCK_COMMIT,
        "package": "sherlock_project",
        "catalog_size": 104_039,
        "catalog_sha256": SHERLOCK_DATABASE_SHA256,
    },
)


class VerificationError(RuntimeError):
    """The installed toolchain differs from the reviewed build contract."""


CONSTRAINTS = Path(__file__).resolve().parents[1] / "constraints" / "brand.txt"


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


def _verify_constraints(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise VerificationError("bağımlılık sürüm kısıtları okunamadı") from error
    seen = set()
    for line in lines:
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        parts = value.split("==")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise VerificationError(f"geçersiz bağımlılık kısıtı: {value}")
        name, expected = parts
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
        direct_url.get("url") != tool["repository"]
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


def verify(prefix: Path) -> None:
    if sys.version_info < (3, 11):
        raise VerificationError("Python 3.11 veya daha yeni bir sürüm gerekiyor")
    if Path(sys.prefix).resolve() != prefix.resolve():
        raise VerificationError("doğrulayıcı hedef sanal ortamdan çalıştırılmadı")
    _verify_constraints(CONSTRAINTS)
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
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise VerificationError("Maigret sürüm kontrolü çalıştırılamadı") from error
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    if result.returncode != 0 or first_line != f"maigret {MAIGRET_VERSION}":
        raise VerificationError("Maigret çalıştırıcı sürümü uyuşmuyor")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        verify(args.prefix)
    except VerificationError as error:
        print(f"Marka araçları doğrulanamadı: {error}", file=sys.stderr)
        return 1
    print(
        f"Marka araçları doğrulandı: Maigret {MAIGRET_VERSION}, "
        f"Sherlock {SHERLOCK_VERSION}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
