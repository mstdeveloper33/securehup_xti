# 0036 — FIRST EPSS günlük kataloğunu anlamı ve disk sınırı korunarak yerelde tut

**Durum:** Kabul edildi · **Tarih:** 29 Ekim 2026 · **Sürüm:** 0.36.0

## Bağlam

KEV geçmişte doğrulanmış istismarı gösterir; EPSS ise bir CVE için önümüzdeki 30 günde istismar gözlenme olasılığını tahmin eder. Bu iki bilgi aynı anlamda değildir. EPSS önem, etki, tam risk veya izlenen varlıkta maruziyet kanıtı olarak sunulursa kullanıcı yanlış sonuca yönelir.

FIRST günlük tam dosyada yüz binlerce puan yayımlar. Her CVE için her gün ayrı yerel kopya tutmak kişisel ve ücretsiz kullanımda hızlı, sınırsız disk büyümesi yaratır. Birincil kaynaklar [FIRST EPSS veri sayfası](https://www.first.org/epss/data) ve sabit günlük gzip adresidir.

## Karar

- Ağ bağlantısı yalnız açık `vuln sync --source epss` komutuyla kurulur.
- Adaptör `https://epss.empiricalsecurity.com/epss_scores-current.csv.gz` adresini kullanır. Yalnız HTTPS ve aynı resmî sunucu içindeki yönlendirme kabul edilir.
- Yanıt 30 saniye, 16 MiB sıkıştırılmış, 64 MiB açılmış ve 1.000.000 kayıtla sınırlıdır. HTTP içerik kodlaması kabul edilmez; gzip dosyanın kendi biçimidir.
- UTF-8, metadata, model sürümü, puan zamanı, kesin CSV başlığı, satır şekli, CVE kimliği, yinelenen CVE ve `[0,1]` olasılıkları bütün dosya kabul edilmeden doğrulanır.
- FIRST'ün çok küçük değerler için kullandığı bilimsel gösterim sınırlı olarak kabul edilir ve en fazla 18 ondalık basamaklı sabit gösterime çevrilir.
- Geçerli tam katalog tek transaction'da uygulanır. Yeni, değişen, aynı kalan, katalogdan çıkan ve geri giren kayıt sayıları çalışma kaydında tutulur.
- Kaynak başarısızlığı ayrı bir başarısız çalışma olarak kaydedilir; önceki geçerli puanlar değiştirilmez.
- Yerelde her CVE için yalnız güncel puan tutulur. Günlük puan kopyaları biriktirilmez; başarılı ve başarısız kaynak çalışma geçmişi korunur.
- `status`, `list` ve `show` yalnız yerel kaydı okur; ağ veya gizli güncelleme yapmaz.
- EPSS hiçbir yerde önem, CVSS, tam risk, KEV durumu veya varlık maruziyeti yerine kullanılmaz.

## Sonuçlar

Kullanıcı dosya hazırlamadan resmî günlük puanları alabilir, en yüksek olasılıkları ve tek CVE ayrıntısını çevrimdışı inceleyebilir. Depolama günlük tam kopyalarla sınırsız büyümez. Bunun karşılığında yerel sistem geçmiş günlere ait tekil puan zaman serisini sunmaz; gerekiyorsa FIRST'ün tarihsel veri ürünleri ayrı kapsam ve saklama politikasıyla ele alınmalıdır.

EPSS ile KEV aynı CVE üzerinden birlikte görülebilir ancak birleştirilmiş risk veya maruziyet kararı üretilmez. NVD CVE/CVSS ve doğrulanmış ürün/sürüm eşleştirmesi ayrı katmanlardır.

## Veri ve geri dönüş

Şema 18, `epss_scores` tablosunu ekler ve mevcut `vulnerability_source_runs` tablosunu kullanır. Şema 17→18 geçişi önce doğrulanabilir yedek alır, tabloyu tek transaction'da boş oluşturur ve bütünlük kontrollerinden sonra sürümü yükseltir. Hata ana veritabanını şema 17'de bırakır. Eski kayıtlardan EPSS puanı veya maruziyet uydurulmaz. Eski uygulamaya dönüş için geçiş öncesi yedek kullanılır.

## Doğrulama

Testler güvenli taşıma ve katı ayrıştırmayı; bilimsel sayı gösterimini; ekleme, aynı kalma, değişme, katalogdan çıkma ve geri girişi; kaynak hatasında eski kataloğun korunmasını; bozuk saklı kayıtta güvenli durmayı; terminal, kilit, yedek/restore ve şema 17→18 yollarını doğrular. Otomatik testlerde gerçek ağ kullanılmaz.

Ayrı canlı doğrulamada 29 Ekim 2026 tarihli `v2026.06.15` modelinden 397.508 kayıt 5,30 saniyede atomik olarak alındı. Veritabanı 128 MiB oldu; `status`, `list` ve `show` öncesi/sonrası SHA-256 aynı kaldı. Bu tek cihaz ölçümüdür, kapasite garantisi değildir.
