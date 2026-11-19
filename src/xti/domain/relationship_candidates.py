"""Deterministic two-edge hypotheses; never automatic attribution or a CTI assertion."""

from dataclasses import asdict
from xti.domain.research import identity, node_id

RULES = {
    'shared_report': 'Aynı kayıtlı raporda iki gösterge geçiyor; birlikte geçme ilişki adayıdır.',
    'report_review_context': 'Göstergeyi anan rapora insan bağlantısı var; doğrudan aktör atfı değildir.',
    'shared_dns_address': 'Kayıtlı DNS kontrollerinde aynı IP kullanılmış; ortak barındırma olabilir.',
    'shared_certificate': 'Aynı sunulmuş sertifika kayıtlı; aynı işletmeci veya tehdit sonucu değildir.',
}


def candidates(graph):
    nodes = {node_id(node.key): node for node in graph.nodes}
    edges = {edge.id: edge for edge in graph.edges}
    result = {}
    for path, links in graph.paths:
        if len(links) != 2 or len(path) != 3 or path[0] != graph.root_id:
            continue
        left, right = (edges[key] for key in links)
        middle = nodes[path[1]]
        types = {left.relationship_type, right.relationship_type}
        rule = ('shared_report' if middle.key[0] == 'report_document' and types == {'report_text_mention'} else
                'report_review_context' if middle.key[0] == 'report_document' and types == {'report_text_mention', 'report_reviewed_link'} else
                'shared_dns_address' if middle.key[0] in ('ipv4', 'ipv6') and types == {'dns_address'} else
                'shared_certificate' if middle.key[0] == 'certificate' and types == {'certificate_presented'} else None)
        if rule is None:
            continue
        identifier = identity('relationship-candidate-v1', rule, [nodes[key].key for key in path])
        proof = [{'id': edge.id, 'source': list(edge.source), 'target': list(edge.target),
                  'relationship_type': edge.relationship_type, 'kind': edge.kind,
                  'evidence': [asdict(row) for row in edge.evidence],
                  'evidence_total_count': edge.evidence_total_count} for edge in (left, right)]
        rows = [row for edge in proof for row in edge['evidence']]
        historical = any(row['current'] is False or row['status'] in ('withdrawn', 'revoked', 'historical_document', 'expired') for row in rows)
        result[identifier] = {'id': identifier, 'rule': rule, 'reason': RULES[rule],
            'root': list(nodes[path[0]].key), 'via': list(middle.key), 'target': list(nodes[path[2]].key),
            'evidence': proof, 'evidence_sha256': identity(proof),
            'evidence_scope': 'historical_or_withdrawn' if historical else 'stored_context',
            'coverage_complete': not graph.limitations and all(len(e['evidence']) == e['evidence_total_count'] for e in proof),
            'limitations': list(graph.limitations)}
    return sorted(result.values(), key=lambda row: row['id'])
