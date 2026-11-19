"""Read-only company review scope, independent of the host's user management."""
from typing import Protocol


class CompanyReviewRepository(Protocol):
    def read(self, *, checked_at: str, stale_after_hours: int, root_offset: int, root_limit: int,
             social_offset: int = 0, social_limit: int = 20) -> dict: ...
