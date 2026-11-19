"""Resolve safe, bounded snapshots of existing local evidence records."""

from dataclasses import asdict, replace
from pathlib import Path

from xti.adapters.sqlite_brand_username_reviews import (
    SQLiteBrandUsernameReviewRepository,
)
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.domain.assets import ValidationError
from xti.domain.cases import (
    CaseEvidenceSnapshot,
    canonical_snapshot,
    normalize_case_evidence_id,
    normalize_case_evidence_type,
    PUBLIC_NOTICE_CASE_TYPES, parse_public_notice_case_evidence_id,
    validate_public_notice_case_payload,
)


class SQLiteCaseEvidenceSourceRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @staticmethod
    def _snapshot(
        evidence_type: str, evidence_id: str, display: str,
        source_reference: str, payload: dict,
    ) -> CaseEvidenceSnapshot:
        snapshot_json, digest = canonical_snapshot(payload)
        return CaseEvidenceSnapshot(
            evidence_type=evidence_type,
            evidence_id=evidence_id,
            display_value=display,
            source_reference=source_reference,
            snapshot_json=snapshot_json,
            snapshot_sha256=digest,
        )

    def _finding(self, evidence_id: str) -> CaseEvidenceSnapshot:
        details = SQLiteFindingRepository(self.path).get_finding(evidence_id)
        payload = {
            "kind": "finding",
            "finding": asdict(details.finding),
            "observations": [asdict(item) for item in details.observations],
            "reviews": [asdict(item) for item in details.reviews],
            "limitations": [
                "Bulgu adaydır; tek başına phishing veya kötü niyet kanıtı değildir."
            ],
        }
        return self._snapshot(
            "finding", evidence_id,
            f"{details.finding.domain} — {details.finding.status}",
            "findings show", payload,
        )

    def _social_profile(self, evidence_id: str) -> CaseEvidenceSnapshot:
        details = SQLiteBrandUsernameReviewRepository(self.path).details(
            evidence_id, event_limit=100,
        )
        payload = {
            "kind": "social_profile_review",
            "candidate": asdict(details.candidate),
            "current_review": asdict(details.current),
            "recent_review_events": [asdict(item) for item in details.events],
            "total_review_event_count": details.total_event_count,
            "limitations": [
                "Profil bulunması kimlik sahipliğini veya taklidi kendiliğinden doğrulamaz."
            ],
        }
        display = (
            f"{details.candidate.platform} / {details.candidate.username} — "
            f"{details.current.decision}"
        )
        return self._snapshot(
            "social_profile", evidence_id, display,
            "brand watch-review-show", payload,
        )

    def _threatcluster(self, evidence_id: str) -> CaseEvidenceSnapshot:
        snapshot = SQLiteRansomwareClaimRepository(self.path).latest_snapshot()
        claim = next((item for item in snapshot.claims if item.id == evidence_id), None)
        if claim is None:
            raise ValidationError(
                "Kimlik son başarılı ThreatCluster snapshot'ında bulunamadı."
            )
        payload = {
            "kind": "ransomware_claim",
            "source": "threatcluster",
            "source_run": {
                "id": snapshot.run.id, "sequence": snapshot.run.sequence,
                "finished_at": snapshot.run.finished_at,
                "content_sha256": snapshot.run.content_sha256,
            },
            "claim": asdict(claim),
            "limitations": [
                "Kayıt bir ransomware grubunun kamuya açık iddiasıdır; doğrulanmış ihlal değildir."
            ],
        }
        return self._snapshot(
            "ransomware_threatcluster", evidence_id,
            f"{claim.victim} — {claim.group}", "ransomware status", payload,
        )

    def _ransomlook(self, evidence_id: str) -> CaseEvidenceSnapshot:
        snapshot = SQLiteRansomLookClaimRepository(self.path).latest_snapshot()
        claim = next((item for item in snapshot.claims if item.id == evidence_id), None)
        if claim is None:
            raise ValidationError("Kimlik son başarılı RansomLook snapshot'ında bulunamadı.")
        payload = {
            "kind": "ransomware_claim",
            "source": "ransomlook",
            "source_run": {
                "id": snapshot.run.id, "sequence": snapshot.run.sequence,
                "finished_at": snapshot.run.finished_at,
                "content_sha256": snapshot.run.content_sha256,
            },
            "claim": asdict(claim),
            "limitations": [
                "Kayıt bir ransomware grubunun kamuya açık iddiasıdır; doğrulanmış ihlal değildir."
            ],
        }
        return self._snapshot(
            "ransomware_ransomlook", evidence_id,
            f"{claim.victim} — {claim.group}", "ransomware status --source ransomlook",
            payload,
        )

    def resolve(self, evidence_type: str, evidence_id: str) -> CaseEvidenceSnapshot:
        evidence_type = normalize_case_evidence_type(evidence_type)
        evidence_id = normalize_case_evidence_id(evidence_id)
        if evidence_type == 'relationship_review':
            from xti.adapters.sqlite_relationship_notifications import case_snapshot
            with SQLiteAssetRepository(self.path)._connection(readonly=True) as connection:
                connection.execute('BEGIN')
                return case_snapshot(connection, evidence_id)
        if evidence_type in PUBLIC_NOTICE_CASE_TYPES:
            with SQLiteAssetRepository(self.path)._connection(readonly=True) as connection:
                connection.execute("BEGIN")
                return read_public_notice_case_snapshot(connection, evidence_type, evidence_id)
        if evidence_type == "finding":
            return self._finding(evidence_id)
        if evidence_type == "social_profile":
            return self._social_profile(evidence_id)
        if evidence_type == "ransomware_threatcluster":
            return self._threatcluster(evidence_id)
        if evidence_type == "ransomware_ransomlook":
            return self._ransomlook(evidence_id)
        raise ValidationError("Tedarikçi kartı birleşik vaka çözücüsüyle alınmalı.")



def read_public_notice_case_snapshot(connection, evidence_type, evidence_id):
    """Resolve an exact historical record under the caller's SQLite snapshot."""
    from xti.adapters.sqlite_public_notices import read_public_notice_history
    from xti.adapters.sqlite_public_notice_watches import _Catalog, _audit, _comparison
    from xti.domain.public_notices import HIBP_ATTRIBUTION, HIBP_LICENSE, HIBP_SOURCE_NAME, HIBP_SOURCE_URL, notice_sha256
    if evidence_type not in PUBLIC_NOTICE_CASE_TYPES:
        raise ValidationError("Kamu olay vaka kanıt türü geçersiz.")
    run_id, name = parse_public_notice_case_evidence_id(evidence_id)
    watch_payload = None
    if evidence_type == 'public_notice_watch':
        state = _audit(connection)
        watch_run = state.runs.get(run_id)
        if watch_run is None:
            raise ValidationError("Kamu olay izleme çalışması bulunamadı.")
        comparison = _comparison(state, watch_run)
        selected = tuple(entry for entry in comparison.items if entry.notice_id == name)
        if not selected:
            raise ValidationError("Bu olay seçili tarihî kuruluş izleme çalışmasında bulunamadı.")
        history, catalog = state.source_history, state.catalog
        source_run = catalog.runs[watch_run.source_run_id]
        previous_watch_run = state.runs.get(watch_run.previous_run_id)
        previous = catalog.runs[previous_watch_run.source_run_id] if previous_watch_run else None
        scope = state.scopes[watch_run.id]
        relevant_domains = {entry.domain for entry in selected}
        for entry in selected:
            relevant_domains.update(record.domain for record in (entry.before, entry.after) if record is not None)
        reduced_scope = replace(scope, members=tuple(member for member in scope.members if member.domain in relevant_domains))
        event = state.events[watch_run.watch_event_id]
        watch_payload = {
            'id': watch_run.watch_id, 'organization_id': watch_run.organization_id,
            'revision': event.revision, 'enabled_event_id': event.id,
            'run': asdict(watch_run), 'scope': asdict(reduced_scope),
            'scope_sha256': watch_run.scope_sha256, 'scope_member_count': len(scope.members),
            'scope_complete': len(reduced_scope.members) == len(scope.members),
        }
        entries = [asdict(entry) for entry in selected]
        reference = f'notices watch-run-show {run_id}'
    else:
        history = read_public_notice_history(connection)
        catalog = _Catalog(history)
        source_run = catalog.runs.get(run_id)
        if source_run is None:
            raise ValidationError("Kamu olay kaynak çalışması bulunamadı.")
        if source_run.status != 'complete':
            raise ValidationError("Başarısız kaynak çalışması olay kanıtı olarak bağlanamaz.")
        previous = next((run for run in reversed(history.runs)
                         if run.sequence < source_run.sequence and run.status == 'complete'), None)
        before = catalog.snapshot(previous.id if previous else None).get(name)
        after = catalog.snapshot(run_id).get(name)
        if before is None and after is None:
            raise ValidationError("Bu olay seçili tarihî kaynak çalışmasında bulunamadı.")
        if after is None:
            action = 'removed'
        elif previous is None:
            action = 'baseline'
        elif before is None:
            action = 'added'
        else:
            action = 'unchanged' if notice_sha256(before) == notice_sha256(after) else 'updated'
        entries = [{'notice_id': name, 'action': action, 'domain': (after or before).domain,
                    'before': asdict(before) if before else None, 'after': asdict(after) if after else None}]
        reference = f'notices run-show {run_id}'
    payload = {
        'kind': 'public_notice_historical_evidence', 'version': 1,
        'selection': {'evidence_type': evidence_type, 'run_id': run_id, 'notice_id': name},
        'source': {'name': HIBP_SOURCE_NAME, 'url': HIBP_SOURCE_URL, 'attribution': HIBP_ATTRIBUTION, 'license': HIBP_LICENSE},
        'source_run': asdict(source_run), 'previous_source_run': asdict(previous) if previous else None,
        'is_source_baseline': next(run.id for run in history.runs if run.status == 'complete') == source_run.id,
        'items': entries, 'watch': watch_payload,
        'limitations': [
            'Kaynağın kamu olay metadata kaydıdır; kuruluş için doğrulanmış ihlal veya çalınmış hesap kanıtı değildir.',
            'Başlangıç tarihî katalogdur; eşleşmeden çıkış olayın çözüldüğünü göstermez.',
            'Vaka yalnız seçili tarihî kaydı dondurur; güncel kaynak veya insan kararını değiştirmez.',
            'Kapsam üyeleri seçili olayla ilgili domainlerle sınırlıdır; tam çalışma kapsamının özeti ve toplamı ayrıca korunur.',
        ],
    }
    validate_public_notice_case_payload(evidence_type, evidence_id, payload)
    display = f"{name} | {', '.join(entry['action'] for entry in entries)} | {', '.join(sorted({entry['domain'] or 'domain yok' for entry in entries}))}"
    return SQLiteCaseEvidenceSourceRepository._snapshot(evidence_type, evidence_id, display, reference, payload)
