# XTI — Açık kaynak bileşen seçim planı

**Tarih:** 15 Kasım 2026. **Uygulama:** 0.138.0 / şema 64.
**Durum:** Hazır bileşen seçimi için araştırmaya dayalı plan tercihleri.
Yeni paket kurulmadı, bağımlılık dosyası veya kullanıcı verisi değiştirilmedi.
Seçilen proje ile test edilip kullanıma alınan sürüm ayrı durumlardır.

Kullanıcı diğer özellikleri uygulamadan önce hazır bileşen seçimini
netleştirmek istiyor. Bu belge [kurumsal planın](ENTERPRISE_INTEGRATION_PLAN.md)
EIP-01 parçasıdır. Tek ürün, kullanıcı akışı ve ana kayıt merkezi XTI'dır.
Her bileşenin görevi sınırlıdır; sonuçları XTI modeline alınır.

## 1. Net seçimler

| İş | Plan tercihi | Hangi parçası kullanılacak? | Zamanı ve durumu |
|---|---|---|---|
| Sosyal kullanıcı adı ve mevcut arşiv keşfi | Mevcut Sherlock, Maigret ve theHarvester adaptörleri | Şimdiden belirlenmiş kaynak/iş kapsamı | Kullanılan mevcut entegrasyonlar korunur |
| Kaynaklar arası olay adayı | XTI kaynak/domain/tarih kuralları; ek ad benzerliği için **RapidFuzz** | Yalnız ad/başlık benzerliği hesaplama ve aday sıralama | İlk dar karşılaştırma deneyi için seçildi; fayda kabulünden önce üretime alınmaz |
| Kaydedilmiş genel arama ve bildirim | Mevcut XTI arama, CTI kayıtlı arama ve bildirim desenleri | On kayıt türü için kalıcı kimlik, tam sonuç farkı ve bildirim | Yeni arama motoru/harici platform eklenmez; onaylı EIP-05 |
| Haber/RSS/Atom okuma | **feedparser** | XTI'nın indirdiği sınırlı yanıtı ayrıştırma | Haber modülü EIP-06 için seçildi |
| Haber sayfasından ana metin | **Trafilatura** | Önceden alınmış HTML'den metin/metadata çıkarma | RSS özeti yetersizse ikinci dilim; ilk haber tesliminin zorunlu parçası değil |
| Kendi API'miz | **FastAPI + Pydantic** | Mevcut uygulama servislerini çağıran API; istek/yanıt doğrulaması | API aşaması EIP-07 için seçildi |
| Kendi panelimizde ilişki grafiği | **Cytoscape.js** | XTI'nın sunduğu düğüm/ilişkileri çizme ve kullanıcı etkileşimi | React aşaması EIP-07 için seçildi; bugün terminale eklenmez |
| Geniş STIX nesne aktarımı | **stix2** | XTI kaydı ile standart nesneler arasında oluşturma/ayrıştırma | Paylaşım aşaması EIP-08 için seçildi |
| Kurumsal giriş | **OpenID Connect** bağlantısı; referans sağlayıcı **Keycloak** | Kimlik, oturum ve çok faktörlü doğrulama | Ekip aşaması; kurumun uygun mevcut sağlayıcısı kullanılabilir, XTI veri yetkisi uygulamada kalır |

Burada "seçildi", kullanılacak görev ve proje tercihini belirtir. Paket
sürümünün XTI'da çalıştığı veya özelliğin tamamlandığı anlamına gelmez.
Gerekli olmadığı kanıtlanan bileşen sırf listede yer aldığı için kurulmaz;
seçim değişirse gerekçe bu kayda eklenir.

## 2. İlk iki özellikte neyi tekrar kullanacağız?

Mevcut [genel arama](../../src/xti/application/global_search.py) on kayıt
ailesini arar. [CTI kayıtlı aramalar](../../src/xti/application/cti_saved_searches.py)
tanım, çalışma ve fark desenini;
[ransomware karşılaştırması](../../src/xti/application/ransomware_source_comparison.py)
iki kaynağı gerekçeleriyle yan yana getirmeyi zaten sağlar.

### Olay adayı ve RapidFuzz

İlk dayanaklar tam domain, açık kuruluş bağlantısı, özgün kaynak kimliği
ve anlamı korunmuş tarih alanlarıdır. HIBP olay günü, kataloğa eklenme günü
ve ransomware keşif zamanı aynı tarih türü kabul edilmez. Kaynak iddiası
doğrulanmış ihlale dönüşmez; aynı kuruluşun iki olayı ayrı kalabilir.

RapidFuzz bu dayanakların yanında yalnız ad/başlık benzerliğiyle aday
sıralayabilir. XTI normalleştirme, aday azaltma, eşik ve insan kararını
yönetir. İlk deneyde `fuzz.ratio` gibi tam metin karşılaştırması esas
alınır; seçilen yöntem ve sürümü sonuçta kaydedilir. Skor aynı olay olma
olasılığı değildir. Özellikle `token_set_ratio` bir metin diğerinin alt
kümesiyken 100 verebilir; bu değer kimlik veya olay eşitliği sayılmaz.
[Resmî davranış](https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html).

Mevcut [domain eşleştirme kuralları](../../src/xti/domain/matching.py),
IDN/public suffix davranışı ve kayıtlı kararlar topluca değiştirilmez.
Kesin kurallar ilk teslimi karşılıyorsa RapidFuzz çalışma bağımlılığı
olmaz; yeni ad benzerliği ihtiyacı için deney sonucu saklanır.

Deneyde aynı isim/farklı kuruluş, aynı kuruluş/farklı olay, Türkçe harfler,
kısaltma, eski yeniden yayın ve çelişen tarihler bulunur. Ayarlama ve kabul
örnekleri ayrılır. Yeni doğru/yanlış aday, inceleme yükü, süre ve bellek
kesin kurallarla karşılaştırılır. Kabul eşikleri ölçümden önce iş kartına
yazılır; sonucu gördükten sonra kabul için değiştirilmez. Deney, otomatik
olay birleştirme veya alarm verme yetkisi kazandırmaz.

### Genel arama: eksik iş bir paketle çözülmüyor

Arama ve bildirim mekanizmaları mevcut; yeni iş genel aramayı güvenilir
bir izleme tanımına dönüştürmektir. Mevcut CTI kayıtlı arama şeması CTI
türlerine bağlıdır; bütün türlere sessizce genişletilmez.

- Kalıcı kayıt kimliği ile her kaynak çalışmasının kimliği ayrılır.
  Örneğin [genel arama adaptöründe](../../src/xti/adapters/sqlite_global_search.py)
  sosyal sonuçların çalışma öğesi kimliği yenilenebilir. Aynı profil yeni
  bir çalışma kimliği aldı diye tekrar yeni eşleşme bildirimi çıkmamalı.
- Tam sonuç aynı veritabanı okuma anından alınır. Ayrı zamanlarda alınan
  500'er satırlık ekran sayfaları birleştirilerek geçmiş oluşturulmaz.
  Görüntüleme sınırı saklanan karşılaştırmayı kesmez.
- İlk ölçüm sessizdir; tekrar ve kaynak hatası yeni sonuç/kaybolma sayılmaz.
  Sorgu revizyonu, kanıt, fark ve bildirim aynı kayıt kurallarını izler.
- İlk genel arama izlemesinde bildirim yalnız yeni eşleşme içindir;
  içerik değişimi ve çıkarılma çalışma farkında gösterilir. Mevcut CTI
  kayıtlı aramasının çıkarılmada da bildiren davranışı aynen kopyalanmaz
  ve eski CTI davranışı bu yeni özellik nedeniyle değiştirilmez.
- Kalıcı iş/çalışma ve bildirim tutarlılığı, yeniden başlatma ve yedekli
  şema geçişi korunur. Yeni tablo gerekiyorsa açık migration yapılır.

Bu nedenle ilk iki özellik için Elasticsearch/OpenSearch, yeni bir grafik
veritabanı veya dinamik eklenti yükleme çatısı seçmiyoruz. Mevcut küçük
port/adaptör sınırları kullanılır. Arama kapasitesi ihtiyacı ayrıca ölçülür.

## 3. Seçilen diğer parçaların sınırları

**feedparser:** Kaynak listesi ve HTTP alma XTI'da kalır. Sınırlı yanıt
`feedparser.parse` ile ayrıştırılıp kaynak, adres, başlık, tarih ve özet
alanlarına dönüştürülür. Paket haber kaynağı veya internet arama motoru
değildir. Tekrar önleme, kuruluş eşleştirme, kaynak hatası ve bildirim XTI'dır.
[Resmî API](https://feedparser.readthedocs.io/en/latest/introduction/).

**Trafilatura:** `extract`/`bare_extraction` ile XTI'nın aldığı HTML işlenir.
Paketin indirme/crawler yetenekleri otomatik açılmaz. Çıkarılmış metin ham
kaynaktan ayrı saklanır; çıkarılan tarih doğrulanmış olay tarihi sayılmaz.
Tam metin ihtiyacı yoksa bağımlılık eklenmez.
[Resmî işlevler](https://trafilatura.readthedocs.io/en/latest/corefunctions.html).

**FastAPI/Pydantic:** Terminal ve API aynı uygulama servislerini çağırır.
Pydantic ağ sınırındaki istek/yanıt modellerinde kullanılır; mevcut domain
modelleri ve tarihî kanıt biçimleri dönüştürülmez. Kesin kimlik/tarih/tür
alanlarında örtük dönüşüm yerine açık doğrulama uygulanır. API eklemek,
veritabanını veya mevcut migration düzenini değiştirmeyi gerektirmez.
[FastAPI veritabanı sınırı](https://fastapi.tiangolo.com/tutorial/sql-databases/),
[Pydantic doğrulama](https://docs.pydantic.dev/latest/concepts/strict_mode/).

**Cytoscape.js:** MIT lisanslı grafik görselleştirme/analiz kütüphanesi
kendi React deneyimimizin bir parçası olur. Sunucu yalnız kullanıcının
görebildiği, boyutu sınırlı ilişki kümesini verir. Grafik çizimi yeni ilişki
kanıtı, veritabanı veya müşteri yetkisi oluşturmaz; seçim ve inceleme XTI
kayıtlarına bağlanır. Ayrı ürün paneli veya grafik SaaS'ı gerekmez.
[Resmî belge](https://js.cytoscape.org/).

**stix2:** OASIS'in Python bileşeni nesne oluşturma/ayrıştırma için
kullanılır. Söz diziminin doğru olması iddianın gerçekliği değildir.
XTI'daki aday ve gözlem otomatik zararlı `Indicator` olmaz; kimlik,
kaynak, tarih ve paylaşım işaretlerinin anlamı ayrıca doğrulanır.
Mevcut sınırlı IOC dışa aktarımı gerekçesiz yeniden yazılmaz.
[Resmî depo](https://github.com/oasis-open/cti-python-stix2).

**OIDC/Keycloak:** XTI standart kimlik bağlantısını kullanır. Referans
kurulum Keycloak olabilir; kullanıcı kapsamı, müşteri ayrımı, veri sorgusu
ve arka plan işi yetkisi XTI'nın sorumluluğudur. Ekip aşamasında ayrı
kurulum/işletim kabulü gerekir; Python paketini eklemekle tamamlanmaz.
[Resmî entegrasyon rehberi](https://www.keycloak.org/securing-apps/overview).

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

Aşağıdakiler 15 Kasım 2026'da resmî paket sayfalarındaki yayın bilgileridir;
XTI'da kurulmuş, test edilmiş veya kilitlenmiş sürümler değildir.

| Paket | Gözlenen sürüm / yayın | Bildirilen Python tabanı | Lisans / kaynak |
|---|---|---|---|
| RapidFuzz | 3.14.6 / 30 Ağustos 2026 | ≥3.11 | MIT · [PyPI](https://pypi.org/project/RapidFuzz/) |
| feedparser | 6.0.14 / 30 Temmuz 2026 | ≥3.10 | BSD-2-Clause · [PyPI](https://pypi.org/project/feedparser/) |
| Trafilatura | 2.3.1 / 6 Ekim 2026 | ≥3.10 | Apache-2.0 · [PyPI](https://pypi.org/project/trafilatura/) |
| FastAPI | 0.163.0 / 14 Kasım 2026 | ≥3.11 | MIT · [PyPI](https://pypi.org/project/fastapi/) |
| Pydantic | 2.14.3 / 5 Kasım 2026 | ≥3.10 | MIT · [PyPI](https://pypi.org/project/pydantic/) |
| stix2 | 3.0.2 / 12 Şubat 2026 | ≥3.10 | BSD-3-Clause · [PyPI](https://pypi.org/project/stix2/) |
| NetworkX — ertelendi | 3.7 / 21 Eylül 2026 | ≥3.12; 3.14.1 hariç | BSD-3-Clause · [PyPI](https://pypi.org/project/networkx/) |
| taxii2-client — aday | 2.3.0 / 12 Mart 2021 | Yayın sınıfları 3.6–3.9; 3.11 kabulü yapılmadı | BSD-3-Clause · [PyPI](https://pypi.org/project/taxii2-client/) |

Cytoscape.js JavaScript bileşenidir; Keycloak ayrı kimlik servisidir.
Python uyumluluk tablosu onlara uygulanmaz. Sürümleri kendi aşamalarında
tarayıcı/Node veya protokol/sunucu uyumuyla seçilir.
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
   oluşturulur. Bugün bir kurulum kilidi oluşturulmuş değildir.
4. Seçilen modülün kurulumu XTI reposundan yönetilir. Kullanıcı upstream
   repoyu geliştirmez; `main/latest` kendiliğinden güncellenmez. Yeni paket
   uygun aşamada [üçüncü taraf bildirimlerine](../../THIRD_PARTY_NOTICES.md)
   eklenir; bu plan henüz kurulu bağımlılık bildirimini değiştirmez.
5. Güncellemede aynı kabul örnekleri, eski kayıtların okunması ve geri
   dönüş denenir. Bileşen hatası kaynağın boş/temiz sonucu sayılmaz.

Somut bağımlılık farkı: feedparser 6.0.14 yayını `feedparser-sgmllib`
gerektirir. Trafilatura 2.3.1 ise lxml ve ek ayrıştırma/ağ yardımcılarıyla
daha geniş bir bağımlılık kümesi getirir; bu nedenle ilk RSS işi için
ikisini birlikte kurma kararı verilmez.
[feedparser release metadata](https://pypi.org/pypi/feedparser/6.0.14/json),
[Trafilatura release metadata](https://pypi.org/pypi/trafilatura/2.3.1/json).

## 7. Bu seçimden sonraki teslim

Önce onaylı olay adayları için mevcut kesin kuralların karşılaştırma
örnekleri ve RapidFuzz deneyi hazırlanır. Yarar gösterilirse dar benzerlik
adaptörü eklenir; kalıcı olay kimliği ve karar XTI'da kalır. Genel kayıtlı
arama işi mevcut altyapıyla paralel ilerler. Haber modülü başladığında
feedparser kullanılır. API, panel ve paylaşım paketleri kendi aşamalarında
eklenir; bugün hepsinin kurulması planlanmaz.

Bu belgede özellik uygulaması, canlı hedef sorgusu, ücretli hizmet açılması
veya bağımlılık değişikliği yapılmadı. Belge araştırması ve yerel kod
incelemesi, entegrasyon kabul testi olarak sunulmaz.
