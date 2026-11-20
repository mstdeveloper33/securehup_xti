"""New social discoveries in the common bounded workspace research snapshot."""
from xti.adapters.research_read_budget import ResearchReadBudget
from xti.adapters.sqlite_social_tracking import audit, discovery_in, provider_window
from xti.adapters.sqlite_social_enrichment import SQLiteSocialEnrichmentRepository
from xti.domain.research import ResearchEdge, ResearchEvidence, identity
from xti.domain.research_social import social_key, profile_node, profile_evidence, decision_evidence, provider_evidence
from xti.domain.social_tracking import profile_key


class StoredSocialContext:
    def __init__(self, path, connection, *, limitations, coverage):
        self.path, self.connection = path, connection
        self.limitations, self.coverage = limitations, coverage
        self.loaded, self.nodes, self.edges = False, {}, []

    def load(self):
        if self.loaded:
            return
        self.loaded = True
        admitted = ResearchReadBudget(self.connection, self.limitations, rows=5000).admit(
            ('social_discovery_runs', 'social_tracking_journal', 'social_enrichment_runs'), 'unified_social_read_budget')
        self.coverage.append(dict(kind='unified_social', scope='workspace', examined_count=0,
            window_limit=5000, complete=admitted, order='stored_newest_first'))
        if not admitted:
            return
        coverage = self.coverage[-1]
        state = audit(self.connection)[0]
        latest, profiles = {}, {}
        for identifier, domain in self.connection.execute(
                'SELECT id,domain FROM social_discovery_runs WHERE report_json IS NOT NULL ORDER BY sequence DESC'):
            record = discovery_in(self.connection, identifier)
            latest.setdefault(domain, record)
            coverage['examined_count'] += 1
            for row in record['report']['profiles']:
                if row['state'] not in ('found', 'candidate') and not row['claimed_by'] and 'retained_profile' not in row['discovered_by']:
                    continue
                key = (domain, row['url'])
                if key not in profiles and len(profiles) >= 1000:
                    self.limitations.add('unified_social_profile_limit')
                    coverage['complete'] = False
                    continue
                # Keep the latest and the most recent definitive observation.
                bucket = profiles.setdefault(key, [])
                if not bucket or len(bucket) == 1 and bucket[0][1]['state'] not in ('found', 'not_found') and row['state'] in ('found', 'not_found'):
                    bucket.append((record, row))
        provider_cache = {}
        repository = SQLiteSocialEnrichmentRepository(self.path)
        for (domain, url), observations in sorted(profiles.items()):
            record, profile = observations[0]
            key = social_key(domain, url)
            current = record['id'] == latest[domain]['id']
            history = state['reviews'].get(profile_key(domain, url), [])
            review_current = bool(history and current and history[-1]['discovery_id'] == record['id'])
            rows = [decision_evidence(r, current=i == len(history)-1 and review_current)
                    for i, r in reversed(list(enumerate(history)))]
            # Latest decisions and network proof precede older decision history.
            old_decisions, rows = rows[1:], rows[:1]
            for discovery, item in observations:
                rows.extend(profile_evidence(discovery, item, current=discovery['id'] == latest[domain]['id']))
            rows.append(ResearchEvidence('social_review_state', record['id'], 'local-social-review', url,
                'source_context', 'reviewed' if review_current else 'outdated' if history else 'pending',
                record['finished_at'], record['finished_at'], 'İnsan kararının bu keşif kesitiyle ilişkisi; ağ gözlemi değildir.',
                current=current, state_sha256=identity(record['id'], history[-1] if history else None),
                source_run_id=record['id'], time_basis='stored_context_updated_at'))
            if record['id'] not in provider_cache:
                provider_cache[record['id']] = provider_window(self.connection, record, repository)
            providers, truncated = provider_cache[record['id']]
            if truncated:
                self.limitations.add('social_provider_window')
            rows.extend(provider_evidence(p, url) for p in providers if url in p['scope']['targets'])
            rows.extend(old_decisions)
            if len(rows) > 52:
                self.limitations.add('source_evidence_limit')
            node = profile_node(domain, url, rows)
            self.nodes[key] = node
            scope_proof = ResearchEvidence('social_discovery_scope', record['id'], 'local-social-discovery', domain,
                'candidate_context', 'searched', record['finished_at'], record['finished_at'],
                'Tam domain kapsamındaki keşif adayı; bu bağlantı hesap sahipliği veya resmîlik kanıtı değildir.',
                current=current, state_sha256=record['report_sha256'], source_run_id=record['id'], time_basis='response_received_at')
            self.edges.extend((
                ResearchEdge('social-scope:' + identity(domain, url), ('domain', domain), key,
                    'social_discovery_scope', 'candidate_context', (scope_proof,), 1),
                ResearchEdge('social-url:' + identity(domain, url), key, ('url', url),
                    'social_profile_url', 'source_context', node.evidence, node.evidence_total_count),
            ))

    def neighbors(self, key):
        self.load()
        rows = sorted((e for e in self.edges if key in (e.source, e.target)), key=lambda e: e.id)
        if len(rows) > 200:
            self.limitations.add('unified_social_adjacency_limit')
        self.coverage.append(dict(kind='unified_social_links', scope=list(key), examined_count=min(200, len(rows)),
            window_limit=200, complete=len(rows) <= 200 and 'unified_social_read_budget' not in self.limitations,
            order='record_id'))
        return tuple(rows[:200])
