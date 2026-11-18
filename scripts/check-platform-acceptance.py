#!/usr/bin/env python3
"""Bounded offline capacity and actual-process recovery acceptance; writes a new external JSON artifact."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from uuid import uuid4


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
HELPER = PROJECT / "tests" / "platform_acceptance_worker.py"
# Fixed before execution, never fitted to measurements. This is a bounded local
# fixture acceptance, not a production load test or a continuous-service claim.
LIMITS = {"records_per_company": [100, 1000], "companies": 2, "read_repeats": 3,
          "command_timeout_seconds": 15, "read_p95_seconds": 5,
          "child_peak_rss_bytes": 512 * 1024 * 1024, "disk_bytes": 128 * 1024 * 1024,
          "gate_timeout_seconds": 20, "total_seconds": 120}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def request(operation, parameters):
    return {"contract_version": 1, "request_id": "offline-acceptance", "operation": operation,
            "parameters": parameters}


def digest_files(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


class Acceptance:
    def __init__(self, base):
        self.base, self.root = base, base / "platform"
        self.deadline = time.monotonic() + LIMITS["total_seconds"]
        self.sequence, self.measurements = 0, []
        self.last_command = None
        self.contexts, self.organizations, self.jobs = {}, {}, {}

    def command(self, company, action="request", *, extra=(), gate=None, marker=None, source_log=None):
        self.sequence += 1
        metrics = self.base / f"metrics-{self.sequence}.json"
        args = [sys.executable, str(HELPER), "--metrics", str(metrics)]
        if gate:
            args += ["--gate", gate, "--marker", str(marker)]
        if source_log:
            args += ["--source-log", str(source_log)]
        args += ["--", "platform", action, "--root", str(self.root), "--company", company, *extra]
        return args, metrics

    def call(self, company, payload=None, *, action="request", extra=(), expected_error=None,
             source_log=None, measure=None):
        args, metrics = self.command(company, action, extra=extra, source_log=source_log)
        started = time.perf_counter()
        remaining = self.deadline - time.monotonic()
        self.last_command = {"sequence": self.sequence, "company": company, "action": action,
            "operation": payload.get("operation") if payload else None,
            "remaining_seconds": remaining, "completed": False}
        require(remaining > 0, "Total acceptance duration threshold exceeded")
        process = subprocess.run(args, input=json.dumps(payload) if payload else "", text=True,
                                 capture_output=True, cwd=PROJECT,
                                 timeout=min(LIMITS["command_timeout_seconds"], remaining))
        elapsed = time.perf_counter() - started
        require(not process.stderr, "Child command wrote unexpected stderr")
        response = json.loads(process.stdout)
        require(response["protocol"] == "xti-platform", "Wrong child protocol")
        if expected_error:
            require(process.returncode != 0 and response["error"]["code"] == expected_error,
                    "Child did not fail with expected safe error")
        else:
            require(process.returncode == 0 and response["status"] == "complete", "Child command did not complete")
            require(response["scope"]["company_id"] == company, "Child response company mismatch")
        sample = json.loads(metrics.read_text())
        require(sample["peak_rss_bytes"] <= LIMITS["child_peak_rss_bytes"], "Child RSS threshold exceeded")
        if measure:
            self.measurements.append({**sample, "process_wall_seconds": elapsed,
                                      "company": company, **measure})
        self.last_command["completed"] = True
        return response["data"]

    def seed(self):
        from xti.adapters.company_workspaces import resolve_company_workspace
        from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
        from xti.adapters.sqlite_mentions import SQLiteMentionRepository
        from xti.adapters.sqlite_mention_targets import SQLiteMentionTargetRepository
        from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
        from xti.domain.collection_profiles import CollectionProfileDefinition
        from xti.domain.mentions import MentionHit, MentionRequest, MentionResponse, build_query
        now = datetime.now(timezone.utc).isoformat()
        for company in ("alpha", "beta"):
            self.call(company, action="provision")
            context = self.contexts[company] = resolve_company_workspace(self.root, company)
            organization = SQLiteOrganizationRepository(context.database).add(name_key="company", display_name="Company",
                reason="Offline fixture", recorded_at=now).organization
            self.organizations[company] = organization.id
            target = SQLiteMentionTargetRepository(context.database).resolve("organization", organization.id)
            mention_request = MentionRequest(target, "news", 10)
            hit = MentionHit("https://publisher.example/" + company, "Company fixture " + company,
                             company + " fixture excerpt", "2026-11-16", .8)
            SQLiteMentionRepository(context.database).apply(mention_request,
                MentionResponse(build_query(target), None, (hit,), 1), started_at=now, finished_at=now)
            self.grow(company, 0, 100)
            SQLiteCollectionProfileRepository(context.database).save("Fixture",
                CollectionProfileDefinition("host0." + company + ".example", task_ids=("ioc-feodo",)), recorded_at=now)
            self.jobs[company] = self.submit(company, "capacity-fixture")["job_id"]

    def grow(self, company, previous, count):
        from xti.adapters.sqlite import SQLiteAssetRepository
        now = datetime.now(timezone.utc).isoformat()
        with SQLiteAssetRepository(self.contexts[company].database)._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany("INSERT INTO assets (id, value, created_at) VALUES (?, ?, ?)",
                [(str(uuid4()), f"host{index}.{company}.example", now) for index in range(previous, count)])
            connection.commit()

    def submit(self, company, key):
        return self.call(company, request("jobs.submit", {"idempotency_key": key,
            "profile_name": "Fixture", "profile_revision": 1,
            "expected_workspace_id": self.contexts[company].workspace_id}))

    def capacity(self):
        previous = 100
        for count in LIMITS["records_per_company"]:
            if count > previous:
                for company in self.contexts:
                    self.grow(company, previous, count)
            before = digest_files(self.root)
            for company in self.contexts:
                for repeat in range(LIMITS["read_repeats"]):
                    for operation, parameters in (
                        ("search", {"query": "example", "kinds": ["domain"], "limit": 50}),
                        ("organization.content", {"organization_id": self.organizations[company]}),
                        ("jobs.status", {"job_id": self.jobs[company]}),
                    ):
                        data = self.call(company, request(operation, parameters), measure={
                            "operation": operation, "records": count, "repeat": repeat + 1})
                        if operation == "search":
                            require(data["total_match_count"] == count, "Search fixture total differs")
                            require(all(company + ".example" in row["display_value"] for row in data["results"]),
                                    "Search crossed company scope")
                        elif operation == "organization.content":
                            items = data["sections"]["content"]["items"]
                            require(len(items) == 1 and items[0]["available_excerpt"] == company + " fixture excerpt",
                                    "Content crossed company scope")
                        else:
                            require(data["job_id"] == self.jobs[company] and data["status"] == "queued",
                                    "Job status crossed company scope")
            require(digest_files(self.root) == before, "Read-only capacity requests changed stored bytes")
            previous = count
        self.call("alpha", request("jobs.status", {"job_id": self.jobs["beta"]}), expected_error="not_found")
        # Remove the capacity jobs from runnable queue before controlled crash cases.
        for company, job_id in self.jobs.items():
            self.call(company, request("jobs.cancel", {"job_id": job_id}))

    def receipt_counts(self, company):
        database = self.contexts[company].database
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
            return {"source_runs": connection.execute("SELECT COUNT(*) FROM cti_feed_runs").fetchone()[0],
                    "receipts": connection.execute("SELECT COUNT(*) FROM collection_step_receipts").fetchone()[0]}

    def crash(self, gate):
        key = "crash-" + gate
        job = self.submit("alpha", key)
        marker, source_log = self.base / (gate + ".marker"), self.base / (gate + ".calls")
        args, _metrics = self.command("alpha", "worker", extra=("--job-id", job["job_id"]),
                                      gate=gate, marker=marker, source_log=source_log)
        baseline = self.receipt_counts("alpha")
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, cwd=PROJECT)
        try:
            deadline = min(self.deadline, time.monotonic() + LIMITS["gate_timeout_seconds"])
            while not marker.exists():
                require(process.poll() is None, "Gated worker exited before reaching durable boundary")
                require(time.monotonic() < deadline, "Gated worker exceeded wait threshold")
                time.sleep(.02)
            observed = json.loads(marker.read_text())
            require(observed["job_id"] == job["job_id"] and observed["phase"] == gate, "Worker gate identity mismatch")
            self.call("alpha", action="worker", extra=("--job-id", job["job_id"]),
                      expected_error="busy", source_log=source_log)
            self.call("alpha", action="recover", expected_error="busy")
            # B completes a real fixture collection while A's process still owns
            # its worker lock, proving the lock is scoped rather than global.
            other = self.submit("beta", "independent-" + gate)
            other_log = self.base / (gate + ".beta-calls")
            other_result = self.call("beta", action="worker", extra=("--job-id", other["job_id"]),
                                     source_log=other_log)
            require(other_result["job_id"] == other["job_id"] and other_result["status"] == "complete",
                    "Independent company worker could not complete while first company was locked")
            require(len(other_log.read_text().splitlines()) == 1, "Independent company fixture call count differs")
            process.terminate()
            _stdout, stderr = process.communicate(timeout=5)
            require(process.returncode == -signal.SIGTERM and not stderr, "Worker did not terminate at gated boundary")
            self.call("alpha", action="worker", extra=("--job-id", job["job_id"]),
                      expected_error="busy", source_log=source_log)
            recovered = self.call("alpha", action="recover")
            require(len(recovered) == 1 and recovered[0]["job_id"] == job["job_id"]
                    and recovered[0]["status"] == "interrupted", "Explicit recovery did not preserve uncertain job")
            replay = self.submit("alpha", key)
            require(replay["job_id"] == job["job_id"] and replay["status"] == "interrupted", "Replay created a new job")
            require(self.call("alpha", action="worker", extra=("--job-id", job["job_id"]), source_log=source_log) is None,
                    "Interrupted job was automatically replayed")
            calls = len(source_log.read_text().splitlines()) if source_log.exists() else 0
            expected_calls = int(gate == "after-receipt")
            require(calls == expected_calls, "Source call count changed after uncertain recovery/replay")
            after = self.receipt_counts("alpha")
            require(after == {name: value + expected_calls for name, value in baseline.items()},
                    "Durable source evidence was lost or duplicated")
            return {"gate": gate, "terminated_by": "SIGTERM", "source_calls": calls,
                    "durable_receipts_preserved": after["receipts"] - baseline["receipts"],
                    "second_worker": "busy", "concurrent_recovery": "busy",
                    "other_company_worker": "completed_one_fixture_collection",
                    "other_company_source_calls": 1, "replay": "same_interrupted_job"}
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

    def integrity(self):
        from xti.adapters.sqlite import SQLiteAssetRepository
        from xti.interfaces.platform_jobs import validate_jobs
        for context in self.contexts.values():
            with SQLiteAssetRepository(context.database)._connection(readonly=True) as connection:
                SQLiteAssetRepository._check_integrity(connection)
            validate_jobs(context)
        disk = sum(path.stat().st_size for path in self.root.rglob("*") if path.is_file())
        require(disk <= LIMITS["disk_bytes"], "Fixture disk threshold exceeded")
        return {"companies": len(self.contexts), "sqlite_integrity": "passed", "disk_bytes": disk}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New JSON file outside the repository.")
    args = parser.parse_args()
    output = Path(args.output).expanduser().absolute()
    require(output.parent.is_dir() and not output.exists() and not output.is_symlink(), "Output requires a new file in an existing directory")
    require(not output.resolve().is_relative_to(PROJECT), "Acceptance artifacts must stay outside source control")
    started = time.perf_counter()
    report = {"kind": "xti-platform-offline-acceptance", "version": 1,
              "started_at": datetime.now(timezone.utc).isoformat(), "thresholds": LIMITS,
              "environment": {"os": platform.platform(), "machine": platform.machine(),
                  "python": sys.version, "sqlite": sqlite3.sqlite_version, "cpu_count": os.cpu_count()},
              "scope": "Two disposable companies; offline fixtures and real local processes; no live-source or 24/7 claim."}
    code, acceptance = 1, None
    try:
        with tempfile.TemporaryDirectory(prefix="xti-platform-acceptance-") as temporary:
            acceptance = Acceptance(Path(temporary).resolve())
            acceptance.seed()
            acceptance.capacity()
            report["crash_cases"] = []
            for gate in ("before-source", "after-receipt"):
                report["crash_cases"].append(acceptance.crash(gate))
            report["integrity"] = acceptance.integrity()
            report["measurements"] = acceptance.measurements
            values = sorted(item["process_wall_seconds"] for item in acceptance.measurements)
            p95 = values[math.ceil(.95 * len(values)) - 1]
            require(p95 <= LIMITS["read_p95_seconds"], "Read latency p95 threshold exceeded")
            report["summary"] = {"read_requests": len(values), "p95_process_wall_seconds": p95,
                "max_process_wall_seconds": max(values), "max_child_peak_rss_bytes": max(
                    item["peak_rss_bytes"] for item in acceptance.measurements)}
        require(time.perf_counter() - started <= LIMITS["total_seconds"], "Total acceptance duration threshold exceeded")
        report["status"], code = "passed", 0
    except Exception as error:
        report["status"] = "failed"
        # No exception message from a source or subprocess is copied to artifacts.
        report["failure_type"] = type(error).__name__
        report["failure"] = str(error) if isinstance(error, AssertionError) else "Acceptance execution failed; inspect the local fixture."
        if acceptance is not None:
            # Preserve completed synthetic measurements even when the total deadline
            # expires; do not raise limits or publish subprocess/source error bodies.
            report["measurements"] = acceptance.measurements
            report["last_command"] = acceptance.last_command
    report["elapsed_seconds"] = time.perf_counter() - started
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"status": report["status"], "elapsed_seconds": report["elapsed_seconds"]}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
