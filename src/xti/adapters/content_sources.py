"""Public source windows; stored sources perform no network or paid API calls."""
from datetime import datetime, timezone, timedelta
import importlib.metadata
import json
import time
from urllib.parse import urljoin

from xti.adapters.content_http import ContentHTTP
from xti.adapters.content_credentials import load_credential
from xti.adapters.rss_atom_news import _parser, _plain, _date
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.domain.content_monitoring import ContentError, ContentDocument, digest, public_url
from xti.domain.assets import ValidationError
from xti.ports.discovery import SourceError


def _version(name, wanted):
    try: return 'ready' if importlib.metadata.version(name) == wanted else 'version_mismatch'
    except importlib.metadata.PackageNotFoundError: return 'not_installed'


def _time(value):
    if not value: return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc).isoformat() if parsed.tzinfo is not None else None
    except (ValueError, TypeError): return None


def parse_feed(body, locator):
    if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper(): raise ContentError('invalid_response', 'DTD/entity içeren akış kabul edilmedi.')
    parsed = _parser().parse(body, resolve_relative_uris=False)
    if not parsed.get('version') or parsed.get('bozo'):
        raise ContentError('invalid_response', 'Kaynak geçerli RSS/Atom akışı olarak doğrulanamadı.')
    entries, skipped, seen = [], 0, set()
    if len(parsed.entries) > 5000: raise ContentError('response_too_large', 'Akış 5000 öğelik ayrıştırma sınırını aşıyor.')
    for entry in parsed.entries:
        try:
            url = public_url(urljoin(locator, entry.get('link', '')))
            native = str(entry.get('id') or url)
            if native in seen: continue
            title, summary = _plain(entry.get('title', '')), _plain(entry.get('summary', ''))
            if not summary and entry.get('content'):
                summary = _plain(entry['content'][0].get('value', ''))
            document = ContentDocument(native, url, title, summary,
                _date(entry, 'published')[1], _date(entry, 'updated')[1]).validate()
            seen.add(native); entries.append(document)
        except (ValidationError, ValueError, TypeError, KeyError): skipped += 1
    return entries, skipped


def _window(documents, checkpoint, maximum, consume):
    fingerprint = digest([[d.native_id, digest([d.title, d.content, d.updated_at])] for d in documents])
    offset = checkpoint.get('offset', 0) if checkpoint.get('window_sha256') == fingerprint else 0
    if type(offset) is not int or not 0 <= offset <= len(documents): raise ContentError('invalid_checkpoint', 'Kaynak ilerleme kaydı geçersiz.')
    selected = documents[offset:offset + maximum]
    for document in selected: consume(document)
    complete = offset + len(selected) >= len(documents)
    return {'status': 'complete' if complete else 'partial', 'items': len(selected),
            'checkpoint': {'window_sha256': fingerprint, 'offset': 0 if complete else offset + len(selected),
                           'baseline_complete': complete or checkpoint.get('baseline_complete', False)},
            'window_items': len(documents), 'window_complete': complete,
            'window_changed_during_paging': bool(offset == 0 and checkpoint.get('offset', 0) and checkpoint.get('window_sha256') != fingerprint)}


class PublicContentSources:
    def __init__(self, database, *, http=None, credentials=load_credential, clock=time.monotonic, telegram=None, irc=None):
        self.database, self.http, self.credentials, self.clock = database, http or ContentHTTP(), credentials, clock
        self.telegram, self.irc = telegram, irc

    def status(self):
        return [
            {'provider': 'rss', 'tool': 'feedparser', 'version': '6.0.14', 'state': _version('feedparser', '6.0.14'), 'access': 'public', 'coverage': 'published_feed_window'},
            {'provider': 'bluesky', 'tool': 'Bluesky public AppView', 'state': 'ready', 'access': 'public', 'coverage': 'latest_public_search_pages'},
            *[{'provider': p, 'tool': 'XTI stored evidence', 'state': 'ready', 'access': 'workspace', 'coverage': 'stored_current_records'} for p in ('local-news', 'local-mentions', 'local-reports')],
            {'provider': 'telegram', 'tool': 'Telethon', 'version': '1.46.0', 'state': _version('Telethon', '1.46.0'), 'access': 'account_required', 'coverage': 'selected_public_channel_window'},
            {'provider': 'discord', 'tool': 'Discord REST v10', 'state': 'ready', 'access': 'bot_and_channel_permissions_required', 'coverage': 'selected_channel_window'},
            {'provider': 'irc', 'tool': 'irctokens', 'version': '2.0.2', 'state': _version('irctokens', '2.0.2'), 'access': 'selected_public_tls_channel', 'coverage': 'connected_interval_only'},
        ]

    def collect(self, source, checkpoint, budget, consume, *, targets=()):
        definition = source['definition']; provider = definition['provider']
        cooldown = _time(checkpoint.get('retry_at'))
        if cooldown and datetime.fromisoformat(cooldown) > datetime.now(timezone.utc):
            return {'status': 'cooldown', 'items': 0, 'operations': 0, 'checkpoint': None, 'retry_at': cooldown}
        try:
            if provider == 'rss': return self._rss(definition, checkpoint, budget, consume)
            if provider == 'bluesky':
                from xti.adapters.content_bluesky import collect_bluesky
                return collect_bluesky(definition, checkpoint, budget, consume,
                                       targets=targets, http=self.http, clock=self.clock)
            if provider.startswith('local-'): return self._local(provider, checkpoint, budget, consume)
            if provider == 'irc':
                from xti.adapters.content_irc import collect_irc
                return (self.irc or collect_irc)(definition, checkpoint, budget, consume)
            credentials = self.credentials(provider, definition['credential_profile'])
            if credentials is None: return {'status': 'missing_credentials', 'items': 0, 'operations': 0, 'checkpoint': None}
            if provider == 'discord':
                from xti.adapters.content_discord import collect_discord
                return collect_discord(definition, credentials, checkpoint, budget, consume, http=self.http, clock=self.clock)
            from xti.adapters.content_telegram import collect_telegram
            return (self.telegram or collect_telegram)(definition, credentials, checkpoint, budget, consume)
        except SourceError:
            return {'status': 'dependency_unavailable', 'items': 0, 'operations': 0, 'checkpoint': None}

    def _rss(self, definition, checkpoint, budget, consume):
        response = self.http.get(definition['locator'], seconds=budget['seconds'], max_operations=budget['max_operations'])
        base = {'operations': len(response['attempts']), 'operation_unit': 'http_open_attempt',
                'attempts': response['attempts'], 'coverage': 'published_feed_window', 'history_complete': False}
        if response['status'] != 'complete':
            updated = None
            if response['status'] == 'rate_limited':
                updated = {**checkpoint, 'retry_at': (datetime.now(timezone.utc) + timedelta(seconds=response.get('retry_after_seconds', 300))).isoformat()}
            return {**base, 'status': response['status'], 'items': 0, 'checkpoint': updated}
        consumed = 0
        def accept(document):
            nonlocal consumed
            consume(document); consumed += 1
        try:
            documents, skipped = parse_feed(response['body'], definition['locator'])
            result = _window(documents, checkpoint, budget['max_items'], accept)
            if skipped: result['status'] = 'partial'
            return {**base, **result, 'skipped_items': skipped}
        except SourceError:
            return {**base, 'status': 'dependency_unavailable', 'items': 0, 'checkpoint': None}
        except (ContentError, ValidationError) as error:
            return {**base, 'status': getattr(error, 'code', 'invalid_response'), 'items': consumed, 'checkpoint': None}

    def _local(self, provider, checkpoint, budget, consume):
        documents = []
        with SQLiteAssetRepository(self.database)._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            if provider == 'local-news':
                from xti.adapters.sqlite_news import read_news_catalog
                for stored in read_news_catalog(connection).articles:
                    item = stored.article
                    documents.append(ContentDocument(item.id, item.url, item.title, item.summary, item.published_at, item.updated_at, 'stored_text'))
            elif provider == 'local-mentions':
                from xti.adapters.sqlite_mentions import read_mentions_catalog
                for stored in read_mentions_catalog(connection).records:
                    item = stored.hit
                    documents.append(ContentDocument(stored.id, item.url, item.title, item.summary, _time(item.published_at), None, 'stored_text'))
            else:
                from xti.adapters.sqlite_reports import read_reports
                for identifier, report in read_reports(connection)[0].items():
                    doc = report['documents'][-1]['document']
                    content = doc.get('text', doc.get('summary', ''))
                    # Existing full reports can be larger; this adapter reports excerpt extent explicitly.
                    clipped = content.encode('utf-8')[:32768].decode('utf-8', errors='ignore')
                    documents.append(ContentDocument(identifier, doc['source_reference'], doc['title'], clipped,
                        doc.get('publication', {}).get('at'), doc.get('source_updated_at'),
                        'source_excerpt' if len(content.encode('utf-8')) > 32768 else 'stored_text'))
        documents.sort(key=lambda d: d.native_id)
        result = _window(documents, checkpoint, budget['max_items'], consume)
        return {**result, 'operations': 1, 'operation_unit': 'local_snapshot', 'network_requests': 0,
                'coverage': 'stored_current_records', 'history_complete': False}
