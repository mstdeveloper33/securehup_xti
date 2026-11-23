"""Code/paste evidence rules. No network, storage, subprocess or UI dependencies."""
from dataclasses import dataclass
import hashlib
import json
import re
from urllib.parse import urlsplit

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.mentions import mention_uuid

POLICY = 'code-exposure-v1'
PROVIDERS = ('github-repositories', 'github-code', 'gitlab-projects', 'gitlab-code', 'pastebin')
DECISIONS = ('relevant', 'unrelated', 'example', 'uncertain', 'remediated')
READS = ('code.sources', 'code.watch.list', 'code.watch.show', 'code.plan',
         'code.runs', 'code.run.show', 'code.findings', 'code.finding.show',
         'code.changes', 'code.report', 'code.reviews', 'code.evidence.show')
WRITES = ('code.watch.add', 'code.watch.update', 'code.run', 'code.recover', 'code.review')
SCOPE_FIELDS = {'domain', 'name', 'aliases', 'repositories', 'sources', 'max_requests',
                'max_files', 'budget_seconds', 'interval_seconds'}
MAX_FILE_BYTES = 256 * 1024
MAX_RUN_BYTES = 32 * 1024 * 1024
MAX_CANDIDATES = 1000  # one bounded run; retained history has no count ceiling


class CodeExposureError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text(value, *, maximum=160, minimum=1):
    if (not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValidationError('Kod izleme metni boş, fazla uzun veya kontrol karakteri içeriyor.')
    return value.strip()


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValidationError(f'Kod izleme sayısı {low}–{high} arasında olmalı.')
    return value


def repository(value):
    value = text(value, maximum=300)
    parsed = urlsplit(value if '://' in value else 'https://' + value)
    parts = parsed.path.strip('/').removesuffix('.git').split('/')
    if (parsed.scheme != 'https' or parsed.netloc not in ('github.com', 'gitlab.com')
            or parsed.query or parsed.fragment or len(parts) < 2 or len(parts) > 10
            or (parsed.netloc == 'github.com' and len(parts) != 2)
            or any(not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', p) or p in ('.', '..') for p in parts)):
        raise ValidationError('Depo HTTPS GitHub/GitLab proje adresi olmalı.')
    return 'https://' + parsed.netloc + '/' + '/'.join(parts)


def scope(values):
    if not isinstance(values, dict) or set(values) - SCOPE_FIELDS or 'domain' not in values:
        raise ValidationError('Kod izleme kapsamı geçersiz veya domain eksik.')
    result = dict(values)
    result['domain'] = normalize_domain(result['domain'])
    result['name'] = text(result.get('name', result['domain']))
    for key, maximum in (('aliases', 10), ('repositories', 100), ('sources', len(PROVIDERS))):
        default = ['github-repositories', 'gitlab-projects'] if key == 'sources' else []
        items = result.get(key, default)
        if not isinstance(items, list) or len(items) > maximum:
            raise ValidationError('Kod izleme kaynak/alias/depo listesi geçersiz.')
        if key == 'sources':
            if not items or any(not isinstance(v, str) or v not in PROVIDERS for v in items):
                raise ValidationError('Kod/paste kaynağı bilinmiyor veya seçilmedi.')
        else:
            items = [repository(v) if key == 'repositories' else text(v, minimum=3, maximum=120) for v in items]
        result[key] = sorted(set(items))
    for key, default, low, high in (
            ('max_requests', 30, 1, 100), ('max_files', 30, 1, 100),
            ('budget_seconds', 120, 5, 600), ('interval_seconds', 86400, 300, 604800)):
        result[key] = integer(result.get(key, default), low, high)
    if min(result['max_requests'], result['max_files']) < len(result['sources']):
        raise ValidationError('İstek ve dosya bütçesi seçili her kaynağa en az bir yer ayırmalı.')
    return result


def parameters(operation, values, *, scoped=False):
    from xti.domain.research_history import history_key
    if not isinstance(values, dict): raise ValidationError('Kod izleme seçenekleri nesne olmalı.')
    pages = {'after', 'limit'}
    fields = {
        'code.sources': set(), 'code.watch.add': SCOPE_FIELDS | {'idempotency_key'},
        'code.watch.update': SCOPE_FIELDS | {'identifier', 'enabled', 'expected_revision', 'idempotency_key'},
        'code.watch.list': pages | {'domain'}, 'code.watch.show': {'identifier'},
        'code.plan': {'identifier'}, 'code.run': {'identifier', 'expected_revision', 'force', 'idempotency_key'},
        'code.recover': {'identifier', 'idempotency_key'}, 'code.runs': pages | {'watch_id'},
        'code.run.show': {'identifier'}, 'code.findings': pages | {'watch_id', 'domain', 'kind', 'decision'},
        'code.finding.show': {'identifier'}, 'code.changes': pages | {'watch_id'},
        'code.reviews': pages | {'identifier'}, 'code.evidence.show': {'identifier'},
        'code.report': {'domain'}, 'code.review': {'identifier', 'decision', 'reason', 'evidence_id',
                                                'expected_revision', 'expected_observation_revision', 'idempotency_key'},
    }
    if operation not in fields: raise ValidationError('Kod izleme işlemi bilinmiyor.')
    required = {
        'code.watch.add': {'domain', 'idempotency_key'},
        'code.watch.update': {'identifier', 'expected_revision', 'idempotency_key'},
        'code.watch.show': {'identifier'}, 'code.plan': {'identifier'},
        'code.run': {'identifier', 'expected_revision', 'idempotency_key'},
        'code.recover': {'identifier', 'idempotency_key'}, 'code.run.show': {'identifier'},
        'code.finding.show': {'identifier'}, 'code.report': {'domain'},
        'code.reviews': {'identifier'}, 'code.evidence.show': {'identifier'},
        'code.review': fields['code.review'],
    }.get(operation, set()).copy()
    allowed = fields[operation].copy()
    if scoped and operation in WRITES:
        allowed.add('expected_workspace_id'); required.add('expected_workspace_id')
    result = dict(values)
    if set(result) - allowed or required - result.keys():
        raise ValidationError('Kod izleme alanları eksik veya bilinmiyor.')
    for key in ('identifier', 'watch_id', 'evidence_id', 'expected_workspace_id'):
        if key in result: result[key] = mention_uuid(result[key])
    if 'idempotency_key' in result: result['idempotency_key'] = history_key(result['idempotency_key'])
    if 'domain' in result: result['domain'] = normalize_domain(result['domain'])
    if 'expected_revision' in result: integer(result['expected_revision'], 0, 2**53 - 1)
    if 'expected_observation_revision' in result: integer(result['expected_observation_revision'], 1, 2**53 - 1)
    if 'reason' in result: result['reason'] = text(result['reason'], maximum=1000)
    if 'decision' in result and result['decision'] not in DECISIONS:
        raise ValidationError('Kod maruziyeti inceleme kararı geçersiz.')
    if 'kind' in result and result['kind'] not in ('brand_mention', 'secret_candidate'):
        raise ValidationError('Kod maruziyeti türü geçersiz.')
    for key in ('enabled', 'force'):
        if key in result and type(result[key]) is not bool: raise ValidationError('Seçim doğru/yanlış olmalı.')
    if operation == 'code.watch.add':
        result.update(scope({k: v for k, v in result.items() if k in SCOPE_FIELDS}))
    if operation == 'code.watch.update':
        if not (set(result) & (SCOPE_FIELDS | {'enabled'})):
            raise ValidationError('İzleme güncellemesinde değiştirilecek alan gerekli.')
        # Full scope validation follows merging with the current stored revision.
    if operation in ('code.watch.list', 'code.runs', 'code.findings', 'code.changes', 'code.reviews'):
        result['after'] = integer(result.get('after', 0), 0, 2**63 - 1)
        result['limit'] = integer(result.get('limit', 20), 1, 100)
    if operation == 'code.run': result.setdefault('force', False)
    return result


@dataclass(frozen=True)
class Document:
    provider: str
    locator: str
    url: str
    repository: str
    path: str
    revision: str
    content: str
    basis: str


def terms_in(content, selected_scope):
    terms = [selected_scope['domain'], *selected_scope['aliases']]
    if len(selected_scope['name']) >= 3: terms.append(selected_scope['name'])
    return sorted({term for term in terms if re.search(
        (r'(?<![\w-])' if term == selected_scope['domain'] else r'(?<![\w.-])') +
        re.escape(term) + r'(?![\w.-])', content, re.IGNORECASE)})


def observations(document, selected_scope, secrets):
    """Produce metadata only. Never preserve source lines, matches or token values."""
    matched = terms_in(document.content, selected_scope)
    if not matched and document.basis not in ('declared_repository', 'repository_search', 'code_search'):
        return []
    base = {'policy': POLICY, 'source': document.provider, 'locator': document.locator,
            'url': document.url, 'repository': document.repository, 'path': document.path,
            'revision': document.revision, 'content_sha256': hashlib.sha256(document.content.encode()).hexdigest(),
            'company_basis': 'text_match' if matched else document.basis,
            'matched_terms': matched, 'ownership': 'unverified', 'credential_validity': 'not_tested'}
    rows = []
    if matched:
        rows.append({**base, 'kind': 'brand_mention', 'rule': 'company-text', 'line': 0,
                     'evidence': 'Firma terimi içerikte geçiyor; sahiplik veya sızıntı hükmü değildir.'})
    for finding in secrets:
        # Adapter may return only this narrow rule/line contract.
        if set(finding) != {'rule', 'line'}:
            raise ValidationError('Tarayıcı maskeli çıktı sözleşmesine uymuyor.')
        rule = text(finding['rule'], maximum=100)
        line = integer(finding['line'], 1, MAX_FILE_BYTES)
        rows.append({**base, 'kind': 'secret_candidate', 'rule': rule, 'line': line,
                     'evidence': '[MASKELENDİ] — biçim eşleşmesi; çalışır anahtar veya firma sahipliği doğrulanmadı.'})
    for row in rows:
        row['identity'] = digest([document.provider, document.locator, row['kind'], row['rule'], row['line']])
        row['content_group'] = digest([row['kind'], row['content_sha256'], row['rule'], row['line']])
    return rows


def validate_observation(value):
    fields = {'policy', 'source', 'locator', 'url', 'repository', 'path', 'revision', 'content_sha256',
              'company_basis', 'matched_terms', 'ownership', 'credential_validity', 'kind', 'rule',
              'line', 'evidence', 'identity', 'content_group'}
    if not isinstance(value, dict) or set(value) != fields or value['policy'] != POLICY:
        raise ValidationError('Kod kanıtı biçimi geçersiz.')
    if value['source'] not in PROVIDERS or value['kind'] not in ('brand_mention', 'secret_candidate'):
        raise ValidationError('Kod kanıtı kaynağı/türü geçersiz.')
    for key in ('locator', 'url', 'repository', 'path', 'revision', 'rule', 'evidence'):
        text(value[key], maximum=2000, minimum=0)
    for key in ('identity', 'content_sha256', 'content_group'):
        if not re.fullmatch('[a-f0-9]{64}', value[key]): raise ValidationError('Kod kanıtı özeti geçersiz.')
    if (value['ownership'] != 'unverified' or value['credential_validity'] != 'not_tested'
            or value['company_basis'] not in ('text_match', 'declared_repository', 'repository_search', 'code_search')
            or not isinstance(value['matched_terms'], list) or len(value['matched_terms']) > 12):
        raise ValidationError('Kod kanıtı firma bağı geçersiz.')
    for term in value['matched_terms']: text(term, maximum=253)
    integer(value['line'], 0, MAX_FILE_BYTES)
    if value['identity'] != digest([value['source'], value['locator'], value['kind'], value['rule'], value['line']]):
        raise ValidationError('Kod kanıtı kimliği uyuşmuyor.')
    if value['content_group'] != digest([value['kind'], value['content_sha256'], value['rule'], value['line']]):
        raise ValidationError('Kod içerik grubu uyuşmuyor.')
    return value
