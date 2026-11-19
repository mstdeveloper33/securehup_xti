"""Terminal and company composition for lossless journal retention."""
from contextlib import nullcontext
from xti.domain.journal_storage import FIELDS, WRITES


def make_journal_service(database):
    from xti.adapters.sqlite_journal_storage import SQLiteJournalStorageRepository
    from xti.application.journal_storage import JournalStorageService
    return JournalStorageService(SQLiteJournalStorageRepository(database))


def register_journal_parser(commands):
    parser = commands.add_parser('journals', help='Rapor/kanıt günlüklerinin geçmişini silmeden yedekle, sıkıştır ve geri al.')
    actions = parser.add_subparsers(dest='journal_action', required=True)
    for action in ('status', 'archive-plan', 'archive-apply', 'show', 'restore'):
        child = actions.add_parser(action)
        allowed, required = FIELDS['journals.' + action]
        for field in sorted(allowed):
            if field == 'identifier':
                child.add_argument(field)
            else:
                child.add_argument('--' + field.replace('_', '-'), required=field in required,
                    **({'type': int} if field in ('older_than_days', 'limit') else {}))


def journal_lines(data):
    lines = []
    for row in data.get('journals', []):
        lines.append(f"{row['journal']}: {row['logical_count']} kayıt; {row['cold_count']} arşivde, {row['hot_count']} açık gövdeli.")
        lines.append(f"  Arşiv gövdeleri: {row['cold_original_bytes']} → {row['cold_compressed_bytes']} bayt.")
    if 'selected_count' in data:
        lines.extend([f"Seçilen: {data['selected_count']} | kalan: {data['remaining_count']} | korunan son kayıt: {data['protected_latest_count']}",
            'Kesim tarihi: ' + data['cutoff'], 'Önizleme kimliği: ' + data['token'],
            f"Uygula: journals archive-apply --older-than-days {data['older_than_days']} --limit {data['limit']} --token {data['token']}"])
    if 'changed_count' in data:
        lines.append(f"Taşınan gövde: {data['changed_count']}; mantıksal kayıt silinmedi.")
        if data['backup']:
            lines.append('İşlem öncesi yedek: ' + data['backup'])
    if data.get('event') is not None:
        event = data['event']
        lines.append(f"İşlem: {event['id']} | {event['action']} | {event['created_at']}")
        if event['action'] == 'archive':
            lines.append('Geri al: journals restore ' + event['archive_id'])
    for event in data.get('recent_events', []):
        lines.append(f"Geçmiş: {event['id']} | {event['action']} | {event['created_at']}")
    lines.extend(data.get('notes', []))
    return lines


def execute_journal(database, args):
    from xti.adapters.worker_lock import LocalExecutionLock
    operation = 'journals.' + args.journal_action
    options = {key: getattr(args, key) for key in FIELDS[operation][0] if getattr(args, key, None) is not None}
    with LocalExecutionLock(database).acquire() if operation in WRITES else nullcontext():
        data = make_journal_service(database).execute(operation, **options)
    return data, journal_lines(data)


def execute_platform_journal(context, request):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.engine import EngineContractError
    options = dict(request.parameters)
    if options.pop('expected_workspace_id') != context.workspace_id:
        raise EngineContractError('scope_mismatch', 'İstek güncel firma veri alanına ait değil.')
    with LocalExecutionLock(context.database).acquire():
        return make_journal_service(context.database).execute(request.operation, **options)
