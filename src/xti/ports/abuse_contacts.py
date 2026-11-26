"""Ports for abuse-contact collection and durable review workflows."""

from typing import Protocol

from xti.domain.abuse_contacts import SourceOutcome


class AbuseContactSource(Protocol):
    def local_capabilities(self) -> dict: ...

    def collect(
        self, subject_kind: str, subject_value: str, *, include_whois: bool,
        timeout_seconds: int,
    ) -> tuple[SourceOutcome, ...]: ...


class AbuseContactRepository(Protocol):
    def read(self, operation: str, values: dict, recorded_at: str) -> dict: ...

    def mutate(self, operation: str, values: dict, recorded_at: str) -> dict: ...

    def reserve_run(self, values: dict, recorded_at: str) -> tuple[dict, bool]: ...

    def finish_run(
        self, run_id: str, outcomes: tuple[SourceOutcome, ...], recorded_at: str,
    ) -> dict: ...

    def fail_run(
        self, run_id: str, code: str, message: str, recorded_at: str,
    ) -> dict: ...
