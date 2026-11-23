# Kaynak güncelleme işleri

22 Kasım 2026 · 0.185.0 · çekirdek şema 94 · iş kuyruğu şeması 4.

Güncel kaynak işi modeli12, tek kaynaklı ve ağsız `darkweb-monitor` adımını
ekler. Profil kimliği/sürümü ile dondurulmuş kapsam SHA256 değeri kabulde ve
worker'da yeniden doğrulanır. Dış HTTP tavanı ve gerçek deneme sıfırdır;
XposedOrNot verified-domain çağrısı bu genel işin içine gizlenmez ve yalnız
açık `darkweb.credential.refresh` işleminde yapılır. Parola kontrolü de kaynak
işi değildir; yalnız açık, gizli terminal girişiyle çalışır. Tamamlanan çekirdek tur
makbuzu kuyruk kesintisinde yeniden kullanılır; belirsiz `running` tur
otomatik tekrarlanmaz. Eski modeller1–11 kendi saklı biçimleriyle okunur.
[Kullanım](DARKWEB_MONITORING.md#ortak-kuyrukla-düzenli-analiz).

Kaynak işi modeli11 `cti-analysis`; model10 `brand-protection`; model9
`content-monitor`; model8 `code-monitor` adımlarını eklemiştir. Aşağıdaki
tarihî açıklamalar bu eski makbuzların anlamını korur.


Kaynak işi modeli9 `content-monitor` ekler; eski1–8 kendi kayıtlarıyla
okunur. Firma/tedarikçi izlemesinin güncel kimliği, sürümü, domain veya
kapsam özeti ve bütçeleri plan/submit/worker aşamalarında doğrulanır.
Başarılı core makbuzu varsa retry kaynak çağrısını tekrarlamaz.
HTTP, Telegram mantıksal çağrısı ve IRC bağlantı penceresi ayrı ölçülür.
[Kullanım, bütçe ve kurtarma](CONTENT_MONITORING.md#düzenli-çalışma-ve-kuyruk).

İş modeli **8**, `code-monitor` ile kayıtlı kod/paste izlemesini
çalıştırır. `code_watch_id`, `code_watch_revision` ve isteğe bağlı
`code_force` aynı firma/domain kapsamında doğrulanır. Tek kaynaklı bu işin
varsayılan30/en fazla100 HTTP bütçesi vardır; diğer kaynakların mevcut
sınırları değişmez. Çekirdek makbuzu tamamlanıp iş kesilirse açık retry
eski sonucu bulur ve yeniden ağ isteği yapmaz. [Örnekler](CODE_EXPOSURE.md#ortak-iş-kuyruğu-ve-firma-json).

0.179.0 biten işleri etkin kapasiteden ayırır; özgün makbuz/sonuç/retry
bağı korunur. Güncel geçmiş, kapasite, audit ve yedekli kuyruk geçişi
[iş geçmişi rehberindedir](JOB_HISTORY.md). Aşağıdaki eski kaynak işi
sürümlerinin plan ve kanıt anlamları değişmez.

İş modeli **7**, `group-refresh` ve zorunlu `group_id` alanını
ekler (terminalde `--group`). Saklı grubun aynı firma/kök kapsamında yerel
kontrolüdür; dış istek yapmaz. Kaynak adımlarından sonra yürütülür.
Sonuç/bildirim birlikte saklanır; kesilen kuyruk ilerlemesi özgün grup
makbuzuyla toparlanır. Eski modeller1–6 okunur. Yeni bağımlılık yoktur.
[Grup işleri, monitor, bildirim ve arşiv](GROUP_OPERATIONS.md).

İş modeli 6, aynı firma/domain ve izleme sürümüne bağlı ücretsiz
`social-tracking` adımını ekler. Eski modeller 1–5 değişmeden okunur.
Toplam sosyal araç HTTP sayısı ölçülemediğinden plan ve kullanım toplamı
`null` olabilir; sosyal turun sayfa/süre sınırı ayrı korunur.
[Sosyal kuyruk örneği ve kesinti kuralları](SOCIAL_TRACKING.md#ortak-iş-kuyruğuyla-çalıştırma).

İş modeli 5, açıkça seçilmiş en fazla beş yayıncı HTML/PDF belgesini
ve ilişki bildirimi adımını ekler. Toplam altı yürütme adımı korunur.
Önceki modeller 1–4 kendi kanıtlarıyla okunur.
[Belge işleri, kesinti/tekrar ve bildirim kullanımı](PUBLISHER_JOB_DELIVERY.md).

İş modeli 4, `ripestat-whois` ve `report-capture` adımlarını, açık adım
sırasını ve hata sonrası devam/durdurma seçimini ekler. Önceki iş modeli
1/2/3 kendi makbuzlarıyla okunur. `reports` önceki metin çıkarımı adımıdır;
`report-capture` belge sürümü saklar. Yeni seçeneklerin örnekleri ve tekrar
kuralları [kanıt akışları belgesindedir](EVIDENCE_WORKFLOWS.md).

IP/URL/hash kaynaklarını, seçilmiş MISP listelerini, yayıncı akışlarını ve
saklı rapor çıkarımını bir işe bağlayabilirsin.
İş sıraya girer, açıkça çalıştırılır, her adımın sonucu saklanır. İstersen
son adımda inceleme kaydı alınır ve aynı kapsamın önceki incelemesiyle
karşılaştırılır. Yeni ücretli API, anahtar veya paket gerekmez.

## Terminalden kullanım

Normal `./setup` ile çekirdek alan hazır olmalı. Eski çekirdek için
`./xti migrate` kullan. Yerel iş kuyruğu ilk kez kurulacaksa
`./xti source-jobs init`, eski sürüm 1/2 kuyruğu varsa
`./xti source-jobs migrate` çalıştır. `init` var olan dosyaya yazmaz.
Yükseltme önce benzersiz, doğrulanmış `.vESKISURUM-UUID.backup` dosyası oluşturur;
eski profil işleri, anahtarlar ve olay içerikleri korunur. Çalışan veya
kurtarma bekleyen iş varken geçiş reddedilir. Şema 3 zaten varsa değişmez.
Eski iş/event byte'ları ve rowid değerleri korunur. Altı adım ve son anda
iptal dahil en fazla 16 kuyruk olayı yeni şemada doğrulanır.

```sh
./xti source-jobs plan https://example.com/ --type url --source urlscan --source misp --list rfc6761 --record-review
./xti source-jobs submit https://example.com/ --type url --source urlscan --source misp --list rfc6761 --record-review --idempotency-key example-review-1
./xti source-jobs list
./xti source-jobs worker --job-id IS_KIMLIGI
./xti source-jobs status IS_KIMLIGI
./xti source-jobs result IS_KIMLIGI
```

`IS_KIMLIGI`, submit çıktısındaki kimliktir. Plan, kabul, durum, sonuç ve
listeleme internet çağırmaz. Worker en fazla bir işi yürütür; kimlik
verilmezse ortak kuyruğun sıradaki işini alır. Sürekli hizmet otomatik
kurulmaz. Terminalde her adımın özgün kanıtını ve inceleme değişimini açan
komut gösterilir. `--json` kayıtlı ilerleme ve sonuç başvurularını verir.

Hash için `--type sha256 --source circl` (MD5/SHA-1 da desteklenir),
domain/IP için `--source misp --list LISTE` seçilir. İncelenmiş MISP
listeleri: `cloudflare`, `rfc1918`, `rfc3849`, `rfc6761`.
Uyumsuz sağlayıcı ve bilinmeyen kaynak reddedilir.

## Sınırlar ve sonuçların anlamı

| Seçim | Davranış |
|---|---|
| Kaynak | En fazla beş: türle uyumlu CIRCL/urlscan/RIPEstat/RIPEstat WHOIS, MISP, `news:cisa`, `news:ncsc`, `news:cert-fr`, `reports`, `report-capture` seçenekleri |
| `--max-requests` | Normal kaynak işinde 1–7; publisher içeren işte 1–32. Varsayılan 7; seçilmiş her belge için dört deneme ayrılır |
| MISP istek hesabı | Commit + gerekirse koşul belgesi + seçilen her liste için bir istek |
| RIPEstat / yayıncı | IP başına bir GET / yayıncı başına bir GET; haber isteğine firma domaini eklenmez |
| `reports` | Sıfır dış istek; en yeni 20 saklı haberden aday çıkarımı, varsa `has_more` ve kısmi kapsam |
| `report-capture` | Sıfır dış istek; `--capture-source news\|mentions`, `--capture-limit` 1–20; sürümlü belge makbuzu |
| `--step` | Her seçilmiş kaynağı tam bir kez içeren adım sırası; haber yenilemesi ilgili rapor yakalamasından önce |
| `--failure-policy` | `continue` (varsayılan) veya `stop`; durdurmada sonraki adımlar açık gerekçeyle atlanır |
| `--max-seconds` | 1–600, varsayılan 180; adımlar arasında yeni işe başlama sınırı |
| `--record-review` | Varsayılan kapalı; kaynakların ardından aynı kapsamın incelemesini saklar |
| Araştırma | `--max-hops`, `--node-limit`, `--edge-limit`, `--stale-after-hours`; mevcut araştırma sınırları |
| Listeleme | `--offset`, `--limit` (1–100); en yeni iş başta |
| Kuyruk | Aynı alanda profil/kaynak türlerinde en fazla 10.000 bekleyen/çalışan iş; biten geçmiş korunur, otomatik silme yok |
| Tekrar zinciri | En fazla 32; eski iş ve tamamlanmış kaynak makbuzları korunur |

Süre sınırı devam eden HTTP çağrısını zorla kesmez; isteğin kendi zaman
aşımı ve boyut sınırı korunur. MISP seçili listeleri tek commit altında
bir adımda indirir; iptal/süre denetimi grubun öncesi ve sonrasındadır.
Toplam süre bu nedenle seçilen adımlar arası bütçeyi aşabilir. Firmalar
arası ortak sağlayıcı kotası backendin tek merkezde yöneteceği entegrasyon
işidir (NOTES N-007). Motor firma paketi veya abonelik kararı vermez.

`complete` seçilen işlemler tamamlandı demektir; tehdit bulunduğu veya
bütün arşivin tarandığı anlamına gelmez. urlscan ilk 20 sonuçla sınırlıdır;
`has_more` makbuzda korunur. `no_match` başarılı boş yanıttır. Başarısız
kaynak adımı son hata makbuzunu taşır; eski geçerli veri silinmez. Bir
kaynak tamamlanıp diğeri başarısızsa iş `partial` olur. İnceleme kaydının
başarısı bütün kaynakları başarısız bir işi başarılıya çevirmez. Ayrıntılı
hata özgün `enrich run-show` / `warninglists run-show` çıktısındadır.

urlscan'e URL, CIRCL'e hash, RIPEstat'a IP gönderilir; MISP'e araştırılan müşteri değeri
gönderilmez. URL sorgusu yeni tarama başlatmaz. İnceleme kaydı insan
kararını/alarmı değiştirmez. Kaynak atıfları ve ticari kullanım şartları
[NOTES](../NOTES.md) içindedir; kuyruk eklenmesi yeni veri hakkı sağlamaz.

## İşin kullanım raporu

`source-jobs status/result/list` ve aynı firma platformu işlemleri
`execution` alanını verir. Ayrıca worker, submit, cancel ve retry'nin
döndürdüğü kaynak işi aynı görünümü taşır. Yeni işlem eklenmez.

| Alan | Anlamı |
|---|---|
| `limits.max_requests` | Ölçümlü kaynak adımları için verilen üst sınır; sosyal araç trafiği dahil değildir |
| `limits.max_seconds` | Adımlar arasında uygulanan süre sınırı |
| `requests.attempts` | Bu işteki HTTP açma denemesi; kesin sayı yoksa `null` |
| `requests.measurement_complete` | Kaydedilmiş iş durumunda bütün başlamış kaynak adımlarının kullanımı biliniyor mu? İşin bittiğini göstermez |
| `requests.recorded` | Kaydedilmiş `attempts`, `responses`, `transport_errors`, `rate_limited`, `budget_rejections` sayaçları |
| `requests.possible_unrecorded_attempts_maximum` | Ölçülemeyen başlamış adımlardaki ek denemelerin üst sınırı; sosyal araç için bilinmediğinde `null`; harcanmış sayı değildir |
| `requests.by_step` | Her adım için ölçüm durumu, sayı ve varsa yeniden kullanılan iş kimliği |
| `timing.queue_wait_seconds` | İşin kabulünden worker tarafından alınmasına kadar kayıtlı süre |
| `timing.execution_seconds` | Başlangıç/bitiş UTC kayıtları arası süre; iş bitmediyse `null` |
| `stop_reasons` | Tamamlanma, iptal, süre/istek sınırı, kaynak hatası, HTTP 429 veya belirsiz kesinti; birlikte bulunabilir |

Örneğin CIRCL ve iki MISP listesi için plan en fazla **5** istek ayırır.
MISP'in incelenmiş commit'i değişmemişse koşul belgesi tekrar indirilmez;
gerçek toplam **4** olabilir. Commit sorgusu başarısızsa iki listenin ayrı
hata kaydı oluşması iki ek HTTP isteği yapılmış olduğu anlamına gelmez.

Sayaç HTTP açma çağrısından hemen önce ilerler. DNS/bağlantı hatası da bir
denemedir; istek sağlayıcıya ulaşmış veya ücretlendirilmiş sayılmaz.
Yanıt alındıktan sonra içerik okuma/ayrıştırma hatası olması, yanıtın
alınmış olduğu bilgisini değiştirmez. `responses` başarılı içerik sayısı
değildir; 404 ve 429 gibi yanıtları da kapsar. Sırlar, başlıklar ve
yanıt gövdeleri kullanım kaydına kopyalanmaz. Ortak sağlayıcı kotası ve
ticari faturalama bu sayaçtan otomatik türetilmez.

Ölçümlü kaynak adımlarının önceden hesaplanan istek tavanı HTTP açılmadan uygulanır;
adımların tavanları planın toplam bütçesini aşamaz. Yeni sayaç kaynakların
mevcut bekleme ve zaman aşımı kurallarını değiştirmez. Süre ölçümü UTC
kayıt farkıdır; CPU süresi veya kesintide gerçek çalışma süresi değildir.

Kullanım adım tamamlandığında kanıt başvurusuyla birlikte saklanır.
Çalışan/kesilen adımın henüz makbuzu yoksa kesin kullanım bilinmez. Örneğin
bir adımda **1** deneme kaydedilip sonraki MISP adımında süreç kesilirse
`attempts=null`, `recorded.attempts=1` ve ölçülemeyen MISP adımının üst
sınırı döner. Sayaçları sıfırlayarak bütçeyi geri verme kararı alınmamalı.
Eski işlerin ölçülmemiş kullanımı `legacy_unmeasured` olarak görünür.
Tekrar kullanılan başarılı adımın **bu işteki** tüketimi sıfırdır; eski
işin tüketimi kendi kaydında kalır. İlk iş ve tekrarları ayrı iş
kimlikleriyle değerlendirilir; bu görünüm zincirin toplamı değildir.

### Sosyal adımın ölçümü

`social-tracking` varsa plan `maximum_external_requests=null` döndürür.
`maximum_metered_source_requests` yalnız diğer kaynakların hesaplanabilir
tavanıdır; `request_limit_scope=metered_source_steps_excludes_social_collection`
plan ve execution limits içinde bu ayrımı bildirir. Plan okumasında ayrıca
`social_watch` altında dondurulan izleme sürümü, kapsam ve aralık görünür.
Makbuzdaki izleme kimliği/sürümü ve tur hash'i özgün core kanıtına doğrulanır.

Sosyal makbuzun `usage.version=2`, `unit=social_profile_collection` alanları
`attempted`, `page_http_requests`, `tool_requests`, `receipt_reused` içerir.
Kaynak çalıştıysa `tool_requests=null`; sayfa HTTP denemeleri özgün rapordan
alınır. Execution özetinde `recorded_social_page_http_requests` ayrı sayılır,
toplam `attempts=null` ve `measurement_complete=false` olur. Başlamamış
veya gerçekten ağsız tekrarın bu işteki tüketimi sıfırdır. Sosyal olmayan
makbuz usage v1 ve önceki sayaç anlamları değişmez.

Sosyal guard (`not_found`, `scope_mismatch`, `revision_changed`, `paused`,
`not_due`, `busy`) yeni ağ çağrısı olmadan `source_status=blocked` makbuzu
bırakır; adım `failed` olur. Bütün işi başarılı göstermez. Ayrıntı
`receipt.reason` içindedir. İş geçmişindeki karar sonraki watch değişimiyle
yeniden hesaplanmaz. Kaynak sonucu kısmi ise adım/iş `partial` kalabilir.

### Sürüm uyumu

Yeni kabul edilen `sources.refresh` işlerindeki yürütme/sonuç sürümü 6'dır;
platform zarfı v1 ve kuyruk şeması3 korunur. Çekirdek84 geçişi `./xti migrate`
ile açıkça/yedekli yapılır. Eski v1–v5 işler kendi biçimleriyle
çalışır/okunur; saklı JSON/hash'ler yeniden yazılmaz. Aynı tekrar anahtarı
eski işi döndürür. Eski başarısız işin açık retry'si yeni v6 iş olur.
İstek niyeti aynı olduğundan kanonik istek sürümü 1 kalır;
yürütme sürümü payload/result içinde ayrıca saklanır.

0.173.0 ve önceki kod yeni v6 işleri okuyamaz. Kod yükseltmeden önce birlikte firma
yedeği alınmalı; kod geri dönüşünde yükseltme öncesi yedek yeni alana
dönülmelidir. Şemanın aynı olması eski kodun yeni kayıt biçimini
desteklediği anlamına gelmez.

Yeni makbuzlar `news_run` ile özgün yayıncı çalışma kimliğini,
`report_extractions` ile aday kimliği ve özgün önerinin hash'ini tutar.
Sonradan insan kararı verilmesi rapor kaynağı makbuzunu değiştirmez.
Aynı içerikle yenilenen haber yeni rapor adayı oluşturmaz. [Komut örnekleri](INVESTIGATION.md#kaynak-işleri-ve-platform-sözleşmesi).

## İptal, kesinti ve tekrar

```sh
./xti source-jobs cancel IS_KIMLIGI
./xti source-jobs recover
./xti source-jobs retry IS_KIMLIGI --idempotency-key example-retry-1
```

Sıradaki iş hemen iptal edilir. Çalışan kaynak işinde iptal isteği
kaydedilir; devam eden isteğin sonucu saklanır, sonraki adımlar atlanır.
Eski profil işleri yalnız başlamadan iptal edilebilir.

Kesintide dış istek gönderilmiş veya kaynak kaydı yazılmış olabilir.
`recover` çalışan kaydı `interrupted` yapar; isteği tekrarlamaz. Bu işin
yeniden gönderilmesi ayrıca `--allow-uncertain` gerektirir. Otomatik
devralma veya zaman aşımıyla yeniden gönderme yoktur.

`retry` yeni iş/anahtar üretir. Tamamlanmış kaynak makbuzlarını doğrular ve
yeniden sorgulamaz. Diğer kaynak adımlarını tekrar eder. Kısmi MISP grubu
tamamen tekrar alınır; eski başarılı makbuzlar silinmez. İnceleme seçilmişse
yeni sonuçlardan tekrar kaydedilir. Tamamlanmış iş retry edilemez; yeni
güncel sorgu için yeni anahtarla submit kullan. Aynı anahtar/plan mevcut
işi döndürür; farklı plan reddedilir. Profil/kaynak işleri anahtar alanını
paylaşır. İş ve kanıt hash'leri yerel bütünlük denetimidir, imza değildir.

## Firma platformu

Yeni `platform provision` şema 4 kuyruğu oluşturur. Mevcut firma için:

```sh
./xti platform jobs-migrate --root "$PWD/.xti-platform" --company firma-a
```

Gerekliyse çekirdek geçişi ayrıca firma alanında yapılır. İşler mevcut
`platform worker/recover/backup/restore` komutlarını kullanır. Firma
güvenilen başlatıcı tarafından seçilir; JSON keyfî dosya/komut/HTTP adresi
veya farklı firma seçemez.

| İşlem | Parametreler |
|---|---|
| `sources.plan` | `indicator_type`, `value`, `sources`; isteğe bağlı `warninglist_ids`, `record_review`, bütçe ve araştırma kapsamı. `social-tracking` için `social_watch_id`, `social_watch_revision` zorunlu; `social_force` isteğe bağlı boolean |
| `sources.jobs.submit` | Aynı plan + `plan_sha256`, `idempotency_key`, `expected_workspace_id` |
| `sources.jobs.list` | İsteğe bağlı `offset`, `limit` |
| `sources.jobs.status` / `sources.jobs.result` | `job_id` |
| `sources.jobs.cancel` | `job_id`, `expected_workspace_id` |
| `sources.jobs.retry` | `job_id`, `idempotency_key`, `expected_workspace_id`; isteğe bağlı boolean `allow_uncertain` |

Önce platform request stdin'ine:

```json
{"contract_version":1,"request_id":"plan-1","operation":"sources.plan","parameters":{"indicator_type":"url","value":"https://example.com/","sources":["urlscan"],"record_review":true}}
```

Yanıttaki `data.plan` alanlarını, `data.plan_sha256` değerini ve güncel
`scope.workspace_id` bilgisini submit parametrelerine aktar; yeni
`idempotency_key` seç. Yanıt `data.job_id`, `status`, `steps`,
`completed_steps`, `total_steps`, `cancel_requested` içerir. Result işlemi
`data.job` ve `data.result` döndürür. Sonuç plan özeti ve özgün kanıt
kimlikleridir; sağlayıcı yanıtları kuyrukta ikinci kez kopyalanmaz.

Platform zarfında `status=complete` / çıkış 0 protokolün tamamlanmasıdır;
kaynak başarısı için `data.status` veya `data.result.status` okunmalı.
Yerel worker kısmi/başarısız sonuçta `ok=false`, çıkış 3 verir. Durum/sonuç
okuması normalde 0'dır. Geçersiz platform seçenekleri `invalid_parameters`
/ 2; bulunmayan kaynak işi `not_found` / 3. `scope_mismatch`, `plan_changed`,
`idempotency_conflict`, `migration_required`, `invalid_job_state`,
`uncertain_outcome`, `busy`, `storage_error` çıkış 1'dir.

Salt okunur engine bu yazma işlemlerini kabul etmez. Mevcut araştırma ve
kaynak okumaları değişmez. .NET/HTTP bağlantısı tüketici ekibin işidir.

## Yedek ve geri dönüş

Firma `platform backup` çekirdek kanıtlarıyla kuyruğu birlikte yedekler.
Restore özgün sonuçları korur, yeni workspace kimliği üretir, yedekteki
sırada işleri iptal eder; eski ortamda gönderilmiş olabilecek iş başlamaz.

Kişisel `backup` yalnız çekirdeğin mevcut yedeğidir, sidecar kuyruğun
birleşik yedeği değildir. İşletimde firma backup akışını kullan. Kuyruk
geçişinin `.backup` dosyası da bütün firma yedeği değildir. Şema 2 eski
uygulamayla açılmaz. Tam kod/veri geri dönüşü için yükseltme öncesi
birlikte alınmış firma yedeğini yeni alana geri yükle; çalışan alanın
üzerine dosya kopyalama.

[Mimari karar](decisions/0161-source-jobs-in-common-queue.md).

## P03 — kaynak iş modeli10

`brand-protection` tek kaynaklı iş; `protection_watch_id`,
`protection_watch_revision`, `protection_identity_revision`, isteğe bağlı
`protection_force` kullanır. Kapsam domain veya marka kimliği SHA256'dır.
İzleme ve kimlik kabul/çalıştırmada yeniden doğrulanır. `max_requests`
en fazla200; izleme bütçesinden küçük olamaz. Maigret/Sherlock içindeki
bütün trafik ölçülmez; bu durumda toplam sayı `null` kalır. Core makbuzu
commit sonrası iş kesintisinde tekrar kullanılır. Kaynak modeli1–9
okunmaya devam eder; kuyruk şeması4 ve dış JSONv1 değişmez.
`brand protection recover` belirsiz core çalışmayı açıkça kapatır;
kuyruk yeniden çalıştırması mevcut açık retry yoludur. [P03](BRAND_PROTECTION.md).

## P04 — kaynak iş modeli11

`cti-analysis` yalnız `analysis_profile_id`, `analysis_profile_revision`
ve isteğe bağlı `analysis_force` kullanır. İşin `value` alanı profil,
kuruluş ve sürümlü tanımın SHA256 kapsamıdır; `indicator_type=sha256`
olmalıdır. Başka kaynakla aynı plana eklenemez. Plan ve submit ağsızdır;
worker saklı CTI/IOC ve yerel ATT&CK snapshot'ını dondurur, dış HTTP
göndermez. Makbuz tur kimliğini, profil/sürümünü, rapor hash'ini ve tekrar
durumunu taşır. Core commit sonrası kuyruk kesilirse özgün tur doğrulanıp
yeniden kullanılır. [P04](CTI_ANALYSIS.md).

## P05 — kaynak iş modeli12

`darkweb-monitor` yalnız `darkweb_profile_id`, `darkweb_profile_revision`
ve isteğe bağlı `darkweb_force` kullanır. İşin `value` alanı profil,
kuruluş ve sürümlü tanımın SHA256 kapsamıdır; `indicator_type=sha256`
olmalıdır. Başka kaynakla aynı plana eklenemez. Plan ve submit ağsızdır;
worker saklı ransomware iddiaları ve daha önce maskelenmiş credential kanıtını
tek SQLite kesitinde dondurur. XposedOrNot canlı domain veya parola isteği
çalıştırmaz. Makbuz tur kimliğini, profil/sürümünü, rapor hash'ini ve tekrar
durumunu taşır. Core commit sonrası kuyruk kesilirse özgün tur doğrulanıp
yeniden kullanılır. [P05](DARKWEB_MONITORING.md#ortak-kuyrukla-düzenli-analiz).
