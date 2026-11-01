"""Pinned, redirect-free HTTPS transport for user-approved webhook targets."""

from __future__ import annotations

from collections.abc import Mapping
import http.client
import socket
import ssl
from urllib.parse import urlsplit

from xti.adapters.https_probe import is_public_address
from xti.domain.webhooks import WebhookSendResult, normalize_webhook_url


_MAX_RESPONSE_BODY = 8 * 1024
_MAX_RESPONSE_HEADERS = 16 * 1024
_MAX_RESOLVED_ADDRESSES = 16


class _PermanentTargetError(Exception):
    pass


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, *, timeout: float) -> None:
        super().__init__(
            host, port=443, timeout=timeout, context=ssl.create_default_context(),
        )
        self._address = address

    def connect(self) -> None:
        raw = socket.create_connection((self._address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def _resolve_public(host: str, port: int) -> tuple[str, ...]:
    try:
        rows = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as error:
        raise TimeoutError("DNS çözümlemesi tamamlanamadı") from error
    addresses = tuple(sorted({row[4][0] for row in rows}))
    if not addresses or len(addresses) > _MAX_RESOLVED_ADDRESSES:
        raise _PermanentTargetError("Webhook hedefinin DNS kapsamı güvenli sınırda değil.")
    if any(not is_public_address(value) for value in addresses):
        raise _PermanentTargetError(
            "Webhook hedefi yalnız genel internet IP adreslerine çözülmeli."
        )
    return addresses


class SafeHttpsWebhookSender:
    """POST one bounded body to one DNS-pinned public HTTPS address."""

    def send(
        self, url: str, body: bytes, headers: Mapping[str, str], *, timeout: float,
    ) -> WebhookSendResult:
        connection: _PinnedHTTPSConnection | None = None
        try:
            canonical, _ = normalize_webhook_url(url)
            if canonical != url or not isinstance(body, bytes) or len(body) > 256 * 1024:
                raise _PermanentTargetError("Webhook hedefi veya gövdesi geçersiz.")
            if type(timeout) not in {int, float} or not 1.0 <= float(timeout) <= 30.0:
                raise _PermanentTargetError("Webhook zaman aşımı güvenli sınırda değil.")
            parsed = urlsplit(url)
            assert parsed.hostname is not None
            addresses = _resolve_public(parsed.hostname, 443)
            connection = _PinnedHTTPSConnection(
                parsed.hostname, addresses[0], timeout=float(timeout),
            )
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            connection.request("POST", path, body=body, headers=dict(headers))
            response = connection.getresponse()
            header_size = sum(
                len(name.encode("latin-1")) + len(value.encode("latin-1")) + 4
                for name, value in response.getheaders()
            )
            if header_size > _MAX_RESPONSE_HEADERS:
                raise _PermanentTargetError("Webhook yanıt başlıkları güvenli sınırı aştı.")
            response.read(_MAX_RESPONSE_BODY + 1)
            status = response.status
            if not 100 <= status <= 599:
                raise _PermanentTargetError("Webhook geçerli HTTP durumu döndürmedi.")
            if 200 <= status <= 299:
                return WebhookSendResult("delivered", status, None)
            if status in {408, 425, 429} or 500 <= status <= 599:
                return WebhookSendResult(
                    "retryable", status,
                    "Hedef geçici başarısızlık bildirdi; daha sonra açıkça yeniden denenebilir.",
                )
            return WebhookSendResult(
                "failed", status,
                "Hedef isteği kalıcı olarak reddetti; adres ve alıcı yapılandırmasını kontrol edin.",
            )
        except _PermanentTargetError as error:
            return WebhookSendResult("failed", None, str(error))
        except ssl.SSLCertVerificationError:
            return WebhookSendResult(
                "failed", None, "Webhook hedefinin TLS kimliği doğrulanamadı.",
            )
        except (TimeoutError, socket.timeout, ConnectionError, OSError, ssl.SSLError,
                http.client.HTTPException):
            return WebhookSendResult(
                "retryable", None,
                "Webhook ağı veya hedefi geçici olarak tamamlanamadı; daha sonra yeniden denenebilir.",
            )
        finally:
            if connection is not None:
                connection.close()
