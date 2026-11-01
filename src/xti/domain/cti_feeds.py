"""Complete-snapshot CTI feed records and deterministic provenance."""

from dataclasses import dataclass
import hashlib
import json

from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import (
    normalize_confidence,
    normalize_cti_timestamp,
    normalize_indicator_description,
    normalize_indicator_type,
    normalize_indicator_value,
    normalize_source_name,
    normalize_source_reference,
)


FEODO_SOURCE = "feodo-tracker"
FEODO_URL = "https://feodotracker.abuse.ch/downloads/ipblocklist.json"
FEODO_CONFIDENCE = 50
CERTPL_SOURCE = "certpl-warning-list"
CERTPL_URL = "https://hole.cert.pl/domains/v2/domains_ublock.txt"
CERTPL_CONFIDENCE = 50
FEED_RUN_STATUSES = {"complete", "failed"}
FEED_ITEM_ACTIONS = {
    "added", "observed", "updated", "unchanged", "reactivated", "revoked",
}


@dataclass(frozen=True, slots=True)
class CtiFeedPolicy:
    """Static trust and storage rules for one complete-snapshot source."""

    cli_name: str
    source_name: str
    label: str
    source_url: str
    confidence: int
    maximum_records: int
    indicator_types: tuple[str, ...]
    reference_template: str | None
    preserve_active_observation_time: bool
    record_unchanged_items: bool
    retraction_reason: str
    notes: tuple[str, ...]

    def source_reference(self, indicator_type: str, value: str) -> str:
        if indicator_type not in self.indicator_types:
            raise ValidationError("IOC beslemesi gösterge türü kaynak politikasıyla uyumsuz.")
        if self.reference_template is None:
            return self.source_url
        return self.reference_template.format(value=value)


FEODO_POLICY = CtiFeedPolicy(
    cli_name="feodo",
    source_name=FEODO_SOURCE,
    label="Feodo Tracker",
    source_url=FEODO_URL,
    confidence=FEODO_CONFIDENCE,
    maximum_records=50_000,
    indicator_types=("ipv4", "ipv6"),
    reference_template="https://feodotracker.abuse.ch/browse/host/{value}/",
    preserve_active_observation_time=False,
    record_unchanged_items=True,
    retraction_reason="Feodo Tracker tam IOC snapshot'ında kayıt artık bulunmuyor.",
    notes=(
        "Feodo Tracker 30 günlük, saldırgan olmayan tam IOC listesi kullanılır.",
        "50/100 güven puanı kaynak verisi değil, XTI yerel nötr politikasıdır.",
        "Kayıtlar otomatik engelleme kararı değildir; analist doğrulaması gerekir.",
    ),
)

CERTPL_POLICY = CtiFeedPolicy(
    cli_name="certpl",
    source_name=CERTPL_SOURCE,
    label="CERT Polska Warning List",
    source_url=CERTPL_URL,
    confidence=CERTPL_CONFIDENCE,
    maximum_records=50_000,
    indicator_types=("domain",),
    reference_template=None,
    preserve_active_observation_time=True,
    record_unchanged_items=False,
    retraction_reason=(
        "Domain CERT Polska son bir aylık etkin Warning List diliminde artık bulunmuyor."
    ),
    notes=(
        "CERT Polska Warning List'in son bir ayda eklenen etkin domain dilimi kullanılır.",
        "Liste ağırlıklı olarak Polonya kullanıcılarını hedefleyen aldatıcı domainleri kapsar; küresel kapsam değildir.",
        "50/100 güven puanı kaynak verisi değil, XTI yerel nötr politikasıdır.",
        "Kayıtlar otomatik engelleme kararı değildir; kaynak da tamlık veya güncellik garantisi vermez.",
    ),
)

CTI_FEED_POLICIES = {
    FEODO_POLICY.cli_name: FEODO_POLICY,
    CERTPL_POLICY.cli_name: CERTPL_POLICY,
}


def feed_indicator_state_sha256(
    *, indicator_type: str, value: str, source_reference: str, confidence: int,
    description: str, valid_from: str, last_seen_at: str,
) -> str:
    """Hash normalized feed state, independent from local database identities."""
    indicator_type = normalize_indicator_type(indicator_type)
    value = normalize_indicator_value(indicator_type, value)
    payload = {
        "confidence": normalize_confidence(confidence),
        "description": normalize_indicator_description(description),
        "indicator_type": indicator_type,
        "last_seen_at": normalize_cti_timestamp(
            last_seen_at, field="IOC son gözlem zamanı",
        ),
        "source_reference": normalize_source_reference(source_reference),
        "valid_from": normalize_cti_timestamp(
            valid_from, field="IOC geçerlilik başlangıcı",
        ),
        "value": value,
    }
    canonical = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def validate_sha256(value: str, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValidationError(f"{field} geçerli SHA-256 özeti olmalı.")
    return value


@dataclass(frozen=True, slots=True)
class CtiFeedIndicator:
    indicator_type: str
    value: str
    source_reference: str
    confidence: int
    description: str
    valid_from: str
    last_seen_at: str
    state_sha256: str


@dataclass(frozen=True, slots=True)
class CtiFeedSnapshot:
    source_name: str
    source_url: str
    content_sha256: str
    source_record_count: int
    indicators: tuple[CtiFeedIndicator, ...]


@dataclass(frozen=True, slots=True)
class CtiFeedRun:
    id: str
    sequence: int
    source_name: str
    status: str
    source_url: str
    content_sha256: str | None
    started_at: str
    finished_at: str
    source_record_count: int
    indicator_count: int
    added_count: int
    observed_count: int
    updated_count: int
    unchanged_count: int
    reactivated_count: int
    revoked_count: int
    error: str | None


@dataclass(frozen=True, slots=True)
class CtiFeedStatus:
    source_name: str
    source_label: str
    active_assertion_count: int
    total_indicator_count: int
    latest_run: CtiFeedRun | None
    recent_runs: tuple[CtiFeedRun, ...]
    notes: tuple[str, ...]

