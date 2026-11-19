"""Explicit CLI and company-scoped composition for observation and review services."""
from contextlib import nullcontext
from xti.domain.evidence_contract import FIELDS, WRITES
from xti.interfaces.text import safe_text


def make_evidence_service(database):
    from xti.adapters.sqlite_evidence import SQLiteEvidenceRepository
    from xti.application.evidence import EvidenceService
    return EvidenceService(SQLiteEvidenceRepository(database))


def _configure(parser, operation):
    parser.set_defaults(evidence_operation=operation)
    allowed, required = FIELDS[operation]
    for key in sorted(allowed):
        kwargs = {}
        if key in ('offset', 'limit', 'expected_revision'):
            kwargs['type'] = int
        if key == 'decision':
            kwargs['choices'] = ('accepted', 'rejected', 'uncertain', 'withdrawn')
        if key == 'kind':
            kwargs['choices'] = ('entity', 'organization')
        if key in ('identifier', 'indicator_type', 'value'):
            continue
        parser.add_argument('--' + key.replace('_', '-'), required=key in required, **kwargs)
    for key in ('indicator_type', 'value', 'identifier'):
        if key in allowed:
            parser.add_argument('--' + key.replace('_', '-') if operation == 'relationships.queue' else key)


def register_evidence_parser(commands):
    for family, help_text, actions in (
        ('sightings', 'Sensörün bildirdiği gerçek görülmeler; kaynak listelerinden ayrı.', ('record', 'list', 'show', 'revoke')),
        ('relationships', 'Kayıtlı kanıttan ilişki önerileri ve gerekçeli insan kararları.', ('candidates', 'review', 'show', 'queue', 'notify', 'notification-show')),
        ('identity', 'Kabul edilmiş kimlik bağlarını özgün kayıtlarla birlikte göster.', ('view',))):
        parser = commands.add_parser(family, help=help_text)
        subs = parser.add_subparsers(dest=family + '_action', required=True)
        for action in actions:
            _configure(subs.add_parser(action), family + '.' + action)


def register_comparison_parser(commands):
    _configure(commands.add_parser('compare', help='IOC kaynaklarını ve yerel sensör görülmelerini ayrı karşılaştır.'), 'ioc.compare')


def evidence_lines(data):
    lines = []
    if 'created_count' in data:
        lines.append(f"Yeni bildirim: {data['created_count']} | Daha önce bildirilen: {data['existing_count']} | Eksik kapsam: {data['skipped_incomplete_count']}")
    if 'notification' in data:
        data = {**data, 'records': [data['notification']]}
    rows = [data['record']] if 'record' in data else data.get('records', [])
    for row in rows:
        if 'snapshot' in row and row['snapshot'].get('kind') == 'relationship_review_notification':
            lines.append('Bildirim: ' + row['id'] + ' | kanıt: ' + row['snapshot_sha256'])
            row = row['snapshot']['change']
        if row.get('kind') == 'relationship_re_review':
            lines.extend([f"Yeniden incele: {row['relationship_id']} | {safe_text(row['root'][1])} → {safe_text(row['target'][1])}",
                '  ' + row['explanation'], f"  Önceki karar: {row['previous']['decision']} | sürüm {row['previous']['revision']}"])
            if row['current'] is not None:
                lines.append('  Yeni dayanak: ' + row['current']['evidence_sha256'])
        elif row.get('kind') == 'sighting':
            item = row['observation']
            lines.extend([f"{row['id']} | {row['state']} | sürüm {row['revision']}",
                f"  {safe_text(item['value'])} | {safe_text(item['source'])} / {safe_text(item['sensor'])}",
                f"  Görülme: {item['observed_at']} | kayıt: {row['history'][0]['recorded_at']}",
                '  Başvuru: ' + safe_text(item['reference'])])
        elif row.get('kind') == 'relationship':
            lines.append(f"{row['id']} | {row['decision']} | sürüm {row['revision']} | {safe_text(row['reason'])}")
            for event in row['history']:
                lines.append(f"  {event['recorded_at']} | {event['request']['decision']} | {safe_text(event['request']['reason'])}")
        elif 'evidence_sha256' in row:
            lines.extend([f"{row['id']} | {row['rule']} | {safe_text(row['target'][1])}",
                '  ' + safe_text(row['reason']), '  Dayanak: ' + row['evidence_sha256']])
            review = row['review']
            lines.append('  İnsan kararı: ' + (f"{review['decision']} | sürüm {review['revision']} | aynı dayanak: {review['evidence_current']}" if review else 'henüz yok; beklenen sürüm 0'))
        elif 'claims' in row:
            lines.append('Kaynak: ' + safe_text(row['source']))
            for claim in row['claims']:
                lines.append(f"  {claim['claim_state']} | {claim['currency']['state']} | {safe_text(claim['source_reference'])}")
                lines.append(f"  Zaman temeli: {claim['time_basis']} | son toplama: {claim['collection']['status']}")
    for member in data.get('members', []):
        record = member['record']
        lines.append(f"Kimlik: {member['id']} | {safe_text(record.get('display_name', record.get('name', member['kind'])))}")
        for claim in member['source_assertions']:
            lines.append('  Kaynak: ' + safe_text(claim['source_name']) + ' | ' + safe_text(claim['source_reference']))
    if 'local_sightings' in data:
        lines.append('Yerel görülme: ' + str(data['local_sightings']['active_count']) + ' etkin; ayrıntı sightings list komutunda.')
    if 'total_count' in data:
        lines.append(f"Gösterilen: {len(rows)} / {data['total_count']}")
    if 'examined_count' in data:
        lines.append(f"Bu pencerede {data['examined_count']} karar incelendi; {data['pending_in_window']} yeniden inceleme gerekiyor. Toplam karar: {data['total_review_count']}.")
    if data.get('has_more'):
        lines.append(f"Devam: --offset {data['next_offset']} --expected-snapshot {data['snapshot_id']}")
    if data.get('coverage_complete') is False:
        lines.append('Kapsam kısmi: ' + ', '.join(data['limitations']))
    if data.get('replayed'):
        lines.append('Tekrar anahtarının ilk sonucu gösteriliyor.')
    lines.extend(data.get('notes', []))
    return lines


def execute_evidence(database, args):
    from xti.adapters.worker_lock import LocalExecutionLock
    operation = args.evidence_operation
    options = {key: getattr(args, key) for key in FIELDS[operation][0] if getattr(args, key, None) is not None}
    with LocalExecutionLock(database).acquire() if operation in WRITES else nullcontext():
        data = make_evidence_service(database).execute(operation, **options)
    return data, evidence_lines(data)


def execute_platform_evidence(context, request):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.engine import EngineContractError
    options = dict(request.parameters)
    if options.pop('expected_workspace_id') != context.workspace_id:
        raise EngineContractError('scope_mismatch', 'İstek güncel firma veri alanına ait değil.')
    with LocalExecutionLock(context.database).acquire():
        return make_evidence_service(context.database).execute(request.operation, **options)
