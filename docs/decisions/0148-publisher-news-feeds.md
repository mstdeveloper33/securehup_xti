# 0148 — Hazır RSS/Atom ayrıştırıcısı ve kaynaklı haber kanıtı

Tarih: 15 Kasım 2026. Uygulama: 0.143.0 / şema 66.

Haber formatını yeniden yazmak yerine `feedparser==6.0.14` ve bağımlılığı
`feedparser-sgmllib==2.1.0` kullanılır. Bunlar Python 3.11 ile uyumlu saf
Python paketleridir. [Feedparser sürüm kaydı](https://pypi.org/pypi/feedparser/6.0.14/json),
[bağımlılık kaydı](https://pypi.org/pypi/feedparser-sgmllib/2.1.0/json).
`requirements/news.txt` iki wheelin sürüm ve SHA-256 değerlerini sabitler.
Normal kurulum `brand,news` eklerini mevcut kurtarılabilir ortamda kurar;
eski ortamı doğrudan pip ile değiştirmez. `--core-only` ağsız çekirdek
seçimidir; parser yokken haber toplama açık kurulum hatası verir, diğer
komutlar import sırasında bozulmaz.

HTTP ve kaynak seçimi XTI'da kalır. İlk katalog doğrudan HTTPS CISA News,
UK NCSC ve CERT-FR actualité yayınlarından oluşur. Üçü de 15 Kasım 2026'da
yeni adaptörle HTTP 200 vererek sırasıyla 10, 20 ve 40 haber döndürdü.
Bu anlık erişim kanıtıdır; sürekli erişim garantisi değildir.
[NCSC yayın listesi](https://www.ncsc.gov.uk/information/rss-feeds),
[CERT-FR yayın listesi](https://cert.cyber.gouv.fr/flux-rss/),
[CISA akışı](https://www.cisa.gov/news.xml).

Parser yalnız `io.BytesIO` alır; URL/dosya yolu veya ham bytes doğrudan
verilmez. Yanıt 4 MiB, akış 2.000 kayıt ve XML yapı sayısı ile sınırlanır.
Yönlendirme, ortam proxy'si, sıkıştırılmış gövde, DTD/entity, HTML yanıtı
ve `bozo` işaretli XML reddedilir. Başlık/özet düz metne çevrilir; özet
2.000 karakteri aşarsa açık kısaltma işaretiyle saklanır. Makale sayfaları,
logolar, enclosure ve HTML içindeki bağlantılar alınmaz. Tarih ayrıştırma
feedparser'a aittir; normalize edilmiş tarih yanında kaynak metni de
saklanır. Eksik/ayrıştırılamayan tarih toplama zamanı ile doldurulmaz.
[Parser davranışı](https://feedparser.readthedocs.io/en/latest/bozo/),
[tarihler](https://feedparser.readthedocs.io/en/latest/date-parsing/).

Haber kimliği kaynak anahtarı ile yayıncı GUID/Atom ID'sinden; bu yoksa
özgün haber bağlantısından türetilir. Aynı kaynak/kimlikte aynı içerik
tekrardır; farklı içerik yeni haldir. Aynı akışta çelişen kimlikler tüm
alımı başarısız yapar. RSS kayan penceredir: son akışta bulunmayan eski
haber saklanır ve aranabilir kalır; geri çekilme hükmü verilmez.

Şema 66 `news_runs`, `news_snapshots`, `news_articles` tablolarını ekler.
İçerik adresli tam kanıt, çalışma zinciri ve güncel görünüm aynı işlemde
yazılır. Okuyucu tarihî görüntüleri, kaynak/kimlik bağını, sayıları ve
güncel görünümü yeniden denetler. İlk görülme, son içerik değişimi, son
görülme ve kaynak tarihi ayrıdır. Yeni haber sayfası sınırı toplama
kapsamını kesmez. Hata önceki başarıyı korur; boş geçerli akış ayrı başarılı
çalışmadır. Kapasite aşımında kısmi kayıt veya otomatik geçmiş silme yoktur.

Genel arama `news` türünü açıkça ekler. Engine v1 dört işlemle devam eder;
`news/news_article` ve üç yayıncı namespace'i kontrollü yeni kayıt türüdür.
Eski saved-search tanımları somut tür listelerini korur. Yeni kapsama
geçiş açık kullanıcı tanımıdır ve sessiz başlangıç üretir. Haber alanları
anlamlı değişikliktir; çalışma kimliği/toplama zamanı tekrar alarmı olmaz.
Bildirim mevcut `search-watch → inbox` yoluyla yapılır. Bu teslim haberleri
`collect` işlerine, otomatik zamanlayıcıya veya kuruluş raporuna gizlice
eklemez. Bunlar ayrı sözleşme ve kabul gerektirir.

Yayıncı atfı ve özgün bağlantı her sonuçta korunur. NCSC'de aksi
belirtilmedikçe OGL v3, CERT-FR'da Licence Ouverte v2 geçerlidir; üçüncü
taraf içerik ve logolar için genel izin varsayılmaz. CISA yayınının açık
erişimi, tüm içeriği sınırsız yeniden dağıtma iddiasına dönüştürülmez.
[NCSC koşulları](https://www.ncsc.gov.uk/section/about-this-website/terms-and-conditions),
[CERT-FR koşulları](https://cert.cyber.gouv.fr/mentions-legales/).
