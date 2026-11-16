"""Combined company backups retain evidence, job identity and conservative recovery."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from xti.adapters.company_workspaces import provision_company_workspace, resolve_company_workspace
from xti.adapters.platform_backup import (
    PLATFORM_BACKUP_MANIFEST, backup_platform_workspace, restore_platform_workspace,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
from xti.adapters.sqlite_engine_jobs import ENGINE_JOB_DATABASE_NAME, SQLiteEngineJobRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.engine_jobs import EngineJobService
from xti.domain.collection import COLLECTION_TASKS, CollectionPlan
from xti.domain.collection_history import freeze_collection_plan
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.domain.engine_jobs import EngineJobPayload, request_json
from xti.ports.jobs import WorkerBusyError


class PlatformBackupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "original"
        self.context = provision_company_workspace(self.root, "alpha")
        self.core = SQLiteAssetRepository(self.context.database)
        self.core.initialize()
        self.core.add("alpha.example")
        self.job_path = self.context.data_dir / ENGINE_JOB_DATABASE_NAME
        self.jobs = SQLiteEngineJobRepository(self.job_path)
        self.jobs.initialize()
        self.now = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
        definition = CollectionProfileDefinition("alpha.example", task_ids=("scan-crtsh",))
        profile = SQLiteCollectionProfileRepository(self.context.database).save(
            "Company source", definition, recorded_at=self.tick()).profile
        self.history = SQLiteCollectionHistoryRepository(self.context.database)
        frozen = freeze_collection_plan(definition,
            CollectionPlan("alpha.example", False, (COLLECTION_TASKS[0],), ()),
            contracts={"scan-crtsh": "rules-v1"}, origin=self.history.profile_origin(profile))
        self.payload = EngineJobPayload(profile.id, profile.display_name, profile.revision, definition, frozen)
        self.backup = self.base / "backup"
        self.restore_root = self.base / "restored"
        self.addCleanup(patch.stopall)
        patch("socket.socket.connect", side_effect=AssertionError("Backup must stay local")).start()
        patch("socket.getaddrinfo", side_effect=AssertionError("Backup must stay local")).start()

    def tick(self):
        self.now += timedelta(seconds=1)
        return self.now.isoformat()

    def create_job(self, key="request-one"):
        return self.jobs.create(key, request_json(self.payload.profile_name, self.payload.profile_revision),
                                self.payload, recorded_at=self.tick())

    def result_job(self):
        job = self.create_job("result-job")
        claim = self.jobs.claim(job.id, recorded_at=self.tick())
        details = self.history.begin(self.payload.frozen_plan, started_at=self.tick())
        session_id = details.session.id
        self.jobs.link_session(claim, session_id, recorded_at=self.tick())
        details = self.history.finish_session(session_id, analysis_status="failed", stop_reason="execution_failed",
                                              finished_at=self.tick())
        session = details.session
        result = {"collection_session_id": session.id, "collection_status": session.status,
            "asset_value": "alpha.example", "analysis_status": session.analysis_status,
            "started_at": session.started_at, "finished_at": session.finished_at,
            "steps": [{"step_key": step.step_key, "source": step.source, "status": step.status, "receipt": None}
                      for step in details.steps]}
        return self.jobs.finish(claim, status=session.status, result=result, error_code=None, recorded_at=self.tick())

    def manifest(self):
        return json.loads((self.backup / PLATFORM_BACKUP_MANIFEST).read_text())

    def rewrite_manifest_hash(self, name):
        manifest = self.manifest()
        data = (self.backup / name).read_bytes()
        manifest["files"][name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        (self.backup / PLATFORM_BACKUP_MANIFEST).write_text(json.dumps(manifest))

    def test_roundtrip_retains_core_result_and_idempotency_but_generates_new_binding(self):
        job = self.result_job()
        old_core, old_queue = self.context.database.read_bytes(), self.job_path.read_bytes()
        output = backup_platform_workspace(self.context, self.backup)
        self.assertEqual(output, self.backup)
        manifest = self.manifest()
        self.assertEqual(manifest["company_id"], "alpha")
        self.assertEqual(manifest["registry_id"], self.context.registry_id)
        self.assertEqual(manifest["workspace_id"], self.context.workspace_id)
        self.assertEqual(set(manifest["files"]), {"xti.db", ENGINE_JOB_DATABASE_NAME})
        self.assertEqual(self.backup.stat().st_mode & 0o777, 0o700)
        for path in self.backup.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.stat().st_nlink, 1)
        restored = restore_platform_workspace(self.restore_root, "alpha", self.backup)
        self.assertNotEqual(restored.registry_id, self.context.registry_id)
        self.assertNotEqual(restored.workspace_id, self.context.workspace_id)
        self.assertEqual(restored, resolve_company_workspace(self.restore_root, "alpha"))
        self.assertEqual(SQLiteAssetRepository(restored.database).list(), self.core.list())
        recovered_jobs = SQLiteEngineJobRepository(restored.data_dir / ENGINE_JOB_DATABASE_NAME)
        self.assertEqual(recovered_jobs.get(job.id), job)
        self.assertEqual(SQLiteCollectionHistoryRepository(restored.database).get(job.collection_session_id),
                         self.history.get(job.collection_session_id))
        service = EngineJobService(recovered_jobs, None, LocalExecutionLock(recovered_jobs.path), clock=lambda: self.now)
        self.assertEqual(service.submit(job.request_key, self.payload.profile_name, self.payload.profile_revision), job)
        self.assertEqual(service.results(job.id)["result"], job.result)
        self.assertEqual(self.context.database.read_bytes(), old_core)
        self.assertEqual(self.job_path.read_bytes(), old_queue)

    def test_cancelled_and_interrupted_jobs_remain_terminal_after_restore(self):
        cancelled = self.create_job("cancelled")
        cancelled = self.jobs.cancel(cancelled.id, recorded_at=self.tick())
        interrupted = self.create_job("interrupted")
        claim = self.jobs.claim(interrupted.id, recorded_at=self.tick())
        interrupted = self.jobs.finish(claim, status="interrupted", result=None,
            error_code="execution_uncertain", recorded_at=self.tick())
        queued = self.create_job("queued")
        backup_platform_workspace(self.context, self.backup)
        restored = restore_platform_workspace(self.restore_root, "alpha", self.backup)
        repository = SQLiteEngineJobRepository(restored.data_dir / ENGINE_JOB_DATABASE_NAME)
        runner = Mock()
        service = EngineJobService(repository, runner, LocalExecutionLock(repository.path), clock=lambda: self.now)
        for job in (cancelled, interrupted):
            with self.subTest(status=job.status):
                self.assertEqual(service.submit(job.request_key, self.payload.profile_name, 1), job)
                self.assertIsNone(service.work_one(job.id))
        runner.run.assert_not_called()
        quarantined = repository.get(queued.id)
        self.assertEqual((quarantined.status, quarantined.error_code), ("cancelled", "restored_uncertain"))
        self.assertEqual(quarantined.payload_sha256, queued.payload_sha256)
        self.assertEqual(quarantined.request_sha256, queued.request_sha256)
        self.assertEqual(service.submit(queued.request_key, self.payload.profile_name, 1), quarantined)
        self.assertIsNone(service.work_one(queued.id))
        runner.run.assert_not_called()
        self.assertEqual(self.jobs.get(queued.id), queued)
        self.assertEqual(SQLiteEngineJobRepository(self.backup / ENGINE_JOB_DATABASE_NAME).get(queued.id), queued)

    def test_job_sent_on_original_after_backup_is_not_replayed_after_restore(self):
        job = self.create_job()
        backup_platform_workspace(self.context, self.backup)
        claim = self.jobs.claim(job.id, recorded_at=self.tick())
        self.jobs.finish(claim, status="interrupted", result=None,
                         error_code="execution_uncertain", recorded_at=self.tick())
        restored = restore_platform_workspace(self.restore_root, "alpha", self.backup)
        repository = SQLiteEngineJobRepository(restored.data_dir / ENGINE_JOB_DATABASE_NAME)
        runner = Mock()
        service = EngineJobService(repository, runner, LocalExecutionLock(repository.path), clock=lambda: self.now)
        replay = service.submit(job.request_key, self.payload.profile_name, 1)
        self.assertEqual((replay.id, replay.status, replay.error_code), (job.id, "cancelled", "restored_uncertain"))
        self.assertIsNone(service.work_one(job.id))
        runner.run.assert_not_called()
        self.assertEqual(self.jobs.get(job.id).status, "interrupted")

    def test_cross_company_restore_rejected_before_destination_creation(self):
        backup_platform_workspace(self.context, self.backup)
        with self.assertRaisesRegex(StorageError, "başka bir firmaya"):
            restore_platform_workspace(self.restore_root, "beta", self.backup)
        self.assertFalse(self.restore_root.exists())

    def test_existing_backup_and_existing_workspace_are_never_overwritten(self):
        backup_platform_workspace(self.context, self.backup)
        before = {path.name: path.read_bytes() for path in self.backup.iterdir()}
        with self.assertRaises(StorageError):
            backup_platform_workspace(self.context, self.backup)
        with self.assertRaises(StorageError):
            restore_platform_workspace(self.root, "alpha", self.backup)
        self.assertEqual({path.name: path.read_bytes() for path in self.backup.iterdir()}, before)
        self.assertEqual(resolve_company_workspace(self.root, "alpha"), self.context)

    def test_corrupt_file_hash_fails_before_provision(self):
        backup_platform_workspace(self.context, self.backup)
        with (self.backup / ENGINE_JOB_DATABASE_NAME).open("ab") as stream:
            stream.write(b"unexpected bytes")
        with self.assertRaisesRegex(StorageError, "SHA-256"):
            restore_platform_workspace(self.restore_root, "alpha", self.backup)
        self.assertFalse(self.restore_root.exists())

    def test_core_schema_and_job_history_are_validated_even_with_matching_hashes(self):
        for name in ("xti.db", ENGINE_JOB_DATABASE_NAME):
            with self.subTest(name=name):
                output = self.base / ("corrupt-" + name)
                self.create_job("history-" + name)
                backup_platform_workspace(self.context, output)
                self.backup = output
                with closing(sqlite3.connect(output / name)) as connection:
                    if name == "xti.db":
                        connection.execute("PRAGMA user_version=99999")
                    else:
                        connection.execute("UPDATE engine_jobs SET payload_sha256=?", ("0" * 64,))
                    connection.commit()
                self.rewrite_manifest_hash(name)
                with self.assertRaises(StorageError):
                    restore_platform_workspace(self.restore_root, "alpha", output)
                self.assertFalse(self.restore_root.exists())

    def test_missing_duplicate_or_oversized_manifest_rejected_before_provision(self):
        for value in (None, '{"version":1,"version":1}', " " * 8193):
            output = self.base / ("invalid-" + str(len(list(self.base.iterdir()))))
            backup_platform_workspace(self.context, output)
            manifest = output / PLATFORM_BACKUP_MANIFEST
            if value is None:
                manifest.unlink()
            else:
                manifest.write_text(value)
            with self.subTest(value=value and value[:30]), self.assertRaises(StorageError):
                restore_platform_workspace(self.restore_root, "alpha", output)
            self.assertFalse(self.restore_root.exists())

    def test_source_and_output_symlinks_are_rejected(self):
        backup_platform_workspace(self.context, self.backup)
        linked = self.base / "linked"
        linked.symlink_to(self.backup, target_is_directory=True)
        with self.assertRaises(StorageError):
            restore_platform_workspace(self.restore_root, "alpha", linked)
        with self.assertRaises(StorageError):
            backup_platform_workspace(self.context, linked / "nested")
        self.assertFalse(self.restore_root.exists())

    def test_restore_inside_source_backup_rejected_without_modifying_backup(self):
        backup_platform_workspace(self.context, self.backup)
        before = {path.name: path.read_bytes() for path in self.backup.iterdir()}
        with self.assertRaises(StorageError):
            restore_platform_workspace(self.backup / "new-root", "alpha", self.backup)
        self.assertEqual({path.name: path.read_bytes() for path in self.backup.iterdir()}, before)

    def test_runtime_hardlinks_or_public_files_block_backup(self):
        for path in (self.context.database, self.job_path):
            linked = self.base / (path.name + "-hardlink")
            os.link(path, linked)
            with self.subTest(path=path, variant="hardlink"), self.assertRaises(StorageError):
                backup_platform_workspace(self.context, self.backup)
            linked.unlink()
            path.chmod(0o644)
            with self.subTest(path=path, variant="public"), self.assertRaises(StorageError):
                backup_platform_workspace(self.context, self.backup)
            path.chmod(0o600)
        self.assertFalse(self.backup.exists())

    def test_untrusted_writable_ancestors_are_rejected(self):
        unsafe = self.base / "shared"
        unsafe.mkdir(mode=0o700)
        unsafe.chmod(0o777)
        with self.assertRaises(StorageError):
            backup_platform_workspace(self.context, unsafe / "backup")
        self.assertEqual(list(unsafe.iterdir()), [])
        backup_platform_workspace(self.context, self.backup)
        moved = self.backup.rename(unsafe / "snapshot")
        with self.assertRaises(StorageError):
            restore_platform_workspace(self.restore_root, "alpha", moved)
        self.assertFalse(self.restore_root.exists())

    def test_wal_mode_cannot_bypass_held_core_read_lock(self):
        with closing(sqlite3.connect(self.context.database)) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
        with self.assertRaises(StorageError):
            backup_platform_workspace(self.context, self.backup)
        self.assertFalse(self.backup.exists())

    def test_backup_files_and_manifest_reject_symlinks_hardlinks_and_public_permissions(self):
        for name in ("xti.db", ENGINE_JOB_DATABASE_NAME, PLATFORM_BACKUP_MANIFEST):
            for variant in ("symlink", "hardlink", "public"):
                output = self.base / (name + "-" + variant)
                backup_platform_workspace(self.context, output)
                path = output / name
                alternate = self.base / (name + "-" + variant + "-original")
                if variant == "public":
                    path.chmod(0o644)
                else:
                    path.rename(alternate)
                    if variant == "symlink":
                        path.symlink_to(alternate)
                    else:
                        os.link(alternate, path)
                with self.subTest(name=name, variant=variant), self.assertRaises(StorageError):
                    restore_platform_workspace(self.restore_root, "alpha", output)
                self.assertFalse(self.restore_root.exists())

    def test_active_worker_and_unrecovered_running_job_block_backup(self):
        for path in (self.job_path, self.context.database):
            with LocalExecutionLock(path).acquire(), self.assertRaises(WorkerBusyError):
                backup_platform_workspace(self.context, self.backup)
            self.assertFalse(self.backup.exists())
        job = self.create_job()
        self.jobs.claim(job.id, recorded_at=self.tick())
        with self.assertRaises(WorkerBusyError):
            backup_platform_workspace(self.context, self.backup)
        self.assertFalse(self.backup.exists())
        self.jobs.recover_interrupted(recorded_at=self.tick())
        backup_platform_workspace(self.context, self.backup)
        restored = restore_platform_workspace(self.restore_root, "alpha", self.backup)
        self.assertEqual(SQLiteEngineJobRepository(restored.data_dir / ENGINE_JOB_DATABASE_NAME).get(job.id).status,
                         "interrupted")

    def test_partial_backup_has_no_manifest_and_cannot_be_restored_or_overwritten(self):
        with patch.object(SQLiteEngineJobRepository, "backup", side_effect=StorageError("Simulated queue failure")):
            with self.assertRaises(StorageError):
                backup_platform_workspace(self.context, self.backup)
        self.assertTrue((self.backup / "xti.db").exists())
        self.assertFalse((self.backup / PLATFORM_BACKUP_MANIFEST).exists())
        with self.assertRaises(StorageError):
            restore_platform_workspace(self.restore_root, "alpha", self.backup)
        with self.assertRaises(StorageError):
            backup_platform_workspace(self.context, self.backup)
        self.assertFalse(self.restore_root.exists())

    def test_core_read_lock_prevents_legacy_commit_through_queue_snapshot(self):
        original = SQLiteEngineJobRepository.backup
        blocked = []

        def snapshot(repository, destination):
            writer = sqlite3.connect(self.context.database, timeout=0, isolation_level=None)
            try:
                writer.execute("BEGIN IMMEDIATE")
                writer.execute("UPDATE assets SET value='changed.example' WHERE value='alpha.example'")
                with self.assertRaises(sqlite3.OperationalError):
                    writer.commit()
                blocked.append(True)
            finally:
                writer.rollback()
                writer.close()
            return original(repository, destination)

        with patch.object(SQLiteEngineJobRepository, "backup", snapshot):
            backup_platform_workspace(self.context, self.backup)
        self.assertEqual(blocked, [True])
        self.assertEqual(self.core.list()[0].value, "alpha.example")


if __name__ == "__main__":
    unittest.main()
