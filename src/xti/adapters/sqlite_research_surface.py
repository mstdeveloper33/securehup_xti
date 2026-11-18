"""Bounded saved surface links on the research reader's existing transaction."""

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_cname import SQLiteSurfaceCnameRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.domain.assets import normalize_domain
from xti.domain.research import ResearchEdge, ResearchNode, identity
from xti.domain.research_surface import cname_evidence, cname_links, certificate_evidence


MAX_CNAME_CHECKS = 1000
MAX_CNAME_BYTES = 16 * 1024 * 1024
MAX_SURFACE_RELATIONS = 200
MAX_SURFACE_EVIDENCE = 50


class StoredSurfaceLinks:
    def __init__(self, connection, *, web_checks, limitations, coverage):
        self.connection, self.web_checks = connection, web_checks
        self.limitations, self.coverage = limitations, coverage
        self.checks, self.scopes, self.latest = {}, {}, {}
        self.read_bytes = 0

    def _load(self, row):
        identifier, asset_id, domain, size = row
        if identifier in self.checks:
            return self.checks[identifier]
        if len(self.checks) >= MAX_CNAME_CHECKS or self.read_bytes + size > MAX_CNAME_BYTES:
            self.limitations.add("cname_read_budget")
            return None
        self.read_bytes += size
        stored = self.connection.execute(
            "SELECT id,asset_id,?,result,state_sha256,change,recorded_at FROM surface_cname_checks WHERE id=?",
            (domain, identifier),
        ).fetchone()
        check = SQLiteSurfaceCnameRepository._check(stored, domain)
        if normalize_domain(domain) != domain or check.asset_id != asset_id:
            raise StorageError("Araştırmanın CNAME varlık bağlantısı tutarsız.")
        scope = SQLiteSurfaceRepository._scope_row(self.connection, asset_id)
        if scope is None or SQLiteSurfaceRepository._scope(scope).asset_value != domain:
            raise StorageError("Araştırmanın CNAME kapsam kaydı eksik veya tutarsız.")
        self.checks[identifier] = check
        return check

    def cname_checks(self, domain=None):
        if domain in self.scopes:
            return self.scopes[domain]
        where, values = ("WHERE a.value=?", (domain,)) if domain else ("", ())
        rows = self.connection.execute(
            "SELECT s.id,s.asset_id,a.value,LENGTH(CAST(s.result AS BLOB))+LENGTH(CAST(s.change AS BLOB)) "
            "FROM surface_cname_checks s LEFT JOIN assets a ON a.id=s.asset_id " + where +
            " ORDER BY s.rowid DESC LIMIT ?", (*values, MAX_CNAME_CHECKS + 1),
        ).fetchall()
        if len(rows) > MAX_CNAME_CHECKS:
            self.limitations.add("cname_history_window")
        checks = []
        self.latest[domain] = None
        for index, row in enumerate(rows[:MAX_CNAME_CHECKS]):
            check = self._load(row)
            if index == 0:
                # Never promote an older readable observation to latest.
                self.latest[domain] = check
            if check is not None:
                checks.append(check)
        self.coverage.append({"kind": "cname", "scope": domain or "workspace_recent_checks",
            "examined_count": len(checks), "window_limit": MAX_CNAME_CHECKS,
            "complete": len(rows) <= MAX_CNAME_CHECKS and len(checks) == len(rows),
            "order": "stored_newest_first"})
        self.scopes[domain] = tuple(checks)
        return tuple(checks)

    def latest_cname_evidence(self, domain):
        self.cname_checks(domain)
        check = self.latest[domain]
        return cname_evidence(check) if check is not None else None

    def _edges(self, key, observations, *, prefix, limit_code):
        grouped = {}
        for source, target, relationship, evidence in observations:
            if key not in (source, target):
                continue
            binding = source, target, relationship
            if binding not in grouped and len(grouped) >= MAX_SURFACE_RELATIONS:
                self.limitations.add(limit_code)
                continue
            count, rows = grouped.setdefault(binding, [0, []])
            grouped[binding][0] = count + 1
            if len(rows) < MAX_SURFACE_EVIDENCE:
                rows.append(evidence)
            else:
                self.limitations.add("source_evidence_limit")
        return tuple(ResearchEdge(prefix + identity(relationship, source, target), source, target,
            relationship, "observation", tuple(rows), count)
            for (source, target, relationship), (count, rows) in sorted(grouped.items()))

    def cname_edges(self, key):
        if key[0] not in {"domain", "ipv4", "ipv6"}:
            return ()
        # Reverse lookup must include checks whose ORIGINAL domain differs
        # from the searched target. It remains a bounded recent window.
        recent = self.cname_checks()
        checks = {check.id: check for check in (*recent, *self.checks.values())}
        observations = ((source, target, relationship, cname_evidence(check, observation=True))
            for check in checks.values() for source, target, relationship in cname_links(check)
            if key in (source, target))
        return self._edges(key, observations, prefix="cname:", limit_code="cname_adjacency_limit")

    def certificate_edges(self, key):
        if key[0] not in {"domain", "certificate"}:
            return ()
        checks = self.web_checks(key[1] if key[0] == "domain" else None)
        observations = ((("domain", check.result.domain), ("certificate", check.result.certificate.sha256),
                         "certificate_presented", certificate_evidence(check))
                        for check in checks if check.result.certificate is not None and
                        key in (("domain", check.result.domain), ("certificate", check.result.certificate.sha256)))
        return self._edges(key, observations, prefix="tls:", limit_code="certificate_adjacency_limit")

    def certificate_node(self, key):
        # This is a peer-certificate identity, never a file hash indicator.
        checks = [check for check in self.web_checks() if check.result.certificate is not None
                  and check.result.certificate.sha256 == key[1]]
        if len(checks) > MAX_SURFACE_EVIDENCE:
            self.limitations.add("source_evidence_limit")
        return ResearchNode(key, "TLS SHA-256 " + key[1], "tls_certificate",
            evidence=tuple(certificate_evidence(check) for check in checks[:MAX_SURFACE_EVIDENCE]),
            evidence_total_count=len(checks))
