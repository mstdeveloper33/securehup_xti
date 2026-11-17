"""Standalone, escaped HTML over an already validated organization snapshot."""

from collections.abc import Iterable
from datetime import datetime, timezone
from html import escape
import shlex
from urllib.parse import urlsplit

from xti.domain.organization_export import OrganizationExportSnapshot, export_record_count
from xti.domain.organization_report import OrganizationReportAttempt, OrganizationReportRecord, ReportNavigation
from xti.domain.organizations import organization_link_effective
from xti.domain.public_notices import PublicNotice
from xti.interfaces.cname import check_lines as cname_lines
from xti.interfaces.mail import check_lines as mail_lines
from xti.interfaces.services import check_lines as service_lines
from xti.interfaces.surface import check_lines as web_lines
from xti.interfaces.organization_report import CONTENT_SCOPE_LABELS
from xti.interfaces.evidence_status import coverage_status_text


_SECTIONS = {"findings": "Domain ve marka bulguları", "surface_candidates": "Pasif alt alan adı adayları",
             "profiles": "Sosyal profil sonuçları", "claims": "Kaynak iddiaları",
             "public_notices": "Kamu olay kataloğu", "notifications": "Yerel bildirimler",
             "case_links": "Açık vaka bağlantıları", "public_notice_case_links": "Kamu olay vaka bağlantıları",
             "content": "Güncel kapsamın içerik adayları", "historical_content": "Tarihî kapsamın içerik adayları"}
_FRESHNESS = {"never": "Tam başarılı çalışma yok", "current": "Güncel", "stale": "Eski",
              "clock_error": "Gelecek zamanlı kayıt"}
_STATUS = {"complete": "Tamamlandı", "partial": "Kısmi", "failed": "Başarısız",
           "new": "Yeni", "suspicious": "Şüpheli", "uncertain": "Belirsiz", "dismissed": "Normal / kapatıldı",
           "pending": "İnceleme bekliyor", "owned": "Kullanıcı bana ait olarak işaretledi", "rejected": "Reddedildi",
           "unread": "Okunmadı", "read": "Okundu", "source_metadata": "Kaynak metaverisi",
           "added": "Yeni eşleşen kayıt", "updated": "Değişen kayıt", "removed": "Eşleşmeden çıkan kayıt",
           "unchanged": "Değişmeyen kayıt", "baseline": "Sessiz başlangıç", "enabled": "Açıldı", "disabled": "Kapatıldı",
           "empty": "Başarılı, boş sonuç", "reserved": "Kaynak çağrısı ayrıldı, sonuç bilinmiyor", "unknown": "Kaynak sonucu bilinmiyor",
           "source_candidate": "Arama adayı", "retained_candidate": "Önceki aramadan korunan aday",
           "historical_candidate": "Tarihî kapsamın adayı"}
_KINDS = {"domain": "Domain", "username-watch": "Kullanıcı adı izlemesi",
          "ransomware-watch": "ThreatCluster izlemesi", "ransomlook-watch": "RansomLook izlemesi"}

_CSS = """
:root{color-scheme:light;--ink:#182a3f;--muted:#526579;--line:#dbe4ec;--paper:#fff;--soft:#f2f6fa;--accent:#2254a4}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#eef3f8;color:var(--ink);font:15px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:var(--accent);text-decoration-thickness:1px;text-underline-offset:3px;overflow-wrap:anywhere}a:focus-visible{outline:3px solid #bf7a16;outline-offset:3px}
header{background:#112941;color:white;border-bottom:5px solid #5ac4ba;padding:44px max(24px,calc((100vw - 1180px)/2))}header .eyebrow{font-size:12px;letter-spacing:.16em;font-weight:750;color:#a9dedb}h1{margin:12px 0;font-size:clamp(26px,4vw,40px);line-height:1.2;overflow-wrap:anywhere}header p{color:#d8e4ef;margin:8px 0}
main{max-width:1228px;margin:auto;padding:28px 24px 56px}h2{font-size:23px;line-height:1.3;margin:0 0 18px}h3{font-size:18px;margin:26px 0 12px}h4{font-size:16px;margin:0 0 12px;overflow-wrap:anywhere}p{margin:8px 0;overflow-wrap:anywhere}ul{padding-left:22px}li{margin:5px 0;overflow-wrap:anywhere}
.panel,.target{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:24px;margin-bottom:24px}.target{border-top:4px solid #447bb2}.muted,.fine{color:var(--muted)}.fine{font-size:13px}.notice{background:#eff7f7;border-left:4px solid #468f88;padding:14px 18px;margin:18px 0;border-radius:4px}.empty{padding:12px 16px;background:var(--soft);color:var(--muted);border-radius:6px}
.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-bottom:24px}.stat{background:white;border:1px solid var(--line);padding:18px 22px;border-radius:12px}.stat strong{font-size:30px;line-height:1.2;display:block}.stat span{color:var(--muted);font-size:13px}
.toc{display:flex;flex-wrap:wrap;gap:8px}.toc a{border:1px solid var(--line);background:var(--soft);border-radius:7px;padding:7px 11px;text-decoration:none;font-size:14px}.target-title{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.pill{display:inline-block;font-size:12px;font-weight:650;line-height:1.4;border:1px solid #cbd8e5;background:#f0f5fa;color:#36516e;border-radius:99px;padding:4px 10px;white-space:normal}.bad{background:#fff1ee;color:#913d2e;border-color:#eec3b8}.warn{background:#fff7e5;color:#805817;border-color:#e8d29f}.good{background:#ecf7f3;color:#28634e;border-color:#b7dcca}
.table-wrap{overflow-x:auto;margin:12px 0}table{border-collapse:collapse;width:100%;text-align:left;font-size:13px}th{background:#f0f5f9;color:#36516e;font-weight:650}td,th{padding:12px;vertical-align:top;border-bottom:1px solid var(--line);overflow-wrap:anywhere}table.coverage{min-width:680px}table.scope{min-width:620px}.coverage td:nth-child(1){width:18%}.coverage td:nth-child(2){width:14%}.coverage td:nth-child(3),.coverage td:nth-child(4){width:34%}.attempt{font-size:12px;line-height:1.6}.attempt p{margin:3px 0}
.columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.evidence,.record,.delta{border:1px solid var(--line);border-radius:9px;padding:17px;margin:12px 0;background:#fff}.evidence{background:#fbfcfe}.record{border-left:3px solid #a3bbd3}.record h4{margin-bottom:4px}.meta{display:grid;grid-template-columns:145px minmax(0,1fr);gap:4px 14px;font-size:12px;margin:14px 0}.meta dt{color:var(--muted)}.meta dd{margin:0;overflow-wrap:anywhere}.evidence-lines p{margin:5px 0;font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}.record ul{font-size:13px}.commands{background:#f4f7fa;border-radius:6px;padding:10px 13px;font-size:12px}.commands p{margin:6px 0}code{font:12px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere;white-space:pre-wrap}.watch-run{border-top:2px solid #a5bdce;margin-top:26px;padding-top:22px}.watch-run h3{margin-top:0}footer{color:var(--muted);font-size:12px;padding:8px 4px}.back{font-size:12px;font-weight:500;float:right}.source-credit{font-size:13px;color:#36516e}
@media(max-width:700px){main{padding:18px 12px 36px}header{padding:30px 18px}.panel,.target{padding:18px 14px;border-radius:10px}.columns{grid-template-columns:1fr}.stats{gap:8px}.stat{padding:14px 10px}.stat strong{font-size:24px}.meta{grid-template-columns:1fr;gap:1px}.meta dd{margin-bottom:6px}.target-title{display:block}}
@media print{body{background:white;color:#111;font-size:10pt}header{background:white!important;color:#111;border-bottom:2px solid #333;padding:0 0 18px}header p,header .eyebrow{color:#333}main{max-width:none;padding:20px 0}.panel,.target{box-shadow:none;border-radius:0;padding:15px;margin-bottom:18px}.toc,.back{display:none}.table-wrap{overflow:visible}table.coverage,table.scope{min-width:0}td,th{padding:7px}thead{display:table-header-group}tr,.record,.evidence,.delta{break-inside:avoid}.columns{display:block}h2,h3,h4{break-after:avoid}.stats{display:flex}.stat{flex:1}.commands{border:1px solid #ddd}.meta{font-size:8pt}a{color:#111;text-decoration:underline}@page{size:A4;margin:16mm}}
"""


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def safe_external_url(value: str) -> str | None:
    """Keep external evidence links inert unless they are ordinary HTTP(S) URLs."""
    if (not isinstance(value, str) or not 1 <= len(value) <= 4096 or value != value.strip()
            or "\\" in value or any(not character.isprintable() or character.isspace() for character in value)):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"https", "http"} or not parsed.netloc or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            return None
        parsed.hostname.encode("idna")
        parsed.port
    except (ValueError, UnicodeError):
        return None
    return value


def _linked(value: object) -> str:
    text = str(value)
    url = safe_external_url(text)
    return (f'<a href="{_text(url)}" rel="noopener noreferrer" target="_blank">{_text(text)}</a>'
            if url is not None else _text(text))


def _pill(value: str, *, freshness: bool = False) -> str:
    label = (_FRESHNESS if freshness else _STATUS).get(value, value)
    color = "bad" if value in {"failed", "clock_error"} else "warn" if value in {"partial", "stale", "never"} else "good" if value == "current" else ""
    return f'<span class="pill {color}">{_text(label)}</span>'


def _meta(values: Iterable[tuple[str, object]]) -> str:
    return '<dl class="meta">' + ''.join(f'<dt>{_text(label)}</dt><dd>{_linked(value)}</dd>'
                                        for label, value in values if value is not None) + '</dl>'


def _lines(values: Iterable[str]) -> str:
    return '<div class="evidence-lines">' + ''.join(f'<p>{_text(value)}</p>' for value in values) + '</div>'


def _commands(values: tuple[ReportNavigation, ...]) -> str:
    if not values:
        return ""
    return '<div class="commands">' + ''.join(
        f'<p>{_text(value.label)}<br><code>{_text(shlex.join(("./xti", *value.arguments)))}</code></p>'
        for value in values
    ) + '</div>'


def _attempt(value: OrganizationReportAttempt | None) -> str:
    if value is None:
        return '<span class="muted">Kayıt yok</span>'
    lines = f'<div class="attempt">{_pill(value.status)}<p>{_text(value.recorded_at)}</p><p>Kimlik: {_text(value.id)}</p>'
    if value.source_run_id:
        lines += f'<p>Kaynak çalışması: {_text(value.source_run_id)}</p>'
    if value.definition_sha256:
        lines += f'<p>Tanım özeti: {_text(value.definition_sha256)}</p>'
    if value.definition_matches_current is not None:
        lines += '<p>Güncel tanımla aynı: ' + ('evet' if value.definition_matches_current else 'hayır') + '</p>'
    if value.is_baseline is not None:
        lines += '<p>' + ('İlk karşılaştırma tabanı' if value.is_baseline else 'Devam çalışması') + '</p>'
    if value.error:
        lines += f'<p><strong>Kaynak hatası:</strong> {_text(value.error)}</p>'
    return lines + '</div>'


def _notice(notice: PublicNotice | None, label: str) -> str:
    if notice is None:
        return f'<div class="evidence"><h4>{_text(label)}</h4><p class="muted">Bu tarafta kayıt yok.</p></div>'
    flags = (("Kaynak doğrulanmış diyor", notice.is_verified), ("Kaynak uydurma/yanlış iddia diyor", notice.is_fabricated),
             ("Kaynak hassas diyor", notice.is_sensitive), ("Kaynak geri çekmiş", notice.is_retired),
             ("Kaynak spam listesi diyor", notice.is_spam_list), ("Kaynak malware bağlantılı diyor", notice.is_malware),
             ("Kaynak stealer-log bağlantılı diyor", notice.is_stealer_log))
    return f'<div class="evidence"><h4>{_text(label)}</h4>' + _meta((
        ("Olay", notice.title), ("Kaynak olay kimliği", notice.id), ("Kaynak domain alanı", notice.domain or "Belirtilmedi"),
        ("Tahminî olay tarihi", notice.breach_date), ("Kataloğa eklenme", notice.added_at),
        ("Kaynakta değişme", notice.modified_at), ("Kaynağın hesap sayısı", notice.pwn_count),
        ("Veri kategorileri", ", ".join(notice.data_classes)), ("Kaynak kaydı", notice.source_url),
        ("Ek kaynak atfı", notice.source_attribution),
        *((name, "Evet" if value else "Hayır") for name, value in flags),
    )) + '<p class="fine">Bu sınıflar kaynağın değerlendirmesidir; XTI’nin bağımsız ihlal doğrulaması değildir.</p></div>'


def _record(record: OrganizationReportRecord) -> str:
    result = f'<article class="record"><h4>{_linked(record.value)}</h4>{_pill(record.status)}'
    result += _meta((("Kayıt kimliği", record.id), ("Kayıt zamanı", record.recorded_at), ("Kaynak", record.source),
                     ("Çalışma", record.run_id), ("Kaynak çalışması", record.source_run_id),
                     ("Tanım özeti", record.definition_sha256)))
    if record.details:
        result += '<ul>' + ''.join(f'<li>{_linked(value)}</li>' for value in record.details) + '</ul>'
    if record.public_notice is not None:
        result += _notice(record.public_notice, "Kaynağın tam metaverisi")
    return result + _commands(record.navigation) + '</article>'


class HtmlOrganizationReportRenderer:
    def render(self, snapshot: OrganizationExportSnapshot) -> Iterable[str]:
        report = snapshot.report
        organization = report.scope.organization
        displayed_at = datetime.fromisoformat(report.observed_at).astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        yield '<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        yield '<meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; base-uri &#39;none&#39;; form-action &#39;none&#39;">'
        yield '<title>' + _text(organization.display_name) + ' — XTI kuruluş raporu</title><style>' + _CSS + '</style></head><body>'
        yield '<header id="top"><div class="eyebrow">XTI · KURULUŞ RAPORU</div><h1>' + _text(organization.display_name) + '</h1>'
        yield f'<p>Rapor zamanı: {_text(displayed_at)}</p><p>Yerelde kayıtlı kanıtlar · Tam rapor görünümü · Ağsız dışa aktarım</p></header><main>'
        yield '<div class="stats">' + ''.join(f'<div class="stat"><strong>{count}</strong><span>{label}</span></div>' for count, label in (
            (len(report.targets), "Etkin ve açıkça bağlı hedef"), (export_record_count(snapshot), "Listelenen kapsam / kanıt / geçmiş kaydı"),
            (len(snapshot.public_notice_watch_runs), "Kamu olay izleme çalışması"))) + '</div>'
        yield '<section class="panel"><h2>Bu dosyanın kapsamı</h2><p>Kuruluş raporundaki bütün etkin hedefler, bölüm kayıtları ve kamu olay izleme geçmişi bu dosyada yer alır; sayfalama nedeniyle gizlenen kayıt yoktur.</p>'
        yield '<p>DNS/TLS/web, posta, servis ve CNAME bölümleri her ailenin son kayıtlı kontrolünü ve son başarı durumunu gösterir. Eski yüzey kontrollerinin tamamı bu raporun kapsamına girmez.</p>'
        yield '<div class="notice">Kuruluş bağlantısı açık kullanıcı seçimidir. Kaynak iddiası, benzerlik veya domain eşleşmesi tek başına sahiplik ya da doğrulanmış ihlal anlamına gelmez. Veri bulunmaması güvenli olduğu anlamına gelmez.</div>'
        yield _meta((("Kuruluş kimliği", organization.id), ("Kuruluş durumu", "Etkin" if organization.active else "Geri çekilmiş"),
                     ("Tam rapor zamanı", report.observed_at), ("Güncellik eşiği", f"{report.stale_after_hours} saat"),
                     ("Şema sürümü", report.schema_version)))
        yield '<nav class="toc" aria-label="Rapor bölümleri"><a href="#scope">Açık kapsam</a>'
        for index, target in enumerate(report.targets):
            yield f'<a href="#target-{index}">{_text(target.membership.target.display_name)}</a>'
        yield '<a href="#content">Firma ve tedarikçi içerikleri</a><a href="#public-watch">Kamu olay izleme geçmişi</a><a href="#public-cases">Kamu olay vaka bağlantıları</a></nav></section>'
        yield '<section class="panel" id="scope"><h2>Açık kuruluş kapsamı</h2><p class="muted">Etkin olmayan bağlantılar da açıklamasıyla listelenir; güncel hedef bölümlerine kanıt eklemezler.</p>'
        if report.scope.links:
            yield '<div class="table-wrap"><table class="scope"><thead><tr><th>Hedef</th><th>Tür</th><th>Durum</th><th>Açık bağlantı</th></tr></thead><tbody>'
            for view in report.scope.links:
                active = organization_link_effective(organization, view)
                states = []
                if not organization.active: states.append("Kuruluş geri çekilmiş")
                if not view.link.active: states.append("Bağlantı geri çekilmiş")
                if not view.target.active: states.append("Hedef etkin değil")
                yield f'<tr><td>{_text(view.link.target.value)}</td><td>{_text(_KINDS.get(view.link.target.kind, view.link.target.kind))}</td><td>{"Etkin" if active else _text("; ".join(states))}</td><td>{_text(view.link.id)}<p>{_text(view.link.reason)}</p></td></tr>'
            yield '</tbody></table></div>'
        else:
            yield '<p class="empty">Bu kuruluş için açık hedef bağlantısı yok.</p>'
        yield '</section>'
        for index, target in enumerate(report.targets):
            view = target.membership
            yield f'<section class="target" id="target-{index}"><div class="target-title"><h2>{_text(view.target.display_name)}</h2><span class="pill">{_text(_KINDS.get(view.link.target.kind, view.link.target.kind))}</span></div>'
            yield _meta((("Hedef", view.link.target.value), ("Açık bağlantı", view.link.id), ("Kaynak", view.target.source), *target.current_definition))
            yield '<h3>Kaynak durumu ve eksik kanıt</h3><div class="table-wrap"><table class="coverage"><thead><tr><th>Kaynak / aile</th><th>Güncellik</th><th>Son deneme</th><th>Son başarılı kayıt</th></tr></thead><tbody>'
            for coverage in target.coverage:
                yield f'<tr><td>{_text(coverage.source)}<p class="fine">{_text(coverage.family)}</p></td><td>{_pill(coverage.freshness, freshness=True)}<p>{_text(coverage_status_text(coverage))}</p></td><td>{_attempt(coverage.latest_attempt)}</td><td>{_attempt(coverage.latest_success)}</td></tr>'
                if coverage.notes:
                    yield '<tr><td colspan="4"><ul class="fine">' + ''.join(f'<li>{_linked(note)}</li>' for note in coverage.notes) + '</ul></td></tr>'
            yield '</tbody></table></div>'
            if target.surface is not None:
                surface = target.surface
                scope = surface.scope
                yield '<h3>Son kayıtlı yüzey kanıtları</h3><p class="fine">Bu dosya oluşturulurken hedefe bağlantı veya yeni kontrol yapılmadı.</p>'
                yield _meta((("Kontrol yetki kapsamı", "Etkin" if scope and scope.active else "Geri çekilmiş" if scope else "Kaydedilmemiş"),
                             ("Kapsam gerekçesi", scope.reason if scope else None)))
                yield '<div class="columns">'
                for label, check, formatter in (("Web / DNS / TLS", surface.latest_check, web_lines),
                                                ("E-posta DNS", surface.latest_mail_check, mail_lines),
                                                ("Servis", surface.latest_service_check, service_lines),
                                                ("CNAME", surface.latest_cname_check, cname_lines)):
                    yield '<article class="evidence"><h4>' + _text(label) + '</h4>'
                    if check is None:
                        yield '<p class="empty">Kontrol kaydı yok; durum bilinmiyor.</p>'
                    else:
                        yield _meta((("Kanıt kimliği", check.id),))
                        lines = formatter(check, now=datetime.fromisoformat(report.observed_at)) if formatter is web_lines else formatter(check)
                        yield _lines(lines)
                    yield '</article>'
                yield '</div>'
            for section in target.sections:
                yield '<h3>' + _text(_SECTIONS.get(section.kind, section.kind)) + f' <span class="pill">{section.total_count} kayıt · tamamı</span></h3>'
                if not section.items:
                    yield '<p class="empty">Bu bölümde kayıt yok. Kaynak durumunu yukarıdaki tablodan değerlendirin.</p>'
                for record in section.items:
                    yield _record(record)
            yield _commands(target.navigation)
            yield '<ul class="fine">' + ''.join(f'<li>{_text(note)}</li>' for note in target.notes) + '</ul><a class="back" href="#top">Başa dön</a></section>'
        yield from self._content(snapshot)
        yield from self._watch_history(snapshot)
        yield '<section class="panel" id="public-cases"><h2>Kamu olay vaka bağlantıları</h2><p class="fine">Yalnız bu kuruluşun tam kaynak kanıtına açıkça bağlanan vaka kimlikleri gösterilir. Başka vaka kanıtlarının içeriği bu dosyaya katılmaz.</p>'
        cases = report.public_notice_case_links
        if cases is None or not cases.items:
            yield '<p class="empty">Bu kapsamda açık kamu olay vaka bağlantısı yok.</p>'
        else:
            for record in cases.items:
                yield _record(record)
        yield '</section><footer><p>Tek dosya · JavaScript, uzaktan font veya görsel içermez. Bağlantılara tıklamak seçilen dış kaynak sitesini açar; terminal komutları yalnız gezinme bilgisidir.</p>'
        yield ''.join(f'<p>{_text(note)}</p>' for note in report.notes)
        yield '</footer></main></body></html>'

    def _content(self, snapshot: OrganizationExportSnapshot) -> Iterable[str]:
        content = snapshot.report.content
        yield '<section class="panel" id="content"><h2>Firma ve tedarikçi içerikleri</h2>'
        if content is None:
            yield '<p class="empty">Kayıtlı içerik raporu yok.</p></section>'
            return
        yield '<p>Kaynak: Tavily. İçerikler arama adaylarıdır; doğrulanmış tehdit veya ihlal değildir.</p>'
        yield f'<h3>İstek kapsamları · {content.total_scope_count} kaydın tamamı</h3>'
        for item in content.scopes:
            target, coverage = item.target, item.coverage
            yield '<article class="evidence"><h4>' + _text(target.name) + '</h4>'
            yield _meta((("Hedef türü", target.kind), ("Kesin hedef kimliği", target.id),
                ("Kapsam durumu", CONTENT_SCOPE_LABELS[item.scope_status]),
                ("Aramadaki domainler", ", ".join(target.domains) or "yok"),
                ("Güncel açık grup kimlikleri", ", ".join(item.current_group_ids) or "yok"),
                ("Konu", item.request.topic if item.request else "Kayıtlı arama yok"),
                ("Sonuç sınırı", item.request.max_results if item.request else None),
                ("İstek özeti", item.request_key),
                ("Son başarılı aramanın sonuç sayısı", item.latest_success_result_count if item.latest_success_result_count is not None else "Başarılı kayıt yok"),
                ("Korunan aday sayısı", item.retained_record_count)))
            yield '<p>Bu istek kapsamının kaynak güncelliği: ' + _pill(coverage.freshness, freshness=True) + '</p>'
            yield '<div class="columns"><div><h4>Son deneme</h4>' + _attempt(coverage.latest_attempt) + '</div><div><h4>Son başarılı kayıt</h4>' + _attempt(coverage.latest_success) + '</div></div>'
            yield '<ul class="fine">' + ''.join(f'<li>{_text(note)}</li>' for note in (*coverage.notes, *item.notes)) + '</ul>'
            yield _commands(item.navigation) + '</article>'
        for page in content.sections:
            yield '<h3>' + _text(_SECTIONS[page.kind]) + f' <span class="pill">{page.total_count} kayıt · tamamı</span></h3>'
            if not page.items:
                yield '<p class="empty">Bu bölümde aday yok; kaynak denemesi, boş başarı ve eksik kapsamı yukarıda ayrı inceleyin.</p>'
            for record in page.items:
                yield _record(record)
        yield '<ul class="fine">' + ''.join(f'<li>{_text(note)}</li>' for note in content.notes) + '</ul></section>'

    def _watch_history(self, snapshot: OrganizationExportSnapshot) -> Iterable[str]:
        watch = snapshot.report.public_notice_watch
        yield '<section class="panel" id="public-watch"><h2>Kamu olay izleme geçmişi</h2>'
        if watch is None:
            yield '<p class="empty">Bu kuruluş için kamu olay izlemesi açılmamış.</p></section>'
            return
        yield '<p>Bu bölüm her çalışmanın o zamanki kapsamını gösterir. Güncel domain bağlantıları tarihî kayıtların yerine geçirilmez.</p>'
        yield f'<p class="source-credit">Kaynak: {_text(watch.attribution)}<br>Lisans: {_text(watch.license)}</p>'
        yield _meta((("İzleme kimliği", watch.watch.id), ("Güncel izleme durumu", "Açık" if watch.watch.active else "Kapalı")))
        for label, source in (("Son katalog denemesi", watch.latest_source_run), ("Son başarılı katalog", watch.latest_complete_source_run)):
            yield '<h4>' + _text(label) + '</h4>'
            if source is None:
                yield '<p class="empty">Kayıt yok; bu durum sıfır eşleşme sonucu değildir.</p>'
            else:
                yield _meta((("Durum", _STATUS.get(source.status, source.status)), ("Kaynak çalışması", source.id),
                             ("Bitiş zamanı", source.finished_at), ("Hata", source.error)))
        yield '<h3>Açma / kapatma geçmişi</h3>'
        for event in watch.events:
            yield '<article class="record">' + _pill(event.action) + _meta((("Olay kimliği", event.id), ("Zaman", event.recorded_at),
                    ("Sürüm", event.revision), ("Kullanıcı gerekçesi", event.reason))) + '</article>'
        if not snapshot.public_notice_watch_runs:
            yield '<p class="empty">Henüz izleme çalışması yok. İlk başarılı değerlendirme sessiz başlangıçtır.</p>'
        for entry in snapshot.public_notice_watch_runs:
            run = entry.run
            yield '<section class="watch-run"><h3>Tarihî çalışma · ' + _text(entry.scope.organization_name) + '</h3>'
            yield _meta((("Çalışma kimliği", run.id), ("Kayıt zamanı", run.recorded_at), ("Kaynak çalışması", run.source_run_id),
                         ("Önceki kaynak çalışması", entry.previous_source_run_id), ("Kapsam özeti", run.scope_sha256),
                         ("Sonuç özeti", run.result_sha256), ("Bildirim kimliği", entry.notification_id)))
            yield f'<p>Eşleşen {run.matched_count} · sessiz başlangıç {run.baseline_count} · yeni {run.added_count} · değişen {run.updated_count} · çıkan {run.removed_count} · aynı {run.unchanged_count}</p>'
            yield '<h4>Çalışma anındaki açık domain kapsamı</h4>'
            if not entry.scope.members:
                yield '<p class="empty">Bu çalışmada etkin domain kapsamı yoktu.</p>'
            for member in entry.scope.members:
                state = "Sessiz başlangıç" if member.domain in entry.baseline_domains else "Devam eden kapsam"
                yield '<div class="record"><h4>' + _text(member.domain) + '</h4><p>' + state + '</p>' + _meta((
                    ("Bağlantı kimliği", member.link_id), ("Bağlantı sürümü", member.revision),
                    ("Bağlantı olayı", member.event_id), ("Etkinleştirme olayı", member.epoch_event_id))) + '</div>'
            yield f'<h4>Kaynak kayıtları · {entry.total_item_count} öğenin tamamı</h4>'
            for change in entry.items:
                yield '<article class="delta"><h4>' + _text(_STATUS.get(change.action, change.action)) + ' · ' + _text(change.notice_id) + '</h4><p>' + _text(change.domain) + '</p><div class="columns">'
                yield _notice(change.before, "Önceki kaynak kaydı") + _notice(change.after, "Bu çalışmadaki kaynak kaydı") + '</div>'
                if change.before is not None and change.after is not None:
                    fields = tuple(name for name in change.before.__dataclass_fields__ if getattr(change.before, name) != getattr(change.after, name))
                    if fields:
                        yield '<p class="fine">Değişen metadata alanları: ' + _text(", ".join(fields)) + '</p>'
                yield '</article>'
            yield '<div class="commands"><p>Yerel çalışma kanıtı<br><code>' + _text(shlex.join(("./xti", "notices", "watch-run-show", run.id))) + '</code></p></div></section>'
        yield '<ul class="fine">' + ''.join(f'<li>{_text(note)}</li>' for note in watch.notes) + '</ul></section>'
