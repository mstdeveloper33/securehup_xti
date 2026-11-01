"""One consistent, read-only view of monitoring history and local work."""

from typing import Protocol

from xti.domain.status import StatusSnapshot


class StatusRepository(Protocol):
    def snapshot(
        self, providers: tuple[str, ...], domain: str | None, limit: int,
    ) -> StatusSnapshot:
        """Global counts plus bounded asset coverage in one read transaction.

        Select attempts by insertion order, including retries of older jobs.
        A complete multi-target attempt applies to every target of that job;
        partial attempts never count as complete for an individual target.
        No locks, recovery, migration, requests or database creation on read.
        """
        ...
