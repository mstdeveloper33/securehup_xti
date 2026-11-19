"""Frozen selected document steps, without network or storage dependencies."""

from xti.domain.assets import ValidationError
from xti.domain.publisher_documents import publisher_url
from xti.domain.collection_history import history_uuid
from xti.domain.reports import sha


def documents(value):
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 5:
        raise ValidationError('Yayıncı işi için 1–5 belge açıkça seçilmeli.')
    result = []
    for row in value:
        if not isinstance(row, dict) or set(row) != {'provider', 'url'} or not isinstance(row['provider'], str):
            raise ValidationError('Her belge provider ve url içermeli.')
        # Historical queue validation is independent of later active allowlists.
        url = publisher_url(row['provider'], row['url'], policy='publisher-text-v1')
        item = {'provider': row['provider'], 'url': url}
        if item in result:
            raise ValidationError('Aynı yayıncı belgesi bir işte iki kez seçilemez.')
        result.append(item)
    return result


def document_for(key, plan):
    keys = [f'publisher:{index + 1}' for index in range(len(plan.get('publisher_documents', [])))]
    if key not in keys:
        raise ValidationError('Yayıncı belge adımı planla uyuşmuyor.')
    return plan['publisher_documents'][keys.index(key)]


def validate_publisher_receipt(key, value, plan):
    selected = document_for(key, plan)
    if (set(value) != {'kind', 'provider', 'url', 'run_id', 'source_status', 'document'}
            or value['kind'] != 'publisher_document'
            or any(value[name] != selected[name] for name in ('provider', 'url'))
            or value['source_status'] not in {'complete', 'failed'}):
        raise ValidationError('Yayıncı işi kanıtı seçilen belgeyle uyuşmuyor.')
    history_uuid(value['run_id'])
    doc = value['document']
    if value['source_status'] == 'failed':
        if doc is not None:
            raise ValidationError('Başarısız yayıncı adımı belge üretemez.')
    else:
        if not isinstance(doc, dict) or set(doc) != {'id', 'document_revision', 'content_sha256'}:
            raise ValidationError('Yayıncı işi belge başvurusu geçersiz.')
        history_uuid(doc['id'])
        sha(doc['content_sha256'])
        if type(doc['document_revision']) is not int or not 1 <= doc['document_revision'] <= 1000:
            raise ValidationError('Yayıncı işi belge sürümü geçersiz.')
