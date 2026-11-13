"""Explicit passive collection plans and source-bound results."""

from dataclasses import dataclass

from xti.domain.analysis import UnifiedAnalysisReport
from xti.domain.cti_feeds import CtiFeedRun
from xti.domain.jobs import ScanAttempt
from xti.domain.surface import SurfaceDiscoveryResult


@dataclass(frozen=True, slots=True)
class CollectionTask:
    id: str
    kind: str
    source: str
    label: str


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
)
COLLECTION_TASK_IDS = tuple(task.id for task in COLLECTION_TASKS)
DEFAULT_COLLECTION_TASKS = COLLECTION_TASK_IDS[:3]


@dataclass(frozen=True, slots=True)
class CollectionPlan:
    asset_value: str
    typos: bool
    tasks: tuple[CollectionTask, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CollectionStep:
    task: CollectionTask
    status: str
    attempt: ScanAttempt | None = None
    discovery: SurfaceDiscoveryResult | None = None
    feed: CtiFeedRun | None = None


@dataclass(frozen=True, slots=True)
class CollectionResult:
    plan: CollectionPlan
    started_at: str
    finished_at: str
    status: str
    steps: tuple[CollectionStep, ...]
    analysis: UnifiedAnalysisReport
