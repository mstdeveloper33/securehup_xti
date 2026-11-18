"""Supplier source claims, local comparisons and derived review context.

These conversions retain original identities. A match, a local notification,
and an analyst's supplier inventory are never promoted to a confirmed breach.
"""

from dataclasses import asdict
from datetime import datetime

from xti.domain.research import ResearchEvidence, identity
from xti.domain.supplier_watches import supplier_watch_hash


def supplier_source_evidence(source, latest, complete, *, inventory_time):
    if complete is None:
        state = "not_collected" if latest is None else "unavailable"
    else:
        state = "stale_after_failure" if latest.id != complete.id else "available"
    timestamp = latest.finished_at if latest else inventory_time
    rows = [ResearchEvidence(
        "supplier_source_coverage", source.source_key, source.source_key, source.url,
        "source_context", state, timestamp, timestamp,
        f"{source.name}; son deneme: {latest.id if latest else 'yok'}; "
        f"korunan başarılı yanıt: {complete.id if complete else 'yok'}. "
        "Kaynak kapsamıdır; eşleşme veya güvenli olma sonucu değildir. "
        f"Atıf: {source.attribution}; kullanım: {source.license}",
        state_sha256=identity(source.source_key, asdict(latest) if latest else None,
                              asdict(complete) if complete else None),
        source_run_id=latest.id if latest else None,
        time_basis="source_response_received_at" if latest else "inventory_recorded_at",
    )]
    for run in (latest, complete if complete != latest else None):
        if run is None:
            continue
        rows.append(ResearchEvidence(
            "supplier_source_run", run.id, source.source_key, source.url, "source_context",
            run.status, run.fetched_at or run.finished_at, run.finished_at,
            f"{source.name}; {'son deneme' if run == latest else 'korunan önceki başarılı yanıt'}; "
            f"çalışma: {run.id}; hata: {run.error or 'yok'}.",
            current=run == latest, state_sha256=identity(asdict(run)), source_run_id=run.id,
            time_basis="source_response_received_at",
        ))
    return tuple(rows)


def supplier_risk_evidence(card, coverage, dependencies):
    timestamp = max((card.supplier.updated_at, *(item.updated_at for item in dependencies),
        *(item.latest_attempt_finished_at for item in coverage if item.latest_attempt_finished_at)),
        key=datetime.fromisoformat)
    return ResearchEvidence(
        "supplier_risk_context", card.supplier.id, "local-supplier-risk", card.supplier.id,
        "source_context", card.attention, timestamp, timestamp,
        f"Hesaplanan inceleme kartı: {card.attention}; aday: {card.claim_candidate_count}; "
        f"domain dayanaklı: {card.domain_evidence_count}; yalnız ad: {card.name_only_evidence_count}; "
        f"belirsiz ad: {card.ambiguous_name_count}; güncel insan onaylı bağımlılık: {card.current_dependency_count}. "
        + " ".join((*card.reasons, *card.missing_data, *card.next_actions)) +
        " Bu türetilmiş görünüm ayrı bir kalıcı risk kaydı, doğrulanmış ihlal veya müşteri etkisi değildir.",
        current=True, state_sha256=identity(asdict(card), [asdict(item) for item in coverage],
            [asdict(item) for item in dependencies]), time_basis="stored_context_updated_at",
    )


def supplier_event_evidence(event, *, source_finished_at):
    domain = any(item.field == "website" for item in event.match_evidence)
    status = "domain_match" if domain else "ambiguous_name" if event.same_name_supplier_count > 1 else "name_match"
    return ResearchEvidence(
        "supplier_threat_match", event.id, event.source_key, event.claim_id,
        "candidate_context", status, event.discovered_at, source_finished_at,
        f"Kaynak iddiası adayı: {event.group} / {event.victim}; tedarikçi: {event.supplier_name} "
        f"({event.supplier_domain}); " + "; ".join(f"{m.field}:{m.match_type}={m.value}" for m in event.match_evidence) +
        f"; aynı adı taşıyan etkin tedarikçi: {event.same_name_supplier_count}; "
        f"kaynak durumu: {event.claim_status or 'belirtilmedi'}; özgün kayıt özeti: {event.claim_state_sha256}. "
        "Bu eşleşme doğrulanmış ihlal veya tedarikçinin müşteriye etkisi değildir.",
        current=True, state_sha256=identity(asdict(event)), source_run_id=event.source_run_id,
        first_observed_at=event.discovered_at,
    )


def supplier_watch_evidence(watch, event):
    return ResearchEvidence(
        "supplier_watch", watch.id, "local-supplier-watches", watch.supplier_id,
        "human_decision", "enabled" if watch.active else "disabled",
        event.recorded_at, event.recorded_at,
        f"Kaynak: {watch.source_key}; insanın izleme tercihi: {event.action}; gerekçe: {event.reason}.",
        event_id=event.id, current=True, state_sha256=identity(asdict(watch), asdict(event)),
        time_basis="decision_recorded_at",
    )


def supplier_watch_pending_evidence(watch):
    return ResearchEvidence(
        'supplier_watch_pending', watch.id, 'local-supplier-watches', watch.id,
        'source_context', 'not_evaluated', watch.updated_at, watch.updated_at,
        'Bu izleme için kayıtlı karşılaştırma henüz yok; sıfır eşleşme sonucu değildir.',
        state_sha256=identity(asdict(watch), 'not_evaluated'), time_basis='watch_configured_at',
    )


def supplier_watch_run_evidence(report, *, applicable, context_status):
    run, scope = report.run, report.scope
    return ResearchEvidence(
        "supplier_watch_run", run.id, run.source_key, run.watch_id, "source_context", context_status,
        report.source_run.get("fetched_at") or run.recorded_at, run.recorded_at,
        f"Özgün yerel karşılaştırma: {run.id}; tarihî tedarikçi: {scope['supplier']['display_name']} "
        f"({scope['supplier']['primary_domain']}); o tarihte aynı ad: {scope['same_name_supplier_count']}; "
        f"başlangıç={run.baseline_count}, yeni={run.added_count}, değişen={run.updated_count}, "
        f"çıkarılan={run.removed_count}, aynı={run.unchanged_count}; "
        f"yerel bildirim: {report.notification_id or 'yok'}; sonuç özeti: {run.result_sha256}. "
        "İlk ölçüm sessiz başlangıçtır; kaynak listesinden çıkarılma çözülmüş ihlal değildir.",
        event_id=report.notification_id, current=applicable,
        state_sha256=identity(asdict(run), scope, context_status), source_run_id=run.source_run_id,
        time_basis="source_response_received_at",
    )


def supplier_watch_item_evidence(report, item, *, applicable):
    # Keep the original record ID and before/after hashes. Full safe metadata
    # remains reachable through the immutable watch-run-show report.
    record = item.after or item.before
    matched = item.match_after or item.match_before
    before = supplier_watch_hash(item.before) if item.before else "yok"
    after = supplier_watch_hash(item.after) if item.after else "yok"
    return ResearchEvidence(
        "supplier_watch_item", item.record_id, report.run.source_key, report.run.id,
        "candidate_context", item.action,
        report.source_run.get("fetched_at") or report.run.recorded_at, report.run.recorded_at,
        f"{record.get('victim', record.get('title', item.record_id))}; yerel değişim: {item.action}; "
        f"eşleşme: {', '.join(matched)}; önceki kayıt özeti: {before}; sonraki kayıt özeti: {after}. "
        "Kaynak iddiası/kamu metaverisi; doğrulanmış ihlal, çalınmış parola veya müşteri etkisi değildir.",
        current=applicable and bool(item.match_after), state_sha256=identity(asdict(item)),
        source_run_id=report.run.source_run_id, time_basis="source_response_received_at",
    )
