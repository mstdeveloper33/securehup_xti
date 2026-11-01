"""Persistence boundary for canonical IOC identities and source assertions."""

from typing import Protocol

from xti.domain.cti_indicators import (
    CtiIndicatorDetails,
    CtiIndicatorExportSnapshot,
    CtiIndicatorMutation,
    CtiIndicatorSummary,
)


class CtiIndicatorRepository(Protocol):
    def add_assertion(
        self, *, indicator_type: str, value: str, source_name: str,
        source_reference: str, confidence: int, valid_from: str | None,
        valid_until: str | None, description: str, observed_at: str,
        recorded_at: str,
    ) -> CtiIndicatorMutation:
        ...

    def revoke_assertion(
        self, assertion_id: str, *, reason: str, recorded_at: str,
    ) -> CtiIndicatorMutation:
        ...

    def list(
        self, *, indicator_type: str | None, active_only: bool, checked_at: str,
        limit: int,
    ) -> tuple[CtiIndicatorSummary, ...]:
        ...

    def current_summary(
        self, indicator_type: str, value: str, *, checked_at: str,
    ) -> CtiIndicatorSummary | None:
        ...

    def details(
        self, indicator_id: str, *, assertion_limit: int, event_limit: int,
    ) -> CtiIndicatorDetails:
        ...

    def lookup(
        self, indicator_type: str, value: str, *, assertion_limit: int,
        event_limit: int,
    ) -> CtiIndicatorDetails:
        ...

    def export_snapshot(
        self, *, indicator_type: str | None, checked_at: str,
    ) -> CtiIndicatorExportSnapshot:
        ...

