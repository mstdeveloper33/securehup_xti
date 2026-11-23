"""Offline Chromium PDF renderer; the worker cannot access the network."""

import base64
import json
import os
import sys


def main() -> None:
    raw = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("input budget")
    values = json.loads(raw)
    html = values["html"]
    if not isinstance(html, str) or len(html.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("html budget")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, chromium_sandbox=True,
            args=[
                "--disable-background-networking", "--disable-component-update",
                "--disable-sync", "--disable-breakpad", "--no-first-run",
                "--host-resolver-rules=MAP * ~NOTFOUND",
            ],
            proxy={"server": "http://127.0.0.1:9", "bypass": ""},
        )
        context = browser.new_context(
            java_script_enabled=False, service_workers="block", offline=True,
            accept_downloads=False,
        )
        page = context.new_page()
        page.route("**/*", lambda route: route.abort())
        page.set_content(html, wait_until="load", timeout=15_000)
        payload = page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
        context.close()
        browser.close()
    if not payload.startswith(b"%PDF-") or len(payload) > 8 * 1024 * 1024:
        raise ValueError("pdf budget")
    sys.stdout.write(json.dumps({
        "status": "complete", "pdf": base64.b64encode(payload).decode("ascii"),
        "network_requests": 0,
    }, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stdout.write('{"status":"renderer_error"}')
        raise SystemExit(1)
