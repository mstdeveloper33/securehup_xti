"""Structured company content and conservative presentation state."""

from dataclasses import dataclass

from xti.domain.mentions import MENTION_NOTES, MentionHit, MentionTarget
from xti.domain.organization_report import OrganizationContentScope
from xti.domain.organizations import Organization


COMPANY_CONTENT_NOTES = (*MENTION_NOTES,
    "Kuruluş içerikleri kesin kuruluş kimliğiyle seçilir; aynı adlı bağımsız firma aramaları eklenmez.",
    "Güncel tedarikçi içerikleri yalnız etkin gruplarda açıkça seçilmiş etkin tedarikçi kimliklerinden gelir.",
    "Bağlantısı kaldırılmış tedarikçilerde yalnız bu kuruluşun tarihî grup kaynak kanıtları gösterilir.",
    "Eski isim/domain veya grup sorgu ayarı tarihî bölümde kalır; tarihî kapsam güncel başarı sayılmaz.",
    "İçerik toplamları gösterilen kapsam sayfasıyla daralmaz; kapsam ve içerik sayfaları ayrı ilerler.",
    "Görünüm kapsam başına son deneme/başarıyı ve korunan son içerik kanıtını gösterir.",
)


@dataclass(frozen=True, slots=True)
class CompanyContentItem:
    id: str
    target: MentionTarget
    request_key: str
    scope_status: str
    status: str
    hit: MentionHit
    matched_terms: tuple[str, ...]
    match_fields: tuple[str, ...]
    source_run_id: str
    last_seen_at: str


@dataclass(frozen=True, slots=True)
class CompanyContentPage:
    kind: str
    items: tuple[CompanyContentItem, ...]
    total_count: int
    offset: int
    limit: int
    has_more: bool


@dataclass(frozen=True, slots=True)
class CompanyContentSnapshot:
    organization: Organization
    # All scopes are needed to compute overall state before display pagination.
    scopes: tuple[OrganizationContentScope, ...]
    pages: tuple[CompanyContentPage, ...]
    notes: tuple[str, ...]
    monitored_content: dict | None = None
    brand_protection: dict | None = None
    cti_analysis: dict | None = None
    darkweb_monitoring: dict | None = None
    unified_monitoring: dict | None = None


def content_source_status(scope: OrganizationContentScope) -> str:
    attempt = scope.coverage.latest_attempt
    if attempt is None:
        return "uncollected"
    return {"complete": "success", "failed": "error"}.get(attempt.status, attempt.status)


def content_scope_state(scope: OrganizationContentScope) -> str:
    """A previous success never hides a failed or unresolved latest attempt."""
    source_status = content_source_status(scope)
    if source_status == "uncollected":
        return "not_checked"
    if source_status == "error":
        return "check_failed"
    if source_status not in {"success", "empty"}:
        return "outcome_unknown"
    if scope.coverage.freshness == "stale":
        return "stale"
    if scope.coverage.freshness != "current":
        return "outcome_unknown"
    return "no_content" if scope.latest_success_result_count == 0 else "content_found"


def company_content_state(snapshot: CompanyContentSnapshot) -> str:
    if not snapshot.organization.active:
        return "inactive"
    states = {content_scope_state(scope) for scope in snapshot.scopes if scope.scope_status == "current"}
    if not states:
        return "not_checked"
    if len(states) == 1:
        return next(iter(states))
    if states <= {"content_found", "no_content"}:
        return "content_found"
    return "partial"
