# İlişkili kanıt araştırması

18 Kasım 2026 · 0.159.0 · araştırma modeli 1 · engine/platform v1 · çekirdek şema 75.

Domain, kesin IP, URL veya dosya kimliği için mevcut DNS/CNAME/TLS, IOC ve CTI kayıtlarını tek
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

Domain tam değerle eşleşir; alt alan adlarını otomatik kapsamına almaz.
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
`valid_from`, `valid_until`, `state_sha256`, `description` taşır.
DNS gözlemlerinde `current=null`; eski gözlem bugünkü DNS doğrulaması değildir.
CTI `current` iddianın etkinlik/geçerlilik durumudur. `freshness` son gözlem
zamanına göre `fresh`, `stale` veya `future` olur. `recorded_at` DNS kontrolünün
kaydedilme veya CTI iddiasının güncellenme zamanıdır. `event_id` son eklenen
olaya başvurur; olayın bütün geçmişi özgün kayıt ayrıntısında kalır.
Kaynak çalışması yalnız kayıtlı makbuzla kesin eşleştiğinde verilir; yerel
geri çekme kararı için bir dış kaynak çalışması uydurulmaz.

Boş, başlatılmış bir kayıt alanında `unknown.example` için örnek cevap parçası:

```json
{
  "model_version": 1,
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

Makine sınır kodları: `node_limit`, `edge_limit`, `path_limit`,
`dns_history_window`, `dns_read_budget`, `dns_adjacency_limit`,
`cname_history_window`, `cname_read_budget`, `cname_adjacency_limit`,
`certificate_adjacency_limit`, `cti_adjacency_limit`, `source_evidence_limit`,
`enrichment_result_window`. `coverage_complete` yalnız
bu kapsamın sınırsız kalıp kalmadığını söyler; tazelik, internet kapsamı,
eldeki kaynakların yeterliliği veya güvenlik garantisi değildir.

Başarılı salt okumanın exit kodu 0'dır; `data.status=partial` olabilir.
Yanlış seçenek/ek alan `invalid_parameters` / 2; kayıp/bozuk veri veya
bütünlük bütçesi `storage_error` / 1; değişen kesit `snapshot_changed` / 1;
fazla büyük cevap `response_too_large` / 1. `not_recorded` normal veri
durumudur. İşlem ağ veya ücretli çağrı yapmadığından kaynak kesintisi yeni
bir hata üretmez; saklı son kontrolün hatası görünür kalır.

## Kapsam envanteri ve sonraki dilim

| Yetenek | Önceden | 0.159.0 |
|---|---|---|
| Genel kayıt araması/ayrıntı, kaynak/araç durumu | CLI + engine/platform | Korundu |
| DNS/sertifika/CNAME ilişki geçmişi | `surface relations` CLI | Korundu; kayıtlı kanıt ortak araştırma/öncelik/incelemede de kullanılır |
| Tedarikçi ilişki kararları | `surface relations` CLI | Ortak araştırmaya aktarımı henüz yapılmadı |
| Doğrudan CTI bağlamı | `cti context` CLI | Korundu; kaynak denetimi yeniden kullanılır |
| Domain/IP → DNS/IOC → CTI kaynaklı yolları | Ortak görünüm yok | `research` CLI ve `research.show` engine/platform |
| Otomatik varlık birleştirme, açıklamalı çıkarım | Plan | Sonraki MTR-01/02 dilimleri |
| MISP warninglists | Plan | Dört seçilmiş liste; kaynaklı domain/IP bağlamı, [ayrıntı](WARNINGLISTS.md) |
| URL/hash zenginleştirme | Plan | CIRCL ve kayıtlı urlscan yanıtları; sınırlı kaynak bağlamı |

Güncel çekirdek şema 75'tir; 0.159.0 yeni migration gerektirmez.
0.152.0'ın araştırması tablo eklemiyordu. 0.153.0 warninglist kaynak
geçmişi şema 73, 0.154.0 URL/hash şema 74, 0.156.0 inceleme şema 75
oldu; daha eski alanlardan geçiş açık ve yedeklidir.
Graph deposu, LLM veya zorunlu ücretli servis yoktur. Bu teslim bütün
MTR-01/02/03 planının veya OpenCTI seviyesinin tamamlandığı anlamına gelmez.
