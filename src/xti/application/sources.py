"""The reviewed source catalog, independent from terminal and persistence."""

from xti.domain.sources import SourceCatalogEntry
from xti.domain.news import NEWS_SOURCES, NEWS_NOTES
from xti.domain.warninglists import POLICIES as WARNINGLIST_POLICIES, LICENSE, LICENSE_URL
from xti.domain.indicator_enrichment import PROVIDERS as ENRICHMENT_PROVIDERS


_CATALOG = (
    SourceCatalogEntry(
        identifier="crt.sh",
        label="crt.sh Certificate Search",
        kind="passive_archive",
        purpose="Sertifika kayıtlarında görülen domain ve alt domain adaylarını bulur.",
        access="Herkese açık HTTPS araması; XTI ücretli anahtar kullanmaz.",
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=("scan", "watch", "surface discover", "surface watch"),
        limits=(
            "Yalnız yayımlanmış sertifika şeffaflığı kayıtlarını kapsar.",
            "XTI yanıt, süre ve tekrar sayılarını güvenli sınırlar içinde tutar.",
        ),
        reference_url="https://crt.sh/",
    ),
    SourceCatalogEntry(
        identifier="theharvester-archives",
        label="theHarvester P0 Common Crawl ve Wayback Archive",
        kind="passive_archive",
        purpose=(
            "Arşivlenmiş web adreslerinden kayıtlı kökün kesin alt alan adı "
            "adaylarını bulur."
        ),
        access=(
            "İsteğe bağlı, tam commit'e sabitlenmiş ayrı açık kaynak araç; seçilen "
            "iki kaynak için hesap veya ücretli anahtar kullanılmaz."
        ),
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=(
            "surface discover KOK --source theharvester",
            "surface watch KOK --source theharvester",
        ),
        limits=(
            "Yalnız Common Crawl ve Wayback Archive P0 hostname sonuçları kabul edilir.",
            "Common Crawl yalnız katalogdaki en yeni bitiş tarihinden geriye "
            "365 günlük indeksleri kapsar; bütün tarihsel arşiv değildir.",
            "Arşiv v3 profili Common Crawl için 150, Wayback için 90 saniye "
            "ve kaynak başına en çok 30 istek kullanır; "
            "süre, istek veya sonuç sınırında kalan kapsam kısmi gösterilir.",
            "HTTP/TLS/bağlantı hatası boş yanıt sayılmaz; 429/503 sonrasında "
            "anında tekrar yapılmaz ve kaynak bekleme bilgisi korunur.",
            "Common Crawl istekleri yanıt bittikten sonra en az bir saniye "
            "arayla gönderilir; bağlantı hatasında bütçe yeterliyse tek tekrar "
            "öncesinde 60 saniye beklenir.",
            "DNS çözümleme, e-posta toplama, ekran görüntüsü, takeover ve aktif "
            "hedef işlemleri kapalıdır.",
            "Arşivde görülen ad sahiplik veya güncel erişilebilirlik kanıtı değildir.",
        ),
        reference_url="https://github.com/laramies/theHarvester",
    ),
    SourceCatalogEntry(
        identifier="urlscan",
        label="urlscan Search API",
        kind="passive_archive",
        purpose="Daha önce yapılmış herkese açık web incelemelerinde domain adaylarını bulur.",
        access="Kimliksiz küçük kota; XTI ücretli anahtar kullanmaz.",
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=("scan", "watch"),
        limits=(
            "XTI yeni web taraması göndermez; yalnız mevcut arşivi arar.",
            "Bir sorguda en fazla 100 kayıt alınır; tarih ve kota sınırı sonuçta gösterilir.",
            "Ticari ürüne veri dahil etmek için sağlayıcı anlaşması gerekir: https://urlscan.io/terms/",
        ),
        reference_url="https://docs.urlscan.io/pages/api-intro",
    ),
    SourceCatalogEntry(
        identifier="google-public-dns",
        label="Google Public DNS DoH",
        kind="dns_resolver",
        purpose="A, AAAA, MX, SPF ve DMARC DNS kayıtlarını gözlemler.",
        access="Herkese açık DNS-over-HTTPS; ücretli anahtar kullanılmaz.",
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=(
            "scan --check", "surface check", "surface mail check",
            "surface services check", "surface monitor",
        ),
        limits=(
            "Yalnız komutun gerektirdiği sabit DNS kayıt türleri sorulur.",
            "DNS yanıtı sahiplik, güvenlik veya teslimat kararı sayılmaz.",
        ),
        reference_url="https://developers.google.com/speed/public-dns/docs/doh",
    ),
    SourceCatalogEntry(
        identifier="explicit-https-head",
        label="Açık komutla HTTPS HEAD kontrolü",
        kind="active_check",
        purpose="Açık kullanıcı komutundaki adayın veya onaylı kökün TLS/HTTPS durumunu gözlemler.",
        access="Yalnız açık --check seçimi veya surface kapsam onayıyla; ücretli servis yoktur.",
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=True,
        commands=("scan --check", "surface check", "surface monitor"),
        limits=(
            "Yalnız doğrulanmış genel IP, HTTPS portu ve HEAD isteği kullanılır.",
            "Yönlendirme, sayfa gövdesi, özel ağ ve kapsam genişletmesi yoktur.",
        ),
        reference_url="https://www.rfc-editor.org/rfc/rfc9110.html#name-head",
    ),
    SourceCatalogEntry(
        identifier="explicit-tcp-connect",
        label="Açık komutla sınırlı TCP servis kontrolü",
        kind="active_check",
        purpose="Onaylı domainin açıkça belirtilen genel IP'sinde sabit TCP portlarını gözlemler.",
        access=(
            "Etkin domain kapsamı, güncel DNS eşleşmesi, kesin IP ve kullanıcı gerekçesi gerekir; "
            "ücretli servis yoktur."
        ),
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=True,
        commands=("surface services check", "surface monitor --checks services"),
        limits=(
            "Yalnız sabit 10 TCP portuna bağlantı denemesi yapılır; banner veya veri alınmaz.",
            "Tek kesin genel IP kontrol edilir; açık port ürün, sürüm veya zafiyet kararı değildir.",
        ),
        reference_url="https://www.rfc-editor.org/rfc/rfc9293.html",
    ),
    SourceCatalogEntry(
        identifier="feodo-tracker",
        label="abuse.ch Feodo Tracker Botnet C2 Blocklist",
        kind="community_threat_intelligence_feed",
        purpose=(
            "Son 30 günde etkin veya görülmüş botnet komuta-kontrol IP'lerini "
            "kaynaklı yerel IOC iddiaları olarak sağlar."
        ),
        access=(
            "Yalnız açık 'ioc sync --source feodo' komutuyla saldırgan olmayan "
            "30 günlük tam JSON listesi; anahtar ve ücretli servis yoktur."
        ),
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=(
            "ioc sync --source feodo", "ioc status --source feodo",
            "ioc list", "ioc lookup ipv4 IP_ADRESI",
        ),
        limits=(
            "Kaynak hatası veya biçim bozukluğu boş liste sayılmaz; önceki geçerli "
            "IOC iddiaları korunur.",
            "Yalnız başarılı tam snapshot'ta artık bulunmayan kaynak iddiaları geçmişi "
            "silinmeden geri çekilir.",
            "50/100 güven kaynağın puanı değil XTI yerel nötr politikasıdır; IOC'ler "
            "otomatik engellenmez.",
        ),
        reference_url="https://feodotracker.abuse.ch/blocklist/",
    ),
    SourceCatalogEntry(
        identifier="certpl-warning-list",
        label="CERT Polska Dangerous Websites Warning List",
        kind="official_phishing_domain_feed",
        purpose=(
            "Son bir ayda listeye eklenmiş ve hâlâ etkin olan aldatıcı domainleri "
            "kaynaklı yerel IOC iddiaları olarak sağlar."
        ),
        access=(
            "Yalnız açık 'ioc sync --source certpl' komutuyla resmî son-ay metin "
            "listesi; anahtar ve ücretli servis yoktur."
        ),
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=(
            "ioc sync --source certpl", "ioc status --source certpl",
            "ioc list --type domain", "ioc lookup domain ALAN_ADI",
        ),
        limits=(
            "Kaynak ağırlıklı olarak Polonya kullanıcılarını hedefleyen aldatıcı "
            "domainleri kapsar; küresel phishing kapsamı değildir.",
            "Son-ay dilimi kişisel depolamayı sınırlar; daha eski etkin kayıtların "
            "tam arşivi değildir.",
            "Kaynak hatası veya biçim bozukluğu boş liste sayılmaz; önceki geçerli "
            "IOC iddiaları korunur ve IOC otomatik engellenmez.",
        ),
        reference_url="https://cert.pl/lista-ostrzezen/",
    ),
    SourceCatalogEntry(
        identifier="hibp-public-breach-catalog",
        label="Have I Been Pwned Public Breach Catalog",
        kind="public_incident_metadata_catalog",
        purpose="Yayımlanmış olayların başlık, domain, tarih, veri kategorisi ve kaynak sınıflarını araştırır.",
        access=(
            "Açık 'notices refresh' veya 'collect --task notices-hibp' seçimiyle anahtarsız kamu kataloğu okunur; "
            "ücretli servis yoktur. Kota veya erişim sınırı uygulanabilir."
        ),
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=(
            "notices refresh", "notices status", "notices search KURULUS",
            "notices search --domain ALAN_ADI", "notices show KAYNAK_KIMLIGI",
            "notices run-show CALISMA_KIMLIGI",
            "collect ALAN_ADI --task notices-hibp",
        ),
        limits=(
            "Yalnız https://haveibeenpwned.com/api/v3/breaches okunur; hedef domain veya kişilere istek gönderilmez.",
            "E-posta, hesap, parola ve stealer-log içerik sorguları bu entegrasyonda yoktur.",
            "Kaynağın doğrulama ve diğer sınıfları korunur; XTI ihlal kararı üretmez. Domain filtresi birebir, metin araması adaydır.",
            "Kaynak verisi CC BY 4.0 ile Have I Been Pwned — https://haveibeenpwned.com atfıyla gösterilir.",
            "16 MiB ve 10.000 kayıt sınırı vardır; hata son başarılı kataloğu silmez. Kalan komutlar yerel kopyada çalışır.",
        ),
        reference_url="https://haveibeenpwned.com/API/v3",
    ),
    SourceCatalogEntry(
        identifier="threatcluster-ransomware-claims",
        label="ThreatCluster Public Ransomware Victim Feed",
        kind="public_ransomware_claim_feed",
        purpose=(
            "Ransomware ve şantaj gruplarının leak sitelerinde adını yayımladığı "
            "kuruluşlara ilişkin son dönem iddialarını araştırır."
        ),
        access=(
            "Yalnız açık 'ransomware recent', 'ransomware refresh' veya "
            "'ransomware watch-refresh-all/watch-monitor' komutuyla anahtarsız HTTPS "
            "JSON akışı; "
            "veri CC BY 4.0 atfıyla sunulur ve ücretli servis kullanılmaz."
        ),
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=(
            "ransomware recent", "ransomware recent KURULUS_VEYA_DOMAIN",
            "ransomware recent --status listed --limit 50", "ransomware refresh",
            "ransomware watch-run IZLEME_KIMLIGI", "ransomware watch-refresh-all",
            "ransomware watch-monitor --cycles 3 --interval 3600 --duration 86400",
            "ransomware watch-monitor-list",
            "ransomware watch-monitor-show OTURUM_KIMLIGI",
            "ransomware watch-timeline IZLEME_KIMLIGI",
            "ransomware watch-identity-candidates IZLEME_KIMLIGI",
            "ransomware watch-identity-review IZLEME_KIMLIGI ADAY_KIMLIGI",
            "ransomware watch-identity-review-show ADAY_KIMLIGI",
            "ransomware source-compare",
            "ransomware source-review KARSILASTIRMA_KIMLIGI",
            "ransomware source-review-show KARSILASTIRMA_KIMLIGI",
        ),
        limits=(
            "Kayıt, grubun yayımladığı doğrulanmamış iddiadır; gerçekleşmiş ihlal veya "
            "veri sızıntısı kararı değildir.",
            "XTI yalnız ThreatCluster HTTPS akışına bağlanır; Tor/leak-site adreslerini "
            "açmaz, ham gönderi metnini veya ekran görüntüsünü almaz.",
            "Açık refresh komutu tam snapshot çalışma/değişiklik geçmişini yerelde tutar; "
            "kuruluş/domain izlemeleri yalnız yeni/değişen eşleşmeyi yerel kutuya taşır.",
            "Ağsız zaman çizelgesi değişmeyen tekrarları yeni olay saymaz; aynı kaynak "
            "kimliğinin pencereden çıkıp geri gelmesini yeniden görünme olarak ayırır.",
            "Ağsız kimlik adayı görünümü yakın snapshot geçişlerinde en az iki ortak "
            "alanı açıklar; kayıtları otomatik birleştirmez veya alarm üretmez.",
            "Kimlik adayı kararı açık kullanıcı komutuyla eklemeli geçmişe yazılır; "
            "karar kaynak kimliklerini, zaman çizelgesini veya alarm durumunu değiştirmez.",
            "Kaynak karşılaştırması son yerel ThreatCluster ve RansomLook snapshot'larını "
            "yalnız tam kuruluş ve ek grup/zaman kanıtıyla ağsız karşılaştırır; kayıtları "
            "birleştirmez, yazmaz veya ihlal hükmü üretmez.",
            "Kaynak karşılaştırma kararı gerekçeli ve silinmeyen olay geçmişidir; iki "
            "kaynak kaydını birleştirmez, alarm veya ihlal hükmü üretmez.",
            "Toplu komut tek seferliktir; monitor yalnız terminal açıkken sınırlı tur ve "
            "süreyle tekrarlar. Oturum/tur geçmişi kalıcıdır; zamanlayıcı veya görünmez "
            "arka plan servisi kurulmaz.",
        ),
        reference_url="https://threatcluster.io/feeds",
    ),
    SourceCatalogEntry(
        identifier="ransomlook-ransomware-posts",
        label="RansomLook Public Posts API",
        kind="public_ransomware_claim_feed",
        purpose=(
            "Ransomware gruplarının yayımladığı son yedi günlük kuruluş başlıklarını "
            "ThreatCluster'dan ayrı ikinci açık kaynak olarak araştırır."
        ),
        access=(
            "Yalnız açık 'ransomware recent/refresh --source ransomlook' komutlarıyla "
            "anahtarsız HTTPS JSON okuması; API verisi CC BY 4.0 atfıyla sunulur."
        ),
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=(
            "ransomware source-evaluation",
            "ransomware recent --source ransomlook",
            "ransomware recent KURULUS --source ransomlook --limit 50",
            "ransomware refresh --source ransomlook",
            "ransomware status --source ransomlook",
            "ransomware watch-add AD SORGU --kind organization --source ransomlook",
            "ransomware watch-list --source ransomlook",
            "ransomware watch-run IZLEME_KIMLIGI --source ransomlook",
            "ransomware source-compare",
            "ransomware source-review KARSILASTIRMA_KIMLIGI",
            "ransomware source-review-show KARSILASTIRMA_KIMLIGI",
        ),
        limits=(
            "Kayıt bir grubun yayımladığı doğrulanmamış iddiadır; gerçekleşmiş ihlal "
            "veya veri sızıntısı kararı değildir.",
            "Seçilen uç nokta yalnız grup, kuruluş başlığı ve kaynak keşif zamanı verir; "
            "ülke, sektör, domain ve güncel/kaldırılmış durum uydurulmaz.",
            "Recent önizlemesi yazmasızdır; açık refresh tam snapshot farklarını ayrı "
            "RansomLook tablolarına kaydeder ve ThreatCluster geçmişiyle birleştirmez.",
            "İlk snapshot ve ilk izleme çalışması alarm değildir; sonraki yeni kuruluş "
            "başlığı eşleşmeleri kalıcı çalışma içinde inceleme adayı olarak ayrılır.",
            "Kaynak domain sağlamadığı için RansomLook tarafında domain izlemesi yoktur; "
            "kayan pencereden çıkış silinme, çözüm veya yanlış iddia kanıtı değildir.",
            "Bu dar izleme ortak gelen kutusuna ya da otomatik bildirime bağlı değildir; "
            "watch-run/watch-run-show terminal ve JSON sonucunda incelenir.",
            "Kaynak karşılaştırması yalnız iki son başarılı yerel snapshot'ın ortak "
            "kuruluş+grup/zaman kanıtını gösterir; fuzzy eşleşme veya otomatik olay "
            "birleştirme yapmaz.",
            "İnsan kararı karşılaştırmaya bağlı ayrı bir inceleme geçmişidir; kaynak "
            "iddiasını değiştirmez, birleştirmez veya doğrulanmış ihlal saymaz.",
            "XTI Tor/leak-site adreslerine bağlanmaz ve ham içerik toplamaz.",
        ),
        reference_url="https://www.ransomlook.io/doc/",
    ),
    SourceCatalogEntry(
        identifier="mitre-attack-enterprise",
        label="MITRE ATT&CK Enterprise STIX 2.1",
        kind="official_cti_knowledge_base",
        purpose=(
            "Grup, kampanya, malware, teknik, alt teknik ve taktik kataloğunu "
            "kaynak kimlikleriyle sağlar; etkin grup/kampanya/malware ve seçili "
            "ilişkiler ayrıca yerel CTI bilgi tabanına alınır."
        ),
        access=(
            "Yalnız açık 'cti attack-sync' komutuyla sürümü sabitlenmiş resmî "
            "Enterprise ATT&CK STIX dosyası; anahtar ve ücretli servis yoktur."
        ),
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=(
            "cti attack-sync", "cti attack-status", "cti attack-search SORGU",
            "cti attack-show ATTACK_KIMLIGI", "cti search", "cti entity-list",
            "cti relation-list",
        ),
        limits=(
            "Katalog grup, kampanya, malware, teknik, alt teknik, taktik ve seçili "
            "uses/attributed-to/subtechnique-of ilişkilerini içerir; tool, savunma "
            "ve diğer STIX nesneleri kapsam dışıdır.",
            "Teknik–taktik bağları kill_chain_phases alanından türetilmiş olarak "
            "gösterilir; STIX ilişkisi sayılmaz. CTI bilgi tabanı etkin grup, "
            "kampanya, malware ve aralarındaki uses/attributed-to alt kümesini korur.",
            "ATT&CK intrusion-set/grup kaydı yerelde threat-actor etiketiyle görünür; "
            "bu otomatik aktör atfı veya tehdit hükmü değildir.",
            "50/100 güven MITRE'ın puanı değil XTI yerel nötr politikasıdır; "
            "senkron yalnız açık komutla yapılır.",
        ),
        reference_url="https://attack.mitre.org/resources/attack-data-and-tools/",
    ),
    SourceCatalogEntry(
        identifier="cisa-kev",
        label="CISA Known Exploited Vulnerabilities",
        kind="official_vulnerability_catalog",
        purpose=(
            "Gerçek saldırılarda istismar edildiği bilinen CVE kayıtlarını ve "
            "CISA'nın gerekli işlem bilgisini sağlar."
        ),
        access=(
            "Yalnız açık 'vuln sync --source kev' komutuyla resmî CISA HTTPS "
            "JSON akışı; anahtar ve ücretli servis yoktur."
        ),
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=("vuln sync --source kev", "vuln status", "vuln list", "vuln show"),
        limits=(
            "KEV kaydı bir zafiyetin gerçek dünyada istismar edildiğini gösterir; "
            "izlenen varlığın etkilendiğini tek başına kanıtlamaz.",
            "Kaynak hatası boş katalog sayılmaz; önceki doğrulanmış katalog korunur.",
        ),
        reference_url="https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
    ),
    SourceCatalogEntry(
        identifier="first-epss",
        label="FIRST Exploit Prediction Scoring System",
        kind="official_vulnerability_probability",
        purpose=(
            "CVE başına önümüzdeki 30 gün için nüfus düzeyinde istismar olasılığı "
            "ve yüzdelik dilim sağlar."
        ),
        access=(
            "Yalnız açık 'vuln sync --source epss' komutuyla FIRST'ün önerdiği "
            "günlük tam CSV; kayıt ve ücretli anahtar yoktur."
        ),
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=(
            "vuln sync --source epss", "vuln status --source epss",
            "vuln list --source epss", "vuln show --source epss",
        ),
        limits=(
            "EPSS önem, etki, tam risk veya izlenen varlıkta maruziyet kanıtı değildir.",
            "Yalnız güncel tam puan kümesi yerelde tutulur; günlük tarihçe çoğaltılmaz.",
        ),
        reference_url="https://www.first.org/epss/data",
    ),
    SourceCatalogEntry(
        identifier="nist-nvd-cve",
        label="NIST National Vulnerability Database CVE API 2.0",
        kind="official_vulnerability_context",
        purpose=(
            "İstenen CVE için açıklama, durum, yayın/değişiklik zamanı ve kaynaklı "
            "CVSS değerlendirmelerini sağlar."
        ),
        access=(
            "Yalnız açık 'vuln sync --source nvd --cve ...', sınırlı "
            "'vuln enrich-nvd' / 'vuln tracked-nvd-refresh' ya da tek sayfalık "
            "'vuln nvd-window-fetch' komutlarıyla resmî "
            "NVD API isteği; bu dilimde anahtar ve ücretli servis yoktur."
        ),
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=(
            "vuln sync --source nvd --cve CVE-YIL-SAYI",
            "vuln plan", "vuln enrich-nvd --limit 3",
            "vuln tracked-nvd-plan", "vuln tracked-nvd-refresh --limit 3",
            "vuln nvd-window-plan", "vuln nvd-window-fetch",
            "vuln nvd-window-list", "vuln nvd-window-coverage",
            "vuln nvd-window-gap-plan", "vuln nvd-window-gap-fetch",
            "vuln nvd-window-operations",
            "vuln nvd-window-show", "vuln nvd-window-restart",
            "vuln status --source nvd", "vuln list --source nvd",
            "vuln show --source nvd", "vuln applicability CVE-YIL-SAYI",
        ),
        limits=(
            "Tek-CVE veya açıkça seçilmiş en fazla yedi günlük değişiklik penceresi "
            "yerelde tutulur; tam NVD aynası değildir.",
            "Pencere yürütmesi çağrı başına bir ve en fazla 100 kayıtlık sayfa alır; "
            "başarılı sayfa ile ilerleme aynı transaction'da kaydedilir.",
            "Tamamlanan pencereler kapsama görünümüne girer; yeniden başlatma açık "
            "gerekçe ve silinmeyen denetim olayı gerektirir.",
            "Boşluk planı en fazla 366 günlük görünümü yedi günlük adaylara böler; "
            "ağ isteği göndermez, kayıt yazmaz ve adayları otomatik çalıştırmaz.",
            "Boşluk yürütmesi en fazla üç adayın her birinden yalnız bir sayfa alır, "
            "istek aralığını korur ve ilk kaynak hatasında durur.",
            "Operasyon özeti seçilen dönemin pencere, hata, son ilerleme ve kapsama "
            "durumunu tek salt-okunur anlık görüntüde birleştirir.",
            "Plan yürütme bir komutta en fazla beş ardışık istek gönderir, yanıtlar "
            "arasında en az 6,5 saniye bırakır ve ilk hatada durur.",
            "CVSS teknik önem bağlamıdır; istismar olasılığı, KEV veya varlık maruziyeti değildir.",
        ),
        reference_url="https://nvd.nist.gov/developers/vulnerabilities",
    ),
    SourceCatalogEntry(
        identifier="osv-dev",
        label="OSV.dev Open Source Vulnerability API",
        kind="vulnerability_advisory_aggregator",
        purpose=(
            "Açıkça seçilen CVE için açık kaynak paket/sürüm bağlamını ve "
            "ADVISORY türündeki kaynak başvurularını önizler."
        ),
        access=(
            "Yalnız açık 'vuln advisory-preview CVE-YIL-SAYI' veya insan onaylı "
            "'vuln advisory-evidence-add' komutuyla resmî OSV API isteği; "
            "anahtar ve ücretli servis yoktur."
        ),
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=(
            "vuln advisory-preview CVE-YIL-SAYI",
            "vuln advisory-evidence-add INCELEME_KIMLIGI",
        ),
        limits=(
            "OSV bir toplayıcıdır; kayıt üretici hükmü veya varlık maruziyeti değildir.",
            "Yalnız kullanıcının tam HTTPS adresini seçtiği ekleme komutu, güncel "
            "OSV ADVISORY üyeliğini doğruladıktan sonra destek kanıtı yazar.",
            "Tek CVE yanıtı 8 MiB, terminal paket ve duyuru görünümü ayrı ayrı 200 kayıtla sınırlıdır.",
        ),
        reference_url="https://google.github.io/osv.dev/api/",
    ),
    SourceCatalogEntry(
        identifier="canonical-ubuntu-osv",
        label="Canonical Ubuntu Security OSV records",
        kind="official_vendor_osv",
        purpose=(
            "Açıkça seçilen CVE için Ubuntu yayınları, kaynak paketleri, etkilenen "
            "sürümler ve düzeltilmiş sürüm sınırlarını üreticinin OSV kaydından önizler."
        ),
        access=(
            "Yalnız açık 'vuln ubuntu-preview CVE-YIL-SAYI' komutuyla Canonical'ın "
            "resmî GitHub veri deposundaki tek UBUNTU-CVE JSON dosyası; anahtar ve ücret yoktur."
        ),
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=(
            "vuln ubuntu-preview CVE-YIL-SAYI",
            "vuln ubuntu-match CVE-YIL-SAYI --ecosystem Ubuntu:24.04:LTS --source-package PAKET --version SURUM",
            "vuln ubuntu-inventory-match UBUNTU_PAKET_KIMLIGI CVE-YIL-SAYI",
            "vuln ubuntu-inventory-scan CVE-YIL-SAYI --domain ALAN_ADI",
            "vuln ubuntu-evidence-add INCELEME_KIMLIGI UBUNTU_PAKET_KIMLIGI --summary ACIKLAMA",
            "vuln ubuntu-evidence-check KANIT_KIMLIGI",
            "vuln ubuntu-evidence-plan --domain ALAN_ADI",
            "vuln ubuntu-evidence-scan --domain ALAN_ADI --limit 10",
        ),
        limits=(
            "Sabit HTTPS yolu, yönlendirme reddi, 30 saniye ve 8 MiB yanıt sınırı vardır.",
            "Kayıt yalnız Ubuntu ürün/yayın bağlamında Canonical'ın üretici verisidir; "
            "başka dağıtımlara veya yerel kurulu pakete otomatik uygulanmaz.",
            "Paket karşılaştırması yalnız açıkça verilen yayın, kaynak paket ve Debian sürümünü kullanır.",
            "Envanter karşılaştırması yalnız kullanıcı doğrulamalı binary→source paket kanıtını kullanır.",
            "Envanter taraması en fazla 10.000 etkin kaydı doğrular, tek Canonical kaydı alır ve 1–500 paket gösterir.",
            "Kalıcı destek kanıtı yalnız aynı varlıktaki insan maruziyeti ve güncel tek affected bağı için açık seçimle yazılır.",
            "Kanıt kontrolü güncel paket ve Canonical sonucunu salt okunur karşılaştırır; kararı veya kanıtı değiştirmez.",
            "Toplu plan ağsızdır; toplu tarama en fazla 20 kanıt seçer ve aynı CVE için tek kaynak çağrısı kullanır.",
            "Önizleme ve karşılaştırma veritabanı yazmaz veya maruziyet kararı üretmez.",
        ),
        reference_url="https://documentation.ubuntu.com/security/security-updates/osv/",
    ),
    SourceCatalogEntry(
        identifier="redhat-csaf-vex",
        label="Red Hat Product Security per-CVE CSAF VEX",
        kind="official_vendor_vex",
        purpose=(
            "Seçilen CVE için Red Hat ürün ve bileşenlerinin fixed, known_affected, "
            "known_not_affected ve under_investigation durumlarını önizler; açık komutla "
            "kesin yerel RPM+dağıtım bağıyla karşılaştırır ve insan seçimiyle kaynak özetli "
            "kanıta dönüştürür."
        ),
        access=(
            "Yalnız açık 'vuln vendor-preview', 'vuln vendor-match' veya "
            "'vuln vendor-evidence-add' komutuyla "
            "sabit resmî Red Hat HTTPS VEX dosyası; anahtar ve ücret yoktur."
        ),
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=(
            "vuln vendor-preview CVE-YIL-SAYI --provider redhat",
            "vuln vendor-match PAKET_KIMLIGI CVE-YIL-SAYI --provider redhat",
            "vuln vendor-evidence-add INCELEME_KIMLIGI PAKET_KIMLIGI",
            "vuln vendor-evidence-check KANIT_KIMLIGI",
        ),
        limits=(
            "VEX beyanı yalnız Red Hat ürünleri için Red Hat'in kaynak gerçeğidir.",
            "Eşleşme NEVRA, PURL ve dağıtım CPE bağını birlikte gerektirir; sonuç yine "
            "Red Hat beyanıdır ve insan maruziyet kararını değiştirmez. Kalıcı seçim "
            "maruziyet, paket, kaynak özeti ve tam ürün bağını birlikte saklar; açık kontrol "
            "komutu güncel kaynakla salt okunur karşılaştırır.",
            "Tek belge 16 MiB, bağlantı 30 saniye ve terminal örnekleri açık "
            "gösterim sınırlarıyla kısıtlıdır; önizleme yazmaz.",
        ),
        reference_url="https://security.access.redhat.com/data/csaf/v2/vex/",
    ),
    SourceCatalogEntry(
        identifier="suse-csaf-vex",
        label="SUSE Product Security per-CVE CSAF VEX",
        kind="official_vendor_vex",
        purpose=(
            "Seçilen CVE için SUSE ve openSUSE ürün/bileşenlerinin resmî VEX "
            "durumlarını yazmasız önizler."
        ),
        access=(
            "Yalnız açık 'vuln vendor-preview CVE-YIL-SAYI --provider suse' "
            "komutuyla sabit resmî SUSE HTTPS VEX dosyası; anahtar ve ücret yoktur."
        ),
        credential_required=False,
        paid_dependency=False,
        contacts_monitored_target=False,
        commands=("vuln vendor-preview CVE-YIL-SAYI --provider suse",),
        limits=(
            "VEX beyanı yalnız SUSE/openSUSE ürünleri için SUSE'nin kaynak gerçeğidir.",
            "Bu dilimde yerel SUSE paket eşleştirmesi veya kalıcı kanıt yazımı yoktur; "
            "önizleme insan maruziyet kararını değiştirmez.",
            "Tek belge 16 MiB, bağlantı 30 saniye ve terminal örnekleri açık "
            "gösterim sınırlarıyla kısıtlıdır.",
        ),
        reference_url="https://ftp.suse.com/pub/projects/security/csaf-vex/",
    ),
)


class SourceCatalogService:
    """Return the reviewed catalog without network or storage access."""

    def list(self) -> tuple[SourceCatalogEntry, ...]:
        return _CATALOG + tuple(SourceCatalogEntry(
            identifier='news:' + source.key, label=source.name, kind='publisher_news_feed',
            purpose='RSS/Atom başlık, sınırlı özet, yayın tarihi ve özgün bağlantıyı kaynaklı yerel kanıt olarak saklar.',
            access='Herkese açık HTTPS akışı; ücretli anahtar kullanılmaz. Yayıncının kota ve erişim koşulları geçerlidir.',
            credential_required=False, paid_dependency=False, contacts_monitored_target=False,
            commands=('news sources', 'news refresh --source ' + source.key,
                      'news list --source ' + source.key, 'search --kind news'),
            limits=(*NEWS_NOTES, source.attribution,
                    'Yalnız seçilen sabit yayıncı akışı alınır; keyfî adres, makale gövdesi veya ek dosya indirilmez.'),
            reference_url=source.homepage,
        ) for source in NEWS_SOURCES) + (
            SourceCatalogEntry(
                identifier='mentions:tavily', label='Tavily firma ve tedarikçi içerik araması',
                kind='company_content_search',
                purpose='Seçilen kuruluş veya tedarikçi adına web/haber araması yapar; bağlantı, başlık, sınırlı özet ve eşleşme nedenini saklar.',
                access='Tavily hesabına ait API anahtarı gerekir. Ücretsiz kredi kullanılabilir; hesap kotası ve ücretli kullanım ayarları sağlayıcıda yönetilir.',
                credential_required=True, paid_dependency=False, contacts_monitored_target=False,
                commands=('mentions search --organization KURULUS_KIMLIGI',
                          'mentions search --supplier TEDARIKCI_KIMLIGI',
                          'mentions list', 'mentions status', 'search --kind mention'),
                limits=(
                    'Bir açık arama basic derinlikte tek istek yapar; otomatik tekrar veya ücretli paket yükseltme yoktur.',
                    'En çok 20 sıralanmış sonuç alınır; bütün interneti veya tüm firma haberlerini kapsadığı iddia edilmez.',
                    'Ad/domain eşleşmesi araştırma adayıdır; doğrulanmış kuruluş kimliği veya tehdit kararı değildir.',
                    'Aranan firma bilgisi Tavily hizmetine gönderilir; XTI sonuç sayfalarını doğrudan ziyaret etmez.',
                    'API anahtarı kaynak listesinde, kayıtlarda veya engine çıktısında bulunmaz.',
                    'Ücretsiz kredi miktarı ve erişim koşulları değişebilir; kalan hesap bakiyesi yerel kayıtlardan kesin hesaplanamaz.',
                ),
                reference_url='https://docs.tavily.com/documentation/api-reference/endpoint/search',
            ),
        ) + tuple(SourceCatalogEntry(
            identifier='warninglist:' + policy.id, label='MISP: ' + policy.label,
            kind='reference_context', purpose=policy.label + ' için kaynaklı domain/IP bağlamı sunar.',
            access='Herkese açık GitHub HTTPS kaynağı; API anahtarı veya ücretli abonelik gerekmez. Sağlayıcı erişim sınırları geçerlidir.',
            credential_required=False, paid_dependency=False, contacts_monitored_target=False,
            commands=('warninglists sync --list ' + policy.id, 'warninglists status',
                      'warninglists lookup DOMAIN --type domain', 'warninglists lookup IP --type ip',
                      'warninglists history ' + policy.id),
            limits=(
                'Yalnız seçilen dört liste desteklenir; eşleşme güvenli kararı, otomatik istisna veya alarm kapatma değildir.',
                'Sorgulanan değer sağlayıcıya gönderilmez; yalnız sync internetten liste indirir.',
                'Aynı commit, liste başına 1 MiB/10.000 üye; hata ve sürüm gerilemesinde eski geçerli liste korunur.',
                'İncelenmiş veri lisansı: ' + LICENSE + '; kaynak/koşul belgesi değişirse yeni inceleme gerekir.',
            ),
            reference_url=LICENSE_URL,
        ) for policy in WARNINGLIST_POLICIES.values()) + tuple(SourceCatalogEntry(
            identifier='enrichment:' + identifier, label=policy['label'], kind='indicator_context',
            purpose='Sorgulanan IP, URL veya dosya kimliğine ait kaynak bağlamını saklar.',
            access='Mevcut public endpoint; anahtar gerekmez, sağlayıcı kota ve koşulları geçerlidir.',
            credential_required=False, paid_dependency=False, contacts_monitored_target=False,
            commands=('enrich fetch VALUE --type ' + policy['types'][0], 'enrich lookup VALUE --type ' + policy['types'][0],
                      'enrich history VALUE --type ' + policy['types'][0], 'enrich run-show RUN_ID'),
            limits=('Sorgulanan IP/URL/hash açık fetch komutunda sağlayıcıya gönderilir; hedef taranmaz, dosya yüklenmez.',
                    'Tek istek, 2 MiB yanıt; URL için ilk 20 sonuç. Eşleşme güvenli/zararlı kararı değildir.',
                    'Veri koşulu: ' + policy['license'] + '; ticari kullanım: ' + policy['commercial_use']),
            reference_url=policy['terms'],
        ) for identifier, policy in ENRICHMENT_PROVIDERS.items())

