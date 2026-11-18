"""Saved surface/IOC/CTI evidence, selected workspace, one read transaction."""

from contextlib import contextmanager
from datetime import datetime
import ipaddress
from pathlib import Path

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_context import _audit_assertion_history
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_research_surface import StoredSurfaceLinks
from xti.adapters.sqlite_warninglists import read_warninglists
from xti.adapters.sqlite_enrichment import read_enrichment
from xti.domain.indicator_enrichment import enrichment_query, request_url
from xti.domain.assets import normalize_domain
from xti.domain.cti_attack import ATTACK_SOURCE_NAME
from xti.domain.cti_feeds import CTI_FEED_POLICIES, feed_indicator_state_sha256
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.research import ResearchEdge, ResearchEvidence, ResearchNode, identity
from xti.domain.research_surface import tls_check_evidence
from xti.domain.warninglists import match_data


MAX_DNS_CHECKS = 1000
MAX_DNS_BYTES = 16 * 1024 * 1024
MAX_RELATIONS_PER_NODE = 200
MAX_AUDIT_ROWS = 20_000
MAX_ASSERTIONS = 1000
MAX_EVENTS = 10_000
MAX_SHOWN_SOURCES = 50


def _reference(kind, record_type, namespace, identifier):
    return dict(kind=kind, record_type=record_type, namespace=namespace, record_id=identifier)


def _dns_evidence(check):
    result = check.result
    return ResearchEvidence(
        "surface_check", check.id, "surface-web", check.id, "observation",
        result.dns_status, result.finished_at, check.recorded_at,
        "; ".join((f"DNS: {result.dns_status}; politika: {result.policy_version}", *result.errors)),
        state_sha256=check.state_sha256,
        first_observed_at=result.finished_at,
    )


class SQLiteResearchRepository:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def open(self, query, checked_at):
        with SQLiteAssetRepository(self.path)._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            reader = _Reader(self.path, connection, checked_at)
            yield reader
            if reader.audit_attack:
                reader.knowledge._audit_attack_source(connection)
            connection.rollback()


class _Reader:
    def __init__(self, path, connection, checked_at):
        self.connection, self.checked_at = connection, checked_at
        self.knowledge = SQLiteCtiKnowledgeRepository(path)
        self.indicators = SQLiteCtiIndicatorRepository(path)
        self.limitations, self.coverage = set(), []
        self.nodes, self.indicator_ids, self.edges = {}, {}, {}
        self.checks, self.dns_scopes, self.dns_latest = {}, {}, {}
        self.audit_rows, self.dns_bytes, self.audit_attack = 0, 0, False
        self.warninglists = read_warninglists(connection)
        self.enrichment_edges = {}
        self.surface_links = StoredSurfaceLinks(connection, web_checks=self._web_checks,
            limitations=self.limitations, coverage=self.coverage)

    def _claims(self, kind, identifier):
        # The kind is internal, never a request SQL fragment. Bound histories
        # BEFORE calling existing decoders, then replay their original events.
        table = {"indicator": "indicator_id", "entity": "entity_id", "relationship": "relationship_id"}[kind]
        counts = self.connection.execute(
            f"SELECT (SELECT COUNT(*) FROM cti_{kind}_assertions WHERE {table}=?), "
            f"(SELECT COUNT(*) FROM cti_{kind}_assertion_events e JOIN cti_{kind}_assertions a "
            f"ON a.id=e.assertion_id WHERE a.{table}=?)", (identifier, identifier),
        ).fetchone()
        self.audit_rows += sum(counts)
        if counts[0] > MAX_ASSERTIONS or counts[1] > MAX_EVENTS or self.audit_rows > MAX_AUDIT_ROWS:
            raise StorageError("Araştırmanın kaynak geçmişi doğrulama sınırı aşıldı; doğrulanmamış kanıt sunulmadı.")
        if kind == "indicator":
            row = self.indicators._select_indicator(self.connection, identifier)
            if row is None:
                raise StorageError("Araştırmanın IOC bağlantısı eksik.")
            details = self.indicators._details(self.connection, row,
                                               assertion_limit=MAX_ASSERTIONS, event_limit=MAX_EVENTS)
        else:
            method = self.knowledge._entity_details if kind == "entity" else self.knowledge._relationship_details
            details = method(self.connection, identifier, MAX_ASSERTIONS, MAX_EVENTS)
        if not details.assertions:
            raise StorageError("Araştırmanın kaynak iddiası eksik.")
        _audit_assertion_history(self.connection, details, kind)
        self.audit_attack |= any(item.source_name == ATTACK_SOURCE_NAME for item in details.assertions)
        last_events = {}
        for event in details.events:
            last_events.setdefault(event.assertion_id, event)
        claims = []
        for item in sorted(details.assertions, key=lambda claim: (claim.source_name, claim.source_reference, claim.id)):
            source_run_id = None
            if kind == "indicator" and any(policy.source_name == item.source_name for policy in CTI_FEED_POLICIES.values()):
                event = last_events[item.id]
                digest = feed_indicator_state_sha256(
                    indicator_type=details.indicator.indicator_type, value=details.indicator.value,
                    source_reference=item.source_reference, confidence=event.confidence,
                    description=event.description, valid_from=event.valid_from, last_seen_at=event.observed_at)
                receipts = self.connection.execute(
                    "SELECT i.run_id FROM cti_feed_run_items i JOIN cti_feed_runs r ON r.id=i.run_id "
                    "WHERE i.assertion_id=? AND i.recorded_at=? AND r.source_name=? "
                    "AND r.status='complete' AND i.action=? AND i.state_sha256=? LIMIT 2",
                    (item.id, event.recorded_at, item.source_name, event.action, digest),
                ).fetchall()
                # An operator may revoke a feed assertion locally; that event
                # has no feed run. Keep the event reference, never invent a run.
                if len(receipts) == 1:
                    source_run_id = receipts[0][0]
            current = self.indicators._is_current(item, self.checked_at) if kind == "indicator" else item.active
            status = "active" if current else "revoked" if not item.active else (
                "not_yet_valid" if item.valid_from and
                datetime.fromisoformat(item.valid_from) > datetime.fromisoformat(self.checked_at) else "expired")
            claims.append(ResearchEvidence(
                "cti_" + kind, identifier, item.source_name, item.source_reference,
                "source_claim", status, item.last_seen_at, item.updated_at, item.description,
                item.id, last_events[item.id].id, item.confidence, current,
                getattr(item, "valid_from", None), getattr(item, "valid_until", None),
                first_observed_at=item.first_seen_at, source_run_id=source_run_id,
            ))
        if len(claims) > MAX_SHOWN_SOURCES:
            self.limitations.add("source_evidence_limit")
        return details, tuple(claims[:MAX_SHOWN_SOURCES])

    def _load_check(self, row):
        identifier, asset_id, domain, size = row
        if identifier in self.checks:
            return self.checks[identifier]
        if len(self.checks) >= MAX_DNS_CHECKS or self.dns_bytes + size > MAX_DNS_BYTES:
            self.limitations.add("dns_read_budget")
            return None
        self.dns_bytes += size
        stored = self.connection.execute(
            "SELECT id,asset_id,?,result,state_sha256,change,recorded_at FROM surface_checks WHERE id=?",
            (domain, identifier),
        ).fetchone()
        check = SQLiteSurfaceRepository._check(stored, domain)
        if normalize_domain(domain) != domain or check.asset_id != asset_id:
            raise StorageError("Araştırmanın DNS varlık bağlantısı tutarsız.")
        scope = SQLiteSurfaceRepository._scope_row(self.connection, asset_id)
        if scope is None or SQLiteSurfaceRepository._scope(scope).asset_value != domain:
            raise StorageError("Araştırmanın DNS kapsam kaydı eksik veya tutarsız.")
        self.checks[identifier] = check
        return check

    def _dns(self, domain=None):
        if domain in self.dns_scopes:
            return self.dns_scopes[domain]
        where, values = ("WHERE a.value=?", (domain,)) if domain else ("", ())
        rows = self.connection.execute(
            "SELECT s.id,s.asset_id,a.value,LENGTH(CAST(s.result AS BLOB))+LENGTH(CAST(s.change AS BLOB)) "
            "FROM surface_checks s LEFT JOIN assets a ON a.id=s.asset_id " + where +
            " ORDER BY s.rowid DESC LIMIT ?", (*values, MAX_DNS_CHECKS + 1),
        ).fetchall()
        if len(rows) > MAX_DNS_CHECKS:
            self.limitations.add("dns_history_window")
        checks = []
        self.dns_latest[domain] = None
        for index, row in enumerate(rows[:MAX_DNS_CHECKS]):
            check = self._load_check(row)
            if index == 0:
                self.dns_latest[domain] = check
            if check is not None:
                checks.append(check)
        self.coverage.append({"kind": "dns", "scope": domain or "workspace_recent_checks",
            "examined_count": len(checks), "window_limit": MAX_DNS_CHECKS,
            "complete": len(rows) <= MAX_DNS_CHECKS and len(checks) == len(rows),
            "order": "stored_newest_first"})
        self.dns_scopes[domain] = tuple(checks)
        return tuple(checks)

    def _web_checks(self, domain=None):
        checks = self._dns(domain)
        if domain is not None:
            return checks
        # Global reverse lookup shares the existing count/byte budget. Keep
        # already decoded root observations even outside the recent window.
        return tuple({check.id: check for check in (*checks, *self.checks.values())}.values())

    def node(self, key):
        if key in self.nodes:
            return self.nodes[key]
        kind, value = key
        if kind == "certificate":
            result = self.surface_links.certificate_node(key)
            self.nodes[key] = result
            return result
        references, evidence, evidence_total = [], [], 0
        label, record_type = value, kind
        if kind == "entity":
            details, claims = self._claims("entity", value)
            label, record_type = details.entity.display_name, details.entity.entity_type
            references.append(_reference("cti", record_type, "local-cti", value))
            evidence.extend(claims)
            evidence_total += details.total_assertion_count
        else:
            if kind == "domain":
                row = self.connection.execute("SELECT id FROM assets WHERE value=?", (value,)).fetchone()
                if row:
                    normalize_knowledge_id(row[0])
                    references.append(_reference("domain", "registered_domain", "local-assets", row[0]))
                # Only the latest check is attached to a node; all selected
                # positive DNS observations belong to the corresponding edges.
                self._dns(value)
                latest = self.dns_latest[value]
                if latest is not None:
                    evidence.append(_dns_evidence(latest))
                    evidence_total += 1
                    if latest.result.tls_status != "not_checked":
                        evidence.append(tls_check_evidence(latest))
                        evidence_total += 1
                cname = self.surface_links.latest_cname_evidence(value)
                if cname is not None:
                    evidence.append(cname)
                    evidence_total += 1
            row = self.connection.execute(
                "SELECT id FROM cti_indicators WHERE indicator_type=? AND value=?", key,
            ).fetchone()
            if row:
                details, claims = self._claims("indicator", row[0])
                if (details.indicator.indicator_type, details.indicator.value) != key:
                    raise StorageError("Araştırmanın IOC tipi/değeri tutarsız.")
                self.indicator_ids[key] = row[0]
                references.append(_reference("indicator", kind, "local-ioc", row[0]))
                evidence.extend(claims)
                evidence_total += details.total_assertion_count
        enrichment = None
        if kind in {"url", "md5", "sha1", "sha256"}:
            enrichment = read_enrichment(self.connection, enrichment_query(indicator_type=kind, value=value))
            latest, good, snapshot = enrichment.latest_run, enrichment.successful_run, enrichment.snapshot
            if latest:
                evidence.append(ResearchEvidence("enrichment_run", latest.id, latest.provider,
                    request_url(enrichment.query), "source_context", latest.status, latest.finished_at,
                    latest.finished_at, latest.error or "Kaynak sorgusu yanıtı; alınma tarihi kaynak gözlem tarihi değildir.",
                    state_sha256=latest.snapshot_sha256, source_run_id=latest.id, time_basis="response_received_at"))
                evidence_total += 1
            if snapshot:
                if snapshot.has_more:
                    self.limitations.add("enrichment_result_window")
                for record in snapshot.records:
                    claim = ResearchEvidence("enrichment_run", good.id, good.provider, record["reference"],
                        "source_context", "matched", record["observed_at"] or good.finished_at, good.finished_at,
                        record["description"], state_sha256=good.snapshot_sha256, source_run_id=good.id,
                        time_basis="source_observation" if record["observed_at"] else "response_received_at")
                    for link in record["relationships"]:
                        source = (link["source_type"], link["source_value"])
                        target = (link["target_type"], link["target_value"])
                        edge_id = "enrich:" + identity(good.id, record["id"], link)
                        self.enrichment_edges[edge_id] = ResearchEdge(edge_id, source, target,
                            link["relationship_type"], "source_context", (claim,), 1)
        # Frozen review v1 permits 52 evidence rows per item. Preserve latest
        # check states first; expose omitted claims with their true total.
        if len(evidence) > 52:
            self.limitations.add("source_evidence_limit")
        result = ResearchNode(key, label, record_type, tuple(references), tuple(evidence[:52]), evidence_total,
                              tuple(match_data(self.warninglists, kind, value)), enrichment)
        self.nodes[key] = result
        return result

    def _dns_edges(self, key):
        if key[0] not in {"domain", "ipv4", "ipv6"}:
            return ()
        checks = self._dns(key[1] if key[0] == "domain" else None)
        grouped = {}
        for check in checks:
            result = check.result
            if result.dns_status != "resolved":
                continue
            for address in result.addresses:
                ip = ipaddress.ip_address(address)
                source, target = ("domain", result.domain), (f"ipv{ip.version}", ip.compressed)
                if key not in (source, target):
                    continue
                pair = (source, target)
                if pair not in grouped and len(grouped) >= MAX_RELATIONS_PER_NODE:
                    self.limitations.add("dns_adjacency_limit")
                    continue
                grouped.setdefault(pair, []).append(_dns_evidence(check))
        edges = []
        for (source, target), evidence in sorted(grouped.items()):
            if len(evidence) > MAX_SHOWN_SOURCES:
                self.limitations.add("source_evidence_limit")
            edges.append(ResearchEdge("dns:" + identity(source, target), source, target,
                                      "dns_address", "observation", tuple(evidence[:MAX_SHOWN_SOURCES]), len(evidence)))
        return tuple(edges)

    def neighbors(self, key):
        self.node(key)
        edges = list(self._dns_edges(key))
        edges.extend(self.surface_links.cname_edges(key))
        edges.extend(self.surface_links.certificate_edges(key))
        edges.extend(edge for edge in self.enrichment_edges.values() if key in (edge.source, edge.target))
        if key[0] == "entity":
            where, values = "source_entity_id=? OR target_entity_id=?", (key[1], key[1])
        elif key in self.indicator_ids:
            where, values = "target_indicator_id=?", (self.indicator_ids[key],)
        else:
            return tuple(edges)
        rows = self.connection.execute(
            "SELECT id FROM cti_relationships WHERE " + where + " ORDER BY id LIMIT ?",
            (*values, MAX_RELATIONS_PER_NODE + 1),
        ).fetchall()
        if len(rows) > MAX_RELATIONS_PER_NODE:
            self.limitations.add("cti_adjacency_limit")
        self.coverage.append({"kind": "cti", "scope": list(key),
            "examined_count": min(len(rows), MAX_RELATIONS_PER_NODE),
            "window_limit": MAX_RELATIONS_PER_NODE, "complete": len(rows) <= MAX_RELATIONS_PER_NODE,
            "order": "record_id"})
        for (identifier,) in rows[:MAX_RELATIONS_PER_NODE]:
            if identifier not in self.edges:
                details, claims = self._claims("relationship", identifier)
                relation = details.summary.relationship
                if relation.target_kind == "entity":
                    target = ("entity", relation.target_entity_id)
                else:
                    row = self.indicators._select_indicator(self.connection, relation.target_indicator_id)
                    if row is None:
                        raise StorageError("Araştırma ilişkisinin IOC hedefi eksik.")
                    indicator = self.indicators._indicator(row)
                    target = (indicator.indicator_type, indicator.value)
                self.edges[identifier] = ResearchEdge("cti:" + identifier,
                    ("entity", relation.source_entity_id), target,
                    relation.relationship_type, "source_claim", claims, details.total_assertion_count)
            edges.append(self.edges[identifier])
        return tuple(edges)
