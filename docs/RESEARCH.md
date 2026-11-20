# İlişkili kanıt araştırması

0.175.0 birleşik sosyal keşifleri domain, tam profil URL'si, insan kararı
ve vaka üzerinden araştırmaya bağlar. `social_page`, `social_source_claim`,
`social_provider`, `social_review_decision` kanıtları ayrı kalır. Düğüm ve
kenar JSON'undaki ek `source_comparisons` alanı kaynak/referans başına son
gözlemi, zamanı, farklılığı veya doğrulama eksiğini gösterir. Bir araç
bildirimi tek başına resmî hesap/taklit kararı değildir.
Araştırma kuralı v9; geçmiş kayıtlı incelemeler değişmez. Sosyal kapsam
5.000 satır/16MiB ön denetim ve1.000 profil sınırına sığmazsa `coverage`
eksikliği açıkça belirtir. [Kullanım](SOCIAL_TRACKING.md).

0.168.0 yerel sensör görülmelerini `local_sighting` kanıtı olarak, WHOIS
kayıt bağlarını ayrı kaynak bağlamı olarak ekler. İlişki adayı/insan kararı
`relationships`, birleşik kimlik `identity view`, kaynak farkı `ioc compare`
komutlarındadır. [Anlamı ve kullanım](EVIDENCE_WORKFLOWS.md).


19 Kasım 2026 · 0.168.0 · araştırma modeli 3 · öncelik v8 · engine/platform zarfı v1 · çekirdek şema 78.

0.167.0 raporun her belge sürümünü ayrı düğüm olarak gösterir. Metinde
geçme, özgün arama domaini ve insan CTI/IOC bağlantısı ayrı ilişkilerdir.
Örnek: IP → saklı rapor sürümü → insanın bağladığı kampanya. Eski sürüm
ve geri çekilmiş karar korunur; `record.get` / terminal ayrıntısı doğru
belgeyi açar. [Kullanım, zaman anlamları ve sınırlar](REPORTS_OBSERVATIONS.md).

0.164.0 mevcut vaka/insan kararları, sosyal profil, saklı firma içeriği,
kimlik eşleştirme ve rapor adayları ile RIPEstat IP/ağ/ASN kanıtını ekler.
Yeni öncelik v7; eski incelemeler özgün kalır. Firma geneli pencere ve
karar komutları [inceleme rehberinde](INVESTIGATION.md) açıklanır.

Domain, kesin IP, URL veya dosya kimliği için mevcut DNS/CNAME/TLS, pasif aday, tedarikçi, IOC ve CTI kayıtlarını tek
araştırmada gösterir. Örnek: domain → gözlenen IP → kaynakta ilişkilendirilen
aktör. Her bağlantı özgün kanıt/iddia kimliğini ve tarihini taşır. Bu bir
saldırı veya ihlal kararı değildir. Kaynak iddiaları yeni gözleme dönüşmez.

Bu ilk MTR-01/02 dilimi ücretli API, anahtar veya yeni bağımlılık gerektirmez.
İnternet verisi mevcut toplama işleriyle alınır; araştırma bunların kayıtlarını
okur. İleride seçilen ücretli kaynaklar aynı kaynak/kanıt modeline adaptörle
katılabilir; araştırma çalıştırmak ücretli sorgu başlatmaz.

## Terminalden kullanım

```sh
./xti research securehup.com --type domain
./xti research 93.184.216.34 --type ip
./xti research 'https://example.com/' --type url
./xti research securehup.com --type domain --max-hops 1 --limit 10
./xti --data-dir /path/to/data --json research securehup.com --type domain
```

Domain kökü tam değerle eşleşir; kayıtlı pasif aday bağlantıları üzerinden
alt alanlara genişler. Ad son ekinden kayıtsız alt alan ilişkisi türetilmez.
IP örneği yalnız saklı kayıt aramasıdır, hedefe paket göndermez. Root domain
kaydı ve aynı domainin IOC kaydı tek araştırma düğümünde özgün kimlikleriyle
bulunur. CTI varlıklarının kimlikleri korunur; benzer adlar birleştirilmez.

Çıktıda yollar, ardından her bağlantının kaynakları, ilk/son gözlem ve kayıt
zamanları, iddia/son olay kimliği, varsa kaynak çalışması, kaynak güveni ve
kanıt ayrıntısına geçiş bulunur. Aynı bağlantıdaki farklı gözlemler ayrı
kanıtlardır; aynı gözlem birden fazla yol yüzünden yeniden kaydedilmez.
Geri çekilmiş veya süresi dolmuş IOC/CTI kayıtları tarihî kanıt olarak kalır.
Eski DNS gözlemi, sonraki DNS kontrolü başarısız olsa da silinmez; domain
düğümünün son kontrolü ayrıca görünür.

Her kaynak iddiasının etkinliği ve gözlem güncelliği ayrı değerlendirilir.
Kaynağın verdiği güven sayısı XTI'nın tehdit puanı değildir. Ortak IP iki
domain arasında araştırma yolu sağlayabilir; ortak sahiplik veya ortak aktör
bağı oluşturmaz. CTI ilişkinin özgün yönü korunur; araştırma onu iki yönden
gezebilir. Geçmiş gözlemler aynı anda gerçekleşmiş olay zinciri sayılmaz.

`not_recorded`: bu kapsamda kayıt yok. `no_relationships`: kayıt var,
bağlantı yok. `related_records`: ilişki var. `partial`: bir araştırma sınırına
ulaşıldı. Hiçbiri “güvenli” veya “internetin tamamı kontrol edildi” demek değildir.

Gerekçeli inceleme sırası için `research ... --priorities` veya
`research.priorities` kullanılır. Bu ayrı görünüm bütün toplanan düğüm ve
ilişkileri sıralar; yol sayfalamasıyla karıştırılmaz.
[Örnekler, sıralama kuralları ve sözleşme](RESEARCH_PRIORITIES.md).

## CNAME ve gözlenmiş TLS sertifikaları

0.159.0 aynı araştırmaya iki kayıtlı ilişki ailesi ekler:

| Yol | Dayanak | Sınır |
|---|---|---|
| Domain → CNAME hedefi → son hedefin IP'si | Kayıtlı CNAME kontrolü; her zincir adımı ayrı | IP yalnız son hedefte gerçekten çözümlenmişse eklenir; uzun zincirin tamamı iki adımlık sorguya sığmayabilir |
| Domain → sertifika → başka domain | İki domainin kayıtlı web kontrollerinde aynı DER SHA-256 | Aynı sertifika, aynı sahip veya aynı saldırgan demek değildir |

Örneğin elindeki kayıtlar `example.com → edge.example.net` CNAME'ini
gösteriyorsa, hedef adından araştırma da bu gelen bağlantıyı bulabilir.
Hedef adının ayrıca kayıtlı varlık olması gerekmez; bulundu diye aktif
kontrol onayı veya sahiplik oluşturulmaz. Bu örnek canlı hedef sonucu değildir.

Sertifika düğümünün `kind=certificate`, `record_type=tls_certificate`,
değeri DER SHA-256'dır. Bu düğüm dosya `sha256` IOC'sine dönüşmez.
Sertifikanın SAN/wildcard alanındaki diğer adlar, gerçekten kontrol edilmiş
hostlar gibi bağlanmaz. Yalnız issuer/konu adı benzerliği eşleşme değildir.
`--type certificate` yeni kök seçeneği olarak eklenmedi; domain/IP
araştırmasının bağlantılarında sertifikaya ulaşılır.

İlişki türleri `cname_alias`, `cname_target_address`, `certificate_presented`.
Özgün kontrol kimliği `record_id`, kontrol domaini `source_reference`,
özgün durum özeti `state_sha256` içinde kalır. CNAME kontrolünün son
durumu `surface_cname_check`, gözlenmiş bağlantı `surface_cname_observation`;
TLS son kontrolü `surface_tls_check`, sertifika gözlemi `surface_certificate`
olarak ayrılır. `valid_from/valid_until` sertifika geçerlilik tarihleridir.
`status=presented` ve `current=null` bugünkü sunumu doğrulamaz.

Sertifika değişimi veya sonraki başarısız TLS/CNAME denemesi eski bağlantıyı
silmez. Son kontrol düğümde ayrıca görünür. Kanıtlar farklı tarihlerde
gözlenmiş olabilir; yollar eşzamanlı altyapı resmi değildir. Geçmişin tamamı
özgün salt okuma komutlarından açılabilir:

```sh
./xti surface relations securehup.com --kind cname --history
./xti surface relations securehup.com --kind certificate --history
./xti research securehup.com --type domain --priorities
./xti research-history record securehup.com --type domain
```

İlk iki komut mevcut varlık geçmişini okur; son komut inceleme kaydını
saklar. Bu komutlar yeni internet taraması başlatmaz. Henüz kaydedilmemiş
CNAME/TLS kanıtı burada üretilmez. Mevcut açık onaylı `surface` kontrolleri
kanıt toplama işini yapmaya devam eder. Yeni kaynak, paket veya şema yoktur.

## Tedarikçi adayları ve insan kararları

0.160.0 mevcut tedarikçi kayıtlarını aynı araştırmaya ekler. Aday, insan
onayı ve teknik gözlem birbirine dönüşmez:

| Yol / kayıt | Tür | Ne anlatır? |
|---|---|---|
| Domain → aday → olası hizmet domaini | `candidate_context` | Kayıtlı CNAME'den daha önce türetilmiş teknik aday; insan onayı değildir |
| Domain → tedarikçi | `human_decision` | Kullanıcının kaydettiği kabul ve sonradan kaldırma/değiştirme kararları |
| Tedarikçi → envanter domaini | `human_decision` | Envantere girilmiş ana domain; bağımsız sahiplik doğrulaması değildir |

İç düğüm türleri `supplier_candidate` ve `supplier`; ilişki türleri
`supplier_candidate`, `supplier_candidate_domain`, `human_supplier_link`,
`supplier_registered_domain`. Yeni kök sorgu seçeneği eklenmedi. Tedarikçinin
ana domainini `--type domain` ile aradığında aynı çalışma alanında onunla
ilişkilendirilmiş kayıtlı domainlere iki adımda ulaşabilirsin. Aynı isimdeki
tedarikçiler birleştirilmez. Adayın hizmet domaini ile insanın seçtiği
tedarikçinin ana domaini farklı olabilir; iki değer de korunur.

```sh
./xti research securehup.com --type domain
./xti research securehup.com --type domain --priorities
./xti research-history record securehup.com --type domain
./xti suppliers candidate-list
```

`research` yalnız saklı kayıtları okur. Henüz aday üretilmediyse mevcut
`./xti suppliers candidate-refresh` kayıtlı CNAME kontrollerinden açıkça
aday oluşturur; internet sorgulamaz. Araştırma bu yazımı kendiliğinden
başlatmaz. Ekrandaki ayrıntı komutları `suppliers candidate-show KIMLIK`
ve `suppliers show KIMLIK` üzerinden özgün geçmişe gider. `candidate-list`
varsayılan olarak yalnız güncel/bekleyen adayları listeler; araştırma
tarihî ve reddedilmiş adayları da kaynak bağlamında korur.

İnsan kanıtının `time_basis=decision_recorded_at` değeri kararın tarihidir;
bir hizmetin teknik başlangıç/bitişi veya yeni ağ gözlemi değildir.
`current=true` **son ilgili karar** demektir. `status=accepted`,
`withdrawn`, `pending`, `uncertain`, `rejected`, envanterde `active/revoked`
ayrıca okunmalıdır. Son kararın kaldırılmış olması mümkündür.
Karar alan kişiye ilişkin kullanıcı kimliği mevcut kayıtta bulunmadığından
uydurulmaz; özgün karar kimliği, zamanı ve gerekçesi gösterilir.

Başka tedarikçiyi kabul etmek, reddetmek veya yeniden incelemeye almak eski
onayı tarihî yapar. İlgili özgün yeni olay eski bağlantıda `withdrawn`
olarak gösterilir; yeni bir karar kaydı oluşturulmaz. CNAME kaydının
kaybolması insan onayını kaldırmaz. Envanterin pasifleştirilmesi de adayın
karar geçmişini silmez. Adaydaki `current` son **aday yenilemesinin** teknik
durumudur; araştırma güncel DNS'i yeniden kontrol etmez.

Kanıt başvuruları:

| `record_type` | Özgün başvuru |
|---|---|
| `supplier_candidate` | `record_id` aday kimliği; durum özeti son kayıtlı adaya aittir |
| `supplier_candidate_evidence` | `record_id` aday; `event_id` türetme kanıtı; `source_reference` özgün CNAME kontrol kimliği; PSL sürümü/özeti açıklamada |
| `supplier_resolution` | `record_id/event_id` insan karar olayı; `source_reference` aday kimliği |
| `supplier_inventory` | `record_id/event_id` envanter olayı; `source_reference` tedarikçi kimliği |

Tedarikçi düğümündeki `references` mevcut `record.get` ile açılır. Aday
kanıtı için sahte `record.get` başvurusu üretilmez. Güncel risk kartı veya
tedarikçi izleme uyarıları henüz ortak araştırmanın parçası değildir;
ilgili mevcut modüllerde kalır.

**Sürüm uyumu:** Bu teslim araştırma/değerlendirmeyi `model_version=2`,
önceliği `research-priority-v3` yaptı. 0.161.0 modeli korur, politikayı v4'e
yükseltir; aşağıda açıklanır. Engine/platform istek ve
dış zarfı v1, veritabanı şeması 75 kalır. Eski değerlendirme modeli 1 özgün
okunur; yeni model/kuralın ilk kaydı karşılaştırma başlangıcıdır. Model 1
bilen istemci model 2'yi aynı kabul etmemeli. Eski motor yeni model 2
incelemeyi okuyamaz; geri dönüşte yükseltme öncesi uygun yedek kullanılır.
İlk sayfa yeniden alınmalıdır; kesit kimliği model sürümünü de içerir.

## Tedarikçi izleme ve inceleme bağlamı

0.163.0 mevcut tedarikçi modüllerinin yerel verisini aynı araştırmaya bağlar:

| İki adımlık yol | Görülen bilgi |
|---|---|
| Domain → insan onaylı tedarikçi → kaynak iddiası adayı | ThreatCluster/RansomLook özgün iddiası, tam ad/domain dayanağı, kaynak çalışması ve tarihi |
| Domain → tedarikçi → izleme | ThreatCluster/RansomLook/HIBP için izleme tercihi, son kayıtlı karşılaştırma, yeni/değişen/çıkarılan eşleşmeler ve varsa yerel bildirim kimliği |
| Domain → tedarikçi → inceleme kartı | Mevcut `risk-show` kurallarıyla hesaplanan gerekçeli inceleme durumu, eksik kaynaklar ve güncel insan onaylı CNAME bağı sayısı |

```sh
./xti research securehup.com --type domain --limit 100
./xti research securehup.com --type domain --priorities --limit 100
./xti research-history record securehup.com --type domain
```

Önceden kayıtlı envanter ve insan onaylı ilişki gerekir. Tedarikçinin kendi
ana domaini de kök olabilir. Sırf adı aynı diye ilişkisiz tedarikçi eklenmez.
Bu komutlar internete çıkmaz; kaynaklar mevcut `ransomware refresh`,
`notices refresh` veya bunları içeren toplama işleriyle ayrı yenilenir.
İzleme mevcut `suppliers watch enable` ile açık seçilir; araştırma açmaz.

Kaynak kesildiğinde son başarısız deneme ve önceki başarılı yanıt birlikte
kalır. `not_collected` / `unavailable` / `stale_after_failure` / `available`
eşleşme sayısından ayrı kaynak durumlarıdır. `no_current_match` yalnız
okunan son başarılı snapshot'larda eşleşme yok demektir. Sonuç internetin
tamamını veya tedarikçinin güvenli olduğunu doğrulamaz.

Aynı ad birden fazla etkin tedarikçiye uyuyorsa belirsizlik gösterilir;
tek tedarikçi filtresi diğerlerini belirsizlik hesabından çıkarmaz.
Domain dayanağı ayrı kalır. Risk kartı türetilmiş karar desteğidir, kalıcı
ayrı bir risk olayı veya sayısal risk puanı değildir. HIBP kamu metaverisi
hesap/parola sorgusu ya da ransomware iddiasına dönüştürülmez.

İzleme kaydı kendi tarihî tedarikçi adını, o andaki aynı-ad sayısını,
özgün kaynak çalışmasını ve sonuç özetini taşır. İzleme kapatılması,
tedarikçinin pasife alınması veya kimlik döneminin değişmesi eski
karşılaştırmayı `historical_scope` yapar; geçmiş silinmez. İlk ve yeniden
açılmış karşılaştırma sıfır eşleşmeyle de `baseline` olabilir. `removed`
kaynaktan/eşleşmeden çıkarılmadır; ihlalin çözüldüğü sonucu değildir.

İç düğüm ve ilişki türleri `supplier_event`, `supplier_watch`,
`supplier_risk` olur. Yeni kök türü veya `record.get` türü eklenmez.

| Kanıt türü | Özgün kimlik / anlam |
|---|---|
| `supplier_threat_match` | `record_id`: mevcut olay görünümünün kararlı kimliği; `source_reference`: özgün kaynak kaydı; `source_run_id`: başarılı snapshot; `observed_at`: kaynağın iddia tarihi |
| `supplier_watch` | `record_id`: izleme; `event_id`: son insan açma/kapatma olayı |
| `supplier_watch_run` | `record_id`: değişmez karşılaştırma; `source_run_id`: özgün kaynak çalışması; `event_id`: varsa yerel bildirim |
| `supplier_watch_item` | `record_id`: özgün kaynak öğesi; `source_reference`: karşılaştırma; açıklama: önce/sonra kayıt özetleri |
| `supplier_source_coverage/run` | Kaynak kapsamı, son deneme ve korunmuş başarılı yanıt; iddia kanıtıyla karıştırılmaz |
| `supplier_risk_context` | `record_id/source_reference`: tedarikçi; `status`: ortak kuralla hesaplanan inceleme durumu |

Terminal özgün ayrıntılar için `suppliers event-show`, `risk-show`,
`watch show`, `watch-run-show` komutlarını seçili veri klasörüyle verir.
Kaynak çalışma kimlikleri JSON/kanıtta korunur; ransomware kaynak geçmişi
`ransomware status --source ...`, HIBP çalışması `notices run-show` ile
incelenir. Olay/kart ayrıntısı güncel görünüm, watch-run ayrıntısı tarihî
kanıttır; daha sonra kaynak değişirse bunların aynı sonucu vermesi beklenmez.

İstek başına bağlam doğrulaması 20.000 satır / 16 MiB saklı içerik /
2.000.000 muhafazakâr yeniden oynatma iş birimiyle sınırlıdır. Kimlik
belirsizliği için aynı firmanın tam tedarikçi kimlik geçmişi gerekir;
başka tedarikçilerin izleme payload'ları okunmaz. Sınır aşılırsa
`partial` ve `supplier_context_read_budget` görünür; eksik veriden kesin
kart üretilmez. Tedarikçi başına 150 olay, düğüm başına 52 kanıt;
`source_evidence_limit` / `supplier_context_event_limit` ile eksik görünüm
bildirilir. Genel 100 düğüm / 200 bağlantı sınırı ayrıca geçerlidir.

JSON modeli 3 korunur, politika v6 olur. Önceki model 1/2/3 incelemeleri
özgün okunur; ilk v6 incelemesi yeni politika başlangıcıdır. Sonraki
karşılaştırmalar kaynak/kimlik/izleme/kart değişimini ayrı kayıtlar üzerinden
izler; görünmeyen kayıt otomatik geri çekilmiş/çözülmüş sayılmaz.

## Pasif alt alan adayları ve sahiplik incelemesi

0.161.0 daha önce `surface discover` ile saklanmış adayları aynı araştırmaya
ekler. Örneğin kayıt varsa `example.com → api.example.com → gözlenmiş IP`
iki adımda görülebilir. İlk bağ pasif arşivden, ikinci bağ ayrıca yapılmış
DNS kontrolünden gelir; iki kanıtın türü ve tarihi ayrı kalır.

| İlişki | Kanıt türü | Anlamı |
|---|---|---|
| `passive_subdomain` | `candidate_context` | Kök altında kaydedilmiş aday ve özgün kaynakları |
| `subdomain_classification` | `human_decision` | Kullanıcının `owned`, `rejected`, yeniden `pending` kararları |

İlk otomatik keşif insan kararı değildir; böyle bir bağ ancak kaydedilmiş
insan kararı varsa görünür. `owned` teknik sahiplik doğrulaması veya aktif
tarama izni değildir. Yeniden keşif insan kararını sıfırlamaz. Ret geçmişi
silmez; ayrıca verilmiş aktif kontrol onayını da kendiliğinden kaldırmaz.
Karar veren kişiye ait kimlik mevcut kayıtta yoksa uydurulmaz.

```sh
./xti surface candidates securehup.com --status all
./xti research securehup.com --type domain
./xti research securehup.com --type domain --priorities
./xti research-history record securehup.com --type domain
```

Bu komutlar kayıtlı veriyi kullanır. Aday yoksa mevcut `surface discover`
ile açıkça kaynak toplamak gerekir; `research` bunu kendiliğinden yapmaz.
Bir adayın tam domainini araştırmak kayıtlı kök bağlantısını ters yönde de
bulur. Aynı ad iki kayıtlı kökün adayıysa iki aday kimliği ve kararları
ayrı korunur. Joker ad veya yalnız benzer ad yeni host/ilişki üretmez.

| `record_type` | Özgün kimlik ve tarih |
|---|---|
| `surface_candidate` | `record_id` aday; `stored_seen_range` kayıtlı kaynakların görülme aralığıdır; `current=null` |
| `surface_candidate_source` | `record_id` aday; `event_id` kaynak satırı; `source_reference` özgün URL; `state_sha256` kayıtlı kaynak özeti |
| `surface_candidate_decision` | `record_id/event_id` karar olayı; `source_reference` aday; `decision_recorded_at` kararın kayıt zamanı |

Kaynak gözlem zamanı yoksa alınma/kayıt zamanı `response_received_at`
olarak belirtilir. Yeni karar veya aynı kaynak kaydının tekrarı eski gözlem
zamanını yenilemez. Kararda `current=true` son ilgili karardır; son durum
`rejected` veya `pending` olabilir. Önceki `owned` güncel onay diye sunulmaz.

Domain düğümünün aday başvurusu mevcut `record.get` ile açılabilir:
`kind=domain`, `record_type=surface_candidate`, `namespace=passive-discovery`.
Terminal ayrıca `surface candidate show KIMLIK` komutunu verir. Kaynak
SHA-256 özgün kayıtla korunur; ham sağlayıcı payload'ı saklanmadığı için
içerikten tekrar doğrulandığı iddia edilmez. Kesin ilişki tablosu bulunmayan
keşif çalışma kimliği zaman eşleştirmesiyle tahmin edilmez.

Yeni boş/başarısız keşif çalışması eski adayı silmez. 0.161.0 aday
geçmişini model 2/politika v4 ile ekledi. 0.162.0 son sorgu durumunu aşağıda
ayrı bağlam olarak sunar; adayın kaynak tarihi veya insan kararı yenilenmez.

## Pasif kaynakların son sorgu durumu

```sh
./xti research securehup.com --type domain
./xti research securehup.com --type domain --priorities
./xti surface discovery-health securehup.com
```

Araştırma kayıtlı kök domain için `crt.sh` ve `theharvester` durumunu ayrı
gösterir. Yeni internet sorgusu yapmaz; kayıtsız alt alan kökün durumunu
miras almaz. JSON'da `nodes[].discovery`, öncelik/incelemede
`items[].discovery` bulunur. Diğer düğümler/ilişkilerde boş listedir.

| `outcome` | Anlamı |
|---|---|
| `never` | Bu kök/sağlayıcı için kayıtlı sorgu yok; tarih veya çalışma kimliği yok |
| `complete_found` | Sorgu tamamlanmış, bu yanıtta aday görülmüş |
| `complete_empty` | Sorgu tamamlanmış, bu yanıtta aday görülmemiş |
| `partial_found` | Eksik yanıtta aday var; sonuçların tamamı alınmış değil |
| `partial_empty` | Eksik yanıtta aday görülmemiş; boş sonuç doğrulanmış sayılmaz |
| `failed` | Son sorgu başarısız; aday varlığı hakkında yeni sonuç yok |
| `read_limited` | Yerel okuma sınırına sığmamış; sorgulanmadı/boş deneme değildir |

Her sağlayıcıda `latest_run` ve `successful_run` (son **complete** çalışma)
ayrı okunur. `previous_success_preserved=true` eski complete yanıtın
korunduğunu anlatır. Her çalışma özgün `id`, `source_url`, başlangıç/bitiş,
sonuç sayıları, uyarı/hata ve kendi `freshness` alanını taşır. Son başarısız
deneme eski başarılı yanıtın tarihini yenilemez. Sıra saatten değil kayıtlı
çalışma sırasından seçilir. Boş sonuç bütün internette aday veya risk
olmadığını kanıtlamaz. `never` isteğe bağlı aracın kurulu olmadığını da
kanıtlamaz; yalnız kayıtlı deneme yoktur.

`surface_discovery_run/source_context` kanıtı aynı domain düğümündedir;
çalışma kimliği `source_run_id`, zaman `response_received_at` olarak
korunur. Buradaki hash çalışma kaydının özetidir; sağlayıcı ham payload'ı
değildir. Bu kimlik adayın arşiv kaynak satırına otomatik bağlanmaz.
Terminalde özgün çalışma için `surface run KIMLIK` ayrıntısı sunulur.

Her kökte en fazla dört çalışma, istek genelinde 4 MiB seçili çalışma
alanı okunur. Ön kontrol sınırı aşarsa `discovery_status_read_budget`
belirtilir; eski aday bağlantısı görünmeye devam edebilir. Üstteki
`coverage_complete` yalnız sınırlı **yerel okumanın** tamamlanmasını ifade
eder; bütün kaynakların sorgulandığı veya son yanıtlarının başarılı olduğu
anlamına gelmez. Kaynak sonucu için `discovery` okunmalıdır.

Araştırma/değerlendirme modeli **3**, öncelik **v5** olur; dış istek/zarf
v1, DB/iş şeması 75/2 korunur. Eski model 1/2 incelemeleri kendi biçiminde
okunur; ilk yeni inceleme `policy_baseline` olur. Yeni deneme kesit
kimliğini değiştirir; eski sayfa anahtarıyla devam edilmez. Kod geri
dönüşünde yükseltme öncesi uygun yedek gerekir; eski motor model 3'ü
okuyamaz. [Karar](decisions/0167-passive-source-research-context.md).

## URL/hash kaynak bağlamı

0.154.0 URL, MD5, SHA-1, SHA-256 köklerini ekler. `enrich fetch` ile saklanan
yanıtlar `nodes[].enrichment` içinde okunur. Kaynağın dosya kimliği, tarihî
gezinme ve son sayfa IP iddiaları `source_context` bağlantılarıdır; IOC veya
risk kararı oluşturmaz. Kanıtlardaki `time_basis` gerçek kaynak gözlemi
ile yanıtın alınma zamanını ayırır. Son başarısız deneme eski başarılı
yanıtı silmez. Bütün arşivde ters indeks araması bu dilimde yoktur.
[Kullanım ve parametreler](INDICATOR_ENRICHMENT.md).

## Liste bağlamı

0.153.0 ile `./xti warninglists sync` üzerinden alınan dört seçilmiş MISP
listesinin eşleşmeleri araştırma düğümlerinde görünür. Liste, eşleşen üye,
özgün çalışma kimliği ve kaynak durumu korunur. Örneğin bir IP'nin
Cloudflare ağı içinde olması ortak altyapı bağlamıdır; sahiplik, zararlılık
veya güvenlik kararı değildir. Mevcut IOC/CTI kayıtları ve alarmlar değişmez.

Listeler aynı okuma kesitinden alınır. Araştırma yeni liste indirmez ve
başka firmanın kataloğunu kullanmaz. Liste güncelliğinin varsayılan eşiği
168 saattir; araştırmanın gözlem güncelliği parametresi bunu değiştirmez.
Sadece liste eşleşen ama kayıtlı kanıtı olmayan kökün durumu yine
`not_recorded` olabilir. [Liste durumu ve kullanımı](WARNINGLISTS.md).

## Sürümlü platform işlemi

İstek hem `./xti engine` hem de güvenilen başlatıcının seçtiği
`./xti platform request --root /srv/xti --company firma-a` girişinde aynıdır:

```json
{
  "contract_version": 1,
  "request_id": "arastirma-1",
  "operation": "research.show",
  "parameters": {
    "indicator_type": "domain",
    "value": "securehup.com",
    "max_hops": 2,
    "limit": 20
  }
}
```

| Parametre | Kural |
|---|---|
| `indicator_type`, `value` | Zorunlu; `domain`, `ip`, `ipv4`, `ipv6`, `url`, `md5`, `sha1`, `sha256`; kesin değer |
| `max_hops` | 1–2, varsayılan 2 |
| `node_limit` | 2–100, varsayılan 100 |
| `edge_limit` | 1–200, varsayılan 200 |
| `offset`, `limit` | 0–1.000.000 ve 1–100, varsayılan 0 ve 50; **yol sayfası** |
| `stale_after_hours` | 1–8.760, varsayılan 24; yalnız gözlem güncelliği |
| `expected_snapshot` | Önceki cevabın 64 karakterli `snapshot_id` değeri |

Firma ve dosya yolu JSON ile seçilemez. Kayıtlar yalnız seçilmiş firmanın
veritabanından okunur; aynı IP'nin başka firmadaki kanıtları eklenmez.
`nodes[].references` mevcut `record.get` işlemine verilebilir. CTI ilişki
kanıtının ayrıntısı `cti relation-show`, DNS tarihçesi `surface relations
DOMAIN --kind dns --history` ile okunur. DNS ve ilişki kanıt kimlikleri
`record.get` destekli düğüm referanslarıyla karıştırılmamalıdır.

Sonuç `data` alanları:

| Alan | Anlamı |
|---|---|
| `model_version`, `status`, `checked_at` | Model ve okuma durumu/zamanı |
| `snapshot_id`, `consistency` | Okunan alt grafın içerik kimliği; `single_read_snapshot` |
| `root_id`, `query`, `stored_data_only` | Kök, kanonik seçim/sınırlar ve kayıtlı veri işareti |
| `nodes` | Bu sayfanın düğümleri: kararlı kimlik, tür, değer, etiket, özgün referanslar, kanıt ve `warninglist_matches` |
| `warninglists` | Liste kaynakları ve bu dört listenin güncellik/başarı kapsamı; araştırma kanıt bütçesinden ayrıdır |
| `edges` | Bu sayfanın bağlantıları: kimlik, kaynak/hedef düğüm, ilişki türü ve özgün kanıt |
| `paths` | Kökten başlayan `node_ids`, `edge_ids`, `hops`; en fazla iki adım, döngüsüz |
| `collected_node_count`, `collected_edge_count`, `collected_path_count` | Bütçe içinde toplanan alt graf/yol sayıları; bütün veri tabanının toplamı değildir |
| `offset`, `limit`, `has_more`, `next_offset` | Yol sayfalaması |
| `coverage_complete`, `limitations`, `coverage` | Seçilen dar kapsamın eksikleri ve incelenen DNS/TLS, CNAME, CTI pencereleri |
| `notes` | Yorum ve kapsam sınırları |

Kanıt nesnesi `record_type`, `record_id`, `assertion_id`, `event_id`,
`source`, `source_reference`, `source_run_id`, `kind`, `status`, `current`,
`first_observed_at`, `observed_at`, `recorded_at`, `freshness`, `confidence`,
`valid_from`, `valid_until`, `state_sha256`, `description`, `time_basis` taşır.
DNS gözlemlerinde `current=null`; eski gözlem bugünkü DNS doğrulaması değildir.
CTI `current` iddianın etkinlik/geçerlilik durumudur. `freshness` son gözlem
zamanına göre `fresh`, `stale` veya `future` olur. `recorded_at` DNS kontrolünün
kaydedilme veya CTI iddiasının güncellenme zamanıdır. `event_id` son eklenen
olaya başvurur; olayın bütün geçmişi özgün kayıt ayrıntısında kalır.
Kaynak çalışması yalnız kayıtlı makbuzla kesin eşleştiğinde verilir; yerel
geri çekme kararı için bir dış kaynak çalışması uydurulmaz.
Tedarikçi insan kararında zaman temeli `decision_recorded_at` olur;
karar yaşı gösterilir ancak ağ gözlemi eskimesi gibi sıralanmaz. Özgün
kararlar ayrı kanıtlardır, `event_id` her birinin kendi olayına başvurur.

Boş, başlatılmış bir kayıt alanında `unknown.example` için örnek cevap parçası:

```json
{
  "model_version": 3,
  "status": "not_recorded",
  "stored_data_only": true,
  "consistency": "single_read_snapshot",
  "collected_node_count": 1,
  "collected_edge_count": 0,
  "collected_path_count": 0,
  "coverage_complete": true,
  "limitations": [],
  "edges": [],
  "paths": [],
  "has_more": false,
  "next_offset": null
}
```

Bu **kısaltılmış şema örneğidir**; canlı hedef sonucu değildir. Tek düğüm
aranan köktür; kayıt bulunduğu anlamına gelmez. Tam cevap kimlik, saat,
kapsam, düğüm kanıtı ve dış engine/platform zarfını da içerir.

## Sayfa tutarlılığı ve sınırlar

Bir istek tek SQLite okuma işlemindedir. Sonraki sayfanın `offset` değerini
`next_offset`, `expected_snapshot` değerini önceki `snapshot_id` yapın;
diğer seçimleri koruyun. Terminal devam komutu bunu hazır verir. Kanıt,
etkinlik veya kapsam değişmişse `snapshot_changed` / çıkış 1 döner; ilk
sayfadan başlayın. Kesit saklanmaz, geçmiş bir kesit tekrar açılmaz. Aynı
veride sıra kararlıdır; işaret verilmeden ayrı istekler arasında güncelleme
olursa sayfalar karışabilir. Sayfada yalnız yolların düğüm/bağları ve kök
görünür. İlişki iddiasının özgün yönünü yolun okuma yönünden çıkarmayın.

Sabit okuma sınırları:

- DNS ve TLS birlikte en fazla 1.000 farklı web kontrolü, toplam 16 MiB
  JSON kullanır. Domain kendi en yeni kontrollerini; IP veya sertifikadan
  geriye arama çalışma alanının en yeni 1.000 web kontrolünü inceler.
  `coverage.kind=dns` bu ortak web kontrol penceresini ifade eder.
- CNAME ayrıca en fazla 1.000 farklı kontrol/16 MiB kullanır. Domainin
  son kontrolü ve gelen bağlantılar için çalışma alanının en yeni 1.000
  CNAME kontrolü okunur. Her iki ailede ilgisiz kontroller de pencereye
  dahildir; ters arama bütün arşiv değildir. Önceden okunan kök kanıtı
  ters pencerenin dışında kaldığında da korunur.
- Düğüm başına aile başına en fazla 200 DNS, CNAME, sertifika veya CTI
  bağı; istek genelinde yine en fazla 200 bağ ve 2.000
  döngüsüz yol. İstek ayrıca daha küçük düğüm/bağ bütçesi seçebilir.
- Her IOC/CTI kaydı, yüzey bağı veya sertifika düğümünde en fazla 50
  kaynak/kanıt gösterilir. Domain düğümünde son DNS/TLS/CNAME kontrolü
  önce, ardından sığan IOC kanıtları görünür; toplam üst sınır 52'dir.
  Bütçeye sığmayan son
  kontrolün yerine eski kontrol son kontrol diye gösterilmez.
  `evidence_total_count` o kayıt/pencere içindeki sayıyı verir; atlananlar
  özgün ayrıntıdan incelenebilir. Bu durumda kapsam kısmi işaretlenir.
- Kaynak geçmişi doğrulamasında kayıt başına 1.000 iddia/10.000 olay ve
  istek başına 20.000 iddia+olay sınırı vardır. Doğrulanamayan kaynak
  geçmişi `storage_error` olur; eksik geçmişten etkinlik hesaplanmaz.
  Mevcut ATT&CK iç denetimi kendi bütünlük sınırlarını ayrıca korur.
- Tedarikçi adayı ve envanteri için düğüm başına en fazla 200 bağ;
  araştırma genelinde 10.000 bağlı satır/16 MiB ön doğrulama bütçesi.
  Adayın tam kaynak/karar geçmişi ve ilgili tedarikçi yaşam döngüsü
  doğrulanır. İlgisiz envanter içerikleri okunmaz; küresel olay sıra
  boşluğu denetlenir. Bütçeye sığmayan kayıt atlanır, kısmi kapsam verilir;
  bozuk kanıt ise `storage_error` olur. Aday düğümünde en fazla 52 kanıt,
  son durum/son karar/en az bir teknik kanıt önce; diğer bağlarda en fazla
  50 kanıt bulunur. Toplam geçmiş sayıları korunur.
- Pasif alt alanlarda düğüm başına 200 aday seçilir; her biri en fazla iki
  ilişki verir ve genel 200 bağ sınırı ayrıca uygulanır. İstekte 10.000
  kaynak/olay/durum satırı ve 16 MiB ön kontrol; aday başına 1.000 karar
  olayı sınırı vardır. Sığmayan adayın geçmişi bütünüyle atlanır; doğrulanmış
  aday sayısı ve kısmi kapsam açık gösterilir. Bağ başına 50 kanıt: aday
  özeti önce, kaynakta gözlem/alınma zamanı en yeni önce, kararda son eklenen
  olay önce. Olay sırası saat gerilemesiyle değiştirilmez.

Makine sınır kodları: `node_limit`, `edge_limit`, `path_limit`,
`dns_history_window`, `dns_read_budget`, `dns_adjacency_limit`,
`cname_history_window`, `cname_read_budget`, `cname_adjacency_limit`,
`certificate_adjacency_limit`, `cti_adjacency_limit`, `source_evidence_limit`,
`enrichment_result_window`, `supplier_adjacency_limit`, `supplier_read_budget`,
`discovery_candidate_limit`, `discovery_read_budget`, `discovery_status_read_budget`,
`supplier_context_read_budget`, `supplier_context_event_limit`.
`coverage_complete` yalnız
bu kapsamın sınırsız kalıp kalmadığını söyler; tazelik, internet kapsamı,
eldeki kaynakların yeterliliği veya güvenlik garantisi değildir.

Başarılı salt okumanın exit kodu 0'dır; `data.status=partial` olabilir.
Yanlış seçenek/ek alan `invalid_parameters` / 2; kayıp/bozuk veri veya
bütünlük bütçesi `storage_error` / 1; değişen kesit `snapshot_changed` / 1;
fazla büyük cevap `response_too_large` / 1. `not_recorded` normal veri
durumudur. İşlem ağ veya ücretli çağrı yapmadığından kaynak kesintisi yeni
bir hata üretmez; saklı son kontrolün hatası görünür kalır.

## Kapsam envanteri ve sonraki dilim

| Yetenek | Önceden | 0.163.0 |
|---|---|---|
| Genel kayıt araması/ayrıntı, kaynak/araç durumu | CLI + engine/platform | Korundu |
| DNS/sertifika/CNAME ilişki geçmişi | `surface relations` CLI | Korundu; kayıtlı kanıt ortak araştırma/öncelik/incelemede de kullanılır |
| Tedarikçi adayları ve ilişki kararları | Ayrı aday/tedarikçi ve `surface relations` CLI | Ortak araştırma/öncelik/inceleme; teknik aday ile insan kararı ayrı |
| Pasif alt alan adayları ve sahiplik sınıflandırması | Keşif/envanter/aday CLI | Ortak araştırma/öncelik/inceleme; arşiv, karar ve aktif kapsam ayrı |
| Pasif kaynak son sorgusu ve önceki complete yanıt | `surface discovery-status/health` CLI | Aynı araştırma kesitinde ayrı bağlam; aday kanıtını yenilemez |
| Tedarikçi iddiası/izleme/kartı | Ayrı tedarikçi komutları | Ortak araştırma/öncelik/inceleme; kaynak ve tarihî kapsam ayrı |
| Doğrudan CTI bağlamı | `cti context` CLI | Korundu; kaynak denetimi yeniden kullanılır |
| Domain/IP → DNS/IOC → CTI kaynaklı yolları | Ortak görünüm yok | `research` CLI ve `research.show` engine/platform |
| Otomatik varlık birleştirme, açıklamalı çıkarım | Plan | Sonraki MTR-01/02 dilimleri |
| MISP warninglists | Plan | Dört seçilmiş liste; kaynaklı domain/IP bağlamı, [ayrıntı](WARNINGLISTS.md) |
| URL/hash zenginleştirme | Plan | CIRCL ve kayıtlı urlscan yanıtları; sınırlı kaynak bağlamı |

Güncel çekirdek şema 75'tir; 0.163.0 yeni migration gerektirmez.
0.152.0'ın araştırması tablo eklemiyordu. 0.153.0 warninglist kaynak
geçmişi şema 73, 0.154.0 URL/hash şema 74, 0.156.0 inceleme şema 75
oldu; daha eski alanlardan geçiş açık ve yedeklidir.
Graph deposu, LLM veya zorunlu ücretli servis yoktur. Bu teslim bütün
MTR-01/02/03 planının veya OpenCTI seviyesinin tamamlandığı anlamına gelmez.
