# ADR 0043 — Ürün/NVD karşılaştırması maruziyet hükmü vermeden sınıflandırılacak

- **Durum:** Kabul edildi
- **Tarih:** 29 Ekim 2026

## Bağlam

Doğrulanmış ürün kaydı ile NVD CPE koşullarının aynı üretici ve ürün adını taşıması yararlı bir adaydır; ancak sürüm karşılaştırması her zaman basit değildir. NVD aralıkları, jokerler, `AND/OR`, tersleme ve çevresel donanım koşulları içerir. Dağıtım backport'ları, kurulum seçeneği ve çalışma/erişim durumu da yalnız CPE'den bilinemez.

## Karar

`vuln assess-product ÜRÜN_KİMLİĞİ CVE` ürün kaydını ve NVD kaynak nesnesini aynı salt-okunur SQLite anlık görüntüsünden alır. CPE türü, üretici ve ürün tam eşleşir. Yalnız basit `OR`, terslemesiz ve tam sürümü eşit `vulnerable=true` satırı “kesin NVD koşulu adayı”dır; bu ad bile zafiyet doğrulaması değildir.

Sürüm aralığı, joker veya uygulanamaz sürüm; `AND`, `negate` ve çevresel bağlar “elle inceleme gerekli” kalır. Aynı `AND` yapısındaki farklı ürün/donanım koşulları ilişkili bağlam olarak gösterilir. Kesin sürüm uyuşmazlığı, ürün koşulu yokluğu, NVD koşulu yokluğu ve etkisiz ürün ayrı sonuçlardır. Bunların hiçbiri güvenli/etkilenmiyor hükmü değildir.

Komut ağ isteği, veritabanı yazısı, alarm, risk skoru veya maruziyet kaydı oluşturmaz. Gösterim sınırlı olsa da saklı NVD koşullarının tamamı mevcut katı ayrıştırıcıyla doğrulanır; bozuk ürün veya NVD kanıtında bütün görünüm durur.

## Sonuçlar

- Kullanıcı hangi NVD koşulunun kendi doğrulanmış ürün kaydıyla ilişkili olduğunu görebilir.
- Karmaşık sürüm mantığı yanlış bir otomatik karara indirgenmez.
- Bu aşama aday incelemesidir; kalıcı exposure yaşam döngüsü, güven skoru, backport bilgisi ve düzeltme doğrulaması sonraki VUL-02/VUL-03 dilimleridir.
