"""Reuse pinned OSINT tools; isolate failures and optional metered search."""
import subprocess
import time

from xti.adapters.maigret_username import MaigretUsernameSource
from xti.adapters.sherlock_username import SherlockUsernameSource
from xti.adapters.tavily_search import TavilySearchSource, load_tavily_api_key
from xti.domain.assets import ValidationError
from xti.domain.brand_username import MAIGRET_PLATFORM_HOSTS, SHERLOCK_PLATFORM_HOSTS
from xti.domain.mentions import MentionRequest, company_target
from xti.ports.discovery import SourceError


class SocialDiscoverySourceAdapter:
    def __init__(self, *, runner=None, key_loader=None, tavily_factory=None, monotonic=None):
        self.runner = runner or subprocess.run
        self.key_loader = key_loader or load_tavily_api_key
        self.tavily_factory = tavily_factory or TavilySearchSource
        self.monotonic = monotonic or time.monotonic

    def collect(self, source, username, platforms, *, timeout, remaining):
        catalog = MAIGRET_PLATFORM_HOSTS if source == 'maigret' else SHERLOCK_PLATFORM_HOSTS
        selected = tuple(p for p in platforms if p in catalog)
        result = {'source': source, 'username': username, 'status': 'unsupported' if not selected else 'complete',
                  'requested_platforms': list(selected), 'unreported_platforms': [], 'matches': [], 'error': None}
        if not selected: return result
        deadline = self.monotonic() + remaining
        def bounded_runner(command, **kwargs):
            available = deadline-self.monotonic()
            if available <= 0: raise subprocess.TimeoutExpired(command[0], remaining)
            kwargs['timeout'] = min(kwargs['timeout'], available)
            return self.runner(command, **kwargs)
        try:
            factory = MaigretUsernameSource if source == 'maigret' else SherlockUsernameSource
            preview = factory(runner=bounded_runner).preview(username, platforms=selected, request_timeout=timeout)
            result.update(source_version=preview.source_version, checked_at=preview.checked_at,
                          integration_profile=preview.integration_profile,
                          matches=[{'url':match.profile_url,'platform':match.platform} for match in preview.matches],
                          unreported_platforms=list(preview.unreported_platforms))
        except (SourceError, ValidationError, OSError, subprocess.TimeoutExpired):
            # Never serialize subprocess output, environment, or arbitrary exception strings.
            result.update(status='failed', error='tool_unavailable_or_failed')
        return result

    def search(self, scope, *, remaining):
        base = {'source': 'tavily', 'status': 'failed', 'attempted': False, 'credits': None,
                'matches': [], 'search_depth': 'advanced', 'include_domains': []}
        if remaining <= 0: return ({**base, 'error': 'budget_exhausted'},)
        try: key = self.key_loader()
        except ValidationError: return ({**base, 'error': 'missing_or_invalid_api_key'},)
        deadline = self.monotonic() + remaining
        filters = [()]
        if 'Instagram' in scope['platforms']: filters.append(('instagram.com',))
        if 'Twitter' in scope['platforms']: filters.append(('x.com','twitter.com'))
        results = []
        request = MentionRequest(company_target(scope['name'], [scope['domain']]), 'general', 20)
        for index, domains in enumerate(filters):
            run = {**base, 'include_domains': list(domains)}
            available = deadline-self.monotonic()
            if available <= 0:
                results.append({**run, 'error': 'budget_exhausted'})
                continue
            try:
                # Divide remaining collection time so one slow query cannot consume every variant.
                source = self.tavily_factory(key, search_depth='advanced', include_domains=domains,
                                            budget_seconds=min(45,available/(len(filters)-index)))
                run['attempted'] = True
                response = source.fetch(request)
                run.update(status='complete', query=response.query, request_id=response.request_id,
                           credits=response.credits, error=None, matches=[{'url': hit.url} for hit in response.hits])
            except (SourceError, ValidationError, OSError):
                run['error'] = 'search_unavailable_or_failed'
            results.append(run)
        return tuple(results)
