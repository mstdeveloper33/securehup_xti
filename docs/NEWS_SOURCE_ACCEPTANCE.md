# Planlı haber toplama — canlı kullanım kabulü

**Tarih:** 16 Kasım 2026, 01:45 TRT (15 Kasım 22:45 UTC).
**Kod:** `56d606ea8e4a9eb182fb0c83be6e72c693d7cdcd`, 0.146.0 / şema 69.

Gerçek CLI ile ayrı geçici SQLite veri alanında iki toplama turu
çalıştırıldı. Ortam macOS / Python 3.13.3, haber okuyucusu
`feedparser==6.0.14` ve `feedparser-sgmllib==2.1.0` idi. Kullanıcının
veritabanı ve kurulu araç ortamı değiştirilmedi. Ham yayınlar ve firma
arama kayıtları kaynak kod deposuna eklenmedi.

## Kaynak sonucu

Her turda üç yayıncıya birer GET, toplam **altı HTTPS isteği** yapıldı.
Firma adı ve domain araması alınmış kayıtlar üzerinde yerelde çalıştı;
bu sorgular yayıncılara gönderilmedi. Hedef firma sitesine, haber
sayfalarına veya ek dosyalara bağlanılmadı.

| Kaynak | İlk turda eklenen | İkinci turda aynı kalan | Özet içeren | Kaynağın en yeni yayın tarihi |
|---|---:|---:|---:|---|
| [CISA News](https://www.cisa.gov/news.xml) | 10 | 10 | 0 | 9 Kasım 2026 |
| [UK NCSC](https://www.ncsc.gov.uk/api/1/services/v1/all-rss-feed.xml) | 20 | 20 | 20 | 11 Kasım 2026 |
| [CERT-FR Actualité](https://cert.cyber.gouv.fr/actualite/feed/) | 40 | 40 | 40 | 9 Kasım 2026 |

İki turda da üç kaynak başarılıydı. İkinci tur yeni/değişen haber
üretmedi; toplam **70 kayıt** olarak kaldı. Bunlar bu tarihli kaynak
yanıtlarının sayılarıdır; sabit ürün kapasitesi veya firma bulgu sayısı
değildir. Altı kaynak çalışması ve iki toplama oturumu ayrı saklandı.

## Gerçek akışta doğrulananlar

- Profilin ağsız planında üç kaynak ve üç kayıtlı arama vardı. Plan
  sırasında veritabanı dosyasının SHA-256 özeti değişmedi.
- Firma adı ve domain için ayrı aramalar, 70 kayıtta **sıfır eşleşme**
  verdi. Kaynaklar başarılı olduğundan bu sonuç kaynak hatası değildi.
- Aramanın sonuç döndürebildiğini görmek için ayrı `cyber` kontrolü
  kullanıldı: 58 eşleşme, ilk turda sessiz başlangıç, ikinci turda
  sıfır fark. Bu kontrol firma bulgusu değildir. Eşleşmelerin 12'si
  başlıkta, 6'sı özette, 40'ı CERT-FR bağlantısındaki `cyber` sözcüğündeydi.
- İki tur sonunda inbox boş kaldı; aynı içerik tekrar bildirime dönüşmedi.
- İkinci turdan sonra ilk oturumun ayrıntısı yeniden okundu; önceki
  çalışma kanıtı birebir aynı kaldı.
- Haber listesi, kaynak durumu ve üç aramanın bütün sonuçları okundu;
  listeleme sınırının arkasında gizli kalan sayfa yoktu.
- Profil için günlük Linux zamanlama dosyaları üretildi. Hizmet
  etkinleştirilmedi; bu deneme 7/24 işletim kabulü değildir.

Bu gerçek kaynaklar hata veya içerik değişikliği üretmedi. Kesinti,
kaynak hatası, yeni/değişen eşleşme bildirimi ve devam senaryoları
[0.146.0 otomatik doğrulamasında](STATUS.md) ayrıca sınanır; burada canlı
olarak yaşanmış gibi sunulmaz.

## Ölçülen kapsam boşluğu

**RSS içeriği tam makale değildir.** Bu yanıtta CISA özet vermedi;
NCSC özetleri 70–191, CERT-FR özetleri 294–299 karakterdi. XTI'nın
`summary_truncated=false` alanı, XTI'nın kendi sınırı nedeniyle kesmediği
anlamına gelir; yayıncının tam metni verdiği anlamına gelmez. Firma adı
yalnız makalenin gövdesindeyse mevcut RSS araması onu göremeyebilir.

**Toplama tarihi yayın tarihi değildir.** CERT-FR yanıtında 24 Ocak 2014
tarihli bir kayıt da vardı. Bugün alınan her kayıt yeni haber sayılmaz;
yayın, ilk görülme ve son görülme tarihleri ayrı değerlendirilir.

**Eşleşme yokluğu yalnız aranan katalog için geçerlidir.** Bu üç güvenlik
yayınında firma adına rastlanmaması, internette firma hakkında haber
olmadığını göstermez. Bağlantı metnindeki eşleşme de haberin firma
hakkında olduğuna tek başına kanıt değildir; eşleşen alan sonuçta görünür.

## Kabul sonrası iş sırası

1. Kullanıcı Tavily anahtarını daha sonra ekleyecek. Anahtar tanımlanınca
   gerçek firma sorgusu, seçilmiş gerçek tedarikçi, kredi kaydı ve
   birleşik kuruluş raporu canlı olarak doğrulanacak. Bu kabul bekliyor;
   bu denemede Tavily isteği veya kredi kullanımı yok.
2. Ölçülen özet eksikliği için sınırlı makale metni alma ayrı bir teslim
   olarak değerlendirilecek. Önce yayıncı erişim koşulları, izinli
   adresler, yanıt sınırları, kaynak atfı ve RSS kanıtından ayrı metin
   geçmişi belirlenecek. Trafilatura plan tercihidir; henüz kurulmadı
   veya makale tarama özelliği eklenmedi.
3. Yeni yayıncı ve yaklaşık ad eşleştirmesi, mevcut kayıtlarda görülen
   somut eksik örneklerle seçilecek. Sıfır firma eşleşmesi tek başına
   eşleştirme hatası veya yeni kütüphane ihtiyacı sayılmayacak.

[Kullanım ve sonuçları görüntüleme](NEWS_COLLECTION.md),
[güncel motor yol haritası](roadmap/ENGINE_INTEGRATION_ROADMAP.md).
