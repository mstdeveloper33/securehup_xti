# Firmadan sosyal profil keşfi

0.174.0 [düzenli takip](SOCIAL_TRACKING.md), önceki kaynak destekli adresleri
yeni keşif kaynakları bildirmese de dönüşümlü kontrol eder. Bu iç `tracking`
kapsamı keşif kaydına dondurulur; `brand discover` için serbest URL listesi
eklenmez. [Yeni canlı örneklem ve ortak kuyruk ölçümü](SOCIAL_TRACKING_ACCEPTANCE.md).

0.173.0 sonuçları [firma incelemesi, vaka ve düzenli takibe](SOCIAL_TRACKING.md)
bağlar. İnsan kararı ve sağlayıcı kanıtı özgün keşif sonucundan ayrı kalır.

0.172.0'da bulunan LinkedIn şirket adaylarına isteğe bağlı
[Bright Data ek kanıtı](BRIGHTDATA_SOCIAL.md) bağlanabilir. Bu ayrı ve açık
seçilen işlem, aşağıdaki ücretsiz keşfi kendiliğinden ücretli hale getirmez.

0.171.0 ile firma adı/domaini, tek bir sosyal keşif çalışmasının başlangıcıdır.
`brand discover` sonuçları birleştirir, açık profil sayfalarını kontrol eder ve
kanıtlı sonucu aynı çalışma alanında saklar. Firecrawl kurulmaz; yeni bağımlılık yoktur.

## Kullanım

Mevcut kurulumda şema 80 → 81 geçişi açıkça yapılır. `migrate` eski veritabanını
yedekler; eski kayıtlar ve satır kimlikleri korunur. Yeni kurulum `./setup` ve
`./xti init` ile başlar.

```sh
./xti migrate
./xti brand discover securehup.com --name SecureHup
```

Firma adı verilmezse domain etiketinden çıkarılır. Sosyal hesap kullanıcı adını
vermek ön koşul değildir. Çalışma, domain/firma adından en fazla iki kullanıcı
adı adayı türetir; firma ana sayfasındaki ve aynı domain için saklanmış arama
sonuçlarındaki profil bağlantıları farklı kullanıcı adlarını da ekleyebilir.

```sh
# Ağ çağrısı veya kredi tüketimi olmadan kapsam
./xti brand discovery-plan securehup.com --name SecureHup

# Aynı anahtar tekrar kullanıldığında saklanan ilk sonuç; yeni ağ isteği yok
./xti brand discover securehup.com --name SecureHup --idempotency-key securehup-social-1

# Geçmiş ve bütün bağlantılar/kanıtlar
./xti brand discoveries --domain securehup.com
./xti brand discovery-show CALISMA_UUID
./xti --json brand discovery-show CALISMA_UUID

# İsteğe bağlı dar kapsam / farklı bütçe
./xti brand discover securehup.com --name SecureHup \
  --platform Instagram --platform Twitter --platform LinkedIn \
  --budget-seconds 90 --timeout 10 --max-pages 20

# İsteğe bağlı Tavily; mevcut özel anahtar yapılandırmasını kullanır
./xti brand discover securehup.com --name SecureHup --web-search
```

Varsayılan akış Tavily çağırmaz. `--web-search`, genel ve seçilmiş Instagram/X
alanlarında en fazla üç `advanced` sorgu yapar; mevcut kredi modelinde planlanan
üst sınır altı kredidir. Otomatik tekrar veya otomatik sorgu genişletme yoktur.
Sağlayıcının bildirdiği kredi ve kullanımın bilinmediği başarısız istekler
raporda ayrıdır. Anahtar yoksa ücretsiz kaynaklar ve sayfa kontrolleri devam eder;
Tavily durumu ayrıca gösterilir. Anahtar eklendikten sonra yeni çalışma için yeni
tekrar anahtarı gerekir. Anahtarı komut argümanına veya rapora yazmayın.

## Sonuçların anlamı

| JSON durumu | Terminal | Dayanak |
|---|---|---|
| `found` | Bulundu | Profil adresi ve sayfanın profil kimliği işaretleri birlikte uyuşuyor. |
| `candidate` | Aday / doğrulanamadı | Araç, arama veya firma sayfası bağlantıyı bildirdi; sayfa doğrulanamadı. |
| `not_found` | Bu adreste bulunamadı | Seçili adres 404/410 veya açık hesap yokluğu yanıtı verdi. |
| `inconclusive` | Kontrol edilemedi | Denenen kullanıcı adı için yeterli kanıt yok, erişim/süre/sayfa sınırı var. |

HTTP 200 tek başına profil kanıtı değildir. Giriş ekranı, CAPTCHA, erişim engeli,
farklı hesaba yönlendirme veya araçta kaydın bildirilmemesi yokluk kararı üretmez.
HackerNews `No such user.` yanıtı, araç hesabı bildirse bile `not_found` olur.
GitLab kullanıcı sayfası ve LinkedIn'in sayfa kimliğini belirten yapılandırılmış
verisi ayrıca tanınır. Genel JavaScript gövdesi veya bir gönderide başka bir
kişinin/kuruluşun adı geçmesi profil doğrulaması sayılmaz.

`found` **hesabın varlığıdır**. `brand_relation` ayrıca `unverified`, `name_match`
veya `profile_links_to_domain` döner. Firma adına benzemek ya da firma domainine
bağlantı vermek otomatik resmî hesap/sahiplik/taklit kararı değildir.

Her satırda tam URL, kimlerin bildirdiği, kontrol gerekçesi, zaman, HTTP durumu,
başlık, sınırlı açıklama ve gövde SHA-256 bulunur. Aynı kanonik URL farklı
kaynaklardan geldiğinde tek satırdır. LinkedIn company → showcase yönlendirmesi,
hedef profil doğrulandığında `aliases` altında birleşir. Ham HTML saklanmaz.

## Kapsam, performans ve güven

- Kurulu, sürümü ve kataloğu doğrulanan Maigret/Sherlock kullanılır. Varsayılan
  birleşim 41 platformdur; kaynağın `unreported_platforms` bilgisi korunur.
  Her platformda bütün kullanıcı adlarının tarandığı anlamına gelmez.
- Varsayılan ağ bütçesi 90 saniye, tek sayfa 10 saniye, en fazla 40 profil
  sayfasıdır. İzin verilen aralıklar sırasıyla 15–300, 5–30 ve 1–80'dir.
  Toplam bütçenin yarısı aday toplamaya ayrılır; kalanı bağımsız doğrulamaya kalır.
  Saklama/yerel okuma giderleri ağ bütçesinin dışındadır.
- Sayfa eşzamanlılığı dört; aday sınırı 120'dir. Kuyrukta süre dolarsa yeni
  sayfa isteği başlamaz. Yavaş veri gönderen yanıtlar toplam süreyi sıfırlayamaz.
- Her HTTPS adımında genel IP kontrolü, sayısal adrese bağlantı ve TLS/SNI
  doğrulaması yapılır. Yönlendirme yalnız ilgili platformun izinli hostlarına
  gider. Yerel/özel IP, başka host, HTTP, özel port veya kullanıcı bilgili URL
  reddedilir. Anahtar/cookie/oturum bilgisi profil sayfasına gönderilmez.
- 0.171.1 firma ana sayfasında kök, `www` ve `about` tam hostlarını destekler.
  `about` adresi yalnız sunucu oraya yönlendirirse alınır; ek sayfa taraması
  başlatılmaz. Diğer alt alanlar ve dış domainler otomatik açılmaz.
- Sayfa başına en fazla üç HTTP adımı, 2 MiB gövde, 32 KiB başlık; HTML
  derinliği/düğüm sayısı ve yapılandırılmış veri boyutu sınırlıdır. Eksik veya
  çelişkili HTTP yanıtı profil kanıtına dönüştürülmez.
- `gzip` yanıtı 0.171.1 ile açılır; hem aktarılan hem açılmış boyut için
  ayrı 2 MiB sınırı vardır. Bozuk, kesik, ek veri taşıyan veya ardışık gzip
  üyeli yanıt kanıt sayılmaz. `body_sha256` açılmış gövdeyi; `received_bytes`
  aktarılan gövdeyi gösterir. Brotli veya üst üste kodlamalar desteklenmez.
- `metrics.page_http_requests` yalnız ek sayfa kontrollerini ölçer.
  Maigret/Sherlock iç trafiği ölçülmediği için toplam internet isteği diye sunulmaz.
- Çalışma anahtarı ağdan önce transaction içinde ayrılır. Tamamlanan sonucun
  tekrar okunması ağ çağırmaz. Kesintiden kalan `running` makbuzu otomatik
  yeniden çalıştırılmaz; kullanıcı yeni anahtarla yeni deneme başlatır.
- Aynı anahtar/farklı kapsam `idempotency_conflict` verir. Firma alanları ayrı;
  sonuçta kapsam ve kanıt özeti doğrulanır. Yedek/geri yükleme raporu da korur.
  En fazla 10.000 çalışma, 64 MiB toplam JSON, rapor başına 2 MiB saklanır;
  sınırda sessiz silme yapılmaz.

Bir kaynak kesilirse diğer kaynakların kanıtları korunur; çalışma `partial`
olabilir. Terminalde bütün profil satırları ve doğrulanmış hesap bulunmayan
platformlar gösterilir. Bu durum “o platformlarda hesabı yok” anlamına gelmez.

Eski `username-preview` ve `watch-*` komutları kaynak iddialarını kendi mevcut
sözleşmeleriyle sunar. Bu belgedeki birleşik sayfa doğrulaması `brand discover`
ve `brand.discovery.*` yüzeyindedir; eski `found_unverified` sahiplik kanıtına
dönüştürülmez.

## Platforma bağlanacak JSON işlemleri

`engine` ve firma kapsamlı `platform request`: `brand.discovery.plan/list/show`
salt okunur; ağ veya araç çalıştırmaz. `plan` alanları CLI kapsamıyla aynıdır.
`list` alanları `domain?`, `offset` (varsayılan 0), `limit` (varsayılan 20,
en çok 100); `show` alanı `identifier`dır.

Yazma/arama yalnız `platform request` içindeki `brand.discovery.run` işlemidir.
Bu işlem eşzamanlı çalışır ve yanıt dönene kadar firma yazıcı kilidini tutar;
UI ekibi çağrıyı kendi arka plan işine koyabilir. Mevcut kaynak iş kuyruğuna
kendiliğinden görev eklemez. .NET/oturum/API sunucusu bu değişikliğin parçası değildir.

```json
{
  "contract_version": 1,
  "request_id": "social-1",
  "operation": "brand.discovery.run",
  "parameters": {
    "expected_workspace_id": "GUNCEL_FIRMA_WORKSPACE_UUID",
    "idempotency_key": "securehup-social-1",
    "domain": "securehup.com",
    "name": "SecureHup",
    "web_search": false,
    "budget_seconds": 90,
    "timeout": 10,
    "max_pages": 40
  }
}
```

Sonuç `data.record` (kimlik, kapsam, başlangıç/bitiş, durum, rapor hash'i ve
`report`) ile `data.replayed` alanlarını içerir. Raporda `profiles`, `counts`,
`coverage`, `sources`, `homepage`, `metrics`, `notes` vardır. Kesintiden kalan
makbuzda `record.status=running`, `record.report=null` olabilir; başarılı ve
tamamlanmış tarama gibi gösterilmemelidir. Ağ/kaynak eksikleri raporun `partial`
durumundadır; taşıma zarfının `complete` olması bütün hesapların bulunduğunu
ifade etmez.

Eksik sonuç `not_found`, yanlış workspace `scope_mismatch`, farklı kapsamda
tekrar anahtarı `idempotency_conflict` verir. Anahtar, ham Nmap seçenekleri,
serbest URL/host veya firma seçimini değiştiren alanlar kabul edilmez.
Manifestte ağ erişimi olan firma işlemleri `request_network_operations`
alanında açıkça listelenir: `reports.fetch`, `brand.discovery.run`.

## 19 Kasım 2026 canlı kabul

0.171.0, macOS/Python 3.13 üzerinde yeni ve izole veri alanı; SecureHup için
varsayılan ücretsiz akış. Anahtar, Tavily veya Firecrawl kullanılmadı.

| Profil | Sonuç |
|---|---|
| `github.com/securehup` | Profil doğrulandı. |
| `gitlab.com/securehup` | Profil ve firma domainine bağlantı görüldü. |
| `instagram.com/securehup` | Maigret bildirmedi; bağımsız sayfa kontrolü doğruladı. |
| `linkedin.com/showcase/securehup` | Profil doğrulandı; company adresi aynı hesaba birleştirildi. |
| `x.com/securehup` | Profil doğrulandı. |
| HackerNews `securehup` | Kaynak adayı; canlı sayfa HTTP 419 verdi, doğrulanmış hesap sayılmadı. |

Ölçüm: 6,438 saniye toplam, ağ/karar akışı 6,329 saniye. Yedi profil sayfası
kontrolü, yönlendirmeler ve ana sayfayla 12 ek HTTP isteği, altı tekil kayıt,
bir yönlendirme birleşimi. Aynı anahtarın tekrarı 0,063 saniye; ağ çağrısını
hata veren test kancasıyla kapatıp aynı raporun döndüğü doğrulandı.

Bu tek hedef ölçümüdür; genel internet doğruluk yüzdesi veya SLA değildir.
Doğrulanmış profil varlığı, bütün hesapların keşfi ve firma sahipliği ayrı
değerlendirilir. Eski gerçek `No such user.` HTML örneği ağsız yeniden işleme ve regresyon
senaryosuyla korunur; bugünkü 419 yanıtı eski yokluk yanıtıymış gibi gösterilmez.

Yeni Tavily `advanced`/alan filtreli orkestrasyonunun payload, kredi görünürlüğü,
eksik anahtar ve kısmi hata davranışları kontrollü testtedir. Bu sürümün canlı
kabulü ücretsiz akış içindir; önceki Tavily canlı kabulü [ayrı kayıttadır](TAVILY_LIVE_ACCEPTANCE.md).
Özel kanıt alanı: `/private/tmp/xti-social-0171-acceptance-4ibp8wit`;
ham kanıtlar ve veritabanları Git'e eklenmez.

## Farklı firmalarda sonraki kabul

0.171.1 ile on firmanın önceden seçilmiş 26 profil referansı karşılaştırıldı.
Tümü sonuçta yer alıyor: 23 profil doğrulandı, üç LinkedIn profili aday kaldı.
Farklı kullanıcı adlarını kaçıran gzip/ana sayfa yönlendirme eksikleri bu
çalışmada düzeltildi. Bütün referans bağlantıları, iki turun karşılaştırması
ve genelleme sınırları [ayrı rapordadır](SOCIAL_DISCOVERY_ACCEPTANCE.md).
