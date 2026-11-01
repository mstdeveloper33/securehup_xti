"""Versioned evidence for measuring a second social username source."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BrandSourceCoverageSource:
    identifier: str
    label: str
    role: str
    version: str
    upstream_commit: str
    catalog_sha256: str
    catalog_bytes: int
    catalog_entries: int
    eligible_entries: int
    current_approved_platforms: int
    license: str
    reference_url: str


@dataclass(frozen=True, slots=True)
class BrandSourceCoverageComparison:
    shared_candidate_entries: int
    candidate_unmatched_entries: int
    candidate_unmatched_distinct_hosts: int
    candidate_unmatched_distinct_registrable_domains: int
    current_approved_total: int
    current_shared_platforms: int
    current_primary_only: tuple[str, ...]
    current_candidate_only: tuple[str, ...]
    method_notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BrandSourceCoverageCriterion:
    key: str
    label: str
    required: bool
    passed: bool
    evidence: str


@dataclass(frozen=True, slots=True)
class BrandSourceCoverageShortlistItem:
    platform: str
    host: str
    purpose: str


@dataclass(frozen=True, slots=True)
class BrandSourceCoverageReport:
    profile_version: str
    profile_sha256: str
    evaluated_at: str
    matching_rule_version: str
    public_suffix_version: str
    public_suffix_sha256: str
    sources: tuple[BrandSourceCoverageSource, ...]
    comparison: BrandSourceCoverageComparison
    criteria: tuple[BrandSourceCoverageCriterion, ...]
    decision: str
    decision_reason: str
    shortlist: tuple[BrandSourceCoverageShortlistItem, ...]
    next_step: str
    limitations: tuple[str, ...]
    reference_urls: tuple[str, ...]
