# Üçüncü Taraf Yazılım ve Veri Bildirimi

**26 Kasım 2026 — P05 / 0.195.1:** XposedOrNot verified-domain ve parola
entegrasyonları yeni kullanımda devre dışıdır. Üretim composition'ı SDK,
ağ, secret veya parola adaptörü kurmaz; kurulum ve handoff API anahtarı
istemez. Önceki sürümlerin parser/adaptör kaynakları, şema geçişi ve tarihî
kanıt kabulünü sürdürebilmek için repoda kalır fakat desteklenen bir canlı
kaynak yüzeyi değildir. Eski maskeli kayıtlar provider kimliği değiştirilmeden
salt okunur korunur. Bu karar yeni bir üçüncü taraf bağımlılığı eklemez.
[ADR0201](docs/decisions/0201-retire-xposedornot-new-use.md).

**25 Kasım 2026 — P06 / 0.195.0:** Abuse iletişim uzantısı yeni Python SDK,
vendored kod veya ücretli API eklemez. IANA RDAP bootstrap ile seçilen
registrar/RIR RDAP hizmetleri ve hedefin RFC 9116 `security.txt` dosyası
standart kütüphane HTTPS adaptörüyle pasif okunur. İsteğe bağlı WHOIS yalnız
işletim sistemindeki ayrı `whois` executable'ını argv/no-shell sınırında
çalıştırır; XTI bu aracı dağıtmaz. Erişilebilir kamu verisi veya araç lisansı,
verinin ticari saklama ve müşteriye gösterim hakkı sayılmaz; karar
[ticari kaynak incelemesinde](docs/COMMERCIAL_SOURCE_REVIEW.md) açıktır.
[IANA RDAP bootstrap](https://www.iana.org/assignments/rdap-dns/rdap-dns.xhtml),
[RFC 9116](https://www.rfc-editor.org/rfc/rfc9116.html).

**24 Kasım 2026 — P11 / 0.193.0:** Lunar/Webz.io Domain Exposure bir veri
hizmetidir; XTI yeni SDK veya sağlayıcı kodu almaz, standart kütüphane HTTPS
adaptörüyle yalnız toplu domain sayaçlarını okur. Resmî belge hizmeti son on
iki aylık toplu görünüm, ücretsiz/hesapsız/anahtarsız erişim ve bireysel
credential/PII sunmama sınırıyla açıklar. Sağlayıcının veri ve hizmet
koşulları XTI kod lisansından ayrıdır; ham yanıt yeniden dağıtılmaz.
[Açıklama](https://docs.webz.io/docs/webz/dea-introduction),
[API](https://docs.webz.io/docs/webz/dea-api-reference).

[AIL Framework v7.1](https://github.com/ail-project/ail-framework/releases/tag/v7.1)
ayrı ve isteğe bağlı yeraltı veri analiz sistemi adayıdır; incelenen commit
`4b94304bcd4d3d08b9e0c0772be4773e6bbbd350`, lisans
[AGPL-3.0](https://github.com/ail-project/ail-framework/blob/v7.1/LICENSE)'dır.
AIL kodu, bağımlılığı, container'ı veya Tor bileşeni XTI'ya kopyalanmaz,
kurulmaz, çalıştırılmaz ve bu teslimle dağıtılmaz. XTI yalnız işletici
tarafından hazırlanmış `xti-ail-v1` küçültülmüş JSON zarfını içe alır. AIL
lisansı, toplanan forum/pazar içeriğinin kullanım hakkı değildir; gerçek
kurulum, kaynak hakları, yalıtım ve canlı kabul ayrıca bekler.
[N-056](NOTES.md#n-056--p11-yeraltı-ve-toplu-credential-maruziyet-kaynakları),
[ticari karar](docs/COMMERCIAL_SOURCE_REVIEW.md).

**23 Kasım 2026 — P12 / 0.191.0:** P12 çekirdeğe yeni Python paketi,
vendored kod veya otomatik kurulum eklemez. [Cowrie](https://github.com/cowrie/cowrie)
ayrı SSH/Telnet honeypot altyapısıdır; XTI yalnız resmî JSONL olaylarının
allowlist alt kümesini güvenli normalize eder. Cowrie kök
[lisansı](https://github.com/cowrie/cowrie/blob/main/LICENSE.rst) BSD
3-clause benzeri koşullar taşır ve resmî
[çıktı sözleşmesi](https://docs.cowrie.org/en/stable/OUTPUT.html) credential
alanlarının da bulunabildiğini gösterir; XTI bunları kalıcı alana yazmaz.
[CAPEv2](https://github.com/kevoreilly/CAPEv2) ayrı malware sandbox
altyapısıdır; XTI yalnız tamamlanmış `report.json` içindeki izinli alanları
okur ve örnek, PCAP, bellek, ekran görüntüsü veya ham rapor saklamaz.
CAPE kök [LICENSE](https://github.com/kevoreilly/CAPEv2/blob/master/LICENSE)
GPLv3'tür; XTI'ya gömülmez, XTI sürecinden çalıştırılmaz ve bu teslimle
dağıtılmaz. CAPE'nin [sonuç belgesi](https://capev2.readthedocs.io/en/latest/usage/results.html)
ham artefakt kapsamını doğrular. Araç lisansı sensör verisinin, müşteri
telemetrisinin veya incelenen örneğin ticari saklama/gösterim hakkı değildir.
Gerçek kurulum, ağ yalıtımı, canlı kabul ve olası müşteriye dağıtım ayrıca
incelenir; kontrollü test fixture'ı bu kararı kapatmaz.

**23 Kasım 2026 — P10 / 0.190.0:** Yeni repo, SDK, Python paketi veya
ücretli API eklenmedi. XTI standart kütüphane adaptörüyle Bluesky'nin resmî
`app.bsky.feed.searchPosts` genel okuma sözleşmesini kullanır. Yalnız
`public.api.bsky.app` ve `api.bsky.app` hostları izinlidir; üçüncü taraf proxy,
firehose, profil/medya veya özel içerik yoktur. API/protokolün açık olması,
kullanıcı gönderilerinin ticari üründe saklanması ve müşteriye gösterilmesi
için otomatik hak verildiği anlamına gelmez. Teknik kaynak manifestte aktif,
ticari kullanım/saklama/gösterim `review_required`, yeniden dağıtım kapalıdır.
[Resmî API hostları](https://docs.bsky.app/docs/advanced-guides/api-directory),
[arama sözleşmesi](https://docs.bsky.app/docs/api/app-bsky-feed-search-posts),
[koşullar](https://bsky.social/about/support/tos),
[N-054](NOTES.md), [teslim](docs/roadmap/P10_DELIVERY.md).

**23 Kasım 2026 — P09 / 0.189.0:** Yeni üçüncü taraf repo, Python paketi,
çalıştırılabilir araç, ücretli API veya canlı veri kaynağı eklenmedi. P09,
mevcut 49 kaynak ve iş akışının erişim, maliyet, dil/bölge, kota, hata,
provenance ve veri hakkı koşullarını XTI manifestlerinde görünür yapar.
Manifestteki `active` teknik entegrasyon durumudur; yazılım lisansı, sağlayıcı
verisini saklama/müşteriye gösterme/yeniden dağıtma izni veya canlı hizmet
garantisi değildir. Kaynağa özgü lisans ve hizmet koşulları aşağıdaki mevcut
kayıtlarda ve [ticari kaynak kararında](docs/COMMERCIAL_SOURCE_REVIEW.md)
geçerliliğini korur. [ADR0194](docs/decisions/0194-source-governance-manifests.md),
[N-052](NOTES.md#n-052--p09-kaynak-manifesti-ve-canlı-kabul-sınırı).

**22 Kasım 2026 — P06 / 0.186.0:** Yeni Python paketi, repo, veri kaynağı
veya ücretli API eklenmedi. Runbook, takedown kaydı, vaka paketi ve IOC
dosya işlemleri XTI kodudur. İsteğe bağlı PDF, P03 için zaten sabitlenmiş
Playwright1.65.2/Chromium1255'i JavaScript kapalı ve ağsız ayrı süreçte
yeniden kullanır; ilgili Chromium ve üçüncü taraf bildirimleri korunur.
Haricî takedown/abuse, SIEM, SOAR veya ticket SDK'sı yoktur. Bir IOC/vaka
dosyasının içeriği ve gerçek portal başvurusunun hukuki yetkisi yazılım
lisansından ayrıdır. [Karar](docs/decisions/0191-human-approved-actionability.md),
[kullanım](docs/ACTIONABILITY.md).

**22 Kasım 2026 — P05 / 0.185.0 tarihî kayıt (yeni kullanım 0.195.1'de
ADR0201 ile kapatıldı):** Yeni üçüncü taraf Python paketi veya
vendored crawler eklenmedi. Mevcut RansomLook, ThreatCluster ve tarihî HIBP
snapshot'ları kendi kaynak kimlikleriyle okunur. Yeni credential-domain ve
parola maruziyet kaynağı XposedOrNot'tur. Sabit uç noktalar için stdlib HTTPS
adaptörleri ile yerel, resmî test vektörlü legacy Keccak-512 uygulaması
kullanılır; XposedOrNot SDK kodu repoya alınmaz. Ham alias bellekte maskelenir;
parola, tam hash, gönderilen önek, token ve cookie saklanmaz. Parola uç noktası
bilinen zararsız `test` girdisiyle canlı doğrulandı; gerçek kullanıcı sırrı
kullanılmadı. API anahtarı ve doğrulanmış domain gerektiren canlı domain
kabulü henüz yapılmadı. HIBP
verified-domain yeni profile/ağ çağrısına kapalı, eski şema93 kayıtlarında
salt-okunurdur. ThreatCluster yazılı izin olmadan ticari profilde kapalıdır.
RansomLook atıf/CC BY 4.0 ve XposedOrNot hesap/hizmet koşulları veri
gösteriminde korunur. API deposunun açık kaynak lisansı, hizmet verisinin
ticari kullanım hakkı yerine geçmez.
[Kullanım](docs/DARKWEB_MONITORING.md),
[ticari kaynak kararı](docs/COMMERCIAL_SOURCE_REVIEW.md),
[takip notu N-048](NOTES.md#n-048--p05-dark-web-ve-credential-kaynaksaklama-sınırı).

**21 Kasım 2026 — P03 / 0.182.0:** ImageHash4.3.2 (BSD-2-Clause),
Pillow13.0.0 (MIT-CMU/HPND bildirimi), Playwright1.65.2 (Apache-2.0),
google-play-scraper1.2.7 (MIT). Görsel hesaplamalar SciPy1.16.3 (BSD-3-Clause),
PyWavelets1.9.0 (MIT), mevcut Python koşullu NumPy2.4.6/2.5.4 ve greenlet3.5.0
(MIT/Python-2.0) kullanır. Wheel içindeki ek native lisanslar da geçerlidir;
kurulu paketlerin lisans dosyaları korunur. [Tam hash listesi](requirements/brand-protection.txt).
Chromium revision1255, SDK1.65.2 ile seçilir; Chromium/üçüncü taraf
bildirimleri dağıtımda korunur. SDK kod lisansı tarayıcıdaki bütün native
bileşenlerin lisansını tek başına tanımlamaz. Tarayıcı ayrı upstream arşiv
hash piniyle sunulmuyor; resmî SDK TLS indirimi ve yerel hash makbuzu var.
Mağaza ve açık sayfa verilerinin hakları bunlardan ayrıdır: [N-046](NOTES.md#n-046--p03-marka-koruması-görsel-kanıt-ve-mağaza-kaynakları).
Google kitaplığı motor TLS ayarını değiştirmemesi için yalnız ağsız parser
alt sürecinde kullanılır; kaynak HTTPS taşımasını XTI yapar. Kaynaklardan
APK/IPA veya çalıştırılabilir phishing kit alınmaz.


**21 Kasım 2026 — P02 / 0.181.0:** Telegram için
[Telethon1.46.0](https://pypi.org/project/Telethon/1.46.0/) (MIT), IRC
ayrıştırması için [irctokens2.0.2](https://pypi.org/project/irctokens/2.0.2/)
(MIT) normal kuruluma eklendi. Bağımlılıklar pyaes1.6.1 (MIT), rsa4.9.1
(Apache-2.0), pyasn1 0.6.5 (BSD-2-Clause); kaynak paketini hazırlayan
setuptools84.2.1 (MIT) ayrıca sabittir. Resmî PyPI dosya SHA256'ları
[kanal listesinde](requirements/channels.txt) ve
[derleme listesinde](requirements/channels-build.txt) bulunur.
Paket kodu kopyalanmaz; kurulu dağıtımların özgün lisans dosyaları korunur.
Discord SDK'sı alınmaz; resmî RESTv10 için XTI okuma adaptörü kullanılır.
RSS/Atom mevcut feedparser6.0.14'ü, çevrimdışı maskeleme Betterleaks'i kullanır.
Yeni kanal/yayın verilerinin ticari saklama ve gösterim kararı araç
lisansından ayrı olarak [N-045](NOTES.md#n-045--p02-kaynak-kanal-ve-teslim-kapsamı)
altında açıktır. Canlı kanal hesabı kabulü yapılmış sayılmaz.

**21 Kasım 2026 eklemesi — P01 / A03:**
[Betterleaks1.10.1](https://github.com/betterleaks/betterleaks/tree/v1.10.1)
native araç olarak normal kuruluma eklendi. Tam commit
`39d5bdcf34db54e944facac5cf6e8b03db5e2b99`; MIT lisanslıdır.
Kurulum arşiv SHA256'sını doğrular, özgün `LICENSE` dosyasını ikiliyle
birlikte korur. Kod repoya kopyalanmaz; `stdin` taraması kullanılır,
aktif credential validation kapalıdır. Sürüm/platform hash'leri
[pin kaydındadır](src/xti/domain/betterleaks_pin.py).
Araç lisansı GitHub/GitLab/Pastebin içeriklerinin saklanması veya
müşterilere gösterilmesi için izin yerine geçmez. Bu yeni kaynakların
ticari kararı [N-044](NOTES.md#n-044--p01--a03-kaynak-erişimi-ve-secret-inceleme-aracı)
altında açıktır; aşağıdaki20 Kasım kapanışı bu yeni kaynakları kapsamaz.

**20 Kasım 2026:** Mevcut veri hizmetleri ve sabit yazılım bileşenleri için
saklama, müşteri gösterimi, kullanım ve dağıtım değerlendirmesi
[ticari karar matrisinde](docs/COMMERCIAL_SOURCE_REVIEW.md) tamamlandı.
Koşullarıyla seçilen kapsam ile yazılı izin beklediği için ilk ticari
profilden çıkarılan kaynaklar ayrı kayıtlıdır. Mevcut kişisel komutların
çalışması bütün ticari hakların alındığı anlamına gelmez.

**16 Kasım 2026 ürün kararı:** XTI kendi platformumuzun kapalı kaynak
motoru olarak geliştiriliyor. Aşağıdaki üçüncü taraf bildirimleri ve
lisansları korunur. Teknik olarak kurulmuş bir araç ticari ürün içinde
kullanım/dağıtım bakımından otomatik onaylı değildir. Nmap ve theHarvester
için dağıtım biçimine bağlı değerlendirme; bütün veri sağlayıcıları için
saklama, müşteriye sunma ve paylaşma hakları
[bileşen seçim planında](docs/roadmap/COMPONENT_SELECTION_PLAN.md) izlenir.
Gelecekte düşünülen paketler kurulu bağımlılık listesine eklenmez.

İlk ticari işletim kendi sunucularımızda müşterilere hizmet sunma olarak
seçildi. Bileşen ve veri hakları bu kullanım biçimiyle değerlendirilecek;
müşteriye kurulum paketi dağıtımı ilk teslimin kapsamında değildir.

## pypdf ve izinli yayıncı metinleri — 0.169.0

PDF metni için [pypdf 7.1.1](https://pypi.org/project/pypdf/7.1.1/),
[BSD-3-Clause lisansıyla](https://github.com/py-pdf/pypdf/blob/7.1.1/LICENSE)
kullanılır. Paket kodu kopyalanmaz; `reports` extra'sı ve yönetilen
kurulumda sürüm sabittir. İncelenen evrensel wheel SHA-256:
`04c5680d4b4cfa04ab505b09393fc949860c34a4dad6565284d11a2f5c3ce8b1`.
CI `requirements/reports.txt` ile bu hash'i doğrular. Kurulu paketin lisans
ve telif bildirimleri korunmalıdır; OCR/kriptografi extra'ları alınmaz.

HTML ana metni stdlib ile, PDF metni sınırlı ayrı süreçte çıkarılır.
pypdf'nin kod lisansı yayıncı içerik hakkını sağlamaz. İlk veri kapsamı:

- [CERT-FR](https://cert.cyber.gouv.fr/mentions-legales/): belirtilen
  istisnalar dışında Licence Ouverte 2.0; kaynak/atıf ve lisans bağlantısı
  belgenin metaverisinde korunur.
- [NCSC](https://www.ncsc.gov.uk/section/about-this-website/terms-and-conditions):
  belirtilen istisnalar ve üçüncü taraf içerikleri dışında Open Government
  Licence v3.0. Kaynak/atıf ve lisans bağlantısı korunur.

Bu genel politikalar özel kısıtlı/üçüncü taraf içeriği, marka veya logoları
otomatik lisanslamaz. Logo/görseller ayrı indirilmez veya marka varlığı
olarak kullanılmaz; özgün PDF'nin bunları içerebileceği unutulmamalıdır.
Ham belge ve çıkarılmış metin firma alanında saklanır. Yeni yayıncı/URL
kapsamı ayrıca incelenmeden allowlist'e eklenmez. Sağlayıcı erişilebilirliği
ve gelecekteki şart değişiklikleri izlenir; sınırsız erişim taahhüdü yoktur.
[Kullanım ve sınırlar](docs/PUBLISHER_REVIEW_RETENTION.md),
[takip notu N-029](NOTES.md#n-029--tam-yayın-metni-yeniden-inceleme-ve-günlük-arşivi).

## Nmap sistem aracı

0.148.0'dan itibaren isteğe bağlıdır; 0.150.0 yönetilen TCP/SYN/UDP,
servis/sürüm, OS ve seçili NSE çalıştırmasını ekler. Kaynak kodu, ikili
dosya veya NSE scriptleri bu repoya kopyalanmaz. `scripts/setup-nmap`
sistem paket yöneticisini kullanır; kurulu araç `--version` ile Nmap 7.x
olarak kontrol edilir. İşin kanıtı gerçek sürümü taşır. İşletici sistem
paketinin ve script dosyalarının güvenilirliğinden sorumludur; paket
içeriği tam commit/hash pin'iyle sabitlenmiş sayılmaz.

Nmap'in lisansı [NPSL](https://nmap.org/npsl/)'dir; kurulu sürümün LICENSE
dosyası esas alınır. Kapalı kaynak ürüne entegrasyon/dağıtım için
[OEM koşulları](https://nmap.org/oem/) ayrıca değerlendirilmelidir. Ayrı
süreç veya sistem paketi kullanmak otomatik lisans muafiyeti olarak
yorumlanmaz. Kişisel kullanım kararı ticari dağıtım onayı değildir.

Seçili NSE kaydı ve resmî açıklamaları [Nmap kullanımında](docs/NMAP_MANAGED.md)
listelenir. Bunlar XTI'ın yazdığı zafiyet imzaları değildir; Nmap çıktısı
kaynaklı kanıt olarak korunur.

## Bright Data sosyal profil hizmeti

0.172.0 kullanıcının kendi API hesabıyla isteğe bağlı LinkedIn şirket
profili kanıtı alır. Bright Data SDK/sunucu kodu repoya kopyalanmaz;
stdlib adaptörü yalnız `gd_l1vikfnt1wgvvqz95w` dataset'ine sınırlı async
POST, ilerleme GET'i ve sonuç GET'i yapar. Hizmetin açık kaynak olduğu
veya API ücretinin yeniden yayın hakkı verdiği varsayılmaz. Ticari ürünün
saklama/müşteriye gösterme koşulları N-034'te açık takip maddesidir.

Seçilen şirket profil URL'leri gönderilir; profil kimliği, ad, web adresi,
sınırlı açıklama ve içerik özeti saklanır. Çalışan/kişi listesi, gönderiler,
logo veya tam ham yanıt saklanmaz. İstek/yerel profil limiti fatura limiti
değildir. Anahtar sonra eklenecek; canlı kabul henüz yapılmadı.
[API ve alanlar](https://docs.brightdata.com/products/scrapers/linkedin/send-first-request.md),
[fiyatlar](https://brightdata.com/pricing/web-scraper),
[kullanım](docs/BRIGHTDATA_SOCIAL.md),
[entegrasyon kararı](docs/decisions/0177-optional-social-provider-evidence.md).

## Tavily arama hizmeti

0.144.0, kullanıcının kendi hesabı ve API anahtarıyla isteğe bağlı
[Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)
kullanır. Bir arama motoru veya SDK kodu repoya kopyalanmaz; sabit HTTPS
protokolünü kullanan küçük adaptör stdlib ile çalışır. Servis şartları ve
ücretsiz/ücretli hesap hakları bir açık kaynak yazılım lisansı değildir.

Yalnız seçilmiş firma adı ve domainleri gönderilir. Başlık, URL, sınırlı
açıklama, sağlayıcı tarihi/puanı ve sorgu kanıtı saklanır; LLM cevabı ve
tam sayfa istenmez. Anahtar kanıt veya loglara girmez.
[Krediler](https://docs.tavily.com/documentation/api-credits),
[saklama ve müşteriler arası kullanım](https://help.tavily.com/articles/1612400809-storing-caching-retaining-output),
[hizmet şartları](https://www.tavily.com/terms).
Sağlayıcının saklama açıklaması yayıncı içeriğine ait hakları devretmez.
[Entegrasyon kararı](docs/decisions/0149-tavily-company-mentions.md).

## RIPEstat ve internet kayıt kaynakları

0.164.0 `network-info`, 0.168.0 `whois` uçlarını küçük HTTP adaptörüyle
kullanır; RIPEstat yazılımı veya SDK'sı repoya kopyalanmaz. Yanıtta kaynak,
atıf ve kullanım koşulu başvuruları korunur. WHOIS görünümünde yalnız
seçilmiş alanlar sunulur; saklı ham kaynak yanıtı ayrıca korunur.
[Kaynak kapsamı](docs/INDICATOR_ENRICHMENT.md),
[RIPEstat hizmet koşulları](https://www.ripe.net/about-us/legal/ripestat-service-terms-and-conditions/).
Ticari hizmette kullanım için izin ve alttaki kayıt kaynaklarının koşulları
[N-022](NOTES.md#n-022--ripestat-ticari-kullanım-izni) kapsamında açık tutulur.
Anahtarsız canlı sorgunun çalışması bu iznin tamamlandığı anlamına gelmez.

## RSS/Atom ayrıştırıcısı ve haber kaynakları

Normal `./setup`, `news` ekini Maigret/Sherlock ile aynı korumalı `.venv`
ortamına kurar. `--core-only` bu kurulumu atlar. XTI bu kütüphanelerin
kaynak kodunu deposuna kopyalamaz; PyPI'daki sabit paketleri kullanır.

| Paket | Sürüm | Lisans | Resmî sürüm kaydı |
|---|---|---|---|
| feedparser | 6.0.14 | BSD-2-Clause | [PyPI](https://pypi.org/pypi/feedparser/6.0.14/json) |
| feedparser-sgmllib | 2.1.0 | PSF-2.0 | [PyPI](https://pypi.org/pypi/feedparser-sgmllib/2.1.0/json) |

Wheel SHA-256 değerleri [requirements/news.txt](requirements/news.txt)
içindedir. Kurulum doğrulaması sürümü, ortam sahipliğini ve ağsız
RSS/Atom örneklerini denetler; kütüphanelerin tüm geçişli kaynak koduna
bağımsız güvenlik denetimi yapıldığı iddiası değildir.

Haberlerde yayıncı adı, özgün makale bağlantısı, kaynak tarihleri ve
sınırlı yayın özeti korunur. Makale sayfası, resim veya logo indirilmez.
Desteklenen yayınlar CISA News, UK NCSC ve CERT-FR actualité'dir.
NCSC içeriği aksi belirtilmedikçe Open Government Licence v3.0,
CERT-FR içeriği aksi belirtilmedikçe Licence Ouverte v2.0 kapsamındadır;
üçüncü taraf materyal ve logolar için aynı izin varsayılmaz.
[NCSC koşulları](https://www.ncsc.gov.uk/section/about-this-website/terms-and-conditions),
[CERT-FR koşulları](https://cert.cyber.gouv.fr/mentions-legales/).
CISA akışının açık erişimli olması bütün içeriğin sınırsız yeniden
dağıtılabileceği iddiası değildir. Kaynak erişimi/kapsamı yayıncıya bağlıdır.
[Entegrasyon kararı](docs/decisions/0148-publisher-news-feeds.md).

## theHarvester pasif arşiv aracı

İsteğe bağlı `./scripts/setup-harvester`, theHarvester'ı resmî
`laramies/theHarvester` deposundaki incelenmiş
`6790b147f52309e4eee22ed941db1d285ab2ec23` commit'inden proje içindeki ayrı
`.tools/theharvester` alanına kurar. XTI kaynak deposuna theHarvester kodu
kopyalanmaz ve çekirdek Python bağımlılığına eklenmez.

- Resmî depo: [laramies/theHarvester](https://github.com/laramies/theHarvester).
- İncelenen commit: `6790b147f52309e4eee22ed941db1d285ab2ec23`.
- Lisans: [GPL-2.0-only](https://github.com/laramies/theHarvester/blob/6790b147f52309e4eee22ed941db1d285ab2ec23/LICENSE).
- Kurulum ortamı: upstream gereksinimine göre ayrı Python 3.14 ve `uv`.

XTI yalnız Common Crawl ve Wayback Archive P0 hostname kaynaklarını sabit
argümanlarla çalıştırır. E-posta/kişi sonucu, DNS etkileşimi, screenshot,
takeover, API scan, proxy ve doğrudan hedef bağlantısı kullanılmaz. JSONL
sonuçları XTI'ın bağımsız adaptöründe yeniden doğrulanır. Kaynak kodu değiştirmek
veya dağıtmak isteyen kişi GPL-2.0-only koşullarını ayrıca yerine getirmelidir.

Common Crawl ve Internet Archive/Wayback hizmetlerinin erişilebilirliği,
kapsamı ve güncel kullanım koşulları XTI'ın kontrolünde değildir. Arşiv sonucu
bir hostname'in sahibini, güncel olduğunu veya güvenlik riski taşıdığını
kanıtlamaz.

## Sherlock sosyal kullanıcı adı aracı ve kapsam kanıtı

`brand source-coverage`, Sherlock 0.16.2'nin resmî
`sherlock-project/sherlock` reposundaki
`a38ba54fda799cd786a2ab67a50143e1a63169e6` commit'inde bulunan site
kataloğunun yalnız türetilmiş kapsam sayaçlarını ve SHA-256 özetini taşır.
Normal `./setup` (ve doğrudan `./scripts/setup-brand`), aynı tam commit'teki
Sherlock 0.16.2'yi proje içindeki `.venv` ortamına kurar. `./setup --core-only`
bu üçüncü taraf kurulumu atlar. XTI kaynak deposuna Sherlock kodu veya site
kataloğu kopyalanmaz.

- Resmî depo: [sherlock-project/sherlock](https://github.com/sherlock-project/sherlock).
- İncelenen sürüm: 0.16.2; yukarıdaki tam commit'e sabitlenmiştir.
- Katalog SHA-256: `3fdfc6694c5cd99798881215554b09e617c6d5284a6219fae309882566a9fb30`.
- Lisans: [MIT](https://github.com/sherlock-project/sherlock/blob/a38ba54fda799cd786a2ab67a50143e1a63169e6/LICENSE).
- Telif: Copyright © 2019 Sherlock Project.

`brand username-preview ... --source sherlock`, upstream CLI'ı çağırmaz. CLI'ın
seçili profillere ek olarak yaptığı GitHub sürüm isteğini önlemek için sabit
kütüphane işlevi ayrı bir Python sürecinde çağrılır. Önce tam katalog özeti
doğrulanır, sonra `safe` profilde 5 veya `extended` profilde 26 elle incelenmiş
HTTPS tanım arasından seçilenler geçici dosyaya alınır. XTI kendi dört alanlı
NDJSON raporunu yazar; ham yanıtı ve profil ayrıntılarını almaz. Upstream'in tam
kataloğu, canlı katalog/exclusion güncellemesi, proxy, Tor, toplu kullanıcı adı
ve kullanıcı adı türetme kullanılmaz.

Canlı sorgular seçilen platformların herkese açık profil adreslerine gider. Bu
platformların erişilebilirliği, yönlendirmeleri, oran sınırları ve kullanım
koşulları XTI'nin kontrolünde değildir. Bir eşleşme sahiplik veya taklit kanıtı
değildir.

## Maigret sosyal kullanıcı adı aracı

Normal `./setup` (ve doğrudan `./scripts/setup-brand`), Maigret 0.6.6'yı resmî
`soxoj/maigret` reposundaki incelenmiş
`b8747b98820f4df9d1baf23235db7b2cb55d0198` commit'inden proje içindeki
`.venv` ortamına kurar. XTI, kullanıcının açık `brand username-preview`
komutunda Maigret CLI'ın yalnız seçili herkese açık profil kontrolü ve NDJSON
çıktısını kullanır.

- Resmî depo: [soxoj/maigret](https://github.com/soxoj/maigret).
- Kullanılan sürüm: 0.6.6; yukarıdaki tam commit'e sabitlenmiştir.
- Katalog SHA-256: `8dd404e6b3012f01fd467c154b5159386d1362587070c661c2565ec8fa649899`.
- Lisans: [MIT](https://github.com/soxoj/maigret/blob/b8747b98820f4df9d1baf23235db7b2cb55d0198/LICENSE).
- Telif: Copyright © 2020–2026 Soxoj.

Maigret kaynak kodu ve site veritabanı XTI kaynak deposuna kopyalanmaz. Paket
kurulurken resmî repodan alınır; lisans dosyası kurulu dağıtımla birlikte gelir.
Adaptör site veritabanının incelenmiş SHA-256 özetini doğrular, seçilen platform
tanımlarını yalnız geçici çalışma klasörüne ayırır ve klasörü işlem sonunda
kaldırır. `safe` profil 6, `extended` profil 30 elle incelenmiş HTTPS hedefi
içerir; upstream'in bütün kataloğu çalıştırılmaz. Canlı sorgular seçilen platformlara doğrudan gider; bu platformların
erişilebilirliği, oran sınırları ve kullanım koşulları XTI'nin kontrolünde
değildir.

## RansomLook açık ransomware gönderi verisi

XTI, kullanıcı açıkça `ransomware recent --source ransomlook` komutunu
çalıştırdığında RansomLook'un açık son-yedi-gün API yanıtını okur. Yanıt yalnız
grup adı, gönderi başlığı ve keşif zamanı olarak yazmasız önizlenir; kaynak
verisi bu depoda paketlenmez veya yeniden yayımlanmaz.

- Resmî kaynak ve yazılım deposu: [RansomLook](https://github.com/RansomLook/RansomLook).
- API açıklaması: [RansomLook API documentation](https://www.ransomlook.io/doc/).
- Veri kullanım koşulu: API yanıtları ve veri kümeleri [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) ile sunulur.
- Atıf: RansomLook — <https://www.ransomlook.io>.

XTI, RansomLook yazılım kodunu bu depoya kopyalamaz veya gömmez; yalnız açık API
yanıtını kendi bağımsız adaptörüyle okur. Sağlayıcının güncel şartları ürünün
ileride ticari veri hizmetine dönüşmesinden önce yeniden incelenmelidir.
P05, mevcut yerel snapshot'taki sınırlı başlık/grup/zaman metaverisini
kuruluş veya tedarikçi için kaynak iddiası olarak eşleştirir; çalınmış dosya,
torrent, leak-site sayfası veya kişisel veri indirmez.

## Public Suffix List

`src/xti/data/public_suffix_list.dat`, Public Suffix List projesinin yayımladığı dosyanın değiştirilmemiş kopyasıdır. Alan adlarının kayıt sınırlarını ayırmak için çevrimdışı kullanılır. ICANN ve PRIVATE bölümleri dahildir.

- Resmî kaynak: [publicsuffix.org listesi](https://publicsuffix.org/list/public_suffix_list.dat).
- Format ve kullanım: [Public Suffix List](https://publicsuffix.org/list/).
- Lisans: [Mozilla Public License 2.0](https://mozilla.org/MPL/2.0/).
- Kaynak sürümü, alım tarihi ve SHA-256: `src/xti/data/public_suffix_metadata.json`.

Orijinal lisans ve katkı bildirimleri veri dosyasında korunmuştur. Uygulama her çalışmada liste indirmez. Liste güncellendiğinde metaveri ve eşleştirme değerlendirmesi de güncellenir.

## Unicode güvenlik ve IDNA verisi

`src/xti/data/unicode_confusables_18_0_0.dat` ve `src/xti/data/unicode_idna_mapping_18_0_0.dat`, Unicode Consortium'un yayımladığı dosyaların değiştirilmemiş kopyalarıdır. İlki UTS #39 benzer-harf iskeletleri, ikincisi UTS #46 IDNA eşleme/doğrulama durumları için çevrimdışı kullanılır.

- Sürüm: Unicode 18.0.0.
- Resmî kaynaklar: [confusables.txt](https://www.unicode.org/Public/security/latest/confusables.txt), [IdnaMappingTable.txt](https://www.unicode.org/Public/idna/latest/IdnaMappingTable.txt).
- Standartlar: [UTS #39](https://www.unicode.org/reports/tr39/), [UTS #46](https://www.unicode.org/reports/tr46/).
- Lisans/kullanım koşulları: [Unicode Terms of Use](https://www.unicode.org/terms_of_use.html) ve [Unicode Data Files and Software License](https://www.unicode.org/license.txt).
- Alım tarihi, yayın tarihleri ve SHA-256 özetleri: `src/xti/data/unicode_security_metadata.json`.

Uygulama bu dosyaları çalışma sırasında internetten güncellemez. Beklenen sürüm veya SHA-256 uyuşmazsa profil yüklenmez. Yeni Unicode sürümü ayrı kural değerlendirmesi ve açık veri güncellemesi gerektirir.
