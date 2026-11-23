# Kuruluş verisi saklama, koruma ve arşiv

XTI 0.192.0 / P08+P12, eski birleşik izleme ve normalize telemetri
kanıtlarının JSON gövdelerini kuruluş politikasıyla kayıpsız sıkıştırır.
Kayıt kimliği, hash, zaman, alarm, sürüm, insan kararı ve vaka bağı silinmez.
Arşivlenmiş kanıt normal `monitoring.*` ve `telemetry.*` okumalarında aynı
sonuçla açılır.

Bu paket genel bir “bütün tabloları süre dolunca sil” özelliği değildir.
Açıkça yönetilen aileler `unified_monitoring_runs` ve `telemetry_records`
gövdeleridir. Bilinmeyen bir aile kapalı biçimde reddedilir. Eski `journals.*`
belge arşivi kendi mevcut yaşam döngüsünü korur.

## Güvenli başlangıç

Mevcut veri alanını önce şema 99'a yükselt:

```sh
./xti migrate
./xti retention capabilities
./xti retention catalog
```

`migrate`, eski veri alanını değiştirmeden önce kurtarma yedeği üretir. Şema
98→99 geçişi mevcut P08 politika, hold, arşiv ve audit kimliklerini korur.
Politika oluşturmak için kuruluş UUID'si gerekir:

```sh
./xti retention policy-add \
  --name "90 günlük izleme gövdesi" \
  --organization ORGANIZATION_UUID \
  --family unified_monitoring_runs \
  --family telemetry_records \
  --archive-after-days 90 \
  --batch-limit 100 \
  --purpose "Güvenlik izleme kanıtı" \
  --retention-basis "Kuruluşça onaylanan saklama politikası" \
  --actor privacy-operator \
  --reason "Onaylanan yaşam döngüsü politikası" \
  --idempotency-key retention-policy-1
```

`actor` güvenilir kullanıcı kimliği değildir; motorun çağırandan aldığı
denetim değeridir. Üretimde .NET/backend bu alanı oturumdan üretmeli,
kullanıcının serbest metin olarak değiştirmesine izin vermemelidir.

## Önizleme ve uygulama

Önce yazmasız plan al:

```sh
./xti retention plan POLICY_UUID
```

Plan; veri ailesi bazında kesim zamanını, uygun/seçilen/kalan sayısını, vaka veya açık koruma
nedeniyle atlanan kayıtları, ham ve sıkıştırılmış gövde boyutunu ve SHA-256
önizleme kimliğini gösterir. Uygulama aynı politika revision'ı ve token ile
yapılır:

```sh
./xti retention apply POLICY_UUID \
  --expected-revision 1 \
  --token PLAN_SHA256 \
  --actor privacy-operator \
  --reason "Onaylanan arşiv partisi" \
  --idempotency-key retention-batch-2026-11-22-1
```

Plan ile uygulama arasında politika, uygun kayıt, gövde hash'i, koruma veya
vaka bağı değişirse işlem yazmadan durur. Her parti en fazla politikanın
`batch_limit` değeri kadar kayıt işler. Uygulama, gövde değişmeden önce tam
SQLite kurtarma yedeği alır.

## Koruma (hold)

Kuruluşun tamamını, tek izleme çalışmasını veya tek telemetri kaydını saklama
politikasından koruyabilirsin:

```sh
./xti retention hold-add \
  --organization ORGANIZATION_UUID \
  --family unified_monitoring_runs \
  --record-id MONITORING_RUN_UUID \
  --kind investigation \
  --actor analyst \
  --reason "Aktif inceleme tamamlanmadı" \
  --idempotency-key hold-1

./xti retention hold-release HOLD_UUID \
  --expected-revision 1 \
  --actor analyst \
  --reason "İnceleme tamamlandı" \
  --idempotency-key hold-release-1
```

Türler `legal`, `case`, `investigation` ve `contractual`dır. `case` türünde
geçerli vaka kimliği zorunludur. Ayrıca aktif `unified_monitoring` vaka
kanıtına kaynak olan izleme çalışmaları politika planından otomatik çıkarılır.
Tek kapsam üzerinde birden fazla bağımsız hold aynı anda bulunabilir; birini
kaldırmak diğerinin korumasını kaldırmaz.
Motor bunun hukuken yeterli bir legal-hold süreci olduğunu iddia etmez.

Telemetri için aynı komutta `--family telemetry_records` ve
`--record-id TELEMETRY_RECORD_UUID` kullanılır. Aktif `telemetry` vaka kanıtı
olan kayıtlar da otomatik korunur. Sonradan değişen bir telemetri kaydı yeni
sürüm üretirse eski arşiv bozulmaz; zamanı geldiğinde yeni sıcak sürüm ayrı,
geri alınabilir bir arşiv nesli olur.

## Geçmiş, denetim, geri yükleme ve kurtarma

```sh
./xti retention policies --organization ORGANIZATION_UUID --limit 20
./xti retention holds --organization ORGANIZATION_UUID --active --limit 20
./xti retention runs --policy-id POLICY_UUID --limit 20
./xti retention run-show RETENTION_RUN_UUID
./xti retention audit --organization ORGANIZATION_UUID --limit 100

./xti retention restore ARCHIVE_RUN_UUID \
  --actor privacy-operator \
  --reason "Kontrollü sıcak geri yükleme" \
  --idempotency-key restore-1

./xti retention recover POLICY_UUID \
  --actor operator \
  --reason "Kesilen süreç açıkça kapatıldı" \
  --idempotency-key recover-1
```

Liste işlemleri `--after` ve `--limit` ile sıralı sayfalanır. Denetim
olayları aktör, gerekçe, kaynak kimliği, ayrıntı hash'i ve önceki olay
hash'iyle zincirlidir; zincir bozulursa okuma/yazma kapalı biçimde durur.
`recover` yarım `running` çalışmaları `interrupted` yapar; kaynak gövdesini
silmez ve işi kendiliğinden tekrar çalıştırmaz.

Geri yükleme sıkıştırılmış gövdeyi kanonik JSON/hash doğrulamasından geçirir,
önce yedek alır ve sıcak satıra koyar. Aynı tamamlanmış arşiv ikinci kez yeni
bir anahtarla boş geri yükleme oluşturamaz.

## Engine ve firma platformu

Salt-okunur engine işlemleri:

- `retention.capabilities`, `retention.catalog`
- `retention.policies`, `retention.policy.show`, `retention.plan`
- `retention.runs`, `retention.run.show`
- `retention.holds`, `retention.hold.show`, `retention.audit`

Firma platformu bunlara ek olarak şunları yazar:

- `retention.policy.add/update/disable`
- `retention.hold.add/release`
- `retention.apply`, `retention.restore`, `retention.recover`

Her platform yazması güncel `expected_workspace_id` ister. Politika ve hold
değişimleri revision, bütün mutasyonlar idempotency anahtarıyla korunur.
Başka firma veri alanındaki kimlik `not_found`, eski workspace
`scope_mismatch` olur. Kimlik doğrulama, RBAC, scheduler ve kullanıcıya
gösterilecek onay ekranı tüketici platformun sorumluluğudur.

## Depolama ve doğruluk sınırları

- Arşiv kayıpsız zlib gövdesidir; her açılışta kanonik JSON ve SHA-256
  doğrulanır. Bu hash dijital imza veya kullanıcı kimliği kanıtı değildir.
- Mantıksal izleme/telemetri kaydı, alarm, sürüm, review, vaka kanıtı ve
  provenance silinmez.
- Sıkıştırılmış gövde aynı SQLite veri alanındadır. Serbest SQLite sayfaları
  daha sonra yeniden kullanılabilir; dosyanın fiziksel boyutu `VACUUM`
  olmadan hemen küçülmeyebilir. P08 otomatik `VACUUM` çalıştırmaz.
- Aktif arşiv için koruyucu sınırlar 512 MiB ham ve 256 MiB sıkıştırılmış
  gövdedir; 50.000 arşiv kalemi ve 50.000 audit olayı aşıldığında otomatik
  silme yerine açık kapasite hatası oluşur.
- Bu teknik kontroller GDPR, KVKK, CCPA veya başka bir mevzuata uygunluk
  sertifikası değildir. Amaç/dayanak metni, erişim kararı, saklama süresi,
  legal hold, veri sahibi talebi ve bölgesel yerleşim kuruluşun hukuk ve
  işletim sürecinde tanımlanmalıdır.
- P08 yeni ağ isteği, dış repo, ücretli API veya Python paketi eklemez.

Mimari kararlar: [ADR0193](decisions/0193-organization-retention-and-audit.md)
ve [ADR0197](decisions/0197-telemetry-retention-generations.md).
Teslim/kapasite kanıtı: [P08 teslim kartı](roadmap/P08_DELIVERY.md).
