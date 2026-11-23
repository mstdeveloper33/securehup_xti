"""Exclusive, self-verifying filesystem publication for case evidence packages."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from datetime import datetime, timezone

from xti.adapters.case_package_pdf import render_pdf
from xti.domain.assets import ValidationError
from xti.domain.case_packages import (
    CasePackageArtifact, canonical_bytes, evidence_csv, executive_html,
    package_manifest,
)


_MEDIA = {
    "technical.json": "application/json",
    "executive.html": "text/html; charset=utf-8",
    "evidence.csv": "text/csv; charset=utf-8",
    "executive.pdf": "application/pdf",
}
_MAX_FILE_BYTES = {
    "manifest.json": 2 * 1024 * 1024,
    "technical.json": 32 * 1024 * 1024,
    "executive.html": 2 * 1024 * 1024,
    "evidence.csv": 16 * 1024 * 1024,
    "executive.pdf": 8 * 1024 * 1024,
}


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_new(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _read_regular(path: Path, *, maximum: int, label: str) -> bytes:
    """Read one unchanged regular file without following a swapped symlink."""
    descriptor = None
    try:
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or path.is_symlink()
                or not 1 <= before.st_size <= maximum):
            raise ValidationError(f"{label} güvenli bir gerçek dosya değil.")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        if ((opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                or not stat.S_ISREG(opened.st_mode)
                or not 1 <= opened.st_size <= maximum):
            raise ValidationError(f"{label} okunurken değişti; işlem durduruldu.")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            payload = stream.read(maximum + 1)
        if len(payload) != opened.st_size:
            raise ValidationError(f"{label} okunurken değişti; işlem durduruldu.")
        return payload
    except ValidationError:
        raise
    except OSError as error:
        raise ValidationError(f"{label} eksik veya okunamıyor.") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


class AtomicCasePackagePublisher:
    def publish(
        self, snapshot: dict, destination: Path, *,
        created_at: str, include_pdf: bool,
    ) -> CasePackageArtifact:
        destination = destination.expanduser().absolute()
        if os.path.lexists(destination):
            raise ValidationError("Vaka paketi konumu zaten var; farklı bir dizin seçin.")
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.mkdir(destination, 0o700)
        marker = destination / ".incomplete"
        try:
            _write_new(marker, b"XTI package publication in progress\n")
            technical, snapshot_sha = canonical_bytes(snapshot)
            html = executive_html(snapshot, created_at=created_at, snapshot_sha256=snapshot_sha)
            payloads = {
                "technical.json": technical,
                "executive.html": html,
                "evidence.csv": evidence_csv(snapshot),
            }
            if include_pdf:
                payloads["executive.pdf"] = render_pdf(html)
            files = []
            for name, payload in payloads.items():
                _write_new(destination / name, payload)
                files.append({
                    "name": name, "media_type": _MEDIA[name],
                    "byte_count": len(payload), "sha256": _digest(payload),
                })
            manifest = package_manifest(
                case_id=snapshot["case"]["id"], created_at=created_at,
                case_snapshot_sha256=snapshot_sha, files=files,
                pdf_included=include_pdf,
            )
            manifest_bytes, manifest_sha = canonical_bytes(manifest)
            _write_new(destination / "manifest.json", manifest_bytes)
            marker.unlink()
            descriptor = os.open(destination, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return CasePackageArtifact(
                str(destination), snapshot["case"]["id"], created_at,
                snapshot_sha, manifest_sha,
                tuple(sorted((*payloads, "manifest.json"))), include_pdf,
            )
        except BaseException:
            shutil.rmtree(destination, ignore_errors=True)
            raise

    def verify(self, destination: Path) -> CasePackageArtifact:
        destination = destination.expanduser().absolute()
        try:
            info = destination.lstat()
        except OSError as error:
            raise ValidationError("Vaka paketi dizini bulunamadı.") from error
        if not stat.S_ISDIR(info.st_mode) or destination.is_symlink():
            raise ValidationError("Vaka paketi güvenli bir gerçek dizin olmalı.")
        try:
            manifest_bytes = _read_regular(
                destination / "manifest.json", maximum=_MAX_FILE_BYTES["manifest.json"],
                label="Vaka paketi manifesti",
            )
            manifest = json.loads(manifest_bytes)
        except json.JSONDecodeError as error:
            raise ValidationError("Vaka paketi manifesti okunamadı.") from error
        canonical, manifest_sha = canonical_bytes(manifest)
        if canonical != manifest_bytes:
            raise ValidationError("Vaka paketi manifesti kanonik değil.")
        required = {
            "kind", "package_version", "case_id", "created_at",
            "case_snapshot_sha256", "pdf_included", "files", "limitations",
        }
        if (not isinstance(manifest, dict) or set(manifest) != required
                or manifest["kind"] != "xti_case_evidence_package"
                or manifest["package_version"] != 1
                or type(manifest["pdf_included"]) is not bool):
            raise ValidationError("Vaka paketi manifest alanları geçersiz.")
        try:
            created = datetime.fromisoformat(manifest["created_at"])
            if created.tzinfo is None or created.utcoffset() is None:
                raise ValueError("timezone")
            if created.astimezone(timezone.utc).isoformat() != manifest["created_at"]:
                raise ValueError("noncanonical")
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Vaka paketi oluşturma zamanı geçersiz.") from error
        if package_manifest(
            case_id=manifest["case_id"], created_at=manifest["created_at"],
            case_snapshot_sha256=manifest["case_snapshot_sha256"],
            files=manifest["files"], pdf_included=manifest["pdf_included"],
        ) != manifest:
            raise ValidationError("Vaka paketi manifest içeriği geçersiz.")
        expected = {"manifest.json"}
        verified_payloads = {}
        for item in manifest["files"]:
            if (not isinstance(item, dict)
                    or set(item) != {"name", "media_type", "byte_count", "sha256"}
                    or item["name"] not in _MEDIA or item["media_type"] != _MEDIA[item["name"]]
                    or item["name"] in expected or type(item["byte_count"]) is not int
                    or item["byte_count"] < 0):
                raise ValidationError("Vaka paketi dosya manifesti geçersiz.")
            path = destination / item["name"]
            payload = _read_regular(
                path, maximum=_MAX_FILE_BYTES[item["name"]],
                label="Vaka paketi dosyası",
            )
            if len(payload) != item["byte_count"] or _digest(payload) != item["sha256"]:
                raise ValidationError("Vaka paketi dosya bütünlüğü doğrulanamadı.")
            expected.add(item["name"])
            verified_payloads[item["name"]] = payload
        actual = {item.name for item in destination.iterdir()}
        if (not {"technical.json", "executive.html", "evidence.csv", "manifest.json"} <= expected
                or actual != expected
                or ("executive.pdf" in expected) != manifest["pdf_included"]):
            raise ValidationError("Vaka paketi beklenmeyen veya eksik dosya içeriyor.")
        technical = verified_payloads["technical.json"]
        if _digest(technical) != manifest["case_snapshot_sha256"]:
            raise ValidationError("Vaka paketi teknik görünümü manifestle uyuşmuyor.")
        if manifest["pdf_included"] and not verified_payloads["executive.pdf"].startswith(b"%PDF-"):
            raise ValidationError("Vaka paketi PDF dosyası geçersiz.")
        return CasePackageArtifact(
            str(destination), manifest["case_id"], manifest["created_at"],
            manifest["case_snapshot_sha256"], manifest_sha,
            tuple(sorted(expected)), manifest["pdf_included"],
        )
