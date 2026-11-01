# ADR 0041 — NVD CPE koşulları mantığı korunarak salt okunur gösterilecek

- **Durum:** Kabul edildi
- **Tarih:** 29 Ekim 2026

## Bağlam

NVD kayıtları yalnız CVSS puanı değil, CVE'nin uygulanabildiği ürün ve sürümleri CPE 2.3 ifadeleriyle yayımlar. Bu ifadeler basit bir ürün listesi değildir: birden fazla yapı ve düğüm, `AND`/`OR`, tersleme, etkilenen ürün satırları ve yalnız ortamı bağlayan `vulnerable=false` satırları içerebilir. Bunları düz bir ürün listesine indirgemek yanlış maruziyet sonucuna yol açar.

## Karar

`vuln applicability CVE-YIL-SAYI`, yerelde saklanan kanonik NVD kaynak nesnesinin `configurations` bölümünü salt okunur ayrıştırır. Şunlar korunur:

- yapı, düğüm ve kaynak sırası;
- `AND`/`OR` ve varsa `negate` bilgisi;
- `vulnerable=true` ile `vulnerable=false` ayrımı;
- ham CPE, CPE türü, üretici, ürün, tam sürüm ve dahil/hariç sürüm sınırları;
- NVD `matchCriteriaId` UUID kanıtı.

Gösterim 1–500 satırla sınırlıdır; ancak 2.000 yapı, 10.000 düğüm ve 20.000 CPE sınırları içindeki bütün kaynak nesnesi doğrulanır. Bozuk bir koşul kısmi görünüm üretmez. NVD kaydında `configurations` yoksa bu yalnız “CPE koşulu yayımlanmamış” anlamına gelir; güvenli veya etkilenmiyor sonucu değildir.

Bu görünüm yeni tabloya kopyalanmaz. NVD kaynak kaydının özeti kanıt kimliği olarak taşınır. Ağ isteği veya veritabanı yazması yapılmaz.

## Sonuçlar

- Kullanıcı NVD'nin ürün/sürüm dayanağını terminalden inceleyebilir.
- Bağlayıcı donanım koşulları yanlışlıkla güvenli ürün veya bağımsız zafiyet sayılmaz.
- CPE mantığı gelecekteki eşleştirme katmanı için kayıpsız kalır.
- Henüz varlıkta çalışan ürün/sürüm kanıtı yoktur; bu görünüm maruziyet üretmez.
- NVD'nin yeni `affected` alanı ve üretici duyuruları ayrı sonraki kaynak dilimleridir.
