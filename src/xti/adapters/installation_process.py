"""Bounded owned subprocesses for recoverable installation transactions."""

from contextlib import contextmanager
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

from xti.adapters.tool_installation import ToolInstallationError

class SetupInterrupted(ToolInstallationError):
    pass


class ProcessCleanupError(ToolInstallationError):
    """Do not restore directories while an unconfirmed child may still write."""


@contextmanager
def interruption_handlers():
    def interrupted(number, _frame):
        raise SetupInterrupted(f"Kurulum sinyal nedeniyle kesildi ({number}).")

    previous = {}
    try:
        for number in (signal.SIGTERM, signal.SIGHUP):
            previous[number] = signal.signal(number, interrupted)
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def terminate_group(process, *, recovery_command):
    # A second Ctrl-C/TERM must not interrupt shutdown and let recovery race
    # with a child still writing into the canonical installation directory.
    previous = {number: signal.signal(number, signal.SIG_IGN)
                for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    try:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        # The leader can exit before its children. Kill the owned group too.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    except OSError as error:
        raise ProcessCleanupError(
            "Araç alt süreçleri güvenle durdurulamadı; otomatik geri dönüş yapılmadı. "
            f"Süreçler tamamlandıktan sonra {recovery_command} çalıştır."
        ) from error
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def run_command(arguments, *, cwd, lock_fd, timeout, recovery_command,
                environment=None, output_limit=1024 * 1024):
    with tempfile.TemporaryFile() as output:
        process = None
        try:
            process = subprocess.Popen(
                [str(item) for item in arguments], cwd=cwd, env=environment,
                stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                pass_fds=(lock_fd,), start_new_session=True,
            )
            deadline = time.monotonic() + timeout
            while True:
                if os.fstat(output.fileno()).st_size > output_limit:
                    raise ToolInstallationError("Araç yanıtı boyut sınırını aştı.")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(arguments, timeout)
                try:
                    process.wait(timeout=min(0.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            # Keep normal cleanup in this try: interruption between leader exit
            # and cleanup must not let a background descendant race with rollback.
            terminate_group(process, recovery_command=recovery_command)
        except ProcessCleanupError:
            raise
        except BaseException as error:
            if process is None:
                if isinstance(error, (SetupInterrupted, KeyboardInterrupt)):
                    # Popen may already have spawned the child before returning
                    # its handle. Its inherited lock must gate later recovery.
                    raise ProcessCleanupError(
                        "Araç başlatılırken kesinti oldu; alt süreç durumu doğrulanamadı. "
                        f"Süreçler tamamlandıktan sonra {recovery_command} çalıştır."
                    ) from error
            else:
                terminate_group(process, recovery_command=recovery_command)
            raise
        if process.returncode:
            raise ToolInstallationError(f"{Path(arguments[0]).name} komutu başarısız (çıkış {process.returncode}).")
        if output.tell() > output_limit:
            raise ToolInstallationError("Araç yanıtı boyut sınırını aştı.")
        output.seek(0)
        return output.read().decode("utf-8", errors="strict").strip()
