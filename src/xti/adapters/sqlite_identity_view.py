"""Accepted identity connected component; original records remain independent."""
from dataclasses import asdict
from xti.adapters.research_read_budget import ResearchReadBudget
from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_investigation import read_investigations, identity_read_tables
from xti.domain.reports import ReportError
from xti.domain.research import identity


def identity_view(connection, path, kind, identifier):
    from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
    from xti.adapters.sqlite_cti_context import _audit_assertion_history
    from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
    from xti.adapters.sqlite_ioc_lifecycle import _budget
    records = read_investigations(connection)[0]
    links = [row for row in records.values() if row['kind'] == 'identity' and row['proposal']['left']['kind'] == kind]
    graph = {}
    for row in links:
        if row['decision'] == 'accepted':
            left, right = (row['proposal'][key]['id'] for key in ('left', 'right'))
            graph.setdefault(left, set()).add(right)
            graph.setdefault(right, set()).add(left)
    members, pending, partial = {identifier}, [identifier], False
    while pending:
        current = pending.pop(0)
        for other in sorted(graph.get(current, ())):
            if other in members:
                continue
            if len(members) >= 100:
                partial = True
                continue
            members.add(other); pending.append(other)
    state = None
    if kind == 'organization':
        if not ResearchReadBudget(connection, set()).admit(identity_read_tables(connection, {'organization'}), 'identity_budget'):
            raise StorageError('Kuruluş kimlikleri okuma sınırını aşıyor.')
        state = SQLiteOrganizationRepository._audit(connection)
    result, entity_types, budget = [], set(), 16 * 1024 * 1024
    knowledge = SQLiteCtiKnowledgeRepository(path)
    for member in sorted(members):
        if kind == 'organization':
            try:
                item = SQLiteOrganizationRepository._organization_by_id(state, member)
            except Exception as error:
                from xti.domain.assets import ValidationError
                if isinstance(error, ValidationError):
                    raise ReportError('not_found', 'Kimlik seçili çalışma alanında bulunamadı.') from error
                raise
            result.append({'kind': kind, 'id': member, 'record': asdict(item), 'source_assertions': [], 'events': []})
        else:
            if not connection.execute('SELECT 1 FROM cti_entities WHERE id=?', (member,)).fetchone():
                raise ReportError('not_found', 'Kimlik seçili çalışma alanında bulunamadı.')
            budget = _budget(connection, 'cti_entity_assertions', 'entity_id=?', (member,), 500, budget)
            budget = _budget(connection, 'cti_entity_assertion_events',
                'assertion_id IN (SELECT id FROM cti_entity_assertions WHERE entity_id=?)', (member,), 10000, budget)
            details = knowledge._entity_details(connection, member, 500, 10000)
            _audit_assertion_history(connection, details, 'entity')
            entity_types.add(details.entity.entity_type)
            result.append({'kind': kind, 'id': member, 'record': asdict(details.entity),
                'source_assertions': [asdict(item) for item in details.assertions],
                'events': [asdict(item) for item in details.events]})
    if len(entity_types) > 1:
        raise StorageError('Kabul edilmiş kimlik bağı farklı CTI türlerini içeriyor.')
    decisions = [row for row in links if any(row['proposal'][key]['id'] in members for key in ('left', 'right'))]
    decisions.sort(key=lambda row: row['id'])
    return {'model_version': 1, 'root': {'kind': kind, 'id': identifier}, 'members': result,
        'decisions': decisions, 'coverage_complete': not partial, 'limitations': ['identity_member_limit'] if partial else [],
        'snapshot_id': identity(result, decisions, partial), 'physical_merge': False,
        'notes': ['Yalnız kabul edilmiş kimlik bağları izlenir; özgün kayıtlar ve kaynak iddiaları korunur.',
                  'Geri çekilen bağ görünümden çıkar; alternatif kabul edilmiş yol varsa grup bağlı kalır.']}
