# 0093 — Sınırlı açık ransomware iddiası önizlemesi

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

Yol haritasında ransomware duyuru takibi dark web/sızıntı katmanının ilk düşük riskli parçasıdır. Doğrudan Tor forumları veya leak siteleriyle bağlantı; içerik, kişisel veri, erişim güvenliği, kaynak koşulları ve operasyon yükü getirir. Kişisel ve ücretsiz ilk kullanım için kayıt gerektirmeyen, açık kullanım koşulu bulunan ve bir iddianın doğrulanmış ihlal olmadığını açıkça belirten aracı bir kamu akışı gerekir.

ThreatCluster sabit HTTPS JSON akışı son dönem ransomware/leak-site iddialarını anahtarsız yayımlar. Akış kendi içinde CC BY 4.0 atfı taşır; sağlayıcının güncel koşulları kamu akışını TLP:CLEAR ve atıfla kullanılabilir olarak tanımlar. Ticari ürüne gömme ayrıca sağlayıcı anlaşmasına tabi olabilir.

## Karar

- `RansomwareClaimSource` yalnız tamamen doğrulanmış bir kaynak snapshot'ı döndüren küçük porttur. Uygulama servisi kaynağa veya HTTP biçimine bağlı değildir.
- `ThreatClusterRansomwareSource` yalnız sabit `https://threatcluster.io/api/darkweb/public/victims.json` adresine gider. Yönlendirme ve sıkıştırma yoktur; TLS doğrulaması, 30 saniye, 8 MiB, 10.000 kayıt ve 48 saat güncellik sınırı uygulanır.
- JSON yinelenen alan, sonlu olmayan sayı, beklenmeyen üst/kayıt alanı, sayaç uyuşmazlığı, bilinmeyen durum, bozuk zaman/ülke/URL, yinelenen iddia ve beklenmeyen lisans kimliğinde bütünüyle reddedilir. Kısmi sonuç gösterilmez.
- Domain modeli leak-site `post_url` değerini taşımaz. Adaptör yalnız geçerli bir kaynak gönderi adresi bulunup bulunmadığını boolean olarak aktarır. Ham metin, ekran görüntüsü ve kişisel veri alınmaz.
- `ransomware recent [QUERY]` tüm doğrulanmış 30 günlük snapshot üzerinde kuruluş, web bilgisi, grup, ülke ve sektörü cihaz içinde arar. Tam, başlangıç ve içerme eşleşmesi sıralanır; 1–100 görünüm sınırı eşleşen toplamı değiştirmez.
- Her çıktı kaydı “grubun yayımladığı doğrulanmamış iddia” olarak etiketlenir. `listed/delisted` yalnız kaynak gönderisinin gözlenen durumudur; ihlal, ödeme, çözüm veya doğruluk kararı değildir. Eşleşme yokluğu güvenlik ya da kapsam tamlığı kanıtı sayılmaz.
- İlk dilim canlı ve açık kullanıcı komutlu önizlemedir. Veritabanı, geçmiş, bildirim, otomatik izleme, kuruluş çözümleme, Tor erişimi veya takedown işlemi eklenmez. Şema 39 değişmez.
- Kaynak adı, URL, lisans, akış zamanı, zaman penceresi, kayıt sayısı ve içerik SHA-256 çıktıda korunur. ThreatCluster atfı üçüncü taraf bildirimine eklenir.

## Sonuçlar

Kullanıcı ücretsiz ve anahtarsız bir kaynaktaki son dönem ransomware iddialarını terminalden araştırabilir; XTI suç altyapısına bağlanmaz ve iddiayı doğrulanmış olay gibi sunmaz. Bu dilim kalıcı izleme değildir. Sonraki teslim, kaynak koşulları yeniden doğrulanarak snapshot yaşam döngüsü, kayıtlı kuruluş/domain eşleştirmesi ve yalnız değişiklikte yerel bildirim eklemelidir.
