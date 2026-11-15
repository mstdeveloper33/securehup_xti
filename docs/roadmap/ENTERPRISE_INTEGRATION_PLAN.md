# XTI — Kurumsal kullanım ve entegrasyon yol haritası

**Karar tarihi:** 15 Kasım 2026. **Mevcut uygulama:** 0.138.0 / şema 64.
**Durum:** Kullanıcının kurumsal hedefi ve entegrasyon önceliği kabul edildi;
bu belgede planlanan bağlantılar henüz uygulanmadı veya kurulmadı.

Bu plan bundan sonraki teslim sırasını belirler. Ana roadmap ve backlog'daki
eski kişisel kullanım önceliğini günceller; çalışan kapsamı değiştirmez.
Gerçek teslimlerin kaydı [STATUS](../STATUS.md), mimari karar
[0141](../decisions/0141-enterprise-integration-first.md) içindedir.

## 1. Hedef ve değişmeyen sınırlar

Hedef, analistlerin ve daha sonra birden fazla müşterinin kullanabileceği
kurumsal XTI platformudur. OpenCTI ve IntelOwl'un uygun işlevlerinden
yararlanılır; mevcut bir yeteneği yeniden yazmak ancak somut gerekçeyle
seçilir. Ürünümüzün katkısı izleme kapsamını, dış risk gözlemlerini, kaynaklı
kanıtı, değişiklikleri ve insan incelemesini tek iş akışına bağlamaktır.

Bugün ücretsiz yerel kullanım sürer. Kurumsal hedef; bütün servisleri bugün
kurma, ücretli API açma veya mevcut veriyi dışarı gönderme talimatı değildir.
Gelecekteki sunucu, veri erişimi, lisans ve işletim bütçeleri ayrı ölçülür.

- Savunmacı OSINT yönü korunur. Saldırı, istismar, otomatik engelleme veya
  yama yükleme eklenmez. Yeni aktif kontrol ve dosya gönderimi bir analiz
  platformunun kurulmasıyla kendiliğinden açılmaz.
- Sunucu içi envanter, ürün/sürüm, paket ve CVE/KEV/EPSS geliştirmesi aktif
  kapsam dışıdır. Eski veriler uyumluluk için korunur.
- Otomatik HTML rapor arşivi kaldırılmıştır. Elle HTML dışa aktarma kalır.
- API/React, takım ve paylaşım özellikleri artık aşağıdaki somut kurumsal
  aşamalardadır. E-posta/SMS, geniş marka ve takedown ayrı teslimlerdir.
- LLM isteğe bağlı gelecekteki yardımcıdır; kaynak veya doğrulama yerine
  geçmez. [Mevcut LLM planının](LLM_PLAN.md) kanıt ve yetki sınırları korunur.

## 2. Hangi işi hangi parça yapacak?

| Parça | Görevi | XTI'da koruyacağımız sorumluluk | Başlangıç kararı |
|---|---|---|---|
| XTI | Domain/kuruluş/tedarikçi izleme, özgün kanıt, farklar, insan kararları ve vaka akışı | Asıl izleme ve karar geçmişi; ortak terminal ve ileride React deneyimi | Mevcut ürün geliştirilir |
| OpenCTI | Ayrıntılı CTI bilgisi, aktör/kampanya/malware ilişkileri, araştırma ve paylaşım | Kapsam seçimi, paylaşım izni, kaynak kökeni, uzak kimlik ve aktarım geçmişi | CE ile ayrı tek kuruluş laboratuvarı |
| IntelOwl | Seçilmiş araçlarla IP/domain/hash hakkında ek analiz ve kaynak sorgusu | Hangi analizin hangi veriyi nereye göndereceği, sonuç kanıtı ve hata durumu | Ayrı laboratuvarda dar pasif profil |
| Mevcut Sherlock/Maigret/theHarvester adaptörleri | Mevcut sınırlar içinde sosyal kullanıcı adı ve arşiv keşfi | Kapsam, kurulum sürümü, kaynak hatası ve insan değerlendirmesi | Korunur; aynı işi ikinci kez çalıştırmayız |
| Kimlik sağlayıcısı | Giriş, kurum hesabı, çok faktörlü doğrulama ve oturum | Her veri/iş için XTI erişim kararı ve müşteri kapsamı | Ekip aşamasında mevcut kurumsal sağlayıcı veya Keycloak değerlendirilir |
| Diğer platformlar | MISP paylaşımı veya kurumun vaka/SIEM sistemi gibi somut ihtiyaç | Açık veri yönü ve tek asıl kayıt sorumlusu | Gereksinim çıktığında; ilk kuruluma topluca eklenmez |

OpenCTI resmî GraphQL API ve Python istemcisi sunar. IntelOwl resmî REST
API ve Python istemcisi sunar. Büyük platformların kodunu ana repoya
kopyalamak yerine bu desteklenen bağlantı yolları değerlendirilir.
[OpenCTI API](https://docs.opencti.io/latest/reference/api/),
[PyCTI](https://docs.opencti.io/latest/development/python/),
[IntelOwl istemcisi](https://intelowlproject.github.io/docs/pyintelowl/).

Keycloak kimlik hizmeti adayıdır; onu kurmak XTI verisine erişim kurallarını
kendiliğinden tamamlamaz. MISP ise paylaşım ihtiyacı oluşursa değerlendirilir.
[Keycloak](https://www.keycloak.org/), [MISP](https://www.misp-project.org/).

## 3. Kurulum ve mimari

Aşağıdaki çizim hedef tasarımdır; bugün bağlı servisleri göstermez.

```mermaid
flowchart LR
    CLI[Terminal] --> XTI[XTI uygulama servisleri]
    UI[Gelecekte React] --> API[Kimlik ve kapsam denetimli XTI API]
    API --> XTI
    XTI --> LOCAL[İzleme, kanıt, karar ve vaka deposu]
    XTI --> BRIDGE[Bağımsız entegrasyon adaptörleri]
    BRIDGE --> CTI[OpenCTI servisi]
    BRIDGE --> OWL[IntelOwl servisi]
```

- **Yerel profil:** Bugünkü kolay kurulum korunur. OpenCTI, IntelOwl veya
  Docker zorunlu olmaz. Entegrasyonlar kapalıyken mevcut işler çalışır.
- **Entegrasyon laboratuvarı:** Ayrı veri alanı, sürümü sabit servisler,
  örnek veriler ve görünür kaynak tüketimi. Önce servisler ayrı denenir;
  birleşik kurulumun ihtiyacı daha sonra ölçülür. Python istemcisinin
  kurulması dış platformun sunucusunu kurmuş sayılmaz.
- **Tek kuruluş ekip kurulumu:** Kimlik, yetki, API/React, işletim ve kurtarma
  kabulünden sonra ayrı dağıtım profili. Kurumun mevcut servislerine bağlanma
  seçeneği de bulunur.
- **Çok müşteri kurulumu:** Ayrı müşteri dağıtımları başlangıç adayıdır.
  Ortak servis kullanımı ancak uçtan uca ayrım ve maliyet doğrulanınca seçilir.

İş mantığı dış SDK'ları veya dış veritabanı şemasını bilmez. Okuma,
analiz isteği ve paylaşım ayrı küçük sözleşmelerdir. Dış veritabanına
doğrudan yazılmaz. Her platformun kendi bağımlılıkları ayrı tutulur;
XTI'nin mevcut Python ortamına bütün analiz araçları yüklenmez.

OpenCTI'nin kendi arama, kuyruk, önbellek ve nesne depolama bileşenleri;
IntelOwl'un kendi veritabanı ve iş çalıştırıcıları vardır. Bu, XTI'ye de
hemen Kafka veya ikinci bir arama kümesi ekleme gerekçesi değildir.
[OpenCTI dağıtımı](https://docs.opencti.io/latest/deployment/overview/),
[IntelOwl kurulumu](https://intelowlproject.github.io/docs/IntelOwl/installation/).

## 4. Verinin ve kararın sahibi

| Kayıt | Asıl kayıt / değişiklik sahibi | Bağlantı davranışı |
|---|---|---|
| İzlenen varlık, kapsam, tedarikçi, kullanıcı tercihi | XTI | Dış platformdaki aynı ad izleme kapsamını değiştirmez |
| Özgün gözlem, kaynak cevabı ve tarihî kanıt | Toplama kaynağı + XTI kanıt kaydı | Paylaşılmış görünüm yerel kanıtın yerine geçmez |
| İnsan kararı, vaka durumu ve görev | İlk aşamada XTI | OpenCTI çıkarımı veya analiz sonucu vakayı kapatmaz |
| IntelOwl analiz raporu | IntelOwl işi ve asıl analiz sağlayıcısı | İzinli gerekli sonuç XTI'da tarihli dış analiz kanıtı olur |
| OpenCTI'den alınan ilişki/rapor | OpenCTI kaydı ve onun özgün kaynağı | Ayrı dış bağlam olarak alınır; otomatik kesin atıf yapılmaz |
| Teslim/alım, uzak kimlik eşlemesi ve hata | XTI entegrasyon kaydı | Tekrar, belirsizlik, kısmi başarı ve yeniden deneme görünürdür |

İlk entegrasyonda her alanın çift yönlü düzenlenmesi hedeflenmez. XTI'dan
seçili veri gönderme ve dış bağlam okuma ayrı işlemlerdir. Yerel ve uzak
kimlikler ile kurum/kurulum/kaynak/sürüm eşlemesi tutulur. Uzak silme veya
birleştirme yerel geçmişi silmez; açık bir dış olay olarak kaydedilir.

Aynı MITRE veya IOC kaydının doğrudan ve OpenCTI üzerinden gelmesi iki
bağımsız kaynak teyidi sayılmaz. Aracı servis ile asıl kaynak ayrı tutulur.
Yalnız isim benzerliği kayıt birleştirme gerekçesi olmaz. Benzer domain
adayı STIX'e aktarılınca kendiliğinden zararlı `Indicator` sayılmaz;
desteklenen gözlem ve rapor türleri anlamlarına uygun eşlenir.

Kaynak, gözlem/yayın/alınma tarihleri, belirsizlik, paylaşım işaretleri,
lisans/atıf ve dönüşüm sürümü taşınır. Dış bağlantı sonradan kaybolabileceği
için vaka kanıtı yalnız o bağlantıya bırakılmaz; saklama izni çerçevesinde
gerekli anlık kanıt korunur. Dışarıdan gelen karar yerel insan kararından
ayrı görünür. Kurumun vaka sistemi ileride asıl kayıt olacaksa bu geçiş
ayrı kararla, geçmiş ve kimlik eşlemesi korunarak yapılır.

## 5. Sıralı teslimler

Her satır ayrı, küçük sürümlere ayrılır. Süre tahmini donanım ve laboratuvar
sonuçları görülmeden verilmez. “Bağlandı” demek için gerçek servis kabulü
gerekir; yalnız sahte yanıtla geçen test yeterli değildir.

| İş | Somut teslim | Önkoşul ve tamamlanma kanıtı |
|---|---|---|
| **EIP-01 — Sınırlar ve karşılaştırma** | Görev paylaşımı, kabul senaryoları, lisans/erişim/sürüm kayıt şablonu, pilot iş yükü | Bu belge sınır kararını kaydeder. Donanım, ilk iş yükü ve sürüm seçimi hâlâ açıktır |
| **EIP-02 — IntelOwl denemesi** | Tek izinli pasif analiz, rapor okuma ve XTI örneğine bağlama | EIP-01; önce rapor okuma, sonra hassas olmayan örnekte gerçek sorgu. Eklenti kapsamı, hata ve tüketim ölçülür |
| **EIP-03 — OpenCTI denemesi** | Seçili kamu/örnek kanıtını CE'ye aktarma; sınırlı salt okunur ilişki bağlamı alma | EIP-01; kaynak/tarih/anlam korunur, tekrar veri çoğaltmaz, uzak kimlik görünür. IntelOwl başarısı teknik önkoşul değildir |
| **EIP-04 — Kalıcı bağlantılar** | Doğrulanmış prototipleri sürümlü adaptör, kalıcı iş/teslim kaydı, hata/kota/güncellik görünümü ve kurtarmaya dönüştürme | İlgili platformun EIP-02 veya EIP-03 kabulü; kesinti, cevap kaybı, yeniden başlatma ve servis kapalıyken yerel kullanım testleri; gerçek Linux kabulü |
| **EIP-05 — Onaylı 1 ve 2** | Kaynaklar arası olay adayları; platform genelinde kaydedilmiş aramalar ve yeni eşleşme bildirimleri | EIP-01 veri/sahiplik sözleşmesi. EIP-04 canlı kabulünü beklemek zorunda değildir; mevcut kanıtlarla ve entegrasyon kapalıyken çalışır |
| **EIP-06 — Kaynak kapsamı** | Önce haber/RSS; sonra ölçülmüş boşluğa göre yeni açık kaynak adaptörleri | EIP-01 kaynak kaydı; her kaynakta erişim, ek katkı ve hata/sıfır ayrımı. İlk bağlantılar doğrulanınca paralel ilerleyebilir |
| **EIP-07 — Tek kuruluşta ekip** | Sürümlü API, kimlik/rol, denetim kaydı, görev atama ve React kullanıcı akışı | EIP-04/05; yetki iptali ve erişim testleri; EIP-10 pilot işletim koşulları. Önce tek kuruma ayrılmış kurulum |
| **EIP-08 — Paylaşım ve iş akışı** | Gereken STIX nesneleri, TAXII/SIEM ve kurum vaka sistemi bağlantıları | Destek/anlam matrisi, paylaşım yetkisi, gerçek karşı uç testi. OpenCTI'nin mevcut uygun işlevleri önce değerlendirilir |
| **EIP-09 — Birden fazla müşteri** | Kuruma özel erişim, veri/iş/rapor ayrımı; sonra MSSP deneyimi | EIP-07 ve EIP-10. Dış servisler dahil ayrım kanıtı olmadan müşteri verisi alınmaz |
| **EIP-10 — İşletim ve kapasite** | İzleme, bakım, kapasite ölçümü, yedek/geri dönüş, destek ve hizmet hedefleri | EIP-01'den itibaren yürür. Pilot ve müşteri aşamalarından önce ilgili koşullar zorunludur; en sona bırakılmaz |
| **EIP-11 — İsteğe bağlı LLM** | Kaynaklı açıklama, günlük özet, vaka taslağı; sonrasında sınırlı soru-cevap | AIM planı. Yerel örneklerle bağımsız başlayabilir; takımda erişim kapsamı korunur, diğer bütün fazları beklemez |

İlk geliştirme sırası **EIP-01'in açık ölçümleri → EIP-02 → EIP-03 →
EIP-04 → EIP-05**; bu tercih edilen sıradır, bağımsız işlere teknik engel
değildir. Dış erişim/donanım denemesi beklerse EIP-05 yerel kanıtlarla
paralel ilerler; OpenCTI denemesi IntelOwl'un başarısını beklemek zorunda
değildir. EIP-06 ve işletim çalışmaları uygun noktada paraleldir.
API ve React, dış platformlara bağlanmanın önkoşulu değildir; ilk bağlantılar
terminalden kanıtlanır. Canlı kaynak erişimi sağlanamayan deneme “kısmi”
kalır; bunun için bütün bağımsız işleri durdurmayız.

### İlk IntelOwl denemesinin sınırı

Önce önceden üretilmiş zararsız bir rapor okunur. Ardından kurulum sürümünde
davranışı incelenmiş tek pasif analizciyle kamuya açık bir IP/domain/hash
sorgulanır. İlk deneme dosya yükleme, hedefe yeni tarama veya otomatik
analiz zinciri içermez. Anahtarsız uygun kaynak tercih edilir; ücretli
kaynağa sessiz geçiş yapılmaz. Örnek rapor tek başına canlı kabul değildir.

Resmî istemci belgesinde boş analizci/connector listeleri bütün ilgili
eklentileri seçebilir, paylaşım seviyesi de varsayılan değer alır. Bu
nedenle boş liste “kapalı” kabul edilmez: seçilen sürümde açık izinli liste,
gereksiz dışa aktarıcıların kapatılması ve gerçek ağ davranışı sınanır.
Bir analizcinin pasifliği adıyla değil yaptığı işlemle doğrulanır.
İzinli analizci dışında hiçbir analizci, dışa aktarıcı veya pivot
çalışmadığı iş ve ağ kayıtlarıyla doğrulanır.
[İstemci sözleşmesi](https://intelowlproject.github.io/docs/pyintelowl/IntelOwlClass/),
[analizci kataloğu](https://intelowlproject.github.io/docs/IntelOwl/usage/).

### İlk OpenCTI denemesinin sınırı

Tek kuruluşlu CE ortamına seçili domain/IP gözlemleri ve kaynaklı raporlar
gönderilir. Desteklenen nesne türü ve tarih anlamı önceden tanımlanır.
Gerekli yetkilere sahip ayrı entegrasyon hesabı kullanılır. OpenCTI'deki
görünüm ve kimlikler doğrulanır; ardından sınırlı dış bağlam okunur.
Yönetici token'ı varsayılan entegrasyon kimliği olmaz.
[Bağlayıcılar](https://docs.opencti.io/latest/deployment/connectors/).

### Önceden onaylanan iki özellik

1. **Olay ilişki adayları:** Mevcut iki ransomware kaynağı karşılaştırması
   genişletilerek HIBP kamu olaylarıyla birlikte kaynakları korunmuş
   inceleme sunulur. Aynı kuruluş farklı olaylar yaşayabilir; tarihlerin
   anlamı ve kesin domain dayanağı açıklanır. Haber ancak EIP-06 ile gerçekten
   toplandıktan sonra dahil edilir. Genel CTI grafik motoru yeniden yazılmaz.
2. **Kaydedilmiş genel arama:** Mevcut on tür yerel arama ve CTI'ya özel
   kayıtlı aramalar temel alınır. Tanım/filtre ve sonuç kanıtı kaydedilir;
   ilk ölçüm sessizdir, sonraki yeni eşleşmeler bildirilir. Tekrar bildirim
   üretmez; kaynak hatası sonuç kaybolması sayılmaz. Toplanan veri üzerinden
   çalışır; her arama bütün internette yeni bir sorgu anlamına gelmez.

## 6. Her bağlantının kabul koşulları

- Sunucu, istemci, eklenti ve yapılandırma sürümü birlikte kaydedilir.
  Container digest/dağıtım bütünlüğü doğrulanır; kör `latest` güncellemesi
  yapılmaz. Alt araçların lisans ve destek durumu da kayıt altındadır.
- Kalıcı yerel iş kimliği, uzak iş/nesne kimliği, asıl kaynak ve kapsam
  taşınır. Boş, eski, kısmi, başarısız ve hiç çalışmamış sonuç ayrılır.
- Yerel veritabanı işlemi ile uzak API çağrısı atomik değildir. Gönderilecek
  iş önce kalıcı kaydedilir; cevap kaybolursa uzaktaki durum sorgulanır.
  Sonuç doğrulanamıyorsa belirsiz kalır, kör tekrar gönderim yapılmaz.
  Tam olarak bir kez ağ teslimi garantisi yerine tekrar güvenliği sınanır.
- 429, süre aşımı, kimlik iptali, şema değişimi, kısmi sonuç, bozuk yanıt ve
  kapalı servis senaryolarında eski kanıt ve yerel kullanım korunur.
- Dışa giden verinin kapsamı, sağlayıcısı ve amacı açıktır. TLP/etiket tek
  başına yetki kontrolü değildir. API anahtarları log veya repoya girmez.
- Sunucunun verdiği bağlantılar, dosyalar ve metinler güvenilmeyen girdidir;
  boyut, süre, yönlendirme, terminal/HTML gösterimi ve ağ hedefi sınırları
  uygulanır. Dış kaynak metni komut çalıştırmaz.
- Güncelleme önce ayrı ortamda denenir. Veri değişmişse yalnız eski servis
  imajına dönmek geri dönüş değildir; tutarlı yedek ve ayrı ortama gerçek
  geri yükleme doğrulanır. [OpenCTI yükseltmesi](https://docs.opencti.io/latest/deployment/upgrade/).
- Kayıt silme/saklama isteği, paylaşılmış kopyalar ve yedekler için de
  tanımlanır. Güncel silme işlemi ile korunması gereken denetim geçmişinin
  kapsamı ürün politikasında açık olur.

## 7. Kurumsal kullanım ve müşteri ayrımı

Bugünkü `OrganizationScope` bir gruplamadır; güvenlik sınırı değildir.
Ortak arama, bildirim kutusu ve depo doğrudan müşteri erişimine açılmaz.
Kimlik sağlayıcısı kullanıcıyı tanır; XTI her işlemde neyi görebileceğini
ve çalıştırabileceğini ayrıca denetler. Tarayıcıya servis yönetici anahtarı
verilmez. İlk React sürümü kanıtlı API işlemlerini kullanır.

OpenCTI CE Apache-2.0 kapsamındadır; EE ayrı lisanslıdır. Kuruluş bazlı
ayrım ve bazı ileri işletim özellikleri EE kapsamındadır. CE'deki bir etiket
veya ön yüzde filtre, müşteri yalıtımı kanıtı sayılmaz.
[Sürüm ayrımı](https://docs.opencti.io/latest/administration/enterprise/).

Çok müşteri aşamasında seçenekler: müşteri başına ayrı kurulum veya lisansı,
yetkisi ve davranışı doğrulanmış ortak servis. IntelOwl için de aynı ayrım
gereği geçerlidir. Tek ortak güçlü servis hesabıyla yalnız XTI ekranında
filtreleme yeterli görülmez. Bir müşterinin diğerinin verisine erişemediği
arama, grafik, API, dosya, iş, sonuç, önbellek, dışa aktarım, bildirim,
LLM bağlamı ve yedek/kurtarma yollarında sınanır.

Ekip pilotunda kullanıcı/rol, oturum ve anahtar iptali, denetim izi,
görev sahipliği, temel kurtarma ve erişim kabulü bulunur. Müşteri hizmetinde
bunlara veri yaşam döngüsü, müşteri taşıma/ayrılma, olay müdahalesi, destek
sorumlusu ve ölçülmüş hizmet hedefi eklenir. Bir dış ürünün lisanslı
özelliğini atlatmak veya güvenlik sınırını taklit etmek çözüm değildir.

## 8. Ücretsiz geliştirme, kapasite ve işletim

| Alan | Bugünkü yaklaşım | Kurumsal aşamada karar |
|---|---|---|
| Yazılım | OpenCTI CE ve IntelOwl ile ücretsiz laboratuvar hedefi | Gerekli sürüm/özellik, dağıtım ve SDK lisansları kayıtlı olmalı |
| Veri | Önce uygun ücretsiz ve açık kaynaklar | API anahtarı, kota, geçmiş veri, ticari kullanım ve paylaşım koşulları kaynak başına değerlendirilir |
| Donanım | Mevcut cihaz uygunsa ayrı denemeler | Birleşik bellek/CPU/disk, arşiv büyümesi ve eşzamanlı analiz ölçülür; uzaktaki deneme ortamı gerekebilir |
| İşletim | Yerel kurulum ve kontrollü deney | Sürekli sunucu, ayrı yedek, bakım, izleme ve destek için bütçe gerekir |
| Ölçek | SQLite yerel profilde kalır | Eşzamanlı yazma ve sorgu gereksinimine göre PostgreSQL, iş kuyruğu veya arama deposu seçilir |

IntelOwl ve resmî Python istemcisi AGPL-3.0 olarak yayımlanır; seçilen
dağıtım/entegrasyon modeli ve alt araçların lisansları ürün kararına dahil
edilir. API üzerinden bağlanmak bütün lisans değerlendirmesinin bittiği
anlamına gelmez. [IntelOwl lisansı](https://github.com/intelowlproject/IntelOwl/blob/master/LICENSE),
[Python istemcisi](https://github.com/intelowlproject/pyintelowl).

Resmî gereksinimler ilk tahmin için kullanılır; toplam kurulumun yeterliliği
kendi ölçümümüzle belirlenir. İlk kapasite kaydında cihaz/işletim sistemi,
kuruluş/varlık sayısı, günlük gözlem ve analiz hacmi, aynı anda kullanıcı,
saklama süresi, gecikme ve kurtarma beklentisi bulunur. Eşikler deneyden önce
kaydedilir. Veri kopyası üzerinde taşıma, sorgu, geri dönüş ve kesinti
ölçülmeden yeni veri altyapısına geçilmez. Mevcut geçmiş denetimlerinin ve
tek yazıcı kilidinin maliyeti de ölçüme dahildir.

## 9. “Geri kalmamak” nasıl ölçülecek?

Amaç seçilen kurumsal senaryoları karşılamaktır. Repo sayısı, komut sayısı
veya dış ürünün menüsünde bir özelliğin bulunması tamamlanma ölçüsü olmaz.

| Senaryo | Mevcut durum | Planlanan sağlama yolu | Kabul kanıtı |
|---|---|---|---|
| Kuruluşun dış riskini izleme | Yerel toplama, rapor ve değişim akışları var | XTI + katkısı ölçülmüş kaynaklar | Kaynak/güncellik boşluklarıyla gerçek günlük iş akışı |
| IP/domain/hash bağlamını zenginleştirme | Seçili yerel IOC kaynakları var | IntelOwl adaptörü | Seçili analiz, asıl kaynak, hata ve zaman görünür |
| Aktör/kampanya/rapor ilişkilerini araştırma | Temel CTI ve ATT&CK var | OpenCTI + XTI bağlam bağlantısı | Örnek olayda kaynakları korunmuş araştırma tamamlanır |
| İlişkili olay ve kayıtlı arama izleme | Dar ransomware/CTI parçaları var | EIP-05 | Aynı ad/farklı olay, tekrar ve kaynak kesintisi sınanır |
| Vaka altında çalışma | Kişisel vaka ve kanıt var | Ekip API/React ve gerektiğinde kurum vaka sistemi | Görev, karar, yetki ve kanıt zinciri korunur |
| SIEM/istihbarat paylaşımı | Sınırlı IOC STIX ve manuel webhook var | EIP-08; uygun OpenCTI paylaşım işlevleri | İkinci sistemde anlamı korunmuş alım ve tekrar deneyi |
| Birden fazla müşteri | Henüz yok | EIP-09 | Bütün erişim yollarında müşteri ayrımı testi |
| Sürekli hizmet | Linux gerçek hizmet kabulü ve uzun işletim ölçümü açık | EIP-10 | Hedef yükte çalışma, kesinti ve geri yükleme kayıtları |
| Geniş marka/dark web/kimlik kapsamı | Kısmi açık kaynaklar; birçok alan yok | Ayrı kaynak ve erişim programı | Tarihli gerçek kaynak kapsamı; erişilemeyen alanlar açık |
| LLM desteği | Planlı, uygulanmadı | EIP-11 | Kaynak atfı, yarar ve yanlış yorum ölçümü |

Her senaryo için işlev, veri kapsamı, doğruluk, güncellik, operasyon ve
güvenlik ayrı değerlendirilir. Aşamalar: **planlandı → prototip → gerçek
entegrasyon doğrulandı → pilotta ölçüldü → desteklenen hizmet**.
Bir aşamadaki başarı diğerlerini otomatik tamamlamaz. OpenCTI/IntelOwl
veya SOCRadar ile eşdeğerlik ancak aynı tanımlı senaryo ve karşılaştırılabilir
kanıt için söylenir; kapalı kaynak erişimi ve bütün ürün kapsamı garanti
edilmez. Karşılaştırma her önemli sürümde güncellenir.

## 10. Bir sonraki somut teslim

EIP-01'in açık noktalarıyla başlayacağız: mevcut deneme ortamını ölçmek,
ilk izinli analiz ve örnek veri kümesini seçmek, sürüm/istemci/lisans
uyumluluğunu kaydetmek. Ardından EIP-02'de **IntelOwl'dan tek bir pasif
analiz sonucunu alıp XTI'da kaynaklı kanıt olarak göstermek** ilk küçük
entegrasyon hedefidir. OpenCTI denemesi bunun ardından gelir.

Bu plan güncellemesinde paket/servis kurulmadı, gerçek veri paylaşılmadı,
veritabanı değiştirilmedi ve yeni bir özellik çalışır ilan edilmedi.
