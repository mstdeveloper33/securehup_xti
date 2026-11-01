"""Persistence boundary for imported observations and candidate review."""

from typing import Protocol, Sequence

from xti.domain.findings import (
    Finding, FindingDetails, ImportDocument, ImportSummary, MatchCandidate,
)


class FindingRepository(Protocol):
    def save_import(
        self, document: ImportDocument, candidates: Sequence[MatchCandidate]
    ) -> ImportSummary:
        """Save the entire validated import atomically and preserve past reviews."""
        ...

    def list_findings(self, status: str | None = None) -> list[Finding]:
        ...

    def get_finding(self, finding_id: str) -> FindingDetails:
        ...

    def review_finding(self, finding_id: str, decision: str, reason: str) -> Finding:
        ...

