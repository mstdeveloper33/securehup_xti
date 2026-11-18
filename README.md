# XTI — Dijital Risk ve Tehdit İstihbaratı Motoru

**Sürüm:** 0.159.0 · **Tarih:** 18 Kasım 2026 · **Çekirdek şema:** 75 · **İş kuyruğu:** 2.

**Ürün hedefi:** Kendi platformumuzun kapalı kaynak XTI motoru.
İlk ticari kullanım yalnız kendi sunucularımızda hizmet olarak planlanır;
müşteri sunucusuna kurulum ilk sürümün kapsamına alınmamıştır.
Lisans ve veri kullanım koşulları uygun hazır bileşenlerden yararlanılır.
Ortak istihbarat, ilişki araştırması ve kaynak kapsamı için sonraki işler
[motor geliştirme planında](docs/roadmap/ENGINE_INTEGRATION_ROADMAP.md)
kayıtlıdır; planlanan yetenekler mevcut sürüme dahil sayılmaz.

Kullanım koşulları, maliyetler, ertelenen doğrulamalar ve korunacak kararlar
[NOTES.md](NOTES.md) içinde takip edilir; durumları değiştikçe güncellenir.

0.159.0, `./xti research securehup.com --type domain` içinde kayıtlı CNAME
yollarını ve aynı TLS sertifikasının gözlendiği domainleri birleştirir.
Bağlantının kaynağı/tarihi, son başarısız kontrol ve sertifikanın geçerlilik
tarihleri korunur. Aynı görünüm öncelik, kayıtlı inceleme ve firma JSON
işlemlerinde kullanılır. Yeni internet isteği, ücretli API veya şema
geçişi yoktur. Ortak sertifika sahiplik veya tehdit kararı değildir.
[Kullanım ve kapsam](docs/RESEARCH.md#cname-ve-gözlenmiş-tls-sertifikaları).

0.158.0 kaynak işlerinde HTTP denemesi, alınan yanıt, bağlantı hatası ve
429 bekleme yanıtını saklar; terminal ve firma JSON çıktısı işin sınırını,
gerçek ölçümü ve durma nedenini ayırır. Kesilmiş/eski işte ölçülmeyen
istekler sıfır gösterilmez. Abonelik ve ortak kota politikası backendin
sorumluluğudur. [Kullanım ve ölçüm sınırları](docs/SOURCE_JOBS.md#işin-kullanım-raporu).

0.157.0, CIRCL/urlscan ve seçilmiş MISP listelerini aynı kalıcı iş kuyruğuna
bağlar. `source-jobs plan/submit/worker/status/result/cancel/retry` ile
kaynak seçimini, ilerlemeyi ve sonucu görebilirsin. İsteğe bağlı
`--record-review` güncelleme ardından incelemeyi kaydeder. Firma JSON girişi
aynı akışı sunar. Kesilen istek otomatik tekrarlanmaz; tamamlanmış kaynak
adımları açık yeniden denemede korunur. Yeni kişisel kuyruk için
`source-jobs init`, eski kuyruk için yedekli `source-jobs migrate` kullanılır.
Yeni ücretli API veya paket yoktur. [Kullanım ve sınırlar](docs/SOURCE_JOBS.md).

0.156.0, `./xti research-history record securehup.com --type domain` ile
o anki incelemeyi saklar ve önceki aynı kapsamlı kayıtla karşılaştırır.
Yeni kanıt, geri çekilen kaynak iddiası ve yalnız zamanla eskiyen bilgi
ayrı gösterilir. `list/show` geçmişi okur; firma platformu aynı kayıt ve
okuma işlemlerini sunar. Yeni API maliyeti, LLM veya internet çağrısı yoktur.
Mevcut alanlarda önce yedekli `./xti migrate` gerekir.
[Kullanım ve kapsam](docs/RESEARCH_HISTORY.md).

0.155.0, `./xti research securehup.com --type domain --priorities` ile
"önce hangi kaydı incelemeliyim, neden?" sorusuna gerekçeli bir liste verir.
Etkin IOC iddiası, kaynak durum farkı, eski/eksik kanıt ve son başarısız
kontrol ayrı görünür. Aynı çıktı firma kapsamında `research.priorities`
işleminden alınır. Mevcut kayıtları okur; ücretli API, LLM, yeni bağımlılık
veya 74'ten yeni bir şema geçişi gerektirmez.
[Kullanım, kurallar ve kapsam](docs/RESEARCH_PRIORITIES.md).

0.154.0, `enrich fetch/lookup/history/run-show` ile URL ve dosya kimliği
araştırmasını ekler. CIRCL bilinen dosya bağlamını, urlscan mevcut public
tarama kayıtlarını sağlar. Kaynak, tarih, son hata ve korunan yanıt görünür;
URL/hash sonuçları `research` ve firma kapsamlı JSON üzerinden de okunur.
Bu dilim anahtar/ücretli API gerektirmez; urlscan verisini ticari ürüne
dahil etmek için sağlayıcı koşulları ayrıca netleştirilmelidir.
Mevcut veri alanı için yedekli `./xti migrate` gerekir.
[Kullanım, kaynak koşulları ve sınırlar](docs/INDICATOR_ENRICHMENT.md).

0.153.0, MISP'in dört açık kaynak listesini IP/domain araştırmasına ekler:
Cloudflare ortak altyapısı, özel IPv4, örnek IPv6 ve özel kullanım domainleri.
`./xti warninglists sync` internetten alır; `warninglists lookup` ve
`research` kaynaklı eşleşmeleri gösterir. Anahtar/ücretli API gerekmez.
Son iyi liste, hata geçmişi ve firma ayrımı korunur; eşleşme alarm kapatmaz.
Mevcut veri alanı için yedekli `./xti migrate` gerekir.
[Kullanım ve sınırlar](docs/WARNINGLISTS.md).

0.152.0, `./xti research securehup.com --type domain` ile kayıtlı domain/IP,
DNS ve IOC/CTI kanıtlarını en fazla iki adımlı yollarla birleştirir. Kaynak,
tarih, eski/geri çekilmiş iddia ve eksik kapsam görünür; yeni toplama veya
ücretli API gerekmez. Aynı işlem firma kapsamlı `research.show` JSON
sözleşmesindedir. [Kullanım ve kapsam](docs/RESEARCH.md).

0.151.0, kaynak hatası, tamamlanmış boş sonuç, kısmi kanıt ve korunan eski
sonucu daha açık gösterir. `collect`, `search` ve `organizations report`
komutlarında `--summary` kısa terminal görünümünü seçer; ayrıntı komutları
seçili veri klasörünü korur. JSON, toplama kapsamı ve kayıtlar değişmez.
[Örnek kullanım](docs/DAILY_USE.md#kısa-görünüm-ve-kayıt-ayrıntıları).

0.150.0, yetkili IP/CIDR Nmap planlarını kalıcı kuyruk, hedef başına kanıt,
iptal ve kesinti kurtarmasıyla çalıştırır. TCP connect/SYN/UDP,
servis/sürüm, OS tahmini ve seçilmiş NSE kontrolleri tipli seçeneklerdir.
Terminal ve firma kapsamlı platform JSON girişi aynı motoru kullanır.
SYN/UDP/OS yetkili çalıştırıcı ister. [Kullanım ve sınırlar](docs/NMAP_MANAGED.md).
Tavily dışındaki gerçek kaynak ve yerel kullanım sonuçları, başarısız
arşiv erişimleri dahil, [kullanım kabulünde](docs/FUNCTIONAL_ACCEPTANCE.md)
ayrı gösterilir.

XTI, SQLite ile kişisel terminal kullanımını ve güvenilen başlatıcının
seçtiği ayrı firma alanlarında platform kullanımını destekler. Bu repo
toplama ve analiz motorunu, sürümlü sözleşmeleri, kullanım örneklerini
ve belgeleri sunar; kaynaklı kanıt ve iş geçmişini korur. Platform girişi
firma kapsamlı okuma, kalıcı toplama işi kabulü, açık worker ve birlikte
yedek/geri yükleme sağlar. .NET bağlantısını repoyu kullanan ekip geliştirir.
.NET istemcisi/backend'i, kullanıcı/oturum/rol yönetimi, web paneli ve
platformun PostgreSQL yerleşimi ile gerekiyorsa veri geçişi o ekibin
sorumluluğundadır. Motorun veri bütünlüğü ve iş sözleşmeleri bu repoda
geliştirilmeye devam eder. Firma seçimi JSON isteğine veya kuruluş adına
bırakılmaz; platformun yetkilendirdiği başlatıcı tarafından yapılır.
Uygun yerel açık kaynak bileşenler kullanılır; OpenCTI/IntelOwl zorunlu
değildir ve henüz bağlı değildir. .NET bağlantısı da henüz uygulanmadı.
Mevcut sınırlı STIX çıktısı korunur; geniş STIX/TAXII paylaşımı ve isteğe
bağlı LLM desteği en son, ihtiyaç oluşursa değerlendirilecek başlıklardır.
Kurulum, güncelleme, test, hata yönetimi ve kurtarma davranışlarının
doğrulama kapsamı ve sonuçları [kabul kaydında](docs/STATUS.md) izlenir.
Görev paylaşımı ve teslim sırası
[motor yol haritasındadır](docs/roadmap/ENGINE_INTEGRATION_ROADMAP.md).

Kurulumdan sonra günlük kullanım, yarım kalan toplama ve yedekten dönüş
adımları [başlangıç rehberindedir](docs/GETTING_STARTED.md).
Sınanmış sürüm/ortam ve gerçek Linux kabul sonuçları
[durum belgesinde](docs/STATUS.md) kaydedilir.

Firmanı ve seçtiğin tedarikçileri Tavily ile birlikte aramak, günlük sorgu
sınırı koymak ve yeni/değişen içerikleri mevcut bildirim kutusunda görmek
için [firma izleme grupları rehberini](docs/MENTION_GROUPS.md) kullan.
Terminalde sınırlı tekrar ve Linux günlük/haftalık zamanlama dosyaları
desteklenir; kaynak kullanımı kendi Tavily anahtarını gerektirir.

Engine'in ilk sürümlü bağlantısı kullanılabilir: `./xti engine --describe`
desteklenen işlemleri gösterir. `./xti engine`, standart girdiden tek JSON
isteği alarak kayıtlı verilerde arama, kayıt ayrıntısı, kaynak durumu ve
projedeki araçların kurulum bilgisini okur. Eski komutlar ve `--json` çıktıları korunur. Bu bağlantı toplama
başlatmaz; mevcut toplama komutları kullanılmaya devam eder. Dört işlem
korunur; haber ve firma içerik kayıtlarını da okuyabilir. [Engine kullanım ve sözleşme rehberi](docs/ENGINE_CONTRACT.md).

Çok firmalı kullanım için ayrı `./xti platform` girişi vardır. Her firmanın
kanıtları ve kalıcı iş anahtarları kendi kayıt alanında tutulur. Aynı iş
isteği eski işi döndürür; kesilmiş iş otomatik yeniden çalıştırılmaz.
`organizations content KURULUS_KIMLIGI` kayıtlı firma/tedarikçi başlığını,
mevcut açıklamasını, bağlantısını ve yayın tarihini gösterir; güncel ve
tarihî kapsamı, boş sonucu ve kaynak hatasını ayırır.
[Platform kurulumu, sözleşme ve kurtarma](docs/PLATFORM_ENGINE.md).
Bu görünüm internet araması yapmaz. Gerçek firma/tedarikçi Tavily kabulü
kullanıcının daha sonra sağlayacağı anahtarı bekler.

Bağlı açık kaynak araçlarını tek yerde görmek için:

```sh
./xti components
./xti --json components
```

Maigret, Sherlock ve theHarvester'ın beklenen sürümü, kullanım kapsamı ve
yerel kurulum durumu gösterilir. Bu okuma araç çalıştırmaz; internetten veri
toplama başarısı ayrıca kaynak geçmişinden izlenir. Aynı görünüm engine
`components.list` işleminde vardır. [Araç kataloğu rehberi](docs/COMPONENTS.md).

Kuruluş birleşik raporu, kuruluşa özel değişim/kaynak görünümü, ayrıntılı
önce/sonra kanıtı, CTI ilişki bağlamı ve ücretsiz kamu ihlal kataloğu kullanılabilir.
Kamu olayının tarihî kanıtını vakaya bağlayabilir, kuruluş raporunu tek HTML
dosyası olarak internetsiz açabilirsin: [kullanım rehberi](docs/PUBLIC_NOTICE_CASES_AND_EXPORT.md).

Tek komutla yerel arama, tedarikçi değişim bildirimleri ve domainin IP/sertifika/
CNAME/tedarikçi ilişki geçmişi de kullanılabilir: [yeni özellikler rehberi](docs/SEARCH_SUPPLIERS_AND_RELATIONS.md).

Kendi alan adını yaz; XTI herkese açık sertifika ve geçmiş web inceleme kayıtlarında benzer adları arasın, adayları gerekçeleriyle kaydetsin. Adres listesi hazırlaman gerekmez. Bir aday bulgu kesin phishing/dolandırıcılık kararı değildir.

Aktif ürün kapsamı dış kaynaklı OSINT/XTI'dır. Sunucu içine ajan kurulmaz; ürün/sürüm, Ubuntu/Red Hat paketi veya CVE eşleştirmesi birleşik analizde kullanılmaz. Önceki sürümlerde oluşmuş bu tür kayıtların kodu ve şeması veri uyumluluğu için korunur, fakat aktif geliştirme planının parçası değildir.

## Hızlı başlangıç

Çekirdek için Python 3.11 veya daha yeni bir sürüm gerekir. Önceki Linux
kabul turlarında temiz kurulum Ubuntu 24.04 x86_64 üzerinde Python 3.11 ve 3.12 ile doğrulandı;
ayrıntılar aşağıdaki [ortam tablosundadır](#sınanmış-ortamlar).
Kurulum global Python ortamına paket kurmaz; sosyal kullanıcı adı araçlarını
ve haber ayrıştırıcısını proje içindeki `.venv` ortamına kurar:

```sh
git clone https://github.com/mstdeveloper33/securehup_xti.git
cd securehup_xti
./setup
./xti assets add example.com
./xti scan example.com --typos
```

Sonraki kullanımlarda proje klasöründe doğrudan `./xti` komutunu çalıştır.
Yerel veriler `.xti-data` altında kalır ve GitHub'a gönderilmez. Ayrıntılı ama
kısa kurulum ve güncelleme rehberi için
[XTI hızlı başlangıç belgesine](docs/GETTING_STARTED.md) bak.

## Nereden başlayacağım?

Aynı toplama seçimini her seferinde yazmamak için bir profil kaydet:

```sh
./xti profiles save gunluk example.com
./xti collect --profile gunluk --plan
./xti collect --profile gunluk
./xti profiles show gunluk
```

Domain önceden `assets add` ile kayıtlı olmalı. `profiles save` seçimleri
kaydeder; internetten toplama başlatmaz. `--plan` yalnız önizler. Profil
kaydederken `collect` ile aynı `--task` ve izleme seçeneklerini verebilirsin.
Aynı adla yeniden kaydetmek **tam seçimi değiştirir**; eski seçenekler otomatik
eklenmez. Değişiklikler geçmişte korunur. `profiles list` kayıtları gösterir;
`profiles revoke gunluk --reason "Şimdilik kapalı"` çalıştırmayı kapatır.
Eski kurulumda şema 69 için önce `./xti migrate` çalıştır; geri dönüş yedeği
otomatik alınır. Sekiz teslimin durumu [sıralı plandadır](docs/roadmap/ORDERED_INTEGRATION_PLAN.md).

Her yeni toplama bir oturum kimliği verir. Geçmişini açabilir ve eksik
kalan işleri yeniden deneyebilirsin:

```sh
./xti collections list
./xti collections show OTURUM_KIMLIGI
./xti collections resume OTURUM_KIMLIGI --plan
./xti collections resume OTURUM_KIMLIGI
```

Kimliği ilk komutun çıktısından al. Tamamlanan kaynak/izleme kayıtları
korunur; eski kısmi sonuç değiştirilmeden yeni yürütme açılır. Bilgisayar
kapanmış ve oturum hâlâ çalışıyor görünüyorsa `./xti collections recover`
ile kesilmiş kayıtları kapatabilirsin. Bu komut internetten toplama yapmaz.

```sh
./xti sources status
./xti sources status --domain example.com
./xti sources status --domain example.com --details
```

Bu ekran kaynak/iş akışlarının kurulumunu, son çalışma sonucunu, son başarılı
yerel kaydın güncelliğini ve önerilen sonraki komutu birlikte gösterir.
Tarama ile alt alan adı keşfi ayrı satırlardır. `--domain` bu iki işlemi seçilen
domaine daraltır; sosyal izlemeler ve genel beslemeler kendi kapsamını korur.
İlk iki komut kısa tablo, `--details` kapsam ve kanıt zamanlarını gösterir.
`./xti --json sources status` aynı bilgileri makine-okunur verir.

Durum ekranı yerel geçmişi okur; kaynakları yenilemek için gösterilen komutları
çalıştırman gerekir. MITRE ATT&CK geçmişinde başarısız senkron denemesi
tutulmadığından son deneme bilinmiyor olarak kalır; kayıtlı başarılı veri
ayrıca gösterilir. Verinin yeni alınmış olması kaynağın güncel veya şu an
erişilebilir olduğunu garanti etmez.

İlk gün kayıt, veri toplama, sonuç inceleme, gerçek adayı vakaya ekleme ve
sonraki gün tekrar için [günlük kullanım rehberini](docs/DAILY_USE.md) izle.

## Linux'ta günlük çalıştırma

Kayıtlı `gunluk` profili için:

```sh
./xti schedule generate gunluk --output ./.xti-data/zamanlama-gunluk --at 09:00 --timezone Europe/Istanbul --keep 7
```

Komut yalnız yeni klasöre hizmet/zamanlayıcı dosyaları ve bilgisayarına özel
kurulum komutları içeren `README.txt` üretir. Hizmeti etkinleştirmez. Her
çalışma öncesi profil, kilit, disk alanı ve kesilmiş oturum kontrol edilir;
yeni yedek alınıp ayrı dosyaya geri yükleme doğrulanır. Saklama yalnız kendi
kayıtlı zamanlanmış yedeklerine uygulanır. Ayrıntılar ve Linux'ta etkinleştirme
[zamanlama rehberindedir](docs/LINUX_SCHEDULING.md).

## Kuruluş altında açıkça grupla

```sh
./xti organizations add "Örnek kuruluş"
./xti organizations link KURULUS_KIMLIGI --kind domain --value example.com
./xti organizations link KURULUS_KIMLIGI --kind ransomlook-watch --value IZLEME_KIMLIGI
./xti organizations show KURULUS_KIMLIGI
```

Büyük harfli yerleri komutların verdiği gerçek kimliklerle değiştir. Domain
ve izleme önceden kayıtlı olmalı. Sosyal izleme için `username-watch`,
ThreatCluster için `ransomware-watch` seçilir. `organizations list` grupları
listeler; `unlink`, `rename`, `revoke` ve `reactivate` değişiklik geçmişini korur.
Gruplama sahiplik veya ihlal doğrulaması değildir; toplama başlatmaz ve
profillerin seçimini değiştirmez. Aynı kayıt birden çok grupta bulunabilir.

Kuruluşun bütün bağlı domain ve izlemelerinin kayıtlarını birlikte aç:

```sh
./xti organizations report KURULUS_KIMLIGI
./xti changes --organization KURULUS_KIMLIGI --days 7
./xti sources contribution --organization KURULUS_KIMLIGI
```

Raporda gerçek adresler, profil/iddia kayıtları, son deneme ve son başarı,
eski/eksik veriler, bildirimler ve ilgili mevcut vakalara geçiş bulunur.
Firma ve seçilmiş tedarikçiler için saklanan Tavily içerikleri de kaynak,
bağlantı, arama kapsamı ve güncellikle görünür. Tedarikçi kapsamı kuruluşun
etkin `mentions groups` seçiminden gelir; eski ilişkiler tarihî bölümde kalır.
Geri çekilmiş domain/izleme bağlantıları güncel hedef bölümlerine girmez. `--target-offset/--target-limit`
hedefleri, `--item-offset/--item-limit` her bölümdeki kayıtları sayfalar;
toplamlar değişmez. Bu bir yerel gruplamadır, müşteri erişim yalıtımı değildir.
[Kuruluş raporu rehberi](docs/ORGANIZATION_REPORT.md) bütün komutları açıklar.

## Son bir günde veya bir haftada ne değişti?

```sh
./xti changes --days 1
./xti changes --days 7
./xti changes --days 7 --domain example.com
./xti --json changes --days 7
```

Rapor son 24/168 saatte **yerelde kaydedilen** yenilikleri, değişimleri,
ilk ölçümleri ve kaynak hatalarını ayrı gösterir. Varsayılan bütün yerel
marka, dış yüzey, sosyal, iki ransomware kaynağı, toplama oturumları ve kamu
olay kataloğudur. Domain filtresi marka, dış yüzey ve katalogdaki tam domain
eşleşmelerini kapsar. `--organization` yalnız kuruluşun güncel etkin
bağlantılarını seçer; geçmişte sahiplik varmış gibi yorumlanmaz.

Her satırın kayıt/izleme/çalışma kimliği bulunur. Aynı iddianın farklı
kaynaklardaki satırları tek doğrulanmış olay sayılmaz. `--limit 200` bölüm
başına gösterimi artırır; `--offset 200` sonraki sayfayı açar. Toplam ve
gösterilmeyen sayı ayrıca verilir. DNS/TLS/web/posta/servis/CNAME satırlarında
saklanmış önce/sonra değerleri ve önceki kayıt kimlikleri bulunur. Başarısız
kontrol boş değerle karşılaştırılmaz; son başarılı ölçüm korunur.
Komut internete çıkmaz, yeni analiz veya bildirim oluşturmaz.

## Hangi kaynak hangi adresleri getirdi?

```sh
./xti sources contribution example.com
./xti sources contribution example.com --family brand
./xti sources contribution example.com --family surface
./xti sources contribution example.com --detail-limit 50 --detail-offset 50
./xti --json sources contribution example.com
```

Gerçek domain listeleri, ortak adresler, yalnız bir kaynakta bulunanlar ve
bunların kanıt kimlikleri gösterilir. Ayrıntı sayfası değişse de toplamlar
korunur. `--detail-limit` 1–500; sonraki sayfa başlangıcı çıktıda belirtilir.
Marka araması ve alt alan keşfi ayrı değerlendirilir. Görülen oran,
tamamlanan kayıtlı denemelerin toplam bitmiş denemelere oranıdır; doğruluk
veya internet kapsama oranı değildir. Hiç veri yoksa oran bilinmiyor kalır.

Bu rapor ağsız ve yazmasızdır. Kaynaklarda görülen bir alt alan adı otomatik
olarak sana ait sayılmaz; mevcut inceleme kararı ayrıca gösterilir. Bu
karşılaştırmaya yeni domain keşif sağlayıcısı eklenmedi: katkı ve erişim koşulları doğrulanmadan
adaptör seçilmeyecek. Common Crawl'ın dış erişim sorunu açık kalıyor;
ücretsiz erişim, sınırsız sorgu veya kesintisiz hizmet garantisi değildir.
[Karar dayanağı](docs/roadmap/SOURCE_PROVIDER_EVALUATION.md) ayrıntıları açıklar.

## Ücretsiz kamu ihlal kataloğu ve CTI ilişkileri

Kuruluşuna bağladığın domainler için yerel bildirimleri açıkça açabilirsin:

```sh
./xti notices watch enable KURULUS_KIMLIGI
./xti notices refresh
./xti notices watch show KURULUS_KIMLIGI
./xti inbox list
```

İlk değerlendirme sessiz başlangıçtır. Sonraki yeni/değişen tam domain
eşleşmeleri çalışma başına tek bildirim oluşturur; önceki/sonraki metadata,
gerçek kaynak ve tarihî kuruluş kapsamı korunur. Yeni domainin ilk ölçümü
sessizdir; mevcut domainlerin değişimleri bildirilmeye devam eder. Okuma
komutları ağ kullanmaz ve bildirimleri okundu yapmaz. Ayrıntılar ve kapatma
komutu [kuruluş kamu olay izlemesi rehberindedir](docs/PUBLIC_NOTICE_WATCHES.md).

HIBP kataloğunu günlük toplama profiline de katabilirsin:

```sh
./xti collect example.com --task scan-crtsh --task scan-urlscan --task discover-crtsh --task notices-hibp --plan
./xti profiles save gunluk example.com --task scan-crtsh --task scan-urlscan --task discover-crtsh --task notices-hibp
./xti collect --profile gunluk
```

`--task` tam seçimi belirtir; yalnız `--task notices-hibp` kullanırsan sadece
katalog yenilenir. Kayıtlı bir domain gerekir. HIBP açık seçimlidir; eski
profillerin seçimi ve geçmişi korunur. Normal varsayılan üç iş aynıdır.
Bu profil mevcut `schedule generate` akışıyla zamanlanabilir; dosya üretimi
ve hazırlık komutları kaynak sorgusu veya hizmet etkinleştirmesi yapmaz.

Katalog ve toplama sonucu aynı işlemde kaydedilir. Başarılı indirmeden sonra
üst işlem kesilirse `collections resume` bu kaydı korur; yalnız eksik işleri
çalıştırır. Kaynak hatası son başarılı kataloğu silmez ve toplamayı başarılı
göstermez. Katalog sayaçları bütün kaynağa aittir, domainin bulgu sayısı değildir.
İlk alım tarihî başlangıç çizgisidir. Ayrıntı için çıktıdaki `notices run-show`
komutunu kullan; terminaldeki kısa görünüm saklanan kataloğu kısmaz.

```sh
./xti notices refresh
./xti notices search --domain example.com
./xti notices search "kuruluş adı"
./xti notices status
./xti cti context --type domain --value example.com
./xti cti context --entity CTI_VARLIK_KIMLIGI
```

`notices refresh`, [Have I Been Pwned](https://haveibeenpwned.com) kamu
olay kataloğunu tek istekle alır; API anahtarı veya ücretli abonelik gerekmez.
Diğer komutlar yerel kayıtları okur. Katalog olay adı, domain, tarih ve
kaynak sınıfları içerir; e-posta/hesap/parola sorgusu yapmaz. İlk alım
başlangıç ölçümüdür. Hata son başarılı veriyi silmez; tam domain eşleşmeleri
kuruluş ve dönem raporuna girer. Kaynak atfı ve CC BY 4.0 lisansı korunur.
[Erişim ve kapsam doğrulaması](docs/PUBLIC_NOTICE_SOURCE_ACCEPTANCE.md).

`cti context`, tam IOC değerinden veya kayıtlı varlık kimliğinden bir adım
uzaktaki mevcut aktör/kampanya/malware/rapor ilişkilerini dayanaklarıyla açar.
İlişkiyi sistem kendisi çıkarmaz; kaynağın iddiasını ve etkinlik durumunu
gösterir. Kayıt bulunmaması güvenli olduğu anlamına gelmez. Ayrıntı ve
sayfalama [kuruluş rehberinde](docs/ORGANIZATION_REPORT.md) yer alır.

## Firma ve tedarikçi hakkında içerik ara

Tavily ile firma adına gerçek web/haber araması yapabilir, sonuçları
kaynakları ve önceki halleriyle saklayabilirsin. Kendi Tavily hesabından
API anahtarı gerekir; ücretsiz krediyle başlanabilir. Anahtarı repoya yazma.

```sh
./xti migrate
./xti mentions configure
./xti mentions plan --name "Örnek Firma" --domain example.com
./xti mentions search --name "Örnek Firma" --domain example.com --topic news
./xti mentions list
./xti mentions status
```

`configure` gizli girişle özel anahtar dosyasını oluşturur. `plan` ağsızdır;
`search` tek temel istek gönderir (belgelenen tüketim 1 kredi), otomatik tekrar
yapmaz. `--organization KIMLIK` veya `--supplier KIMLIK` ile kayıtlı hedefler
de seçilebilir. Başlık, bağlantı, açıklama, eşleşme gerekçesi ve yeni/değişen/aynı
ayrımı gösterilir; sonuçlar doğrulanmış tehdit sayılmaz.

Kayıtlar `search --kind mention`, mevcut kayıtlı arama ve engine v1 üzerinden
de okunur. Okuma internet veya API anahtarı istemez. Geçiş önceki veriyi
yedekler; Tavily için ek paket kurulmaz. [Kurulum, örnekler ve sınırlar](docs/MENTIONS.md).

## RSS ve Atom haberlerini topla

Ücretsiz CISA, Birleşik Krallık NCSC ve Fransa CERT-FR yayınlarını
internetten okuyabilirsin. RSS/Atom ayrıştırıcısı hazır `feedparser`
kütüphanesidir; toplama, kanıt, arama ve bildirim bağlantısı XTI'dadır.
Normal `./setup` sabit sürümleri kurar. Önceki kurulumunu güncellerken:

```sh
git pull --ff-only
./xti migrate
./scripts/setup-brand
```

Geçiş yedek alır. Kurucu, haber paketleri eksikse mevcut araç ortamını
benzersiz yedekte koruyarak yeniler. Sağlıklı tekrar paket indirmez.
`./setup --core-only` ek paket kurmaz; haber toplamak için yukarıdaki
kurulum gerekir. Haber kaydı okuma/aramanın kendisi parser istemez.

Kaynak seç ve haberleri getir:

```sh
./xti news sources
./xti news refresh --source cisa
./xti news refresh --source ncsc
./xti news refresh --source cert-fr
./xti news list
./xti news list "example.com" --limit 20
./xti news status
```

`news` komutlarında yalnız `refresh` internete çıkar. Her `refresh` bir kaynağı bir kez okur;
haber sayfaları, resimler ve ekler açılmaz. Başlık, yayıncının sunduğu
en fazla 2.000 karakterlik düz metin özet, özgün bağlantı ve kaynak
tarihleri saklanır. Özet kısaltılmışsa açıkça gösterilir. Eksik veya
ayrıştırılamayan tarih bilinmiyor olarak kalır; toplama tarihi yayın
tarihi yapılmaz. Yayıncının ham tarih metni ayrıca görülebilir.

```sh
./xti news show HABER_KIMLIGI
./xti news run-show CALISMA_KIMLIGI --offset 0 --limit 20
./xti news status --source ncsc --offset 0 --limit 20
./xti search "example.com" --kind news
./xti --json news list "example.com"
```

Kimlikleri komut çıktısından al. Gösterim sınırı toplama kapsamını kesmez;
sonraki sayfa komutu veri dizini ve filtreleri korur. Çalışma ayrıntısı
o sırada alınan haberleri, aynı olanlar dahil, önce/sonra kanıtıyla açar.
`news show` haberin son bilinen halini; `run-show` tarihî kanıtı gösterir.
Akıştan çıkan eski haber silinmez. Başka yayıncı aynı kimliği kullanırsa
ayrı kayıttır. Aynı haberin tekrar alınması yeni haber sayılmaz; başlık,
özet veya kaynak tarihi değişirse yeni içerik hali kaydedilir.

Bir kuruluş veya domain için yerel bildirim takibi:

```sh
./xti search-watch add "Markam haberleri" "example.com" --kind news
./xti search-watch run ARAMA_KIMLIGI
./xti news refresh --source ncsc
./xti search-watch run ARAMA_KIMLIGI
./xti inbox
```

İlk arama çalışması sessiz başlangıçtır; sonraki yeni/anlamlı değişen
eşleşmeler yerel kutuya gelir. Kaynak yenileme tek başına izlemeyi
çalıştırmaz. `search-watch monitor` yerel karşılaştırmayı tekrarlar;
haberleri internetten yenilemez. Eski kayıtlı aramaların somut tür listesi
korunur; haber eklemek açık yeni tanım veya aynı adla `add` gerektirir.
Bir marka adının haber içinde geçmesi doğrulanmış ihlal anlamına gelmez.

Her kaynak için hiç toplanmadı, başarılı boş yanıt ve hata ayrıdır;
son hata önceki başarılı kayıtları silmez. Kaynaklar yayınlarını veya
erişim kurallarını değiştirebilir; ücretsiz olması sınırsız erişim
garantisi değildir. İlk sürüm sabit üç HTTPS yayını destekler, serbest URL
veya makale tarayıcısı değildir.

Haberleri ve kayıtlı aramayı aynı profilde çalıştırmak için:

```sh
./xti profiles save haberler example.com --only-news --news-source cisa --news-source ncsc --news-source cert-fr --search-watch ARAMA_KIMLIGI
./xti collect --profile haberler --plan
./xti collect --profile haberler
./xti inbox
```

`ARAMA_KIMLIGI`, yukarıdaki `search-watch add ... --kind news` çıktısından
gelir. Domain kayıtlı olmalı. Bu profil yalnız seçilen yayıncıları alır;
hedef siteye bağlanmaz. Üçü başarılıysa seçilen haber araması karşılaştırılır.
Kaynak hatasında önceki başarı korunur ve karşılaştırma atlanır. İlk ölçüm
sessiz başlangıçtır. Tamamlanan kaynakları yeniden almadan eksik adımlara
`collections resume` ile devam edilir. Profil mevcut Linux zamanlama yolunu
kullanır; hizmet kendiliğinden açılmaz. Tek kaynağı aramasız toplamak da
mümkündür. [Kurulum, kullanım ve sınırlar](docs/NEWS_COLLECTION.md).
[Canlı kullanım kabulü ve ölçülen kaynak kapsamı](docs/NEWS_SOURCE_ACCEPTANCE.md)
16 Kasım 2026 denemesinde üç kaynaktan 70 kaydın iki turda çoğalmadan
korunduğunu gösterir; bu sayı firma eşleşmesi veya tam internet kapsamı değildir.

Yanıt en fazla 4 MiB/2.000 haber; saklanan haber 50.000, çalışma 10.000,
tek kanıt görüntüsü 8 MiB ve toplam görüntü/projeksiyon ayrı ayrı 64 MiB
ile sınırlıdır. Aşımda kısmi sonuç kaydedilmez veya eski veri silinmez.
Bunlar koruma sınırlarıdır, ölçülmüş kapasite garantisi değildir.
[Karar ve kaynaklar](docs/decisions/0148-publisher-news-feeds.md).

## Genel aramayı kaydet ve değişiklikleri izle

`search QUERY` ile aradığın on bir kayıt ailesini bir ad altında izleyebilirsin.
Mevcut internet toplayıcıları kayıtları günceller; aşağıdaki komutlar bu
yerel kayıtların tamamını karşılaştırır ve sonuç farkını yerel kutuya yazar.
Kuruluş/marka adı, domain veya başka bir arama metni kullanabilirsin:

```sh
./xti search-watch add "Markam" "example.com"
./xti search-watch list
./xti search-watch run ARAMA_KIMLIGI
./xti search-watch monitor ARAMA_KIMLIGI --cycles 10 --interval 60 --duration 600
./xti inbox
```

`example.com` yerine arama metnini, `ARAMA_KIMLIGI` yerine ilk komutun
verdiği kimliği yaz. İlk `run` mevcut sonuçları sessiz başlangıç olarak
kaydeder. Sonraki çalışmada yeni veya anlamlı biçimde değişen eşleşme
varsa çalışma başına bir bildirim üretir. Değişmeyen tekrar veya yalnız
artık eşleşmeyen kayıt olması bildirim üretmez; farklar geçmişte görünür.
Bu, yerel arama sonucunun değişmesidir; olayın yeni gerçekleştiği veya
kaydın güvenlik tehdidi olduğu anlamına gelmez. Sonradan ilk kez alınan
bir kaynaktaki eski olay da yerel aramaya yeni girmiş olabilir.

`monitor` terminal açıkken seçilen aramayı tekrarlar; her turdan sonra
yazma kilidini bırakır. Kaynak yenileme komutları aralarda çalışabilir.
Toplayıcıları kendiliğinden çalıştırmaz, arka plan hizmeti kurmaz.
`Ctrl+C` ile durdurabilirsin; tamamlanmış çalışmalar korunur. Süre sınırı
yeni tur başlatmayı sınırlar, başlamış veritabanı işlemini yarıda kesmez.

Kapsamı daraltma ve geçmişi açma:

```sh
./xti search-watch add "Markam" "example.com" --kind ransomware --kind public-notice
./xti search-watch show ARAMA_KIMLIGI
./xti search-watch run-show CALISMA_KIMLIGI --offset 0 --limit 50
./xti search-watch disable ARAMA_KIMLIGI --reason "İzleme tamamlandı"
./xti search-watch list --all
./xti --json search-watch run-show CALISMA_KIMLIGI
```

Aynı adla `add` tanımı günceller veya kapalı aramayı yeniden etkinleştirir.
Tanım/etkinlik sürümü değişince yeni sessiz başlangıç yapılır; A→B→A
şeklinde eski sorguya dönmek veya kapatıp açmak eski başlangıcı sürdürmez.
Aynı tanımı yeniden eklemek değişiklik oluşturmaz. Kapatma geçmişi ve
bildirimleri silmez. `add --all` etkin olmayan kayıtların son bilinen
durumunu da kapsar; bütün eski sürümleri tek tek aramaz.

Her çalışmanın o günkü sorgusu, filtreleri, kaynak kapsamı ve önce/sonra
kanıtı saklanır. Sonradan kaynağın veya arama tanımının değişmesi eski
raporu değiştirmez. Sayfa sınırı yalnız gösterimi etkiler; karşılaştırma
tam sonuç üzerinden yapılır. Devam komutları filtreleri ve seçilmiş veri
dizinini korur. `show` için `--event-offset/--event-limit` ve
`--run-offset/--run-limit`, sonuçlar için `--offset/--limit` vardır.

Yalnız toplama zamanı, çalışma kimliği veya ayrıntı komutunun değişmesi
alarm oluşturmaz. Sosyal profiller değişen çalışma-öğe kimliğiyle değil,
araç/izleme/tanım/platform kimliğiyle izlenir. Profil durumu ve insan
kararı değişiklikleri karşılaştırılır. Ransomware kaynaklarının aynı ham
kimliği ayrı tutulur; yalnız `last_seen_at` yenilenmesi alarm oluşturmaz.
Kaynak hatası ve boş sonuç, çalışmanın kaynak kapsamında ayrı gösterilir;
son başarılı kanıt korunur. `inbox read` yalnız okundu durumudur.

Değişmeyen kanıt, içerik özetiyle tekrar kullanılır. Bu ilk yerel sürümde
en fazla 1.000 arama, 10.000 tanım olayı, 20.000 çalışma, çalışma başına
50.000 eşleşme, tek kanıt görüntüsünde 16 MiB ve toplam görüntülerde
64 MiB sınırı vardır. Aşım kısmi sonuç veya kayıt silme yerine açık hata
verir. Her okuma saklanan geçmişin bütünlüğünü denetler; bu sınırlar
performans garantisi değildir. İzleme 1–1.000 tur, 1–86.400 saniye aralık
ve 1–604.800 saniye süre kabul eder; görünüm sınırı 1–500'dür.

Şema 65 beş boş tablo ekler. Mevcut kurulumda `./xti migrate` açık ve
yedekli geçiştir; okuma otomatik geçiş yapmaz. Eski kod şema 65'i açamaz;
geri dönüş gerekiyorsa geçiş öncesi yedek ayrı, yeni bir veri dizinine
geri yüklenir. Yeni ücretli API veya paket bağımlılığı eklenmedi.

## Kaynaklar arası olay adaylarını incele

Önce mevcut internet toplayıcılarıyla kayıtları yenile:

```sh
./xti ransomware refresh --source threatcluster
./xti ransomware refresh --source ransomlook
./xti notices refresh
```

Sonra kayıtlı kanıtları birlikte incele:

```sh
./xti events candidates
./xti events candidates --domain example.com
./xti events candidates --offset 50 --limit 50
./xti --json events candidates --domain example.com --stale-hours 48
```

`example.com` yerine ilgili domaini yaz. Yenileme komutları internete çıkar;
`events candidates` tek yerel okuma anından rapor üretir. Kaynakları
kendiliğinden yenilemez; kayıt, karar veya alarm yazmaz.

| Görünen tür | Neden gösterilir? |
|---|---|
| Aynı olay olabilir | ThreatCluster ve RansomLook'ta aynı kuruluş adı, aynı grup ve en fazla 72 saat farkla kaynak keşif zamanı vardır. Adın yalnız harf büyüklüğü/boşluk/noktalama farkı da ayrı kural olarak desteklenir |
| Ortak kuruluş/domain bağlamı | HIBP domaini ile ThreatCluster website hostu tam aynıdır; veya mevcut ransomware karşılaştırması yalnız daha zayıf ad/grup/zaman bağlamı sağlar. Aynı olay olarak sınıflandırılmaz |

Her çiftin iki kaynak kaydı, nedenleri, çelişen/eksik alanları, tarihlerin
anlamları, kaynak bağlantıları ve çalışma kimlikleri ayrı gösterilir.
HIBP'nin tahmini olay günü ransomware keşif zamanına eşitlenmez. RansomLook
domain sağlamaz; ona domain ataması veya üç kaynağı geçişli birleştirme
yapılmaz. `--domain` tam host filtresidir; `www` veya alt domain genişletmez.
72 saat bir aday seçme kuralıdır; doğruluk yüzdesi değildir. Genel yaklaşık
isim eşleştirmesi, sözcük/sonek çıkarma veya yeni bağımlılık eklenmedi.

Önceden verilmiş ransomware kaynak karşılaştırması kararı kendi dondurulmuş
kanıtıyla ilişkilendirilir; güncel içerik farklıysa açıkça belirtilir.
Yeni genel adayın kimliği `ransomware source-review` kimliği değildir.
Mevcut `source-compare/source-review` davranışı korunur; bu yeni görünüm
genel adaylar için karar kaydetme işlemi eklemez.

Eksik, hatalı ve eski kaynaklar ayrı görünür. `--stale-hours` 1–8760,
`--limit` 1–500, `--offset` 0–1.000.000 olabilir; limit yalnız gösterimi
sınırlar, toplamı kesmez. Sayfalar ayrı okumalardır; arada kaynak yenilenirse
sonuç sırası değişebilir. Güncel kaynak kayıtları 50.000, karşılaştırma
referansları 100.000 veya adaylar 50.000 sınırını aşarsa kısmi rapor
yerine açık hata verilir. Yeni tablo, migration veya engine v1 işlemi yoktur.

## Bir domain için kaynakları birlikte çalıştır

Önceden kaydettiğin bir domainin marka aramasını, alt alan adı keşfini ve
isteğe bağlı IOC listesi yenilemesini aynı çalışmada yapabilirsin:

```sh
./xti collect example.com --plan
./xti collect example.com
./xti --json collect example.com
```

`--plan` yalnız seçilen işleri gösterir; internete çıkmaz ve veri yazmaz.
Normal çalıştırma sırasıyla crt.sh marka araması, urlscan marka araması ve
crt.sh alt alan adı keşfi yapar; sonunda kayıtlı kanıtların birleşik analizini
gösterir. Domain kayıtlı değilse önce `./xti assets add example.com` gerekir.

`--task` ile aşağıdaki işleri seçebilirsin. Tekrarlanan seçenekler birlikte
çalışır; **seçim varsayılan listenin yerine geçer**. Her iş en fazla bir kez,
tabloda belirtilen sabit sırayla çalışır:

| İş | İşlev |
|---|---|
| `scan-crtsh` | Sertifika kayıtlarında benzer domain araması |
| `scan-urlscan` | Mevcut web inceleme kayıtlarında benzer domain araması |
| `discover-crtsh` | Sertifika kayıtlarında alt alan adı keşfi |
| `discover-theharvester` | Kurulu araçla Common Crawl/Wayback pasif arşiv keşfi |
| `ioc-feodo` | Genel C2 IP listesini yenileme |
| `ioc-certpl` | Genel domain IOC listesini yenileme |
| `notices-hibp` | Kamu ihlal/olay metadata kataloğunu yenileme |

```sh
./xti collect example.com \
  --task scan-crtsh --task scan-urlscan --task discover-crtsh \
  --task ioc-feodo --task ioc-certpl
```

Her adım kendi gerçek çalışma kimliği, sonucu, yeni kayıtları ve hatalarıyla
gösterilir. IOC listesi toplamı domainin bulgu sayısı değildir. Kaynaklar aynı
adresi görebileceği için sayaçlar tek bir “benzersiz toplam” gibi toplanmaz.
Kaynak hatası diğer adımların çalışmasını engellemez; önceki geçerli veriler
korunur. Depolama/bütünlük hatası veya `Ctrl+C` yeni adımları durdurur;
tamamlanmış kayıtlar kendi geçmişlerinde kalır. Kısmi/başarısız toplama JSON'da
`ok:false`, terminal çıkışında `3` üretir; analiz üretilmesi toplama hatasını
başarıya çevirmez.

### Kayıtlı kullanıcı adı ve kuruluş izlemelerini ekle

Önce çalıştırmak istediğin kayıtların kimliklerini mevcut listelerden al:

```sh
./xti brand watch-list
./xti ransomware watch-list
./xti ransomware watch-list --source ransomlook
```

Aşağıdaki büyük harfli yer tutucuları bu kimliklerle değiştir:

```sh
./xti collect example.com \
  --username-watch SOSYAL_IZLEME_KIMLIGI \
  --ransomware-watch THREATCLUSTER_IZLEME_KIMLIGI \
  --ransomlook-watch RANSOMLOOK_IZLEME_KIMLIGI --plan
```

Planı çalıştırmak için aynı komuttan `--plan` seçeneğini çıkar. Üç izleme
seçeneği de isteğe bağlıdır ve farklı kimlikler için tekrarlanabilir.
**İzleme seçenekleri temel işlere eklenir**; `--task` verilmezse varsayılan
üç domain işi de çalışır. `--task` yalnız bu temel işlerin seçimini değiştirir.
Sherlock veya Maigret, seçtiğin sosyal kayıttaki kaynak ve platformlarla
çalışır; domain adından kullanıcı adı/kuruluş tahmin edilmez. Seçilmeyen
izlemeler çalıştırılmaz. Önizleme hangi kaynağın hangi adı arayacağını gösterir.

Her ransomware kaynağı yalnız bir kez yenilenir; seçilen izlemeler tam o
yenilemenin verisini kullanır. Kaynak yenilenemezse izlemeleri çalıştırılmaz;
eski snapshot yeni sonuç gibi sunulmaz. Diğer kaynaklar devam eder.
İlk ölçüm başlangıç kaydıdır; yeni olay veya doğrulanmış ihlal sayılmaz.
Sonraki çalışmalarda yeni/değişen/raporlanmayan öğeler, profil adresleri,
iddia adları ve çalışma kimlikleri gösterilir. Sosyal ve ransomware sonuçları
domain analizinin yanında ayrı sunulur; domainle sahiplik bağı kurulmaz.

Bir çalışmada toplam en fazla 50 izleme kimliği açıkça seçilebilir;
taşmada işlem başlamadan hata verilir. `--watch-item-limit 1–500` yalnız
her izleme sonucunda gösterilen öğe sayısını belirler (varsayılan 100);
tam sonuç kalıcı geçmişte korunur. Çıktı gösterilmeyen öğe sayısını ve ayrıntı komutunu
gösterir. Yinelenen, bulunamayan veya geri çekilmiş izleme ilk ağ isteğinden
önce reddedilir. Araç/sunucu erişimi ise gerçek çalıştırmada belli olur.

Komut hedef siteye DNS/TLS/HTTPS/port kontrolü göndermez. ATT&CK ve dış
bildirim bu toplama akışında yer almaz. Toplama oturumunu `collections list`
ve `collections show` ile açabilir, eksik işleri açık `collections resume`
komutuyla yeniden deneyebilirsin. Ani kesintiden kalan açık oturumlar için
`collections recover` vardır; kendiliğinden devam başlatılmaz. Kaynaklara
ait `jobs`, `surface runs` ve `ioc status` geçmişleri de korunur. Kayıtlı
profilin zamanlama dosyaları ayrı `schedule generate` komutuyla hazırlanır;
`collect` hizmet veya takvim kurmaz. Normal `analyze` komutu ağsız kalır.
İş mantığı terminalden bağımsız uygulama servisindedir. Kayıtlı toplama
profili, [platform iş sözleşmesi](docs/PLATFORM_ENGINE.md) üzerinden
kuyruğa alınabilir; ayrı worker en fazla bir işi çalıştırır. .NET bağlantısını
kullanan ekip geliştirir. Kişisel `engine` v1 okuma sözleşmesi korunur.

## Bulguları vaka altında yönet

Bir veya daha fazla yerel kanıtı tek incelemede toplayabilir; not, görev, öncelik,
durum, sonuç ve tam zaman çizelgesiyle takip edebilirsin:

```sh
./xti cases create "Olası marka taklidi" \
  --summary "Domain ve sosyal profil birlikte incelenecek" \
  --priority high \
  --reason "İki bağımsız aday aynı markayla ilişkili"
./xti cases list
./xti cases show VAKA_KIMLIGI
./xti cases note-add VAKA_KIMLIGI "İlk kaynaklar gözden geçirildi" --kind observation
./xti cases task-add VAKA_KIMLIGI "Marka sahibinden teyit al" \
  --due-at 2026-11-02T12:00:00+03:00 \
  --reason "Kapanıştan önce insan doğrulaması gerekli"
./xti cases task-update VAKA_KIMLIGI GOREV_KIMLIGI \
  --status done --reason "Teyit alındı"
./xti cases status VAKA_KIMLIGI investigating --reason "Kanıt incelemesi başladı"
./xti cases report VAKA_KIMLIGI
```

Kanıt eklerken, ilgili komutun gösterdiği kaynak kayıt kimliğini kullan:

```sh
./xti cases evidence-add VAKA_KIMLIGI --type finding \
  --evidence-id BULGU_KIMLIGI --reason "Domain adayı vakayla ilgili"
./xti cases evidence-add VAKA_KIMLIGI --type social_profile \
  --evidence-id PROFIL_INCELEME_ADAYI_KIMLIGI --reason "İnsan kararı bulunan profil"
./xti cases evidence-add VAKA_KIMLIGI --type ransomware_threatcluster \
  --evidence-id KAYNAK_KAYDI_KIMLIGI --reason "ThreatCluster iddiası incelenecek"
./xti cases evidence-add VAKA_KIMLIGI --type ransomware_ransomlook \
  --evidence-id KAYNAK_KAYDI_KIMLIGI --reason "RansomLook iddiası incelenecek"
./xti cases evidence-add VAKA_KIMLIGI --type supplier \
  --evidence-id TEDARIKCI_KIMLIGI --reason "Tedarikçi kartı vakaya eklendi"
```

Sosyal profil kanıtı için önce `brand watch-review` ile insan kararı bulunmalıdır.
Her bağlantı, kaynağın o andaki bütünlüğü denetlenmiş görünümünü vakada dondurur;
kaynak kayıt silinmez veya değiştirilmez. Aynı kanıt yeniden seçildiğinde
çoğalmaz; kaynak değişmişse anlık görüntü yenilenir. Bağı kaldırmak da geçmişi
silmez. Vaka `open`, `investigating`, `monitoring`, `resolved` ve `closed`
durumlarında ilerler. `resolved` ve `closed` için `--resolution` zorunludur;
açık görev varken vaka kapatılamaz. Kapalı vakaya kanıt/görev eklemek için önce
gerekçeyle yeniden açmak gerekir.

Liste, ayrıntı ve rapor internete çıkmaz. Vaka birden çok kaydı aynı çalışma
altında toplar fakat onları tek tehdit kaydı olarak birleştirmez; kaynak iddiasını
doğrulanmış saldırı veya ihlal saymaz. Atama, kullanıcı/rol, web paneli ve ekip
SLA'ları kişisel terminal sürümünün kapsamı dışındadır.

## Tedarikçilerini kaydet

Kullandığın dış hizmetleri kendi beyanınla yerel envantere ekleyebilirsin:

```sh
./xti suppliers add "Örnek Bulut" --domain vendor.example --relationship cloud --criticality high --reason "Ana yedekleme hizmetini sağlıyor"
./xti suppliers list
./xti suppliers show TEDARIKCI_KIMLIGI
./xti suppliers update TEDARIKCI_KIMLIGI --criticality critical --reason "Müşteri verisinin ana saklama hizmeti"
./xti suppliers revoke TEDARIKCI_KIMLIGI --reason "Hizmet sözleşmesi sona erdi"
./xti suppliers list --all
```

İlişki türleri `software`, `cloud`, `payment`, `communications`,
`professional_service` ve `other`; iş önemi düzeyleri `low`, `medium`, `high`
ve `critical` olabilir. Aynı isimli iki kuruluş farklı ana domainlerle ayrı
kayıtlar olarak tutulur. Ana domain kuruluş kimliğinin parçasıdır ve güncelleme
komutuyla değiştirilemez. Pasife alma geçmişi silmez; aynı domain yeniden
eklenirse eski kimlik ve olay zinciri korunarak etkinleşir.

Kayıt, kullanıcının tedarikçi ilişkisi beyanıdır; kuruluşun güvenli veya riskli
olduğunu kanıtlamaz. Risk puanı ve tehdit olayı üretmez.

### Kayıtlı CNAME kanıtlarından tedarikçi adayı çıkar

Önce sana ait tam adresi dış yüzey kapsamına alıp CNAME kontrolünü açıkça
çalıştırmış olmalısın. Ardından mevcut kayıtları internete çıkmadan incele:

```sh
./xti suppliers candidate-refresh
./xti suppliers candidate-list
./xti suppliers candidate-show ADAY_KIMLIGI
```

Son CNAME hedefi farklı bir kayıt köküne gidiyorsa sistem yalnız “olası dış
hizmet domaini” önerir. Kuruluş adı çıkarmaz; CDN, ortak barındırma veya başka
bir teknik aracı tedarikçi saymaz. Gerçek ilişkiyi biliyorsan önce tedarikçiyi
envantere ekle, sonra açık karar ver:

```sh
./xti suppliers candidate-review ADAY_KIMLIGI --decision accepted --supplier TEDARIKCI_KIMLIGI --reason "Bu hizmet için sözleşmemiz bulunuyor"
./xti suppliers candidate-review ADAY_KIMLIGI --decision uncertain --reason "Ortak altyapı olabilir; yeniden incelenecek"
./xti suppliers candidate-review ADAY_KIMLIGI --decision rejected --reason "Bu domain yalnız CDN altyapısıdır"
./xti suppliers candidate-review ADAY_KIMLIGI --decision pending --reason "Kuruluş bağlantısı yeniden incelemeye alındı"
```

Kararlar geri alınabilir ve eski kararlar silinmez. Sonraki CNAME kanıtında
artık görünmeyen adaylar tarihsel olarak korunur; `candidate-list
--include-historical --status all` ile görüntülenebilir. Aday yenileme ağ
isteği yapmaz.

### Tedarikçiyle eşleşen kaynak iddialarını incele

ThreatCluster ve RansomLook kaynaklarını daha önce açıkça yenilediysen, etkin
tedarikçilerinle eşleşen son yerel iddiaları internete çıkmadan görebilirsin:

```sh
./xti suppliers event-list
./xti suppliers event-list --supplier TEDARIKCI_KIMLIGI
./xti suppliers event-list --source threatcluster
./xti suppliers event-show OLAY_KIMLIGI
./xti --json suppliers event-list
```

Eşleşme yalnız tam kuruluş adı veya ThreatCluster kaydında bulunan ilk-taraf web
domaini üzerinden yapılır. Yaklaşık ad benzerliği kullanılmaz. Aynı isimli iki
tedarikçi varsa belirsizlik açıkça gösterilir; iki kaynağın kayıtları
birleştirilmez. Kaynak hiç yenilenmediyse veya son yenileme başarısızsa bu durum
“eşleşme yok” sonucundan ayrı gösterilir.

Komutlar yalnız yerel snapshot'ları okur; internete çıkmaz ve veritabanına
yazmaz. Kaynak kaydı doğrulanmış ihlal, tedarikçi etkisi, alarm veya risk puanı
değildir.

### Açıklanabilir tedarikçi inceleme kartı

Envanter kaydını, insan onaylı güncel CNAME bağlarını, iki ransomware
kaynağının durumunu ve eşleşen iddiaları tek kartta birleştirebilirsin:

```sh
./xti suppliers risk-list
./xti suppliers risk-show TEDARIKCI_KIMLIGI
./xti --json suppliers risk-list
```

Kartlar `öncelikli insan incelemesi`, `insan incelemesi`, `önce kuruluş
kimliğini ayır`, `kaynak verisi yetersiz` veya `son yerel snapshot'ta eşleşme
yok` durumlarından birini gösterir. Her durumun nedenleri, eksik/eski kaynak
verisi, en yeni kanıt zamanı ve önerilen sonraki adımlar ayrıca yazılır.

Bu bir sayısal risk skoru değildir. Kaynak iddiasını doğrulanmış ihlal veya
kullanıcı etkisi saymaz; otomatik alarm, engelleme ya da dış aksiyon üretmez.
Terminal ve JSON çıktısı ağsız ve salt okunurdur. Böylece tedarikçi çekirdeği;
envanter → teknik bağımlılık → kaynak iddiası → açıklanabilir insan incelemesi
zincirini tamamlar.

## Sosyal kullanıcı adını araştır

Normal `./setup`, Maigret ve Sherlock'u resmî depolarındaki incelenmiş tam
commit'lerden proje içindeki ayrı ortama kurar ve her sonraki çalışmada
kurulumu doğrular. Araçların geçişli Python bağımlılıkları da incelenmiş tam
sürümlere bağlıdır; kurulum resmî GitHub ve PyPI kaynaklarını kullanır. Yalnız
bu araçları denetlemek veya onarmak için:

```sh
./scripts/setup-brand --check
./scripts/setup-brand --force
./scripts/setup-brand --recover
```

Kurulum eski ortamı korur; ani kesinti sonrası `--recover` kullanılır.
Çalışan XTI komutlarıyla ortam değişikliği ortak kilitle ayrılır. Önceki
ve başarısız ortamlar otomatik silinmez. Ayrıntılar
[marka araçları kurulum rehberinde](docs/BRAND_INSTALLATION.md).

Ardından bir marka kullanıcı adını seçili herkese açık platformlarda araştır:

```sh
./xti brand username-preview markam
./xti brand profile-list
./xti brand username-preview markam --profile extended
./xti brand username-preview markam --site GitHub --site Instagram
./xti --json brand username-preview markam --site GitHub
./xti brand username-preview markam --source sherlock
./xti brand username-preview markam --source sherlock --profile extended
./xti brand username-preview markam --source sherlock --site Carrd --site Rumble
./xti --json brand username-preview markam --source sherlock --site Carrd
```

Komut yalnız açıkça verilen kullanıcı adını ve seçilen platformları kontrol
eder. Seçenek verilmezse `safe` profili kullanılır: Maigret'te 6, Sherlock'ta
5 platform. `--profile extended`, URL/host tanımları tek tek incelenmiş sabit
geniş listeyi kullanır: Maigret'te 30, Sherlock'ta 26 platform. `--site`
tekrarlanarak özel liste seçilebilir. `--profile` ile `--site` birlikte
kullanılamaz; iki kaynağın platform listeleri de birbirine karıştırılamaz.

`extended`, upstream aracın bütün kataloğu değildir. HTTP kullanan, yetişkin
içerikli, yalnız arama sonucu döndüren veya incelenmemiş başka hedefe sıçrayan
tanımlar kapsam dışıdır. Daha çok platform daha uzun çalışma, oran sınırlaması
ve daha fazla “raporlanmadı” sonucu doğurabilir; hiçbir kota aşma yöntemi
kullanılmaz.

Sonuçlar XTI veritabanına yazılmaz; ham HTTP yanıtı, çıkarılmış profil bilgisi
veya üçüncü taraf kimlikleri tutulmaz. “Bulundu, doğrulanmadı” yalnız aynı
kullanıcı adına açık bir profil işareti görüldüğünü söyler; hesabın markaya ait
veya taklit olduğunu kanıtlamaz. Raporlanmayan platform da tek başına “hesap
yok” anlamına gelmez.

Her adaptör yalnız incelenen upstream site veritabanı özetini kabul eder ve her
çalışmada bunun geçici bir kopyasını tam seçilen platformlarla sınırlar.
Sherlock'un kendi komut satırı kullanılmaz; seçilen sitelere ek istek yapan
sürüm kontrolünü devre dışı bırakmak için sabit kütüphane işlevi yalıtılmış bir
işçide çağrılır ve XTI yalnız dört alanlı kendi NDJSON raporunu üretir. Tor,
I2P, proxy, Cloudflare aşma, otomatik güncelleme, yapay zekâ, kullanıcı adı
türetme, özyinelemeli profil çıkarımı ve domain arama kapalıdır. Her platform
için 5–30 saniye sınırı vardır; Maigret'te en fazla 30, Sherlock'ta en fazla 26
platform seçilebilir. Bütün süreç Maigret'te en fazla 300, Sherlock'ta en fazla
100 saniyede güvenli biçimde durur.

### Kullanıcı adını kalıcı izle

İzleme tanımını bir kez ekle, sonra istediğin zaman canlı kontrolü çalıştır:

```sh
./xti brand watch-add "Markam sosyal hesapları" markam --site GitHub --site Instagram
./xti brand watch-add "Markam geniş takip" markam --profile extended
./xti brand watch-add "Markam Sherlock" markam --source sherlock --site Carrd --site Rumble
./xti brand watch-list
./xti brand watch-show IZLEME_KIMLIGI
./xti brand watch-run IZLEME_KIMLIGI
./xti brand watch-run-all --watch-limit 10
./xti brand watch-monitor IZLEME_KIMLIGI --cycles 3 --interval 3600 --duration 86400
./xti brand watch-run-show CALISMA_KIMLIGI
./xti brand watch-review IZLEME_KIMLIGI GitHub --decision known_official --reason "Resmî siteden bağlantı veriliyor"
./xti brand watch-review IZLEME_KIMLIGI Instagram --decision possible_impersonation --reason "Marka bu hesabı tanımıyor"
./xti brand watch-review-show INCELEME_ADAYI_KIMLIGI
./xti inbox list --status unread
./xti inbox show BILDIRIM_KIMLIGI
./xti inbox read BILDIRIM_KIMLIGI
./xti brand watch-revoke IZLEME_KIMLIGI --reason "Artık izlenmeyecek"
```

İlk başarılı çalışma sessiz başlangıç çizgisidir; bulunan profilleri yeni alarm
saymaz. Sonraki çalışmalarda yeni bulunan, profil adresi değişen, artık
raporlanmayan, bulunup değişmeyen ve raporlanmayıp değişmeyen platformlar ayrı
gösterilir. “Artık raporlanmadı” hesabın silindiğini; “bulundu” hesabın markaya
ait veya taklit olduğunu kanıtlamaz. Kaynak hatası ayrı başarısız çalışma olarak
saklanır ve önceki başarılı ölçümle “hesap yok” farkı üretmez. Liste, ayrıntı ve
eski çalışma gösterimi ağsızdır; `watch-run`, `watch-run-all` ve
`watch-monitor` internete çıkar.

Her kalıcı izleme `maigret` veya `sherlock` kaynağına oluşturulurken bağlanır.
Profil adı yerine o anda çözülen tam platform listesi saklanır; ileride profil
tanımı değişse bile mevcut izlemenin kapsamı sessizce değişmez. Kaynak sonradan
değiştirilemez; aynı kullanıcı adını iki kaynakla izlemek için
iki farklı yerel izleme adı kullanılır. Böylece her kaynağın ilk başarılı
çalışması, fark geçmişi, kaynak hatası ve insan kararı ayrı kalır. Terminal ve
JSON çıktıları seçilen kaynağı açıkça gösterir. Normal `./setup` iki aracı da
kurup doğrular. `--core-only` kullanıldıysa önce `./scripts/setup-brand`
çalıştırılmalıdır.

`watch-run-all`, bütün etkin izlemeleri görünen adlarına göre sabit sırada bir
kez çalıştırır. Varsayılan sınır 10, açıkça seçilebilen üst sınır 100
izlemedir. Etkin izlemelerin tamamı `--watch-limit` içine sığmıyorsa komut
hiçbir ağ isteği veya çalışma kaydı başlatmadan durur. Her izleme ayrı atomik
kayıttır: bir kaynak hatası önceki başarılı kanıtı geri almaz ve sonraki
izlemeyi engellemez; veritabanı bütünlük hatası ise yeni izleme başlatmayı
durdurur. Bütün toplu çalışma boyunca ortak yerel çalışma kilidi tutulur.
Komut bir kez çalışır; zamanlayıcı, daemon veya açılış görevi kurmaz.

`watch-monitor`, tek bir etkin izlemeyi yalnız terminal açıkken tekrarlar.
Varsayılan üç tur, turlar arasında 3600 saniye ve yeni tur başlatmak için
86400 saniyelik toplam bütçe kullanır. Tur sayısı 1–1000, aralık 300–86400 ve
süre bütçesi 1–604800 saniye arasında sınırlandırılır. Her tamamlanan tur normal
bir `watch-run` kaydıdır. Kaynak hatası ayrı başarısız tur olarak korunur ve
bütçe kaldığında sonraki tur denenir. Süre dolunca yeni tur başlamaz; başlamış
Maigret çalışması kendi süre sınırıyla tamamlanabilir. `Ctrl+C`, daha önce
tamamlanan turları silmeden komutu durdurur. Bütün monitor boyunca ortak yerel
çalışma kilidi tutulur; terminal kapalıyken çalışma veya otomatik devam yoktur.

`watch-review`, güncel izleme tanımının son başarılı çalışmasında gerçekten
bulunan platform için zorunlu gerekçeli `known_official` (bilinen resmî/meşru),
`possible_impersonation` (olası taklit) veya `uncertain` (belirsiz) kullanıcı
kararı kaydeder. Karar yalnız o tam profil adresi ve gözlem durumuna bağlıdır;
profil adresi değişirse yeni sonuç kararsız başlar. Aynı karar ve gerekçe tekrar
satır üretmez; karar değişikliği önceki kaydı silmeden geçmişe eklenir.
`watch-run` ve `watch-run-show` varsa güncel kullanıcı kararını profilin yanında
gösterir. `possible_impersonation` kararı aynı işlem içinde ortak yerel kutuya
bir bildirim ekler. Aynı tam profil ikinci kez bildirilmez; profil adresi
değişirse yeni kanıt ayrı bildirim olabilir. `known_official` ve `uncertain`
bildirim üretmez. Karar sonradan değişse bile eski bildirimin onu oluşturan karar
ve gerekçesi yeniden yazılmaz; ayrıntıda ayrıca güncel karar gösterilir.

Bildirim yalnız kullanıcının olası taklit değerlendirmesini kaydeder; teknik
sahiplik doğrulaması değildir. Listelemek bildirimi okundu yapmaz. Okundu durumu
karardan bağımsızdır. E-posta, SMS, otomatik webhook teslimi veya dış aksiyon
başlatılmaz; mevcut manuel webhook komutu ancak kullanıcı bu bildirimi ayrıca
seçerse kullanılabilir.

Kalıcı fark sözleşmesi [0109 numaralı kararda](docs/decisions/0109-durable-maigret-username-watches.md),
tam profile bağlı insan kararı
[0110 numaralı kararda](docs/decisions/0110-exact-social-profile-human-decisions.md)
açıklanır. Yerel kutu bağlantısı
[0111 numaralı kararda](docs/decisions/0111-reviewed-social-profile-inbox.md)
kayıtlıdır. Sınırlı toplu çalışma
[0112 numaralı kararda](docs/decisions/0112-bounded-social-watch-batch.md)
açıklanır. Sınırlı ön plan tekrarı
[0113 numaralı kararda](docs/decisions/0113-bounded-foreground-social-watch.md)
kayıtlıdır.

## Marka OSINT araçlarını değerlendir

İlk sosyal kullanıcı adı kaynağı için alınan sürümlü kararı görmek üzere:

```sh
./xti brand source-evaluation
./xti --json brand source-evaluation
./xti brand source-coverage
./xti --json brand source-coverage
```

Komut Maigret, Sherlock, theHarvester, Web-Check, Holehe ve olası telefon aracı Ignorant seçeneklerini aynı zorunlu kapılarla karşılaştırır. Çalışma sırasında internete bağlanmaz, araç kurmaz, kullanıcı adı aramaz ve veri klasörü oluşturmaz. Bu kapının seçtiği Maigret adaptörü normal doğrulanmış kurulumla çalışmaktadır. Maigret kaynak kodu XTI içine kopyalanmamıştır; paket resmî repodaki tam commit'ten kurulur ve yalnız sınırlı özellik kümesi çağrılır.

`source-coverage`, sabit Maigret 0.6.6 ve Sherlock 0.16.2 kataloglarını
incelenen tam commit ve SHA-256 özetleriyle karşılaştıran ikinci kapıdır. Yalnız
etkin, HTTPS kullanan doğrudan kullanıcı adı tanımları alınır; aynı
normalleştirilmiş ad veya aynı Public Suffix List kayıt kökü ortak sayılır.
Sherlock'un 455 uygun tanımından 352'si ortak, 103'ü eşleşmeyen tanımdır; bu
tanımlar 102 host ve 101 ayrı kayıt kökü oluşturur. İlk değerlendirmedeki 10 platformda
ise 9 platform ortaktır, Facebook yalnız Maigret'tedir ve Sherlock yeni platform
eklemez.

Sherlock bütün kataloğuyla çalıştırılmaz. Güncel kurulumda `safe` profili
5, `extended` profili 26 incelenmiş platform içerir; Maigret'te bu sayılar
6 ve 30'dur. Tam güncel seçim `brand profile-list` ile görülür.
`brand source-coverage` hâlâ ağsız ölçüm komutudur;
`brand username-preview ... --source sherlock` ise yalnız kullanıcı açıkça
çalıştırdığında seçilen platformlara bağlanan, yazmasız canlı önizlemedir.
Kurulum tam commit'e, site kataloğu tam SHA-256 özetine sabittir. Geniş katalog,
Sherlock CLI, canlı exclusion/katalog güncellemesi ve profil ayrıntısı çıkarımı
kullanılmaz.

theHarvester'ın yalnız Common Crawl ve Wayback Archive P0 hostname profili artık
mevcut `surface` aday akışında çalışır. Web-Check'in tamamı mevcut
DNS/TLS/web kanıtıyla çakıştığı için eklenmez. Holehe ve telefon hesabı yoklama
araçları hesap-kurtarma mekanizmalarına dayandığından mevcut pasif OSINT
kapsamına alınmaz. Bir kullanıcı adı eşleşmesi, hesabın aynı kişi veya markaya
ait olduğunu ya da taklit olduğunu tek başına kanıtlamaz.

Seçim gerekçeleri [0107 numaralı kararda](docs/decisions/0107-free-brand-osint-tool-gate.md), çalışan Maigret adaptörünün teknik ve güvenlik sınırları [0108 numaralı kararda](docs/decisions/0108-bounded-maigret-username-preview.md), ikinci kaynak kapsam ölçümü [0114 numaralı kararda](docs/decisions/0114-second-social-source-coverage-gate.md), sınırlı Sherlock çalıştırma kararı [0115 numaralı kararda](docs/decisions/0115-bounded-sherlock-username-preview.md), theHarvester arşiv sınırı ise [0117 numaralı kararda](docs/decisions/0117-bounded-theharvester-archive-discovery.md) kayıtlıdır.

## Tek görünümde incele

Kayıtlı marka, alt alan adı, DNS/TLS/HTTPS, e-posta, sınırlı port ve IOC kanıtını tek ekranda görmek için:

```sh
./xti analyze markam.com
./xti analyze markam.com --refresh-ioc feodo
./xti analyze markam.com --refresh-ioc certpl
./xti --json analyze markam.com
```

Varsayılan `analyze` yeni internet isteği göndermez ve kayıt değiştirmez. Daha önce toplanmış kanıtı birleştirir; güncel, eski, eksik ve başarısız bölümleri ayırır. IOC kataloğu güncelse kök domaini, bu kök için kayıtlı bütün marka/domain adaylarını ve son kayıtlı IP'leri yalnız tam değer eşleşmesiyle karşılaştırır. Ekranda gösterilecek bulgu sınırı IOC kapsamını daraltmaz. Eşleşme tek başına zararlılık veya etkilenme hükmü değildir. Çıktının sonunda gerekli sonraki komutlar gösterilir.

`--refresh-ioc feodo` açıkça verilirse ücretsiz Feodo Tracker C2 IP listesi; `--refresh-ioc certpl` verilirse CERT Polska'nın son bir ayda eklenmiş ve hâlâ etkin domain listesi önce güvenli tam snapshot olarak yenilenir ve analiz yeniden üretilir. Bu seçenekler internete çıkar ve IOC çalışma geçmişini kaydeder. Kaynak hatası önceki geçerli kataloğu silmez; çıktı hatayı “eşleşme bulunmadı” sonucundan ayrı gösterir ve başarısızlık koduyla döner. Bilinmeyen domain, geçersiz sınır veya bozuk yerel kanıt ağ isteğinden önce reddedilir.

CERT Polska kaynağı anahtarsız ve ücretsizdir; ancak Polonya kullanıcılarını korumaya odaklanır ve bu entegrasyon yalnız son-ay dilimini alır. Küresel veya tarihsel tüm phishing domainlerini kapsamaz. Bir domainin listeden çıkması da güvenli olduğu anlamına gelmez.

## Ransomware iddialarını araştır

Son dönem ransomware/leak-site duyurularını görmek veya bir kuruluş/domain ifadesini aramak için:

```sh
./xti ransomware recent
./xti ransomware recent markam.com
./xti ransomware recent "Marka Adı" --limit 50
./xti ransomware recent --status delisted
./xti ransomware recent --source ransomlook --limit 20
./xti ransomware recent markam.com --source ransomlook
./xti ransomware source-evaluation
./xti --json ransomware recent markam.com
./xti ransomware refresh
./xti ransomware status
./xti ransomware refresh --source ransomlook
./xti ransomware status --source ransomlook
./xti ransomware source-compare
./xti ransomware source-compare --limit 200
./xti ransomware source-review KARSILASTIRMA_KIMLIGI --decision uncertain --reason "Ek kanıt bekleniyor"
./xti ransomware source-review-show KARSILASTIRMA_KIMLIGI
./xti ransomware watch-add "Marka adı" "Marka AŞ" --kind organization --source ransomlook
./xti ransomware watch-list --source ransomlook
./xti ransomware watch-run IZLEME_KIMLIGI --source ransomlook
./xti ransomware watch-show IZLEME_KIMLIGI --source ransomlook
./xti ransomware watch-run-show CALISMA_KIMLIGI --source ransomlook
./xti ransomware watch-revoke IZLEME_KIMLIGI --reason "Artık izlenmeyecek" --source ransomlook
./xti ransomware watch-add "Marka adı" "Marka AŞ" --kind organization
./xti ransomware watch-add "Marka domain" markam.com --kind domain
./xti ransomware watch-list
./xti ransomware watch-refresh-all
./xti ransomware watch-monitor --cycles 3 --interval 3600 --duration 86400
./xti ransomware watch-monitor-list
./xti ransomware watch-monitor-show OTURUM_KIMLIGI
./xti ransomware watch-timeline IZLEME_KIMLIGI
./xti ransomware watch-identity-candidates IZLEME_KIMLIGI
./xti ransomware watch-identity-review IZLEME_KIMLIGI ADAY_KIMLIGI --decision uncertain --reason "Ek kanıt bekleniyor"
./xti ransomware watch-identity-review-show ADAY_KIMLIGI
./xti ransomware watch-run IZLEME_KIMLIGI
./xti ransomware watch-show IZLEME_KIMLIGI
./xti ransomware watch-run-show CALISMA_KIMLIGI
```

Varsayılan `recent`, ThreatCluster'ın anahtarsız açık JSON akışını bir kez HTTPS üzerinden alır ve aramayı cihazında yapar. Kaynaktaki kuruluş adı, grup, ilk gözlem zamanı, ülke, sektör, ilan durumu ve varsa web bilgisi gösterilir. Çıktıdaki her kayıt yalnız ransomware/şantaj grubunun yayımladığı **doğrulanmamış iddiadır**; gerçekleşmiş ihlal, veri sızıntısı veya saldırı doğrulaması değildir. Kaynakta kaldırılmış görünmesi ödeme yapıldığı, olayın çözüldüğü veya iddianın doğru/yanlış olduğu anlamına gelmez.

`--source ransomlook`, bağımsız RansomLook kaynağının yalnız son yedi günlük açık gönderi listesini yazmasız önizler. Bu kaynak sadece grup adı, gönderi/kuruluş başlığı ve keşif zamanı verdiği için XTI ülke, sektör, domain veya ilan durumu uydurmaz; `--status` yalnız `all` olabilir. Yanıt en fazla 2 MiB/10.000 kayıt, 30 saniye ve sabit HTTPS uç noktasıyla sınırlıdır. Yönlendirme, sıkıştırılmış yanıt, beklenmeyen alan veya zaman kabul edilmez. Komut veritabanı oluşturmaz, RansomLook kayıtlarını ThreatCluster geçmişiyle birleştirmez ve Tor/leak-site adresine bağlanmaz.

`ransomware refresh --source ransomlook`, aynı doğrulanmış yedi günlük tam snapshot'ı yalnız açık kullanıcı isteğiyle ayrı RansomLook geçmişine kaydeder. İlk başarılı kayıt başlangıç çizgisidir ve alarm değildir; sonraki çalışmalarda yeni, aynı ve pencereden çıkan kayıtlar ayrılır. Pencereden çıkış silinme, çözüm veya iddianın yanlışlığı anlamına gelmez. Kaynak hatası ayrı çalışma olarak saklanır ve son başarılı snapshot korunur. `ransomware status --source ransomlook` bu geçmişi internete çıkmadan gösterir. Bu tabloların ThreatCluster izleme, bildirim ve kimlik tablolarıyla bağlantısı yoktur.

`watch-add ... --source ransomlook`, yalnız kaynağın gönderi/kuruluş başlığı alanı için kalıcı izleme tanımlar. Tam eşleşme varsayılandır; en az beş karakterli `--match contains` seçilebilir. RansomLook domain sağlamadığı için `--kind domain` ağ veya kayıt yazımı başlamadan reddedilir. `watch-run --source ransomlook`, son başarılı yerel snapshot üzerinde ağsız çalışır. İlk çalışma sessiz başlangıçtır; sonraki yeni eşleşmeler terminal/JSON sonucunda insan inceleme adayı olarak ayrılır. Yalnız pencereden çıkan kayıt dikkat adayı veya çözüm sayılmaz. Tanım değişirse yeni sessiz başlangıç yapılır; geri çekme geçmişi silmez. Sessiz başlangıçtan sonraki yeni/değişen eşleşmeler çalışma başına tek yerel `inbox` bildirimi üretir; aynı sonucun tekrarı veya yalnız pencereden çıkış üretmez. Bildirim tam izleme ve kaynak çalışma kimliğine bağlıdır. Bağımsız RansomLook monitor komutu yoktur. `collect --ransomlook-watch ID` seçilen izlemeleri tek kaynak yenilemesinden sonra çalıştırır; ThreatCluster kanıtlarıyla birleştirmez.

`ransomware source-compare`, iki kaynağın ayrı tutulan son başarılı yerel snapshot'larını internete çıkmadan ve kayıt yazmadan karşılaştırır. Bir sonuç için kuruluş adının normalleştirilmiş biçimi iki kaynakta tam aynı olmalı; buna ek olarak grup adı veya kaynak keşif zamanı da aynı olmalıdır. Terminal ve JSON, iki özgün kayıt kimliğini, aynı alanları ve farklı ortak alanları birlikte gösterir. Yaklaşık isim benzerliği, domain, ülke veya kaynakta bulunmayan alanlar kullanılmaz. Sonuçlar kayıtları birleştirmez, alarm üretmez ve aynı olay ya da gerçekleşmiş ihlal kararı değildir.

`ransomware source-review`, `source-compare` çıktısındaki karşılaştırma kimliği için `possible_same` (aynı olay olabilir), `different` (farklı olay) veya `uncertain` (belirsiz) insan kararı kaydeder. Her karar 2–500 karakterlik gerekçe ister. Aynı karar ve gerekçe tekrar verilirse yeni olay oluşmaz; karar veya gerekçe değişirse önceki olay silinmeden yenisi eklenir. `source-review-show` ilk kararda dondurulan iki özgün kaynak kaydını ve bütün karar zincirini ağsız gösterir. Yeni kaynak snapshot'ları eski karar kanıtını değiştirmez. Karar iki kaynak kaydını birleştirmez, alarm/inbox kaydı oluşturmaz ve gerçekleşmiş ihlali doğrulamaz.

`source-evaluation`, RansomLook, arşivlenmiş RansomWatch ve Darkfield seçeneklerinin bakım, ücretsiz erişim, dar veri biçimi, yeniden kullanım koşulu, bağımsız toplama ve güvenli asgari içerik kapılarını çevrimdışı gösterir. Bu rapor neden RansomLook'un seçildiğini ve diğer seçeneklerin neden ertelendiğini ya da elendiğini açıklar; kendisi internet isteği veya veritabanı yazımı yapmaz.

XTI Tor ağına ya da kaynak leak-site adresine bağlanmaz. Ham gönderi metni, ekran görüntüsü, kişisel veri veya `.onion` adresi alınan sonuca eklenmez; terminal/JSON çıktısında ve yerel geçmişte tutulmaz. `recent` yazmasız canlı önizlemedir. `refresh` ise açık seçimle aynı doğrulanmış snapshot'ı yerel veritabanına kaydeder ve önceki başarılı snapshot'a göre `yeni`, `değişen`, `aynı` ve `30 günlük kaynak penceresinden çıkan` kayıtları ayırır. Pencereden çıkmak iddianın geri çekildiğini veya olayın çözüldüğünü kanıtlamaz.

İlk başarılı `refresh` yalnız başlangıç çizgisidir; içindeki bütün kayıtlar teknik olarak `added` olsa da yeni alarm sayılmaz. Kaynak hatası ayrı başarısız çalışma olarak saklanır ve önceki başarılı snapshot silinmez. `status` internete bağlanmadan son denemeyi, son başarılı snapshot'ı ve sınırlı çalışma geçmişini gösterir.

`watch-add`, kuruluş adı veya domain için kalıcı bir yerel izleme tanımı oluşturur. Kuruluş izlemesi yalnız kaynaktaki kuruluş alanına bakar; varsayılan tam eşleşmedir, istenirse en az beş karakterli `--match contains` seçilebilir. Domain izlemesi yalnız kaynaktaki web alanını kök/alt alan adı ilişkisiyle eşleştirir; grup, sektör ve serbest metin alarma çevrilmez. `watch-run` internete çıkmadan son başarılı yerel snapshot'ı kullanır. Her yeni veya değişmiş tanımın ilk çalışması sessiz başlangıçtır; yalnız sonraki yeni/değişen eşleşme `./xti inbox` içine girer. Yalnız kaynak penceresinden çıkış bildirim üretmez ve kapatma/çözüm sayılmaz. Aramada sonuç çıkmaması da kuruluş hakkında hiç iddia olmadığı veya güvenli olduğu anlamına gelmez.

`watch-refresh-all`, önce açık kaynağı bir kez yeniler ve yalnız tam yenileme başarılıysa bütün etkin izlemeleri adlarına göre sabit sırayla çalıştırır. Kaynak hatasında önceki başarılı snapshot korunur fakat eski veri üzerinde izleme yapılmaz. Etkin izlemelerin tamamı `--watch-limit` sınırına sığmıyorsa komut internete çıkmadan durur; sessiz kırpma yapmaz. Her izleme ayrı atomik kayıttır: sonraki bir izleme hatası tamamlanmış olanları silmez, ancak toplu akış güvenli biçimde durur. Bu tek seferlik ön plan komutudur; zamanlayıcı veya arka plan servisi kurmaz.

`watch-monitor`, aynı güvenli akışı terminal açık kaldığı sürece tekrarlar. `--cycles` en fazla turu, `--interval` tamamlanmış turlar arasındaki saniyeyi ve `--duration` yeni tur başlatılabilecek toplam saniyeyi belirler. En kısa aralık 300 saniyedir. Başarısız kaynak turu kaydedilir, eski veri üzerinde izleme yapılmaz ve bütçe kaldıysa sonraki tur denenir. `Ctrl+C` işlemi durdurur fakat tamamlanan turları silmez. Komut cron, daemon veya işletim sistemi hizmeti kurmaz; terminal kapandığında biter. Çıktı sessiz başlangıç sayısını ayrı verir; çok turlu toplamlar benzersiz kayıt sayısı değildir, aynı eşleşme farklı turlarda yeniden sayılabilir.

Her çalıştırma başlamadan kalıcı bir oturum kimliği alır. Tamamlanan her tur, kullandığı kaynak çalışmasına ve yalnız o turda oluşan kuruluş/domain izleme çalışmalarına bağlanır. Normal bitiş, kaynak hatalarıyla kısmi bitiş, `Ctrl+C`, uygulama hatası ve ani kapanmadan sonra açık kalan/bilinmeyen durum birbirine karıştırılmaz. `watch-monitor-list` son oturumları, `watch-monitor-show` ise seçilen oturumun tur kanıtlarını internete bağlanmadan gösterir. Ani kapanmada oturum otomatik olarak “tamamlandı” sayılmaz; bu sürüm otomatik devam veya sahipsiz oturumu kapatma işlemi yapmaz.

`watch-timeline`, seçilen izlemenin güncel kuruluş/domain tanımını bütün kayıtlı kaynak snapshot'larına ağsız uygular. İlk eşleşme, kaynak bilgisinin değişmesi, domain ilişkisinin başlaması veya bitmesi, kayan kaynak penceresinden çıkış ve aynı iddia kimliğinin yeniden görünmesi ayrı olaylardır. Aynı grup + kuruluş + kaynak keşif zamanı kimliği değişmeden sonraki snapshot'ta tekrar görülürse yeni olay oluşturulmaz; yalnız “değişmeden tekrar gözlem” sayacı artar. Kaynak bu üç kimlik alanından birini değiştirirse otomatik birleştirme yapılmaz; gerçek hayatta aynı olay olsa bile ayrı kimlik görünebilir. Görünüm yalnız cihazda saklanan snapshot dönemini kapsar ve hiçbir kayıt doğrulanmış ihlal sayılmaz.

`watch-identity-candidates`, eski kimlik kaybolurken başka bir kimlik aynı veya hemen sonraki başarılı snapshot'ta belirmişse dar bir insan inceleme listesi üretir. Aday için grup, kuruluş adı, kaynak keşif zamanı veya normalleştirilmiş web alanından en az ikisinin aynı olması gerekir; terminal hangi alanların aynı, hangilerinin değişmiş olduğunu açıkça gösterir. Eşzamanlı yaşayan kayıtlar, uzak snapshot geçişleri, yalnız tek ortak alan ve aynı kimliğin normal geri dönüşü aday yapılmaz. Komut internete bağlanmaz, alarm üretmez, karar kaydetmez ve kayıtları birleştirmez; aday “aynı olay olabilir” demektir, doğrulama değildir.

`watch-identity-review`, listede gösterilen aday kimliğine açık bir analist kararı kaydeder. `possible_same` “aynı olay olabilir”, `different` “farklı olay”, `uncertain` ise “belirsiz” anlamındadır ve her karar için 2–500 karakterlik gerekçe zorunludur. Aynı karar ve gerekçeyi tekrarlamak yeni olay üretmez; karar veya gerekçe değişirse önceki olay silinmeden yenisi eklenir. `watch-identity-review-show` tam karar zincirini ağsız gösterir. Hiçbir karar iki kaynak kimliğini birleştirmez, geçmiş zaman çizelgesini yeniden yazmaz, alarm oluşturmaz veya iddiayı doğrulanmış ihlal saymaz.

Akış verisi ThreatCluster atfıyla CC BY 4.0/TLP:CLEAR olarak sunulur. Kişisel kullanım ve açık kaynak kod bağlantısı bu dilimde uygundur; uygulamayı ileride müşterilere veri sunan ticari bir ürüne dönüştürmeden önce sağlayıcının güncel ürün/yeniden dağıtım koşulları yeniden incelenmelidir. Kaynak verisi repoya paketlenmez.

## İnternette ara

Proje klasöründe:

```sh
./xti scan markam.com
./xti status
./xti inbox
./xti triage
```

`markam.com` yerine izlemek istediğin adresi yaz. İlk komut kayıt alanı yoksa oluşturur, adresini kaydeder, internetten arar ve sonuçları saklar. Sonraki çalıştırmada yalnız `./xti scan` yazarak kayıtlı adresleri yeniden kontrol edebilirsin. Bir turda en fazla beş adres aranır.

Varsayılan olarak iki kaynak kullanılır:

| Kaynak | Ne getirir? |
|---|---|
| crt.sh | Yayımlanmış sertifikalarda görülen adresler |
| urlscan | Daha önce yapılmış web incelemelerinde görülen adresler |

Ücretli API anahtarı gerekmez. urlscan'in anonim erişimi küçük kotalara ve geçmiş sınırına tabidir; bu sınır sonuçta gösterilir. Gerçek denemede son 30 gün sınırı bildirildi. Her sorguda en fazla ilk 100 urlscan kaydı alınır; kalan sonuç varsa arama kısmi gösterilir. Arşiv araması yeni site taraması göndermez; hedef bağlantısı aşağıdaki `--check` seçeneğiyle yapılır. Bu bütün interneti kapsayan bir arama değildir.

Kullanılan bütün internet bağlantılarını ve aralarındaki farkı görmek için:

```sh
./xti sources
```

Bu komut crt.sh, isteğe bağlı theHarvester Common Crawl/Wayback ve urlscan pasif arşivlerini, Google Public DNS çözümleyicisini, ücretsiz Feodo Tracker ve CERT Polska IOC beslemelerini, ThreatCluster açık ransomware iddia akışını, resmî MITRE ATT&CK Enterprise verisini, CISA KEV, FIRST EPSS, NIST NVD, OSV.dev, Canonical Ubuntu OSV, Red Hat ve SUSE CSAF VEX zafiyet kaynaklarını, yalnız açık kullanıcı komutuyla hedefe bağlanan HTTPS HEAD kontrolünü ve onaylı kesin IP'ye yapılan sınırlı TCP servis kontrolünü ayrı gösterir. Her bağlantının amacı, ücretli anahtar kullanıp kullanmadığı, hangi komutlarda çalıştığı ve temel sınırları görünürdür. Komut yeni ağ isteği göndermez; son kaydedilen kaynak sonuçlarını da ayrıca listeler.

İlk ikinci-kaynak değerlendirmesinde HackerTarget, Common Crawl, Cert Spotter ve Subfinder doğrudan çekirdek adaptörüne alınmadı. Daha sonra Common Crawl ile Wayback Archive, kaynak durumunu ve JSONL kanıtını ayrı raporlayan sabit theHarvester profili üzerinden sınırlandırılarak kabul edildi. Subfinder v2.17.0 yeniden incelendi; normal CLI çıktısı kaynak hatası ile tamamlanmış boş sonucu güvenilir biçimde ayıramadığı ve mevcut ücretsiz kapsamın çoğunu tekrarladığı için eklenmedi. Kararı internete çıkmadan görmek için:

```sh
./xti surface source-evaluation
```

İlk değerlendirme [0023 numaralı kayıtta](docs/decisions/0023-free-passive-source-evaluation.md), theHarvester kararı [0117 numaralı kayıtta](docs/decisions/0117-bounded-theharvester-archive-discovery.md), güncel kabul kapısı ise [0124 numaralı kayıtta](docs/decisions/0124-passive-source-integrity-and-adapter-gate.md) bulunur.

Kaynakların yanıtları ve hataları ayrı tutulur. Bir kaynak erişim hatası verdiğinde diğerinden alınan sonuçlar korunur; genel sonuç kısmi olarak görünür. Depolama veya uygulama doğrulama hataları ise kalan işleri durdurabilir. Kaynak hatası, aday bulunmadığı anlamına gelmez.

Yalnız bir kaynağı seçmek istersen:

```sh
./xti scan markam.com --source urlscan
./xti scan markam.com --source crt.sh
```

crt.sh marka ifadesini içeren veya onunla başlayan adları; urlscan adınla başlayan alan adı parçalarını arar. Örneğin farklı uzantı veya ek sözcük taşıyan adresler bulunabilir. Kaynakların indeksleri ve arama sınırları nedeniyle adın geçtiği bütün adreslerin bulunacağı garanti edilmez. Ek olarak bazı harf değişimlerini aramak için:

```sh
./xti scan markam.com --typos
```

Bu seçenek ad başına en fazla altı yan yana harf değişimini ve en fazla dört sınırlı Unicode benzer-harf/Punycode varyantını ayrıca sorgular. Kaynaklardan gelen geçerli Punycode adresleri seçenek olmasa da analiz edilir; seçenek, normal marka aramasında görünmeyecek Punycode biçimlerini ayrıca internette aratır. Bütün yazım ve Unicode olasılıklarını kapsamaz, daha fazla kaynak isteği kullanır ve daha uzun sürer. Dört karakterden kısa marka etiketleri çok geniş sorguları önlemek için şimdilik kabul edilmez.

Örnek: Kiril `е` harfiyle yazılmış `еxample.net`, DNS için ASCII `xn--...` biçiminde saklanır; bulgu nedeninde güvenle çözülen görünüm ve “Unicode benzer-harf” açıklaması gösterilir. Bu yalnız inceleme adayıdır, phishing kararı değildir. Unicode 18.0 kuralları uygulamayla paketlidir ve çalışma sırasında indirilmez.

## Eşleştirme kalitesini ölç

```sh
./xti evaluate
```

Bu komut eşleştirme kurallarını uygulamayla paketlenmiş 47 sürümlü sentetik örnekte ölçer. İnternete bağlanmaz, kayıt alanı veya veritabanı oluşturmaz. Yakalanan, kaçırılan ve gereksiz alarma dönüşen örnekleri; isabet, yakalama ve gereksiz alarm oranlarını gösterir.

`review` etiketi “insan incelemesine gönderilmesi bekleniyor” anlamındadır; phishing veya kötü niyet kararı değildir. Kümede sahip olunan adres, farklı uzantı, yazım farkı, hizmet eki, yanıltıcı alt alan adı, private/public suffix, Unicode benzer-harf ve sentetik meşru bağlam örnekleri bulunur. Mevcut bilinen açıklar rapordan saklanmaz.

Bu küçük sentetik kümenin sonucu gerçek internet doğruluk oranı değildir. Yeni kurallar önce bu kümede davranış değişikliği açısından görülebilir; gerçek kullanım geri bildirimi geldikçe veri kümesi ayrı sürümle genişletilmelidir. Otomasyon için `./xti --json evaluate` kullanılabilir.

0.14.0 ölçümünde yan yana harf değişimiyle bilinen hizmet ekinin birleşimi (`exampel-login.net`) ve yeterince uzun markaya bitişik `shop` ifadesi (`exampleshop.net`) yakalanır. Bilinmeyen ekler, `workshop.net` gibi kısa sözcük birleşimleri ve `exampleshopping.net` gibi daha uzun sözcükler bu yeni dar kuralla aday yapılmaz. Sonuç: 27 beklenen adayın 27'si yakalandı; 20 göz ardı örneğinin 17'si doğru elendi. Kalan üç bağlamsal yanlış alarm otomatik susturulmadı; doğrulanırsa tam adres istisnası kullanılmalıdır.

Yeni desenler ayrı kural kimliği taşır. Önceki ASCII bulgular, Unicode bulgular, kararlar ve bildirimler eski kimlikleriyle korunur. Harf değişimli adresin kaynak aramasına eklenmesi için `--typos` kullanılması gerekir; eşleştiricinin bir adresi tanıyabilmesi kaynağın o adresi mutlaka bulacağı anlamına gelmez.

## Kendi inceleme geri bildirimini gör

```sh
./xti feedback
./xti --json feedback
```

Bu komut toplam adayları, kaçını incelediğini, son kararlarının dağılımını, birden çok kez değerlendirdiğin bulguları ve bunların kural sürümüne göre sayılarını gösterir. İnternete bağlanmaz; veritabanını, okundu bilgisini veya karar geçmişini değiştirmez. JSON görünümü de yalnız toplu sayıları ve kural sürümlerini verir; domain, karar gerekçesi veya bulgu kimliği çıkarmaz.

Bu özet bir kalite sinyalidir, doğruluk raporu değildir. `dismissed` kararı otomatik “yanlış pozitif”, `suspicious` kararı otomatik “gerçek phishing” sayılmaz. Precision/recall gibi kalite oranları ancak kökeni belli ve ayrıca doğrulanmış etiketlerle hesaplanabilir. Kayıtlı son karar ile silinmeyen karar geçmişi uyuşmazsa komut yanıltıcı sayı vermek yerine güvenli biçimde durur.

**0.1–0.123 sürümlerinde kayıt oluşturduysan:** önce `./xti migrate` çalıştır. Bu komut önce yedek alır, sonra mevcut kayıtları koruyarak düzeni günceller. Vaka tabloları boş başlar; eski bulgu, sosyal profil, ransomware veya tedarikçi kayıtlarından kendiliğinden vaka üretilmez.

Yeni kayıt düzeni şema 54'tür. Eski uygulamaya dönmek gerekiyorsa geçiş öncesi yedeği kullan. Listeleme ve raporlama veritabanını kendiliğinden dönüştürmez.

## Yerel IOC kataloğu

Bir domain, IP, HTTP(S) URL veya hash göstergesini kaynağıyla ekleyebilirsin:

```sh
./xti ioc add domain bad.example \
  --source manual \
  --reference local:case-1 \
  --confidence 70 \
  --description "Savunma amaçlı yerel incelemede kaydedildi"
./xti ioc list
./xti ioc lookup domain bad.example
./xti ioc show IOC_KIMLIGI
./xti ioc revoke KAYNAK_IDDIASI_KIMLIGI --reason "Kaynak kaydı geri çekti"
./xti ioc sync --source feodo
./xti ioc status --source feodo
./xti ioc sync --source certpl
./xti ioc status --source certpl
```

Desteklenen türler `domain`, `ipv4`, `ipv6`, `url`, `md5`, `sha1` ve `sha256`dır. Aynı gösterge yalnız bir ana kimlik alır; farklı kaynaklar birbirini ezmeden ayrı güven puanı, açıklama, ilk/son görülme ve isteğe bağlı `--valid-from` / `--valid-until` taşır. Aynı kaynak gözlemi yeniden verilirse zaman aralığı genişletilir; aynı olayın tekrarı çoğaltılmaz. `revoke` yalnız seçilen kaynak iddiasını etkisizleştirir ve geçmişi silmez.

`ioc sync --source feodo`, Feodo Tracker'ın saldırgan olmayan son 30 günlük botnet C2 JSON listesini açık komutla alır. Sabit HTTPS adresi, yönlendirme reddi, 30 saniye, 8 MiB ve 50.000 kaynak satırı sınırı vardır. Aynı IP'nin port/malware satırları tek kaynak iddiasında birleşir. Her çalışma ve IOC başına işlem kaydedilir. Ağ/biçim hatası boş liste sayılmaz ve önceki etkin kayıtlar korunur; yalnız başarılı tam snapshot'ta artık bulunmayan Feodo iddiaları geçmiş silinmeden geri çekilir.

`ioc sync --source certpl`, CERT Polska Warning List'in son bir ay içinde eklenmiş ve hâlâ etkin domainlerden oluşan uBlock metin listesini alır. Başlık ve zaman bilgileri, kanonik domainler, tekrarlar, 48 saatlik güncellik, 8 MiB ve 50.000 domain sınırı bütün liste yazılmadan önce doğrulanır. Değişmeyen binlerce üyelik her çalışmada ayrı öğe satırı olarak çoğaltılmaz; içerik özeti, toplamlar ve değişiklikler korunur. Kaynak Polonya odaklıdır ve küresel/tarihsel tam phishing listesi değildir.

`ioc list/show/lookup/status` salt okunurdur; yalnız `sync` internete çıkar. İki kaynak için de 50/100 güven puanı kaynağın verdiği puan değil, açıkça belgelenmiş XTI yerel nötr politikasıdır. IOC'ler otomatik engellenmez; zararlılık doğrulaması, yanlış pozitif kararı ve varlık etkisi ayrıca incelenmelidir.

Güncel IOC kaynak iddialarını standart bir STIX 2.1 JSON paketine çıkarmak için:

```sh
./xti cti stix-export xti-iocs.json
./xti cti stix-export domain-iocs.json --indicator-type domain
```

`stix-export`, domain, IPv4/IPv6, URL, MD5, SHA-1 ve SHA-256 değerlerini STIX `Indicator` pattern'lerine dönüştürür; güncel kaynak başvurularını, açıklamaları, en yüksek kaynak güvenini ve geçerlilik zamanını korur. Aynı anda en fazla 50.000 IOC ve 50.000 bağlı kaynak iddiası tek salt-okunur SQLite anlık görüntüsünde doğrulanır. Kapsam sınırı aşılır veya ilgili kayıt bozuksa kısmi dosya yayımlanmaz. Çıktı en fazla 32 MiB'dir, özel dosya izniyle atomik oluşturulur ve mevcut dosyanın üzerine yazılmaz.

Komut internete çıkmaz, veritabanını değiştirmez ve IOC'yi otomatik zararlı saymaz. Bu ilk STIX dilimi yalnız güncel IOC `Indicator` nesnelerini kapsar; CTI varlık/ilişki nesneleri, içe aktarma, TLP işaretleri ve TAXII servisi henüz dahil değildir.

## İmzalı webhook teslim kuyruğu

Yerel bildirim kutusundaki seçtiğin tek olayı bir HTTPS alıcısına göndermek için:

```sh
./xti webhook secret-generate .xti-data/my-webhook.key
./xti webhook target-add "Yerel SIEM" https://siem.example.net/xti \
  --secret-file .xti-data/my-webhook.key
./xti webhook target-list
./xti inbox list --status all
./xti webhook queue HEDEF_KIMLIGI BILDIRIM_KIMLIGI
./xti webhook delivery-list --status queued
./xti webhook deliver TESLIM_KIMLIGI
./xti webhook delivery-show TESLIM_KIMLIGI
```

`queue`, bildirimin o andaki kanıtını en fazla 256 KiB'lik değişmez JSON gövdesi olarak saklar. Aynı hedef ve bildirim çifti ikinci kez çoğaltılmaz. `deliver` her denemeyi ayrı kaydeder; geçici hata yeniden denenebilir, başarılı teslim tekrar gönderilmez. Otomatik veya arka plan gönderimi yoktur: her gönderim terminalden açıkça başlatılır.

İstek `X-XTI-Delivery`, `X-XTI-Event`, `X-XTI-Timestamp` ve `X-XTI-Signature-256` başlıklarını taşır. İmza, gizli anahtarla `timestamp + "." + gönderilen_ham_gövde` üzerinde HMAC-SHA256 hesaplanarak `sha256=...` biçiminde doğrulanır. Alıcı, teslim kimliğini tekrar önleme anahtarı olarak saklamalı ve zaman damgasına kendi kabul penceresini uygulamalıdır.

Hedef yalnız `HTTPS` ve port `443` olabilir. Her gönderimde DNS yeniden çözülür; sonuçlardan biri bile yerel/özel/loopback/rezerve IP ise bağlantı kurulmaz. Bağlantı doğrulanan genel IP'ye sabitlenir, TLS adı hedef host ile doğrulanır, yönlendirme izlenmez ve yanıt gövdesi kanıt olarak saklanmaz. Tam URL ve gizli anahtar terminal/JSON çıktısına yazılmaz. Gizli anahtar komut satırı yerine yalnız sahibi tarafından okunabilen (`0600`) dosyadan alınır; yerel SQLite veritabanı ve yedekleri anahtarı içerdiği için cihaz, veri klasörü ve yedekler özel tutulmalıdır.

`target-secret-set` anahtarı döndürür; `target-revoke` hedefi geçmişi silmeden kapatır. Bu ilk dilim yalnız kullanıcının seçtiği mevcut yerel bildirimleri kapsar. Otomatik olay aboneliği, toplu gönderici, takvim servisi, webhook alıcısı, e-posta/SMS, SIEM'e özgü biçimler ve dış hizmetin olayı gerçekten işlediğini doğrulama henüz yoktur.

## Yerel CTI bilgi tabanı

Aktör, kampanya, malware ve rapor kayıtlarını; bunların birbirleriyle veya IOC'lerle ilişkilerini kaynağıyla saklayabilirsin:

Resmî MITRE ATT&CK Enterprise v20.0 grup, kampanya, zararlı yazılım, teknik, alt teknik ve taktik kataloğunu almak için:

```sh
./xti cti attack-sync
./xti cti attack-status
./xti cti attack-search "DNS"
./xti cti attack-show T1059.001
./xti cti attack-show T1105 --relationship-limit 500 --relationship-offset 500
./xti cti search "APT29"
./xti cti entity-list --type threat-actor --limit 20
./xti cti relation-list --limit 20
```

İlk komut yaklaşık 55 MB'lık sürümü sabitlenmiş STIX 2.1 dosyasını resmî MITRE deposundan indirir. Dosyanın tamamı doğrulanmadan hiçbir kayıt yazılmaz; yazma da tek işlem içindedir. Kaynak kesilir, biçim değişir veya yerel ATT&CK geçmişi bozuksa önceki kayıtlar korunur. Aynı sürümü yeniden çalıştırmak kayıtları çoğaltmaz; kaynakta artık etkin olmayan ATT&CK iddiaları geçmişi silinmeden geri çekilir. Elle eklediğin başka kaynak iddiaları etkilenmez.

Ek katalog teknikleri, alt teknikleri ve taktikleri kesin STIX/ATT&CK kimlikleriyle saklar; aynı adlı teknikleri birleştirmez. `attack-search` için `--limit/--offset`, `attack-show` için `--relationship-limit/--relationship-offset` sonraki kayıtları gösterir. Teknik–taktik bağları `kill_chain_phases` alanından türetilmiş olarak ayrı etiketlenir; STIX ilişkisi diye sunulmaz. Arama, ayrıntı ve durum komutları internete çıkmaz. Savunma nesneleri, `tool` ve diğer STIX türleri bu katalogda yoktur. ATT&CK `intrusion-set` kaydı yerelde araştırılabilir `threat-actor` etiketiyle tutulur; bu otomatik kişi/grup atfı veya tehdit hükmü değildir. 50/100 güven değeri MITRE'nin verdiği puan değil, XTI'ın nötr yerel politikasıdır. Sürüm kendiliğinden yükselmez; yeni ATT&CK sürümü kod ve veri sözleşmesi incelenerek ayrıca alınır. Başarılı katalog senkronlarının tarih/hash ve değişim geçmişi `attack-status` ile görünür; başarısız indirmeler için ayrı kalıcı senkron kaydı ve kendiliğinden ATT&CK güncellemesi yoktur.

ATT&CK verisi MITRE'nin telif ve lisans koşullarına tabidir; proje veriyi kendi kaynak kodunda paketlemez, açık komutta resmî adresten indirir. Atıf ve lisans bağlantısı [üçüncü taraf bildiriminde](THIRD_PARTY_NOTICES.md) yer alır.

Elle kayıt eklemek istersen:

```sh
./xti cti entity-add threat-actor "Example Group" \
  --alias "Example Crew" \
  --source manual \
  --reference local:report-1 \
  --confidence 60 \
  --description "Analist incelemesinde rapordan kaydedildi"
./xti cti entity-list
./xti cti entity-lookup threat-actor "Example Group"
./xti cti entity-show VARLIK_KIMLIGI

./xti cti relation-add KAYNAK_VARLIK_KIMLIGI uses \
  --to-entity HEDEF_VARLIK_KIMLIGI \
  --source manual \
  --reference local:report-1-relation \
  --confidence 55 \
  --description "Rapor bu kullanım ilişkisini bildiriyor"
./xti cti relation-add KAYNAK_VARLIK_KIMLIGI communicates-with \
  --to-ioc IOC_KIMLIGI \
  --source manual \
  --reference local:report-1-ioc \
  --confidence 50 \
  --description "Rapor bu altyapı ilişkisini bildiriyor"
./xti cti relation-list
./xti cti relation-show ILISKI_KIMLIGI
```

Varlık adı, kaynaklı alternatif ad veya IOC değeri içinde tek arama yapmak için:

```sh
./xti cti search "Example"
./xti cti search "Example" --kind entity --entity-type malware
./xti cti search "192.0.2" --kind indicator --indicator-type ipv4
./xti cti search "eski ad" --all --limit 100
```

Sonuçlar tam eşleşme, başlangıç eşleşmesi ve içerme eşleşmesi sırasındadır. Varsayılan kapsam yalnız etkin CTI iddialarını ve sorgu anında geçerli IOC iddialarını kullanır; `--all` geri çekilmiş veya süresi dolmuş kaynak geçmişini de arar. En fazla 50.000 CTI varlığı ve 50.000 IOC güvenli üst sınır içinde tümden doğrulanır, sonuç görünümü 1–500 kayıtla sınırlandırılır. Arama yeni tablo oluşturmaz, internete çıkmaz ve hiçbir kaydı değiştirmez.

Aynı aramayı zaman içinde karşılaştırmak için kaydedebilirsin:

```sh
./xti cti watch-add "Example takibi" "Example" --kind entity
./xti cti watch-list
./xti cti watch-run KAYITLI_ARAMA_KIMLIGI
./xti cti watch-run-all --search-limit 50 --item-limit 100
./xti cti watch-monitor KAYITLI_ARAMA_KIMLIGI --cycles 3 --interval 3600 --duration 86400
./xti cti watch-tag-add KAYITLI_ARAMA_KIMLIGI priority:high
./xti cti watch-note-add KAYITLI_ARAMA_KIMLIGI --kind hypothesis --text "İlişki incelenecek"
./xti cti watch-note-add KAYITLI_ARAMA_KIMLIGI --run-id CALISMA_KIMLIGI --kind conclusion --text "Çalışma incelendi"
./xti cti watch-journal KAYITLI_ARAMA_KIMLIGI
./xti cti watch-show KAYITLI_ARAMA_KIMLIGI
./xti cti watch-run-show CALISMA_KIMLIGI
./xti cti watch-revoke KAYITLI_ARAMA_KIMLIGI --reason "İzleme artık gerekli değil"
```

Her açık `watch-run`, görünüm sınırından bağımsız tam eşleşme kümesini tek işlemde saklar ve aynı tanımın bir önceki çalışmasına göre `yeni`, `değişen`, `aynı` ve `artık eşleşmeyen` kayıtları ayırır. İlk çalışma sessiz başlangıçtır. Sonraki çalışmada yeni, değişen veya artık eşleşmeyen kayıt varsa çalışma kanıtına bağlı tek bildirim `./xti inbox` kutusuna eklenir; değişmeyen tekrar bildirim üretmez. Sorgu veya filtre değişirse eski tanımla yanlış karşılaştırma yapılmaz; yeni ve sessiz bir karşılaştırma tabanı başlar. Komutlar internete çıkmaz, tehdit hükmü üretmez ve otomatik zamanlayıcı başlatmaz.

`watch-run-all`, bütün etkin kayıtlı aramaları adlarına göre sabit sırada bir kez yeniler. Varsayılan en fazla 50, açıkça en fazla 500 aramaya izin verir. Etkin arama sayısı `--search-limit` değerini aşarsa sessizce bir bölümünü atlamak yerine hiçbirini çalıştırmadan durur. Her arama ayrı atomik kanıttır; sonraki bir hata daha önce tamamlanan aramaları silmez. Geri çekilmiş aramalar çalıştırılmaz. Komutun bütün ömründe ortak yerel çalışma kilidi tutulur.

`watch-monitor`, yalnız terminal açıkken çalışır. Her tamamlanan tur normal ve kalıcı bir `watch-run` kaydıdır. Tur sayısı 1–1000, aralık 300–86400 saniye, yeni tur başlatma süresi 1–604800 saniye arasında açıkça sınırlıdır. Süre dolunca yeni tur başlamaz; `Ctrl+C` daha önce tamamlanan turları silmeden işlemi durdurur. İşletim sistemi servisi, açılış görevi veya gizli arka plan süreci kurulmaz.

Etiketler yalnız düzenleme ve filtreleme bağlamıdır; tehdit kararı değildir. Aynı etiket ekleme, görünüm güncelleme, kaldırma ve yeniden etkinleştirme geçmişi korunur; bir aramada en fazla 50 etkin etiket bulunabilir. Analist notları `observation`, `hypothesis`, `conclusion` veya `follow-up` türündedir ve sonradan sessizce değiştirilmez. `--run-id` verilirse çalışma aynı kayıtlı aramaya ait olmalıdır. Etiket ve not eklemek arama sorgusunu değiştirmez veya karşılaştırma tabanını sıfırlamaz.

Desteklenen varlık türleri `threat-actor`, `campaign`, `malware` ve `report`; ilişki türleri `attributed-to`, `uses`, `targets`, `delivers`, `communicates-with`, `indicates`, `related-to` ve `reports-on` değerleridir. Aynı isim ve tür tek ana kayıtta tutulur; her `kaynak + başvuru` ayrı alternatif ad, güven, açıklama ve gözlem geçmişi taşır. Aynı ilişkiyi bildiren kaynaklar da birbirini ezmez. `entity-revoke` veya `relation-revoke`, yalnız verilen kaynak iddiasını geçmişi silmeden geri çeker.

Bu katman otomatik aktör atfı, isim benzerliğine göre birleştirme, nedensellik veya doğrulanmış tehdit hükmü üretmez. Çelişen atıflar ayrı ilişkiler olarak korunur. `entity-list/show/lookup` ve `relation-list/show` ağsız ve salt okunurdur; bilgi tabanı yalnız açık ekleme veya geri çekme komutuyla değişir.

## Takibin genel durumunu gör

```sh
./xti status
./xti status markam.com
```

İlk komut son aramaları, sıradaki işleri, kaynak beklemelerini, inceleme durumlarını ve okunmamış bildirimleri bir arada gösterir. İkinci komut arama ayrıntısını tek kayıtlı adresle sınırlar; üstteki toplam sayılar bütün kayıt alanına ait kalır.

Her adresin crt.sh ve urlscan geçmişi ayrı değerlendirilir. Yeni eklenen adres, başka bir adresin araması nedeniyle güncel görünmez. Son tamamlanan arama ile son deneme ayrı gösterilir: başarılı bir aramadan sonra hata oluşmuşsa eski başarı hatayı gizlemez. Birden fazla adresli iş kısmi kaldıysa bu iş hiçbir adres için tamamlanmış sayılmaz.

Varsayılan olarak son 24 saatte tamamlanan arama “Son tam arama güncel” görünür. Daha eski kayıtlar, hiç tamamlanmamış aramalar ve tutarsız zamanlar ayrıca belirtilir. Bu bilgi kaynağın şu anda erişilebilir olduğunu veya adayların güvenli olduğunu söylemez. Eşiği değiştirebilirsin:

```sh
./xti status --stale-after-hours 48
./xti status --limit 50
./xti --json status
```

Saat eşiği 1–8760, gösterilecek adres sayısı 1–100 arasındadır. Varsayılan ilk 20 adres alfabetik gösterilir; kalan adres sayısı açıkça yazılır. Listede olmayan bir adresin ayrıntısına `status ALAN_ADI` ile ulaşılır. Eşik, otomatik arama sıklığını değiştirmez.

Özeti açmak internete bağlanmaz, iş başlatmaz, bildirimleri okundu yapmaz veya yarım işleri kurtarmaz. “Çalışıyor olarak kayıtlı” ifadesi programın hâlâ açık olduğunu kanıtlamaz. Geçmiş başarısız işlerin toplamı, şu an kesinti yaşayan kaynak sayısı değildir. Kayıt alanı yoksa oluşturulmaz; önce `scan ALAN_ADI` veya `init` gerekir. Veritabanı bütünlük kontrolü için `doctor` kullanılır.

Özet bütün verileri aynı kayıt anından okur. Sonuç ayrıntıları sınırlı yüklenir; geçmiş uzadıkça kayıt tarama süresi artabilir. Bu sürüm büyük ölçek performansı iddiası taşımaz.

## Bul, kontrol et, incele, raporla

```sh
./xti scan markam.com --check
./xti triage
```

İlk komut internette adayları arar; ardından bu izlenen adrese bağlı, kontrol bekleyen en fazla 10 açık bulguyu kontrol eder. DNS ile IP adresini öğrenir, uygun adrese güvenli HTTPS bağlantısı kurup yalnız yanıt başlıklarını ister. Bulunan sayfayı açıp içeriğini çalıştırmaz. `--check-limit 5` gibi bir değerle tur sınırını 1–20 arasında seçebilirsin. Kalan sayı sonuçta gösterilir.

İnceleme listesinde önce senin şüpheli işaretlediklerin ve son altı saatte HTTPS yanıtı alınan adaylar görünür. Yanında neden ve kontrolün güncelliği bulunur. Bu sıra risk puanı değildir; erişilen bir site normal olabilir. DNS bulunamaması veya zaman aşımı da adayı güvenli yapmaz.

Listede gördüğün kimliği kullan:

```sh
./xti findings show BULGU_KIMLIGI
./xti findings check BULGU_KIMLIGI
./xti findings review BULGU_KIMLIGI --decision uncertain --reason "Ek inceleme gerekiyor"
./xti report BULGU_KIMLIGI --output ./raporlar/bulgu-1.json
```

Tek kimlikle kontrol, hemen yeni bir deneme yapar. Kimlik vermeden `./xti findings check` dersen kontrol bekleyen açık bulgular işlenir. Toplu işlem son altı saatteki denemeleri, hata vermiş olsalar da tekrar etmez; kapattığın bulguları atlar. Aynı turdaki aynı aday domain için tek ağ kontrolü yapılır. `./xti triage --all` kapatılanları da gösterir. `--limit` ile inceleme listesini en fazla 500 kayda çıkarabilirsin.

Rapor kaynak bağlantılarını, eşleşme nedenlerini, verdiğin kararları ve tüm tamamlanmış hedef kontrollerini içerir. Mevcut dosya ezilmez; yeni dosya adı kullan. Rapor üretmek veya inceleme listesini görmek internete bağlanmaz. Rapor 8 MiB ile sınırlıdır; tam yedek ayrıca alınabilir. Kontrol bir hata nedeniyle yarıda kalsa bile önceki tamamlanan kontroller korunur; bitmemiş hedef kontrolü kaydedilmiş sayılmaz.

Hedef kontrolü Google Public DNS üzerinden yapılır; sorgulanan aday adları bu sağlayıcıya iletilir. Hedefte yalnız 443 numaralı HTTPS portu, tek IP ve `/` yolu kontrol edilir. Yönlendirmeler izlenmez; diğer IP, port veya sayfalara geçilmez. Özel/yerel IP içeren DNS yanıtlarında hedef bağlantısı engellenir. TLS doğrulaması başarısızsa devam edilmez. Bir hedef için toplam süre sınırı 25 saniye, her bağlantı için en fazla 8 saniyedir. Bu sınırlar nedeniyle kontrol tamamlanamayabilir; ayrıntı kaydedilir.

HTTP `103 Early Hints` gibi ek ara yanıtlar bu sürümde tamamlanamayan kontrol olarak kaydedilir. Bu da sitenin kapalı olduğunu göstermez. Ağ ve kayıt sınırlarının teknik gerekçeleri [tasarım kararında](docs/decisions/0006-controlled-checks-and-reports.md) bulunur.

## Düzenli kontrol et

```sh
./xti watch markam.com
./xti watch markam.com --check
```

Program hemen arar, sonra her kontrolün bitişinden bir saat sonra tekrarlar. Terminal açık kalmalı; bilgisayarın kapanması veya işlemin durması kontrolü durdurur. Durdurmak için `Ctrl+C`. Yeniden çalıştırınca tekrar arar ve önceki kayıtları çoğaltmaz. Bir kaynak kesintisi döngüyü bitirmez; sonraki turda yeniden dener. Sağlayıcının bekleme talebi varsa buna uyar.

`--check` kullanıldığında aramadan sonra bekleyen adayların hedef kontrolü de yapılır; altı saatlik tekrar sınırı geçerlidir. Hedef kontrolündeki ağ hatası sonraki turu engellemez.

Aralığı veya tur sayısını belirlemek için:

```sh
./xti watch markam.com --interval 1800
./xti watch markam.com --cycles 1
```

Aralık en az 300, en fazla 86400 saniye olabilir. Bu sürüm bilgisayar kapalıyken çalışan bir sunucu hizmeti veya kesintisiz sertifika akışı değildir.

## Süreli izleme denemesi yap

```sh
./xti monitor start markam.com --cycles 3 --interval 300 --duration 1800
```

Bu komut iki internet kaynağında en fazla üç tur arama yapar; turlar arasında beş dakika bekler. En fazla 30 dakika boyunca yeni kaynak araması başlatır. Tur veya süre sınırından hangisine önce ulaşılırsa deneme biter. Başlamış kaynak araması kendi sorgu ve zaman sınırlarıyla tamamlanabilir; bu yüzden toplam süre belirtilen sınırı aşabilir.

Tek kaynak için `--source urlscan` veya `--source crt.sh` ekleyebilirsin. Adres vermezsen başlangıçta kayıtlı en fazla beş adres seçilir. Adresler, kaynaklar ve kurallar denemeye kaydedilir. `--typos` sınırlı ek yazım aramalarını açar. Bu komut aday sitelere aktif kontrol yapmaz.

Varsayılanlar üç tur, turlar arasında 3600 saniye ve 86400 saniyelik süre sınırıdır. Tur sayısı 1–1000, aralık 300–86400 saniye, süre 1–604800 saniye olabilir. Program terminal açıkken çalışır; durdurmak için Ctrl+C kullan.

Sonuçta her kaynak için planlanan/başlayan çalışmalar, tamamlanan/kısmi/başarısız denemeler, kayıtlı sorgular ve yeni bulgular görünür. “Tamamlanan tur”, bütün kaynak denemelerinin bitmesidir; hepsinin başarılı olduğu anlamına gelmez. Yarıda kalan denemenin son sayı özeti yoksa bu açıkça belirtilir; eksik sayı sıfır sayılmaz. Sorgu sayısı, sağlayıcının HTTP isteği sayısı veya erişilebilirlik oranı değildir.

```sh
./xti monitor list
./xti monitor show DENEME_KIMLIGI
./xti monitor show DENEME_KIMLIGI --limit 100
```

Kimliği başlangıçta veya listede görebilirsin. `show`, kaynak özetlerini ve varsayılan son 20 kaynak çalışmasını gösterir; `--limit` 1–2000 arasındadır. İş kimliğiyle `jobs show IS_KIMLIGI` tam sorgu geçmişini açar. Listelemek ve raporu açmak internete bağlanmaz, bildirimleri okundu yapmaz ve yarım işi kendiliğinden düzeltmez.

Deneme boyunca, bekleme sırasında da aynı kayıt alanında başka arama veya hedef kontrolü çalışmaz. `status`, `inbox` ve inceleme komutları kullanılabilir; normal işleri `scan --queue` ile sıraya ekleyebilirsin. İzleme işleri genel worker tarafından alınmaz ve ayrı `jobs retry` ile yeniden çalıştırılmaz; yeni ölçüm için yeni deneme başlatılır.

Program zorla kapandıysa:

```sh
./xti monitor recover
```

Bu komut aktif çalıştırıcı yokken yarım denemeyi kapatır; tamamlanmış kayıtları korur, başlamamış işi çalıştırmaz. Yeni `monitor start` da önce bu kurtarmayı yapar. Süreç öldürüldüğünde ölçülen süre güvenilir biçimde geri getirilemiyorsa “bilinmiyor” kalır. İzleme geçmişi yedeklere dahildir. Bu özellik otomatik başlayan arka plan hizmeti değildir.

## Kontrol geçmişini gör

Her kaynak için ayrı iş ve deneme kaydedilir. Varsayılan `scan` ve her `watch` turu iki iş oluşturur. Terminal kapandıktan sonra geçmişi görebilirsin:

```sh
./xti jobs list
./xti sources
```

İşler sırada, çalışıyor, tamamlandı, kısmi, başarısız veya yarım kaldı olarak görünür. `sources`, son denemenin kaydedilmiş sorgu sonuçlarını gösterir; o anda internete bağlanıp kaynağın çalıştığını ölçmez.

Kaynak “bir süre bekle” derse bekleme artık diske de kaydedilir. Programı kapatıp açmak bu süreyi sıfırlamaz. `sources` kalan süreyi ve en erken yeniden istek zamanını gösterir. Beş saniyeden uzun bekleme varsa o kaynağa yeni istek gönderilmez; işte nedeni görünür ve diğer kaynak devam edebilir. Süre dolunca yeni `scan`, sıradaki `worker` veya uygun iş için `jobs retry` ile yeniden denenir; program kendiliğinden arka planda uyanmaz.

crt.sh için en az bir, urlscan için en az iki saniyelik istek aralığı da aynı kayıt alanında korunur. Kota bilgisi yanıtın başlıkları alınır alınmaz saklanır; yanıtın devamı gelmese veya program kapansa da korunur. Kayıt okunamaz/yazılamazsa yeni istek gönderilmez. Bu düzen aynı kayıt alanına aittir; başka programların veya başka kayıt klasörlerinin kaynak kullanımını ölçmez. Yeniden açılışta cihazın saatinin doğru olması gerekir.

Listede gördüğün kimliği `IS_KIMLIGI` yerine yaz:

```sh
./xti jobs show IS_KIMLIGI
./xti jobs retry IS_KIMLIGI
```

Ayrıntıda başlangıç/bitiş zamanı, tamamlanan sorgular, kaynak bağlantıları ve hata nedenleri bulunur. Yeniden deneme, bekleyen/kısmi/başarısız/yarım iş için yapılır ve eski geçmişi koruyan ayrı bir deneme oluşturur. Arama baştan yapılır; önceki gözlem ve bulgular çoğaltılmaz. Tamamlanmış bir işi yeniden kontrol etmek için yeni `scan` kullanılır.

Program zorla kapatıldıysa işi son kayıtta hâlâ çalışıyor görebilirsin. Bunu kontrol etmek için:

```sh
./xti jobs recover
./xti jobs list --status interrupted
```

Bu işlem, başka çalıştırıcı olmadığını kontrol ettikten sonra kapanmış işleri yarım olarak işaretler; arama başlatmaz. Sonraki `scan`, `worker` veya `jobs retry` başlangıcında da aynı kontrol yapılır. Gerçekten çalışan başka bir işlem varsa kurtarma/ikinci çalıştırma engellenir. Yalnız listelemek durumu değiştirmez.

İstersen işi şimdi kaydedip sonra çalıştırabilirsin:

```sh
./xti scan markam.com --queue
./xti worker --once
```

İlk komut ağ isteği yapmadan iki kaynak için iki iş kaydeder. İkinci komut sıradaki tek işi çalıştırıp çıkar; diğer iş için yeniden çalıştırılır. `worker` ve `jobs retry`, işin kayıtlı kaynağını otomatik seçer. Başarısız işler kendiliğinden sonsuz tekrar döngüsüne girmez. Aynı kayıt alanında tek çalıştırıcı çalışır; çakışan yeni işler sırada korunur. Kalıcı kayıt, bilgisayar kapalıyken çalışma anlamına gelmez; otomatik sunucu hizmeti henüz yoktur.

`--queue` ile `--check` birlikte kullanılamaz. Sıradaki aramalar tamamlandıktan sonra `./xti findings check` çalıştır. Hedef kontrolleri de aynı yerel çalıştırma kilidini kullanır; tarama veya başka kontrol sürerken ikinci kontrol başlamaz.

## Bulguyu inceleme ve karar

Listede görülen kimliği aşağıdaki `BULGU_KIMLIGI` yerine yaz:

```sh
./xti findings show BULGU_KIMLIGI
./xti findings review BULGU_KIMLIGI --decision uncertain --reason "Ek inceleme gerekiyor"
./xti findings list --status uncertain
```

Kararlar: `suspicious` = şüpheli, `dismissed` = normal/kapatıldı, `uncertain` = emin değilim. Gerekçe zorunludur. Her karar geçmişe eklenir. Bu kararlar otomatik engelleme veya dışarıya bildirim göndermez.

Aynı internet kaydını yeniden görmek bulguyu çoğaltmaz. Aynı aday ikinci kaynakta bulunursa yeni kaynak bilgisi mevcut bulguya bağlanır; verdiğin karar korunur. Ayrıntıda sertifika veya web inceleme bağlantısı, kaynakta görülen asıl ad ve varsa kaynak zamanı görünür. Kaynak zamanı domainin açıldığı tarih değildir. Wildcard (`*.`) kaydı belirli bir sitenin var olduğunu; eski web incelemesi sitenin bugün erişilebilir olduğunu kanıtlamaz.

## Meşru tam adresi istisna yap

Bir bulguyu doğrulayıp bunun meşru bir iş ortağı, kampanya veya kendi test adresin olduğuna karar verdiysen bulgu kimliğiyle istisna ekleyebilirsin:

```sh
./xti allowlist add-finding BULGU_KIMLIGI --reason "Doğrulanmış iş ortağı"
./xti allowlist add-finding BULGU_KIMLIGI --reason "30 günlük kampanya" --expires-in-days 30
./xti allowlist list
```

`--expires-in-days` verilmezse istisna kalıcıdır; verilirse 1–3650 gün arasında olmalıdır. Terminal kesin UTC bitiş zamanını gösterir. Tam o anda kayıt artık etkin sayılmaz; bunu yapmak için arka planda çalışan bir zamanlayıcı veya veritabanına gizli yazma gerekmez.

Bu işlem mevcut bulguyu, kanıtlarını, kararını veya bildirimini silmez. Sonraki aramalarda aynı **tam adres** aynı izlenen varlık için görülürse ham gözlem saklanır; yeni bulgu, kanıt bağlantısı ve bildirim üretilmez. `*.example.net` gibi joker karakterler ve ilgisiz/geniş istisnalar kabul edilmez. Aynı aday başka bir izlenen varlıkla eşleşiyorsa o varlık için ayrıca değerlendirilir.

Henüz bulgu oluşmadan da tam adres eklenebilir; adresin mevcut eşleştirme kurallarında seçilen varlık için aday olması gerekir:

```sh
./xti allowlist add markam.com markam-destek.net --reason "Bize ait kampanya adresi" --expires-in-days 90
```

İşlem geçmişini açmak veya istisnayı geri almak için:

```sh
./xti allowlist show ISTISNA_KIMLIGI
./xti allowlist revoke ISTISNA_KIMLIGI --reason "Artık bize ait değil"
./xti allowlist list --all
```

Geri alma geçmişi silmez. `list --all`, süresi dolmuş kayıtları da gösterir; süre değişikliği, yeniden etkinleştirme ve geri alma aynı kimliğin silinmeyen geçmişine eklenir. Süre dolması tek başına yeni bulgu yazmaz. Adres daha sonra yeniden görülürse veya aynı saklanmış gözlem yeniden işlenirse tekrar aday olabilir. İstisna zararsızlık kanıtı ya da alan adı sahipliği doğrulaması değildir; gerekçeyi senin doğrulamana dayanarak kaydeder.

## Alt alan adlarını pasif kaynaklarda bul

Önce kök adresi kaydet. Varsayılan crt.sh sertifika kaynağını doğrudan
kullanabilir veya isteğe bağlı ikinci arşiv kaynağını bir kez kurabilirsin:

```sh
./scripts/setup-harvester
```

Bu kurulum için ücretsiz `git` ve `uv` gerekir. Betik önce PATH'teki `uv`
aracını, yoksa proje içindeki `.tools/uv/bin/uv` kurulumunu kullanır. `uv`
kendiliğinden indirilmez; kurulum seçenekleri [resmî belgede](https://docs.astral.sh/uv/getting-started/installation/)
anlatılır. Python ve önbellek varsayılan olarak proje içindeki `.tools`
alanında tutulur; açıkça verilmiş `UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR` ve
`UV_PYTHON_BIN_DIR` değerleri korunur. theHarvester ayrı Python 3.14 ortamına,
resmî deponun incelenmiş tam commit'inden ve kilitli bağımlılıklarıyla kurulur;
kodu XTI çekirdeğine kopyalanmaz. Sağlıklı kurulumu tekrar çalıştırmak indirme
yapmaz. Kurulum kontrolü ve kesintiden kurtarma için:

```sh
./scripts/setup-harvester --check
./scripts/setup-harvester --recover
```

Yeni kurulum başarısız olursa önceki ortam geri getirilir; ani kesinti
sonrasında `--recover` kullanılır. Önceki ve başarısız ortamlar otomatik
silinmez. [Kurulum ve kurtarma rehberi](docs/HARVESTER_INSTALLATION.md)
`--force`, eşzamanlı çalışma ve disk kullanımını açıklar.
Ardından yalnız kayıtlı kökün altındaki adları ara:

```sh
./xti assets add markam.com
./xti surface discover markam.com
./xti surface discover markam.com --source theharvester
./xti surface watch markam.com --cycles 3 --interval 3600 --duration 86400
./xti surface watch markam.com --source theharvester --cycles 3 --interval 3600 --duration 86400
./xti surface candidates markam.com
./xti surface runs markam.com
./xti surface discovery-health markam.com
```

`discover` varsayılan olarak crt.sh sertifika kayıtlarını sorgular.
`--source theharvester` yalnız Common Crawl ve Wayback Archive P0 arşivlerini
kullanır. Bulunan `vpn.markam.com` veya `api.markam.com` gibi kesin alt alan
adlarını sağlayıcı ve arşiv kaynağı ayrı kalacak biçimde saklar. Kök adres,
ilgisiz ad, e-posta, kişi, IP ve başka sonuç türleri alınmaz. DNS çözümleme,
ekran görüntüsü, takeover veya hedefe doğrudan bağlantı açılmaz.

Arşiv v3 profili, kurulu theHarvester'ın ayrıştırma yardımcılarını ayrı süreçte
kullanır; üçüncü taraf kaynak dosyalarını değiştirmez. Wayback tek domain
sorgusunu küçük sayfalar ve devam anahtarıyla yürütür. Common Crawl aynı sayfanın
kalanını atlamadan okur. Common Crawl için 150, Wayback için 90 saniye ve
kaynak başına en çok 30 istek ayrılır. Common Crawl'da her yanıtın ardından
en az bir saniye beklenir; bağlantı hatasında kalan bütçe yeterliyse tek
tekrar 60 saniye sonra yapılır. Sınırda kalan çalışma kısmi gösterilir.
HTTP, TLS, zaman aşımı ve bağlantı kesilmesi
gerçek boş yanıttan ayrılır. 429/503 durumlarında anında tekrar yapılmaz;
sağlayıcının erişimi, tamamlanan yerel kurulumdan bağımsızdır.

Aynı ad iki arşivde görülürse tek aday ve iki ayrı kaynak kanıtı oluşur; ekranda
yalnız yanıltıcı bir “2 aynı kayıt” sayısı gösterilmez. Aynı kanıt yeniden
görülürse kayıt çoğalmaz. İlk kez bulunan aday yerel bildirim kutusuna bir kez
eklenir; sonraki keşifler bildirimi çoğaltmaz veya okundu durumunu sıfırlamaz.
Arşivde görülmek sahiplik, güncel erişilebilirlik veya risk kanıtı değildir.

Her keşif tamamlandı, kısmi veya başarısız sonucuyla geçmişe yazılır. Kaynak kesintisi boş ve başarılı sonuç sayılmaz:

```sh
./xti surface runs markam.com
./xti surface run CALISMA_KIMLIGI
```

Bu iki komut salt okunurdur. Adaylar, kaynak kanıtları, yeni bildirimler ve başarılı çalışma özeti birlikte kaydedilir; kayıt işlemi yarıda kalırsa hiçbiri kısmen yayımlanmaz.

Son pasif keşfin gerçekten boş mu, eksik mi, yoksa kaynak hatası mı olduğunu tek ekranda görmek için:

```sh
./xti surface discovery-status markam.com
./xti surface discovery-status markam.com --source crt.sh
./xti surface discovery-status markam.com --source theharvester
./xti surface discovery-status markam.com --stale-after-hours 72
./xti surface discovery-health markam.com
```

`discovery-status` varsayılan olarak en son pasif çalışmayı gösterir; `--source` ile tek sağlayıcının son kaydı seçilir. `discovery-health` ise crt.sh ve theHarvester satırlarını aynı ekranda ama ayrı sonuçlar olarak gösterir. Birinin tamamlanması diğerinin hatasını gizlemez.

`Kaynak çalıştı` ve `Aday görülmedi` birlikte görünüyorsa seçilen sorgu tamamlanmış, o kaynak yanıtında aday bulunmamıştır. `Kaynak sonucu eksik` veya `Kaynak çalışmadı` durumunda aday görülmemesi boş sonuç sayılmaz; veri sonucu `Bilinmiyor` ya da eksik kapsam olarak açıklanır. Hiç çalışma yoksa bu da ayrı gösterilir.

Güncellik varsayılan 24 saatlik rapor eşiğiyle ayrıca gösterilir. Eski tamamlanmış boş sonuç geçmişte geçerli olsa da bugünkü durumu anlatmayabilir. Bu komutlar yalnız kayıtlı çalışma geçmişini okur; crt.sh'ye, arşivlere veya bulunan hedeflere bağlanmaz, yeni çalışma başlatmaz ve veritabanını değiştirmez. “Güncel kayıt”, kaynağın şu anda canlı olduğunu kanıtlamaz. Tamamlanmış boş yanıt da internette hiç alt alan adı veya risk olmadığını göstermez.

`surface watch`, aynı pasif keşfi terminal açıkken sınırlı biçimde tekrarlar. `--cycles` en fazla turu, `--interval` tamamlanan iki tur arasındaki beklemeyi, `--duration` ise yeni bir tur başlatılabilecek toplam süreyi belirler. Varsayılanlar 3 tur, 3600 saniye ve 86400 saniyedir. Kaynak hatası bir turu başarısız olarak geçmişe yazar; bütçe varsa izleme sonraki turda yeniden dener.

Her tamamlanan tur `surface runs` geçmişinde kalır. `Ctrl+C` izlemeyi durdurur; daha önce tamamlanan turlar, adaylar ve bildirimler korunur. Bilgisayar veya terminal kapalıyken kendiliğinden çalışmaz ve yeniden açıldığında yarım turu sürdürmez. Aynı aday yeniden görülürse yeni bildirim oluşturulmaz. İzleme bulunan adlara bağlanmaz, sahiplik kararı vermez ve aktif kontrol kapsamı açmaz.

Bir adayın ayrıntısını açıp kararını kaydedebilirsin:

```sh
./xti surface candidate show ADAY_KIMLIGI
./xti surface candidate decide ADAY_KIMLIGI --status owned --reason "Kurumsal VPN adresimiz"
./xti surface candidate decide ADAY_KIMLIGI --status rejected --reason "Bize ait değil"
./xti surface candidates markam.com --status all
```

Durumlar `pending` (onay bekliyor), `owned` (bana ait) ve `rejected` (reddedildi) biçimindedir. Karar ve gerekçe geçmişi silinmez; sonraki keşif sahiplik kararını sıfırlamaz. Liste ve ayrıntı komutları internete çıkmaz.

Bu işlem tamamen pasiftir: bulunan alt alan adına DNS, TLS veya web isteği göndermez ve onu aktif kapsama almaz. `owned` kararı da tek başına bağlantı izni değildir. Aktif kontrol istersen adayı ayrıca kaydedip gerekçeli kapsam onayı vermen gerekir:

```sh
./xti assets add vpn.markam.com
./xti surface approve vpn.markam.com --reason "Yönetmeye yetkili olduğum kurumsal VPN"
./xti surface check vpn.markam.com
```

Bu dört ayrı katmanın güncel durumunu tek ekranda karşılaştırmak için:

```sh
./xti surface inventory markam.com
./xti surface inventory markam.com --status owned --limit 50
```

`surface inventory`, köke bağlı her pasif aday için aday kararını, adresin ayrıca kayıtlı bir varlık olup olmadığını ve aktif kontrol kapsamının bulunup bulunmadığını ayrı ayrı gösterir. Örneğin bir adres `Bana ait` seçilmiş fakat henüz varlık olarak kaydedilmemiş olabilir; başka bir adres kayıtlı olsa da aktif kontrol izni verilmemiş olabilir. Çıktı sonraki güvenli adımı önerir fakat hiçbir adımı kendi başına uygulamaz.

Komut internete bağlanmaz, yeni keşif veya kontrol başlatmaz, sahiplik kararı vermez ve veritabanını değiştirmez. `owned`, `assets add` ve `surface approve` birbirinin yerine geçmez. Aktif kapsam da teknik sahiplik doğrulaması değil, kullanıcının açık yetki beyanıdır.

## Kendi DNS/TLS dış yüzeyini izle

Bu bölüm yalnız kontrol etmeye yetkili olduğun kendi adreslerin içindir. Önce adresi kaydet, sonra neden yetkili olduğunu açıkça beyan ederek dış yüzey kapsamına al:

```sh
./xti assets add markam.com
./xti surface approve markam.com --reason "Kendi kurumsal alan adım"
./xti surface check markam.com
```

İlk kontrol DNS adreslerini, doğrulanmış TLS/HTTPS durumunu ve sunucunun doğrulanmış sertifika kimliğini temel kayıt olarak saklar. Sertifikanın veren kurumu, konusu, seri numarası, SHA-256 parmak izi, başlangıç/bitiş zamanı ve kapsadığı DNS adları gösterilir. Bitişe 30 gün veya daha az kaldığında terminal uyarır.

Sonraki kontroller aynı durumu yeniden görürse “Değişiklik yok”; IP, DNS, TLS, HTTPS veya sertifika kimliği farklıysa eklenen/çıkan IP ve değişen alanlar gösterilir. Sertifika yenilenmesi ayrı değişikliktir. Her kontrol ayrı kanıt olarak korunur.

```sh
./xti surface list
./xti surface show markam.com
./xti surface show markam.com --history-limit 50
```

`list` ve `show` internete bağlanmaz ve kaydı değiştirmez. Aktif kontrol yetkisini geri almak için:

```sh
./xti surface revoke markam.com --reason "Bu adresi artık yönetmiyorum"
./xti surface list --all
```

Kapsam onayı teknik sahiplik doğrulaması değil, senin kayıtlı yetki beyanındır. `surface check` yalnız açıkça onaylanan tam adresi kontrol eder; pasif adaylara veya başka alt alanlara genişlemez, port taramaz, sayfa içeriği indirmez, yönlendirme izlemez veya zafiyet sömürmez. Google Public DNS'e A/AAAA sorgusu gönderir; yalnız genel IP görülürse 443 üzerinde doğrulanmış TLS ve `HEAD /` kullanır. Özel/yerel IP'ye ve doğrulamasız TLS bağlantısına devam etmez.

DNS/TLS sonucu güvenlik, sahiplik veya zafiyet kararı değildir. Örneğin geçerli TLS sertifikası sitenin güvenli olduğunu; DNS hatası alan adının kapandığını kanıtlamaz. Sertifika bitiş uyarısı operasyonel hatırlatmadır, saldırı tespiti değildir. Pasif keşif yalnız seçilen crt.sh veya theHarvester Common Crawl/Wayback arşivinin görebildiği kayıtlarla sınırlıdır; arka plan servisi/takvim zamanlaması, tam DNS ve tam servis envanteri henüz yoktur.

## Kendi e-posta DNS kayıtlarını izle

Aynı onaylı kökün internette görünen MX, SPF ve DMARC kayıtlarını temel alıp sonraki kontrollerde değişikliği görebilirsin:

```sh
./xti surface mail check markam.com
./xti surface mail show markam.com
./xti surface mail show markam.com --history-limit 50
```

`check`, Google Public DNS'e tam olarak üç sınırlı sorgu gönderir: kökte MX, kökte TXT içinden yalnız `v=spf1` ve `_dmarc.markam.com` TXT içinden yalnız `v=DMARC1`. Tek sorgu tamamlanamazsa diğer iki sonuç saklanır, çalışma kısmi görünür ve çıkış kodu 3 olur. Kayıt bulunmaması tamamlanmış bir DNS gözlemidir; tek başına hata veya güvenlik kararı değildir. `show` yalnız yerel geçmişi okur ve internete çıkmaz.

DKIM seçici adı bilinmeden bulunamaz; program seçici tahmin etmez ve rastgele alt adlara sorgu göndermez. Birden fazla SPF/DMARC kaydı görülürse bunları kanıt olarak gösterir fakat otomatik “hatalı/güvenli” hükmü vermez. Bu görünüm e-posta teslim garantisi, sahiplik kanıtı veya kapsamlı e-posta güvenliği denetimi değildir.

Bu adım için ücretli API anahtarı veya ek Python paketi gerekmez. Google Public DNS harici bir kamu hizmetidir; erişilebilirliği ve kullanım koşulları XTI'nin kontrolünde değildir. Kontrol yalnız sen komutu çalıştırdığında yapılır; arka planda kendiliğinden tekrarlanmaz.

## Kendi sunucundaki sınırlı TCP servislerini izle

Bu bölüm yalnız yönetmeye yetkili olduğun kesin genel IP adresleri içindir. Domain kapsamı etkin olmalı; ayrıca kontrol edilecek IP'yi ve yetki gerekçeni her çalıştırmada açıkça yazmalısın:

```sh
./xti surface services check markam.com \
  --address 93.184.216.34 \
  --reason "Yönettiğim kurumsal sunucunun sabit genel IP adresi"

./xti surface services show markam.com
```

Program önce yazdığın IP'nin o anda `markam.com` DNS cevabında bulunduğunu doğrular. IP cevapta yoksa veya DNS cevabında özel/yerel adres varsa hiçbir hedef portuna bağlanmaz. Yalnız yazdığın tek IP kontrol edilir; DNS'teki diğer adreslere kendiliğinden genişlemez.

İlk sürümde sabit olarak `22, 25, 53, 80, 443, 587, 993, 3389, 8080 ve 8443/tcp` kontrol edilir. Her porta yalnız kısa bir TCP bağlantısı denenir. Banner, sayfa, ürün adı, sürüm, parola veya başka veri alınmaz; karşı tarafa uygulama verisi gönderilmez. Kullanıcı özel port aralığı veremez.

Sonuçlar `Açık`, `Kapalı` veya `Belirsiz` olur. Belirsiz sonuç kapalı sayılmaz. Port yanındaki “SSH adayı” veya “HTTPS adayı” ifadesi yalnız yaygın port kullanımını anlatır; o ürünün gerçekten çalıştığını kanıtlamaz. Açık port da zafiyet, saldırı veya sahiplik kararı değildir.

Her kontrol önceki kanıtı silmeden kaydedilir. Sonraki çalışmada port durumu değişirse önceki ve yeni durum gösterilir. `surface services show` internete bağlanmaz. Kontrol ücretli API, nmap, masscan veya ek Python paketi kullanmaz; Python'un sınırlı ağ bağlantısıyla çalışır.

## Yetkili sunucularda ayarlanabilir Nmap TCP kanıtı

Daha geniş veya özel bir TCP port kapsamı gerektiğinde Nmap ayrı bir aktif
kanıt sağlayıcısıdır. Önce işletim sistemi aracını tek komutla kurup doğrula:

```sh
./scripts/setup-nmap
./xti surface nmap readiness
```

macOS'ta Homebrew, Linux'ta desteklenen sistem paket yöneticisi kullanılır.
Nmap repoya kopyalanmaz; Python bağımlılığı değildir. XTI yalnız doğrulanmış
Nmap 7.x ailesini, `-sT -Pn -n --unprivileged` profilinde çalıştırır.

Varsayılan güvenli profil mevcut 10 TCP portunu Nmap ile kontrol eder:

```sh
./xti surface nmap check markam.com \
  --address 93.184.216.34 \
  --reason "Yönettiğim kurumsal sunucunun kesin genel IP adresi"

./xti surface nmap show markam.com
```

Süre ve trafik temposu özelleştirilebilir:

```sh
./xti surface nmap check markam.com \
  --address 93.184.216.34 \
  --reason "Yönettiğim kurumsal sunucu" \
  --profile custom --ports 22,80,443,8000-8100 \
  --timeout-seconds 180 --max-rate 40 --max-retries 1 \
  --target-limit 1 --max-probes 500
```

Profiller `safe`, `extended` (`1-1024`), `full` (`1-65535`) ve `custom`dır.
1024 porttan geniş kapsam ayrıca `--confirm-wide-scan` ister. Birden fazla
kesin IP, tekrarlanan `--address` ile verilir; `--target-limit` yanında
`--confirm-multi-target` da zorunludur. En fazla 16 IP kabul edilir. CIDR,
IP aralığı, hostname hedefi ve ham Nmap argümanı bu doğrudan `check` komutunda
kabul edilmez.

`--max-rate` Nmap'in paket/saniye tavanıdır; kesin byte kotası değildir.
`--max-probes`, `port × hedef × (yeniden deneme + 1)` planının kabul sınırıdır.
Her hedef yine güncel domain DNS cevabında bulunmalı ve bütün DNS adresleri
genel IP olmalıdır. Plan ve kullanılan bütün sınırlar sonuçla birlikte
eklemeli kaydedilir.

Bu katman UDP, SYN/root taraması, NSE, `-sV`, banner, işletim sistemi keşfi,
ürün/sürüm veya CVE sonucu üretmez. Nmap kanıtı mevcut hafif servis
kanıtından ayrı tutulur; `surface overview`, teknoloji ipuçları ve alarm
mantığına kendiliğinden karışmaz. Açık port yalnız o andaki TCP
erişilebilirliğidir.

Kurumsal kullanıma hazırlanacak adlandırılmış IP/CIDR kapsamını ve bütün
sınırları ağ bağlantısı kurmadan kaydetmek için:

```sh
./xti surface nmap targets save markam.com production \
  --network "YETKILI_GENEL_IP_VEYA_CIDR" \
  --reason "Yönettiğimiz kurumsal genel IP aralığı"

./xti surface nmap targets show markam.com production

./xti surface nmap plans create markam.com \
  --target production --profile custom --ports 22,80,443,8000-8100 \
  --timeout-seconds 180 --max-rate 40 --max-retries 1 \
  --scan-delay-ms 25 --max-parallelism 16 --max-hostgroup 8 \
  --max-targets 14 --max-probes 5000

./xti surface nmap plans list markam.com
```

`targets save` yalnız kanonik kesin genel IP veya en fazla 4096 adreslik
genel CIDR kabul eder. Kapsamdaki her adres doğrulanır; özel/yerel/ayrılmış
adres içeren bütün aralık reddedilir. Hariç tutmalar ana kapsam içinde olmalı
ve kapsamın tamamını kaldıramaz. Hedef güncellemeleri ve geri çekmeleri
eklemeli geçmişte kalır.

`plans create` hedef kapsamının o anki sürümünü, gerçek hedef sayısını,
portları ve tüm işletim sınırlarını SHA-256 kimlikli değiştirilemez bir
dry-run kaydında dondurur; Nmap çalıştırmaz. 16'dan fazla hedef ayrıca
`--confirm-range-scan`, 1024'ten fazla port `--confirm-wide-scan` ister.
`YETKILI_GENEL_IP_VEYA_CIDR` yer tutucusunu kendi yetkili adresinle değiştir.
Eski `surface nmap check` küçük ve DNS'e sabit kesin-IP kontrolleri içindir.
Yönetilen planı çalıştırmak için:

```sh
./xti surface nmap jobs submit markam.com PLAN_KIMLIGI --request-key kontrol-001
./xti surface nmap jobs worker markam.com IS_KIMLIGI
./xti surface nmap jobs show markam.com IS_KIMLIGI
./xti surface nmap jobs cancel markam.com IS_KIMLIGI
```

`plans create` ayrıca `--scan-type tcp_connect|tcp_syn|udp`,
`--service-detection`, `--version-intensity`, `--os-detection`,
`--script`, `--script-timeout-seconds`, `--max-duration-seconds` alır.
UDP açık custom port seçimi ister. `./xti --json surface nmap capabilities`
arayüzün okuyabileceği seçenek kataloğudur.
[Gelişmiş kullanım, sonuç anlamı ve kurtarma](docs/NMAP_MANAGED.md).

## Seçili dış yüzey kontrollerini terminal açıkken tekrarla

Web ve e-posta DNS kontrollerini tek komutla sınırlı olarak tekrarlamak için:

```sh
./xti surface monitor markam.com \
  --checks web mail \
  --cycles 3 --interval 3600 --duration 86400
```

`--checks` yazılmazsa `web mail` kullanılır. `web`, onaylı DNS/TLS/HTTPS kontrolünü; `mail`, MX/SPF/DMARC kontrolünü çalıştırır. Kesin IP'ye sınırlı servis kontrolünü de eklemek istersen IP ve yetki gerekçesi açıkça verilmelidir:

```sh
./xti surface monitor markam.com \
  --checks web mail services \
  --service-address 93.184.216.34 \
  --service-reason "Yönettiğim kurumsal sunucunun sabit genel IP adresi" \
  --cycles 3 --interval 3600 --duration 86400
```

`--cycles` en fazla turu, `--interval` tamamlanmış iki tur arasındaki beklemeyi, `--duration` ise yeni bir kontrol başlatılabilecek toplam süreyi sınırlar. Kabul edilen değerler sırasıyla 1–1000 tur, 300–86400 saniye aralık ve 1–604800 saniye süredir. Varsayılanlar 3 tur, 3600 saniye ve 86400 saniyedir.

Komut ön planda çalışır. Terminal kapanırsa veya `Ctrl+C` kullanılırsa izleme durur; daha önce tamamlanmış DNS/TLS, posta veya servis kanıtları ve oluşan bildirimler korunur. Bilgisayar kapalıyken çalışmaz, yeniden açıldığında kaldığı yerden devam etmez ve ayrı bir arka plan servisi kurmaz. Her gerçek değişiklik mevcut `./xti inbox` kutusuna düşer; ilk temel kayıt ve değişmeyen tekrar alarm değildir.

Tek terminal özeti oturumun kaç tam tur ve kontrol bitirdiğini gösterir. Oturumun kendisi için yeni kalıcı çalışma tablosu yoktur; ayrıntılı kalıcı geçmiş mevcut `surface show`, `surface mail show`, `surface services show`, `surface overview` ve `inbox` komutlarındadır. Seçilen bütün kontroller aynı etkin `surface approve` kapsamını kullanır. `services` seçimi mevcut kesin genel IP, DNS eşleşmesi ve görünür yetki gerekçesi güvenlik kapılarını değiştirmez.

## Dış yüzey kanıtlarının güncelliğini gör

Kayıtlı web, posta ve servis kanıtlarının yaşını tek ekranda görmek için:

```sh
./xti surface freshness markam.com
./xti surface freshness markam.com --stale-after-hours 72
```

Varsayılan eşik 24 saattir; 1–8760 saat arasında değiştirilebilir. Her kanıt ailesi ayrı olarak `Güncel`, `Eski`, `Henüz kontrol edilmedi` veya `Zaman bilgisi tutarsız` görünür. Son kontrolün tam, kısmi veya başarısız olması kanıt yaşından ayrı gösterilir. Örneğin yeni fakat kısmi bir posta kontrolü “güncel” olabilir; buna rağmen eksik sorgusu ayrıca açıklanır.

Komut internete bağlanmaz, yeni kontrol başlatmaz ve veritabanını değiştirmez. Etkin kapsamı, son web DNS/TLS/HTTPS kanıtını, son MX/SPF/DMARC kanıtını ve son sınırlı TCP servis kanıtını tek SQLite okuma anlık görüntüsünden alır. Eski veya hiç alınmamış kanıt tek başına saldırı, kesinti ya da güvenlik açığı kararı değildir. Yeni kanıt almak için `surface monitor` veya ilgili tek kontrol komutu açıkça çalıştırılmalıdır.

## CNAME hedefini güvenli biçimde izle

Bu kontrol yalnız kayıtlı ve etkin dış yüzey kapsamındaki tam adres içindir. Pasif bulunan bir alt alan adına otomatik uygulanmaz; önce adresin sana ait olduğunu değerlendirip ayrı varlık ve kapsam olarak açıkça kaydetmelisin:

```sh
./xti assets add api.markam.com
./xti surface approve api.markam.com --reason "Yönettiğim kurumsal API adresi"
./xti surface cname check api.markam.com
./xti surface cname show api.markam.com
```

`check`, Google Public DNS üzerinden yalnız tam adresin CNAME kaydını ve varsa zincirin terminal hedefi için A/AAAA durumunu alır. En fazla sekiz CNAME adımı ve 16 IP saklanır. İlgisiz, çelişen, döngülü, kesilmiş veya beklenmeyen DNS yanıtı başarılı boş sonuç sayılmaz. İlk kanıt temel kayıt, tekrar aynı durum değişiklik yok, zincir/hedef/IP farkı değişiklik olarak eklemeli geçmişe yazılır.

CNAME hedefi NXDOMAIN döndürürse `surface exposures` bunu “sarkan CNAME hedefi adayı” olarak gösterir. Bu yalnız hedef adın o genel DNS görünümünde bulunmadığı anlamına gelir; üçüncü taraf kaynağın alınabilir olduğunu veya gerçek bir takeover bulunduğunu kanıtlamaz. Özel DNS görünümü, geçici kesinti, sağlayıcı hesabı ve hizmet sahipliği ayrıca insan tarafından doğrulanmalıdır.

Program hedef siteye bağlanmaz, HTTP isteği veya banner almaz, sağlayıcı hesabı açmaz, kaynağı sahiplenmez, oturum açmayı ya da exploit'i denemez ve DNS kaydını otomatik değiştirmez. `show` yalnız kayıtlı geçmişi okur. Google Public DNS harici ücretsiz bir hizmettir; erişimi ve koşulları XTI tarafından garanti edilmez.

## Kayıtlı kanıttan maruziyet adaylarını gör

Son web, posta ve sınırlı servis kanıtlarını incelenebilir adaylara dönüştürmek için:

```sh
./xti surface exposures markam.com
./xti surface exposures markam.com --stale-after-hours 72
```

Bu ekran artık pasif alt alan adı keşfi, web, e-posta, sınırlı servis ve CNAME kanıtlarını birlikte gösterir. Her bölüm `Güncel ve tam`, `Kontrol edilmedi`, `Eski kanıt`, `Kısmi kanıt`, `Başarısız kontrol` veya `Zaman bilgisi tutarsız` olarak ayrılır. İlgi isteyen bölümün altında çalıştırılabilecek tam terminal komutu bulunur. Aktif kontroller için kapsam onayı yoksa önce `surface approve` komutu ayrıca gösterilir. Servis komutundaki `GENEL_IP` yerine yalnız yönettiğin ve kontrol iznin bulunan kesin genel IP yazılmalıdır.

Pasif keşifte sıfır aday tek başına başarı değildir. Kaynak sorgusu tamamlandıysa “yalnız bu kaynak yanıtında aday görülmedi” denir; kısmi veya başarısız çalışmada boş sonuç doğrulanmış sayılmaz. Komutlar yalnız öneridir: `surface exposures` bunları kendiliğinden çalıştırmaz.

İlk kurallar tamamlanamayan TLS bağlantısı/doğrulamasını, MX kullanan bir domainde görülmeyen veya birden çok görülen SPF/DMARC kaydını, `22`, `3389`, `8080`, `8443/tcp` üzerinde gözlenen bağlantı kabulünü ve CNAME hedefinin NXDOMAIN olmasını açıklar. Her aday kanıt kimliği/zamanı, güncellik durumu, doğrudan olgular, neyi kanıtlamadığı ve sonraki insan adımıyla gösterilir. Eski veya zamanı tutarsız kanıt güncelmiş gibi sunulmaz.

Bu komut “zafiyet bulundu” demez. Açık TCP portu çalışan ürün, yönetim paneli veya CVE kanıtı değildir; TLS başarısızlığı da tek başına sertifika hatası veya kesinti değildir. Null MX (`0 .`) görülen bir domain için eksik SPF/DMARC adayı üretilmez. Eksik kayıt gözlemi kurum politikasının yanlış olduğunu otomatik kanıtlamaz.

Sayfa gövdesi, başlık ve banner toplanmadığı için açık panel kimliği hâlâ “henüz desteklenmiyor” görünür. CNAME/NXDOMAIN yalnız sağlayıcıdan bağımsız bir ön adaydır; delegasyon ve sağlayıcıya özgü alınabilirlik doğrulaması yoktur. Böylece veri eksikliği güvenli sonuç gibi gösterilmez. `surface exposures` internete bağlanmaz, sahiplenme/exploit yapmaz, yeni bulgu kaydetmez ve veritabanını değiştirmez.

## Teknoloji ve ürün ipuçlarını gör

Son sınırlı servis kontrolündeki açık portları, yanlış ürün veya sürüm iddiası üretmeden görmek için:

```sh
./xti surface technologies markam.com
./xti surface technologies markam.com --stale-after-hours 72
```

Örneğin `22/tcp` açık görülürse çıktı yalnız “SSH adayı” der. Üretici, ürün ve sürüm bilinmiyor olarak kalır; banner okunmadığı ve protokol konuşulmadığı için bu kayıt CVE eşleştirmesine uygun değildir. Aynı ilke `80`, `443`, `3389`, `8080` ve diğer sabit portlar için de geçerlidir. Port numarası, o portta gerçekten hangi yazılımın çalıştığını kanıtlamaz.

Komut yalnız son kayıtlı servis kanıtını okur; internete bağlanmaz, yeni port kontrolü yapmaz ve veritabanını değiştirmez. Kontrol edilmemiş, başarısız, kısmi, eski ve zamanı tutarsız kanıt ayrı görünür. Kapalı veya belirsiz porttan ürünün bulunmadığı sonucu çıkarılmaz. Aşağıdaki doğrulanmış ürün kaydı ayrı ve açık bir kullanıcı işlemidir.

## Varlığın senin için iş önemini kaydet

Bir varlığın iş açısından önemini yalnız sen belirleyebilirsin. Kayıtlı domaine açık bir seviye ve gerekçe bağlamak için:

```sh
./xti assets criticality-set markam.com --level critical --reason "Müşteri girişlerinin bağlı olduğu ana üretim hizmeti"
./xti assets criticality-show markam.com
./xti assets criticality-clear markam.com --reason "Varlık üretim görevinden çıkarıldı"
```

Seviyeler `low`, `medium`, `high` ve `critical` değerleridir. Her değişiklik ve kaldırma geçmişte korunur; aynı kararın tekrarı yeni olay üretmez. Bu kayıt insan beyanıdır: ürün, zafiyet, sahiplik veya internet erişimi kanıtı değildir.

`vuln exposure-queue`, bu beyanı son kayıtlı web ve izinli servis kanıtıyla birlikte gösterir. Güncel doğrulanmış HTTPS yanıtı veya güncel açık izinli TCP portu “internet erişimi doğrulandı” bağlamı verir. Yalnız DNS görünmesi ayrı kalır. Kapsam yoksa, hiç kontrol edilmediyse veya kanıt eskiyse durum bilinmiyor gösterilir; erişimin doğrulanamaması güvenli ya da internete kapalı anlamına gelmez. Kuyruk bu görünüm sırasında internete bağlanmaz ve yeni kontrol başlatmaz.

## Doğrulanmış ürün ve sürüm kanıtını yönet

Kayıtlı bir varlıkta üretici, ürün ve kesin sürümü gerçekten doğruladıysan bunu kanıt açıklamasıyla kaydedebilirsin:

```sh
./xti products add markam.com --part a --vendor apache --product http_server --version 2.4.58 --evidence "Paket yöneticisi çıktısında doğrulandı"
./xti products list markam.com
./xti products show URUN_KIMLIGI
./xti products revoke URUN_KIMLIGI --reason "Paket kaldırıldı ve elle doğrulandı"
./xti products list --all
```

`--part` için `a` uygulama, `o` işletim sistemi, `h` donanım demektir. Üretici ve ürün küçük harfli CPE adlarıyla, sürüm ise joker olmayan açık değerle kaydedilir. Aynı varlık+ürün+sürüm ikinci kez çoğalmaz; kanıt değişikliği, kaldırma ve yeniden etkinleştirme geçmişte korunur.

Bu kayıt port taramasından, teknoloji ipucundan veya NVD'den otomatik oluşmaz. Kullanıcı doğrulaması da ürünün hâlâ çalıştığını, internete açık olduğunu veya zafiyet taşıdığını tek başına kanıtlamaz.

### Kesin Red Hat RPM paketini kaydet

Red Hat paketinin tam kimliğini ve hangi dağıtım bağlamında kurulu olduğunu doğruladıysan ayrı RPM envanterine ekleyebilirsin:

```sh
./xti packages add markam.com --name openssl --epoch 0 --version 1.0.1e --release 16.el6_5.7 --arch x86_64 --distribution-cpe cpe:/o:redhat:enterprise_linux:6::client --source-rpm openssl-1.0.1e-16.el6_5.7.src.rpm --evidence "rpm sorgusu ve işletim sistemi kaydı birlikte doğrulandı"
./xti packages list markam.com
./xti packages show PAKET_KIMLIGI
./xti packages revoke PAKET_KIMLIGI --reason "Paket kaldırıldı ve envanterden doğrulandı"
./xti packages list --all
```

Paket adı, epoch, sürüm, release, mimari ve Red Hat Enterprise Linux CPE'si zorunludur. Paket yöneticisi epoch için `(none)` gösteriyorsa `0` kullanılır. Kaynak RPM bilinmiyorsa `--source-rpm` verilmez; bilinmeyen değer uydurulmaz. Sistem PURL değerini bu alanlardan kendisi üretir ve serbest PURL kabul etmez.

Bu kayıt başka bir dağıtıma uygulanmaz ve tek başına `affected`, `fixed` veya `known_not_affected` sonucu değildir. Doğrudan karşılaştırma aşağıdaki `vuln vendor-match` komutuyla açıkça yapılır; sonuç yine üretici beyanıdır ve insan kararını değiştirmez.

## Bilinen istismar zafiyetlerini güncelle ve incele

Resmî CISA Known Exploited Vulnerabilities (KEV) kataloğunu doğrudan internetten almak için:

```sh
./xti vuln sync --source kev
./xti vuln status --source kev
./xti vuln list --source kev
./xti vuln show CVE-2026-1234 --source kev
```

`sync` yalnız açıkça çalıştırıldığında CISA'nın resmî JSON adresine bağlanır. Dosyayı senin vermen gerekmez; API anahtarı ve ücretli servis kullanılmaz. Yanıt boyutu, içerik türü, kayıt sayısı, yinelenen CVE'ler, tarihler ve alanlar bütün katalog kabul edilmeden önce doğrulanır.

Yeni, değişen, katalogdan çıkan ve yeniden eklenen kayıtların geçmişi korunur. CISA geçici olarak yanıt vermez veya bozuk veri döndürürse bu durum “katalog boş” sayılmaz; hata kaydedilir ve son geçerli katalog değiştirilmez. `status`, `list` ve `show` yalnız yerel veriyi okur, internete bağlanmaz.

KEV, bir CVE'nin gerçek saldırılarda istismar edildiği bilgisidir. Tek başına senin bilgisayarında veya domaininde o zafiyetin bulunduğunu kanıtlamaz. Ürün karşılaştırması ancak açıkça doğrulanmış ürün kaydıyla ve aşağıdaki ayrı komutla yapılır.

FIRST'ün günlük Exploit Prediction Scoring System (EPSS) kataloğunu almak için:

```sh
./xti vuln sync --source epss
./xti vuln status --source epss
./xti vuln list --source epss --limit 20
./xti vuln show CVE-2021-44228 --source epss
```

EPSS, bir CVE için önümüzdeki 30 gün içinde istismar gözlenme olasılığının nüfus düzeyindeki tahminidir. Önem, etki, tam risk veya senin varlığında zafiyet kanıtı değildir. Model sürümü, puan tarihi, olasılık ve yüzdelik dilim korunur. Tam günlük dosya kabul edilmeden önce gzip, UTF-8, metadata, başlık, satır sayısı, yinelenen CVE ve olasılık sınırları doğrulanır; hata olursa önceki katalog korunur.

Yerelde yalnız güncel EPSS puanı tutulur. Yaklaşık 397 bin kaydın günlük kopyalarını biriktirmek kişisel kullanımda gereksiz disk büyümesine yol açacağından her CVE için günlük geçmiş çoğaltılmaz; başarılı/başarısız kaynak çalışma geçmişi saklanır. `status`, `list` ve `show` internete bağlanmaz ve veritabanını değiştirmez.

NVD'nin açıklama ve CVSS bağlamını belirli bir CVE için almak istersen:

```sh
./xti vuln advisory-preview CVE-2014-0160
./xti vuln advisory-evidence-add INCELEME_KIMLIGI --type vendor_advisory --reference https://uretici.example/duyuru --summary "OSV önizlemesindeki duyuru insan tarafından seçildi"
./xti vuln vendor-preview CVE-2014-0160 --provider redhat
./xti vuln vendor-preview CVE-2014-0160 --provider suse
./xti vuln vendor-match PAKET_KIMLIGI CVE-2014-0160 --provider redhat
./xti vuln vendor-evidence-add INCELEME_KIMLIGI PAKET_KIMLIGI --vex-product-id 'VENDOR_MATCH_CIKTISINDAKI_TAM_KIMLIK' --summary "Kesin Red Hat ürün bağı insan tarafından seçildi"
./xti vuln vendor-evidence-list INCELEME_KIMLIGI
./xti vuln vendor-evidence-show KANIT_KIMLIGI
./xti vuln vendor-evidence-check KANIT_KIMLIGI
./xti vuln vendor-evidence-revoke KANIT_KIMLIGI --reason "Kanıt artık kullanılmıyor"
./xti vuln sync --source nvd --cve CVE-2021-44228
./xti vuln source-evaluation
./xti vuln ubuntu-preview CVE-2025-6491 --affected-limit 20 --reference-limit 20
./xti vuln ubuntu-match CVE-2025-6491 --ecosystem Ubuntu:24.04:LTS --source-package php8.3 --version 8.3.6-0ubuntu0.24.04.4
./xti ubuntu-packages add example.com --ecosystem Ubuntu:24.04:LTS --binary-package php8.3-cli --binary-version 8.3.6-0ubuntu0.24.04.4 --arch amd64 --source-package php8.3 --source-version 8.3.6-0ubuntu0.24.04.4 --evidence "dpkg-query ve apt-cache showsrc çıktıları birlikte doğrulandı"
./xti ubuntu-packages list example.com
./xti ubuntu-packages show UBUNTU_PAKET_KIMLIGI
./xti vuln ubuntu-inventory-match UBUNTU_PAKET_KIMLIGI CVE-2025-6491
./xti vuln ubuntu-inventory-scan CVE-2025-6491 --domain example.com --limit 50
./xti vuln ubuntu-evidence-add INCELEME_KIMLIGI UBUNTU_PAKET_KIMLIGI --summary "Canonical sonucu ve yerel source paket sürümü birlikte incelendi"
./xti vuln ubuntu-evidence-check KANIT_KIMLIGI
./xti vuln ubuntu-evidence-plan --domain example.com --limit 50
./xti vuln ubuntu-evidence-scan --domain example.com --limit 10
./xti ubuntu-packages revoke UBUNTU_PAKET_KIMLIGI --reason "Paket kaldırıldı ve envanterden doğrulandı"
./xti vuln status --source nvd
./xti vuln list --source nvd
./xti vuln show CVE-2021-44228 --source nvd
./xti vuln overview CVE-2021-44228
./xti vuln plan --min-epss 0.9 --limit 20
./xti vuln enrich-nvd --min-epss 0.9 --limit 3
./xti vuln tracked-nvd-plan --stale-after-hours 168
./xti vuln tracked-nvd-refresh --stale-after-hours 168 --limit 3
./xti vuln nvd-window-plan --start 2026-10-01T00:00:00Z --end 2026-10-02T00:00:00Z --page-size 20
./xti vuln nvd-window-fetch --start 2026-10-01T00:00:00Z --end 2026-10-02T00:00:00Z --page-size 20
./xti vuln nvd-window-list --status all
./xti vuln nvd-window-coverage --start 2026-10-01T00:00:00Z --end 2026-10-31T00:00:00Z
./xti vuln nvd-window-gap-plan --start 2026-10-01T00:00:00Z --end 2026-10-31T00:00:00Z --page-size 20 --limit 20
./xti vuln nvd-window-gap-fetch --start 2026-10-01T00:00:00Z --end 2026-10-31T00:00:00Z --page-size 20 --limit 2
./xti vuln nvd-window-operations --start 2026-10-01T00:00:00Z --end 2026-10-31T00:00:00Z --recent-limit 10
./xti vuln nvd-window-show --start 2026-10-01T00:00:00Z --end 2026-10-02T00:00:00Z --page-size 20
./xti vuln nvd-window-restart --start 2026-10-01T00:00:00Z --end 2026-10-02T00:00:00Z --page-size 20 --reason "Kaynak toplamı değişti; dönem baştan doğrulanacak"
./xti vuln applicability CVE-2014-0160 --limit 50
./xti vuln assess-product URUN_KIMLIGI CVE-2014-0160
./xti vuln asset-overview URUN_KIMLIGI CVE-2014-0160
./xti vuln match-products CVE-2014-0160
./xti vuln exposure-open URUN_KIMLIGI CVE-2014-0160 --reason "Ürün ve sürüm adayı incelenecek"
./xti vuln exposure-list
./xti vuln exposure-queue
./xti vuln reassessment-plan
./xti vuln reassessment-run
./xti vuln reassessment-runs
./xti vuln change-notify
./xti vuln exposure-evidence-add INCELEME_KIMLIGI --type package_inventory --reference yerel-paket-kontrolu-1 --summary "Kurulu paket ve sürüm kullanıcı tarafından doğrulandı"
```

`vuln advisory-preview`, açıkça verdiğin tek CVE için OSV.dev'in ücretsiz API'sine bağlanır; anahtar istemez. OSV kimliğini, yayın/değişiklik zamanını, açıklamayı, ekosistem-paket bağlamını, bildirilen sürüm sınırlarını ve `ADVISORY` türündeki başvuruları sınırlı biçimde gösterir. Yanıt 8 MiB, bağlantı 30 saniye; paket ve başvuru görünümü varsayılan 50, en fazla 200 kayıtla sınırlıdır.

`vuln source-evaluation`, ek resmî üretici kaynaklarını çalışma anında internete çıkmadan aynı kapıdan geçirir. Zorunlu ölçütler üreticinin resmî verisi, ücretsiz/kimlik doğrulamasız erişim, yapılandırılmış biçim, sınırlı tek-kayıt erişimi, ürün-yayın bağlamı ve açık yeniden kullanım koşuludur. `official-vendor-source-gate-v1` değerlendirmesinde Canonical Ubuntu OSV 6/6 ile seçildi; Microsoft MSRC CVRF ile Debian Security Tracker tek-kayıt/lisans çalışmaları için ertelendi; Cisco openVuln istemci kimliği ve OAuth belirteci istediği için ücretsiz-anahtarsız profil dışında bırakıldı. Bu karar kaynakların güvenilirlik veya kapsam bakımından eşdeğer olduğunu söylemez ve henüz ağ adaptörü çalıştırmaz.

`vuln ubuntu-preview`, verdiğin CVE için Canonical'ın resmî `ubuntu-security-notices` deposundaki tek `UBUNTU-CVE` OSV dosyasını alır. Yıl ve kayıt yolu CVE'den türetilir; başka adres kabul edilmez. HTTPS yönlendirmesi reddedilir, bağlantı 30 saniye ve yanıt 8 MiB ile sınırlıdır; yalnız JSON/metin içerik türü ve kimlik kodlaması kabul edilir. Kayıt kimliği tam `UBUNTU-CVE-...`, upstream bağı tam CVE ve bütün paket ekosistemleri `Ubuntu:*` olmak zorundadır. Terminal Ubuntu yayını, kaynak paket, bildirilen sürüm sayısı, düzeltilmiş sürüm sınırı ve USN bağlantılarını gösterir; görünüm sınırları ayrı 1–200'dür. Komut veritabanı yazmaz, yerel paketin kurulu olduğunu varsaymaz ve Ubuntu dışı dağıtımlar için hüküm üretmez. `Ubuntu:Pro:*` kayıtları abonelik/ESM bağlamıdır; görünmesi erişimin ücretsiz olduğunu söylemez.

`vuln ubuntu-match`, aynı resmî kayıtta kullanıcının açıkça verdiği tam Ubuntu OSV ekosistemini, Debian kaynak paket adını ve kurulu sürüm beyanını karşılaştırır. Girdiler ağ isteğinden önce doğrulanır. Tam yayın+paket bağı tekilse Debian'ın epoch, upstream sürüm, revision, sayısal parça ve `~` sıralaması uygulanır; sonuç `düzeltme sınırından önce`, `eşit` veya `sonra` olarak açıklanır. Kayıt eşleşmiyorsa `listelenmiyor`; eşleşip fixed sınırı yoksa `listelenmiş fakat düzeltme sınırı yok`; geri çekilmiş kayıtta ayrıca `geri çekilmiş` sonucu verilir. `listelenmiyor`, Canonical eşlemesine göre “paket o yayında yok” veya “etkilenmiyor” durumlarından hangisi olduğunu tek başına ayırmaz. Duyurular varsayılan 50, en fazla 200 bağlantıyla sınırlıdır.

Bu karşılaştırma yerel makineden paket okumaz; verdiğin yayın, kaynak paket ve sürümün doğru olduğunu bağımsız doğrulamaz. Sonuç Canonical'ın o kayıttaki sınırına göre inceleme adayıdır; veritabanı/veri klasörü oluşturmaz, maruziyet kaydı açmaz, insan kararını değiştirmez ve Ubuntu Pro erişim hakkı varsaymaz.

`ubuntu-packages add`, bir domain varlığına kurulu binary paket adı, tam Debian sürümü, mimari, kaynak paket adı ve kaynak sürümünü tek kullanıcı kanıtıyla bağlar. Bu alanları Ubuntu üzerinde `dpkg-query` ve paket kaynağı bilgisi gibi güvenilir yerel çıktılardan doğrulamak kullanıcının sorumluluğundadır; XTI bu sürümde makineye uzaktan bağlanmaz ve alanları tahmin etmez. Aynı kesin kimlik tekrar eklenmez; kanıt güncellemeleri, kaldırma ve yeniden etkinleştirme silinmeyen geçmişte kalır. `list` ve `show` internete çıkmaz.

`vuln ubuntu-inventory-match`, kayıtlı etkin paketi seçilen CVE'nin güncel Canonical kaydıyla karşılaştırır. Canonical OSV kaynak paket düzeyinde olduğundan karşılaştırma yalnız kayıttaki `source-package` ve `source-version` alanlarını kullanır; binary sürüm ayrı kanıt olarak görünür fakat fixed sınırıyla karşılaştırılmaz. Kaldırılmış kayıt ağdan önce reddedilir. Sonuç üretici sınırına göre inceleme adayıdır; otomatik maruziyet açmaz, destek kanıtı yazmaz ve insan kararını değiştirmez.

`vuln ubuntu-inventory-scan`, tek bir CVE için seçilen varlığın veya bütün kayıtlı varlıkların etkin Ubuntu paketlerini birlikte tarar. Canonical dosyası bir kez alınır; bütün paketler doğrulanmış source sürümleriyle karşılaştırılır. Çıktı listelenmiyor, fixed sınırı yok, sınırdan önce, eşit, sonra ve geri çekilmiş sayılarını ayrı verir; önce/fixed-yok kayıtlarını görünümde öne alır. En fazla 10.000 etkin paket ve 100.000 kanıt olayı doğrulanır, `--limit` yalnız gösterimi 1–500 arasında keser. Boş kapsamda ağa çıkılmaz; tarama veritabanını veya insan kararını değiştirmez.

`vuln ubuntu-evidence-add`, seçtiğin mevcut maruziyet ile Ubuntu paketinin aynı varlığa ait olduğunu doğrular, maruziyetin CVE'si için Canonical kaydını yeniden alır ve güncel sonucu genel `package_inventory` destek kanıtına bağlar. Paket Canonical kaydının tek `affected` yayın+kaynak paket bağıyla eşleşmiyorsa, kayıt geri çekilmişse, paket kaldırılmışsa veya ağ isteği sürerken paket kanıtı değişmişse hiçbir kanıt yazılmaz. Kaynak başvurusunda CVE, paket kimliği, tam paket anlık görüntüsü ve Canonical içerik özetleri ile karşılaştırma durumu saklanır. Aynı seçim tekrar edilirse çoğalmaz; paket veya Canonical içerik gerçekten değişirse yeni kanıt oluşur. Bu işlem maruziyeti otomatik olarak `affected`, `not_affected` veya `fixed` yapmaz; karar ve gerekçe ayrı insan incelemesinde kalır. Oluşan kayıt mevcut `exposure-evidence-list/show/revoke`, `exposure-queue`, yedek ve restore akışlarında görünür.

`vuln ubuntu-evidence-check`, bu özel kanıtın kayıtlı CVE, paket kimliği, paket özeti, Canonical içerik özeti ve sonucunu güncel durumla karşılaştırır. Kaynak belgesinin değişip sonucun aynı kalmasını, paketin yeniden doğrulanmasını, sürüm sonucunun değişmesini, bağın kaybolmasını ve Canonical kaydının geri çekilmesini ayrı gösterir. Paket veya kanıt etkisizse ağa çıkmaz; paket kaynak sorgusu sürerken değişirse kesin sonuç vermek yerine yeniden çalıştırılmasını söyler. Komut salt okunurdur: eski kanıtı güncellemez, yeni kanıt oluşturmaz ve insan kararını değiştirmez. Değişmiş güncel sonucu kalıcılaştırmak istersen önce inceleyip yeniden `ubuntu-evidence-add` çalıştırırsın. `ubuntu-osv-v1` ile başlayan yapılandırılmış kaynak başvuruları genel `exposure-evidence-add` yoluna kapalıdır.

`vuln ubuntu-evidence-plan`, bütün etkin seçilmiş Ubuntu kanıtlarını yalnız yerel veriden inceler; paket anlık görüntüsü aynı, değişmiş veya etkisiz olanları sayar ve dikkat gerektirenleri önce gösterir. Canonical kaynağına bağlanmaz. En fazla 10.000 kanıt ile bunların 100.000 olayını görünüm limitinden bağımsız doğrular; bozuk gizli kayıt kısmi plan üretmez. `--domain` yalnız kayıtlı bir varlığı seçebilir, `--limit` 1–500 arasında yalnız çıktıyı keser.

`vuln ubuntu-evidence-scan`, bu plandaki ilk 1–20 kanıtı güncel Canonical kaydıyla denetler. Seçilen birden çok kanıt aynı CVE'ye bağlıysa dosya yalnız bir kez alınır. Boş kapsam kaynak çağırmaz; etkisiz paket için tekil kontroldeki gibi kaynak atlanır. Toplam/işlenen/kalan, gerçek Canonical çağrısı, güncel/değişmiş/atlanan sayıları birlikte görünür. Komut salt okunurdur ve arka planda zamanlanmaz; kullanıcı açıkça çalıştırır.

Genel `vuln advisory-preview` akışındaki OSV.dev kaydı bir açık kaynak zafiyet toplayıcısıdır; önizleme üreticinin “etkileniyor/etkilenmiyor” kararı değildir. Paket kaydı bulunmaması güvenli olduğun anlamına gelmez ve genel OSV aralıkları otomatik sürüm hükmüne çevrilmez. Önizleme veritabanı veya veri klasörü oluşturmaz, maruziyet kararı vermez ve başvuruları destek kanıtına kendiliğinden eklemez.

Bir HTTPS başvurusunu incelemene bağlamak istersen `vuln advisory-evidence-add` komutunda inceleme kimliğini, önizlemede gördüğün tam adresi, kendi seçtiğin üretici/dağıtım türünü ve açıklamanı verirsin. XTI önce incelemenin CVE'sini yerelden okur, OSV'nin o anki kaydını yeniden alır ve adresin gerçekten `ADVISORY` listesinde olduğunu doğrular; ancak sonra mevcut eklemeli destek kanıtı geçmişine yazar. HTTP, listede olmayan adres, kaynak hatası veya bilinmeyen inceleme hiçbir kanıt oluşturmaz. OSV'de listelenmek bağlantının içeriğini, sahibini veya üretici hükmünü doğrulamaz; insan kararı ve öncelik değişmez.

`vuln vendor-preview`, `--provider redhat` veya `--provider suse` seçimine göre üreticinin resmî tek-CVE CSAF VEX 2.0 dosyasını doğrudan alır. Belgenin yayımcısını, CVE bağını, sürüm geçmişini, ürün ağacını ve çelişmeyen durum kümelerini doğrular; durum sayılarını, sınırlı ürün/bileşen örneklerini ve düzeltme başvurularını gösterir. Yanıt 16 MiB ve 30 saniye; durum başına örnek varsayılan 5/en fazla 50, düzeltme görünümü varsayılan 10/en fazla 100 kayıttır. Komut veritabanı veya veri klasörü oluşturmaz.

SUSE eski CVE'leri 2023 geri-doldurma dizininde, daha yeni CVE'leri kendi yıl dizininde yayımlar; XTI bu yolu otomatik seçer. SUSE görünümündeki `recommended`, `known_not_affected` veya diğer durumlar yalnız SUSE/openSUSE ürün bağlamında SUSE'nin beyanıdır. Bu sürüm SUSE yerel paket eşleştirmesi ya da kalıcı SUSE kanıtı yazmaz.

Bu VEX, yalnız Red Hat ürünleri için Red Hat'in doğrudan beyanıdır. Örneğin Red Hat Enterprise Linux 5 bileşeninin `known_not_affected` olması Ubuntu, Debian, başka bir OpenSSL paketi veya senin makinen için aynı sonucu doğurmaz. `fixed` kimliği de yalnız listelenen Red Hat bileşen/sürüm bağlamında anlamlıdır. Kurulu paket kimliği ayrıca doğrulanmadan XTI maruziyet kararı üretmez; backport bilgisi kaybolmaz.

`vuln vendor-match`, `packages list` çıktısındaki etkin paketi seçilen Red Hat VEX belgesiyle karşılaştırır. Tam ikili paket ancak NEVRA (ad+epoch+sürüm+release+mimari), PURL ve dağıtım CPE'si birlikte aynıysa eşleşir. VEX kaynak paket düzeyinde beyan veriyorsa yerel kayıtta doğrulanmış kaynak RPM adı ve aynı dağıtım CPE'si gerekir. Farklı dağıtım eki, epoch, release veya mimari sonuç üretmez.

Çıktıdaki `fixed`, `known_affected` veya `known_not_affected` Red Hat'in belge beyanıdır; XTI'nin yerel maruziyet kararı değildir. `vendor-match` veritabanını yazmaz. Kesin eşleşme bulunmaması güvenli olduğun anlamına gelmez; belge başka ürün bağlamı kullanabilir veya veri eksik olabilir.

Kesin bağı inceledikten sonra `vendor-evidence-add` ile maruziyet kimliğini, aynı varlığa ait kesin RPM kimliğini, çıktıda gördüğün tam VEX ürün kimliğini ve kendi açıklamanı verirsin. XTI girdileri ve varlık bağını ağdan önce doğrular, güncel Red Hat belgesini yeniden alır ve seçimin hâlâ tekil/çelişkisiz kesin eşleşme olduğunu kontrol eder. Başarılıysa CVE, RPM, dağıtım CPE'si, VEX ürün/bileşen ilişkisi, belge sürümü, yayım zamanı ve kaynak SHA-256 özeti birlikte saklanır. Ağ sırasında paket değişirse yazma reddedilir; yeni belge özeti veya yeniden doğrulanmış paket anlık görüntüsü eski kanıtı ezmeden ayrı kayıt olur.

Ekleme komutu CVE'yi seçilen maruziyetten alır. Önce `vuln exposure-show INCELEME_KIMLIGI` ile bu CVE'yi gör; `vendor-match` çağrısında da aynı CVE'yi kullan. Başka bir CVE için alınmış eşleşme bu maruziyete kanıt olmaz. VEX ürün kimliğini çıktıda olduğu gibi, başındaki/sonundaki boşlukları da koruyarak tırnak içinde aktar; XTI bu kimliği kırpmaz veya başka bir kimlikle birleştirmez.

Bu yapılandırılmış kanıt `vuln exposure-queue --evidence present` görünümünde `exact_vendor_package` türü olarak sayılır. Kanıt ekleme, güncelleme, iptal ve yeniden etkinleştirme geçmişi korunur; hiçbir işlem insanın `investigating/affected/not_affected/fixed` kararını veya öncelik bandını kendiliğinden değiştirmez. Şema 23 veritabanı yalnız açık `./xti migrate` komutuyla, önce doğrulanmış yedek alınarak şema 24'e taşınır.

`vendor-evidence-check`, kayıtlı kanıtı güncel RPM kaydı ve yeniden alınan Red Hat VEX belgesiyle salt okunur karşılaştırır. Tamamen güncel; kaynak dosyası değişmiş ama beyan aynı; RPM yeniden doğrulanmış; beyan değişmiş; seçilen bağ kaybolmuş; çelişen bağlam veya etkisiz paket durumlarını ayrı gösterir. Etkisiz pakette ağa çıkmaz. Komut yeni kanıt eklemez, eski kanıtı güncellemez ve insan kararını değiştirmez.

Bir maruziyet için düzeltmeyi planlayıp sonucunu izlemek için:

```sh
./xti vuln remediation-plan INCELEME_KIMLIGI --recommendation "Paketi düzeltilmiş sürüme yükselt" --source-type vendor_package_evidence --source-reference KANIT_KIMLIGI --reason "Kesin üretici kanıtı insan tarafından incelendi" --recheck-days 7
./xti vuln remediation-implement PLAN_KIMLIGI --reason "Bakım penceresinde uygulandı" --evidence-reference degisiklik-kaydi-1042 --recheck-days 2
./xti vuln remediation-recheck PLAN_KIMLIGI --outcome not_observed --reason "Eski paket artık envanterde gözlenmiyor" --evidence-reference paket-kontrolu-2
./xti vuln remediation-list --due-only
./xti vuln remediation-show PLAN_KIMLIGI
./xti vuln remediation-cancel PLAN_KIMLIGI --reason "Plan değiştirildi"
```

Plan kaynağı olarak etkin kesin paket/VEX kanıtı, etkin genel maruziyet kanıtı veya `analyst_note` kullanılabilir. Uygulama kaydı sonraki kontrol tarihini zorunlu kılar. Kontrol sonucu `still_present` veya `inconclusive` ise yeni tarih de zorunludur; açık risk sessizce takip dışı kalmaz. `not_observed` yalnız kontrol gözlemidir: maruziyet `fixed` olmaz. Kapatmak için ayrı, gerekçeli `exposure-review --status fixed` kararı gerekir. Bu komutlar internete bağlanmaz ve paket kurmaz.

Bu ücretsiz ilk NVD dilimi yalnız açıkça istediğin CVE için NIST'in resmî API 2.0 adresine tek istek gönderir; API anahtarı gerekmez. Açıklama, durum, yayın/son değişiklik zamanı, CWE'ler ve NVD ile diğer sağlayıcıların bütün CVSS 4.0/3.1/3.0/2.0 kaynak-sürüm-vektör kayıtları ayrı korunur. Tam kaynak CVE nesnesi de gelecekteki CPE/ürün eşleştirmesi için saklanır; değişiklikte önceki sürüm eklemeli geçmişte kalır.

Bu bir tam NVD aynası değildir ve bütün CVE'leri otomatik indirmez. CVSS teknik önem ve etki bağlamıdır; EPSS olasılığı, KEV gerçek istismar bilgisi ve kayıtlı varlıkta ürün/sürüm kanıtı yerine geçmez. Bu sürüm port numarasını ürüne dönüştürmez veya otomatik CVE maruziyeti üretmez. İlgili-kayıt yenilemesi zaten insan incelemesine alınmış CVE'leri; aşağıdaki tarih penceresi ise açıkça verdiğin küçük değişiklik dönemini kapsar.

`vuln overview`, CVE'nin daha önce alınmış KEV, EPSS ve NVD kayıtlarını tek ekranda gösterir. Komut internete bağlanmaz ve kayıtları değiştirmez. Üç kaynaktan biri alınmadıysa bunu açıkça eksik gösterir; eksik bilgi “risk yok” anlamına gelmez. Üç kayıt aynı veritabanı anından okunur. KEV, EPSS ve CVSS'nin anlamları ayrı tutulur ve bu ekran tek başına kayıtlı bir varlık için zafiyet maruziyeti oluşturmaz.

`vuln plan`, güncel KEV kataloğunda bulunan veya verdiğin EPSS eşiğini geçen fakat NVD ayrıntısı henüz alınmamış CVE'leri sıralar. Aynı CVE iki koşulu da karşılıyorsa tek satır gösterilir; NVD kaydı olanlar yeniden planlanmaz. Komut yalnız yerel kayıtları okur, internete çıkmaz ve otomatik indirme başlatmaz. Böylece önce ne kadar iş oluşacağını görür, ardından gerekli CVE'leri açıkça ve kontrollü biçimde alırsın. Bu liste de varlıklarında zafiyet bulunduğu anlamına gelmez.

`vuln enrich-nvd`, bu planın başındaki en fazla beş CVE'yi resmî NVD API'sinden sırayla alır. Ücretsiz/anahtarsız erişimde istekler arasında en az 6,5 saniye bırakılır; önceki çalışmanın zamanı da hesaba katılır. İlk bağlantı, kaynak veya ayrıştırma hatasında işlem durur. O ana kadar başarıyla alınan kayıtlar kaybolmaz; hata da geçmişte kalır. Aynı komutu tekrar çalıştırdığında NVD'si tamamlananlar plandan çıktığı için kalanlardan devam edilir. Bu komut tam NVD aynası oluşturmaz ve ürün/sürüm kanıtı olmadan varlık maruziyeti üretmez.

`vuln tracked-nvd-plan`, varsayılan olarak açık ve görünür maruziyetlerde kullanılan benzersiz CVE'lerin son başarılı NVD kontrol zamanını inceler. Varsayılan 168 saatlik eşiği `--stale-after-hours` ile 1–8760 arasında değiştirebilirsin. Aynı CVE birden çok varlığa bağlıysa tek satır ve tek olası ağ isteği olarak gruplanır. `--include-closed` kapanmış, `--include-suppressed` gizlenmiş kayıtları açıkça kapsama ekler. Plan internete bağlanmaz, kayıt yazmaz; sistem saatinden ileride görünen kaynak zamanını ayrıca gösterir ve bunu yenileme adayı saymaz.

`vuln tracked-nvd-refresh`, plandaki zamanı gelmiş ilk en fazla beş CVE'yi resmî NVD API'sinden yeniler. Önceki süreçteki son NVD denemesi dahil istekler arasında en az 6,5 saniye bırakır; her CVE ayrı atomik kaydedilir ve ilk hatada sonraki isteklere geçmez. Kaynakta değişiklik olsa bile insanın maruziyet kararı ve geçmişi değişmez. Ardından `vuln reassessment-plan` çalıştırarak hangi incelemelerin yeni NVD kanıtından etkilendiğini görürsün. Komut bir daemon veya otomatik zamanlayıcı değildir; çalıştırmayı sen başlatırsın.

`vuln nvd-window-plan`, saat dilimi belirtilmiş başlangıç ve bitiş arasındaki NVD `lastModified` akışının sıradaki sayfasını internete çıkmadan gösterir. Kişisel kullanım sınırı tek pencere için en fazla yedi gün, sayfa için 1–100 kayıttır. Plan yeni, devam etmeye hazır, son denemesi başarısız veya tamamlanmış durumu; sonraki sıra, bilinen toplam ve kalan sayıyı açıkça verir. Tamamlanmış plan yeniden çalıştırıldığında ağ isteği yapılmaz.

`vuln nvd-window-fetch` yalnız bir sayfa alır. Ücretsiz anahtarsız erişimde önceki NVD denemesini de dikkate alarak en az 6,5 saniyelik aralığı korur. Sayfadaki bütün CVE kayıtları ile sonraki sıra aynı SQLite işlemi içinde yazılır; bozuk/eksik sayfa, kaynak hatası, değişen toplam veya eşzamanlı plan sapması sırayı ilerletmez. Aynı başlangıç, bitiş ve sayfa boyutuyla tekrar çağırınca kaldığı yerden devam eder. Kaynak kaydı değişse bile insanın maruziyet kararı ve geçmişi değişmez; değişiklik daha sonra `reassessment-plan` ve `change-notify` ile açıkça incelenir. Bu komut otomatik zamanlayıcı veya tam NVD aynası değildir.

`vuln nvd-window-list`, kayıtlı pencereleri `ready`, `failed` ve `complete` durumlarıyla ağsız listeler. `nvd-window-show` tam başlangıç+bitiş+sayfa boyutunun ilerlemesini ve gerekçeli yeniden başlatma geçmişini gösterir. Bu okumalar imleci, hata bilgisini veya veritabanını değiştirmez.

`vuln nvd-window-coverage`, en fazla 366 günlük bir inceleme döneminde yalnız tamamen bitmiş pencereleri kapsama sayar. Örtüşen ve uç uca gelen bitmiş dönemleri birleştirir; hazır veya başarısız pencereyi kapsanmış göstermez ve kalan boşlukları açıkça listeler. “Tam kapsama” o dönem için sayfaların tamamlandığını söyler; NVD'nin eksiksizliği, ürün maruziyeti veya kaynağın bugün çalıştığı anlamına gelmez.

`vuln nvd-window-gap-plan`, bu açık boşlukları kronolojik sırada en fazla yedi günlük pencerelere böler. Her aday için başlangıç, bitiş, sayfa boyutu, yeni/devam/başarısız durumu ve sonraki sıra gösterilir; aynı kimlikle yarım kalmış pencere varsa mevcut ilerleme korunarak görünür. `--limit` 1–100 aday gösterir ve kalan adayları gizlemeden toplamı bildirir. Komut internet isteği göndermez, pencere oluşturmaz, veritabanını değiştirmez ve adayları otomatik çalıştırmaz. Kullanıcı seçtiği adayı aynı değerlerle `nvd-window-fetch` komutuna verir.

`vuln nvd-window-gap-fetch`, aynı planın başındaki açıkça seçilmiş 1–3 adayın her birinden en fazla bir sayfa alır. Önce aday toplamını belirler, yerel çalıştırma kilidini alır, her istekten önce süreçler arası anahtarsız NVD aralığını korur ve ilk kaynak hatasında sonraki adaylara geçmez. Başarılı sayfa kendi pencere imleciyle atomik yazılır; bir pencerenin daha çok sayfası varsa sonraki açık komuta bırakılır. Sonuç denenmiş/başarılı/başarısız sayfaları, bu çalışmada denenmeyen önceki adayları ve güncel boşluk planını ayrı gösterir. Bu komut bir arka plan zamanlayıcısı veya tam NVD aynası değildir.

`vuln nvd-window-operations`, verdiğin en fazla 366 günlük dönemle kesişen bütün kalıcı pencereleri tek SQLite okuma anında değerlendirir. Tamam, devam etmeye hazır ve son denemesi hatalı pencere sayılarını; dikkat bekleyen toplamı, yeniden başlatma sayısını, en son güncellenen pencereyi ve `--recent-limit` ile 1–100 son pencereyi gösterir. Aynı ekranda tamamlanmış pencerelerden hesaplanan gerçek kapsama ve açık zaman aralıkları bulunur. Durum `no_activity`, `in_progress`, `attention`, `gaps` veya `covered` olarak açıklanır. Komut internete bağlanmaz, hata temizlemez, pencere ilerletmez ve veritabanını değiştirmez.

NVD toplam sonucu sayfalar arasında değiştiyse ya da aynı dönemi baştan doğrulamak istiyorsan `nvd-window-restart` zorunlu bir gerekçeyle kalıcı imleci sıfırlar. Önceki sıra, toplam, durum, hata, başarı zamanı ve kaynak çalışma bağı silinmeyen olayda kalır. Mevcut CVE kayıtları, değişiklik geçmişi ve kaynak çalışmaları silinmez. Sistem saati son pencere kaydından gerideyse yeniden başlatma reddedilir. Yeniden başlatılan dönem, bütün sayfalar tekrar tamamlanana kadar kapsama görünümünde açık kalır.

`vuln applicability`, alınmış NVD kaydındaki CPE ürün ve sürüm koşullarını açar. Uygulama, işletim sistemi ve donanım satırları; tam sürüm veya başlangıç/bitiş aralığı; NVD'nin `AND`/`OR` grupları birlikte korunur. `vulnerable=false` satırı çoğu zaman bir donanım/ortam koşuludur ve “güvenli” anlamına gelmez. Gösterim sınırlandırılsa bile bütün koşullar doğrulanır ve toplam sayı görünür. Bu ekran yalnız NVD'nin CVE için hangi ürün koşullarını yayımladığını söyler; senin varlığında o ürünün bulunduğunu veya zafiyetin gerçekten mevcut olduğunu kanıtlamaz.

`vuln assess-product`, `products list` çıktısındaki doğrulanmış ürün kimliğini seçtiğin yerel NVD CVE kaydıyla karşılaştırır. Tür+üretici+ürün tam eşleşir. Basit ve kesin sürüm eşleşmesi yalnız “NVD koşulu adayı”dır; sürüm aralığı, joker, `AND`, tersleme ve çevresel koşullar elle inceleme gerektirir. Ürün/sürüm koşulu bulunmaması da “güvenli” demek değildir. Komut internete bağlanmaz, alarm/risk kaydı oluşturmaz ve veritabanını değiştirmez.

`vuln asset-overview`, aynı ürün+CVE için ürün koşulunu, KEV gerçek istismar bilgisini, EPSS 30 günlük olasılık tahminini ve NVD/CVSS teknik önemini tek ekranda gösterir. Bunları tek bir risk puanına dönüştürmez. NVD eksikse mevcut KEV/EPSS kaybolmaz; ürün koşulu açıkça değerlendirilemedi görünür. Saklı kaynaklardan biri bozuksa yanıltıcı kısmi ekran yerine işlem durur.

`vuln match-products`, bir yerel NVD CVE kaydını bütün etkin doğrulanmış ürünlerinle karşılaştırır. Varsayılan çıktı yalnız kesin koşul ve elle inceleme adaylarını gösterir; `--all` eşleşmeyenleri de ekler. Bütün ürünler doğrulanır, fakat gösterim en fazla 500 ürün ve JSON'da ürün başına 20 ilgili koşulla sınırlıdır. Bu bir inceleme aday listesidir; otomatik vaka, alarm veya maruziyet kaydı değildir.

`vuln exposure-open`, yalnız bu adaylardan bir ürün+CVE çiftini açık gerekçeyle insan incelemesine alır. İlk durum `investigating` olur. Karar anındaki ürün kanıt zamanı, NVD kaynak özeti ve aday türü saklanır; komut internete bağlanmaz. Aynı çift tekrar açıldığında eski insan kararını veya geçmişi ezmez.

İnceleme kimliğini `exposure-list` çıktısından alıp kararı kaydedebilirsin:

```sh
./xti vuln exposure-review INCELEME_KIMLIGI --status affected --reason "Üretici duyurusu ve kurulu paket doğrulandı" --recheck-days 14
./xti vuln exposure-suppress INCELEME_KIMLIGI --days 14 --reason "Onaylı bakım penceresine kadar tekrar ele alınmayacak"
./xti vuln exposure-suppression-show INCELEME_KIMLIGI
./xti vuln exposure-unsuppress INCELEME_KIMLIGI --reason "Bakım tamamlandı; kayıt yeniden görünür olmalı"
./xti vuln exposure-show INCELEME_KIMLIGI
./xti vuln exposure-list --include-suppressed
```

Durumlar `investigating`, `affected`, `not_affected` ve `fixed` değerleridir. `exposure-suppress` yalnız açık kaydı gerekçeli ve 1–3650 günlük süreyle varsayılan liste/kuyruktan gizler. Kesin bitiş anında kayıt, veritabanına yazma veya insan kararını değiştirme olmadan yeniden görünür; uzatma, yeniden etkinleştirme ve erken kaldırma eklemeli geçmişte kalır. Eski süresiz `exposure-review --suppress/--unsuppress` seçeneği geriye dönük uyumluluk için korunur; yeni geçici ertelemelerde süreli komut tercih edilir. `--recheck-days` zamanı geldiğinde kayıt kendiliğinden değişmez, yalnız yeniden inceleme uyarısı verir. Ürün kanıtı veya NVD kaydı değişir ya da ürün etkisizleştirilirse eski karar korunur ve nedenleriyle yeniden inceleme gerekli görünür. Her karar gerekçesi eklemeli geçmişte kalır; bu yaşam döngüsü de otomatik tarayıcı hükmü değil, açık insan kararıdır.

`vuln exposure-queue`, görünür ve açık incelemeleri KEV, EPSS, birincil CVSS, etkin destek kanıtı, düzeltme takibi, insan beyanlı varlık önemi ve son kayıtlı internet erişim kanıtıyla sıraya koyar. Tek bir gizli risk puanı kullanmaz; “Hemen”, “Yüksek”, “Normal” ve “İzlenen” bantlarını ve nedenlerini ayrı gösterir. Her satırda destek kanıtı, açık düzeltme planı, kontrol sonuçları, iş önemi ve web/izinli servis erişilebilirliği görünür. Kontrol vadesi, yüksek/kritik iş önemi ve doğrulanmış güncel erişim dikkat nedeni olabilir; hiçbiri insanın maruziyet kararını değiştirmez. `--surface-stale-hours 72` kayıtlı web/servis kanıtının kaç saat sonra eski sayılacağını belirler; varsayılan 24 saattir. `--evidence present` yalnız etkin kanıtı olanları, `--evidence missing` kanıtı olmayanları gösterir; varsayılan `all` değeridir. Varsayılan EPSS eşiği `0.9` değeridir; `--min-epss 0.8` ile değiştirebilirsin. `--include-closed` etkilenmiyor/düzeltildi, `--include-suppressed` süresiz veya henüz dolmamış süreli bastırılmış kayıtları da ekler. Süresi dolmuş kayıt normal kuyruğa yazmasız döner. Kapanmış karar yalnız yüksek kaynak puanı veya varlık bağlamı nedeniyle kendiliğinden açılmaz; ürün/NVD kanıtı değişmişse yeniden incelemeye yükselir. Kuyruk internete bağlanmaz, karar yazmaz ve erişim kanıtının yokluğunu güvenli sonuç saymaz.

Değişen ürün ve NVD kanıtlarını kontrollü olarak yeniden değerlendirmek için önce planı gör, sonra açıkça çalıştır:

```sh
./xti vuln reassessment-plan
./xti vuln reassessment-plan --include-closed --include-suppressed --limit 100
./xti vuln reassessment-run
./xti vuln reassessment-runs
./xti vuln reassessment-show CALISMA_KIMLIGI
./xti vuln change-notify
./xti vuln change-notify --include-closed --include-suppressed --limit 100
```

Plan; ürünün etkisizleşmesini, ürün kanıtının veya NVD kaydının değişmesini ve yeniden kontrol tarihinin gelmesini ayrı nedenlerle gösterir. Varsayılan olarak yalnız açık ve görünür incelemeler alınır. `reassessment-plan` internete bağlanmaz ve hiçbir kayıt yazmaz. `reassessment-run` güncel yerel koşulu yeniden hesaplayıp değişmez bir denetim kaydı oluşturur; insanın kararını, gerekçesini, tarihini veya karar geçmişini değiştirmez. Eşleşmenin artık görülmemesi de otomatik `not_affected` veya `fixed` sonucu değildir. Plan ile kayıt arasında ilgili veri değişirse çalışma kısmen yazılmadan bütünüyle durur.

`change-notify`, aynı plan nedenlerini mevcut yerel gelen kutusuna ekler. Bir çalışmada en fazla 100 yeni durum kaydeder; daha önce aynı kanıt özetiyle bildirilmiş adayları atlayıp sıradaki yeni duruma ilerler. Ürün/NVD kanıtı veya yeniden kontrol tarihi gerçekten değişirse yeni bildirim oluşur; aynı komutun tekrarı bildirim çoğaltmaz ve eski okundu işaretini sıfırlamaz. Komut internete çıkmaz, insan kararını değiştirmez ve e-posta/SMS göndermez. Plan ile yazma arasında veri değişirse bütün çalışma geri alınır.

Bir incelemeye karar dayanağı eklemek için destek kanıtını ayrı kaydedebilirsin:

```sh
./xti vuln exposure-evidence-add INCELEME_KIMLIGI --type vendor_advisory --reference https://ureticinin-guvenlik-adresi.example/duyuru --summary "Üretici duyurusu incelendi"
./xti vuln exposure-evidence-add INCELEME_KIMLIGI --type package_inventory --reference yerel-paket-kontrolu-1 --summary "Kurulu paket sürümü yerel envanterden doğrulandı"
./xti vuln exposure-evidence-list INCELEME_KIMLIGI
./xti vuln exposure-evidence-show KANIT_KIMLIGI
./xti vuln exposure-evidence-revoke KANIT_KIMLIGI --reason "Yanlış kayda bağlandığı için etkisizleştirildi"
```

Kanıt türleri üretici duyurusu, dağıtım duyurusu, yerel paket envanteri ve analist notudur. Duyuru adresleri yalnız güvenli HTTPS kaynak başvurusu olarak saklanır; XTI bu komutlarda bağlantıyı açmaz veya içeriği kendiliğinden indirmez. Aynı kaynak güncellenir, kaldırılır ya da yeniden etkinleştirilirse tek kimlik ve silinmeyen olay geçmişi korunur. Kanıtın varlığı insanın `affected`, `not_affected` veya `fixed` kararını otomatik vermez.

## Dış yüzeyin tek ekranlık özetini gör

Önceki komutların kaydettiği bilgileri tek yerde görmek için:

```sh
./xti surface overview markam.com
./xti --json surface overview markam.com --candidate-limit 50
```

Bu görünüm kök domaini; pasif bulunan alt alan adlarını; son DNS/IP, doğrulanmış TLS sertifikası, MX ve açık TCP bağlantı kanıtını birbirine bağlar. Aktif kapsam durumunu, son pasif keşfi ve kaç adayın onay beklediğini, sana ait veya reddedilmiş olduğunu da birlikte gösterir. Her ilişkinin dayandığı kayıt türü, kimliği ve gözlem zamanı JSON çıktısında bulunur.

Komut internete bağlanmaz, yeni tarama başlatmaz ve veritabanını değiştirmez. Bütün bölümleri aynı SQLite anlık görüntüsünden okur; bu nedenle görünümün bir kısmı eski, bir kısmı yeni bir ana ait olmaz. Adayların tamamını belleğe yüklememek için ilk 20 ilişki gösterilir; `--candidate-limit` 1–100 arasında değiştirilebilir ve toplam sayılar her zaman ayrıca görünür.

Bu bir grafik veritabanı veya yeni veri kopyası değildir. Mevcut kanıtların salt okunur ilişki görünümüdür. Bir alt alan adı ilişkisi sahipliği, bir IP ilişkisi özel sunucuyu, açık port çalışan ürünü, geçerli sertifika da güvenliği veya zafiyet bulunmadığını kanıtlamaz. Yeni veri toplamak için `surface discover`, yetkili aktif kontrol için `surface check`, posta DNS kontrolü için `surface mail check` ve servis kanıtı için `surface services check` ayrıca çalıştırılır.

## Yeni olay ve değişiklikleri bildirim kutusundan takip et

```sh
./xti inbox
./xti inbox show BILDIRIM_KIMLIGI
./xti inbox read BILDIRIM_KIMLIGI
```

Her yeni marka bulgusu, pasif keşifte ilk kez bulunan alt alan adı adayı, onaylı dış yüzey kanıtındaki gerçek değişiklik ve açıkça `vuln change-notify` ile kaydedilen yeni zafiyet kanıt durumu için yerel kutuya bildirim eklenir. Değişiklik bildirimi DNS/TLS/HTTPS, MX/SPF/DMARC veya sınırlı TCP servis kontrolünün ikinci ve sonraki sonuçlarında oluşabilir. İlk temel kayıt ve aynı sonucun tekrarı alarm değildir. İlk komut okunmamış bildirimleri gösterir. Kutuda gördüğün bildirim kimliğini diğer komutlarda kullan. Ayrıntı; kayıt türüne göre eşleşme nedenini, pasif sertifika kanıtını, değişen alan/portu veya zafiyet inceleme tetikleyicisini gösterir. Bildirim kutusu yenilikleri ve okundu durumunu; `triage` ise yalnız marka bulgularının inceleme sırasını gösterir.

RansomLook izlemesinde ilk ölçüm sessizdir. Sonraki yeni/değişen eşleşmeler
çalışma başına tek bildirim verir; ayrıntıda kaynak, izleme, kaynak yenileme ve
izleme çalışması kimlikleri görünür. Tam liste için
`./xti ransomware watch-run-show CALISMA_KIMLIGI --source ransomlook` kullan.
Tekrar, yalnız kaynak penceresinden çıkış veya kaynak hatası yeni bildirim
üretmez. Bildirim, iddianın doğrulandığı veya bir ihlal yaşandığı anlamına gelmez.

Listeye veya ayrıntıya bakmak otomatik olarak okundu sayılmaz. `inbox read` yalnız seçtiğin bildirimi işaretler; bulgunun şüpheli/normal veya alt alan adı adayının sahiplik kararını değiştirmez. Bir kaydı sınıflandırmak da bildirimini kendiliğinden okundu yapmaz. Aynı bulgu veya alt alan adı sonraki aramada görülürse bildirim çoğalmaz ve okundu işareti korunur. Bir adres farklı izlenen varlıkla veya yeni kural sürümüyle ayrı bulgu oluşturursa onun ayrı bildirimi olur.

```sh
./xti inbox list --status all
./xti inbox list --status read
./xti inbox unread BILDIRIM_KIMLIGI
./xti inbox read BIRINCI_KIMLIK IKINCI_KIMLIK
```

`unread` yeniden okunmamış yapar. Tek komutta en fazla 100 kimlik işaretlenebilir. Kimliklerden biri geçersizse hiçbirinin durumu değişmez. Tekrar okundu işaretlemek ilk okundu zamanını korur. Yalnız güncel okundu durumu saklanır; ayrı bir okundu işlem günlüğü yoktur.

Varsayılan sayfa 20 kayıt gösterir; `inbox list --limit 50` ile 1–100 arasında seçebilirsin. Daha fazla kayıt varsa sonraki sayfanın tam komutu gösterilir. Sonraki sayfalara geçerken yeni bildirimler eski sayfaları kaydırmaz; yeni gelenleri görmek için `./xti inbox` komutuyla başa dön. Filtre sayıları o andaki toplamı gösterir; sayfalar arasında yapılan okundu değişiklikleri sonraki görünümü etkileyebilir.

Bildirim ilgili bulgu, pasif aday veya değişiklik kanıtıyla aynı işlemde kaydedilir. İşlem başarısız olursa yarım kanıt ya da bildirim bırakılmaz. Okundu bilgisi program yeniden açıldığında ve yedekten dönüldüğünde korunur. Kutuyu okumak veya işaretlemek internete bağlanmaz. Değişiklik ilgili toplama, izleme veya kontrol komutunu çalıştırdığında fark edilir; bu sürümde arka plan takvimi, e-posta, SMS veya masaüstü teslimi ve kaynak kesintisi bildirimi yoktur.

## İsteğe bağlı dosya içe aktarma

İnternet araması için bu bölüm gerekli değildir. Dışarıdan hazır bir listeyi ayrıca incelemek istersen kullanılabilir.

`.txt` dosyasında her satıra bir adres yaz. Boş satırlar ve `#` ile başlayan yorumlar atlanır:

```text
example-support.net
exampel.com
unrelated.org
```

```sh
./xti import domains ./adresler.txt
```

İsteğe bağlı kaynak zamanı için JSONL biçimi de desteklenir:

```json
{"domain":"example-support.net","observed_at":"2026-10-28T12:00:00Z"}
```

Her satır ayrı nesnedir; yalnız `domain` ve isteğe bağlı `observed_at` kabul edilir. Zaman verilirse saat dilimi gerekir. Zaman yoksa bilinmiyor olarak saklanır; domain kayıt tarihi çıkarılmaz.

Dosya en fazla 2 MiB, 5000 fiziksel satır ve satır başına 8192 bayt olabilir. İzlenen adreslerle benzersiz girdi adreslerinin çarpımı en fazla 250.000 karşılaştırmadır. Hatalı satır varsa dosyanın tamamı reddedilir; yarım kayıt bırakılmaz. Kaynak dosyanın adı, özeti, satır numarası ve orijinal adres metni saklanır; dosyanın bütünü kopyalanmaz.

## Kayıt, kontrol ve yedek

```sh
./xti assets list
./xti doctor
./xti backup
```

Varsayılan kayıt konumu, komutu çalıştırdığın klasördeki `.xti-data/xti.db` dosyasıdır. Bu sürümün yedeği adresleri, gözlemleri, bulguları, karar geçmişini, tam adres istisnalarını ve işlem geçmişini, hedef kontrollerini, bekleyen işleri, deneme geçmişini, kaynak beklemelerini, tamamlanmış temizlik kayıtlarını ve bildirimlerin okundu durumunu kapsar.

```sh
./xti backup --output ./backups/ilk-yedek.db
./xti --data-dir ./geri-yukleme restore ./backups/ilk-yedek.db
./xti --data-dir ./geri-yukleme findings list
```

Geri yükleme boş kayıt alanına yapılır; mevcut dosyaların üstüne yazılmaz. Eski sürüm yedeği kendi düzeninde açılır, ardından `migrate` gerekir. Geçiş öncesi yedekler kayıt klasörünün `backups/` bölümündedir. Aynı diskteki yedek disk arızasına karşı korumaz; ayrı ortama kopyalanmalıdır.

Disk, yedek, saklama ve yerel kurtarma hazırlığını birlikte görmek için:

```sh
./xti storage readiness
./xti storage readiness --backup-stale-after-days 14 --retention-days 180
```

Komut kayıt klasörünün toplam dosya kullanımını, diskte kullanılabilir alanı, veritabanı boyutunu, SQLite'ın yeniden kullanabileceği alanı ve `backups/*.db` altındaki yönetilen yedekleri gösterir. En yeni yönetilen yedeğin XTI şeması ve SQLite bütünlüğü salt okunur olarak doğrulanır. Varsayılan olarak yedi günden eski yedek “eski”, 90 günden eski bağlantısız gözlemler ise saklama incelemesi gerektiren kayıtlar olarak görünür.

Disk çalışma payı için en az 64 MiB veya veritabanının mantıksal boyutunun iki katından büyük olan ihtiyatlı eşik kullanılır. Bu bir disk kotası veya kapasite garantisi değildir. Yalnız yerel `backups/` klasörü görülebilir; başka klasöre yazdığın yedekler, ayrı disk/bulut kopyası ve gerçekten yapılmış geri yükleme tatbikatı otomatik bilinmez. Bu nedenle bunlar açıkça `Bilinmiyor` ve `Kaydedilmedi` gösterilir.

`storage readiness` hiçbir dosyayı oluşturmaz, silmez veya taşımayı denemez; internete bağlanmaz. Bozuk en yeni yedek varsa bunu görünür hata yapar fakat sessizce eski yedeği “en yeni sağlıklı” diye sunmaz. Sembolik bağlantılar takip edilmez ve güvenli dosya sayısı sınırına ulaşılırsa toplamların eksik olabileceği açıklanır.

## Biriken kayıtları yönet

```sh
./xti storage status
./xti storage cleanup
```

İlk komut kayıt dosyasının boyutunu ve kayıt sayılarını gösterir. İkinci komut yalnız önizlemedir: hiçbir bulguya bağlı olmayan, ilk yerel kaydı 90 günden eski gözlemleri sayar. Bir bulguya bağlı kayıtlar, o bulguyu kapatmış olsan bile korunur. Bulguların, kararların, hedef kontrollerinin veya arama geçmişinin silinmesi bu komutun kapsamında değildir.

Önizleme, seçilen sayı ve yedek alarak uygulayacak tam komutu gösterir. Temizlemek istediğinde ekrandaki komutu kullan. Komut `--apply` ardından önizlemenin kimliğini taşır. Seçim değişmişse veya UTC günü değiştiyse işlem yapılmaz; yeniden önizleme gerekir. İlk komutun ürettiği kimlik başka kayıt klasöründe kullanılamaz.

Süreyi ve bir seferde işlenecek kayıt sayısını değiştirebilirsin:

```sh
./xti storage cleanup --older-than-days 180 --limit 1000
./xti storage history
```

Süre 7–3650 gün, işlem sınırı 1–10000 kayıt olabilir. Varsayılan sınır 10000'dir; daha fazla uygun kayıt varsa kalan sayı gösterilir. Yaş, kaynağın sertifika/tarama tarihinden değil, gözlemin ilk kez yerel kayda alınmasından hesaplanır. Aynı gözlemi tekrar almak bu zamanı yenilemez. Tarihi bozuk, saat dilimsiz veya gelecekte olan bağlantısız kayıtlar korunur. Kesim zamanı tam günlerle, UTC gün başlangıcına göre belirlenir.

Uygulama sırasında önce `backups/` içine tutarlı yedek alınır. Yedek alınamazsa hiçbir kayıt silinmez. Silme veya işlem kaydı başarısız olursa değişiklik geri alınır; alınmış yedek korunur. Başarılı temizlik ve yedek konumu `storage history` içinde görünür. Temizlik öncesi yedeği boş bir konuma geri yükleyerek o andaki tüm kayıtları geri alabilirsin.

Temizlik veritabanı içinde yeniden kullanılabilir yer açar; dosyayı hemen küçültmez. Ayrıca yedek dosyası için disk alanı gerekir. `storage status` yedek ve rapor klasörlerini, SHM dosyasını veya diskteki toplam boş alanı saymaz; bunları birlikte görmek için `storage readiness` kullanılır. Bu bakım ve geçiş yedekleri kendiliğinden silinmez; `schedule prepare` yalnız ayrı `scheduled-backups/` havuzundaki doğrulanmış kendi yedeklerini azaltabilir. `scan/watch` otomatik temizlik yapmaz. Temizlenmiş bağlantısız gözlem bir kaynakta tekrar alınırsa yeni gözlem olarak kaydedilebilir; eski işlerin tarihsel sayıları değiştirilmez. Ayrıntılar [bakım kararında](docs/decisions/0007-durable-waits-and-maintenance.md) bulunur.

## Kullanım sınırları

- `scan` ve `watch`, seçilen crt.sh/urlscan kaynaklarına HTTPS isteği yapar. `--check` ve `findings check` ayrıca sınırlı hedef bağlantısı yapar. Yeni urlscan taraması gönderilmez; sayfa içeriği veya açık port taraması yapılmaz.
- Sonuçlar geçmiş kayıtlardır. Kaynağa hiç girmemiş, henüz indekslenmemiş, geçmiş sınırının dışında kalan veya arama ifadesine uymayan adresler bulunmayabilir.
- Başarılı kaynak yanıtı bile bütün internetin veya tüm tehditlerin kontrol edildiği anlamına gelmez. Alınamayan ek sonuç, atlanan ad veya başarısız sorgu varsa sonuç kısmi gösterilir. Bilgi amaçlı tarih kapsamı notu tek başına kısmi durum oluşturmaz.
- İzlenen marka adresi şimdilik normal ASCII olmalı; Unicode veya `xn--` biçimindeki adres izleme hedefi kabul edilmez. Kaynaktan gelen geçerli U-label/Punycode adresler kanonik ASCII A-label olarak saklanır ve Unicode 18.0 UTS #39/UTS #46 profiliyle karşılaştırılır. Sağdan sola ve birleştirme denetimli IDNA etiketleri bu ilk profilde güvenli biçimde atlanır.
- `--typos` ile üretilen en fazla dört Punycode sorgusu yalnız sınırlı Latin/Greek/Cyrillic benzer-harf kapsamıdır. Tüm Unicode permütasyonları aranmaz; kaynak indeks/kota sınırları nedeniyle aday kaçabilir. Benzer iskelet kötüye kullanım kanıtı değildir.
- Alan adı kayıt sınırları paketlenmiş Public Suffix List ile ayrılır; özel barındırma sınırları da dahildir. Liste otomatik indirilmez.
- İzlediğin kayıt köklerinin altındaki adresler bu dış taklit kontrolünden çıkarılır. Bu, o adreslerde güvenlik sorunu olmadığı anlamına gelmez.
- Kısa ve genel sözcüklerde bazı benzerlik kuralları bilinçli olarak uygulanmaz. Yanlış veya kaçırılmış adaylar olabilir.
- Sahiplik doğrulanmaz. DNS/HTTPS kontrolü yalnız kayıtlı zamandaki dar bir gözlemdir. Bağlı kanıtlar korunur; bağlantısız eski gözlemler açık bakım komutuyla temizlenebilir. Otomatik zamanlanmış temizlik yoktur.
- Tam geçmiş kaynak dosyasını saklamak istiyorsan kendi dosyanı da korumalısın. Hash, içeriğin doğru olduğunu kanıtlamaz.
- Ransomware iddia görünümü suç gruplarının yayımladığı adları savunma amacıyla araştırır. Bu kayıtlar hedef seçmek, taciz etmek, kurbanları profillemek veya doğrulanmış ihlal gibi yayımlamak için kullanılmamalıdır.

## Yardım ve geliştirme

```sh
./xti --help
./xti --version
./xti --json findings list
./scripts/check-fast
./scripts/check
```

`./scripts/check-fast` her değişiklikte çalıştırılan kısa, ağsız
çekirdek ve kurulum kontrolüdür. `./scripts/check` tam regresyon paketidir;
sürüm oluşturmadan önce veya GitHub'daki elle başlatılan tam kontrolde çalışır.
GitHub'daki temiz Maigret/Sherlock kurulumu yalnız ilgili kurulum, sürüm veya
marka adaptörü dosyaları değiştiğinde tekrar çalışır. `v*` etiketi ancak tam
paket başarılı olursa GitHub sürümüne dönüştürülür.

### Sınanmış ortamlar

0.140.4 kod commit'i `7060cec` için doğrulanan temiz kurulumlar ve yerel
geliştirme ortamı:

| Ortam | Python | Doğrulama kapsamı |
|---|---|---|
| Ubuntu 24.04, x86_64 | 3.11 ve 3.12 | Maigret/Sherlock temiz kurulumu, yerel kontrol, tekrar ve geçici kayıtların korunması; [iki sürümün kabul işi](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43709958013) başarılı |
| Ubuntu 24.04, x86_64 | Çekirdek 3.11; theHarvester ayrı araç ortamında | İsteğe bağlı theHarvester temiz kurulumu, tekrar, engine okuma ve yedekten dönüş; [Linux kabul işi](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43709958037) başarılı |
| macOS 26.6.2, arm64 | 3.13.3 | Yerel geliştirme ve test ortamı; çalıştırılan kontrollerin kapsamı [durum belgesinde](docs/STATUS.md) |

Çekirdeğin Python alt sınırı 3.11'dir; başka Python sürümleri, dağıtımlar
ve mimariler için aynı kurulum başarısı bu tabloyla doğrulanmış sayılmaz.
Çalıştırıcı kilidi macOS/Linux içindir; Windows çalıştırıcısı henüz
desteklenmez. Gerçek kaynak erişimi ve Linux hizmet işletimi kendi kabul
sonuçlarıyla [durum belgesinde](docs/STATUS.md) izlenir.

Mevcut yerel çekirdek ek Python paketi istemez; haber toplama için
`feedparser` ve `feedparser-sgmllib` gerekir. Normal `./setup`, bu sabit
paketleri ve Maigret/Sherlock depolarının sabit commit'lerini `.venv` içine
önceki ortamı koruyarak kurar; sürüm, commit ve katalog bütünlüğünü doğrular.
Ek araçları kurmadan çekirdek için `./setup --core-only` kullanılabilir. Gerçek aramalar
internet ister; geçmiş kayıtları okuma ve yerel kuyruk yönetimi internetsiz
çalışır. Genel regresyon testleri ağsızdır; gerçek temiz kurulum kabulü
paketleri indirmek için internet kullanır. Public Suffix List, Unicode ve
sosyal kaynak/lisans bilgileri [THIRD_PARTY.md](THIRD_PARTY.md) içindedir.

### Geliştirme kontrolleri ve çıktı biçimleri

Geliştirme için tekrarlanabilir, tamamen geçici verili kontrol:

```sh
./scripts/python scripts/verify_inbox_soak.py --cycles 30
```

Bu komut sahte iki kaynakla tekrar, kaynak hatası ve kontrollü kesinti senaryolarını çalıştırır. Kullanıcı kayıt alanını kullanmaz; ağ girişimleri engellenir ve geçici veritabanı sonunda kaldırılır. JSON çıktısı ortamı, sayıları, süreyi ve ölçülebiliyorsa süreç tepe belleğini içerir. 10–1000 tur desteklenir. Bu hızlandırılmış deneme, saatlerce/günlerce canlı kullanım veya kapasite garantisi değildir.

`--data-dir` ve `--json` seçenekleri alt komuttan önce yazılır. `XTI_DATA_DIR` varsayılan klasörü, `XTI_PYTHON` çalıştırıcıyı seçer. Genel JSON hataları stderr'e yazılır. Arama veya hedef kontrolü kısmi/başarısız olsa da stdout'ta `ok:false` ve ayrıntıları içeren `data` döner. Çıkış kodları: 0 başarılı, 1 kayıt/dosya hatası, 2 geçersiz girdi/komut, 3 en az bir arama veya bu turda denenen hedef kontrolü kısmi/başarısız, 4 başka çalıştırıcı etkin, 130 iptal. Hedef bulunamaması tamamlanmış bir DNS yanıtıdır; tek başına hata kodu veya güvenli kararı üretmez.

0.5 JSON biçimi: varsayılan iki kaynaklı arama, tek nesnede `data.status` ve `data.results` listesini döndürür. `--source crt.sh` veya `--source urlscan` seçilirse `data` doğrudan tek arama sonucudur. Her kaynak sonucunda `provider`, `job_id`, `attempt_id`, `attempt_number` bulunur. Sorgularda eski `certificate_count` yerine genel `record_count`, ayrıca `coverage_notes` vardır. Kapsam notu tek başına hata değildir; sonuç eksikliği veya sorgu hatası kısmi durum oluşturur. `./xti --json watch` kaynak başına değil, tur başına tek JSON satırı üretir. Sıraya almada varsayılan `data.jobs`, tek kaynak seçiminde `data.job` döner.

0.6 bu yapıyı korur. `--check` sonucunda `data.checks` içinde bu turdaki kontroller, `skipped_fresh`, `remaining` ve kendi `status` alanı yer alır. Tek kaynak seçiminde `data.status` arşiv aramasına aittir; `ok` ve çıkış kodu hedef kontrolünü de hesaba katar. `checks.status` yalnız bu turda denenen hedeflere aittir; atlanan güncel denemeler başarılı kabul edilmez ve geçmişten görülebilir. Limit nedeniyle kalan adaylar `remaining` sayısındadır. `findings show` çıktısına `assessments` eklenir. Rapor dosyası `format: xti-finding-report`, `format_version: 1` taşır; stdout JSON çıktısı standart `ok/data` zarfındadır.

0.7 `sources` çıktısına `cooldowns` ve UTC değerlendirme zamanı `observed_at` ekler. Bekleme kaydında sağlayıcı, `not_before`, `recorded_at`, neden kodu, `active` ve `remaining_seconds` bulunur. `storage cleanup` önizlemede `plan` ve `apply_command`, uygulamada plan, silinen sayı, yedek ve işlem kaydını döndürür. Temizlenecek kayıt yoksa yedek/işlem kaydı oluşturulmaz. Önizleme değişikliği geçersiz girdi olarak çıkış 2 verir.

0.8 `inbox` çıktısı `items`, `total_count`, `unread_count`, `matching_count`, `next_before` ve `next_command` içerir. Her öğe `notification` ve güncel `finding` alanlarını taşır. `next_before` sonraki sayfanın sıralama sınırıdır; bildirim kimliği değildir. `inbox show` bir bildirimle ilgili `details` bulgu/gözlem/karar kayıtlarını verir. İşaretleme `notifications` ve `changed_count` döndürür. Arama JSON biçimi değişmez. `doctor` toplam ve okunmamış bildirim sayılarını da gösterir.

0.9 `status` çıktısı `observed_at`, `freshness_hours`, `domain_filter`, global sayaçlar, `displayed_asset_count`, `has_more_assets`, `assets`, `cooldowns`, `notes` ve kayıt klasörünü koruyan `commands` içerir. Her adresin `sources` listesinde `latest_attempt`, `last_complete`, `queued_count`, `freshness`, `age_seconds` ve gerekçeler bulunur. Güncellik `current`, `stale`, `never` veya `clock_error` olabilir. Beklemede `clock_error:true` ise `active` ve `remaining_seconds` değerlendirme için kullanılmaz. `status` çıkış 0/`ok:true`, özetin başarıyla okunduğunu belirtir; kaynakların sağlıklı olduğu anlamına gelmez. Mevcut komutların JSON biçimi değişmez.

0.10 `monitor start` tek final `report` ve `show_command` döndürür. `report.run.status` denemenin yaşam durumunu, `stop_reason` bitiş nedenini, `outcome` kayıtlı kaynak sonuçlarının özetini taşır. `sources` kaynak başına sayaçları içerir; `unknown_result_count` son sayı özeti olmayan başlamış denemeleri gösterir. Başlamayan çalışmalar `not_started` içinde kalır. Başlayan bütün denemeler tamamsa ve en az bir deneme varsa çıkış 0; kısmi/başarısız sonuçta çıkış 3 olur. Ctrl+C çıkış 130 verir; kayıt `monitor list/show` ile açılır. `monitor show` okuma başarılıysa çıkış 0 verir; `report`, sınırlı `entries`, `total_entries` ve `show_command` içerir. Deneme özeti güncel işin son tekrarını değil, bağlanan ilk denemeyi kullanır.

0.21 `surface watch` tek final `data` nesnesinde planlanan/tamamlanan turu, tamamlandı/kısmi/başarısız sayılarını, yeni aday/kanıt toplamlarını, bitiş nedenini ve küçük tur özetlerini döndürür. En az bir tur tamamlandıysa ve bütün tamamlanan turlar başarılıysa süre sınırında dursa da çıkış 0/`ok:true`; kısmi/başarısız veya hiç başlamayan sonuçta çıkış 3 olur. Ctrl+C çıkış 130 verir; bitmiş turlar `surface runs` geçmişindedir. JSON modunda bekleme ilerlemesi yazılmaz.

0.26 `inbox` öğelerinde kayıt türüne göre `finding`, `candidate` veya `change_evidence` alanını doldurur; diğerleri `null` kalır. Değişiklik kanıtı tür, kontrol kimliği, domain, değişen alanlar, eklenen/kaldırılan IP'ler ve varsa port geçişlerini taşır. `surface check`, `surface mail check` ve `surface services check` sonucu `notification_created` alanıyla bu kontrolün yerel bildirim oluşturup oluşturmadığını açıklar. `doctor` ayrıca `surface_change_notification_count` döndürür. Önceki JSON alanları korunur.

0.27 `surface monitor` tek final `data` nesnesinde seçilen kontrol türlerini, planlanan/tamamlanan tam turu, tamamlanan kontrol sayısını, tamamlandı/kısmi/başarısız sayılarını, yeni bildirim sayısını, bitiş nedenini ve her kalıcı kanıtın küçük adım özetini döndürür. En az bir tam tur bittiyse, yarım tur yoksa ve bütün sonuçlar tamamsa çıkış 0/`ok:true`; eksik, kısmi, başarısız veya hiç başlamayan sonuçta çıkış 3 olur. `Ctrl+C` çıkış 130 verir; daha önce yazılmış kanıtlar ve bildirimler korunur. JSON modunda bekleme ilerlemesi yazılmaz.

0.28 `surface freshness` tek final `data` nesnesinde değerlendirme zamanını, saat eşiğini, kapsam durumunu, dört güncellik sayacını ve sabit `web/mail/services` öğelerini döndürür. Her öğede `freshness`, saniye cinsinden yaş, kanıt kimliği/zamanı, `result_status`, son değişim türü ve açıklamalar bulunur. Kanıt yoksa kimlik/zaman/değişim `null`, sonuç `not_checked` olur. Komut başarılı bir salt okuma olduğundan eski veya alınmamış kanıt varlığında da çıkış 0/`ok:true` verir; bozuk zaman güvenli biçimde `clock_error` olarak görünür.

0.29 `surface inventory` tek final `data` nesnesinde kök kapsamını, bütün aday durum toplamlarını, seçilen filtredeki toplam/gösterilen sayısını ve adaylara bağlı kayıt/kapsam sayılarını döndürür. Her öğede `candidate_status`, `registration_status`, `scope_status`, `active_check_authorized` ve yalnız öneri olan `next_step` ayrı alanlardır. Filtreleme bu katmanları değiştirmez; komut başarılı salt okuma için çıkış 0/`ok:true` verir.

0.30 `surface discovery-status` son kayıtlı pasif keşif çalışmasını `source_status`, `result_status`, `outcome`, `coverage_complete`, `empty_result_confirmed`, güncellik ve yaş alanlarıyla açıklar. Son çalışma kimliği/sayıları, uyarı ve hata korunur. Kısmi veya başarısız çalışma `empty_result_confirmed:false` verir; komut internet ve yazma yapmadan başarılı salt okuma için çıkış 0/`ok:true` döndürür.

0.126 `surface discovery-status --source` aynı sözleşmeyi seçilen sağlayıcının son kaydıyla sınırlar. Yeni `surface discovery-health` sonucu sabit sağlayıcı sırasındaki `sources` listesini; tamamlanan/kısmi/başarısız/hiç çalışmamış ve kayıt güncelliği sayaçlarını taşır. Bir sağlayıcının tamamlanması diğerinin hatasını gizlemez. `surface source-evaluation` aktif kimlikleri, sürümlü ölçütleri ve ertelenen adaptör engellerini veri klasörü oluşturmadan döndürür. Üç komut da canlı ağ sağlığı iddiası üretmez; şema 54 değişmez.

0.31 `storage readiness` kullanım, klasör/disk toplamları, ihtiyatlı boş alan eşiği, yönetilen yedek envanteri, son yedek bütünlüğü/şema/yaş durumu ve saklama önizlemesini tek final `data` nesnesinde verir. `local_recovery_status`, ayrı ortam ve restore tatbikatı hakkında kanıt olmayan bilgiyi tamamlanmış saymaz. Dosya taraması ve SQLite doğrulaması salt okunurdur; başarılı görünüm çıkış 0/`ok:true` verir.

0.32 `surface exposures` son kayıtlı kanıtlardan `candidates`, `coverage`, kategori ve güncellik sayaçlarını tek final `data` nesnesinde verir. Her aday tür, kategori, başlık, özet, kanıt seviyesi/yaşı/kimliği, olgular, sınırlar ve sonraki adımı taşır. 0.33 ile son CNAME kanıtı da kapsama katılır; hedef NXDOMAIN ise yalnız kesin olmayan aday üretilir. 0.94 ile son pasif keşif çalışması aynı SQLite anlık görüntüsüne katılır; her kapsam öğesi uygulanabilir `next_command`, rapor da güncel/ilgilenilmeli/desteklenmeyen sayaçları ve gerekiyorsa `scope_next_command` taşır. Tamamlanmış boş kaynak yanıtı, kısmi yanıt ve kaynak hatası ayrı kalır. Açık panel veri gereksinimi `unsupported`, gerçek takeover doğrulaması ise kapsam dışı kalır. Aday olmaması güvenli sonuç sayılmaz; başarılı salt okuma çıkış 0/`ok:true` verir.

0.33 `surface cname check` sonucunda `status` ve eklemeli `check` kanıtı verir. Sonuçta takma ad/hedef durumu, sınırlı CNAME zinciri, terminal hedef, IP'ler, güvenli hata/notlar ve değişim alanları bulunur. Başarısız DNS kanıtı kaydedilir ve çıkış 3/`ok:false`; tamamlanan mevcut/yok/NXDOMAIN gözlemi çıkış 0 verir. `surface cname show` ve `surface exposures` yalnız kayıtlı kanıtı okur. Şema 16'dır; şema 1–15 açık `migrate` gerektirir.

0.34 `surface technologies` tek final `data` nesnesinde servis kanıtı kapsamını, açık port ipuçlarını ve CVE eşleştirme uygunluğunu verir. Her ipucunda uç nokta, yaygın kullanım, `hint` güveni, `tcp_connect_only` yöntemi, kanıt kimliği/zamanı/güncelliği ve sınırlar bulunur. Üretici/ürün/sürüm kanıt yokken `null`, `cve_match_eligible` ise `false` kalır. Komut salt okunur başarılı görünüm için çıkış 0/`ok:true` verir; şema 16 değişmez.

0.95 `ransomware recent` tek final `data` nesnesinde kaynak/akış zamanı, gün sayısı, kaynak kayıt sayısı, içerik SHA-256, lisans, yerel sorgu, durum filtresi, eşleşen/gösterilen sayıları ve sınırlı `claims` listesini verir. Her iddia grup, kuruluş, ülke, sektör, ilk/son gözlem, ilan durumu, varsa web bilgisi ve ham kaynak gönderisinin mevcut olup olmadığı işaretini taşır; gönderi URL'sini veya metnini taşımaz. Komut veritabanı oluşturmaz/yazmaz. Kaynak veya biçim hatası çıkış 3; geçersiz sorgu/limit çıkış 2; tam doğrulanmış akış çıkış 0/`ok:true` verir.

0.96 `ransomware refresh` tek final `data` nesnesinde kalıcı çalışma kanıtı, ilk-snapshot işareti, toplam/sınırlı öğeler ve `added/updated/unchanged/removed` sayaçlarını verir. `removed` yalnız kaydın kayan kaynak penceresinde artık bulunmadığını söyler. İlk başarılı snapshot sessiz başlangıç çizgisidir. Kaynak hatası `failed` çalışma olarak saklanır, önceki başarılı snapshot korunur ve çıkış 3/`ok:false` döner. `ransomware status` ağsız/salt-okunur son deneme, son başarılı snapshot ve sınırlı geçmiş görünümüdür. Ham leak-site URL'si hiçbir kalıcı öğede bulunmaz.

0.97 `ransomware watch-add/list/show/revoke/run/run-show` kuruluş/domain izleme tanımını, değişmez çalışma farkını ve varsa ortak kutu bildirim kimliğini döndürür. İlk veya değişmiş tanım çalışması sessizdir. Sonraki `added/updated` bildirim üretir; yalnız `removed` üretmez. Her çalışma kullandığı kaynak snapshot kimliğine bağlıdır.

0.98 `ransomware watch-refresh-all` tek final `data` nesnesinde kaynak yenileme kanıtını, planlanan/tamamlanan izleme sayısını, toplu fark sayaçlarını, bildirim sayısını ve sınırlı izleme özetlerini döndürür. Kaynak başarısızsa çıkış 3/`ok:false`, tamamlanan kaynak ve bütün izlemelerde çıkış 0/`ok:true` verir. Sınır aşımı veya bozuk yerel veri ağ isteğinden önce reddedilir. Bir izleme hatası çıkış 1 verir; daha önce atomik tamamlanan kaynak/izleme kayıtları korunur.

0.99 `ransomware watch-monitor` tek final `data` nesnesinde planlanan/tamamlanan turu, başarılı/başarısız kaynak turunu, tamamlanan ve sessiz başlangıç olan kuruluş/domain izleme sayılarını, tur bazlı fark/bildirim sayaçlarını, bitiş nedenini, geçen süreyi ve her kaynak çalışma kimliğini verir. Tur toplamları benzersiz eşleşme sayısı değildir. En az bir tur tamamlanmış ve kaynak hatası yoksa çıkış 0/`ok:true`; herhangi bir kaynak turu başarısızsa çıkış 3/`ok:false`; `Ctrl+C` çıkış 130 verir. Tamamlanan kaynak ve izleme kayıtları her durumda korunur.

0.22 `surface mail check` çıktısında `data.status` (`complete`, `partial`, `failed`) ve eklemeli `check` kanıtı bulunur. MX/SPF/DMARC durumları `present`, `missing`, `nxdomain` veya `failed`; değişim `baseline`, `unchanged` veya `changed` olur. Yalnız sorgu hatası `ok:false`/çıkış 3 üretir; kayıt bulunmaması üretmez. `surface mail show` kapsamı, sınırlı geçmişi ve toplam kontrol sayısını salt okunur döndürür.

Sorgu bağlantıları, arama zamanları, hatalar ve son adım veritabanında kalır. Her tamamlanan sorgu sonuç raporundan önce kaydedilir. İş kesilmişse bazı gözlemler zaten kaydedilmiş olabilir; tamamlanmamış denemeye sıfır sonuç uydurulmaz. Yeni kayıt sayıları yalnız ilgili denemeye aittir. Ham HTTP yanıtları henüz arşivlenmez.

Paketleme bilgisi `pyproject.toml` içindedir. Doğrulanan yol `./xti` ve `./scripts/check`; kurulmuş wheel dağıtımı henüz doğrulanmadı.

## Proje ve yol haritası

| Belge | İçerik |
|---|---|
| [Güncel durum](docs/STATUS.md) | Gerçekte çalışanlar, testler ve sonraki teslim |
| [Mimari](docs/ARCHITECTURE.md) | Ayrı bölümler ve veri koruma kararları |
| [İlk çalışma döngüleri](docs/roadmap/FIRST_ITERATIONS.md) | Öğrenme ve uygulama sırası |
| [Ana yol haritası](docs/roadmap/MASTER_ROADMAP.md) | Uzun vadeli ürün geliştirme planı |
| [Yetenek matrisi](docs/roadmap/CAPABILITY_MATRIX.md) | 122 hedef yetenek |
| [İş listesi](docs/roadmap/BACKLOG.md) | 73 iş paketi ve kabul koşulları |

Plan 14 faz içerir. Gerçek uygulama durumunu STATUS.md belirler; uzun vadeli hedefler tamamlanmış özellik sayılmaz.
