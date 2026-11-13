# 0126 — Arşiv bağlantısı ve sayfalama düzeltmesi

**Durum:** Kabul edildi

**Tarih:** 13 Kasım 2026

**Uygulama:** 0.128.0, arşiv profili v2; şema 54 değişmez.

## Gözlenen sorun

İncelenen theHarvester commit'inin ortak HTTP işlevi bazı bağlantı/TLS/süre
hatalarını boş metne dönüştürüyor. Common Crawl bunu `invalid-catalog`
olarak raporlarken Wayback boş sayfa gibi kabul edebiliyor. Gerçek boş
yanıtla bağlantı hatası bu nedenle güvenilir biçimde ayrılamıyor.

Wayback'in 30 saniyelik toplam bütçesi altında 60 saniyelik HTTP isteği ve
1000 satırlık sayfalar var. `*.domain` ve `domain/*` sorguları domain
kapsamını tekrarlıyor. Common Crawl tarafında `pageSize` blok sayısı olduğu
halde sayfadan yalnız 50 satır alıp sonraki sayfaya geçmek eksik kapsamı
tamamlanmış gibi gösterebilir.

Canlı tanıda Common Crawl için TLS doğrulaması başarılı oldu, ardından
sunucu HTTP yanıtı vermeden bağlantıyı kapattı. Aynı durum urllib, aiohttp
ve curl ile gözlendi. Bu, bozuk katalog veya kesin bir IP engeli kanıtı
değildir. Yazılım düzeltmesi dış sağlayıcının hizmet vereceğini garanti etmez.

## Karar

- Upstream tam commit'i ve bağımlılık kilidi korunur; `.tools` içindeki kod
  değiştirilmez. Yeni bağımlılık eklenmez. Kurulum `--no-editable` ile standart
  pakettir; kontrol checkout dışından yapılır. Böylece macOS'ta gizli işaretli
  `.pth` dosyasının Python tarafından atlanması çalışmayı bozmaz.
- Projeye ait `theharvester_archive_worker.py`, aracın ayrı Python ortamında
  yalnız iki arşivi çalıştırır. Sabit upstream indeks seçimi, hostname ve
  sayfa ayrıştırma yardımcılarını kullanır; genel CLI/aktif özellikler açılmaz.
- `archive_http.py` yalnız iki resmî HTTPS sunucusunu ve izinli API yollarını
  kabul eder. Sorgu domaini kayıtlı kökle aynı olmak zorundadır. TLS doğrulaması
  açık, yönlendirme ve proxy kapalıdır. Kaynak metni yeni hedef oluşturamaz.
- Kaynak başına 90 saniye ve en çok 30 HTTP denemesi ayrılır. Kaynaklar seri
  çalışır; ikinci kaynağın bütçesi sıra kendisine geldiğinde başlar.
  Common Crawl istekleri arasında en az bir saniye bırakılır.
- Tek istek en fazla 30 saniye/2 MiB kullanır. Bağlantı veya geçici sunucu
  hatasında en fazla bir gecikmeli tekrar vardır; bütçe buna dahildir.
  TLS/biçim hataları tekrarlanmaz. 429/503 ve bekleme talimatı anında
  tekrar edilmez; sağlayıcının bekleme bilgisi sonuçta korunur.
- HTTP durumu, gerçek başarılı boş yanıt, zaman aşımı, TLS hatası,
  bağlantının kesilmesi ve biçim bozukluğu ayrı kalır. Common Crawl 404
  yalnız beklenen domaini taşıyan dar “No Captures found” yanıtıyla boş
  kabul edilir; genel 404/HTML boş sonuç değildir.
- Wayback tek `url=kök&matchType=domain` sorgusunda küçük sayfa ve devam
  anahtarı kullanır. Yinelenen devam anahtarı tamamlanma sayılmaz.
- Common Crawl `pageSize=1` ile sayfa sayısını alır ve her sayfayı satır
  kesme parametresi olmadan okur. Yanıt/bütçe sınırı aşılırsa eksik sayfa
  sessizce atlanmaz. Kayıt, sayfa, istek veya süre sınırında kalan kapsam
  kısmi olarak gösterilir. Seçilen indeksler upstream davranışıyla katalogdaki
  en yeni bitiş tarihinden geriye 365 günle sınırlıdır; tüm tarihsel kapsam
  iddia edilmez.
- Önceki tamamlanmış sayfalardan gelen kanıtlar korunur. İki kaynak da
  başarısız/kota nedeniyle çalışmamışsa genel sonuç başarısızdır; diğer
  kaynağın doğrulanmış başarısı varsa kısmi sonuç olabilir.
- İşçi mevcut katı JSONL sözleşmesini üretir. Ana süreç tekrar şema, sayaç,
  kök kapsamı ve kaynakları doğrular. Süreç için 240 saniyelik dış sınır vardır.
  Sonuç dosyası yalnız yeni dosyaya, özel izinle yazılır.

Standart kütüphanenin DNS çözümü ve yanıt başlığını okuma aşamaları her ortamda
socket süresiyle kesin kesilemediğinden 240 saniyelik dış süreç sınırı son
güvencedir. Kaynak bütçeleri kontrol edilir; tam bir ağ iptal garantisi olarak
sunulmaz.

## Veri uyumluluğu ve doğrulama

Profil `p0-archives-v2` olur. Yeni kanıt özeti bu profili içerir; eski
kanıtlar, aday kimlikleri ve inceleme kararları korunur. Veritabanı geçişi
gerekmez. Kaynak hata nedeni uygulamadaki sınırlı metin alanında saklanır;
ham istisna, yanıt başlığı veya sistem ayarı kullanıcı çıktısına taşınmaz.

Taşıma testleri HTTP/boş yanıt/kesinti/TLS/kota/boyut/süre ve kapsam reddini;
işçi testleri tek sorgu, sayfaların kayıpsız işlenmesi, devam anahtarı,
kısmi kanıt ve bağımsız kaynak bütçelerini ağsız sınar. Canlı deneme sonucu
ayrıca `STATUS.md` içinde yazılır; otomatik test başarısı canlı kaynak
kapsamı olarak sunulmaz.

## Birincil kaynaklar

- [Common Crawl indeks sunucusu](https://index.commoncrawl.org/)
- [Common Crawl bağlantı ve oran sınırı açıklamaları](https://www.commoncrawl.org/faq)
- [Internet Archive CDX API](https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server)
- [pywb CDX sayfalama API'si](https://github.com/webrecorder/pywb/wiki/CDX-Server-API#pagination-api)
- [pywb boş sonuç durum kodları](https://github.com/webrecorder/pywb/issues/627)
