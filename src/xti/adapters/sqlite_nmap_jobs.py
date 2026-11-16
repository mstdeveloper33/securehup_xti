"""Atomic admission, progress and cancellation; every transition is replay-checked."""

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_nmap_management import SQLiteNmapManagementRepository
from xti.domain.assets import ValidationError
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.engine_jobs import job_time, request_key
from xti.domain.nmap_execution import NmapWork, apply_event, encoded, parse_event, sha, MAX_JOB_EVIDENCE_BYTES


class SQLiteNmapWorkRepository:
    def __init__(self, path: Path):
        self.storage = SQLiteAssetRepository(path)
        self.binding = sha(str(self.storage.path.resolve()))

    def check_binding(self, work):
        if work.binding != self.binding:
            raise ValidationError("Bu Nmap işi başka kayıt alanından/yedekten geldi; yeni istek anahtarıyla iş oluşturun.")

    @staticmethod
    def _request_hash(work):
        return sha(encoded({"id": work.id, "asset_id": work.plan.asset_id,
            "plan_id": work.plan.id, "plan_sha256": work.plan.plan_sha256,
            "key": work.request_key, "binding": work.binding, "created_at": work.created_at}))

    def _read(self, connection, asset_id, job_id):
        row = connection.execute(
            "SELECT id,request_key,plan_id,binding,created_at,event_count,last_hash,cancel_requested "
            "FROM surface_nmap_jobs WHERE asset_id=? AND id=?", (asset_id, job_id)).fetchone()
        if row is None:
            raise ValidationError("Bu domain kapsamında Nmap işi bulunamadı.")
        try:
            _targets, _events, plans = SQLiteNmapManagementRepository._audit(connection)
            plan = next(p for p in plans if p.id == row[2] and p.asset_id == asset_id)
            work = NmapWork(normalize_knowledge_id(row[0]), request_key(row[1]), plan,
                            row[3], job_time(row[4]))
            work = replace(work, last_hash=self._request_hash(work))
            if type(row[5]) is not int or not 0 <= row[5] <= 8400:
                raise ValueError("event limit")
            size = connection.execute("SELECT COALESCE(SUM(length(event_json)),0) FROM surface_nmap_job_events WHERE job_id=?",
                                      (job_id,)).fetchone()[0]
            if size > MAX_JOB_EVIDENCE_BYTES:
                raise ValueError("job evidence bytes")
            events = connection.execute(
                "SELECT ordinal,event_json,event_sha256 FROM surface_nmap_job_events "
                "WHERE job_id=? ORDER BY ordinal LIMIT 8401", (job_id,)).fetchall()
            for ordinal, value, digest in events:
                if ordinal != work.event_count + 1 or sha(value) != digest:
                    raise ValueError("event chain")
                work = apply_event(work, parse_event(value))
            if (work.event_count != row[5] or work.last_hash != row[6]
                    or type(row[7]) is not int or row[7] != int(work.cancel_requested)):
                raise ValueError("materialized state")
            return work
        except (ValueError, TypeError, KeyError, StopIteration, RecursionError) as error:
            raise StorageError("Nmap iş geçmişi bozuk; işlem durduruldu.") from error

    def get(self, asset_id, job_id):
        normalize_knowledge_id(asset_id)
        normalize_knowledge_id(job_id)
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            return self._read(connection, asset_id, job_id)

    def find_request(self, asset_id, key):
        request_key(key)
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = connection.execute("SELECT id FROM surface_nmap_jobs WHERE asset_id=? AND request_key=?",
                                     (asset_id, key)).fetchone()
            return self._read(connection, asset_id, row[0]) if row else None

    def create(self, plan, key, at):
        request_key(key)
        job_time(at)
        with self.storage._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT id FROM surface_nmap_jobs WHERE asset_id=? AND request_key=?",
                                          (plan.asset_id, key)).fetchone()
            if existing:
                work = self._read(connection, plan.asset_id, existing[0])
                if work.plan.id != plan.id:
                    raise ValidationError("Tekrar önleme anahtarı başka Nmap planına bağlı.")
                return work
            if connection.execute("SELECT COUNT(*) FROM surface_nmap_jobs").fetchone()[0] >= 10000:
                raise ValidationError("Nmap iş kayıt sınırına ulaşıldı.")
            work = NmapWork(str(uuid4()), key, plan, self.binding, at)
            work = replace(work, last_hash=self._request_hash(work))
            connection.execute("INSERT INTO surface_nmap_jobs VALUES (?,?,?,?,?,?,0,?,0)",
                (work.id, plan.asset_id, plan.id, key, self.binding, at, work.last_hash))
            self._read(connection, plan.asset_id, work.id)
            connection.commit()
            return work

    def list(self, asset_id, *, limit=20, offset=0):
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 10000:
            raise ValidationError("Nmap iş sayfalaması geçersiz.")
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            ids = connection.execute("SELECT id FROM surface_nmap_jobs WHERE asset_id=? "
                "ORDER BY rowid DESC LIMIT ? OFFSET ?", (asset_id, limit, offset)).fetchall()
            return tuple(self._read(connection, asset_id, row[0]) for row in ids)

    def append(self, work, kind, payload, at, *, token):
        with self.storage._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._read(connection, work.plan.asset_id, work.id)
            # Cancellation may be appended by another process while a target runs.
            if current.event_count >= 8400:
                raise ValidationError("Nmap iş olay sınırına ulaşıldı.")
            if kind == "cancel" and (current.cancel_requested or current.status not in {"queued", "running"}):
                return current
            event = {"kind": kind, "at": at, "payload": payload, "token": token, "previous": current.last_hash}
            changed = apply_event(current, event)
            value = encoded(event)
            size = connection.execute("SELECT COALESCE(SUM(length(event_json)),0) FROM surface_nmap_job_events WHERE job_id=?",
                                      (work.id,)).fetchone()[0]
            if size + len(value) > MAX_JOB_EVIDENCE_BYTES:
                raise ValidationError("Nmap iş kanıtı boyut sınırına ulaşıldı.")
            connection.execute("INSERT INTO surface_nmap_job_events VALUES (?,?,?,?)",
                (work.id, changed.event_count, value, changed.last_hash))
            connection.execute("UPDATE surface_nmap_jobs SET event_count=?,last_hash=?,cancel_requested=? WHERE id=?",
                (changed.event_count, changed.last_hash, int(changed.cancel_requested), work.id))
            connection.commit()
            return changed

    def cancelled(self, asset_id, job_id):
        with self.storage._connection(readonly=True) as connection:
            row = connection.execute("SELECT cancel_requested FROM surface_nmap_jobs WHERE asset_id=? AND id=?",
                                     (asset_id, job_id)).fetchone()
            if row is None or row[0] not in {0, 1}:
                raise StorageError("Nmap iptal durumu okunamadı.")
            return bool(row[0])
