# ADR 0042 — Varlık ürünleri yalnız açık kullanıcı doğrulamasıyla kaydedilecek

- **Durum:** Kabul edildi
- **Tarih:** 29 Ekim 2026

## Bağlam

Açık TCP portu, yaygın protokol etiketi veya NVD ürün adı varlıkta gerçekten çalışan üretici, ürün ve sürümü kanıtlamaz. Bu ipuçlarını otomatik ürün envanterine çevirmek yanlış CVE eşleşmelerine ve kalıcı yanlış kayıtlara yol açar. Buna karşılık zafiyet bağlamını varlığa taşıyabilmek için kaynağı ve yaşam döngüsü görülen bir ürün kanıtına ihtiyaç vardır.

## Karar

`products add` yalnız önceden kayıtlı tam domain için açık CPE türü (`a/o/h`), kanonik üretici/ürün adı, joker olmayan kesin sürüm ve en az beş karakterlik kullanıcı kanıtı kabul eder. Kanıt türü ilk dilimde sabit `user_verified` değeridir. Port ipuçları, banner tahmini veya NVD kayıtları kendiliğinden bu tabloya yazılmaz.

Aynı varlık+tür+üretici+ürün+sürüm tek kimliktir. Aynı kanıt tekrarında yeni olay oluşmaz; kanıt değişikliği, kaldırma ve yeniden etkinleştirme eklemeli olay olarak saklanır. `list/show` salt okunur, `revoke` geçmişi silmeden kaydı etkisiz yapar. Farklı varlıkların kayıtları kesin `asset_id` ilişkisiyle ayrılır.

Şema 20, `asset_products` ve `asset_product_events` tablolarını ekler. Şema 19→20 geçişi önce yedek alır, tabloları boş oluşturur ve bütünlük doğrulamasından sonra sürümü yükseltir. Eski servis/port kayıtlarından ürün uydurulmaz; hata şema 19'u ve yedeği korur.

## Sonuçlar

- Ürün ve sürüm kanıtı açık, geri alınabilir ve geçmişlidir.
- Servis ipucu ile doğrulanmış ürün arasındaki güven sınırı korunur.
- Kayıt tek başına ürünün çalıştığını, dışarıdan erişildiğini veya zafiyet taşıdığını kanıtlamaz.
- Otomatik/banner tabanlı doğrulama, paket yöneticisi adaptörleri ve çok kiracılı yetki ayrı sonraki dilimlerdir.
