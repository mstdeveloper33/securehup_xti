# 0136 — Kamuya açık olay kataloğu, ayrı kaynak sınırı

**Durum:** Kabul edildi · **Tarih:** 14 Kasım 2026 · **Şema:** 60

Yeni kaynak, ransomware grubunun paylaşımını kopyalayan üçüncü bir arşiv
değildir. Have I Been Pwned'ın yayımladığı kamu olay metadata kataloğunu
okur. Kişi, e-posta, parola veya çalınmış kayıt aramaz. Ücretsiz katalog
erişimi, başka HIBP hizmetlerinin ücretsiz olduğu anlamına gelmez.

Kaynak portu yalnız tam doğrulanmış `PublicNoticeFeed` döndürür. Sabit
HTTPS adresi, kimliğini belirten User-Agent, yönlendirme yasağı, boyut,
kayıt ve süre sınırı vardır. Ek API anahtarı veya bağımlılık gerekmez.
Kaynak yayınındaki başlık, domain, tarihler, kayıt sayısı, veri kategorisi
adları ve sınıflandırmalar saklanır. HTML açıklaması, logo, dış duyuru
bağlantıları ve gelecekte eklenebilecek başka alanlar saklanmaz veya açılmaz.

`Name` kalıcı kayıt kimliğidir; görünen başlık değişebilir. Kaynağın
doğrulama, uydurma, spam, malware, stealer-log, hassasiyet ve emekliye ayırma
işaretleri ayrı tutulur. Bunlar XTI'nin doğrulaması değildir. Kaynakta domain
yoksa isimden domain veya kuruluş bağlantısı türetilmez. Metin araması
adaydır; domain filtresi yalnız birebir eşleşir. Sonuç yokluğu güvenlik
garantisi değildir. Kaynaktan kalkma çözülme olarak yorumlanmaz.

Şema 60 iki ek tablo kullanır: toplama çalışmaları ve yalnız değişen
kayıtlar. İlk başarılı katalog başlangıç çizgisidir. Tekrar aynı katalog
geldiğinde tüm kayıtlar çoğaltılmaz. Her çalışmanın tam katalog özeti,
sayaçları ve sıralı geçmişi doğrulanarak durum yeniden oluşturulur.
Hatalı toplama ayrı çalışma kaydıdır; son başarılı katalog korunur.
Okumalar tek tutarlı salt okunur işlemde yapılır. İnternete çıkmadan önce
yerel veritabanı/şema/geçmiş denetlenir; yazma sırasında yeniden denetlenir.

Mevcut veritabanı okunurken kendiliğinden yükseltilmez. `./xti migrate`
benzersiz yedek oluşturup tabloları tek işlemde ekler. Hata halinde hem
DDL hem sürüm geri alınır; kurtarma yedeği korunur. Mevcut dosya üzerine
geri yükleme yapılmaz. Eski kaynak, kuruluş, vaka veya bildirim kayıtlarına
ihlal ilişkisi eklenmez.

Kaynak adı, bağlantısı, lisans ve varsa katkı atfı terminal/JSON çıktısında
taşınmalıdır. Güncel kaynak kabul kanıtı ve sınırlamalar
[kaynak kabul notunda](../PUBLIC_NOTICE_SOURCE_ACCEPTANCE.md) bulunur.
