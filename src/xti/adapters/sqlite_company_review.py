"""Company-wide bounded roots with a shared SQLite read transaction."""

from xti.adapters.sqlite_research import SQLiteResearchRepository
from xti.domain.research import ResearchQuery, build_research
from xti.domain.research_priority import prioritize_research


class SQLiteCompanyReviewRepository:
    def __init__(self, path):
        self.repository = SQLiteResearchRepository(path)

    def read(self, *, checked_at, stale_after_hours, root_offset, root_limit):
        with self.repository.open(None, checked_at) as reader:
            reader.case_context.load()
            reader.content_context.load()
            reader.investigation_context.load()
            # A single UNION query bounds payload transfer. COUNT does not load
            # a potentially large indicator catalog into Python.
            sql = ("SELECT 'domain' AS kind,value FROM assets UNION SELECT indicator_type,value FROM cti_indicators "
                   "UNION SELECT 'entity',id FROM cti_entities")
            total = reader.connection.execute('SELECT COUNT(*) FROM (' + sql + ')').fetchone()[0]
            context_roots = sorted(set(reader.case_context.nodes) | set(reader.content_context.nodes) | set(reader.investigation_context.nodes))
            reader.sightings.evidence(('domain', ''))  # Audited once; no external query.
            sighting_roots = []
            for kind, value in reader.sightings.index:
                if not (reader.connection.execute('SELECT 1 FROM cti_indicators WHERE indicator_type=? AND value=?', (kind, value)).fetchone() or
                        kind == 'domain' and reader.connection.execute('SELECT 1 FROM assets WHERE value=?', (value,)).fetchone()):
                    sighting_roots.append((kind, value))
            context_roots = sorted(set(context_roots) | set(sighting_roots))
            # Stable order: inventory/IOC roots, then independent local review
            # records so cases without a domain are not silently excluded.
            roots = reader.connection.execute(sql + ' ORDER BY kind,value LIMIT ? OFFSET ?',
                (root_limit, root_offset)).fetchall() if root_offset < total else []
            remaining = root_limit - len(roots)
            if remaining:
                start = max(0, root_offset - total)
                roots.extend(context_roots[start:start + remaining])
            root_total = total + len(context_roots)
            reviews = []
            for kind, value in roots:
                query = ResearchQuery(kind, value, max_hops=2, node_limit=30, edge_limit=60,
                                      stale_after_hours=stale_after_hours)
                reviews.append(prioritize_research(build_research(reader, query, checked_at, paginate=False), paginate=False))
            limited = root_offset != 0 or len(roots) < root_total
            if limited:
                reader.limitations.add('company_root_window')
            return {'reviews': reviews, 'checked_at': checked_at,
                'root_total_count': root_total, 'root_examined_count': len(roots), 'root_offset': root_offset,
                'root_limit': root_limit, 'root_has_more': root_offset + len(roots) < root_total,
                'next_root_offset': root_offset + len(roots) if root_offset + len(roots) < root_total else None,
                'coverage_complete': not reader.limitations, 'limitations': sorted(reader.limitations)}
