"""Preflight stored bytes before invoking existing replay readers."""


class ResearchReadBudget:
    def __init__(self, connection, limitations, *, rows=20_000, size=16 * 1024 * 1024):
        self.connection, self.limitations = connection, limitations
        self.rows, self.size, self.checked = rows, size, set()

    def admit(self, tables, reason):
        pending, rows, size = [], 0, 0
        for table in tables:
            # Table names come exclusively from adapter constants.
            if table in self.checked:
                continue
            columns = self.connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            expression = '+'.join(f'COALESCE(LENGTH(CAST("{column[1]}" AS BLOB)),0)' for column in columns)
            count, length = self.connection.execute(
                f'SELECT COUNT(*),COALESCE(SUM({expression}+128),0) FROM "{table}"'
            ).fetchone()
            if table in ('report_journal', 'evidence_journal'):
                from xti.adapters.compressed_evidence import logical_extra
                length += logical_extra(self.connection, table)
            pending.append(table)
            rows, size = rows + count, size + length
        if rows > self.rows or size > self.size:
            self.limitations.add(reason)
            return False
        self.rows, self.size = self.rows - rows, self.size - size
        self.checked.update(pending)
        return True
