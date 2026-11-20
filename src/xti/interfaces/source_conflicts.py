"""Explain exact recorded disagreement without labelling a source as true."""
from xti.interfaces.text import safe_text, xti_command


def conflict_lines(data, *, data_dir=None):
    lines = ['Kaynak değerlendirmesi: ' + safe_text(data['query']['value'])]
    for item in data['items']:
        lines.append(safe_text(item['subject']) + ' | ' + item['reason'])
        for row in item['observations']:
            qualifier = ' | karşılaştırma dışında: ' + row['excluded_reason'] if row['excluded_reason'] else ''
            lines.append('  ' + safe_text(row['source']) + ': ' + safe_text(row['value']) +
                         ' | ' + safe_text(row['observed_at']) + qualifier)
            lines.append('    Kanıt: ' + safe_text(row['record_id']) + ' | ' + safe_text(row['source_reference']))
    if not data['items']:
        lines.append('Bu kapsamda desteklenen türde karşılaştırılabilir kayıt bulunmadı.')
    if not data['coverage_complete']:
        lines.append('Kapsam kısmi; gösterilmeyen kayıtlar değerlendirilmiş sayılmaz.')
    if data['has_more']:
        lines.append('Sonraki sayfa: ' + xti_command('research', data['query']['value'], '--type', data['query']['indicator_type'],
            '--conflicts', '--offset', str(data['next_offset']), '--limit', str(data['limit']),
            '--max-hops', str(data['query']['max_hops']), '--node-limit', str(data['query']['node_limit']),
            '--edge-limit', str(data['query']['edge_limit']), '--stale-after-hours', str(data['query']['stale_after_hours']),
            '--expected-snapshot', data['snapshot_id'], data_dir=data_dir))
    return lines + data['notes']
