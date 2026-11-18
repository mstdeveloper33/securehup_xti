"""CLI and company protocol use the same review services."""

from xti.interfaces.text import safe_text, xti_command


from xti.domain.investigation_contract import READ_OPERATIONS, WRITE_OPERATIONS


def make_investigation_service(database):
    from xti.adapters.sqlite_investigation import SQLiteInvestigationRepository
    from xti.application.investigation import InvestigationService
    return InvestigationService(SQLiteInvestigationRepository(database))


def register_investigation_parser(commands):
    parser = commands.add_parser('investigate', help='Kimlik ve rapor adaylarını gerekçeli, geri alınabilir kararlarla incele.')
    actions = parser.add_subparsers(dest='investigation_action', required=True)
    candidates = actions.add_parser('candidates', help='Ad ve kaynak alternatif adından kimlik adaylarını bul.')
    candidates.add_argument('query')
    propose = actions.add_parser('propose', help='İki mevcut kimlik için kanıtlı eşleştirme adayı oluştur.')
    propose.add_argument('--kind', choices=('entity', 'organization'), required=True)
    propose.add_argument('left_id')
    propose.add_argument('right_id')
    propose.add_argument('--evidence', action='append', required=True)
    propose.add_argument('--reason', required=True)
    propose.add_argument('--idempotency-key', required=True)
    extract = actions.add_parser('extract', help='Kayıtlı haber/firma metninden IOC ve metinde geçme ilişkisi adayları çıkar.')
    extract.add_argument('--source', choices=('news', 'mentions'), required=True)
    extract.add_argument('identifier')
    extract.add_argument('--idempotency-key', required=True)
    decide = actions.add_parser('decide', help='İnsan kararını kaydet; kayıtları birleştirme veya IOC oluşturma.')
    decide.add_argument('identifier')
    decide.add_argument('--decision', choices=('accepted', 'rejected', 'uncertain', 'withdrawn'), required=True)
    decide.add_argument('--reason', required=True)
    decide.add_argument('--expected-revision', type=int, required=True)
    decide.add_argument('--idempotency-key', required=True)
    show = actions.add_parser('show', help='Özgün aday, metin/kanıt ve bütün karar geçmişini göster.')
    show.add_argument('identifier')
    listing = actions.add_parser('list', help='Adayları karar durumlarıyla listele.')
    listing.add_argument('--kind', choices=('identity', 'report'))
    listing.add_argument('--offset', type=int, default=0)
    listing.add_argument('--limit', type=int, default=20)
    listing.add_argument('--expected-snapshot')


def investigation_lines(data, data_dir=None):
    lines = []
    for candidate in data.get('candidates', []):
        lines.append(f"{safe_text(candidate['kind'])} | {safe_text(candidate['id'])} | {safe_text(candidate['name'])}")
    for row in data.get('records', []):
        lines.append(f"{row['id']} | {row['kind']} | {row['decision']} | karar sürümü {row['revision']}")
    if 'record' in data:
        row, proposal = data['record'], data['record']['proposal']
        lines.extend([f"{row['id']} | {row['kind']} | {row['decision']} | karar sürümü {row['revision']}",
                      'Ayrıntı: ' + xti_command('investigate', 'show', row['id'], data_dir=data_dir)])
        if proposal['kind'] == 'identity':
            lines.append(safe_text(str(proposal['left'])) + ' ↔ ' + safe_text(str(proposal['right'])))
            lines.extend('Kanıt: ' + safe_text(ref) for ref in proposal['evidence'])
        else:
            lines.extend(['Kaynak: ' + safe_text(proposal['source_reference']),
                          'Metin SHA-256: ' + proposal['text_sha256'],
                          'Saklı kaynak metni: ' + safe_text(proposal['text'])])
            lines.extend(f"Aday: {item['indicator_type']} | {safe_text(item['value'])} | metin [{item['start']}:{item['end']}]"
                         for item in proposal['candidates'])
        lines.extend(f"{event['recorded_at']} | {event['action']} | {safe_text(event['reason'])}" for event in row['events'])
    if data.get('has_more'):
        lines.append('Ek kayıtlar var; sonraki sayfayı aynı snapshot_id ile alın.')
    lines.extend(data.get('notes', ()))
    lines.append('Eşleştirme adaylarıdır; otomatik kimlik birleştirme, saldırı atfı veya zararlılık kararı değildir.')
    return lines


def execute_investigation(database, args):
    from contextlib import nullcontext
    from xti.adapters.worker_lock import LocalExecutionLock
    writing = args.investigation_action in {'propose', 'extract', 'decide'}
    with LocalExecutionLock(database).acquire() if writing else nullcontext():
        return _execute_investigation(database, args)


def _execute_investigation(database, args):
    action = args.investigation_action
    service = make_investigation_service(database)
    fields = {'candidates': ('query',), 'extract': ('source', 'identifier', 'idempotency_key'),
              'decide': ('identifier', 'decision', 'reason', 'expected_revision', 'idempotency_key'),
              'show': ('identifier',), 'list': ('kind', 'offset', 'limit', 'expected_snapshot')}
    if action == 'propose':
        data = service.propose({'kind': args.kind, 'id': args.left_id}, {'kind': args.kind, 'id': args.right_id},
                               args.evidence, args.reason, args.idempotency_key)
    else:
        data = getattr(service, action)(**{field: getattr(args, field) for field in fields[action]})
    return data, investigation_lines(data, database.parent)
