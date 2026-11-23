# Ticari kaynak ve bileşen kararları

**23 Kasım 2026 — P12 telemetri eklemesi:** Katalog 53 kaynağa çıktı.
`telemetry:xti-sensor-v1` dış veri sağlayıcısı kullanmayan yerel sözleşmedir.
Cowrie ve CAPEv2 ayrı süreç/altyapı olarak değerlendirilir; XTI bunları
vendored etmez, otomatik kurmaz ve bu teslimle dağıtmaz. Cowrie kök lisansı
BSD koşullu, CAPEv2 kök lisansı GPLv3'tür. Bu yazılım lisansları müşteri
telemetrisinin, saldırgan verisinin veya analiz edilen örneğin saklama ve
müşteriye gösterim hakkını vermez. Gerçek sensör/sandbox işletimi, canlı
kabul, veri işleme amacı/süresi ve olası dağıtım biçimi kararlaştırılmadan
Cowrie/CAPE kaynakları ticari üretimde onaylı sayılmaz.
[N-055](../NOTES.md),
[teslim](roadmap/P12_DELIVERY.md).

**23 Kasım 2026 — P10 Bluesky eklemesi:** Anahtarsız resmî genel arama
teknik ve canlı olarak doğrulandı. Bununla katalog 50 kaynağa çıktı. Yalnız
genel gönderi metni/bağlantısı/zamanı sınırlı kanıt olarak alınır; medya,
profil ve özel içerik yoktur. Bluesky koşulları kamu içeriğinin geliştirici
uygulamalarca görülebileceğini açıklar, ancak bu inceleme müşteriye sunulan
ticari arşiv/gösterim için yeterli açık lisans sonucu üretmedi. Bu nedenle
kişisel teknik kullanım aktiftir; ticari kullanım, saklama ve müşteri
gösterimi `review_required`, yeniden dağıtım kapalıdır. [N-054](../NOTES.md),
[teslim](roadmap/P10_DELIVERY.md).

**23 Kasım 2026 — P09 yönetişim görünümü:** P09 teslimindeki 49 kaynak ve iş akışının
ticari kullanım, saklama, müşteriye gösterme ve yeniden dağıtım durumları
`sources catalog/show` manifestlerinde ayrı alanlardır. `active` teknik
entegrasyon durumudur; `review_required` veya `contract_required` kararı
kendiliğinden kapatmaz. Bu görünüm aşağıdaki tarihli incelemeleri tek teknik
sözleşmeye bağlar fakat hukuk görüşü, sağlayıcı yazılı izni veya canlı kaynak
kabulü yerine geçmez. Yeni provider kendi güncel koşulu incelenmeden mevcut
bir kaynağın kararını devralamaz. [P09 kullanımı](SOURCE_GOVERNANCE.md),
[N-052](../NOTES.md#n-052--p09-kaynak-manifesti-ve-canlı-kabul-sınırı).

**22 Kasım 2026 — P05 ek kapsam:** RansomLook'un atıflı kamu iddiaları,
ThreatCluster'ın yazılı ticari izin sınırı, tarihî HIBP kamu kataloğu ve
XposedOrNot domain/parola uçları ayrı veri sınıflarıdır. P05 hiçbirini
doğrulanmış incident, aktif hesap veya geçerli credential hükmüne dönüştürmez.
XposedOrNot domain görünümü API anahtarı, sağlayıcıda doğrulanmış kuruluş
domaini ve güncel hesap/hizmet koşulu gerektirir; ham alias saklanmaz. Parola
kontrolü yalnız açık kullanıcı işlemiyle, yerelde hashlenerek ve kalıcı geçmiş
oluşturmadan çalışır. Zararsız bilinen `test` girdisiyle parola uç noktası
canlı doğrulandı; gerçek kullanıcı sırrı kullanılmadı. Canlı domain kabulü
henüz yapılmadı. HIBP verified-domain
yeni çalışmalarda seçilmemiştir; eski şema93 kayıtları yalnız okunur. Genel
forum/pazar/Tor ve stealer-log kaynağı bu karara dahil değildir.
[N-048](../NOTES.md#n-048--p05-dark-web-ve-credential-kaynaksaklama-sınırı).

**21 Kasım 2026 — P02 ek kapsam:** Telethon/irctokens ve bağımlılıkları
[üçüncü taraf listesinde](../THIRD_PARTY.md) sabitlendi. Resmî Discord
REST adaptörü, seçilmiş Telegram/IRC kanalları ve kullanıcı tanımlı
RSS/Atom yayınları teknik erişim kapsamıdır. Kanal veya yayıncının
saklama, müşteriye gösterme, kullanıcı hesabı ve yeniden paylaşma
şartları ayrıca açık; bütün kaynaklar ticari onaylı olarak ilan edilmez.
Mevcut NCSC/CERT-FR değerlendirmesi kendi istisna/atıf kapsamıyla sürer;
yeni keyfî yayıncı ve kanalları otomatik kapsamaz. Hesaplı kanalların
canlı kabulü kullanıcı erişimi bekler. [N-045](../NOTES.md#n-045--p02-kaynak-kanal-ve-teslim-kapsamı).

**21 Kasım 2026 — yeni P01 kaynakları:** Betterleaks1.10.1 (MIT) pin ve
lisans dosyasıyla teknik olarak bağlandı. GitHub/GitLab kamu depo keşfi,
hesaplı genel kod araması ve Pastebin ayrı kaynaklardır. Kamu API'ye
erişim, üçüncü taraf kodu veya metaverisini müşteriye yeniden sunma hakkı
olarak yorumlanmaz. Bu kaynakların saklama/gösterme/hesap kapsamı ve
Pastebin'in güncel erişim şartları **açık**; ilk ticari profile onaylanmış
olarak dahil edilmez. [N-044](../NOTES.md#n-044--p01--a03-kaynak-erişimi-ve-secret-inceleme-aracı)
ve [P01 kabulü](roadmap/P01_DELIVERY.md) takip eder. Aşağıdaki20 Kasım
kararlarının kapsamı o tarihteki kaynaklarla sınırlıdır.

20 Kasım 2026. İlk işletim: kendi sunucularımızdaki kapalı kaynak XTI
motorundan müşterilere hizmet. Müşteriye sunucu/ikili dosya, Docker imajı
veya kaynak paketi dağıtmak bu kararın kapsamı değildir. Aşağıdaki kayıt,
teknik lisans/ürün değerlendirmesidir; sağlayıcıdan alınmış yazılı izin
veya imzalanmış sözleşme yerine geçmez.

**Sonuç:** Kaynağa erişebilmek ile verisini ticari üründe kullanma hakkı
ayrı değerlendirildi. Açık izin veren kapsam seçildi; belirsiz veya yazılı
izin isteyen kapsam ticari açılıştan çıkarıldı. Mevcut kişisel komutlar
kaldırılmadı. Bu belge ticari profil kararıdır; çalışma zamanında bütün
komutları engelleyen bir lisans kilidi değildir. Platform ekibi kaynak
seçimini bu karara göre yapar. Bir kaynak açılmadan ilgili satır ve hesap
sözleşmesi birlikte kontrol edilir.

## Kararların anlamı

- **Koşullarıyla seçildi:** Aşağıdaki saklama/gösterme/atıf sınırlarıyla
  ilk ticari kapsamda değerlendirilebilir. Erişim kotası ve kesintisiz
  çalışma garantisi anlamına gelmez.
- **İzin bekliyor — ticari profilde kapalı:** Entegrasyon bulunabilir;
  müşteri verisini bu kaynağa gönderme veya kaynağı müşteriye açma kararı
  verilmedi. Yazılı belge olmadan bu durum değişmez.
- **Seçilmedi:** İlk ticari teslimin dışında; gelecekte eklenirse ayrı
  inceleme gerekir. Yeni yapılacak yazılım işi olarak bu teslimi büyütmez.

## Veri hizmetleri

| Kaynak / mevcut kullanım | Saklama | Müşteriye gösterme / kullanım | Yeniden dağıtım ve karar |
| --- | --- | --- | --- |
| **Tavily Search** — firma/tedarikçi içerikleri, sosyal aday bağlantıları | Resmî yardım metni çıktı, metadata ve özetlerin kalıcı saklanmasına, yedeklenmesine izin veriyor. Yayıncı metninin hakkı ayrı. Firma alanları ayrı tutulur. | Müşteri uygulamaları, ücretli SaaS ve raporlar açıkça destekleniyor. API anahtarı yalnız sunucuda; kaynak URL'si ve alım zamanı korunur. | **Koşullarıyla seçildi.** API'nin kendisi yeniden satılmaz. Firmalar arası ortak sonuç havuzu bu karara dahil değil; sağlayıcı plan teyidi gerekir. [Kullanım](https://help.tavily.com/articles/5880393096-permitted-use-customer-applications), [saklama](https://help.tavily.com/articles/1612400809-storing-caching-retaining-output), [ana şartlar](https://www.tavily.com/terms). |
| **Bluesky public AppView** — firma/tedarikçi genel gönderi eşleşmeleri | Teknik profil yalnız genel metin, bağlantı, zaman ve hash'lenmiş kimlik saklar; medya/profil/DM/ham yanıt yoktur. Saklama süresi ve alıntı kapsamı ticari ürün için ayrıca onaylanmadı. | Kişisel teknik kullanım ve canlı erişim doğrulandı. Müşteriye gösterim, kullanıcı içeriği ve ilgili mevzuat/koşullar bakımından ürün/hukuk incelemesi bekler. | **Ticari profilde inceleme bekliyor; yeniden dağıtım kapalı.** [Koşullar](https://bsky.social/about/support/tos), [API](https://docs.bsky.app/docs/api/app-bsky-feed-search-posts), [P10 sınırı](roadmap/P10_DELIVERY.md). |
| **urlscan Search** — mevcut tarama arşivindeki URL/IP bağlamı | Kişisel kabulde saklama çalışır; müşteriye hizmette saklama/rapor hakları onaylanmış sayılmaz. | Sağlayıcı FAQ'sı ticari ürüne katılan veri için önceden iletişim istiyor. SOC içi araştırma izni ürün entegrasyonuna genellenmez. | **İzin bekliyor — ticari profilde kapalı.** Yalnız arama; yeni tarama gönderimi yok. N-001. [FAQ](https://docs.urlscan.io/pages/faq), [koşullar](https://urlscan.io/terms/). |
| **RIPEstat network-info / WHOIS** | Ticari saklama ve türetilmiş veri koşulları yazılı kapsamda ele alınmalı. | Madde 3.3, ücretli ürün/hizmet ve başka verilerle ticari birleştirme için RIPE NCC yazılı iznini gerektiriyor. | **İzin bekliyor — ticari profilde kapalı.** Yeniden paketleme/dağıtım da bu isteğe dahil. N-022. [Resmî koşullar](https://www.ripe.net/about-us/legal/ripestat-service-terms-and-conditions/). |
| **Bright Data** — seçilmiş LinkedIn şirket profili | Hesabın dataset/sipariş sözleşmesi ve saklama hakkı doğrulanmadan ticari saklama onayı yok. | Genel sözleşme veriyle benzer/rakip hizmet sunmayı sınırlar; XTI kullanım amacı ve son kullanıcıya gösterim hesaba özel netleştirilmeli. | **İzin ve canlı kabul bekliyor — ticari profilde kapalı.** Anahtar henüz eklenmedi; ücretli çağrı yapılmadı. N-034. [MSA, 12 Ekim 2026, §3.9](https://brightdata.com/license). |
| **CIRCL hashlookup** — bilinen dosya hash bağlamı | Kaynak sayfası CC-BY altında ticari kullanıma izin veriyor; lisans sürümünü belirtmiyor. Kaynak bağlantısı saklanır. | CIRCL hashlookup sayfasına görünür atıf. Eşleşme tek başına güvenli/zararlı hükmü değildir. | **Koşullarıyla seçildi.** Ham veritabanını yeni ürün olarak paketleme ilk kapsam değil. [Veri lisansı](https://www.circl.lu/services/hashlookup/). |
| **CERT Polska Warning List** — domain IOC | Kamu koşulları her amaçla, ticari kullanım dahil, kullanım izni veriyor. Özgün kaynak/tarih yine korunur. | Kaynak gönüllü belirtilirse ortaklık/onay izlenimi verilmez. Tarihî kayıt güncel aktif IOC gibi sunulmaz. | **Koşullarıyla seçildi.** [Veri kullanım kuralları](https://cert.pl/lista-ostrzezen/). |
| **Feodo Tracker** — C2 IP listesi | abuse.ch koşullarında Feodo için açık CC0 ticari/ticari olmayan kullanım istisnası var. | Kaynak ve kontrol zamanı gösterilir; iddia ile doğrulama ayrılır. | **Koşullarıyla seçildi.** Bu izin URLhaus, ThreatFox veya MalwareBazaar'a genellenmez. [§3.4 istisnası](https://abuse.ch/terms-of-use/). |
| **MITRE ATT&CK** — teknik/aktör/kampanya bağlamı | Resmî veri lisansı ticari kopyaya izin veriyor; telif bildirimi ve lisans korunur. | ATT&CK adı/atıf ve kaynak sürümü korunur; MITRE onayı veya tam savunma kapsamı iddiası yok. | **Koşullarıyla seçildi.** [Resmî veri lisansı](https://github.com/mitre-attack/attack-stix-data/blob/master/LICENSE.txt). |
| **MISP warninglists** — yalnız cloudflare, rfc1918, rfc3849, rfc6761 | Sabit commit ve README hash'i tekrar doğrulandı; genel CC0, kaynak özel istisnaları ayrı. Seçili dört liste kapsamı korunur. | Liste bağlamı ve özgün kaynak gösterilir; otomatik güvenli kararı yok. | **Koşullarıyla seçildi.** Yeni listenin hakkı bu karardan türetilmez. [İncelenen commit](https://github.com/MISP/misp-warninglists/blob/40e2b570fda2e5443a2d6fa1d1db16c37ab0a956/README.md#license), [motor sınırları](WARNINGLISTS.md). |
| **HIBP kamu ihlal kataloğu** | Yalnız herkese açık olay metaverisi; CC BY 4.0 ve hizmet koşullarıyla kayıt. Parola/hesap/stealer verisi değil. | Tarihî `notices` modülü ve mevcut kayıtlar kendi kaynak kimliğiyle korunur; yeni P05 credential profili bunu kullanmaz. | **Mevcut tarihî özellik; P05 yeni varsayılanı değil.** HIBP'nin yerine geçen ihlal arama hizmeti/veritabanı satılmaz; ücretli hesap uçları dahil değildir. [API lisansı](https://haveibeenpwned.com/API/v3#License), [şartlar](https://haveibeenpwned.com/termsofuse). |
| **HIBP verified-domain API** — eski P05 seçimi | Şema93'te oluşmuş kayıtlar kaynak kimliği değiştirilmeden okunur. Yeni anahtar, profil veya ağ çağrısı oluşturulmaz. | Eski kanıt denetlenebilir kalır; XposedOrNot verisiymiş gibi yeniden etiketlenmez. | **Yeni çalışmalarda seçilmedi / devre dışı.** Kullanıcı kararı ADR0190 ile kaydedildi. [ADR0190](decisions/0190-xposedornot-credential-source.md). |
| **XposedOrNot verified-domain API** — kuruluşa ait maskeli credential maruziyeti | Yalnız sağlayıcı hesabında doğrulanmış ve XTI kuruluşuna tam bağlı domain sorgulanır. Ham alias bellekte maskelenir; firma alanında yalnız maskeli görünüm, kuruluş anahtarlı HMAC kimliği ve ihlal adları saklanır. | Sonuç kaynaklı maruziyet metaverisidir; güncel hesap/parola geçerliliği veya doğrulanmış incident değildir. API ve pseudonym anahtarları yalnız özel sunucu config alanındadır. | **Teknik olarak seçildi; canlı ve ticari kabul bekliyor.** Kişisel/düşük hacimli ücretsiz kullanım müşteriye sunulan ürün hakkı sayılmaz; güncel ticari plan/şartlar üretim öncesi doğrulanır. [Resmî API](https://github.com/XposedOrNot/XposedOrNot-API), [P05 sınırı](DARKWEB_MONITORING.md), [ADR0190](decisions/0190-xposedornot-credential-source.md). |
| **XposedOrNot parola API** — açık, tek seferlik maruziyet kontrolü | Parola yerelde legacy Keccak-512 ile özetlenir; yalnız ilk10 hex karakter gönderilir. Parola, tam hash, önek ve sağlayıcının karakter bileşimi alanı saklanmaz; kontrol geçmişi oluşturulmaz. | Yalnız terminalde açık kullanıcı işlemi. Eşleşme parolanın corpus'ta görüldüğünü; boş sonuç güvenli olduğunu kanıtlamaz. Önek sıfır bilgi değildir. | **Teknik olarak seçildi; ticari şart teyidi açık.** Toplu, zamanlanmış veya arka planda parola taraması yapılmaz. [Resmî API](https://github.com/XposedOrNot/XposedOrNot-API), [resmî Go istemcisi](https://github.com/XposedOrNot/XposedOrNot-Go), [ADR0190](decisions/0190-xposedornot-credential-source.md). |
| **RansomLook** — açık ransomware gönderi metaverisi | About sayfası API/website/dataset içeriği için CC BY 4.0 bildiriyor; atıf/lisans/tarih korunur. | İddia olarak gösterilir, doğrulanmış ihlal denmez. Yalnız mevcut başlık/grup/keşif zamanı kapsamı. | **Koşullarıyla seçildi.** Çalınmış dosya, torrent, kişi/kimlik bilgileri ve yeni veri kümeleri bu karara dahil değil. [Lisans](https://www.ransomlook.io/about#usage-of-the-api-and-license), [API](https://www.ransomlook.io/doc/). |
| **ThreatCluster** — mevcut açık ransomware feed | Kamu feed'i atıfla paylaşılabilir. Anahtarlı API ayrı iç kullanım koşuluna sahip. | Genel şartlar satılan platforma gömmek için Business/MSSP anlaşması da istiyor; açık feed dağıtım izninin müşteri platformuna uygulanması net değil. | **İzin bekliyor — ticari profilde kapalı.** CC BY 4.0 periyodik dataset izni mevcut canlı feed'e otomatik taşınmaz. [Koşullar](https://threatcluster.io/terms), [ayrı dataset açıklaması](https://threatcluster.io/datasets). |
| **crt.sh** — CT sertifika araması | Güncel teknik erişim kanıtlandı; sağlayıcı hizmeti için açık ticari saklama/yeniden gösterim izni bu incelemede bulunamadı. | Sertifikaların kamuya açık oluşu crt.sh hizmeti için sözleşme sayılmaz. | **İzin bekliyor — ticari profilde kapalı.** [Hizmet](https://crt.sh/), [20 Kasım teknik kanıtı](SOURCE_EVIDENCE_2026_11_20.md). N-039. |
| **Common Crawl** — arşiv hostname adayları | Yalnız indeks/URL/domain kanıtı; arşivlenmiş sayfaların telifi ayrı. Hizmet lisansı sınırlı; kaynak içerik hakkı devredilmiyor. | İndeks metaverisinin müşteri hizmetinde saklama/yeniden gösterim kapsamı için belgeli karar gerekir. | **İzin bekliyor — ticari profilde kapalı.** [Koşullar](https://commoncrawl.org/terms-of-use). theHarvester lisansı bu hizmetin izni değildir. N-039. |
| **Wayback** — arşiv hostname adayları | Bu incelemede resmî şart sayfasının metni alınamadı; haklar varsayılmadı. | Geçmiş teknik çalışma ticari kullanım onayı değildir. | **İzin bekliyor — ticari profilde kapalı.** [Şart sayfası](https://archive.org/about/terms). N-039. |
| **Doğrudan sosyal sayfalar / Sherlock / Maigret sonuçları** | Profil URL'si ve sınırlı sayfa kanıtı mevcut teknik kapsam; her hedef sitenin veri/erişim koşulları ayrı. | MIT araç lisansı Instagram/X/LinkedIn vb. verilerinin müşteriye yeniden sunma izni değildir. Marka hesabı kararı insan incelemesine bağlı. | **Site kapsamı onayı bekliyor — ticari otomatik sosyal toplama profili kapalı.** Müşteri platformu için site bazlı seçim gerekir; mevcut kişisel kullanım genişletilmedi. N-039. |
| **Müşteri tarafından yetkilendirilmiş DNS/TLS/HTTPS/posta ölçümü ve yerel analist kaydı** | Kendi ölçüm/gerekçeli karar kanıtı firma alanında saklanır. Üçüncü taraf sayfa metni/kişisel içerik sınırsız arşivlenmez. | İlgili müşteri kapsamı ve kaynak türüyle gösterilir; yetki ve veri saklama politikası platformun verdiği sınırlarla yürür. | **Koşullarıyla seçildi.** Bir müşterinin kanıtı diğerine aktarılmaz; Nmap lisansı aşağıda ayrıca ele alınır. |

## Yayıncı metinleri

| Kaynak | Saklama ve gösterim kararı | İstisnalar |
| --- | --- | --- |
| NCSC | **Koşullarıyla seçildi:** OGL v3.0 kapsamındaki metin, kaynak/atıf/lisansla alınabilir, saklanabilir ve rapora katılabilir. [Şartlar](https://www.ncsc.gov.uk/section/about-this-website/terms-and-conditions). | Üçüncü taraf içerik ve logolar otomatik izinli değil. URL allowlist'i her belgenin hakkını garanti etmez; belge istisnası gözden geçirilir. |
| CERT-FR | **Koşullarıyla seçildi:** Aksi belirtilmeyen metin Licence Ouverte v2.0 kapsamında; atıf, tarih ve değişiklik bilgisi korunur. [Şartlar](https://cert.cyber.gouv.fr/mentions-legales/). | ANSSI adı/logosu ürün onayı anlamında kullanılamaz; özel telif notları ayrıca ele alınır. |
| CISA RSS | **İlk ticari profilde tam içerik seçilmedi.** Başlık/bağlantı ve kaynağın açıklanan kullanım kapsamı yeniden değerlendirilir. | Federal sitedeki her üçüncü taraf içerik otomatik telifsiz değildir. Bu tur CISA'ya ait içerik özel koşulları doğrulanamadı; N-039. |
| Tavily üzerinden diğer yayıncılar | Arama sonucu bağlantısı/başlık/kısa özet kapsamı; Tavily çıktı izni, yayıncı tam metin izni yerine geçmez. | Otomatik tam sayfa/PDF alma yalnız zaten incelenmiş NCSC/CERT-FR allowlist'iyle. |

## Yazılım, veri dosyaları ve dağıtım

Buradaki seçimler kodun kendi lisansına ilişkindir. Aracın sorguladığı
sitelerin/verilerin hakları üstteki tablodan ayrıca değerlendirilir.

| Bileşen / sabit sürüm | Kendi sunucumuzdaki kullanım | Dağıtım / korunan yükümlülük |
| --- | --- | --- |
| Cowrie / ayrı güncel kurulum | Kök BSD lisans koşullarıyla ayrı honeypot sunucusunda değerlendirilir; XTI yalnız seçilmiş JSONL olaylarını normalize eder. Bu sürümde kurulum veya canlı işletim yapılmadı. | XTI ile paketlenmiyor. Dağıtım biçimi, lisans bildirimleri ve müşteri telemetrisinin veri hakkı üretimden önce ayrıca onaylanır. [Lisans](https://github.com/cowrie/cowrie/blob/main/LICENSE.rst), [çıktı sözleşmesi](https://docs.cowrie.org/en/stable/OUTPUT.html). |
| CAPEv2 / ayrı güncel kurulum | Kök GPLv3 lisanslı ayrı sandbox olarak değerlendirilir; XTI yalnız tamamlanmış raporun izinli özetini alır ve malware çalıştırmaz. Bu sürümde canlı CAPE kurulmadı. | XTI ile paketlenmiyor veya dağıtılmıyor. İmaj/kod dağıtımı, GPL yükümlülüğü, örnek/veri hakkı ve güvenli işletim ayrı inceleme gerektirir. [Lisans](https://github.com/kevoreilly/CAPEv2/blob/master/LICENSE), [sonuçlar](https://capev2.readthedocs.io/en/latest/usage/results.html). |
| Sherlock 0.16.2 / `a38ba54f…` | MIT; telif/lisans korunarak **seçildi**. | [Sabit lisans](https://github.com/sherlock-project/sherlock/blob/a38ba54fda799cd786a2ab67a50143e1a63169e6/LICENSE). MIT bildirimi kopyalarla korunur. |
| Maigret 0.6.6 / `b8747b98…` | MIT; telif/lisans korunarak **seçildi**. | [Sabit lisans](https://github.com/soxoj/maigret/blob/b8747b98820f4df9d1baf23235db7b2cb55d0198/LICENSE). Kurulu lisans hash'i resmî commit ile aynı. |
| theHarvester / `6790b147…` | GPL-2.0-only; ayrı yönetilen araç olarak yalnız kendi sunucularımızda, dağıtım yapmadan kullanım **seçildi**. XTI içine kod kopyalama kararı yok. | [Sabit lisans](https://github.com/laramies/theHarvester/blob/6790b147f52309e4eee22ed941db1d285ab2ec23/LICENSE), [GNU özel kullanım açıklaması](https://www.gnu.org/licenses/gpl-faq.html#GPLRequireSourcePostedPublic). Müşteriye imaj/ikili/kod verme ayrı dağıtım incelemesi gerektirir. Bu karar kaynak API haklarını açmaz. |
| Nmap sistem paketi 7.x | NPSL/OEM değerlendirmesi mevcut kapalı kaynak müşteri ürününe entegrasyon bakımından **izin bekliyor; ticari profilde kapalı**. | [NPSL](https://nmap.org/npsl/), [OEM](https://nmap.org/oem/). Sırf ayrı süreç veya yalnız sunucuda çalışması otomatik muafiyet sayılmaz. Kurulu tam sürüm/LICENSE ve ürün kullanım biçimi yazılı netleşmeli; her iç kullanım için ücret gerektiği de iddia edilmez. N-002. |
| pypdf 7.1.1 | BSD-3-Clause; **seçildi**. | Kurulu lisans/telif ve sorumluluk reddi korunur; [lisans](https://github.com/py-pdf/pypdf/blob/7.1.1/LICENSE). PDF içeriğini lisanslamaz. |
| feedparser 6.0.14 | BSD-2-Clause; **seçildi**. | Lisans/telif korunur; [sürüm metaverisi](https://pypi.org/pypi/feedparser/6.0.14/json). |
| feedparser-sgmllib 2.1.0 | PSF-2.0; **seçildi**. | Lisans bildirimi korunur; değiştirilen dağıtımda değişiklik bildirimi ayrıca gerekir. [Sürüm](https://pypi.org/pypi/feedparser-sgmllib/2.1.0/json). |
| Depodaki Public Suffix List | MPL-2.0 veri dosyası; **seçildi**. | Özgün lisans/telif korunur. Dosya düzeyindeki yükümlülük XTI'nın tüm kodunu otomatik MPL yapmaz. [Kaynak](https://publicsuffix.org/list/public_suffix_list.dat). |
| Depodaki Unicode IDNA/confusables | Dosya/dağıtımda mevcut Unicode lisansı korunarak **seçildi**. | [Resmî lisans](https://www.unicode.org/license.txt); güncel sayfa sürümü eski paket içindeki bildirimin üzerine yazılmaz. |

Çekirdekte zorunlu üçüncü taraf Python bağımlılığı yok. İsteğe bağlı
araçların alt bağımlılıkları kurulumda kendi dağıtımlarıyla gelir;
lisanslarını kaldırmak/tek paket yapıp müşteriye dağıtmak onaylanmadı.
Bu değerlendirme her işletim sistemi paketinin alt bağımlılıklarını ve
gelecekte kurulacak sürümleri koşulsuz onaylayan bir SBOM denetimi değildir.
İlk işletimde bu araçlar sunucuda tutulur; dağıtım biçimi değişirse N-003
yeniden ele alınır. `requirements/news.txt` ve `requirements/reports.txt`
hash sabitlemeleri korunur; bu çalışmada bağımlılık yükseltilmedi.

Eski ürün/paket/CVE uyumluluk komutları, yeni URLhaus/ThreatFox beslemeleri,
Firecrawl, LLM ve geniş STIX/TAXII için yeni ticari kullanım kararı
verilmedi. Bunların varlığı bu seçili kaynak listesini genişletmez.

## İnceleme kanıtı ve kapanış

- Sayfalar 20 Kasım 2026'da okundu. Web aracının erişemediği RIPE koşulu,
  theHarvester/Maigret sabit lisansları ve MISP sabit README'si resmî
  adreslerinden HTTP200 ile ayrıca doğrulandı. Lisans metinleri topluca
  repoya kopyalanmadı; karar ve kaynak bağlantıları saklandı.
- RIPE yanıt SHA-256: `5ad023d666ecbbed5a0b681d8be82d17deffffa44100a07985496bd49a60aed5`.
- theHarvester LICENSE SHA-256: `aaf135472f81c5b4a0dca9367e5bb5e9750032b5bebe5442b36e4c0a47430df3`.
- Maigret LICENSE SHA-256: `9748c279c95c58e64cc9e538e8c717ae9dce66bbed1d69e7d3e77e431d7e582d`.
- MISP README SHA-256: `6f107071dcc8ee3918db3d3b7182adb5c47a7fb2e110a46b03696c98acab3808`; motordaki incelenmiş hash ile aynı.
- Kurulu pypdf/feedparser/feedparser-sgmllib lisansları da sürümleriyle
  okundu; bunlar yalnız dokümana dayanılarak varsayılmadı.
- Tavily ana metni ile yardım belgeleri birlikte ele alındı: müşteri
  uygulaması izinli; hesap/Order Form şartı ve yayıncı hakları korunuyor.
  Ortak müşteriler arası cache kararı ayrıca bekliyor.
- **Araştırma/karar işi kapatıldı.** N-001, N-002'nin Nmap bölümü,
  N-022, N-034 ve N-039'daki dış onaylar alınmış sayılmadı. Sağlayıcıya
  e-posta, ücretli hesap açma veya sözleşme imzalama yapılmadı.
- Koşul/sürüm, hizmet amacı, içerik türü, müşteri paylaşımı veya dağıtım
  biçimi değişirse ilgili satır yeniden değerlendirilir. Tarihli karar,
  gelecekteki bütün koşullara süresiz izin değildir.
