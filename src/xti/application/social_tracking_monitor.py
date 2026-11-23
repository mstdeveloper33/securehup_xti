"""Bounded foreground scheduling; locks are held by each operation, never while sleeping."""
from datetime import datetime, timezone
import time
from uuid import uuid4

from xti.application.foreground_monitor import MonotonicBudget
from xti.domain.assets import ValidationError
from xti.domain.social_discovery import SocialDiscoveryError
from xti.domain.social_tracking import due_at


def monitor(identifier, execute, *, max_cycles=3, max_duration_seconds=86400,
            clock=None, monotonic=time.monotonic, sleeper=time.sleep, progress=None):
    for value, low, high in ((max_cycles, 1, 1000), (max_duration_seconds, 1, 604800)):
        if type(value) is not int or not low <= value <= high:
            raise ValidationError('İzleme tur sınırı 1–1000, süre sınırı 1–604800 saniye olmalı.')
    clock = clock or (lambda: datetime.now(timezone.utc))
    budget = MonotonicBudget(
        monotonic,
        invalid_message='İzleme süresini ölçen saat geçersiz veya geriye gitti.',
        rollback_message='İzleme süresini ölçen saat geçersiz veya geriye gitti.',
    )
    budget.start()
    runs, stop = [], 'cycles'
    elapsed = budget.elapsed

    while len(runs) < max_cycles:
        remaining = max_duration_seconds - elapsed()
        if remaining <= 0: stop = 'duration'; break
        watch = execute('brand.tracking.show', identifier=identifier)['record']
        if not watch['enabled']: stop = 'paused'; break
        due = due_at(watch)
        wait = max(0.0, (datetime.fromisoformat(due) - clock()).total_seconds()) if due else 0.0
        if wait:
            sleeper(min(1.0, remaining, wait))
            continue
        try:
            result = execute('brand.tracking.run', identifier=identifier, force=False,
                             idempotency_key='monitor-' + str(uuid4()))
        except SocialDiscoveryError as error:
            if error.code != 'not_due': raise
            continue  # Another runner may have completed the due operation.
        run = result['record']
        runs.append({key: run[key] for key in ('id', 'status', 'discovery_id', 'baseline', 'unchecked_count')})
        if progress: progress(run)
    return {'watch_id': identifier, 'runs': runs, 'completed_cycles': len(runs), 'stop_reason': stop,
            'elapsed_seconds': round(elapsed(), 3),
            'notes': ['Her tur kalıcıdır. Ctrl+C tamamlanan turları korur.',
                      'Yalnız terminal açıkken çalışır; süre sınırı yeni tur başlatmayı sınırlar.',
                      'Düzenli takip Tavily veya Bright Data çağrısı yapmaz.']}
