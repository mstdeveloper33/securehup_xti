"""Bounded, audited passive candidates in the parent research read transaction."""

from datetime import datetime

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.domain.assets import ValidationError
from xti.domain.research import ResearchEdge, identity
from xti.domain.research_discovery import (
    discovery_decision, discovery_source, discovery_state, validate_discovery_history,
)


MAX_DISCOVERY_CANDIDATES = 200
MAX_DISCOVERY_AUDIT_ROWS = 10_000
MAX_DISCOVERY_AUDIT_BYTES = 16 * 1024 * 1024
MAX_DISCOVERY_DECISIONS = 1000  # Existing candidate detail reader's limit.
MAX_DISCOVERY_EVIDENCE = 50


def _stored_bytes(*columns):
    # Internal SQL identifiers only. Count all stored text, including fields
    # that a corrupted database could enlarge beyond decoder constraints.
    return "+".join(f"COALESCE(LENGTH(CAST({column} AS BLOB)),0)" for column in columns) + "+256"


_SOURCE_BYTES = _stored_bytes("id", "candidate_id", "provider", "source_name", "source_sha256",
                              "raw_domain", "observed_at", "recorded_at")
_EVENT_BYTES = _stored_bytes("id", "candidate_id", "action", "status", "reason", "created_at")
_STATE_BYTES = _stored_bytes("c.id", "c.asset_id", "c.asset_value", "c.domain", "c.status", "c.reason",
                             "c.first_seen_at", "c.last_seen_at", "c.created_at", "c.updated_at", "a.value")


class StoredDiscoveryLinks:
    def __init__(self, connection, *, limitations, coverage):
        self.connection, self.limitations, self.coverage = connection, limitations, coverage
        self.candidates, self.selections = {}, {}
        self.audit_rows, self.audit_bytes = 0, 0

    def _candidate(self, identifier):
        if identifier in self.candidates:
            return self.candidates[identifier]
        sources, source_bytes = self.connection.execute(
            f"SELECT COUNT(*),COALESCE(SUM({_SOURCE_BYTES}),0) "
            "FROM surface_candidate_sources WHERE candidate_id=?",
            (identifier,),
        ).fetchone()
        events, event_bytes = self.connection.execute(
            f"SELECT COUNT(*),COALESCE(SUM({_EVENT_BYTES}),0) "
            "FROM surface_candidate_events WHERE candidate_id=?", (identifier,),
        ).fetchone()
        state = self.connection.execute(
            f"SELECT {_STATE_BYTES} FROM surface_candidates c LEFT JOIN assets a ON a.id=c.asset_id "
            "WHERE c.id=?", (identifier,),
        ).fetchone()
        if state is None:
            raise StorageError("Araştırmanın pasif alt alan adayı bulunamadı.")
        rows, size = 1 + sources + events, state[0] + source_bytes + event_bytes
        self.candidates[identifier] = None
        if (events > MAX_DISCOVERY_DECISIONS or self.audit_rows + rows > MAX_DISCOVERY_AUDIT_ROWS or
            self.audit_bytes + size > MAX_DISCOVERY_AUDIT_BYTES):
            self.limitations.add("discovery_read_budget")
            return None
        self.audit_rows += rows
        self.audit_bytes += size
        try:
            details = SQLiteSurfaceCandidateRepository._details(self.connection, identifier, source_limit=sources)
            candidate = details.candidate
            stored = self.connection.execute(
                "SELECT asset_value,domain FROM surface_candidates WHERE id=?", (identifier,),
            ).fetchone()
            if stored != (candidate.asset_value, candidate.domain):
                raise ValidationError("Pasif adayın domain/kök kimliği kanonik değil.")
            validate_discovery_history(details)
        except (ValueError, TypeError, OverflowError) as error:
            raise StorageError("Pasif adayın kayıtlı kanıt/karar bağlantısı bozuk; işlem durduruldu.") from error
        self.candidates[identifier] = details
        return details

    def _entries(self, key):
        if key[0] != "domain":
            return ()
        if key in self.selections:
            return self.selections[key]
        value = key[1]
        # No suffix guess: only an explicit stored root/candidate relationship.
        # The actual root asset also selects corrupted projections for audit.
        rows = self.connection.execute(
            "SELECT c.id FROM surface_candidates c LEFT JOIN assets a ON a.id=c.asset_id "
            "WHERE c.asset_value=? OR a.value=? OR c.domain=? ORDER BY c.domain,c.id LIMIT ?",
            (value, value, value, MAX_DISCOVERY_CANDIDATES + 1),
        ).fetchall()
        complete = len(rows) <= MAX_DISCOVERY_CANDIDATES
        if not complete:
            self.limitations.add("discovery_candidate_limit")
        selected = tuple(details for (identifier,) in rows[:MAX_DISCOVERY_CANDIDATES]
                         if (details := self._candidate(identifier)) is not None)
        self.coverage.append({"kind": "surface_candidates", "scope": list(key),
            "examined_count": len(selected), "window_limit": MAX_DISCOVERY_CANDIDATES,
            "complete": complete and len(selected) == len(rows), "order": "domain_record_id"})
        self.selections[key] = selected
        return selected

    def references(self, key):
        return tuple({"kind": "domain", "record_type": "surface_candidate", "namespace": "passive-discovery",
                      "record_id": item.candidate.id} for item in self._entries(key) if item.candidate.domain == key[1])

    def _shown(self, rows):
        if len(rows) > MAX_DISCOVERY_EVIDENCE:
            self.limitations.add("source_evidence_limit")
        return tuple(rows[:MAX_DISCOVERY_EVIDENCE])

    def neighbors(self, key):
        edges = []
        for details in self._entries(key):
            candidate = details.candidate
            source, target = ("domain", candidate.asset_value), ("domain", candidate.domain)
            prefix = "passive:" + identity(candidate.id)
            # New human decisions and duplicate archive results do not refresh
            # the original source observation time.
            sources = sorted(details.sources, key=lambda row: (
                datetime.fromisoformat(row.observed_at or row.recorded_at),
                datetime.fromisoformat(row.recorded_at), row.id), reverse=True)
            evidence = [discovery_state(candidate), *(discovery_source(row) for row in sources)]
            edges.append(ResearchEdge(prefix + ":0", source, target, "passive_subdomain",
                "candidate_context", self._shown(evidence), len(evidence)))
            decisions = details.events[1:]  # Automatic 'discovered' isn't a human decision.
            if decisions:
                evidence = [discovery_decision(row, current=row == decisions[-1]) for row in reversed(decisions)]
                edges.append(ResearchEdge(prefix + ":1", source, target, "subdomain_classification",
                    "human_decision", self._shown(evidence), len(evidence)))
        return tuple(edges)
