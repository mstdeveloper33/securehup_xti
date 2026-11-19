"""Fixed-host, bounded Bright Data LinkedIn company collection; no POST retry."""
from datetime import datetime, timezone
from http.client import HTTPException
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from xti import __version__
from xti.adapters.brightdata_credentials import load_key
from xti.domain.assets import ValidationError
from xti.domain.social_discovery import fingerprint
from xti.domain.social_enrichment import (
    MAX_PROFILES, assess_record, clean_text, company_url, snapshot_id, validate_evidence, website_url,
)
from xti.ports.social_enrichment import SocialProviderError as ProviderError

API = 'https://api.brightdata.com/datasets/v3/'
DATASET = 'gd_l1vikfnt1wgvvqz95w'
MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = 20


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('Duplicate field')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Non-finite number')


class BrightDataSocialProvider:
    def __init__(self, *, key_loader=None, opener=None, monotonic=None, clock=None):
        self._key_loader = key_loader or load_key
        self._opener = opener or build_opener(ProxyHandler({}), NoRedirects())
        self._monotonic = monotonic or time.monotonic
        self._clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self._key = None

    def ready(self):
        self._key = self._key_loader()
        from xti.adapters.brightdata_credentials import validate_key
        validate_key(self._key)

    def _request(self, path, *, query=None, body=None):
        if self._key is None: self.ready()
        url = API + path + ('?' + urlencode(query) if query else '')
        request = Request(url, method='GET' if body is None else 'POST',
            data=None if body is None else json.dumps(body, allow_nan=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + self._key, 'Content-Type': 'application/json',
                     'Accept': 'application/json', 'Accept-Encoding': 'identity', 'User-Agent': 'XTI/' + __version__})
        deadline = self._monotonic() + TIMEOUT
        try:
            with self._opener.open(request, timeout=TIMEOUT) as response:
                if response.geturl() != url or response.status != 200:
                    raise ProviderError('invalid_response')
                if response.headers.get('Content-Encoding', 'identity').lower() not in ('', 'identity'):
                    raise ProviderError('invalid_response')
                if response.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                    raise ProviderError('invalid_response')
                length = response.headers.get('Content-Length')
                if length is not None and not 0 < int(length) <= MAX_BYTES: raise ValueError('Size')
                chunks, total = [], 0
                reader = getattr(response, 'read1', response.read)
                while True:
                    remaining = deadline - self._monotonic()
                    if remaining <= 0: raise ProviderError('transport_error')
                    sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
                    if sock is not None: sock.settimeout(max(0.001, remaining))
                    chunk = reader(min(65536, MAX_BYTES + 1 - total))
                    if self._monotonic() > deadline: raise ProviderError('transport_error')
                    if not chunk: break
                    total += len(chunk)
                    if total > MAX_BYTES: raise ValueError('Size')
                    chunks.append(chunk)
                if length is not None and int(length) != total: raise ValueError('Truncated')
                content = b''.join(chunks).decode('utf-8')
                if self._key in content: raise ValueError('Credential in response')
                parsed = json.loads(content, object_pairs_hook=_object, parse_constant=_constant)
                if self._key in json.dumps(parsed, ensure_ascii=False): raise ValueError('Credential in decoded response')
                return parsed
        except HTTPError as error:
            code = error.code; error.close()
            raise ProviderError('auth_error' if code in (401, 403) else 'rate_limited' if code == 429 else 'provider_unavailable') from None
        except (URLError, HTTPException, OSError, TimeoutError):
            raise ProviderError('transport_error') from None
        except (ValueError, TypeError, RecursionError):
            raise ProviderError('invalid_response') from None

    def submit(self, targets):
        if not 1 <= len(targets) <= MAX_PROFILES or len(set(targets)) != len(targets):
            raise ValidationError('Sağlayıcı hedef sayısı geçersiz.')
        for target in targets:
            if company_url(target)['url'] != target: raise ValidationError('Sağlayıcı hedef kimliği geçersiz.')
        raw = self._request('trigger', query={'dataset_id': DATASET, 'format': 'json',
            'include_errors': 'true', 'notify': 'false', 'limit_multiple_results': len(targets),
            'custom_output_fields': 'url|id|company_id|name|website|about'},
            body={'input': [{'url': url} for url in targets], 'limit_per_input': 1})
        try:
            if not isinstance(raw, dict): raise ValueError('Shape')
            return snapshot_id(raw.get('snapshot_id'))
        except (ValueError, ValidationError): raise ProviderError('invalid_response') from None

    def collect(self, snapshot, targets, domain):
        snapshot_id(snapshot)
        progress = self._request('progress/' + snapshot)
        if (not isinstance(progress, dict) or progress.get('snapshot_id') != snapshot
                or progress.get('dataset_id') != DATASET):
            raise ProviderError('invalid_response')
        status = progress.get('status')
        at = self._clock()
        state = {'status': 'pending', 'snapshot_id': snapshot, 'profiles': [], 'error': None, 'checked_at': at}
        if status in ('starting', 'running'): return state
        if status in ('failed', 'canceled'):
            return {**state, 'status': 'failed', 'error': 'provider_' + status}
        if status != 'ready': raise ProviderError('invalid_response')
        raw = self._request('snapshot/' + snapshot, query={'format': 'json'})
        try:
            if not isinstance(raw, list) or len(raw) > len(targets): raise ValueError('Unbounded results')
            by_target = {}
            for row in raw:
                if not isinstance(row, dict): raise ValueError('Record')
                # Per-input errors/absence are not proof that the account does not exist.
                if row.get('error') or row.get('error_code'): continue
                provider_id = clean_text(row.get('id'), 200)
                returned = company_url(row.get('url') or ('https://linkedin.com/company/' + provider_id))
                evidence = {'url': returned['url'], 'url_basis': 'provider_url' if row.get('url') else 'provider_id', 'provider_id': provider_id,
                    'company_id': clean_text(str(row['company_id']) if type(row.get('company_id')) is int else row.get('company_id') or '', 200),
                    'name': clean_text(row.get('name'), 500), 'website': website_url(row.get('website')),
                    'about': clean_text(row.get('about') or '', 4000), 'record_sha256': fingerprint(row)}
                validate_evidence(evidence)
                input_value = row.get('input')
                input_url = row.get('input_url') or (input_value.get('url') if isinstance(input_value, dict) else None)
                if input_url:
                    selected = company_url(input_url)['url']
                    matches = [selected] if selected in targets else []
                else:
                    matches = [target for target in targets if target == returned['url'] or
                        company_url(target)['username'] in (evidence['provider_id'], evidence['company_id'])]
                if not matches: raise ValueError('Unbound record')
                # Numeric and named company URLs can identify the same account.
                # Bind both only through exact returned URL/ID evidence, never a
                # company-name or website similarity. Repeated equivalent rows
                # add no extra proof; conflicting duplicates fail closed.
                for target in matches:
                    previous = by_target.get(target)
                    if previous is not None:
                        fields = set(evidence) - {'record_sha256'}
                        if any(previous[k] != evidence[k] for k in fields):
                            raise ValueError('Conflicting duplicate record')
                    else:
                        by_target[target] = evidence
            profiles = [assess_record(target, by_target.get(target), domain) for target in targets]
            return {**state, 'status': 'complete' if all(p['state'] == 'provider_supported' for p in profiles) else 'partial',
                    'profiles': profiles, 'checked_at': self._clock()}
        except (ValueError, TypeError, KeyError, ValidationError):
            raise ProviderError('invalid_response') from None
