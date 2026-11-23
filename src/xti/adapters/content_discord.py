"""Official read-only Discord API. Verify visibility/history/content permissions before empty success."""
from datetime import datetime, timezone, timedelta
import json
import re
import time

from xti.domain.content_monitoring import ContentError, ContentDocument


def effective_permissions(guild_id, bot_id, member, roles, channel):
    selected = set(member['roles']) | {guild_id}
    permissions = 0
    for role in roles:
        if role['id'] in selected: permissions |= int(role['permissions'])
    if permissions & 8: return permissions | (1 << 10) | (1 << 16)
    overrides = channel.get('permission_overwrites', [])
    for group in ([o for o in overrides if o['type'] == 0 and o['id'] == guild_id],
                  [o for o in overrides if o['type'] == 0 and o['id'] in selected and o['id'] != guild_id],
                  [o for o in overrides if o['type'] == 1 and o['id'] == bot_id]):
        allow = deny = 0
        for entry in group: allow |= int(entry['allow']); deny |= int(entry['deny'])
        permissions = (permissions & ~deny) | allow
    return permissions


def collect_discord(definition, credentials, checkpoint, budget, consume, *, http, clock=time.monotonic):
    started = clock(); attempts = []; items = 0
    guild, channel_id = definition['locator'].split('/')
    retry_at = None
    if budget['max_operations'] < 6:
        return {'status': 'budget_exhausted', 'items': 0, 'operations': 0, 'checkpoint': None}

    def request(path):
        nonlocal retry_at
        if len(attempts) >= budget['max_operations'] or clock() - started >= budget['seconds']:
            raise ContentError('budget_exhausted', 'Discord işlem bütçesi doldu.')
        response = http.get('https://discord.com/api/v10' + path, seconds=budget['seconds'] - (clock() - started),
                            max_operations=budget['max_operations'] - len(attempts), headers={'Authorization': 'Bot ' + credentials['token']})
        attempts.extend(response['attempts'])
        if response['status'] != 'complete':
            if response['status'] == 'rate_limited':
                retry_at = (datetime.now(timezone.utc) + timedelta(seconds=response.get('retry_after_seconds', 300))).isoformat()
            raise ContentError(response['status'], 'Discord kaynağı yanıtı tamamlanamadı.')
        return json.loads(response['body'])

    try:
        me = request('/users/@me'); app = request('/applications/@me')
        if not me.get('bot') or not re.fullmatch('[1-9][0-9]{5,19}', me.get('id', '')):
            raise ContentError('access_denied', 'Discord için bot erişimi gerekli.')
        if not int(app.get('flags', 0)) & ((1 << 18) | (1 << 19)):
            raise ContentError('content_permission_missing', 'Discord Message Content izni doğrulanamadı.')
        channel = request('/channels/' + channel_id)
        if channel.get('id') != channel_id or channel.get('guild_id') != guild:
            raise ContentError('scope_mismatch', 'Discord kanalı seçilen sunucuya ait değil.')
        if channel.get('type') not in (0, 5):
            raise ContentError('unsupported_channel_type', 'Bu adaptör seçili metin/duyuru kanalını okur; DM/forum/thread ayrıca desteklenmelidir.')
        member = request('/guilds/' + guild + '/members/' + me['id'])
        roles = request('/guilds/' + guild + '/roles')
        permissions = effective_permissions(guild, me['id'], member, roles, channel)
        if permissions & ((1 << 10) | (1 << 16)) != ((1 << 10) | (1 << 16)):
            raise ContentError('history_permission_missing', 'Discord kanal görünürlüğü/geçmiş okuma izni yok.')
        # Always inspect newest messages before one bounded historical page.
        before = checkpoint.get('before')
        if before is not None and not re.fullmatch('[1-9][0-9]{5,19}', str(before)):
            raise ContentError('invalid_checkpoint', 'Discord ilerleme kaydı geçersiz.')
        can_backfill = bool(before and budget['max_items'] > 1 and budget['max_operations'] >= 7)
        page_limit = min(100, max(1, budget['max_items'] // 2) if can_backfill else budget['max_items'])
        def page(limit, cursor=None):
            nonlocal items
            rows = request('/channels/' + channel_id + '/messages?limit=' + str(limit) + ('&before=' + cursor if cursor else ''))
            if not isinstance(rows, list) or len(rows) > limit: raise ValueError()
            previous = int(cursor) if cursor else None
            for row in rows:
                identifier = row['id']
                if not re.fullmatch('[1-9][0-9]{5,19}', identifier) or row.get('channel_id') != channel_id: raise ValueError()
                if previous is not None and int(identifier) >= previous: raise ValueError()
                previous = int(identifier)
                content = row.get('content', '')
                if not isinstance(content, str): raise ValueError()
                when = lambda value: datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc).isoformat() if value else None
                consume(ContentDocument(identifier, f'https://discord.com/channels/{guild}/{channel_id}/{identifier}',
                    'Discord kanal mesajı', content, when(row.get('timestamp')), when(row.get('edited_timestamp')), 'message', historical=bool(cursor)))
                items += 1
            return rows
        latest = page(page_limit)
        historical_complete = len(latest) < page_limit and not before
        next_before = before or (latest[-1]['id'] if len(latest) == page_limit else None)
        historical_page_checked = False
        if can_backfill and len(attempts) < budget['max_operations']:
            older_limit = min(100, budget['max_items'] - items)
            older = page(older_limit, before)
            historical_complete = len(older) < older_limit
            next_before = None if historical_complete else older[-1]['id']
            historical_page_checked = True
        return {'status': 'complete', 'items': items, 'operations': len(attempts),
                'operation_unit': 'http_open_attempt', 'attempts': attempts, 'coverage': 'selected_channel_text_pages',
                'history_complete': historical_complete, 'latest_window_checked': True, 'latest_window_limit': page_limit,
                'historical_page_checked': historical_page_checked, 'attachments_checked': False,
                'older_edits_require_backfill_cycle': True,
                'checkpoint': {'before': next_before, 'baseline_complete': True}}
    except (ContentError, ValueError, TypeError, KeyError, OverflowError) as error:
        return {'status': getattr(error, 'code', 'invalid_response'), 'items': items, 'operations': len(attempts),
                'operation_unit': 'http_open_attempt', 'attempts': attempts,
                'checkpoint': {**checkpoint, 'retry_at': retry_at} if retry_at else None}
