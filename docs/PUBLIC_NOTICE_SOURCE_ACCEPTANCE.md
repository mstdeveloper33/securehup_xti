# Ücretsiz kamu olay kaynağı kabul kaydı

Değerlendirme tarihi: **14 Kasım 2026**.

Kaynak: **Have I Been Pwned kamu ihlal kataloğu**. Birincil belge:
[HIBP API v3](https://haveibeenpwned.com/API/v3).
Kullanılan tek adres:
`https://haveibeenpwned.com/api/v3/breaches`.

Belgede bu katalog herkese açık hizmet olarak sunulur; e-posta ve kuruluş
hesaplarına ait kayıt sorguları ayrı yetkili hizmetlerdir. `Name` sabit
kimlik, `Title` görünen ad, `Domain` kaynak domainidir. Olay tarihi yaklaşık
olabilir; eklenme ve değiştirilme tarihleri ayrı alanlardır. Kaynak
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) kapsamında
Have I Been Pwned adı ve bağlantısıyla görünür atıf ister. User-Agent doğru
istemci kimliğini belirtmelidir. Ücretsiz erişim sınırsız istek veya
kesintisiz hizmet garantisi değildir.

Canlı, anahtarsız tek GET doğrulamasında **1.052 olay metadata kaydı** ve
**1.133.548 bayt** alındı. SHA-256:
`86e0d3cee72b16f0665eb12e0e9d8217d911b0fbeb0313dce74de33fea80ec31`.
Bu tarihli ölçümdür; sabit ürün sayısı değildir. Yerel parser bütün kayıtları
doğruladı; aynı katalogla ilk yazım, tekrar yazım ve çevrimdışı birebir domain
araması gerçek geçici SQLite üzerinde doğrulandı. Ham yanıt repoya eklenmedi.

Son adaptörle ayrıca **15:49:35 UTC** tarihinde tek istekle canlı toplama
başarılı oldu: aynı özet ve 1.052 kayıt geçici veritabanına kaydedildi;
`adobe.com` için çevrimdışı birebir arama `Adobe` kimliğini döndürdü.
Toplama kimlik bilgisi göndermeden tamamlandı; geçici doğrulama veritabanı
kaldırıldı.

Katkı: mevcut ransomware iddia kaynaklarından ayrı, yayımlanmış geçmiş
olayların domain, tarih, kategori ve kaynak sınıfı bilgisi. Sınırlama:
yalnız yayıncının katalogladığı olaylar; bütün internet veya bütün ihlaller
değildir. `is_verified` kaynağın işaretidir, XTI kararı değildir. Uydurma,
spam, malware, emekliye ayrılma ve diğer işaretler gizlenmez.

Taşıma: en fazla 16 MiB, 10.000 kayıt, 20 saniye soket süre sınırı ve
45 saniye okuma bütçesi; parça okuması en fazla bir soket süresi kadar
bütçeyi aşabilir. Bir komut bir istek yapar; HTTP 429/403, yönlendirme,
HTML, bozuk veya boş katalog başarısızdır. Otomatik yeniden deneme ve
erişim engeli aşma yoktur. Sorgular yerel kopyada çalışır; hedef adı,
domaini veya kişi bilgisi dış kaynağa sorgu olarak gönderilmez.

Diğer değerlendirilen kaynak:
[California DOJ kamu listesi](https://www.oag.ca.gov/privacy/databreach/list)
resmî [CSV çıktısı](https://www.oag.ca.gov/privacy/databreach/list-export)
yayımlar; ancak bu ortamda doğrudan bağlantı süre sınırına takıldı.
Çalışan kaynak diye sunulmadı veya ürüne eklenmedi.
