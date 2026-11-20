"""Evidence-backed stars, never transitive campaigns, ownership or risk votes."""
from collections import defaultdict, Counter
from dataclasses import asdict, fields
from datetime import datetime
import json

from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.engine_jobs import canonical_json
from xti.domain.research import identity, ResearchEvidence
from xti.domain.group_contract import parameters
from xti.domain.reports import sha

POLICY = 'research-groups-v1'
MAX_GROUP_BYTES = 192 * 1024
MAX_MEMBERS = 50
RULES = {'shared_dns_address': 'dns_address', 'shared_certificate': 'certificate_presented',
         'shared_report': 'report_text_mention'}
NOTES = [
    'Gruplar kayıtlı ortak kanıtı gösterir; sahiplik, zararlılık veya saldırgan/kampanya atfı değildir.',
    'Gözlem noktalarının yakınlığı kesintisiz kullanım veya aynı anda faaliyet kanıtı değildir.',
    'Belgenin alınma/yayın tarihi olay zamanı değildir. Bilinmeyen zaman tahmin edilmez.',
    'Tek kaynak veya kopya belge bağımsız doğrulama oyu oluşturmaz; bütün internet araştırılmış sayılmaz.',
]


def _plain(value):
    return json.loads(canonical_json(value))


def temporal(members, window):
    """Smallest observed window covering all members; no first/last interpolation."""
    points = []
    known = 0
    for index, member in enumerate(members):
        times = set()
        for edge in member['edges']:
            for row in edge['evidence']:
                if row['kind'] == 'observation' and row['time_basis'] in (
                        'source_observation', 'sensor_reported_observation'):
                    times.add(row['observed_at'])
        if times:
            known += 1
        points.extend((datetime.fromisoformat(at).timestamp(), index, at) for at in times)
    if known != len(members):
        return {'state': 'unknown', 'window_hours': window, 'members_with_observation_time': known,
                'observed_span_seconds': None, 'from': None, 'to': None}
    points.sort()
    counts, start, best = Counter(), 0, None
    for end, item in enumerate(points):
        counts[item[1]] += 1
        while len(counts) == len(members):
            candidate = (item[0] - points[start][0], points[start][2], item[2])
            if best is None or candidate < best:
                best = candidate
            counts[points[start][1]] -= 1
            if not counts[points[start][1]]:
                del counts[points[start][1]]
            start += 1
    return {'state': 'near_observations' if best[0] <= window * 3600 else 'separated_observations',
            'window_hours': window, 'members_with_observation_time': known,
            'observed_span_seconds': best[0], 'from': best[1], 'to': best[2]}


def compose(root, scope, rule, anchors, members, limitations):
    """Canonical derivation used both on live graphs and immutable proof replay."""
    anchors = sorted(anchors, key=lambda a: a['key'])
    members = sorted(members, key=lambda m: m['key'])
    context = (['report_text', anchors[0]['text_sha256']] if rule == 'shared_report'
               else anchors[0]['key'])
    reasons = []
    if rule == 'shared_dns_address':
        reasons.append('shared_hosting_possible')
    if rule == 'shared_certificate':
        reasons.append('shared_certificate_not_ownership')
    if any(a['warninglist_matches'] for a in anchors):
        reasons.append('warninglist_context')
    if rule == 'shared_report':
        reasons.append('document_cooccurrence_only')
        if len(anchors) > 1:
            reasons.append('duplicate_document_content')
    observations = [row for member in members for edge in member['edges'] for row in edge['evidence']]
    if any(row['current'] is False or row['status'] in ('expired', 'withdrawn', 'revoked', 'historical_document') for row in observations):
        reasons.append('historical_or_withdrawn_evidence')
    if any(edge['evidence_total_count'] != len(edge['evidence']) for member in members for edge in member['edges']):
        limitations = sorted(set(limitations) | {'group_evidence_window'})
    # A repeated check or a document copied by several providers is not a vote.
    proof_keys = {(row['record_type'], row['record_id'], row['event_id'], row['state_sha256']) for row in observations}
    result = {'version': 1, 'policy_version': POLICY,
        'id': identity(POLICY, root, scope, rule, context), 'root': root, 'scope': scope,
        'rule': rule, 'anchors': anchors, 'members': members,
        'temporal': temporal(members, scope['time_window_hours']), 'noise_reasons': sorted(reasons),
        'unique_evidence_count': len(proof_keys), 'coverage_complete': not limitations,
        'limitations': sorted(set(limitations)), 'attribution': 'not_assessed'}
    result['evidence_sha256'] = identity(result)
    return result


def groups(graph, *, time_window_hours=24, report_text_hashes=None):
    nodes = {node.key: node for node in graph.nodes}
    root = [graph.query.indicator_type, graph.query.value]
    scope = {'max_hops': graph.query.max_hops, 'time_window_hours': time_window_hours}
    buckets, missing_text = {}, False
    report_text_hashes = report_text_hashes or {}
    for edge in graph.edges:
        rule = next((key for key, value in RULES.items() if value == edge.relationship_type), None)
        if rule is None:
            continue
        if rule == 'shared_report':
            anchor, member = (edge.source, edge.target) if edge.source[0] == 'report_document' else (edge.target, edge.source)
            node = nodes[anchor]
            content_hash = report_text_hashes.get(anchor[1])
            if content_hash is None:
                missing_text = True
                continue
            bucket_key = rule, content_hash
        else:
            anchor, member = edge.target, edge.source
            content_hash = None
            if member[0] != 'domain' or anchor[0] not in ('ipv4', 'ipv6', 'certificate'):
                continue
            node = nodes[anchor]
            bucket_key = rule, anchor
        if member == anchor:
            continue
        bucket = buckets.setdefault(bucket_key, {'anchors': {}, 'members': {}})
        bucket['anchors'][anchor] = {'key': list(anchor), 'label': node.label,
            'text_sha256': content_hash, 'warninglist_matches': _plain(node.warninglist_matches)}
        item = bucket['members'].setdefault(member, {'key': list(member), 'label': nodes[member].label, 'edges': []})
        proof = _plain(asdict(edge))
        item['edges'].append(proof)
    result, omitted = [], 0
    base_limits = sorted(set(graph.limitations) | ({'group_document_digest_missing'} if missing_text else set()))
    for (rule, _), bucket in sorted(buckets.items(), key=lambda item: str(item[0])):
        if len(bucket['members']) < 2:
            continue
        if len(bucket['members']) > MAX_MEMBERS:
            omitted += 1
            continue
        members = list(bucket['members'].values())
        for member in members:
            member['edges'].sort(key=lambda edge: edge['id'])
        row = compose(root, scope, rule, list(bucket['anchors'].values()), members, base_limits)
        if len(canonical_json(row)) > MAX_GROUP_BYTES:
            omitted += 1
            continue
        result.append(row)
    limitations = sorted(set(base_limits) | ({'group_size_limit'} if omitted else set()))
    if omitted:
        # A truncated group set must not become an apparently complete capture
        # that can be accepted, while preview/queue correctly report partial.
        bounded = []
        for row in result:
            row = compose(root, scope, row['rule'], row['anchors'], row['members'],
                          sorted(set(row['limitations']) | {'group_size_limit'}))
            if len(canonical_json(row)) > MAX_GROUP_BYTES:
                omitted += 1
            else:
                bounded.append(row)
        result = bounded
    return sorted(result, key=lambda row: row['id']), limitations, omitted


def validate_group(row):
    """Check frozen semantics, not just a caller-provided checksum."""
    try:
        if not isinstance(row, dict) or type(row['version']) is not int or row['version'] != 1 or row['policy_version'] != POLICY:
            raise ValueError('Group version')
        sha(row['id']); sha(row['evidence_sha256'])
        query = parameters('groups.preview', dict(indicator_type=row['root'][0], value=row['root'][1], **row['scope']))
        if row['root'] != [query['indicator_type'], query['value']] or set(row['scope']) != {'max_hops', 'time_window_hours'}:
            raise ValueError('Group scope')
        if row['rule'] not in RULES or not isinstance(row['anchors'], list) or not 1 <= len(row['anchors']) <= 100:
            raise ValueError('Group anchor')
        if not isinstance(row['members'], list) or not 2 <= len(row['members']) <= MAX_MEMBERS:
            raise ValueError('Group members')
        anchor_keys = set()
        for anchor in row['anchors']:
            if set(anchor) != {'key', 'label', 'text_sha256', 'warninglist_matches'}:
                raise ValueError('Anchor fields')
            key = tuple(anchor['key'])
            if len(key) != 2 or any(not isinstance(x, str) or not x for x in key) or key in anchor_keys or not isinstance(anchor['label'], str):
                raise ValueError('Anchor identity')
            if not isinstance(anchor['warninglist_matches'], list) or any(not isinstance(x, dict) for x in anchor['warninglist_matches']):
                raise ValueError('Warninglist context')
            anchor_keys.add(key)
            if row['rule'] == 'shared_report':
                sha(anchor['text_sha256'])
                if key[0] != 'report_document' or anchor['text_sha256'] != row['anchors'][0]['text_sha256']:
                    raise ValueError('Document content')
            elif anchor['text_sha256'] is not None or len(row['anchors']) != 1:
                raise ValueError('Infrastructure anchor')
            elif key[0] not in (('ipv4', 'ipv6') if row['rule'] == 'shared_dns_address' else ('certificate',)):
                raise ValueError('Infrastructure type')
        member_keys, edge_keys = set(), set()
        for member in row['members']:
            if set(member) != {'key', 'label', 'edges'} or not isinstance(member['label'], str):
                raise ValueError('Member fields')
            key = tuple(member['key'])
            if len(key) != 2 or any(not isinstance(x, str) or not x for x in key) or key in member_keys or key in anchor_keys:
                raise ValueError('Member identity')
            if row['rule'] != 'shared_report' and key[0] != 'domain':
                raise ValueError('Infrastructure member type')
            member_keys.add(key)
            if not isinstance(member['edges'], list) or not 1 <= len(member['edges']) <= 200:
                raise ValueError('Member evidence')
            for edge in member['edges']:
                if set(edge) != {'id', 'source', 'target', 'relationship_type', 'kind', 'evidence', 'evidence_total_count'}:
                    raise ValueError('Edge fields')
                if not isinstance(edge['id'], str) or edge['id'] in edge_keys or edge['relationship_type'] != RULES[row['rule']]:
                    raise ValueError('Repeated or different edge')
                edge_keys.add(edge['id'])
                if len(edge_keys) > 200:
                    raise ValueError('Group edge budget')
                ends = {tuple(edge['source']), tuple(edge['target'])}
                if key not in ends or len(ends & anchor_keys) != 1:
                    raise ValueError('Edge outside group')
                if not isinstance(edge['evidence'], list) or not 1 <= len(edge['evidence']) <= 52 or type(edge['evidence_total_count']) is not int or edge['evidence_total_count'] < len(edge['evidence']):
                    raise ValueError('Edge evidence count')
                for evidence in edge['evidence']:
                    if set(evidence) != {field.name for field in fields(ResearchEvidence)}:
                        raise ValueError('Evidence fields')
                    for name in ('record_type', 'record_id', 'source', 'source_reference', 'kind', 'status', 'description', 'time_basis'):
                        if not isinstance(evidence[name], str):
                            raise ValueError('Evidence text')
                    if evidence['current'] is not None and type(evidence['current']) is not bool:
                        raise ValueError('Evidence state')
                    if evidence['confidence'] is not None and (type(evidence['confidence']) is not int or not 0 <= evidence['confidence'] <= 100):
                        raise ValueError('Evidence confidence')
                    if evidence['state_sha256'] is not None:
                        sha(evidence['state_sha256'])
                    for name in ('observed_at', 'recorded_at'):
                        if normalize_cti_timestamp(evidence[name]) != evidence[name]:
                            raise ValueError('Evidence timestamp')
        if not isinstance(row['limitations'], list) or any(not isinstance(x, str) for x in row['limitations']):
            raise ValueError('Coverage')
        if compose(row['root'], row['scope'], row['rule'], row['anchors'], row['members'], row['limitations']) != row:
            raise ValueError('Derived group differs')
        if len(canonical_json(row)) > MAX_GROUP_BYTES:
            raise ValueError('Group size')
        return row
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as error:
        raise ValidationError('İnceleme grubu kanıtı veya türetilmiş değerlendirmesi geçersiz.') from error
