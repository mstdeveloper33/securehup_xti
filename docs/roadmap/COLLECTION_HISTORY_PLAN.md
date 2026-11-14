# Kalıcı toplama geçmişi ve kontrollü devam — Aşama 2

**Durum: PLANLANDI — HENÜZ UYGULANMADI.**

**Tarih: 14 Kasım 2026.** Tasarım, mevcut `CollectionService`,
`CollectionWatchService` ve hazırlanan şema 55 profil sözleşmelerine dayanır.
Hedef geçiş **55 → 56**; araya başka şema değişikliği girerse numara yeniden
seçilir. Bu belge bir uygulama veya test tamamlama beyanı değildir.

## Kullanıcı davranışı

Her toplama bir oturum kimliği alır. Geçmişte hangi seçimle çalışıldığı,
hangi adımın tamamlandığı, gerçek kaynak çalışma kimlikleri ve hatalar görülür.
Kullanıcı açıkça devam istediğinde yalnız eksik işler yürütülür. Tamamlanan
sosyal veya ransomware izlemeleri tekrar çalıştırılmaz. Genel bir iş akışı
motoru, daemon veya kendiliğinden tekrar deneme eklenmez.

Devam yeni bir yürütme oturumu oluşturur ve önceki oturuma bağlanır. Eski
başarısız/kısmi/kesilmiş oturum başarı olarak yeniden yazılmaz. Birleşik görünüm
hangi sonucun önceki yürütmeden korunduğunu ve hangi kaynağın ne zaman yeniden
alındığını açıkça gösterir. Bu görünüm tek anda alınmış ortak snapshot değildir.

Önerilen CLI: `collect history`, `collect show ID`, `collect resume ID --plan`
ve açık `collect resume ID`. Mevcut `collect DOMAIN` ile ayrıştırıcı uyumu
uygulama sırasında korunmalı; komut adları henüz kesinleşmiş arayüz değildir.
Önizleme ve geçmiş okuma ağsız/yazmasız kalır.

## Dondurulmuş seçim

İlk oturumda kanonik `CollectionProfileDefinition` bütünü saklanır: domain,
temel görevler, bütün açık izleme kimlikleri, typos, güncellik eşiği, bulgu sınırı
ve izleme görünüm sınırı. Mevcut `CollectionPlan` son iki analiz seçeneğini
taşımadığı için yalnız bu nesneyi JSON'a çevirmek yeterli değildir.

Ayrıca çözümlenmiş plan saklanır: kararlı görev sırası, kaynak, her izlemenin
kimliği/tanımı/platformları ve tanım özeti; ilgili eşleştirici/çalıştırıcı sözleşme
sürümü. Canonical JSON ve SHA-256 birbirini doğrular. Görünüm sınırı saklanan
gerçek kaynak sonuçlarını kesmez. Profil üzerinden başlatıldıysa kaynak profil
revizyonu `collection_profile_events.id` ile bağlanır; ad/değer snapshot'ı da
planın içindedir. Doğrudan collect için aynı seçim modeli kullanılır.

Devam güncel profil varsayılanlarını sessizce benimsemez. Kayıtlı seçim aynen
korunur. Kaynak profil geri çekilmiş/değişmişse veya eksik işin izleme tanımı,
etkinliği, araç ya da eşleştirme sözleşmesi değişmişse ağ öncesi ret verilir;
kullanıcı güncel planla yeni çalışma başlatır. Tamamlanan kanıtın tarihsel
görünümü sonradan değişmiş izleme adına/sorgusuna göre yeniden yorumlanmaz.

## Pratik adım ve tekrar sınırı

| Birim | Kalıcı tamamlanma kanıtı | Devam davranışı |
| --- | --- | --- |
| Marka araması | Tam scan attempt; job bağlantısı da korunur | Complete değilse ayrı deneme; kaynak içindeki yarım sorgular baştan çalışabilir |
| Pasif alt alan keşfi | Discovery run | Partial/failed/kesilmiş iş yeniden alınır |
| IOC yenilemesi | Kaynağa ait feed run | Yalnız eksik kaynak yeniden alınır |
| Tek sosyal izleme | Tam username watch run | Complete üye atlanır; failed/kesilmiş üye yeniden çalışır |
| Ransomware kaynak yenilemesi | Kaynağa ait claim run | Eksik izleme varsa yeni yürütmede bir kez taze yenileme gerekir |
| Tek ransomware izlemesi | Watch run + kesin source run bağı | Yalnız eksik üye, o yürütmenin başarılı yenileme kimliğine bağlı çalışır |

Ransomware grubu tek tamamlanma kutusu olamaz. Bugün grup kaynak yenilemesi ve
bütün üyeler bittikten sonra tek `CollectionStep` döndürüyor. A üyesi commit
olduktan sonra B'de kesinti olursa yalnız grup sonunu kaydetmek A'nın başarısını
kaybeder. Refresh ve her üye ayrı alt adım olmalı. Alt adımlar yürütme planında
en fazla 6 temel iş + 50 izleme + 2 refresh, yani 58 kaynak birimidir.

Örnek: ilk yürütmede ThreatCluster yenilemesi ve A tamamlandı, B yarım kaldı.
Devam yalnız **yeni refresh → B** çalıştırır; A'nın eski run kimliği korunur.
Yeni refresh başarısızsa B atlanır ve eski snapshot'a dönülmez. Yeni refresh,
tamamlanan A'yı tekrar etme gerekçesi değildir; eksik B için güncel önkoşuldur.
B'nin `expected_source_run_id` değeri yeni refresh kimliği olmalı ve mevcut
repository'nin transaction içindeki son başarılı snapshot denetimi korunmalı.

Yalnız son yerel analiz üretimi eksikse kaynaklara tekrar gidilmez. Analiz
güncel yerel kanıttan yeniden üretilir ve zamanı gösterilir. Geçmiş komutu ise
kendiliğinden `analyze` çalıştırıp bugünkü görünümü eski sonuç diye sunmaz.

## Şema 56: üç tablo

Tablo adları ve aşağıdaki alanlar önerilen kesin başlangıç sözleşmesidir.
UUID, UTC zaman, kanonik JSON ve küçük sabit enum doğrulamaları hem adapter
hem şema denetiminde bulunur. Yabancı anahtarlarda `ON DELETE RESTRICT` kullanılır.

### `collection_sessions`

- `sequence INTEGER PRIMARY KEY AUTOINCREMENT`, `id TEXT NOT NULL UNIQUE`.
- `root_id TEXT NOT NULL` aynı tabloya FK; ilk kayıtta kendi kimliğidir.
  `parent_id TEXT NULL UNIQUE` aynı tabloya FK. Bir oturumdan iki bağımsız
  devam dalı açılamaz; yalnız zincirin son oturumundan devam edilir.
- `generation INTEGER NOT NULL` (ilk 1), `UNIQUE(root_id, generation)`.
- `profile_event_id TEXT NULL` → `collection_profile_events(id)`.
- `definition_json TEXT NOT NULL`, `definition_sha256 TEXT NOT NULL`,
  `plan_json TEXT NOT NULL`, `plan_sha256 TEXT NOT NULL`,
  `executor_contract_version INTEGER NOT NULL`.
- `status TEXT NOT NULL`: running/complete/partial/failed/interrupted.
  `started_at TEXT NOT NULL`, `finished_at TEXT NULL`,
  `stop_reason TEXT NULL` (sabit kod; serbest exception metni değil).
- `analysis_status TEXT NOT NULL`: pending/complete/failed;
  `analysis_recorded_at TEXT NULL`. Tarihsel kaynak raporu için analiz
  çıktısını sınırsız JSON olarak çoğaltmak zorunlu değildir.

Zincir boyunca plan/definition özetleri ve kaynak profil revizyonu değişmez;
ebeveyn daha küçük sequence/generation değerine sahip olmalıdır. Bütün
değişmez alanlar yeniden doğrulanır. Sıra UTC saate göre belirlenmez.

### `collection_session_steps`

- `id TEXT PRIMARY KEY`, `session_id TEXT NOT NULL` → sessions(id),
  `ordinal INTEGER NOT NULL`, `step_key TEXT NOT NULL`;
  `UNIQUE(session_id, ordinal)` ve `UNIQUE(session_id, step_key)`.
- `kind TEXT NOT NULL`: scan/discovery/ioc/username_watch/ransomware_refresh/
  ransomware_watch. `source TEXT NOT NULL` sabit kaynak kümesinden seçilir.
- `watch_id TEXT NULL`, `target_sha256 TEXT NOT NULL` (dondurulmuş plan birimi).
  İzleme kimliği kaynak türüne göre gerçek watch tablosuyla adapter'da doğrulanır;
  genel bir metin kimliğinin tek başına FK güvencesi verdiği iddia edilmez.
- `depends_on_step_id TEXT NULL` → aynı tablo: ransomware üyesinin **aynı
  yürütmedeki** refresh adımı. Kaynak ve görev türü eşleşmeli.
- `scan_job_id TEXT NULL` → `scan_jobs(id)`; yalnız scan için kullanılır.
- `status TEXT NOT NULL`: pending/running/complete/partial/failed/interrupted/
  skipped. `started_at TEXT NULL`, `finished_at TEXT NULL`, `error_code TEXT NULL`.

Devam oturumuna yalnız eksik birimler ve gerekli yeni refresh adımları eklenir.
Önceki complete birimler kopyalanmaz; kök plan ve atalarındaki receipt'lerden
çözülür. Tamamlanan üye için yeni step oluşturmak repository tarafından reddedilir.
Terminal state, kimlikler ve bağlar değiştirilemez; pending/running geçişleri
koşullu güncelleme ile yapılır.

### `collection_step_receipts`

- `step_id TEXT PRIMARY KEY` → steps(id), `recorded_at TEXT NOT NULL`,
  `result_status TEXT NOT NULL` (complete/partial/failed/interrupted),
  `summary_json TEXT NOT NULL`, `summary_sha256 TEXT NOT NULL`.
- Aşağıdaki nullable UNIQUE FK alanlarından **tam biri** doludur:
  `scan_attempt_id` → scan_attempts(id),
  `discovery_run_id` → surface_discovery_runs(id),
  `feed_run_id` → cti_feed_runs(id),
  `username_run_id` → brand_username_watch_runs(id),
  `threatcluster_source_run_id` → ransomware_claim_runs(id),
  `ransomlook_source_run_id` → ransomlook_claim_runs(id),
  `threatcluster_watch_run_id` → ransomware_watch_runs(id),
  `ransomlook_watch_run_id` → ransomlook_watch_runs(id).

Receipt eklemelidir; başka run'a çevrilemez. Özet yalnız sürümlü, sınırlı
sayaçlar/sonuç alanlarıdır; ham belge veya traceback değildir. Kaynak türü,
domain/watch, tamamlanma durumu, definition ve ransomware source run bağı gerçek
kayda karşı doğrulanır. Kaynak run yoksa uydurma receipt yazılmaz; örneğin network
öncesi kesinti yalnız interrupted step olarak kalabilir.

İndeksler: sessions(status, sequence), sessions(root_id, generation),
steps(session_id, ordinal), steps(scan_job_id). UNIQUE/FK indeksleri ayrıca
korunur. Listeleme limitli ve sequence cursor'lıdır; devam zinciri için açık
üst sınır konur, taşma sessizce kesilmez.

## Atomik kanıt: gerekli tamamlanma kapısı

Kaynak repository kendi commit'ini yaptıktan sonra üst serviste `record_step`
çağırmak tek başına güvenilir değildir. İki commit arasındaki SIGKILL'de kaynak
başarılıdır ama üst kayıt boş kalır. Zaman aralığına veya en son run'a bakarak
eşleştirme yapılmaz; başka bir işlemin kanıtı sahiplenilemez.

Öneri: yeni domain `CollectionOperationToken` nesnesi session/step kimliğini,
plan hedef özetini ve gerekiyorsa refresh bağımlılığını taşır. İlgili mevcut
servis/port metoduna isteğe bağlı keyword olarak açıkça geçirilir. SQLite
adaptörü kendi mevcut kaynak sonuç transaction'ında küçük
`finish_collection_step(connection, token, reference, summary)` yardımcısını
çağırır. Yardımcı receipt'i ekler ve step'i aynı transaction'da tamamlar.
Kaynak yazımı veya receipt başarısızsa ikisi de geri alınır. Token yoksa mevcut
bağımsız komut davranışı korunur. Domain/uygulama katmanına SQLite bağlantısı
veya transaction callback'i sızdırılmaz; yardımcı adaptör katmanında kalır.

Bu bağlama scan finish, discovery record, feed apply/failure, sosyal
record_preview/failure, iki ransomware refresh apply/failure ve iki watch run
sonucunda gerekir. Kaynak portları generic workflow motoruna dönüştürülmez.

Scan için enqueue de job kimliğini aynı transaction'da step'e bağlamalıdır.
Collection'a ait queued/running job bağımsız `jobs run` veya genel kuyruk işçisi
tarafından tekrar sahiplenilememeli; mevcut monitor sahipliği yaklaşımı
incelenerek küçük collection sahibi kontrolü eklenir. Kesilmiş eski işi yeni
oturuma sessizce devretmek yerine yeni deneme/iş bağı açıkça kaydedilir.

Scan'ın kendi bulgu/gözlem yazımları attempt finish'ten önce gerçekleşebilir.
Bu yüzden garanti tüm dış çağrıların exactly-once olması değildir. Complete
receipt'i olmayan yarım temel iş yeniden işlenebilir; mevcut tekilleştirme ve
insan kararlarını koruma kuralları sürer. **Complete izleme üyesi tekrar
çalıştırılmaz** garantisi ise atomik watch run + receipt ile sağlanır.

Atomik receipt bağları yapılmadan yalnız oturum sonu callback ile history
sunulabilir; fakat bu, güvenilir resume tamamlandı olarak yayımlanamaz.

## Küçük domain/port ve yürütme düzeni

Domain modelleri: `CollectionSession`, `CollectionSessionStep`,
`CollectionStepReceipt`, `CollectionOperationToken`, `CollectionResumePlan`,
limitli `CollectionSessionDetails/Page`. Sabit türler, kanonik plan özeti ve
durum/bağımlılık kuralları storage'dan bağımsızdır.

`CollectionHistoryRepository` sözleşmesi: `begin(plan, origin, parent_id)`,
`start_step(session_id, step_id) -> token`,
`stop_step_without_result(token, status, error_code)`,
`finish_session(id, analysis_status, stop_reason)`,
`recover_interrupted(reason)`, `get(id)`, `list(limit, before)`.
`begin`, yeni zincir ve devam planını tek transaction'da doğrular/oluşturur.
Kaynak receipt yazımı bu repository'ye ikinci bağlantılı callback olarak değil,
yukarıdaki adapter transaction yordamıyla bağlanır.

1. Bütün seçimi ve depoları mevcut ağsız preflight ile doğrula.
2. Mevcut ortak `jobs.lock` kilidini tek kez al; profil/izleme değişmezliğini
   tekrar doğrula. HTTP boyunca SQLite write transaction açık tutma.
3. Kilit sahibiyken eski running oturumları denetle. Atomik receipt'i olmayan
   çalışan step'i interrupted yap; receipt'i olan sonucu kaybetme. Salt okunur
   history çağrısı recovery yapmaz. Sonucu bilinmeyeni complete sayma.
4. Oturum ve alt adımları kaydet; her kaynak çağrısından önce ilgili step'i
   running yap. Bağımsız normal kaynak hatalarında sonraki kaynak sürsün;
   depolama/bütünlük/program hatasında yeni kaynak başlatma.
5. Ransomware refresh başarısızsa ilgili bekleyen üyeleri skipped yap;
   failed refresh'e bağlı watch receipt'i hiçbir zaman kabul etme.
6. Final yerel analiz ve oturum kapanışını kaydet. Kapanış hatası önceki
   kaynak commit'lerini geri almış gibi gösterilmez; sonraki recovery korur.

Ctrl+C/SystemExit yakalandığında güvenli kodla interrupted kapanışı denenir,
asıl hata korunur. DB yazılamıyorsa running bırakılır ve sonraki kilitli recovery
tamamlar. SIGKILL ve elektrik kesintisinde de aynı kayıt kuralı geçerlidir.
SIGTERM'ın kendiliğinden Python exception üreteceği varsayılmaz; sinyal davranışı
ayrı ele alınır. Ham exception/ortam bilgisi kayda veya terminale dökülmez.

`complete` tüm plan birimlerinin complete receipt'i ve başarılı final analiz
gerektirir. Normal kaynak sonuçları bugünkü complete/partial/failed ayrımını
korur. Beklenmeyen yürütme hatası failed, kesinti interrupted olarak kapanır;
bu durumda da tamamlanan kaynak sayısı ayrıca görünür. Final analiz kaynak
hatalarını başarıya çeviremez. Yalnız skipped iş varlığı başarı değildir.

## Migration, kurtarma ve kabul testleri

Şema 55→56 önce mevcut benzersiz doğrulanmış yedeği alır; üç boş tabloyu tek
transaction'da ekler. Eski kaynak geçmişinden oturum uydurulmaz. Eski DB,
profil revizyonları, sonuçlar ve inbox okundu durumları korunur. Yeni DDL ayrı
tutulur; kolon/unique/FK/index/SQL denetimleri, VERSION_TABLES eski sürüm
istisnaları ve legacy test fixture'ları birlikte güncellenir. Restore yeni/boş
hedefe yapılır. Run FK'leri temizlik politikalarının kanıtı silmesini engeller;
bu aşama yeni otomatik retention eklemez.

Kabul kapısı:

- Frozen profil/seçim/tanım ve sürüm uyuşmazlığında ağ öncesi ret; plan/geçmiş
  okuma yazmasız. İki resume aynı parent'tan dal oluşturamaz.
- Complete temel iş ve sosyal üyeler atlanır; partial/failed iş açıkça yeniden
  çalışır. Görünüm sınırı kalıcı sonucu veya atlama kararını değiştirmez.
- Ransomware A tamamlanıp B'de kesildiğinde yeni refresh+B; A için ikinci run
  veya bildirim yok. Yeni refresh hatasında eski snapshot kullanılmaz.
- Kaynak run commit'inden hemen önce/sonra hata enjeksiyonu: receipt ve kaynak
  sonucu birlikte var/yok; oturum kapanışından önce kesinti sonucu kaybetmez.
- Scan enqueue sonrası kesinti yetim işi genel kuyruğa salmaz. Kaynak snapshot
  beklenmedik biçimde değişirse mevcut pin denetimi yazımı durdurur.
- Ctrl+C, SIGTERM/SIGKILL recovery, kilit doluluğu ve bozuk receipt/plan/FK için
  süreç ve kalıcılık testleri; duvar saati gerilemesi sıra bilgisini bozmaz.
- Migration hatasında eski DB ve geçerli backup; backup/restore ile zincir,
  receipt ve kaynak bağları aynı kalır. Kaynak geçmişi backfill edilmez.
- CLI/JSON geçmişinde başarılı, kısmi, başarısız, kesilmiş, atlanmış ve önceki
  oturumdan korunan sonuçlar anlaşılır biçimde ayrılır. Uygun testler ve
  `./scripts/check` geçmeden resume tamamlandı sayılmaz.
