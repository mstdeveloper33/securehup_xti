"""Report context, read from the caller's workspace transaction with explicit bounds."""

from xti.adapters.research_read_budget import ResearchReadBudget
from xti.adapters.sqlite_reports import read_reports
from xti.domain.research_reports import bindings, document_node, document_id, report_edge


MAX_REPORT_READ_BYTES = 16 * 1024 * 1024
MAX_REPORT_READ_ROWS = 10000
MAX_REPORT_ADJACENCY = 200
MAX_REPORT_BINDINGS = 50000


class StoredReportContext:
    def __init__(self, connection, *, limitations, coverage):
        self.connection, self.limitations, self.coverage = connection, limitations, coverage
        self.records, self.nodes, self.adjacency = None, {}, {}
        self.remaining = MAX_REPORT_BINDINGS

    def load(self):
        if self.records is not None:
            return
        self.records = {}
        admitted = ResearchReadBudget(self.connection, self.limitations,
            rows=MAX_REPORT_READ_ROWS, size=MAX_REPORT_READ_BYTES).admit(('report_journal',), 'report_read_budget')
        if admitted:
            self.records, _, _ = read_reports(self.connection)
        self.coverage.append(dict(kind='report_documents', scope='workspace',
            examined_count=sum(len(record['documents']) for record in self.records.values()),
            window_limit=MAX_REPORT_READ_ROWS, byte_limit=MAX_REPORT_READ_BYTES,
            complete=admitted, order='report_id_document_revision_desc'))

    def neighbors(self, key):
        if key in self.adjacency:
            return self.adjacency[key]
        self.load()
        rows, complete = [], True
        # Only incident edges are constructed. The stored journal bounds the
        # scan; up to 200 candidates per document never expand into a full graph.
        for rid, record in sorted(self.records.items()):
            for revision in range(len(record['documents']), 0, -1):
                document_key = ('report_document', document_id(rid, revision))
                if key[0] == 'report_document' and key != document_key:
                    continue
                for target, relationship, detail in bindings(record, revision):
                    if self.remaining == 0:
                        self.limitations.add('report_work_budget')
                        complete = False
                        break
                    self.remaining -= 1
                    if key not in (document_key, target):
                        continue
                    if len(rows) == MAX_REPORT_ADJACENCY:
                        self.limitations.add('report_adjacency_limit')
                        complete = False
                        break
                    if document_key not in self.nodes:
                        self.nodes[document_key] = document_node(record, revision)
                    node = self.nodes[document_key]
                    edge = report_edge(record, revision, node, target, relationship, detail)
                    rows.append(edge)
                    if edge.evidence_total_count > len(edge.evidence):
                        self.limitations.add('source_evidence_limit')
                if not complete:
                    break
            if not complete:
                break
        self.coverage.append(dict(kind='report_links', scope=list(key), examined_count=len(rows),
            window_limit=MAX_REPORT_ADJACENCY, complete=complete, order='report_id_document_revision_desc'))
        result = tuple(sorted(rows, key=lambda row: row.id))
        self.adjacency[key] = result
        return result
