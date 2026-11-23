"""Explicit interactive Telegram login; the resulting session is never printed."""
import asyncio
import getpass
import importlib.metadata
import logging

from xti.domain.assets import ValidationError


def telegram_login(prompt=getpass.getpass):
    try:
        if importlib.metadata.version('Telethon') != '1.46.0': raise ImportError()
        from telethon import TelegramClient, errors
        from telethon.sessions import StringSession
    except (ImportError, importlib.metadata.PackageNotFoundError):
        raise ValidationError('Telegram bağımlılığı hazır değil; ./scripts/setup-brand çalıştır.') from None
    try:
        api_id = int(prompt('Telegram API id (görünmez): '))
        api_hash = prompt('Telegram API hash (görünmez): ')
        from xti.adapters.content_credentials import validate_credential
        validate_credential('telegram', {'api_id': api_id, 'api_hash': api_hash, 'session': 'a' * 100})
        phone = prompt('Telegram telefon numaran (görünmez): ')
        import re
        if not re.fullmatch(r'\+[0-9]{7,15}', phone): raise ValueError()
    except (ValueError, TypeError): raise ValidationError('Telegram giriş bilgisi biçimi geçersiz.') from None

    async def sign_in():
        client = TelegramClient(StringSession(), api_id, api_hash, timeout=15,
            request_retries=0, connection_retries=0, auto_reconnect=False, receive_updates=False, flood_sleep_threshold=0)
        try:
            await asyncio.wait_for(client.connect(), 20)
            code = await asyncio.wait_for(client.send_code_request(phone), 20)
            received = prompt('Telegram doğrulama kodu (görünmez): ')
            try:
                await asyncio.wait_for(client.sign_in(phone=phone, code=received, phone_code_hash=code.phone_code_hash), 20)
            except errors.SessionPasswordNeededError:
                password = prompt('Telegram iki aşamalı doğrulama parolası (görünmez): ')
                await asyncio.wait_for(client.sign_in(password=password), 20)
            return {'api_id': api_id, 'api_hash': api_hash, 'session': client.session.save()}
        finally: await client.disconnect()

    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try: return asyncio.run(sign_in())
    except Exception:
        raise ValidationError('Telegram girişi tamamlanamadı; oturum kaydedilmedi ve gizli bilgiler gösterilmedi.') from None
    finally: logging.disable(previous)
