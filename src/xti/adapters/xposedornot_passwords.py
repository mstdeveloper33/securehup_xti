"""Non-persistent XposedOrNot password exposure check with local Keccak-512."""

from __future__ import annotations

from datetime import datetime, timezone
from http.client import HTTPException
import json
import re
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from xti import __version__
from xti.domain.assets import ValidationError


BASE = "https://passwords.xposedornot.com/api/v1/pass/anon/"
MAX_RESPONSE = 64 * 1024
TIMEOUT = 15
DEADLINE = 30
_MASK = (1 << 64) - 1
_ROUND_CONSTANTS = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A,
    0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
    0x8000000080008081, 0x8000000000008009, 0x000000000000008A,
    0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
    0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
    0x000000000000800A, 0x800000008000000A, 0x8000000080008081,
    0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)
_ROTATIONS = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)


class XposedOrNotPasswordError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def _rotate(value: int, count: int) -> int:
    if count == 0:
        return value & _MASK
    return ((value << count) | (value >> (64 - count))) & _MASK


def _permutation(state: list[int]) -> None:
    for constant in _ROUND_CONSTANTS:
        columns = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15]
                   ^ state[x + 20] for x in range(5)]
        deltas = [columns[(x - 1) % 5] ^ _rotate(columns[(x + 1) % 5], 1)
                  for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] ^= deltas[x]
        moved = [0] * 25
        for x in range(5):
            for y in range(5):
                moved[y + 5 * ((2 * x + 3 * y) % 5)] = _rotate(
                    state[x + 5 * y], _ROTATIONS[x][y]
                )
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] = (
                    moved[x + 5 * y]
                    ^ ((~moved[(x + 1) % 5 + 5 * y])
                       & moved[(x + 2) % 5 + 5 * y])
                ) & _MASK
        state[0] ^= constant


def keccak_512(content: bytes) -> bytes:
    """Return legacy Keccak-512 (not FIPS SHA3-512), dependency-free."""
    if not isinstance(content, bytes):
        raise TypeError("Keccak input must be bytes")
    rate = 72
    padding = bytearray(content)
    padding.append(0x01)
    padding.extend(b"\x00" * ((rate - len(padding) % rate) % rate))
    padding[-1] |= 0x80
    state = [0] * 25
    for offset in range(0, len(padding), rate):
        block = padding[offset:offset + rate]
        for lane in range(rate // 8):
            state[lane] ^= int.from_bytes(block[lane * 8:(lane + 1) * 8], "little")
        _permutation(state)
    output = bytearray()
    while len(output) < 64:
        for lane in range(rate // 8):
            output.extend(state[lane].to_bytes(8, "little"))
            if len(output) >= 64:
                break
        if len(output) < 64:
            _permutation(state)
    return bytes(output[:64])


def password_prefix(password: str) -> str:
    if not isinstance(password, str):
        raise ValidationError("Parola metin olmalı.")
    encoded = password.encode("utf-8")
    if len(encoded) > 4096:
        raise ValidationError("Parola 4096 UTF-8 bayt sınırını aşıyor.")
    return keccak_512(encoded).hex()[:10]


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _parse(content: bytes, expected_prefix: str) -> tuple[int, bool]:
    try:
        raw = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
        if not isinstance(raw, dict) or not isinstance(raw.get("SearchPassAnon"), dict):
            raise ValueError("invalid envelope")
        result = raw["SearchPassAnon"]
        if result.get("anon") != expected_prefix:
            raise ValueError("prefix mismatch")
        count_value = result.get("count")
        if isinstance(count_value, str) and count_value.isascii() and count_value.isdecimal():
            count = int(count_value)
        elif type(count_value) is int:
            count = count_value
        else:
            raise ValueError("invalid count")
        if not 0 <= count <= 2**63 - 1:
            raise ValueError("count outside bounds")
        wordlist_value = result.get("wordlist", 0)
        if wordlist_value not in (0, 1, False, True):
            raise ValueError("invalid wordlist flag")
        # `char` describes the secret's length/composition and is intentionally discarded.
        return count, bool(wordlist_value)
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise XposedOrNotPasswordError(
            "source_invalid", "XposedOrNot parola yanıtı geçersiz veya güvenli sınırları aşıyor."
        ) from error


class XposedOrNotPasswordSource:
    def __init__(self, *, opener=None, now=None, monotonic=None):
        self.opener = opener or build_opener(ProxyHandler({}), _NoRedirects())
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic

    def check_password(self, password: str) -> dict:
        prefix = password_prefix(password)
        url = BASE + prefix
        request = Request(url, headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": f"XTI/{__version__} password-prefix-check",
        })
        started = self.monotonic()
        try:
            with self.opener.open(request, timeout=TIMEOUT) as response:
                if response.getcode() != 200 or response.geturl() != url:
                    raise XposedOrNotPasswordError(
                        "source_unexpected", "XposedOrNot beklenen sabit HTTPS yanıtını vermedi."
                    )
                if response.headers.get("Content-Encoding") not in (None, "identity"):
                    raise XposedOrNotPasswordError(
                        "source_invalid", "XposedOrNot desteklenmeyen sıkıştırma kullandı."
                    )
                if "application/json" not in response.headers.get("Content-Type", "").casefold():
                    raise XposedOrNotPasswordError(
                        "source_invalid", "XposedOrNot parola yanıtı JSON değil."
                    )
                declared = response.headers.get("Content-Length")
                if declared is not None and (
                    not declared.isascii() or not declared.isdecimal()
                    or int(declared) > MAX_RESPONSE
                ):
                    raise XposedOrNotPasswordError(
                        "source_too_large", "XposedOrNot parola yanıtı 64 KiB sınırını aşıyor."
                    )
                chunks, size = [], 0
                while True:
                    if self.monotonic() - started > DEADLINE:
                        raise XposedOrNotPasswordError(
                            "source_timeout", "XposedOrNot parola yanıtı okuma süresini aştı."
                        )
                    block = response.read(min(8192, MAX_RESPONSE + 1 - size))
                    if not block:
                        break
                    size += len(block)
                    if size > MAX_RESPONSE:
                        raise XposedOrNotPasswordError(
                            "source_too_large", "XposedOrNot parola yanıtı 64 KiB sınırını aşıyor."
                        )
                    chunks.append(block)
                if declared is not None and size != int(declared):
                    raise XposedOrNotPasswordError(
                        "source_invalid", "XposedOrNot parola yanıtı eksik alındı."
                    )
                count, wordlist = _parse(b"".join(chunks), prefix)
        except HTTPError as error:
            if error.code == 404:
                count, wordlist = 0, False
            elif error.code == 429:
                raise XposedOrNotPasswordError(
                    "rate_limited", "XposedOrNot parola istek sınırına ulaşıldı."
                ) from None
            else:
                raise XposedOrNotPasswordError(
                    "source_unavailable", f"XposedOrNot parola kaynağı HTTP {error.code} verdi."
                ) from None
        except XposedOrNotPasswordError:
            raise
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError):
            raise XposedOrNotPasswordError(
                "source_unavailable", "XposedOrNot parola kaynağına güvenli bağlantı tamamlanamadı."
            ) from None
        checked = self.now()
        if checked.tzinfo is None or checked.utcoffset() is None:
            raise XposedOrNotPasswordError(
                "clock_error", "XposedOrNot parola kontrol zamanı saat dilimli olmalı."
            )
        return {
            "provider": "xposedornot_passwords",
            "checked_at": checked.astimezone(timezone.utc).isoformat(),
            "exposed": count > 0,
            "exposure_count": count,
            "wordlist": wordlist,
            "stored": False,
            "plaintext_transmitted": False,
            "full_hash_transmitted": False,
            "prefix_characters_transmitted": 10,
            "limitations": [
                "Gönderilen 10 hexadecimal karakterlik önek olası parolalar hakkında sınırlı bilgi taşır.",
                "Kayıt bulunmaması parolanın güvenli olduğunu veya başka veri kümelerinde bulunmadığını kanıtlamaz.",
            ],
        }
