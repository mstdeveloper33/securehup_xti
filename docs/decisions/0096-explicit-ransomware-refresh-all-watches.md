# 0096 — Açık kaynak yenilemesi ve bütün etkin ransomware izlemeleri

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Karar

`ransomware watch-refresh-all`, tek açık kullanıcı komutunda ThreatCluster snapshot'ını yeniler ve yalnız yenileme tamamen başarılıysa bütün etkin kuruluş/domain izlemelerini çalıştırır. İzlemeler normalleştirilmiş ad ve kimliğe göre kararlı sıradadır. Komut 1–500 etkin izleme, kaynak fark öğesi ve izleme sonuç öğesi sınırlarını işlemden önce doğrular. Bütün etkin tanımlar verilen sınıra sığmıyorsa ağ isteği veya yazma yapılmaz; gizli kırpma olmaz.

Kaynak hatası boş snapshot değildir. Başarısız kaynak çalışması denetim geçmişine eklenir, önceki başarılı snapshot korunur ve eski veri üzerinde hiçbir izleme çalıştırılmaz. Her izleme az önce tamamlanan kaynak çalışma kimliğini başlamadan önce doğrular. Her izleme kendi atomik transaction'ını kullanır; sonraki bir izleme hatası daha önce tamamlanan kaynak veya izleme kayıtlarını geri almaz, fakat güvenli biçimde toplu akışı durdurur.

İlk veya değişmiş tanım çalışması sessiz başlangıçtır. Sonraki yeni/değişen eşleşmeler mevcut ortak yerel kutuya girer; yalnız kayan kaynak penceresinden çıkış bildirim değildir. Komut tek seferlik ön plan işlemidir; zamanlayıcı, daemon veya görünmez ağ işi kurmaz.

## Gerekçe ve sınırlar

Kullanıcının ayrı `refresh`, `watch-list` ve çok sayıda `watch-run` komutunu elle birleştirmesi unutulan izlemelere ve eski snapshot üzerinde çalışmaya yol açabilir. Tek açık komut bu bağı güvenli ve görünür yapar. Bununla birlikte kaynak kapsamı hâlâ tek kamu akışının son dönem penceresidir; sonuç doğrulanmış ihlal değildir. İkinci kaynak, tekrar yayın çözümleme, tarihsel derinlik ve kalıcı zamanlama bu kararla tamamlanmış sayılmaz.
