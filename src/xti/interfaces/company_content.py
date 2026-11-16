"""Company-centred terminal results; collection metrics stay in diagnostic views."""

import shlex

from xti.interfaces.text import safe_text


STATES = {
    'not_checked': 'Bu firma için henüz içerik kontrolü yapılmadı.',
    'content_found': 'Firma kapsamında içerik adayları bulundu.',
    'no_content': 'Kontrol edilen kaynaklarda ilgili içerik bulunamadı.',
    'check_failed': 'Son kontrol tamamlanamadı; önceki içerikler korunuyor.',
    'outcome_unknown': 'Son kontrolün sonucu henüz doğrulanamadı.',
    'stale': 'Kayıtlı kontrol güncel değil; içerikler eski olabilir.',
    'partial': 'Bazı kontroller eksik, eski veya başarısız; aşağıdaki içeriklerin kapsamını incele.',
    'inactive': 'Kuruluş etkin değil; kayıtlı içerik geçmişi korunuyor.',
}


def register_company_content_parser(actions):
    parser = actions.add_parser('content', help='Firma ve seçili tedarikçi içeriklerini sade biçimde göster; ağsız okuma.')
    parser.add_argument('organization_id')
    for name, default in (('scope-offset', 0), ('scope-limit', 50), ('offset', 0), ('limit', 50),
                          ('stale-after-hours', 24)):
        parser.add_argument('--' + name, type=int, default=default)
    parser.add_argument('--history', action='store_true', help='Eski kapsamın içeriklerini ayrıca göster.')


def content_lines(report, *, data_dir=None, history=False):
    lines = [f"Firma içerikleri: {safe_text(report['organization']['name'])}",
             STATES[report['state']], '']
    for scope in report['scopes']['items']:
        if scope['scope_status'] == 'current':
            lines.append(f"{safe_text(scope['target']['name'])}: {STATES[scope['state']]}")
    sections = [('content', 'Güncel kapsam')]
    if history:
        sections.append(('historical_content', 'Eski kapsamın kayıtlı içerikleri'))
    for kind, label in sections:
        page = report['sections'][kind]
        if page['items']:
            lines.extend(('', label))
        for item in page['items']:
            lines.extend(('', safe_text(item['title']),
                f"  İlgili firma: {safe_text(item['target']['name'])}",
                f"  İçerik: {safe_text(item['available_excerpt']) if item['available_excerpt'] else 'Kaynak açıklama sağlamadı.'}",
                f"  Kaynak: {safe_text(item['source_url'])}",
                f"  Yayın tarihi: {safe_text(item['published_at']) if item['published_at'] else 'Kaynak belirtmedi.'}"))
            if item['match_status'] == 'provider_candidate':
                lines.append('  İnceleme adayı: görünen metinde firma eşleşmesi yok; sağlayıcının önerisi.')
            else:
                lines.append('  Eşleşen ifade: ' + ', '.join(safe_text(term) for term in item['matched_terms']))
            if item['status'] == 'retained_candidate':
                lines.append('  Önceki aramadan korunuyor; son aramada yeniden görülmedi.')
        if page['has_more']:
            lines.append(f"Sonraki içerik sayfası: {_next(report, data_dir, history, offset=page['offset'] + page['limit'])}")
    scopes = report['scopes']
    if scopes['has_more']:
        lines.append(f"Sonraki kontrol kapsamı: {_next(report, data_dir, history, scope_offset=scopes['offset'] + scopes['limit'])}")
    lines.append('Bu görünüm kayıtlı sonuçları okur; yeni internet araması başlatmaz.')
    return lines


def _next(report, data_dir, history, *, offset=None, scope_offset=None):
    page = report['sections']['content']
    scope = report['scopes']
    command = ['./xti'] + (['--data-dir', str(data_dir)] if data_dir is not None else [])
    command += ['organizations', 'content', report['organization']['id'],
                '--offset', str(page['offset'] if offset is None else offset), '--limit', str(page['limit']),
                '--scope-offset', str(scope['offset'] if scope_offset is None else scope_offset),
                '--scope-limit', str(scope['limit']), '--stale-after-hours', str(report['stale_after_hours'])]
    if history:
        command.append('--history')
    return safe_text(shlex.join(command))
