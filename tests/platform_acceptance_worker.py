"""Offline child-process harness for the platform acceptance script; never a live collector."""

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import resource
import sys
import time
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))


def private_json(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--gate", choices=("before-source", "after-receipt"))
    parser.add_argument("--marker")
    parser.add_argument("--source-log")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    started = time.perf_counter()
    with ExitStack() as stack:
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection",
                       "socket.getaddrinfo", "subprocess.Popen"):
            stack.enter_context(patch(target, side_effect=AssertionError("Acceptance is offline; network/tools forbidden")))
        from xti.interfaces.entrypoint import main as cli_main
        entrypoint_ready = time.perf_counter()
        if args.source_log:
            from xti.adapters.feodo_tracker import parse_feodo_response

            def fake_feed():
                descriptor = os.open(args.source_log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(descriptor, "w", encoding="ascii") as stream:
                    stream.write("fixture-feodo-request\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                return parse_feodo_response(json.dumps([{
                    "ip_address": "192.0.2.123", "port": 443, "status": "online", "hostname": None,
                    "as_number": 64500, "as_name": "Offline fixture", "country": "TR",
                    "first_seen": "2026-10-20 10:00:00", "last_online": "2026-11-15", "malware": "Fixture",
                }]).encode("utf-8"))

            stack.enter_context(patch("xti.adapters.feodo_tracker.FeodoTrackerSource.fetch", side_effect=fake_feed))
        if args.gate:
            if not args.marker or not args.source_log:
                parser.error("A gate requires marker and source log.")
            from xti.interfaces.platform_jobs import make_job_service

            def gated_service(context):
                service = make_job_service(context)
                original = service.runner

                class GatedRunner:
                    def prepare(self, name, revision):
                        return original.prepare(name, revision)

                    def run(self, payload, *, session_started):
                        if args.gate == "before-source":
                            self.pause(None)
                        result = original.run(payload, session_started=session_started)
                        if args.gate == "after-receipt":
                            if not any(step["receipt"] for step in result["steps"]):
                                raise AssertionError("Fixture run did not produce a durable source receipt")
                            self.pause(result)
                        return result

                    @staticmethod
                    def pause(result):
                        job = service.repository.active_job()
                        if job is None or job.status != "running":
                            raise AssertionError("Gate did not follow a durable claim")
                        private_json(args.marker, {"phase": args.gate, "job_id": job.id,
                            "collection_session_id": job.collection_session_id,
                            "source_receipt_count": 0 if result is None else sum(
                                step["receipt"] is not None for step in result["steps"])})
                        # Parent sends SIGTERM; a timeout fails instead of continuing to a source.
                        time.sleep(30)
                        raise AssertionError("Acceptance gate timed out")

                service.runner = GatedRunner()
                return service

            stack.enter_context(patch("xti.interfaces.platform_engine.make_platform_jobs", side_effect=gated_service))
        try:
            return cli_main(command)
        finally:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            private_json(args.metrics, {"wall_seconds": time.perf_counter() - started,
                "entrypoint_import_seconds": entrypoint_ready - started,
                "loaded_xti_modules": sum(name.startswith('xti.') for name in sys.modules),
                "cpu_seconds": usage.ru_utime + usage.ru_stime,
                "peak_rss_bytes": int(usage.ru_maxrss if sys.platform == "darwin" else usage.ru_maxrss * 1024)})


if __name__ == "__main__":
    raise SystemExit(main())
