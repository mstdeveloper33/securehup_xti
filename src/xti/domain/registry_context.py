"""Selected RIR registration context; registry identity is not customer ownership."""

import ipaddress
from xti.domain.indicator_enrichment import EnrichmentSnapshot, request_url, _text
from xti.domain.research import identity

FIELDS = {'inetnum', 'inet6num', 'netname', 'country', 'organisation', 'org-name',
          'status', 'source', 'descr', 'route', 'route6', 'origin'}


def registry_snapshot(query, status, data, digest):
    if status != 200 or data.get('status') != 'ok' or data.get('data_call_name') != 'whois':
        raise ValueError('Invalid WHOIS response')
    payload = data['data']
    if not isinstance(payload, dict) or payload.get('resource') != query.value:
        raise ValueError('Wrong WHOIS query scope')
    params = data.get('query_params', {})
    if not isinstance(params, dict) or params.get('resource', query.value) != query.value:
        raise ValueError('Wrong WHOIS parameters')
    authorities, rows = payload.get('authorities'), payload.get('records')
    if not isinstance(authorities, list) or len(authorities) > 20 or not isinstance(rows, list) or len(rows) > 100:
        raise ValueError('Registry window')
    authorities = sorted({_text(value, limit=100) for value in authorities})
    records, seen, excluded = [], set(), 0
    address = ipaddress.ip_address(query.value)
    for row in rows:
        if not isinstance(row, list) or len(row) > 200:
            raise ValueError('Registry record size')
        attrs = {}
        for entry in row:
            if not isinstance(entry, dict) or not isinstance(entry.get('key'), str):
                raise ValueError('Registry field')
            key = entry['key'].lower()
            if key in FIELDS:
                attrs.setdefault(key, []).append(_text(entry['value']))
        if not attrs:
            excluded += 1
            continue
        links, in_scope = [], True
        for key in ('inetnum', 'inet6num', 'route', 'route6'):
            for value in attrs.get(key, []):
                if '-' in value:
                    start, end = [ipaddress.ip_address(part.strip()) for part in value.split('-', 1)]
                    if start.version != end.version or int(start) > int(end):
                        raise ValueError('Registry range')
                    present = address.version == start.version and int(start) <= int(address) <= int(end)
                    normalized, kind = f'{start}-{end}', 'network_range'
                else:
                    network = ipaddress.ip_network(value, strict=True)
                    present = address in network
                    normalized, kind = str(network), 'network_prefix'
                if not present:
                    in_scope = False
                links.append(dict(source_type=query.indicator_type, source_value=query.value,
                    target_type=kind, target_value=normalized, relationship_type='registry_reports_range'))
        if not in_scope:
            excluded += 1
            continue
        for handle in attrs.get('organisation', []):
            links.append(dict(source_type=query.indicator_type, source_value=query.value,
                target_type='registry_entity', target_value=','.join(authorities) + ':' + handle,
                relationship_type='registry_references_entity'))
        attrs = {key: sorted(set(value)) for key, value in sorted(attrs.items())}
        identifier = identity(authorities, attrs)
        if identifier in seen:
            continue
        seen.add(identifier)
        records.append(dict(id=identifier, reference=request_url(query), observed_at=None,
            description='RIPE NCC / ilgili RIR kayıt bilgisi; teknik sahiplik doğrulaması, fiziksel konum veya saldırı atfı değildir.',
            attributes={'authorities': authorities, 'registration': attrs, 'attribution': 'RIPE NCC / RIR'},
            relationships=sorted(links, key=lambda link: identity(link))))
    return EnrichmentSnapshot(digest, 'matched' if records else 'no_match', tuple(records), False, excluded)
