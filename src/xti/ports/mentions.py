"""Small provider and append-only content discovery persistence boundaries."""

from typing import Protocol

from xti.domain.mentions import MentionCatalog, MentionRequest, MentionResponse, MentionRun


class MentionSource(Protocol):
    def fetch(self, request: MentionRequest) -> MentionResponse: ...


class MentionRepository(Protocol):
    def validate(self, *, max_results: int = 20) -> None: ...

    def apply(self, request: MentionRequest, response: MentionResponse, *, started_at: str,
              finished_at: str) -> MentionRun: ...

    def record_failure(self, request: MentionRequest, *, error: str, started_at: str,
                       finished_at: str) -> MentionRun: ...

    def catalog(self) -> MentionCatalog: ...

    def run_show(self, identifier: str) -> MentionRun: ...
