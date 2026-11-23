"""Bounded public discovery, with authenticated code search explicitly separate."""
import base64
from datetime import datetime, timezone
import http.client
import json
import re
import socket
import ssl
import time
from urllib.parse import quote, urlencode, urlsplit

from xti.adapters.code_credentials import load_key
from xti.adapters.public_profile_pages import resolve_public, _DeadlineSocket, PageFailure
from xti.domain.assets import ValidationError
from xti.domain.code_exposure import Document, MAX_FILE_BYTES, MAX_RUN_BYTES, PROVIDERS, repository

HOSTS = {'api.github.com', 'gitlab.com', 'scrape.pastebin.com'}
MAX_RESPONSE = 2 * 1024 * 1024


class SourceFailure(Exception):
    def __init__(self, state, *, status=None, retry_after=0):
        super().__init__(state)
        self.state, self.status, self.retry_after = state, status, retry_after


def request(host, path, token, timeout):
    """One pinned public TLS destination. No redirects, proxies, cookies or body logging."""
    if host not in HOSTS or not path.startswith('/') or any(ord(c) < 33 or ord(c) > 126 for c in path):
        raise SourceFailure('invalid_response')
    deadline = time.monotonic() + timeout
    address = resolve_public(host, min(timeout, 5))
    raw = socket.create_connection((address, 443), timeout=max(.01, deadline - time.monotonic()))
    try:
        raw.settimeout(max(.01, deadline - time.monotonic()))
        tls = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    except BaseException:
        raw.close(); raise
    try:
        headers = ['User-Agent: XTI-Code-Exposure/1', 'Accept: application/json',
                   'Accept-Encoding: identity', 'Connection: close']
        if host == 'api.github.com': headers.append('X-GitHub-Api-Version: 2022-11-28')
        if token:
            if host not in ('api.github.com', 'gitlab.com') or re.fullmatch(r'[A-Za-z0-9._~+/=-]{16,512}', token) is None:
                raise SourceFailure('invalid_credentials')
            headers.append(('Authorization: Bearer ' if host == 'api.github.com' else 'PRIVATE-TOKEN: ') + token)
        wire = f'GET {path} HTTP/1.1\r\nHost: {host}\r\n' + '\r\n'.join(headers) + '\r\n\r\n'
        tls.settimeout(max(.01, deadline - time.monotonic())); tls.sendall(wire.encode('ascii'))
        response = http.client.HTTPResponse(_DeadlineSocket(tls, deadline))
        try:
            response.begin()
            pairs = response.getheaders()
            for name in ('content-length', 'content-type', 'content-encoding', 'transfer-encoding'):
                if sum(k.lower() == name for k, _ in pairs) > 1: raise SourceFailure('invalid_response')
            hdr = {k.lower(): v for k, v in pairs}
            if ('content-length' in hdr and 'transfer-encoding' in hdr
                    or hdr.get('content-encoding', 'identity') not in ('identity', '')
                    or hdr.get('transfer-encoding', '') not in ('', 'chunked')):
                raise SourceFailure('invalid_response')
            if response.status != 200: return response.status, hdr, b''
            if 'content-length' in hdr and not 0 <= int(hdr['content-length']) <= MAX_RESPONSE:
                raise SourceFailure('response_too_large')
            data = response.read(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE or 'content-length' in hdr and len(data) != int(hdr['content-length']):
                raise SourceFailure('response_too_large')
            return response.status, hdr, data
        finally: response.close()
    finally: tls.close()


def _path(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 1000 or value.startswith('/')
            or any(ord(c) < 32 or ord(c) == 127 for c in value) or '..' in value.split('/')):
        raise SourceFailure('invalid_response')
    return value


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch('[a-fA-F0-9]{40,64}', value):
        raise SourceFailure('invalid_response')
    return value.lower()


class PublicCodeSources:
    def __init__(self, transport=request, credentials=load_key, clock=time.monotonic, wall=time.time, cancelled=lambda: False):
        self.transport, self.credentials, self.clock, self.wall = transport, credentials, clock, wall
        self.cancelled = cancelled

    def status(self):
        ready = {}
        for provider in ('github', 'gitlab'):
            try: ready[provider] = 'configured' if self.credentials(provider) else 'not_configured'
            except ValidationError: ready[provider] = 'invalid_credentials'
        return [{'source': p, 'access': ready[p.split('-')[0]] if p.endswith('-code') else
                 'scraping_access_unverified' if p == 'pastebin' else 'public_discovery',
                 'coverage': 'recent_public_pastes' if p == 'pastebin' else
                 'provider_code_search' if p.endswith('-code') else 'public_repository_discovery',
                 'live_verified': False} for p in PROVIDERS]

    def collect(self, scope, checkpoints, consume):
        self.scope, self.consume, self.started = scope, consume, self.clock()
        self.deadline = self.started + scope['budget_seconds']
        self.total_bytes = 0
        reports = []
        count = len(scope['sources'])
        for position, provider in enumerate(scope['sources']):
            self.provider = provider
            previous = checkpoints.get(provider, {})
            self.cursor = max(0, int(previous.get('cursor', 0)))
            self.file_offsets = dict(previous.get('file_offsets', {}))
            self.tree_pages = dict(previous.get('tree_pages', {}))
            terms = list(dict.fromkeys([scope['domain'], scope['name'], *scope['aliases']]))
            self.term = terms[self.cursor % len(terms)]
            from xti.domain.code_exposure import digest
            self.pages = {digest(term): previous.get('pages', {}).get(digest(term), 1) for term in terms}
            self.page_key = digest(self.term)
            self.page = max(1, min(33, int(self.pages[self.page_key])))
            self.limit = scope['max_requests'] // count + int(position < scope['max_requests'] % count)
            self.file_limit = max(1, scope['max_files'] // count + int(position < scope['max_files'] % count))
            self.report = {'source': provider, 'status': 'complete', 'requests': 0, 'bytes': 0, 'files': 0,
                           'skipped_files': 0, 'query': self.term, 'http_status': None,
                           'bounded': True, 'incomplete_results': False, 'cursor': self.cursor,
                           'retry_at': None, 'observed': False, 'page': self.page, 'pages': self.pages,
                           'file_offsets': self.file_offsets, 'tree_pages': self.tree_pages,
                           'coverage': 'recent_public_pastes' if provider == 'pastebin' else 'public_text_files_current_revision',
                           'responses': 0, 'transport_errors': 0, 'rate_limited': 0}
            self.token = None
            try:
                if previous.get('retry_at') and self.wall() < previous['retry_at']:
                    self.report['retry_at'] = previous['retry_at']; raise SourceFailure('cooldown')
                if provider != 'pastebin':
                    try: self.token = self.credentials(provider.split('-')[0])
                    except ValidationError: raise SourceFailure('invalid_credentials') from None
                if provider.endswith('-code') and not self.token: raise SourceFailure('missing_credentials')
                if self.clock() >= self.deadline: raise SourceFailure('budget_exhausted')
                if provider.startswith('github-'): self._github(code=provider.endswith('-code'))
                elif provider.startswith('gitlab-'): self._gitlab(code=provider.endswith('-code'))
                else: self._pastebin()
            except SourceFailure as error:
                self.report['status'] = error.state
                if error.status is not None: self.report['http_status'] = error.status
                if error.retry_after: self.report['retry_at'] = int(self.wall()) + error.retry_after
            except ValidationError:
                self.report['status'] = 'invalid_response'
            except (OSError, TimeoutError, PageFailure, http.client.HTTPException):
                self.report['status'] = 'unavailable'
            except (KeyError, TypeError, ValueError, UnicodeError, RecursionError):
                self.report['status'] = 'invalid_response'
            reports.append(self.report)
            if self.report['observed']:
                self.report['cursor'] = self.cursor + 1
                self.report['pages'][self.page_key] = self.report['page']
        return {'sources': reports, 'elapsed_seconds': round(self.clock() - self.started, 3),
                'requests': sum(r['requests'] for r in reports), 'bytes': self.total_bytes,
                'http_usage': {'attempts': sum(r['requests'] for r in reports),
                    'responses': sum(r['responses'] for r in reports),
                    'transport_errors': sum(r['transport_errors'] for r in reports),
                    'rate_limited': sum(r['rate_limited'] for r in reports), 'budget_rejections': 0}}

    def _get(self, host, path, *, raw=False, authenticated=True):
        if self.cancelled(): raise SourceFailure('cancelled')
        if (self.report['requests'] >= self.limit or self.clock() >= self.deadline
                or self.total_bytes >= MAX_RUN_BYTES): raise SourceFailure('budget_exhausted')
        self.report['requests'] += 1
        try:
            status, headers, data = self.transport(host, path, self.token if authenticated else None,
                min(15, max(.01, self.deadline - self.clock())))
        except BaseException:
            self.report['transport_errors'] += 1
            raise
        self.report['responses'] += 1
        self.report['rate_limited'] += int(status == 429)
        self.report['http_status'] = status
        self.report['bytes'] += len(data); self.total_bytes += len(data)
        if len(data) > MAX_RESPONSE or self.total_bytes > MAX_RUN_BYTES: raise SourceFailure('response_too_large')
        if status in (403, 429) and (status == 429 or headers.get('x-ratelimit-remaining') == '0' or 'retry-after' in headers):
            try:
                delay = int(headers.get('retry-after', '60'))
                if headers.get('x-ratelimit-reset'): delay = max(delay, int(headers['x-ratelimit-reset']) - int(self.wall()))
            except (ValueError, TypeError): delay = 60
            raise SourceFailure('rate_limited', status=status, retry_after=max(30, min(delay, 86400)))
        if status == 401: raise SourceFailure('authentication_required', status=status)
        if status == 403: raise SourceFailure('access_denied', status=status)
        if status != 200: raise SourceFailure('unavailable', status=status, retry_after=60 if status >= 500 else 0)
        if raw: return data
        if 'json' not in headers.get('content-type', '').lower(): raise SourceFailure('invalid_response')
        result = json.loads(data)
        self.report['observed'] = True
        return result

    def _deliver(self, *, locator, url, repo, path, revision, body, basis):
        if self.report['files'] >= self.file_limit: raise SourceFailure('budget_exhausted')
        if len(body) > MAX_FILE_BYTES:
            self.report['skipped_files'] += 1; return
        try: content = body.decode('utf-8')
        except UnicodeError:
            self.report['skipped_files'] += 1; return
        if '\x00' in content:
            self.report['skipped_files'] += 1; return
        self.consume(Document(self.provider, locator, url, repo, path, revision, content, basis))
        self.report['files'] += 1

    def _rotate(self, items):
        if not items: return []
        start = self.cursor % len(items)
        return items[start:] + items[:start]

    def _files(self, repo, items):
        from xti.domain.code_exposure import digest
        key = digest(repo)
        if not items: return
        start = self.file_offsets.get(key, 0) % len(items)
        # Retain at most the currently discovered/declared window; this is a cursor, not evidence history.
        if key not in self.file_offsets and len(self.file_offsets) >= 130:
            self.file_offsets.pop(next(iter(self.file_offsets)))
        for index in range(start, len(items)):
            yield items[index]
            self.file_offsets[key] = (index + 1) % len(items)

    def _github(self, *, code):
        host = 'api.github.com'
        if code:
            response = self._get(host, '/search/code?' + urlencode({'q': '"' + self.term.replace('"', ' ') + '"', 'per_page': 30, 'page': self.page}))
            self.report['incomplete_results'] = bool(response.get('incomplete_results'))
            items = response['items']
            self.report['page'] = self.page + 1 if self.page < 33 and len(items) == 30 else 1
            if not isinstance(items, list) or len(items) > 50: raise SourceFailure('invalid_response')
            for row in self._rotate(items):
                project = row['repository']
                if project.get('private') is not False: continue
                repo = repository('https://github.com/' + project['full_name'])
                self._github_blob(repo, _path(row['path']), _sha(row['sha']), 'code_search')
            return
        repos = [(r, 'declared_repository') for r in self.scope['repositories'] if urlsplit(r).netloc == 'github.com']
        response = self._get(host, '/search/repositories?' + urlencode({'q': '"' + self.term.replace('"', ' ') + '" in:readme', 'per_page': 30, 'page': self.page}))
        self.report['incomplete_results'] = bool(response.get('incomplete_results')) or response.get('total_count', 0) > 30
        items = response['items']
        self.report['page'] = self.page + 1 if self.page < 33 and len(items) == 30 else 1
        if not isinstance(items, list) or len(items) > 30: raise SourceFailure('invalid_response')
        for row in items:
            if row.get('private') is False:
                candidate = repository('https://github.com/' + row['full_name'])
                if candidate not in [r[0] for r in repos]: repos.append((candidate, 'repository_search'))
        # Rotate repository priority as well as file priority; a large first repo cannot starve all others forever.
        for repo, basis in self._rotate(repos):
            prefix = '/repos/' + urlsplit(repo).path.strip('/')
            meta = self._get(host, prefix)
            if meta.get('private') is not False: continue
            commits = self._get(host, prefix + '/commits?per_page=1')
            if not commits: continue
            tree_sha = _sha(commits[0]['commit']['tree']['sha'])
            tree = self._get(host, prefix + '/git/trees/' + tree_sha + '?recursive=1')
            self.report['incomplete_results'] |= bool(tree.get('truncated'))
            files = [item for item in tree['tree'] if item.get('type') == 'blob' and item.get('mode') != '120000'
                     and type(item.get('size')) is int and 0 <= item['size'] <= MAX_FILE_BYTES]
            self.report['skipped_files'] += sum(item.get('type') == 'blob' and item.get('mode') != '120000'
                and (type(item.get('size')) is not int or not 0 <= item['size'] <= MAX_FILE_BYTES) for item in tree['tree'])
            files.sort(key=lambda v: (not v['path'].rsplit('/', 1)[-1].lower().startswith('readme'), v['path']))
            for item in self._files(repo, files):
                self._github_blob(repo, _path(item['path']), _sha(item['sha']), basis)

    def _github_blob(self, repo, path, sha, basis):
        if self.report['files'] >= self.file_limit: raise SourceFailure('budget_exhausted')
        endpoint = '/repos/' + urlsplit(repo).path.strip('/') + '/git/blobs/' + sha
        result = self._get('api.github.com', endpoint, authenticated=False)
        if result.get('encoding') != 'base64' or result.get('size', MAX_FILE_BYTES + 1) > MAX_FILE_BYTES:
            self.report['skipped_files'] += 1; return
        body = base64.b64decode(result['content'].replace('\n', ''), validate=True)
        if len(body) != result['size']: raise SourceFailure('invalid_response')
        self._deliver(locator=repo + ':' + path, url='https://api.github.com' + endpoint,
                      repo=repo, path=path, revision=sha, body=body, basis=basis)

    def _gitlab(self, *, code):
        host = 'gitlab.com'
        if code:
            rows = self._get(host, '/api/v4/search?' + urlencode({'scope': 'blobs', 'search': self.term, 'per_page': 30, 'page': self.page}))
            if not isinstance(rows, list) or len(rows) > 30: raise SourceFailure('invalid_response')
            self.report['incomplete_results'] = len(rows) == 30
            self.report['page'] = self.page + 1 if self.page < 33 and len(rows) == 30 else 1
            for row in self._rotate(rows):
                identifier = row['project_id']
                if type(identifier) is not int or identifier < 1: raise SourceFailure('invalid_response')
                project = self._get(host, f'/api/v4/projects/{identifier}')
                if project.get('visibility') != 'public': continue
                repo = repository(project['web_url'])
                path = _path(row['path'])
                detail = self._get(host, f'/api/v4/projects/{identifier}/repository/files/' + quote(path, safe='') + '?ref=' + quote(project['default_branch'], safe=''))
                self._gitlab_blob(identifier, repo, path, _sha(detail['blob_id']), 'code_search')
            return
        projects = self._get(host, '/api/v4/projects?' + urlencode({'search': self.term.split('.')[0] if self.term == self.scope['domain'] else self.term,
                            'visibility': 'public', 'per_page': 30, 'page': self.page, 'simple': 'true'}))
        if not isinstance(projects, list) or len(projects) > 30: raise SourceFailure('invalid_response')
        self.report['incomplete_results'] = len(projects) == 30
        self.report['page'] = self.page + 1 if self.page < 33 and len(projects) == 30 else 1
        repos = []
        for project in projects:
            if project.get('visibility') != 'public': continue
            if type(project.get('id')) is not int or project['id'] < 1: raise SourceFailure('invalid_response')
            repo = repository(project['web_url'])
            if urlsplit(repo).netloc != 'gitlab.com': raise SourceFailure('invalid_response')
            repos.append((repo, str(project['id']), 'repository_search'))
        for repo in self.scope['repositories']:
            if urlsplit(repo).netloc == 'gitlab.com' and repo not in [r[0] for r in repos]:
                repos.insert(0, (repo, quote(urlsplit(repo).path.strip('/'), safe=''), 'declared_repository'))
        for repo, identifier, basis in self._rotate(repos):
            if not re.fullmatch(r'[A-Za-z0-9_.%/-]+', identifier): raise SourceFailure('invalid_response')
            prefix = '/api/v4/projects/' + identifier
            meta = self._get(host, prefix)
            if meta.get('visibility') != 'public': continue
            commits = self._get(host, prefix + '/repository/commits?per_page=1')
            if not commits: continue
            commit = _sha(commits[0]['id'])
            from xti.domain.code_exposure import digest
            key = digest(repo)
            checkpoint = self.tree_pages.get(key, {})
            if checkpoint.get('commit') != commit:
                checkpoint = {'commit': commit, 'page': 1}
                self.file_offsets[key] = 0
            if key not in self.tree_pages and len(self.tree_pages) >= 130:
                self.tree_pages.pop(next(iter(self.tree_pages)))
            self.tree_pages[key] = checkpoint
            while True:
                rows = self._get(host, prefix + '/repository/tree?' + urlencode({
                    'ref': commit, 'recursive': 'true', 'per_page': 100, 'page': checkpoint['page']}))
                if not isinstance(rows, list) or len(rows) > 100: raise SourceFailure('invalid_response')
                for item in self._files(repo, [r for r in rows if r.get('type') == 'blob' and r.get('mode') != '120000']):
                    self._gitlab_blob(identifier, repo, _path(item['path']), _sha(item['id']), basis)
                self.file_offsets[key] = 0
                checkpoint['page'] = checkpoint['page'] + 1 if len(rows) == 100 else 1
                if len(rows) < 100: break

    def _gitlab_blob(self, identifier, repo, path, sha, basis):
        if self.report['files'] >= self.file_limit: raise SourceFailure('budget_exhausted')
        endpoint = f'/api/v4/projects/{identifier}/repository/blobs/{sha}/raw'
        body = self._get('gitlab.com', endpoint, raw=True, authenticated=False)
        self._deliver(locator=repo + ':' + path, url='https://gitlab.com' + endpoint,
                      repo=repo, path=path, revision=sha, body=body, basis=basis)

    def _pastebin(self):
        rows = self._get('scrape.pastebin.com', '/api_scraping.php?limit=100')
        if not isinstance(rows, list) or len(rows) > 100: raise SourceFailure('invalid_response')
        # Completion refers only to this declared recent window, never all paste history.
        for item in self._rotate(rows):
            identifier = item['key']
            if not isinstance(identifier, str) or not re.fullmatch('[A-Za-z0-9]{6,16}', identifier):
                raise SourceFailure('invalid_response')
            if self.report['files'] >= self.file_limit: raise SourceFailure('budget_exhausted')
            body = self._get('scrape.pastebin.com', '/api_scrape_item.php?i=' + identifier, raw=True)
            self._deliver(locator='pastebin:' + identifier, url='https://pastebin.com/' + identifier,
                          repo='', path=identifier, revision=identifier, body=body, basis='public_window')
