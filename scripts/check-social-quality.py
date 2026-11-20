#!/usr/bin/env python3
"""Offline labelled social-page benchmark; no live accuracy/ownership claim."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from xti.adapters.public_profile_pages import parse_page
from xti.domain.social_discovery import assess, profile_url


def run():
    path = ROOT / 'tests/fixtures/social_quality_v1.json'
    raw = path.read_bytes()
    corpus = json.loads(raw)
    counts, matrix, results = Counter(), Counter(), []
    started = time.monotonic()
    for case in corpus['cases']:
        candidate = profile_url(case['url'], case['platform'])
        page = parse_page(case['url'], case['final_url'], case['status'], case['html'].encode(),
            checked_at='2026-11-20T00:00:00+00:00')
        if case['error']:
            from dataclasses import replace
            page = replace(page, error=case['error'])
        observed = assess(candidate, page, {'domain': 'acme.example', 'name': 'Acme'})
        ok = (observed['state'], observed['brand_relation']) == (case['expected_state'], case['expected_relation'])
        counts['passed' if ok else 'failed'] += 1
        counts['label_' + case['expected_state']] += 1
        if observed['state'] == 'found' and case['expected_state'] != 'found': counts['false_presence'] += 1
        if observed['state'] == 'not_found' and case['expected_state'] != 'not_found': counts['false_absence'] += 1
        if case['expected_state'] == 'found' and observed['state'] != 'found': counts['missed_presence'] += 1
        matrix[(case['expected_state'], observed['state'])] += 1
        results.append({'id': case['id'], 'expected': case['expected_state'], 'observed': observed, 'passed': ok})
    return {'version': 1, 'corpus_sha256': hashlib.sha256(raw).hexdigest(), 'scope': corpus['scope'],
        'cases': len(results), 'counts': dict(counts), 'network_requests': 0,
        'elapsed_seconds': round(time.monotonic() - started, 6),
        'confusion': [{'expected': a, 'observed': b, 'count': count} for (a, b), count in sorted(matrix.items())],
        'results': results, 'notes': ['Kontrollü sayfa örnekleri; bütün internet veya canlı keşif doğruluğu yüzdesi değildir.',
            'Bir profilin varlığı ile firmanın resmî hesabı olması ayrı değerlendirilir.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(text)
    print(text)
    raise SystemExit(1 if report['counts'].get('failed', 0) else 0)
