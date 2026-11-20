#!/usr/bin/env python3
"""Bounded passive crt.sh diagnostic; never touches the user's evidence DB."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener

from xti import __version__
from xti.adapters.crtsh import CrtShSource, _NoRedirects, MAX_RESPONSE_BYTES, REQUEST_TIMEOUT
from xti.domain.assets import normalize_domain


def utc():
    return datetime.now(timezone.utc).isoformat()


class ObservedResponse:
    def __init__(self, response, row, started):
        self.response, self.row, self.started = response, row, started
        self.headers = response.headers
        self.checksum = hashlib.sha256()
        row.update(http_status=response.getcode(), bytes_read=0,
            headers={key: response.headers[key] for key in ('Content-Type', 'Content-Length', 'Date', 'Server', 'Retry-After', 'Content-Encoding') if key in response.headers})

    def getcode(self):
        return self.response.getcode()

    def read(self, size):
        return self.read1(size)

    def read1(self, size):
        if time.monotonic() - self.started > REQUEST_TIMEOUT * 2:
            raise TimeoutError('Total diagnostic response deadline exceeded')
        data = getattr(self.response, 'read1', self.response.read)(size)
        self.checksum.update(data)
        self.row['bytes_read'] += len(data)
        return data

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self.row.update(finished_at=utc(), elapsed_seconds=round(time.monotonic() - self.started, 6),
            body_sha256=self.checksum.hexdigest(), body_complete=kind is None,
            exception_type=kind.__name__ if kind else None, error=str(value)[:1000] if value else None)
        self.response.close()


def observe_open(rows):
    opener = build_opener(_NoRedirects())
    def open_request(request, *, timeout):
        row = {'method': request.get_method(), 'url': request.full_url, 'started_at': utc(), 'timeout_seconds': timeout}
        rows.append(row)
        started = time.monotonic()
        try:
            return ObservedResponse(opener.open(request, timeout=timeout), row, started)
        except Exception as error:
            row.update(finished_at=utc(), elapsed_seconds=round(time.monotonic() - started, 6),
                http_status=error.code if isinstance(error, HTTPError) else None,
                exception_type=type(error).__name__, error=str(error)[:1000])
            if isinstance(error, HTTPError):
                row['headers'] = {key: error.headers[key] for key in ('Content-Type', 'Date', 'Server', 'Retry-After') if key in error.headers}
                error.close()
            raise
    return open_request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', default='securehup.com')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    domain = normalize_domain(args.domain)
    # Reserve a private new output first; no network if output is unsafe/existing.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as target:
        result = {'version': 1, 'xti_version': __version__, 'started_at': utc(),
            'platform': platform.platform(), 'python': platform.python_version(), 'domain': domain,
            'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
            'working_tree_changed': bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()),
            'adapter_attempts': [], 'direct_attempts': []}
        source = CrtShSource(opener=observe_open(result['adapter_attempts']))
        url = source.search_url('%.' + domain)
        result['request_url'] = url
        try:
            batch = source.search('%.' + domain)
            result['adapter_result'] = {'status': 'success', 'result_type': type(batch).__name__}
        except Exception as error:
            result['adapter_result'] = {'status': 'failed', 'exception_type': type(error).__name__, 'error': str(error)[:1000]}
        # Honor provider wait instructions; do not immediately probe a throttled service.
        if any(row.get('http_status') == 429 or row.get('headers', {}).get('Retry-After') for row in result['adapter_attempts']):
            result['direct_result'] = {'status': 'skipped_provider_backoff'}
        else:
            try:
                request = Request(url, headers={'User-Agent': f'XTI/{__version__} source-diagnostic', 'Accept': 'application/json', 'Accept-Encoding': 'identity'})
                with observe_open(result['direct_attempts'])(request, timeout=REQUEST_TIMEOUT) as response:
                    body = bytearray()
                    while len(body) <= MAX_RESPONSE_BYTES:
                        part = response.read1(min(65536, MAX_RESPONSE_BYTES + 1 - len(body)))
                        if not part:
                            break
                        body.extend(part)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ValueError('Response exceeds 8 MiB')
                    parsed = json.loads(body)
                    result['direct_result'] = {'status': 'success', 'json_type': type(parsed).__name__,
                        'record_count': len(parsed) if isinstance(parsed, list) else None}
            except Exception as error:
                result['direct_result'] = {'status': 'failed', 'exception_type': type(error).__name__, 'error': str(error)[:1000]}
        result.update(finished_at=utc(), scope='real_adapter_and_independent_http_only',
            previous_snapshot='not_applicable_isolated_diagnostic_no_database',
            attribution='This observation does not establish the cause of any historical outage.')
        json.dump(result, target, ensure_ascii=False, indent=2)
        target.write('\n')
    print(json.dumps({'output': str(args.output), 'adapter': result['adapter_result']['status'],
        'direct': result['direct_result']['status'], 'finished_at': result['finished_at']}))


if __name__ == '__main__':
    main()
