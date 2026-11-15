"""Publish optional regular collection files without depending on a service manager."""

from typing import Protocol

from xti.domain.mention_groups import MentionGroup
from xti.domain.scheduling import GeneratedSchedule, ScheduleSpec


class MentionScheduleFiles(Protocol):
    def publish(self, group: MentionGroup, *, output: str, spec: ScheduleSpec,
                api_key_file=None) -> GeneratedSchedule: ...
