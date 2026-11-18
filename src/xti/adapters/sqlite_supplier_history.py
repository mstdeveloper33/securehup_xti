"""Shared audited supplier lifecycle, including historical activation identity."""

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.domain.assets import ValidationError
from xti.domain.suppliers import Supplier, SupplierEvent, normalize_supplier_id, normalize_supplier_name

MAX_SUPPLIERS = 10_000
MAX_SUPPLIER_EVENTS = 100_000


@dataclass
class SupplierHistory:
    suppliers: dict[str, Supplier]
    events: tuple[SupplierEvent, ...]
    complete: bool = True


def read_supplier_history(connection, *, supplier_id=None) -> SupplierHistory:
    try:
        if supplier_id is not None:
            normalize_supplier_id(supplier_id)
        values = (supplier_id,) if supplier_id is not None else ()
        rows = connection.execute('SELECT id,name_key,display_name,primary_domain,relationship_type,criticality,active,reason,created_at,updated_at FROM suppliers ' +
            ('WHERE id=? ' if values else '') + 'ORDER BY id LIMIT ?', (*values, MAX_SUPPLIERS + 1)).fetchall()
        raw_events = connection.execute('SELECT sequence,id,supplier_id,action,display_name,primary_domain,relationship_type,criticality,reason,recorded_at FROM supplier_events ' +
            ('WHERE supplier_id=? ' if values else '') + 'ORDER BY sequence LIMIT ?', (*values, MAX_SUPPLIER_EVENTS + 1)).fetchall()
        if len(rows) > MAX_SUPPLIERS or len(raw_events) > MAX_SUPPLIER_EVENTS:
            raise ValueError('Supplier history capacity exceeded')
        suppliers = {value.id: value for value in map(SQLiteSupplierRepository._supplier, rows)}
        events = tuple(map(SQLiteSupplierRepository._event, raw_events))
        allocated = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='supplier_events'").fetchone()
        # Scoped reads still detect missing global sequence entries, without
        # materializing unrelated suppliers or their event payloads.
        count, first, last = connection.execute('SELECT COUNT(*),MIN(sequence),MAX(sequence) FROM supplier_events').fetchone()
        if ((allocated[0] if allocated else 0) != count or
            (count and (first != 1 or last != count)) or
            (supplier_id is not None and set(suppliers) != {supplier_id})):
            raise ValueError('Supplier history sequence allocator differs')
        states = {}
        for sequence, event in enumerate(events, 1):
            if (supplier_id is None and event.sequence != sequence) or event.supplier_id not in suppliers:
                raise ValueError('Supplier history sequence or pointer differs')
            before = states.get(event.supplier_id)
            if before is None:
                if event.action != 'added':
                    raise ValueError('Supplier history lacks addition')
                created, active = event.recorded_at, True
            else:
                if (event.primary_domain != before.primary_domain or event.action == 'added'
                        or event.action == 'reactivated' and before.active
                        or event.action in {'updated', 'revoked'} and not before.active):
                    raise ValueError('Supplier lifecycle transition differs')
                created, active = before.created_at, event.action != 'revoked'
            name_key, _ = normalize_supplier_name(event.display_name)
            updated = max((before.updated_at if before else created, event.recorded_at), key=datetime.fromisoformat)
            states[event.supplier_id] = Supplier(event.supplier_id, name_key, event.display_name,
                event.primary_domain, event.relationship_type, event.criticality, active,
                event.reason, created, updated)
        if states != suppliers:
            raise ValueError('Supplier state differs from lifecycle')
        return SupplierHistory(suppliers, events, complete=supplier_id is None)
    except (ValueError, TypeError, KeyError, OverflowError, ValidationError) as error:
        raise StorageError('Tedarikçi yaşam döngüsü kaynak kaydıyla uyuşmuyor; kayıtlar değiştirilmedi.') from error


def supplier_scope(history: SupplierHistory, supplier_id: str, cutoff: int | None = None) -> dict:
    if not history.complete:
        raise ValueError('Historical workspace watermark requires complete supplier history')
    cutoff = len(history.events) if cutoff is None else cutoff
    if type(cutoff) is not int or not 1 <= cutoff <= len(history.events):
        raise ValueError('Supplier event watermark invalid')
    selected = [event for event in history.events[:cutoff] if event.supplier_id == supplier_id]
    if not selected:
        raise ValueError('Supplier absent at historical watermark')
    first, last = selected[0], selected[-1]
    name_key, _ = normalize_supplier_name(last.display_name)
    supplier = Supplier(supplier_id, name_key, last.display_name, last.primary_domain,
        last.relationship_type, last.criticality, last.action != 'revoked', last.reason,
        first.recorded_at, max((event.recorded_at for event in selected), key=datetime.fromisoformat))
    epoch = next(event.id for event in reversed(selected) if event.action in {'added','reactivated'})
    # Returning to a former name starts a new comparison epoch as well.
    identity_epoch = selected[0].id
    previous_key = None
    for event in selected:
        event_key = normalize_supplier_name(event.display_name)[0]
        if event.action in {'added','reactivated'} or event_key != previous_key:
            identity_epoch = event.id
        previous_key = event_key
    current = {}
    for event in history.events[:cutoff]:
        current[event.supplier_id] = event
    same_name_count = sum(event.action != 'revoked' and normalize_supplier_name(event.display_name)[0] == name_key for event in current.values())
    definition = hashlib.sha256(json.dumps([name_key, supplier.primary_domain, epoch, identity_epoch], ensure_ascii=True, separators=(',',':')).encode()).hexdigest()
    return {'supplier': asdict(supplier), 'supplier_event_sequence': cutoff,
            'supplier_event_id': last.id, 'supplier_epoch_event_id': epoch,
            'identity_epoch_event_id': identity_epoch, 'definition_sha256': definition,
            'same_name_supplier_count': same_name_count}
