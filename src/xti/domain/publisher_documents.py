"""Reviewed publisher scope and immutable full-text document rules; no IO."""

from dataclasses import dataclass
from copy import deepcopy
import hashlib
from urllib.parse import unquote, urlsplit, urlunsplit

from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.news import news_text
from xti.domain.research import identity
from xti.domain.report_extraction import extract_document, DOCUMENT_POLICY

PDF_VERSION = '7.1.1'
MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 64 * 1024
MAX_PAGES = 80
POLICY_VERSION = 'publisher-text-v1'
_PUBLISHERS_V1 = {
    'cert-fr': {
        'label': 'ANSSI / CERT-FR',
        'hosts': ('cert.cyber.gouv.fr', 'www.cert.ssi.gouv.fr', 'cert.ssi.gouv.fr'),
        'paths': ('/cti/', '/alerte/', '/avis/', '/actualite/', '/uploads/'),
        'license': 'Licence Ouverte 2.0',
        'license_url': 'https://www.etalab.gouv.fr/licence-ouverte-open-licence/',
        'terms_url': 'https://cert.cyber.gouv.fr/mentions-legales/',
    },
    'ncsc': {
        'label': 'UK National Cyber Security Centre',
        'hosts': ('www.ncsc.gov.uk',),
        'paths': ('/news/', '/report/', '/guidance/', '/blog-post/', '/files/', '/static-assets/documents/', '/collection/'),
        'license': 'Open Government Licence v3.0',
        'license_url': 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/',
        'terms_url': 'https://www.ncsc.gov.uk/section/about-this-website/terms-and-conditions',
    },
}

PUBLISHERS = deepcopy(_PUBLISHERS_V1)

# Persisted documents are validated against their recorded policy, not a future
# installation pin. New parser/scope semantics require a new entry, never edits
# to the meaning of an already released policy.
READ_POLICIES = {
    'publisher-text-v1': {'publishers': _PUBLISHERS_V1, 'pdf_parser': 'pypdf/7.1.1',
        'html_parser': 'xti-publisher-html-v1', 'body_bytes': 8 * 1024 * 1024, 'text_bytes': 64 * 1024, 'pdf_pages': 80},
}
MAX_STORED_BODY_BYTES = max(policy['body_bytes'] for policy in READ_POLICIES.values())


def publisher_url(provider, value, *, policy=None):
    publishers = PUBLISHERS if policy is None else READ_POLICIES[policy]['publishers']
    if not isinstance(provider, str) or provider not in publishers:
        raise ValidationError('Yayıncı cert-fr veya ncsc olmalı.')
    if not isinstance(value, str) or not 1 <= len(value) <= 2048 or not value.isascii() or any(c.isspace() or not c.isprintable() for c in value):
        raise ValidationError('Yayıncı URL alanı geçersiz.')
    try:
        parsed = urlsplit(value)
        path = unquote(parsed.path, errors='strict')
        if (parsed.scheme != 'https' or parsed.hostname not in publishers[provider]['hosts'] or
                parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443) or
                parsed.query or parsed.fragment or '\\' in path or '%' in path or
                any(not c.isprintable() for c in path) or any(p in ('.', '..', '') for p in path.strip('/').split('/')) or
                not path.startswith(publishers[provider]['paths'])):
            raise ValueError('Publisher scope')
        return urlunsplit(('https', parsed.hostname, parsed.path, '', ''))
    except (ValueError, UnicodeError) as error:
        raise ValidationError('URL incelenmiş yayıncının açık içerik kapsamına ait değil.') from error


def stored_publisher_url(provider, value):
    """Historical request validation grants no permission to make a new GET."""
    for policy in READ_POLICIES:
        try:
            return publisher_url(provider, value, policy=policy)
        except ValidationError:
            pass
    raise ValidationError('Saklı yayıncı isteği bilinen kaynak politikalarından birine ait değil.')


@dataclass(frozen=True)
class FetchedDocument:
    provider: str
    url: str
    final_url: str
    redirects: tuple[str, ...]
    media_type: str
    body: bytes
    text: str
    title: str
    parser: str
    page_count: int | None
    fetched_at: str


def validate_fetch(value):
    if not isinstance(value, FetchedDocument):
        raise ValidationError('Yayıncı yanıtı beklenen kayıtta değil.')
    if publisher_url(value.provider, value.url) != value.url or publisher_url(value.provider, value.final_url) != value.final_url:
        raise ValidationError('Yayıncı URL normalleştirmesi tutarsız.')
    if (not isinstance(value.redirects, tuple) or len(value.redirects) > 3 or
            value.final_url != (value.redirects[-1] if value.redirects else value.url)):
        raise ValidationError('Yayıncı yönlendirme kanıtı tutarsız.')
    for url in value.redirects:
        if publisher_url(value.provider, url) != url:
            raise ValidationError('Yayıncı yönlendirmesi kapsam dışı.')
    if not isinstance(value.body, bytes) or not 1 <= len(value.body) <= MAX_BODY_BYTES:
        raise ValidationError('Yayıncı yanıtı 8 MiB sınırını aşıyor veya boş.')
    if (not isinstance(value.text, str) or not value.text.strip() or
            len(value.text.encode('utf-8')) > MAX_TEXT_BYTES or
            any(not c.isprintable() and c not in '\n\t' for c in value.text)):
        raise ValidationError('Çıkarılmış metin boş veya 64 KiB sınırının dışında; kısmi metin saklanmadı.')
    news_text(value.title, maximum=500)
    if value.media_type == 'application/pdf':
        if not value.body.startswith(b'%PDF-') or value.parser != 'pypdf/' + PDF_VERSION or type(value.page_count) is not int or not 1 <= value.page_count <= MAX_PAGES:
            raise ValidationError('PDF ayrıştırma kanıtı geçersiz.')
    elif value.media_type == 'text/html':
        if value.parser != 'xti-publisher-html-v1' or value.page_count is not None:
            raise ValidationError('HTML ayrıştırma kanıtı geçersiz.')
    else:
        raise ValidationError('Yalnız HTML veya PDF yayın metni desteklenir.')
    if normalize_cti_timestamp(value.fetched_at) != value.fetched_at:
        raise ValidationError('Yayıncı alınma zamanı geçersiz.')
    return value


def full_document(value, run_id):
    value = validate_fetch(value)
    normalize_knowledge_id(run_id)
    policy = PUBLISHERS[value.provider]
    result = {
        'model_version': 2, 'source': 'publisher', 'provider': value.provider,
        'source_record_id': identity('publisher-url-v1', value.provider, value.url),
        'source_reference': value.url, 'title': value.title,
        'summary': value.text[:2000], 'summary_truncated': len(value.text) > 2000,
        'published_raw': None, 'published_normalized': None, 'source_updated_at': None,
        'publication': {'raw': None, 'at': None, 'date': None, 'precision': 'unknown'},
        'source_run_id': run_id, 'source_sha256': hashlib.sha256(value.body).hexdigest(),
        'collected_at': value.fetched_at, 'scope': [], 'text': value.text,
        'extraction_policy': DOCUMENT_POLICY, 'candidates': extract_document(value.text),
        'acquisition': {
            'policy': POLICY_VERSION, 'final_url': value.final_url, 'redirects': list(value.redirects),
            'media_type': value.media_type, 'body_bytes': len(value.body), 'http_status': 200,
            'parser': value.parser, 'page_count': value.page_count, 'text_complete': True,
            'text_sha256': hashlib.sha256(value.text.encode('utf-8')).hexdigest(),
            'attribution': policy['label'], 'license': policy['license'], 'license_url': policy['license_url'],
            'terms_url': policy['terms_url'],
            'rights_scope': 'Publisher default license; explicit exceptions and third-party rights still apply.',
        },
    }
    result['content_sha256'] = identity({k: v for k, v in result.items() if k not in {'source_run_id', 'collected_at'}})
    return result


def validate_full_document(value):
    """Validate persisted text independently of the network and PDF library."""
    from xti.domain.reports import sha
    fields = {'model_version', 'source', 'provider', 'source_record_id', 'source_reference', 'title', 'summary',
              'summary_truncated', 'published_raw', 'published_normalized', 'source_updated_at', 'publication',
              'source_run_id', 'source_sha256', 'collected_at', 'scope', 'text', 'extraction_policy', 'candidates',
              'acquisition', 'content_sha256'}
    try:
        if not isinstance(value, dict) or set(value) != fields or value['model_version'] != 2 or value['source'] != 'publisher':
            raise ValueError('Document shape')
        sha(value['source_sha256']); normalize_knowledge_id(value['source_run_id'])
        if normalize_cti_timestamp(value['collected_at']) != value['collected_at']:
            raise ValueError('Time')
        provider, url, text, info = value['provider'], value['source_reference'], value['text'], value['acquisition']
        if not isinstance(info, dict) or not isinstance(info.get('policy'), str) or info['policy'] not in READ_POLICIES:
            raise ValueError('Unknown recorded publisher policy')
        recorded_policy = READ_POLICIES[info['policy']]
        if publisher_url(provider, url, policy=info['policy']) != url or value['source_record_id'] != identity('publisher-url-v1', provider, url):
            raise ValueError('Source identity')
        news_text(value['title'], maximum=500)
        if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > recorded_policy['text_bytes'] or any(not c.isprintable() and c not in '\n\t' for c in text):
            raise ValueError('Text')
        if (value['summary'] != text[:2000] or type(value['summary_truncated']) is not bool or value['summary_truncated'] != (len(text) > 2000) or
                any(value[k] is not None for k in ('published_raw', 'published_normalized', 'source_updated_at')) or
                value['publication'] != {'raw': None, 'at': None, 'date': None, 'precision': 'unknown'} or value['scope'] != [] or
                value['extraction_policy'] != DOCUMENT_POLICY or value['candidates'] != extract_document(text)):
            raise ValueError('Document meaning')
        policy = recorded_policy['publishers'][provider]
        expected = {'policy', 'final_url', 'redirects', 'media_type', 'body_bytes', 'http_status', 'parser', 'page_count',
                    'text_complete', 'text_sha256', 'attribution', 'license', 'license_url', 'terms_url', 'rights_scope'}
        if set(info) != expected or type(info['http_status']) is not int or info['http_status'] != 200 or info['text_complete'] is not True:
            raise ValueError('Acquisition')
        if type(info['body_bytes']) is not int or not 1 <= info['body_bytes'] <= recorded_policy['body_bytes'] or info['text_sha256'] != hashlib.sha256(text.encode('utf-8')).hexdigest():
            raise ValueError('Acquisition size')
        if not isinstance(info['redirects'], list) or len(info['redirects']) > 3 or info['final_url'] != (info['redirects'][-1] if info['redirects'] else url):
            raise ValueError('Redirect chain')
        for link in [info['final_url'], *info['redirects']]:
            if publisher_url(provider, link, policy=info['policy']) != link:
                raise ValueError('Redirect scope')
        if info['media_type'] == 'application/pdf':
            if info['parser'] != recorded_policy['pdf_parser'] or type(info['page_count']) is not int or not 1 <= info['page_count'] <= recorded_policy['pdf_pages']:
                raise ValueError('PDF metadata')
        elif info['media_type'] != 'text/html' or info['parser'] != recorded_policy['html_parser'] or info['page_count'] is not None:
            raise ValueError('HTML metadata')
        if any(info[k] != policy[k] for k in ('license', 'license_url', 'terms_url')) or info['attribution'] != policy['label'] or info['rights_scope'] != 'Publisher default license; explicit exceptions and third-party rights still apply.':
            raise ValueError('Publisher policy')
        if value['content_sha256'] != identity({k: v for k, v in value.items() if k not in {'source_run_id', 'collected_at', 'content_sha256'}}):
            raise ValueError('Content hash')
    except (KeyError, TypeError, ValueError, AttributeError, UnicodeError) as error:
        raise ValidationError('Tam yayın belgesi veya kaynak kanıtı tutarsız.') from error
