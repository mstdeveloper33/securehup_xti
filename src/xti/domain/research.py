"""Bounded evidence paths; adjacency is not attribution or a risk verdict."""

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import re

from xti.domain.assets import ValidationError
from xti.domain.cti_context import context_query
from xti.domain.warninglists import WarninglistState, catalog_data


MAX_PATHS = 2000
Key = tuple[str, str]


def identity(*values) -> str:
    return hashlib.sha256(json.dumps(values, ensure_ascii=True, sort_keys=True,
                                    separators=(",", ":")).encode("ascii")).hexdigest()


def node_id(key: Key) -> str:
    return "node:" + identity(*key)


class ResearchSnapshotChanged(ValidationError):
    pass


@dataclass(frozen=True, slots=True)
class ResearchQuery:
    indicator_type: str
    value: str
    max_hops: int = 2
    node_limit: int = 100
    edge_limit: int = 200
    offset: int = 0
    limit: int = 50
    stale_after_hours: int = 24
    expected_snapshot: str | None = None


def research_query(*, indicator_type, value, max_hops=2, node_limit=100,
                   edge_limit=200, offset=0, limit=50, stale_after_hours=24,
                   expected_snapshot=None) -> ResearchQuery:
    if indicator_type not in ("domain", "ip", "ipv4", "ipv6"):
        raise ValidationError("Araştırma kökü domain veya kesin IPv4/IPv6 adresi olmalı.")
    root = context_query(indicator_type=indicator_type, value=value)
    for name, number, low, high in (
        ("Adım", max_hops, 1, 2), ("Düğüm", node_limit, 2, 100),
        ("Bağlantı", edge_limit, 1, 200), ("Başlangıç", offset, 0, 1_000_000),
        ("Sayfa", limit, 1, 100), ("Güncellik saati", stale_after_hours, 1, 8760),
    ):
        if type(number) is not int or not low <= number <= high:
            raise ValidationError(f"{name} sınırı {low}–{high} arasında tamsayı olmalı.")
    if expected_snapshot is not None and (
        not isinstance(expected_snapshot, str) or re.fullmatch(r"[0-9a-f]{64}", expected_snapshot) is None
    ):
        raise ValidationError("Araştırma kesit kimliği 64 küçük onaltılık karakter olmalı.")
    return ResearchQuery(root.indicator_type, root.value, max_hops, node_limit,
                         edge_limit, offset, limit, stale_after_hours, expected_snapshot)


@dataclass(frozen=True, slots=True)
class ResearchEvidence:
    record_type: str
    record_id: str
    source: str
    source_reference: str
    kind: str
    status: str
    observed_at: str
    recorded_at: str
    description: str
    assertion_id: str | None = None
    event_id: str | None = None
    confidence: int | None = None
    current: bool | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    state_sha256: str | None = None
    first_observed_at: str | None = None
    source_run_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResearchNode:
    key: Key
    label: str
    record_type: str
    # Engine record.get references; DNS check references stay on evidence.
    references: tuple[dict, ...] = ()
    evidence: tuple[ResearchEvidence, ...] = ()
    evidence_total_count: int = 0
    warninglist_matches: tuple[dict, ...] = ()


@dataclass(frozen=True, slots=True)
class ResearchEdge:
    id: str
    source: Key
    target: Key
    relationship_type: str
    kind: str
    evidence: tuple[ResearchEvidence, ...]
    evidence_total_count: int = 0


@dataclass(frozen=True, slots=True)
class ResearchReport:
    query: ResearchQuery
    checked_at: str
    snapshot_id: str
    status: str
    root_id: str
    nodes: tuple[ResearchNode, ...]
    edges: tuple[ResearchEdge, ...]
    paths: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]
    collected_node_count: int
    collected_edge_count: int
    collected_path_count: int
    has_more: bool
    limitations: tuple[str, ...]
    coverage: tuple[dict, ...]
    warninglists: tuple[WarninglistState, ...]


def build_research(reader, query: ResearchQuery, checked_at: str) -> ResearchReport:
    """One snapshot reader, breadth-first bounds, stable simple paths without cycles."""
    root = (query.indicator_type, query.value)
    nodes = {root: reader.node(root)}
    edges, limitations = {}, set()
    frontier = [root]
    for _ in range(query.max_hops):
        following = set()
        for key in sorted(frontier):
            for edge in sorted(reader.neighbors(key), key=lambda item: item.id):
                if key not in (edge.source, edge.target):
                    raise ValidationError("Araştırma deposu istenen düğüm dışında ilişki döndürdü.")
                if edge.id in edges:
                    continue
                other = edge.target if edge.source == key else edge.source
                if other not in nodes and len(nodes) >= query.node_limit:
                    limitations.add("node_limit")
                    continue
                if len(edges) >= query.edge_limit:
                    limitations.add("edge_limit")
                    continue
                if other not in nodes:
                    nodes[other] = reader.node(other)
                    following.add(other)
                edges[edge.id] = edge
        frontier = sorted(following)
        if not frontier:
            break
    for key, node in nodes.items():
        if node.key != key:
            raise ValidationError("Araştırma deposu farklı düğüm kapsamı döndürdü.")
    adjacency = {key: [] for key in nodes}
    for edge in edges.values():
        adjacency[edge.source].append((edge.target, edge.id))
        if edge.source != edge.target:
            adjacency[edge.target].append((edge.source, edge.id))
    paths, frontier_paths = [], [((root,), ())]
    for _ in range(query.max_hops):
        following = []
        for keys, links in frontier_paths:
            for target, edge_id in sorted(adjacency[keys[-1]]):
                if target in keys:
                    continue
                if len(paths) >= MAX_PATHS:
                    limitations.add("path_limit")
                    break
                path = (keys + (target,), links + (edge_id,))
                paths.append(path)
                following.append(path)
            if "path_limit" in limitations:
                break
        frontier_paths = following
        if "path_limit" in limitations:
            break
    limitations.update(reader.limitations)
    coverage = tuple(reader.coverage)
    snapshot = identity(
        "research-v1", root, query.max_hops, query.node_limit, query.edge_limit,
        [asdict(nodes[key]) for key in sorted(nodes)],
        [asdict(edges[key]) for key in sorted(edges)], sorted(limitations), coverage,
        catalog_data(reader.warninglists, checked_at=checked_at),
    )
    if query.expected_snapshot is not None and query.expected_snapshot != snapshot:
        raise ResearchSnapshotChanged("Araştırma kayıtları değişti; ilk sayfadan yeniden başlayın.")
    shown = paths[query.offset:query.offset + query.limit]
    selected_nodes, selected_edges = {root}, set()
    for keys, links in shown:
        selected_nodes.update(keys)
        selected_edges.update(links)
    status = ("partial" if limitations else "related_records" if edges else
              "no_relationships" if nodes[root].references or nodes[root].evidence else "not_recorded")
    return ResearchReport(
        query, checked_at, snapshot, status, node_id(root),
        tuple(nodes[key] for key in sorted(selected_nodes)),
        tuple(edges[key] for key in sorted(selected_edges)),
        tuple((tuple(node_id(key) for key in keys), links) for keys, links in shown),
        len(nodes), len(edges), len(paths), query.offset + len(shown) < len(paths),
        tuple(sorted(limitations)), coverage, reader.warninglists,
    )


def freshness(observed_at: str, checked_at: str, hours: int) -> str:
    age = (datetime.fromisoformat(checked_at) - datetime.fromisoformat(observed_at)).total_seconds()
    return "future" if age < 0 else "stale" if age > hours * 3600 else "fresh"
