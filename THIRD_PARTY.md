# Üçüncü Taraf Yazılım ve Veri Bildirimi

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
- Lisans: [MIT](https://github.com/soxoj/maigret/blob/master/LICENSE).
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
