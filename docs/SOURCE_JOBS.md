# Kaynak güncelleme işleri

18 Kasım 2026 · 0.157.0 · çekirdek şema 75 · iş kuyruğu şeması 2.

URL/hash kaynaklarını ve seçilmiş MISP listelerini bir işe bağlayabilirsin.
İş sıraya girer, açıkça çalıştırılır, her adımın sonucu saklanır. İstersen
son adımda inceleme kaydı alınır ve aynı kapsamın önceki incelemesiyle
karşılaştırılır. Yeni ücretli API, anahtar veya paket gerekmez.

## Terminalden kullanım

Normal `./setup` ile çekirdek alan hazır olmalı. Eski çekirdek için
`./xti migrate` kullan. Yerel iş kuyruğu ilk kez kurulacaksa
`./xti source-jobs init`, eski sürüm 1 kuyruğu varsa
`./xti source-jobs migrate` çalıştır. `init` var olan dosyaya yazmaz.
Yükseltme önce benzersiz, doğrulanmış `.v1-UUID.backup` dosyası oluşturur;
eski profil işleri, anahtarlar ve olay içerikleri korunur. Çalışan veya
kurtarma bekleyen iş varken geçiş reddedilir. Şema 2 zaten varsa değişmez.

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
| Kaynak | En fazla iki; CIRCL/urlscan'den uygun olanı ve isteğe bağlı MISP |
| `--max-requests` | 1–7, varsayılan 7; planın en kötü istek sayısını karşılamalı |
| MISP istek hesabı | Commit + gerekirse koşul belgesi + seçilen her liste için bir istek |
| `--max-seconds` | 1–600, varsayılan 180; adımlar arasında yeni işe başlama sınırı |
| `--record-review` | Varsayılan kapalı; kaynakların ardından aynı kapsamın incelemesini saklar |
| Araştırma | `--max-hops`, `--node-limit`, `--edge-limit`, `--stale-after-hours`; mevcut araştırma sınırları |
| Listeleme | `--offset`, `--limit` (1–100); en yeni iş başta |
| Kuyruk | Aynı alanda bütün iş türleri toplam en fazla 10.000; otomatik silme yok |
| Tekrar zinciri | En fazla 32; eski iş ve tamamlanmış kaynak makbuzları korunur |

Süre sınırı devam eden HTTP çağrısını zorla kesmez; isteğin kendi zaman
aşımı ve boyut sınırı korunur. MISP seçili listeleri tek commit altında
bir adımda indirir; iptal/süre denetimi grubun öncesi ve sonrasındadır.
Toplam süre bu nedenle seçilen adımlar arası bütçeyi aşabilir. Firmalar
arası ortak sağlayıcı kotası henüz yoktur (NOTES N-007).

`complete` seçilen işlemler tamamlandı demektir; tehdit bulunduğu veya
bütün arşivin tarandığı anlamına gelmez. urlscan ilk 20 sonuçla sınırlıdır;
`has_more` makbuzda korunur. `no_match` başarılı boş yanıttır. Başarısız
kaynak adımı son hata makbuzunu taşır; eski geçerli veri silinmez. Bir
kaynak tamamlanıp diğeri başarısızsa iş `partial` olur. İnceleme kaydının
başarısı bütün kaynakları başarısız bir işi başarılıya çevirmez. Ayrıntılı
hata özgün `enrich run-show` / `warninglists run-show` çıktısındadır.

urlscan'e URL, CIRCL'e hash gönderilir; MISP'e araştırılan müşteri değeri
gönderilmez. URL sorgusu yeni tarama başlatmaz. İnceleme kaydı insan
kararını/alarmı değiştirmez. Kaynak atıfları ve ticari kullanım şartları
[NOTES](../NOTES.md) içindedir; kuyruk eklenmesi yeni veri hakkı sağlamaz.

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

Yeni `platform provision` şema 2 kuyruğu oluşturur. Mevcut firma için:

```sh
./xti platform jobs-migrate --root "$PWD/.xti-platform" --company firma-a
```

Gerekliyse çekirdek geçişi ayrıca firma alanında yapılır. İşler mevcut
`platform worker/recover/backup/restore` komutlarını kullanır. Firma
güvenilen başlatıcı tarafından seçilir; JSON keyfî dosya/komut/HTTP adresi
veya farklı firma seçemez.

| İşlem | Parametreler |
|---|---|
| `sources.plan` | `indicator_type`, `value`, `sources`; isteğe bağlı `warninglist_ids`, `record_review`, bütçe ve araştırma kapsamı |
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
