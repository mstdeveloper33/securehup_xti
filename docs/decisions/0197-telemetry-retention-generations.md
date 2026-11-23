# ADR0197 — Telemetriyi mevcut retention motorunda çok kuşaklı arşivleme

**Tarih:** 23 Kasım 2026
**Durum:** Kabul edildi
**Sürüm/şema:** 0.192.0 / 99

## Bağlam

P12 telemetri kayıtları güncel normalize gövdeyi ve değişmez geçmiş
sürümleri birlikte taşır. Bu gövdeler zamanla büyür. P08 daha önce P07
izleme gövdeleri için kuruluş politikası, hold, aktif vaka koruması,
yedekli arşiv, şeffaf okuma, restore, recovery ve audit sağlıyordu. P12 için
ikinci bir zamanlayıcı, saklama tablosu veya arşiv protokolü yazmak aynı işi
iki kez yapacak ve firma/koruma kurallarının ayrışmasına yol açacaktı.

## Karar

1. P12 `telemetry_records` mevcut P08 retention ailesine eklenir; politika,
   plan, hold, run, receipt, audit, firma sınırı ve idempotency aynen kullanılır.
2. Polimorfik aile/record bağı SQLite'ta tek bir yabancı anahtarla ifade
   edilemediği için parent varlığı ve kuruluş sahipliği her yazmada repository
   guard ile fail-closed doğrulanır.
3. Bir arşiv kuşağı güncel gövdeyi ve o sırada sıcak olan değişmez sürüm
   gövdelerini kanonik, boyut sınırlı, sıkıştırılmış tek pakette tutar. Sıcak
   satırlarda yalnız arşiv kimliği, sürüm ve hash'e bağlı işaretçi kalır.
4. Kayıt sonradan güncellenirse yeni güncel gövde sıcak kalır; eski kuşak
   değiştirilmez. Sonraki politika çalışması ayrı kuşak üretir. Eski kuşağı
   restore etmek daha yeni güncel gövdeyi ezmez; yalnız o kuşağa bağlı
   işaretçileri geri açar.
5. Normal telemetri okuması işaretçiyi şeffaf çözer ve paket/kimlik/aile/
   revision/kanonik JSON/boyut/hash bağlarını doğrular. Her uyuşmazlıkta veri
   uydurmak yerine okuma durur.
6. Açık aile hold'u veya aktif vaka kanıtı olan telemetri kaydı otomatik
   korunur. Apply ve restore öncesinde tam SQLite yedeği alınır; mantıksal
   kayıt silinmez.
7. Şema98'deki P07 politikaları, hold'lar, audit olayları ve arşivler 99'a
   kimlikleri ve sıra numaraları korunarak taşınır.

## Sonuçlar

- P07 ve P12 aynı açıklanabilir saklama yaşam döngüsünü paylaşır; UI/backend
  ayrı bir telemetri arşiv protokolü öğrenmez.
- Aynı telemetri kaydı birden fazla doğrulanabilir arşiv kuşağına sahip olabilir.
- Haricî soğuk depo, otomatik silme, mevzuat uygunluğu, okuma audit'i ve gerçek
  scheduler bu kararın kapsamı değildir.
- Cowrie veya CAPE kurulmaz ya da çalıştırılmaz. XTI yalnız önceden güvenli
  biçimde normalize edilmiş kayıtları arşivler; malware örneği, PCAP, bellek,
  ham komut veya ham CAPE raporu saklamaz.

## Kanıt

- Hedefli yaşam döngüsü, tamper, tenant ve 98→99 migration testleri:
  `tests/test_telemetry_retention.py`
- Ağsız iki firmalı kapasite ve restore kabulü:
  `scripts/check-telemetry-retention-delivery.py`
- Kullanım ve bilinçli sınırlar: [DATA_RETENTION](../DATA_RETENTION.md) ve
  [TELEMETRY](../TELEMETRY.md).
