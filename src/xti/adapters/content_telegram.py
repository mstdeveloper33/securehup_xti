"""Bounded Telethon child; credentials go through stdin and never through argv or logs."""
from dataclasses import asdict
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from xti.domain.content_monitoring import ContentDocument


def collect_telegram(definition, credentials, checkpoint, budget, consume):
    try:
        if importlib.metadata.version('Telethon') != '1.46.0': raise importlib.metadata.PackageNotFoundError('Telethon')
    except importlib.metadata.PackageNotFoundError:
        return {'status': 'dependency_unavailable', 'operations': 0, 'items': 0, 'checkpoint': None}
    if budget['max_operations'] < 2:
        return {'status': 'budget_exhausted', 'operations': 0, 'items': 0, 'checkpoint': None}
    with tempfile.TemporaryDirectory(prefix='xti-content-telegram-') as directory:
        destination = Path(directory) / 'result.json'
        payload = {'definition': definition, 'credentials': credentials, 'checkpoint': checkpoint, 'budget': budget}
        try:
            result = subprocess.run([sys.executable, '-m', 'xti.adapters.content_telegram_worker', str(destination)],
                input=json.dumps(payload).encode(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=max(.1, budget['seconds']), check=False,
                env={k: v for k, v in os.environ.items() if k in ('PATH', 'PYTHONPATH', 'LANG', 'SYSTEMROOT')})
            if result.returncode or not destination.is_file() or destination.stat().st_size > 12 * 1024 * 1024:
                raise ValueError()
            response = json.loads(destination.read_text())
            rows = response.pop('documents', [])
            if not isinstance(rows, list) or len(rows) > budget['max_items']: raise ValueError()
            for item in rows: consume(ContentDocument(**item).validate())
            return response
        except subprocess.TimeoutExpired:
            return {'status': 'timeout', 'operations': 0, 'operation_unit': 'telegram_logical_call', 'items': 0,
                    'checkpoint': None, 'usage_complete': False, 'network_requests': None}
        except (OSError, ValueError, TypeError):
            return {'status': 'invalid_response', 'operations': 0, 'operation_unit': 'telegram_logical_call', 'items': 0,
                    'checkpoint': None, 'usage_complete': False, 'network_requests': None}
