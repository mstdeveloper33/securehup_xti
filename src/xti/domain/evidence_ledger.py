"""Replayable sightings and candidate reviews, with immutable source identity."""

from datetime import datetime, timedelta
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.evidence_contract import parameters, WRITES
from xti.domain.research import identity
from xti.domain.reports import ReportError, sha
from xti.domain.engine_jobs import canonical_json

MAX_ENTRIES = 20_000
MAX_BYTES = 64 * 1024 * 1024
MAX_RECORD_BYTES = 2 * 1024 * 1024


def sighting_key(request):
    return identity(request['source'], request['sensor'], request['source_event_id'])


def validate_candidate(row):
    from dataclasses import fields
    from xti.domain.research import ResearchEvidence
    from xti.domain.evidence_contract import text
    from xti.domain.relationship_candidates import RULES
    if not isinstance(row, dict) or set(row) != {'id', 'rule', 'reason', 'root', 'via', 'target', 'evidence',
            'evidence_sha256', 'evidence_scope', 'coverage_complete', 'limitations'}:
        raise ValidationError('İlişki dayanağı geçersiz.')
    sha(row['id']); sha(row['evidence_sha256'])
    if row['rule'] not in RULES or row['reason'] != RULES[row['rule']]:
        raise ValidationError('İlişki kuralı geçersiz.')
    for key in ('root', 'via', 'target'):
        if not isinstance(row[key], list) or len(row[key]) != 2:
            raise ValidationError('İlişki ucu geçersiz.')
        text(row[key][0], 80); text(row[key][1], 8192)
    if len({tuple(row[key]) for key in ('root', 'via', 'target')}) != 3:
        raise ValidationError('İlişki yolu çevrim içeremez.')
    if row['id'] != identity('relationship-candidate-v1', row['rule'], [tuple(row[k]) for k in ('root', 'via', 'target')]):
        raise ValidationError('İlişki adayı kimliği uyuşmuyor.')
    if row['evidence_sha256'] != identity(row['evidence']) or not isinstance(row['evidence'], list) or len(row['evidence']) != 2:
        raise ValidationError('İlişki dayanağı özeti uyuşmuyor.')
    if type(row['coverage_complete']) is not bool or not isinstance(row['limitations'], list):
        raise ValidationError('İlişki kapsamı geçersiz.')
    if row['evidence_scope'] not in ('historical_or_withdrawn', 'stored_context'):
        raise ValidationError('İlişki kanıt kapsamı geçersiz.')
    for index, edge in enumerate(row['evidence']):
        if not isinstance(edge, dict) or set(edge) != {'id', 'source', 'target', 'relationship_type', 'kind', 'evidence', 'evidence_total_count'}:
            raise ValidationError('İlişki dayanağı bağlantısı geçersiz.')
        expected = [row['root'], row['via']] if index == 0 else [row['via'], row['target']]
        if sorted([edge['source'], edge['target']]) != sorted(expected):
            raise ValidationError('İlişki dayanağı farklı uçlara ait.')
        for key in ('id', 'relationship_type', 'kind'):
            text(edge[key], 128)
        if not isinstance(edge['evidence'], list) or not 1 <= len(edge['evidence']) <= 52 or type(edge['evidence_total_count']) is not int or edge['evidence_total_count'] < len(edge['evidence']):
            raise ValidationError('İlişki kanıt satırları geçersiz.')
        for item in edge['evidence']:
            if not isinstance(item, dict) or set(item) != {field.name for field in fields(ResearchEvidence)}:
                raise ValidationError('İlişki kanıt başvurusu geçersiz.')
            for key in ('observed_at', 'recorded_at'):
                if normalize_cti_timestamp(item[key]) != item[key]:
                    raise ValidationError('İlişki kanıt saati geçersiz.')
            for key in ('record_type', 'record_id', 'source', 'source_reference', 'kind', 'status'):
                text(item[key], 8192)
            if item['state_sha256'] is not None:
                sha(item['state_sha256'])
    return row


def project(entries):
    records = {}
    natural = {}
    sizes = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'version', 'id', 'subject_id', 'operation', 'request', 'recorded_at', 'candidate'}:
            raise ValidationError('Kanıt günlüğü olayı geçersiz.')
        if type(entry['version']) is not int or entry['version'] != 1 or entry['operation'] not in WRITES:
            raise ValidationError('Kanıt günlüğü sürümü/işlemi geçersiz.')
        normalize_knowledge_id(entry['id'])
        operation, request, identifier, at = (entry[k] for k in ('operation', 'request', 'subject_id', 'recorded_at'))
        if parameters(operation, request) != request or normalize_cti_timestamp(at) != at:
            raise ValidationError('Kanıt isteği veya zamanı kanonik değil.')
        previous = records.get(identifier)
        if previous and at < previous['history'][-1]['recorded_at']:
            raise ValidationError('Kanıt kayıt saati geriye gidemez.')
        if operation == 'sightings.record':
            normalize_knowledge_id(identifier)
            if entry['candidate'] is not None or datetime.fromisoformat(request['observed_at']) > datetime.fromisoformat(at) + timedelta(minutes=5):
                raise ValidationError('Görülme zamanı gelecekte; sensör saatini kontrol edin.')
            key = sighting_key(request)
            payload = {k: v for k, v in request.items() if k != 'idempotency_key'}
            if natural.get(key, identifier) != identifier:
                raise ValidationError('Kaynak olay kimliği çoğalmış.')
            natural[key] = identifier
            if previous:
                if previous['kind'] != 'sighting' or previous['observation'] != payload:
                    raise ReportError('source_event_conflict', 'Aynı kaynak olay kimliği farklı bir gözleme bağlı.')
            else:
                records[identifier] = {'id': identifier, 'kind': 'sighting', 'observation': payload,
                    'state': 'active', 'revision': 0, 'history': []}
        elif operation == 'sightings.revoke':
            if previous is None or previous['kind'] != 'sighting':
                raise ReportError('not_found', 'Görülme kaydı bulunamadı.')
            if identifier != request['identifier'] or previous['revision'] != request['expected_revision'] or entry['candidate'] is not None:
                raise ReportError('revision_changed', 'Görülme kaydı değişmiş; güncel sürümü alın.')
            previous['state'] = 'revoked'
        else:
            row = validate_candidate(entry['candidate'])
            if identifier != request['identifier'] or row['id'] != identifier or row['root'] != [request['indicator_type'], request['value']] or row['evidence_sha256'] != request['evidence_sha256']:
                raise ValidationError('Karar farklı bir ilişki dayanağına ait.')
            if previous is not None and previous['kind'] != 'relationship':
                raise ValidationError('Karar kaydı türü uyuşmuyor.')
            if request['expected_revision'] != (previous['revision'] if previous else 0):
                raise ReportError('revision_changed', 'İlişki kararı değişmiş; güncel sürümü alın.')
            if previous is None and request['decision'] == 'withdrawn':
                raise ValidationError('Geri çekilecek ilişki kararı yok.')
            if previous is None:
                records[identifier] = {'id': identifier, 'kind': 'relationship', 'revision': 0, 'history': []}
            records[identifier].update(candidate=row, decision=request['decision'], reason=request['reason'])
        current = records[identifier]
        current['history'].append(entry)
        current['revision'] += 1
        sizes[identifier] = sizes.get(identifier, 0) + len(canonical_json(entry).encode('ascii'))
        if current['revision'] > 1000:
            raise ValidationError('Tek kanıt kaydı 1000 olay sınırını aşıyor.')
        if sizes[identifier] > MAX_RECORD_BYTES:
            raise ValidationError('Tek kanıt kaydı 2 MiB sınırını aşıyor; önceki kanıt korunur.')
    for current in records.values():
        current['state_sha256'] = identity(current['history'])
    return records
