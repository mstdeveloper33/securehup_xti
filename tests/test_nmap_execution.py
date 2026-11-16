"""Managed Nmap acceptance: no real network; actual CLI, SQLite and subprocess boundaries."""

from contextlib import closing, redirect_stdout, redirect_stderr
from dataclasses import replace
from datetime import datetime, timezone
from io import StringIO
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import unittest

from xti.adapters.managed_nmap import ManagedNmapRuntime, NmapWorkerLock, build_command, parse_xml
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.nmap_execution import empty_result, validate_result
from xti.domain.nmap_management import canonical_managed_plan_json, parse_managed_plan_json
from xti.domain.nmap_options import NmapExecutionOptions, normalize_options
from xti.interfaces.cli import main
from xti.interfaces.nmap_execution import make_nmap_service
from xti.ports.jobs import WorkerBusyError


def xml_result(address, ports="80,443", protocol="tcp", body=None):
    body = body if body is not None else '<port protocol="tcp" portid="443"><state state="open" reason="syn-ack"/></port><extraports state="closed" count="1"/>'
    return (f'<?xml version="1.0"?><!DOCTYPE nmaprun><nmaprun scanner="nmap" version="7.95">'
            f'<scaninfo protocol="{protocol}" services="{ports}"/><host><status state="up"/>'
            f'<address addr="{address}" addrtype="ipv4"/><ports>{body}</ports></host>'
            '<runstats><finished exit="success"/></runstats></nmaprun>').encode()


class FakeRunner:
    def __init__(self):
        self.addresses = []
        self.callback = None

    def readiness(self, plan):
        return {"version": "7.95"}

    def run(self, plan, address, **kwargs):
        self.addresses.append(address)
        if self.callback:
            self.callback(plan, address, kwargs)
        return parse_xml(xml_result(address), plan, address, "7.95")


class ManagedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.database = self.directory / "data" / "xti.db"
        self.cli("init")
        self.cli("assets", "add", "example.com")
        self.cli("surface", "approve", "example.com", "--reason", "Kontrol yetkisi")
        self.cli("surface", "nmap", "targets", "save", "example.com", "network",
                 "--network", "8.8.8.0/30", "--reason", "Sentetik test kapsamı; ağ yok")
        self.service = make_nmap_service(self.database)
        self.runner = FakeRunner()
        self.service.runner = self.runner
        self.plan = self.service.management.create_plan("example.com", "network",
            profile="custom", ports="80,443", options=NmapExecutionOptions())

    def cli(self, *args):
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(["--data-dir", str(self.database.parent), "--json", *args])
        self.assertEqual(code, 0, errors.getvalue())
        return json.loads(output.getvalue())["data"]

    def job(self, key="one"):
        return self.service.submit("example.com", self.plan.plan.id, key)

    def test_queue_worker_results_and_idempotency_survive_reopen(self):
        work = self.job()
        self.assertEqual(self.runner.addresses, [])
        self.assertEqual(self.job().id, work.id)
        done = self.service.work("example.com", work.id)
        self.assertEqual(done.status, "complete")
        self.assertEqual(len(done.results), 4)
        self.assertEqual(self.job().id, work.id)
        self.assertEqual(make_nmap_service(self.database).show("example.com", work.id), done)
        with self.assertRaises(ValidationError):
            self.service.work("example.com", work.id)
        self.assertEqual(len(self.runner.addresses), 4)
        page = self.cli("surface", "nmap", "jobs", "show", "example.com", work.id, "--limit", "2")
        self.assertEqual((page["total_results"], page["next_offset"]), (4, 2))

    def test_cancel_queued_and_running_is_durable_and_stops_next_target(self):
        queued = self.job("queued")
        self.assertEqual(self.service.cancel("example.com", queued.id).status, "cancelled")
        with self.assertRaises(ValidationError):
            self.service.work("example.com", queued.id)
        work = self.job("active")
        def cancel(_plan, _address, options):
            self.service.cancel("example.com", work.id)
            self.assertTrue(options["should_stop"]())
        self.runner.callback = cancel
        result = self.service.work("example.com", work.id)
        self.assertEqual((result.status, result.started_count), ("cancelled", 1))
        self.assertEqual(self.service.cancel("example.com", work.id), result)

    def test_interruption_preserves_unknown_attempt_and_resume_skips_it(self):
        work = self.job()
        def fail(*_args):
            raise KeyboardInterrupt
        self.runner.callback = fail
        with self.assertRaises(KeyboardInterrupt):
            self.service.work("example.com", work.id)
        interrupted = self.service.show("example.com", work.id)
        self.assertEqual((interrupted.status, interrupted.results[0]["status"]), ("interrupted", "interrupted"))
        self.service.resume("example.com", work.id)
        self.runner.callback = None
        done = self.service.work("example.com", work.id)
        self.assertEqual(done.status, "partial")
        self.assertEqual(self.runner.addresses, ["8.8.8.0", "8.8.8.1", "8.8.8.2", "8.8.8.3"])

    def test_explicit_recovery_needs_free_worker_lock_and_never_runs_network(self):
        work = self.job()
        repository = self.service.repository
        now = datetime.now(timezone.utc).isoformat()
        work = repository.append(work, "claimed", {}, now, token="11111111-1111-4111-8111-111111111111")
        repository.append(work, "target_started", {"index": 0, "address": "8.8.8.0"}, now, token=work.token)
        with NmapWorkerLock(self.database).acquire():
            with self.assertRaises(WorkerBusyError):
                self.service.recover("example.com", work.id)
        recovered = self.service.recover("example.com", work.id)
        self.assertEqual(recovered.results[0]["status"], "interrupted")
        self.assertEqual(self.runner.addresses, [])

    def test_changed_or_revoked_scope_blocks_execution_before_readiness(self):
        work = self.job()
        self.service.management.revoke_target("example.com", "network", "Yetki geri alındı")
        with patch.object(self.runner, "readiness") as readiness:
            with self.assertRaises(ValidationError):
                self.service.work("example.com", work.id)
        readiness.assert_not_called()

    def test_restore_keeps_evidence_but_cannot_replay_old_queued_jobs(self):
        work = self.job()
        destination = self.directory / "restored.db"
        SQLiteAssetRepository(self.database).backup(destination)
        restored = make_nmap_service(destination)
        restored.runner = self.runner
        with self.assertRaisesRegex(ValidationError, "yedekten"):
            restored.work("example.com", work.id)
        self.assertEqual(restored.show("example.com", work.id).status, "queued")
        self.assertEqual(self.runner.addresses, [])

    def test_deleting_event_tail_or_changing_hash_fails_closed(self):
        work = self.job()
        self.service.cancel("example.com", work.id)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DELETE FROM surface_nmap_job_events WHERE job_id=?", (work.id,))
            connection.commit()
        before = self.database.read_bytes()
        with self.assertRaises(StorageError):
            self.service.show("example.com", work.id)
        self.assertEqual(self.database.read_bytes(), before)

    def test_plan_and_request_conflict_does_not_create_new_job(self):
        self.job()
        other = self.service.management.create_plan("example.com", "network", profile="safe")
        with self.assertRaises(ValidationError):
            self.service.submit("example.com", other.plan.id, "one")
        self.assertEqual(len(self.service.list("example.com")), 1)

    def test_options_are_versioned_and_old_plan_bytes_are_preserved(self):
        old = replace(self.plan.plan.definition, options=None)
        old_json = canonical_managed_plan_json(old)
        self.assertNotIn('"options"', old_json)
        self.assertIn('"version":1', old_json)
        self.assertEqual(canonical_managed_plan_json(parse_managed_plan_json(old_json)), old_json)
        new = replace(old, scan_type="tcp_syn", options=NmapExecutionOptions(
            service_detection=True, os_detection=True, scripts=("banner", "ssl-cert")))
        new_json = canonical_managed_plan_json(new)
        self.assertEqual(parse_managed_plan_json(new_json), new)
        command = build_command("/usr/bin/nmap", replace(self.plan.plan, definition=new), "8.8.8.0")
        for option in ("-sS", "-sV", "-O", "--script", "--script-timeout", "--max-rate"):
            self.assertIn(option, command)
        self.assertNotIn("--unprivileged", command)
        self.assertEqual(command[command.index("--max-hostgroup") + 1], "1")

    def test_raw_categories_paths_duplicates_and_invalid_option_types_are_rejected(self):
        for script in ("vuln", "safe", "brute", "exploit", "all", "../scan.nse", "banner or all", "banner,ssh-hostkey"):
            with self.subTest(script=script), self.assertRaises(ValidationError):
                normalize_options(NmapExecutionOptions(scripts=(script,)))
        with self.assertRaises(ValidationError):
            normalize_options(NmapExecutionOptions(service_detection=1))
        with self.assertRaises(ValidationError):
            normalize_options(NmapExecutionOptions(scripts=("banner", "banner")))
        with self.assertRaises(ValidationError):
            self.service.management.create_plan("example.com", "network", scan_type="udp", options=NmapExecutionOptions())

    def test_udp_unknown_is_not_open_and_service_os_scripts_are_evidence(self):
        definition = replace(self.plan.plan.definition, scan_type="udp")
        plan = replace(self.plan.plan, definition=definition)
        result = parse_xml(xml_result("8.8.8.0", protocol="udp", body='<extraports state="open|filtered" count="2"/>'), plan, "8.8.8.0", "7.95")
        self.assertEqual(result["port_states"], {"open|filtered": 2})
        rich = replace(self.plan.plan, definition=replace(self.plan.plan.definition,
            options=NmapExecutionOptions(service_detection=True, os_detection=True, scripts=("banner", "ssl-cert"))))
        content = xml_result("8.8.8.0", body='<port protocol="tcp" portid="443"><state state="open"/>'
            '<service name="https" product="Example" version="1.0" method="probed" conf="10"/>'
            '<script id="banner" output="Example&#10;service"/></port><extraports state="closed" count="1"/>')
        content = content.replace(b'</host>', b'<os><osmatch name="Linux candidate" accuracy="92"/></os></host>')
        result = parse_xml(content, rich, "8.8.8.0", "7.95")
        self.assertEqual(result["ports"][0]["service"]["version"], "1.0")
        self.assertEqual(result["scripts_without_output"], ["ssl-cert"])
        self.assertEqual(result["os_matches"][0]["accuracy"], 92)

    def test_bad_xml_scope_version_protocol_entities_and_wrong_result_are_rejected(self):
        valid = xml_result("8.8.8.0")
        for content in (valid.replace(b'8.8.8.0', b'8.8.8.1'), valid.replace(b'7.95', b'7.94'),
                        valid.replace(b'protocol="tcp"', b'protocol="udp"'),
                        valid.replace(b'<!DOCTYPE nmaprun>', b'<!DOCTYPE nmaprun [<!ENTITY a SYSTEM "file:///etc/passwd">]>'),
                        valid.replace(b'services="80,443"', b'services="1-65535"'),
                        valid.decode().encode("utf-16-le")):
            with self.subTest(content=content), self.assertRaises(ValidationError):
                parse_xml(content, self.plan.plan, "8.8.8.0", "7.95")
        with self.assertRaises(ValidationError):
            validate_result(empty_result("8.8.8.1", "failed", ""), self.plan.plan, "8.8.8.0")

    def test_privileged_plan_never_silently_falls_back_or_runs_sudo(self):
        plan = replace(self.plan.plan, definition=replace(self.plan.plan.definition, scan_type="tcp_syn"))
        runtime = ManagedNmapRuntime()
        with patch.object(runtime.runtime, "readiness", return_value=("7.95", "/usr/bin/nmap")), patch("os.geteuid", return_value=501):
            with self.assertRaisesRegex(ValidationError, "yetkili çalıştırıcı"):
                runtime.readiness(plan)

    def test_missing_tool_leaves_job_queued_and_target_unattempted(self):
        work = self.job()
        with patch.object(self.runner, "readiness", side_effect=ValidationError("Nmap kurulu değil")):
            with self.assertRaises(ValidationError):
                self.service.work("example.com", work.id)
        self.assertEqual(self.service.show("example.com", work.id).status, "queued")
        self.assertEqual(self.runner.addresses, [])

    def test_event_write_failure_never_sends_first_packet(self):
        work = self.job()
        original = self.service.repository.append
        def fail(work, kind, *args, **kwargs):
            if kind == "target_started":
                raise StorageError("simulated disk failure")
            return original(work, kind, *args, **kwargs)
        with patch.object(self.service.repository, "append", side_effect=fail):
            with self.assertRaises(StorageError):
                self.service.work("example.com", work.id)
        self.assertEqual(self.runner.addresses, [])
        self.assertEqual(self.service.show("example.com", work.id).status, "interrupted")

    def test_job_time_budget_preserves_never_started_targets_for_explicit_resume(self):
        work = self.job()
        self.service.monotonic = iter([0, 4000]).__next__
        done = self.service.work("example.com", work.id)
        self.assertEqual((done.status, done.started_count), ("interrupted", 0))
        self.assertEqual(self.runner.addresses, [])

    def test_request_plan_rebinding_fails_even_before_first_event(self):
        work = self.job()
        other = self.service.management.create_plan("example.com", "network", profile="safe")
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE surface_nmap_jobs SET plan_id=? WHERE id=?", (other.plan.id, work.id))
            connection.commit()
        with self.assertRaises(StorageError):
            self.service.show("example.com", work.id)

    def test_nse_smb_check_requires_the_exact_selected_service_port(self):
        with self.assertRaises(ValidationError):
            self.service.management.create_plan("example.com", "network", profile="custom", ports="443",
                options=NmapExecutionOptions(scripts=("smb-vuln-ms17-010",)))
        plan = self.service.management.create_plan("example.com", "network", profile="custom", ports="445",
                options=NmapExecutionOptions(scripts=("smb-vuln-ms17-010",))).plan
        command = build_command("/usr/bin/nmap", plan, "8.8.8.0")
        self.assertEqual(command[command.index("--script-args") + 1], "smbport=445")

    def test_fake_subprocess_can_finish_with_real_nmap_style_xml(self):
        executable = self.directory / "nmap-success-fixture"
        xml = xml_result("8.8.8.0")
        executable.write_text(f'#!{sys.executable}\nimport sys\n'
            'if "--version" in sys.argv:\n print("Nmap version 7.95");sys.exit(0)\n'
            f'sys.stdout.buffer.write({xml!r})\n', encoding="utf-8")
        executable.chmod(0o700)
        runtime = ManagedNmapRuntime(str(executable))
        with NmapWorkerLock(self.database).acquire() as descriptor:
            result = runtime.run(self.plan.plan, "8.8.8.0", should_stop=lambda: False,
                                 lock_fd=descriptor, duration_seconds=5)
        self.assertEqual(result["status"], "complete")

    def test_inherited_worker_lock_blocks_recovery_while_child_lives(self):
        with NmapWorkerLock(self.database).acquire() as descriptor:
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"],
                                     pass_fds=(descriptor,))
        try:
            with self.assertRaises(WorkerBusyError):
                with NmapWorkerLock(self.database).acquire():
                    pass
        finally:
            child.kill()
            child.wait(timeout=5)
        with NmapWorkerLock(self.database).acquire():
            pass

    def test_empty_success_without_port_evidence_is_rejected(self):
        result = empty_result("8.8.8.0", "complete", "")
        result.update(tool_version="7.95", xml_sha256="a" * 64)
        with self.assertRaises(ValidationError):
            validate_result(result, self.plan.plan, "8.8.8.0")

    def test_large_plan_has_preallocated_bounded_partial_evidence(self):
        from xti.domain.nmap_execution import encoded, result_byte_limit
        self.service.management.save_target("example.com", "large", "8.8.0.0/20", (), "Sentetik kapsam")
        plan = self.service.management.create_plan("example.com", "large", profile="custom", ports="443",
            options=NmapExecutionOptions(scripts=("banner",)), max_targets=4096,
            confirm_range_scan=True).plan
        body = ('<port protocol="tcp" portid="443"><state state="open"/>'
                '<script id="banner" output="' + "A" * 20000 + '"/></port>')
        result = parse_xml(xml_result("8.8.0.0", ports="443", body=body), plan, "8.8.0.0", "7.95")
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["truncated"])
        self.assertLessEqual(len(encoded(result)), result_byte_limit(plan))
        self.assertEqual(result["port_states"], {"open": 1})

    def test_timeout_and_output_flood_kill_only_owned_subprocess(self):
        executable = self.directory / "nmap-budget-fixture"
        executable.write_text(f'#!{sys.executable}\nimport sys,time\n'
            'if "--version" in sys.argv:\n print("Nmap version 7.95");sys.exit(0)\n'
            'print("A" * 4096, flush=True)\ntime.sleep(10)\n', encoding="utf-8")
        executable.chmod(0o700)
        runtime = ManagedNmapRuntime(str(executable))
        with NmapWorkerLock(self.database).acquire() as descriptor:
            start = time.monotonic()
            result = runtime.run(self.plan.plan, "8.8.8.0", should_stop=lambda: False,
                                 lock_fd=descriptor, duration_seconds=0.1)
            self.assertEqual(result["status"], "timeout")
            with patch("xti.adapters.managed_nmap.NMAP_MAX_XML_BYTES", 512):
                result = runtime.run(self.plan.plan, "8.8.8.0", should_stop=lambda: False,
                                     lock_fd=descriptor, duration_seconds=5)
            self.assertEqual(result["status"], "failed")
            self.assertLess(time.monotonic() - start, 5)

    def test_migration_71_preserves_plans_and_creates_empty_job_history(self):
        before = canonical_managed_plan_json(self.plan.plan.definition)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("PRAGMA user_version=71")
            connection.commit()
        result = SQLiteAssetRepository(self.database).migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (71, 72))
        self.assertTrue(Path(result["backup"]).is_file())
        self.assertEqual(canonical_managed_plan_json(self.service.management.show_plan("example.com", self.plan.plan.id).definition), before)
        self.assertEqual(self.service.list("example.com"), ())

    def test_child_process_has_sanitized_environment_and_cancellable_output(self):
        executable = self.directory / "nmap-fixture"
        executable.write_text(f'#!{sys.executable}\nimport os,sys,time\n'
            'if "--version" in sys.argv:\n print("Nmap version 7.95");sys.exit(0)\n'
            'assert "NMAPDIR" not in os.environ\n'
            'assert os.getcwd() == os.environ["HOME"]\n'
            'time.sleep(10)\n', encoding="utf-8")
        executable.chmod(0o700)
        runtime = ManagedNmapRuntime(str(executable))
        calls = []
        def cancel():
            calls.append(True)
            return len(calls) >= 3
        with NmapWorkerLock(self.database).acquire() as descriptor, patch.dict(os.environ, {"NMAPDIR": "/untrusted"}):
            start = time.monotonic()
            result = runtime.run(self.plan.plan, "8.8.8.0", should_stop=cancel,
                                 lock_fd=descriptor, duration_seconds=5)
        self.assertEqual(result["status"], "cancelled")
        self.assertLess(time.monotonic() - start, 5)

    def test_cancel_remains_effective_after_child_closes_both_output_streams(self):
        executable = self.directory / "nmap-closed-output-fixture"
        ready_file = self.directory / "output-closed"
        executable.write_text(f'#!{sys.executable}\nimport os,sys,time\n'
            'if "--version" in sys.argv:\n print("Nmap version 7.95");sys.exit(0)\n'
            'os.close(1)\nos.close(2)\n'
            f'with open({str(ready_file)!r}, "w") as output: output.write("ready")\n'
            'time.sleep(10)\n', encoding="utf-8")
        executable.chmod(0o700)
        runtime = ManagedNmapRuntime(str(executable))
        with NmapWorkerLock(self.database).acquire() as descriptor:
            result = runtime.run(self.plan.plan, "8.8.8.0", should_stop=ready_file.exists,
                                 lock_fd=descriptor, duration_seconds=3)
        self.assertTrue(ready_file.exists())
        self.assertEqual(result["status"], "cancelled")


class PlatformNmapTests(unittest.TestCase):
    def setUp(self):
        from xti.adapters.company_workspaces import resolve_company_workspace
        from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
        from xti.application.surface import SurfaceService
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "companies"
        self.contexts = {}
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("No network")))
        self.enterContext(patch("subprocess.Popen", side_effect=AssertionError("No process on request")))
        for company in ("alpha", "beta"):
            self.assertEqual(self.invoke(company, action="provision")[0], 0)
            context = self.contexts[company] = resolve_company_workspace(self.root, company)
            assets = SQLiteAssetRepository(context.database)
            assets.add("example.com")
            SurfaceService(assets, SQLiteSurfaceRepository(context.database)).approve("example.com", "Sentetik yetki")
            service = make_nmap_service(context.database)
            service.management.save_target("example.com", "network", "8.8.8.0/30", (), "Sentetik kapsam")

    def invoke(self, company, operation=None, parameters=None, *, action="request", extra=()):
        request = {"contract_version": 1, "request_id": "example:1", "operation": operation,
                   "parameters": parameters or {}}
        out, err = StringIO(), StringIO()
        with patch("sys.stdin", StringIO(json.dumps(request))), redirect_stdout(out), redirect_stderr(err):
            code = main(["platform", action, "--root", str(self.root), "--company", company, *extra])
        self.assertEqual(err.getvalue(), "")
        return code, json.loads(out.getvalue())

    def plan(self, company):
        code, response = self.invoke(company, "nmap.plans.create", {"domain": "example.com", "target_name": "network",
            "expected_workspace_id": self.contexts[company].workspace_id,
            "profile": "custom", "ports": "80,443", "options": {"service_detection": True, "scripts": ["ssl-cert"]}})
        self.assertEqual(code, 0, response)
        return response["data"]["plan"]["id"]

    def test_options_planning_queue_cancel_and_read_are_company_scoped_and_offline(self):
        jobs = {}
        for company in ("alpha", "beta"):
            plan_id = self.plan(company)
            code, response = self.invoke(company, "nmap.jobs.submit", {"domain": "example.com", "plan_id": plan_id,
                "key": "same-key", "expected_workspace_id": self.contexts[company].workspace_id})
            self.assertEqual(code, 0, response)
            jobs[company] = response["data"]["job"]["id"]
        self.assertNotEqual(jobs["alpha"], jobs["beta"])
        for operation in ("nmap.jobs.status", "nmap.jobs.result", "nmap.jobs.cancel"):
            code, _response = self.invoke("beta", operation, {"domain": "example.com", "job_id": jobs["alpha"]})
            self.assertNotEqual(code, 0)
        code, response = self.invoke("alpha", "nmap.jobs.cancel", {"domain": "example.com", "job_id": jobs["alpha"]})
        self.assertEqual((code, response["data"]["job"]["status"]), (0, "cancelled"))
        code, response = self.invoke("beta", "nmap.jobs.status", {"domain": "example.com", "job_id": jobs["beta"]})
        self.assertEqual((code, response["data"]["job"]["status"]), (0, "queued"))

    def test_foreign_workspace_raw_command_and_unknown_script_rejected(self):
        plan_id = self.plan("alpha")
        code, response = self.invoke("alpha", "nmap.jobs.submit", {"domain": "example.com", "plan_id": plan_id,
            "key": "same-key", "expected_workspace_id": self.contexts["beta"].workspace_id})
        self.assertEqual(response["error"]["code"], "scope_mismatch")
        for options in ({"raw_arguments": "--script=all"}, {"scripts": ["exploit"]}):
            code, response = self.invoke("alpha", "nmap.plans.create", {"domain": "example.com", "target_name": "network",
                "expected_workspace_id": self.contexts["alpha"].workspace_id, "options": options})
            self.assertNotEqual(code, 0)
        code, response = self.invoke("alpha", "nmap.capabilities")
        self.assertEqual(code, 0)
        self.assertIn("udp", response["data"]["scan_types"])


if __name__ == "__main__":
    unittest.main()
