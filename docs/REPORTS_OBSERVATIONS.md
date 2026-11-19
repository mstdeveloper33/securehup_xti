# Rapor sürümleri ve gözlemler

0.169.0 güncellemesi: önceki `capture` başlık/özet davranışı korunur.
Yeni `reports fetch` açık işlemle CERT-FR/NCSC HTML/PDF ana metnini model 2
olarak alır. `report-capture` kaynak işi, 0.168.0'dan beri seçilmiş saklı
haber/firma kayıtlarını model 1 rapora otomatik alabilir.
[Yeni kullanım ve saklama sınırları](PUBLISHER_REVIEW_RETENTION.md).

0.167.0 · Rapor modeli 1 · Araştırma modeli 3 / öncelik v8 · Çekirdek şema 77 · Engine/platform sözleşmesi 1.

Bu katman, internetten zaten toplanmış haber veya firma içeriğini kaynaklı
rapora alır. Başlık ve özet saklanır; URL açılıp tam makale/PDF indirilmez.
Yeni API veya ücretli servis gerekmez. Tavily içeriği için mevcut anahtar
gereksinimi sürer; ücretsiz RSS/Atom haberleriyle de kullanılabilir.

## Kullanım

Önce var olan toplayıcıyla haber alıp kayıt kimliğini seçin:

```sh
./xti news refresh --source ncsc
./xti news list
./xti reports capture --source news HABER_KIMLIGI --idempotency-key rapor-001
./xti reports list
./xti reports show RAPOR_KIMLIGI
./xti reports show RAPOR_KIMLIGI --document-revision 1
./xti observations ipv4 192.0.2.10
```

`HABER_KIMLIGI` ve `RAPOR_KIMLIGI` gerçek çıktıdaki kimliklerle değiştirilir.
Son IP yalnız örnek değerdir; komut ağ taraması yapmaz. Firma araması
için `reports capture --source mentions ICERIK_KIMLIGI` kullanılır.

`capture` açık bir işlemdir. Mevcut kaynak işi `reports` adımı ve
`investigate extract`, önceki aday/inceleme modelini kullanmaya devam eder;
yeni belge günlüğünü doldurmazlar; 0.168.0 `report-capture` adımı bu işi ayrı yapar. Geçmiş kaynak
sürümleri kendiliğinden taşınmaz; capture anındaki saklı sürüm alınır.

## Aynı içerik ve değişiklik

- Rapor kimliği kaynak türü + özgün kayıt kimliğine bağlıdır. Aynı URL'nin
  farklı yayıncı/arama kapsamındaki kayıtları otomatik birleştirilmez.
- Aynı içeriğin yeniden alınması belge/gözlem oluşturmaz. Kaynak indirme
  zamanı veya arama sıralama puanının değişmesi yeni metin sayılmaz.
- Metin, yayın bilgisi veya anlamlı belge metaverisi değişirse yeni belge
  sürümü korunur. A → B → A değişimi üç sürümdür; tarih geri yazılmaz.
- Aynı `idempotency_key` aynı isteğin ilk sonucunu döndürür; sonradan kaynak
  değişmiş olsa da ilk sonuç korunur. Yeni kaydı almak için yeni anahtar
  kullanılır. Aynı anahtar farklı istekle kullanılırsa ret verilir.
- Yeni anahtar + aynı içerikte yalnız tekrar makbuzu eklenir. Belge sürümü,
  gözlem kimliği ve semantik sayfa özeti değişmez.

`revision` tüm belge/insan kararı değişikliklerini sayar;
`document_revision` yalnız kaynak metin sürümüdür. Bunlar farklı alanlardır.

## İnsan bağlantısı

Önce rapor ve mevcut CTI kaydı incelenir. Sonra şu bağlantı yapılabilir:

```sh
./xti reports link RAPOR_KIMLIGI \
  --target-kind entity --target-id CTI_KIMLIGI \
  --state linked --reason 'Analist bu metindeki kampanya bağını inceledi.' \
  --expected-revision 1 --idempotency-key rapor-bag-001
```

`entity` hedefi mevcut `threat-actor`, `campaign` veya `malware` olabilir.
`indicator` mevcut IOC kimliğine bağlar. Hedef seçili firma alanında
bulunmalı ve etkin kaynak iddiası taşımalıdır. Bağ `reports-on` anlamındadır;
göstergeyi zararlı yapmaz, kaynak güven puanını değiştirmez ve aktör atfı
üretmez. Kararın gerekçesi ve hedefin o andaki kimlik/kanıt özeti korunur.

Geri çekme için `--state withdrawn`, yeni anahtar ve güncel
`--expected-revision` kullanılır. Geçmiş silinmez. Bağ varsayılan olarak
son belgeye aittir; eski belge için `--document-revision 1` verilebilir.
Kaynak metin değişince eski bağ yeni belgeye taşınmaz. Eski belgeye verilmiş
karar, yeni belge geldikten sonra da ayrıca geri çekilebilir.

## Dört ayrı kanıt anlamı

| `kind` | Anlam | Zaman |
| --- | --- | --- |
| `text_mention` | Saklı başlık/özette gösterge adayı var. Özgün metin aralığı korunur. | Olay zamanı bilinmiyor; yayın, kaynak toplama ve rapora kayıt ayrı. |
| `provider_observation` | Feodo'nun bildirdiği IP gözlem iddiası. | Kaynağın kayıtlı IP zamanı; hassasiyeti sağlayıcıya bağlı. |
| `feed_membership` | CERT Polska listesindeki kaynak iddiası. | Liste sürümü zamanı; saldırı zamanı değil. |
| `source_assertion` | Eski elle girilmiş kaynak iddiası. | Saklı zamanın gerçek olay mı giriş zamanı mı olduğu belirsiz. |

IOC geçmişi yeniden kopyalanmaz; mevcut denetlenmiş geçmişten ayrı kayıtlar
olarak okunur. Aynı kaynak iddiası/zamanındaki düzeltmelerin olay kimlikleri
tek gözlem altında korunur. Yeni indirme gözlem sayısını artırmaz; geri
çekme yeni saldırı/gözlem oluşturmaz. Eski gözlemin `assertion_active`
alanı güncel iddia durumunu gösterir; gözlemin kendisi silinmez.

Kaynak tarihinin hassasiyeti bilinmiyorsa tahmin edilmez. Yalnız gün
verilmişse `publication.date` dolu, `publication.at` null olur. Saat dilimi
olmayan belirsiz yayın metni ham biçimde korunur. Tarihî IOC toplama
zamanını sonraki indirmeden türetmeyiz; bu görünümde `collected_at` null
olabilir. Son toplama sağlığı için `ioc lifecycle` veya kaynak durumunu
kullanın. Donmuş raporun okunması canlı kaynağın sağlıklı olduğu anlamına gelmez.

Bu kayıtlar müşteri ağından toplanmış gerçek sighting veya doğrulanmış
olay değildir. Yeni belgeler `report-document-candidates-v2` kuralını
kullanır: URL, IP, hash ve `[.]` ile yazılmış domain adayları. Cümle
sonundaki nokta IP'nin parçası sayılmaz; `192.0.2.10.5` gibi daha uzun
bir ifadenin ön kısmı IP diye alınmaz. Eski investigation önerileri kendi
`report-candidates-v1` kuralıyla okunur; geçmiş yeniden yorumlanmaz. Tam doğal dil
çözümleme, genel ilişki çıkarımı veya otomatik IOC kaydı yapılmaz.

Metin aralıkları (`start`, `end`) başlık + satır sonu + özet içindeki
sıfır tabanlı Unicode kod noktası konumlarıdır; `end` dahil değildir.
Bayt veya UTF-16 konumu değildir. JavaScript/.NET istemcisi vurgulama
yaparken bu farkı gözetir; özgün aday metni ayrıca `original` alanındadır.

## JSON sözleşmesi

| İşlem | Zorunlu parametreler | İsteğe bağlı |
| --- | --- | --- |
| `reports.list` | Yok | `source`, `offset`, `limit`, `expected_snapshot` |
| `reports.show` | `identifier` | `document_revision` |
| `observations.list` | `indicator_type`, `value` | `offset`, `limit`, `expected_snapshot` |
| `reports.capture` | `source`, `identifier`, `idempotency_key`, `expected_workspace_id` | Yok |
| `reports.link` | `identifier`, `target_kind`, `target_id`, `state`, `reason`, `expected_revision`, `idempotency_key`, `expected_workspace_id` | `document_revision` |

İlk üç işlem engine ve platformda salt okunur. Son ikisi yalnız platform
JSON girişinde yazabilir; kişisel terminalde de karşılığı vardır. Firma
başlatıcı tarafından seçilir; JSON başka firma veya dosya yolu alamaz.
Workspace kimliği restore sonrasında değişir; eski yazma isteği reddedilir.

```json
{
  "contract_version": 1,
  "request_id": "report-capture-1",
  "operation": "reports.capture",
  "parameters": {
    "source": "news",
    "identifier": "HABER_KIMLIGI",
    "idempotency_key": "report-capture-1",
    "expected_workspace_id": "GUNCEL_WORKSPACE_UUID"
  }
}
```

Bu istek `./xti platform request --root PLATFORM_KOKU --company FIRMA`
komutunun stdin girişine verilir. Sonuç `data.record` altında belge,
yayın/toplama/kayıt tarihleri, kaynak bağı, metin adayları, insan bağlantıları
ve değişiklik geçmişini taşır. Yazmada `data.action` changed/unchanged ve
`data.replayed` ilk isteğin tekrarını belirtir. Liste cevapları `records`,
`total_count`, `has_more`, `next_offset`, `snapshot_id` taşır.

`not_found` çıkış 3; biçim/parametre hataları 2; `revision_changed`,
`snapshot_changed`, `idempotency_conflict`, `scope_mismatch`, `busy` ve
depo hataları 1 döner. Başarı 0'dır. CLI biçim hatası `validation_error`,
JSON protokolünde `invalid_parameters` olarak ifade edilir.

## Saklama, geçiş ve sınırlar

Mevcut veri alanı için açık `./xti migrate` gerekir. Şema 76 → 77 önce
geçiş yedeği alır, sonra yalnız rapor journal tablosunu ekler. Kaynak,
eski investigation, varlık, IOC ve iş kimlikleri değişmez. Kuyruk şeması
3 kalır. Geri dönüş eski kodla geçiş öncesi yedeğin **boş hedefe** restore
edilmesidir; şema 77'yi eski kodla açmak değildir. Gerçek kullanıcı alanı
geliştirme testlerinde yükseltilmez.

Journal en fazla 10.000 makbuz / 32 MiB; tek rapor en fazla 1.000 değişiklik
/ 2 MiB; kaynak okuma 20.000 satır / 32 MiB; sayfa 1–100 kayıt. Seçili IOC
kanıtı [yaşam döngüsü sınırlarını](IOC_LIFECYCLE.md) kullanır. Sınırlar
aşılınca eksik başarı veya eski geçmişi silme yerine açık ret verilir.
Yazma cevabının boyutu da commit öncesi sınırlandırılır. Bunlar ölçülmüş
çok büyük veri desteği iddiası değildir.

0.166.0'dan 0.167.0'a ek migration yoktur. Rapor günlüğünün kuruluşu
[0171 kararında](decisions/0171-report-revisions-and-observations.md),
araştırma bağlantısı [0172 kararında](decisions/0172-report-research-context.md) açıklanır.

## Raporu bir IP veya domain araştırmasında kullanma

Kaynak kaydını yukarıdaki `reports capture` ile rapora aldıktan sonra:

```sh
./xti research 192.0.2.10 --type ip
./xti research 192.0.2.10 --type ip --priorities
./xti research suspect.example --type domain
```

İlgili metin/bağlantı kayıtlıysa örnek yol **IP → raporun 1. sürümü →
insanın bağladığı kampanya** olur. Her belge ayrı görünür. İlk sürümdeki
bağlantı ikinci sürüme kendiliğinden geçmez; geri çekilen bağlantının eski
ve son kararları birlikte gösterilir. Terminal her kanıttan doğru
`reports show RAPOR_UUID --document-revision N` komutuna yönlendirir.

| Araştırma ilişkisi | Anlamı |
| --- | --- |
| `report_text_mention` | Saklı başlık/özette çıkarılmış IP, URL, hash veya `[.]` biçimindeki domain adayı. Zararlılık değildir. |
| `report_search_scope` | Firma aramasında kullanılan domain. Metinde geçtiği anlamına gelmez. |
| `report_reviewed_link` | İnsan tarafından belirli belge sürümüne bağlanan aktör/kampanya/malware veya mevcut IOC. Geri çekmeler dahildir. |

Bağlantılar iki adımlı araştırmada gezilebilir; bu yol otomatik aktör–IOC
saldırı ilişkisi oluşturmaz. Sadece kaynağın URL'sinde yer almak domain
adayı sayılmaz. Eski investigation adayı ile yeni rapor aynı kaynağa
dayanabilir; tekrarlar bağımsız doğrulama veya ek puan üretmez.

`current_document` son **kayıtlı** belge, `historical_document` önceki
belgedir; canlı sayfanın bugün aynı olduğu iddiası değildir. İnsan
kararında `current=true` son karar anlamına gelir; `linked/withdrawn`
durumu ayrıca okunur. Kaynak metni, alınma zamanı, yayın zamanı ve insan
kararı zamanı ayrıdır. Araştırmanın eski zaman alanı `observed_at`,
raporlarda `time_basis=response_received_at` ile kaynak alınma tarihidir;
bilinmeyen saldırı/olay tarihi yerine kullanılamaz.

Araştırmadaki rapor kararının `event_id` değeri rapor kimliği ve kararın
`revision` numarasından üretilen sabit kanıt başvurusudur; ham journal satır
UUID'si değildir. `record_id` belgeyi, ayrıntının `history` alanı özgün
karar sürümünü ve gerekçesini gösterir.

Mevcut `research.show`, `research.priorities`, `research.review.record`
ve `research.review.get` bu kapsamı kullanır. Öncelik politikası v8'dir;
v7 inceleme değişmez, ilk v8 inceleme yeni karşılaştırma başlangıcıdır.
Rapor düğümünün `references` alanı doğrudan `record.get` ile açılır:

```json
{
  "contract_version": 1,
  "request_id": "report-detail",
  "operation": "record.get",
  "parameters": {
    "reference": {
      "kind": "report",
      "record_type": "report_document",
      "namespace": "local-reports",
      "record_id": "RAPOR_UUID:1"
    }
  }
}
```

`RAPOR_UUID:1` yerine araştırma yanıtındaki başvuruyu aynen kullanın.
Yanıt `record.document` içinde seçilen metni, `sections.links/history`
içinde sayfalı bağlantıları/geçmişi verir. Başka firmanın veya olmayan
belgenin kimliği `not_found` üretir. İşlem ağ çağrısı veya yazma yapmaz.

Araştırma rapor ön okuması 10.000 makbuz/16 MiB, düğüm başına 200
bağlantı, istek boyunca 50.000 bağlantı incelemesiyle sınırlıdır.
`report_read_budget`, `report_adjacency_limit`, `report_work_budget`
eksik kapsamı belirtir; boş sonuç değildir. Tek ilişkide 52 kanıt sınırı
aşılırsa toplam korunur; ayrıntıdan geçmiş açılır. Bozulmuş günlük için
eksik başarı verilmez. Genel model/sayfalama sınırları da geçerlidir.
