#!/usr/bin/env python3
"""P04 accumulated capacity acceptance; creates only a temporary local dataset."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import resource
import statistics
import sys
import tempfile
import time
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_cti_analysis import SQLiteCtiAnalysisRepository, company_in
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.application.cti_analysis import CtiAnalysisService
from xti.domain.cti_analysis import PREFIX, profile_definition


CANDIDATES = 10_000
UNCHANGED_RUNS = 30
READS = 40


class Inputs:
    def __init__(self, organization_id: str, label: str):
        self.organization_id, self.label = organization_id, label
        at = datetime(2026, 11, 21, tzinfo=timezone.utc).isoformat()
        entities = []
        for index in range(CANDIDATES):
            identifier = str(uuid5(NAMESPACE_URL, f"p04:{label}:entity:{index}"))
            assertion_id = str(uuid5(NAMESPACE_URL, f"p04:{label}:assertion:{index}"))
            entities.append({"id": identifier, "entity_type": "campaign",
                "display_name": f"Synthetic {index:05d}", "assertions": [{
                    "id": assertion_id, "source_name": "capacity-fixture",
                    "source_reference": f"fixture:p04:{label}:{index}", "confidence": 80,
                    "description": "finance", "last_seen_at": at, "aliases": []}]})
        self.snapshot = {"policy": "cti-analysis-v1", "captured_at": at,
            "profile_id": "", "profile_revision": 1, "definition": {},
            "organization": {"id": organization_id, "display_name": label,
                             "domains": [label + ".example"]},
            "entities": entities, "relationships": [], "indicators": [],
            "attack": {"run_id": None, "version": None, "content_sha256": None,
                       "entities": [], "relationships": [], "phases": []},
            "accepted_identity_links": []}

    def capture(self, plan, accepted, at):
        value = deepcopy(self.snapshot)
        value.update(captured_at=at, profile_id=plan["profile"]["id"],
                     profile_revision=plan["profile"]["revision"],
                     definition=plan["definition"], accepted_identity_links=deepcopy(accepted))
        return value


def percentile(values, percentage):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(len(ordered) * percentage) - 1))]


def rss_mib():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports KiB.
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


def run_company(root: Path, label: str) -> dict:
    path = root / label / "xti.db"
    SQLiteAssetRepository(path).initialize()
    base = datetime(2026, 11, 21, tzinfo=timezone.utc)
    organization = SQLiteOrganizationRepository(path).add(
        name_key=label, display_name=label.title(), reason="P04 capacity acceptance",
        recorded_at=base.isoformat()).organization
    clock = [base]
    repository = SQLiteCtiAnalysisRepository(path)
    service = CtiAnalysisService(repository, Inputs(organization.id, label),
                                 now=lambda: clock[0].isoformat())
    profile = service.execute(PREFIX + "profile.add", name="P04 capacity",
        organization_id=organization.id, max_entities=CANDIDATES,
        max_candidates=CANDIDATES, max_relationships=1,
        source_policies=[{"source_name": "capacity-fixture", "reliability": 80,
                          "independence_group": "capacity-fixture"}],
        idempotency_key="profile")

    timings = []
    for index in range(UNCHANGED_RUNS + 1):
        clock[0] += timedelta(minutes=10)
        started = time.perf_counter()
        run = service.execute(PREFIX + "run", identifier=profile["id"],
            expected_revision=1, force=True, idempotency_key=f"run:{index}")
        timings.append(time.perf_counter() - started)
        if index == 0:
            assert run["report"]["new_candidates"] == CANDIDATES
            assert run["report"]["silent_baseline"]
        else:
            assert run["report"]["new_evidence"] == 0
            assert run["report"]["changed_candidates"] == 0
            assert run["report"]["notifications"] == 0
            assert run["report"]["unchanged_candidates"] == CANDIDATES

    read_times = []
    for index in range(READS):
        started = time.perf_counter()
        if index % 2:
            service.execute(PREFIX + "candidates", profile_id=profile["id"],
                            after=(index % 10) * 100, limit=100)
        else:
            with repository.connection() as connection:
                company_in(connection, organization.id, offset=(index % 10) * 100, limit=100)
        read_times.append(time.perf_counter() - started)
    report = service.execute(PREFIX + "report", profile_id=profile["id"])
    assert report["candidate_counts"] == {"tag": CANDIDATES}
    return {"company": label, "candidates": CANDIDATES,
        "total_runs": UNCHANGED_RUNS + 1,
        "unchanged_runs": UNCHANGED_RUNS,
        "run_seconds": {"median": statistics.median(timings), "maximum": max(timings)},
        "read_seconds": {"p95": percentile(read_times, .95), "maximum": max(read_times)}}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="xti-p04-capacity-") as temporary:
        root = Path(temporary)
        results = [run_company(root, label) for label in ("company-alpha", "company-beta")]
        maximum_p95 = max(item["read_seconds"]["p95"] for item in results)
        memory = rss_mib()
        if maximum_p95 >= 2:
            raise SystemExit(f"P04 read p95 exceeded 2 seconds: {maximum_p95:.3f}")
        if memory >= 256:
            raise SystemExit(f"P04 peak RSS exceeded 256 MiB: {memory:.1f}")
        print(json.dumps({"ok": True, "policy": "p04-capacity-v1",
            "companies": results, "peak_rss_mib": round(memory, 2),
            "read_p95_limit_seconds": 2, "rss_limit_mib": 256},
            ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
