"""Explicit organization watches over exact public catalog domain metadata."""

from dataclasses import dataclass

from xti.domain.organizations import Organization
from xti.domain.public_notices import (
    HIBP_ATTRIBUTION, HIBP_LICENSE, HIBP_SOURCE_NAME, HIBP_SOURCE_URL,
    PublicNotice, PublicNoticeRun,
)


PUBLIC_NOTICE_WATCH_NOTES = (
    "İzleme açık kullanıcı seçimiyle kuruluşun etkin domain bağlantılarını kullanır; sahiplik veya ihlal doğrulaması değildir.",
    "İlk ölçüm ve yeni/yeniden etkin kapsam sessiz başlangıçtır; eski katalog olayları yeni ihlal sayılmaz.",
    "Yalnız kaynağın tam Domain alanı eşleştirilir; ad, alt alan adı veya hesap bilgisi tahmin edilmez.",
    "Kaynak sınıfları HIBP'nin değerlendirmesidir. Eşleşmeden çıkış, olayın çözüldüğünü göstermez.",
)


@dataclass(frozen=True, slots=True)
class PublicNoticeWatch:
    id: str
    organization_id: str
    active: bool
    revision: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class PublicNoticeWatchEvent:
    sequence: int
    id: str
    watch_id: str
    organization_id: str
    action: str
    revision: int
    reason: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class PublicNoticeWatchScopeMember:
    domain: str
    link_id: str
    revision: int
    event_id: str
    epoch_event_id: str


@dataclass(frozen=True, slots=True)
class PublicNoticeWatchScope:
    organization_id: str
    organization_name: str
    organization_active: bool
    organization_revision: int
    organization_event_id: str
    organization_epoch_event_id: str
    organization_event_sequence: int
    link_event_sequence: int
    members: tuple[PublicNoticeWatchScopeMember, ...]


@dataclass(frozen=True, slots=True)
class PublicNoticeWatchRun:
    sequence: int
    id: str
    watch_id: str
    organization_id: str
    source_run_id: str
    watch_event_id: str
    previous_run_id: str | None
    recorded_at: str
    scope_sha256: str
    result_sha256: str
    matched_count: int
    baseline_count: int
    added_count: int
    updated_count: int
    removed_count: int
    unchanged_count: int


@dataclass(frozen=True, slots=True)
class PublicNoticeWatchItem:
    notice_id: str
    action: str
    domain: str
    before: PublicNotice | None
    after: PublicNotice | None


@dataclass(frozen=True, slots=True)
class PublicNoticeWatchMutation:
    action: str
    watch: PublicNoticeWatch


@dataclass(frozen=True, slots=True)
class PublicNoticeWatchSummary:
    watch: PublicNoticeWatch
    organization_name: str
    organization_active: bool
    effective_domain_count: int
    latest_run: PublicNoticeWatchRun | None
    total_run_count: int


@dataclass(frozen=True, slots=True)
class PublicNoticeWatchPage:
    watches: tuple[PublicNoticeWatchSummary, ...]
    total_count: int
    offset: int
    limit: int
    latest_source_run: PublicNoticeRun | None
    latest_complete_source_run: PublicNoticeRun | None
    notes: tuple[str, ...] = PUBLIC_NOTICE_WATCH_NOTES
    attribution: str = HIBP_ATTRIBUTION
    license: str = HIBP_LICENSE


@dataclass(frozen=True, slots=True)
class PublicNoticeWatchDetails:
    watch: PublicNoticeWatch
    organization: Organization
    effective_domains: tuple[str, ...]
    events: tuple[PublicNoticeWatchEvent, ...]
    runs: tuple[PublicNoticeWatchRun, ...]
    total_event_count: int
    total_run_count: int
    latest_source_run: PublicNoticeRun | None
    latest_complete_source_run: PublicNoticeRun | None
    notes: tuple[str, ...] = PUBLIC_NOTICE_WATCH_NOTES
    attribution: str = HIBP_ATTRIBUTION
    license: str = HIBP_LICENSE

    run_offset: int = 0
    event_offset: int = 0


@dataclass(frozen=True, slots=True)
class PublicNoticeWatchRunReport:
    watch: PublicNoticeWatch
    run: PublicNoticeWatchRun
    scope: PublicNoticeWatchScope
    previous_source_run_id: str | None
    items: tuple[PublicNoticeWatchItem, ...]
    total_item_count: int
    offset: int
    notification_id: str | None
    baseline_domains: tuple[str, ...]
    continuing_domains: tuple[str, ...]
    notes: tuple[str, ...] = PUBLIC_NOTICE_WATCH_NOTES
    attribution: str = HIBP_ATTRIBUTION
    license: str = HIBP_LICENSE
    source_name: str = HIBP_SOURCE_NAME
    source_url: str = HIBP_SOURCE_URL


@dataclass(frozen=True, slots=True)
class PublicNoticeWatchChangeEvidence:
    watch_id: str
    organization_id: str
    organization_name: str
    run_id: str
    source_run_id: str
    previous_source_run_id: str | None
    recorded_at: str
    scope_sha256: str
    scope: PublicNoticeWatchScope
    matched_count: int
    baseline_count: int
    added_count: int
    updated_count: int
    removed_count: int
    items: tuple[PublicNoticeWatchItem, ...]
    total_item_count: int
    has_more: bool
    attribution: str = HIBP_ATTRIBUTION
    license: str = HIBP_LICENSE
    notes: tuple[str, ...] = PUBLIC_NOTICE_WATCH_NOTES


@dataclass(frozen=True, slots=True)
class PublicNoticeWatchComparison:
    items: tuple[PublicNoticeWatchItem, ...]
    baseline_domains: tuple[str, ...]
    continuing_domains: tuple[str, ...]
    matched_count: int
    baseline_count: int
    added_count: int
    updated_count: int
    removed_count: int
    unchanged_count: int


def compare_public_notice_watch(previous_notices, current_notices, *, scope: PublicNoticeWatchScope,
                                previous_scope: PublicNoticeWatchScope | None,
                                same_watch_epoch: bool) -> PublicNoticeWatchComparison:
    """Domain continuity follows explicit activation epochs, never labels or dates."""
    from xti.domain.public_notices import notice_sha256
    members = {member.domain: member for member in scope.members} if scope.organization_active else {}
    previous_members = ({member.domain: member for member in previous_scope.members}
                        if previous_scope is not None and previous_scope.organization_active
                        and same_watch_epoch
                        and previous_scope.organization_epoch_event_id == scope.organization_epoch_event_id else {})
    continuing = {domain for domain, member in members.items()
                  if domain in previous_members
                  and (member.link_id, member.epoch_event_id)
                  == (previous_members[domain].link_id, previous_members[domain].epoch_event_id)}
    baseline = set(members) - continuing
    current = {key: notice for key, notice in current_notices.items() if notice.domain in members}
    previous = {key: notice for key, notice in previous_notices.items() if notice.domain in continuing}
    items = []
    counts = dict(baseline=0, added=0, updated=0, removed=0, unchanged=0)
    for identifier, notice in current.items():
        before = previous_notices.get(identifier)
        if notice.domain in baseline:
            action, before = 'baseline', None
        elif identifier not in previous:
            action = 'added'
        else:
            action = 'unchanged' if notice_sha256(previous[identifier]) == notice_sha256(notice) else 'updated'
        counts[action] += 1
        items.append(PublicNoticeWatchItem(identifier, action, notice.domain, before, notice))
    removed = previous.keys() - current.keys()
    removed |= {identifier for identifier in previous.keys() & current.keys()
                if current[identifier].domain in baseline}
    for identifier in removed:
        notice = previous[identifier]
        counts['removed'] += 1
        items.append(PublicNoticeWatchItem(identifier, 'removed', notice.domain,
                                          notice, current_notices.get(identifier)))
    priority = {'added': 0, 'updated': 1, 'baseline': 2, 'removed': 3, 'unchanged': 4}
    items.sort(key=lambda item: (priority[item.action], item.domain, item.notice_id))
    return PublicNoticeWatchComparison(tuple(items), tuple(sorted(baseline)), tuple(sorted(continuing)),
                                       len(current), *(counts[key] for key in ('baseline', 'added', 'updated', 'removed', 'unchanged')))
