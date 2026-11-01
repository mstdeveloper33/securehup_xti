"""Persist provider waits while keeping each process's monotonic lower bound.

The caller holds the local worker lock. This gate is not a distributed rate
limiter and does not coordinate different database directories or applications.
"""

from datetime import datetime, timedelta, timezone
import math
from typing import Callable

from xti.ports.discovery import SourceError
from xti.ports.operations import CooldownRepository


MAX_INLINE_WAIT = 5.0
_LATEST = datetime.max.replace(tzinfo=timezone.utc)


class SourceCooldownGate:
    def __init__(
        self, provider: str, repository: CooldownRepository,
        *, clock: Callable[[], float], wall_clock: Callable[[], datetime],
        sleep: Callable[[float], None],
    ) -> None:
        self.provider = provider
        self.repository = repository
        self.clock = clock
        self.wall_clock = wall_clock
        self.sleep = sleep
        self._not_before = 0.0

    def _now(self) -> datetime:
        now = self.wall_clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise SourceError("Kaynak bekleme zamanı için geçerli saat dilimi gerekli; istek gönderilmedi.")
        return now.astimezone(timezone.utc)

    def _load_delay(self) -> float:
        saved = self.repository.get(self.provider)
        if saved is not None:
            # Repository validates stored rows; retain a local monotonic floor so
            # a later forward wall-clock adjustment cannot shorten a seen wait.
            until = datetime.fromisoformat(saved.not_before)
            if until.tzinfo is None or until.utcoffset() is None:
                raise SourceError("Kaynak bekleme kaydı geçersiz; istek gönderilmedi.")
            delay = max(0.0, (until - self._now()).total_seconds())
            self._not_before = max(self._not_before, self.clock() + delay)
        return max(0.0, self._not_before - self.clock())

    def record(self, delay: float | None, reason: str) -> bool:
        if delay is None:
            return True
        if math.isnan(delay) or delay < 0:
            raise SourceError("Kaynağın bekleme süresi geçersiz; istek durduruldu.")
        now = self._now()
        try:
            until = now + timedelta(seconds=delay)
        except OverflowError:
            # Never turn an unrepresentably long provider request into a short
            # retry. The maximum calendar date stays visible in source status.
            until = _LATEST
        saved = self.repository.extend(self.provider, until.isoformat(), now.isoformat(), reason)
        self._not_before = max(self._not_before, self.clock() + delay)
        # A previous provider wait may be longer than this new hint.
        stored = datetime.fromisoformat(saved.not_before)
        if stored.tzinfo is None or stored.utcoffset() is None:
            raise SourceError("Kaynak bekleme kaydı geçersiz; istek durduruldu.")
        self._not_before = max(self._not_before, self.clock() + max(0.0, (stored - now).total_seconds()))
        return stored <= until

    def before_request(self, interval: float) -> None:
        """Read before every attempt, wait briefly, then reserve before opening."""
        delay = self._load_delay()
        if delay > MAX_INLINE_WAIT:
            self._blocked()
        if delay > 0:
            self.sleep(delay)
            # Re-read rather than assuming sleep completed or another writer did
            # not extend the wait. A stuck/backwards clock must not send early.
            if self._load_delay() > 0:
                self._blocked()
        if not self.record(interval, "request_spacing"):
            # A longer hold appearing between read and reservation must win.
            self._blocked()

    def _blocked(self) -> None:
        raise SourceError(
            f"{self.provider} bekleme süresi devam ediyor; yeni istek gönderilmedi. Daha sonra yeniden dene."
        )
