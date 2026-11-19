"""Revision-bound report context in research; no attribution or new IOC claim."""

from dataclasses import replace

from xti.domain.assets import ValidationError
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.research import ResearchEdge, ResearchEvidence, ResearchNode, identity
from xti.domain.reports import MAX_REPORT_CHANGES


def document_id(report_id, revision):
    return f'{report_id}:{revision}'


def parse_document_id(value):
    try:
        report_id, revision = value.split(':')
        normalize_knowledge_id(report_id)
        number = int(revision)
        if str(number) != revision or not 1 <= number <= MAX_REPORT_CHANGES:
            raise ValueError('Document revision')
        return report_id, number
    except (ValueError, AttributeError, TypeError) as error:
        raise ValidationError('Rapor belge başvurusu geçersiz.') from error


def document_node(record, revision):
    stored = record['documents'][revision - 1]
    doc = stored['document']
    identifier = document_id(record['id'], revision)
    current = revision == len(record['documents'])
    published = doc['publication']['at'] or doc['publication']['date'] or 'bilinmiyor'
    text_scope = ('Yayıncı HTML/PDF ana metni; görsel, OCR ve ek bağlantılar dahil değildir. '
        if doc['model_version'] == 2 else 'Yalnız saklı başlık ve özet; tam makale değildir. ')
    proof = ResearchEvidence('report_document', identifier, doc['provider'], doc['source_reference'],
        'candidate_context', 'current_document' if current else 'historical_document',
        doc['collected_at'], stored['recorded_at'],
        f"Rapor {record['id']}, belge sürümü {revision}; kaynak kaydı {doc['source_record_id']}; "
        f"yayın zamanı {published} ({doc['publication']['precision']}); "
        'olay/gözlem zamanı bilinmiyor. ' + text_scope +
        'Alınma zamanı yeniden yakalama veya insan kararıyla güncellenmez.',
        current=current, state_sha256=doc['content_sha256'], source_run_id=doc['source_run_id'],
        time_basis='response_received_at')
    reference = dict(kind='report', record_type='report_document', namespace='local-reports', record_id=identifier)
    return ResearchNode(('report_document', identifier), f"{doc['title']} [belge {revision}]",
        'report_document', references=(reference,), evidence=(proof,), evidence_total_count=1)


def bindings(record, revision):
    """Yield endpoints without materializing an unbounded cross-report graph."""
    doc = record['documents'][revision - 1]['document']
    for candidate in doc['candidates']:
        yield (candidate['indicator_type'], candidate['value']), 'report_text_mention', candidate
    for domain in doc['scope']:
        yield ('domain', domain), 'report_search_scope', None
    for link in record['links'].values():
        if link['document_revision'] == revision:
            target = link['target']
            endpoint = ('entity', target['id']) if target['kind'] == 'entity' else (target['type'], target['label'])
            yield endpoint, 'report_reviewed_link', link


def report_edge(record, revision, node, target, relationship, detail):
    proof = node.evidence[0]
    evidence = (proof,)
    kind = 'candidate_context'
    if relationship == 'report_text_mention':
        evidence = (replace(proof, record_type='report_text_mention',
            description=proof.description + f" Metindeki aralık [{detail['start']}, {detail['end']}): {detail['original']}. "
            'Metinde geçmek zararlılık veya saldırı ilişkisi kanıtı değildir.',
            state_sha256=identity(proof.state_sha256, detail)),)
    elif relationship == 'report_search_scope':
        evidence = (replace(proof, record_type='report_search_scope',
            description=proof.description + ' Bu domain özgün aramanın kapsamıdır; metinde geçtiği anlamına gelmez.'),)
    else:
        kind = 'human_decision'
        events = [event for event in record['history'] if event['action'] == 'link_decided'
            and event['document_revision'] == revision
            and (event['target']['kind'], event['target']['id']) == (detail['target']['kind'], detail['target']['id'])]
        evidence += tuple(ResearchEvidence('report_link_decision', proof.record_id, 'local-report-review',
            proof.source_reference, 'human_decision', event['state'], event['recorded_at'], event['recorded_at'],
            f"Belge sürümü {revision}; rapor değişikliği {event['revision']}; " + event['reason'] +
            '; yalnız bu belge ile hedef arasında insan bağlantısıdır; doğrudan saldırı atfı değildir.',
            event_id=identity(record['id'], event['revision']), current=index == 0,
            state_sha256=identity(event), time_basis='decision_recorded_at')
            for index, event in enumerate(reversed(events)))
    return ResearchEdge('report:' + identity(node.key, target, relationship), node.key, target,
        relationship, kind, evidence[:52], len(evidence))
