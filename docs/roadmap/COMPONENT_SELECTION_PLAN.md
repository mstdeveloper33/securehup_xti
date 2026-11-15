# XTI — Açık kaynak bileşen seçim planı

**Tarih:** 15 Kasım 2026. **Uygulama:** 0.143.0 / şema 66.
**Durum:** Uygulanan bileşenler ile araştırmaya dayalı plan tercihleri ayrı gösterilir.
Mevcut üç aracın ortak kimliği ve yerel kurulum kataloğu 0.140.0'da
[uygulandı](../COMPONENTS.md). 0.143.0 haber modülü feedparser 6.0.14 ve
feedparser-sgmllib 2.1.0 kullanır; mevcut üç aracın sürümleri korunur.
Diğer seçilmiş projeler ile test edilip kullanıma alınan sürümler ayrı durumlardır.

**Son kapsam kararı:** Uygulama backend'i, kullanıcı oturumu ve web mevcut
.NET platformundadır. Bu belge [motor planının](ENGINE_INTEGRATION_ROADMAP.md)
ENG-02 parçasıdır. XTI veri toplama/analiz ve kaynaklı kayıt motorudur.
Önceki FastAPI/Pydantic, Keycloak ve Cytoscape.js backend/panel tercihleri
bu repo için geri çekilmiştir. Her motor bileşeninin görevi sınırlıdır;
sonuçları ortak modele alınarak .NET'e kararlı sözleşmeyle sunulur.

Mevcut SQLite motorunun 11 maddelik sağlamlaştırma paketi tamamlandı.
Kaynaklar arası olay adaylarının ilk dilimi 0.141.0'da, kayıtlı genel
arama ve yerel bildirimleri 0.142.0'da uygulandı; yeni kütüphane
gerektirmedi. RSS/Atom haberlerinin ilk dilimi 0.143.0'da uygulandı.
Sonraki işler haberlerin toplama oturumuna bağlanması ve ölçülmüş katkıyla
kaynak genişlemesidir. Entegrasyon teslim
hazırlığı ile geniş paylaşım/LLM en sona kalır.
.NET adaptörü ve platform PostgreSQL yerleşimi/veri geçişi repoyu
kullanan ekibe aittir; bu repo sözleşme, örnek ve belge sağlar.

## 1. Net seçimler

| İş | Plan tercihi | Hangi parçası kullanılacak? | Zamanı ve durumu |
|---|---|---|---|
| Sosyal kullanıcı adı ve mevcut arşiv keşfi | Mevcut Sherlock, Maigret ve theHarvester adaptörleri | Şimdiden belirlenmiş kaynak/iş kapsamı | 0.140.0 ortak pin ve kurulum kataloğu var; mevcut sürümler korunur |
| Kaynaklar arası olay adayı | Mevcut XTI kaynak/domain/tarih kuralları | Kesin ve sınırlı noktalama düzenlemeli ad eşleştirmesi; ortak tam domain bağlamı | İlk dilim 0.141.0'da uygulandı; RapidFuzz gerekmedi ve kurulmadı. Yaklaşık ad benzerliği için ileride ölçümlü deney adayı |
| Kaydedilmiş genel arama ve bildirim | Mevcut XTI arama, CTI kayıtlı arama ve bildirim desenleri | Kalıcı kimlik, değişmez tam sonuç/kapsam, fark ve yerel bildirim | 0.142.0 on türde uygulandı; 0.143.0 haber türünü açıkça ekler, eski tanımlar kendi kapsamını korur |
| Haber/RSS/Atom okuma | **feedparser 6.0.14** + **feedparser-sgmllib 2.1.0** | XTI'nın indirdiği sınırlı yanıtı yalnız bellek akışından ayrıştırma | ENG-04 ilk teslimi 0.143.0'da CISA, UK NCSC ve CERT-FR için uygulandı |
| Haber sayfasından ana metin | **Trafilatura** | Önceden alınmış HTML'den metin/metadata çıkarma | RSS özeti yetersizse ikinci dilim; ilk haber tesliminin zorunlu parçası değil |
| Motor bağlantı sözleşmesi | Sürümlü motor istek/sonuç sözleşmesi | Motorun desteklediği veri ve işlemler için sözleşme, örnek ve belge | ENG-01/05; son aşamada teslim hazırlığı. .NET adaptörü/gerçek bağlantı kabulü tüketici ekibin işi |
| Geniş STIX nesne aktarımı | **stix2** | XTI kaydı ile standart nesneler arasında oluşturma/ayrıştırma | En sona ertelenen ENG-07 tercihi |
| Backend, giriş ve panel | Mevcut **.NET platformu** | Motor bu tarafa kaynaklı kayıt/analiz sunar | Bu repoda FastAPI/Keycloak/panel geliştirme işi yok |

Burada "seçildi", kullanılacak görev ve proje tercihini belirtir. Paket
sürümünün XTI'da çalıştığı veya özelliğin tamamlandığı anlamına gelmez.
Gerekli olmadığı kanıtlanan bileşen sırf listede yer aldığı için kurulmaz;
seçim değişirse gerekçe bu kayda eklenir.

## 2. İlk iki özellikte tekrar kullanılan yapı

Mevcut [genel arama](../../src/xti/application/global_search.py), 0.143.0
haber ekiyle on bir kayıt ailesini arar. [CTI kayıtlı aramalar](../../src/xti/application/cti_saved_searches.py)
tanım, çalışma ve fark desenini;
[ransomware karşılaştırması](../../src/xti/application/ransomware_source_comparison.py)
iki kaynağı gerekçeleriyle yan yana getirmeyi zaten sağlar.

### Uygulanan olay adayı dilimi ve ileride RapidFuzz değerlendirmesi

0.141.0, mevcut ransomware kesin karşılaştırmasını değiştirmeden tekrar
kullanır. ThreatCluster–RansomLook'ta aynı grup ve en fazla 72 saat
keşif farkı varsa kesin ad eşleşmesi “aynı olay olabilir” adayıdır.
Yeni dar ad kuralı yalnız NFKC/harf büyüklüğü, boşluk ve noktalama
düzenlemesi yapar; şirket eki veya sözcük çıkarmaz, harf çevirisi yapmaz.
Bu kural da aynı grup ve 72 saat koşulunu gerektirir. Eski kuralın diğer
eşleşmeleri yalnız kuruluş bağlamı olarak korunur.

ThreatCluster–HIBP tam website hostu/domain eşitliği yalnız ortak domain
bağlamıdır. Ana domain/alt domain veya `www` genişletmesi yapılmaz.
HIBP olay günü, kataloğa eklenme günü ve ransomware keşif zamanı aynı
tarih türü kabul edilmez. RansomLook domain taşımadığından HIBP ile ad
üzerinden veya üçüncü kaynağa geçişli bağ kurulmaz. Önceki insan kararı
özgün karşılaştırma kanıtına aittir; yeni adayın otomatik kararı olmaz.

`events candidates` terminal/JSON görünümü son başarılı yerel kayıtları
tek tutarlı okumada değerlendirir; domain filtresi ve sayfalama sunar.
Kaynak toplama ayrı işlemdir. Komut ağ veya veri yazımı yapmaz; 0.141.0
teslimi yeni engine v1 işlemi eklemedi ve şema 64'ü korudu. Kaynak iddiası
doğrulanmış ihlale dönüşmez; kayıt birleştirme ve alarm üretimi yoktur.

Bu ilk kapsam kesin kurallarla karşılandığı için RapidFuzz kurulmadı;
yaklaşık eşleştirme deneyi yapıldığı veya faydasının ölçüldüğü iddia
edilmez. İleride somut ad benzerliği ihtiyacı oluşursa RapidFuzz
bu dayanakların yanında yalnız ad/başlık benzerliğiyle aday
sıralayabilir. XTI normalleştirme, aday azaltma, eşik ve insan kararını
yönetir. İlk deneyde `fuzz.ratio` gibi tam metin karşılaştırması esas
alınır; seçilen yöntem ve sürümü sonuçta kaydedilir. Skor aynı olay olma
olasılığı değildir. Özellikle `token_set_ratio` bir metin diğerinin alt
kümesiyken 100 verebilir; bu değer kimlik veya olay eşitliği sayılmaz.
[Resmî davranış](https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html).

Mevcut [domain eşleştirme kuralları](../../src/xti/domain/matching.py),
IDN/public suffix davranışı ve kayıtlı kararlar topluca değiştirilmez.
İlk teslimde RapidFuzz çalışma bağımlılığı değildir; ileride yapılacak
ad benzerliği deneyi için sonuç ve kabul gerekçesi ayrıca saklanır.

Gelecekteki deneyde aynı isim/farklı kuruluş, aynı kuruluş/farklı olay,
Türkçe harfler, kısaltma, eski yeniden yayın ve çelişen tarihler bulunur. Ayarlama ve kabul
örnekleri ayrılır. Yeni doğru/yanlış aday, inceleme yükü, süre ve bellek
kesin kurallarla karşılaştırılır. Kabul eşikleri ölçümden önce iş kartına
yazılır; sonucu gördükten sonra kabul için değiştirilmez. Deney, otomatik
olay birleştirme veya alarm verme yetkisi kazandırmaz.

### Uygulanan genel arama izlemesi — 0.142.0

`search-watch` mevcut genel arama ve bildirim desenleriyle on kayıt
ailesini izler. Mevcut CTI kayıtlı arama şeması ve eski bildirim davranışı
değiştirilmedi; ayrı yaşam döngüsü ve kanıt kayıtları eklendi.

- Kalıcı kayıt kimliği ile her kaynak çalışmasının kimliği ayrılır.
  Örneğin [genel arama adaptöründe](../../src/xti/adapters/sqlite_global_search.py)
  sosyal sonuçların çalışma öğesi kimliği yenilenebilir. Aynı profil yeni
  bir çalışma kimliği aldı diye tekrar yeni eşleşme bildirimi çıkmaz.
- Tam sonuç aynı veritabanı okuma anından alınır. Ayrı zamanlarda alınan
  500'er satırlık ekran sayfaları birleştirilerek geçmiş oluşturulmaz.
  Görüntüleme sınırı saklanan karşılaştırmayı kesmez.
- İlk ölçüm, tanım değişikliği ve yeniden etkinleştirme sessizdir.
  Tanım sürümü, tam sonuç ve kaynak kapsamı çalışma kanıtında dondurulur;
  tekrar veya kaynak hatası tek başına yeni eşleşme sayılmaz.
- Bildirim yeni **veya anlamlı biçimde değişmiş** eşleşme içindir.
  Yalnız çıkarılma çalışma farkında kalır ve alarm üretmez. Mevcut CTI
  kayıtlı aramasının çıkarılmada da bildiren davranışı değiştirilmez.
- Şema 65, tanım/olay/snapshot/çalışma/bildirim için beş tablo ekler.
  `global_search_snapshots` aynı tam kanıtı içerik özetiyle tekilleştirir;
  öğe tablosu yoktur. Fark kaydedilmiş snapshot'lardan hesaplanır ve
  gerekli bildirim çalışma ile aynı transaction'da yazılır.
- Geçiş açık `migrate` ile benzersiz eski-sürüm yedeği aldıktan sonra
  yapılır. Okuma/kurulum otomatik geçiş yapmaz. Eski koda geri dönüş,
  önceki yedeği yeni veri yoluna restore ederek gerçekleştirilir;
  mevcut şema 65 verisinin üstüne yazılmaz.
- CLI/JSON ve ortak yerel inbox kullanılır. Sonlu `monitor` yalnız
  terminal açıkken yerel aramayı tekrarlar; internet toplaması veya
  daemon değildir. Yeni ağ API'si veya engine v1 işlemi eklenmedi.

Bu nedenle ilk iki özellik için Elasticsearch/OpenSearch, yeni bir grafik
veritabanı veya dinamik eklenti yükleme çatısı seçmiyoruz. Mevcut küçük
port/adaptör sınırları kullanılır. Arama kapasitesi ihtiyacı ayrıca ölçülür.

## 3. Seçilen diğer parçaların sınırları

**feedparser — uygulandı:** Kaynak listesi ve HTTP alma XTI'da kalır.
Sınırlı yanıt `io.BytesIO` üzerinden `feedparser.parse` ile ayrıştırılır;
URL veya yerel dosya yolu doğrudan parsere verilmez. CISA, UK NCSC ve
CERT-FR için kaynak, bağlantı, başlık, düz metin özet ve ayrı tarih
alanları saklanır. Makale sayfaları ve ekler otomatik alınmaz.
Akıştan düşen eski haber korunur; tekrar önleme, kaynak hatası ve genel
arama XTI'dadır. Bildirim açık `search-watch` çalışmasıyla mevcut inbox'a
girer. Paket haber kaynağı veya internet arama motoru değildir.
[0148 kararı](../decisions/0148-publisher-news-feeds.md),
[Resmî API](https://feedparser.readthedocs.io/en/latest/introduction/).

**Trafilatura:** `extract`/`bare_extraction` ile XTI'nın aldığı HTML işlenir.
Paketin indirme/crawler yetenekleri otomatik açılmaz. Çıkarılmış metin ham
kaynaktan ayrı saklanır; çıkarılan tarih doğrulanmış olay tarihi sayılmaz.
Tam metin ihtiyacı yoksa bağımlılık eklenmez.
[Resmî işlevler](https://trafilatura.readthedocs.io/en/latest/corefunctions.html).

**Backend/panel araştırması geri çekildi:** Önceki FastAPI/Pydantic,
Cytoscape.js ve OIDC/Keycloak tercihleri bu repo için kurulum hedefi
değildir. Mevcut .NET platformu kendi backend, kullanıcı ve arayüz
tercihlerini korur. Motor için gerektiğinde ince servis taşıma adaptörü
ayrı seçilebilir; bununla giriş/oturum sistemi yeniden kurulmaz.

**stix2:** OASIS'in Python bileşeni nesne oluşturma/ayrıştırma için
kullanılır. Söz diziminin doğru olması iddianın gerçekliği değildir.
XTI'daki aday ve gözlem otomatik zararlı `Indicator` olmaz; kimlik,
kaynak, tarih ve paylaşım işaretlerinin anlamı ayrıca doğrulanır.
Mevcut sınırlı IOC dışa aktarımı gerekçesiz yeniden yazılmaz.
[Resmî depo](https://github.com/oasis-open/cti-python-stix2).

**Kapsam uygulaması:** Kimlik ve rol .NET tarafında doğrulanır; motor
güvenilir çağrı bağlamındaki veri/iş sınırını uygular. Serbest kurum
etiketi yetki değildir; mevcut kuruluş grupları müşteri yalıtımı sayılmaz.

## 4. Şimdilik seçilmeyenler

| Bileşen | Karar | Yeniden değerlendirme koşulu |
|---|---|---|
| OpenCTI ve IntelOwl'un tamamı | İlk teslimin zorunlu bağımlılığı değil; kaynak kodları topluca taşınmaz | Bağımsız bileşenden daha çok ölçülmüş fayda; bütün işin XTI'da tamamlanması; lisans/veri/işletim kabulü |
| NetworkX | İlk olay adayı/genel arama işi için eklenmez | Gerçek çok adımlı yol/komşuluk algoritması ve Python sürüm uyumu ihtiyacı |
| taxii2-client | Şimdiden kesin bağımlılık seçilmez | TAXII istemcisi ihtiyacı, Python 3.11 kabulü ve gerçek karşı uç deneyi |
| Yeni genel arama motoru veya dinamik plugin çatısı | İlk iki özellik için eklenmez | Ölçülmüş arama kapasitesi veya üçüncü taraf eklenti yükleme gereksinimi |

NetworkX'in gözlenen güncel sürümü Python 3.12 ister; mevcut XTI tabanı
Python 3.11'dir. Sırf bir kütüphaneyi eklemek için destek tabanı değiştirilmez.
[Sürüm bilgisi](https://pypi.org/project/networkx/).
taxii2-client bir TAXII 2.0/2.1 **istemcisidir**, sunucu değildir. Yayın
metadata'sı Python 3.11 kabulünü tek başına doğrulamıyor; bu, paketin bozuk
olduğunu da kanıtlamaz. TAXII sunucusu seçimi paylaşım aşamasının ayrı
işidir. [Resmî belge](https://taxii2client.readthedocs.io/en/latest/),
[yayın bilgisi](https://pypi.org/project/taxii2-client/).

OpenCTI/IntelOwl araştırması yararlı yetenekleri ve bağlantı sözleşmelerini
belirlemek içindir. Paket olarak sunulmayan bir ürün iç modülünü doğrudan
kopyalamak bağımsız bir kütüphane kullanmakla eşit değildir; kendi veritabanı,
kuyruk ve yapılandırmasına bağlı olabilir. Somut modül seçilmeden kod
taşıma yapılmaz. Önce uygun bağımsız araç tercih edilir; bütün servis
seçilirse [0141 sınırları](../decisions/0141-enterprise-integration-first.md)
geçerlidir. Çalışan araştırma ve sonuç kaydı XTI'da kalır.

## 5. Yayın kanıtı ile kurulum kilidi ayrı

Aşağıdakiler 15 Kasım 2026'da resmî paket sayfalarındaki yayın bilgileridir.
Feedparser 6.0.14, aşağıda anlatılan 0.143.0 kurulumuna alınmıştır;
diğer araştırma satırları kurulmuş/test edilmiş sürüm sayılmaz. FastAPI
ve Pydantic satırları geri çekilen backend seçiminin tarihî araştırmasıdır.

| Paket | Gözlenen sürüm / yayın | Bildirilen Python tabanı | Lisans / kaynak |
|---|---|---|---|
| RapidFuzz | 3.14.6 / 30 Ağustos 2026 | ≥3.11 | MIT · [PyPI](https://pypi.org/project/RapidFuzz/) |
| feedparser | 6.0.14 / 30 Temmuz 2026 | ≥3.10 | BSD-2-Clause · [PyPI](https://pypi.org/project/feedparser/) |
| Trafilatura | 2.3.1 / 6 Ekim 2026 | ≥3.10 | Apache-2.0 · [PyPI](https://pypi.org/project/trafilatura/) |
| FastAPI — repo kapsamı dışı | 0.163.0 / 14 Kasım 2026 | ≥3.11 | MIT · [PyPI](https://pypi.org/project/fastapi/) |
| Pydantic — önceki tercih geri çekildi | 2.14.3 / 5 Kasım 2026 | ≥3.10 | MIT · [PyPI](https://pypi.org/project/pydantic/) |
| stix2 | 3.0.2 / 12 Şubat 2026 | ≥3.10 | BSD-3-Clause · [PyPI](https://pypi.org/project/stix2/) |
| NetworkX — ertelendi | 3.7 / 21 Eylül 2026 | ≥3.12; 3.14.1 hariç | BSD-3-Clause · [PyPI](https://pypi.org/project/networkx/) |
| taxii2-client — aday | 2.3.0 / 12 Mart 2021 | Yayın sınıfları 3.6–3.9; 3.11 kabulü yapılmadı | BSD-3-Clause · [PyPI](https://pypi.org/project/taxii2-client/) |

Cytoscape.js JavaScript bileşenidir; Keycloak ayrı kimlik servisidir.
Python uyumluluk tablosu onlara uygulanmaz. İkisi de bu reponun aktif
seçimi değildir; .NET platformuna bu araçları seçme zorunluluğu getirilmez.
[Cytoscape.js lisansı](https://github.com/cytoscape/cytoscape.js/blob/master/LICENSE),
[Keycloak deposu/lisansı](https://github.com/keycloak/keycloak).

Yayın tarihi bakım için bir kanıttır, güvenlik veya sorunsuzluk garantisi
değildir. Entegrasyon başlarken bakım/yayın durumu tekrar kontrol edilir.
Seçim yalnız yıldız sayısı veya "en yeni sürüm" etiketine dayanmaz.

## 6. Kurulum ve güncelleme planı

1. Bileşenin kaynağı, seçilen release/commit, lisansı, doğrudan/geçişli
   bağımlılıkları ve kullandığımız işlevleri kayda alınır. GitHub ana dalı
   ile yayımlanmış paket bağımlılıkları birbirine karıştırılmaz.
2. Ayrı geçici ortamda desteklenen Python sürümleri ve Linux kurulumu
   denenir; ağ gerektirmeyen eski işlevler ve isteğe bağlı modüller korunur.
3. Tam çözülmüş sürümler ve dosya bütünlükleri doğrulanıp uygun kilit kaydı
   oluşturulur. Haber okuyucusunun iki saf Python wheel'i için
   [requirements/news.txt](../../requirements/news.txt) sürüm/SHA-256 kaydı
   vardır; CI bu dosyayla yalnız doğrulanmış wheel'leri kurar.
4. Seçilen modülün kurulumu XTI reposundan yönetilir. Kullanıcı upstream
   repoyu geliştirmez; `main/latest` kendiliğinden güncellenmez. Yeni paket
   uygun aşamada [üçüncü taraf bildirimlerine](../../THIRD_PARTY_NOTICES.md)
   eklenir; haber okuyucusunun iki paketi bu bildirimde kayıtlıdır.
5. Güncellemede aynı kabul örnekleri, eski kayıtların okunması ve geri
   dönüş denenir. Bileşen hatası kaynağın boş/temiz sonucu sayılmaz.

Normal `./setup`, `news` ve `brand` eklerini aynı kurtarılabilir proje
ortamında kurar. Yeni haber bağımlılıkları yoksa mevcut ortam yerinde pip
ile değiştirilmez; önceki ortam korunarak yenisi oluşturulur ve doğrulanır.
`--check` eksik okuyucuyu reddeder, kendiliğinden kurmaz. `--core-only`
haber paketi indirmeyen çekirdek seçimi olarak kalır; eksik parser yalnız
haber toplamayı kontrollü kurulum hatasıyla durdurur. Saklı haber okuması
ve diğer çekirdek işlemler parser gerektirmez. Gerçek ortam/kurtarma
kabulünün sonucu [STATUS](../STATUS.md) içindedir.

Somut bağımlılık farkı: feedparser 6.0.14 yayını `feedparser-sgmllib`
gerektirir; XTI'da bu bağımlılık 2.1.0'a sabitlendi. Trafilatura 2.3.1 ise lxml ve ek ayrıştırma/ağ yardımcılarıyla
daha geniş bir bağımlılık kümesi getirir; bu nedenle ilk RSS işi için
ikisini birlikte kurma kararı verilmez.
[feedparser release metadata](https://pypi.org/pypi/feedparser/6.0.14/json),
[Trafilatura release metadata](https://pypi.org/pypi/trafilatura/2.3.1/json).

## 7. Bu seçimden sonraki teslim

[Motor planındaki](ENGINE_INTEGRATION_ROADMAP.md) mevcut STB paketi
tamamlandı. Olay adaylarının ilk dilimi 0.141.0'da, genel kayıtlı arama
ve yerel bildirimleri 0.142.0'da ek bağımlılık olmadan uygulandı. 0.143.0,
ilk üç RSS/Atom kaynağını hazır ayrıştırıcıyla bağladı. Sonraki işler
haberlerin toplu/zamanlı toplama oturumuna katılması ve ölçülmüş veri
boşluğuna kaynak eklenmesidir; bunlar henüz uygulanmadı.
Yaklaşık ad eşleştirmesi ancak yeni ihtiyaç ve
ölçülmüş faydayla ele alınır. Tercihler somut katkı/kabul koşullarıyla yeniden değerlendirilir.
ENG-01'in yerel okuma sınırı 0.139.0'da
[uygulandı](../ENGINE_CONTRACT.md); ENG-02 mevcut araç düzeni 0.140.0'da
[kataloğa](../COMPONENTS.md) bağlandı. 0.140.1 doğrulama/belge düzeltmesidir.
Entegrasyon teslim hazırlığı ve paylaşım/LLM en sondadır; gerçek .NET
bağlantısı, backend/panel ve platform PostgreSQL işleri tüketici ekibe aittir.

Haber okuyucusu dışındaki yeni kütüphane tercihleri hâlâ plandır;
yaklaşık benzerlik, tam makale çıkarımı ve geniş paylaşım bu seçim
belgesiyle uygulanmış sayılmaz. Araştırma ve yerel kod incelemesi entegre
bileşenlerin gerçek kabul testinden ayrıdır. Ücretsiz yayın erişimi
sürekli hizmet veya sınırsız yeniden kullanım garantisi değildir.
