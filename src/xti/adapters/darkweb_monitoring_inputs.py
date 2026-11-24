"""Frozen P05 inputs from audited local source history; no network access."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_mention_groups import _audit as read_group_state
from xti.adapters.sqlite_organization_scope import read_organization_scope
from xti.adapters.sqlite_public_notices import read_public_notice_snapshot
from xti.adapters.sqlite_ransomware_source_reviews import SQLiteRansomwareSourceReviewRepository
from xti.adapters.sqlite_supplier_history import read_supplier_history
from xti.domain.darkweb_monitoring import DarkwebError, POLICY, profile_definition
from xti.domain.event_candidate_rules import website_domain
from xti.domain.public_notices import (
    HIBP_ATTRIBUTION,
    HIBP_LICENSE,
    HIBP_SOURCE_NAME,
    HIBP_SOURCE_URL,
    notice_sha256,
)
from xti.domain.ransomlook_ransomware import (
    RANSOMLOOK_SOURCE_LICENSE,
    RANSOMLOOK_SOURCE_NAME,
    RANSOMLOOK_SOURCE_URL,
    ransomlook_claim_state_sha256,
)
from xti.domain.ransomware_claims import (
    RANSOMWARE_SOURCE_LICENSE,
    RANSOMWARE_SOURCE_NAME,
    RANSOMWARE_SOURCE_URL,
    ransomware_claim_state_sha256,
)


MAX_TARGETS = 1_000
MAX_SOURCE_RECORDS = 100_000
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
XPOSEDORNOT_DOMAIN_NAME = "XposedOrNot verified-domain exposure"
XPOSEDORNOT_DOMAIN_URL = "https://api.xposedornot.com/v1/domain-breaches/"
XPOSEDORNOT_LICENSE = (
    "XposedOrNot terms apply; personal/low-volume free use, commercial product use "
    "requires the applicable provider plan and terms review"
)
LUNAR_DOMAIN_NAME = "Lunar/Webz.io aggregate domain exposure"
LUNAR_DOMAIN_URL = "https://api.lunarcyber.com/domain-exposure"
LUNAR_DOMAIN_LICENSE = (
    "Webz.io Domain Exposure API terms: free public aggregate use; abusive traffic may be blocked"
)
AIL_TRACKER_NAME = "AIL Framework selected tracker intake"
AIL_TRACKER_URL = "https://www.ail-project.org/"
AIL_TRACKER_LICENSE = (
    "AIL Framework AGPL-3.0; XTI stores only minimized connector metadata and no AIL source code"
)


def _latest_complete(runs):
    return next((run for run in reversed(runs) if run.status == "complete"), None)


def _run_source(key, name, url, license_, runs, snapshots, convert):
    latest = runs[-1] if runs else None
    complete = _latest_complete(runs)
    records = [] if complete is None else [
        convert(record) for _, record in sorted(snapshots.get(complete.id, {}).items())
    ]
    return {
        "key": key,
        "name": name,
        "url": url,
        "license": license_,
        "run_id": complete.id if complete else None,
        "fetched_at": complete.fetched_at if complete else None,
        "latest_status": latest.status if latest else "not_checked",
        "latest_attempt_at": latest.finished_at if latest else None,
        "successful_snapshot_available": complete is not None,
        "records": records,
    }


def _threatcluster(record):
    return {
        "id": record.id,
        "title": record.victim,
        "domain": website_domain(record.website),
        "group": record.group,
        "discovered_at": record.discovered_at,
        "last_seen_at": record.last_seen_at,
        "status": record.status,
        "state_sha256": ransomware_claim_state_sha256(record),
    }


def _ransomlook(record):
    return {
        "id": record.id,
        "title": record.victim,
        "domain": None,
        "group": record.group,
        "discovered_at": record.discovered_at,
        "last_seen_at": None,
        "status": "source_claim",
        "state_sha256": ransomlook_claim_state_sha256(record),
    }


def _notice(record):
    return {
        "id": record.id,
        "title": record.title,
        "domain": record.domain,
        "breach_date": record.breach_date,
        "added_at": record.added_at,
        "modified_at": record.modified_at,
        "verified": record.is_verified,
        "fabricated": record.is_fabricated,
        "sensitive": record.is_sensitive,
        "data_classes": list(record.data_classes),
        "state_sha256": notice_sha256(record),
    }


def _credential_source(connection, organization_id: str) -> dict:
    latest = connection.execute(
        "SELECT * FROM darkweb_credential_runs WHERE organization_id=? "
        "AND provider='xposedornot_domain' "
        "ORDER BY sequence DESC LIMIT 1", (organization_id,),
    ).fetchone()
    complete = connection.execute(
        "SELECT * FROM darkweb_credential_runs WHERE organization_id=? "
        "AND provider='xposedornot_domain' AND status='complete' "
        "ORDER BY sequence DESC LIMIT 1", (organization_id,),
    ).fetchone()
    records = []
    if complete is not None:
        rows = connection.execute(
            "SELECT id,domain,identity_hmac,masked_account,breaches_json,breaches_sha256,state_sha256 "
            "FROM darkweb_credential_accounts WHERE organization_id=? AND active=1 "
            "ORDER BY domain,identity_hmac LIMIT 50001", (organization_id,),
        ).fetchall()
        if len(rows) > 50_000:
            raise DarkwebError("scope_too_large", "Credential kanıtı 50.000 etkin hesap sınırını aşıyor.")
        for row in rows:
            try:
                breaches = json.loads(row[4])
            except (ValueError, RecursionError):
                raise StorageError("Credential kanıt listesi bozuk.") from None
            from xti.domain.content_monitoring import canonical, digest
            if (not isinstance(breaches, list) or canonical(breaches) != row[4]
                    or digest(breaches) != row[5]):
                raise StorageError("Credential kanıt listesi veya özeti bozuk.")
            safe = {"identity_hmac": row[2], "masked_account": row[3],
                    "domain": row[1], "breaches": breaches}
            if digest(safe) != row[6]:
                raise StorageError("Credential kanıt durumu bozuk.")
            records.append({"id": row[0], "organization_id": organization_id,
                            "title": row[3], **safe, "state_sha256": row[6]})
    return {
        "key": "xposedornot_domain", "name": XPOSEDORNOT_DOMAIN_NAME,
        "url": XPOSEDORNOT_DOMAIN_URL, "license": XPOSEDORNOT_LICENSE,
        "run_id": complete["id"] if complete else None,
        "fetched_at": complete["fetched_at"] if complete else None,
        "latest_status": latest["status"] if latest else "not_checked",
        "latest_attempt_at": latest["finished_at"] if latest else None,
        "successful_snapshot_available": complete is not None,
        "records": records,
    }


def _managed_source(connection, organization_id: str, provider: str) -> dict:
    metadata = {
        "lunar_domain": (LUNAR_DOMAIN_NAME, LUNAR_DOMAIN_URL, LUNAR_DOMAIN_LICENSE),
        "ail_tracker": (AIL_TRACKER_NAME, AIL_TRACKER_URL, AIL_TRACKER_LICENSE),
    }
    name, url, license_ = metadata[provider]
    latest_row = connection.execute(
        "SELECT id FROM darkweb_source_runs WHERE organization_id=? AND provider=? "
        "ORDER BY sequence DESC LIMIT 1", (organization_id, provider),
    ).fetchone()
    complete_row = connection.execute(
        "SELECT id FROM darkweb_source_runs WHERE organization_id=? AND provider=? "
        "AND status='complete' ORDER BY sequence DESC LIMIT 1", (organization_id, provider),
    ).fetchone()
    from xti.adapters.sqlite_darkweb_monitoring import source_record_in, source_run_in
    latest = source_run_in(connection, latest_row[0]) if latest_row else None
    complete = source_run_in(connection, complete_row[0]) if complete_row else None
    records = []
    if complete is not None:
        rows = connection.execute(
            "SELECT id FROM darkweb_source_records "
            "WHERE organization_id=? AND provider=? AND active=1 "
            "ORDER BY external_key LIMIT 100001", (organization_id, provider),
        ).fetchall()
        if len(rows) > 100_000:
            raise DarkwebError("scope_too_large", "Dark web kaynak kaydı 100.000 sınırını aşıyor.")
        for row in rows:
            stored = source_record_in(connection, row[0])
            body = stored["body"]
            if provider == "lunar_domain":
                records.append({
                    "id": stored["id"], "organization_id": organization_id,
                    "title": stored["title"], "domain": stored["target_domain"],
                    **{key: body[key] for key in (
                        "period_from", "period_to", "total_events", "infostealer_events",
                        "data_breach_events", "employee_events", "client_events",
                        "first_seen", "last_seen",
                    )}, "state_sha256": stored["state_sha256"],
                })
            else:
                records.append({
                    "id": stored["id"], "organization_id": organization_id,
                    "title": stored["title"], "domain": stored["target_domain"],
                    **{key: body[key] for key in (
                        "match_kind", "match_value", "claim_type", "object_type",
                        "object_subtype", "network", "observed_at", "evidence_sha256",
                    )}, "state_sha256": stored["state_sha256"],
                })
    return {
        "key": provider, "name": name, "url": url, "license": license_,
        "run_id": complete["id"] if complete else None,
        "fetched_at": complete["fetched_at"] if complete else None,
        "latest_status": latest["status"] if latest else "not_checked",
        "latest_attempt_at": latest["finished_at"] if latest else None,
        "successful_snapshot_available": complete is not None,
        "records": records,
    }


class SQLiteDarkwebInputs:
    def __init__(self, path: Path) -> None:
        self.storage = SQLiteAssetRepository(path)

    def capture(self, plan: dict, at: str) -> dict:
        profile = plan["profile"]
        definition = profile_definition(profile["definition"], allow_legacy=True)
        if profile["organization_id"] != definition["organization_id"]:
            raise StorageError("Dark web profili kuruluş kapsamıyla uyuşmuyor.")
        with self.storage._connection(readonly=True) as connection:
            connection.row_factory = __import__("sqlite3").Row
            connection.execute("BEGIN")
            scope = read_organization_scope(connection, definition["organization_id"])
            if not scope.organization.active:
                raise DarkwebError("organization_unavailable", "Dark web izleme kuruluşu etkin değil.")
            domains = sorted({target.value for target in scope.effective_targets
                              if target.kind == "domain"})
            targets = [{
                "kind": "organization", "id": scope.organization.id,
                "label": scope.organization.display_name, "aliases": definition["aliases"],
                "domains": domains, "criticality": "high",
            }]
            if definition["include_suppliers"]:
                group_state = read_group_state(connection)
                history = read_supplier_history(connection)
                supplier_ids = sorted({identifier
                    for group in group_state.groups.values()
                    if group.active and group.definition.organization_id == scope.organization.id
                    for identifier in group.definition.supplier_ids})
                for identifier in supplier_ids:
                    supplier = history.suppliers.get(identifier)
                    if supplier is None:
                        raise StorageError("Dark web profilinin tedarikçi bağı bulunamadı.")
                    if supplier.active:
                        targets.append({
                            "kind": "supplier", "id": supplier.id,
                            "label": supplier.display_name, "aliases": [],
                            "domains": [supplier.primary_domain],
                            "criticality": supplier.criticality,
                        })
            if len(targets) > MAX_TARGETS:
                raise DarkwebError("scope_too_large", "Dark web hedef kapsamı 1.000 kaydı aşıyor.")

            sources = []
            selected = set(definition["sources"])
            if selected & {"threatcluster", "ransomlook"}:
                threat_runs, ransom_runs, threat_snapshots, ransom_snapshots, _, _, _ = (
                    SQLiteRansomwareSourceReviewRepository._audit(connection, compact=True)
                )
                if "threatcluster" in selected:
                    sources.append(_run_source(
                        "threatcluster", RANSOMWARE_SOURCE_NAME, RANSOMWARE_SOURCE_URL,
                        RANSOMWARE_SOURCE_LICENSE, threat_runs, threat_snapshots, _threatcluster,
                    ))
                if "ransomlook" in selected:
                    sources.append(_run_source(
                        "ransomlook", RANSOMLOOK_SOURCE_NAME, RANSOMLOOK_SOURCE_URL,
                        RANSOMLOOK_SOURCE_LICENSE, ransom_runs, ransom_snapshots, _ransomlook,
                    ))
            if "hibp_public" in selected:
                notices = read_public_notice_snapshot(connection)
                latest, complete = notices.latest_run, notices.latest_complete_run
                sources.append({
                    "key": "hibp_public", "name": HIBP_SOURCE_NAME, "url": HIBP_SOURCE_URL,
                    "license": HIBP_LICENSE + "; " + HIBP_ATTRIBUTION,
                    "run_id": complete.id if complete else None,
                    "fetched_at": complete.fetched_at if complete else None,
                    "latest_status": latest.status if latest else "not_checked",
                    "latest_attempt_at": latest.finished_at if latest else None,
                    "successful_snapshot_available": complete is not None,
                    "records": [_notice(record) for record in notices.notices] if complete else [],
                })
            if "xposedornot_domain" in selected:
                sources.append(_credential_source(connection, scope.organization.id))
            for provider in ("lunar_domain", "ail_tracker"):
                if provider in selected:
                    sources.append(_managed_source(connection, scope.organization.id, provider))
            count = sum(len(source["records"]) for source in sources)
            if count > MAX_SOURCE_RECORDS:
                raise DarkwebError("scope_too_large", "Dark web kaynak kapsamı 100.000 kaydı aşıyor.")
            snapshot = {
                "policy": POLICY, "captured_at": at,
                "profile_id": profile["id"], "profile_revision": profile["revision"],
                "definition": definition,
                "organization": {"id": scope.organization.id,
                                 "display_name": scope.organization.display_name,
                                 "domains": domains},
                "targets": targets, "sources": sorted(sources, key=lambda item: item["key"]),
            }
            encoded = json.dumps(snapshot, ensure_ascii=True, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False)
            if len(encoded.encode("ascii")) > MAX_SNAPSHOT_BYTES:
                raise DarkwebError("scope_too_large", "Dark web dondurulmuş girdisi 64 MiB sınırını aşıyor.")
            return snapshot
