"""Explicit passive collection plans and source-bound results."""

from dataclasses import dataclass

from xti.domain.analysis import UnifiedAnalysisReport
from xti.domain.brand_username_watches import BrandUsernameWatchRunReport
from xti.domain.cti_feeds import CtiFeedRun
from xti.domain.jobs import ScanAttempt
from xti.domain.news import NewsRefreshReport
from xti.domain.global_saved_searches import GlobalSavedSearchRunReport
from xti.domain.public_notices import PublicNoticeRefreshReport
from xti.domain.ransomlook_ransomware import RansomLookClaimRunReport
from xti.domain.ransomlook_watches import RansomLookWatchRunReport
from xti.domain.ransomware_claims import RansomwareClaimRunReport
from xti.domain.ransomware_watches import RansomwareWatchRunReport
from xti.domain.surface import SurfaceDiscoveryResult


@dataclass(frozen=True, slots=True)
class CollectionWatchTarget:
    watch_id: str
    display_name: str
    query: str
    kind: str
    match_mode: str
    platforms: tuple[str, ...] = ()
    search_event_id: str | None = None
    revision: int | None = None


@dataclass(frozen=True, slots=True)
class CollectionTask:
    id: str
    kind: str
    source: str
    label: str
    watches: tuple[CollectionWatchTarget, ...] = ()


COLLECTION_TASKS = (
    CollectionTask("scan-crtsh", "scan", "crt.sh", "crt.sh marka araması"),
    CollectionTask("scan-urlscan", "scan", "urlscan", "urlscan marka araması"),
    CollectionTask("discover-crtsh", "discovery", "crt.sh", "crt.sh alt alan adı keşfi"),
    CollectionTask(
        "discover-theharvester", "discovery", "theharvester",
        "theHarvester arşivlerinde alt alan adı keşfi",
    ),
    CollectionTask("ioc-feodo", "ioc", "feodo", "Feodo Tracker IOC yenilemesi"),
    CollectionTask("ioc-certpl", "ioc", "certpl", "CERT Polska IOC yenilemesi"),
    CollectionTask("notices-hibp", "public_notice", "hibp", "HIBP kamu olay kataloğu yenilemesi"),
)
COLLECTION_TASK_IDS = tuple(task.id for task in COLLECTION_TASKS)
DEFAULT_COLLECTION_TASKS = COLLECTION_TASK_IDS[:3]


@dataclass(frozen=True, slots=True)
class CollectionPlan:
    asset_value: str
    typos: bool
    tasks: tuple[CollectionTask, ...]
    notes: tuple[str, ...]
    watch_item_limit: int = 100


@dataclass(frozen=True, slots=True)
class CollectionRansomwareResult:
    refresh: RansomwareClaimRunReport | RansomLookClaimRunReport
    watches: tuple[RansomwareWatchRunReport | RansomLookWatchRunReport, ...]
    skipped_watch_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CollectionStep:
    task: CollectionTask
    status: str
    attempt: ScanAttempt | None = None
    discovery: SurfaceDiscoveryResult | None = None
    feed: CtiFeedRun | None = None
    username: BrandUsernameWatchRunReport | None = None
    ransomware: CollectionRansomwareResult | None = None
    public_notices: PublicNoticeRefreshReport | None = None
    news: NewsRefreshReport | None = None
    search: GlobalSavedSearchRunReport | None = None
    social: dict | None = None


@dataclass(frozen=True, slots=True)
class CollectionResult:
    plan: CollectionPlan
    started_at: str
    finished_at: str
    status: str
    steps: tuple[CollectionStep, ...]
    analysis: UnifiedAnalysisReport
    session_id: str | None = None
