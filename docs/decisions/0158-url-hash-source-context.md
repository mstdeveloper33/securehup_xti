# 0158 — URL/hash kaynak bağlamı ve araştırma bağlantısı

Tarih: 17 Kasım 2026. Durum: 0.154.0'da uygulandı.

## İhtiyaç

Motor URL/hash IOC'lerini zaten saklıyordu; yeni IOC tablosu gerekmiyor.
Eksik olan, dış kaynaktaki dosya/arşiv bağlamını IOC zararlılık iddiası
yaratmadan kaydetmek ve mevcut araştırma ekranına bağlamak.

## Karar

`indicator_enrichment` domain/application/port/interface modülleri,
`enrichment_sources` sabit HTTP adaptörü ve `sqlite_enrichment` deposu
kullanılır. Mevcut `enrichment` modülleri phishing/HTTPS değerlendirmesine
aittir ve korunur. Yeni bağımlılık veya üçüncü taraf sunucu kurulmaz.

Şema 74 yalnız iki tablo ve sorgu indeksi ekler. Yanıt byte'ları ve SHA-256
tek kopya, her sorgu denemesi ayrı makbuzdur. Kaynak/sorgu/yanıt statüsü,
zaman sırası ve içerik özeti okumada doğrulanır. Bozuk kayıtta sonuç
uydurulmaz. Geçiş öncesi yedek, transaction rollback ve eski şemaya
düşürülmüş dolu yeni tabloyu reddetme uygulanır. Makbuzlar/yeni tablolar
mevcut veritabanı yedeğine dahildir; iş kuyruğu şeması değişmez.

Bir geçerli boş yanıt güncel sonucun yerini alabilir; hata bunu yapamaz.
`lookup` son deneme ile son geçerli yanıtı ayırır. Geçmiş değişmezdir.
Domain modeli ve source policy sürümü 1'dir; ileride format değişiminde
eski byte'ların anlamını koruyan sürümlü parser veya açık geçiş gerekir.

Araştırma aynı SQLite read transaction içinde bu kayıtları okur.
URL/hash kökleri, mevcut IOC/CTI ilişkileri ve yeni `source_context`
bağlantıları birlikte gezilir. Kaynak alınma ve kaynak gözlem zamanları
ayrıdır. Kökte görülen kaynak yanıtının ters indeks üzerinden bütün firma
arşivinde aranması bu dilimde yoktur. Kanıtsız host/sahiplik/aktör bağı
çıkarılmaz. Kaynak sonucu hiçbir alarm veya analist kararını değiştirmez.

Engine/platform yalnız okur; sorgu gönderimi işletici CLI'sinde ortak
yerel kilit altında olur. Kaynak beklemeleri mevcut kalıcı cooldown deposunu
kullanır. Firma dışı ortak API kotası ayrı işletim sorumluluğudur.

## Kaynak seçimi

- **CIRCL:** Resmî hizmet sayfası bilinen dosya bağlamını ücretsiz/best effort
  sunar; veriler kaynak gösterilerek ticari kullanım dahil CC-BY'dir.
  Sürüm numarası belirtilmediğinden CC-BY-4.0 varsayılmadı.
  [Veri ve kullanım koşulları](https://www.circl.lu/services/hashlookup/).
  Sunucu/istemci lisansı veri lisansından ayrıdır; yalnız standart HTTP
  çağrısı kullanılır. AGPL/GPL sunucu/istemci kodu motora dahil edilmez.
- **urlscan:** Mevcut public arşiv adaptörü yaklaşımı kesin URL sorgusuna
  genişletilir. Kimliksiz sorgu canlı çalıştı. Ücretsiz erişim, müşteriye
  yeniden sunma hakkı sayılmaz; ürün entegrasyonundan önce sağlayıcı
  koşulları netleştirilir. [Şartlar](https://urlscan.io/terms/),
  [ticari kullanım açıklaması](https://docs.urlscan.io/pages/faq),
  [arama alanları](https://docs.urlscan.io/pages/search-api-reference).
- **URLhaus:** Güncel API anahtarı ve ticari kullanım koşulları nedeniyle
  bu anahtarsız dilime eklenmedi. [Resmî API](https://urlhaus.abuse.ch/api/).
- **PhishTank:** Eski ücretsiz kullanım metni arşiv şartları altında;
  güncel izinlerin yerine kullanılamaz. Bu teslimin sağlayıcısı yapılmadı.
  [Güncel/arşiv koşul ayrımı](https://phishtank.org/terms.php).

Bu inceleme sağlayıcı erişim/yeniden kullanım sınırlarını görünür tutar;
ticari dağıtım için tüm platformun genel lisans onayı değildir.

## Kabul

Kaynak bağını yanlış kurma, URL yol/sorgu ayrımı, 404 ile ağ hatası farkı,
429 beklemesi, eski başarılı yanıtın korunması, ham içerik bozulması,
şema geçişi/kurtarma, firma izolasyonu, salt okuma ve araştırma kesit
kontrolü test edilir. Gerçek API sonuçları kontrollü fixture sonuçlarından
ayrı kaydedilir. [Kullanım ve sözleşme](../INDICATOR_ENRICHMENT.md).
