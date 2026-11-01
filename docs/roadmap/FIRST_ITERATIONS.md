# XTI — İlk Dört Çalışma Döngüsü

**Tarih:** 29 Ekim 2026 · **Durum:** Çalışma planı; yerel temel, iki kaynaktan arama, kaynak kataloğu, kalıcı işler/beklemeler, sınırlı hedef kontrolü, inceleme sırası, JSON rapor, kontrollü bakım, bulgu/pasif aday/dış yüzey değişikliği için birleşik yerel bildirim kutusu ve okundu takibi, kayıtlı takibin durum ve dış yüzey kanıt güncellik özetleri, pasif kaynak/veri durumu ayrımı, katmanlı aday/kayıt/kapsam envanteri, tur/süre sınırlı marka, pasif yüzey ve seçili aktif yüzey izleme, sınırlı Unicode/IDN adayları, süreli istisna, sürümlü kalite ölçümü, kullanıcı onaylı DNS/TLS ve MX/SPF/DMARC dış yüzey temel kaydı, doğrulanmış sertifika kimliği, pasif alt alan adı aday/çalışma envanteri, kesin IP'ye sabitlenmiş sınırlı TCP servis kanıtı, CNAME hedef DNS kanıtı ve bunların tek anlık görüntüde ilişki özeti uygulanmıştır. Gerçek komutlar ve sınırlar [STATUS.md](../STATUS.md) ve [README](../../README.md) içinde izlenir.

0.87.0, aktör/kampanya/malware/rapor ana ve alternatif adlarıyla yerel IOC değerlerini tek ağsız aramada birleştirir; sorguyu kalıcı kaydedip her açık çalışmanın tam sonucunu önceki aynı tanımla karşılaştırır, anlamlı farkı birleşik yerel kutuya bildirir, tek/bütün etkin sorguyu sınırlı yeniler ve araştırmayı geçmişi korunan etiket/not defteriyle düzenler.

Bu belge veritabanı deneyimi az olan kullanıcı için başlangıç rehberidir. Komut örnekleri hedef kullanıcı deneyimidir; yalnız güncel README'de listelenen komutlar uygulanmıştır. Her döngü bir kullanıcı sonucuna odaklanır. Döngülerin birer hafta süreceği varsayılmaz; haftalık çalışma süresi ve donanım öğrenildikten sonra takvimlendirilir.

Güncel kullanıcı hedefi: **İzlenecek domaini ver → internette ara → neden eşleştiğini gör → kararını kaydet → düzenli kontrol et.** Örnek dosyalar, geliştirme ve isteğe bağlı içe aktarma içindir; internet aramasının ön koşulu değildir. Aşağıdaki döngüler temel geliştirme sırasını anlatır; kısmi uygulama durumunu STATUS.md belirler.

## Başlamadan netleştirilecek kısa bilgiler

- Bilgisayarın RAM'i, kullanılabilir diski ve işlemcisi.
- Haftada yaklaşık ne kadar geliştirme/öğrenme zamanı ayrılabileceği.
- Bilgisayarın sürekli açık mı, yalnız kullanılırken mi çalışacağı.
- İzlenecek ilk 1–3 domain/marka ve aktif kontrol yapılabilecek yetkili kapsam.
- İlk verinin saklanacağı yer ve ayrı yedek ortamı bulunup bulunmadığı.

Bu bilgiler planı geliştirmeye engel değildir; performans ve tarih taahhüdü verilmesini sınırlar. Canlı kullanım ve kapasite deneyi öncesi tamamlanır. İlk örneklerde gerçek sır veya özel sızıntı verisi kullanılmaz.

## Döngü 1 — Uygulamanın hafızası

**İşler:** FND-01, FND-02, FND-03, FND-04; FND-08'in temel çıktı ve yapılandırma kuralları.

**Kullanıcının göreceği:** Uygulama kuruluyor, kendini kontrol ediyor, domain ekliyor ve listeliyor.

```text
xti init
xti doctor
xti assets add example.com
xti assets list
```

**Üründe yapılacaklar:** Python paketi; CLI giriş noktası; ayar dosyası; uygulama veri dizini; SQLite bağlantısı ve şema sürümü; varlık ekleme/listeleme; geçersiz girdiye anlaşılır hata; aynı domaini yeniden eklemede belirlenmiş davranış.

**Öğrenilecekler:** Terminal komutu ve yardım; dosya/klasör; sanal ortam; tablonun bir kayıt grubu, satırın tek bir kayıt olduğu; verinin nerede durduğu; Git ile değişikliği izleme.

**Demo:** `example.com` eklenir. Uygulama kapatılıp açılır, kayıt hâlâ vardır. `EXAMPLE.COM` tekrar eklendiğinde ikinci varlık oluşmaz. Geçersiz domain anlamlı hata verir. Uygulama sürümü ile veritabanı şema sürümü görülebilir.

**Bitiş kanıtı:** Temiz kurulum notu, örnek terminal çıktısı, kalıcılık/tekrar/bozuk veri kontrolleri. Kullanıcı günlük iş için SQL çalıştırmaz.

## Döngü 2 — Örnek veriden açıklanabilir bulgu

**İşler:** FND-05, PHI-01, PHI-02, PHI-05; FND-08 girdi güvenliği.

**Kullanıcının göreceği:** Dosyadan örnek domainler alınır, eşleşen adayın nedeni görülür, karar kaydedilir.

```text
xti import domains ./examples/domains.jsonl
xti findings list
xti findings show 42
xti findings review 42 --decision dismissed --reason "Meşru benzerlik"
```

**Üründe yapılacaklar:** Gözlem/bulgu/kanıt/geri bildirim modelleri; sentetik veri dosyası; domain normalleştirme; marka ve benzerlik kuralları; kural sürümü; kaynak ve zaman; bulgu gerekçesi; karar geçmişi; güvenli metin gösterimi.

**Öğrenilecekler:** Gözlem ile bulgunun farkı; benzerliğin phishing kanıtı olmadığı; yanlış alarm; kurala dayalı açıklama; JSON dosyasının ne taşıdığı.

**Demo:** Meşru domain, benzer aday, alakasız domain, Unicode örneği, yanıltıcı alt domain ve bozuk kayıt işlenir. Her beklenen sonucun nedeni açıklanır. Aynı dosya yeniden alındığında tanımlı tekil gözlem/bulgu davranışı korunur. Kullanıcı kararı kapat/aç sonrasında da görünür.

**Bitiş kanıtı:** İlk etiketli örnek kümesi; beklenen/gerçek sonuç karşılaştırması; kaçırılan ve yanlış aday listesi. Canlı dünya doğruluğu hakkında yüzde iddiası yapılmaz.

## Döngü 3 — Yeniden başlatma, kanıt ve yedek

**İşler:** FND-06, FND-07, FND-08'in kalanı, PHI-06; OPS-03'ün ilk disk/saklama sınırları.

**Kullanıcının göreceği:** Bekleyen işler izlenir, yedek alınır ve ayrı dizine geri yüklenir.

```text
xti jobs list
xti status
xti backup
xti restore ./backups/example-backup --destination ./restore-check
xti export --format json
```

**Üründe yapılacaklar:** Kalıcı işler; iş alma sahipliği ve süre aşımı; sınırlı yeniden deneme; bulgu/bildirim tekrarları; dosya/DB tutarlılığı; kanıt manifesti; tutarlı backup; ayrı dizine restore; hata günlüğü; güvenli export; başlangıç retention sınırları.

**Öğrenilecekler:** İş kuyruğu; yarım iş; transaction; tekrar güvenli davranış; yedeğin varlığı ile geri yüklenebilir olmasının farkı; aynı diskte yedeğin sınırı.

**Demo:** Bir iş sırasında süreç kapatılır. Yeniden açıldığında iş kaybolmaz; tamamlanmış bulgu çoğalmaz. Kanıt dosyası eksikse tanı ekranı bunu gösterir. Yedek yeni dizine açılır; varlıklar, kararlar ve kanıt özetleri karşılaştırılır. Bozuk yedek mevcut verinin üstüne sessizce yazmaz.

**Bitiş kanıtı:** Kapatma noktaları test sonucu, tekrar oynatma raporu, restore raporu ve kısa kurtarma yönergesi. İlk G1 değerlendirmesi yapılır; eksik madde varsa kapı tamamlandı sayılmaz.

## Döngü 4 — Tek canlı kaynağa kontrollü geçiş

**İşler:** PHI-03, PHI-04'ün gereken kısmı, OPS-01, OPS-02; OPS-04 ilk ölçümler.

**Kullanıcının göreceği:** Seçilmiş kaynaktan veri akışı, son veri zamanı, iş kuyruğu, adaylar ve kaynak hataları.

```text
xti sources list
xti watch start
xti status
xti findings list --status new
xti watch stop
```

**Üründe yapılacaklar:** Kaynak erişim deneyi; adaptör; kaynak koşulları ve kapsam kaydı; bağlantı kopması; kota/zaman aşımı; sınırlandırılmış işler; mümkünse checkpoint; replay yoksa veri boşluğu; kontrollü aday zenginleştirme; kuyruk/disk/hata ölçümü.

**Öğrenilecekler:** API/akış; ücretsiz kaynağın erişim sınırları; kaynak gecikmesi ve uygulama gecikmesi; bilgisayar kapalıyken olabilecek veri boşluğu; işlem kapasitesi.

**Demo:** Kaynak geçici olarak erişilemez yapılır; durum “kaynak sorunu” olarak görünür. Yeniden bağlanır, desteklediği ölçüde devam eder. İşleri yetiştiremediğinde bellek sınırsız büyümez; sınır ve gecikme görünür olur. Kaynak tarihsel erişim sunmuyorsa eksik dönem raporlanır.

**Bitiş kanıtı:** Bir uçtan uca canlı örnek; bağlantı kopma testi; kaynak kapsamı; gerçek donanımda RAM/disk/işlem ölçümü. G2 değerlendirmesi yapılır. Uzun çalışma ve tam operasyon kapısı G3 ayrı teslimdir.

## Bu dört döngünün sonunda teslim paketi

| Teslim | Kullanıcının kontrolü |
|---|---|
| Kurulum ve yardım | Komutları çalıştırıp yardım alabiliyorum |
| Veri konumu | Kayıtların nerede olduğunu biliyorum |
| Aday bulgu | Neden eşleştiğini ve kaynağını görebiliyorum |
| Geri bildirim | Yanlış alarmı gerekçesiyle işaretleyebiliyorum |
| Sağlık | Kaynak durmuş mu, iş gecikmiş mi ayırabiliyorum |
| Kurtarma | Yedeği ayrı konuma açıp doğrulayabiliyorum |
| Kapsam sınırları | Neyi izlemediğimizi ve hangi geçmişin eksik olduğunu biliyorum |
| Sonraki plan | Ölçülen darboğaz ve sonraki kullanıcı sonucunu biliyorum |

## Kısa terim sözlüğü

| Terim | Bu projedeki anlamı |
|---|---|
| Varlık / Asset | İzlediğin domain, IP, marka veya diğer dijital öğe |
| Gözlem / Observation | Bir kaynakta görülen kayıt; henüz tehdit kararı değil |
| Bulgu / Finding | Gözleme uygulanan kuralın ürettiği gerekçeli sonuç |
| Kanıt / Evidence | Sonucu incelemeyi sağlayan içerik ve kaynak bilgisi |
| Bildirim | Bulguyu bir kanaldan kullanıcıya ulaştırma işlemi |
| Vaka / Case | Birlikte araştırılan bulgular ve yapılan işler |
| Transaction | Bir grup veritabanı değişikliğinin birlikte tamamlanması |
| Migration | Kayıt düzenini eski sürümden yeni sürüme taşıma |
| Worker | Kuyruktan iş alıp çalıştıran süreç |
| Checkpoint | Kaynağın son tutarlı işlenen konumu |
| Retry | Başarısız işi sınırlı ve kontrollü yeniden deneme |
| Idempotency | Aynı iş tekrar geldiğinde gereksiz ikinci sonuç üretmeme |
| Retention | Verinin ne kadar süre tutulacağı |
| Adapter | Dış araç/kaynak ile uygulama arasındaki bağlantı parçası |
| Tenant | İleride hizmet alan ayrı kurumun veri ve yetki kapsamı |
| Gate / Kapı | Sonraki aşamaya geçmek için gereken doğrulama koşulu |

Bir terimi önceden bilmek başlangıç şartı değildir. İlgili özellik geliştirilirken gerçek örnek üzerinde açıklanır. Uzun vadeli bütün modülleri öğrenmeden ilk çalışan parçayı kurabiliriz.
