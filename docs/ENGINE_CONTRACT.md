# Engine okuma sözleşmesi v1

**Uygulama:** 0.153.0 · **Sözleşme:** 1 · **Veritabanı şeması:** 73.

`engine` komutu, başka bir uygulamanın XTI'da saklanan kayıtları ortak bir
JSON biçiminde okuyabilmesini sağlar. Sekiz işlem vardır: arama, kayıt ayrıntısı,
kaynak durumu, proje araç kataloğu, `research.show` ilişkili kanıt araştırması
ve üç warninglist okuma işlemi.
Mevcut terminal komutları ve `--json` çıktıları korunur. `news` ve `mention`
kayıt aileleri mevcut arama/ayrıntı işlemleriyle okunur; araştırmanın ilk
kapsamı DNS/IOC/CTI'dır. [Araştırma isteği, sonucu ve sınırları](RESEARCH.md).
0.153.0 warninglist geçmişi için çekirdek şemayı 73'e taşımıştır; mevcut
kayıt alanlarının geçişi ayrı ve açık `./xti migrate` adımıdır.
[Güncelleme rehberi](GETTING_STARTED.md) uygulanır.

Bu okuma katmanı yeni internet toplaması başlatmaz. İnternetten veri alan
mevcut toplama komutları kullanılmaya devam eder; `engine` onların sakladığı
sonuçları okur. Bu kişisel `engine` girişinde firma seçimi veya kalıcı iş
kuyruğu yoktur. 0.147.0'ın ayrı [platform protokolü](PLATFORM_ENGINE.md),
güvenilen başlatıcının seçtiği firmaya özel kayıt alanını doğrular; içerik
okuma ve kalıcı iş kabulü/durum/sonuç/iptal işlemlerini sağlar. Kaynakları
çalıştıran worker ayrıca açıkça çağrılır. Platform işlemleri bu belgedeki
`engine` v1'e eklenmez; iki girişin sözleşme sürümü ayrı ayrı `1`'dir.

Bu repo motoru, sürümlü sözleşmeleri, kullanım örneklerini ve belgeleri
sunar. .NET istemcisini ve bağlantısını repoyu kullanan ekip geliştirir;
backend, kullanıcı/oturum/rol yönetimi ve web paneli o ekibin kapsamındadır.
Mevcut kayıtlar SQLite'ta tutulur. Platformun PostgreSQL yerleşimi ve
gerekiyorsa veri geçişi de kullanan ekibin sorumluluğundadır; bu sürüm
PostgreSQL geçişi yapmaz. Motorun depolama portları, veri bütünlüğü ve
iş sözleşmeleri bu repoda korunur ve geliştirilir.

Gerçek .NET bağlantısı, kullanıcı oturumu ve yetkilendirme tüketici
platformun işidir. Geniş STIX/TAXII paylaşımı ve isteğe bağlı LLM desteği
en son, ihtiyaç halinde değerlendirilir.
Mevcut sınırlı STIX çıktısı değişmez. Güncel sıra ve sorumluluklar
[motor planındadır](roadmap/ENGINE_INTEGRATION_ROADMAP.md).

## Hızlı kullanım

Desteklenen işlemleri ve sınırları kayıt alanına erişmeden görmek için:

```sh
./xti engine --describe
```

Kayıtlı verilerde domain aramak için:

```sh
./xti engine <<'JSON'
{
  "contract_version": 1,
  "request_id": "arama-1",
  "operation": "search",
  "parameters": {
    "query": "example.com",
    "kinds": ["domain"],
    "offset": 0,
    "limit": 20
  }
}
JSON
```

`example.com` burada örnek arama metnidir. Eşleşme bulunmaması geçerli bir
arama sonucudur. Veritabanı hazırlanmamışsa arama hata verir ve kendiliğinden
kayıt alanı oluşturmaz.

Başka kayıt alanı kullanılacaksa güvenilen başlatıcı seçer:

```sh
./xti --data-dir /operatorun/sectigi/kayit-alani engine --describe
```

Bu yol örnektir. `data_dir`, dosya yolu, komut metni, kullanıcı kimliği veya
`tenant_id` JSON isteğine konulmaz; bilinmeyen alanlar reddedilir.

## İstek ve cevap

Her çalıştırma stdin üzerinden **tek UTF-8 JSON belgesi** okur. İsteği gönderen
uygulama yazmayı bitirip stdin'i kapatmalıdır. `request_id` 1–128 ASCII
karakterdir: ilk karakter harf veya sayı; devamında harf, sayı, `.`, `_`, `:`
ve `-` kullanılabilir. Bu alan isteği cevapla eşleştirir; kalıcı iş kimliği
veya tekrar önleme anahtarı değildir.

İstek alanlarının tamamı zorunludur:

| Alan | Anlamı |
|---|---|
| `contract_version` | Tamsayı `1`; uygulama sürümünden ve veritabanı şemasından ayrıdır |
| `request_id` | İstemcinin seçtiği eşleştirme kimliği |
| `operation` | `search`, `record.get`, `sources.status`, `components.list`, `research.show`, `warninglists.status`, `warninglists.lookup`, `warninglists.run.get` |
| `parameters` | İşleme özel seçenek nesnesi; seçenek yoksa `{}` |

Cevabın ortak alanları:

| Alan | Anlamı |
|---|---|
| `contract_version` / `engine_version` | Cevabın sözleşme ve uygulama sürümü |
| `request_id` / `operation` | Tanınan istek kimliği ve işlem; çözülemeyen alan `null` olabilir |
| `status` | Yerel okuma tamamlandıysa `complete`, hata varsa `error` |
| `scope` | Bu girişte `{"mode":"local-workspace"}` |
| `data` | Başarıda işlem sonucu; hatada `null` |
| `error` | Başarıda `null`; hatada `code`, `message`, `retryable` |

`complete`, yerel okumanın tamamlandığı anlamına gelir. Kaynak eski,
başarısız veya hiç çalıştırılmamış olabilir; bunlar veri içinde ayrıca
gösterilir. Boş eşleşme listesi de “tehdit yok” kararı değildir.

Geçerli sabit CLI çağrısında başarı ve işlem hataları stdout'a tek JSON
cevabı yazar. İnsan için terminal açıklaması veya traceback bu cevaba
karışmaz. `--help` ve yanlış CLI seçenekleri normal terminal davranışını
korur; JSON protokolünün parçası değildir. İstemci çalıştırıcıyı ve argv
değerlerini sabit tutmalı, kullanıcı metnini shell komutu olarak üretmemelidir.

## `search`: saklanan verilerde arama

| Parametre | Kural |
|---|---|
| `query` | Zorunlu; normalleştirilmiş 2–200 görünür karakter |
| `kinds` | İsteğe bağlı, boş olmayan kayıt türü listesi; verilmezse on iki aile |
| `include_inactive` | Boolean; varsayılan `false` |
| `offset` / `limit` | Sayfa başlangıcı ve boyutu; varsayılan `0` / `50` |

On iki kayıt ailesi: `domain`, `finding`, `social`, `ransomware`, `public-notice`,
`case`, `supplier`, `organization`, `cti`, `indicator`, `news`, `mention`.

Firma/tedarikçi içerik referansı `kind="mention"`,
`record_type="company_mention"`, `namespace="tavily"` kullanır.
Kaynağın sonucu bir adaydır; kayıt ayrıntısı sorgu/hedef tanımını,
görünür eşleşme gerekçesini ve o sorgunun son deneme/başarı durumunu
korur. API anahtarı ve ham HTTP cevabı engine çıktısına girmez.

Haber referansı `kind="news"`, `record_type="news_article"` ve yayıncının
`cisa`, `ncsc` veya `cert-fr` namespace'ini taşır. `record_id`, kaynak ile
yayıncı kimliğinden türetilmiş 64 haneli kimliktir; içerik özeti değildir.
`record.get` kontrollü haber alanlarını, ilk/son görülme ve son içerik
değişimi bağlarını, kaynak son deneme/son başarı bilgisini verir. `current`
son bilinen yerel haber halidir; akışta hâlâ bulunma veya doğrulanmış
tehdit iddiası değildir. Yayıncı atfı ve kaynak tarihinin ham metni korunur.

Sonuç `query`, `kinds`, `include_inactive`, `checked_at`,
`total_match_count`, `offset`, `limit`, `has_more`, `results`, `coverage`,
`notes` ve `consistency` alanlarını taşır. Her eşleşmede kayıt referansı,
gösterim değeri, eşleşen alan/değer, eşleşme türü, yerel kayıt durumu, kaynak,
kayıt zamanı ve varsa kaynak çalışma kimliği bulunur.

`coverage`, hangi kaynakta kaç kaydın incelendiğini ve eşleştiğini; varsa
son deneme ve son başarılı çalışma bilgilerini ayrı gösterir. Arama
sonucundaki `details` insan için açıklama metnidir. Yapılandırılmış kayıt
ve kanıt bölümleri için `record.get` kullanılır.

Arama kendi içinde tek salt okunur veritabanı kesitidir:
`consistency="single_read_snapshot"`. Ayrı sayfa istekleri aynı kesiti
paylaşmaz. Arada kayıt değişirse sıralama ve toplam değişebilir. Sonuçlar
tam eşleşme, başlangıç eşleşmesi ve içerme sırasıyla; eşitliklerde kayıt
türü/değer/kaynak/kimlik üzerinden kararlı biçimde sıralanır.

`include_inactive=true`, etkin olmayan veya kaynaktan çıkarılmış kimliklerin
son bilinen kayıtlarını da getirir. Bütün tarihî sürümlerin arşivi değildir.
`current` kaynakla yeni bağlantı kurulduğu veya hedefin güvenli olduğu
anlamına gelmez.

## `record.get`: kayıt ve kanıt ayrıntısı

Arama sonucundaki `reference` nesnesini aynen kullanın. Aşağıdaki sıfırlı
UUID yer tutucudur; çalıştırmadan önce arama sonucundaki gerçek referansla
değiştirilmelidir:

```sh
./xti engine <<'JSON'
{
  "contract_version": 1,
  "request_id": "ayrinti-1",
  "operation": "record.get",
  "parameters": {
    "reference": {
      "kind": "domain",
      "record_type": "registered_domain",
      "namespace": "local-assets",
      "record_id": "00000000-0000-0000-0000-000000000000"
    },
    "offset": 0,
    "limit": 20
  }
}
JSON
```

Referansın dört alanı birlikte kimliktir. `record_id` tek başına yeterli
değildir: iki ransomware kaynağı aynı kimliği kullanabilir. `source`
gösterim metninden `namespace` türetmeyin; CTI'da birden çok kaynak adı
birleşebilir. Desteklenen bütün eşlemeler `engine --describe` içinde vardır.

| Kayıt ailesi | Sabit kaynak alanı (`namespace`) |
|---|---|
| Kayıtlı domain / alt alan adayı | `local-assets` / `passive-discovery` |
| Marka bulgusu | `local-match` |
| Sosyal izleme / sosyal çalışma öğesi | `local-social` |
| Ransomware iddiası | `threatcluster` veya `ransomlook` |
| Kamu ihlal olayı | `hibp` |
| Yayıncı haberi | `cisa`, `ncsc` veya `cert-fr` |
| Firma/tedarikçi içerik adayı | `tavily` |
| Vaka / tedarikçi / kuruluş | `local-case-management` / `local-suppliers` / `local-organizations` |
| CTI varlığı / IOC | `local-cti` / `local-ioc` |

Cevapta `reference`, yapılandırılmış ana `record`, `sections`, `provenance`
ve `notes` bulunur. Bölümler kayıt türüne göre kaynak gözlemleri, insan
incelemeleri, değişimler, kaynak iddiaları, vaka kanıtları veya bağlantı
geçmişini taşır. Her bölüm `items`, `total_count`, `offset`, `limit` ve
`has_more` alanlarıyla sayfalanır. Seçilen `offset` ve `limit` bütün bölümlere
uygulanır; ana kayıt sayfalanmaz. Toplam kayıt sayısı gösterilen sayıyla
karıştırılmaz.

Kaynak iddiası ile insan kararı ayrı korunur. Çıkarılmış katalog kaydı son
bilinen içeriği ve çıkarılma kanıtıyla okunabilir. Sosyal kayıt kendi
tarihî çalışma öğesiyle çözülür; güncel izleme tanımıyla yeniden yazılmaz.
Sosyal profilin güncel insan kararı yalnız `provenance.current_review`
alanındadır; bu karar tarihî kaynak öğesinin içine yazılmaz.

Her ayrıntı isteği kendi salt okunur kesitini açar. Arama ile ayrıntı arasında
veri değişmiş olabilir; referans, arama anındaki bütün içeriği donduran bir
sürüm anahtarı değildir. Geçersiz kaynak/tür birleşimi reddedilir; geçerli
bir referansla kayıt bulunamazsa `not_found` döner.

## `sources.status`: kayıtlı kaynak durumu

```sh
./xti engine <<'JSON'
{
  "contract_version": 1,
  "request_id": "kaynaklar-1",
  "operation": "sources.status",
  "parameters": {
    "stale_after_hours": 24
  }
}
JSON
```

`stale_after_hours` 1–8760 arasında tamsayıdır; varsayılan 24. İsteğe bağlı
`domain` kayıtlı kök domaini seçer. Bu filtre yalnız ilgili tarama/keşif
kayıtlarını daraltır; sosyal izlemeler ve genel beslemeler ayrıca görünür.
Domain filtresi kullanıcı yetkisi veya müşteri yalıtımı değildir.

Cevap `observed_at`, `domain`, `storage_state`, `stale_after_hours`,
`attention_count`, `sources`, `notes` ve `consistency` alanlarını taşır.
Kaynak satırlarında kimlik/kapsam, kurulum, son çalışma sonucu, son deneme,
son başarı, kayıt sayısı, hata, güncellik, başarı yaşı ve bekleme bilgileri
ayrıdır. Kaynak çalışma kimliği olmayan yerde kimlik üretilmez.

Bu görünüm kaynağın şu an erişilebilir olduğunu denemez. Kaynak okumaları
bağımsız olabilir: `consistency="independent_source_reads"`. Bütün kaynaklar
için tek ortak anlık kesit garantisi yoktur. Kayıt alanı yoksa
`storage_state="not_initialized"` bildirilir; klasör veya veritabanı yaratılmaz.

## `components.list`: proje araç kataloğu

```sh
./xti engine <<'JSON'
{
  "contract_version": 1,
  "request_id": "araclar-1",
  "operation": "components.list",
  "parameters": {}
}
JSON
```

Parametre nesnesi boş olmalıdır; dosya yolu, kurulum veya araç çalıştırma
seçeneği kabul edilmez. İşlem `--data-dir` ile seçilen kanıt alanından
bağımsız olarak çalışan proje kurulumunu okur. Veritabanı gerektirmez ve
veri dizini oluşturmaz. Ortak zarfın kapsamı `local-workspace` kalır;
katalog içindeki `scope="project-managed-tools"` gözlem alanını belirtir.

`data`, `catalog_version`, `observed_at`, `scope`, `components` ve `notes`
alanlarını taşır. Üç satır mevcut Maigret, Sherlock ve theHarvester'dır.
Her satır beklenen sürüm/commit/katalog kimliğini `expected`, lisans ve
ortamı `license`/`runtime`, kullanılabilen seçimleri `configuration`,
kurulum gözlemini `installation` altında verir. Komut dizileri yalnız yol
gösterir. `source_status_ids` kaynak durumundaki ilgili kimlikleri belirtir.

`installation.state` `ready`, `missing` veya `invalid` olabilir.
`verification="metadata_only"`, `execution_tested=false` ve
`scope="project-managed"` denetimin sınırıdır. `inspection_checks` denetim
kapsamını listeler; her maddenin geçtiği anlamına gelmez. Beklenen sürüm
kurulu sürüm gibi sunulmaz. Kaynak canlılığı veya tam bağımlılık bütünlüğü
kanıtlanmaz; bağımsız yerel okumalar için ortak kurulum kesiti garantisi yoktur.

0.140.0 bu işlemi v1'e ekler; önceki üç işlemin biçimi korunur.
[Araç kataloğu rehberi](COMPONENTS.md) ayrıntılı kapsam ve kullanımını açıklar.

## `warninglists.*`: kaynaklı domain/IP bağlamı

`warninglists.status` liste durumunu, `warninglists.lookup` kesin domain/IP
eşleşmesini, `warninglists.run.get` kaynak çalışması ile özgün üyelerini
okur. İndirme ve sorgu ayrı işlemlerdir; engine internetten liste indirmez.
`research.show` sonucunda aynı kesitin `warninglists` bilgisi ve
`nodes[].warninglist_matches` alanı da bulunur. Alanlar v1'e eklenmiştir;
mevcut düğüm/ilişki anlamları ve kararlar korunur.
[Parametreler, sonuçlar, güncellik ve hata kodları](WARNINGLISTS.md#engine-ve-firma-platformu).

## Hatalar ve sınırlar

| Hata kodu | Çıkış kodu | Anlamı |
|---|---|---|
| `invalid_request` | 2 | Bozuk JSON, geçersiz ortak alanlar veya girdi sınırı |
| `unsupported_version` | 2 | Desteklenmeyen tamsayı sözleşme sürümü |
| `unsupported_operation` | 2 | Desteklenmeyen işlem adı |
| `invalid_parameters` | 2 | Geçersiz veya bilinmeyen işlem seçeneği/referans |
| `not_found` | 3 | İstenen tür/kaynak alanında kayıt bulunamadı |
| `snapshot_changed` | 1 | `research.show` sayfasının kanıt/kapsam kesiti değişmiş; ilk sayfadan yeniden başlayın |
| `storage_error` | 1 | Kayıt alanı/girdi okunamadı veya kanıt bütünlüğü doğrulanamadı |
| `response_too_large` | 1 | Cevap boyutu sınırı aşıldı; daha küçük sayfa/kapsam gerekir |
| `internal_error` | 1 | Beklenmeyen hata; iç istisna metni cevaba eklenmez |
| `interrupted` | 130 | Okuma kullanıcı tarafından durduruldu |

Başarılı okumanın çıkış kodu 0'dır. Hata mesajının metnine göre karar
vermeyin; `error.code` kullanın. `retryable` yeniden denemenin uygunluğunu
belirtir; bu ilk sürüm otomatik yeniden deneme çalıştırmaz.

Örneğin sözleşme sürümü `2` ile gönderilmiş, kimliği `arama-1` olan bir
arama isteğinin cevabı aşağıdaki biçimdedir. Bu hata yeni veri toplamaz:

```json
{
  "contract_version": 1,
  "engine_version": "0.153.0",
  "request_id": "arama-1",
  "operation": "search",
  "status": "error",
  "scope": {"mode": "local-workspace"},
  "data": null,
  "error": {
    "code": "unsupported_version",
    "message": "Yalnız motor sözleşmesi 1 destekleniyor.",
    "retryable": false
  }
}
```

- Girdi en fazla 65.536 bayt; JSON iç içeliği en fazla 16 düzeydir.
- Cevap en fazla 8 MiB'dir. Büyük cevap kesilip başarı sayılmaz.
- `offset` 0–1.000.000; `limit` 1–500 arasındadır.
- Yinelenen JSON alanları, fazla belge, geçersiz UTF-8/Unicode,
  `NaN`/`Infinity` ve bilinmeyen alanlar reddedilir.
- Boolean değer, tamsayı gereken yerde kabul edilmez.
- Mevcut depoların kanıt/kapasite sınırları korunur; bozuk veya eksik
  geçmiş boş başarılı sonuca dönüştürülmez.

## Entegrasyon sınırı ve sürüm uyumu

Bu `engine` girişi güvenilen yerel çalışma alanını bütünüyle okur. İşletici veri
alanını ve süreç erişimini yönetir. Serbest kurum etiketi, domain filtresi
veya dosya yolu kullanıcı yetkisi sayılmaz. Firma kapsamında çalışma için
[ayrı platform girişi](PLATFORM_ENGINE.md) kullanılır; platform JSON'undan
firma veya dosya yolu seçilemez. Firma eşlemesini, kimliği ve yetkiyi
tüketici uygulama doğrular. Motor seçilen kayıt alanının firma bağını ve
iş/arama/sonuç kapsamını denetler. Bu sınır, servis hesabının dosyalarına
tam erişimi olan işleticiye karşı yalıtım veya hazır bir kullanıcı yetki
sistemi değildir.

İstemci desteklediği `contract_version` değerini doğrulamalıdır. İsteklerin
alanları açıkça tanımlanır; bilinmeyen istek alanları reddedilir. Cevaplara
bilinçli olarak eklenen yeni alanlar istemcinin var olan alanları okumasını
engellememelidir. Alan silme, tip veya anlam değiştirme yeni sözleşme sürümü
gerektirir; iç modeldeki değişiklik dış cevaba kendiliğinden taşınmaz.

Gerçek .NET tüketicisi ve platforma taşıma bağlantısı kullanan ekibin
işidir; bu repo bunları geliştirmez. Kalıcı iş kuyruğu ve firma alanını
iş geçmişiyle birlikte yedekleme 0.147.0 platform protokolünde uygulanır.
Kişisel `engine` v1 dört salt okuma işlemiyle kalır; platform zarfı ayrıca
`protocol="xti-platform"` ve firma kapsamı taşır. İstemci hangi girişi
kullandığını açıkça seçmelidir.
[Güncel motor planı](roadmap/ENGINE_INTEGRATION_ROADMAP.md) ve
[0143 karar kaydı](decisions/0143-versioned-engine-read-contract.md).
