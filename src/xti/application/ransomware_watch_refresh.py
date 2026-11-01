"""Explicit source refresh followed by every active ransomware claim watch."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.application.ransomware_claims import RansomwareClaimHistoryService
from xti.application.ransomware_watches import RansomwareWatchService
from xti.domain.assets import ValidationError
from xti.domain.ransomware_watches import (
    RansomwareWatchRefreshItem,
    RansomwareWatchRefreshReport,
)


class RansomwareWatchRefreshService:
    def __init__(
        self, history: RansomwareClaimHistoryService,
        watches: RansomwareWatchService, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.history = history
        self.watches = watches
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def validate_limits(
        max_watches: int, source_item_limit: int, watch_item_limit: int,
    ) -> None:
        for value, label in (
            (max_watches, "Etkin izleme sınırı"),
            (source_item_limit, "Kaynak değişiklik sınırı"),
            (watch_item_limit, "İzleme sonuç sınırı"),
        ):
            if type(value) is not int or not 1 <= value <= 500:
                raise ValidationError(f"{label} 1–500 arasında olmalı.")

    def _now(self) -> str:
        value = self.clock()
        try:
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("timezone required")
            return value.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Ransomware toplu izleme zamanı geçersiz.") from error

    def preflight(self, *, max_watches: int = 50) -> int:
        """Validate all active definitions and reject silent truncation before network."""
        if type(max_watches) is not int or not 1 <= max_watches <= 500:
            raise ValidationError("Etkin izleme sınırı 1–500 arasında olmalı.")
        watches, has_more = self.watches.list_window(
            active_only=True, limit=max_watches,
        )
        if has_more:
            raise ValidationError(
                "Etkin ransomware izlemelerinin tamamı toplu sınıra sığmıyor; "
                "--watch-limit değerini artırın. Kaynak yenilenmedi ve hiçbir izleme "
                "çalıştırılmadı."
            )
        return len(watches)

    def run(
        self, *, max_watches: int = 50, source_item_limit: int = 100,
        watch_item_limit: int = 100,
        progress: Callable[[str], None] | None = None,
    ) -> RansomwareWatchRefreshReport:
        self.validate_limits(max_watches, source_item_limit, watch_item_limit)
        watches, has_more = self.watches.list_window(
            active_only=True, limit=max_watches,
        )
        if has_more:
            raise ValidationError(
                "Etkin ransomware izlemelerinin tamamı toplu sınıra sığmıyor; "
                "--watch-limit değerini artırın. Kaynak yenilenmedi ve hiçbir izleme "
                "çalıştırılmadı."
            )

        started_at = self._now()
        if progress:
            progress("Ransomware açık kaynağı yenileniyor.")
        refresh = self.history.refresh(item_limit=source_item_limit)
        if refresh.run.status != "complete":
            if progress:
                progress("Kaynak yenilenemedi; etkin izlemeler çalıştırılmadı.")
            return RansomwareWatchRefreshReport(
                refresh=refresh, planned_watch_count=len(watches),
                completed_watch_count=0, baseline_watch_count=0,
                started_at=started_at,
                finished_at=self._now(), total_count=0, added_count=0,
                updated_count=0, unchanged_count=0, removed_count=0,
                notification_count=0, items=(),
                notes=(
                    "Kaynak hatası boş snapshot sayılmadı; önceki başarılı veri korundu.",
                    "Eski snapshot üzerinde hiçbir izleme çalıştırılmadı.",
                ),
            )

        planned = len(watches)
        items: list[RansomwareWatchRefreshItem] = []
        for position, summary in enumerate(watches, start=1):
            watch = summary.watch
            if progress:
                progress(
                    f"Ransomware izlemesi {position}/{planned}: {watch.display_name}"
                )
            report = self.watches.run(
                watch.id, item_limit=watch_item_limit,
                expected_source_run_id=refresh.run.id,
            )
            run = report.run
            if run.source_run_id != refresh.run.id:
                raise ValidationError(
                    "Ransomware izlemesi yenilenen kaynak snapshot'ıyla eşleşmedi; "
                    "toplu işlem durduruldu."
                )
            items.append(RansomwareWatchRefreshItem(
                position=position, watch_id=watch.id,
                display_name=watch.display_name, run_id=run.id,
                source_run_id=run.source_run_id, executed_at=run.executed_at,
                total_count=run.total_count, added_count=run.added_count,
                updated_count=run.updated_count,
                unchanged_count=run.unchanged_count,
                removed_count=run.removed_count,
                notification_id=report.notification_id,
                is_baseline=report.is_baseline,
            ))
            if progress:
                progress(f"Ransomware izlemesi {position}/{planned} tamamlandı.")

        return RansomwareWatchRefreshReport(
            refresh=refresh, planned_watch_count=planned,
            completed_watch_count=len(items),
            baseline_watch_count=sum(item.is_baseline for item in items),
            started_at=started_at,
            finished_at=self._now(),
            total_count=sum(item.total_count for item in items),
            added_count=sum(item.added_count for item in items),
            updated_count=sum(item.updated_count for item in items),
            unchanged_count=sum(item.unchanged_count for item in items),
            removed_count=sum(item.removed_count for item in items),
            notification_count=sum(item.notification_id is not None for item in items),
            items=tuple(items),
            notes=(
                "Kaynak yalnız açık komutla yenilendi; izlemeler adlarına göre sabit sırada çalıştı.",
                "Her izleme ayrı atomik kayıttır; ilk veya değişmiş tanım ölçümü sessizdir.",
                "Bu komut tek seferliktir; görünmez arka plan servisi kurmaz.",
            ),
        )
