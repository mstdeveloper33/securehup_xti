# Kuruluş raporu ve ücretsiz kaynak genişlemesi

Kullanıcının 0.133.0 sonrasındaki onayı: kuruluş bazlı birleşik rapor ve
önerilen ücretsiz geliştirmeler. Web/API, geniş marka, Telegram/forum,
LLM, TAXII, e-posta ve takım ürününün önceki bekleme kararları korunur.
Ürün/sürüm/paket/CVE eşleştirmesi aktif kapsam dışında kalır.

| Teslim | Kabul hedefi |
| --- | --- |
| Kuruluş birleşik görünümü | Yalnız açık ve etkin domain/izleme bağlantıları; gerçek satırlar, kaynak durumları, eski/eksik veri ayrımı |
| Kuruluşa özel gün/hafta raporu | Tek okuma anında doğru kapsam; güncel üyelikten geçmiş sahiplik çıkarılmaması |
| Kanıt ve vaka gezinmesi | Tam kayıt kimlikleri; yalnız ilgili mevcut vaka/bildirimler; başka kuruluş kanıtının rapora taşınmaması |
| Kuruluş kaynak katkısı | Her domain/kural/kaynak ayrı; gerçek adresler ve tamamlanma oranlarının pay/paydasının korunması |
| Kayıtlı değişiklik ayrıntıları | DNS/TLS/web/posta/servis/CNAME için saklanmış önce/sonra değerleri; hata boş başarı sayılmaması |
| CTI bağlamı | Tam IOC değeri veya açık varlık kimliği; kaynaklı doğrudan ilişkiler, geçmiş ve sayfalama; otomatik atıf olmaması |
| Ücretsiz kamu olay kataloğu | HIBP kamu metadata uç noktası; ücretli hesap/e-posta/parola sorgusu yok; kaynak atfı, ilk başlangıç, fark ve kesinti geçmişi |

İlk altı teslim mevcut kayıtları salt okunur kullanır. Kaynak yenilemesi
yalnız açık komutla yapılır. HIBP lisansına uygun atıf her metadata görünümünde
korunur; kaynak doğrulaması XTI'nin bağımsız doğrulaması sayılmaz. İsim
eşleşmesi araştırma adayıdır; domain filtresi yalnız kaynağın domain alanına
tam eşleşir. Hiç kayıt bulunmaması güvenli olma sonucu değildir.

Yedi teslim 0.134.0'da uygulandı. Yeni kalıcı kaynak verisi için açık, yedekli
şema 60 geçişi gerekir. Eski kanıt, insan kararı ve okundu durumu korunur.
Testler ağsız hata/kesinti, tek okuma anı, kapsam ayrımı, sınırlar, bütünlük
ve gerçek CLI akışını kapsar. Yeni kaynağın canlı erişimi
[ayrıca doğrulandı](../PUBLIC_NOTICE_SOURCE_ACCEPTANCE.md). Mevcut Common
Crawl dış erişim sorunu ve gerçek Linux hizmet kabulü ayrı açık konulardır.

Bu belge tamamlanan dar teslimin kapsamını belirtir. Güncel doğrulama
sonuçları [STATUS](../STATUS.md) belgesinde tutulur.
