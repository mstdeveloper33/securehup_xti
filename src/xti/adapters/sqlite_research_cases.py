"""Bounded case projection in the research reader's existing transaction."""

import json

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_cases import SQLiteCaseRepository, read_case_evidence_links
from xti.adapters.research_read_budget import ResearchReadBudget
from xti.domain.assets import ValidationError
from xti.domain.cases import canonical_snapshot
from xti.domain.research import ResearchEdge, ResearchNode, identity
from xti.domain.research_cases import case_decision, case_link_evidence, case_subjects


class StoredCaseContext:
    def __init__(self, connection, *, limitations, coverage):
        self.connection, self.limitations, self.coverage = connection, limitations, coverage
        self.nodes, self.edges, self.loaded = {}, (), False

    def load(self):
        if self.loaded:
            return
        self.loaded = True
        if not ResearchReadBudget(self.connection, self.limitations).admit(
                ('cases', 'case_evidence', 'case_activities'), 'case_read_budget'):
            return
        try:
            self._load()
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise StorageError('Araştırmanın vaka kanıtı veya karar geçmişi tutarsız.') from error

    def _load(self):
        links = read_case_evidence_links(self.connection)
        cases = {row[0]: SQLiteCaseRepository._case(row) for row in self.connection.execute(
            'SELECT id,title,summary,status,priority,resolution,created_at,updated_at,closed_at FROM cases')}
        histories = {identifier: [] for identifier in cases}
        link_events = {}
        for row in self.connection.execute('SELECT sequence,id,case_id,activity_type,reference_id,'
                'summary,reason,snapshot_json,snapshot_sha256,recorded_at FROM case_activities ORDER BY sequence'):
            event = SQLiteCaseRepository._activity(row)
            histories[event.case_id].append((event, json.loads(row[7])))
            if event.activity_type.startswith('evidence_'):
                link_events[event.reference_id] = event
        for identifier, case in cases.items():
            events = histories[identifier]
            lifecycle = [(event, payload) for event, payload in events
                         if event.activity_type in {'case_created', 'case_updated', 'status_changed'}]
            if not events or events[0][0].activity_type != 'case_created' or not lifecycle:
                raise ValueError('Missing case lifecycle')
            if canonical_snapshot(lifecycle[-1][1]) != canonical_snapshot(SQLiteCaseRepository._case_payload(case)):
                raise ValueError('Case state differs from lifecycle')
            last = lifecycle[-1][0].id
            evidence = [case_decision(event, current=event.id == last,
                status=payload['status'] if event.activity_type in {'case_created', 'case_updated', 'status_changed'} else event.activity_type)
                for event, payload in reversed(events) if not event.activity_type.startswith('evidence_')]
            if len(evidence) > 52:
                self.limitations.add('source_evidence_limit')
            self.nodes[('case', identifier)] = ResearchNode(('case', identifier), case.title, 'case',
                evidence=tuple(evidence[:52]), evidence_total_count=len(evidence))
        edges = []
        for link in links:
            if link.case_id not in cases:
                raise ValueError('Missing linked case')
            evidence = case_link_evidence(link, link_events[link.id])
            for subject in case_subjects(link):
                edges.append(ResearchEdge('case-link:' + identity(link.id, subject), subject,
                    ('case', link.case_id), 'case_evidence_link', 'human_decision', (evidence,), 1))
        self.edges = tuple(edges)

    def neighbors(self, key):
        self.load()
        selected = [edge for edge in self.edges if key in (edge.source, edge.target)]
        if len(selected) > 200:
            self.limitations.add('case_adjacency_limit')
        self.coverage.append(dict(kind='case', scope=list(key), examined_count=min(len(selected), 200),
            window_limit=200, complete=len(selected) <= 200 and 'case_read_budget' not in self.limitations,
            order='record_id'))
        return tuple(sorted(selected, key=lambda item: item.id)[:200])
