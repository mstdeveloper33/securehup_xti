"""Bounded supplier monitoring/risk composition in the research transaction."""

from collections import Counter
from datetime import datetime

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_supplier_history import read_supplier_history, supplier_scope
from xti.adapters import sqlite_supplier_history as supplier_history_limits
from xti.adapters.sqlite_supplier_watches import _Catalog, _SOURCES, _audit, _run_report
from xti.domain.ransomware_claims import RansomwareClaim
from xti.domain.ransomlook_ransomware import RansomLookClaim
from xti.domain.research import ResearchEdge, ResearchNode, identity
from xti.domain.research_supplier_context import (
    supplier_source_evidence, supplier_risk_evidence, supplier_event_evidence,
    supplier_watch_evidence, supplier_watch_run_evidence, supplier_watch_item_evidence,
    supplier_watch_pending_evidence,
)
from xti.domain.supplier_risk import build_supplier_risk_card
from xti.domain.supplier_threat_events import supplier_claim_event, supplier_threat_coverage, supplier_claim_name_key


MAX_CONTEXT_ROWS = 20_000
MAX_CONTEXT_BYTES = 16 * 1024 * 1024
MAX_CONTEXT_WORK = 2_000_000
MAX_CONTEXT_EVENTS = 150
MAX_CONTEXT_EVIDENCE = 52
_CATALOG_TABLES = {
    "threatcluster": ("ransomware_claim_runs", "ransomware_claim_run_items"),
    "ransomlook": ("ransomlook_claim_runs", "ransomlook_claim_run_items"),
    "hibp": ("public_notice_runs", "public_notice_changes"),
}
_WATCH_TABLES = ("supplier_watches", "supplier_watch_events", "supplier_watch_runs", "supplier_watch_notifications")


class StoredSupplierContext:
    def __init__(self, connection, *, suppliers, limitations, coverage):
        self.connection, self.suppliers = connection, suppliers
        self.limitations, self.coverage = limitations, coverage
        self.nodes, self.edges = {}, {}
        self.history, self.catalogs = None, {}
        self.prepared = False
        self.rows = self.size = self.work = 0
        self.catalog_costs = {}

    def _measure(self, table, supplier_id=None):
        # Table/column identifiers are exclusively from our fixed schema.
        # Count bytes in ALL columns before materializing untrusted payloads.
        columns = [row[1] for row in self.connection.execute(f'PRAGMA table_info({table})')]
        sizes = '+'.join(f'COALESCE(LENGTH(CAST("{name}" AS BLOB)),0)' for name in columns)
        where, values = (' WHERE supplier_id=?', (supplier_id,)) if supplier_id else ('', ())
        return self.connection.execute(
            f'SELECT COUNT(*),COALESCE(SUM({sizes}),0) FROM {table}{where}', values,
        ).fetchone()

    def _reserve(self, rows, size, work=0):
        if (self.rows + rows > MAX_CONTEXT_ROWS or self.size + size > MAX_CONTEXT_BYTES
                or self.work + work > MAX_CONTEXT_WORK):
            self.limitations.add("supplier_context_read_budget")
            return False
        self.rows += rows
        self.size += size
        self.work += work
        return True

    def _prepare(self):
        if self.prepared:
            return self.history is not None
        self.prepared = True
        counts = [self._measure(table) for table in ('suppliers', 'supplier_events')]
        if (counts[0][0] > supplier_history_limits.MAX_SUPPLIERS
                or counts[1][0] > supplier_history_limits.MAX_SUPPLIER_EVENTS):
            self.limitations.add('supplier_context_read_budget')
            return False
        if not self._reserve(sum(row[0] for row in counts), sum(row[1] for row in counts)):
            return False
        # Full identities are needed for name ambiguity, including historical
        # watch watermarks. They remain inside this ONE company's database.
        self.history = read_supplier_history(self.connection)
        return True

    def _catalog(self, source):
        if source in self.catalogs:
            return self.catalogs[source]
        self.catalogs[source] = None
        runs, changes = (self._measure(table) for table in _CATALOG_TABLES[source])
        if runs[0] > 10_000:
            self.limitations.add('supplier_context_read_budget')
            return None
        # Conservatively bound snapshot replay and hashing as well as bytes.
        work = (runs[0] + 1) * (changes[0] + 1)
        if not self._reserve(runs[0] + changes[0], runs[1] + changes[1], work):
            return None
        catalog = _Catalog(self.connection, source)
        self.catalogs[source] = catalog
        self.catalog_costs[source] = changes[0] + 1
        return catalog

    @staticmethod
    def _runs(catalog):
        runs = tuple(catalog.runs.values())
        return (runs[-1] if runs else None,
                next((run for run in reversed(runs) if run.status == 'complete'), None))

    def _shown(self, rows):
        if len(rows) > MAX_CONTEXT_EVIDENCE:
            self.limitations.add("source_evidence_limit")
        return tuple(rows[:MAX_CONTEXT_EVIDENCE])

    def _add(self, supplier_id, kind, identifier, label, rows, *, total=None):
        source, target = ('supplier', supplier_id), (kind, identifier)
        shown = self._shown(rows)
        self.nodes[target] = ResearchNode(target, label, kind, evidence=shown,
            evidence_total_count=len(rows) if total is None else total)
        return ResearchEdge('supplier-ctx:' + identity(source, target), source, target,
            kind, 'candidate_context' if kind == 'supplier_event' else 'source_context',
            shown[:1], 1 if shown else 0)

    def _risk(self, supplier):
        catalogs = {source: self._catalog(source) for source in ('threatcluster', 'ransomlook')}
        if any(value is None for value in catalogs.values()):
            return [], False
        dependencies = self.suppliers.current_dependencies(supplier.id)
        if dependencies is None:
            return [], False
        count = sum(self.catalog_costs[key] for key in catalogs) + len(self.history.suppliers)
        if not self._reserve(0, 0, count):
            return [], False
        names = Counter(record.name_key for record in self.history.suppliers.values() if record.active)
        coverage, events, source_rows = [], [], []
        for source, catalog in catalogs.items():
            latest, complete = self._runs(catalog)
            coverage.append(supplier_threat_coverage(source_key=source, source_name=_SOURCES[source].name,
                latest=latest, complete=complete))
            source_rows.extend(supplier_source_evidence(_SOURCES[source], latest, complete,
                inventory_time=supplier.created_at))
            if complete is None:
                continue
            record_type = RansomwareClaim if source == 'threatcluster' else RansomLookClaim
            for record in catalog.snapshot(complete.id).values():
                event = supplier_claim_event(supplier, record_type(**record), source_key=source,
                    source_run_id=complete.id, same_name_count=names[supplier_claim_name_key(record["victim"])])
                if event is not None:
                    events.append(event)
        events.sort(key=lambda item: (datetime.fromisoformat(item.discovered_at), item.source_key, item.id), reverse=True)
        card = build_supplier_risk_card(supplier, tuple(coverage), dependencies, tuple(events))
        card_row = supplier_risk_evidence(card, coverage, dependencies)
        result = [self._add(supplier.id, 'supplier_risk', supplier.id,
            f'Tedarikçi inceleme kartı: {supplier.display_name}', [card_row, *source_rows])]
        complete = len(events) <= MAX_CONTEXT_EVENTS
        if not complete:
            self.limitations.add('supplier_context_event_limit')
        self.coverage.append(dict(kind='supplier_claim_candidates', scope=['supplier', supplier.id],
            examined_count=min(len(events), MAX_CONTEXT_EVENTS), window_limit=MAX_CONTEXT_EVENTS,
            complete=complete, order='discovered_at_desc_source_id'))
        for event in events[:MAX_CONTEXT_EVENTS]:
            run = catalogs[event.source_key].runs[event.source_run_id]
            rows = [supplier_event_evidence(event, source_finished_at=run.finished_at)]
            result.append(self._add(supplier.id, 'supplier_event', event.id,
                f'Kaynak iddiası adayı: {event.victim} / {event.group}', rows))
        return result, complete

    def _watches(self, supplier):
        counts = [self._measure(table, supplier.id) for table in _WATCH_TABLES]
        if not any(row[0] for row in counts):
            return [], True
        if not self._reserve(sum(row[0] for row in counts), sum(row[1] for row in counts)):
            return [], False
        sources = [row[0] for row in self.connection.execute(
            'SELECT DISTINCT source_key FROM supplier_watches WHERE supplier_id=?', (supplier.id,))]
        if any(source not in _CATALOG_TABLES for source in sources):
            raise StorageError('Araştırmanın tedarikçi izleme kaynağı geçersiz.')
        catalogs = {source: self._catalog(source) for source in sources}
        if any(value is None for value in catalogs.values()):
            return [], False
        work = (counts[2][0] + counts[0][0] + 1) * (
            len(self.history.events) + sum(self.catalog_costs[source] for source in sources))
        if not self._reserve(0, 0, work):
            return [], False
        state = _audit(self.connection, selected_supplier_id=supplier.id, supplier_history=self.history, catalogs=catalogs)
        current_scope = supplier_scope(self.history, supplier.id)
        result = []
        for watch in sorted(state.watches.values(), key=lambda item: (item.source_key, item.id)):
            event = next(item for item in reversed(tuple(state.events.values())) if item.watch_id == watch.id)
            latest, complete = self._runs(catalogs[watch.source_key])
            rows = [supplier_watch_evidence(watch, event), *supplier_source_evidence(
                _SOURCES[watch.source_key], latest, complete, inventory_time=supplier.created_at)]
            run = next((item for item in reversed(tuple(state.runs.values())) if item.watch_id == watch.id), None)
            total = len(rows)
            if run is not None:
                report = _run_report(state, run, item_limit=MAX_CONTEXT_EVIDENCE)
                applicable = (watch.active and supplier.active and run.watch_event_id == event.id
                    and report.scope['definition_sha256'] == current_scope['definition_sha256']
                    and complete is not None and run.source_run_id == complete.id)
                previous = state.runs.get(run.previous_run_id)
                baseline = (previous is None or previous.watch_event_id != run.watch_event_id or
                    report.previous_scope['definition_sha256'] != report.scope['definition_sha256'])
                status = ('baseline' if baseline else 'changes' if
                    run.added_count + run.updated_count + run.removed_count else 'unchanged')
                if not applicable:
                    status = 'historical_scope'
                rows.append(supplier_watch_run_evidence(report, applicable=applicable, context_status=status))
                rows.extend(supplier_watch_item_evidence(report, item, applicable=applicable) for item in report.items)
                total += 1 + report.total_item_count
            else:
                rows.append(supplier_watch_pending_evidence(watch))
                total += 1
            if total > MAX_CONTEXT_EVIDENCE:
                self.limitations.add('source_evidence_limit')
            result.append(self._add(supplier.id, 'supplier_watch', watch.id,
                f'Tedarikçi izlemesi: {supplier.display_name} / {watch.source_key}', rows, total=total))
        return result, True

    def neighbors(self, key):
        if key[0] != 'supplier':
            return ()
        if key in self.edges:
            return self.edges[key]
        result, complete = [], self._prepare()
        if complete:
            supplier = self.history.suppliers.get(key[1])
            if supplier is None:
                raise StorageError('Araştırmanın tedarikçi kaydı bulunamadı.')
            watched, watch_complete = self._watches(supplier)
            result.extend(watched)
            risk, risk_complete = self._risk(supplier) if supplier.active else ([], True)
            result.extend(risk)
            complete = watch_complete and risk_complete
        self.coverage.append(dict(kind='supplier_monitoring_context', scope=list(key),
            examined_count=len(result), window_limit=MAX_CONTEXT_EVENTS + 4,
            complete=complete, order='source_id'))
        self.edges[key] = tuple(result)
        return self.edges[key]
