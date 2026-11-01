# 0032 — Açıklanabilir dış yüzey maruziyet adayları

**Tarih:** 29 Ekim 2026 · **Durum:** 0.32.0'da uygulandı.

## Sorun

Web, e-posta DNS ve sınırlı TCP kanıtları ayrı ayrı görülebiliyor; fakat kullanıcı hangi kayıtların elle incelenmesi gerektiğini tek yerde göremiyor. Kanıtı doğrudan “zafiyet”, “açık panel” veya “takeover” diye etiketlemek ise mevcut verinin söyleyebileceğinden fazlasını iddia eder. Port kontrolü banner okumaz, web kontrolü gövde indirmez ve pasif alt alan adı kaydı CNAME/delegasyon kanıtı taşımaz.

## Karar

`surface exposures DOMAIN`, mevcut `SurfaceFreshnessRepository` anlık görüntüsünü yeniden kullanır. Uygulama katmanı yalnız son kayıtlı web, posta ve servis kanıtından geçici, açıklanabilir adaylar çıkarır; yeni tabloya yazmaz ve ağ adaptörü çağırmaz.

İlk kural kümesi şunlarla sınırlıdır:

- TLS aşaması tamamlanmadığında bağlantı/doğrulama sorunu adayı; neden sertifika, ağ veya geçici hizmet olarak kesinleştirilmez.
- MX kabul eden domainde eksik veya birden çok SPF/DMARC kaydı; Null MX tek başına bu adayları üretmez.
- `22` ve `3389/tcp` için uzak erişim, `8080` ve `8443/tcp` için alternatif web erişimi adayı; yalnız TCP bağlantı kabulü söylenir.

Her aday tür/kategori, kanıt seviyesi, kanıt kimliği/zamanı/güncelliği, olgular, sınırlamalar ve önerilen insan adımı taşır. Varsayılan 24 saatlik güncellik eşiği 1–8760 saat arasında rapor politikası olarak değiştirilebilir. Eski ve gelecekteki/tutarsız zaman ayrı kalır.

Kapsam listesi web, posta ve servis kanıtının güncel/eski/kısmi/başarısız/alınmamış durumunu; ayrıca açık panel kimliği ile takeover değerlendirmesinin neden desteklenmediğini gösterir. Sayfa içeriği/banner olmadığı için panel, CNAME/delegasyon/sağlayıcı yanıtı olmadığı için takeover sonucu üretilmez.

## Güvenlik ve veri sınırı

Komut salt okunurdur: internet bağlantısı, DNS sorgusu, port bağlantısı, içerik indirme, oturum açma, kaynak sahiplenme, exploit, kayıt düzeltme veya kalıcı aday oluşturma yapmaz. Aday sayısının sıfır olması güvenli sonuç değildir. Kısmi, başarısız, eski ve desteklenmeyen kapsam ayrıca görünür kalır.

## Sonuçlar

ASM-05 ve CAP-031'in ilk dar dilimi, mevcut kanıtı abartmadan kullanıcıya görünür olur. Tam açık panel tanıma, güvenli CNAME/delegasyon toplama, sağlayıcıya özgü takeover imzaları, teknoloji/sürüm doğrulaması ve CVE ilişkisi ayrı tasarım ve laboratuvar kapıları olarak açık kalır. Yeni tablo, migration, ücretli servis, API anahtarı veya Python paketi yoktur; şema 15 sürer.
