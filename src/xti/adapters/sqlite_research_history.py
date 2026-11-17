"""Atomic append, idempotent replay and bounded immutable review reads."""

from datetime import datetime
import re
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.research import identity
from xti.domain.research_history import (
    MAX_SNAPSHOT_BYTES, MAX_COMPARISON_BYTES, ResearchHistoryError, ReviewHeader, StoredReview,
    capture_scope, compare, decode, digest, encode, history_key, validate_snapshot,
)


FIELDS = ("id,scope_key,indicator_type,value,sequence,request_key,previous_id,checked_at,policy_version,"
          "scope_json,snapshot_sha256,comparison_sha256,summary_json,header_sha256")


def _summary(comparison):
    return {key: value for key, value in comparison.items() if key != "changes"}


def _header(row):
    try:
        if row is None or len(row) != 14 or identity(*row[:-1]) != row[-1]:
            raise ValidationError("Header hash")
        identifier, scope_key, kind, value, sequence, key, previous, at, policy, scope_json, snapshot_hash, comparison_hash, summary_json, _ = row
        normalize_knowledge_id(identifier)
        if previous:
            normalize_knowledge_id(previous)
        scope = decode(scope_json, digest(scope_json), limit=8192)
        if capture_scope(**scope) != scope or identity(scope) != scope_key or (scope["indicator_type"], scope["value"]) != (kind, value):
            raise ValidationError("Scope")
        if type(sequence) is not int or sequence < 1 or (sequence == 1) != (previous is None):
            raise ValidationError("Chain")
        if normalize_cti_timestamp(at) != at:
            raise ValidationError("Clock")
        history_key(key)
        summary = decode(summary_json, digest(summary_json), limit=8192)
        if (not isinstance(summary, dict) or
            set(summary) != {"model_version", "state", "counts", "coverage_limited", "context_changed", "context_origin"} or
            type(summary["model_version"]) is not int or summary["model_version"] != 1 or
            summary["state"] not in {"baseline", "policy_baseline", "changed", "unchanged"} or
            not isinstance(summary["counts"], dict) or set(summary["counts"]) != {"entered_view", "not_in_current_view", "changed"} or
            any(type(count) is not int or not 0 <= count <= 600 for count in summary["counts"].values()) or
            any(type(summary[key]) is not bool for key in ("coverage_limited", "context_changed")) or
            summary["context_origin"] not in (None, "time_only", "evidence_or_mixed") or
            summary["context_changed"] != (summary["context_origin"] is not None)):
            raise ValidationError("Summary")
        if re.fullmatch(r"[a-z0-9-]{1,80}", policy) is None or any(re.fullmatch(r"[a-f0-9]{64}", value) is None for value in (snapshot_hash, comparison_hash)):
            raise ValidationError("Policy or content digest")
        return ReviewHeader(identifier, scope, scope_key, sequence, key, previous, at, policy, snapshot_hash, comparison_hash, summary)
    except (ValidationError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        raise StorageError("İnceleme geçmişinin kimlik, kapsam veya özet kaydı bozuk.") from error


def _read_header(connection, identifier):
    row = connection.execute(f"SELECT {FIELDS} FROM research_reviews WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise ResearchHistoryError("not_found", "İnceleme kaydı seçili alanda bulunamadı.")
    return _header(row)


def _parent(connection, header):
    if header.previous_id is None:
        return None
    try:
        parent = _read_header(connection, header.previous_id)
    except ResearchHistoryError as error:
        raise StorageError("İnceleme geçmişinin önceki kaydı eksik.") from error
    if parent.scope_key != header.scope_key or parent.sequence + 1 != header.sequence or datetime.fromisoformat(parent.checked_at) > datetime.fromisoformat(header.checked_at):
        raise StorageError("İnceleme geçmişinin sırası, zamanı veya kapsam bağı tutarsız.")
    return parent


def _body(connection, header, *, snapshot_only=False):
    sizes = connection.execute("SELECT LENGTH(snapshot_json),LENGTH(comparison_json) FROM research_reviews WHERE id=?", (header.id,)).fetchone()
    if sizes is None or not 0 < sizes[0] <= MAX_SNAPSHOT_BYTES or not 0 < sizes[1] <= MAX_COMPARISON_BYTES:
        raise StorageError("İnceleme kaydı boş, eksik veya okuma boyutu sınırı dışında.")
    raw = connection.execute("SELECT snapshot_json,comparison_json FROM research_reviews WHERE id=?", (header.id,)).fetchone()
    try:
        snapshot = validate_snapshot(decode(raw[0], header.snapshot_sha256))
        if snapshot["query"] != header.scope or snapshot["checked_at"] != header.checked_at or snapshot["policy_version"] != header.policy_version:
            raise ValidationError("Metadata mismatch")
        if snapshot_only:
            return snapshot
        comparison = decode(raw[1], header.comparison_sha256, limit=MAX_COMPARISON_BYTES)
        if _summary(comparison) != header.summary:
            raise ValidationError("Summary mismatch")
        return StoredReview(header, snapshot, comparison)
    except (ValidationError, TypeError, ValueError, KeyError, AttributeError, RecursionError) as error:
        raise StorageError("İnceleme içeriği, özeti veya kapsamı doğrulanamadı.") from error


def _load(connection, identifier):
    header = _read_header(connection, identifier)
    parent = _parent(connection, header)
    record = _body(connection, header)
    previous = _body(connection, parent, snapshot_only=True) if parent else None
    try:
        if compare(previous, record.snapshot) != record.comparison:
            raise ValidationError("Changed comparison")
    except (ValidationError, TypeError, KeyError, ValueError, AttributeError, RecursionError) as error:
        raise StorageError("İnceleme karşılaştırması özgün kayıtlarla uyuşmuyor.") from error
    return record


class SQLiteResearchHistoryRepository:
    def __init__(self, path):
        self.storage = SQLiteAssetRepository(path)

    def find_key(self, key):
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = connection.execute("SELECT id FROM research_reviews WHERE request_key=?", (key,)).fetchone()
            return _load(connection, row[0]) if row else None

    def latest(self, scope):
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = connection.execute(f"SELECT {FIELDS} FROM research_reviews WHERE scope_key=? ORDER BY sequence DESC LIMIT 1", (identity(scope),)).fetchone()
            if row is None:
                return None
            header = _header(row)
            _parent(connection, header)
            return header

    def append(self, scope, snapshot, key, expected_previous):
        validate_snapshot(snapshot)
        if snapshot["query"] != scope:
            raise ValidationError("İnceleme sonucu istenen kapsamla uyuşmuyor.")
        history_key(key)
        snapshot_json = encode(snapshot)
        scope_key = identity(scope)
        with self.storage._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                replay = connection.execute("SELECT id FROM research_reviews WHERE request_key=?", (key,)).fetchone()
                if replay:
                    record = _load(connection, replay[0])
                    if record.header.scope != scope:
                        raise ResearchHistoryError("idempotency_conflict", "Tekrar anahtarı başka inceleme kapsamına bağlı.")
                    connection.rollback()
                    return record, True
                row = connection.execute("SELECT id FROM research_reviews WHERE scope_key=? ORDER BY sequence DESC LIMIT 1", (scope_key,)).fetchone()
                latest = row[0] if row else None
                if latest != expected_previous:
                    raise ResearchHistoryError("review_changed", "Aynı kapsamda başka inceleme kaydedildi; güncel kayıtla yeniden deneyin.")
                previous = _load(connection, latest) if latest else None
                if previous and datetime.fromisoformat(snapshot["checked_at"]) < datetime.fromisoformat(previous.header.checked_at):
                    raise ResearchHistoryError("clock_regression", "İnceleme zamanı önceki kayıttan eski; sistem saatini kontrol edin.")
                comparison = compare(previous.snapshot if previous else None, snapshot)
                comparison_json = encode(comparison, MAX_COMPARISON_BYTES)
                identifier = str(uuid4())
                fields = (identifier, scope_key, scope["indicator_type"], scope["value"],
                    previous.header.sequence + 1 if previous else 1, key, latest,
                    snapshot["checked_at"], snapshot["policy_version"], encode(scope), digest(snapshot_json),
                    digest(comparison_json), encode(_summary(comparison)))
                connection.execute(f"INSERT INTO research_reviews({FIELDS},snapshot_json,comparison_json) VALUES ({','.join('?' for _ in range(16))})",
                    (*fields, identity(*fields), snapshot_json, comparison_json))
                record = _load(connection, identifier)
                connection.commit()
                return record, False
            except BaseException:
                connection.rollback()
                raise

    def show(self, review_id):
        normalize_knowledge_id(review_id)
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            return _load(connection, review_id)

    def history(self, indicator_type, value, *, offset, limit, expected_snapshot):
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            args = (indicator_type, value)
            count = connection.execute("SELECT COUNT(*) FROM research_reviews WHERE indicator_type=? AND value=?", args).fetchone()[0]
            rows = connection.execute(f"SELECT {FIELDS} FROM research_reviews WHERE indicator_type=? AND value=? ORDER BY rowid DESC LIMIT ? OFFSET ?", (*args, limit, offset)).fetchall()
            head = connection.execute(f"SELECT {FIELDS} FROM research_reviews WHERE indicator_type=? AND value=? ORDER BY rowid DESC LIMIT 1", args).fetchone()
            if head:
                _header(head)
            snapshot = identity("research-history-v1", indicator_type, value, count, head[-1] if head else None)
            if expected_snapshot is not None and expected_snapshot != snapshot:
                raise ResearchHistoryError("snapshot_changed", "İnceleme geçmişine kayıt eklendi; ilk sayfadan yeniden başlayın.")
            records = tuple(_header(row) for row in rows)
            for record in records:
                _parent(connection, record)
            return dict(records=records, total_count=count, snapshot_id=snapshot)
