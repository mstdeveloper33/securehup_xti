"""Bounded offline repetitions over disposable SQLite data, never a live soak.

Run with ./scripts/python scripts/verify_inbox_soak.py --cycles 30.
Only a TemporaryDirectory is used. Socket/DNS entry points are blocked. The
fixture replays the same three candidates from two sources, injects recorded
failures and one controlled post-commit interruption, and reopens repositories
between cycles. Job history intentionally grows; duplicate evidence does not.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile
import time
from unittest.mock import patch
from urllib.parse import urlencode

from xti import __version__
from xti.adapters.public_suffix import PublicSuffixResolver
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.assets import AssetService
from xti.application.discovery import DiscoveryService, build_prefix_query_plan, build_query_plan
from xti.application.findings import FindingService
from xti.application.inbox import InboxService
from xti.application.jobs import JobService
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument
from xti.domain.matching import DomainMatcher
from xti.ports.discovery import SourceError


FIXTURE_DOMAINS = ("example-support.test", "exampel.test", "example.com.other.test")


def require(condition: bool, message: str) -> None:
    """Checks must stay enabled when Python is launched with optimization."""
    if not condition:
        raise AssertionError(message)


class FixtureSource:
    def __init__(self, provider: str, mode: str, counters: Counter) -> None:
        self.provider = provider
        self.mode = mode
        self.counters = counters
        self.documents = tuple(
            ImportDocument(
                f"fixture://inbox-soak/{provider}/{index}",
                hashlib.sha256(f"inbox-soak:{provider}:{domain}".encode()).hexdigest(),
                (DomainInput(domain, domain, 1, "2026-10-29T00:00:00+00:00"),),
            )
            for index, domain in enumerate(FIXTURE_DOMAINS, start=1)
        )

    def search_url(self, pattern: str) -> str:
        return f"fixture://inbox-soak/{self.provider}?" + urlencode({"pattern": pattern})

    def search(self, pattern: str) -> SourceBatch:
        self.counters["fixture_query_calls"] += 1
        if self.mode == "failed" or (self.mode == "partial" and pattern.startswith("%")):
            self.counters["fixture_query_failures"] += 1
            raise SourceError("Ağsız doğrulama: kontrollü kaynak yanıt hatası.")
        return SourceBatch(
            self.documents, 0, len(self.documents),
            coverage_notes=("Sentetik doğrulama kaynağı; internetten alınmış veri değildir.",),
        )


def _service(database: Path, matcher: DomainMatcher, sources: dict[str, FixtureSource]) -> JobService:
    assets = SQLiteAssetRepository(database)
    findings = SQLiteFindingRepository(database)
    discoveries = {
        provider: DiscoveryService(
            assets, findings, matcher, source,
            query_planner=build_query_plan if provider == "crt.sh" else build_prefix_query_plan,
        )
        for provider, source in sources.items()
    }
    return JobService(
        SQLiteJobRepository(database), discoveries["crt.sh"], LocalExecutionLock(database),
        discoveries=discoveries,
    )


def _max_rss() -> dict:
    # ru_maxrss is bytes on macOS and KiB on Linux; avoid guessing elsewhere.
    try:
        import resource
    except ImportError:
        return {"bytes": None, "scope": "unavailable"}
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    factor = 1 if sys.platform == "darwin" else 1024 if sys.platform.startswith("linux") else None
    return {
        "bytes": int(raw * factor) if factor is not None else None,
        "raw": raw,
        "raw_unit": "bytes" if factor == 1 else "KiB" if factor == 1024 else "platform-dependent",
        "scope": "whole_process_peak; includes interpreter and imported modules",
    }


def verify(cycles: int) -> dict:
    if type(cycles) is not int or not 10 <= cycles <= 1000:
        raise ValueError("Tur sayısı 10–1000 arasında olmalı.")
    counters = Counter()

    def deny_network(*arguments, **keywords):
        counters["network_calls_blocked"] += 1
        raise AssertionError("Ağsız doğrulama sırasında beklenmeyen ağ çağrısı.")

    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    resolver = PublicSuffixResolver()
    matcher = DomainMatcher(resolver)
    elapsed_cycles = []
    attempts = Counter()
    initial_notification_ids = None
    stable_evidence = None
    marked_notification = None
    notifications_before = None

    with (
        tempfile.TemporaryDirectory(prefix="xti-inbox-soak-") as directory,
        patch("socket.socket", side_effect=deny_network),
        patch("socket.create_connection", side_effect=deny_network),
        patch("socket.getaddrinfo", side_effect=deny_network),
    ):
        database = Path(directory) / "xti.db"
        assets = SQLiteAssetRepository(database)
        assets.initialize()
        AssetService(assets).add("example.com")

        for cycle in range(1, cycles + 1):
            cycle_started = time.perf_counter()
            sources = {
                "crt.sh": FixtureSource("crt.sh", "partial" if cycle % 5 == 0 else "complete", counters),
                "urlscan": FixtureSource("urlscan", "failed" if cycle % 7 == 0 else "complete", counters),
            }
            service = _service(database, matcher, sources)
            for provider in ("crt.sh", "urlscan"):
                job = service.enqueue(provider=provider)
                if cycle == 1 and provider == "crt.sh":
                    finding_repository = service.discovery.findings
                    original_save = finding_repository.save_import

                    def commit_then_interrupt(*arguments):
                        original_save(*arguments)
                        raise KeyboardInterrupt

                    with patch.object(finding_repository, "save_import", side_effect=commit_then_interrupt):
                        try:
                            service.run(job.id)
                        except KeyboardInterrupt:
                            counters["controlled_post_commit_interruptions"] += 1
                        else:
                            raise AssertionError("Beklenen kontrollü kesinti oluşmadı.")
                    interrupted = SQLiteJobRepository(database).get(job.id).attempts[0]
                    require(interrupted.status == "interrupted", "Kesinti iş geçmişine yazılmadı.")
                    require(len(interrupted.queries) == 2, "Kesintide tamamlanan sorgular korunmadı.")
                    first_page = InboxService(SQLiteInboxRepository(database)).list(status="all")
                    require(first_page.total_count == 1, "İlk commit bulgu ve bildirimi birlikte saklamadı.")
                    first_notification = first_page.items[0].notification
                    service = _service(database, matcher, sources)
                    attempt = service.retry(job.id)
                    counters["retry_attempts"] += 1
                    attempts["interrupted"] += 1
                    require(
                        InboxService(SQLiteInboxRepository(database)).show(first_notification.id).notification
                        == first_notification,
                        "Kesinti sonrası retry ilk bildirimi değiştirdi.",
                    )
                    require(
                        SQLiteJobRepository(database).get(job.id).attempts[0] == interrupted,
                        "Retry kesinti geçmişini değiştirdi.",
                    )
                else:
                    attempt = service.run(job.id)
                require(attempt is not None, "Sıraya alınan iş çalıştırılmadı.")
                attempts[attempt.status] += 1
                if attempt.status in {"failed", "partial"}:
                    counters[f"{attempt.status}_jobs_retried"] += 1
                    before_retry = SQLiteJobRepository(database).get(job.id).attempts
                    sources[provider].mode = "complete"
                    service = _service(database, matcher, sources)
                    retried = service.retry(job.id)
                    counters["retry_attempts"] += 1
                    attempts[retried.status] += 1
                    require(retried.status == "complete", "Kaynak düzelince retry tamamlanmadı.")
                    require(
                        SQLiteJobRepository(database).get(job.id).attempts[:-1] == before_retry,
                        "Retry önceki kaynak hata geçmişini değiştirdi.",
                    )
                else:
                    require(attempt.status == "complete", "Beklenmeyen deneme durumu.")

            inbox = InboxService(SQLiteInboxRepository(database))
            page = inbox.list(status="all", limit=100)
            require(page.total_count == 3 and len(page.items) == 3, "Yinelenen veya eksik bildirim.")
            require(page.next_before is None, "Üç bildirim için beklenmeyen ek sayfa.")
            if cycle == 1:
                selected = page.items[-1]
                result = inbox.mark([selected.notification.id])
                require(result.changed_count == 1, "İlk okundu işlemi kaydedilmedi.")
                marked_notification = result.notifications[0]
                FindingService(SQLiteFindingRepository(database)).review(
                    selected.finding.id, "dismissed", "Ağsız doğrulama için sentetik örnek.",
                )
                initial_notification_ids = tuple(item.notification.id for item in page.items)
                notifications_before = tuple(item.notification for item in inbox.list(status="all").items)
                stable_evidence = {
                    finding.id: SQLiteFindingRepository(database).get_finding(finding.id)
                    for finding in SQLiteFindingRepository(database).list_findings()
                }
            repeated_mark = inbox.mark([marked_notification.id])
            require(repeated_mark.changed_count == 0, "Tekrar okundu işlemi zamanı değiştirdi.")
            require(repeated_mark.notifications == (marked_notification,), "Okundu kaydı değişti.")
            page = inbox.list(status="all")
            require(page.unread_count == 2, "Tekrar işleme okundu durumunu sıfırladı.")
            require(tuple(item.notification.id for item in page.items) == initial_notification_ids, "Bildirim kimliği değişti.")
            require(tuple(item.notification for item in page.items) == notifications_before, "Bildirim olay kaydı değişti.")
            findings = SQLiteFindingRepository(database)
            require(
                {finding.id: findings.get_finding(finding.id) for finding in findings.list_findings()}
                == stable_evidence,
                "Tekrar işleme bulgu, kaynak kanıtı veya insan kararını değiştirdi.",
            )
            inspection = SQLiteAssetRepository(database).inspect()
            require(inspection["observation_count"] == 6, "Kaynak gözlemleri tekrarlandı veya kayboldu.")
            require(inspection["finding_count"] == 3, "Bulgu sayısı değişti.")
            require(inspection["notification_count"] == 3, "Bildirim sayısı değişti.")
            require(inspection["running_job_count"] == 0, "Tamamlanan turda açık çalışan iş kaldı.")
            counters["stable_cycles_verified"] += 1
            elapsed_cycles.append(time.perf_counter() - cycle_started)

        with closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)) as connection:
            actual_attempts = dict(connection.execute("SELECT status, COUNT(*) FROM scan_attempts GROUP BY status"))
            final_jobs = dict(connection.execute("SELECT status, COUNT(*) FROM scan_jobs GROUP BY status"))
            require(actual_attempts == dict(attempts), "Deneme geçmişinin sayıları uyuşmuyor.")
            require(final_jobs == {"complete": cycles * 2}, "Son iş durumları uyuşmuyor.")
        expected_retries = 1 + cycles // 5 + cycles // 7
        require(counters["retry_attempts"] == expected_retries, "Retry sayısı uyuşmuyor.")
        require(counters["fixture_query_failures"] == cycles // 5 + cycles // 7, "Kaynak hata sayısı uyuşmuyor.")
        require(
            counters["fixture_query_calls"] == 3 * cycles + 2 * (cycles // 5) + cycles // 7 + 2,
            "Kaynak çağrı sayısı uyuşmuyor.",
        )
        require(counters["network_calls_blocked"] == 0, "Beklenmeyen ağ girişimi oldu.")
        database_bytes = database.stat().st_size

    return {
        "status": "passed", "verification": "offline-inbox-repetition-v1",
        "started_at": started_at, "cycles": cycles,
        "environment": {
            "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
            "platform": platform.platform(), "xti_version": __version__,
            "rule_version": matcher.rule_version, "psl_version": resolver.version,
            "psl_sha256": resolver.sha256,
        },
        "measurements": {
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "cycle_seconds_min": round(min(elapsed_cycles), 6),
            "cycle_seconds_max": round(max(elapsed_cycles), 6),
            "final_database_bytes": database_bytes, "max_rss": _max_rss(),
        },
        "counts": {
            "observations": inspection["observation_count"],
            "findings": inspection["finding_count"],
            "notifications": inspection["notification_count"],
            "unread_notifications": inspection["unread_notification_count"],
            "jobs": inspection["job_count"], "attempts": sum(actual_attempts.values()),
            "attempt_statuses": actual_attempts, "fixture_query_calls": counters["fixture_query_calls"],
            "fixture_query_failures": counters["fixture_query_failures"],
            "retry_attempts": counters["retry_attempts"],
            "controlled_post_commit_interruptions": counters["controlled_post_commit_interruptions"],
            "partial_jobs_retried": counters["partial_jobs_retried"],
            "failed_jobs_retried": counters["failed_jobs_retried"],
            "stable_cycles_verified": counters["stable_cycles_verified"],
            "network_calls_blocked": counters["network_calls_blocked"],
        },
        "expected_stable_counts": {
            "observations": 6, "findings": 3, "notifications": 3, "unread_notifications": 2,
        },
        "checks": {
            "evidence_and_review_preserved": True, "notification_ids_preserved": True,
            "explicit_read_time_preserved": True, "retry_history_preserved": True,
            "temporary_database_removed": not database.exists(), "network_entry_points_disabled": True,
        },
        "limits": [
            "Sentetik iki kaynak; gerçek ağ, sağlayıcı erişimi veya kota davranışı ölçülmedi.",
            "Süreç içi kontrollü KeyboardInterrupt; SIGKILL denemesi ayrı otomatik testlerdedir.",
            "Hızlandırılmış kısa tekrar ölçümü; saatler/günler süren çalışma veya kapasite garantisi değildir.",
            "Bulgu/kanıt/bildirim sayısı sabit kaldı; iş ve deneme geçmişi her turda büyür.",
            "Kullanıcı kayıt alanına erişilmedi; geçici doğrulama veritabanı silindi.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Geçici verilerle ağsız bildirim tekrar doğrulaması.")
    parser.add_argument("--cycles", type=int, default=30, help="10–1000 tur (varsayılan: 30)")
    arguments = parser.parse_args()
    if not 10 <= arguments.cycles <= 1000:
        parser.error("--cycles 10–1000 arasında olmalı.")
    try:
        result = verify(arguments.cycles)
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "message": str(error)}, ensure_ascii=True))
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
