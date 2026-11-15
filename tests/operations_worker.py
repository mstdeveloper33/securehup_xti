"""Test-only transport injection for real CLI and systemd acceptance processes.

The production HIBP parser/adapter, services and SQLite repositories still run.
Only its HTTP opener is controlled; this is not a real-socket outage experiment.
All socket connection attempts are denied so a fixture cannot contact a source.
"""

from io import BytesIO
import json
import os
from pathlib import Path
import socket
import sys
import time
from urllib.error import HTTPError, URLError


MODES = {"success", "timeout", "disconnect", "429", "503", "malformed", "block"}


def catalog():
    return [{
        "Name": "SyntheticAcceptance", "Title": "Synthetic acceptance record",
        "Domain": "example.com", "BreachDate": "2025-01-02",
        "AddedDate": "2025-02-03T04:05:00Z", "ModifiedDate": "2025-02-03T04:05:00Z",
        "PwnCount": 1, "DataClasses": ["Email addresses"],
        "IsVerified": False, "IsFabricated": True, "IsSensitive": False,
        "IsRetired": False, "IsSpamList": False, "IsMalware": False, "IsStealerLog": False,
    }]


class Response(BytesIO):
    def __init__(self, body, url):
        super().__init__(body)
        self.url = url
        self.headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}

    def getcode(self):
        return 200

    def geturl(self):
        return self.url


def controlled_opener(control):
    def open_response(request, *, timeout):
        from xti.domain.public_notices import HIBP_SOURCE_URL

        if request.full_url != HIBP_SOURCE_URL:
            raise AssertionError("Acceptance transport received an unexpected endpoint.")
        config = json.loads(control.read_text())
        if set(config) != {"mode"} or config["mode"] not in MODES:
            raise AssertionError("Invalid acceptance source control.")
        mode = config["mode"]
        with control.with_suffix(".calls").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"mode": mode, "pid": os.getpid()}) + "\n")
            stream.flush()
        if mode == "timeout":
            raise TimeoutError("Controlled transport timeout")
        if mode == "disconnect":
            raise URLError(ConnectionResetError("Controlled transport disconnection"))
        if mode in {"429", "503"}:
            raise HTTPError(request.full_url, int(mode), "Controlled HTTP error",
                            {"Retry-After": "600"}, None)
        if mode == "block":
            # The real systemd service must stop this child. Never a network wait.
            time.sleep(120)
            raise TimeoutError("Controlled blocking fixture expired")
        body = b"not-json" if mode == "malformed" else json.dumps(catalog()).encode()
        return Response(body, request.full_url)
    return open_response


def install(control):
    from xti.adapters.hibp_public_notices import HibpPublicNoticeSource
    from xti.interfaces import cli

    control = Path(control)
    if not control.is_file() or control.is_symlink():
        raise AssertionError("Acceptance control must be a real file.")
    cli.HibpPublicNoticeSource = lambda: HibpPublicNoticeSource(opener=controlled_opener(control))

    def deny(*args, **kwargs):
        raise AssertionError("Network connection forbidden in the operations acceptance fixture.")

    socket.create_connection = deny
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.getaddrinfo = deny


if __name__ == "__main__":
    install(os.environ["XTI_OPERATIONS_CONTROL"])
    from xti.interfaces.cli import main
    raise SystemExit(main(sys.argv[1:]))
