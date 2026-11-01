# 0023 — İkinci ücretsiz pasif kaynak değerlendirmesi

**Tarih:** 29 Ekim 2026  
**Karar:** Yeni kaynak şimdilik eklenmedi; kullanılan bağlantılar terminal kaynak kataloğunda açıklandı.

## Neden

Pasif alt alan adı keşfini yalnız crt.sh verisine bağlı bırakmamak istiyoruz. Bununla birlikte kişisel aşamada ücretsiz görünen bir bağlantının ileride ürünleşmeyi engelleyen koşul, belirsiz kota veya sürekli kesinti oluşturmasını istemiyoruz. Yeni kaynak; otomasyona açık, hedefe doğrudan trafik göndermeyen, sınırı ölçülebilen ve ilerideki kullanımımızla çelişmeyen bir erişim modeli taşımalıdır.

## İncelenen seçenekler

- **HackerTarget Host Search:** Resmî sayfa anahtarsız erişimde 20 sorgu/gün ve 50 sonuç/sorgu sınırı bildiriyor. Ancak kullanım koşulları benzer hizmet geliştiren rakiplerin erişimini dışlıyor ve içeriğin ticari kullanımını sınırlandırıyor. Gelecekte XTI'yi ürüne dönüştürme hedefiyle uyumlu olmadığı için adaptör yazılmadı. Kaynaklar: <https://hackertarget.com/find-dns-host-records/>, <https://hackertarget.com/terms/>.
- **Common Crawl URL Index:** Veri ücretsiz ve alan adı kapsamlı sorgu teknik olarak mümkün. Buna karşılık resmî SSS indeks API'sinin ağır biçimde sınırlandığını, hızlı istekte geçici engel ve 503 oluşabileceğini belirtiyor. 29 Ekim 2026 erişim deneyinde tek `example.com` sorgusu 504 verdi. Büyük veri indirme altyapısı kişisel ilk sürüm için orantısız olduğundan canlı adaptör eklenmedi. Kaynaklar: <https://index.commoncrawl.org/>, <https://commoncrawl.org/faq>, <https://commoncrawl.org/terms-of-use>.
- **Cert Spotter:** Anahtarsız List Issuances erişimi kişisel/değerlendirme kullanımı için sınırlı; üretim kullanımı kimlikli erişime yönlendiriliyor. Ayrıca crt.sh ile aynı Certificate Transparency veri ailesindedir; aradığımız bağımsız DNS/web kapsamını sağlamaz. Kaynak: <https://sslmate.com/help/reference/ct_search_api_v1>.
- **ProjectDiscovery Subfinder:** Yararlı bir açık kaynak toplayıcıdır; fakat kaynaklarının önemli bölümü ayrı anahtar ister ve anahtarsız kaynakların bir kısmı kendi testlerinde kararsız/engelli olarak işaretlenmiştir. Çekirdeğe dış süreç bağımlılığı olarak eklenmedi. İleride isteğe bağlı, sürümü sabitlenmiş bir adaptör olarak yeniden değerlendirilebilir. Kaynak: <https://github.com/projectdiscovery/subfinder>.

## Sonuç

Sırf kaynak sayısını artırmak için kırılgan veya kullanım koşulu belirsiz entegrasyon yapılmayacak. crt.sh ve urlscan mevcut güvenli sınırlarla devam eder. `sources` komutu kullanılan pasif kaynakları, DNS çözümleyicisini ve yalnız açık kullanıcı komutuyla hedefe bağlanan aktif kontrolü birbirinden ayırır. Yeni bir kaynak bulunduğunda önce küçük erişim/koşul deneyi, sonra bağımsız adaptör ve sahte ağ testleri yazılacaktır; üçüncü taraf kodu çekirdeğe kopyalanmayacaktır.

Bu karar “ikinci kaynak hiçbir zaman eklenmeyecek” anlamına gelmez. Ücretsiz kişisel aşamada güvenilir bir seçenek bulunmadığını ve tam ürün kapsamının ileride veri erişimi bütçesi gerektirebileceğini görünür tutar.
