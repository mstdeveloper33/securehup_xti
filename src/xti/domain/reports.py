"""Immutable source documents and revision-bound human links; no IO."""

from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
import re

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.cti_indicators import normalize_cti_timestamp, normalize_indicator_value
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.news import news_text, news_url, news_source
from xti.domain.report_extraction import extract_document, DOCUMENT_POLICY as EXTRACTION_POLICY
from xti.domain.research import identity

MODEL_VERSION = 1
MAX_ENTRIES = 10000
MAX_BYTES = 32 * 1024 * 1024
MAX_REPORT_CHANGES = 1000
MAX_REPORT_BYTES = 2 * 1024 * 1024


class ReportError(ValidationError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def sha(value):
    if not isinstance(value, str) or re.fullmatch('[a-f0-9]{64}', value) is None:
        raise ValidationError('İçerik özeti geçersiz.')
    return value


def publication(raw, normalized=None):
    """Retain provider text; never invent time or timezone for date-only values."""
    if raw is not None:
        news_text(raw, maximum=256)
    result = {'raw': raw, 'at': None, 'date': None, 'precision': 'unknown'}
    if raw is not None and re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
        try:
            result.update(date=date.fromisoformat(raw).isoformat(), precision='date')
        except ValueError:
            pass
        return result
    candidate = normalized or raw
    if candidate:
        try:
            try:
                at = datetime.fromisoformat(candidate.replace('Z', '+00:00'))
            except ValueError:
                at = parsedate_to_datetime(candidate)
            if at.tzinfo is not None and at.utcoffset() is not None:
                result.update(at=at.astimezone(timezone.utc).isoformat(), precision='timestamp')
        except (ValueError, TypeError, OverflowError):
            pass
    return result


def document(*, source, provider, source_record_id, source_reference, title, summary,
             summary_truncated, published_raw, published_normalized, source_updated_at,
             source_run_id, source_sha256, collected_at, scope):
    if source not in ('news', 'mentions'):
        raise ValidationError('Rapor kaynağı news veya mentions olmalı.')
    if source == 'news':
        news_source(provider)
    elif provider != 'tavily':
        raise ValidationError('Firma raporu sağlayıcısı geçersiz.')
    for value, maximum in ((provider, 100), (source_record_id, 128), (title, 500)):
        news_text(value, maximum=maximum)
    news_text(summary, maximum=2000, empty=True)
    news_url(source_reference)
    if type(summary_truncated) is not bool or not isinstance(scope, list) or len(scope) > 100:
        raise ValidationError('Rapor özet/kapsam bilgisi geçersiz.')
    source_run_id = normalize_knowledge_id(source_run_id)
    sha(source_sha256)
    collected_at = normalize_cti_timestamp(collected_at)
    if source_updated_at is not None:
        source_updated_at = normalize_cti_timestamp(source_updated_at)
    if published_normalized is not None:
        published_normalized = normalize_cti_timestamp(published_normalized)
    result = dict(source=source, provider=provider, source_record_id=source_record_id,
        source_reference=source_reference, title=title, summary=summary,
        summary_truncated=summary_truncated, published_raw=published_raw,
        published_normalized=published_normalized, source_updated_at=source_updated_at,
        source_run_id=source_run_id, source_sha256=source_sha256, collected_at=collected_at,
        scope=sorted({normalize_domain(value) for value in scope}))
    text = title + '\n' + summary
    result.update(model_version=MODEL_VERSION, publication=publication(published_raw, published_normalized),
                  text=text, extraction_policy=EXTRACTION_POLICY, candidates=extract_document(text))
    result['content_sha256'] = identity({k: v for k, v in result.items()
        if k not in {'source_run_id', 'source_sha256', 'collected_at'}})
    return result


DOCUMENT_INPUTS = ('source', 'provider', 'source_record_id', 'source_reference', 'title', 'summary',
    'summary_truncated', 'published_raw', 'published_normalized', 'source_updated_at',
    'source_run_id', 'source_sha256', 'collected_at', 'scope')


def validate_document(value):
    if isinstance(value, dict) and value.get('model_version') == 2:
        from xti.domain.publisher_documents import validate_full_document
        return validate_full_document(value)
    if not isinstance(value, dict) or document(**{k: value[k] for k in DOCUMENT_INPUTS}) != value:
        raise ValidationError('Rapor belge kanıtı veya çıkarılan adaylar tutarsız.')


def report_view(record, document_revision=None):
    if record is None:
        raise ReportError('not_found', 'Rapor seçili çalışma alanında bulunamadı.')
    selected = document_revision or len(record['documents'])
    if selected > len(record['documents']):
        raise ReportError('not_found', 'Rapor belge sürümü bulunamadı.')
    doc = record['documents'][selected - 1]
    return {'id': record['id'], 'revision': record['revision'], 'document_revision': selected,
        'current_document_revision': len(record['documents']), 'document': doc['document'],
        'recorded_at': doc['recorded_at'], 'state_sha256': identity(record),
        'links': [value for value in record['links'].values() if value['document_revision'] == selected],
        'history': record['history']}


def project(entries):
    """Validate semantic replay, including no-op receipts and optimistic fences."""
    from xti.domain.report_contract import parameters
    records, sources, keys = {}, {}, set()
    previous_at = None
    fields = {'version', 'id', 'report_id', 'request_key', 'operation', 'request', 'recorded_at', 'payload'}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != fields or type(entry['version']) is not int or entry['version'] != 1:
            raise ValidationError('Rapor journal alanları geçersiz.')
        for field in ('id', 'report_id'):
            if normalize_knowledge_id(entry[field]) != entry[field]:
                raise ValidationError('Rapor kimliği geçersiz.')
        at = normalize_cti_timestamp(entry['recorded_at'])
        if at != entry['recorded_at'] or (previous_at is not None and at < previous_at):
            raise ValidationError('Rapor kayıt zamanı sırası geçersiz.')
        previous_at = at
        request = parameters(entry['operation'], entry['request'], scoped=False, stored=True)
        if request != entry['request'] or request['idempotency_key'] != entry['request_key'] or entry['request_key'] in keys:
            raise ValidationError('Rapor tekrar anahtarı veya isteği tutarsız.')
        keys.add(entry['request_key'])
        rid, payload = entry['report_id'], entry['payload']
        record = records.get(rid)
        if entry['operation'] in ('reports.capture', 'reports.fetch'):
            source_key = (('publisher', identity('publisher-url-v1', request['provider'], request['url']))
                if entry['operation'] == 'reports.fetch' else (request['source'], request['identifier']))
            if sources.get(source_key, rid) != rid or (record is not None and record['source_key'] != list(source_key)):
                raise ValidationError('Rapor kaynak kimliği değişmiş.')
            if payload is None:
                if record is None:
                    raise ValidationError('İlk rapor belgesi eksik.')
                if request.get('expected_content_sha256', record['documents'][-1]['document']['content_sha256']) != record['documents'][-1]['document']['content_sha256']:
                    raise ValidationError('Değişmeyen rapor makbuzu kaynak kesitiyle uyuşmuyor.')
                continue
            validate_document(payload)
            if request.get('expected_content_sha256', payload['content_sha256']) != payload['content_sha256']:
                raise ValidationError('Rapor kaynak kesiti beklenen içerikle uyuşmuyor.')
            if ((payload['source'], payload['source_record_id']) != source_key or payload['collected_at'] > at):
                raise ValidationError('Rapor kaynak bağı veya toplama zamanı tutarsız.')
            if record is None:
                record = records[rid] = {'id': rid, 'source_key': list(source_key), 'revision': 0,
                    'documents': [], 'links': {}, 'history': []}
                sources[source_key] = rid
            elif record['documents'][-1]['document']['content_sha256'] == payload['content_sha256']:
                raise ValidationError('Değişmeyen rapor için yeni belge sürümü oluşturulamaz.')
            record['documents'].append({'document': payload, 'recorded_at': at})
            selected_document = len(record['documents'])
            history = {'action': 'captured', 'content_sha256': payload['content_sha256']}
        elif entry['operation'] == 'reports.link':
            if record is None or request['identifier'] != rid:
                raise ValidationError('Bağlantı raporu eksik.')
            if request['expected_revision'] != record['revision']:
                raise ReportError('revision_changed', 'Rapor değişmiş; güncel sürümü yeniden alın.')
            selected_document = request.get('document_revision', len(record['documents']))
            if selected_document > len(record['documents']):
                raise ReportError('not_found', 'Bağlanacak rapor belge sürümü bulunamadı.')
            key = identity(selected_document, request['target_kind'], request['target_id'])
            old = record['links'].get(key)
            if payload is None:
                if old is None or any(old[k] != request[k] for k in ('state', 'reason')):
                    raise ValidationError('Değişmeyen bağlantı makbuzu tutarsız.')
                continue
            validate_target(payload)
            if (payload['id'], payload['kind']) != (request['target_id'], request['target_kind']):
                raise ValidationError('Rapor bağlantısı farklı hedefe bağlı.')
            if request['state'] == 'withdrawn' and (old is None or payload != old['target']):
                raise ValidationError('Geri çekilecek mevcut bağlantı gerekli.')
            if old is not None and all(old[k] == request[k] for k in ('state', 'reason')):
                raise ValidationError('Değişmeyen bağlantı yeniden oluşturulamaz.')
            history = {'action': 'link_decided', 'relationship': 'reports-on', 'target': payload,
                       'state': request['state'], 'reason': request['reason']}
            record['links'][key] = {**history, 'document_revision': selected_document, 'recorded_at': at}
        else:
            raise ValidationError('Rapor journal işlemi geçersiz.')
        record['revision'] += 1
        record['history'].append({**history, 'revision': record['revision'],
                                 'document_revision': selected_document, 'recorded_at': at})
        if record['revision'] > MAX_REPORT_CHANGES:
            raise ValidationError('Tek rapor değişiklik sınırını aşıyor.')
    # Every mutation response (including complete history) must fit before
    # commit; a successful write must not become a response-too-large error.
    from xti.domain.engine_jobs import canonical_json
    if any(len(canonical_json(record).encode('ascii')) > MAX_REPORT_BYTES for record in records.values()):
        raise ValidationError('Tek rapor kanıt/geçmiş byte sınırını aşıyor; işlem kaydedilmedi.')
    return records


def validate_target(value):
    if not isinstance(value, dict) or set(value) != {'kind', 'id', 'type', 'label', 'state_sha256', 'assertion_ids'}:
        raise ValidationError('Rapor bağlantısı kanıt alanları geçersiz.')
    normalize_knowledge_id(value['id'])
    sha(value['state_sha256'])
    news_text(value['label'], maximum=2048)
    if value['kind'] == 'entity':
        if value['type'] not in ('threat-actor', 'campaign', 'malware'):
            raise ValidationError('Bağlantı aktör, kampanya veya malware kaydına ait olmalı.')
    elif value['kind'] == 'indicator':
        normalize_indicator_value(value['type'], value['label'])
    else:
        raise ValidationError('Bağlantı hedef türü geçersiz.')
    if not isinstance(value['assertion_ids'], list) or not 1 <= len(value['assertion_ids']) <= 500:
        raise ValidationError('Bağlantı kaynak iddiası gerekli.')
    for identifier in value['assertion_ids']:
        normalize_knowledge_id(identifier)
