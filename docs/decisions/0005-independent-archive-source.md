# Karar 0005 — İkinci Kaynak ve Kaynaklar Arası Bulgu Birleştirme

**28 Ekim 2026 · 0.5.0 içinde uygulandı.**

## Seçim ve erişim kanıtı

İkinci kaynak, urlscan'in mevcut herkese açık web inceleme arşividir. Sertifika arama kaynağından bağımsız gözlemler sağlar. Anonim temel arama küçük kotalarla kullanılabilir; API anahtarı zorunlu tutulmadı. Bu sürüm kişisel, sınırlı aramalar içindir. [API açıklaması](https://docs.urlscan.io/pages/api-intro), [kullanım koşulları](https://urlscan.io/terms/)

Önce gerçek erişim denendi. Tek alan adı ve ön ek sorguları HTTP 200 döndürdü. Sonrasında gerçek `scan badssl.com --source urlscan` komutu 36 arşiv kaydını 36 gözlem olarak geçici veritabanına kaydetti; aday bulgu oluşmadı. Kaynak son 30 gün sınırı bildirdi ve bu bilgi iş geçmişinde saklandı. Bu bir kullanım/kayıt doğrulamasıdır; tehdit yakalama veya kalıcı erişilebilirlik garantisi değildir.

## Sorgu ve veri kapsamı

HTTPS GET ile `/api/v1/search/` kullanılır. Her terim için `(page.domain:marka* OR task.domain:marka*)`, en fazla 100 sonuç istenir. Alan adı parçaları indekslendiği için alt alan adları da eşleşebilir. Terimler yalnız doğrulanmış marka etiketi ve varsa sınırlı harf değişimleridir; `-` sorgu diline uygun kaçırılır. Başında wildcard veya regex kullanılmaz. [Arama kuralları](https://docs.urlscan.io/pages/search-general), [alan referansı](https://docs.urlscan.io/pages/search-api-reference)

Ek sayfalar indirilmez. `total` dönen satırlardan büyükse, `has_more` doğruysa veya dolu sayfada toplam bilinmiyorsa uyarı/kısmi durum üretilir. `has_more:false` tek başına bütün sonuçların alındığını göstermez. `search_date_limit_days` varsa geçmiş sınırı ayrı kapsam notudur; başarılı sorguyu hata yapmaz. Tarih sınırı dışında kalan kayıtlar için eksiksizlik iddiası yoktur. [Arama API sözleşmesi](https://docs.urlscan.io/apis/urlscan-openapi/search)

Yalnız `page.domain` ve `task.domain` adları alınır. Bunlar yönlendirme nedeniyle farklı olabilir. Site başlığı, tam URL yolu/sorgusu, ekran görüntüsü veya içerik indirilmez. Dönen `result`/`screenshot`/hedef URL'lere bağlanılmaz, yeni tarama gönderilmez.

## Kaynak gözlemi

Tarama kimliği `_id`/`task.uuid` alanından doğrulanır; UUIDv7 dahil geçerli UUID biçimleri desteklenir. İki kimlik varsa uyuşmalıdır. Her tarama/ad/kaynak zamanı için sabit gözlem özeti üretilir. Kaynak bağlantısı yalnız doğrulanmış kimlikle `https://urlscan.io/result/UUID/` olarak kurulur. Aynı taramanın aynı adı iki alanda yer alsa da tek gözlem olur.

`task.time` taramanın kaynak zamanıdır. Eksik zaman uydurulmaz; kapsam notu eklenir. Desteklenmeyen adlar sayılarak atlanır. Aynı arşiv kaydının yeniden alınması gözlemi çoğaltmaz. Kaynaklar farklı gözlem kimlikleri taşır; bulgu kimliği varlık/ad/kural sürümü olduğundan ikinci kaynak mevcut bulguya bağlanır. İnceleme kararı sıfırlanmaz. Arşivde bulunmak, sitenin bugün çalıştığı veya zararlı olduğu anlamına gelmez.

## İş düzeni ve hata yalıtımı

Varsayılan scan/watch iki sağlayıcıyı sırayla çalıştırır. Her sağlayıcıya ayrı iş ve deneme oluşturulur; tek kaynak seçilebilir. Worker işi kilit altında aldıktan sonra kayıtlı sağlayıcıya uygun arama servisini seçer. Kuyruk başına kilitten önce bakıp sağlayıcı seçilmez. Eski crt.sh işleri mevcut sağlayıcısıyla çalışmaya devam eder.

Beklenen kaynak erişim/yanıt hatası, diğer sağlayıcının çalışmasını veya kaydını engellemez. Her kaynağın son durumu ayrı görüntülenir. Genel doğrulama veya depolama hatası kalan işleri durdurabilir; sıraya alınan işler geçmişte görünür. Tek çalıştırıcı kilidi ve mevcut kurtarma düzeni korunur.

crt.sh ve urlscan farklı sorgu planları kullanır. Ortak alan adı kuralları, inceleme ve kayıt sözleşmeleri değişmez. Kaynak sınıfı, sorgu planlayıcı ve iş sağlayıcısı başlangıç noktasında bağlanır. Yeni kaynağın modeli sertifika kavramına bağlı değildir.

## Sınırlar

urlscan yanıtı 2 MiB ve 100 kayıtla sınırlıdır. TLS doğrulaması açık, yönlendirmeler kapalıdır. İstekler en az iki saniye aralıklıdır; uygun geçici hatalarda en fazla iki deneme yapılır. `Retry-After` ve sağlayıcının kota başlıkları değerlendirilir. Uzun bekleme komutu uyutmak yerine aynı süreçte yeni sorguları durdurur. Yanıt başlıklarından bilinen kota, gövde kesilse veya hata yanıtı gelse de korunur. Socket/okuma süre sınırı 20 saniyedir; bu bütün turun kesin bitiş süresi değildir. [Kota referansı](https://docs.urlscan.io/pages/api-rate-limits), [uygulama önerileri](https://docs.urlscan.io/pages/api-best-practices)

Kota durumu süreçler arasında kalıcı değildir. Hesap/API anahtarı yönetimi, geniş tarih araması, ücretli kapsam, toplu arşiv kopyalama ve sürekli web taraması bu dilime dahil değildir.

## Uyumluluk ve çıktı

SQL şeması 3 kalır. Ortak sayım alanı `record_count`, bilgi amaçlı kapsam alanı `coverage_notes` oldu. Geçmiş okuyucu eski `certificate_count` nesnesini yeni modele dönüştürür; veritabanındaki eski JSON'u yeniden yazmaz. Eski/yeni geçmişin birlikte yedeği ve geri yüklemesi test edilir. Yeni kayıtları eski uygulama okuyamaz; geri dönüş sürüm öncesi yedekle yapılır.

Varsayılan JSON tek nesnede genel `status` ve kaynak başına `results` içerir. Tek kaynak seçiminde tek sonuç döner. Watch tur başına tek JSON satırıdır. Kaynakların gözlem/aday sayıları ayrı tutulur; aynı adresi iki kaynakta görmek toplamda iki bağımsız bulgu gibi sunulmaz.

## Doğrulama

Adaptör testleri gerçek ağ kullanmadan kimlik, isteğe bağlı alan, tarih sınırı, kısmi yanıt, bozuk/kesilmiş JSON, boyut/süre ve kota davranışlarını doğrular. Uygulama testleri sağlayıcı seçimi, tekilleştirme, karar koruma, eski geçmiş, kuyruk/worker/retry, kısmi sonuç ve JSON biçimini kapsar. Gerçek kaynak denemesi ayrıca geçici veritabanında yapıldı; kullanıcı veritabanı değiştirilmedi.
