# Yayın metni, yeniden inceleme ve kayıt saklama

19 Kasım 2026 — 0.169.0, çekirdek şema 79. Kuyruk 3, kaynak işi 4,
araştırma modeli 3 ve dış JSON sözleşmesi 1 korunur.

Bu teslim üç iş ekler: izinli yayıncının makale/PDF metnini kaydetmek,
dayanağı değişen insan ilişki kararlarını yeniden incelemek ve eski günlük
gövdelerini geçmişi silmeden sıkıştırmak. Terminal ile firma kapsamlı
JSON aynı uygulama servislerini kullanır.

## Kurulum ve güncelleme

Yeni klonda `./setup` yeterlidir. Mevcut veri alanını güncellerken önce
açık toplama/worker süreçlerini bitir, sonra repo klasöründe:

```sh
git pull --ff-only
./xti migrate
./setup
./xti reports publishers
```

`migrate` geçiş öncesi yedeği alır; mevcut şema zaten 79 ise değişiklik
yapmaz. Bu sıra, eski şemanın `./setup` sonundaki `init` adımında ret
vermesini önler. Farklı veri dizini kullanıyorsan aynı `XTI_DATA_DIR`
ayarı veya `--data-dir` seçimi korunmalıdır.

Normal kurulum artık `brand,news,reports` paketlerini birlikte doğrular.
PDF için **pypdf 7.1.1** sabittir; ücretli API/anahtar gerekmez. Çekirdek
kurulumunda HTML kullanılabilir, PDF bağımlılığı eksikse açık kurulum
hatası verilir. CI, `requirements/reports.txt` içindeki wheel SHA-256
ile paketi doğrular; normal kurulum `constraints/brand.txt` sürüm pin'ini
kullanır. OCR veya ek kriptografi paketi kurulmaz.

`migrate` önce eski veritabanını ayrı dosyaya yedekler, dört yeni tablo
ekler; eski günlükleri yeniden yazmaz. Kuyruk zaten 3 ise kuyruk geçişi
gerekmez. Firma kurulumu için yönetici `platform backup` alıp seçili
firmanın veri dizininde `--data-dir ... migrate` çalıştırır. Restore yeni,
boş hedefe yapılır; eski kodla dönüşte geçiş öncesi yedek kullanılır.

## İzinli yayıncıdan metin al

```sh
./xti reports fetch \
  'https://cert.cyber.gouv.fr/cti/CERTFR-2026-CTI-010/' \
  --provider cert-fr --idempotency-key cert-fr-html-001

./xti reports fetch \
  'https://cert.cyber.gouv.fr/uploads/CERTFR-2026-CTI-010.pdf' \
  --provider cert-fr --idempotency-key cert-fr-pdf-001

./xti reports list --source publisher
./xti reports show RAPOR_KIMLIGI
./xti reports fetches
./xti reports fetch-show CALISMA_KIMLIGI
```

İkinci yayıncı `ncsc`'dir. Örnek:
`https://www.ncsc.gov.uk/collection/top-tips-for-staying-secure-online`.
`reports publishers` izinli host ve içerik yollarını gösterir. HTML
sayfasındaki PDF bağlantıları otomatik izlenmez; PDF'nin URL'si açıkça
verilir. Rastgele siteler, oturum isteyen sayfalar ve arama motorları bu
işlemin kapsamına girmez.

Sonuçta kaynak URL'si, alınma zamanı, yayıncı/atıf/lisans bağlantıları,
ayrıştırıcı sürümü, özgün içerik SHA-256'sı ve metin yer alır. Özgün HTML
veya PDF sıkıştırılarak aynı veritabanında korunur. Belge modeli 2 tam
metin çıkarımını; önceki model 1 saklı başlık/özeti temsil eder. Yayın
tarihi bu ilk adaptörde sayfadan tahmin edilmez; `unknown` kalır.

Metinde IP/domain/hash geçmesi yalnız araştırma adayıdır. Kaynakta geçen
bir kurumu otomatik müşteri varlığı veya bir göstergeyi zararlı yapmaz.
Mevcut `observations`, `research`, `record.get` ve `reports link` aynı
belge sürümünü kullanır. Rapor kimliği yayıncı + istenen URL'ye bağlıdır;
HTML/PDF veya eski/yeni host adresleri otomatik birleştirilmez.

**Tekrar davranışı:** Aynı istek anahtarı ilk sonucu döndürür ve yeniden
internete çıkmaz. Başarısız deneme de makbuz olarak korunur; yeniden
denemek için yeni anahtar gerekir. Yeni anahtar + aynı içerik yeni belge
oluşturmaz. Özgün gövde, çıkarılmış metin veya anlamlı kaynak metaverisi
değişirse yeni sürüm saklanır. Eski belge ve insan bağlantıları korunur.
HTML'nin metin dışı yapısının değişmesi de özgün gövde hash'ini değiştirir;
bu durum otomatik tehdit veya alarm değildir.

**Sınırlar:** Yanıt en fazla 8 MiB, çıkarılmış metin 64 KiB, PDF 80 sayfa.
Mevcut rapor çıkarımı tek belgede 200 gösterge adayıyla sınırlıdır; aşımda
eksik aday listesiyle belge kaydedilmez. Depo/rapor kapasitesi retleri
validation/storage hatasıdır; kaynak hatası makbuzundan ayrı değerlendirilir.
PDF ayrı süreçte 18 saniye duvar süresi, 12 saniye CPU, sınırlı çıktı ve
dosya tanıtıcısıyla okunur; Linux'ta ayrıca 768 MiB adres alanı sınırı
vardır. macOS'ta aynı bellek sınırı garanti edilmez. PDF metni görsel/OCR
içermez; `text_complete` çıkarılmış metnin kesilmediğini belirtir, belgenin
görsellerinin veya her yazı katmanının çözüldüğünün garantisi değildir.
Boş, şifreli, bozuk veya sınırı aşan belge kısaltılarak başarılı gösterilmez.
HTML yalnız ana içerik alanından okunur; scriptler çalıştırılmaz.

HTTPS adresleri her yönlendirmede yayıncı kapsamına karşı kontrol edilir;
DNS yalnız genel IP'ye çözülmeli, bağlantı bu IP'ye sabitlenmelidir. DNS
çözümlemesi 10 saniyelik ayrı süreçtedir. En fazla üç yönlendirme, bağlantı
başına en fazla 20 saniye bekleme ve gövde okumasında 60 saniyelik bütçe
uygulanır. Ortam proxy/cookie/API anahtarı aktarılmaz. Alım eşzamanlıdır;
firma yazıcı kilidi işlem boyunca tutulur. Otomatik kaynak kuyruğu bu
teslimde rastgele tam metin URL'leri çalıştırmaz.

Yayıncı çalışma günlüğü en fazla 10.000 kayıt/16 MiB; özgün nesne deposu
64 MiB açılmış gövde ile sınırlıdır. Kaynak başarısızlığı `reports fetches`
içinde görünür, önceki başarılı belgeyi silmez. Ayrı genel kaynak durumu
yerine bu işlem ailesinin çalışma geçmişi kullanılır.

## Dayanağı değişen ilişkiyi yeniden incele

```sh
./xti relationships queue
./xti relationships queue --indicator-type ipv4 --value 192.0.2.10
./xti relationships show ILISKI_KIMLIGI
./xti relationships candidates ipv4 192.0.2.10
```

Liste eski insan kararını güncel kayıtlı dayanakla karşılaştırır:

| Durum | Anlamı |
| --- | --- |
| `evidence_changed` | Kararın dayanağı değişmiş. |
| `historical_evidence` | Dayanak tarihî veya geri çekilmiş kanıt içeriyor. |
| `evidence_outside_current_view` | Eski aday güncel yerel görünümde yok; geçmiş karar duruyor. |
| `indeterminate` | Görünüm kısmi; dayanağın kaybolduğu söylenemez. |

Yeni karar mevcut `relationships review` komutuyla, **güncel**
`evidence_sha256`, önceki `revision`, açık gerekçe ve yeni tekrar
anahtarıyla verilir. Aynı güncel kanıta karar verilince kayıt listeden
çıkar. Önceki karar silinmez. Artık görünmeyen aday için eski kanıtla
`withdrawn` kararı verilebilir; bu veri silme değildir.

Pencere varsayılan/en fazla **20 karar** inceler. `pending_in_window`
yalnız bu pencerenin bekleyenleridir; `total_review_count` toplam kayıtlı
karardır, toplam bekleyen sayısı değildir. Bekleyen sıfır olsa da
`has_more=true` olabilir. `offset` incelenen kararlar üzerinde ilerler.
`expected_snapshot` karar listesini sabitler; kanıt her pencerede yeniden
okunur. Sayfalar arasında tek kanıt kesiti iddia edilmez;
`evidence_snapshot_id` pencerenin güncel dayanağını belirtir.

## Eski günlük gövdelerini arşivle

```sh
./xti journals status
./xti journals archive-plan --older-than-days 90 --limit 500
./xti journals archive-apply --older-than-days 90 --limit 500 --token PLAN_KIMLIGI
./xti journals show ARSIV_ISLEM_KIMLIGI
./xti journals restore ARSIV_ISLEM_KIMLIGI
```

Plan kişisel/firma veritabanına ve güncel günlük zincirlerine bağlıdır.
Veri, gün veya çalışma alanı değişirse yeni plan alınmalıdır. Saklama
eşiği 7–3650 gün, işlem penceresi 1–1000 kayıttır. Her rapor/görülme/ilişki
konusunun son günlük girdisi açık gövdeli kalır. Yakın kayıtlar ve
sıkıştırıldığında net yer kazanılmayan gövdeler taşınmaz.

Uygulama önce ayrı bir yedek alır. Eski JSON gövdelerini sıkıştırır ve
aynı veritabanındaki arşive taşır. Mantıksal günlük satırı, sıra numarası,
kimliği, hash zinciri ve tekrar anahtarı korunur. Okuyucu arşiv gövdesini
boyut/hash denetiminden geçirerek açar. Bozuk veya eksik gövde boş başarı
olarak sunulmaz. Geri alma da önce yedek alır; arşiv ve geri alma geçmişi
kalır. Aynı arşivi tekrar geri almak değişiklik yapmaz.

Arşiv **silme veya sınırsız ölçekleme değildir**. Önceki mantıksal satır,
tek kayıt ve okuma bütçeleri aynıdır; sıkıştırılmış boyutla sınır aşılmaz.
SQLite boşalan sayfaları yeniden kullanabilir; dosya anında küçülmeyebilir.
Yedekler ayrıca disk kullanır ve otomatik silinmez. Yeni yedek dosyasını
oluşturacak boş alan gerekir. Sıkıştırılmış özgün yayın nesneleri bu
arşiv planıyla silinmez.

Gerçek süreç kesintisinden sonra aynı `archive-apply` yazma işlemiyle
SQLite'ın yarım transaction'ı geri alıp planı yeniden kontrol etmesi
sınandı. Ortam salt okunursa rollback kurtarması yapılamayabilir; böyle
bir durumda yedek yeni boş hedefe geri yüklenir. Platform yedeği bütün
soğuk gövdeleri de içerir; dış dosya arşivine bağımlı değildir.

## JSON sözleşmesi

Motor (`engine`) aşağıdaki okumaları sunar; firma girişi bunlara ek
yazmaları sunar. JSON içinde dosya yolu, firma seçimi veya serbest HTTP
başlığı yoktur. Firma yazmalarında `expected_workspace_id` zorunludur;
restore sonrasında eski workspace reddedilir.

| İşlem | Alanlar |
| --- | --- |
| `reports.publishers` | Yok. Yayıncı politikası ve sınırları. |
| `reports.fetches` | `offset`, `limit` (1–100), `expected_snapshot`. |
| `reports.fetch-show` | `identifier`: çalışma UUID'si. |
| `reports.fetch` — yazma | `provider`, `url`, `idempotency_key`, `expected_workspace_id`. |
| `relationships.queue` | İsteğe bağlı birlikte `indicator_type`, `value`; `offset`, `limit` (1–20), `expected_snapshot`. |
| `journals.status` | Yok. Günlük/nesne boyutları ve son 20 saklama işlemi. |
| `journals.archive-plan` | `older_than_days` (varsayılan 90), `limit` (varsayılan 500). |
| `journals.show` | `identifier`: saklama işlemi UUID'si. |
| `journals.archive-apply` — yazma | Planla aynı `older_than_days`, `limit`, `token`, `expected_workspace_id`. |
| `journals.restore` — yazma | `identifier`: arşiv UUID'si, `expected_workspace_id`. |

`reports.fetch` sonucunda `run`, `record`, `action`, `replayed` bulunur.
`record` önceki rapor sözleşmesidir; `document.model_version=2` yeni tam
metin ve `acquisition` alanını ekler. Eski model 1 okunur. Başarısız
alım hata zarfı döndürür; saklı çalışma `reports.fetches/fetch-show` ile
açılır. `journals.archive-apply/restore` sonucunda `changed_count`,
`backup`, `event` bulunur. İşlem yapılmamışsa yedek/olay `null` olur.

Yaygın hatalar: `source_error` kaynak/PDF hatası, `not_found` bu alanda
kayıt yok, `idempotency_conflict` tekrar anahtarı farklı isteğe bağlı,
`snapshot_changed` plan/liste yenilenmeli, `scope_mismatch` eski/yanlış
firma alanı, `storage_error` saklı kanıt veya depolama hatası.

## Doğrulama ve sonraki kapsam

HTML/PDF canlı denemeleri CERT-FR ve NCSC'nin kamuya açık içeriklerinde
yapıldı; gerçek müşteri hedef taraması değildir. PDF metni ayrı gerçek
süreçte, arşiv kesintisi ayrı gerçek SIGKILL sürecinde sınandı. Firma
izolasyonu, yedek/restore, şema 78 → 79, eski makbuz tekrarı ve bozuk
arşiv için testler vardır. Sayılar ve tam paket sonucu
[kabul kaydındadır](ACCEPTANCE_REVIEW.md).

GitHub/Linux teslimi ayrıca tamamlandı: aynı `071a076` kodunun altı
workflow'u başarılı, 3.187 testlik tam paketi hatasız/atlamasız geçti.
[Linux kabulü](ACCEPTANCE_REVIEW.md#01690--github-ve-linux-teslimi).
LLM, geniş STIX/TAXII, UI/.NET, OCR, dağıtık arşiv ve toplu tam metin
iş kuyruğu bu paketin tamamlanma iddiası değildir.
Kaynak koşulları [NOTES N-029](../NOTES.md#n-029--tam-yayın-metni-yeniden-inceleme-ve-günlük-arşivi)
ve [üçüncü taraf bildiriminde](../THIRD_PARTY.md) takip edilir.
