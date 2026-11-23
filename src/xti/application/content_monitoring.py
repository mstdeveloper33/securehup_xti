"""One company workflow for public feeds, stored intel and explicitly selected channels."""
from datetime import datetime, timezone
import time

from xti.domain.content_monitoring import (ContentError, READS, WRITES, SCOPE_FIELDS, scope,
    parameters, match_terms, evidence_body, digest)
from xti.domain.assets import ValidationError
from xti.ports.content_monitoring import ContentRepository, ContentSources
from xti.ports.code_exposure import SecretScanner
from xti.ports.mention_targets import MentionTargetRepository


class ContentMonitoringService:
    def __init__(self, repository: ContentRepository, sources: ContentSources, targets: MentionTargetRepository,
                 scanner: SecretScanner, *, now=None, clock=time.monotonic):
        self.repository, self.sources, self.targets, self.scanner = repository, sources, targets, scanner
        self.now = now or (lambda: datetime.now(timezone.utc).isoformat())
        self.clock = clock
        self.cancelled = lambda: False

    def bindings(self, selected):
        targets = []
        for target in selected['targets']:
            if target['kind'] == 'company': targets.append(dict(target)); continue
            resolved = self.targets.resolve(target['kind'], target['id'])
            targets.append({'kind': resolved.kind, 'id': resolved.id, 'name': resolved.name,
                            'domains': list(resolved.domains), 'aliases': target['aliases']})
        sources = []
        for identifier in selected['sources']:
            source = self.repository.read('content.source.show', {'identifier': identifier})
            if not source['enabled']: raise ContentError('source_disabled', 'Seçilen içerik kaynağı devre dışı.')
            sources.append({k: source[k] for k in ('id', 'revision', 'definition')})
        return {'targets': targets, 'sources': sources}

    def execute(self, operation, **values):
        values = parameters(operation, values)
        if operation == 'content.providers':
            return {'providers': self.sources.status(), 'privacy_scanner': self.scanner.status(),
                    'network_access': False, 'credential_validation': False}
        if operation == 'content.plan':
            watch = self.repository.read(operation, values)
            try:
                current = self.bindings(watch['scope'])
                state = 'ready' if current == watch['bindings'] else 'scope_changed'
            except (ContentError, ValidationError): state = 'scope_unavailable'
            notes = ['Yalnız seçilen kaynak pencereleri incelenir; geçmiş kanal arşivi veya bütün internet değildir.',
                     'Hesap ve kanal erişimi canlı toplama sırasında doğrulanır.']
            if any(source['definition']['provider'] == 'bluesky' for source in watch['bindings']['sources']):
                notes.append('Çalışma sırasında seçilen firma/tedarikçi adı, domaini ve alternatif adları Bluesky genel aramasına gönderilir.')
            return {'watch': watch, 'binding_state': state, 'providers': self.sources.status(),
                    'privacy_scanner': self.scanner.status(), 'network_access': False,
                    'notes': notes}
        if operation in READS: return self.repository.read(operation, values)
        if operation not in WRITES: raise ContentError('invalid_parameters', 'İçerik işlemi bilinmiyor.')
        if operation in ('content.watch.add', 'content.watch.update'):
            replay = self.repository.replay_mutation(operation, values)
            if replay is not None: return {**replay, 'replayed': True}
            if operation == 'content.watch.update' and values.get('enabled') is False and not SCOPE_FIELDS.intersection(values):
                # Stopping requires the stored revision, never healthy external bindings.
                return self.repository.mutate(operation, values, self.now())
            current = self.repository.read('content.watch.show', {'identifier': values['identifier']}) if operation.endswith('.update') else None
            selected = scope({**(current['scope'] if current else {}), **{k: v for k, v in values.items() if k in SCOPE_FIELDS}})
            return self.repository.mutate(operation, values, self.now(), bindings=self.bindings(selected))
        if operation != 'content.run': return self.repository.mutate(operation, values, self.now())
        replay = self.repository.replay_run(values)
        if replay: return {**replay, 'replayed': True}
        watch = self.repository.read('content.watch.show', {'identifier': values['identifier']})
        run, replayed = self.repository.reserve(values, self.now(), bindings=self.bindings(watch['scope']))
        if replayed: return {**run, 'replayed': True}
        selected = run['snapshot']['scope']
        bindings = run['snapshot']['bindings']
        started = self.clock()
        documents, reports, seen, privacy_errors = [], [], set(), set()
        operations_left, items_left = selected['max_operations'], selected['max_items']
        scanner_state = self.scanner.status()
        minimum = lambda source: {'discord': 6, 'telegram': 2, 'bluesky': 2}.get(source['definition']['provider'], 1)
        for index, source in enumerate(bindings['sources']):
            remaining_sources = len(bindings['sources']) - index
            minimum_remaining = sum(minimum(s) for s in bindings['sources'][index:])
            allocation = minimum(source) + max(0, operations_left - minimum_remaining) // remaining_sources
            budget = {'max_operations': min(operations_left, allocation),
                      'max_items': max(1, items_left // remaining_sources),
                      'seconds': max(0, selected['budget_seconds'] - (self.clock() - started))}
            consumed = 0

            def consume(document):
                nonlocal consumed
                if self.cancelled(): raise ContentError('cancelled', 'İçerik işi iptal edildi.')
                if consumed >= budget['max_items']: raise ContentError('budget_exhausted', 'İçerik öğe sınırına ulaşıldı.')
                document.validate(); consumed += 1
                key = (source['id'], document.native_id)
                if key in seen: return
                seen.add(key)
                matches = [{'target': target, 'match': match} for target in bindings['targets']
                           if (match := match_terms(document, target)) is not None]
                matched_targets = {(m['target']['kind'], m['target']['id']) for m in matches}
                if len(matched_targets) != len(bindings['targets']):
                    previous = self.repository.previous_targets(watch['id'], source['id'], document.native_id)
                    matches.extend({'target': target, 'match': {'kind': 'previous_match_not_in_current_text',
                        'domains': [], 'names': [], 'policy': 'company-content-v1',
                        'identity_confirmed': False, 'threat_confirmed': False}}
                        for target in bindings['targets'] if (target['kind'], target['id']) in previous - matched_targets)
                if not matches: return
                combined = document.url + '\n' + ' '.join(document.title.split()) + '\n' + document.content
                privacy = 'metadata_only_scanner_unavailable'
                title, excerpt, url = '[İçerik gizli — maskeleme kontrolü tamamlanmadı]', '', ''
                seconds = selected['budget_seconds'] - (self.clock() - started)
                if scanner_state['state'] == 'ready' and seconds > 0:
                    try:
                        detected = self.scanner.scan(combined, seconds=min(10, seconds))
                        lines = combined.splitlines()
                        for finding in detected:
                            if (set(finding) != {'rule', 'line'} or type(finding['line']) is not int
                                    or not 1 <= finding['line'] <= len(lines)):
                                raise ContentError('invalid_scanner_output', 'Maskeleme aracı satır sözleşmesine uymuyor.')
                            lines[finding['line'] - 1] = '[OLASI GİZLİ BİLGİ MASKELENDİ]'
                        url = '' if any(f['line'] == 1 for f in detected) else document.url
                        title = lines[1]
                        excerpt = '\n'.join(lines[2:])[:4000]
                        privacy = 'secret_lines_masked' if detected else 'secret_pattern_checked'
                    except Exception as error:
                        # External scanners must never leak source lines, tokens or exception text.
                        privacy_errors.add(getattr(error, 'code', 'scanner_failed'))
                else: privacy_errors.add('scanner_unavailable' if scanner_state['state'] != 'ready' else 'budget_exhausted')
                body = evidence_body(source, document, masked_text=excerpt, masked_title=title, privacy=privacy, masked_url=url)
                body['excerpt_truncated'] = len(document.content) > 4000
                documents.append({'body': body, 'matches': matches, 'suppress_new_notification': document.historical})

            if self.cancelled():
                report = {'status': 'cancelled', 'operations': 0, 'items': 0, 'checkpoint': None}
            elif budget['seconds'] <= 0 or budget['max_operations'] < minimum(source) or items_left <= 0:
                report = {'status': 'budget_exhausted', 'operations': 0, 'items': 0, 'checkpoint': None}
            else:
                try:
                    report = self.sources.collect(source, run['snapshot']['checkpoints'].get(source['id'], {}),
                                                  budget, consume, targets=tuple(bindings['targets']))
                except (ContentError, ValidationError) as error:
                    report = {'status': getattr(error, 'code', 'invalid_response'), 'operations': 0,
                              'items': consumed, 'checkpoint': None, 'usage_complete': False}
            reports.append({**report, 'source_id': source['id'], 'provider': source['definition']['provider'],
                            'source_revision': source['revision']})
            operations_left -= (report.get('operations', budget['max_operations']) if report.get('usage_complete', True)
                                else budget['max_operations'])
            items_left -= consumed
        complete = all(r['status'] == 'complete' for r in reports)
        any_observation = any(r.get('items', 0) or r['status'] == 'complete' for r in reports)
        status = 'complete' if complete and not privacy_errors else 'partial' if any_observation else 'failed'
        return self.repository.finish(run['id'], {'status': status, 'sources': reports, 'documents': documents,
            'privacy_errors': sorted(privacy_errors), 'policy': 'company-content-v1',
            'target_count': len(bindings['targets']), 'all_internet_covered': False,
            'elapsed_seconds': round(self.clock() - started, 3)}, self.now())
