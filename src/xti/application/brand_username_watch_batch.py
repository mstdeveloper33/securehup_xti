"""Bounded foreground execution of every active social username watch."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.application.brand_username import validate_brand_request_timeout
from xti.application.brand_username_watches import BrandUsernameWatchService
from xti.domain.assets import ValidationError
from xti.domain.brand_username_watches import (
    BrandUsernameWatchBatchItem,
    BrandUsernameWatchBatchReport,
)


class BrandUsernameWatchBatchService:
    def __init__(
        self,
        watches: BrandUsernameWatchService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.watches = watches
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def validate_limits(max_watches: int, request_timeout: int) -> None:
        if type(max_watches) is not int or not 1 <= max_watches <= 100:
            raise ValidationError("Toplu sosyal izleme sınırı 1–100 arasında olmalı.")
        validate_brand_request_timeout(request_timeout)

    def _now(self) -> str:
        value = self.clock()
        try:
            if (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise ValueError("timezone required")
            return value.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Toplu sosyal izleme zamanı geçersiz.") from error

    def run(
        self,
        *,
        max_watches: int = 10,
        request_timeout: int = 10,
        progress: Callable[[str], None] | None = None,
    ) -> BrandUsernameWatchBatchReport:
        self.validate_limits(max_watches, request_timeout)
        watches, has_more = self.watches.list_window(
            active_only=True,
            limit=max_watches,
        )
        if has_more:
            raise ValidationError(
                "Etkin sosyal kullanıcı adı izlemelerinin tamamı toplu sınıra "
                "sığmıyor; --watch-limit değerini artırın. Hiçbir izleme "
                "çalıştırılmadı."
            )

        started_at = self._now()
        items: list[BrandUsernameWatchBatchItem] = []
        planned = len(watches)
        for position, summary in enumerate(watches, start=1):
            watch = summary.watch
            if progress:
                progress(
                    f"Sosyal toplu izleme {position}/{planned}: "
                    f"{watch.display_name}"
                )
            report = self.watches.run(
                watch.id,
                request_timeout=request_timeout,
                item_limit=10,
            )
            run = report.run
            items.append(BrandUsernameWatchBatchItem(
                position=position,
                watch_id=watch.id,
                display_name=watch.display_name,
                source_key=watch.source_key,
                run_id=run.id,
                status=run.status,
                recorded_at=run.recorded_at,
                platform_count=run.platform_count,
                found_count=run.found_count,
                newly_found_count=run.newly_found_count,
                changed_count=run.changed_count,
                unchanged_found_count=run.unchanged_found_count,
                no_longer_reported_count=run.no_longer_reported_count,
                unreported_count=run.unreported_count,
                attention_count=report.attention_count,
                error=run.error,
            ))
            if progress:
                outcome = (
                    "kaynak hatasıyla kaydedildi"
                    if run.status == "failed"
                    else "tamamlandı"
                )
                progress(f"Sosyal toplu izleme {position}/{planned} {outcome}.")

        finished_at = self._now()
        return BrandUsernameWatchBatchReport(
            planned_watch_count=planned,
            completed_watch_count=len(items),
            successful_watch_count=sum(item.status == "complete" for item in items),
            failed_watch_count=sum(item.status == "failed" for item in items),
            started_at=started_at,
            finished_at=finished_at,
            platform_count=sum(item.platform_count for item in items),
            found_count=sum(item.found_count for item in items),
            newly_found_count=sum(item.newly_found_count for item in items),
            changed_count=sum(item.changed_count for item in items),
            no_longer_reported_count=sum(
                item.no_longer_reported_count for item in items
            ),
            attention_count=sum(item.attention_count for item in items),
            items=tuple(items),
            notes=(
                "Yalnız etkin izlemeler adlarına göre sabit sırada çalıştırıldı.",
                "Her izleme ayrı atomik kayıttır; kaynak hatası yokluk sayılmaz.",
                "Bulunan profil otomatik taklit kararı veya bildirim değildir.",
                "Bu komut tek seferliktir; arka plan servisi kurmaz.",
            ),
        )
