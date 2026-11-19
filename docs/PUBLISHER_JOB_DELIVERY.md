# Seçilmiş rapor işleri, bildirim ve vaka

19 Kasım 2026 · 0.170.0 · çekirdek 80 · kuyruk 3 · kaynak işi modeli 5.

İncelemende kullanacağın belirli CERT-FR/NCSC HTML veya PDF adreslerini
seçip tek işe verebilirsin. Motor her belgenin durumunu, alınan sürümünü
ve kaynak makbuzunu ayrı gösterir. İşin sonunda kayıtlı insan kararlarının
dayanağı değişmişse yerel bildirim oluşturabilir. Bildirimi mevcut vakaya
sen eklersin; kaynak metni veya bildirim kendi başına tehdit kararı değildir.

## Güncelleme ve kullanım

Eski kurulumda `git pull --ff-only`, ardından `./xti migrate` ve `./setup`
çalıştırılır. Migration eski çekirdeği ayrı dosyaya yedekler. Kuyruk zaten
3 ise ek kuyruk geçişi yoktur. İlk yerel kuyruk için bir kez
`./xti source-jobs init` gerekir; firma çalışma alanı bunu provision ile alır.

```sh
./xti source-jobs plan securehup.com --type domain \
  --source publisher --source relationship-notify \
  --document cert-fr https://cert.cyber.gouv.fr/cti/CERTFR-2026-CTI-010/

./xti source-jobs submit securehup.com --type domain \
  --source publisher --source relationship-notify \
  --document cert-fr https://cert.cyber.gouv.fr/cti/CERTFR-2026-CTI-010/ \
  --idempotency-key securehup-report-1

./xti source-jobs worker --job-id IS_KIMLIGI
./xti source-jobs status IS_KIMLIGI
./xti source-jobs result IS_KIMLIGI
./xti source-jobs cancel IS_KIMLIGI
./xti source-jobs retry IS_KIMLIGI --idempotency-key securehup-report-2
```

Buradaki domain inceleme kapsamıdır; seçilen raporun o firmayı anlattığı
iddia edilmez. Firmanın adı için internet araması ayrı `mentions` akışıdır.
Her ek belge için `--document YAYINCI URL` tekrarlanır. İki belge için
`--max-requests 8`, beş belge için `--max-requests 20` verilebilir.
Plan ve submit internete çıkmaz; worker açıkça çalıştırılır.

Her belge en fazla dört HTTP denemesi ayırır: ilk istek ve en fazla üç
yönlendirme. Gerçek denemeler sonuçta ayrıca sayılır. Belge başına mevcut
8 MiB yanıt, 64 KiB metin, 80 PDF sayfası ve ayrıştırıcı süre/bellek sınırları
korunur. Yalnız onaylı yayıncı adresleri kabul edilir.

Bir iş en fazla **beş belge ve toplam altı adım** içerebilir. Örneğin beş
belge + bildirim altı adımdır. Haber yenileme veya inceleme kaydı da
eklenecekse belge sayısı azaltılır; aşım plan aşamasında reddedilir.
Kaynaklar `--step` ile sıralanabilir; `relationship-notify` kaynaklardan
sonra gelmelidir. `--failure-policy continue` kalan belgeleri dener;
`stop` sonraki adımları atlar. Süre/iptal adımlar arasında uygulanır;
başlamış HTTP/PDF işleminin kendi sınırlı tamamlanması beklenir.

Tamamlanan adım tekrar işinde kullanılır. Belge commit edildikten sonra
ilerleme kaydı yazılmadan kesinti olursa `source-jobs recover`, ardından
açık `retry --allow-uncertain` gerekir. Başarılı kalıcı makbuz bulunursa
yeniden indirme yapılmaz. Kalıcı sonuç yoksa dış istek tekrarlanabilir.
Kesilmiş eski işin bilinmeyen istek sayısı sıfır diye gösterilmez.
Başarısız yayıncı makbuzu yeni tekrar işinde yeni anahtarla denenir.

## Bildirimden vakaya

Kuyruk dışında da kayıtlı kararların dayanağı kontrol edilebilir:

```sh
./xti relationships notify domain securehup.com
./xti inbox list
./xti inbox show BILDIRIM_KIMLIGI
./xti relationships notification-show BILDIRIM_KIMLIGI
./xti cases evidence-add VAKA_KIMLIGI --type relationship_review \
  --evidence-id BILDIRIM_KIMLIGI --reason "Değişen rapor dayanağını incele"
```

Bildirim, önceki karar sürümünü/gerekçesini, eski ve yeni kanıtı, kaynak
başvurularını ve kayıt zamanını korur. Aynı karar sürümündeki aynı kanıt
değişikliği ikinci bildirim oluşturmaz; okundu işareti sıfırlanmaz. Yeni
insan kararı bildirimi silmez. Vaka bağlantısı donmuş bildirim kanıtını
saklar; sonraki kaynak ve karar değişiklikleri bu kopyayı değiştirmez.
Araştırma görünümünde vaka açıkça seçilmiş kanıt uçlarına bağlanır.

Eksik/kısıtlı araştırma görünümü kesin kayıp bildirimi üretmez.
`skipped_incomplete_count` bu sayıyı gösterir. Her bildirim adımı en fazla
20 insan kararını inceler. `has_more` varsa `next_offset` ile sonraki
pencere alınır. Terminalde `relationships notify ... --offset N` veya
yalnız `relationship-notify` içeren yeni işte `--notification-offset N`
kullanılır. Aynı planı retry etmek pencereyi kendiliğinden ilerletmez.
Doğrudan bildirim çağrısında `--expected-snapshot` karar listesindeki
değişimi yakalar. Pencereler ortak bir zamana ait kanıt kesiti değildir.

## Firma JSON yüzeyi

Mevcut `sources.plan`, `sources.jobs.submit/status/result/cancel/retry`
korunur. Planın yeni alanı:

```json
{
  "indicator_type": "domain",
  "value": "securehup.com",
  "sources": ["publisher", "relationship-notify"],
  "publisher_documents": [
    {"provider": "cert-fr", "url": "https://cert.cyber.gouv.fr/cti/CERTFR-2026-CTI-010/"}
  ],
  "max_requests": 4,
  "max_seconds": 180
}
```

Submit, planın SHA-256 değeri, tekrar anahtarı ve güncel
`expected_workspace_id` ister. `relationships.notify` platform yazmasıdır;
aynı workspace kimliğini ister. `relationships.notification-show` salt
okunur engine/platform işlemidir. Okuma bilinmeyen/başka firma kimliğinde
`not_found` verir. Vaka ekleme mevcut terminal/uygulama servisi üzerinden
yapılır; bu değişiklik ayrı bir web API veya .NET backend kurmaz.

## Kapasite ve kurtarma kontrolü

```sh
./scripts/python scripts/check-publisher-delivery.py \
  --documents-per-company 40 --output /tmp/xti-publisher-delivery.json
```

Yeni, repo dışı bir çıktı dosyası gerekir. Kontrollü yanıtlarla gerçek
HTML/PDF ayrıştırıcıları, CLI süreçleri, firma kuyrukları, bildirim/vaka,
gerçek SIGKILL kesintisi, arşiv ve çekirdek+kuyruk geri yükleme denenir.
Kodun SHA-256 değeri başlangıç/sonda aynı olmalıdır. Linux için aynı
kontrol `XTI publisher delivery acceptance` adlı açıkça başlatılan
Actions çalışmasında yer alır. Sonuç ve ölçüm ortamı
[kabul kaydında](ACCEPTANCE_REVIEW.md) tutulur.

64 MiB özgün nesne, 32 MiB rapor günlüğü ve 32 MiB/10.000 bildirim
sınırları korunur. Sıkıştırma mantıksal sınırı büyütmez. Bu ölçümün
belge sayısı/süresi dışındaki kapasite veya 7/24 hizmet garantisi çıkarılmaz.
