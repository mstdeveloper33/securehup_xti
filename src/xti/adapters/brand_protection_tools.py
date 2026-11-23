"""Pinned P03 libraries and locally verified browser installation; no network."""
import base64
import hashlib
import importlib.metadata
import json
from pathlib import Path

PACKAGES={'Pillow':'13.0.0','ImageHash':'4.3.2','playwright':'1.65.2','google-play-scraper':'1.2.7'}
REVISION='1255'


def browser_directory():return Path(__file__).resolve().parents[3]/'.tools'/'playwright'/PACKAGES['playwright']


def binary(directory):
    found=[p for pattern in ('chromium_headless_shell-'+REVISION+'/**/headless_shell','chromium_headless_shell-'+REVISION+'/**/chrome-headless-shell') for p in directory.glob(pattern) if p.is_file()]
    if len(found)!=1 or not found[0].resolve().is_relative_to(directory.resolve()):raise ValueError('Pinned browser binary missing')
    return found[0]


def checksum(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def verify_packages():
    for name,version in PACKAGES.items():
        if importlib.metadata.version(name)!=version:raise ValueError('P03 dependency version differs: '+name)
    # Do not import google-play-scraper in the trusted engine process (TLS side effect).
    from xti.adapters.brand_protection_visual import fingerprint
    from PIL import Image
    from io import BytesIO
    stream=BytesIO();Image.new('RGB',(32,32),'blue').save(stream,format='PNG')
    if fingerprint(stream.getvalue())[0]['algorithm']!='ImageHash-4.3.2/phash8+dhash8+colorhash3':raise ValueError('Visual engine verification failed')


def browser_status(directory=None,*,verify_hash=False):
    directory=directory or browser_directory()
    try:
        receipt=json.loads((directory/'xti-receipt.json').read_text())
        path=binary(directory)
        if receipt['sdk']!=PACKAGES['playwright'] or receipt['revision']!=REVISION or receipt['binary']!=path.relative_to(directory).as_posix():raise ValueError()
        if verify_hash and checksum(path)!=receipt['binary_sha256']:raise ValueError()
        return {'state':'ready','sdk':receipt['sdk'],'revision':receipt['revision'],'archive_hash_pinned':False}
    except (OSError,ValueError,KeyError):return {'state':'not_verified','sdk':PACKAGES['playwright'],'revision':REVISION,'archive_hash_pinned':False}


def smoke(directory=None):
    from xti.adapters.brand_protection_process import run_worker
    url='https://xti-offline.invalid/'
    html=b'<html><title>XTI offline</title><body><h1>Brand fixture</h1><img src="https://127.0.0.1/private"><script>fetch("https://blocked.invalid/")</script></body></html>'
    result=run_worker({'mode':'render','url':url,'resources':{url:{'body':base64.b64encode(html).decode(),'content_type':'text/html'}}},30,browser_path=directory)
    if result.get('status')!='complete' or result.get('network_requests')!=0 or result.get('blocked_resources',0)<1:raise ValueError('Offline Chromium check failed; inspect host browser libraries/sandbox support')
    return {k:v for k,v in result.items() if k!='png'}
