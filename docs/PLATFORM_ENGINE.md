# Çok firmalı platform motoru

0.172.0 `brand.enrichment.plan/list/show` okumalarını ve firma çitiyle
`brand.enrichment.run/refresh` yazmalarını ekler. Ağ çağırabilen işlem
listesi artık `reports.fetch`, `brand.discovery.run`, `brand.enrichment.run`
ve `brand.enrichment.refresh` içerir. Run aynı anahtarı tekrar göndermez;
refresh yalnız kayıtlı snapshot'ı okur. Sağlayıcı hazır/başarısız durumu
`data.record.state` içindedir. [Sözleşme ve sınırlar](BRIGHTDATA_SOCIAL.md).

0.171.0 `brand.discovery.plan/list/show` ağsız okumalarını ve güncel workspace
kimliği isteyen `brand.discovery.run` yazmasını ekler. Run eşzamanlı ağ çağrısı
yapabilir; aynı anahtar/kapsam saklanan ilk sonucu döndürür. Manifestte
`request_network_access=true`; ağ çağırabilen işlemler
o sürümde `request_network_operations=[reports.fetch, brand.discovery.run]` ile sınırlıydı.
İş kabulü ve engine okumaları ağsız kalır. [Parametreler](SOCIAL_DISCOVERY.md).

0.170.0 `relationships.notification-show` firma kapsamlı salt okunur
bildirim kanıtıdır. Platform `relationships.notify` yazması güncel
workspace çitini ister. Kaynak işi v5 `publisher_documents` ve
`relationship-notify` adımını mevcut kuyruk3 içinde yürütür; eski
iş modelleri 1–4 okunur. [Sözleşme/kullanım](PUBLISHER_JOB_DELIVERY.md).

0.169.0 `reports.publishers/fetches/fetch-show`, `relationships.queue`,
`journals.status/archive-plan/show` okumalarını ekler. `reports.fetch`,
`journals.archive-apply/restore` yalnız işletici veya firma yazma girişindedir;
engine okumaları ağa çıkmaz. Belge modeli 1 ve 2 birlikte okunur. Firma
workspace çiti ve ortak yazıcı kilidi korunur.
[Tam parametreler ve sonuçlar](PUBLISHER_REVIEW_RETENTION.md#json-sözleşmesi).

0.168.0 `sightings.list/show`, `relationships.candidates/show`, `identity.view`
ve `ioc.compare` okuma işlemlerini ekler. `sightings.record/revoke` ve
`relationships.review` yalnız firma yazma girişindedir; kapsam çiti,
tekrar anahtarı ve beklenen sürüm kuralları uygulanır. Kaynak işi v4 açık
sıra/hata politikası ile `report-capture` ve `ripestat-whois` adımlarını
sunar. [Alanlar, örnekler, hata ve sınırlar](EVIDENCE_WORKFLOWS.md#json-sözleşmesi).


0.167.0 rapor sürümlerini `research.show` / `research.priorities` ve
kayıtlı incelemelerde gösterir. Rapor `references` alanı `record.get`
ile aynı firmada seçilen belge sürümünü açar; başka firmanın belge
kimliği `not_found` verir. Öncelik v8, model 3, zarf v1; ek migration
yoktur. .NET/UI ekibinin yeni bir tarama veya ayrı rapor motoru yazması
gerekmez. [İlişkiler ve örnek JSON](REPORTS_OBSERVATIONS.md).

0.166.0 rapor/gözlem okumalarını ve `reports.capture` / `reports.link`
yazmalarını ekler. Yazmalar `expected_workspace_id` ve `idempotency_key`
ister; insan bağlantısı ayrıca `expected_revision` ile korunur. Bağlantı
başka firma kaydına gidemez. Restore sonrası eski workspace isteği
reddedilir. Yeni kaynak sorgusu yoktur; saklı başlık/özet kullanılır.
[Parametreler, sürüm ve hata kodları](REPORTS_OBSERVATIONS.md#json-sözleşmesi).

0.165.0 `ioc.lifecycle` işlemi seçili firma alanındaki IOC kanıtını ve
kaynak toplama geçmişini birlikte değerlendirir. Yeni ağ isteği veya
yazma yapmaz; firma/path seçimi JSON parametresi değildir. Aynı gösterge
iki firmada farklı kayıtlarla değerlendirilir. [İstek ve sonuç](IOC_LIFECYCLE.md).

0.163.0 `research.show` / `research.priorities` ve kayıtlı incelemelerde
`supplier_event`, `supplier_watch`, `supplier_risk` düğüm/ilişki türleri
mevcut model 3 alanlarıyla döner. Öncelik `research-priority-v6`;
istek/zarf, firma kapsamı ve `record.get` türleri değişmez. Araştırma
kaynak yenilemez, izleme açmaz ve bildirim yazmaz. Kaynak/karşılaştırma
kimlikleri kanıtlarda kalır; kart ayrı kalıcı risk kaydı değildir.
[Provenans ve durum alanları](RESEARCH.md#tedarikçi-izleme-ve-inceleme-bağlamı).


**Uygulama 0.168.0 · protokol `xti-platform` v1 · çekirdek şema 78 · kuyruk 3.**

0.164.0 firma kapsamlı `company.review` ve `investigation` okuma/yazma
işlemleri ekler. Kimlik/rapor önerisi ve kararları mevcut workspace kimliği,
writer kilidi ve tekrar anahtarıyla korunur. Kaynak işlerinin yeni v3 biçimi
RIPEstat, yayıncı ve yerel rapor adımlarını taşır; eski v1/v2 işler okunur.
Yeni kaynak işleri öncesinde eski firma kuyruğu `platform jobs-migrate`
ile şema 3'e açıkça yükseltilir; öncesinde doğrulanmış yedek alınır.
[Parametreler ve örnekler](INVESTIGATION.md#kaynak-işleri-ve-platform-sözleşmesi).

Bu giriş, aynı platformun farklı firmaları için ayrı kayıt alanlarında
arama, firma içeriği ve kalıcı toplama işleri çalıştırır. .NET ekibi
kullanıcıyı ve yetkisini doğrular; güvenilen başlatıcı doğru firmayı seçer.
Motor bu firma için kayıtlı alanı doğrular ve bütün işlemi o alanda yürütür.
Mevcut kişisel `engine` v1 ve terminal komutları korunur.

## Firma alanını hazırlama

Normal `./setup` sonrasında, repo kökünde yerel deneme:

```sh
./xti platform provision --root "$PWD/.xti-platform" --company firma-a
./xti platform provision --root "$PWD/.xti-platform" --company firma-b
./xti platform request --root "$PWD/.xti-platform" --company firma-a --describe
```

Kök üst klasörü mevcut olmalı. Firma kimliği küçük ASCII harf/rakam,
tire ve alt çizgi kullanan sabit kimliktir; görünen kuruluş adı değildir.
Kök, kayıt listesi ve firma dizinleri özel izinlerle oluşturulur. Var olan
kişisel klasör otomatik benimsenmez. Eski veriler taşınmaz veya silinmez.
Çekirdek veritabanının yanında sürüm 3 `engine-jobs.sqlite3` iş kuyruğu vardır.
Eski sürüm 1/2 kuyruk okunabilir; yeni kaynak işi için açık yedekli
`platform jobs-migrate --root ... --company ...` geçişi gerekir.
Kurulum yarıda kalırsa eksik alan erişim için reddedilir; üzerine otomatik
kurulum yapılmaz. İşletici alanı inceleyip kapatabilir ve yeni alan kurabilir.

Kaynak/izleme profilini hazırlamak güvenilen işletici işidir:

```sh
./xti --data-dir "$PWD/.xti-platform/firma-a" assets add example.com
./xti --data-dir "$PWD/.xti-platform/firma-a" organizations add "Örnek Firma"
./xti --data-dir "$PWD/.xti-platform/firma-a" profiles save haberler example.com --only-news --news-source cisa
```

Bu son örnek kaynak akışını sınamak içindir; firma hakkındaki web araması
[mentions](MENTIONS.md) ve [izleme grupları](MENTION_GROUPS.md) üzerinden
yapılır. Profillerin mevcut pasif kaynak ve açık izleme seçimleri korunur.
Platform kuyruğunun ilk iş türü kayıtlı toplama profilidir; Tavily grup
işi bu kuyruğa otomatik eklenmez. Firma API anahtarları, zamanlama ve
uygulama yetkileri entegrasyon ekibinin açık kapsam seçimiyle yönetilmelidir;
ortak kullanıcı anahtarını farklı müşteriler adına kendiliğinden kullanmayın.

## Warninglist kaynaklarını hazırlama

Mevcut firma alanı eski şemadaysa güvenilen işletici o alanda açık
`./xti --data-dir "$PWD/.xti-platform/firma-a" migrate` çalıştırır.
Kişisel alandaki geçiş diğer firmaların veritabanını değiştirmez.
Ardından `./xti --data-dir "$PWD/.xti-platform/firma-a" warninglists sync`
seçili firmanın listelerini internetten alır. Platformdaki okuma işlemleri
bu alanı kullanır; başka firma/kişisel katalogdan tamamlamaz.
0.157.0 ayrıca `sources.plan` ve `sources.jobs.submit/list/status/result/cancel/retry`
ile açık kaynak yenileme işleri sunar. Mevcut `platform worker` bunları
da çalıştırır; isteğe bağlı inceleme kaydı son adım olabilir. Kabul ağ
kullanmaz, firma yedeği kanıtlarla işi birlikte korur. [Sözleşme ve örnekler](SOURCE_JOBS.md).
0.158.0 aynı iş yanıtlarına `execution` kullanım raporunu ekler. Yeni
payload/result v2, eski v1 işleri de okur; platform zarfı v1 kalır. Backend
firma paketi ve ortak kota politikasını yönetir; motor iş sınırı ve kayıtlı
kullanımı bildirir. Kesilen adımda `requests.attempts=null` sıfır tüketim
anlamına gelmez. [Alanlar ve belirsizlik](SOURCE_JOBS.md#işin-kullanım-raporu).
[Kullanım, kaynak ve koşullar](WARNINGLISTS.md).

## Kayıtlı incelemeler

0.162.0 kaynak denemelerini seçili firmanın aynı araştırma kesitinde
`discovery` alanıyla sunar. Model 3/politika v5, zarf v1; eski model 1/2
incelemeler özgün okunur. Aynı domainin başka firmadaki kaynak hatası veya
çalışma kimliği görünmez. [Alanlar](RESEARCH.md#pasif-kaynakların-son-sorgu-durumu).

Firma komutları ortak kök parser ve mevcut platform yürütücüsüyle daha
hafif başlatılır. Durum/kurtarma komutu toplayıcı CLI'sını yüklemez;
doğrulanmış engine okuması gereken servisi kurar. Oturum/firma sınırı,
dosya doğrulaması, iş kabulü ve kilitler değişmez.
[Başlangıç kararı ve ölçüm](decisions/0166-platform-cold-start.md).

0.161.0 aynı firma araştırmasında kayıtlı pasif alt alan adaylarını ve
sahiplik sınıflandırmalarını da sunar. Kaynak kanıtı ve insan kararı ayrı
bağlardır. Başka firmanın aynı domain kaydı okunmaz. Model 2/zarf v1
korunur; öncelik v4'ün ilk incelemesi politika başlangıcıdır. Yeni HTTP/API
çağrısı veya aktif kapsam yazımı yoktur.
[Kapsam](RESEARCH.md#pasif-alt-alan-adayları-ve-sahiplik-incelemesi).

0.160.0 seçili firmanın kayıtlı tedarikçi adayları ve insan kararları da
aynı işlemlerden sunulur. Araştırma/öncelik `data.model_version=2`, kural
v3 olur; dış `xti-platform` zarfı v1 kalır. Eski model 1 incelemeler kendi
modeliyle okunur. İlk model 2 kaydı yeni karşılaştırma başlangıcıdır.
Firma seçimi/oturum yönetimi sınırı değişmez; kararlar API çağrısıyla
kendiliğinden onaylanmaz. [Kullanım ve uyumluluk](RESEARCH.md#tedarikçi-adayları-ve-insan-kararları).

0.159.0 `research.show`, `research.priorities` ve inceleme kaydı seçili
firmanın CNAME/TLS kanıtlarını da kullanır. Aynı sertifika başka firmada
bulunsa bile o firmanın domaini okunmaz. O dilimde sözleşme/model 1 korundu,
öncelik politikası v2 oldu; 0.160.0'ın güncel sürümleri yukarıdadır.
Eski incelemeler yeniden yazılmaz.
[Bağlantı türleri ve okuma sınırları](RESEARCH.md#cname-ve-gözlenmiş-tls-sertifikaları).

`research.history` ve `research.review.get` seçili firmanın inceleme
geçmişini ve özgün değerlendirmesini okur. `research.review.record` yalnız
bu alanın saklı kanıtlarından yeni inceleme kaydeder; internet sorgulamaz.
Kayıt isteğinde `idempotency_key` ve güncel `expected_workspace_id`
zorunludur. Aynı anahtar/kapsam ikinci kayıt oluşturmaz; yedekten dönmüş
alanda önceki workspace kimliğiyle tekrar isteği bile reddedilir.
Şema 75 geçişi her firma alanında açık ve yedeklidir.
[Tam istek, sonuç, hata ve kullanım örnekleri](RESEARCH_HISTORY.md#engine-ve-firma-platformu).

## Firma içeriklerini görme

```sh
./xti --data-dir "$PWD/.xti-platform/firma-a" organizations content KURULUS_KIMLIGI
./xti --data-dir "$PWD/.xti-platform/firma-a" organizations content KURULUS_KIMLIGI --history
```

`KURULUS_KIMLIGI` yerine kuruluş oluştururken verilen kimliği yazın.
Başlık, mevcut açıklama, kaynak bağlantısı, varsa yayın tarihi ve eşleşen
ifade gösterilir. Kontrol yapılmamış, boş başarılı sonuç, eski kayıt ve
son kontrol hatası ayrı anlatılır. Geçmiş içerik `--history` ile ayrıca
açılır; sayfa sonundaki komutla kalan sonuçlara ulaşılır.

Bu okuma yeni internet araması başlatmaz, anahtar okumaz ve kredi tüketmez.
Kaynak önerisi ile görünen metinde firma eşleşmesi ayrıdır; aynı adlı
başka şirket veya doğrulanmamış iddia otomatik kesin bulgu olmaz. Genel
haber indirme sayıları bu firma görünümünün odağı değildir.

## Başka uygulamadan çağırma

Güvenilen başlatıcı sabit çalıştırıcı ve ayrı argümanlar kullanır:

```sh
./xti platform request --root "$PWD/.xti-platform" --company firma-a
```

stdin'e tek UTF-8 JSON yazılır ve kapatılır. Örnek:

```json
{"contract_version":1,"request_id":"arama-1","operation":"search","parameters":{"query":"example.com","kinds":["domain"],"limit":20}}
```

Her cevap tek JSON belgesidir. `protocol`, `contract_version`,
`engine_version`, `request_id`, `operation`, `status`, `scope`, `data`,
`error` alanları vardır. `scope`, `mode="company-workspace"`, `company_id`,
`registry_id` ve `workspace_id` taşır; dosya yolu içermez. Firma alanı
doğrulanmadan oluşan hatalarda `scope=null` olabilir. Girdi 64 KiB, çıktı
8 MiB ile sınırlıdır.

| İşlem | Girdi | Davranış |
|---|---|---|
| `search`, `record.get`, `sources.status`, `components.list` | [Mevcut okuma sözleşmesi](ENGINE_CONTRACT.md) seçenekleri | Seçilmiş firma alanında okuma; araç kurulumu ortak işletim bilgisidir |
| `research.show` | `indicator_type`, `value`; isteğe bağlı adım/bütçe/sayfa/güncellik ve `expected_snapshot` | Aynı firmanın kayıtlı DNS/IOC/CTI kanıt yolları ve warninglist bağlamı; [sözleşme ve sınırlar](RESEARCH.md) |
| `research.priorities` | Aynı araştırma parametreleri; `offset/limit` öğe sayfasıdır | Aynı firmanın sınırlı araştırmasında gerekçeli inceleme sırası; [kurallar ve sözleşme](RESEARCH_PRIORITIES.md) |
| `research.history` | `indicator_type`, `value`; isteğe bağlı `offset`, `limit`, `expected_snapshot` | Seçili kökün kayıtlı incelemeleri; metadata/önceki kayıt bağı denetimi |
| `research.review.get` | `review_id`; isteğe bağlı `view`, `offset`, `limit` | Sabit tarihli öğeler veya önceki kayıtla fark; içerik/karşılaştırma denetimi |
| `research.review.record` | `indicator_type`, `value`, `idempotency_key`, `expected_workspace_id`; isteğe bağlı araştırma kapsamı | Aynı firmada mevcut kanıtı saklar; internet isteği yapmaz; [kayıt sözleşmesi](RESEARCH_HISTORY.md) |
| `warninglists.status`, `warninglists.lookup`, `warninglists.run.get` | [Warninglist okuma parametreleri](WARNINGLISTS.md#engine-ve-firma-platformu) | Seçili firmanın listeleri, kaynaklı eşleşmeleri ve tarihî kaynak çalışması; ağ isteği yok |
| `enrichment.lookup`, `enrichment.history`, `enrichment.run.get` | [URL/hash okuma parametreleri](INDICATOR_ENRICHMENT.md#engine-ve-firma-platformu) | Seçili firmanın CIRCL/urlscan yanıtları, kaynak ve sorgu geçmişi; ağ isteği yok |
| `organization.content` | `organization_id`; isteğe bağlı `scope_offset`, `scope_limit`, `offset`, `limit`, `stale_after_hours` | Kaynaklı firma/tedarikçi içerikleri, ayrı geçmiş ve kaynak durumları |
| `profiles.list` | İsteğe bağlı `offset`, `limit` | Etkin profil adı, kimliği, sürümü ve seçilen domain; devam sayfası |
| `jobs.submit` | `idempotency_key`, `profile_name`, `profile_revision`, `expected_workspace_id` | Kalıcı kabul; kaynak isteği veya arka plan süreç başlatmaz |
| `jobs.status` | `job_id` | Kaydedilmiş durum, kaynak oturumu ve sonuç varlığı |
| `jobs.result` | `job_id` | Durum ve varsa değişmez kaynak makbuzları; kesintide sonuç özeti boş olabilir |
| `jobs.cancel` | `job_id` | Yalnız bekleyen işi iptal eder; kayıt ve tekrar anahtarı korunur |

İnceleme geçmişi sayfaları 1–100 kayıtla sınırlıdır. Diğer genel liste
sınırı 1–500, kapsam sayfası 1–100, başlangıç 0–1.000.000, güncellik
eşiği 1–8.760 saattir. `profiles.list` sonucunda `profiles`, `offset`,
`limit`, `has_more` ve `next_offset` bulunur. Profil satırları `id`, `name`,
`revision`, `domain` ve `definition_sha256` taşır.

Firma içeriği için örnek istek:

```json
{"contract_version":1,"request_id":"icerik-1","operation":"organization.content","parameters":{"organization_id":"00000000-0000-0000-0000-000000000000","scope_limit":20,"offset":0,"limit":20,"stale_after_hours":24}}
```

Sıfırlı `organization_id` yerine seçilen firma alanındaki gerçek kuruluş
kimliğini yazın. Bu kuruluş kimliği platformun `company_id` değeriyle aynı
alan değildir; başka firmanın kuruluş kimliği seçili alanı değiştiremez.

`organization.content` sonucunda `organization` (`id`, `name`, `active`),
`state`, `observed_at`, `stored_data_only=true`,
`consistency="single_read_snapshot"`, `stale_after_hours`, `scopes`,
`sections` ve `notes` bulunur. `scopes`, `sections.content` ve
`sections.historical_content` sayfaları `items`, `total_count`, `offset`,
`limit`, `has_more` taşır. JSON'da iki içerik bölümü de her zaman vardır;
`--history` yalnız terminal gösterimini değiştirir. Kapsam ve içerik
sayfaları bağımsızdır; toplamlar ve kuruluş durumu kapsam sayfasıyla
daralmaz. Ayrı istekler arasında kayıtlar değişebilir.

İçerik satırlarında `title`, `available_excerpt`, `source_url`,
`published_at`, `target`, `source_run_id`, `scope_status`, `status`,
`match_status`, `matched_terms` ve `match_fields` bulunur. Açıklama
yoksa `available_excerpt=null`, `excerpt_status="unavailable"` olur;
varsa `excerpt_status="available"`, kısaltılma bilgisi `excerpt_truncated`
alanındadır. `match_status="visible_match"` görünür başlık/özet/bağlantı
eşleşmesini, `provider_candidate` yalnız sağlayıcı önerisini anlatır.
Her iki durumda `candidate=true`; bu bir tehdit doğrulaması değildir.

Üst düzey `state`, kuruluşun bütün güncel kapsamlarını değerlendirir.
`scopes.items[].state` tek kapsamın durumudur; `partial` ve `inactive`
yalnız kuruluş özetinde kullanılır.

| `state` | Kuruluş özetindeki anlamı |
|---|---|
| `content_found` | Güncel kapsamların son kontrolleri başarılı ve güncel; en az biri içerik adayı döndürmüş |
| `no_content` | Bütün güncel kapsamların son kontrolleri başarılı, güncel ve boş |
| `not_checked` | Güncel kapsamlar henüz kontrol edilmemiş |
| `check_failed` | Bütün güncel kapsamlarda son deneme başarısız |
| `stale` | Bütün güncel kapsamlarda son deneme başarılı, ancak kayıtlı başarı güncellik eşiğinin dışında |
| `outcome_unknown` | Bütün güncel kapsamlarda sonuç belirsiz veya kayıtlı başarı zamanı görünüm saatinin ilerisinde |
| `partial` | Güncel kapsamların durumları farklı ve en az birinde eksik, başarısız, eski veya belirsiz kontrol var |
| `inactive` | Kuruluş etkin değil; kayıtlı içerik geçmişi korunuyor |

Başarılı dolu ve boş kontrollerin birlikte bulunması `content_found`
üretir. `no_content` internette içerik olmadığını kanıtlamaz; önceki
arama kanıtları `sections.content` içinde `status="retained_candidate"`
olarak kalabilir. Kapsamın `source_status`, `freshness`, `latest_attempt`,
`latest_success` ve `latest_success_result_count` alanları son denemeyi
önceki başarıdan ayırır.

`jobs.submit`, `jobs.status` ve `jobs.cancel` doğrudan `data` içinde iş
özetini verir: `job_id`, `idempotency_key`, `request_sha256`,
`payload_sha256`, `profile`, `status`, `created_at`, `started_at`,
`finished_at`, `collection_session_id`, `result_available`, `error_code`.
`jobs.result` ise `data.job` içinde aynı özeti, `data.result` içinde
kayıtlı sonucu verir. Sonuç henüz kaydedilmemişse `data.result=null` olur.
Kayıtlı sonuç `collection_session_id`, `collection_status`, `asset_value`,
`analysis_status`, `started_at`, `finished_at` ve `steps` taşır. Her adımın
`step_key`, `source`, `status` ve `receipt` alanı vardır; kaynak makbuzu
bulunmayan adımda `receipt=null` olur.

`status=complete` komutun tamamlandığını belirtir. İçindeki iş durumu
`queued`, `running`, `complete`, `partial`, `failed`, `interrupted` veya
`cancelled` olabilir. Kaynak durumunu komut başarısıyla karıştırmayın.
Hatalar kararlı kod taşır: örneğin `scope_unavailable`, `scope_mismatch`,
`not_found`, `invalid_parameters`, `idempotency_conflict`, `profile_changed`,
`busy`, `storage_error`. Hata cevabı SQL, dosya yolu, ham istisna veya sır
dökmez. Desteklenmeyen ana sürüm/alan/işlem reddedilir.

## Hata ve süreç çıkış kodları

Platform işlemleri için mevcut v1 eşlemesi şöyledir. İstemci açıklama
metnini ayrıştırmak yerine `error.code` ve `error.retryable` alanlarını
kullanır. Aynı çıkış kodu birden fazla hata durumunu kapsayabilir.

| Süreç çıkış kodu | Cevap | Anlamı |
|---|---|---|
| `0` | `status="complete"`, `error=null` | İstenen işlem tamamlandı. Dönen işin `partial`, `failed` veya başka bir durumda olması ayrıca incelenir. |
| `2` | `invalid_request`, `invalid_parameters`, `unsupported_version`, `unsupported_operation` | İstek biçimi, işlem veya seçilen kapsam/seçenekler kabul edilmedi. |
| `3` | `not_found` | Bu kodu kullanan kayıt/iş okuma işleminde seçili firma alanında kayıt bulunamadı. |
| `130` | `interrupted` | Motorun yakalayabildiği kullanıcı kesintisi. Süreç zorla öldürülürse JSON cevap üretilemeyebilir. |
| `1` | Diğer hata kodları | Örneğin `scope_unavailable`, `scope_mismatch`, `idempotency_conflict`, `profile_changed`, `snapshot_changed`, `invalid_job_state`, `capacity_exceeded`, `busy`, `storage_error`, `response_too_large`, `internal_error`. |

Mevcut v1, bütün bulunamayan başvuruları tek bir hata kodunda toplamaz:

| Durum | Hata kodu / çıkış |
|---|---|
| `record.get` için geçerli tür/kaynak referansında kayıt yok; `jobs.status`, `jobs.result`, `jobs.cancel` için biçimi doğru iş kimliği yok | `not_found` / `3` |
| `organization.content` için biçimi doğru kuruluş kimliği seçili firmada yok | `invalid_parameters` / `2` |
| Yeni `jobs.submit` isteğinde profil adı yok | `invalid_parameters` / `2` |
| Var olan profil geri çekilmiş veya istenen sürüm güncel sürümle uyuşmuyor | `profile_changed` / `1` |
| `nmap.*` işleminde seçili domain altındaki hedef, plan veya iş başvurusu yok | `invalid_parameters` / `2` |

Başka firmada bulunan kimlik, seçili firmada bulunmayan kimlikten farklı
bir cevapla açıklanmaz; diğer firmanın varlığı araştırılmaz. Biçimi bozuk
kimlik ayrıca `invalid_parameters` olur. Önceden kabul edilmiş aynı işin
tekrar anahtarı mevcut işi döndürebilir; bu, yeni profil kabulü değildir.
Bu tablo mevcut davranışı belgeler; istemcileri etkileyecek hata kodu
birleştirmesi bu düzeltmede yapılmadı. [Yerel engine tablosu](ENGINE_CONTRACT.md#hatalar-ve-sınırlar)
ayrı `engine` girişinin sözleşmesidir.

## Nmap işleri ve arayüz seçenekleri

0.150.0'ın `nmap.*` işlemleri aynı firma alanında, ayrı Nmap plan/iş
kayıtlarıyla çalışır. `nmap.capabilities` boş parametrelerle tipli seçenek
kataloğunu verir. Domain onayı ve IP/CIDR hedef envanteri güvenilen
işletici tarafından önceden kaydedilir; `nmap.targets.list` bunları okur.

Boş firma alanında hazırlık, mevcut terminal komutlarıyla yapılır:

```sh
./xti --data-dir "$PWD/.xti-platform/firma-a" assets add example.com
./xti --data-dir "$PWD/.xti-platform/firma-a" surface approve example.com \
  --reason "Bu domain kapsamındaki kontrollere yetkiliyim."
./xti --data-dir "$PWD/.xti-platform/firma-a" surface nmap targets save example.com production \
  --network YETKILI_GENEL_IP_VEYA_CIDR \
  --reason "Bu kesin IP/CIDR kapsamında kontrol iznim var."
./xti platform request --root "$PWD/.xti-platform" --company firma-a --describe
```

`example.com` ve `YETKILI_GENEL_IP_VEYA_CIDR` yerine gerçek, yetkili kapsamı
yazın. Son cevabın `scope.workspace_id` alanı aşağıdaki `ALAN_UUID`
değeridir. Hedef kaydı tarama başlatmaz. Bu hazırlık SQL veya veritabanı
dosyasını elle değiştirmeyi gerektirmez; platform sözleşmesine hedef
ekleme işlemi henüz açılmadığı için güvenilen işleticiye aittir.
Dosya yolunu son kullanıcı girdisinden oluşturmayın. Domainin CDN/paylaşımlı
IP'ye çözülmesi, o IP için tarama yetkisi oluşturmaz.

Arayüzden bir plan oluşturma isteği:

```json
{
  "contract_version": 1,
  "request_id": "nmap-plan-001",
  "operation": "nmap.plans.create",
  "parameters": {
    "expected_workspace_id": "ALAN_UUID",
    "domain": "example.com",
    "target_name": "production",
    "profile": "custom",
    "ports": "22,80,443",
    "scan_type": "tcp_connect",
    "max_rate_pps": 25,
    "options": {
      "service_detection": true,
      "version_intensity": 2,
      "os_detection": false,
      "scripts": ["banner", "ssl-cert"],
      "script_timeout_seconds": 15,
      "max_duration_seconds": 900
    }
  }
}
```

`ALAN_UUID`, seçilmiş alanın gerçek UUID değeridir. Plan cevabı `data.plan`
altındadır. Diğer plan alanları `timeout_seconds`, `max_retries`,
`scan_delay_ms`, `max_parallelism`, `max_hostgroup`, `max_targets`,
`max_probe_budget`, `confirm_wide_scan`, `confirm_range_scan` olabilir.
Ham komut, dosya yolu, script dosyası ve tanımsız alan reddedilir.

Planın `data.plan.id` değeriyle aynı firma alanında iş kabulü yapılır:

```json
{"contract_version":1,"request_id":"nmap-submit-001","operation":"nmap.jobs.submit","parameters":{"domain":"example.com","plan_id":"PLAN_UUID","key":"kontrol-001","expected_workspace_id":"ALAN_UUID"}}
```

`PLAN_UUID` yerine alınan plan kimliğini yazın. Cevabın `data.job.id`
değeri worker ve sonuç işlemlerinin `job_id` değeridir. `nmap.plans.show`
planı doğrudan `data` içinde döndürür; bu okumanın kimlik alanı `data.id`'dir.

| İşlem | Parametreler | Cevap |
|---|---|---|
| `nmap.targets.list` | `domain`, isteğe bağlı `limit` | `targets` |
| `nmap.plans.show` | `domain`, `plan_id` | Kayıtlı plan |
| `nmap.jobs.submit` | `domain`, `plan_id`, `key`, `expected_workspace_id` | `job` |
| `nmap.jobs.list` | `domain`, isteğe bağlı `offset`, `limit` | `jobs` |
| `nmap.jobs.status` | `domain`, `job_id` | `job` |
| `nmap.jobs.result` | `domain`, `job_id`, isteğe bağlı `offset`, `limit` | `job`, `results`, `total_results`, `next_offset` |
| `nmap.jobs.cancel` | `domain`, `job_id` | İptal durumu dahil `job` |
| `nmap.jobs.resume` | `domain`, `job_id`, `expected_workspace_id` | Hiç başlanmamış hedefler için kuyruk durumu |

`key` aynı domain/plan isteğini tekrar güvenli yapar. İş özeti `id`,
`plan_id`, `domain`, `status`, hedef/başlangıç/sonuç/bekleyen sayıları,
iptal isteği ve hedef durum sayaçları taşır. `results` hedef başına port
durumu/servis/OS/NSE kanıtıdır; hedefler sayfalıdır, hedef içi ayrıntı
sınırları ve `truncated` açıkça korunur. Liste işlemlerinde sayfa boyu
kadar kayıt geldikçe `offset` artırılabilir; boş sayfa sonu gösterir.

İstek yolu Nmap'i başlatmaz. Güvenilen işletici ayrı süreçte çalıştırır:

```sh
./xti platform nmap-worker --root "$PWD/.xti-platform" --company firma-a \
  --domain example.com --job-id IS_KIMLIGI
./xti platform nmap-recover --root "$PWD/.xti-platform" --company firma-a \
  --domain example.com --job-id IS_KIMLIGI
```

SYN/UDP/OS için sistem yetkileri bu worker'ın işletim konusudur. Firma
seçimi, oturum/rol denetimi ve React/.NET bağlantısı tüketici ekiptedir.
Çalışan Nmap ortak çekirdek kilidini tutar; platform yedeği bu çalışma
sırasında alınamaz. Yeni yola restore edilen Nmap işleri eski plan ve
kanıt olarak okunur; tekrar çalıştırmak yeni açık iş kabulü gerektirir.
[Nmap kullanım ve sonuç sınırları](NMAP_MANAGED.md).

## Kalıcı iş ve worker

Önce `profiles.list` ile güncel profil sürümünü; `--describe` cevabının
`scope.workspace_id` alanından güncel veri alanı kimliğini alın. İş örneği:

```json
{"contract_version":1,"request_id":"gonderim-1","operation":"jobs.submit","parameters":{"idempotency_key":"firma-a-gunluk-20261116","profile_name":"haberler","profile_revision":1,"expected_workspace_id":"00000000-0000-0000-0000-000000000000"}}
```

Sıfırlı UUID yer tutucudur; gerçek `scope.workspace_id` ile değiştirin.
Bu alan firma seçmez; güvenilen başlatıcının seçtiği alanla eşit olmalıdır.
Yedekten yeni alana dönüşte eski alanı hedefleyen gecikmiş istekler böylece
yeni iş oluşturamaz. `request_id` cevap eşleştirmesi içindir; tekrar
güvenliği ayrı `idempotency_key` alanıdır.

Aynı firma + anahtar + profil/sürüm tekrarında eski iş döner. Aynı anahtar
başka seçimle kullanılırsa çatışma oluşur. Profilin tam tanımı, kaynak
sürümü ve seçilen izleme tanımları kabulde dondurulur; worker öncesi
değişmişlerse farklı işi sessizce çalıştırmaz. Eski anahtarlar silinmez;
firma başına en fazla 10.000 iş korunur. Bu sınır ölçülmüş hizmet kapasitesi
değildir; sınıra ulaşınca yeni kabul açık hatayla durur.

```sh
./xti platform worker --root "$PWD/.xti-platform" --company firma-a
./xti platform worker --root "$PWD/.xti-platform" --company firma-a --job-id IS_KIMLIGI
./xti platform recover --root "$PWD/.xti-platform" --company firma-a
```

Worker ön planda en fazla bir işi alır. Dağıtık daemon veya HTTP sunucusu
kurulmaz; sürekli çalıştırma politikasını platform işletimi belirler.
Aynı firmada iki worker aynı işi alamaz. İş oturum bağı ilk kaynak isteği
öncesi kalıcıdır. Kesilmiş iş otomatik yeniden denenmez; `recover` canlı
worker varken reddedilir. Sonuç yazımından önce kesintide kaynak makbuzları
çekirdek geçmişinde korunur; `collection_session_id` ile incelenebilir.
Başarılı kaynağı tekrar çağırmak yerine mevcut `collections show/resume`
yolu işletici tarafından açık incelemeyle kullanılabilir. Bu yeni yürütme,
eski platform işinin değişmez sonucunu geriye dönük değiştirmez.

## Birlikte yedek ve yeni alana dönüş

```sh
./xti platform backup --root "$PWD/.xti-platform" --company firma-a --output "$PWD/.xti-platform-backups/ilk"
./xti platform restore --root "$PWD/.xti-platform-restored" --company firma-a --source "$PWD/.xti-platform-backups/ilk"
```

Yedek üst klasörünü önceden özel izinlerle oluşturun. Yedek çekirdek
kanıtları, iş kuyruğunu ve bütünlük manifestini birlikte içerir; sır
dosyaları dahil değildir. Çalışan veya sonucu belirsiz `running` iş varsa
önce inceleme/kurtarma gerekir. Mevcut dosya/alan üzerine yazılmaz;
bozuk, eksik veya farklı firmaya ait yedek reddedilir. WAL kullanan
değiştirilmiş kurulum bu birlikte yedek akışında desteklenmez.

Geri yükleme aynı firma için yeni alan kimliği üretir. Yedekte bekleyen
işler, eski kurulumda yedek sonrasında çalışmış olabilecekleri için
`cancelled/restored_uncertain` olur; kimlik ve anahtarları korunur.
Tamamlanmış veya yarım işler tekrar çalıştırılmaz. Eski kurulumun
durdurulması ve yedek sonrası kayıtların uzlaştırılması işletim işidir;
yedekte olmayan son kayıtlar geri kazanılmış sayılmaz. Kişisel `backup`
yalnız çekirdek DB'yi kapsar; platform tesliminde bu birlikte yedek yolunu
kullanın. Firma alanları başka kimlikle yeniden etiketlenmez.

Kurulum veya geri yükleme cevabı kaybolursa önce `request --describe`
ile alanın tamamlanıp tamamlanmadığını kontrol edin. Yarım kurulum için
yerinde onarma/devam komutu yoktur; `recover` yalnız iş durumlarını düzeltir.
Etkilenen firmanın eski başlatıcısını ve workerlarını durdurun, kayıt bağı
okunabiliyorsa `disable` uygulayın ve eski dosyaları koruyun. İlk boş
kurulum için aynı firma kimliğiyle daha önce kullanılmamış ayrı kökte
`provision`; veri kurtarmak için doğrulanmış birlikte yedekten `restore`
kullanın. Başarılı doğrulamadan sonra güvenilen eşlemeyi ve alan kimliğini
güncelleyin. Kayıt listesini elle silmek/düzenlemek veya mevcut hedefin
üzerine yazmak desteklenen kurtarma yolu değildir.

## Dağıtım sınırı ve doğrulama

Platform JSON'undan firma/dosya/komut seçimi yapılamaz. .NET uygulaması
kullanıcı girdisini doğrudan `--root`, `--company`, `--data-dir` veya shell
metnine dönüştürmemeli; doğrulanmış firma eşlemesini kullanmalıdır.
Firma kökü/ebeveynleri güvenilir sahiplik ve izin gerektirir; symlink,
hardlink, iç içe kayıt kökü ve güvensiz paylaşım reddedilir. `disable`
yeni seçimleri kapatır; başlamış işlemi geriye dönük iptal etmez.

```sh
./xti platform disable --root "$PWD/.xti-platform" --company firma-a
```

Servis hesabına veya kayıt dosyalarına tam erişimi olan işleticiye karşı
bu katman güvenlik sınırı değildir. Rol/oturum, ağ kimlik doğrulaması,
API hız sınırı, sunucu hesapları ve gerçek .NET/PostgreSQL yerleşimi
tüketici ekibin işidir. Motorun firma sınırı kabulü ayrı test edilir;
bu belge platformun tamamının güvenlik onayı veya 7/24 hizmet taahhüdü değildir.

Kabul komutu `./scripts/python scripts/check-platform-acceptance.py --help`
ile görülebilir. Çevrimdışı geçici alanda farklı firmalar, gerçek alt
süreçler, worker kesintisi, tekrar isteği, süre/bellek/disk ölçümü sınanır.
[Karar](decisions/0152-company-scoped-platform-engine.md),
[ölçümlü kabul](PLATFORM_ACCEPTANCE.md), [güncel sonuçlar](STATUS.md),
[teslim yol haritası](roadmap/ENGINE_INTEGRATION_ROADMAP.md).
