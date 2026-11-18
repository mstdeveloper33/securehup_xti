"""Deterministic candidate extraction from bounded, preserved source text."""

import re
import hashlib
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.cti_indicators import normalize_indicator_value
from xti.domain.research import identity


POLICY = 'report-candidates-v1'
PATTERNS = (
    ('url', re.compile(r'(?i)\b(?:https?|hxxps?)://[^\s<>"\x00-\x1f]{1,2048}')),
    ('sha1', re.compile(r'(?i)(?<![a-z0-9])[a-f0-9]{40}(?![a-z0-9])')),
    ('md5', re.compile(r'(?i)(?<![a-z0-9])[a-f0-9]{32}(?![a-z0-9])')),
    ('ipv6', re.compile(r'(?i)(?<![a-z0-9:])(?:[a-f0-9]{0,4}:){2,7}[a-f0-9]{0,4}(?![a-z0-9:])')),
    ('sha256', re.compile(r'(?i)(?<![a-z0-9])[a-f0-9]{64}(?![a-z0-9])')),
    ('ipv4', re.compile(r'(?<![\w.])(?:\d{1,3}(?:\.|\[\.\])){3}\d{1,3}(?![\w.])')),
    ('domain', re.compile(r'(?i)(?<![\w@-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\[\.\])+(?:[a-z]{2,63})(?![\w-])')),
)


def extract(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 65536:
        raise ValidationError('Rapor metni en fazla 64 KiB olmalı.')
    found = {}
    for kind, pattern in PATTERNS:
        for match in pattern.finditer(text):
            original = match.group().rstrip('.,;!)')
            value = original.replace('[.]', '.')
            if kind == 'url':
                value = re.sub(r'^hxxp', 'http', value, flags=re.I)
            try:
                value = normalize_domain(value) if kind == 'domain' else normalize_indicator_value(kind, value)
            except ValidationError:
                continue
            key = (kind, value)
            if key not in found:
                found[key] = {'indicator_type': kind, 'value': value, 'start': match.start(),
                    'end': match.start() + len(original), 'original': original,
                    'relationship': 'report_mentions_candidate'}
            if len(found) > 200:
                raise ValidationError('Rapor 200 aday sınırını aşıyor; eksik liste saklanmadı.')
    return [found[key] for key in sorted(found)]


def report_proposal(*, source, source_reference, source_record_id, source_run_id, text,
                    observed_at, scope, source_sha256, source_text_truncated=False):
    from xti.domain.cti_indicators import normalize_cti_timestamp
    from xti.domain.cti_knowledge import normalize_knowledge_id
    if source not in {'news', 'mentions'}:
        raise ValidationError('Rapor kaynağı news veya mentions olmalı.')
    normalize_knowledge_id(source_run_id)
    if any(not isinstance(value, str) or not 1 <= len(value) <= 4096 or not value.isprintable()
           for value in (source_reference, source_record_id)):
        raise ValidationError('Rapor kaynağı başvurusu geçersiz.')
    if re.fullmatch('[a-f0-9]{64}', source_sha256 or '') is None:
        raise ValidationError('Raporun özgün içerik özeti gerekli.')
    if not isinstance(scope, (list, tuple)) or len(scope) > 100:
        raise ValidationError('Rapor arama kapsamı geçersiz.')
    if type(source_text_truncated) is not bool:
        raise ValidationError('Kaynak metin kesilme bilgisi boolean olmalı.')
    domains = sorted({normalize_domain(value) for value in scope})
    return {'kind': 'report', 'policy_version': POLICY, 'source': source, 'source_reference': source_reference,
        'source_record_id': source_record_id, 'source_run_id': source_run_id,
        'text': text, 'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
        'source_sha256': source_sha256, 'source_text_truncated': source_text_truncated, 'observed_at': normalize_cti_timestamp(observed_at),
        'scope': domains, 'candidates': extract(text)}


def validate_report(value):
    fields = {'kind', 'policy_version', 'source', 'source_reference', 'source_record_id', 'source_run_id',
              'text', 'text_sha256', 'source_sha256', 'source_text_truncated', 'observed_at', 'scope', 'candidates'}
    if set(value) != fields:
        raise ValidationError('Rapor aday alanları geçersiz.')
    expected = report_proposal(**{key: value[key] for key in fields - {'kind', 'policy_version', 'text_sha256', 'candidates'}})
    if value != expected:
        raise ValidationError('Rapor adayları özgün metin ve çıkarım kuralıyla uyuşmuyor.')
    return value
