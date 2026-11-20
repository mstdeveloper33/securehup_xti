"""Bounded lossless decoding. Limits apply to original bytes, never compressed size."""
import hashlib
import json
import zlib

from xti.domain.engine_jobs import canonical_json

JOURNALS = ('report_journal', 'evidence_journal', 'social_discovery_runs', 'research_group_journal')
MAX_PAYLOAD = 2 * 1024 * 1024


def payload_columns(journal):
    if journal not in JOURNALS:
        raise ValueError('Unknown journal')
    return ('report_json', 'report_sha256') if journal == 'social_discovery_runs' else ('payload_json', 'payload_sha256')


def unpack(body, raw_size, sha, *, maximum=MAX_PAYLOAD):
    from xti.adapters.sqlite import StorageError
    try:
        if type(raw_size) is not int or not 1 <= raw_size <= maximum or not isinstance(body, bytes) or len(body) > maximum + 4096:
            raise ValueError('Object size')
        decoder = zlib.decompressobj()
        result = decoder.decompress(body, raw_size + 1)
        if len(result) != raw_size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or hashlib.sha256(result).hexdigest() != sha:
            raise ValueError('Object digest or compressed stream')
        return result
    except (ValueError, zlib.error, TypeError) as error:
        raise StorageError('Sıkıştırılmış kanıt eksik, bozuk veya boyut sınırının dışında.') from error


def marker(journal, sequence, sha):
    return canonical_json({'cold_payload_v1': {'journal': journal, 'sequence': sequence, 'sha256': sha}})


def resolve_payload(connection, journal, sequence, payload, sha):
    from xti.adapters.sqlite import StorageError
    if journal not in JOURNALS:
        raise StorageError('Arşiv günlüğü bilinmiyor.')
    # Normal entries contain a version field, while the marker has exactly one key.
    if payload != marker(journal, sequence, sha):
        return payload
    row = connection.execute('SELECT payload_sha256,raw_size,body FROM journal_payload_archives WHERE journal=? AND sequence=?',
                             (journal, sequence)).fetchone()
    if row is None or row[0] != sha:
        raise StorageError('Günlüğün arşiv kanıtı eksik veya farklı kayda bağlı.')
    try:
        return unpack(row[2], row[1], sha).decode('ascii')
    except UnicodeError as error:
        raise StorageError('Arşiv kanıtının JSON kodlaması bozuk.') from error


def logical_extra(connection, journal):
    """Expand the preflight budget before any decompression or JSON materialization."""
    from xti.adapters.sqlite import StorageError
    if journal not in JOURNALS or not connection.execute("SELECT 1 FROM sqlite_schema WHERE name='journal_payload_archives'").fetchone():
        return 0
    from xti.adapters.sqlite_journal_storage import read_events
    read_events(connection)
    payload_column, hash_column = payload_columns(journal)
    extra = 0
    for sequence, sha, raw_size, payload, stored_sha in connection.execute(
            f'SELECT a.sequence,a.payload_sha256,a.raw_size,j.{payload_column},j.{hash_column} '
            f'FROM journal_payload_archives a LEFT JOIN {journal} j ON j.sequence=a.sequence WHERE a.journal=?', (journal,)):
        if (type(raw_size) is not int or not 1 <= raw_size <= MAX_PAYLOAD or stored_sha != sha or
                payload != marker(journal, sequence, sha)):
            raise StorageError('Arşiv ile günlük kaydı tutarsız.')
        extra += max(0, raw_size - len(payload.encode('ascii')))
    return extra


def journal_bytes(connection, journal):
    if journal not in JOURNALS:
        raise ValueError('Unknown journal')
    payload_column, _ = payload_columns(journal)
    return connection.execute(f'SELECT COALESCE(SUM(COALESCE(LENGTH(CAST({payload_column} AS BLOB)),0)+512),0) FROM {journal}').fetchone()[0] + logical_extra(connection, journal)
