"""Private worker for selected public Telegram channel text; never joins, sends or downloads media."""
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import json
import logging
import os
import sys

from xti.domain.content_monitoring import ContentDocument


async def collect(payload):
    from telethon import TelegramClient, errors, types
    from telethon.sessions import StringSession
    credentials, definition, budget, checkpoint = (payload[k] for k in ('credentials', 'definition', 'budget', 'checkpoint'))
    client = TelegramClient(StringSession(credentials['session']), credentials['api_id'], credentials['api_hash'],
        timeout=min(10, budget['seconds']), request_retries=0, connection_retries=0, retry_delay=0,
        auto_reconnect=False, flood_sleep_threshold=0, receive_updates=False)
    operations, documents = 0, []
    try:
        await client.connect()
        operations += 1
        entity = await client.get_entity(definition['locator'])
        if (not isinstance(entity, types.Channel) or not entity.broadcast or not entity.username
                or entity.username.casefold() != definition['locator'].casefold()):
            return {'status': 'scope_mismatch', 'operations': operations, 'items': 0, 'checkpoint': None}
        before = checkpoint.get('before', 0)
        if type(before) is not int or not 0 <= before < 2**31: raise ValueError()
        can_backfill = bool(before and budget['max_operations'] >= 3 and budget['max_items'] > 1)
        limit = min(100, max(1, budget['max_items'] // 2) if can_backfill else budget['max_items'])
        async def page(size, cursor=0):
            nonlocal operations
            operations += 1
            messages = await client.get_messages(entity, limit=size, offset_id=cursor)
            if len(messages) > size: raise ValueError()
            previous = cursor or 2**31
            for message in messages:
                if type(message.id) is not int or not 0 < message.id < previous: raise ValueError()
                previous = message.id
                doc = ContentDocument(str(message.id), 'https://t.me/' + definition['locator'] + '/' + str(message.id),
                    'Telegram kanal mesajı', message.message or '',
                    message.date.astimezone(timezone.utc).isoformat() if message.date else None,
                    message.edit_date.astimezone(timezone.utc).isoformat() if message.edit_date else None,
                    'message', historical=bool(cursor)).validate()
                documents.append(asdict(doc))
            return messages
        newest = await page(limit)
        complete = len(newest) < limit and not before
        next_before = before or (newest[-1].id if len(newest) == limit else 0)
        if can_backfill:
            older_limit = min(100, budget['max_items'] - len(documents))
            older = await page(older_limit, before)
            complete = len(older) < older_limit
            next_before = 0 if complete else older[-1].id
        return {'status': 'complete', 'operations': operations, 'items': len(documents),
                'documents': documents, 'operation_unit': 'telegram_logical_call', 'network_requests': None,
                'coverage': 'selected_public_channel_text_pages', 'media_checked': False,
                'history_complete': complete, 'latest_window_checked': True, 'latest_window_limit': limit,
                'historical_page_checked': can_backfill, 'older_edits_require_backfill_cycle': True,
                'checkpoint': {'before': next_before, 'baseline_complete': True}}
    except errors.FloodWaitError as error:
        return {'status': 'rate_limited', 'operations': operations, 'items': 0, 'checkpoint': {**checkpoint,
            'retry_at': (datetime.now(timezone.utc) + timedelta(seconds=min(error.seconds, 86400))).isoformat()}}
    except (errors.AuthKeyError, errors.UnauthorizedError):
        return {'status': 'authentication_required', 'operations': operations, 'items': 0, 'checkpoint': None}
    except errors.RPCError:
        return {'status': 'access_denied', 'operations': operations, 'items': 0, 'checkpoint': None}
    finally:
        await client.disconnect()


def main():
    logging.disable(logging.CRITICAL)
    try:
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384: raise ValueError()
        payload = json.loads(raw)
        result = asyncio.run(asyncio.wait_for(collect(payload), timeout=payload['budget']['seconds']))
    except Exception:
        result = {'status': 'unavailable', 'items': 0, 'operations': 0, 'checkpoint': None,
                  'operation_unit': 'telegram_logical_call', 'usage_complete': False, 'network_requests': None}
    with os.fdopen(os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
        json.dump(result, output)


if __name__ == '__main__': main()
