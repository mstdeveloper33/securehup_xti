"""Bounded foreground execution of every active durable CTI search."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.application.cti_saved_searches import CtiSavedSearchService
from xti.domain.assets import ValidationError
from xti.domain.cti_saved_searches import (
    CtiSavedSearchBatchItem,
    CtiSavedSearchBatchReport,
)


class CtiSavedSearchBatchService:
    def __init__(
        self, saved_searches: CtiSavedSearchService, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.saved_searches = saved_searches
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def validate_limits(max_searches: int, item_limit: int) -> None:
        if type(max_searches) is not int or not 1 <= max_searches <= 500:
            raise ValidationError("Toplu CTI arama sınırı 1–500 arasında olmalı.")
        if type(item_limit) is not int or not 1 <= item_limit <= 500:
            raise ValidationError("Toplu CTI sonuç sınırı 1–500 arasında olmalı.")

    def _now(self) -> str:
        value = self.clock()
        try:
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("timezone required")
            return value.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Toplu CTI arama zamanı geçersiz.") from error

    def run(
        self, *, max_searches: int = 50, item_limit: int = 100,
        progress: Callable[[str], None] | None = None,
    ) -> CtiSavedSearchBatchReport:
        self.validate_limits(max_searches, item_limit)
        searches, has_more = self.saved_searches.list_window(
            active_only=True, limit=max_searches,
        )
        if has_more:
            raise ValidationError(
                "Etkin kayıtlı CTI aramalarının tamamı toplu sınıra sığmıyor; "
                "--search-limit değerini artırın. Hiçbir arama çalıştırılmadı."
            )
        started_at = self._now()
        items: list[CtiSavedSearchBatchItem] = []
        planned = len(searches)
        for position, summary in enumerate(searches, start=1):
            search = summary.saved_search
            if progress:
                progress(
                    f"CTI toplu arama {position}/{planned}: {search.display_name}"
                )
            report = self.saved_searches.run(search.id, item_limit=item_limit)
            run = report.run
            items.append(CtiSavedSearchBatchItem(
                position=position, saved_search_id=search.id,
                display_name=search.display_name, run_id=run.id,
                executed_at=run.executed_at, total_count=run.total_count,
                added_count=run.added_count, updated_count=run.updated_count,
                unchanged_count=run.unchanged_count, removed_count=run.removed_count,
                notification_id=report.notification_id,
            ))
            if progress:
                progress(f"CTI toplu arama {position}/{planned} tamamlandı.")
        finished_at = self._now()
        return CtiSavedSearchBatchReport(
            planned_search_count=planned, completed_search_count=len(items),
            started_at=started_at, finished_at=finished_at,
            total_count=sum(value.total_count for value in items),
            added_count=sum(value.added_count for value in items),
            updated_count=sum(value.updated_count for value in items),
            unchanged_count=sum(value.unchanged_count for value in items),
            removed_count=sum(value.removed_count for value in items),
            notification_count=sum(value.notification_id is not None for value in items),
            items=tuple(items),
            notes=(
                "Yalnız etkin kayıtlı aramalar, adlarına göre sabit sırada çalıştırıldı.",
                "Her arama ayrı atomik çalışma kaydıdır; ilk taban sessizdir.",
                "Bu komut tek seferliktir; görünmez arka plan servisi kurmaz.",
            ),
        )
