"""Validated lifecycle and explicit live execution for username watches."""

from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from xti.domain.collection_history import CollectionOperationToken
from xti.domain.assets import ValidationError
from xti.domain.brand_username import normalize_brand_username
from xti.domain.brand_username import BRAND_USERNAME_SOURCE_NAMES
from xti.domain.brand_username_watches import (
    BrandUsernameWatchDetails,
    BrandUsernameWatchMutation,
    BrandUsernameWatchRunReport,
    BrandUsernameWatchSummary,
    brand_watch_definition_sha256,
    brand_watch_name_key,
    normalize_brand_watch_name,
)
from xti.domain.cti_indicators import normalize_assertion_reason
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.ports.brand_username import BrandUsernameSource
from xti.ports.brand_username_watches import BrandUsernameWatchRepository
from xti.ports.discovery import SourceError
from xti.application.brand_username import (
    DEFAULT_PLATFORMS,
    EXTENDED_PLATFORMS,
    SHERLOCK_DEFAULT_PLATFORMS,
    SHERLOCK_EXTENDED_PLATFORMS,
    SHERLOCK_SUPPORTED_PLATFORMS,
    SUPPORTED_PLATFORMS,
    resolve_username_selection,
    validate_brand_platforms,
    validate_brand_request_timeout,
    validate_sherlock_platforms,
)


class BrandUsernameWatchService:
    def __init__(
        self,
        repository: BrandUsernameWatchRepository,
        source: BrandUsernameSource | Mapping[str, BrandUsernameSource],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        if isinstance(source, Mapping):
            self.sources = dict(source)
        else:
            source_key = next(
                (
                    key for key, name in BRAND_USERNAME_SOURCE_NAMES.items()
                    if source.source_name == name
                ),
                None,
            )
            if source_key is None:
                raise ValidationError("Sosyal kullanıcı adı kaynağı desteklenmiyor.")
            self.sources = {source_key: source}
        for source_key, selected_source in self.sources.items():
            if (
                source_key not in BRAND_USERNAME_SOURCE_NAMES
                or selected_source.source_name != BRAND_USERNAME_SOURCE_NAMES[source_key]
            ):
                raise ValidationError("Sosyal kullanıcı adı kaynak eşlemesi geçersiz.")
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValidationError("Sosyal kullanıcı adı izleme zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _limit(value: int, *, field: str) -> int:
        if type(value) is not int or not 1 <= value <= 500:
            raise ValidationError(f"{field} 1–500 arasında olmalı.")
        return value

    @staticmethod
    def _watch_id(value: str) -> str:
        return normalize_knowledge_id(value, field="Sosyal kullanıcı adı izleme kimliği")

    def add(
        self,
        name: str,
        username: str,
        *,
        platforms: tuple[str, ...] | None = None,
        profile: str | None = None,
        source_key: str = "maigret",
    ) -> BrandUsernameWatchMutation:
        display_name = normalize_brand_watch_name(name)
        username = normalize_brand_username(username)
        if source_key == "maigret":
            selected, _ = resolve_username_selection(
                platforms,
                profile,
                safe=DEFAULT_PLATFORMS,
                extended=EXTENDED_PLATFORMS,
            )
            selected = validate_brand_platforms(selected)
            supported = SUPPORTED_PLATFORMS
        elif source_key == "sherlock":
            selected, _ = resolve_username_selection(
                platforms,
                profile,
                safe=SHERLOCK_DEFAULT_PLATFORMS,
                extended=SHERLOCK_EXTENDED_PLATFORMS,
            )
            selected = validate_sherlock_platforms(selected)
            supported = SHERLOCK_SUPPORTED_PLATFORMS
        else:
            raise ValidationError("Kaynak maigret veya sherlock olmalı.")
        ordered = tuple(item for item in supported if item in selected)
        return self.repository.upsert(
            name_key=brand_watch_name_key(display_name),
            display_name=display_name,
            username=username,
            platforms=ordered,
            source_key=source_key,
            recorded_at=self._now(),
        )

    def revoke(self, watch_id: str, *, reason: str) -> BrandUsernameWatchMutation:
        return self.repository.revoke(
            self._watch_id(watch_id),
            reason=normalize_assertion_reason(reason),
            recorded_at=self._now(),
        )

    def list(
        self, *, active_only: bool = True, limit: int = 50,
    ) -> tuple[BrandUsernameWatchSummary, ...]:
        if type(active_only) is not bool:
            raise ValidationError("Sosyal kullanıcı adı izleme filtresi geçersiz.")
        return self.repository.list(
            active_only=active_only,
            limit=self._limit(limit, field="Liste sınırı"),
        )

    def list_window(
        self, *, active_only: bool = True, limit: int = 50,
    ) -> tuple[tuple[BrandUsernameWatchSummary, ...], bool]:
        """Return a deterministic bounded window and an explicit overflow flag."""
        if type(active_only) is not bool:
            raise ValidationError("Sosyal kullanıcı adı izleme filtresi geçersiz.")
        limit = self._limit(limit, field="Liste sınırı")
        records = self.repository.list(active_only=active_only, limit=limit + 1)
        return records[:limit], len(records) > limit

    def show(
        self, watch_id: str, *, event_limit: int = 50, run_limit: int = 20,
    ) -> BrandUsernameWatchDetails:
        return self.repository.details(
            self._watch_id(watch_id),
            event_limit=self._limit(event_limit, field="Olay sınırı"),
            run_limit=self._limit(run_limit, field="Çalışma sınırı"),
        )

    def run(
        self,
        watch_id: str,
        *,
        request_timeout: int = 10,
        item_limit: int = 100,
        operation: CollectionOperationToken | None = None,
    ) -> BrandUsernameWatchRunReport:
        watch = self.repository.get(self._watch_id(watch_id))
        if not watch.active:
            raise ValidationError("Geri çekilmiş sosyal kullanıcı adı izlemesi çalıştırılamaz.")
        timeout = validate_brand_request_timeout(request_timeout)
        item_limit = self._limit(item_limit, field="Sonuç sınırı")
        definition = brand_watch_definition_sha256(
            username=watch.username,
            platforms=watch.platforms,
        )
        source = self.sources.get(watch.source_key)
        if source is None:
            raise ValidationError(
                f"{BRAND_USERNAME_SOURCE_NAMES[watch.source_key]} kaynağı yapılandırılmamış."
            )
        try:
            preview = source.preview(
                watch.username,
                platforms=watch.platforms,
                request_timeout=timeout,
            )
        except SourceError as error:
            return self.repository.record_failure(
                watch.id,
                expected_definition_sha256=definition,
                source_name=source.source_name,
                source_version=source.source_version,
                integration_profile=source.integration_profile,
                error=str(error),
                recorded_at=self._now(),
                **({"operation": operation} if operation is not None else {}),
            )
        return self.repository.record_preview(
            watch.id,
            expected_definition_sha256=definition,
            preview=preview,
            recorded_at=self._now(),
            item_limit=item_limit,
            **({"operation": operation} if operation is not None else {}),
        )

    def show_run(
        self, run_id: str, *, item_limit: int = 100,
    ) -> BrandUsernameWatchRunReport:
        return self.repository.run_details(
            normalize_knowledge_id(
                run_id,
                field="Sosyal kullanıcı adı izleme çalışma kimliği",
            ),
            item_limit=self._limit(item_limit, field="Sonuç sınırı"),
        )
