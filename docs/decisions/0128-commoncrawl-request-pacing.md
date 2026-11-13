# 0128 — Common Crawl istek aralığı ve süre bütçesi

**Durum:** Kabul edildi

**Tarih:** 13 Kasım 2026

**Uygulama:** 0.129.1, arşiv profili v3 ve kabul kapısı v4; şema 54 değişmez.

## Gözlenen sorun

Önceki canlı denemelerde TLS doğrulamasından sonra HTTP yanıtı alınmadan
bağlantı kapanmıştı. Yeni tanıda aynı resmî katalog adresi, doğrulanan TLS
ve aynı v2 istemci kimliğiyle HTTP 200 döndü. Yani katalog erişimi kod
değişmeden geri geldi; önceki kapanmanın kesin nedeni yerelde kanıtlanamadı.

Common Crawl'ın resmî destek başlığında aynı bağlantı kapanması oran
sınırlayıcısıyla açıklanıyor. Bu bilgi olası nedeni açıklar; bizim çıkış
IP'mizin engellendiğini kanıtlamaz. Erişim sorunu JSON bozukluğu değildir.

Gerçek XTI taşımasıyla katalog ve 11 indeks sorgusu HTTP 200 döndü. Sonraki
indeks sorgusu sırasında toplam 90 saniyelik kaynak süresi doldu; sonuç
doğru biçimde kısmi kaldı. Güncel katalogdan seçilen yıllık kapsam 13
indeks içeriyor. Eski istek aralığı başlangıçlar arasında hesaplandığı için
yavaş yanıttan sonra yeni istek hemen başlayabiliyordu. Bağlantı hatasında
bir saniyelik tekrar da sağlayıcının önerdiği istemciden daha kısaydı.

## Karar

- Common Crawl için kaynak bütçesi 150 saniye olur. Wayback'in bağımsız
  90 saniyesi korunur; iki kaynak ve süreç hazırlığı için dış sınır 270
  saniyeye çıkarılır. Kaynak başına 30 istek, istek başına 30 saniye,
  yanıtta 2 MiB ve hostname sonuç sınırı değişmez.
- Common Crawl'ın aynı süreçteki istemcileri ortak kapıda seri çalışır.
  Önceki isteğin başarı/hata ile bitişinden sonra en az bir saniye beklenir.
- Bağlantı veya zaman aşımı hatasında en fazla bir tekrar için 60 saniye
  beklenir. Bekleme ve yeni deneme mevcut toplam bütçeye dahildir.
  İstek hakkı ya da yeterli süre yoksa gereksiz bekleme yapılmaz; gözlenen
  bağlantı/HTTP hatası sonradan üretilmiş süre hatasıyla örtülmez.
- Bekleme talimatı olmayan geçici 5xx yanıtı için ilk tekrar aralığı iki
  saniyedir. 429/503, TLS, yönlendirme ve biçim hatası davranışı değişmez;
  429/503 için aynı çalışmada tekrar yoktur. Wayback'in kısa tekrar
  davranışı ayrı kalır.
- Katalog önbelleği, alternatif sunucu, proxy, IP/istemci kimliği gizleme
  veya TLS gevşetme eklenmez. User-Agent gerçek XTI arşiv profilini belirtir.
- Upstream commit ve bağımlılıklar değiştirilmez. Yeni şema/bağımlılık yoktur.
  Profil v3 eski kanıtı değiştirmez; yeni gözlem farklı profil özeti taşır.

## Doğrulama ve sınır

Sahte saatli testler yavaş yanıt sonrasında aralığı, ortak kapıyı, 60 saniye
tekrarı, yetersiz süre/istek hakkını ve Wayback ayrımını sınar. İşçi ve ana
süreç testleri ayrı kaynak bütçeleri ile dış sınırı denetler. Canlı kabul
ve tam regresyon sonuçları `STATUS.md` içinde ayrıca kaydedilir.

Artan bütçe her domain veya sağlayıcı yoğunluğunda tamamlanma garantisi
değildir. Büyük sonuç veya yavaş kaynak sınırda yine kısmi kalır; bu durum
başarılı boş sonuç sayılmaz. Standart kütüphane DNS/başlık aşamalarındaki
kesin iptal sınırlaması için dış süreç sınırı son güvence olarak korunur.

## Birincil kaynaklar

- [Common Crawl erişim ve oran sınırı açıklamaları](https://www.commoncrawl.org/faq)
- [Resmî destek: bağlantının HTTP yanıtı olmadan kapanması](https://groups.google.com/g/common-crawl/c/tEQjKSsvEOQ)
- [Önerilen istemcinin istek aralığı ve tekrar uygulaması](https://github.com/commoncrawl/cdx_toolkit/blob/main/cdx_toolkit/myrequests.py)
- [Önerilen istemcinin Common Crawl aralık ayarı](https://github.com/commoncrawl/cdx_toolkit/blob/main/cdx_toolkit/settings.py)
