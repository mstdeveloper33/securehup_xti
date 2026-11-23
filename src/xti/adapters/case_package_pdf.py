"""Bounded process adapter for the optional offline case-package PDF."""

import base64
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from xti.domain.assets import ValidationError


def render_pdf(html: bytes, *, timeout: int = 30, browser_path: Path | None = None) -> bytes:
    root = Path(__file__).resolve().parents[3]
    browser_path = browser_path or root / ".tools" / "playwright" / "1.65.2"
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
        "PYTHONPATH": str(root / "src"), "PYTHONNOUSERSITE": "1",
        "PYTHONPYCACHEPREFIX": os.environ.get("PYTHONPYCACHEPREFIX", "/tmp/xti-case-pdf-pycache"),
        "PLAYWRIGHT_BROWSERS_PATH": str(browser_path),
    }
    if os.name != "posix":
        raise ValidationError("Çevrimdışı PDF yalnız desteklenen POSIX sunucuda üretilebilir.")
    process = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "xti.adapters.case_package_pdf_worker"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            start_new_session=True, env=env,
        )
        output, _ = process.communicate(
            json.dumps({"html": html.decode("utf-8")}, ensure_ascii=True).encode("ascii"),
            timeout=max(5, min(timeout, 60)),
        )
        if process.returncode != 0 or len(output) > 12 * 1024 * 1024:
            raise ValidationError(
                "Çevrimdışı PDF üretilemedi; ./setup ile sabit Playwright/Chromium aracını doğrulayın."
            )
        result = json.loads(output)
        if result.get("status") != "complete" or result.get("network_requests") != 0:
            raise ValueError("renderer state")
        payload = base64.b64decode(result["pdf"], validate=True)
        if not payload.startswith(b"%PDF-") or len(payload) > 8 * 1024 * 1024:
            raise ValueError("pdf response")
        return payload
    except subprocess.TimeoutExpired as error:
        raise ValidationError("Çevrimdışı PDF üretimi süre sınırına ulaştı.") from error
    except ValidationError:
        raise
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise ValidationError("Çevrimdışı PDF üreticisi doğrulanamadı.") from error
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
