# 0193 — Kuruluş saklama politikası, kayıpsız arşiv ve audit zinciri

> 0.192.0 notu: İlk aile sınırı, P12 `telemetry_records` ailesini aynı
> yaşam döngüsüne ekleyen [ADR0197](0197-telemetry-retention-generations.md)
> ile genişletilmiştir. Aşağıdaki metin 0.188.0 kararının tarihî kapsamıdır.

Tarih: 22 Kasım 2026. Durum: kabul edildi.

## Bağlam

P07 değişmeyen snapshot'ları tekilleştirir; yine de gerçek değişiklikler
uzun süre kullanıldığında büyük kanıt gövdeleri üretir. Bu gövdeleri sessizce
silmek vaka kanıtı, provenance ve tekrar üretilebilirlik açısından güvenli
değildir. “Tüm tabloları N gün sonra sil” yaklaşımı da her kayıt ailesinin
farklı anlamını ve açık legal/case korumalarını yok sayar.

## Karar

- İlk yönetilen aile yalnız `unified_monitoring_runs`tır. Aile listesi kapalıdır;
  bilinmeyen tablo veya aile dinamik SQL ile çalıştırılmaz.
- Kuruluş politikası sürümlü ad, amaç, dayanak, yaş eşiği, aile ve parti
  sınırı taşır. Plan yazmasızdır; token politika revision'ını, aday kimliklerini
  ve gövde hash'lerini çitler.
- Uygulama öncesi tam SQLite yedeği alınır. Büyük kanonik JSON gövdeleri zlib
  ile aynı veri alanındaki arşiv tablosuna taşınır; sıcak satıra geçersiz-JSON
  bağlama işaretçisi yazılır. Normal P07 okuması işaretçiyi doğrular ve gövdeyi
  şeffaf açar.
- Kimlik, zaman, payload hash'i, alarm, review, vaka bağı ve mantıksal run
  silinmez. Aktif vaka kanıtı ile açık organization/run hold plan dışında kalır.
- Restore yine yedekli ve hash doğrulamalıdır. Arşiv gövdesi bozuksa kayıt
  okunmaz; eksik veriden başarı üretilmez.
- Politika, hold, archive, restore, recovery ve başarısızlık olayları aktör,
  gerekçe ve önceki hash ile eklemeli audit zincirine yazılır. Aktörü güvenilir
  oturum kimliğine bağlamak tüketici backendin sorumluluğudur.
- Engine salt okur; firma platformu yazmaları workspace/revision/idempotency
  çitlidir. Scheduler, RBAC, hukuk kararı ve mevzuat uygunluk iddiası motorun
  içine alınmaz.
- Eski `journals.*` arşivi ayrı, mevcut sözleşmesinde kalır. Bütün veri
  ailelerine uygulanmış genel retention iddiası yapılmaz.

## Sonuçlar

Eski izleme kanıtı daha az canlı gövde baytıyla okunabilir kalır ve geri
yüklenebilir. Kapasite dolunca otomatik kayıt silinmez. Aynı SQLite dosyasına
sıkıştırma fiziksel dosya boyutunu hemen küçültmeyebilir; P08 otomatik
`VACUUM` veya haricî soğuk depo sağlamaz. Yeni aileler ancak kendi vaka,
provenance, restore ve kapasite kabulüyle kataloğa eklenebilir.
