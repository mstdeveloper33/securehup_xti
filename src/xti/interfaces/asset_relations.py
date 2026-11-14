"""Terminal presentation of local asset evidence and explicit human decisions."""

from dataclasses import asdict

from xti.domain.asset_relations import RELATION_KINDS, AssetRelationObservation
from xti.interfaces.text import safe_text


_KINDS = {"dns": "DNS / IP", "certificate": "TLS sertifikası", "cname": "CNAME / dış hedef", "supplier": "Tedarikçi kararı"}
_STATUSES = {
    "observed": "Gözlendi", "accepted": "İnsan kararıyla kabul edildi",
    "withdrawn": "İnsan kararıyla geri çekildi", "pending": "İnceleme bekliyor",
    "uncertain": "Belirsiz", "rejected": "Reddedildi", "failed": "Kontrol başarısız",
    "blocked": "Kontrol yapılamadı", "no_address": "Bu kontrolde adres yok",
    "no_alias": "Bu kontrolde CNAME yok", "no_certificate_evidence": "Sertifika kanıtı kaydedilmemiş",
    "not_checked": "Kontrol edilmedi", "never": "Kayıtlı kontrol yok", "partial": "Kısmi kontrol",
    "no_decision": "İnsan kararı yok", "decisions_recorded": "İnsan kararı kaydedilmiş",
    "resolved": "DNS adresi bulundu", "present": "CNAME bulundu", "absent": "Bu kontrolde CNAME yok",
    "nxdomain": "Bu kontrolde DNS kaydı bulunmadı",
}
_RELATIONS = {
    "dns_address": "Domain → IP", "certificate_presented": "Domain → sertifika SHA-256",
    "cname_alias": "CNAME yönlendirmesi", "cname_target_address": "CNAME son hedefi → IP",
    "human_supplier_link": "Domain → insan onaylı tedarikçi",
    "dns_observation": "DNS kontrolü", "certificate_observation": "TLS kontrolü",
    "cname_observation": "CNAME kontrolü", "cname_target_observation": "CNAME hedef kontrolü",
}


def register_asset_relations_parser(surface_actions):
    parser = surface_actions.add_parser("relations", help="Kayıtlı IP, sertifika, CNAME ve tedarikçi ilişki geçmişi")
    parser.add_argument("domain", help="Kayıtlı tam domain")
    parser.add_argument("--kind", choices=RELATION_KINDS)
    parser.add_argument("--history", action="store_true", help="Başarısız/boş kontroller dahil bütün gözlemler")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=50)
    return parser


def asset_relations_lines(report):
    scope = "onaylı" if report.scope_active else ("geri çekilmiş" if report.scope_active is False else "yok")
    lines = [
        f"Varlık ilişki geçmişi: {safe_text(report.domain)} | Kontrol kapsamı: {scope}",
        f"Tarihî ilişki: {report.total_relationship_count} | Gözlem/karar/kontrol kaydı: {report.total_observation_count}",
        f"Görünüm: {'bütün gözlemler' if report.history else 'ilişki özeti'} | Başlangıç: {report.offset} | Gösterilen: {len(report.items)}/{report.total_count}",
    ]
    for item in report.items:
        label = _RELATIONS.get(item.relation, item.relation)
        target = item.target if item.target is not None else "ilişki kanıtı yok"
        if item.target_label:
            target = f"{item.target_label} ({target})"
        lines.append(f"  {safe_text(label)} | {safe_text(item.subject)} → {safe_text(target)}")
        if isinstance(item, AssetRelationObservation):
            lines.append(f"    {_STATUSES.get(item.status, safe_text(item.status))} | Gözlem: {safe_text(item.observed_at)} | Kayıt: {safe_text(item.recorded_at)}")
            lines.append(f"    Kaynak: {safe_text(item.source)} | Kanıt/karar: {safe_text(item.evidence_id)}")
            if item.state_sha256:
                lines.append(f"    Durum SHA-256: {safe_text(item.state_sha256)}")
            if item.candidate_id:
                lines.append(f"    Teknik aday: {safe_text(item.candidate_id)}")
            lines.extend("    " + safe_text(detail) for detail in item.details)
        else:
            lines.append(f"    İlk gözlem: {safe_text(item.first_observed_at)} | Son gözlem: {safe_text(item.last_observed_at)} | {item.observation_count} gözlem")
            lines.append(f"    Son kayıtlı ilişki olayı: {_STATUSES.get(item.latest_event_status, safe_text(item.latest_event_status))} | {safe_text(item.latest_recorded_at)}")
            lines.append(f"    Kaynak: {safe_text(item.latest_source)} | Son kanıt/karar: {safe_text(item.latest_evidence_id)}")
    if not report.items:
        lines.append("Bu sayfada kayıt yok.")
    lines.append("Kontrol kapsamı ve son kayıt:")
    for item in report.coverage:
        lines.append(f"  {_KINDS[item.kind]}: {item.check_count} kontrol/karar | {_STATUSES.get(item.latest_status, safe_text(item.latest_status))}")
        if item.latest_evidence_id:
            lines.append(f"    Gözlem: {safe_text(item.latest_observed_at)} | Kayıt: {safe_text(item.latest_recorded_at)} | Kanıt/karar: {safe_text(item.latest_evidence_id)}")
        lines.extend("    " + safe_text(note) for note in item.notes)
    if report.has_more:
        lines.append(f"Devamı için aynı komutta --offset {report.offset + report.limit} kullanın.")
    if not report.history:
        lines.append("Tek tek kanıtları ve başarısız/boş kontrolleri görmek için aynı komuta --history ekleyin.")
    lines.extend("Not: " + safe_text(note) for note in report.notes)
    return lines


def execute_asset_relations_command(service, args):
    report = service.show(args.domain, kind=args.kind, history=args.history, offset=args.offset, limit=args.limit)
    return asdict(report), asset_relations_lines(report)
