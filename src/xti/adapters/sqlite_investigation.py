"""Audited candidate/decision journal; replay and revision checks are atomic."""

import json
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.research_read_budget import ResearchReadBudget
from xti.domain.assets import ValidationError
from xti.domain.investigation import project, validate_event, validate_proposal, DECISIONS
from xti.domain.cases import normalize_case_reason
from xti.domain.research import identity
from xti.domain.engine_jobs import canonical_json, digest
from xti.domain.research_history import history_key


def identity_read_tables(connection, kinds):
    tables = []
    if 'entity' in kinds:
        tables.extend(('cti_entities', 'cti_entity_assertions', 'cti_entity_assertion_events'))
    if 'organization' in kinds:
        # Organization audits also validate their linked watch registries.
        tables.extend(row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                      if row[0].startswith(('organization', 'brand_username_', 'ransomware_watch',
                                            'ransomware_claim', 'ransomlook_')))
    return tuple(tables)


def read_investigations(connection):
    if not ResearchReadBudget(connection, set(), rows=10_000, size=32 * 1024 * 1024).admit(
            ('investigation_events',), 'limit'):
        raise StorageError('Araştırma karar günlüğü okuma sınırını aşıyor.')
    events, chain = [], None
    try:
        for sequence, identifier, subject, key, kind, payload, sha, next_chain in connection.execute(
                'SELECT sequence,id,subject_id,request_key,kind,payload_json,payload_sha256,chain_sha256 '
                'FROM investigation_events ORDER BY sequence'):
            if sequence != len(events) + 1 or digest(payload) != sha or identity(chain, sha) != next_chain:
                raise ValueError('Broken journal chain')
            event = validate_event(json.loads(payload))
            if canonical_json(event) != payload or (identifier, subject, key, kind) != (
                    event['id'], event['subject_id'], event['request_key'], event['kind']):
                raise ValueError('Journal metadata mismatch')
            events.append(event)
            chain = next_chain
        allocated = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='investigation_events'").fetchone()
        if allocated is not None and allocated[0] != len(events):
            raise ValueError('Deleted journal tail')
        return project(events), events, chain
    except (ValidationError, KeyError, TypeError, ValueError, OverflowError, RecursionError) as error:
        raise StorageError('Araştırma karar günlüğü bozuk; kayıtlar değiştirilmedi.') from error


class SQLiteInvestigationRepository:
    def __init__(self, path):
        self.storage = SQLiteAssetRepository(path)

    def catalog(self):
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            return read_investigations(connection)[0]

    def _resolve_identity(self, connection, proposal):
        from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
        from xti.adapters.sqlite_cti_context import _audit_assertion_history
        from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
        refs = (proposal['left'], proposal['right'])
        if not ResearchReadBudget(connection, set()).admit(identity_read_tables(connection, {r['kind'] for r in refs}), 'identity_read_budget'):
            raise ValidationError('Kimlik kanıtları güvenli okuma sınırını aşıyor; eşleştirme kaydedilmedi.')
        state = SQLiteOrganizationRepository._audit(connection) if refs[0]['kind'] == 'organization' else None
        entity_types = set()
        for ref in refs:
            if ref['kind'] == 'organization':
                SQLiteOrganizationRepository._organization_by_id(state, ref['id'])
            else:
                details = SQLiteCtiKnowledgeRepository(self.storage.path)._entity_details(connection, ref['id'], 1000, 10000)
                _audit_assertion_history(connection, details, 'entity')
                entity_types.add(details.entity.entity_type)
        if len(entity_types) > 1:
            raise ValidationError('Kimlik eşleştirmesi aynı CTI türündeki kayıtlar arasında yapılmalı.')

    def _append(self, proposal, identifier, *, decision, reason, expected_revision, key, at):
        key = history_key(key)
        if proposal is not None:
            validate_proposal(proposal)
        with self.storage._connection() as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            records, events, chain = read_investigations(connection)
            replay = next((event for event in events if event['request_key'] == key), None)
            if replay:
                if (replay['action'], replay['proposal'], replay['reason'], replay['expected_revision']) != (decision, proposal, reason, expected_revision) or (
                        identifier is not None and replay['subject_id'] != identifier):
                    raise ValidationError('Tekrar anahtarı başka bir istek için kullanılmış.')
                # Return the state AT the original decision, not a newer review.
                return {'record': project(events[:events.index(replay) + 1])[replay['subject_id']], 'replayed': True}
            if len(events) >= 10_000:
                raise ValidationError('Araştırma karar günlüğü kapasitesi doldu.')
            if proposal is not None:
                identifier, previous, kind = str(uuid4()), None, proposal['kind']
                if kind == 'identity':
                    self._resolve_identity(connection, proposal)
            else:
                current = records.get(identifier)
                if current is None:
                    raise ValidationError('İnceleme kaydı seçili alanda bulunamadı.')
                if type(expected_revision) is not int or current['revision'] != expected_revision:
                    raise ValidationError('İnceleme kararı değişmiş; güncel kaydı yeniden alın.')
                previous, kind = current['events'][-1]['id'], current['kind']
            event = {'version': 1, 'id': str(uuid4()), 'subject_id': identifier, 'request_key': key,
                     'kind': kind, 'action': decision, 'proposal': proposal, 'reason': reason,
                     'recorded_at': at, 'previous_id': previous, 'expected_revision': expected_revision}
            validate_event(event)
            projected = project([*events, event])
            payload = canonical_json(event)
            size = connection.execute('SELECT COALESCE(SUM(LENGTH(CAST(payload_json AS BLOB))+512),0) FROM investigation_events').fetchone()[0]
            if size + len(payload.encode('ascii')) + 512 > 32 * 1024 * 1024:
                raise ValidationError('Araştırma karar günlüğü byte kapasitesi doldu.')
            sha = digest(payload)
            connection.execute('INSERT INTO investigation_events (id,subject_id,request_key,kind,payload_json,payload_sha256,chain_sha256) '
                'VALUES (?,?,?,?,?,?,?)', (event['id'], identifier, key, kind, payload, sha, identity(chain, sha)))
            return {'record': projected[identifier], 'replayed': False}

    def propose(self, proposal, *, key, at):
        return self._append(proposal, None, decision='proposed', reason=proposal.get('reason', 'Kaynak metninden aday çıkarımı'),
                            expected_revision=None, key=key, at=at)

    def decide(self, identifier, *, decision, reason, expected_revision, key, at):
        if decision not in DECISIONS:
            raise ValidationError('Karar accepted, rejected, uncertain veya withdrawn olmalı.')
        return self._append(None, identifier, decision=decision, reason=normalize_case_reason(reason),
                            expected_revision=expected_revision, key=key, at=at)

    def resolve_report(self, source, identifier):
        from xti.domain.report_extraction import report_proposal
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            if source == 'news':
                from xti.adapters.sqlite_news import read_news_catalog
                catalog = read_news_catalog(connection)
                record = next((record for record in catalog.articles if record.article.id == identifier), None)
                if record is None:
                    raise ValidationError('Haber kaydı seçili alanda bulunamadı.')
                return report_proposal(source=source, source_reference=record.article.url, source_record_id=identifier,
                    source_run_id=record.last_change_run_id, text=record.article.title + '\n' + record.article.summary,
                    source_sha256=record.state_sha256, observed_at=record.last_changed_at, scope=[], source_text_truncated=record.article.summary_truncated)
            if source == 'mentions':
                from xti.adapters.sqlite_mentions import read_mentions_catalog
                record = next((record for record in read_mentions_catalog(connection).records if record.id == identifier), None)
                if record is None:
                    raise ValidationError('Firma içeriği seçili alanda bulunamadı.')
                return report_proposal(source=source, source_reference=record.hit.url, source_record_id=identifier,
                    source_run_id=record.last_change_run_id, text=record.hit.title + '\n' + record.hit.summary,
                    source_sha256=record.state_sha256, observed_at=record.last_changed_at, scope=record.request.target.domains, source_text_truncated=record.hit.summary_truncated)
            raise ValidationError('Rapor kaynağı news veya mentions olmalı.')

    def identity_candidates(self, query):
        from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
        from xti.adapters.sqlite_cti_context import _audit_assertion_history
        from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
        from xti.domain.cti_knowledge import normalize_search_query
        query = normalize_search_query(query).casefold()
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            limits = set()
            if not ResearchReadBudget(connection, limits).admit(
                    identity_read_tables(connection, {'entity', 'organization'}), 'identity_read_budget'):
                return {'candidates': [], 'coverage_complete': False, 'limitations': sorted(limits)}
            matches = []
            for identifier, in connection.execute('SELECT id FROM cti_entities ORDER BY id'):
                details = SQLiteCtiKnowledgeRepository(self.storage.path)._entity_details(connection, identifier, 1000, 10000)
                _audit_assertion_history(connection, details, 'entity')
                names = {details.entity.display_name.casefold()}
                for assertion in details.assertions:
                    if assertion.active:
                        names.update(alias.casefold() for alias in assertion.aliases)
                if query in names:
                    matches.append({'kind': 'entity', 'id': identifier, 'name': details.entity.display_name,
                                    'matched_name': query, 'basis': 'name_or_source_alias'})
            organization_state = SQLiteOrganizationRepository._audit(connection)
            for organization in organization_state.organizations.values():
                if organization.active and query in {event.name_key for event in organization_state.events if event.organization_id == organization.id}:
                    matches.append({'kind': 'organization', 'id': organization.id, 'name': organization.display_name,
                                    'matched_name': query, 'basis': 'registered_name'})
            return {'candidates': matches[:100], 'coverage_complete': len(matches) <= 100,
                    'limitations': ['identity_candidate_limit'] if len(matches) > 100 else [],
                    'notes': ['Ad/alternatif ad eşleşmesi adaydır; otomatik kimlik birleştirme yapılmaz.']}
