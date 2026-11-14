"""Bounded P0 archive discovery through a pinned theHarvester checkout.

Only Common Crawl and Wayback Archive are enabled.  The subprocess receives a
temporary HOME and data directory, so theHarvester cannot reuse or modify the
operator's own configuration and evidence store.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from uuid import UUID

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument
from xti.ports.discovery import SourceError


PROVIDER = "theharvester"
SOURCE_NAME = "theHarvester P0 arşivleri"
REVIEWED_UPSTREAM_COMMIT = "6790b147f52309e4eee22ed941db1d285ab2ec23"
INTEGRATION_PROFILE = f"theharvester-{REVIEWED_UPSTREAM_COMMIT[:12]}-p0-archives-v3"
SOURCES = ("commoncrawl", "waybackarchive")
MAX_RESULT_LIMIT = 500
DEFAULT_RESULT_LIMIT = 250
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_PROCESS_OUTPUT = 1024 * 1024
PROCESS_TIMEOUT_SECONDS = 270
_SUMMARY_FIELDS = frozenset({
    "action_executions", "artifacts", "completed_at", "counts",
    "evidence_status", "result_count", "run_id", "source_executions",
    "started_at", "target", "type",
})
_EXECUTION_FIELDS = frozenset({
    "source", "status", "duration_ms", "result_count", "error_type",
    "stop_reason",
})
_EXECUTION_STATUSES = frozenset({
    "completed", "partial", "failed", "rate-limited", "skipped",
})


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _safe_text(value: object, *, maximum: int = 1000) -> str:
    if (
        not isinstance(value, str) or not 1 <= len(value) <= maximum
        or not value.isprintable()
    ):
        raise SourceError("theHarvester beklenmeyen kanıt metni üretti.")
    return value


def _utc_timestamp(value: object) -> str:
    text = _safe_text(value, maximum=64)
    if not text.endswith("Z"):
        raise SourceError("theHarvester sonucu UTC zaman taşımıyor.")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except (ValueError, OverflowError) as error:
        raise SourceError("theHarvester geçersiz çalışma zamanı üretti.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SourceError("theHarvester geçersiz çalışma zamanı üretti.")
    return parsed.astimezone(timezone.utc).isoformat()


def _execution(item: object, *, limit: int) -> tuple[str, str, int, str | None]:
    if not isinstance(item, dict) or frozenset(item) != _EXECUTION_FIELDS:
        raise SourceError("theHarvester kaynak özeti beklenen yapıda değil.")
    source = _safe_text(item["source"], maximum=64)
    status = _safe_text(item["status"], maximum=32)
    duration = item["duration_ms"]
    count = item["result_count"]
    error_type = item["error_type"]
    stop_reason = item["stop_reason"]
    if (
        source not in SOURCES or status not in _EXECUTION_STATUSES
        or type(duration) not in (int, float) or not math.isfinite(duration)
        or duration < 0 or type(count) is not int or not 0 <= count <= limit
        or (error_type is not None and not isinstance(error_type, str))
        or (stop_reason is not None and not isinstance(stop_reason, str))
    ):
        raise SourceError("theHarvester kaynak özeti kendi içinde tutarsız.")
    if error_type is not None:
        _safe_text(error_type, maximum=200)
    if stop_reason is not None:
        _safe_text(stop_reason, maximum=200)
    return source, status, count, stop_reason


def parse_theharvester_jsonl(
    payload: bytes, *, domain: str, limit: int,
) -> SourceBatch:
    """Validate a complete one-run JSONL report before exposing any hostname."""
    if len(payload) > MAX_REPORT_BYTES:
        raise SourceError("theHarvester sonuç dosyası 2 MiB sınırını aştı.")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceError("theHarvester sonucu UTF-8 değil.") from error
    records: list[dict] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            raise SourceError("theHarvester sonuç satırı güvenli sınırı aştı.")
        try:
            item = json.loads(line, object_pairs_hook=_object)
        except (ValueError, json.JSONDecodeError, RecursionError) as error:
            raise SourceError("theHarvester geçerli JSONL üretmedi.") from error
        if not isinstance(item, dict):
            raise SourceError("theHarvester JSONL kaydı nesne değil.")
        records.append(item)
    if not records:
        raise SourceError("theHarvester boş sonuç dosyası üretti.")

    summary = records[0]
    if frozenset(summary) != _SUMMARY_FIELDS or summary.get("type") != "summary":
        raise SourceError("theHarvester çalışma özeti beklenen yapıda değil.")
    if summary["target"] != domain:
        raise SourceError("theHarvester sonucu istenen domainle uyuşmuyor.")
    try:
        if str(UUID(_safe_text(summary["run_id"], maximum=36))) != summary["run_id"]:
            raise ValueError("non-canonical UUID")
    except ValueError as error:
        raise SourceError("theHarvester geçersiz çalışma kimliği üretti.") from error
    started_at = _utc_timestamp(summary["started_at"])
    completed_at = _utc_timestamp(summary["completed_at"])
    if datetime.fromisoformat(completed_at) < datetime.fromisoformat(started_at):
        raise SourceError("theHarvester çalışma zamanı geriye gidiyor.")
    if summary["action_executions"] != [] or summary["artifacts"] != []:
        raise SourceError("theHarvester izin verilmeyen aktif işlem kanıtı üretti.")

    raw_executions = summary["source_executions"]
    if not isinstance(raw_executions, list) or len(raw_executions) != len(SOURCES):
        raise SourceError("theHarvester seçili iki arşiv kaynağını ayrı raporlamadı.")
    executions = tuple(_execution(item, limit=limit) for item in raw_executions)
    if tuple(item[0] for item in executions) != SOURCES:
        raise SourceError("theHarvester kaynak sırası veya kimliği değişti.")

    evidence_status = summary["evidence_status"]
    statuses = tuple(item[1] for item in executions)
    expected_status = (
        "failed" if all(status in {"failed", "rate-limited", "skipped"} for status in statuses)
        else "partial" if any(status != "completed" for status in statuses)
        else "complete"
    )
    if evidence_status != expected_status:
        raise SourceError("theHarvester genel durumuyla kaynak durumları uyuşmuyor.")

    findings = records[1:]
    if len(findings) > len(SOURCES) * limit:
        raise SourceError("theHarvester sonuç sayısı güvenli sınırı aştı.")
    observations: dict[str, int] = {source: 0 for source in SOURCES}
    documents: dict[tuple[str, str], ImportDocument] = {}
    seen_domains: set[str] = set()
    for item in findings:
        if frozenset(item) != {"type", "value", "sources"} or item.get("type") != "hostname":
            raise SourceError("theHarvester yalnız izinli hostname kanıtı üretmedi.")
        raw_domain = _safe_text(item["value"], maximum=253)
        try:
            normalized = normalize_domain(raw_domain)
        except ValidationError as error:
            raise SourceError("theHarvester geçersiz hostname kanıtı üretti.") from error
        if normalized != raw_domain or not normalized.endswith("." + domain):
            raise SourceError("theHarvester kayıtlı kökün dışında hostname üretti.")
        raw_sources = item["sources"]
        if (
            not isinstance(raw_sources, list) or not raw_sources
            or any(not isinstance(source, str) for source in raw_sources)
            or raw_sources != sorted(set(raw_sources))
            or any(source not in SOURCES for source in raw_sources)
        ):
            raise SourceError("theHarvester hostname kaynak bağı geçersiz.")
        if normalized in seen_domains:
            raise SourceError("theHarvester yinelenen hostname kaydı üretti.")
        seen_domains.add(normalized)
        for source in raw_sources:
            observations[source] += 1
            # The saved observation includes this normalized completion time.
            # A later collection is new evidence; replaying the same observation
            # keeps its identity and remains idempotent.
            canonical = json.dumps(
                {
                    "provider": PROVIDER, "profile": INTEGRATION_PROFILE,
                    "source": source, "hostname": normalized,
                    "completed_at": completed_at,
                },
                ensure_ascii=True, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")
            digest = hashlib.sha256(canonical).hexdigest()
            documents[(normalized, source)] = ImportDocument(
                source_name=f"theHarvester:{source}@{REVIEWED_UPSTREAM_COMMIT}",
                sha256=digest,
                records=(DomainInput(normalized, raw_domain, 1, completed_at),),
            )

    if any(count != observations[source] for source, _status, count, _reason in executions):
        raise SourceError("theHarvester kaynak sayaçları hostname kanıtıyla uyuşmuyor.")
    result_count = summary["result_count"]
    counts = summary["counts"]
    if (
        type(result_count) is not int or result_count != len(findings)
        or not isinstance(counts, dict)
        or counts != ({"hostname": len(findings)} if findings else {})
    ):
        raise SourceError("theHarvester sonuç sayaçları kendi içinde tutarsız.")
    if evidence_status == "failed":
        details = "; ".join(
            f"{source}: {status}, neden: {reason or 'bildirilmedi'}"
            for source, status, _count, reason in executions
        )
        raise SourceError(
            f"theHarvester iki arşiv kaynağını da tamamlayamadı. {details}."
        )

    warnings = tuple(
        f"{source} kaynağı {status} durumunda tamamlandı"
        + (f" ({reason})" if reason else ".")
        for source, status, _count, reason in executions if status != "completed"
    )
    return SourceBatch(
        documents=tuple(documents[key] for key in sorted(documents)),
        skipped_names=0,
        record_count=len(findings),
        warnings=warnings,
        coverage_notes=(
            f"theHarvester commit {REVIEWED_UPSTREAM_COMMIT}",
            f"XTI bağlantı profili: {INTEGRATION_PROFILE}",
            "Common Crawl: katalogdaki en yeni bitiş tarihinden geriye 365 günlük indeksler.",
            "Yalnız P0 commoncrawl ve waybackarchive; hedefe doğrudan bağlantı yok.",
        ),
    )


class TheHarvesterArchiveSource:
    """Run the pinned tool with two fixed P0 archive providers only."""

    provider = PROVIDER
    source_name = SOURCE_NAME
    integration_profile = INTEGRATION_PROFILE

    def __init__(
        self, *, runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        executable_locator: Callable[[], Path | None] | None = None,
        checkout_locator: Callable[[], Path | None] | None = None,
        result_limit: int = DEFAULT_RESULT_LIMIT,
    ) -> None:
        if type(result_limit) is not int or not 1 <= result_limit <= MAX_RESULT_LIMIT:
            raise ValueError("theHarvester sonuç sınırı 1–500 arasında olmalı.")
        self._runner = runner or subprocess.run
        self._executable_locator = executable_locator or self._locate_executable
        self._checkout_locator = checkout_locator or self._locate_checkout
        self.result_limit = result_limit

    @staticmethod
    def _project_root() -> Path:
        return Path(__file__).resolve().parents[3]

    @classmethod
    def _locate_checkout(cls) -> Path | None:
        path = cls._project_root() / ".tools" / "theharvester"
        return path if path.is_dir() else None

    @classmethod
    def _locate_executable(cls) -> Path | None:
        path = cls._project_root() / ".tools" / "theharvester" / ".venv" / "bin" / "theHarvester"
        return path if path.is_file() and os.access(path, os.X_OK) else None

    @staticmethod
    def _verify_checkout(checkout: Path, executable: Path) -> None:
        try:
            head = checkout.joinpath(".git", "HEAD")
            metadata = head.lstat()
            executable_metadata = executable.lstat()
            commit = head.read_text(encoding="ascii").strip()
        except (OSError, UnicodeError) as error:
            raise SourceError("theHarvester kurulumu doğrulanamadı.") from error
        if (
            not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
            or commit != REVIEWED_UPSTREAM_COMMIT
            or not stat.S_ISREG(executable_metadata.st_mode)
            or stat.S_ISLNK(executable_metadata.st_mode)
            or not executable.resolve().is_relative_to(checkout.resolve())
        ):
            raise SourceError("theHarvester kurulumu incelenen commit ile uyuşmuyor.")
        interpreter = executable.with_name("python")
        if not interpreter.is_file() or not os.access(interpreter, os.X_OK):
            raise SourceError("theHarvester ayrı Python ortamı eksik; ./scripts/setup-harvester çalıştır.")

    @staticmethod
    def _safe_environment(directory: str) -> dict[str, str]:
        environment = dict(os.environ)
        for name in (
            "ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "OPENAI_API_KEY",
            "all_proxy", "https_proxy", "http_proxy",
            "PYTHONHOME", "PYTHONSTARTUP",
        ):
            environment.pop(name, None)
        environment.update({
            "HOME": directory,
            "XDG_DATA_HOME": str(Path(directory) / "data"),
            "THEHARVESTER_RUN_DB": str(Path(directory) / "data" / "run.sqlite"),
            "NO_PROXY": "*", "no_proxy": "*", "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            "PYTHONNOUSERSITE": "1",
        })
        return environment

    @staticmethod
    def _domain(pattern: str) -> str:
        if not isinstance(pattern, str) or not pattern.startswith("%."):
            raise ValidationError("theHarvester için kayıtlı bir kök domain gerekli.")
        return normalize_domain(pattern[2:])

    def search_url(self, pattern: str) -> str:
        self._domain(pattern)
        return (
            "https://github.com/laramies/theHarvester/commit/"
            f"{REVIEWED_UPSTREAM_COMMIT}#commoncrawl-waybackarchive"
        )

    def search(self, pattern: str) -> SourceBatch:
        domain = self._domain(pattern)
        checkout = self._checkout_locator()
        executable = self._executable_locator()
        if checkout is None or executable is None:
            raise SourceError(
                "theHarvester kurulu değil. Bir kez ./scripts/setup-harvester çalıştır."
            )
        self._verify_checkout(checkout, executable)
        with tempfile.TemporaryDirectory(prefix="xti-theharvester-") as directory:
            work = Path(directory)
            report = work / "xti-report.jsonl"
            worker = Path(__file__).with_name("theharvester_archive_worker.py")
            command = [
                str(executable.with_name("python")), str(worker),
                "--domain", domain, "--limit", str(self.result_limit),
                "--report", str(report),
            ]
            try:
                result = self._runner(
                    command, cwd=directory, env=self._safe_environment(directory),
                    text=True, capture_output=True, check=False,
                    timeout=PROCESS_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as error:
                raise SourceError(
                    f"theHarvester {PROCESS_TIMEOUT_SECONDS} saniyelik sürede tamamlanamadı."
                ) from error
            except OSError as error:
                raise SourceError(
                    "theHarvester çalıştırılamadı; sonuç üretilmedi."
                ) from error
            if (
                len(result.stdout.encode("utf-8", errors="replace")) > MAX_PROCESS_OUTPUT
                or len(result.stderr.encode("utf-8", errors="replace")) > MAX_PROCESS_OUTPUT
            ):
                raise SourceError("theHarvester işlem çıktısı güvenli sınırı aştı.")
            if result.returncode != 0:
                raise SourceError("theHarvester kaynak çalışmasını tamamlayamadı.")
            path = report
            try:
                metadata = path.lstat()
                if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                    raise OSError("unsafe report")
                with path.open("rb") as stream:
                    payload = stream.read(MAX_REPORT_BYTES + 1)
            except OSError as error:
                raise SourceError("theHarvester doğrulanabilir JSONL sonucu üretmedi.") from error
            return parse_theharvester_jsonl(
                payload, domain=domain, limit=self.result_limit,
            )
