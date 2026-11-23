#!/usr/bin/env python3
"""Opt-in, public-only live P01 acceptance. Never uses account credentials or paid APIs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from xti.adapters.betterleaks import BetterleaksScanner
from xti.adapters.code_sources import PublicCodeSources
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_code_exposure import SQLiteCodeRepository
from xti.application.code_exposure import CodeExposureService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--domain', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists(): parser.error('Output already exists; original evidence is preserved.')
    root = Path(tempfile.mkdtemp(prefix='xti-p01-public-live-')).resolve()
    database = root / 'xti.db'; SQLiteAssetRepository(database).initialize()
    sources = PublicCodeSources(credentials=lambda _: None)
    service = CodeExposureService(SQLiteCodeRepository(database), sources, BetterleaksScanner())
    watch = service.execute('code.watch.add', domain=args.domain, max_requests=20, max_files=10,
                            budget_seconds=60, idempotency_key='public-live-watch')
    result = service.execute('code.run', identifier=watch['id'], expected_revision=1, idempotency_key='public-live-run')
    findings = service.execute('code.findings', watch_id=watch['id'], limit=100)
    replay = service.execute('code.run', identifier=watch['id'], expected_revision=1, idempotency_key='public-live-run')
    from code_acceptance_identity import identity
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'data_directory': str(root), 'code': identity(),
              'authenticated': False, 'fixture': False, 'run': result, 'findings': findings,
              'replay_unchanged': replay['report_sha256'] == result['report_sha256'] and replay.get('replayed'),
              'not_tested': ['github-code', 'gitlab-code', 'pastebin', 'complete_internet_coverage']}
    with args.output.open('x') as stream: json.dump(report, stream, ensure_ascii=False, indent=2)
    args.output.chmod(0o600)
    print(json.dumps({'status': result['status'], 'sources': result['report']['sources'],
                      'findings': len(findings['items']), 'replay_unchanged': report['replay_unchanged'],
                      'report': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__': main()
