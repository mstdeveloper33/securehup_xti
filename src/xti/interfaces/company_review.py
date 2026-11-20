"""Local terminal projection of the shared company review contract."""

from xti.interfaces.text import safe_text


def make_company_review_service(database):
    from xti.adapters.sqlite_company_review import SQLiteCompanyReviewRepository
    from xti.application.company_review import CompanyReviewService
    return CompanyReviewService(SQLiteCompanyReviewRepository(database))


def register_company_review_parser(commands):
    parser = commands.add_parser('review-queue', help='Firma genelindeki kayıtları gerekçeli inceleme sırasında göster.')
    for name, default in (('offset', 0), ('limit', 20), ('root-offset', 0), ('root-limit', 25), ('stale-after-hours', 24), ('social-offset', 0), ('social-limit', 20), ('group-offset', 0), ('group-limit', 20)):
        parser.add_argument('--' + name, type=int, default=default)
    parser.add_argument('--expected-snapshot')


def execute_company_review(database, args):
    data = make_company_review_service(database).show(**{key: getattr(args, key) for key in (
        'offset', 'limit', 'root_offset', 'root_limit', 'stale_after_hours', 'expected_snapshot', 'social_offset', 'social_limit', 'group_offset', 'group_limit')})
    lines = [f"Firma inceleme listesi: {data['root_examined_count']}/{data['root_total_count']} başlangıç kaydı incelendi."]
    labels = {'review_first': 'Önce incele', 'verify': 'Doğrula', 'context': 'Bağlam'}
    for item in data['items']:
        lines.append(f"{labels[item['priority']]} | {safe_text(item['label'])} | {item['id']}")
        lines.extend('  ' + safe_text(reason['message']) for reason in item['reasons'])
        lines.extend(f"  Kaynak {safe_text(state['source'])}: {safe_text(state['status'])}; {state['freshness']}"
                     for state in item['source_states'])
        from xti.interfaces.research import _surface_detail_commands
        lines.extend('  Ayrıntı: ' + command for command in _surface_detail_commands(item['evidence'], database.parent))
    from xti.interfaces.social_tracking import review_lines
    social = data['social']
    lines.append(f"Sosyal profil incelemesi: {len(social['records'])}/{social['total_count']} kayıt.")
    for row in social['records']: lines.extend(review_lines(row))
    if social['has_more']: lines.append(f"Sonraki sosyal sayfa: --social-offset {social['offset'] + len(social['records'])}")
    from xti.interfaces.research_groups import group_lines
    lines.append('Kayıtlı inceleme grupları (son kayıtlı durum; yeniden kontrol: groups queue):')
    lines.extend(group_lines(data['groups']))
    if data['groups']['has_more']:
        lines.append(f"Sonraki grup sayfası: --group-offset {data['groups']['next_offset']}")
    if not data['coverage_complete']:
        lines.append('Kapsam kısmi: ' + ', '.join(data['limitations']))
    if data['root_has_more']:
        lines.append(f"Sonraki kapsam: --root-offset {data['next_root_offset']}")
    lines.append('Kesit: ' + data['snapshot_id'])
    return data, lines
