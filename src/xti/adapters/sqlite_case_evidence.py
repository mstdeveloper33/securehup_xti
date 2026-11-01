"""Resolve safe, bounded snapshots of existing local evidence records."""

from dataclasses import asdict
from pathlib import Path

from xti.adapters.sqlite_brand_username_reviews import (
    SQLiteBrandUsernameReviewRepository,
)
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.domain.assets import ValidationError
from xti.domain.cases import (
    CaseEvidenceSnapshot,
    canonical_snapshot,
    normalize_case_evidence_id,
    normalize_case_evidence_type,
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
        if evidence_type == "finding":
            return self._finding(evidence_id)
        if evidence_type == "social_profile":
            return self._social_profile(evidence_id)
        if evidence_type == "ransomware_threatcluster":
            return self._threatcluster(evidence_id)
        if evidence_type == "ransomware_ransomlook":
            return self._ransomlook(evidence_id)
        raise ValidationError("Tedarikçi kartı birleşik vaka çözücüsüyle alınmalı.")

