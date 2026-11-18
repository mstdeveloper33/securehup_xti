"""Existing social/content records, bounded and offline in one read snapshot."""

from xti.adapters.research_read_budget import ResearchReadBudget
from xti.adapters.sqlite_brand_username_reviews import SQLiteBrandUsernameReviewRepository
from xti.adapters.sqlite_brand_username_watches import SQLiteBrandUsernameWatchRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_mentions import read_mentions_catalog
from xti.domain.brand_username_reviews import brand_username_review_candidate_id
from xti.domain.organizations import OrganizationLinkView, organization_link_effective
from xti.domain.research import ResearchEdge, ResearchEvidence, ResearchNode, identity
from xti.domain.research_content import social_observation, social_decision, mention_evidence


class StoredContentContext:
    def __init__(self, connection, *, limitations, coverage):
        self.connection, self.limitations, self.coverage = connection, limitations, coverage
        self.nodes, self.edges, self.loaded = {}, [], False
        self.budget = ResearchReadBudget(connection, limitations)

    def _social(self):
        if not self.connection.execute('SELECT 1 FROM brand_username_watches LIMIT 1').fetchone():
            return
        tables = tuple(row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                       if row[0].startswith(('organization', 'brand_username_', 'ransomware_watch',
                                             'ransomware_claim', 'ransomlook_')))
        if not self.budget.admit(tables, 'social_read_budget'):
            return
        watches, runs, items, candidates, _, _, by_candidate, _ = SQLiteBrandUsernameReviewRepository._audit(self.connection)
        organization_state = SQLiteOrganizationRepository._audit(self.connection)
        domains, social = {}, {}
        for stored in organization_state.links.values():
            link = stored.link
            view = OrganizationLinkView(link, organization_state.targets[link.target][1])
            if not organization_link_effective(organization_state.organizations[link.organization_id], view):
                continue
            if link.target.kind == 'domain':
                domains.setdefault(link.organization_id, []).append(link)
            elif link.target.kind == 'username-watch':
                social.setdefault(link.target.value, []).append(link)
        latest = {}
        attempts = {}
        for run in sorted(runs.values(), key=lambda row: row.sequence):
            attempts[(run.watch_id, run.definition_sha256)] = run
            if run.status == 'complete':
                latest[(run.watch_id, run.definition_sha256)] = run.id
        evidence, profile_items = {}, {}
        for item in items:
            if item.status != 'found_unverified':
                continue
            run, watch = runs[item.run_id], watches[runs[item.run_id].watch_id]
            identifier = brand_username_review_candidate_id(watch_id=watch.id,
                definition_sha256=run.definition_sha256, platform=item.platform, state_sha256=item.state_sha256)
            key = ('social_profile', identifier)
            current = (watch.active and SQLiteBrandUsernameWatchRepository._definition(watch) == run.definition_sha256
                       and latest.get((watch.id, run.definition_sha256)) == run.id)
            evidence.setdefault(key, []).append(social_observation(watch, run, item, current=current))
            profile_items[key] = (watch, run, item)
        for key, rows in evidence.items():
            watch, run, item = profile_items[key]
            events = by_candidate.get(key[1], ())
            decisions = [social_decision(event, current=event.id == events[-1].id) for event in reversed(events)]
            attempt = attempts[(watch.id, run.definition_sha256)]
            health = ResearchEvidence('social_watch_run', attempt.id, attempt.source_name, attempt.id,
                'source_context', attempt.status, attempt.recorded_at, attempt.recorded_at,
                attempt.error or 'Son kayıtlı izleme denemesi; hesap kimliğini doğrulamaz.',
                source_run_id=attempt.id, state_sha256=identity(attempt.id, attempt.status, attempt.error),
                time_basis='response_received_at')
            rows = tuple(decisions[:1] + [health] + sorted(rows, key=lambda row: row.recorded_at, reverse=True) + decisions[1:])
            if len(rows) > 52:
                self.limitations.add('source_evidence_limit')
            self.nodes[key] = ResearchNode(key, item.profile_url, 'social_profile', evidence=rows[:52], evidence_total_count=len(rows))
            self.edges.append(ResearchEdge('profile-url:' + identity(key), key, ('url', item.profile_url),
                'observed_profile_url', 'source_context', rows[:52], len(rows)))
            for social_link in social.get(watch.id, ()):
                for domain_link in domains.get(social_link.organization_id, ()):
                    event = next(event for event in reversed(organization_state.link_events) if event.link_id == social_link.id)
                    proof = ResearchEvidence('organization_social_link', social_link.id, 'local-organizations',
                        social_link.organization_id, 'human_decision', 'linked', event.recorded_at, event.recorded_at,
                        f'Kuruluşun açık domain/izleme bağlantısı: {domain_link.id}, {social_link.id}; {event.reason}. '
                        'Bu gruplama hesap sahipliği değildir.', event_id=event.id, current=True,
                        state_sha256=identity(domain_link.id, social_link.id, event.id), time_basis='decision_recorded_at')
                    self.edges.append(ResearchEdge('org-profile:' + identity(domain_link.id, social_link.id, key),
                        ('domain', domain_link.target.value), key, 'organization_profile_candidate', 'human_decision', (proof,), 1))

    def _mentions(self):
        if not self.budget.admit(('mentions_runs',), 'content_read_budget'):
            return
        catalog = read_mentions_catalog(self.connection)
        attempts = {}
        from xti.domain.mentions import request_key
        for run in catalog.runs:
            attempts[request_key(run.request)] = run
        for record in catalog.records:
            key, proof = ('company_content', record.id), mention_evidence(record)
            attempt = attempts[record.request_key]
            health = ResearchEvidence('company_search_run', attempt.id, 'tavily', attempt.id, 'source_context',
                'empty' if attempt.status == 'complete' and attempt.result_count == 0 else attempt.status,
                attempt.finished_at, attempt.finished_at, attempt.error or 'Aynı özgün arama kapsamının son denemesi; eski içerik korunur.',
                source_run_id=attempt.id, state_sha256=identity(attempt.id, attempt.status, attempt.error), time_basis='response_received_at')
            self.nodes[key] = ResearchNode(key, record.hit.title, 'company_content', evidence=(proof, health), evidence_total_count=2)
            # The exact original request domains are evidence of search scope,
            # never of current organization or supplier ownership.
            for domain in record.request.target.domains:
                self.edges.append(ResearchEdge('mention:' + identity(record.id, domain), ('domain', domain), key,
                    'content_search_scope', 'candidate_context', (proof,), 1))
            self.edges.append(ResearchEdge('mention-url:' + identity(record.id), key, ('url', record.hit.url),
                'content_source_url', 'candidate_context', (proof,), 1))

    def load(self):
        if not self.loaded:
            self.loaded = True
            self._social()
            self._mentions()

    def neighbors(self, key):
        self.load()
        selected = sorted((edge for edge in self.edges if key in (edge.source, edge.target)), key=lambda edge: edge.id)
        if len(selected) > 200:
            self.limitations.add('content_adjacency_limit')
        self.coverage.append(dict(kind='social_content', scope=list(key), examined_count=min(len(selected), 200),
            window_limit=200, complete=len(selected) <= 200 and not self.limitations.intersection(
                {'social_read_budget', 'content_read_budget'}), order='record_id'))
        return tuple(selected[:200])
