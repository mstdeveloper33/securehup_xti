"""Link decisions and extracted candidates in the existing research snapshot."""

from xti.adapters.sqlite_investigation import read_investigations, identity_read_tables
from xti.adapters.research_read_budget import ResearchReadBudget
from xti.domain.research import ResearchNode, ResearchEdge, ResearchEvidence, identity


class StoredInvestigationContext:
    def __init__(self, connection, *, limitations, coverage):
        self.connection, self.limitations, self.coverage = connection, limitations, coverage
        self.nodes, self.edges, self.loaded = {}, [], False

    def load(self):
        if self.loaded:
            return
        self.loaded = True
        if not ResearchReadBudget(self.connection, self.limitations).admit(('investigation_events',), 'investigation_read_budget'):
            return
        records, _, _ = read_investigations(self.connection)
        organization_state = None
        organization_available = True
        if any(record['kind'] == 'identity' and record['proposal']['left']['kind'] == 'organization' for record in records.values()):
            organization_available = ResearchReadBudget(self.connection, self.limitations).admit(
                identity_read_tables(self.connection, {'organization'}), 'identity_organization_read_budget')
            if organization_available:
                from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
                organization_state = SQLiteOrganizationRepository._audit(self.connection)
        for record in records.values():
            proposal, events = record['proposal'], record['events']
            if proposal['kind'] == 'identity' and proposal['left']['kind'] == 'organization' and not organization_available:
                continue
            decisions = tuple(ResearchEvidence('investigation_decision', record['id'], 'local-investigation', record['id'],
                'human_decision', event['action'], event['recorded_at'], event['recorded_at'], event['reason'],
                event_id=event['id'], current=event['id'] == events[-1]['id'], state_sha256=identity(event),
                time_basis='decision_recorded_at') for event in reversed(events) if event['action'] != 'proposed')
            if proposal['kind'] == 'identity':
                source, target = tuple(proposal['left'][name] for name in ('kind', 'id')), tuple(proposal['right'][name] for name in ('kind', 'id'))
                event = events[0]
                proof = ResearchEvidence('identity_proposal', record['id'], 'local-investigation', record['id'],
                    'candidate_context', record['decision'], event['recorded_at'], event['recorded_at'],
                    proposal['reason'] + '; kanıt: ' + '; '.join(proposal['evidence']),
                    state_sha256=identity(proposal), time_basis='decision_recorded_at')
                evidence = (proof, *decisions)
                self.edges.append(ResearchEdge('identity:' + record['id'], source, target,
                    'reviewed_identity_link', 'candidate_context', evidence[:52], len(evidence)))
                for kind, identifier in (source, target):
                    if kind == 'organization':
                        state = organization_state
                        org = state.organizations[identifier]
                        self.nodes[(kind, identifier)] = ResearchNode((kind, identifier), org.display_name,
                            'organization', evidence=evidence[:52], evidence_total_count=len(evidence))
                        for stored in state.links.values():
                            link = stored.link
                            if org.active and link.active and link.organization_id == identifier and link.target.kind == 'domain':
                                self.edges.append(ResearchEdge('identity-org:' + identity(record['id'], link.id),
                                    ('domain', link.target.value), (kind, identifier), 'registered_organization_context',
                                    'candidate_context', (proof,), 1))
            else:
                key = ('report_candidate', record['id'])
                proof = ResearchEvidence('report_candidate', record['id'], proposal['source'], proposal['source_reference'],
                    'candidate_context', record['decision'], proposal['observed_at'], events[0]['recorded_at'],
                    f"Metin kaydı {proposal['source_record_id']}; metin SHA-256 {proposal['text_sha256']}; "
                    'Yalnız saklı yayıncı/arama özeti tarandı; metinde geçmek zararlılık veya saldırı ilişkisi değildir.',
                    state_sha256=identity(proposal), source_run_id=proposal['source_run_id'], time_basis='response_received_at')
                evidence = (proof, *decisions)
                self.nodes[key] = ResearchNode(key, proposal['source_reference'], 'report_candidate',
                    evidence=evidence[:52], evidence_total_count=len(evidence))
                for candidate in proposal['candidates']:
                    target = (candidate['indicator_type'], candidate['value'])
                    self.edges.append(ResearchEdge('report-mention:' + identity(record['id'], target), key, target,
                        'report_mentions_candidate', 'candidate_context', (proof,), 1))
                for domain in proposal['scope']:
                    self.edges.append(ResearchEdge('report-scope:' + identity(record['id'], domain), ('domain', domain), key,
                        'original_report_search_scope', 'candidate_context', (proof,), 1))
            if len(evidence) > 52:
                self.limitations.add('source_evidence_limit')

    def neighbors(self, key):
        self.load()
        rows = sorted((edge for edge in self.edges if key in (edge.source, edge.target)), key=lambda row: row.id)
        if len(rows) > 200:
            self.limitations.add('investigation_adjacency_limit')
        return tuple(rows[:200])
