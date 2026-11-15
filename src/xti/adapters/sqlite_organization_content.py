"""Read exact organization/supplier content scope in the report's transaction."""

from datetime import datetime

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_mention_groups import _audit as read_group_state
from xti.adapters.sqlite_mentions import _advance, read_mentions_catalog
from xti.adapters.sqlite_supplier_history import read_supplier_history
from xti.domain.assets import ValidationError
from xti.domain.mentions import MENTION_NOTES, MentionRequest, MentionTarget, request_key
from xti.domain.organization_report import (
    OrganizationContentScope, OrganizationReportAttempt, OrganizationReportContent,
    OrganizationReportCoverage, OrganizationReportPage, OrganizationReportRecord,
    ReportNavigation, content_scope_status, report_freshness,
)


def _navigation(label, *arguments):
    return ReportNavigation(label, arguments)


def _page(kind, records, offset, limit):
    ordered = sorted(records, key=lambda item: (datetime.fromisoformat(item.recorded_at), item.id), reverse=True)
    items = tuple(ordered[offset:offset + limit])
    return OrganizationReportPage(kind, items, len(ordered), offset, limit, offset + len(items) < len(ordered))


def _attempt(run, *, current):
    if run is None:
        return None
    return OrganizationReportAttempt(
        run.id, "empty" if run.status == "complete" and run.result_count == 0 else run.status,
        run.finished_at, run.error, run.id, request_key(run.request), current,
    )


def read_organization_content(connection, scope, *, observed_at, stale_after_hours,
                              scope_offset, scope_limit, item_offset, item_limit):
    """No connection, key lookup or collection is opened by this projection.

    Current explicit supplier membership permits shared supplier evidence. After
    membership is withdrawn, only source receipts from this organization's frozen
    group runs are replayed; later data from another organization cannot leak in.
    """
    organization = scope.organization
    catalog = read_mentions_catalog(connection)
    groups = read_group_state(connection)
    suppliers = read_supplier_history(connection).suppliers
    organization_target = MentionTarget("organization", organization.id, organization.display_name,
        tuple(sorted({view.link.target.value for view in scope.effective_links
                      if view.link.target.kind == "domain"})))
    targets = {("organization", organization.id): organization_target}
    current_groups, configured_queries = {}, {}
    for group in groups.groups.values():
        if group.definition.organization_id != organization.id or not group.active or not organization.active:
            continue
        current_groups.setdefault(("organization", organization.id), set()).add(group.id)
        configured_queries.setdefault(("organization", organization.id), set()).add((group.definition.topic, group.definition.max_results))
        for identifier in group.definition.supplier_ids:
            supplier = suppliers.get(identifier)
            if supplier is None:
                raise StorageError("İçerik raporunun açık tedarikçi bağlantısı bulunamadı.")
            if supplier.active:
                key = ("supplier", identifier)
                current_groups.setdefault(key, set()).add(group.id)
                configured_queries.setdefault(key, set()).add((group.definition.topic, group.definition.max_results))
                targets[key] = MentionTarget("supplier", identifier, supplier.display_name, (supplier.primary_domain,))

    # Group definitions may later change organization, supplier set or query.
    # Historical affiliation comes from the run's frozen definition, never its
    # group's current name/definition or text occurring in an article.
    related_attempts, historical_source_ids, grouped_source_ids = {}, set(), set()
    for run in groups.runs.values():
        grouped_source_ids.update(attempt.result_run_id for attempt in run.attempts if attempt.result_run_id is not None)
        if run.definition.organization_id != organization.id:
            continue
        for attempt in run.attempts:
            key = request_key(attempt.request)
            related_attempts.setdefault(key, []).append((run, attempt))
            if attempt.result_run_id is not None:
                historical_source_ids.add(attempt.result_run_id)

    def admitted(run):
        target = run.request.target
        return ((target.kind == "organization" and target.id == organization.id)
                or (target.kind == "supplier" and (target.kind, target.id) in current_groups)
                or run.id in historical_source_ids)

    selected = tuple(run for run in catalog.runs if admitted(run))
    direct_keys = {request_key(run.request) for run in selected if run.id not in grouped_source_ids}
    records, requests, runs_by_key = {}, {}, {}
    for run in selected:
        key = request_key(run.request)
        requests[key] = run.request
        runs_by_key.setdefault(key, []).append(run)
        _advance(records, run)
    for key, attempts in related_attempts.items():
        requests[key] = attempts[-1][1].request
    unqueryable_targets = set()
    for identity, queries in configured_queries.items():
        for topic, maximum in queries:
            request = MentionRequest(targets[identity], topic, maximum)
            try:
                key = request_key(request)
            except ValidationError:
                # A report may cover more domains than one Tavily query can
                # express. Reading all report evidence must still be possible.
                unqueryable_targets.add(identity)
            else:
                requests.setdefault(key, request)

    records_by_key = {}
    for record in records.values():
        records_by_key.setdefault(record.request_key, []).append(record)
    scopes, pages = [], {"content": [], "historical_content": []}
    for key, request in sorted(requests.items()):
        identity = (request.target.kind, request.target.id)
        supplier = suppliers.get(request.target.id) if request.target.kind == "supplier" else None
        state = content_scope_status(request, current_target=targets.get(identity),
            organization_active=organization.active, supplier_active=supplier is not None and supplier.active,
            supplier_linked=identity in current_groups, configured_queries=tuple(sorted(configured_queries.get(identity, ()))),
            has_direct_search=key in direct_keys)
        current = state == "current"
        runs = runs_by_key.get(key, ())
        latest = runs[-1] if runs else None
        success = next((run for run in reversed(runs) if run.status == "complete"), None)
        last_attempt = _attempt(latest, current=current)
        notes = ["Güncellik yalnız bu tam istek kapsamının son başarılı aramasına aittir."]
        attempts = related_attempts.get(key, ())
        for group_run, attempt in attempts:
            # A reserved request without a durable receipt is not a successful
            # empty search. Pending/skipped work has not attempted collection.
            if attempt.status in {"reserved", "unknown"} and attempt.started_at is not None:
                at = attempt.finished_at or attempt.started_at
                if last_attempt is None or datetime.fromisoformat(at) > datetime.fromisoformat(last_attempt.recorded_at):
                    last_attempt = OrganizationReportAttempt(attempt.id, attempt.status, at,
                        attempt.error_code, None, key, current)
            if attempt.status in {"pending", "skipped"}:
                notes.append(f"Grup çalışması {group_run.id}: {attempt.status}; bu hedef için kaynak çağrısı yapılmadı.")
        if success is not None and success.result_count == 0:
            notes.append("Son başarılı arama boş döndü; bu durum kaynak hatası değildir ve eski kanıtları silmez.")
        if not current:
            notes.append("Tarihî kapsamdır; güncel kuruluş/tedarikçi veya isim/domain tanımı olarak değerlendirilmez.")
        navigation = tuple(_navigation("Etkin açık grup", "mentions", "groups", "show", identifier)
                           for identifier in sorted(current_groups.get(identity, ())))
        if attempts:
            navigation += (_navigation("Son ilişkili tarihî grup çalışması", "mentions", "groups", "run-show",
                                       attempts[-1][0].id, "--details"),)
        coverage = OrganizationReportCoverage("company-content", "tavily", last_attempt,
            _attempt(success, current=current), report_freshness(success.finished_at if success else None,
                observed_at, stale_after_hours), tuple(notes))
        scopes.append(OrganizationContentScope(request.target, request, key, state,
            tuple(sorted(current_groups.get(identity, ()))), coverage,
            success.result_count if success is not None else None, len(records_by_key.get(key, ())), navigation))
        for record in records_by_key.get(key, ()):
            hit = record.hit
            in_latest = success is not None and record.last_seen_run_id == success.id
            details = (
                f"Hedef: {request.target.kind} | {request.target.id} | {request.target.name}",
                f"Kapsam: {state} | konu: {request.topic} | sonuç sınırı: {request.max_results}",
                f"Aramadaki domainler: {', '.join(request.target.domains) or 'yok'}",
                f"Başlık: {hit.title}", f"Özet: {hit.summary}",
                f"Kaynağın yayın tarihi: {hit.published_at or 'belirtilmedi'}",
                f"Kaynağın uygunluk puanı: {hit.score if hit.score is not None else 'belirtilmedi'}; risk puanı değildir.",
                f"Eşleşen terimler: {', '.join(record.matched_terms) or 'yok'}",
                f"Eşleşen alanlar: {', '.join(record.match_fields) or 'yok'}",
                f"İlk görülme: {record.first_seen_at} | son görülme: {record.last_seen_at}",
                f"Son başarılı aramanın sonuçlarında: {'evet' if in_latest else 'hayır; önceki kanıt korunuyor'}",
                f"Özet kaynak sınırına göre kısaltıldı: {'evet' if hit.summary_truncated else 'hayır'}",
                "Arama adayıdır; tehdit veya ihlal kararı değildir.",
            )
            pages["content" if current else "historical_content"].append(OrganizationReportRecord(
                record.id, "content", hit.url,
                "source_candidate" if current and in_latest else "retained_candidate" if current else "historical_candidate",
                record.last_seen_at, "tavily", details, record.last_seen_run_id, record.last_seen_run_id, key,
                (_navigation("Tam kaynak çalışma kanıtı", "mentions", "run-show", record.last_seen_run_id),),
            ))

    # A previous name/domain's successful query must not make a newly configured
    # target look collected. Include an explicit never-collected current scope.
    current_identities = {(item.target.kind, item.target.id) for item in scopes if item.scope_status == "current"}
    for identity, target in targets.items():
        if identity in current_identities or not organization.active:
            continue
        scopes.append(OrganizationContentScope(target, None, None, "current",
            tuple(sorted(current_groups.get(identity, ()))),
            OrganizationReportCoverage("company-content", "tavily", None, None, "never",
                ("Bu güncel isim/domain kapsamı için kayıtlı arama yok; sıfır sonuç olduğu anlamına gelmez.",)),
            None, 0, notes=(("Güncel hedefin isim/domain kapsamı tek arama sorgusunun sınırlarını aşıyor; içerik araması için kapsam düzenlenmeli.",)
                           if identity in unqueryable_targets else ())))
    scopes.sort(key=lambda item: (item.scope_status != "current", item.target.kind, item.target.id, item.request_key or ""))
    visible = tuple(scopes[scope_offset:scope_offset + scope_limit])
    return OrganizationReportContent(organization.id, visible, len(scopes), scope_offset, scope_limit,
        scope_offset + len(visible) < len(scopes),
        tuple(_page(kind, values, item_offset, item_limit) for kind, values in pages.items()),
        (*MENTION_NOTES,
         "Kuruluş içerikleri kesin kuruluş kimliğiyle seçilir; aynı adlı bağımsız firma aramaları eklenmez.",
         "Güncel tedarikçi içerikleri yalnız etkin gruplarda açıkça seçilmiş etkin tedarikçi kimliklerinden gelir; ortak kayıtlı tedarikçi verisidir.",
         "Bağlantısı kaldırılmış tedarikçilerde yalnız bu kuruluşun tarihî grup kaynak kanıtları gösterilir; sonraki ilgisiz aramalar eklenmez.",
         "Eski isim/domain veya grup sorgu ayarı tarihî bölümde kalır. Başarılı boş arama ve kaynak hatası birbirinden ayrılır.",
         "Kapsam sayfaları --target-offset/--target-limit; içerik sayfaları --item-offset/--item-limit ile ilerler. İçerik toplamları gösterilen kapsam sayfasıyla daralmaz.",
         "Bu bölüm bütün arama çalışma geçmişini dışa aktarmaz; kapsam başına son deneme/başarıyı ve korunan son içerik kanıtını gösterir."))
