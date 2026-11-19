# Tam metin, yeniden inceleme ve günlük arşivi

19 Kasım 2026. Kullanıcı 2, 3 ve 4. maddeleri birlikte yetkilendirdi.
Başlangıç 0.168.0 / çekirdek 78. Bu dosya uygulama ve kabul ilerlemesidir;
tamamlanmayan başlık uygulanmış sayılmaz.

| İş | Teslim | Kabul | Durum |
| --- | --- | --- | --- |
| Tam makale/PDF | İncelenmiş yayıncılardan açık, sınırlı HTTPS alımı; HTML ana metni/PDF metni; kaynak, lisans, özgün içerik özeti ve ayrıştırıcı sürümüyle yeni rapor belge modeli | Eski belgeler değişmez; aynı istek tekrar ağ çağırmaz; hatada eski belge korunur; yanlış host/yönlendirme/boyut reddedilir; gerçek PDF ayrıştırıcısı sınanır | Uygulandı; yerel kabul geçti |
| Yeniden inceleme | Kaynak dayanağı değişen insan ilişki kararları için firma kapsamlı, pencereli inceleme listesi | Eski karar silinmez; eksik kapsam kayıp kanıt sayılmaz; güncel dayanakla yeni karar verilince listeden çıkar; firma ve snapshot sınırları korunur | Uygulandı; yerel kabul geçti |
| Günlük saklama | Rapor ve görülme/ilişki günlüklerinin eski gövdelerini doğrulanmış sıkıştırılmış arşive taşıma; önizleme, açık uygulama, geri alma, durum ve yedek | Özgün sıra/hash/kimlik/tekrar anahtarları kalır; okuma ve kanıt bağlantıları aynı sonucu verir; bozuk arşiv reddedilir; eski yedekten dönüş ve transaction rollback doğrulanır | Uygulandı; yerel kabul geçti |

Arşiv bu teslimde aynı SQLite yedeğine dahildir. Kimlik/geçmiş silinmez;
mantıksal satır ve okuma sınırları kaldırılmaz. Sıkıştırma saklanan gövdeyi
küçültür; SQLite boşalan sayfaları tekrar kullanabilir, fiziksel dosyanın
anında küçüldüğü iddia edilmez. Sınırsız büyüme veya dağıtık arşiv değildir.

Tam metin yalnız açık kaynak politikasıyla seçilmiş yayıncılardan alınır.
Rastgele URL, giriş isteyen içerik, OCR, script çalıştırma ve internet
genelinde tarama yoktur. Metin/boyut/süre aşımı açık sonuçtur; kesilmiş
metin tam rapor diye saklanmaz. Paket lisansı ile yayıncı içerik hakkı
ayrı kaydedilir. PDF ayrıştırıcısı bağımsız adaptör ve sınırlı süreçtedir.

Terminal ve mevcut firma JSON sözleşmesi birlikte sunulur. Geniş
STIX/TAXII, LLM, .NET/UI, Tavily anahtarı ve yetkili Nmap testi bu pakette
açılmıyor. İlk uygulama turunda push kapsam dışındaydı; sonraki kullanıcı
yönlendirmesiyle `071a076` kodu GitHub'a gönderildi. Altı Linux workflow'u
ve 3.187 testlik tam paket başarılı; hata/atlama yok.
[Linux teslimi](../ACCEPTANCE_REVIEW.md#01690--github-ve-linux-teslimi).

Güncel sürüm **0.169.0 / çekirdek 79**. [Kullanım](../PUBLISHER_REVIEW_RETENTION.md),
[mimari karar](../decisions/0174-publisher-review-retention.md),
[kabul sonuçları](../ACCEPTANCE_REVIEW.md).
