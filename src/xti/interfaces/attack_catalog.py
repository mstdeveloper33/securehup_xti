"""Local ATT&CK catalog commands and safe Turkish terminal rendering."""
from xti.domain.assets import ValidationError
from xti.domain.attack_catalog import CATALOG_KINDS
from xti.interfaces.text import safe_text
_KIND_LABELS = {'group': 'Grup', 'campaign': 'Kampanya', 'malware': 'Zararlı yazılım', 'technique': 'Teknik', 'subtechnique': 'Alt teknik', 'tactic': 'Taktik'}
_ACTION_LABELS = {'added': 'Eklendi', 'updated': 'Güncellendi', 'reactivated': 'Yeniden etkin', 'revoked': 'Geri çekildi'}

def register_attack_catalog_parsers(cti_actions) -> None:
    status = cti_actions.add_parser('attack-status', help='Yerel ATT&CK kataloğu ve senkron geçmişi.')
    status.add_argument('--run-limit', type=int, default=20)
    search = cti_actions.add_parser('attack-search', help='Yerel ATT&CK tekniği, taktiği, grubu veya yazılımını ara.')
    search.add_argument('query')
    search.add_argument('--kind', choices=sorted(CATALOG_KINDS))
    search.add_argument('--all', dest='all_entries', action='store_true', help='Geri çekilmiş kayıtları da göster.')
    search.add_argument('--limit', type=int, default=50)
    search.add_argument('--offset', type=int, default=0)
    show = cti_actions.add_parser('attack-show', help='T1059, T1059.001 veya STIX kimliğiyle kaynak ayrıntısı.')
    show.add_argument('identifier')
    show.add_argument('--relationship-limit', type=int, default=100)
    show.add_argument('--relationship-offset', type=int, default=0)
    show.add_argument('--event-limit', type=int, default=20)

def _active(value):
    return 'Etkin' if value else 'Geri çekilmiş'

def _entity_line(item):
    entity = item.entity
    return f'{safe_text(entity.external_id)} | {_KIND_LABELS[entity.kind]} | {safe_text(entity.name)} | {_active(item.active)}'

def attack_catalog_status_lines(result):
    lines = ['Yerel MITRE ATT&CK kataloğu', f'Etkin kayıt: {result.active_entity_count} | STIX ilişkisi: {result.active_relationship_count} | Teknik/taktik alan bağı: {result.active_phase_count}', f'Senkron geçmişi: {result.run_count} | Gösterilen: {len(result.runs)}']
    if not result.runs:
        lines.append('Katalog henüz alınmadı. Başlat: ./xti cti attack-sync')
    for run in result.runs:
        lines.extend([f'{safe_text(run.id)} | v{safe_text(run.version)} | {safe_text(run.recorded_at)}', f'  Kaynak SHA-256: {safe_text(run.content_sha256)} | Alındı: {safe_text(run.fetched_at)}', f'  Kayıt {run.entity_count}, ilişki {run.relationship_count}, alan bağı {run.phase_count}; yeni {run.added_count}, güncel {run.updated_count}, yeniden etkin {run.reactivated_count}, geri çekilmiş {run.revoked_count}, aynı {run.unchanged_count}'])
    if result.run_count > len(result.runs):
        lines.append('Daha eski senkronlar var; --run-limit değerini artırabilirsiniz (en çok 100).')
    return lines

def attack_catalog_search_lines(result):
    lines = [f'ATT&CK araması: {safe_text(result.query)} | Toplam: {result.total_count} | Gösterilen: {len(result.items)} | Başlangıç: {result.offset}']
    lines.extend((_entity_line(item) for item in result.items))
    if result.next_offset is not None:
        lines.append(f'Sonraki sayfa: aynı aramaya --offset {result.next_offset} ekleyin.')
    if not result.items:
        lines.append('Bu görünümde kayıt bulunamadı. Katalog durumunu ./xti cti attack-status ile görebilirsiniz.')
    return lines

def attack_catalog_details_lines(result):
    entity = result.item.entity
    lines = [_entity_line(result.item), f'STIX kimliği: {safe_text(entity.stix_id)}', f'Kaynak: {safe_text(entity.source_url)}', f'Kaynak değişikliği: {safe_text(entity.modified_at)}', f'İlk kayıt senkronu: {safe_text(result.item.first_run_id)}', f'Son durum değişimi senkronu: {safe_text(result.item.last_run_id)}', 'Kaynak açıklaması:', safe_text(entity.description or 'Kaynakta açıklama yok.')]
    if entity.aliases:
        lines.append('Alternatif adlar: ' + safe_text(', '.join(entity.aliases)))
    if entity.platforms:
        lines.append('Platformlar: ' + safe_text(', '.join(entity.platforms)))
    lines.append(f'STIX ilişkileri: {result.relationship_count} | Gösterilen: {len(result.relationships)}')
    for view in result.relationships:
        relation = view.relationship
        lines.extend([f'  {safe_text(view.source.external_id)} ({safe_text(view.source.name)}) → {safe_text(relation.relationship_type)} → {safe_text(view.target.external_id)} ({safe_text(view.target.name)}) | {_active(view.active)}', f'    STIX: {safe_text(relation.stix_id)} | Kaynak: {safe_text(relation.source_url)}'])
        if relation.description:
            lines.append('    ' + safe_text(relation.description))
    if result.next_relationship_offset is not None:
        lines.append(f'Ek ilişkiler var; sonraki sayfa: --relationship-offset {result.next_relationship_offset}.')
    lines.append(f'Teknik/taktik bağları: {len(result.phases)}; kaynağı kill_chain_phases alanıdır, STIX relationship değildir.')
    for view in result.phases:
        lines.append(f'  {safe_text(view.technique.external_id)} → {safe_text(view.tactic.external_id)} ({safe_text(view.tactic.name)}) | Alan: {safe_text(view.link.field)} / {safe_text(view.link.phase_name)} | {_active(view.active)}')
    lines.append(f'Kayıt değişimleri: {result.change_count} | Gösterilen: {len(result.changes)}')
    for change in result.changes:
        lines.append(f'  {_ACTION_LABELS[change.action]} | Senkron: {safe_text(change.run_id)} | Ad: {safe_text(change.record.name)}')
    if result.change_count > len(result.changes):
        lines.append('Daha eski değişimler var; --event-limit artırılabilir (en çok 500).')
    if result.cti_entity_id:
        lines.append(f'Aynı resmî kaynağa bağlı CTI kaydı: {safe_text(result.cti_entity_id)}')
    lines.append('Bu katalog tehdit davranışlarını açıklar; bir domainin saldırıya uğradığını veya bir aktöre ait olduğunu göstermez.')
    return lines

def run_attack_catalog_command(args, service):
    """Return (typed result, terminal lines); entrypoint owns serialization/output."""
    if args.cti_action == 'attack-status':
        result = service.status(run_limit=args.run_limit)
        return (result, attack_catalog_status_lines(result))
    if args.cti_action == 'attack-search':
        result = service.search(args.query, kind=args.kind, active_only=not args.all_entries, limit=args.limit, offset=args.offset)
        return (result, attack_catalog_search_lines(result))
    if args.cti_action == 'attack-show':
        result = service.show(args.identifier, relationship_limit=args.relationship_limit, relationship_offset=args.relationship_offset, event_limit=args.event_limit)
        return (result, attack_catalog_details_lines(result))
    raise ValidationError('ATT&CK katalog komutu geçersiz.')
