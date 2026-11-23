import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from xti.adapters.content_discord import collect_discord
from xti.adapters.content_irc import collect_irc
from xti.adapters.content_telegram_worker import collect
from xti.adapters.content_sources import _version


class ChannelTests(unittest.TestCase):
    def test_interactive_telegram_login_never_returns_or_logs_credentials_on_failure(self):
        if _version('Telethon', '1.46.0') != 'ready': self.skipTest('Pinned Telethon absent')
        from xti.adapters.content_login import telegram_login
        from xti.domain.assets import ValidationError
        answers = iter(['12345', 'a'*32, '+905550000000'])
        class Client:
            def __init__(self, *a, **k): pass
            async def connect(self): raise RuntimeError('sensitive-server-error')
            async def disconnect(self): pass
        with patch('telethon.TelegramClient', Client), self.assertRaises(ValidationError) as error:
            telegram_login(lambda message: next(answers))
        self.assertNotIn('sensitive-server-error', str(error.exception))
        self.assertNotIn('+905550000000', str(error.exception))

    def test_discord_newest_page_is_not_starved_by_old_history(self):
        from tests.test_content_sources import DiscordTests
        row = lambda identifier: {'id': str(identifier), 'channel_id': '223456789', 'content': 'Example update'}
        http, definition = DiscordTests().fixture(rows=[row(523456789), row(423456789)])
        original = http.get
        def get(url, **kwargs):
            if '&before=' not in url: return original(url, **kwargs)
            http.calls.append(url)
            return {'status': 'complete', 'body': json.dumps([row(123456789)]).encode(), 'attempts': [{'http_status': 200}]}
        http.get = get; documents = []
        result = collect_discord(definition, {'token': 'fixture'}, {'before': '323456789'},
            {'seconds': 5, 'max_operations': 7, 'max_items': 4}, documents.append, http=http)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual([d.native_id for d in documents], ['523456789', '423456789', '123456789'])
        self.assertEqual([d.historical for d in documents], [False, False, True])
        self.assertNotIn('before=', http.calls[5]); self.assertIn('before=323456789', http.calls[6])
        self.assertTrue(result['history_complete'])

    def test_telegram_pinned_client_reads_latest_and_backfill_without_join_or_send(self):
        if _version('Telethon', '1.46.0') != 'ready': self.skipTest('Pinned Telethon absent')
        from telethon import types
        at = datetime(2026, 11, 21, tzinfo=timezone.utc)
        channel = types.Channel(1, 'Fixture', types.ChatPhotoEmpty(), at, broadcast=True, username='example')
        calls = []
        class Client:
            def __init__(self, *args, **kwargs): pass
            async def connect(self): calls.append('connect')
            async def disconnect(self): calls.append('disconnect')
            async def get_entity(self, value): calls.append(value); return channel
            async def get_messages(self, entity, *, limit, offset_id):
                calls.append((limit, offset_id))
                return [SimpleNamespace(id=i, message='Example Corp', date=at, edit_date=None) for i in ([9, 8] if not offset_id else [3])]
        with patch('telethon.TelegramClient', Client):
            result = asyncio.run(collect({'credentials': {'session': '', 'api_id': 1, 'api_hash': 'a' * 32},
                'definition': {'locator': 'example'}, 'budget': {'seconds': 5, 'max_items': 4, 'max_operations': 3},
                'checkpoint': {'before': 5}}))
        self.assertEqual(result['status'], 'complete'); self.assertEqual(result['operations'], 3)
        self.assertEqual([d['historical'] for d in result['documents']], [False, False, True])
        self.assertIn((2, 0), calls); self.assertIn((2, 5), calls); self.assertEqual(calls[-1], 'disconnect')

    def test_irc_parser_selects_only_joined_channel_and_sends_no_chat(self):
        if _version('irctokens', '2.0.2') != 'ready': self.skipTest('Pinned irctokens absent')
        class Connection:
            def __init__(self): self.sent = []; self.closed = False
            def sendall(self, data): self.sent.append(data)
            def settimeout(self, value): pass
            def recv(self, limit):
                nick = self.sent[0].decode().split()[1]
                return (f':server 001 {nick} :welcome\r\nJOIN #fixture\r\n:{nick}!u@host JOIN #fixture\r\n'
                        ':other!u@host PRIVMSG #other :ignore\r\n:other!u@host PRIVMSG #fixture :Example Corp report\r\n').encode()
            def close(self): self.closed = True
        connection = Connection()
        context = SimpleNamespace(wrap_socket=lambda raw, **kw: raw)
        documents = []
        result = collect_irc({'locator': 'ircs://irc.example:6697/%23fixture'}, {},
            {'seconds': 5, 'max_items': 1, 'max_operations': 1}, documents.append,
            resolve=lambda *a: '93.184.216.34', connect=lambda *a, **k: connection, context=context)
        self.assertEqual(result['status'], 'partial'); self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].content, 'Example Corp report')
        self.assertFalse(any(b'PRIVMSG' in data for data in connection.sent)); self.assertTrue(connection.closed)
        self.assertTrue(result['offline_gap_possible']); self.assertFalse(result['history_complete'])


if __name__ == '__main__': unittest.main()
