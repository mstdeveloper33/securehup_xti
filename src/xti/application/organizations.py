"""User-selected organization grouping over existing domain and watch records."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.organizations import (
    OrganizationDetails, OrganizationLinkDetails, OrganizationLinkMutation,
    OrganizationMutation, OrganizationPage, normalize_organization_id,
    normalize_organization_name, normalize_organization_reason,
    normalize_organization_target,
)
from xti.ports.jobs import ExecutionLock
from xti.ports.organizations import OrganizationRepository


class OrganizationService:
    def __init__(
        self, repository: OrganizationRepository, lock: ExecutionLock, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.lock = lock
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Kuruluş kayıt zamanı saat dilimi bilgili olmalı.")
        try:
            return value.astimezone(timezone.utc).isoformat()
        except (OverflowError, ValueError) as error:
            raise ValidationError("Kuruluş kayıt zamanı geçersiz.") from error

    def _write(self, operation, *args, **kwargs):
        with self.lock.acquire():
            return operation(*args, **kwargs, recorded_at=self._now())

    @staticmethod
    def _window(offset: int, limit: int) -> None:
        if type(offset) is not int or not 0 <= offset <= 1_000_000:
            raise ValidationError("Kuruluş görünüm başlangıcı 0–1000000 arasında olmalı.")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Kuruluş görünüm sınırı 1–500 arasında olmalı.")

    @staticmethod
    def _filter(value: bool) -> bool:
        if type(value) is not bool:
            raise ValidationError("Kuruluş etkinlik filtresi doğru/yanlış olmalı.")
        return value

    def add(self, name: str, *, reason: str) -> OrganizationMutation:
        name_key, display_name = normalize_organization_name(name)
        return self._write(
            self.repository.add, name_key=name_key, display_name=display_name,
            reason=normalize_organization_reason(reason),
        )

    def rename(self, organization_id: str, name: str, *, reason: str) -> OrganizationMutation:
        name_key, display_name = normalize_organization_name(name)
        return self._write(
            self.repository.rename, normalize_organization_id(organization_id),
            name_key=name_key, display_name=display_name,
            reason=normalize_organization_reason(reason),
        )

    def revoke(self, organization_id: str, *, reason: str) -> OrganizationMutation:
        return self._write(
            self.repository.revoke, normalize_organization_id(organization_id),
            reason=normalize_organization_reason(reason),
        )

    def reactivate(self, organization_id: str, *, reason: str) -> OrganizationMutation:
        return self._write(
            self.repository.reactivate, normalize_organization_id(organization_id),
            reason=normalize_organization_reason(reason),
        )

    def link(
        self, organization_id: str, *, kind: str, value: str, reason: str,
    ) -> OrganizationLinkMutation:
        return self._write(
            self.repository.link, normalize_organization_id(organization_id),
            normalize_organization_target(kind, value),
            reason=normalize_organization_reason(reason),
        )

    def unlink(self, organization_id: str, link_id: str, *, reason: str) -> OrganizationLinkMutation:
        return self._write(
            self.repository.unlink, normalize_organization_id(organization_id),
            normalize_organization_id(link_id, field="Kuruluş bağlantısı kimliği"),
            reason=normalize_organization_reason(reason),
        )

    def list(self, *, active_only: bool = True, offset: int = 0, limit: int = 100) -> OrganizationPage:
        self._window(offset, limit)
        return self.repository.list(active_only=self._filter(active_only), offset=offset, limit=limit)

    def show(
        self, organization_id: str, *, active_links_only: bool = False,
        link_offset: int = 0, link_limit: int = 100, event_limit: int = 50,
    ) -> OrganizationDetails:
        self._window(link_offset, link_limit)
        self._window(0, event_limit)
        return self.repository.show(
            normalize_organization_id(organization_id),
            active_links_only=self._filter(active_links_only), link_offset=link_offset,
            link_limit=link_limit, event_limit=event_limit,
        )

    def show_link(
        self, organization_id: str, link_id: str, *, event_limit: int = 50,
    ) -> OrganizationLinkDetails:
        self._window(0, event_limit)
        return self.repository.show_link(
            normalize_organization_id(organization_id),
            normalize_organization_id(link_id, field="Kuruluş bağlantısı kimliği"),
            event_limit=event_limit,
        )
