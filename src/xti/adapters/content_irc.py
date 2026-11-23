"""Selected public TLS IRC channel, bounded connection window and no outbound chat messages."""
from datetime import datetime, timezone
import importlib.metadata
import socket
import ssl
import time
from urllib.parse import urlsplit, unquote
from uuid import uuid4

from xti.adapters.content_http import resolve_public
from xti.domain.content_monitoring import ContentError, ContentDocument, digest


def collect_irc(definition, checkpoint, budget, consume, *, resolve=resolve_public,
                connect=socket.create_connection, context=None, clock=time.monotonic):
    try:
        if importlib.metadata.version('irctokens') != '2.0.2': raise importlib.metadata.PackageNotFoundError('irctokens')
        import irctokens
    except (ImportError, importlib.metadata.PackageNotFoundError):
        return {'status': 'dependency_unavailable', 'operations': 0, 'items': 0, 'checkpoint': None}
    parsed = urlsplit(definition['locator']); channel = unquote(parsed.path.lstrip('/'))
    started = clock(); started_at = datetime.now(timezone.utc).isoformat()
    connection = None; items = incoming = 0; joined = False; operation = 0
    window = str(uuid4()); nick = 'xti_' + uuid4().hex[:10]
    deadline = min(60, budget['seconds'])
    try:
        address = resolve(parsed.hostname, deadline)
        remaining = deadline - (clock() - started)
        if remaining <= 0: raise ContentError('timeout', 'IRC DNS süre sınırına ulaşıldı.')
        operation = 1
        raw = connect((address, 6697), timeout=min(10, remaining))
        try: connection = (context or ssl.create_default_context()).wrap_socket(raw, server_hostname=parsed.hostname)
        except BaseException: raw.close(); raise

        def send(command, params):
            if command not in ('NICK', 'USER', 'JOIN', 'PONG'): raise ContentError('invalid_command', 'IRC komutu kapsam dışında.')
            connection.sendall((irctokens.build(command, params).format() + '\r\n').encode())

        send('NICK', [nick]); send('USER', ['xti', '0', '*', 'XTI public channel monitor'])
        buffered = b''
        while clock() - started < deadline and items < budget['max_items']:
            connection.settimeout(max(.05, min(1, deadline - (clock() - started))))
            try: block = connection.recv(8192)
            except socket.timeout: continue
            if not block: raise ContentError('disconnected', 'IRC bağlantısı pencere bitmeden kapandı.')
            incoming += len(block)
            if incoming > 4 * 1024 * 1024: raise ContentError('response_too_large', 'IRC pencere boyutu aşıldı.')
            buffered += block
            while b'\n' in buffered:
                line, buffered = buffered.split(b'\n', 1)
                if len(line) > 16384: raise ContentError('invalid_response', 'IRC satırı fazla uzun.')
                message = irctokens.tokenise(line.decode('utf-8', errors='replace').rstrip('\r'))
                if message.command == 'PING': send('PONG', message.params[:1])
                elif message.command == '001': send('JOIN', [channel])
                elif (message.command == 'JOIN' and message.params and message.params[0].casefold() == channel.casefold()
                      and message.source and message.hostmask.nickname.casefold() == nick.casefold()): joined = True
                elif message.command in ('403', '405', '471', '473', '474', '475', '477', '464', '465'):
                    raise ContentError('access_denied', 'IRC kanalına okuma erişimi sağlanamadı.')
                elif joined and message.command == 'PRIVMSG' and len(message.params) == 2 and message.params[0].casefold() == channel.casefold():
                    tags = message.tags or {}
                    native = tags.get('msgid') or window + ':' + str(items)
                    # Without negotiated server-time the precise observed time is in the run window.
                    consume(ContentDocument(native, '', 'IRC kanal mesajı', message.params[1], extent='message'))
                    items += 1
                    if items >= budget['max_items']: break
            if len(buffered) > 16384: raise ContentError('invalid_response', 'IRC satır sınırı aşıldı.')
        state = 'complete' if joined else 'connection_not_ready'
        if items >= budget['max_items']: state = 'partial'
    except (ContentError, OSError, ValueError) as error:
        state = getattr(error, 'code', 'unavailable')
    finally:
        if connection is not None: connection.close()
    return {'status': state, 'operations': operation, 'operation_unit': 'irc_connection_window', 'items': items,
            'coverage': 'connected_interval_only', 'history_complete': False, 'offline_gap_possible': True,
            'window_started_at': started_at, 'window_finished_at': datetime.now(timezone.utc).isoformat(),
            'checkpoint': {'baseline_complete': True, 'last_window': window} if joined else None,
            'network_requests': None, 'outbound_chat_messages': 0}
