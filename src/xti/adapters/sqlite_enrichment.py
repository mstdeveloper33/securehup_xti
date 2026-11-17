"""Append-only receipts; a failed query never replaces a valid source response."""
from dataclasses import asdict
from datetime import datetime
import re
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.indicator_enrichment import (MAX_BYTES, EnrichmentRun, EnrichmentRunNotFound,
    EnrichmentState, enrichment_query, parse_enrichment)


FIELDS = "id,provider,indicator_type,value,started_at,finished_at,status,http_status,snapshot_sha256,error"


def _run(row):
    try:
        run = EnrichmentRun(*row)
        normalize_knowledge_id(run.id)
        query = enrichment_query(provider=run.provider, indicator_type=run.indicator_type, value=run.value)
        if query.value != run.value:
            raise ValueError("Noncanonical query")
        if any(normalize_cti_timestamp(t) != t for t in (run.started_at, run.finished_at)) or datetime.fromisoformat(run.finished_at) < datetime.fromisoformat(run.started_at):
            raise ValueError("Invalid clock")
        if run.http_status is not None and (type(run.http_status) is not int or not 100 <= run.http_status <= 599):
            raise ValueError("Invalid HTTP status")
        if run.status in ("matched", "no_match"):
            if run.error is not None or run.http_status not in (200, 404) or not isinstance(run.snapshot_sha256, str) or re.fullmatch(r"[a-f0-9]{64}", run.snapshot_sha256) is None:
                raise ValueError("Invalid success receipt")
        elif run.status == "failed":
            if run.snapshot_sha256 is not None or not isinstance(run.error, str) or not 1 <= len(run.error) <= 1000 or not run.error.isprintable():
                raise ValueError("Invalid failure receipt")
        else:
            raise ValueError("Invalid state")
        return run
    except (ValueError, TypeError, AttributeError) as error:
        raise StorageError("Kaynak araştırması çalışma kaydı bozuk.") from error


def _snapshot(connection, run):
    if run.status == "failed":
        return None
    row = connection.execute("SELECT LENGTH(content) FROM enrichment_snapshots WHERE sha256=?", (run.snapshot_sha256,)).fetchone()
    if row is None or type(row[0]) is not int or not 0 < row[0] <= MAX_BYTES:
        raise StorageError("Kaynak araştırması içeriği eksik veya sınır dışında.")
    content = connection.execute("SELECT content FROM enrichment_snapshots WHERE sha256=?", (run.snapshot_sha256,)).fetchone()[0]
    try:
        snapshot = parse_enrichment(enrichment_query(provider=run.provider, indicator_type=run.indicator_type, value=run.value), run.http_status, content)
        if snapshot.sha256 != run.snapshot_sha256 or snapshot.status != run.status:
            raise ValidationError("Payload or receipt mismatch")
    except ValidationError as error:
        raise StorageError("Kaynak araştırması içeriği doğrulanamadı.") from error
    return snapshot


def read_enrichment(connection, query):
    args = (query.provider, query.indicator_type, query.value)
    sql = f"SELECT {FIELDS} FROM enrichment_runs WHERE provider=? AND indicator_type=? AND value=?"
    latest = connection.execute(sql + " ORDER BY rowid DESC LIMIT 1", args).fetchone()
    success = connection.execute(sql + " AND status!='failed' ORDER BY rowid DESC LIMIT 1", args).fetchone()
    latest, success = _run(latest) if latest else None, _run(success) if success else None
    return EnrichmentState(query, latest, success, _snapshot(connection, success) if success else None)


class SQLiteEnrichmentRepository:
    def __init__(self, path):
        self.storage = SQLiteAssetRepository(path)

    def record(self, query, *, started_at, finished_at, http_status, content, error):
        snapshot = parse_enrichment(query, http_status, content) if content is not None else None
        if (snapshot is None) != (error is not None):
            raise ValidationError("Kaynak araştırması yanıt veya hata içermeli.")
        run = _run((str(uuid4()), query.provider, query.indicator_type, query.value, started_at, finished_at,
            snapshot.status if snapshot else "failed", http_status, snapshot.sha256 if snapshot else None, error))
        with self.storage._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            read_enrichment(connection, query)
            if snapshot:
                old = connection.execute("SELECT content FROM enrichment_snapshots WHERE sha256=?", (snapshot.sha256,)).fetchone()
                if old is not None and old[0] != content:
                    raise StorageError("Kaynak araştırması içerik kimliği uyuşmuyor.")
                if old is None:
                    connection.execute("INSERT INTO enrichment_snapshots VALUES (?,?)", (snapshot.sha256, content))
            connection.execute(f"INSERT INTO enrichment_runs({FIELDS}) VALUES (?,?,?,?,?,?,?,?,?,?)", tuple(asdict(run).values()))
            connection.commit()
        return run

    def read(self, query):
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            return read_enrichment(connection, query)

    def history(self, query, *, offset, limit):
        with self.storage._connection(readonly=True) as connection:
            return tuple(_run(row) for row in connection.execute(f"SELECT {FIELDS} FROM enrichment_runs "
                "WHERE provider=? AND indicator_type=? AND value=? ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (query.provider, query.indicator_type, query.value, limit, offset)))

    def show(self, run_id):
        normalize_knowledge_id(run_id)
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = connection.execute(f"SELECT {FIELDS} FROM enrichment_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise EnrichmentRunNotFound("Kaynak araştırması çalışması seçili alanda bulunamadı.")
            run = _run(row)
            return run, _snapshot(connection, run)
