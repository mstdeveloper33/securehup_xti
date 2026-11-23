#!/usr/bin/env python3
"""Explicit small public-feed acceptance; no Tavily, channel login or outgoing chat."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.interfaces.content_monitoring import make_content_service
from xti.domain.news import NEWS_SOURCES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): parser.error('Output already exists; never overwrite acceptance evidence.')
    root = Path(tempfile.mkdtemp(prefix='xti-content-public-'))
    database = root / 'xti.db'; SQLiteAssetRepository(database).initialize()
    service = make_content_service(database)
    source_ids = []
    for selected in NEWS_SOURCES:
        if selected.key not in ('ncsc', 'cert-fr'): continue
        record = service.execute('content.source.add', provider='rss', name=selected.name, locator=selected.url,
            language='en' if selected.key == 'ncsc' else 'fr', idempotency_key='live-source:' + selected.key)
        source_ids.append(record['id'])
    watch = service.execute('content.watch.add', name='Public publication acceptance', sources=source_ids,
        targets=[{'name': 'SecureHup', 'domains': ['securehup.com']},
                 {'name': 'UK NCSC positive source control', 'domains': ['ncsc.gov.uk']},
                 {'name': 'CERT-FR positive source control', 'domains': ['cert.ssi.gouv.fr', 'cert.cyber.gouv.fr']}],
        max_operations=8, max_items=100, budget_seconds=120, idempotency_key='live-watch')
    run = service.execute('content.run', identifier=watch['id'], expected_revision=1, idempotency_key='live-run')
    replay = service.execute('content.run', identifier=watch['id'], expected_revision=1, idempotency_key='live-run')
    target = watch['bindings']['targets'][0]
    secure = service.execute('content.report', target_kind='company', target_id=target['id'])
    controls = [service.execute('content.report', target_kind=t['kind'], target_id=t['id']) for t in watch['bindings']['targets'][1:]]
    from xti import __version__
    from xti.adapters.schema import SCHEMA_VERSION
    from content_acceptance_identity import identity
    result = {'executed_at': datetime.now(timezone.utc).isoformat(), 'runtime_version': __version__, 'core_schema': SCHEMA_VERSION,
              'code': identity(),
              'data_dir': str(root), 'run_id': run['id'], 'status': run['status'], 'report': run['report'],
              'replay_reused': replay.get('replayed', False), 'securehup_matches': secure['total_matches'],
              'positive_source_controls': [{'matches': r['total_matches'], 'examples': [
                  {'title': m['evidence']['body']['title'], 'url': m['evidence']['body']['url'], 'privacy': m['evidence']['body']['privacy']}
                  for m in r['items'][:2]]} for r in controls],
              'channels_live_tested': [], 'paid_calls': 0,
              'interpretation': 'Public feed window only. Positive controls are publisher identity checks, not SecureHup matches.'}
    with args.output.open('x', encoding='utf-8') as output: json.dump(result, output, ensure_ascii=False, indent=2)
    print(json.dumps({'artifact': str(args.output), 'status': run['status'], 'securehup_matches': secure['total_matches'],
                      'positive_controls': [r['total_matches'] for r in controls], 'replayed': replay.get('replayed', False)}))
    return 0 if replay.get('replayed') and any(r['total_matches'] for r in controls) and run['status'] in ('complete', 'partial') else 1


if __name__ == '__main__': raise SystemExit(main())
