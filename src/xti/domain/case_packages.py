"""Pure rendering rules for self-verifying case evidence packages."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from html import escape
import hashlib
from io import StringIO
import json

from xti.domain.assets import ValidationError
from xti.domain.cases import normalize_case_id


PACKAGE_VERSION = 1
MAX_PACKAGE_JSON = 32 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class CasePackageArtifact:
    destination: str
    case_id: str
    created_at: str
    case_snapshot_sha256: str
    manifest_sha256: str
    files: tuple[str, ...]
    pdf_included: bool


def canonical_bytes(value: object) -> tuple[bytes, str]:
    try:
        payload = (json.dumps(
            value, ensure_ascii=True, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ) + "\n").encode("ascii")
    except (TypeError, ValueError) as error:
        raise ValidationError("Vaka paketi güvenli JSON biçimine dönüştürülemedi.") from error
    if not 3 <= len(payload) <= MAX_PACKAGE_JSON:
        raise ValidationError("Vaka paketi 32 MiB güvenli JSON sınırını aşıyor.")
    return payload, hashlib.sha256(payload).hexdigest()


def executive_html(snapshot: dict, *, created_at: str, snapshot_sha256: str) -> bytes:
    case = snapshot["case"]
    active = [item for item in snapshot["evidence"] if item["active"]]
    type_counts: dict[str, int] = {}
    for item in active:
        type_counts[item["evidence_type"]] = type_counts.get(item["evidence_type"], 0) + 1
    rows = "".join(
        "<tr><td>" + escape(kind) + "</td><td>" + str(count) + "</td></tr>"
        for kind, count in sorted(type_counts.items())
    ) or "<tr><td colspan='2'>Etkin kanıt yok</td></tr>"
    open_tasks = sum(item["status"] == "open" for item in snapshot["tasks"])
    limitations = (
        "Kaynakta görülme doğrulanmış saldırı veya ihlal hükmü değildir. "
        "Bu paket oluşturulduğu andaki yerel, donmuş vaka görünümüdür; "
        "takedown veya engelleme işlemini kendiliğinden başlatmaz."
    )
    body = f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><title>XTI vaka özeti</title>
<style>@page{{size:A4;margin:18mm}}body{{font:14px/1.45 system-ui,sans-serif;color:#172033}}
h1{{font-size:25px}}h2{{font-size:17px;margin-top:24px}}table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ccd3df;padding:7px;text-align:left}}.meta{{color:#536078}}
.warning{{border-left:4px solid #cf7a00;padding:10px;background:#fff7e8}}</style></head><body>
<h1>{escape(case['title'])}</h1>
<p class="meta">Vaka: {escape(case['id'])} · Durum: {escape(case['status'])} · Öncelik: {escape(case['priority'])}</p>
<p>{escape(case['summary'])}</p>
<h2>Yönetici görünümü</h2><table><tr><th>Etkin kanıt</th><th>Açık görev</th><th>Zaman çizelgesi</th></tr>
<tr><td>{len(active)}</td><td>{open_tasks}</td><td>{len(snapshot['activities'])}</td></tr></table>
<h2>Kanıt türleri</h2><table><tr><th>Tür</th><th>Adet</th></tr>{rows}</table>
<h2>Bütünlük ve kapsam</h2><p class="meta">Oluşturma: {escape(created_at)}<br>Vaka görünümü SHA-256: {escape(snapshot_sha256)}</p>
<p class="warning">{escape(limitations)}</p></body></html>"""
    payload = body.encode("utf-8")
    if len(payload) > 2 * 1024 * 1024:
        raise ValidationError("Yönetici HTML özeti 2 MiB sınırını aşıyor.")
    return payload


def _csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    # Spreadsheet applications may treat untrusted cells as formulas.
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def evidence_csv(snapshot: dict) -> bytes:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow((
        "evidence_link_id", "active", "evidence_type", "evidence_id",
        "display_value", "source_reference", "snapshot_sha256",
        "added_at", "updated_at", "removed_at",
    ))
    for item in snapshot["evidence"]:
        writer.writerow(tuple(_csv_cell(item.get(name)) for name in (
            "id", "active", "evidence_type", "evidence_id", "display_value",
            "source_reference", "snapshot_sha256", "added_at", "updated_at", "removed_at",
        )))
    payload = stream.getvalue().encode("utf-8")
    if len(payload) > 16 * 1024 * 1024:
        raise ValidationError("Vaka kanıt CSV dosyası 16 MiB sınırını aşıyor.")
    return payload


def package_manifest(
    *, case_id: str, created_at: str, case_snapshot_sha256: str,
    files: list[dict], pdf_included: bool,
) -> dict:
    return {
        "kind": "xti_case_evidence_package",
        "package_version": PACKAGE_VERSION,
        "case_id": normalize_case_id(case_id),
        "created_at": created_at,
        "case_snapshot_sha256": case_snapshot_sha256,
        "pdf_included": pdf_included,
        "files": sorted(files, key=lambda item: item["name"]),
        "limitations": [
            "Paket yerel vaka kaydının oluşturma anındaki görünümüdür.",
            "Kaynak iddiaları doğrulanmış saldırı, ihlal veya zararlılık hükmü değildir.",
            "Paket otomatik takedown, engelleme veya dış teslim yapmaz.",
        ],
    }
