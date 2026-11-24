"""Read-only source governance catalog built from reviewed connector manifests."""

from __future__ import annotations

from collections import Counter

from xti.application.sources import SourceCatalogService
from xti.domain.assets import ValidationError
from xti.domain.source_governance import (
    CONTRACT_VERSION, SourceManifest, catalog_sha256, manifest_sha256,
    parameters as governance_parameters, validate_manifest,
)
from xti.domain.sources import SourceCatalogEntry


class SourceGovernanceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


PROVENANCE_FIELDS = (
    "source_id", "source_reference", "observed_at", "recorded_at",
    "connector_version", "evidence_sha256",
)


_KIND_PROFILES = {
    "passive_archive": ("search", ("domain_observation",), "preserve_last_success"),
    "dns_resolver": ("active_check", ("dns_observation",), "preserve_last_success"),
    "active_check": ("active_check", ("service_observation",), "preserve_local_evidence"),
    "community_threat_intelligence_feed": ("snapshot", ("indicator",), "preserve_last_success"),
    "official_phishing_domain_feed": ("snapshot", ("indicator",), "preserve_last_success"),
    "public_incident_metadata_catalog": ("catalog", ("incident_claim",), "preserve_last_success"),
    "public_ransomware_claim_feed": ("snapshot", ("threat_claim",), "preserve_last_success"),
    "official_cti_knowledge_base": ("snapshot", ("cti_entity", "cti_relationship"), "preserve_last_success"),
    "official_vulnerability_catalog": ("catalog", ("vulnerability_record",), "preserve_last_success"),
    "official_vulnerability_probability": ("snapshot", ("vulnerability_score",), "preserve_last_success"),
    "official_vulnerability_context": ("search", ("vulnerability_record",), "preserve_last_success"),
    "vulnerability_advisory_aggregator": ("search", ("package_advisory",), "preserve_last_success"),
    "official_vendor_osv": ("search", ("package_advisory",), "preserve_last_success"),
    "official_vulnerability_record": ("search", ("vulnerability_record",), "preserve_last_success"),
    "official_package_advisory": ("search", ("package_advisory",), "preserve_last_success"),
    "official_vendor_vex": ("search", ("vendor_statement",), "preserve_last_success"),
    "publisher_news_feed": ("stream", ("content_item",), "preserve_last_success"),
    "company_content_search": ("search", ("content_item",), "preserve_last_success"),
    "reference_context": ("snapshot", ("reference_indicator",), "preserve_last_success"),
    "indicator_context": ("search", ("indicator_context",), "preserve_last_success"),
    "code_repository": ("search", ("code_document",), "preserve_last_success"),
    "paste_feed": ("stream", ("code_document",), "preserve_last_success"),
    "company_content_channel": ("stream", ("content_item",), "preserve_last_success"),
    "social_profile_search": ("search", ("social_profile",), "preserve_last_success"),
    "application_store": ("search", ("mobile_application",), "preserve_last_success"),
    "public_web_page": ("search", ("web_page_evidence",), "preserve_last_success"),
    "commercial_social_dataset": ("search", ("social_profile_evidence",), "preserve_last_success"),
    "verified_domain_exposure": ("snapshot", ("credential_exposure",), "preserve_last_success"),
    "aggregate_domain_exposure": ("snapshot", ("domain_exposure",), "preserve_last_success"),
    "underground_collector": ("stream", ("underground_mention",), "preserve_local_evidence"),
    "password_prefix_check": ("search", ("password_exposure_result",), "fail_closed"),
    "managed_network_probe": ("active_check", ("service_observation",), "preserve_local_evidence"),
    "sensor_telemetry": ("stream", ("telemetry_observation",), "preserve_local_evidence"),
    "honeypot_telemetry": ("stream", ("telemetry_observation",), "preserve_local_evidence"),
    "malware_sandbox_report": ("local_derived", ("sandbox_analysis",), "preserve_local_evidence"),
}


_VULNERABILITY_IDS = {
    "cisa-kev", "first-epss", "nist-nvd-cve", "osv-dev", "canonical-ubuntu-osv",
    "redhat-csaf-vex", "suse-csaf-vex",
}

_CONTRACT_REQUIRED = {
    "crt.sh", "theharvester-archives", "urlscan", "threatcluster-ransomware-claims",
    "enrichment:ripestat", "enrichment:ripestat-whois",
}

_ATTRIBUTION = {
    "hibp-public-breach-catalog", "ransomlook-ransomware-posts",
    "warninglist:cloudflare", "warninglist:rfc1918", "warninglist:rfc3849",
    "warninglist:rfc6761", "news:ncsc", "news:cert-fr",
}

_LANGUAGES = {
    "certpl-warning-list": ("pl",),
    "news:cisa": ("en",), "news:ncsc": ("en",), "news:cert-fr": ("fr",),
    "hibp-public-breach-catalog": ("en",),
}

_REGIONS = {
    "certpl-warning-list": ("PL",),
    "news:cisa": ("US",), "news:ncsc": ("GB",), "news:cert-fr": ("FR",),
}

_HEALTH_KEYS = {
    "crt.sh": ("scan:crt.sh", "surface:crt.sh"),
    "theharvester-archives": ("surface:theharvester",),
    "urlscan": ("scan:urlscan",),
    "feodo-tracker": ("ioc:feodo",),
    "certpl-warning-list": ("ioc:certpl",),
    "hibp-public-breach-catalog": ("notices:hibp",),
    "threatcluster-ransomware-claims": ("ransomware:threatcluster",),
    "ransomlook-ransomware-posts": ("ransomware:ransomlook",),
    "mitre-attack-enterprise": ("cti:attack",),
    "news:cisa": ("news:cisa",), "news:ncsc": ("news:ncsc",),
    "news:cert-fr": ("news:cert-fr",), "mentions:tavily": ("mentions:tavily",),
    "warninglist:cloudflare": ("warninglist:cloudflare",),
    "warninglist:rfc1918": ("warninglist:rfc1918",),
    "warninglist:rfc3849": ("warninglist:rfc3849",),
    "warninglist:rfc6761": ("warninglist:rfc6761",),
    "enrichment:ripestat-whois": ("enrichment:ripestat-whois",),
    "enrichment:ripestat": ("enrichment:ripestat",),
    "enrichment:circl": ("enrichment:circl",),
    "enrichment:urlscan": ("enrichment:urlscan",),
}


def _entry(
    identifier: str, label: str, kind: str, purpose: str, access: str,
    *, credential_required: bool = False, paid_dependency: bool = False,
    contacts_monitored_target: bool = False, commands: tuple[str, ...],
    limits: tuple[str, ...], reference_url: str,
) -> SourceCatalogEntry:
    return SourceCatalogEntry(
        identifier=identifier, label=label, kind=kind, purpose=purpose, access=access,
        credential_required=credential_required, paid_dependency=paid_dependency,
        contacts_monitored_target=contacts_monitored_target, commands=commands,
        limits=limits, reference_url=reference_url,
    )


_WORKFLOW_ENTRIES = (
    _entry(
        "code:github-repositories", "GitHub public repository discovery", "code_repository",
        "Kuruluş adı, domaini ve açıkça tanımlanmış depolar için kamu depolarındaki sınırlı metin dosyalarını araştırır.",
        "Anahtarsız kamu repository araması; hesaplı genel kod aramasından ayrı ve sınırlıdır.",
        commands=("code sources", "code run WATCH_ID"),
        limits=("Yalnız kamu depoları ve mevcut revision okunur.", "Secret doğrulaması yapılmaz; metin kalıcı kayıttan önce maskelenir."),
        reference_url="https://docs.github.com/en/rest/search/search",
    ),
    _entry(
        "code:github-code", "GitHub authenticated code search", "code_repository",
        "GitHub genel kod indeksinde kuruluş adı veya domainle ilişkili dosya adaylarını araştırır.",
        "Kullanıcının GitHub token'ı ve hesabının izin verdiği code-search kapsamı gerekir.",
        credential_required=True, commands=("code configure github", "code run WATCH_ID --source github-code"),
        limits=("Token özel dosyada kalır ve kanıta yazılmaz.", "Sonuç secret veya ihlal hükmü değil inceleme adayıdır."),
        reference_url="https://docs.github.com/en/rest/search/search#search-code",
    ),
    _entry(
        "code:gitlab-projects", "GitLab public project discovery", "code_repository",
        "Kuruluş adı ve domainiyle ilişkili herkese açık GitLab projelerini ve sınırlı metin dosyalarını araştırır.",
        "Anahtarsız kamu proje araması; hesaplı genel blob aramasından ayrı ve sınırlıdır.",
        commands=("code sources", "code run WATCH_ID"),
        limits=("Yalnız public projeler kabul edilir.", "Kapsam ve dosya bütçesi dolarsa sonuç kısmi gösterilir."),
        reference_url="https://docs.gitlab.com/api/projects/",
    ),
    _entry(
        "code:gitlab-code", "GitLab authenticated blob search", "code_repository",
        "GitLab genel blob aramasında kuruluşla ilişkili kod ve secret adaylarını araştırır.",
        "Kullanıcının GitLab token'ı ve hesap planının izin verdiği blob-search kapsamı gerekir.",
        credential_required=True, commands=("code configure gitlab", "code run WATCH_ID --source gitlab-code"),
        limits=("Token özel dosyada kalır.", "Kaynak erişimi yoksa başarılı boş sonuç üretilmez."),
        reference_url="https://docs.gitlab.com/api/search/",
    ),
    _entry(
        "code:pastebin", "Pastebin recent paste source", "paste_feed",
        "Yakın dönem kamu paste içeriklerinde kuruluş, domain ve maskelenebilir secret adaylarını araştırır.",
        "Pastebin scraping API erişimi ve güncel hizmet koşuluna uygun hesap gerekir.",
        credential_required=True, commands=("code run WATCH_ID --source pastebin",),
        limits=("Bütün tarihsel paste arşivi değildir.", "Erişim olmadan fixture canlı kaynak kabulü sayılmaz."),
        reference_url="https://pastebin.com/doc_scraping_api",
    ),
    _entry(
        "content:rss", "Configured RSS/Atom source", "publisher_news_feed",
        "Açıkça kaydedilen güvenli RSS veya Atom yayınında firma ve tedarikçi eşleşmelerini izler.",
        "Genel HTTPS yayın adresi gerekir; yayıncının erişim ve içerik koşulları geçerlidir.",
        commands=("content source-add --provider rss", "content run WATCH_ID"),
        limits=("Keyfî makale gövdesi indirilmez.", "Yeni yayıncı ticari profile koşul incelemesi olmadan açılmaz."),
        reference_url="https://www.rssboard.org/rss-specification",
    ),
    _entry(
        "content:bluesky-public-search", "Bluesky public post search", "company_content_search",
        "Kuruluş veya tedarikçi adı, domaini ve alternatif adıyla eşleşen genel Bluesky metin gönderilerini araştırır.",
        "Anahtarsız Bluesky public AppView; yalnız genel arama penceresi ve sağlayıcı kotası kapsamındadır.",
        commands=("content source-add --provider bluesky", "content run WATCH_ID"),
        limits=("Yalnız en güncel genel arama sayfası alınır; tam ağ veya tarihsel arşiv değildir.",
                "Medya, özel hesap, mesaj ve profil verisi alınmaz; eşleşme tehdit veya kimlik kanıtı değildir."),
        reference_url="https://docs.bsky.app/docs/api/app-bsky-feed-search-posts",
    ),
    _entry(
        "content:telegram", "Telegram public channel", "company_content_channel",
        "Açıkça seçilmiş kamu Telegram kanalındaki yeni ve geçmiş pencereli iletileri kuruluş hedefleriyle eşleştirir.",
        "Telegram API kimliği, kullanıcı oturumu ve erişilebilir kamu kanalı gerekir.",
        credential_required=True, commands=("content configure telegram", "content source-add --provider telegram", "content run WATCH_ID"),
        limits=("Özel kanal, kişi veya davet bağlantısı kabul edilmez.", "Hesap ve kanal canlı kabulü olmadan aktif gösterilmez."),
        reference_url="https://core.telegram.org/api",
    ),
    _entry(
        "content:discord", "Discord selected channel", "company_content_channel",
        "İzin verilmiş Discord sunucu ve kanalındaki iletileri kuruluş hedefleriyle eşleştirir.",
        "Bot token'ı, sunucu/kanal seçimi ve Message Content dâhil gerekli izinler gerekir.",
        credential_required=True, commands=("content configure discord", "content source-add --provider discord", "content run WATCH_ID"),
        limits=("Yalnız seçilmiş kanal okunur.", "İzin hatası başarılı boş sonuç sayılmaz."),
        reference_url="https://discord.com/developers/docs/resources/channel",
    ),
    _entry(
        "content:irc", "IRC selected TLS channel", "company_content_channel",
        "Seçilmiş TLS IRC kanalındaki yeni iletileri terminal açıkken kuruluş hedefleriyle eşleştirir.",
        "Açık ircs sunucusu ve kanal seçimi gerekir; bazı ağlarda hesap veya kayıt gerekebilir.",
        commands=("content source-add --provider irc", "content run WATCH_ID"),
        limits=("Çevrimdışı dönemin geçmişi uydurulmaz.", "Yalnız TLS 6697 ve seçilmiş kanal kullanılır."),
        reference_url="https://modern.ircdocs.horse/",
    ),
    _entry(
        "brand:maigret", "Maigret selected username catalog", "social_profile_search",
        "Seçilen kullanıcı adının incelenmiş kamu profil adreslerindeki varlık adaylarını araştırır.",
        "Sabitlenmiş Maigret kurulumu ve hedef platformların kamu erişimi gerekir.",
        commands=("brand username-preview USERNAME --source maigret", "brand watch-run WATCH_ID"),
        limits=("Aynı kullanıcı adı aynı marka kanıtı değildir.", "Yalnız XTI'nin seçilmiş güvenli veya geniş profili çalışır."),
        reference_url="https://github.com/soxoj/maigret",
    ),
    _entry(
        "brand:sherlock", "Sherlock selected username catalog", "social_profile_search",
        "Seçilen kullanıcı adının incelenmiş kamu profil adreslerindeki varlık adaylarını ikinci araçla araştırır.",
        "Sabitlenmiş Sherlock kurulumu ve hedef platformların kamu erişimi gerekir.",
        commands=("brand username-preview USERNAME --source sherlock", "brand watch-run WATCH_ID"),
        limits=("Aynı kullanıcı adı sahiplik veya taklit hükmü değildir.", "Tam upstream katalog yerine incelenmiş hedefler kullanılır."),
        reference_url="https://github.com/sherlock-project/sherlock",
    ),
    _entry(
        "brand:apple-app-store", "Apple App Store search", "application_store",
        "Marka kimliğiyle ilişkili olabilecek iOS uygulama ve yayıncı adaylarını seçilmiş bölgede araştırır.",
        "Apple kamu arama/lookup uç noktası; mağaza ve içerik koşulları geçerlidir.",
        commands=("brand protection-run WATCH_ID",),
        limits=("Yalnız seçilmiş ülke penceresidir.", "Sonuç sahte uygulama hükmü değildir."),
        reference_url="https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/",
    ),
    _entry(
        "brand:google-play", "Google Play public search", "application_store",
        "Marka kimliğiyle ilişkili olabilecek Android uygulama ve yayıncı adaylarını seçilmiş bölgede araştırır.",
        "Google Play kamu sayfası; mağaza erişimi ve içerik koşulları geçerlidir.",
        commands=("brand protection-run WATCH_ID",),
        limits=("Yalnız seçilmiş ülke penceresidir.", "APK indirilmez ve sonuç sahte uygulama hükmü değildir."),
        reference_url="https://play.google.com/about/developer-content-policy/",
    ),
    _entry(
        "brand:public-page", "Bounded public web page evidence", "public_web_page",
        "Marka adayının açık HTTPS sayfasından statik metin, logo ve ekran görüntüsü kanıtı üretir.",
        "Giriş gerektirmeyen kamu HTTPS sayfası ve kurulu yönetilen Chromium gerekir.",
        commands=("brand protection-run WATCH_ID",),
        limits=("JavaScript kapalıdır ve oturum açılmaz.", "Görsel benzerlik tek başına taklit kararı değildir."),
        reference_url="https://playwright.dev/python/docs/browsers",
    ),
    _entry(
        "brand:brightdata-linkedin", "Bright Data LinkedIn company dataset", "commercial_social_dataset",
        "Önceden bulunan LinkedIn şirket profili adayı için sınırlı şirket kanıtı alır.",
        "Bright Data hesabı, API anahtarı ve ilgili ücretli dataset erişimi gerekir.",
        credential_required=True, paid_dependency=True,
        commands=("brand brightdata configure", "brand enrich ENRICHMENT_ID"),
        limits=("Yeni profil keşfetmez ve kişi/çalışan listesi almaz.", "Saklama ve müşteri gösterimi hesap sözleşmesi netleşene kadar ticari profilde kapalıdır."),
        reference_url="https://docs.brightdata.com/products/datasets/scrapers/scrapers-library/linkedin",
    ),
    _entry(
        "credential:xposedornot-domain", "XposedOrNot verified-domain exposure", "verified_domain_exposure",
        "Doğrulanmış kuruluş domainine ait maskelenmiş hesap ve ihlal adı eşleşmelerini alır.",
        "XposedOrNot API anahtarı ve sağlayıcı hesabında doğrulanmış domain gerekir.",
        credential_required=True, commands=("darkweb credential-configure", "darkweb credential-refresh PROFILE_ID"),
        limits=("Ham alias yalnız bellekte maskelenir.", "Parola, token veya cookie alınmaz ve hesap etkinliği denenmez."),
        reference_url="https://xposedornot.com/api_doc",
    ),
    _entry(
        "credential:xposedornot-password", "XposedOrNot password prefix check", "password_prefix_check",
        "Kullanıcının açıkça girdiği parolanın maruziyet önekini tek seferlik kontrol eder.",
        "Anahtarsız parola önek uç noktası; gerçek parola ve tam hash yalnız yerelde kalır.",
        commands=("darkweb password-check",),
        limits=("Yalnız Keccak-512 önekinin ilk 10 hex karakteri gönderilir.", "Sonuç saklanmaz ve boş yanıt parolanın güvenli olduğunu kanıtlamaz."),
        reference_url="https://xposedornot.com/api_doc",
    ),
    _entry(
        "credential:lunar-domain-exposure", "Lunar/Webz.io aggregate domain exposure",
        "aggregate_domain_exposure",
        "Kuruluş domaininin son 12 aylık employee/client ve breach/infostealer olay sayılarını toplu olarak alır.",
        "Anahtarsız kamu Domain Exposure API; yalnız açıkça bağlı kesin domain sorgulanır.",
        commands=("darkweb lunar-refresh PROFILE_ID DOMAIN",),
        limits=("Bireysel credential veya PII dönmez ve saklanmaz.",
                "GENERATING_REPORT boş sonuç sayılmaz; açık pending durumudur."),
        reference_url="https://docs.webz.io/docs/webz/dea-introduction",
    ),
    _entry(
        "darkweb:ail-framework", "AIL Framework selected tracker intake",
        "underground_collector",
        "Ayrı işletilen AIL tracker eşleşmelerini firma kapsamlı, içeriksiz ve hash bağlı kaynak iddiasına dönüştürür.",
        "Ayrı AIL 7.x örneği ve xti-ail-v1 zarfı üreten işletici kontrollü connector gerekir.",
        commands=("darkweb ail-preview PROFILE_ID FILE", "darkweb ail-import PROFILE_ID FILE"),
        limits=("Ham Tor/I2P adresi, sayfa gövdesi, credential veya oturum bilgisi saklanmaz.",
                "XTI giriş yapmaz, captcha aşmaz, dosya indirmez ve AIL kodunu bünyesine kopyalamaz."),
        reference_url="https://www.ail-project.org/",
    ),
    _entry(
        "surface:nmap", "Managed Nmap authorized target", "managed_network_probe",
        "Kullanıcıya ait kesin IP/CIDR ve donmuş plan üzerinde izinli servis kanıtı üretir.",
        "Nmap 7.x kurulumu, açık hedef/port/trafik yetkisi ve bazı seçenekler için ayrıcalıklı çalışma gerekir.",
        contacts_monitored_target=True,
        commands=("surface nmap capabilities", "surface nmap plans create", "surface nmap jobs submit"),
        limits=("Kapsam dışı hedef ve ham parametre kabul edilmez.", "Açık port tek başına ürün, zafiyet veya istismar kanıtı değildir."),
        reference_url="https://nmap.org/book/man.html",
    ),
    _entry(
        "telemetry:xti-sensor-v1", "XTI Sensor JSON v1", "sensor_telemetry",
        "Kuruluş sensörü veya sinkhole tarafından üretilen kesin v1 kayıtlarını normalize telemetri kanıtına dönüştürür.",
        "Yerel JSONL dosyası veya firma JSON sözleşmesi; harici hesaba ya da ağ sorgusuna ihtiyaç duymaz.",
        commands=("telemetry capabilities", "telemetry preview FILE --format xti-sensor-v1", "telemetry import SOURCE_ID FILE --format xti-sensor-v1"),
        limits=("Yalnız kesin XTI Sensor JSON v1 alanları kabul edilir.", "Ham paket, parola, kullanıcı adı ve komut içeriği saklanmaz."),
        reference_url="https://github.com/mstdeveloper33/securehup_xti/blob/main/docs/TELEMETRY.md",
    ),
    _entry(
        "telemetry:cowrie-jsonl", "Cowrie JSONL telemetry", "honeypot_telemetry",
        "Ayrı çalışan Cowrie honeypot'un desteklenen bağlantı, kimlik doğrulama ve dosya indirme olaylarını güvenli metadataya indirger.",
        "Yerel Cowrie JSONL çıktısı gerekir; XTI Cowrie kurmaz, çalıştırmaz veya internete açmaz.",
        commands=("telemetry source-add --kind honeypot --format cowrie-jsonl", "telemetry preview FILE --format cowrie-jsonl", "telemetry import SOURCE_ID FILE --format cowrie-jsonl"),
        limits=("Yalnız incelenmiş Cowrie olayları kabul edilir; diğerleri neden sayacıyla atlanır.", "username, password, input, message ve ham olay gövdesi kopyalanmaz."),
        reference_url="https://docs.cowrie.org/en/stable/OUTPUT.html",
    ),
    _entry(
        "telemetry:cape-report-v1", "CAPE completed report import", "malware_sandbox_report",
        "Ayrı ve izole CAPE ortamında tamamlanmış report.json dosyasından hash, imza özeti ve sınırlı ağ göstergelerini alır.",
        "Yerel tamamlanmış CAPE report.json gerekir; XTI zararlı örnek yüklemez veya çalıştırmaz.",
        commands=("telemetry source-add --kind sandbox --format cape-report-v1", "telemetry preview REPORT --format cape-report-v1", "telemetry import SOURCE_ID REPORT --format cape-report-v1"),
        limits=("Ham rapor, örnek dosya, PCAP ve bellek dökümü saklanmaz.", "CAPE ayrı izole altyapıda işletilmeden canlı kabul tamamlanmış sayılmaz."),
        reference_url="https://capev2.readthedocs.io/en/latest/usage/results.html",
    ),
)


_WORKFLOW_PROFILES = {
    "code:github-repositories": {"integration_state": "active", "access_model": "public_service", "credential_mode": "optional", "cost_model": "free", "languages": ("mul",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "review_required", "customer_display": "review_required", "redistribution": "not_enabled", "health_command": "./xti code sources", "retry_policy": "resume_cursor", "health_model": "feature_history"},
    "code:github-code": {"integration_state": "conditional", "access_model": "configured_account", "credential_mode": "required", "cost_model": "free_tier", "languages": ("mul",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "review_required", "customer_display": "review_required", "redistribution": "not_enabled", "health_command": "./xti code sources", "retry_policy": "resume_cursor", "health_model": "feature_history", "prerequisites": ("GitHub hesabı ve izinli token gerekir.",)},
    "code:gitlab-projects": {"integration_state": "active", "access_model": "public_service", "credential_mode": "optional", "cost_model": "free", "languages": ("mul",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "review_required", "customer_display": "review_required", "redistribution": "not_enabled", "health_command": "./xti code sources", "retry_policy": "resume_cursor", "health_model": "feature_history"},
    "code:gitlab-code": {"integration_state": "conditional", "access_model": "configured_account", "credential_mode": "required", "cost_model": "mixed", "languages": ("mul",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "review_required", "customer_display": "review_required", "redistribution": "not_enabled", "health_command": "./xti code sources", "retry_policy": "resume_cursor", "health_model": "feature_history", "prerequisites": ("GitLab hesabı, token ve uygun arama kapsamı gerekir.",)},
    "code:pastebin": {"integration_state": "conditional", "access_model": "configured_account", "credential_mode": "required", "cost_model": "mixed", "languages": ("mul",), "regions": ("global",), "commercial_use": "contract_required", "retention_policy": "contract_required", "customer_display": "contract_required", "redistribution": "not_enabled", "health_command": "./xti code sources", "retry_policy": "resume_cursor", "health_model": "feature_history", "prerequisites": ("Pastebin scraping erişimi ve ticari veri kararı gerekir.",)},
    "content:rss": {"integration_state": "active", "access_model": "public_service", "credential_mode": "none", "cost_model": "free", "languages": ("mul",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "review_required", "customer_display": "review_required", "redistribution": "not_enabled", "health_command": "./xti content sources", "retry_policy": "resume_cursor", "health_model": "feature_history"},
    "content:bluesky-public-search": {"integration_state": "active", "access_model": "public_service", "credential_mode": "none", "cost_model": "free", "languages": ("mul",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "review_required", "customer_display": "review_required", "redistribution": "not_enabled", "health_command": "./xti content providers", "retry_policy": "resume_cursor", "health_model": "feature_history", "prerequisites": ("Ticari saklama ve müşteriye gösterim koşulları üretim profilinde ayrıca onaylanmalıdır.",)},
    "content:telegram": {"integration_state": "conditional", "access_model": "configured_account", "credential_mode": "required", "cost_model": "free", "languages": ("mul",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "review_required", "customer_display": "review_required", "redistribution": "not_enabled", "health_command": "./xti content providers", "retry_policy": "resume_cursor", "health_model": "feature_history", "prerequisites": ("Telegram API bilgisi, kullanıcı oturumu ve seçilmiş kamu kanalı gerekir.",)},
    "content:discord": {"integration_state": "conditional", "access_model": "configured_account", "credential_mode": "required", "cost_model": "free", "languages": ("mul",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "review_required", "customer_display": "review_required", "redistribution": "not_enabled", "health_command": "./xti content providers", "retry_policy": "resume_cursor", "health_model": "feature_history", "prerequisites": ("Discord bot token'ı, sunucu/kanal ve içerik izinleri gerekir.",)},
    "content:irc": {"integration_state": "active", "access_model": "public_service", "credential_mode": "optional", "cost_model": "free", "languages": ("mul",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "review_required", "customer_display": "review_required", "redistribution": "not_enabled", "health_command": "./xti content providers", "retry_policy": "resume_cursor", "health_model": "feature_history"},
    "brand:maigret": {"integration_state": "conditional", "access_model": "public_service", "credential_mode": "none", "cost_model": "free", "languages": ("mul",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "metadata_only", "customer_display": "review_required", "redistribution": "not_enabled", "health_command": "./xti sources status --details", "retry_policy": "explicit_only", "health_model": "shared_readiness", "health_keys": ("social:maigret",), "prerequisites": ("Sabitlenmiş Maigret araç ortamı kurulmuş olmalı.",)},
    "brand:sherlock": {"integration_state": "conditional", "access_model": "public_service", "credential_mode": "none", "cost_model": "free", "languages": ("mul",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "metadata_only", "customer_display": "review_required", "redistribution": "not_enabled", "health_command": "./xti sources status --details", "retry_policy": "explicit_only", "health_model": "shared_readiness", "health_keys": ("social:sherlock",), "prerequisites": ("Sabitlenmiş Sherlock araç ortamı kurulmuş olmalı.",)},
    "brand:apple-app-store": {"integration_state": "active", "access_model": "public_service", "credential_mode": "none", "cost_model": "free", "languages": ("mul",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "review_required", "customer_display": "review_required", "redistribution": "not_enabled", "health_command": "./xti brand source-evaluation", "retry_policy": "explicit_only", "health_model": "feature_history"},
    "brand:google-play": {"integration_state": "active", "access_model": "public_service", "credential_mode": "none", "cost_model": "free", "languages": ("mul",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "review_required", "customer_display": "review_required", "redistribution": "not_enabled", "health_command": "./xti brand source-evaluation", "retry_policy": "explicit_only", "health_model": "feature_history"},
    "brand:public-page": {"integration_state": "conditional", "access_model": "public_service", "credential_mode": "none", "cost_model": "local", "languages": ("mul",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "review_required", "customer_display": "review_required", "redistribution": "not_enabled", "health_command": "./xti brand source-evaluation", "retry_policy": "explicit_only", "health_model": "feature_history", "prerequisites": ("Yönetilen Playwright/Chromium kurulumu gerekir.",)},
    "brand:brightdata-linkedin": {"integration_state": "conditional", "access_model": "configured_account", "credential_mode": "required", "cost_model": "paid", "languages": ("mul",), "regions": ("global",), "commercial_use": "contract_required", "retention_policy": "contract_required", "customer_display": "contract_required", "redistribution": "not_enabled", "health_command": "./xti brand brightdata status", "retry_policy": "explicit_only", "health_model": "feature_history", "prerequisites": ("Bright Data hesabı, anahtar, dataset erişimi ve ticari veri kararı gerekir.",)},
    "credential:xposedornot-domain": {"integration_state": "conditional", "access_model": "configured_account", "credential_mode": "required", "cost_model": "mixed", "languages": ("und",), "regions": ("global",), "commercial_use": "contract_required", "retention_policy": "allowed_with_terms", "customer_display": "allowed_with_terms", "redistribution": "not_enabled", "health_command": "./xti darkweb profile show PROFILE_ID", "retry_policy": "explicit_only", "health_model": "feature_history", "prerequisites": ("XposedOrNot anahtarı ve sağlayıcı hesabında doğrulanmış kuruluş domaini gerekir.",)},
    "credential:xposedornot-password": {"integration_state": "active", "access_model": "public_service", "credential_mode": "none", "cost_model": "free", "languages": ("und",), "regions": ("global",), "commercial_use": "allowed_with_terms", "retention_policy": "not_enabled", "customer_display": "not_enabled", "redistribution": "not_enabled", "health_command": "./xti darkweb password-check --help", "quota_policy": "Yalnız açık kullanıcı işlemi başına tek önek sorgusu; toplu, zamanlanmış veya arka plan kontrolü yoktur.", "retry_policy": "explicit_only", "failure_policy": "fail_closed", "health_model": "static_configuration"},
    "credential:lunar-domain-exposure": {"integration_state": "active", "access_model": "public_service", "credential_mode": "none", "cost_model": "free", "languages": ("und",), "regions": ("global",), "commercial_use": "allowed_with_terms", "retention_policy": "allowed_with_terms", "customer_display": "allowed_with_terms", "redistribution": "not_enabled", "terms_reviewed_at": "2026-11-24", "health_command": "./xti darkweb source-runs --provider lunar_domain", "quota_policy": "Yalnız kullanıcıca başlatılan kesin domain sorgusu; otomatik yoğun polling yoktur.", "retry_policy": "explicit_only", "failure_policy": "preserve_last_success", "health_model": "feature_history"},
    "darkweb:ail-framework": {"integration_state": "conditional", "collection_mode": "stream", "access_model": "local", "credential_mode": "none", "cost_model": "local", "target_contact": "none", "languages": ("mul",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "allowed_with_terms", "customer_display": "allowed_with_terms", "redistribution": "not_enabled", "terms_reviewed_at": "2026-11-24", "health_command": "./xti darkweb capabilities", "quota_policy": "Tek zarf en çok 2 MiB ve 1.000 normalize metadata kaydı; ham içerik kabul edilmez.", "retry_policy": "local_idempotent", "failure_policy": "preserve_local_evidence", "health_model": "static_configuration", "prerequisites": ("Ayrı ve sertleştirilmiş AIL 7.x örneği ile xti-ail-v1 connector gerekir.", "Gerçek AIL olayı ve seçilmiş yasal kaynak olmadan canlı kabul tamamlanmış sayılmaz.")},
    "surface:nmap": {"integration_state": "conditional", "access_model": "authorized_target", "credential_mode": "none", "cost_model": "local", "target_contact": "direct_authorized", "languages": ("und",), "regions": ("global",), "commercial_use": "contract_required", "retention_policy": "not_applicable", "customer_display": "not_applicable", "redistribution": "not_applicable", "health_command": "./xti surface nmap readiness", "quota_policy": "Donmuş plandaki hedef, port, hız, probe ve süre bütçelerinin tamamı uygulanır; kapsam kendiliğinden genişlemez.", "retry_policy": "explicit_only", "health_model": "feature_history", "prerequisites": ("Nmap kurulumu ve kullanıcıya ait açıkça yetkilendirilmiş hedef/port/trafik kapsamı gerekir.",)},
    "telemetry:xti-sensor-v1": {"integration_state": "active", "collection_mode": "stream", "access_model": "local", "credential_mode": "none", "cost_model": "local", "target_contact": "none", "languages": ("und",), "regions": ("global",), "commercial_use": "not_applicable", "retention_policy": "allowed_with_terms", "customer_display": "allowed_with_terms", "redistribution": "not_enabled", "health_command": "./xti telemetry capabilities", "quota_policy": "Dosya başına 32 MiB/50.000; firma JSON isteği başına 1.000 normalize kayıt sınırı uygulanır.", "retry_policy": "local_idempotent", "failure_policy": "preserve_local_evidence", "health_model": "static_configuration"},
    "telemetry:cowrie-jsonl": {"integration_state": "conditional", "collection_mode": "stream", "access_model": "local", "credential_mode": "none", "cost_model": "local", "target_contact": "none", "languages": ("und",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "allowed_with_terms", "customer_display": "allowed_with_terms", "redistribution": "not_enabled", "terms_reviewed_at": None, "health_command": "./xti telemetry capabilities", "quota_policy": "Dosya başına 32 MiB ve 50.000 JSONL satırı; desteklenmeyen olaylar açık sayaçla atlanır.", "retry_policy": "local_idempotent", "failure_policy": "preserve_local_evidence", "health_model": "static_configuration", "prerequisites": ("Ayrı ve güvenli işletilen Cowrie kurulumu ile gerçek JSONL çıktısı gerekir.", "Ticari dağıtımda Cowrie lisans ve işletim kararı ayrıca kapatılmalıdır.")},
    "telemetry:cape-report-v1": {"integration_state": "conditional", "collection_mode": "local_derived", "access_model": "local", "credential_mode": "none", "cost_model": "local", "target_contact": "none", "languages": ("und",), "regions": ("global",), "commercial_use": "review_required", "retention_policy": "allowed_with_terms", "customer_display": "allowed_with_terms", "redistribution": "not_enabled", "terms_reviewed_at": None, "health_command": "./xti telemetry capabilities", "quota_policy": "Tamamlanmış report.json dosyası başına 32 MiB; en çok 200 IOC ve 200 güvenli özellik saklanır.", "retry_policy": "local_idempotent", "failure_policy": "preserve_local_evidence", "health_model": "static_configuration", "prerequisites": ("Zararlı örneklerden ayrı ve izole CAPE altyapısı ile gerçek tamamlanmış report.json gerekir.", "Ticari kullanımda CAPE lisans, altyapı ve zararlı örnek işletim kararı ayrıca kapatılmalıdır.")},
}


def _old_profile(entry: SourceCatalogEntry) -> dict:
    mode, records, failure = _KIND_PROFILES[entry.kind]
    disabled = entry.identifier in _VULNERABILITY_IDS
    conditional = entry.credential_required
    integration_state = "disabled" if disabled else "conditional" if conditional else "active"
    if entry.contacts_monitored_target:
        access_model, target_contact = "authorized_target", "direct_authorized"
    else:
        access_model = "configured_account" if entry.credential_required else "public_service"
        target_contact = "provider_query" if mode in {"search", "active_check"} else "none"
    if entry.identifier in _CONTRACT_REQUIRED:
        commercial = retention = customer_display = "contract_required"
    elif entry.identifier in _ATTRIBUTION:
        commercial, retention, customer_display = (
            "allowed_with_terms", "attribution_required", "attribution_required",
        )
    elif entry.contacts_monitored_target:
        commercial = "contract_required"
        retention = customer_display = "not_applicable"
    else:
        commercial = "review_required"
        retention = customer_display = "review_required"
    if disabled:
        commercial = "disabled"
    health_keys = _HEALTH_KEYS.get(entry.identifier, ())
    prerequisites = ()
    if disabled:
        prerequisites = (
            "Kullanıcı zafiyet kapsamını yeniden açmalı ve doğrulanmış ürün veya paket envanteri sağlamalı.",
        )
    elif conditional:
        prerequisites = ("Sağlayıcı hesabı ve gizli yapılandırma tamamlanmalı.",)
    return {
        "integration_state": integration_state,
        "collection_mode": mode,
        "access_model": access_model,
        "credential_mode": "required" if entry.credential_required else "none",
        "cost_model": "paid" if entry.paid_dependency else "free_tier" if entry.credential_required else "free",
        "target_contact": target_contact,
        "languages": _LANGUAGES.get(entry.identifier, ("und",)),
        "regions": _REGIONS.get(entry.identifier, ("global",)),
        "normalized_record_types": records,
        "quota_policy": "Kaynak ve XTI sınırlarının en düşüğü uygulanır; bilinmeyen kullanım sıfır sayılmaz.",
        "retry_policy": "resume_cursor" if mode in {"stream", "snapshot"} else "bounded_safe_read",
        "failure_policy": failure,
        "commercial_use": commercial,
        "retention_policy": retention,
        "customer_display": customer_display,
        "redistribution": "not_enabled" if not disabled else "not_enabled",
        "terms_reviewed_at": "2026-11-20",
        "health_model": "shared_readiness" if health_keys else "feature_history",
        "health_keys": health_keys,
        "health_command": "./xti sources status --details" if health_keys else entry.commands[0],
        "prerequisites": prerequisites,
    }


def _manifest(entry: SourceCatalogEntry, profile: dict) -> SourceManifest:
    mode, records, failure = _KIND_PROFILES[entry.kind]
    values = {
        "identifier": entry.identifier,
        "manifest_version": 1,
        "label": entry.label,
        "kind": entry.kind,
        "purpose": entry.purpose,
        "integration_state": profile.get("integration_state", "active"),
        "collection_mode": profile.get("collection_mode", mode),
        "access_model": profile.get("access_model", "public_service"),
        "credential_mode": profile.get("credential_mode", "none"),
        "cost_model": profile.get("cost_model", "free"),
        "target_contact": profile.get("target_contact", "provider_query"),
        "access": entry.access,
        "languages": profile.get("languages", ("und",)),
        "regions": profile.get("regions", ("global",)),
        "normalized_record_types": profile.get("normalized_record_types", records),
        "provenance_fields": PROVENANCE_FIELDS,
        "quota_policy": profile.get("quota_policy", "Açık iş bütçesi uygulanır; sağlayıcı kotası ayrıca geçerlidir."),
        "retry_policy": profile.get("retry_policy", "bounded_safe_read"),
        "failure_policy": profile.get("failure_policy", failure),
        "commercial_use": profile.get("commercial_use", "review_required"),
        "retention_policy": profile.get("retention_policy", "review_required"),
        "customer_display": profile.get("customer_display", "review_required"),
        "redistribution": profile.get("redistribution", "not_enabled"),
        "terms_reviewed_at": profile.get("terms_reviewed_at", "2026-11-23"),
        "health_model": profile.get("health_model", "feature_history"),
        "health_keys": profile.get("health_keys", ()),
        "health_command": profile["health_command"],
        "prerequisites": profile.get("prerequisites", ()),
        "commands": entry.commands,
        "limits": entry.limits,
        "reference_url": entry.reference_url,
    }
    return validate_manifest(SourceManifest(**values))


def default_manifests() -> tuple[SourceManifest, ...]:
    workflow_ids = tuple(entry.identifier for entry in _WORKFLOW_ENTRIES)
    if len(set(workflow_ids)) != len(workflow_ids):
        raise ValidationError("Kaynak yönetişim iş akışları yinelenen kimlik içeriyor.")
    if set(workflow_ids) != set(_WORKFLOW_PROFILES):
        raise ValidationError("Kaynak yönetişim iş akışı ve profil kayıtları birebir uyuşmalı.")
    old = tuple(_manifest(entry, _old_profile(entry)) for entry in SourceCatalogService().list())
    extra = tuple(_manifest(entry, _WORKFLOW_PROFILES[entry.identifier]) for entry in _WORKFLOW_ENTRIES)
    return tuple(sorted((*old, *extra), key=lambda item: item.identifier))


class SourceGovernanceService:
    """Stable manifest registry with optional, separately sourced health evidence."""

    def __init__(self, manifests: tuple[SourceManifest, ...] | None = None, *, readiness=None) -> None:
        self.manifests = default_manifests() if manifests is None else tuple(manifests)
        self.readiness = readiness
        identifiers = set()
        for manifest in self.manifests:
            validate_manifest(manifest)
            if manifest.identifier in identifiers:
                raise ValidationError("Kaynak yönetişim kataloğu yinelenen kimlik içeriyor.")
            identifiers.add(manifest.identifier)
        if tuple(sorted(self.manifests, key=lambda item: item.identifier)) != self.manifests:
            raise ValidationError("Kaynak yönetişim kataloğu kimliğe göre sıralı olmalı.")
        self._by_id = {item.identifier: item for item in self.manifests}
        self._sha256 = catalog_sha256(self.manifests)

    @staticmethod
    def _manifest_data(manifest: SourceManifest) -> dict:
        return {**manifest.to_dict(), "manifest_sha256": manifest_sha256(manifest)}

    def _health_map(self, *, domain=None, stale_after_hours=24) -> tuple[dict, dict | None]:
        if self.readiness is None:
            return {}, None
        report = self.readiness.show(domain=domain, stale_after_hours=stale_after_hours)
        rows = {row.evidence.identifier: row for row in report.sources}
        return rows, {
            "observed_at": report.observed_at,
            "storage_state": report.storage_state,
            "stale_after_hours": report.stale_after_hours,
            "consistency": "independent_source_reads",
        }

    @staticmethod
    def _health(manifest: SourceManifest, rows: dict) -> dict:
        if manifest.health_model != "shared_readiness":
            return {
                "model": manifest.health_model,
                "state": "feature_history" if manifest.health_model == "feature_history" else "configuration_only",
                "command": manifest.health_command,
                "evidence": [],
            }
        evidence = []
        for key in manifest.health_keys:
            row = rows.get(key)
            if row is None:
                evidence.append({"key": key, "state": "unavailable"})
                continue
            evidence.append({
                "key": key, "state": row.evidence.latest_status,
                "installation": row.evidence.installation,
                "freshness": row.freshness,
                "last_attempt_at": row.evidence.last_attempt_at,
                "last_success_at": row.evidence.last_success_at,
                "record_count": row.evidence.record_count,
                "cooldown_until": row.evidence.cooldown_until,
                "needs_attention": row.needs_attention,
            })
        if not evidence or any(item["state"] == "unavailable" for item in evidence):
            state = "unavailable"
        elif any(item.get("needs_attention") for item in evidence):
            state = "attention"
        else:
            state = "ready"
        return {"model": manifest.health_model, "state": state,
                "command": manifest.health_command, "evidence": evidence}

    def catalog(
        self, *, kind=None, integration_state=None, language=None, region=None,
        include_health=False, domain=None, stale_after_hours=24, offset=0, limit=50,
    ) -> dict:
        supplied = {
            "include_health": include_health,
            "stale_after_hours": stale_after_hours,
            "offset": offset,
            "limit": limit,
        }
        supplied.update({
            key: value for key, value in {
                "kind": kind, "integration_state": integration_state,
                "language": language, "region": region, "domain": domain,
            }.items() if value is not None
        })
        normalized = governance_parameters("sources.catalog", supplied)
        kind = normalized.get("kind")
        integration_state = normalized.get("integration_state")
        language = normalized.get("language")
        region = normalized.get("region")
        include_health = normalized["include_health"]
        domain = normalized.get("domain")
        stale_after_hours = normalized["stale_after_hours"]
        offset, limit = normalized["offset"], normalized["limit"]
        selected = [item for item in self.manifests
                    if (kind is None or item.kind == kind)
                    and (integration_state is None or item.integration_state == integration_state)
                    and (language is None or language in item.languages)
                    and (region is None or region in item.regions)]
        rows, health_snapshot = self._health_map(
            domain=domain, stale_after_hours=stale_after_hours,
        ) if include_health else ({}, None)
        page = []
        for manifest in selected[offset:offset + limit]:
            data = self._manifest_data(manifest)
            if include_health:
                data["health"] = self._health(manifest, rows)
            page.append(data)
        return {
            "contract_version": CONTRACT_VERSION,
            "catalog_sha256": self._sha256,
            "catalog_count": len(self.manifests),
            "filtered_count": len(selected),
            "offset": offset, "limit": limit,
            "has_more": offset + limit < len(selected),
            "next_offset": offset + limit if offset + limit < len(selected) else None,
            "filters": {"kind": kind, "integration_state": integration_state,
                        "language": language, "region": region},
            "health_snapshot": health_snapshot,
            "sources": page,
            "notes": [
                "Manifest yapılandırma ve yönetişim sözleşmesidir; canlı kaynak erişimi değildir.",
                "Koşullu kaynak, gereksinimi sağlanmadan aktif kabul edilmez.",
                "Kaynak kaydı aday veya iddiadır; doğrulanmış tehdit hükmü değildir.",
            ],
        }

    def get(self, *, identifier, include_health=False, domain=None, stale_after_hours=24) -> dict:
        supplied = {
            "identifier": identifier,
            "include_health": include_health,
            "stale_after_hours": stale_after_hours,
        }
        if domain is not None:
            supplied["domain"] = domain
        normalized = governance_parameters("sources.get", supplied)
        identifier = normalized["identifier"]
        include_health = normalized["include_health"]
        domain = normalized.get("domain")
        stale_after_hours = normalized["stale_after_hours"]
        manifest = self._by_id.get(identifier)
        if manifest is None:
            raise SourceGovernanceError("not_found", "Bu kimlikte kaynak manifesti bulunamadı.")
        rows, snapshot = self._health_map(
            domain=domain, stale_after_hours=stale_after_hours,
        ) if include_health else ({}, None)
        data = self._manifest_data(manifest)
        if include_health:
            data["health_snapshot"] = snapshot
            data["health"] = self._health(manifest, rows)
        return data

    def validate(self) -> dict:
        states = Counter(item.integration_state for item in self.manifests)
        kinds = Counter(item.kind for item in self.manifests)
        rights = Counter(item.commercial_use for item in self.manifests)
        return {
            "contract_version": CONTRACT_VERSION,
            "valid": True,
            "catalog_sha256": self._sha256,
            "source_count": len(self.manifests),
            "integration_states": dict(sorted(states.items())),
            "commercial_states": dict(sorted(rights.items())),
            "kinds": dict(sorted(kinds.items())),
            "required_provenance_fields": list(PROVENANCE_FIELDS),
            "issues": [],
            "notes": [
                "Doğrulama ağ, veritabanı veya haricî araç çalıştırmaz.",
                "Geçerli manifest canlı erişim, veri hakkı veya kaynak doğruluğu garantisi değildir.",
            ],
        }
