"""Scoped, bounded supplier histories in the research reader's transaction."""

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_supplier_candidates import SQLiteSupplierCandidateRepository
from xti.adapters.sqlite_supplier_history import read_supplier_history
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.domain.research import ResearchEdge, ResearchNode, identity
from xti.domain.research_suppliers import (
    candidate_evidence, candidate_state, resolution_evidence, supplier_evidence, supplier_link_events,
)


MAX_SUPPLIER_ADJACENCY = 200
MAX_SUPPLIER_AUDIT_ROWS = 10_000
MAX_SUPPLIER_AUDIT_BYTES = 16 * 1024 * 1024
MAX_SHOWN_EVIDENCE = 50


class StoredSupplierLinks:
    def __init__(self, path, connection, *, limitations, coverage):
        self.connection, self.limitations, self.coverage = connection, limitations, coverage
        self.repository = SQLiteSupplierCandidateRepository(path)
        self.candidates, self.suppliers, self.adjacency = {}, {}, {}
        self.audit_rows, self.audit_bytes = 0, 0

    def _reserve(self, rows, size):
        if (self.audit_rows + rows > MAX_SUPPLIER_AUDIT_ROWS or
            self.audit_bytes + size > MAX_SUPPLIER_AUDIT_BYTES):
            self.limitations.add("supplier_read_budget")
            return False
        self.audit_rows += rows
        self.audit_bytes += size
        return True

    def _candidate(self, identifier):
        if identifier in self.candidates:
            return self.candidates[identifier]
        # Count/size before the existing full candidate/source validation.
        # Including source JSON per reference is deliberately conservative.
        count, size = self.connection.execute(
            "SELECT COUNT(*),COALESCE(SUM(LENGTH(CAST(e.source_domain AS BLOB))+"
            "LENGTH(CAST(e.target_domain AS BLOB))+LENGTH(CAST(e.public_suffix_version AS BLOB))+512+"
            "COALESCE(LENGTH(CAST(c.result AS BLOB))+LENGTH(CAST(c.change AS BLOB)),0)),0) "
            "FROM supplier_candidate_evidence e LEFT JOIN surface_cname_checks c ON c.id=e.source_evidence_id "
            "WHERE e.candidate_id=?", (identifier,),
        ).fetchone()
        decisions, decision_bytes = self.connection.execute(
            "SELECT COUNT(*),COALESCE(SUM(LENGTH(CAST(reason AS BLOB))+256),0) "
            "FROM supplier_candidate_resolution_events WHERE candidate_id=?", (identifier,),
        ).fetchone()
        state_size = self.connection.execute(
            "SELECT LENGTH(CAST(asset_value AS BLOB))+LENGTH(CAST(candidate_domain AS BLOB))+"
            "COALESCE(LENGTH(CAST(resolution_reason AS BLOB)),0)+512 FROM supplier_candidates WHERE id=?",
            (identifier,),
        ).fetchone()
        if state_size is None:
            raise StorageError("Araştırmanın tedarikçi adayı bulunamadı.")
        self.candidates[identifier] = None
        if not self._reserve(1 + 2 * count + decisions, size + decision_bytes + state_size[0]):
            return None
        suppliers = self.connection.execute(
            "SELECT DISTINCT supplier_id FROM supplier_candidate_resolution_events "
            "WHERE candidate_id=? AND supplier_id IS NOT NULL ORDER BY supplier_id", (identifier,),
        ).fetchall()
        for (supplier_id,) in suppliers:
            if self._supplier(supplier_id) is None:
                return None
        details = self.repository._validated_details(self.connection, identifier)
        candidate = details.candidate
        scope = SQLiteSurfaceRepository._scope_row(self.connection, candidate.asset_id)
        if scope is None or SQLiteSurfaceRepository._scope(scope).asset_value != candidate.asset_value:
            raise StorageError("Araştırmanın tedarikçi adayı varlık/kapsam bağlantısı tutarsız.")
        self.candidates[identifier] = details
        return details

    def _supplier(self, identifier):
        if identifier in self.suppliers:
            return self.suppliers[identifier]
        count, size = self.connection.execute(
            "SELECT COUNT(*),COALESCE(SUM(LENGTH(CAST(reason AS BLOB))+"
            "LENGTH(CAST(display_name AS BLOB))+LENGTH(CAST(primary_domain AS BLOB))+256),0) "
            "FROM supplier_events WHERE supplier_id=?", (identifier,),
        ).fetchone()
        state_size = self.connection.execute(
            "SELECT LENGTH(CAST(display_name AS BLOB))+LENGTH(CAST(name_key AS BLOB))+"
            "LENGTH(CAST(primary_domain AS BLOB))+LENGTH(CAST(reason AS BLOB))+512 FROM suppliers WHERE id=?",
            (identifier,),
        ).fetchone()
        if state_size is None:
            raise StorageError("Araştırmanın tedarikçi kaydı bulunamadı.")
        self.suppliers[identifier] = None
        if not self._reserve(count + 1, size + state_size[0]):
            return None
        history = read_supplier_history(self.connection, supplier_id=identifier)
        self.suppliers[identifier] = (history.suppliers[identifier], history.events)
        return self.suppliers[identifier]

    def _shown(self, rows, limit=None):
        limit = MAX_SHOWN_EVIDENCE if limit is None else limit
        if len(rows) > limit:
            self.limitations.add("source_evidence_limit")
        return tuple(rows[:limit])

    def node(self, key):
        kind, identifier = key
        if kind == "supplier_candidate":
            details = self._candidate(identifier)
            if details is None:
                raise StorageError("Araştırmanın tedarikçi adayı doğrulanamadı.")
            candidate = details.candidate
            decisions = [resolution_evidence(event, current=event == details.resolutions[-1])
                         for event in reversed(details.resolutions)]
            sources = [candidate_evidence(item) for item in reversed(details.evidence)]
            # Preserve current state, latest human decision AND a technical
            # source before older histories compete for the 52-row envelope.
            rows = [candidate_state(candidate), *decisions[:1], *sources[:1], *decisions[1:], *sources[1:]]
            return ResearchNode(key, f"Tedarikçi adayı: {candidate.asset_value} → {candidate.candidate_domain}",
                "supplier_candidate", evidence=self._shown(rows, 52), evidence_total_count=len(rows))
        state = self._supplier(identifier)
        if state is None:
            raise StorageError("Araştırmanın tedarikçi kaydı doğrulanamadı.")
        supplier, events = state
        rows = [supplier_evidence(event, current=event == events[-1]) for event in reversed(events)]
        return ResearchNode(key, supplier.display_name, "supplier",
            references=({"kind": "supplier", "record_type": "supplier", "namespace": "local-suppliers",
                         "record_id": supplier.id},), evidence=self._shown(rows), evidence_total_count=len(rows))

    def _ids(self, kind, key, sql, values):
        rows = self.connection.execute(sql + " ORDER BY id LIMIT ?", (*values, MAX_SUPPLIER_ADJACENCY + 1)).fetchall()
        complete = len(rows) <= MAX_SUPPLIER_ADJACENCY
        if not complete:
            self.limitations.add("supplier_adjacency_limit")
        self.coverage.append({"kind": kind, "scope": list(key), "examined_count": min(len(rows), MAX_SUPPLIER_ADJACENCY),
            "window_limit": MAX_SUPPLIER_ADJACENCY, "complete": complete, "order": "record_id"})
        return [row[0] for row in rows[:MAX_SUPPLIER_ADJACENCY]]

    def _candidate_edges(self, details, key):
        candidate = details.candidate
        source, subject, target = ("domain", candidate.asset_value), ("supplier_candidate", candidate.id), ("domain", candidate.candidate_domain)
        if key in (source, subject):
            rows = (candidate_state(candidate),)
            yield ResearchEdge("candidate:" + identity(candidate.id), source, subject, "supplier_candidate",
                               "candidate_context", rows, len(rows))
        if key in (subject, target):
            rows = [candidate_evidence(item) for item in reversed(details.evidence)]
            yield ResearchEdge("candidate-root:" + identity(candidate.id), subject, target, "supplier_candidate_domain",
                               "candidate_context", self._shown(rows), len(rows))
        for supplier_id, transitions in supplier_link_events(details.resolutions).items():
            target = ("supplier", supplier_id)
            if key not in (source, target) or self._supplier(supplier_id) is None:
                continue
            rows = [resolution_evidence(event, current=index == len(transitions) - 1, status=status)
                    for index, (event, status) in reversed(tuple(enumerate(transitions)))]
            yield ResearchEdge("supplier-link:" + identity(candidate.id, supplier_id), source, target,
                "human_supplier_link", "human_decision", self._shown(rows), len(rows))

    def _inventory_edge(self, identifier):
        state = self._supplier(identifier)
        if state is None:
            return None
        supplier, events = state
        rows = [supplier_evidence(event, current=event == events[-1]) for event in reversed(events)]
        return ResearchEdge("supplier-domain:" + identity(identifier), ("supplier", identifier),
            ("domain", supplier.primary_domain), "supplier_registered_domain", "human_decision",
            self._shown(rows), len(rows))

    def neighbors(self, key):
        if key in self.adjacency:
            return self.adjacency[key]
        coverage_start = len(self.coverage)
        kind, value = key
        if kind == "domain":
            candidates = self._ids("supplier_candidates", key,
                "SELECT c.id AS id FROM supplier_candidates c LEFT JOIN assets a ON a.id=c.asset_id "
                "WHERE c.asset_value=? OR a.value=? OR c.candidate_domain=?", (value, value, value))
            suppliers = self._ids("suppliers", key, "SELECT id FROM suppliers WHERE primary_domain=?", (value,))
        elif kind == "supplier":
            candidates = self._ids("supplier_candidates", key,
                "SELECT c.id AS id FROM supplier_candidates c WHERE c.supplier_id=? OR EXISTS "
                "(SELECT 1 FROM supplier_candidate_resolution_events e WHERE e.candidate_id=c.id AND e.supplier_id=?)",
                (value, value))
            suppliers = [value]
        elif kind == "supplier_candidate":
            candidates, suppliers = [value], []
        else:
            return ()
        edges = []
        validated = {"supplier_candidates": 0, "suppliers": 0}
        for identifier in candidates:
            details = self._candidate(identifier)
            if details is not None:
                validated["supplier_candidates"] += 1
                edges.extend(self._candidate_edges(details, key))
        for identifier in suppliers:
            edge = self._inventory_edge(identifier)
            if edge is not None:
                validated["suppliers"] += 1
                edges.append(edge)
        for coverage in self.coverage[coverage_start:]:
            count = validated[coverage["kind"]]
            coverage["complete"] &= coverage["examined_count"] == count
            coverage["examined_count"] = count
        if len(edges) > MAX_SUPPLIER_ADJACENCY:
            self.limitations.add("supplier_adjacency_limit")
        self.adjacency[key] = tuple(sorted(edges, key=lambda edge: edge.id)[:MAX_SUPPLIER_ADJACENCY])
        return self.adjacency[key]
