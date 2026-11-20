# Kayıtlı grupların takibi ve geçmişinin korunması

0.178.0 · çekirdek88 · kaynak işi modeli7 · kuyruk3 · dış JSONv1.

Kaydettiğin inceleme grubunu mevcut iş kuyruğuyla yeniden kontrol
edebilirsin. Örneğin aynı IP'de gözlenen iki domaine üçüncüsü eklendiğinde
grubun önceki ve sonraki kanıtı bildirimde görünür. İnsan kararı korunur;
değişen kanıtın yeniden incelenmesi gerektiği ayrıca belirtilir.

Grup kontrolü motorun saklı verisini okur. İnternetten veri almak için
mevcut kaynak işlerini veya toplama akışlarını ayrıca çalıştırırsın.
Yalnız `group-refresh` seçilen işin dış istek sayısı sıfırdır.

## Bir grubu kuyrukla kontrol etme

Önce [grup önizleme ve kaydetme](RESEARCH_GROUPS.md#kaydetme-karar-ve-değişiklik)
adımlarıyla grup oluşturulmuş olmalı. `GRUP` kayıtlı kimliktir;
`example.com` yerine o grubun kökünü yaz. Farklı firma veya kök reddedilir.
Yerel kuyruk hiç kurulmadıysa bir kez `./xti source-jobs init` gerekir.
Var olan kuyruk yeniden oluşturulmaz.

```sh
./xti source-jobs plan example.com --type domain --source group-refresh --group GRUP
./xti source-jobs submit example.com --type domain --source group-refresh --group GRUP \
  --idempotency-key grup-kontrol-1
./xti source-jobs worker --job-id IS_KIMLIGI
./xti source-jobs status IS_KIMLIGI
./xti source-jobs result IS_KIMLIGI
```

Plan grubun kayıtlı kapsamını ve o anki sürümünü gösterir. Grubun araştırma
adımı/zaman penceresi ilk kayıttaki kapsamdan gelir; kaynak işinin genel
`--max-hops` seçeneği bu kapsamı değiştirmez. İş beklerken insan yeni karar
vermişse worker en güncel kayıt üzerinden kontrol eder, kararı ezmez.

Aynı tamamlanmış işi aynı anahtarla göndermek ilk sonucu getirir. Yeni
kontrol için yeni anahtar gerekir. Birden fazla kaynak seçildiğinde açık
`--step` sırasını ver; `group-refresh` kaynak adımlarından sonra olmalıdır.
`relationship-notify` varsa kendi son adım kuralı korunur. Sonradan gelen
veriyle grubu tekrar değerlendirmek, önceki değişmez iş sonucunu değiştirmez.

## Düzenli kontrol ve bildirim

```sh
./xti groups monitor GRUP --queued --rounds 3 --interval-seconds 60
./xti groups notifications --limit 20
./xti groups notification-show BILDIRIM_KIMLIGI
./xti inbox show BILDIRIM_KIMLIGI
```

`--queued` her turu mevcut kuyrukta ayrı bir iş olarak yürütür. Tur sayısı
1–100, aralık 1–3600 saniyedir. Beklerken yazıcı kilidi tutulmaz; bu komut
kendiliğinden sürekli sunucu hizmeti kurmaz. Başka bir zamanlayıcı da aynı
iş gönderme arayüzünü kullanabilir. `--queued` olmadan önceki doğrudan
terminal monitor davranışı korunur.

| Kontrol sonucu | Bildirim davranışı |
| --- | --- |
| İlk kayıt veya aynı kanıt | Sessiz; kontrol geçmişi korunur |
| Tam kontrolde üye/dayanak/zaman değişti | Önceki ve sonraki kanıtla tek bildirim |
| Tam kontrolde grup görünümden çıktı veya geri geldi | Görünürlük değişikliği; gerçek dünyada silinme iddiası değildir |
| Eksik veya sınırda kalan kanıt | `indeterminate`; kesin kayıp bildirimi yok |

Bildirim okunması insanın grup kararını değiştirmez. Sonraki kontroller
eski bildirimin kanıtını güncellemez. `groups.notifications` özetleri
sayfalar; tam kanıt `groups.notification-show` ile açılır. Bildirim ile
grup değişikliği aynı veritabanı işlemi içinde yazılır; biri yazılamazsa
ikisi birlikte geri alınır. Eski sürümdeki değişikliklere geriye dönük
bildirim üretilmez.

## Kesinti, iptal ve yeniden deneme

Kuyruktaki iş başlamadan iptal edilebilir. Çalışan işte mevcut işçi iptal
kuralı geçerlidir; bitmiş bir kontrol geri alınmaz. Süreç kesildiğinde
`source-jobs recover` veya firma alanında `platform recover` kullanılır.
Bu işlem kendi başına tekrar kontrol veya dış istek göndermez.

Açık `source-jobs retry` yeni iş oluşturur. Ortak kuyruk, sonucu belirsiz
iş için `--allow-uncertain` ister; karma işte bunun dış kaynak tekrarına
da izin verdiği unutulmamalıdır. Grup sonucu çekirdeğe yazılmış ama kuyruk
ilerlemesi kaydedilememişse eski işlem anahtarından özgün sonuç bulunur.
Kontrol/bildirim çoğalmaz. Tamamlanmış kısmi sonuçtan sonra yapılan yeni
retry ise yeni kanıtı kontrol eder. Arşivlenmiş eski makbuz da okunur.

## Geçmişi silmeden arşivleme

Grup geçmişi mevcut `journals` arşivine dahildir:

```sh
./xti journals status
./xti journals archive-plan --older-than-days 90 --limit 500
./xti journals archive-apply --older-than-days 90 --limit 500 --token PLAN_KIMLIGI
./xti journals show ARSIV_ISLEMI
./xti journals restore ARSIV_ISLEMI
```

Plan rapor/kanıt/sosyal/grup günlüklerini birlikte değerlendirir; yalnız
gruba özel bir silme işlemi değildir. Uygulamadan önce seçilen kayıtları
kontrol et. En güncel grup olayı açık kalır. Eski uygun gövdeler aynı
veritabanında sıkıştırılır; kimlik, sıra, özgün hash ve tekrar anahtarı
korunur. Uygula ve geri aç işlemleri önce ayrı doğrulanmış yedek alır.
Eski kanıtlar, bildirimler ve vakalar arşivden aynı şekilde okunur.

0.178.0'da yeni olayların toplam günlük sınırı yerine indeksli güncel durum
ve sayfalı geçmiş kullanılır. Değişmeyen kontroller aynı kanıtı kopyalamaz.
Eski tam `groups show` yanıtı 1000 olay/4 MiB ile sınırlıdır; büyük geçmiş
`groups current/history/changes` ile açılır. Her kontrolün zamanı/anahtarı
saklandığı için disk büyür. Kaynak okuma bütçeleri ve yedek maliyeti sürer.
[Güncel kapasite ve denetim düzeni](GROUP_CAPACITY.md).

## Firma ve JSON bağlantısı

Mevcut `sources.plan`, `sources.jobs.submit/status/result/cancel/retry`
ve `platform worker` kullanılır. Kaynak seçimi:

```json
{
  "indicator_type": "domain",
  "value": "example.com",
  "sources": ["group-refresh"],
  "group_id": "KAYITLI_64_HEX_GRUP_KIMLIGI"
}
```

Bu, `sources.plan` parametre örneğidir; gönderimde planın kanonik alanları,
`plan_sha256`, `idempotency_key` ve güncel `expected_workspace_id` gerekir.
[Ortak iş sözleşmesi](SOURCE_JOBS.md) geçerlidir. İş makbuzu `kind`,
`group_id`, `event_id`, `revision`, `state_sha256`, `group_status`,
`source_status`, `notification_id` ve mevcut `usage` alanını taşır.

`groups.notifications` (`offset,limit,expected_snapshot`) ve
`groups.notification-show` (`identifier`: bildirim UUID'si) hem engine
hem firma JSON girişinde salt okunurdur. Tam yanıt
`data.notification.snapshot.before/after/change` içindedir. Grup kimliği
ile bildirim kimliği farklıdır. Başka firma kaydına erişim `not_found`,
eski firma alanıyla yazma `scope_mismatch` olur.

## Yükseltme ve doğrulama

```sh
git pull --ff-only
./xti migrate
./xti doctor
```

86→87 geçişi yedeklidir; yeni bildirim tablosu eklenir, eski tablolar ve
grup kayıtları değişmez. Kuyruk3 aynı kalır; yeni kaynak işleri model7,
eski modeller1–6 kendi makbuzlarıyla okunur. Eski motor şema87'yi açmaz.
Geri dönüş gerekirse yükseltme öncesi yedek boş hedefe eski kodla geri
yüklenir; yükseltmeden sonraki yeni veriler o eski yedekte bulunmaz.
Firma için çekirdek ve kuyruk birlikte `platform backup/restore` ile
korunur. Restore yeni workspace kimliği üretir.

[Kabul ve teslim kaydı](roadmap/GROUP_OPERATIONS_DELIVERY.md),
[mimari karar](decisions/0182-managed-group-checks-and-lossless-history.md).
