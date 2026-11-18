# Kayıtlı incelemeler ve önceki incelemeye göre değişim

18 Kasım 2026 · 0.160.0 · çekirdek şema 75 · değerlendirme modeli 2 (eski model 1 okunur).

Bir domain, IP, URL veya dosya kimliğini incelerken o günkü kanıtları ve
inceleme sırasını saklayabilirsiniz. Sonraki kayıt, aynı kapsamın önceki
kaydıyla karşılaştırılır. Böylece yeni kanıt, geri çekilen kaynak iddiası
ve yalnız zaman geçtiği için eskiyen bilgi birbirinden ayrılır.

Bu işlem mevcut kayıtları kullanır. Kaynak toplama komutları internetten
veri getirmeye devam eder; incelemeyi kaydetmek yeni tarama, ücretli API
veya LLM çağrısı yapmaz. Alarm ve analist kararlarını değiştirmez.

## Terminalden kullanım

0.160.0 tedarikçi adayları ve insan kararlarını ayrı kanıt türleriyle
saklar. Yeni değerlendirme modeli 2 ve politika v3'tür. Önceki model 1
incelemeler yeniden yazılmaz; sürüm değişiminin ilk kaydı `policy_baseline`
olur. İnsan kararının geri alınması `evidence_or_mixed` değişimidir;
bir IOC iddiasının geri çekilmesi olarak etiketlenmez. Karar zamanı teknik
gözlem zamanı değildir. Üst düzey karşılaştırma/özet modeli 1 kalır.

DB migration gerekmez, fakat eski motor yeni model 2 incelemeyi okuyamaz.
Geri dönülecekse yükseltme öncesi uygun yedek kullanılmalı. Firma yedeği
çekirdek ve kuyruk birlikte; kişisel `backup` yalnız çekirdektir (N-015).
Tarihî model 1 sonuçlarını okuyabilme, eski motorun yeni veriyi okuyabildiği
anlamına gelmez. [Modelin kapsamı](RESEARCH.md#tedarikçi-adayları-ve-insan-kararları).

0.159.0 CNAME ve gözlenmiş TLS bağlantılarını da inceleme içinde saklar.
Politika `research-priority-v2` olur. Önceki v1 incelemeler özgün haliyle
okunur; yeni politikanın ilk kaydı `policy_baseline` üretir, kural değişimi
yeni tehdit veya kanıt geri çekmesi olarak sunulmaz. Sertifika süresinin
yalnız zamanla dolması `time_only` değişimidir; eski kanıt silinmez.
Şema 75 kullanan alanda bu teslim için yeni migration gerekmez.

Eski kayıt alanında bir kez açık ve yedekli geçiş gerekir:

```sh
./xti migrate
```

Başka veri alanı kullanıyorsanız bütün komutlarda aynı `--data-dir`
seçeneğini kullanın. Firma alanlarının her biri ayrı geçirilir; bu komut
başka bir firmanın verisini taşımaz. Yeni kurulum zaten şema 75 oluşturur.

```sh
./xti research-history record securehup.com --type domain
./xti research-history list securehup.com --type domain
```

İlk kayıt **başlangıç**tır; geçmişte olmayan bir değişim uydurulmaz. Daha
sonra aynı `record` komutunu tekrar çalıştırın. Çıktıda kaydın kimliği,
tarihi, önceki kaydı ve ayrıntıyı açacağınız hazır komut bulunur:

```sh
./xti research-history show KAYIT_KIMLIGI
./xti research-history show KAYIT_KIMLIGI --view items
```

`KAYIT_KIMLIGI` yerine çıktının verdiği gerçek kimliği yazın. İlk görünüm
değişimleri; `--view items` o günkü öğeleri, gerekçeleri ve özgün kanıt
kimliklerini gösterir. JSON için komuttan önce `--json` eklenir.
`list` ve `show` sayfaları varsayılan 20, en fazla 100 kayıt gösterir.
Terminalde sonraki sayfa komutu seçili veri klasörünü korur.

Kayıt almadan yalnız bugünkü değerlendirmeyi görmek için mevcut
`./xti research securehup.com --type domain --priorities` kullanılabilir.
Bu komut geçmişe kayıt eklemez.

## Değişimler nasıl yorumlanır?

| Çıktı | Anlamı |
|---|---|
| `baseline` | Bu kapsamda ilk kayıt; karşılaştırma yok |
| `policy_baseline` | Önceki kayda bağlı ama kural sürümü değişmiş; yeni başlangıç |
| `unchanged` | Karşılaştırılan kanıt, durum ve kapsam bilgisi aynı |
| `changed` | Öğelerde veya kaynak/kapsam bağlamında fark var |
| `entered_view` | Öğe bu incelemenin kapsamına girmiş; internette ilk kez oluştuğu iddiası değil |
| `not_in_current_view` | Önceki öğe bu görünümde yok; tehdit çözüldü veya iddia geri çekildi demek değil |
| `time_only` | Kayıtlı kanıt aynı; güncellik/geçerlilik değerlendirmesi zamanla değişmiş |
| `evidence_or_mixed` | Kanıt veya kaynak bağlamı değişmiş; zamanın etkisi de bulunabilir |

Önce/sonra öncelikleri ve kural kodları birlikte döner. Açık geri çekme
yalnız **aynı kaynak iddiasının** durumunun `revoked` olmasıyla belirtilir;
geçerlilik süresinin dolması veya görünümden çıkması geri çekme sayılmaz.
Bir URL arşivi yenilenince makbuz/ilişki kimliğinin değişmesi, aynı yönlü
bağı kaldırılıp yeniden bulunmuş gibi göstermez; özgün kimlikler korunur.
`context_changed/context_origin` liste ve kapsam değişimini ayrıca açıklar.

Karşılaştırma anahtarı normalize edilmiş tür/değer, ilişki adımı, düğüm
sınırı, ilişki sınırı ve güncellik eşiğidir. Bu seçeneklerden biri değişirse
ayrı başlangıç oluşur. Kayıt varsayılan olarak en fazla iki ilişki adımını,
100 düğüm ve 200 ilişkiyi içerir; sayfadaki ilk 20 öğeyle sınırlı değildir.
Eksik kapsam her kayıtla saklanır ve karşılaştırmada görünür kalır.

## Tekrarlanan istekler ve eşzamanlılık

CLI her `record` için yeni bir anahtar üretir. Bağlantı/çıktı kesintisinde
aynı isteği güvenle tekrar edebilmek için anahtarı önceden verin:

```sh
./xti research-history record securehup.com --type domain --idempotency-key securehup-inceleme-20261117-1
```

Aynı veri alanı + anahtar + normalize kapsam mevcut kaydı döndürür;
yeniden değerlendirme veya ikinci yazma yapmaz. Sonraki yeni inceleme için
yeni anahtar kullanın. Aynı anahtarı farklı kapsamda kullanmak
`idempotency_conflict` verir. Eşzamanlı başka inceleme önce kaydedilirse
`review_changed` döner; istemci güncel başlangıçla açıkça tekrar deneyebilir.
Saat önceki incelemeden geriye giderse `clock_regression` ile yazma durur.

Kanıtın toplanması tek okuma kesitindedir. Ardından ayrı, kısa yazma
transaction'ı önceki kayıt kimliğini denetler ve yeni kaydı atomik ekler.
Arada kaynaklar güncellenebilir; kayıt, `checked_at` anındaki okuma kesitini
temsil eder. İki aşama tek veritabanı transaction'ı gibi sunulmaz.

## Engine ve firma platformu

Kişisel `engine` ve firma `platform request` iki salt okuma işlemini paylaşır:

```json
{"contract_version":1,"request_id":"gecmis-1","operation":"research.history","parameters":{"indicator_type":"domain","value":"securehup.com","offset":0,"limit":20}}
```

```json
{"contract_version":1,"request_id":"ayrinti-1","operation":"research.review.get","parameters":{"review_id":"KAYIT_UUID","view":"changes","offset":0,"limit":20}}
```

`research.history`: `records`, `total_count`, `snapshot_id`, sayfa alanları
ve `integrity_check=metadata_and_parent_links` döner. Kök için farklı
kapsamların geçmişi de listelenir; her kaydın `query` alanı gösterilir.
Sonraki sayfada `expected_snapshot` olarak ilk cevabın `snapshot_id`
değerini kullanın. Araya kayıt girerse `snapshot_changed` ile durur.

`research.review.get`: `review`, `view`, `changes` veya `evaluation`,
sayfa alanları ve `integrity_check=content_and_comparison` döner. `items`
görünümünde `evaluation` o günkü öncelik modelini ve bu sayfanın öğelerini
içerir; `changes` görünümünde `evaluation=null` olur. Sabit kayıt kimliğiyle
sayfalama bugünkü saat veya yeni incelemelerle değişmez.

Yeni kayıt **yalnız firma platformunda** şu işlemle alınabilir:

```json
{"contract_version":1,"request_id":"kaydet-1","operation":"research.review.record","parameters":{"indicator_type":"domain","value":"securehup.com","idempotency_key":"inceleme-1","expected_workspace_id":"GUNCEL_FIRMA_ALANI_UUID"}}
```

UUID yer tutucularını gerçek kimliklerle değiştirin. Firma, güvenilen
başlatıcının `--company` seçiminden gelir; JSON firma veya dosya yolu
seçemez. `expected_workspace_id`, güncel firma cevabının `scope.workspace_id`
değeridir; yedekten dönüşte eski kimlikle yazma veya tekrar isteği reddedilir.
Kimlik doğrulama ve kullanıcı yetkisi çağıran platforma aittir.

Kayıt cevabı `review`, `replayed`, `network_access=false` içerir. `review`:
`id`, `query`, `scope_key`, kapsam içi `sequence`, `idempotency_key`,
`previous_id`, `checked_at`, `policy_version`, içerik özetleri ve
`comparison` özetidir. Kayıtta aynı kapsam seçenekleri CLI ile paylaşılır.
Anahtar ve firma alanı kimliği platform isteğinde zorunludur. Yerel
`engine` içinde `research.review.record` desteklenmez.

| Hata | Protokol çıkış kodu | Davranış |
|---|---|---|
| `invalid_parameters` | 2 | Tip, sınır veya bilinmeyen seçenek hatası |
| `not_found` | 3 | İnceleme seçili alanda yok; başka firma aranmaz |
| `snapshot_changed` | 1 | Geçmiş listesinin ilk sayfasından yeniden başlayın |
| `scope_mismatch` | 1 | Güncel firma alanı kimliğini alın |
| `idempotency_conflict` | 1 | Anahtar başka kapsam için kullanılmış |
| `review_changed` | 1 | Araya aynı kapsamda başka inceleme girmiş |
| `clock_regression` | 1 | Sistem saati önceki kayıt zamanından eski |
| `storage_error` | 1 | Şema, kayıt veya bağlı içerik doğrulanamadı |

Başarı 0'dır. Yerel genel CLI geçersiz seçenek için `validation_error`
adıyla 2 döner; protokolün `invalid_parameters` karşılığıdır.

## Saklama, yedek ve sınırlar

Şema 75 tek `research_reviews` tablosu ve kök dizini ekler. Mevcut tabloların
verileri değiştirilmez. `migrate` önce benzersiz yedek alır; kesintide geçiş
geri alınır. Normal SQLite/platform yedeği kayıtları, önceki kayıt bağlarını
ve tekrar anahtarlarını birlikte korur. Eski koda dönüş, geçiş öncesi yedeği
ayrı boş alana açarak yapılır; mevcut veritabanının üstüne restore yapılmaz.

Her kayıt en fazla 8 MiB inceleme, 4 MiB karşılaştırma saklar. Sınır aşılırsa
eksik kayıt yazmak yerine dar kapsam istenir. Geçmiş sayfalıdır; geçmiş
sayısı arttı diye bütün kayıtları belleğe alma veya topluca reddetme yoktur.
Otomatik geçmiş temizliği henüz yoktur; disk takibi ve yedek işletici işidir.
Tekrar anahtarlarını silen bir temizleme mekanizması eklenmemiştir.

Listeleme kimlik/özet ve doğrudan önceki kayıt bağını denetler. Ayrıntı ve
tekrar isteği seçili içeriğin hash/modelini ve önceki içerikle farkını
doğrular; bütün tarihçeyi baştan sona taramaz. Hash'ler bozulma denetimidir,
sunucu hesabını kontrol eden kişiye karşı imza veya bağımsız denetim kanıtı
değildir. Eski içerik bugünkü kaynak veya yeni öncelik kurallarıyla tekrar
yorumlanmaz. Model/politika değişirse önceki okuma desteği korunmalıdır.

Bu dilim zamanlayıcı, otomatik alarm/bildirim, firma geneli analist kuyruğu
veya anlamsal çelişki çözümü eklemez. Geniş STIX/TAXII ve LLM en son kalır.
Kaynak lisansları ve canlı kabul eksikleri [NOTES.md](../NOTES.md) içinde
izlenir. [Mimari karar](decisions/0160-frozen-research-reviews.md).
