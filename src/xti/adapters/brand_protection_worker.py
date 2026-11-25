"""Isolated offline parsers/rendering. No provider URL is fetched in this process."""
import base64
import importlib
import json
import os
import ssl
import sys
from xti.adapters.brand_protection_process import (
    SANDBOX_REQUIRED,
    SANDBOX_TRUSTED_CI_FIXTURE,
    browser_sandbox_mode,
)


def parse_google(values):
    original=ssl._create_default_https_context
    try: module=importlib.import_module('google_play_scraper.features.app' if values.get('app_id') else 'google_play_scraper.features.search')
    finally: ssl._create_default_https_context=original
    # Upstream is used only as a parser, never its TLS-disabling request helper.
    module.get=lambda url:values['html']
    import socket
    def blocked(*args,**kwargs):raise RuntimeError('Offline parser has no network')
    socket.create_connection=blocked
    socket.socket=blocked
    rows=[{**module.app(values['app_id'],country=values['country'].lower()), 'appId': values['app_id']}] if values.get('app_id') else module.search(values['query'],n_hits=values['limit'],country=values['country'].lower())
    if any(not row.get('appId') or not row.get('title') or not row.get('developer') for row in rows):
        return {'status':'invalid_response','items':[]}
    return {'status':'complete' if rows else 'empty_unverified','items':[
        {k:row.get(k) for k in ('appId','title','developer','developerId','url','icon','summary','description')} for row in rows]}


def render(values):
    resources=values['resources']
    sandbox_mode=browser_sandbox_mode()
    if sandbox_mode==SANDBOX_TRUSTED_CI_FIXTURE:
        fixture='https://xti-offline.invalid/'
        if values.get('url')!=fixture or set(resources)!={fixture}:
            raise ValueError('Sandbox-free CI mode accepts only the fixed offline fixture')
    if len(resources)>40:raise ValueError('resource budget')
    if sum(len(v['body']) for v in resources.values())>16*1024*1024:raise ValueError('resource bytes')
    # Reject an invalid or over-budget request before importing the optional
    # browser runtime.  The security boundary must not depend on Playwright
    # being installed, and malformed input must never start browser setup.
    from playwright.sync_api import sync_playwright
    blocked=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,chromium_sandbox=sandbox_mode==SANDBOX_REQUIRED,
            args=['--disable-background-networking','--disable-component-update','--disable-sync','--disable-breakpad',
                  '--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND'],
            proxy={'server':'http://127.0.0.1:9','bypass':''})
        context=browser.new_context(java_script_enabled=False,service_workers='block',offline=True,
            accept_downloads=False,viewport={'width':1280,'height':800},device_scale_factor=1)
        def route(request):
            item=resources.get(request.request.url)
            if request.request.method!='GET' or item is None or request.request.resource_type in ('media','websocket','eventsource'):
                blocked.append(request.request.resource_type);request.abort();return
            request.fulfill(status=200,body=base64.b64decode(item['body'],validate=True),headers={
                'Content-Type':item['content_type'],'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline' https:; img-src https: data:; font-src https: data:; form-action 'none'; frame-src 'none'; script-src 'none'"})
        context.route('**/*',route)
        context.route_web_socket('**/*',lambda ws:ws.close())
        page=context.new_page()
        page.goto(values['url'],wait_until='load',timeout=15000)
        if page.url!=values['url']:raise ValueError('unexpected navigation')
        if values.get('image_url'):
            data=page.locator('img').screenshot(type='png',animations='disabled',timeout=5000)
        else:data=page.screenshot(type='png',full_page=False,animations='disabled',timeout=5000)
        title=page.title()[:400]
        context.close();browser.close()
    if len(data)>3*1024*1024:raise ValueError('screenshot size')
    return {'status':'complete','png':base64.b64encode(data).decode(),'blocked_resources':len(blocked),'title':title,
            'network_requests':0,'render_mode':'static_no_javascript','browser_sandbox_mode':sandbox_mode}


def main():
    raw=sys.stdin.buffer.read(18*1024*1024+1)
    if len(raw)>18*1024*1024:raise ValueError('input budget')
    values=json.loads(raw)
    result=parse_google(values) if values['mode']=='google' else render(values)
    sys.stdout.write(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':
    try:main()
    except Exception:
        sys.stdout.write('{"status":"parser_or_renderer_error"}')
        raise SystemExit(1)
