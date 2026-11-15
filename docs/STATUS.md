# XTI — Güncel Uygulama Durumu

**15 Kasım 2026 · 0.144.0 · Şema 67.**

Bu dosya çalışan uygulamanın durumudur. Roadmap belgeleri hedef kapsamıdır.

**Son ürün yönü:** Bu repo başka platformlara bağlanabilen XTI toplama
ve analiz motorudur. .NET adaptörü, platform bağlantısı, uygulama backend'i,
kullanıcı/giriş oturumu, roller ve web deneyimi repoyu kullanacak ekibe
aittir. Biz motoru, sürümlü sözleşmesini, örneklerini ve belgelerini
sağlarız. [Motor yol haritası](roadmap/ENGINE_INTEGRATION_ROADMAP.md)
geçerlidir. 0.139.0 sürümlü yerel engine okuma sınırını, 0.140.0 ortak
araç kimliği ve yerel kurulum kataloğunu uygular. .NET bağlantısı, ağ servisi
veya müşteri yalıtımı henüz uygulanmadı. 0.144.0 firma içerik geçmişi için
şema 67'ye açık yedekli geçiş ekler; engine v1'in dört işlemi korunur.

**Güncel teslim:** 0.144.0, isteğe bağlı Tavily ile seçilen firma,
kayıtlı kuruluş veya tedarikçi hakkında gerçek web/haber araması ekler.
`mentions configure/plan/search/list/show/status/run-show`, kaynaklı
kalıcı sonuçlar, genel arama/engine ve mevcut kayıtlı arama bağlantısı
uygulanmıştır. Her toplama tek temel API isteğidir; otomatik tekrar ve
LLM cevabı yoktur. Kullanıcının kendi API anahtarı gerekir; kaynak canlı
kullanımı ve ücretsiz kredi bakiyesi bu teslimde doğrulanmış sayılmaz.
[Kullanım ve sınırlar](MENTIONS.md), [karar](decisions/0149-tavily-company-mentions.md).

Şema 67 tek eklemeli çalışma tablosu ekler; açık geçiş yeni yedek alır.
Sorgu/hedef tanımı ve tam sınırlı yanıt geçmişte korunur; güncel görünüm
denetlenmiş çalışmalardan üretilir. Kaynak hatası ve başarılı boş sorgu
ayrıdır. Aynı URL aynı sorgu kapsamında tekrar kayıt oluşturmaz; yalnız
puan değişimi anlamlı değişim sayılmaz. Görünür eşleşme gerekçesi ile
yalnız sağlayıcı adayı ayrıdır; tehdit kararı verilmez. Eski 10/11 tür
kayıtlı arama kapsamları kendiliğinden genişlemez. Yeni engine işlemi yoktur.

Anahtar repodan/veritabanından ayrı özel kullanıcı dosyasında veya ortamda
tutulur. `plan` ağsızdır; yerel sonuç okuma anahtar gerektirmez. Kredi
sayacı yalnız bu veri alanında kaynakça bildirilen tüketimi gösterir;
hesap bakiyesi veya fatura değildir. Kuruluş–tedarikçi toplu izleme,
zamanlanmış arama ve müşteri yalıtımı bu teslimde uygulanmadı.

**0.144.0 doğrulaması:** Tavily taşıması/anahtar, domain/depo/geçiş,
servis/CLI, genel arama/engine ve ilgili mevcut kontrolleri içeren 115 test
30,583 saniyede geçti. Bütün migration paketi 235/235 başarılıdır
(71,337 saniye). Son API hata yönlendirmesi ve engine sorgu alanı dahil
51 ilgili test ayrıca 5,135 saniyede geçti. 48 yerel belge bağlantısı,
bir bölüm bağlantısı ve 29 komut örneği doğrulandı.

Yerel genel tur macOS/Python 3.13 üzerinde 2.350 test çalıştırdı
(965,516 saniye): 2.345 başarılı, üç Linux kontrolü atlandı; iki eski
Linux yükseltme testi yeni şema 67 yerine 66'yı bekliyordu. Beklentiler
67 ve desteklenmeyen sonraki sürüm 68 olarak düzeltildi; test dosyası
hızlı CI kapsamına eklendi. Düzeltme sonrası yükseltme/CI/geçiş/engine
paketinde 48 kontrolün 46'sı başarılı, Linux `/proc` isteyen ikisi
yerelde atlandı (14,511 saniye). Genel tur yeniden çalıştırılmadı.
Gerçek Tavily anahtarıyla dış arama yapılmadı ve kredi tüketilmedi;
canlı kaynak kabulü kullanıcı anahtarı tanımlandıktan sonra yapılabilir.
Kullanıcı veritabanı ve mevcut araç ortamı değiştirilmedi.

**Önceki teslim:** 0.143.0, hazır `feedparser` ile RSS/Atom haberlerini
internetten toplar; kaynaklı haberleri genel arama, engine ayrıntısı ve
mevcut kayıtlı arama/bildirim yoluna bağlar. Kaynaklar arası olay adayları
ve önceki izlemeler kullanılmaya devam eder.

**Tamamlanan temel:** Mevcut SQLite motoru için tanımlanan 11 maddelik
sağlamlaştırma paketi, aşağıdaki ortam ve kabul senaryolarında tamamlandı.
Kişisel terminal kullanımı, kurulum/güncelleme ve kurtarma yolu hazırdır.
Gelecekteki .NET bağlantısı ve platform PostgreSQL yerleşimi/veri geçişi
repoyu kullanan ekibin işidir. Entegrasyon teslim hazırlığı ile geniş
paylaşım ve LLM en sona ertelendi. [0145 kararı](decisions/0145-stabilization-first-local-engine.md)
ve motor planındaki sınırlar geçerlidir.

**Hazır bileşen araştırması:** [Seçim planı](roadmap/COMPONENT_SELECTION_PLAN.md)
olay adaylarında yaklaşık ad eşleştirme deneyini, haber modülünde
feedparser ve sonraki motor/paylaşım tercihlerini kaydeder. İlk aday
tesliminde kesin host ve mevcut ad/grup/zaman kuralları ile sınırlı
noktalama düzenlemesi yeterli olduğu için RapidFuzz kurulmadı; genel
yaklaşık eşleştirme ölçümlü ayrı çalışma olarak kaldı. Önceki FastAPI/Keycloak/panel
tercihleri bu repo kapsamından çıkarıldı. Mevcut genel arama/CTI kayıtlı
arama/bildirim desenleri 0.142.0'da tekrar kullanıldı. 0.143.0 haberler için
`feedparser==6.0.14` ve `feedparser-sgmllib==2.1.0` kullanır; RapidFuzz,
Trafilatura ve diğer gelecek tercihler kurulmuş sayılmaz.

## Çalışanlar

- `news sources/refresh/list/show/status/run-show`: CISA, UK NCSC ve
  CERT-FR yayınlarını sabit HTTPS adreslerinden açıkça toplama; başlık,
  sınırlı düz metin özet, özgün bağlantı ve kaynak tarihlerini araştırma.
- Haber kimliği kaynak + yayıncı GUID/ID'si, bu yoksa bağlantıdır. Aynı
  haber tekrarında yeni kayıt oluşmaz; başlık/özet/tarih değişimi ayrı
  kanıttır. Akıştan çıkan eski haber silinmez. Kaynak hatası ve başarılı
  boş akış ayrı tutulur, önceki başarı korunur.
- Her çalışma aynı olanlar dahil bütün gözlenen haberleri sayfalı
  önce/sonra kanıtıyla gösterir. Güncel haber sonraki sürümde değişse de
  eski çalışma kanıtı değiştirilmez. İlk görülme, son içerik değişimi,
  son görülme ve kaynağın yayın/güncelleme tarihleri ayrıdır.
- Genel arama on birinci tür olarak `news` destekler. Engine v1'in dört
  işlemi korunur; kaynak namespace'iyle haber kayıt ayrıntısı eklenir.
  Eski kayıtlı aramaların on türlük somut kapsamı kendiliğinden genişlemez.
  Yeni haber kapsamı açık tanım gerektirir; mevcut `search-watch → inbox`
  ilk sessiz başlangıç ve yeni/anlamlı değişiklik kurallarını kullanır.
- Haber toplama izlemeyi otomatik çalıştırmaz; `collect` profillerine
  henüz eklenmedi. Haber sayfaları/ekler açılmaz. Kaynaklar üç sabit
  yayıncıyla sınırlıdır; her haber eşleşmesi araştırma bağlamıdır.
- Şema 66 üç boş tablo ekler; açık migration ve yeni dizine yedekten
  dönüş uygulanır. Güncel görünüm, tam akış görüntüleri ve çalışma
  zincirinden denetlenir. 4 MiB yanıt/2.000 haber, toplam 50.000 haber/
  10.000 çalışma, 8 MiB görüntü ve 64 MiB toplam görüntü/projeksiyon
  sınırlarında aşım kısmi kayda veya eski verinin silinmesine yol açmaz.
- Normal kurulum haber kütüphanelerini sabit sürümle mevcut korumalı
  ortamda kurar; eski ortam yedekte kalır. `--core-only` paket indirmez.
  Parser gecikmeli yüklendiği için yokluğu diğer komutları engellemez.
  `sources.status` içindeki `builtin` haber adaptörünü ifade eder; parser
  kurulum doğrulaması değildir. Gerçek yenileme eksik/uyumsuz paketi
  açıklamalı hata olarak bildirir; kurucu sürüm ve yerel RSS/Atom örneğini
  ayrıca doğrular.

**0.143.0 doğrulaması:** Haber parser/servis/depo/geçiş/arama/terminal/
kurulum ve mimari testlerini kapsayan 61 test, 11,080 saniyede geçti.
Son eklenen genel arama veri-dizini regresyonu ayrı entegrasyon turunda
doğrulandı. Tüm migration paketi 229/229 başarılıdır (60,738 saniye).
Mevcut genel arama/engine/izleme/kaynak durumu paketinde 119 test geçti.
Yeni adaptörle üç gerçek HTTPS yayını 10 CISA, 20 NCSC ve 40 CERT-FR
haberi döndürdü; kaynak tarihleri ayrıştırıldı. Bu anlık kaynak erişimidir.
Gerçek CLI ile geçici veri dizininde 70 haberin saklanması, bir kayıtlık
gösterimde tam toplam/devam bilgisi, 10 eşleşmelik sessiz arama başlangıcı
ve aynı yayının tekrarında yeni kayıt/bildirim üretmeme doğrulandı. Geçici
veri deneme sonunda kaldırıldı. Dokuz kullanım belgesindeki 240 yerel
bağlantı hedefi ve 20 haber komut örneği kontrol edildi.
Kullanıcı veritabanı veya mevcut araç ortamı değiştirilmedi.

Yerel genel tur macOS 26.6.2 arm64 / Python 3.13.3 üzerinde 2.275 test
çalıştırdı (933,209 saniye): 2.271 başarılı, üç Linux kontrolü atlandı;
bir eski kaynak-listesi beklentisi yeni üç haber kaynağını içermediğinden
başarısızdı. `fca5a3c` yalnız bu testin beklediği listeyi günceller ve
14 testlik ilgili CLI dosyasını hızlı pakete ekler; uygulama kodunu
değiştirmez. Düzeltilen test dahil 36 kaynak/terminal/haber regresyonu
18,200 saniyede başarılıdır. Genel tur tekrarlanmadı; aynı uygulama
koduyla genişletilmiş son Linux hızlı kontrolü aşağıda ayrıca kayıtlıdır.
[Kullanım](../README.md#rss-ve-atom-haberlerini-topla),
[karar](decisions/0148-publisher-news-feeds.md).

**0.143.0 gerçek Linux kurulum ve kurtarma kabulü — `1c550e6`:**

| Kontrol | Sonuç ve kanıt |
|---|---|
| Linux hızlı kontrolü | Python 3.11.18 üzerinde 848 test, 432,746 saniye; tamamı başarılı, atlanan test yok. [CI işi](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43728962314/job/132856954373) |
| Son genişletilmiş hızlı kontrol (`fca5a3c`) | Aynı uygulama koduyla 862 test, 479,126 saniye; tamamı başarılı, atlanan test yok. Düzeltilen eski kaynak-listesi kontrolü ve aynı dosyadaki diğer CLI testleri dahil. [Son CI işi](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43729980482/job/132860080553) |
| Temiz Sherlock/Maigret ve haber okuyucusu | Python 3.11.18 ve 3.12.16 ortamlarının her birinde 125 test; gerçek kurulum, sağlıklı tekrar, geçici veri korunması ve yedekten dönüş başarılı. [İki ortam](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43728962239) |
| Temiz theHarvester | 104 test; gerçek sabit araç kurulumu, tekrar, engine okuma ve yeni dizine yedekten dönüş başarılı. [Kurulum işi](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43728962324) |
| Önceki sürümden geçiş ve kesintiden kurtarma | İki araçta şema 64→66 açık geçişi; tüm eski satır/rowid/DDL, yedek ve araç kimlikleri korundu. Eski kodla yedeğin yalnız yeni dizine açılması, aday sürüme dönüş, gerçek paket alt süreci sırasında kesinti, miras kilidi ve iki kez açık kurtarma geçti. [İki araç kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43728968574) |

Haber kütüphaneleri eklenirken marka kurucusu yeni yönetilen ortam
oluşturdu; önceki ortamı eksiksiz korudu. Sherlock/Maigret sürümleri,
resmî kaynakları ve katalog özetleri aynı kaldı. Harvester ayrı ortamı
bu bağımlılık değişiminden etkilenmedi. Kabul yalnız geçici veriler ve
gerçek kurulum süreçleriyle yapıldı; hedef taraması yapılmadı. Bunlar
süreç kesintisi kabulleridir, elektrik/disk arızası veya 7/24 hizmet
garantisi değildir. Upgrade-only işinde genel verification/operations
adımlarının atlanması seçilen kapsam gereğidir; genel test ayrı izlenir.

**0.142.0'da eklenen arama izlemesi ve o sürümün doğrulamaları:**

- `search-watch add/list/show/disable/run/run-show/monitor`: on yerel
  kayıt ailesinin tam sonucunu izleme; ad/tür/etkinlik filtresi, sayfalı
  liste, tanım/çalışma geçmişi, önce/sonra kanıt ve kaynak kapsamı.
- Tanımı kaydetmek kaynak toplamaz veya başlangıç çalışması yapmaz.
  İlk `run`, tanım değişimi veya yeniden etkinleştirme sessiz başlangıçtır.
  Aynı tanımı tekrar kaydetmek yeni sürüm oluşturmaz. Arada çalışma
  olmasa da A→B→A veya kapat/aç yeni başlangıçtır; eski kanıt korunur.
- Sonraki yeni/anlamlı değişen eşleşmeler çalışma başına bir yerel bildirim
  üretir. Aynı tekrar ve yalnız artık eşleşmeyen sonuç bildirim üretmez.
  Bunlar yerel arama farklarıdır; yeni ihlal veya çözülmüş tehdit hükmü
  değildir. Sonradan toplanan eski bir olay yerel aramaya yeni girebilir.
- Sosyal profiller araç/izleme/tanım/platform kimliğiyle karşılaştırılır;
  güncel çalışma-öğe kimliği ayrıca kanıtta saklanır. Kaynak yenileme
  zamanı/çalışma kimliği ve gezinme değişikliği alarm üretmez. Yalnız
  ransomware `last_seen_at` yenilenmesi de anlamlı değişim sayılmaz.
- Tanım, tam arama görüntüsü, kaynak kapsamı ve fark aynı yazma işleminde
  bildirimle birlikte kaydedilir. İçerik özeti aynı olan görüntü tekrar
  kullanılır. Eski rapor bugünkü tanım veya kaynakla yeniden yazılmaz.
  Gösterim limiti karşılaştırmanın tamamını kesmez.
- Ortak inbox sayfalaması, bildirim sırası, okundu durumu, status/doctor
  sayaçları ve açık webhook kuyruğu yeni bildirim türünü kapsar. Otomatik
  uzak bildirim gönderimi yoktur; `monitor` yalnız terminal açıkken yerel
  karşılaştırmayı tekrarlar ve her tur sonunda yazıcı kilidini bırakır.
- Şema 65 beş boş tablo ekler; açık `migrate` benzersiz yedekle geçer.
  Eski kod yeni şemayı reddeder; önceki sürüme geri dönüş yedeği yeni
  veri dizinine açarak yapılır. Yeni bağımlılık veya engine v1 işlemi yoktur.
- Sınırlar: 1.000 tanım, 10.000 tanım olayı, 20.000 çalışma; çalışma
  başına 50.000 eşleşme, görüntü başına 16 MiB ve toplam görüntülerde
  64 MiB. Aşımda kısmi sonuç veya veri silme yapılmaz. Geçmiş okuması
  doğrulama maliyeti taşır; ölçülmüş kurumsal kapasite iddiası değildir.

**0.142.0 hedefli doğrulaması:** Son kod `3abafe5` için yeni kimlik/fark,
depolama, terminal, bildirim, geçiş ve Linux kabul betiği testleri; mevcut
genel arama, engine sözleşmesi/kayıtları ve mimariyle birlikte 120 testte,
41,052 saniyede tamamlandı: 118 başarılı, Linux `/proc` isteyen iki test
Mac'te atlandı. Gerçek SQLite kullanan eşzamanlılık regresyonu `add`,
`disable` ve `run` sırasında araya giren yazının korunduğunu, zamanın
kilit alındıktan sonra alındığını doğrular. Tüm migration paketi ayrıca
223/223 başarılıdır. Geçici şema 64 verisinin açık geçişi, tam eski
tablo/rowid/SQL/kanıt koruması ve geçiş öncesi yedeği gerçek CLI ile sınandı.

Yerel genel `./scripts/check` turu macOS 26.6.2 arm64 / Python 3.13.3
üzerinde 2.209 testte, 872,016 saniyede tamamlandı: 2.206 başarılı, hata
yok, üç atlama. Atlamalar iki Linux süreç sahipliği testi ile
`systemd-analyze` kontrolüdür. Genel tur ilk özellik koduyla başlatıldı;
sonraki kabul betiği JSON düzeltmesi ve kilit zamanı düzeltmesinin güncel
testleri yukarıdaki ayrı 120 testlik son turda doğrulandı. Gerçek CLI
örneğinde üç domain sessiz başlangıç oluşturdu; dördüncü domain bir
bildirim üretti, değişmeyen tekrar üretmedi. Bir kayıtlık gösterimde tam
toplam ve devam komutu korundu. Gerçek kullanıcı veritabanı değiştirilmedi.

**0.142.0 Linux güncelleme/kurtarma kabulü — `a868194`:** Önceki yayımlı
`9cdf32c` sürümünden açık şema 64→65 geçişi iki araç ailesinde geçti.
Tüm eski satırlar, rowid/DDL ve kanıt korundu. Eski kodun 65'i reddi,
geçiş öncesi 64 yedeğinin yalnız yeni dizine açılması ve aday sürüme dönüş
doğrulandı. Gerçek pip/uv alt süreci sırasında zorla kesme, miras alınan
kilit, iki kez açık kurtarma ve araç kimliği/engine kayıtlarının korunması
geçti. Kabul Python 3.11.18 kullandı; korunan eski marka ortamı 3.12.3,
Harvester ortamı 3.14.10 idi. Bu süreç çökmesi kabulüdür; elektrik/disk
arızası deneyi değildir. [Sherlock/Maigret](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43724430865/job/132843181876),
[Harvester](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43724430865/job/132843181518).

İlk güncelleme kabulünde gerçek geçiş başarılıydı; test betiği eski kodun
JSON içindeki Unicode kaçışlı Türkçe hata mesajını ham metin olarak
karşılaştırdığı için durmuştu. `a868194` JSON'u çözüp hata kodu ve mesajı
denetler; iki regresyon ekler. Yukarıdaki tekrar iki araçta da başarılıdır.
Son `3abafe5` yalnız kayıtlı arama yazma zamanını ve ilgili regresyonu
değiştirir; kurulum/geçiş kodunu değiştirmez.

**0.142.0 temiz Linux kurulum kabulü — `6bbcc4f`:** Sherlock/Maigret
Python 3.11 ve 3.12 ile ayrı, Harvester kendi kabul işinde başarılıdır.
Gerçek paket kurulumu/tekrar, geçici kayıtların korunması, engine okuması
ve yeni dizine yedekten dönüş doğrulandı; hedef taraması yapılmadı.
[Marka kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43723804542),
[Harvester kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43723804646).

**0.142.0 Linux işletim kabulü — `6bbcc4f`:** Ubuntu x86_64 / Python
3.11.18 üzerinde beş kontrollü kaynak hatası, gerçek systemd kullanıcı
yöneticisi, düşük disk ve 600,007 saniyelik 45 tekrar geçti. Kaynak hata
deneyleri gerçek CLI'ye kontrollü HTTP yanıtları verdi; soket erişimi
kapalıydı. 100/1.000/5.000 sentetik domain araması sırasıyla
1,439/0,902/0,991 saniye, yedek + geri yükleme 0,118/0,119/0,126 saniye
sürdü. Alt süreçlerde gözlenen en yüksek RSS 66.850.816 bayttı. 48 MiB
tmpfs'te 64 MiB rezerv ön kontrolü mevcut kaydı koruyarak işlemi reddetti;
disk doldurulmadı. Gerçek systemd başlatma, durdurma/tekrar, meşgul işin
reddi, kaynak hata kodu ve kaçırılan zamanın bir kez telafisi doğrulandı.
Bu genel işletim kabulüdür; 50.000 kayıtlı arama eşleşmesi için kapasite
ölçümü, sürekli çalışan işçi, yeniden başlatma/güç kaybı veya 7/24 hizmet
garantisi değildir. [İşletim kaydı](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43723819582/job/132841293159).

**0.142.0 son Linux hızlı kontrolü — `3abafe5`:** 787 test, 505,556
saniye; tamamı başarılı, atlanan test yoktur. Son kilit zamanı regresyonu
bu pakete dahildir. [CI kaydı](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43724909855/job/132844708969).

**0.142.0 Linux genel test paketi — `6bbcc4f`:** Ubuntu 24.04 / Python
3.11.18 üzerinde `./scripts/check` 2.209 testte, 1.367,662 saniyede geçti;
hata veya atlanan test yoktur. Bu ilk özellik kodunun genel kabulüdür;
sonraki iki düzeltmenin hedefli, hızlı ve gerçek güncelleme kabulü yukarıda
ayrı kod kimlikleriyle kayıtlıdır. İlk workflow içindeki eski güncelleme
işleri başarısız kaldığından tüm workflow başarılı diye gösterilmez;
genel test işinin sonucu ile düzeltilmiş güncelleme tekrarının sonucu
ayrı değerlendirilir. [Genel test işi](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43723819582/job/132841293288).

11 belgedeki 305 yerel dosya bağlantısı ve 14 yeni terminal komut örneği
denetlendi; örnekler mevcut komut parser'ıyla uyumludur. Son teslim kaydı
yalnız bu belge ve engine rehberindeki geçiş açıklamasını günceller.
[Kullanım](../README.md#genel-aramayı-kaydet-ve-değişiklikleri-izle).

**0.141.0 teslimi ve o sürümün kabulü:**

- `events candidates`, ThreatCluster/RansomLook/HIBP kanıtını tek SQLite
  okuma anında kullanır. Kaynak yenileme ayrı mevcut internet komutlarıdır;
  karşılaştırma ağa çıkmaz, veri tabanı oluşturmaz/göç ettirmez ve yazmaz.
- Aynı kuruluş adı/grup ve en fazla 72 saat keşif farkı olan ThreatCluster–
  RansomLook çiftleri `possible_same_event` üretir. Yalnız harf/boşluk/
  noktalama farkı ayrı kuralla desteklenir; sözcük/sonek atılmaz. 72 saat
  bir aday kuralıdır, doğruluk yüzdesi veya doğrulanmış ihlal değildir.
- ThreatCluster website hostu ile HIBP domaini tam eşitse yalnız
  `organization_context` üretilir. Ad/grup/zaman alanları daha zayıf eski
  ransomware karşılaştırmaları da ayrı bağlam türünde kalır. RansomLook'a
  domain ataması, HIBP–RansomLook veya geçişli üç kaynak birleştirmesi yoktur.
- İki özgün kayıt, kaynakla birlikte kayıt kimliği, içerik özeti, kaynak
  çalışması ve tarih alanlarının anlamı korunur. Önceki ransomware insan
  kararı ayrı gösterilir; güncel kanıtla farklıysa açıkça işaretlenir.
  Genel aday kimliği mevcut karşılaştırma kimliği yerine kullanılamaz;
  yeni genel karar/otomatik alarm saklanmaz.
- Tam domain filtresi, sayfalama, ayrı tür toplamları, kaynak hatası/
  hiç toplanmamış/başarılı boş kapsam ayrımı ve bağımsız güncellik vardır.
  Kaynak sayaçları filtreden önceki kapsamdır; limit toplamı kesmez.
- Yeni okuyucu son tam katalog ile geçmiş kararların gerekli tekil
  kayıtlarını tutar. Bütün kaynak tarihçesi denetlenir; her geçmiş
  çalışmanın tam katalog kopyası bellekte saklanmaz. 50.000 güncel kayıt,
  100.000 karşılaştırma referansı veya 50.000 aday aşılırsa kısmi rapor
  verilmez. Büyük tarihçenin denetimi hâlâ okuma maliyeti taşır.
- Yeni tablo, bağımlılık veya engine v1 işlemi eklenmedi. Şema 64 ve dört
  engine okuma işlemi korunur. Bu dilim CLI/JSON kullanımına açıktır;
  kuruluş filtresi, genel aday kararları ve yaklaşık eşleştirme içermez.

**0.141.0 doğrulaması:** 48 yeni kural/depo/servis/terminal testi ile eski
karşılaştırma, karar, göç ve mimari kontrollerini kapsayan 63 hedefli test
9,430 saniyede geçti. Geçici kanıtlar kullanıldı; gerçek internet veya
kullanıcı veritabanı kullanılmadı. `c1af006` koduyla genel `./scripts/check`
paketi macOS / Python 3.13.3 üzerinde 2.155 test çalıştırdı: 2.152 başarılı,
hata yok, üç atlama; süre 829,791 saniye. Linux `/proc` süreç sahipliği
gerektiren iki kabul testi ile `systemd-analyze` testi bu Mac'te atlandı.
Sonraki değişiklik yalnız bu doğrulama belgesidir. Gerçek terminal örneği
geçici iki kuruluş/üç kaynakta dört çift üretti; tam domain filtresi iki
çifti, bir kayıtlık sayfa ise doğru toplam ve devam komutunu gösterdi.
On belgenin yerel bağlantıları/kod blokları ve Git diff kontrolü geçti.
[Kullanım](../README.md#kaynaklar-arası-olay-adaylarını-incele).

**0.141.0 Linux hızlı kontrolü — kod `c1af006`:** 735 test 462,022
saniyede geçti; hata veya atlanan test yoktur. Yeni 48 test bu pakete
dahildir. [CI kaydı](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43720708420).

**0.141.0 Linux kurulum kabulü — kod `c1af006`:** GitHub'ın temiz Ubuntu
makinelerinde Maigret/Sherlock kurulumları Python 3.11 ve 3.12 ile ayrı
geçti. theHarvester temiz kurulumu da başarılıdır. Mevcut kabul betikleri
kurulum/tekrar, geçici kayıtların korunması, engine okuması ve yeni dizine
yedekten dönüşü sınadı. Bu kurulumlar gerçek paket indirdi; hedef taraması
yapılmadı. [Marka kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43720708443),
[Harvester kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43720708444).

- 0.140.4 karma kayıt kurtarma, gerçek süreç kesintisi/tekrar ve gizli bilgi
  kabullerini birleştirir. On engine arama ailesi, insan kararları, vaka
  kanıtları, bildirim okunma durumu ve iş geçmişi geçici veride sınanır.
  Yedek fiziksel SQLite/şema/bağ bütünlüğünü kontrol eder; her kaydın iş
  anlamını doğruladığı iddia edilmez. Bozuk vaka kanıtının okuma sırasında
  reddi ayrıca sınanır.
- Webhook anahtarında normal dosya olmayan bir FIFO yolu, dosya türü
  denetlenmeden beklemeye neden olabiliyordu. Açma işlemi artık beklemeden
  türü denetler; normal dosya, symlink reddi ve özel izin kuralları korunur.
- Ayrı `XTI stabilization acceptance` işi yalnız elle çalıştırılır. Genel
  testler, önceki sürümden gerçek araç güncelleme/kurtarma, gerçek systemd
  ve sınırlı kaynak/disk/kapasite denemeleri ayrı işlerde raporlanır.
  Kullanıcı verisi, Maigret/Sherlock/theHarvester commitleri ve şema 64 değişmez.
- Gerçek Python 3.11 temiz kurulumunda NumPy 2.5.4'ün Python 3.12 alt
  sınırıyla çakıştığı doğrulandı. Python 3.11 için 2.4.6, 3.12 ve üstünde
  mevcut 2.5.4 koşullu sabitlenir. Kurulum denetimi aynı koşulu uygular;
  CI seçilen yorumlayıcıyı açıkça kullanır ve temiz marka kurulumunu iki
  Python sürümünde ayrı doğrular.

**0.140.4 kabul kaydı — kod `7060cec`:** Kabul ortamı GitHub'ın geçici
Ubuntu 24.04 x86_64 makinesi, çekirdekte Python 3.11.18'dir. Temiz marka
kurulumu ayrıca Python 3.12.16 ile geçti. Yerel geliştirme ortamı macOS
26.6.2 arm64 / Python 3.13.3'tür. Aşağıdaki Linux sonuçları aynı kod
commit'ine aittir; sonradan yalnız belge değişmesi bu kodu değiştirmez.

| Kontrol | Sonuç ve kanıt |
|---|---|
| Hızlı kontroller | 687 test, 392,275 saniye; tamamı başarılı. [CI kaydı](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43709958003) |
| Genel test paketi | 2.107 test, 1.099,978 saniye; tamamı başarılı, atlanan test yok. [CI kaydı](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43709965600/job/132799182088) |
| Temiz Maigret/Sherlock kurulumu | Python 3.11.18 ve 3.12.16; gerçek kurulum/tekrar, ortam ve örnek veri korunması, engine ve yedekten dönüş başarılı. [İki ortamın kaydı](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43709958013) |
| Temiz theHarvester kurulumu | Gerçek sabit araç, tekrar, engine ve yeni dizine yedekten dönüş başarılı. [CI kaydı](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43709958037) |
| İki araçta sürüm güncelleme ve kurtarma | 0.140.2 `9cdf32c` → 0.140.4 `7060cec` → aynı şemada eski kod → güncel kod; gerçek kurucuyu kesme, çalışan alt sürecin kilidi ve iki kez açık kurtarma başarılı. [Kabul kaydı](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43709965600) |
| Linux işletimi | Beş kaynak hata/düzelme senaryosu, gerçek systemd, düşük disk, kapasite ve 600 saniyelik tekrar başarılı. [Ölçüm işi](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43709965600/job/132799181874) |

Sürüm geçişi mevcut araç ortamını korur: eski marka ortamının gerçek
Python'u 3.12.3, theHarvester ortamınınki 3.14.10 olarak ayrıca kaydedildi.
Deney çekirdeğinin Python 3.11 olması, eski araç ortamlarının da 3.11
olduğu anlamına gelmez. Geçiş aynı şema ve aynı araç pinleri içindir;
gelecekte farklı pin/şema geçişi ayrıca doğrulanır.

**Ölçülen işletim kapsamı:** kaynak hata denemeleri, üretim HIBP HTTP
açma sınırına kontrollü yanıtlar vererek gerçek CLI süreçlerinde yapıldı;
gerçek soket erişimi kapalıydı. Zaman aşımı, bağlantı kopması, 429, 503 ve
bozuk yanıtta son başarı korundu; her denemede tek kaynak çağrısı yapıldı.
Bu, bütün sağlayıcıların canlı erişim testi değildir. Gerçek systemd kullanıcı
hizmetinde meşgul iş reddi, hata çıkış kodu, durdurma/yeniden çalışma ve
hızlandırılmış iki tarihte kaçırılan zamanın yalnız bir kez telafisi geçti.

Kapasite ortamı `Linux-7.0.0-1017-azure-x86_64-with-glibc2.39`, Python
3.11.18; aşağıdaki kayıtlar sentetik domainlerdir. Veri sırasıyla 100,
1.000 ve 5.000'e büyütüldü; oluşturma süreleri o aşamada eklenen 100,
900 ve 4.000 kayda aittir. Arama, doğru toplam sayısı ve ilk 20 sonuçla
ölçüldü; süre gerçek komut başlangıcını içerir. Yedek/geri yükleme süreleri
depo işlemini ölçer.

| Toplam domain | Aşamadaki ekleme | Arama | Yedek + geri yükleme | Veritabanı |
|---|---|---|---|---|
| 100 | 1,853 sn | 0,843 sn | 0,111 sn | 2.170.880 bayt |
| 1.000 | 15,799 sn | 0,484 sn | 0,114 sn | 2.338.816 bayt |
| 5.000 | 69,501 sn | 0,531 sn | 0,126 sn | 3.088.384 bayt |

Alt süreçler için gözlenen en yüksek RSS 66.301.952 bayt; kabul betiğinde
42.315.776 bayttır. Bu değerler süreçlerin en yüksek ölçümleridir, toplam
makine belleği veya tek sorguya ait artış değildir. Önceden belirlenen
arama <60 sn, yedek/geri yükleme <120 sn ve alt süreç RSS <1 GiB sınırları
geçti. İzole 48 MiB tmpfs üzerinde 48.177.152 bayt boş alan ölçüldü;
64 MiB ön kontrol rezervinin altında toplama/yedekleme başlamadan açık
`storage_error` üretildi, mevcut kayıtlar korundu. Disk doldurulmadı.

600,004 saniyelik denemede 50 tekrarlı hazırlık/toplama turu tamamlandı;
en büyük veritabanı 2.277.376 bayt, saklanan yedek sayısı en fazla ikiydi.
Veri bütünlüğü ve değişmeyen kaynakta yeni değişiklik kaydı üretmeme kontrolleri
geçti. Bu kabul 5.000 sentetik domain ve 10 dakikalık ölçümle sınırlıdır;
7/24 hizmet seviyesi, sürekli bellekte kalan işçi, işletim sistemi yeniden
açılışı veya donanım güç kaybı kabulü değildir.

Yerel karma veri ve gizlilik kabulleri ayrı ayrı beş testle geçti;
güncel kabul betikleri/testleri son genel pakete dahildir. Kullanım ve
kurtarma komutları [başlangıç rehberinde](GETTING_STARTED.md), 11 işin
kapsamı [motor planında](roadmap/ENGINE_INTEGRATION_ROADMAP.md) kayıtlıdır.

- 0.140.3 Maigret/Sherlock ortamına kalıcı kilit, kimlik kontrollü günlük
  ve açık `--recover` ekler. Sağlıklı tekrar paket indirmez; `--check` ve
  `verify-brand` aynı korumalı doğrulama yoludur. Eski ve başarısız ortamlar
  benzersiz klasörlerde tutulur; otomatik silinmez.
- XTI başlatıcısı ortamı seçmeden önce paylaşımlı kilidi alır. Aktif marka
  kurulumunda komut başlangıcı meşgul hatası verebilir; yarım günlük kalmış
  ama kurulum durmuşsa varsayılan çekirdek sağlam temel Python ile çalışır.
  Sosyal adaptörler kurtarma tamamlanmadan araç çalıştırmaz. Çocuk süreç
  kilidi devralır; alt sürecin durumu belirsizken ortam taşınmaz.
- theHarvester ve marka kurucusu aynı süreç/kimlik/günlük yardımcılarını
  kullanır. Eski PID kilidi veya eski sabit yedek sahiplik kanıtı sayılmaz;
  yeni günlükle birlikte bulunsa da otomatik silinmez veya geri alınmaz.
  [Marka kurulum rehberi](BRAND_INSTALLATION.md),
  [0147 kararı](decisions/0147-recoverable-brand-environment.md).
- Marka Ubuntu kabul işi geçici SQLite ve örnek kanıtı kurulumdan önce
  oluşturup kurulum/tekrar sonrası içerik özetlerini karşılaştırır;
  varsayılan başlatıcı, engine okuma ve yedekten dönüşü sınar. Ortak dosya
  değişiklikleri marka ve Harvester CI filtrelerine dahildir.

**0.140.3 doğrulaması:** Yerel gerçek `setup-brand --check`, Maigret 0.6.6
ve Sherlock 0.16.2'yi indirmesiz doğruladı; son başlatıcı değişikliğinden
sonra `verify-brand` da geçti. Genel `./scripts/check` turu 705,163 saniyede
2.069 test çalıştırdı: 2.068 geçti, macOS'ta `systemd-analyze` bulunmadığı
için bir test atlandı. Tur başladıktan sonra tamamlanan kilit öncesi
çalıştırıcı seçimi ve aşırı iç içe bozuk günlük düzeltmeleri ayrıca sınandı:
güncel 18 runtime testi 9,394 saniyede, 26 marka kurulum testi 13,188
saniyede geçti. Bu son üç yeni regresyon genel turun keşfine dahil değildir.
CLI ve engine bileşen satırları eşleşti; seçilen eksik veri dizini oluşmadı.
Kabuk sözdizimi, Python derleme ve on belgenin bağlantıları doğrulandı.

**Gerçek Ubuntu kabulü:** `cbea620` kod commit'inin
[theHarvester kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43705787750)
ve [marka kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43705787736)
başarıyla tamamlandı. Her iki işte çevrimdışı kilit/kesinti regresyonları
ve gerçek temiz kurulum adımları geçti. Geçici kayıt/kanıt içerikleri
korundu; tekrar kurulum, engine okuma ve yeni dizine yedekten dönüş geçti.
Marka tekrarında ortamın kimliği, dosyaları ve izinleri de değişmedi.
İndirmesiz tekrar davranışı komut korumaları, içerik karşılaştırması ve
çevrimdışı kurucu testleriyle sınandı; bu, işletim sistemi düzeyinde ağ
yalıtımı değildir. Canlı kullanıcı adı veya hedef taraması yapılmadı.
Aynı kod commit'inin
[hızlı kontrolleri](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43705787876)
de başarıyla tamamlandı. Bu üç sonuç `cbea620` koduna aittir; sonraki
yalnız belge değişikliği bu kabulün kodunu değiştirmez.

Bu, 0.140.3 teslim anındaki kabul kaydıdır. O sırada açık kalan önceki
sürümden gerçek güncelleme ve araç ortamını yenilerken kesinti/geri dönüş
zinciri 0.140.4'te doğrulandı; güncel kabul kaydı yukarıdadır. İşletim
sistemi yeniden açılışı ve 7×24 hizmet seviyesi bu kabulün kapsamı değildir.
Araç pinleri, şema 64 ve mevcut kullanıcı kayıtları korunur.

- 0.140.2 theHarvester kurulumu eski ortamı korur; hata halinde geri
  getirir. Ani kesinti için kalıcı günlük ve açık `--recover`, ağsız yerel
  `--check`, aynı sabit sürümü yeniden kurmak için `--force` vardır.
  Sağlıklı seçeneksiz tekrar `uv` veya indirme gerektirmez.
- Kurulum ve arşiv işçisi ortak kalıcı kilit kullanır; çocuk süreç kilidi
  devralır. Hazırlık/bileşen görünümü yarım veya meşgul kurulumu hazır
  saymaz. Eski yedekler ve başarısız adaylar otomatik silinmez.
  [İşletici rehberi](HARVESTER_INSTALLATION.md),
  [0146 kararı](decisions/0146-recoverable-harvester-installation.md).
- Ayrı, dosya değişimine bağlı Ubuntu kabul işi gerçek sabit aracı kurma,
  ağsız tekrar/kontrol, yerel engine kullanımı ve geçici kayıtların
  korunmasını sınamak için eklendi. Bu işin tanımlanması, başarılı
  çalıştığı veya STB-02'nin tamamlandığı anlamına gelmez.

**0.140.2 doğrulaması:** Genel `./scripts/check` turu 677,096 saniyede
2.024 test çalıştırdı: 2.023 geçti, macOS'ta `systemd-analyze` bulunmadığı
için bir test atlandı. Bu tur başladıktan sonra tamamlanan göreli PATH ve
süreç başlatma kesintisi düzeltmeleri dahil, güncel 33 kurulum testi ayrı
olarak 45,067 saniyede geçti. Son iki regresyon genel turun test keşfine
dahil değildir; kurulumun son hali bu ayrı turla doğrulandı.

Gerçek kurulu theHarvester `--check` komutundan indirmesiz geçti. Yerel
CLI/engine bileşen satırları eşleşti ve seçilen eksik veri dizini oluşmadı.
Geçici gerçek SQLite verisiyle çekirdek (`--core-only`) kurulumu, kayıt,
engine okuma, tekrar çekirdek kurulumu, yedek ve yeni dizine geri yükleme
zinciri geçti; özgün veritabanı ve örnek
kanıt dosyası özetleri korundu. Kabuk sözdizimi, Python derleme, değişiklik
boşlukları ve dokuz belgenin yerel bağlantıları kontrol edildi.

Bu teslim anında gerçek Linux/Actions sonucu okunamamıştı. 0.140.3
çalışması sırasında `9cdf32c` commit'inin
[Ubuntu kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43700800551),
[marka kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43700800538)
ve [hızlı kontrolleri](https://github.com/mstdeveloper33/securehup_xti/actions/runs/43700800548)
başarılı olarak doğrulandı. Ubuntu işinin hem çevrimdışı regresyon hem
gerçek temiz kurulum adımı geçti. Bu kayıt yalnız belirtilen commit
içindir; o sürümde hizmet kabulü ayrıca açıktı. 0.140.4'ün gerçek systemd
ve süreli çalışma sonucu yukarıdadır; 7×24 hizmet seviyesi kabul edilmedi.
Kullanıcı verileri, şema 64 ve incelenmiş araç sürümleri korunur.

- 0.140.1 hızlı CI paketine `engine_contract`, `engine_records`,
  `components` ve `component_pins` test dosyalarını ekler. Marka araç
  kurulumunun push/PR filtreleri ortak pin dosyası ve `xti` başlatıcısını
  kapsar. Tam paket hâlâ ayrıca elle veya sürüm etiketiyle çalışır.
- Komut, toplama oturumu ve ATT&CK kapsamı açıklamaları mevcut davranışla
  eşitlenir. Yeni kaynak, iş davranışı, paket veya şema eklenmez.

**0.140.1 doğrulaması:** `./scripts/check-fast`, 64 seçili test dosyasından
587 testi 250,826 saniyede çalıştırdı: 586 geçti, Linux `systemd-analyze`
bulunmadığı için ilgili tek test atlandı. Altı ayrı kaynak kataloğu testi
geçti. Ağ ve süreç çalıştırma engellenmiş beş CLI örneği doğrulandı;
geçici kaynak veritabanı değişmedi, components/engine describe eksik veri
dizini yaratmadı. Sekiz belgelenmiş komut biçimi toplama başlatmadan
ayrıştırıldı; değişen belgelerin yerel bağlantı ve kod blokları kontrol edildi.
Bu dilimde tam paket yeniden çalıştırılmadı; önceki tam test sonucu aşağıda
kendi sürümüyle korunur. Kullanıcı verisi, şema ve araç sürümleri değişmedi.

- `components` ve engine v1 `components.list`: mevcut Maigret, Sherlock ve
  theHarvester'ın görev, beklenen sürüm/commit, lisans, çalışma ortamı ve
  seçim sınırları tek görünümde. Projedeki kurulum durumu beklenen kimlikten
  ayrıdır; araç çalıştırılmaz, internet veya veritabanı gerekmez.
- Ortak pin kaydı adaptör, yerel kurulum denetimi ve sosyal araç
  doğrulayıcısında kullanılır. Paketleme/installer/ayrı işçi dosyalarında
  kalan sabitlerin uyumu test edilir; tarihî profil kimlikleri korunur.
- `ready` yalnız belirtilen yerel kurulum kontrollerinin uygunluğudur;
  canlı kaynak veya bütün bağımlılıkların çalışma garantisi değildir.
  Sosyal araçlarda alternatif çalışma ortamı, theHarvester'da tam kaynak
  ağacı/geçişli bağımlılık bütünlüğü bu okumayla doğrulanmaz. Eski kanıtlar
  araç eksikken de okunabilir. theHarvester kesinti/geri dönüş dilimi
  0.140.2'de eklendi; tanımlanan Linux işletim kabulü 0.140.4'te tamamlandı.
  ENG-03'ün olay adayı dilimi 0.141.0'da, kayıtlı arama 0.142.0'da eklendi;
  RSS/haber sıradadır.
- Sosyal kurulum doğrulayıcısı, Git kaynak bilgisindeki nesne dışı JSON'u
  beklenmedik istisna yerine kontrollü hata olarak bildirir. Araç yükseltmesi,
  paket veya şema değişikliği yoktur.
  [Kullanım](COMPONENTS.md), [0144 kararı](decisions/0144-reviewed-component-catalog.md).

**0.140.0 doğrulaması:** 25 yeni hedefli test geçti. Gerçek CLI ve engine
süreçlerinde bileşen satırları aynı çıktı; seçilen eksik veri dizini
oluşturulmadı. Kurulum seçeneği içeren istek denetim öncesi reddedildi.
Bu projedeki üç araç `ready` göründü; yalnız kurulum bilgileri denetlendi.
`./scripts/check` 696,946 saniyede 1.979 test çalıştırdı: 1.978 geçti;
Linux `systemd-analyze` bulunmadığı için ilgili tek test atlandı. Bu sonuç
gerçek Linux hizmet işletimi veya .NET tüketici kabulü değildir. Yeni
25 test tam pakete dahildir; şema 64 ve kullanıcı verileri değişmedi.

- `engine --describe`: v1 işlem, kayıt türü, kapsam ve sınırları ağsız
  ve kayıt alanı olmadan gösterir. `engine` tek UTF-8 JSON isteğini alır;
  `search`, `record.get`, `sources.status`, `components.list` için tek
  sürümlü stdout JSON cevabı üretir. Yinelenen/bilinmeyen alan, geçersiz tür, sürüm, işlem,
  boyut ve derinlik açık hata olur; JSON ile dosya yolu veya yetki seçilmez.
- Arama on kayıt ailesini mevcut servisle okur; tür/kaynak alanı/kimlik
  referansı ayrıntıya bağlanır. Ayrıntı gerçek kayıt, kaynak/kanıt ve
  sayfalı geçmiş bölümleridir. Katalogdan çıkarılmış kayıt, eski sosyal
  çalışma ve ayrı ransomware kaynakları korunur. Kuruluş grupları
  müşteri yalıtımı olarak sunulmaz.
- Yerel okumanın tamamlanması kaynak başarısı değildir: hata, son başarı,
  güncellik ve hiç çalışmama ayrı kalır. Arama/ayrıntı ayrı okuma kesitleri,
  kaynak durumu bağımsız kaynak okumalarıdır. Eski CLI JSON değişmez;
  iş başlatma, .NET tüketici, ağ erişimi veya yeni bağımlılık eklenmedi.
  [Sözleşme ve kullanım](ENGINE_CONTRACT.md), [0143 kararı](decisions/0143-versioned-engine-read-contract.md).

**0.139.0 doğrulaması:** `./scripts/check` 701,473 saniyede 1.954 test
çalıştırdı: 1.953 geçti, Linux `systemd-analyze` bulunmadığı için ilgili
tek test atlandı. Yeni engine sınırına ait 36 test bu kapsamdadır.
Ayrıca gerçek `./xti` süreci ve stdin/stdout üzerinden geçici veritabanında
arama → referansla ayrıntı → kaynak durumu zinciri çalıştı; dosya özetleri
değişmedi. Üç belgelenmiş istek örneği doğrulandı. Kullanıcı verisi veya
şema değiştirilmedi; canlı hedef sorgusu yapılmadı. Bu kabul gerçek Linux
hizmet işletimi veya .NET tüketicisi kabulü yerine geçmez.

- `search QUERY` on tür yerel kaydı tek salt okunur kesitte arar; tam/başlangıç/
  içerme sırası, tür filtresi, toplamlar, sayfalama ve ayrıntı komutları vardır.
  `--all` etkin olmayan/çıkarılmış kayıtların son bilinen halini de gösterir;
  tüm sürüm arşivi değildir. Kaynak hatası ve son başarı ayrıca görünür.
- `suppliers watch` ThreatCluster, RansomLook ve HIBP için ayrı açık izleme
  seçer. Başarılı kaynak yenilemesiyle aynı işlemde karşılaştırma ve yerel
  bildirim kaydedilir. İlk ölçüm/yeniden açma/kimlik değişimi sessizdir;
  yeni/değişen eşleşmeler bildirilir. Kaynak hatası, tekrar ve yalnız
  çıkarılma bildirim üretmez. Tarihî tedarikçi ve önce/sonra kaynak kanıtı
  korunur; ad belirsizliği ihlal hükmüne dönüştürülmez.
- `surface relations DOMAIN` kayıtlı DNS/IP, TLS sertifikası, CNAME ve insan
  tedarikçi kararlarını ilk/son gözlemle birleştirir. `--history` başarısız ve
  boş kontroller dahil tek tek kanıtları sayfalar. Gözlemlerden kesintisiz
  geçerlilik, sahiplik veya kaydedilmemiş eski kanıt bağı çıkarılmaz.
- Şema 64 dört boş tedarikçi izleme tablosu ekler; açık yedekli geçiş gerekir.
  Üç özellik yeni paket veya ücretli API eklemez. Kullanım:
  [arama, tedarikçi ve ilişki rehberi](SEARCH_SUPPLIERS_AND_RELATIONS.md).

- `cases evidence-add --type public_notice|public_notice_watch` tam tarihî
  çalışma ve olay kimliğini vakaya bağlar; önce/sonra metadata, kaynak
  sınıfları, atıf/lisans ve ilgili tarihî kuruluş kapsamı dondurulur.
  Kaynak sonradan değişse/çıkarılsa da kanıt korunur. `cases evidence-show`
  tek kanıtı görünüm sınırından bağımsız açar; insan kararı değişmez.
- `organizations export ID --output YENI.html` tek SQLite okuma kesitinden
  bütün etkin hedefleri, bütün bölüm kayıtlarını ve kuruluşun kamu olay
  izleme geçmişini çevrimdışı açılan tek HTML dosyasına aktarır. Yüzey
  bölümü son kontrol kanıtı ve son başarılı çalışma durumudur; bütün eski
  kontrol serisi değildir. Açık kapasite sınırı aşılırsa eksik rapor yazılmaz.
  Dış betik/font/görsel yüklenmez; mevcut dosya üzerine yazılmaz.
- Şema 63 yalnız vaka kanıtı tür kısıtını genişletir. Eski satır kimlikleri,
  rowid, snapshot ve olay geçmişi yedekli geçişte korunur. Kullanım
  [vaka ve HTML rehberindedir](PUBLIC_NOTICE_CASES_AND_EXPORT.md).

- `notices watch enable/disable/list/show` kuruluş için açık HIBP izleme
  seçimini ve ağsız kapsam/geçmiş görünümünü sağlar. `watch-run-show` gerçek
  tarihî domain kapsamını, kaynak çalışma kimliklerini ve tüm önce/sonra
  kayıtlarını sayfalar; değişmeyen kayıtlar yalnız sayıya indirgenmez.
- HIBP yenilemesi bütün açık izlemeleri aynı kaynak işleminde değerlendirir.
  Başlangıç/yeni domain/yeniden etkin kapsam sessizdir; mevcut kapsamın
  yeni/değişen eşleşmeleri çalışma başına tek yerel bildirim üretir. Kaynak
  hatası, tekrar ve yalnız çıkarılma bildirim üretmez. Ad/gerekçe değişikliği
  karşılaştırmayı sıfırlamaz; etkinleştirme dönemleri domain başına izlenir.
- Kaynak, izleme, bildirim ve varsa toplama tamamlanma bağı birlikte
  kaydedilir. Tarihî bildirim tam kaynağa ve kuruluş/bağlantı olaylarına
  bağlıdır; güncel üyelikle yeniden yazılmaz. Yerel kutuda atıf/lisans,
  önce/sonra metadata, bağımsız okundu durumu ve sayfalama korunur.
- Kuruluş raporu kendi kamu olay izleme geçmişini güncel hedeflerden ayrı
  gösterir; aynı domaini kullanan kuruluşların bildirimleri karışmaz. Çalışma
  ve tanım geçmişi ayrı offset'lerle, raporda mevcut item-offset ile gezilir.
- Şema 62 dört boş tablo ekler; eski veriden izleme/bildirim üretmez.
  Yedekli açık geçiş ve geri dönüş vardır. Kullanım
  [kamu olay izlemesi rehberinde](PUBLIC_NOTICE_WATCHES.md) açıklanır.

- `collect DOMAIN --task notices-hibp`: HIBP kamu kataloğunu açık seçimle
  mevcut toplama oturumuna bağlama. Profilde saklanır, mevcut Linux zamanlama
  akışı kullanır; kayıtlı domain gerekir. Varsayılan üç iş ve eski profil
  seçimleri değişmez. `--task` tam seçimdir; önceki işleri örtük eklemez.
- Kaynak çalışma/farkları ve toplama tamamlanma bağı aynı transaction içinde
  kaydedilir. Hata da kendi kaynağıyla saklanır; son başarılı katalog korunur.
  Kaynak commit'i sonrası üst işlem kesilirse devam başarılı HIBP'yi yeniden
  indirmez. Yalnız eksik işler yeni yürütmede çalışır.
- Önizleme, profil kaydı ve zamanlama hazırlığı ağsızdır. Seçilen bütün
  depolar, kaynak isteğinden önce doğrulanır; kaynak yazımında işlem kimliği,
  profil/oturum, kaynak sözleşmesi ve gerçek sonuç yeniden doğrulanır.
- Katalog sayıları ortak kaynak kapsamıdır; domain veya kuruluş bulgu sayısı
  değildir. İlk başarılı alım başlangıçtır; kaynak atfı/lisansı terminal,
  JSON, geçmiş ve korunmuş sonuçlarda bulunur. Kuruluş dönem raporu yalnız
  kaynakta tam domain eşleşen olayları ilgili kaynak kaydı olarak gösterir;
  bu eşleşme tek başına doğrulanmış ihlal kararı değildir.
- Şema 61 yalnız mevcut toplama adım ve tamamlanma tablolarını genişletir;
  eski kimlikler/alanlar/özetler korunur, yeni kaynak bağlantısı eskilerde
  boştur. Açık yedekli `migrate` gerekir. HIBP vaka kanıtı ve
  HTML rapor 0.137.0 ile eklendi; [devam planı](roadmap/PUBLIC_NOTICE_WORKFLOW_PLAN.md).

- `organizations report ID`: yalnız güncel etkin açık bağlantılardaki domain,
  dış yüzey, sosyal profil ve iki ransomware kaynağı; tam kayıtlar ve
  sayfalama, son deneme/son başarı, eski/eksik veri, bildirim/vaka gezinmesi.
  Kuruluş, hedef ve bütün kanıtlar tek salt okunur kesitten okunur. Başka
  kuruluşun vaka içeriği rapora katılmaz; kanıt bağı geçmişi doğrulanır.
- `changes --organization ID --days 1|7`: güncel üyelikle seçilen dönem;
  geçmiş sahiplik çıkarılmaz. Karma oturumda yalnız ilgili adımlar görünür.
  `--offset` bütün kategorilere ve kapsama listesine sayfa başlangıcı verir.
  DNS/TLS/web/posta/servis/CNAME ve sosyal değişimlerinde gerçek önce/sonra
  değerleri, önceki kanıt ve çalışma kimlikleri korunur; hata boş başarı sayılmaz.
- `sources contribution --organization ID`: her domain/kural/kaynak için
  ayrı gerçek katkı ve deneme pay/paydasını tek okuma anında gösterir.
- `cti context --type domain --value DOMAIN` veya `--entity ID`: kayıtlı
  doğrudan varlık/IOC ilişkileri, bağımsız kaynak iddiaları, geçerlilik ve
  geri çekilme, sayfalama ve sonraki varlığa geçiş. Aynı isimden veya dolaylı
  bağdan yeni atıf üretilmez; güncel kayıt olay geçmişiyle doğrulanır.
- `notices refresh/status/search/show/run-show`: HIBP'nin anahtarsız kamu
  olay metadata kataloğu. Kişi/e-posta/parola sorgusu yok; ilk başarılı alım
  başlangıç, sonraki ekleme/değişme/çıkarma ayrı. Kaynak hatası son başarıyı
  korur. Kaynak bayrakları, Have I Been Pwned atfı ve CC BY 4.0 lisansı
  bütün metadata görünümlerinde bulunur. `notices` grubunda yalnız açık
  `refresh` ağ kullanır; toplamada ayrıca `notices-hibp` seçilebilir.
- HIBP tam domain eşleşmeleri kuruluş ve dönem raporuna; ortak katalog
  durumu `sources status` içine katılır. Kaynak kataloğu `sources`
  içinde erişim koşullarını açıklar. Canlı tek istekle 1.052 kayıt alınıp
  geçici SQLite'a yazıldı; `adobe.com → Adobe` yerel araması doğrulandı.
  Bu tarihli kabul ölçümüdür; gelecekteki kapsam/güncellik garantisi değildir.
- Şema 59→60 yalnız `public_notice_runs` ve `public_notice_changes` tablolarını
  ekler; açık `migrate` benzersiz yedek alır. Eski kayıtlar yeniden yazılmaz.
  Kullanım [kuruluş rehberinde](ORGANIZATION_REPORT.md), kaynak kabulü
  [ayrı kayıttadır](PUBLIC_NOTICE_SOURCE_ACCEPTANCE.md).

- `schedule generate` kayıtlı profil için Linux kullanıcı hizmeti/zamanlayıcısı
  ve tam kurulum komutlarını yeni klasöre üretir; kendisi etkinleştirmez.
  Günlük/haftalık saat, saat dilimi ve son 1–30 yönetilen yedek seçilebilir.
- `schedule prepare` ortak kilit altında güncel plan, disk ve kesinti kontrolü;
  benzersiz SQLite yedeği ve yeni dosyaya gerçek kurtarma doğrulaması yapar.
  Saklama aynı veritabanının bütün profillerce paylaşılan yönetilen havuzuna
  uygulanır; elle/geçiş yedekleri silinmez. Bozuk sahiplik veya değişmiş yedek
  işlemden önce durdurur. Yarım yayın/silme kayıtları sonraki hazırlıkta toparlanır.
- Hizmet kısmi/busy çıkışlarını saklar; peş peşe yeniden başlatmaz. Profil
  değişirse sonraki tur güncel seçimi kullanır. macOS'ta dosya üretimi, argüman
  iletimi ve bakım sınandı; gerçek Linux hizmeti etkinleştirilmedi. Linux'a özel
  ayrıştırıcı testi burada atlanır. [Kullanım](LINUX_SCHEDULING.md).

- `organizations add/list/show/link/unlink/rename/revoke/reactivate`:
  kayıtlı domain ve sosyal/ThreatCluster/RansomLook izlemelerini kullanıcının
  açık seçimiyle gruplama. Şema 57 tam değişiklik geçmişini ve gerçek kaynak
  bağlantılarını korur. Gruplama sahiplik/olay hükmü veya toplama seçimi değildir.
- `changes --days 1|7`: son 24/168 saatin yerel yeni/değişen kayıtları,
  başlangıç ölçümleri ve kaynak hataları; her satırda dayanak kimlikleri.
  Varsayılan tüm yerel aileler; `--domain` marka/dış yüzey/kamu olayları,
  `--organization` etkin bağlı hedeflerdir. Komut ağsız, yazmasız ve tek okuma anına dayanır;
  bölümlerin toplamı “benzersiz tehdit” sayısı diye sunulmaz.
- `cti attack-status/search/show`: şema 58'de kesin STIX/ATT&CK kimlikli
  grup, kampanya, malware, teknik, alt teknik ve taktik kataloğu. Aynı adlı
  teknikler ayrı kalır. `attack-sync` tek resmî indirmeden eski CTI ve ek
  kataloğu birlikte kaydeder; bir hata ikisini de geri alır. Başarılı senkron
  ve değişim geçmişi tutulur; teknik/taktik alan bağı STIX ilişkisinden ayrıdır.
  Arama ve ilişkiler sayfalanır; eski CTI kanıtı yeniden biçimlendirilmez.
- `sources contribution DOMAIN`: kaynakların gerçek ortak/ayrı domain
  listeleri, kanıt/deneme kimlikleri ve tamamlanma pay/paydasını ağsız gösterir.
  Alt alan keşfi ve marka araması; marka tarafında kural/yazım varyantı
  grupları ayrı kalır. Çok hedefli veya sonucu eksik denemeden domain atfı
  uydurulmaz. Ayrıntı sayfası toplamları değiştirmez; insan kararları korunur.
- Kaynak ölçümü ve [sağlayıcı değerlendirmesi](roadmap/SOURCE_PROVIDER_EVALUATION.md)
  tamamlandı; bağımsız katkı kanıtlanmadığı için yeni domain keşif adaptörü eklenmedi.
  Common Crawl'ın dış erişim sorunu açık. Ücretsiz kaynaklara sınırsız veya
  kesintisiz erişim taahhüt edilmez.
- RansomLook izleme farkları şema 59'daki ayrı kaynak tablosuyla yerel
  `inbox` içine gelir. Sessiz başlangıç sonrası yeni/değişen eşleşmeli çalışma
  tek bildirim oluşturur; tekrar, yalnız çıkarılma ve kaynak hatası oluşturmaz.
  Çalışma, öğeler, bildirim ve toplama sonucu aynı işlemde saklanır. Bildirimde tam
  izleme ve kaynak çalışma kimliği görünür; okundu ve insan kararı ayrıdır.
- Şema 57–59 için açık `migrate` ve geçiş öncesi benzersiz yedek gerekir.
  Eski kayıtlardan kuruluş, ATT&CK katalog geçmişi veya RansomLook bildirimi
  türetilmez. Gerçek veritabanı kopyasında 117 eski tablonun bütün satırları
  korundu; 10 yeni tablo boş başladı, yedekten geri dönüş aynı veriyi verdi.

- `collections list/show`, `collections resume ID [--plan]` ve
  `collections recover`; yeni `collect` çalışmaları gerçek kaynak kayıtlarına
  bağlı oturum kimliği üretir. Eski bağımsız kaynak kayıtlarından geriye dönük
  oturum uydurulmaz. Şema 56 açık ve yedekli geçiş ister.
- Kaynak sonucu ve tamamlanma bağı aynı transaction'da tutulur; üst komut
  kayıttan hemen sonra kesilse de tamamlanan izleme kaybolmaz/tekrar edilmez.
  Ransomware kaynak yenilemesi ile her üye ayrı adımdır. Eksik üyeler yeni
  başarılı yenilemeye bağlanır; kaynak hatasında eski liste kullanılmaz.
- Devam yeni yürütmedir; eski kısmi/başarısız sonuç korunur. Kaynak profil
  revizyonu veya eksik işin tanımı/sürümü değişmişse yeni toplama gerekir.
  Toplamaya ait scan işleri genel kuyruktan ayrılır. Kilitli kurtarma yalnız
  kesilmiş açık işleri kapatır; kaynakları sorgulamaz.
- Geçmiş/önizleme ağsız ve yazmasızdır. Geçmiş komutu analiz üretmez; devam
  sonundaki güncel yerel analiz ayrıca gösterilir. Analiz hatasında kaynak
  kayıtları korunur ve yalnız analiz için kaynaklara tekrar gidilmez.

- `profiles save AD DOMAIN`, `profiles list/show/revoke` ve
  `collect --profile AD [--plan]`: domain, temel işler, seçili izlemeler ve
  görünüm seçenekleri tam tanım olarak kaydedilir. Aynı adla save tam seçimi
  değiştirir; eski seçimler örtük eklenmez. Varsayılanlar kayda açık yazılır.
- Şema 55: profil ve eklemeli tam tanım geçmişi; revizyon, SHA-256, kanonik
  sürümlü JSON ve yaşam döngüsü doğrulaması. Değişmeyen save yeni olay üretmez;
  geri çekme kaydı silmez, yeniden kaydetme aynı kimlikle etkinleştirir.
- Domain/izlemelerin ağ öncesi doğrulanması, ortak kilit altında profil
  revizyonunun yeniden kontrolü. Plan/liste/ayrıntı ağsız ve yazmasızdır.
  Profil gruplaması kuruluş veya sahiplik bağı sayılmaz. Açık yedekli
  `migrate` gerekir. Profil ve toplama oturumu ayrı kayıtlar olarak tutulur.
- theHarvester kaynak kanıtı aynı hostname farklı zamanda tekrar gelince
  çakışmaz. Türetilmiş özet gözlem zamanını da kapsar; eski kanıtlar ve insan
  kararları korunur, aynı gözlemin tekrarında aday çoğaltılmaz. Bu düzeltme
  Common Crawl'ın dış erişim sorununu çözüldü saymaz.

- `collect DOMAIN --username-watch ID --ransomware-watch ID --ransomlook-watch ID`
  ile kayıtlı sosyal/ThreatCluster/RansomLook izlemelerinin açık seçimi;
  seçenekler isteğe bağlı ve tekrarlanabilir. Temel `--task` seçimine veya
  varsayılan üç işe eklenir; domain adından kişi/kuruluş ilişkisi çıkarılmaz.
- Önizlemede kaynak, ad, platformlar ve eşleşme türü; bütün seçili izlemelerde
  ağ öncesi etkinlik/geçmiş doğrulaması ve aynı çalışma kilidi. Kimlik tekrarı,
  bulunamayan/geri çekilmiş kayıt veya toplam 50 seçimin aşılması ağ öncesi
  reddedilir. Seçilmeyen kaynak adaptörü ve izleme çalıştırılmaz.
- Her ransomware kaynağını bir kez yenileme; yalnız seçilen izlemeleri tam o
  yenilemenin kimliğiyle çalıştırma. Yenileme hatasında eski veriyle izleme
  yazılmaz; diğer kaynakların tamamlanması hatalı kaynağı başarıya çevirmez.
- Başlangıç ve sonraki farklar, profil adresleri, iddia satırları, çalışma
  kimlikleri ve gösterilmeyen öğe sayısı terminal/JSON sonucunda ayrı kalır.
  `--watch-item-limit` 1–500 arasında görünüm sınırıdır; kalıcı sonuç kesilmez.
  İzleme sonuçları domain analizinden ayrı tutulur. Kaynak sınırları, mevcut
  karar/bildirim kuralları ve şema 54 korunur.

- `collect DOMAIN` ile kayıtlı domain için crt.sh/urlscan marka aramalarını
  ve crt.sh pasif alt alan adı keşfini tek uygulama servisinde çalıştırma.
  `--task` ile yalnız seçilen işler; isteğe bağlı theHarvester arşivi ve
  Feodo/CERT Polska IOC yenilemesi. `--plan` ağsız/yazmasız önizlemedir.
- Her seçili adımın kaynak sonucu, gerçek iş/deneme/keşif/IOC kimliği ve
  sayaçları ayrı kalır. Beklenen kaynak hatası sonrası diğer adımlar devam
  eder; depolama/bütünlük hatasında yeni adım başlatılmaz. Genel kısmi/hata
  durumu son birleşik analiz tarafından başarıya çevrilmez.
- Ortak çalışma kilidi, kayıtlı hedef ve seçili depoların ağ öncesi
  doğrulaması; tekrarında mevcut tekilleştirme/insan kararlarını koruma.
  Terminalden bağımsız servis ve JSON sonucu ilerideki React/API bağlantısına
  temel oluşturur. 0.132.0 katmanı kalıcı birleşik oturumu ayrıca tutar.

- Arşiv v3 işçisi, sabit theHarvester kurulumundan indeks/hostname/sayfa
  ayrıştırma yardımcılarını kullanır; upstream dosyalarını değiştirmez.
  Yalnız resmî Common Crawl/Wayback HTTPS uç noktalarına ve kayıtlı domain
  sorgularına izin verir. TLS doğrulanır; yönlendirme/proxy açılmaz.
- HTTP hatası, TLS hatası, bağlantı kapanması, zaman aşımı, bozuk veri ve
  başarılı boş yanıt ayrı kalır. 429/503 bekleme bilgisi korunur; anında
  tekrar yapılmaz. Diğer geçici bağlantı hatalarında bütçe içinde bir tekrar
  vardır; Common Crawl bağlantı hatasında 60 saniye bekler. Yeni deneme
  için süre/istek hakkı yoksa beklemeden asıl hata korunur. Common Crawl
  istekleri seri çalışır; her yanıtın bitişinden sonra en az bir saniye ayrılır.
- Wayback tek domain sorgusunu küçük sayfalar ve devam anahtarıyla yürütür.
  Common Crawl sayfasında ilk 50 kayıt sonrasını atlama davranışı giderilir.
  Common Crawl için 150, Wayback için 90 saniye; kaynak başına 30 istek,
  süreçte 270 saniye ve yanıtta 2 MiB sınırı vardır. Sınırda durma kısmi
  kapsamdır; tamamlanan sayfalar korunur.
- theHarvester `--no-editable` ile standart paket olarak kurulur; gizlenmiş
  `.pth` dosyasına bağımlılık kalkar. Kurulum kontrolü checkout dışında
  yapılır. Ayrı Python ortamı eksikse sorgu başlamadan açıklayıcı hata verilir.

- `scripts/setup-harvester`, PATH'te `uv` bulunmazsa proje içindeki
  `.tools/uv/bin/uv` aracını kullanır. Python/önbellek varsayılanları `.tools`
  içinde kalır; açık ortam ayarları korunur. Araç ayrı Python ortamında,
  aynı incelenmiş upstream commit ve kilitli bağımlılıklarla kurulur.
- theHarvester iki arşivi de tamamlayamadığında doğrulanmış kaynak/durum/durma
  nedenlerini hata açıklamasında saklar. Hata boş başarıya çevrilmez;
  kullanıcı kaydı veya önceki adaylar silinmez.

- `sources status [--domain KÖK] [--details]` ile 11 kaynak/iş akışının yerel
  kurulumu, son denemesi, son başarılı verisi, güncelliği, hata/bekleme bilgisi
  ve sonraki komutu. Tarama/keşif kaynakları, sosyal araçlar, IOC, ransomware
  ve MITRE ATT&CK kapsamı ayrı satırlarda korunur.
- Kısa terminal tablosu, ayrıntılı görünüm ve JSON çıktısı; ağ/veri yazımı
  olmadan çalışma. Hazırlanmamış veritabanını oluşturmayıp `./setup` önerme.
  MITRE ATT&CK için mevcut başarı kanıtını gösterme; tutulmayan başarısız
  senkron geçmişinden son deneme uydurmama. Şema 54 değişmez.
- [Günlük kullanım rehberi](DAILY_USE.md) ve toplama → inceleme → vaka → tekrar
  akışının bütünleşik testleri. Aynı kanıtın tekrarında kimlik/vaka geçmişi
  korunur; kaynak hatası önceki başarılı sosyal ölçümü silmez.

- `surface discovery-health KÖK` ile crt.sh ve theHarvester'ın son kayıtlı
  çalışmalarını birbirinden bağımsız gösterme. Tamamlandı, kısmi, başarısız,
  hiç çalışmadı; güncel, eski ve zaman tutarsızlığı durumlarını ayrı tutma.
  Bir sağlayıcının tamamlanmasını diğerinin hatasını örtecek genel başarıya
  dönüştürmeme.
- `surface discovery-status KÖK --source crt.sh|theharvester` ile tek
  sağlayıcının son kanıtını seçme; seçim verilmediğinde önceki en-son-çalışma
  davranışını ve JSON biçimini koruma.
- Sağlayıcı durumunu yalnız kayıtlı geçmişten ve salt okunur üretme. Ağ
  isteği, canlı sağlık iddiası, veri yazımı veya migration başlatmama; her
  eksik/eski/hatalı satırda sağlayıcıya özgü sonraki komutu gösterme.
- `surface source-evaluation` ile çalışma zamanı sağlayıcı kümesine birebir
  bağlı, sürümlü ve ağsız pasif adaptör kabul kapısı. crt.sh ve sınırlı
  theHarvester profilini kabul etme; Subfinder v2.17.0 normal CLI'sini kaynak
  hatası/tamamlanma kanıtını JSONL'de korumadığı ve bağımsız ücretsiz kapsam
  katkısı gösterilmediği için erteleme.
- theHarvester keşfiyle kaydedilen aday kaynak kanıtını ayrıntı ve birleşik
  bildirim yolunda crt.sh ile aynı katı doğrulamayla okuyabilme. Sağlayıcıdan
  bağımsız metinlerde “pasif kaynak kanıtı” kullanma. Şema 54'ü değiştirmeme.

- `./setup` ile Maigret 0.6.6 ve Sherlock 0.16.2'yi kullanıcı global Python
  ortamını değiştirmeden sabit resmî Git commit'lerinden `.venv` alanına
  kurma; eski ortamı doğrulama bitene kadar geri dönüş kopyası olarak koruma ve
  hata/sinyal/yetim kurulumda geri getirme.
- Kurulumda paket sürümü, resmî depo adresi, tam istenen/çözülen commit,
  katalog dosyası türü/boyutu/SHA-256 özeti, geniş profil URL izinleri,
  incelenmiş tam geçişli bağımlılık sürümleri, bağımlılık tutarlılığı ve
  Maigret çalıştırıcısını kapalı biçimde doğrulama. Kullanıcı pip ayarlarından
  yalıtılmış resmî PyPI/GitHub kaynakları kullanma.
  Geçerli kurulumda yeniden indirmeme; `--check`, `--force` ve
  `./setup --core-only` yollarını açık tutma.
- Kullanıcı adı önizlemesi ve kalıcı izlemede birbirini dışlayan `safe`,
  `extended` ve tekrarlı `--site` özel kapsamı. Maigret için 6/30, Sherlock
  için 5/26 platform; upstream tam kataloğunu, HTTP, NSFW ve incelenmemiş
  hedefleri çalıştırmama.
- Önizlemede seçim profilini terminal/JSON sonucunda gösterme. Kalıcı izleme
  oluşturulurken profil adını değil çözülen tam platform listesini saklama;
  gelecekteki profil değişikliğinin mevcut izleme kapsamını sessizce
  değiştirmemesi. Şema 54'ü değiştirmeme.
- CI'da ilgili kurulum dosyaları değiştiğinde temiz Python 3.11 ortamında
  varsayılan kurulumu ve ikinci ağsız bütünlük denetimini çalıştırma.

- `./setup` ile temiz bir Git klonunda global Python ortamını değiştirmeden
  yerel kayıt alanını başlatma. Çekirdekte harici Python bağımlılığı istememe;
  eski şemayı otomatik taşımama ve kullanıcıyı açık `migrate` işlemine
  yönlendirme.
- README başında kısa klonlama, ilk domain ve tarama akışı; ayrı hızlı başlangıç
  belgesinde veri konumu, yedek, güncelleme ve doğrulanmış sosyal araç kurulumu.
- GitHub'da her `main` gönderimi ve pull request için Python 3.11 üzerinde kısa
  ağsız kapı; elle veya `v*` etiketinde Python 3.13 üzerinde tam regresyon;
  yalnız başarılı etiket kontrolünden sonra GitHub sürümü oluşturan ayrık,
  en-az-yetkili iş akışları. Güncel resmî Node 24 tabanlı GitHub action'larını
  kullanma ve checkout kimlik bilgisini çalışma dizininde kalıcı tutmama.
- `.xti-data`, sanal ortamlar, üçüncü taraf araçlar, veritabanları, ortam
  dosyaları ve derleme çıktılarının kaynak kontrolü dışında tutulması.

- `cases create/list/show/update/status` ile gerekçeli başlık, özet, öncelik, durum, sonuç, kapanış ve yeniden açma yaşam döngüsü. `resolved/closed` için sonuç isteme ve açık görev varken kapanışı reddetme.
- `cases note-add`, `task-add/task-update` ile gözlem/aksiyon/karar/kapanış notlarını ve açık/tamamlanmış/iptal görevleri tek sıralı zaman çizelgesinde tutma. Kapalı vakadaki kanıt/görev değişikliği için önce açık yeniden açma.
- `cases evidence-add/remove` ile domain/marka bulgusu, insan kararlı sosyal profil, ThreatCluster iddiası, RansomLook iddiası ve tedarikçi inceleme kartını ayrı kaynak kimlikleriyle bağlama. Kaynak modülünün bütünlük denetiminden geçen sınırlı anlık görüntüyü dondurma; değişmeyen tekrarı tekilleştirme, değişeni yenileme ve çıkarılan bağı geçmişten silmeme.
- `cases report` ile etkin kanıt, açık görev, durum, öncelik ve sonuç özetini ağsız terminal/JSON olarak gösterme. Vakayı otomatik tehdit/ihlal/sahiplik/etki hükmüne veya dış aksiyona dönüştürmeme.
- Vaka güncel durumu ile son yaşam döngüsü anlık görüntüsünü karşılaştırma; bozuk kanıt özeti, kaynak geçmişi veya zaman çizelgesinde kısmi görünüm üretmeden güvenli durma.
- Şema 53→54 geçişinde dört boş vaka tablosunu doğrulanmış yedek ve transaction ile ekleme; eski veriden vaka uydurmama, hata halinde rollback. `doctor` içinde vaka/açık vaka/etkin kanıt/açık görev/aktivite sayaçları.

- `suppliers risk-list/show` ile etkin tedarikçi envanteri, kabul edilmiş güncel CNAME bağları, ThreatCluster/RansomLook kapsamı ve son kaynak iddiası adaylarını tek ağsız, salt-okunur terminal/JSON kartında birleştirme.
- Her kartta insan beyanlı iş önemi, güncel teknik bağımlılık, iddia/kaynak sayısı, domain ve yalnız-ad dayanakları, aynı-ad belirsizliği, en yeni iddia/snapshot zamanı, eksik/eski kaynak verisi ve önerilen insan adımlarını ayrı gösterme.
- Açıklanabilir `priority_review`, `review`, `identity_review`, `insufficient_data` ve `no_current_match` durumları. Aynı ad belirsizliğini yüksek iş önemiyle otomatik öncelikli olaya çevirmeme; önce kuruluş kimliğini ayırma.
- Başarılı boş snapshot ile kaynak verisi yok/hatalı durumunu ayırma. Sıfır eşleşmeyi güvenli olma, kaynak iddiasını doğrulanmış ihlal veya tedarikçi/kullanıcı etkisi saymama.
- Kartı sayısal risk skoru, alarm, dış mesaj, engelleme veya otomatik aksiyona dönüştürmeme. Kaynak, CNAME ve tedarikçi kayıtlarının özgün kimliklerini koruma.
- Şema 53'ü değiştirmeden tedarikçi çekirdek zincirini envanter → teknik bağımlılık → kaynak iddiası → açıklanabilir insan incelemesi olarak tamamlama.

- `suppliers event-list` ile etkin insan onaylı tedarikçileri ThreatCluster ve RansomLook'un son başarılı yerel snapshot'larıyla ağsız ve salt okunur eşleştirme; tedarikçi ve kaynak filtresi ile kararlı terminal/JSON sunma.
- ThreatCluster'da tam kuruluş adı ile ilk-taraf web domainini ayrı dayanaklar olarak kullanma; RansomLook'ta yalnız tam kuruluş adı kullanma. Yaklaşık ad benzerliği veya CNAME'den olay üretmeme.
- Aynı isimli ayrı tedarikçileri ayrı adaylar olarak koruma ve isim eşleşmesinin kaç etkin tedarikçiye uyduğunu açık gösterme. Domain eşleşmesini ad eşleşmesinden ayrı kanıt olarak sunma.
- `event-show` ile kararlı görünüm kimliği, tedarikçi kimliği/iş önemi, özgün kaynak/snapshot/kayıt kimliği, grup, kuruluş, zaman ve bütün eşleşme dayanaklarını gösterme.
- Kaynak hiç toplanmadı, kullanılabilir, son deneme hatasından sonra önceki başarılı snapshot kullanılıyor ve başarılı snapshot yok durumlarını ayırma; sıfır eşleşmeyi kaynak hatası veya güvenlik hükmü saymama.
- Kaynak kayıtlarını birleştirmeme; iddiayı doğrulanmış ihlal, tedarikçi etkisi, alarm veya risk puanına çevirmeme. Komutlarda internet, veri yazımı, bildirim ve dış aksiyon başlatmama.
- Şema 53'ü değiştirmeden mevcut tedarikçi ve ransomware geçmişlerini salt okunur kullanma.

- `suppliers candidate-refresh` ile etkin dış yüzey kapsamının kayıtlı son CNAME kanıtını ağsız inceleme; kaynak ve hedef PSL kayıt kökü farklıysa yalnız teknik dış hizmet adayı oluşturma.
- Adayı kaynak varlık + dış hizmet kayıt köküyle tekilleştirme; yeni CNAME kontrollerini ayrı kanıt olarak ekleme ve artık son kanıtta görünmeyen adayı silmeden tarihsel duruma geçirme.
- Her kanıtta CNAME kayıt kimliği/özeti, tam kaynak/hedef domain, gözlem zamanı ve kullanılan Public Suffix List sürüm/özetini koruma.
- `candidate-list/show/review` ile bekleyen, kabul, belirsiz ve ret durumlarını ağsız inceleme. Kabulü yalnız önceden insan tarafından kaydedilmiş etkin tedarikçiye bağlama; kararı geri alabilme veya başka tedarikçiye gerekçeyle taşıma.
- Ortak altyapı, aynı isim veya CNAME hedefini otomatik kuruluş/sözleşme/risk hükmüne çevirmeme. Bozuk aday, kaynak kanıtı veya karar zincirinde kısmi görünüm ve sessiz onarım üretmeme.
- Şema 52→53 geçişinde boş aday/kanıt/karar tablolarını doğrulanmış yedek ve transaction ile ekleme; mevcut tedarikçileri ve bütün eski veriyi koruma, migration sırasında eski CNAME'den aday uydurmama.

- `suppliers add/list/show/update/revoke` ile kuruluş adı, değiştirilemez ana domain, ilişki türü, iş önemi ve gerekçeye bağlı insan onaylı yerel tedarikçi envanteri.
- Aynı isimli kuruluşları farklı ana domainlerde ayrı tutma; aynı etkin domainin farklı bilgiyle sessizce ezilmesini reddetme. Ortak ad veya altyapıdan otomatik kuruluş birleştirmeme.
- Ekleme, güncelleme, pasife alma ve yeniden etkinleştirmeyi tam anlık görüntülü, silinmeyen olay geçmişinde saklama; aynı isteği idempotent tutma ve liste/ayrıntıyı ağsız/salt okunur sunma.
- Tedarikçi kaydını otomatik güven/risk hükmü, skor, alarm veya internet sorgusuna dönüştürmeme. Kaynaklı iddia görünümü, dış bağımlılıktan teknik aday ve açıklanabilir inceleme kartını ayrı kanıt kimlikleriyle sunma.
- Şema 51→52 geçişinde boş tedarikçi tablolarını doğrulanmış yedek ve transaction ile ekleme; mevcut veriyi koruma ve hata halinde rollback.

- `./scripts/setup-harvester` ile incelenmiş upstream commit'ini proje içindeki ayrı `.tools` ortamına kurma; çekirdeğe üçüncü taraf kod veya Python 3.14 bağımlılığı eklememe.
- `surface discover/watch KÖK --source theharvester` ile yalnız Common Crawl ve Wayback Archive P0 hostname kaynaklarını çalıştırma; hedef hostname'e doğrudan bağlantı, DNS çözümleme, e-posta/kişi toplama, screenshot, takeover ve API scan açmama.
- Geçici HOME/veri alanı, sabit iki kaynak, 250 sonuç, tek işçi, 240 saniyelik dış süreç sınırı ve sıkı çıktı sınırı kullanma. Tam commit ve çalıştırılabilir dosyanın checkout içinde olduğunu her çalışmada doğrulama.
- JSONL özetini ve hostname kanıtını tekrar alan, tam alan kümesi, UTC zaman, kaynak durum/sayaç, boş aktif işlem, kanonik kapsam ve boyut bağlarıyla kapalı biçimde doğrulama.
- Common Crawl ve Wayback gözlemlerini aynı aday altında ayrı kaynak kanıtları olarak saklama; sağlayıcı kimliğini çalışma geçmişi, terminal ve JSON sonucunda gösterme. Kaynak hatasını boş sonuç, arşiv kaydını sahiplik/güncellik/risk kararı saymama.
- Şema 50→51 geçişinde yalnız iki provider denetimini genişletme; bütün crt.sh kanıtlarını ve çalışma sıra numaralarını koruma, önce doğrulanmış yedek alma ve hata halinde rollback.

- `brand watch-add AD KULLANICI --source maigret|sherlock` ile kalıcı izlemeyi tek ve değiştirilemez kaynağa bağlama; kaynak verilmezse Maigret kullanma.
- Aynı kullanıcı adını farklı yerel adlarla Maigret ve Sherlock üzerinde ayrı izleme; her kaynak için bağımsız sessiz başlangıç, başarılı/başarısız çalışma ve fark zinciri.
- `watch-run`, `watch-run-all` ve `watch-monitor` içinde kayıtlı kaynağa otomatik yönlendirme; karma toplu çalışmada her öğeyi doğru adaptörle yürütme ve kaynak kimliğini terminal/JSON çıktısında gösterme.
- Sherlock'un incelenmiş 26 platformundan seçilen tam profile mevcut gerekçeli insan kararını ve yalnız olası taklit kararının yerel bildirim kuralını uygulama.
- Kaynak değişimini, kaynağa ait olmayan platformu, yanlış kaynak üst bilgisini ve platformla uyuşmayan profil hostunu kapalı biçimde reddetme.
- Şema 49→50 geçişinde mevcut izlemeleri geçmiş çalışma, profil kararı ve bildirim kanıtını değiştirmeden Maigret'e bağlama; önce doğrulanmış şema 49 yedeği alma ve hata halinde rollback.

- `brand username-preview KULLANICI_ADI --source sherlock` ile 5 platformluk güvenli varsayılan veya 26 platformluk incelenmiş geniş kapsamda canlı ve yazmasız önizleme.
- Maigret ve Sherlock `safe`, `extended` ve özel platform listelerini ağ erişiminden önce birbirinden ayırma.
- Sherlock 0.16.2'yi resmî tam commit'ten varsayılan kurulumda alma; kurulu sürümü ve 104.039 baytlık upstream katalog dosyasının tam SHA-256 özetini doğrulama.
- Yalnız seçilen site tanımlarını geçici kataloğa alma; URL alanlarını incelenmiş HTTPS/443 host listesiyle doğrulama. Geniş katalog, canlı katalog/exclusion ve seçilmeyen platformları çalıştırmama.
- Ek GitHub sürüm isteği yapan Sherlock CLI yerine sabit `sherlock()` kütüphane işlevini yalıtılmış işçide çağırma. İşçinin yalnız kullanıcı adı, platform, profil adresi ve durum taşıyan kendi NDJSON raporunu üretmesi; ana sürecin bunu tekrar katı biçimde doğrulaması.
- Ham HTTP yanıtını, profil ayrıntısını ve üçüncü taraf kimliklerini almama. Proxy/Tor/I2P, toplu kullanıcı adı, türetme ve profil çıkarımını kapalı tutma; 5–30 saniye istek ve sınırlı süreç/çıktı boyutu uygulama.
- Yalnız `Claimed` sonucunu `found_unverified` gösterme; diğer durumları kesin “hesap yok” hükmüne çevirmeme. Sonucu veritabanına yazmama ve eşleşmeyi sahiplik veya taklit kanıtı saymama. Şema 49'u değiştirmeme.

- `brand source-coverage` ile sabit Maigret 0.6.6 ve Sherlock 0.16.2 katalog kapsamını internet, araç kurulumu, kullanıcı adı sorgusu veya veri klasörü olmadan karşılaştırma.
- Sherlock v0.16.2'yi tam upstream commit ve katalog SHA-256 özetiyle; Maigret'i mevcut incelenmiş commit/katalog özetiyle; kayıt kökü karşılaştırmasını paketli Public Suffix List sürümüyle bağlama.
- Etkin, HTTPS ve doğrudan kullanıcı adı tanımlarını seçme; devre dışı, benzer-ad, ayna/kaynak bağlı, kullanıcı adı dışı, NSFW ve HTTPS dışı tanımları kaynak özelliğine göre eleme.
- Maigret 6.628 ve Sherlock 455 uygun tanımı; Sherlock tarafında 352 ortak, 103 eşleşmeyen tanımı, 102 hostu ve 101 kayıt kökünü açıkça gösterme. Bu sayaçları canlı doğruluk veya bulunan hesap sayısı gibi sunmama.
- İlk 10 güvenli platformda 9 ortak, yalnız Maigret'te Facebook ve yalnız Sherlock'ta sıfır platform ayrımını tarihsel kapsam kanıtında gösterme. Çalışan adaptörlerde yalnız elle incelenmiş 30/26 listeleri kullanma.
- Paketli kanıtı boyut, tam SHA-256, tekrar JSON alanı, tam alan kümeleri, HTTPS başvuruları, kaynak rolleri, sayaç bağları, zorunlu ölçütler ve tekil kısa listeyle güvenli doğrulama. Şema 49'u değiştirmeme.

- `brand watch-monitor IZLEME_KIMLIGI` ile tek etkin sosyal kullanıcı adı izlemesini terminal açıkken sınırlı tur, en az beş dakika aralık ve toplam yeni-tur başlatma bütçesiyle tekrarlama.
- 1–1000 tur, 300–86400 saniye aralık, 1–604800 saniye süre bütçesi ve mevcut 5–30 saniye platform isteği sınırlarını kaynak erişiminden önce doğrulama.
- Her tamamlanan turu mevcut tekil çalışma yolunda ayrı atomik kayıt olarak koruma. Kaynak hatasını hesap yokluğu saymadan başarısız tur olarak kaydetme ve bütçe kalırsa sonraki turu deneme.
- Süreyi monoton saatle ölçme; gerileyen/geçersiz saatte kaynak erişiminden önce veya turlar arasında güvenli durma. Süre dolunca yeni tur başlatmama; başlamış kaynak işini kesilmiş başarı gibi göstermeme.
- `Ctrl+C` ile tamamlanmış turları koruyarak durma. Bütün monitor ömründe ortak yerel çalışma kilidi; terminal kapalıyken çalışma, otomatik devam, zamanlayıcı veya daemon kurmama.
- Terminal/JSON özetinde planlanan/tamamlanan, başarılı/kaynak hatalı tur ve fark sayılarını gösterme; kaynak hatasında çıkış kodu 3 ve JSON `ok:false`. Otomatik taklit kararı veya bildirim üretmeme; şema 49'u değiştirmeme.

- `brand watch-run-all` ile bütün etkin sosyal kullanıcı adı izlemelerini görünen ad + kimliğe göre sabit sırada bir kez çalıştırma; geri çekilmiş izlemeleri dışarıda tutma.
- Varsayılan 10 ve açıkça en fazla 100 izleme sınırı. Etkin kapsamın tamamı sınıra sığmıyorsa hiçbir kaynak çağrısı veya çalışma kaydı başlatmadan durma.
- Her izlemeyi mevcut tekil çalışma yolundan ayrı atomik kayıt olarak geçirme. Kaynak hatasını başarısız çalışma olarak saklayıp sonraki izlemeye devam etme; depolama/bütünlük hatasında tamamlanmış önceki kanıtı koruyup yeni çalışma başlatmama.
- Toplu terminal/JSON sonucunda planlanan, tamamlanan, başarılı ve kaynak hatalı izleme sayılarını; platform/fark özetlerini ve her çalışma kimliğini gösterme. Kaynak hatasında kısmi başarıyı çıkış kodu 3 ve JSON `ok:false` ile ayırma.
- Bütün toplu işlem boyunca ortak yerel çalışma kilidi; gizli zamanlayıcı/daemon, otomatik taklit kararı, bildirim veya dış aksiyon oluşturmama. Şema 49'u değiştirmeme.

- Yalnız yeni `possible_impersonation` sosyal profil kararını, aynı transaction içinde ortak yerel kutuya bağlama; bildirim yazımı başarısızsa karar olayını da geri alma.
- `known_official` ve `uncertain` kararlarında bildirim üretmeme. Aynı tam profil adayı için en fazla bir bildirim oluşturma; karar/gerekçe tekrarı veya değişiminde alarm çoğaltmama.
- Profil adresi değiştiğinde yeni adayın ayrı bildirim oluşturabilmesine izin verme. Eski bildirimi onu oluşturan kesin karar olayı ve gerekçeye bağlı tutma; güncel kullanıcı kararını ayrıca gösterme.
- `inbox list/show/read/unread` ile izleme adı, platform, tam profil, tetikleyen karar/gerekçe ve güncel kararı ağsız görüntüleme; okundu durumunu karar geçmişinden bağımsız tutma.
- Bildirimi mevcut açık seçimli manuel webhook akışıyla uyumlu tutma; otomatik webhook, e-posta/SMS, takedown veya dış aksiyon başlatmama.
- Şema 48→49 geçişini açık `migrate`, doğrulanmış yedek, boş bildirim tablosu ve hata halinde rollback ile yapma. Önceki olası taklit kararlarından geriye dönük bildirim uydurmama.

- `brand watch-review IZLEME_KIMLIGI PLATFORM` ile son başarılı güncel izleme sonucunda bulunan tam profile gerekçeli `known_official`, `possible_impersonation` veya `uncertain` insan kararı verme; `watch-review-show` ile dondurulmuş kanıtı ve karar geçmişini ağsız görme.
- Kararı izleme tanımı + platform + tam profil durumuna bağlama. Profil adresi değiştiğinde eski kararı taşımama; aynı profil tekrar görünürse kayıtlı kullanıcı kararını açıkça gösterme.
- Aynı karar+gerekçeyi idempotent tutma; değişiklikte önceki olaya bağlı eklemeli kayıt oluşturma. Bozuk kanıt özeti, olay zinciri, kaynak çalışma veya zaman ilişkisinde güvenli durma.
- Son kaynak denemesi başarısızsa son başarılı profil kanıtını koruma; son başarılı sonuç raporlanmamışsa veya güncel tanım henüz başarıyla çalışmamışsa karar yazmama.
- `watch-run/run-show` içinde tam profile ait güncel kullanıcı kararı, gerekçe ve zamanı gösterme. Yalnız açık `possible_impersonation` insan kararını ortak kutuya bağlama; bulunan profili kendiliğinden alarm, sahiplik doğrulaması veya dış aksiyona çevirmeme.
- Şema 47→48 geçişini açık `migrate`, doğrulanmış yedek, boş karar tablosu ve hata halinde tam rollback ile yapma. `doctor` içinde incelenmiş profil ve karar olayı sayılarını gösterme.

- `brand watch-add/list/show/revoke/run/run-show` ile açık marka kullanıcı adını seçilen platformlarda kalıcı tanımlama, canlı tek tur çalıştırma ve geçmişi ağsız inceleme.
- İlk başarılı çalışmayı sessiz başlangıç tutma; sonraki çalışmalarda yeni bulunan, profil adresi değişen, artık raporlanmayan, bulunup değişmeyen ve raporlanmayıp değişmeyen platformları ayrı saklama.
- Kaynak hatasını sonuçsuz başarısız çalışma olarak denetleme; son başarılı başlangıcı koruma ve kesintiyi hesap yokluğu/kaldırılma olarak yorumlamama.
- Tanım, yaşam döngüsü, çalışma ve öğe bütünlüğünü SQLite içinde doğrulama; bozuk geçmişte kısmi görünüm veya sessiz onarım üretmeme.
- Şema 46→47 geçişini açık `migrate`, doğrulanmış yedek, boş dört yeni tablo ve hata halinde tam rollback ile yapma. `doctor` içinde sosyal izleme ve kaynak hatası sayılarını gösterme.

- `./scripts/setup-brand` ile Maigret 0.6.6 ve Sherlock 0.16.2'yi resmî depolarının tam incelenmiş commit'lerinden proje içindeki ayrı `.venv` ortamına kurma; çekirdeği bu bağımlılıklardan ayırmaya devam etme.
- `brand username-preview KULLANICI_ADI` ile Maigret'in 6 platformluk güvenli varsayılanı, 30 platformluk incelenmiş geniş profili veya özel seçimi üzerinde canlı/yazmasız önizleme yapma.
- Upstream site veritabanını sabit SHA-256 ile doğrulayıp her çalışmada yalnız tam seçilen platformları içeren geçici veritabanına daraltma; platform HTTPS hostlarını ayrıca doğrulama ve seçilmeyen upstream ayna/yan sitelerini çalıştırmama.
- Maigret'i kabuksuz ayrı süreç, sabit sürüm, süre/çıktı sınırı ve geçici güvenli ayarlarla çalıştırma. Tor/I2P, proxy, otomatik güncelleme, Cloudflare aşma, yapay zekâ, permütasyon, domain arama, özyineleme ve profil çıkarımını kapalı tutma.
- NDJSON'dan yalnız platform, profil HTTPS adresi ve `found_unverified` durumunu alma; ham yanıtı, çıkarılmış profil alanlarını ve üçüncü taraf kimliklerini atma. Sonucu veritabanına yazmama ve profil varlığını sahiplik/taklit hükmüne çevirmeme.

- `brand source-evaluation` ile Maigret, Sherlock, theHarvester, Web-Check, Holehe ve olası Ignorant telefon aracını doğrulanmış upstream, bakım, ücretsiz/hesapsız kullanım, JSON/NDJSON sonucu, sınırlı çalışma, kod lisansı, hesap-kurtarma kullanmama ve güncel kapsam ölçütleriyle ağsız ve kayıtsız karşılaştırma.
- Maigret'in sınırlı CLI ve theHarvester'ın iki P0 arşiv adaptörünü 8/8 zorunlu kapıyla seçme. Sherlock'un sonraki bağımsız kapsam kapısıyla sınırlı kısa listeye kabul edildiğini; Web-Check'in tamamını, Holehe ve telefon hesabı yoklama yöntemlerini mevcut kapsam dışında tutma.
- Kararı terminal ve kararlı JSON ile veri dizini oluşturmadan gösterme. Araç kurmama, canlı kullanıcı adı aramama, üçüncü taraf kodunu XTI'a kopyalamama ve kullanıcı adı eşleşmesini kişi/marka özdeşliği ya da taklit hükmüne çevirmeme.

- `ransomware source-review KARSILASTIRMA_KIMLIGI` ile son yerel kaynak karşılaştırmasındaki iki özgün claim için zorunlu gerekçeli `possible_same`, `different` veya `uncertain` insan kararı kaydetme.
- Aynı karar+gerekçeyi idempotent tutma; karar veya gerekçe değiştiğinde önceki olayı silmeden, önceki olay kimliğine bağlı yeni olay ekleme. İlk karardaki iki kaynak snapshot/claim kanıtını dondurma.
- `ransomware source-review-show` ile dondurulmuş kanıtı ve karar zincirini ağsız gösterme. `source-compare` görünümünde varsa yalnız güncel kararı ayrıca gösterme; görünümü salt okunur tutma.
- Karar öncesi güncel adayı ve iki tam kaynak geçmişini yeniden denetleme. Bozuk kaynak, kanıt özeti, olay bağı veya gerileyen saatte kısmi yazma ve sessiz onarım yapmadan durma.
- Kararı kaynak claim birleştirme, alarm, inbox veya gerçekleşmiş ihlal hükmüne dönüştürmeme. Şema 45→46 geçişini açık `migrate`, doğrulanmış yedek, boş karar tablosu ve hata halinde rollback ile yapma.
- `ransomware source-compare` ile son başarılı yerel ThreatCluster ve RansomLook snapshot'larını ağsız ve salt-okunur karşılaştırma; iki özgün kaynak kaydını sonuçta ayrı tutma.
- Kuruluş adının tam normalleştirilmiş eşleşmesine ek olarak grup adı veya keşif zamanı eşitliğini zorunlu kılma; yalnız isim, yalnız grup/zaman veya yaklaşık metin benzerliğini adaylaştırmama.
- Her sonuçta aynı ve farklı ortak alanları, iki kaynak çalışma zamanını, iki claim kimliğini ve kararlı karşılaştırma kimliğini gösterme. Sonucu otomatik birleştirme, alarm, ortak gelen kutusu kaydı veya doğrulanmış ihlal hükmüne dönüştürmeme.
- Görünüm sınırını toplam sayıdan ayırma; bozuk kaynak geçmişinde güvenli durma ve 100.000 aday başvurusu/50.000 sonuç işlem sınırı uygulama.
- `ransomware watch-add AD SORGU --kind organization --source ransomlook` ile yalnız RansomLook gönderi/kuruluş başlığında tam veya sınırlı içerme eşleşmeli kalıcı izleme tanımlama. Kaynak domain vermediği için domain izlemesini ağ ve yazma öncesi reddetme.
- `watch-list/show/revoke/run/run-show --source ransomlook` ile ayrı tanım, yaşam döngüsü, çalışma ve sonuç geçmişini yönetme. İlk çalışma ile tanım değişikliğini sessiz başlangıç sayma; sonraki yeni/değişen eşleşmeleri kalıcı çalışma içinde insan inceleme adayı olarak ayırma.
- RansomLook izlemelerini yalnız son başarılı yerel snapshot üzerinde ağsız çalıştırma; kaynak penceresinden çıkan kaydı dikkat adayı, çözüm veya kapatma saymama. Geri çekilen tanımın geçmişini silmeme.
- RansomLook izleme tablolarını kendi kaynak snapshot'ına bağlama; ThreatCluster izleme/bildirim/kimlik tablolarından ayrı tutma. `collect` açık seçilen kayıtları tek yenileme ardından çalıştırabilir; RansomLook yeni/değişen izleme sonuçları ortak yerel kutuda ayrı kaynak bildirimi oluşturur; bağımsız RansomLook monitor komutu yoktur.
- Şema 44→45 geçişini açık `migrate`, doğrulanmış yedek, boş dört yeni tablo ve hata halinde rollback ile yapma; geçmiş snapshot'lardan izleme sonucu uydurmama.
- `ransomware refresh --source ransomlook` ile doğrulanmış yedi günlük tam snapshot'ı ThreatCluster'dan ayrı iki tabloya atomik kaydetme; ilk başarılı snapshot'ı alarm değil başlangıç çizgisi sayma.
- Sonraki RansomLook çalışmalarında yeni, aynı ve kayan pencereden çıkan kayıtları ayırma; değişmeyen kayıtları her tur yeniden yazmadan sayaçta koruma. Pencereden çıkışı silinme, çözüm veya yanlış iddia hükmüne çevirmeme.
- `ransomware status --source ransomlook` ile son deneme, son başarılı snapshot ve sınırlı çalışma geçmişini ağsız gösterme. Kaynak hatasını önceki başarılı snapshot'ı bozmadan ayrı başarısız çalışma olarak saklama.
- Ayrı RansomLook modelini, portunu, tablolarını, denetimini ve geri kurulumunu kullanma; ThreatCluster snapshot, izleme, bildirim ve kimlik geçmişiyle yabancı anahtar veya otomatik birleştirme oluşturmama.
- Şema 43→44 geçişini yalnız açık `migrate`, önceden doğrulanmış yedek, boş yeni tablolar ve DDL/doğrulama hatasında rollback ile yapma. Eski önizlemelerden RansomLook geçmişi uydurmama.
- `ransomware source-evaluation` ile RansomLook, arşivlenmiş RansomWatch ve Darkfield seçeneklerini etkin bakım, anahtarsız ücretsiz erişim, dar yapılandırılmış çağrı, açık yeniden kullanım koşulu, bağımsız toplama ve güvenli asgari içerik ölçütleriyle çalışma anında ağ/depolama kullanmadan değerlendirme.
- RansomLook'u 6/6 zorunlu kapıyla seçme; RansomWatch'u arşivlenmiş ve tam veri kümesi olduğu için güncel akıştan eleme; Darkfield'ı anahtarsız dar sözleşme ve üst kaynak çakışması netleşene kadar erteleme. Kararın tarihini, kaynak adreslerini ve engellerini terminal/JSON sonucunda koruma.
- `ransomware recent --source ransomlook [ARAMA]` ile RansomLook'un açık son-yedi-gün gönderilerini bir kez HTTPS üzerinden alma; grup ve gönderi/kuruluş başlığını cihaz içinde tam/başlangıç/içerme sırasıyla arama.
- RansomLook'un yalnız grup, başlık ve keşif zamanı alanlarını ayrı modelde gösterme; ülke, sektör, domain, ilan durumu veya ihlal hükmü uydurmama. ThreatCluster snapshot, izleme, bildirim ve kimlik geçmişiyle otomatik birleştirmeme.
- Sabit HTTPS uç noktası, yönlendirmesiz/sıkıştırmasız yanıt, 30 saniye, 2 MiB, 10.000 kayıt ve yedi günlük zaman sınırı; yinelenen JSON alanı/kayıt, beklenmeyen şema, kontrol karakteri veya bozuk UTC zamanda kısmi sonuç vermeden durma.
- RansomLook `recent` önizlemesinde veritabanı veya veri dizini oluşturmama; açık `refresh` dışında geçmiş yazmama. Tor/leak-site adresine bağlanmama, ham gönderi/çalınmış dosya/ekran görüntüsü almama. CC BY 4.0 kaynak ve atfını terminal/JSON ile üçüncü taraf bildirimlerinde koruma.
- `ransomware recent [ARAMA]` ile ThreatCluster'ın anahtarsız açık HTTPS JSON akışındaki son 30 günlük ransomware/leak-site iddialarını bir kez alma; kuruluş, kaynaktaki web bilgisi, grup, ülke ve sektörü cihaz içinde arama.
- Her kaydı doğrulanmamış grup iddiası olarak gösterme; `listed/delisted` durumunu ihlal, ödeme, çözüm veya doğruluk kararına çevirmeme. Eşleşme yokluğunu güvenlik ya da tam kapsam sonucu saymama.
- Sabit adres, yönlendirmesiz/sıkıştırmasız TLS, 30 saniye, 8 MiB, 10.000 kayıt ve 48 saat güncellik sınırı; yinelenen JSON alanı, şema/lisans/sayaç/zaman/durum/URL bozulmasında kısmi sonuç vermeden durma.
- Tor/leak-site adreslerine bağlanmama; `post_url` değerini domain modeline, normal terminale veya JSON çıktısına taşımama. Ham gönderi metni, ekran görüntüsü ve kişisel veri toplamama.
- Kaynak adı/adresi, akış ve alım zamanı, gün penceresi, kayıt sayısı, içerik SHA-256 ve CC BY 4.0 ThreatCluster atfını sonuçta koruma. `recent` canlı önizlemesinde veritabanı, geçmiş, otomatik izleme veya bildirim oluşturmama.
- `ransomware refresh` ile aynı katı doğrulanmış tam snapshot'ı açık kullanıcı seçimiyle yerel geçmişe yazma; önceki başarılı snapshot'a göre yeni, değişen, aynı ve kayan 30 günlük pencereden çıkan iddiaları ayırma.
- İlk başarılı snapshot'ı yalnız başlangıç çizgisi sayma; kaynak hatasını önceki başarılı geçmişi silmeden ayrı başarısız çalışma olarak kaydetme. `ransomware status` ile son deneme ve son başarılı snapshot'ı internet kullanmadan gösterme.
- Ham leak-site URL'sini veya içeriğini kalıcı tabloda tutmama. Şema 39'u yedekli, açık migration ile iki boş çalışma/öğe tablosu ekleyen şema 40'a taşıma; eski veriden iddia veya çalışma uydurmama.
- `ransomware watch-add/list/show/revoke` ile kuruluş veya domain için sürümlü, geri alınabilir yerel izleme tanımı ve silinmeyen yaşam döngüsü geçmişi tutma.
- Kuruluşu yalnız kaynaktaki `victim` alanında tam veya açık seçilmiş en az beş karakterli içerme eşleşmesiyle; domaini yalnız kaynaktaki normalleştirilmiş `website` hostunda kök/alt alan adı ilişkisiyle eşleştirme. Grup/sektör/ülke metnini alarma dönüştürmeme.
- `ransomware watch-run` ile son başarılı yerel snapshot üzerinde ağsız çalışma; yeni/değişen/aynı/pencereden çıkan sonuçları ayrı ve kaynak snapshot kimliğine bağlı saklama. Yeni veya değişmiş tanımın ilk çalışmasını sessiz başlangıç sayma.
- Yalnız sonraki yeni/değişen eşleşmeyi ortak `inbox` sırasına bağlama; salt pencereden çıkışı kapatma kanıtı saymayıp bildirim üretmeme. Bildirim ayrıntısından tam izleme çalışmasına dönebilme ve bağımsız okundu durumunu koruma.
- Şema 40'ı yedekli açık migration ile beş boş izleme/olay/çalışma/sonuç/bildirim tablosu ekleyen şema 41'e taşıma; eski snapshot'tan izleme veya alarm uydurmama.
- `ransomware watch-refresh-all` ile kaynağı bir kez yenileme ve yalnız başarılı yeni snapshot sonrasında bütün etkin kuruluş/domain izlemelerini adlarına göre kararlı sırayla çalıştırma.
- Geçersiz sınır, bozuk yerel geçmiş veya bütün etkin izlemelerin `--watch-limit` içine sığmaması halinde internet isteğinden önce durma. Kaynak hatasını başarısız çalışma olarak kaydedip eski snapshot üzerinde hiçbir izleme çalıştırmama.
- Her izlemeyi az önce tamamlanan kaynak çalışma kimliğine bağlama; her izlemeyi ayrı atomik kayıt olarak tutma. Sonraki izleme hatasında önceki tamamlanmış kaynak/izleme kanıtını geri almama, fakat akışı güvenli biçimde durdurma. Gizli zamanlayıcı veya arka plan servisi kurmama.
- `ransomware watch-monitor` ile aynı yenileme+bütün etkin izlemeler akışını terminal açıkken 1–1000 tur, 300–86400 saniye aralık ve 1–604800 saniye yeni-tur süresi sınırında tekrarlama.
- Her kaynak turunu ayrı kalıcı çalışma olarak tutma. Başarısız kaynak turunda eski snapshot üzerinde izleme çalıştırmama; süre/tur bütçesi varsa sonraki turu deneme. Tamamlanan turları süre sınırı veya `Ctrl+C` sonrasında koruma.
- Geriye gitmeyen süreç saatiyle süre ölçme; bozuk saatte ağ isteğinden önce durma. Terminal/JSON sonucunda başarılı/başarısız tur, tamamlanan ve sessiz başlangıç olan kuruluş/domain izlemesi, tur bazlı fark/bildirim toplamı, bitiş nedeni, süre ve kaynak çalışma kimliklerini gösterme. Aynı eşleşmenin farklı turlarda yeniden sayılabileceğini açık tutma; kalıcı zamanlayıcı/daemon kurmama.
- Her `watch-monitor` çalıştırmasını başlamadan kalıcı oturum kimliğiyle açma; tamamlanan her turu kaynak çalışmasına ve yalnız o turda oluşan izleme çalışma kimliklerine bağlama. Sonradan aynı snapshot üzerinde elle çalıştırılan izlemeyi eski monitor turuna katmama.
- `ransomware watch-monitor-list/show` ile oturum ve tur geçmişini ağsız gösterme. Tam başarı, kaynak hatalarıyla kısmi bitiş, `Ctrl+C`, beklenmeyen hata ve ani kapanma sonrası açık/bilinmeyen durumu ayırma; açık oturumu okuma sırasında otomatik kapatmama veya tamamlandı saymama.
- Şema 41'i yedekli açık migration ile boş monitor oturumu, turu ve tur–izleme bağlantısı tabloları ekleyen şema 42'ye taşıma; eski kaynak/izleme geçmişinden monitor oturumu uydurmama.
- `ransomware watch-timeline IZLEME_KIMLIGI` ile güncel kuruluş/domain izleme tanımını bütün denetlenmiş yerel snapshot geçmişine ağsız uygulama; geri çekilmiş izlemeyi de geçmiş araştırması için okuyabilme.
- Aynı iddia kimliğinin değişmeden tekrarını yeni olay yapmama. İlk eşleşme, kaynak bilgisi değişikliği, eşleşmenin başlaması/bitmesi, kaynak penceresinden çıkış ve aynı kimliğin yeniden görünmesini ayrı tutma; toplam tekrar gözlemini ayrıca gösterme.
- Kimliği kaynak grup adı + kuruluş adı + kaynak keşif zamanıyla sınırlı tutma; bu alanlar değiştiğinde kanıtsız otomatik olay birleştirmeme. Yalnız yerelde saklanan snapshot dönemini kapsadığını ve kaynak hatalarını ayrı gösterme.
- `ransomware watch-identity-candidates IZLEME_KIMLIGI` ile eski kimlik kaybolurken aynı veya hemen sonraki başarılı snapshot'ta beliren olası yeni kimlikleri ağsız insan inceleme adayı olarak gösterme.
- Grup, kuruluş adı, kaynak keşif zamanı ve normalleştirilmiş web alanından en az iki ortak kanıt isteme; aynı ve değişen alanları terminal/JSON sonucunda açıkça gösterme. Yalnız tek ortak alanı, eşzamanlı yaşayan kayıtları, uzak snapshot geçişlerini ve kesin kimliğin normal geri dönüşünü adaylaştırmama.
- Birden fazla eski kimlik uyduğunda yalnız en yakın başarılı snapshot'ta kaybolanları değerlendirme. Kaynak hatasını boş snapshot saymama; adayı otomatik birleştirme, alarm, karar veya veritabanı yazısına dönüştürmeme.
- `ransomware watch-identity-review` ile yalnız güncel denetlenmiş geçmişte bulunan aday için zorunlu gerekçeli `possible_same`, `different` veya `uncertain` insan kararı kaydetme; aynı karar+gerekçeyi idempotent tutma.
- Karar veya gerekçe değiştiğinde önceki olayı silmeden yeni olayı önceki kimliğine bağlama. `watch-identity-review-show` ile karar zincirini ağsız gösterme; aday listesinde son kararı görünür kılma.
- Karar kanıtını adayın kanonik eski/yeni claim anlık görüntüsü, kaynak geçişi ve SHA-256 özetiyle bağlama; bozuk aday, zincir, zaman, kaynak veya izleme ilişkisinde güvenli durma. Kararı claim birleştirme, zaman çizelgesi değiştirme, alarm veya ihlal hükmüne dönüştürmeme.
- Şema 42'yi yedekli açık migration ile boş eklemeli kimlik adayı karar tablosu ekleyen şema 43'e taşıma; eski adaylardan karar uydurmama.

- `surface exposures DOMAIN` içinde pasif alt alan adı keşfi, web, e-posta, sınırlı servis ve CNAME kanıtını tek salt-okunur SQLite anlık görüntüsünde birleştirme.
- Her kanıt ailesini güncel, eski, kısmi, başarısız, hiç çalışmamış veya zamanı tutarsız olarak ayırma; tamamlanmış boş pasif yanıtı kaynak hatası ya da kısmi boş yanıttan ayırma.
- İlgi isteyen bölüm için çalıştırılabilir sonraki terminal komutunu, aktif kontrol onayı yoksa önce kapsam komutunu gösterme. Komutları otomatik çalıştırmama; ağ, yazma, onarım veya migration yapmama.

- `cti attack-sync` ile resmî MITRE ATT&CK Enterprise v20.0 STIX 2.1 paketindeki etkin grup, kampanya, malware ve bunların `uses`/`attributed-to` ilişkilerini açık kullanıcı komutuyla ücretsiz alma.
- Sabit sürüm/adres, yönlendirmesiz ve sıkıştırmasız HTTPS, 60 saniye, 64 MiB ve 30.000 nesne sınırı; kanonik STIX kimlik/zamanı, koleksiyon sürümü/dizini, resmî ATT&CK başvurusu ve ilişki yönünü tam snapshot yazılmadan doğrulama.
- ATT&CK kaynak iddialarını tek transaction'da ekleme, gözlemleme, güncelleme, geri çekme ve yeniden etkinleştirme; aynı veriyi çoğaltmama, manuel/başka kaynak iddialarını koruma ve bozuk yönetilen geçmişte ağ isteğinden önce güvenli durma.
- ATT&CK `intrusion-set` nesnesini yerel `threat-actor` araştırma etiketiyle tutma; kaynak iddiasını otomatik atıf veya tehdit hükmüne çevirmeme. Teknik/alt teknik/taktik ayrı kimlikli katalogdadır; savunma nesneleri, TAXII ve ayrı başarısız indirme geçmişi bu kapsamda yoktur. ATT&CK kendiliğinden yenilenmez.

- `analyze DOMAIN` ile kayıtlı marka/domain adaylarını, pasif alt alan adı keşif durumunu, DNS/TLS/HTTPS, e-posta ve sınırlı servis kanıtını, güncellik/boşlukları ve açıklanabilir dış yüzey adaylarını tek ağsız, salt-okunur görünümde birleştirme.
- Güncel yerel IOC kataloğu varsa kök domaini, o köke bağlı kayıtlı bütün marka/domain adaylarını ve son kayıtlı web/servis IP'lerini tam değer üzerinden eşleştirme; bulgu görünüm sınırını IOC kapsamına uygulamama. Katalog boşluğunu “eşleşme yok” sonucundan ayırma ve IOC eşleşmesini zararlılık veya etkilenme hükmüne çevirmeme.
- Eksik/eski keşif, kapsam, web, e-posta, servis, IOC ve açık marka incelemesi için sıradaki açık terminal adımlarını üretme. `--json`, 1–8760 saat güncellik eşiği ve 1–50 bulgu görünüm sınırı.
- Birleşik analizde ürün, sürüm, paket ve CVE sonucu üretmeme. Önceki zafiyet, ürün ve paket komutları kullanıcı verisi/şema uyumluluğu için korunur; aktif ürün planının dışında tutulur.
- `analyze DOMAIN --refresh-ioc feodo|certpl` ile yalnız açık kullanıcı seçiminde ücretsiz IP veya domain IOC tam listesini yenileme ve analizi tekrar üretme; varsayılan komutu ağsız/salt-okunur tutma.
- Yenilemeden önce yerel hedefi ve bütün analiz kanıtını doğrulama; kaynak hatasında önceki IOC iddialarını koruma, hatayı eşleşme yokluğundan ayrı terminal/JSON kanıtı ve çıkış kodu 3 ile gösterme.

- `webhook secret-generate/target-add/list/show/target-secret-set/target-revoke` ile özel izinli ortak sır üretme; HTTPS hedefini tam URL ve sırrı çıktıya taşımadan yönetme; eklemeli hedef yaşam döngüsünü koruma.
- `webhook queue HEDEF BILDIRIM` ile seçilen birleşik yerel bildirimin en fazla 256 KiB'lik kanonik, SHA-256 bağlı değişmez anlık görüntüsünü hedefe özgü kuyruğa alma. Aynı hedef+bildirim çiftini çoğaltmama.
- `webhook deliver/delivery-list/delivery-show` ile ham gövdeyi zaman damgasıyla HMAC-SHA256 imzalama; 2xx, geçici ve kalıcı sonuçları sıralı deneme geçmişinde saklama; tamamlanan teslimi tekrar göndermeme ve başarısız teslimi yalnız açık komutla yeniden deneme.
- Yalnız HTTPS/443; bütün DNS sonuçlarında genel-IP zorunluluğu; doğrulanan sayısal IP'ye sabit bağlantı; özgün host ile TLS kimlik doğrulaması; yönlendirme/proxy/düz metin geri dönüşü yok. Otomatik worker veya daemon yok.
- Şema 38'i doğrulanmış yedekten sonra dört boş webhook hedef/olay/teslim/deneme tablosuyla transaction içinde şema 39'a taşıma; eski bildirimlerden hedef veya teslim uydurmama.

- `cti stix-export DOSYA [--indicator-type ...]` ile güncel domain/IPv4/IPv6/URL/MD5/SHA-1/SHA-256 IOC kaynak iddialarını ağsız ve salt-okunur biçimde STIX 2.1 `Indicator` nesnelerine dönüştürme.
- Kanonik STIX pattern, kararlı yerel Indicator kimliği, created/modified/valid zamanları, `unknown` türü, en yüksek güncel kaynak güveni ve bağımsız kaynak başvurusu/açıklamalarını koruma. IOC'yi otomatik zararlı veya varlığı etkilenmiş saymama.
- En fazla 50.000 güncel IOC ve 50.000 ilgili kaynak iddiasını tek SQLite anlık görüntüsünde doğrulama; bozuk/taşan kapsamda kısmi bundle üretmeden durma. İsteğe bağlı tam IOC türü filtresi.
- En fazla 32 MiB UTF-8 JSON dosyasını özel izinle ve atomik yayımlama; mevcut normal dosya veya sembolik bağlantının üzerine yazmama. Veritabanı yazımı, ağ, STIX içe aktarma, CTI varlık/ilişki nesnesi, TLP veya TAXII yok; şema 38 değişmez.

- `cti watch-tag-add/remove` ile kayıtlı aramaya en fazla 50 etkin etiket bağlama; ekleme, görünüm güncelleme, kaldırma ve yeniden etkinleştirme geçmişini silmeden koruma.
- `cti watch-note-add` ile gözlem, hipotez, sonuç veya takip notunu aramaya ya da aynı aramanın belirli çalışma kanıtına eklemeli bağlama; yanlış arama–çalışma bağını reddetme.
- `cti watch-journal` ile etkin etiket, etiket olayı ve not geçmişini sınırlı/ağsız/salt-okunur inceleme. Etiket/not değişikliğini sorgu tanımından ayırma ve fark tabanını sıfırlamama.
- Şema 37'yi doğrulanmış yedekten sonra üç boş avcılık defteri tablosuyla transaction içinde şema 38'e taşıma; eski çalışmalardan etiket veya not uydurmama.

- `cti watch-run-all` ile bütün etkin kayıtlı CTI aramalarını adlarına göre sabit sırada tek sefer yenileme; her aramada mevcut tam sonuç/fark/bildirim zincirini yeniden kullanma.
- Varsayılan 50 ve en fazla 500 aramalık açık sınır; etkin kapsam sınıra sığmıyorsa hiçbirini başlatmadan güvenli durma, geri çekilmiş aramaları dışarıda bırakma.
- Her aramayı ayrı atomik kanıt olarak saklama; sonraki hatada önceki tamamlanmış işleri koruma ve ortak yerel çalışma kilidiyle çakışan uzun işi dışlama. Yeni şema veya görünmez zamanlayıcı yok.

- `cti watch-monitor SAVED_SEARCH_ID` ile tek etkin kayıtlı aramayı terminal açıkken 1–1000 tur, 300–86400 saniye aralık ve 1–604800 saniye yeni-tur süresi sınırında tekrarlama.
- Her turu normal tam çalışma/fark/bildirim yolundan geçirme; süre dolduğunda yeni tur başlatmama ve `Ctrl+C` öncesinde tamamlanan çalışma kanıtlarını koruma.
- Ortak yerel çalışma kilidiyle çakışan uzun işleri dışlama; daemon, işletim sistemi başlangıç görevi, ağ erişimi veya gizli sonsuz döngü kurmama.

- Kayıtlı CTI aramasının ilk çalışmasını sessiz başlangıç kabul etme; sonraki aynı tanımda `added/updated/removed` varsa çalışma kanıtına bağlı tek okunmamış bildirimi birleşik yerel kutuya ekleme.
- Yalnız `unchanged` içeren tekrar ve değişen sorgu tanımının yeni başlangıcında bildirim üretmeme; her anlamlı çalışma için en fazla bir bildirim oluşturma.
- `inbox list/show/read/unread` içinde arama adı, sorgu, çalışma kimliği ve fark sayılarını gösterme; okundu bilgisini CTI tanımı, sonucu veya tehdit kararıyla karıştırmama.
- Çalışma başlığı, tam sonuç öğeleri ve bildirimi aynı transaction'da yazma; bildirim sıra/yazma hatasında bütün çalışmayı geri alma.
- Şema 36'yı doğrulanmış yedekten sonra boş CTI arama bildirim tablosuyla transaction içinde şema 37'ye taşıma; eski çalışmalardan bildirim uydurmama.

- `cti watch-add/list/show/run/run-show/revoke` ile yerel CTI sorgusunu adlandırma, güncelleme, geri çekme, açıkça çalıştırma ve geçmişini ağsız inceleme.
- Her çalışmada en fazla 50.000 CTI varlığı + 50.000 IOC kapsamını doğrulama; tam eşleşme kümesi 20.000 sonucu aşarsa kesilmiş çalışma kaydetmeden durma. Önceki aynı tanıma göre `added/updated/unchanged/removed` farklarını üretme.
- Sorgu, kapsam veya tür filtresi değişince eski sonuçla yanıltıcı kıyas yapmama; yeni tanım için temiz karşılaştırma tabanı başlatma.
- Arama anlık görüntüsü ile çalışma başlığı/öğelerini tek transaction'da saklama; eksik sonuç, gizli geçmiş bozulması veya öğe yazma hatasında kısmi çalışma bırakmama.
- Şema 35'i doğrulanmış yedekten sonra dört boş kayıtlı-arama/geçmiş tablosuyla transaction içinde şema 36'ya taşıma; eski veriden sorgu veya çalışma uydurmama.

- `cti search QUERY` ile CTI varlık ana adı/alternatif adı ve domain/IP/URL/hash IOC değerini tek ağsız, salt-okunur anlık görüntüde arama.
- Tam, başlangıç ve içerme eşleşmesini kararlı sırada ayırma; `--kind`, `--entity-type`, `--indicator-type` ve 1–500 görünüm sınırıyla kapsamı açıkça daraltma.
- Varsayılan yalnız etkin CTI kaynakları ile sorgu anında geçerli IOC kaynaklarını kullanma; `--all` ile geri çekilmiş/süresi dolmuş geçmişi görünür biçimde kapsama.
- En fazla 50.000 CTI varlığı ve 50.000 IOC'nin kaynak iddiası/olay geçmişini görünüm sınırından bağımsız doğrulama; eşleşmeyen gizli bozuk kayıtta kısmi sonuç vermeden durma.
- Aramada ağ, yazma, yeni tablo, otomatik atıf/profil birleştirme veya tehdit hükmü üretmeme; şema 35'i koruma.

- `cti entity-add threat-actor|campaign|malware|report NAME ...` ile kaynak adı/başvurusu, alternatif ad, güven, açıklama ve gözlem zamanlı CTI varlığı ekleme; aynı tür+adı tek ana kimlik altında tutup her kaynağı ayrı iddia olarak koruma.
- Aynı kaynak gözlemini çoğaltmama; yeni gözlem aralığını genişletme, değişen iddiayı güncelleme, geri çekilen iddiayı aynı kimlikle yeniden etkinleştirme. `added/observed/updated/reactivated/revoked` olaylarını eklemeli saklama.
- `cti entity-list/show/lookup` ile ağsız/salt-okunur profil araştırması; `entity-revoke` ile yalnız seçilen kaynak iddiasını geçmişi silmeden geri çekme. Alternatif adı otomatik profil birleşimi saymama.
- `cti relation-add` ile CTI varlığını başka bir CTI varlığına veya yerel IOC'ye sekiz sınırlı ilişki türüyle bağlama; her kaynak ilişki iddiasını bağımsız güven, açıklama ve gözlem geçmişiyle saklama.
- `cti relation-list/show` ile kaynak/hedef bağlamını ve bütün iddia geçmişini gösterme; `relation-revoke` ile yalnız seçilen kaynağı geri çekme. Çelişen aktör atıflarını birbirini ezmeden ayrı tutma.
- Öz ilişkiyi, hedefsiz/çift hedefli ilişkiyi, bulunmayan varlık/IOC'yi ve bozuk gizli geçmişi güvenli biçimde reddetme. İlişkiyi otomatik atıf, nedensellik, zararlılık veya doğrulanmış tehdit hükmüne çevirmeme.
- Şema 34'ü doğrulanmış yedekten sonra altı boş CTI varlık/ilişki/geçmiş tablosuyla transaction içinde şema 35'e taşıma; hata halinde geri alma, eski kayıtlardan grafik uydurmama ve salt okumada otomatik migration yapmama.

- `ioc sync --source feodo` ile Feodo Tracker'ın saldırgan olmayan 30 günlük botnet C2 tam JSON listesini açık komutla alma; aynı IP'nin çoklu port ve malware satırlarını deterministik tek kaynak iddiasında birleştirme.
- Sabit HTTPS adresi, yönlendirme reddi, identity JSON, 30 saniye, 8 MiB ve 50.000 ham kayıt sınırı; yinelenen JSON alanı/kayıt, beklenmeyen alan, bozuk IP/port/zaman/durum ve kontrol karakterinde bütün snapshot'ı reddetme.
- Her başarılı çalışmayı içerik SHA-256, kaynak/IOC sayısı ve `added/observed/updated/unchanged/reactivated/revoked` sayaçlarıyla; her IOC işlemini assertion ve durum SHA-256 bağıyla aynı transaction'da saklama.
- Kaynak/taşıma/biçim hatasını başarısız çalışma olarak kaydedip önceki etkin IOC'leri koruma. Yalnız başarılı tam snapshot'ta listeden çıkan iddiayı geçmiş silmeden geri çekme; yeniden görünürse aynı kimlikle etkinleştirme.
- `ioc status --source feodo [--limit ...]` ile etkin kaynak iddiası, toplam ilişkili IOC ve son çalışma/kesinti geçmişini internetsiz ve salt-okunur gösterme.
- Feodo sayısal güven sağlamadığı için 50/100 değerini açık `XTI yerel nötr politikası` olarak ayırma; hiçbir IOC'yi otomatik engelleme, zararlılık veya varlık etkisi kararına çevirmeme.
- `sources` kataloğunda Feodo'nun anahtarsız, ücretsiz, hedefe temas etmeyen erişimini ve sınırlarını gösterme. Canlı kaynak JSON'unu kullanıcı veritabanına yazmadan 5 satır/5 IOC ile doğrulama.
- Şema 33'ü doğrulanmış yedekten sonra iki boş besleme çalışma/provenance tablosuyla transaction içinde şema 34'e taşıma; hata halinde geri alma ve salt okumada otomatik migration yapmama.

- `ioc sync --source certpl` ile CERT Polska Warning List'in son bir ayda eklenen ve hâlâ etkin domainlerden oluşan uBlock metin listesini açık komutla alma; Polonya/son-ay kapsamını küresel phishing listesi gibi sunmama.
- Sabit HTTPS adresi, yönlendirme reddi, identity metin, 30 saniye, 8 MiB ve 50.000 domain sınırı; katı başlık/sürüm/sona-erme/ana sayfa, UTF-8/LF, kanonik domain, tekrar ve en fazla 48 saat eski snapshot doğrulaması.
- Feodo ve CERT kaynaklarını sabit `CtiFeedPolicy` nesneleriyle aynı depo adaptöründe ayırma; aynı kanonik IOC ana kaydındaki bağımsız kaynak iddialarını, çalışma geçmişlerini ve geri çekmeleri birbirine karıştırmama.
- Kaynak/taşıma/biçim hatasında önceki CERT iddialarını koruma; yalnız başarılı tam snapshot'ta üyelik yaşam döngüsü üretme. Değişmeyen CERT üyelikleri için tekrar çalışma–öğe satırı yazmadan içerik SHA-256, toplamlar ve değişiklik kanıtını saklama.
- `ioc status --source certpl`, `analyze DOMAIN --refresh-ioc certpl`, kaynak kataloğu, terminal ve JSON akışlarını ekleme. 50/100 güveni kaynak puanı değil XTI yerel nötr politikası olarak etiketleme.
- Canlı resmî son-ay listesini kullanıcı veritabanına dokunmadan 18.764 domain olarak ayrıştırma; geçici SQLite'ta ilk kaydı yaklaşık 2,23 saniye/33,7 MB, değişmeyen tekrarı yaklaşık 1,83 saniye ve 18.764 nesneli STIX çıktısını yaklaşık 19,6 MB olarak doğrulama.

- `ioc add TYPE VALUE --source ... --reference ... --confidence ... --description ...` ile domain, IPv4, IPv6, HTTP(S) URL, MD5, SHA-1 ve SHA-256 göstergelerini türüne göre kanonikleştirip tek yerel kimlik altında saklama.
- Aynı IOC için her `kaynak + başvuru` iddiasını ayrı güven, açıklama, isteğe bağlı geçerlilik ve ilk/son görülme aralığıyla tutma; başka kaynağın kaydını ezmeme.
- Aynı gözlemi çoğaltmama; yeni gözlemde aralığı genişletme, değişen iddiayı güncelleme, geri çekilen iddiayı aynı kimlikle yeniden etkinleştirme. `added/observed/updated/reactivated/revoked` geçmişini eklemeli saklama.
- `ioc list [--type ...] [--all]`, `ioc show IOC_KIMLIGI` ve `ioc lookup TYPE VALUE` ile internetsiz/salt-okunur katalog görünümü; geçerliliği süren, etkin ve toplam kaynak sayılarını ayırma.
- `ioc revoke KAYNAK_IDDIASI_KIMLIGI --reason ...` ile yalnız seçilen kaynak iddiasını geçmişini silmeden geri çekme. Güven puanını otomatik zararlılık, varlık etkisi veya engelleme kararı saymama.
- Doctor içinde gösterge/etkin iddia sayaçları; güncel yedek/restore içinde ana kayıt, kaynak iddiası ve bütün olay geçmişi. Gizli bozuk olay veya eksik bağda kısmi ayrıntı vermeden güvenli durma.
- Şema 32'yi doğrulanmış yedekten sonra üç boş IOC tablosuyla transaction içinde şema 33'e taşıma; hata halinde sürüm ve DDL geri alma, eski kayıtlardan IOC uydurmama ve salt okumada otomatik migration yapmama.

- `vuln ubuntu-evidence-plan [--domain ...]` ile etkin seçilmiş Ubuntu kanıtlarını ağsız planlama; yerel paket aynı/değişmiş/etkisiz toplamlarını görünüm sınırından önce hesaplama ve dikkat adaylarını öne alma.
- En fazla 10.000 etkin Ubuntu kanıtı ile bunların 100.000 genel kanıt olayını tek salt-okunur anlık görüntüde doğrulama; kayıtlı olmayan varlık, bozuk ayrılmış kaynak bağı veya eksik geçmişte görünüm limitinden bağımsız güvenli durma.
- `vuln ubuntu-evidence-scan [--domain ...] [--limit 1..20]` ile planın sınırlı ilk grubunu güncel Canonical kayıtlarıyla salt okunur kontrol etme; aynı CVE için tek kaynak çağrısını paylaşma ve boş kapsamda ağa çıkmama.
- Toplam/seçili/kalan, gerçek kaynak çağrısı, güncel/değişmiş ve kaynak atlanan sayıları gösterme. Kanıt, paket, maruziyet kararı veya olay geçmişi yazmama; şema 32'yi koruma.
- `vuln ubuntu-evidence-check KANIT_KIMLIGI` ile seçilmiş Ubuntu destek kanıtını güncel paket anlık görüntüsü ve yeniden alınan Canonical kaydıyla hiçbir veri yazmadan karşılaştırma.
- Tam güncel, kaynak değişmiş/sonuç aynı, paket değişmiş/sonuç aynı, karşılaştırma sonucu değişmiş, bağ kaybolmuş, kayıt geri çekilmiş, paket veya kanıt etkisiz ve paket kontrol sırasında değişmiş durumlarını ayrı gösterme.
- Etkisiz paket/kanıtta kaynak çağırmama; etkin kontrolde kayıtlı CVE, paket UUID'si, iki SHA-256 özeti, seçilebilir durum, maruziyet CVE'si ve varlık bağını yeniden doğrulama. İnsan kararı, öncelik, kanıt ve olay geçmişini değiştirmeme.
- Ayrılmış `ubuntu-osv-v1` başvurusunu genel `exposure-evidence-add` komutunda reddetme; yapılandırılmış Ubuntu kanıtını yalnız doğrulamalı seçim akışının üretmesini sağlama. Şema 32'yi koruma.
- `vuln ubuntu-evidence-add INCELEME_KIMLIGI UBUNTU_PAKET_KIMLIGI --summary ...` ile güncel Canonical sonucunu yeniden alıp açık insan seçimiyle mevcut maruziyete `package_inventory` destek kanıtı olarak bağlama.
- Maruziyet ve etkin Ubuntu paketinde aynı varlık bağını ağdan önce zorunlu kılma; CVE'yi insan incelemesinden alma. Listelenmeyen/geri çekilmiş kaydı, çoğul veya bulunmayan `affected` bağını ve kaldırılmış paketi kanıt saymadan durma.
- Kanıt kaynağında CVE, paket kimliği, tam paket anlık görüntüsü SHA-256, Canonical içerik SHA-256 ve eşleşme durumunu kanonik biçimde mühürleme. Aynı seçimi çoğaltmama; değişmiş paket veya kaynağı ayrı kanıt olarak saklama.
- Ağ isteği sırasında paket kanıtı değişirse yazma transaction'ında güncel kaydı yeniden doğrulayıp eski seçimi atomik reddetme. Genel kanıt liste/ayrıntı/kaldırma, maruziyet kuyruğu, yedek/restore ve bozuk kayıt kapılarını yeniden kullanma; insan kararını ve olay geçmişini değiştirmeme. Şema 32'yi koruma.
- `vuln ubuntu-inventory-scan CVE [--domain ...]` ile seçilen varlığın veya bütün varlıkların etkin Ubuntu paketlerini tek Canonical kayıt çağrısıyla topluca karşılaştırma; bütün kapsam için listelenmiyor/fixed-yok/önce/eşit/sonra/geri-çekilmiş sayaçları.
- 1–500 görünüm sınırını yalnız çıktı satırlarına uygulama; önce/fixed-yok durumlarını kararlı sırada öne alma. En fazla 10.000 etkin paket ve 100.000 olayı görünüm limitinden bağımsız, tek salt-okunur SQLite anında doğrulama.
- Boş etkin kapsamda Canonical kaynağını çağırmama; kayıtlı olmayan varlık, bozuk ana kayıt veya olay geçmişinde ağdan önce güvenli durma. Toplu taramada paket kanıtı, maruziyet veya insan kararı yazmama; şema 32'yi koruma.
- `ubuntu-packages add/list/show/revoke` ile kayıtlı varlığa tam Ubuntu yayını, binary paket adı/sürümü/mimarisi ve doğrulanmış kaynak paket adı/sürümü bağlama; aynı kimliği çoğaltmama ve kanıt güncelleme/kaldırma/yeniden etkinleştirme geçmişini koruma.
- `vuln ubuntu-inventory-match PAKET_KIMLIGI CVE` ile etkin kaydın yalnız doğrulanmış source sürümünü Canonical fixed sınırıyla salt okunur karşılaştırma. Binary sürümü ayrı kanıt olarak gösterme, eşleştirme hükmüne katmama; kaldırılmış kaydı ağdan önce durdurma.
- Ubuntu kayıt/geçmişini bütün görünür ve gizli olayları doğrulayarak okuma; bozuk kayıt veya geçmişte kısmi sonuç vermeme. `doctor` içinde etkin kayıt sayısı, güncel yedek/restore içinde ana kayıt ve bütün olaylar.
- Şema 31'i doğrulanmış yedekten sonra boş Ubuntu paket ve olay tablolarıyla işlem bütünlüğü içinde şema 32'ye taşıma; eski varlık/üründen paket bağı uydurmama, hata geri alma ve açık migration kapısı.
- `vuln ubuntu-match CVE --ecosystem ... --source-package ... --version ...` ile kullanıcının açıkça verdiği Ubuntu OSV yayını, Debian kaynak paket adı ve sürümünü Canonical'ın tek-CVE kaydındaki fixed sınırıyla yazmasız karşılaştırma.
- Debian Policy 5.6.12 sırasıyla epoch, upstream sürüm, Debian revision, rakam/rakam dışı parçalar, baştaki sıfırlar ve tilde davranışını haricî `dpkg` bağımlılığı olmadan uygulama. Önce/eşit/sonra durumlarını ayrı gösterme.
- Geri çekilmiş kayıt, affected bölümünde listelenmeyen yayın+paket ve fixed sınırı olmayan kayıtları ayrı tutma; çoğul bağ, kanonik olmayan Ubuntu/paket kimliği veya beklenmeyen range olayında kısmi hüküm vermeden durma. Girdileri ve 1–200 duyuru sınırını ağdan önce doğrulama; yerel paket okumama, veritabanı yazmama ve maruziyet kararı üretmeme.
- `vuln ubuntu-preview CVE-YIL-SAYI` ile Canonical'ın resmî deposundaki tek `UBUNTU-CVE` OSV kaydını sabit yıl/dosya yolundan alma; yönlendirmesiz TLS, 30 saniye, 8 MiB, identity ve JSON/metin içerik türü sınırları.
- Tam Ubuntu kayıt kimliği ve upstream CVE bağı, ortak OSV şema/zaman/URL/range sınırları ve yalnız `Ubuntu:*` paket ekosistemi doğrulaması. Ubuntu yayını, kaynak paket, sürüm sayısı, fixed sınırı ve USN başvurularını sınırlı terminal/JSON'da gösterme; veri yazmama ve maruziyet kararı vermeme.
- `vuln source-evaluation` ile Canonical Ubuntu OSV, Microsoft MSRC CVRF, Debian Security Tracker ve Cisco openVuln kaynaklarını sürümlü/ağsız olarak resmî üretici, ücretsiz-anahtarsız erişim, yapılandırılmış biçim, tek-kayıt sınırı, ürün bağlamı ve yeniden kullanım koşuluyla karşılaştırma.
- Ubuntu OSV'yi zorunlu kapılarda 6/6 ile tek sonraki kaynak seçme; MSRC ve Debian'ı eksik tek-kayıt/lisans kanıtıyla erteleme, Cisco'yu istemci sırrı/OAuth gereksinimi nedeniyle ücretsiz profil dışında bırakma. Her kararın kanıt açıklaması, engeli ve resmî HTTPS bağlantısını gösterme.
- `vuln nvd-window-plan` ile saat dilimli ve en fazla yedi günlük NVD son-değişiklik aralığının yeni/hazır/başarısız/tamamlanmış durumunu, sonraki sırasını, bilinen toplamını ve kalan kaydını ağsız gösterme.
- `vuln nvd-window-fetch` ile çağrı başına yalnız bir ve en fazla 100 kayıtlık resmî NVD API sayfası alma; sabit HTTPS, yönlendirmesiz, 30 saniye, 8 MiB ve ücretsiz anahtarsız 6,5 saniye aralık sınırları.
- `vuln nvd-window-list` ile kalıcı pencereleri `all/ready/failed/complete` durumuna göre ağsız listeleme; `vuln nvd-window-show` ile tam pencere kimliğini, güncel imleci, kaynak bağlarını ve yeniden başlatma geçmişini gösterme.
- `vuln nvd-window-coverage` ile en fazla 366 günlük bir dönemde yalnız tamamlanmış pencereleri kapsama sayma, örtüşen veya bitişik aralıkları birleştirme ve açık boşlukları gösterme. Hazır/başarısız pencereler kapsanmış sayılmaz.
- `vuln nvd-window-gap-plan` ile kapsama boşluklarını kronolojik ve en fazla yedi günlük aday pencerelere bölme; adayların yeni/hazır/başarısız durumunu ve kalıcı sonraki sırasını ağsız, yazmasız gösterme. Toplam/gösterilen aday ve kesilme ayrı görünür; otomatik yürütme yapılmaz.
- `vuln nvd-window-gap-fetch` ile planın başındaki açıkça seçilmiş 1–3 adayın her birinden yalnız bir sayfa alma; süreçler arası 6,5 saniyelik anahtarsız kaynak aralığını koruma ve ilk kaynak hatasında sonraki adaylara geçmeden durma.
- Yürütme öncesi/güncel boşluk planını, denenmiş/başarılı/başarısız sayfaları ve bu çalışmada denenmeyen önceki adayları ayrı gösterme. Tam kapsamada kaynak çağrısı olmadan `nothing_to_do`; kısmi sayfada sonraki açık komuta kalıcı imleçten devam.
- `vuln nvd-window-operations` ile seçilen en fazla 366 günlük dönemin tamam/hazır/hatalı pencere sayılarını, dikkat bekleyen toplamını, yeniden başlatmalarını, son ilerlemesini, son 1–100 penceresini ve gerçek kapsama boşluklarını tek salt-okunur anlık görüntüde gösterme.
- Operasyon durumunda hatayı `attention`, tam kapsamı `covered`, hazır işi `in_progress`, yalnız açık zamanı `gaps` ve hiç çalışma olmamasını `no_activity` olarak ayırma; örtüşen tam pencere olsa da hatalı çalışmayı gizlememe.
- `vuln nvd-window-restart` ile tam pencere kimliği ve zorunlu gerekçeyle önceki durumu eklemeli denetim olayına yazıp yalnız ilerlemeyi sıfırlama; CVE kayıtları, NVD değişiklik olayları ve kaynak çalışma geçmişini koruma. Saat gerilemesinde yazımı reddetme.
- Sayfa biçimi/sürümü, başlangıç ve sonuç sayıları, CVE kimliği/zamanı, yinelenen ve pencere dışı kayıt ile eksik sayfayı tümden doğrulama. Hata, değişen toplam ve plan sapmasında ilerlemeyi koruma.
- CVE ana kayıtları/değişiklik olayları, kaynak çalışma kaydı ve sonraki sıra imlecini tek transaction'da yazma; süreç kesintisinde son başarılı sayfadan devam etme ve tamamlanan pencereyi tekrar çağırınca ağa çıkmama.
- Tarih penceresi kaynağının insan maruziyet kararını, gerekçesini, zamanını veya olay geçmişini değiştirmemesi; yeniden değerlendirme ve bildirim adımlarını ayrı açık komutlar olarak koruma.
- Şema 30'u doğrulanmış yedekten sonra boş NVD yeniden başlatma denetim tablosuyla işlem bütünlüğü içinde şema 31'e taşıma; mevcut pencere ilerlemesini koruma, geçmiş işlem uydurmama, hata geri alma ve backup/restore desteği.
- `vuln change-notify` ile ürün etkisizliği, ürün kanıtı/NVD özeti değişimi ve gelmiş yeniden kontrol tarihini mevcut yerel bildirim kutusuna taşıma; varsayılan açık/görünür kapsamı kapanmış ve bastırılmış seçenekleriyle açıkça genişletme.
- Maruziyet, sıralı tetikleyiciler, ürün etkinliği/kanıt zamanı, NVD özeti ve yeniden kontrol tarihinden kanonik durum özeti üretme; aynı durumu tekrarsız, farklı durumu yeni bildirim olarak saklama.
- Bir çalışmada en fazla 100 yeni bildirim; önceden bildirilmiş durumları sınırı tüketmeden atlayıp kalan adaylara ilerleme. Plan sonrası veri sapmasında bütün yazımı geri alma.
- Bulgu, pasif aday, dış yüzey ve zafiyet değişikliği bildirimlerini dört tablo arasında ortak artan sırada listeleme; salt-okunur ayrıntı ile açık okundu/okunmadı işlemini insan maruziyet kararından ayırma.
- Şema 28'i doğrulanmış yedekten sonra boş zafiyet bildirim tablosuyla işlem bütünlüğü içinde şema 29'a taşıma; eski kanıttan geriye dönük bildirim uydurmama, hata geri alma ve backup/restore desteği.
- `vuln tracked-nvd-plan` ile varsayılan açık/görünür maruziyetlere bağlı benzersiz CVE'lerin son başarılı NVD kontrolünü ağsız planlama; güncel, zamanı gelmiş ve saat hatalı kayıtları ayırma.
- Aynı CVE'ye bağlı birden çok incelemeyi tek kaynak adayı altında sayma; kapanmış/bastırılmış kapsamı yalnız açık seçeneklerle ekleme ve toplamları gösterim sınırından önce hesaplama.
- `vuln tracked-nvd-refresh` ile zamanı gelen en fazla beş ilgili CVE'yi resmî NVD API'sinden açık komutla yenileme; önceki süreç dahil en az 6,5 saniyelik ücretsiz erişim aralığı, CVE başına atomik kayıt ve ilk hatada durma.
- Kaynak yenilemesinde insan kararını/olay geçmişini değiştirmeme; değişmiş NVD özetini `reassessment-plan` içinde ayrı neden yapma. Saat hatasında ve güncel planda hedef ağa veya NVD'ye istek göndermeme.
- Maruziyet kapsamlı 0.64 yenilemesinde yeni tablo, ücretli servis veya API anahtarı eklemeden mevcut şemayı koruma; kaynak kataloğunda açık komut ve sınırları gösterme.
- `vuln reassessment-plan` ile ürünün etkisizleşmesi, doğrulanmış ürün kanıtının değişmesi, NVD kaynak özetinin değişmesi ve yeniden kontrol tarihinin gelmesini bütün ilgili maruziyetlerde ayrı nedenlerle salt okunur planlama.
- Varsayılan açık/görünür kapsamı `--include-closed` ve `--include-suppressed` ile açıkça genişletme; en fazla 500 satır gösterirken incelenen ve bütün aday sayılarını sınırdan önce verme.
- `vuln reassessment-run` ile seçili adayları güncel yerel ürün/NVD koşullarıyla ağsız yeniden hesaplama; çalışma ve sonuçları değişmez denetim geçmişine yazma.
- İnsan `investigating/affected/not_affected/fixed` kararını, gerekçesini, zamanını, bastırmasını ve olay geçmişini değiştirmeme; eşleşme kaybından güvenli veya etkilenmiyor sonucu üretmeme.
- Plan ile yazım arasında ürün, NVD, karar, bastırma veya tetikleyici değişirse bütün çalışmayı geri alma. `reassessment-runs/show` ile geçmişi ağsız ve yazmasız gösterme; `doctor` içinde çalışma sayısını verme.
- Şema 27'yi doğrulanmış yedekten sonra boş çalışma/sonuç tablolarıyla işlem bütünlüğü içinde şema 28'e taşıma; eski maruziyetlerden denetim çalışması uydurmama, hata geri alma ve backup/restore desteği.
- `assets criticality-set/show/clear` ile kayıtlı varlığa insan onaylı `low/medium/high/critical` iş önemi ve zorunlu gerekçe bağlama; güncel durumla silinmeyen karar geçmişini ayrı tutma.
- Aynı karar tekrarında olay çoğaltmama; güncelleme, kaldırma ve yeniden etkinleştirmeyi `set/updated/cleared/reactivated` olarak koruma. `doctor` içinde etkin/toplam iş önemi sayısını gösterme.
- `vuln exposure-queue` içinde iş önemini ve son kayıtlı web/izinli servis kanıtından çıkarılan internet erişilebilirliğini aynı salt-okunur SQLite anında gösterme.
- Güncel doğrulanmış HTTPS yanıtı veya açık izinli TCP portunu `confirmed`, yalnız DNS'i `dns_only`, güncel kanıtta görülmeyeni `not_confirmed`; kapsam yokluğu, kontrol edilmemiş/eski kanıt, kaldırılmış kapsam ve saat hatasını ayrı `unknown` nedenleriyle gösterme.
- `--surface-stale-hours 1..8760` ile güncellik eşiğini açık yönetme. Kanıt yokluğunu veya doğrulanamayan erişimi güvenli/internete kapalı saymama; kuyruk okumasında ağ isteği ya da yeni kontrol başlatmama.
- Yüksek/kritik iş önemi ve doğrulanmış güncel erişimi açık incelemede ayrı dikkat nedenleri olarak kullanma; çalışma bandını yükseltebilme fakat insanın maruziyet durumunu, kapanmış kararı veya destek kanıtını değiştirmeme.
- Şema 26'yı doğrulanmış yedekten sonra boş iş önemi ve olay tablolarıyla işlem bütünlüğü içinde şema 27'ye taşıma; eski veriden önem uydurmama, hata geri alma ve backup/restore desteği.
- `vuln vendor-preview CVE-YIL-SAYI --provider suse` ile SUSE Product Security Team'in resmî, ücretsiz tek-CVE CSAF VEX belgesini yazmasız önizleme.
- Eski CVE'ler için 2023 geri-doldurma, yeni CVE'ler için CVE yılı dizinini otomatik seçme; yönlendirmesiz 30 saniye, 16 MiB, JSON içerik türü ve tam yayımcı/CVE kimliği doğrulaması.
- Red Hat ile SUSE'yi tek ortak sınırlı CSAF ayrıştırıcısında, ayrı doğrulanmış sağlayıcı politikalarıyla işleme; boş durum kovası, boşluklu ürün kimliği ve CPE 2.3 dahil gerçek SUSE biçimini güvenli ele alma.
- SUSE durumlarını yalnız SUSE/openSUSE ürün kapsamı olarak gösterme; yerel paket eşleştirmesi, kalıcı kanıt, maruziyet veya insan kararı üretmeme. Şema 26 değişmedi.
- `vuln exposure-suppress INCELEME_KIMLIGI --days ... --reason ...` ile yalnız açık maruziyeti 1–3650 gün gerekçeli olarak varsayılan liste ve kuyruktan gizleme.
- `exposure-unsuppress` ile erken kaldırma ve `exposure-suppression-show` ile etkinlik, kesin bitiş ve eklemeli etkinleştirme/uzatma/yeniden etkinleştirme/geri alma geçmişini gösterme.
- Kesin bitiş anında kaydı veritabanına yazmadan, insan kararını değiştirmeden ve sahte olay üretmeden ana liste/kuyruğa geri alma; `--include-suppressed` ile henüz etkin süreli kayıtları açıkça dahil etme.
- Kapanmış veya zaten süresiz bastırılmış kayda yeni süreli bastırma eklememe; bozuk bastırmada görünümü güvenli durdurma ve `doctor` içinde etkin/toplam sayıları gösterme.
- `not_observed` sonucundan sonra ayrı insan `fixed` kararı, yeni NVD kanıtında yeniden inceleme uyarısı ve gerekçeli `investigating` yeniden açılışını laboratuvar kabul akışında doğrulama.
- Şema 25'i doğrulanmış yedekten sonra boş süreli bastırma ve olay tablolarıyla işlem bütünlüğü içinde şema 26'ya taşıma; eski süresiz kararlardan bitiş uydurmama, hata geri alma ve backup/restore desteği.
- `vuln exposure-queue` içinde her incelemenin iptal edilmemiş düzeltme planı sayısını, plan durumlarını, son kontrol sonuçlarını ve kontrol tarihi gelmiş plan sayısını gösterme.
- Kontrol tarihi gelen planı `remediation_recheck_due` gerekçesiyle en az `high` bandında görünür kılma; daha güçlü mevcut gerekçeyi, insan kararını ve plan geçmişini değiştirmeme.
- Düzeltme bağlamını maruziyet, KEV/EPSS/NVD ve destek kanıtlarıyla aynı salt-okunur SQLite anında alma; seçili bütün planları 10.000 sınırına kadar, iptal edilmiş olanlar dahil doğrulayıp bozuk kayıtta kısmi kuyruk vermeden durma.
- Kuyruk okumasında ağ, yazma, otomatik kapatma veya şema değişikliği yapmama; şema 25'i koruma.
- `vuln remediation-plan` ile açık maruziyete etkin kesin paket/VEX kanıtı, etkin genel destek kanıtı veya açık analist notu kaynaklı düzeltme planı bağlama.
- `remediation-implement/recheck/cancel/list/show` ile plan, uygulama kanıtı, kontrol sonucu, sonraki kontrol tarihi ve eklemeli geçmişi internete bağlanmadan yönetme.
- `not_observed`, `still_present` ve `inconclusive` kontrol sonuçlarını ayrı tutma; uygulamada ve süren/belirsiz riskte sonraki kontrol tarihini zorunlu kılma.
- Her düzeltme olayında o andaki insan kararı ile güncel NVD ve ürün kanıt özetini saklama; bozuk kayıt/geçmişte güvenli durma.
- Kontrol sonucu maruziyeti otomatik kapatmama; `not_observed` sonrasında bile `fixed` için ayrı gerekçeli insan kararı gerektirme.
- Şema 24'ü doğrulanmış yedekten sonra boş düzeltme planı/olay tablolarıyla işlem bütünlüğü içinde şema 25'e taşıma; eski kararlardan plan uydurmama, hata geri alma ve backup/restore desteği.
- `vuln vendor-evidence-check KANIT_KIMLIGI` ile kayıtlı kesin Red Hat kanıtını güncel RPM anlık görüntüsü ve yeniden alınan VEX belgesiyle salt okunur karşılaştırma.
- Tam güncel, kaynak değişmiş/beyan aynı, paket yeniden doğrulanmış, beyan değişmiş, seçilen bağ kaybolmuş, çelişen bağlam ve etkisiz paket durumlarını ayrı gösterme; etkisiz pakette dış kaynağı çağırmama.
- Kontrol sonucundan yeni kanıt, maruziyet kararı, yeniden inceleme veya öncelik yazmama; şema 24'ü değiştirmeme.
- `vuln vendor-evidence-add INCELEME_KIMLIGI PAKET_KIMLIGI --vex-product-id ...` ile güncel `vendor-match` çıktısındaki tek bir kesin Red Hat ürün bağını açık insan seçimiyle yapılandırılmış kanıta dönüştürme.
- İnceleme ve paketin aynı varlığa ait olmasını, CVE'nin incelemeden gelmesini ve tam ürün kimliğinin yeniden alınan VEX belgesindeki tekil/çelişkisiz kesin eşleşmede bulunmasını şart koşma; ağ öncesi girdileri doğrulama.
- Kaynak SHA-256, belge sürümü/yayım zamanı, üretici durumu, eşleşme türü, bileşen PURL'si, dağıtım CPE'si ve paket kanıt zamanını birlikte saklama; ağ sırasında paket değişirse eski seçimi yazmama.
- `vendor-evidence-list/show/revoke` ile kayıt ve eklemeli geçmişi yönetme; yeni kaynak özetini eski kanıtı ezmeden ayrı saklama, aynı seçimi çoğaltmama ve bozuk kayıtta güvenli durma.
- Kesin kanıtı maruziyet kuyruğunda `exact_vendor_package` türü ve kanıt boşluğu filtresinde gösterme; insan kararı ile öncelik bandını otomatik değiştirmeme.
- Şema 23'ü doğrulanmış yedekten sonra boş kesin üretici kanıtı/olay tablolarıyla işlemsel olarak şema 24'e taşıma; eski eşleşmelerden kanıt uydurmama, hata geri alma ve backup/restore desteği.
- `vuln vendor-match PAKET_KIMLIGI CVE-YIL-SAYI` ile etkin kesin Red Hat RPM kaydını doğrudan Red Hat VEX belgesiyle salt okunur karşılaştırma.
- VEX ürün PURL/CPE yardımcılarını ve `default_component_of` ilişkisini koruma; tam ikili pakette NEVRA+PURL+CPE, kaynak paket bağında doğrulanmış kaynak adı+PURL+CPE birlikteliğini şart koşma.
- Farklı epoch, release, mimari veya dağıtımı eşleştirmeme; eşleşme yokluğunu güvenli/etkilenmiyor saymama ve çelişen kesin bağları tek duruma indirmeme.
- Eşleşen `fixed/known_affected/known_not_affected` değerini yalnız Red Hat beyanı olarak gösterme; insan maruziyet kararı, destek kanıtı, öncelik veya yeniden inceleme kaydı yazmama.
- `packages add/list/show/revoke` ile kayıtlı varlığa paket adı, epoch, sürüm, release, mimari ve kesin Red Hat Enterprise Linux CPE bağlamı taşıyan kullanıcı doğrulamalı RPM kanıtı ekleme.
- Kaynak RPM biliniyorsa ayrı tutma; PURL'yi doğrulanmış alanlardan üretme ve serbest kullanıcı PURL'si kabul etmeme. Başka dağıtım veya genel ürün kaydından RPM kimliği türetmeme.
- Aynı kesin kimliği çoğaltmama; kanıt/kaynak RPM güncellemesi, iptal ve yeniden etkinleştirmeyi ana kayıtla aynı transaction'da eklemeli geçmişte koruma.
- `doctor` içinde etkin kesin RPM sayısını gösterme; liste/ayrıntıyı ağsız ve yazmasız tutma, bozuk kimlik/PURL/geçmişte güvenli biçimde durma.
- Şema 22'yi doğrulanmış yedekten sonra boş RPM kanıtı/olay tablolarıyla işlemsel olarak şema 23'e taşıma; eski genel ürün kayıtlarından paket uydurmama, hata geri alma ve backup/restore desteği.
- Paket kanıtını tek başına zafiyet, düzeltildi veya etkilenmiyor kararı saymama; VEX eşleştirmesi ve insan seçimiyle kalıcı kanıtı ayrı katmanlarda tutma.
- `vuln vendor-preview CVE-YIL-SAYI --provider redhat` ile Red Hat'in resmî tek-CVE CSAF VEX 2.0 belgesini doğrudan ve yazmasız önizleme.
- Sabit yıl/CVE HTTPS yolu, 30 saniye, 16 MiB, yönlendirmesiz JSON taşıması; Red Hat yayımcı kimliği, CVE, belge zamanları/geçmişi, ürün ağacı, durum ve düzeltme hedeflerini tümden doğrulama.
- `fixed`, `known_affected`, `known_not_affected`, `under_investigation` ve diğer desteklenen durumları çelişmeyen ürün/bileşen kümeleri olarak sayma; kimlikleri ürün ağacındaki anlaşılır adla gösterme.
- VEX sonucunu yalnız Red Hat ürünleri için Red Hat beyanı sayma; yerel paket kimliği olmadan başka dağıtım/varlığa taşımama ve otomatik karar/kanıt/öncelik üretmeme. Şema 22 değişmedi.
- `vuln advisory-evidence-add` ile önizlemede görülen tek bir HTTPS `ADVISORY` başvurusunu açık kullanıcı seçimi, türü ve açıklamasıyla mevcut maruziyet incelemesine bağlama.
- Önce incelemenin CVE kimliğini yerelden doğrulama, ardından güncel OSV kaydını yeniden alma ve verilen tam adresin o kayıtta bulunduğunu denetleme; yalnız başarılı üyelikten sonra kanıt yazma.
- Geçersiz girdi, bilinmeyen inceleme, OSV kaynak hatası ve listede olmayan adreste kalıcı değişiklik yapmama; ağ sırasında SQLite yazma transaction'ı tutmama.
- OSV üyeliğini içerik doğruluğu, üretici sahipliği, etkilenme veya öncelik hükmü saymama; mevcut eklemeli kanıt yaşam döngüsünü ve şema 22'yi koruma.
- `vuln advisory-preview CVE-YIL-SAYI` ile seçilen tek CVE'nin ücretsiz OSV.dev duyuru, paket, ekosistem ve sürüm sınırı bağlamını doğrudan internetten gösterme.
- OSV yanıtını sabit HTTPS uç noktası, yönlendirmesiz 30 saniye, 8 MiB, JSON içerik türü, CVE bağı, zaman, paket/aralık ve başvuru sınırlarıyla bütün olarak doğrulama.
- Paket ve `ADVISORY` başvurularını ayrı 1–200 gösterim sınırıyla açma; OSV kaydını üretici hükmü, varlık maruziyeti, öncelik veya otomatik destek kanıtı saymama.
- OSV önizlemesinde veri klasörü/veritabanı oluşturmama veya yazmama; kaynak hatasını uzak ayrıntı ve traceback sızdırmadan güvenli terminal/JSON hatası olarak gösterme. Şema 22 değişmedi.
- `vuln exposure-queue --evidence all|present|missing` ile tüm incelemeleri, etkin destek kanıtı olanları veya kanıtı olmayanları ayrı çalışma listesi olarak gösterme.
- Kanıt filtresini kapanmış/bastırılmış kapsamla birlikte uygulama; terminal/JSON'da seçimi ve seçili kapsamdaki kanıtlı/kanıtsız sayıları açıkça gösterme.
- Kanıt yokluğunu risk, etkilenme veya kaynakta veri yok hükmü saymama; filtreyle bant, sıra veya kalıcı karar değiştirmeme.
- `vuln exposure-queue` içinde her seçili incelemenin etkin destek kanıtı sayısını ve türlerini, üst özette kanıtlı inceleme ve etkin kanıt toplamını gösterme.
- Destek kanıtını öncelik nedeni veya puanı yapmama; kanıt sayısı/türünden bant, sıralama veya insan kararı üretmeme.
- Kapanmış/bastırılmış filtrelerini kanıt sorgusuna da uygulama; seçili bütün etkin kanıtları 10.000 sınırına kadar doğrulayıp bozuk ilgili kanıtta kısmi kuyruk vermeden durma.
- Kuyruk kanıt bağlamını inceleme, ürün, NVD, KEV ve EPSS ile aynı salt-okunur transaction anında alma; ağ, yazma veya yeni tablo oluşturmama.
- `vuln exposure-evidence-add` ile bir maruziyet incelemesine üretici duyurusu, dağıtım duyurusu, yerel paket envanteri veya analist notu bağlama.
- `vuln exposure-evidence-list/show/revoke` ile etkin veya geçmiş kanıtları, kaynak başvurusunu ve eklemeli olay geçmişini ağsız gösterme; yanlış/eski kanıtı silmeden etkisizleştirme.
- Aynı inceleme+tür+kaynak başvurusunu tek kimlikte tutma; açıklama güncellemesi, iptal ve yeniden etkinleştirmeyi ana kayıtla birlikte tek transaction'da saklama.
- Duyurularda yalnız sınırlı HTTPS başvurusu kabul etme; hiçbir kanıt komutunda adresi kendiliğinden açmama veya kanıt varlığından insan kararı üretmeme.
- Şema 21'i doğrulanmış yedekten sonra boş destek-kanıtı/olay tablolarıyla işlemsel olarak şema 22'ye taşıma; eski kararlardan kanıt uydurmama, hata geri alma ve backup/restore desteği.
- `doctor` içinde etkin maruziyet destek kanıtı sayısını gösterme; saat gerilemesi, bozuk kayıt/geçmiş ve 10.000 olay sınırında güvenli davranma.
- `vuln exposure-queue` ile açık/görünür insan incelemelerini ürün, NVD, CISA KEV, FIRST EPSS ve birincil CVSS bağlamıyla tek salt-okunur veritabanı anında sıralama.
- Tek sayısal risk puanı yerine `immediate`, `high`, `normal`, `monitored` bantları; insan durumu, yeniden inceleme, KEV, ransomware, EPSS ve CVSS nedenlerini ayrı gösterme.
- Varsayılan yalnız `investigating/affected`; `--include-closed` ve `--include-suppressed` ile kapsamı açıkça genişletme ve `--min-epss` eşiğini tam ondalıklı karşılaştırma.
- Kapanmış kararı yalnız yüksek kaynak puanı nedeniyle yeniden açmama; ürün/NVD kanıtı değişmiş kapanmış kaydı yeniden inceleme bandına çıkarma.
- Seçili bütün kayıtları ve ilgili kaynak satırlarını 10.000 kayıt sınırına kadar doğrulama, en fazla 500 gösterme; bozuk ilgili kaynakta kısmi güvenilir kuyruk vermeden durma.
- Kuyrukta ağ, yazma, otomatik karar veya kendi tablosunu oluşturmama; güncel şema 22 üzerinde salt okunur çalışma.
- `vuln exposure-open` ile yalnız kesin-koşul veya elle-inceleme ürün+CVE adayını açık gerekçeyle `investigating` durumunda kalıcı insan incelemesine alma.
- `vuln exposure-review` ile `investigating`, `affected`, `not_affected` ve `fixed` kararlarını zorunlu gerekçe, açık bastırma/geri alma ve isteğe bağlı yeniden kontrol tarihiyle kaydetme.
- `vuln exposure-list/show` ile görünür veya bastırılmış kayıtları, toplam/açık/yeniden-inceleme sayılarını ve eklemeli insan karar geçmişini ağsız gösterme.
- Karar anındaki ürün kanıt zamanı, NVD kaynak özeti ve aday sınıfını saklama; ürünün etkisizleşmesini, ürün/NVD değişimini ve yeniden kontrol tarihinin gelmesini eski kararı silmeden ayrı uyarı nedeni yapma.
- Değerlendirme ile yazım arasında ürün/NVD değişirse işlemi durdurma; ana kayıt ile olayı aynı transaction'da yazma ve saat gerilemesinde olay zamanını korurken ana zamanı geriye taşımama.
- Şema 20'yi doğrulanmış yedekten sonra boş maruziyet/olay tablolarıyla işlemsel olarak şema 21'e taşıma; eski eşleşmelerden insan kararı uydurmama, hata geri alma ve backup/restore desteği.
- `doctor` içinde toplam ve açık/görünür maruziyet incelemesi sayısını gösterme; listeyi 10.000 kayıt, ayrıntı geçmişini 10.000 olay doğrulamasıyla sınırlama.
- `vuln asset-overview ÜRÜN_KİMLİĞİ CVE-YIL-SAYI` ile doğrulanmış ürün koşulunu, CISA KEV'i, FIRST EPSS'yi ve NVD/CVSS bağlamını tek salt-okunur veritabanı anında gösterme.
- Ürün koşulu, gerçek dünyada bilinen istismar, 30 günlük olasılık ve teknik şiddet anlamlarını ayrı tutma; eksik kaynağı sıfır risk veya güvenli saymama.
- `vuln match-products CVE-YIL-SAYI` ile tek yerel NVD kaydını etkin doğrulanmış ürün envanterinin tamamıyla karşılaştırma; varsayılan aday filtresi ve `--all` tam görünümü.
- Etkin ürün, toplam aday, kesin aday, elle inceleme, ürün koşulu yok, sürüm uyuşmuyor ve NVD koşulu yok sayılarını gösterim sınırından bağımsız verme.
- Envanter taramasını 10.000 etkin ürünle sınırlama ve CPE koşullarını kimlik/yapılandırma bağına göre indeksleme; ağ, yazma, alarm, risk skoru veya otomatik maruziyet oluşturmama.
- Herhangi bir saklı ürün veya zafiyet kaynağı bozuksa sınır arkasında bile kaydı gizlemeden bütün ilgili görünümü durdurma.
- `products add/list/show/revoke` ile kayıtlı varlığa kullanıcı doğrulamalı CPE türü, üretici, ürün, kesin sürüm ve açıklayıcı kanıt bağlama; kaldırılmış kayıtları geçmişiyle koruma.
- Aynı varlık+tür+üretici+ürün+sürümü tek kimlikte tutma; aynı kanıtı çoğaltmama, kanıt güncelleme ve yeniden etkinleştirmeyi eklemeli olay olarak saklama.
- Port veya teknoloji ipucunu otomatik ürün kaydına dönüştürmeme; farklı varlıkların kayıtlarını kesin ayırma ve `doctor` içinde etkin ürün sayısını gösterme.
- Şema 19'u doğrulanmış yedekten sonra boş ürün/olay tablolarıyla işlemsel olarak şema 20'ye taşıma; hata geri alma, eski sürümde salt-okunur durma ve backup/restore desteği.
- `vuln assess-product ÜRÜN_KİMLİĞİ CVE-YIL-SAYI` ile doğrulanmış ürünü yerel NVD CPE koşullarıyla tek salt-okunur veritabanı anında karşılaştırma.
- Tür+üretici+ürün tam eşleştirme; yalnız basit, terslemesiz ve kesin sürüm eşleşmesini “NVD koşulu adayı” olarak sınıflandırma.
- Sürüm aralığı, joker/uygulanamaz sürüm, `AND`, tersleme ve çevresel koşulları “elle inceleme gerekli” tutma; aynı `AND` grubundaki farklı donanım/ortam bağını görünür koruma.
- Ürün koşulu yok, kesin sürüm uyuşmuyor, NVD koşulu yok ve etkisiz ürün durumlarını ayrı gösterme; hiçbirinden güvenli/etkilenmiyor veya otomatik maruziyet sonucu üretmeme.
- Karşılaştırmada ağ, yazma, bulgu/alarm veya risk skoru oluşturmama; bozuk ürün/NVD kanıtında kısmi görünüm vermeden durma.

- `vuln applicability CVE-YIL-SAYI --limit 50` ile yerel NVD kaydındaki CPE ürün, işletim sistemi, donanım ve sürüm koşullarını internete çıkmadan gösterme.
- NVD yapı/düğüm `AND`/`OR`, isteğe bağlı tersleme, `vulnerable=true/false`, ham CPE ve `matchCriteriaId` kanıtını kaynak sırasıyla koruma.
- Tam sürüm ile dahil/hariç sürüm başlangıç/bitiş sınırlarını ve kaçışlı CPE bileşenlerini katı ayrıştırma.
- Gösterimi en fazla 500 satırla sınırlarken 2.000 yapı, 10.000 düğüm ve 20.000 eşleşmeye kadar bütün kaynak koşullarını doğrulama ve toplamları verme.
- Uygulanabilirlik verisi yokluğunu güvenli/etkilenmiyor saymama; bozuk tek koşulda kısmi çıktı vermeden durma; yeni tablo/ağ/yazma oluşturmama.
- `vuln enrich-nvd --min-epss 0.9 --limit 3` ile çevrimdışı planın en fazla beş CVE'sini yalnız açık komutla resmî NVD API'sinden alma.
- Ücretsiz/anahtarsız istekleri ardışık gönderme; önceki süreçteki son NVD bitişini de hesaba katarak her tamamlanan istekten sonra en az 6,5 saniye bekleme.
- Ortak çalışma kilidiyle eşzamanlı NVD yürütmesini engelleme; ilk kaynak hatasını kaydedip yeni istek göndermeden durma.
- Her başarılı CVE'yi ayrı atomik kaydetme; sonraki çalıştırmada tamamlananı plandan çıkarıp kalanlardan devam etme.
- Geçersiz limit/eşik, eksik/eski/bozuk veritabanı veya geriye gitmiş sistem saatini ağ isteğinden önce reddetme.
- `vuln plan --min-epss 0.9 --limit 20` ile güncel KEV veya eşik üstü EPSS kayıtlarından NVD bağlamı eksik CVE'leri internete çıkmadan sıralama.
- Güncel KEV adaylarını önceleme, aynı CVE'nin iki seçim nedenini tek satırda birleştirme ve NVD kaydı bulunanları plandan çıkarma.
- Uygun toplamı, NVD'si eksik güncel KEV sayısını ve NVD'si eksik yüksek EPSS sayısını ayrı gösterme; sonucu en fazla 100 kayıtla sınırlama.
- EPSS eşiğini 18 ondalık basamağa kadar kayan nokta yuvarlamasından bağımsız karşılaştırma; seçili kaynak kayıtlarını bütünlük özetleriyle doğrulama.
- Planı tek salt-okunur veritabanı anında üretme; ağ isteği, otomatik indirme, iş kaydı, veri değişikliği veya varlık maruziyeti oluşturmama.
- `vuln overview CVE-YIL-SAYI` ile aynı CVE'nin yerel KEV, EPSS ve NVD/CVSS bağlamını tek terminal/JSON ekranında gösterme.
- Üç kaydı tek salt-okunur SQLite anlık görüntüsünden alma; internete bağlanmama, veritabanını değiştirmeme ve yeni birleşik tablo oluşturmama.
- KEV, EPSS ve CVSS anlamlarını ayrı tutma; eksik kaynağı görünür kılma ve hiçbir kaynaktan ürün/sürüm veya varlık maruziyeti uydurmama.
- Saklı üç kaynaktan biri bütünlük doğrulamasını geçemezse kısmi sonuç yerine birleşik görünümü güvenli biçimde durdurma.
- `vuln sync --source nvd --cve CVE-YIL-SAYI` ile açıkça istenen tek CVE'yi resmî NVD API 2.0'dan ücretsiz ve anahtarsız alma.
- Sabit NVD HTTPS uç noktası, yönlendirme reddi, 30 saniye/8 MiB yanıt ve 4 MiB kayıt sınırı; sayfa, kimlik, zaman, CVSS, CWE ve referans doğrulaması.
- İngilizce açıklama, NVD durumu, yayın/son değişiklik zamanı, CWE ve referans sayısını; bütün desteklenen CVSS kaynak/sürüm/vektörlerini ayrı saklama ve gösterme.
- Tam kanonik NVD CVE kaynak nesnesini gelecekteki CPE/ürün çalışması için koruma; bu sürümde ürün veya maruziyet sonucu üretmeme.
- Yeni/değişen kaynak nesnesini atomik güncel kayda ve eklemeli geçmişe alma; aynı kaydı çoğaltmama, kaynak hatasında eski kaydı koruma.
- `vuln status/list/show --source nvd` ile internete bağlanmadan yerel kapsam, CVE listesi ve ayrıntısını inceleme.
- İlk NVD kapsamını açıkça tek-CVE ve tam ayna olmayan dilim olarak gösterme; CVSS, EPSS, KEV ve varlık maruziyetini birbirine karıştırmama.
- Şema 18'i doğrulanmış yedekten sonra boş NVD kayıt/geçmiş tablolarıyla işlemsel olarak şema 19'a taşıma; hata geri alma ve backup/restore desteği.
- `vuln sync --source epss` ile resmî FIRST günlük HTTPS/gzip akışından ücretsiz ve anahtarsız EPSS kataloğu alma; kullanıcının dosya vermesini istememe.
- Yalnız aynı resmî sunucuya güvenli yönlendirme; 30 saniye, 16 MiB sıkıştırılmış, 64 MiB açılmış ve 1.000.000 kayıt sınırı; metadata, model, tarih, CSV, CVE ve `[0,1]` sayı doğrulaması.
- Model sürümü, puan tarihi, 30 günlük olasılık ve yüzdelik dilimini saklama; bilimsel sayı gösterimini sınırlı sabit ondalığa çevirme.
- Yeni/değişen/aynı/katalogdan çıkan/geri giren puanları atomik uygulama; kaynak başarısızlığında son geçerli kataloğu koruma.
- `vuln status/list/show --source epss` ile internete bağlanmadan katalog durumunu, yüksek puanları ve tek CVE ayrıntısını inceleme.
- EPSS'yi önem, etki, tam risk veya varlık maruziyeti saymama; günlük her-CVE geçmişini sınırsız disk büyümesini önlemek için yerelde çoğaltmama.
- Şema 17'yi doğrulanmış yedekten sonra boş EPSS tablosuyla işlemsel olarak şema 18'e taşıma; hata geri alma, salt-okunur eski sürüm ve backup/restore desteği.
- `vuln sync --source kev` ile resmî CISA HTTPS JSON akışından ücretsiz ve anahtarsız KEV kataloğu alma; kullanıcının dosya vermesini istememe.
- Sabit adres, TLS, yönlendirme reddi, 30 saniye, 16 MiB ve 10.000 kayıt sınırı; içerik türü, sıkıştırma, yinelenen anahtar/CVE, tarih, alan ve toplam doğrulaması.
- Yeni/değişen/katalogdan çıkan/yeniden giren CVE kayıtlarını atomik uygulama; kayıt ve kaynak çalışma geçmişini silmeden koruma.
- Kaynak başarısızlığını boş katalog saymama; başarısız denemeyi kaydederken son geçerli kataloğu değiştirmeme.
- `vuln status/list/show` ile internete bağlanmadan kaynak durumunu, etkin/geçmiş kayıtları ve CVE değişiklik geçmişini inceleme.
- KEV kaydını izlenen varlıkta zafiyet kanıtı saymama; otomatik ürün/sürüm, CVSS, EPSS veya maruziyet kararı üretmeme.
- Şema 16'yı doğrulanmış yedekten sonra boş zafiyet tablolarıyla işlemsel olarak şema 17'ye taşıma; hata geri alma, salt-okunur eski sürüm ve backup/restore desteği.
- `surface technologies KÖK` ile son kayıtlı sınırlı servis kanıtındaki açık portlardan yalnız yaygın kullanım ipucu çıkarma.
- Her ipucunda uç nokta, `confidence=hint`, `detection_method=tcp_connect_only`, kanıt kimliği/zamanı/güncelliği ve açık iddia sınırları.
- Banner veya protokol kanıtı olmadığı için üretici, ürün ve sürümü `null`; `cve_match_eligible` değerini `false` tutma.
- Kapalı veya belirsiz porttan teknoloji yokluğu çıkarmama; kontrol edilmemiş, başarısız, kısmi, eski ve zamanı tutarsız kanıtı ayrı gösterme.
- Ağ, yeni port kontrolü, banner/protokol konuşması, oturum, zafiyet taraması veya veri yazma yapmama; teknoloji görünümü için ayrı tablo oluşturmama.
- `surface cname check/show TAM_ADRES` ile yalnız kayıtlı ve etkin kapsamlı tam adresin CNAME zincirini ve terminal hedef A/AAAA durumunu izleme.
- Sabit Google Public DNS JSON DoH; en fazla sekiz ilişkili CNAME adımı ve 16 IP; ilgisiz, çelişen, döngülü, kesilmiş veya beklenmeyen yanıtı güvenli hata sayma.
- Takma ad `present/absent/nxdomain/failed` ve hedef `resolved/no_address/nxdomain/failed/not_applicable` durumlarını ayrı eklemeli kanıt/değişim geçmişinde tutma.
- Hedef NXDOMAIN sonucunu yalnız kesin olmayan sarkan CNAME adayı yapma; alınabilirlik, sağlayıcı hesabı veya gerçek takeover sonucu iddia etmeme.
- Hedef site bağlantısı, HTTP/banner/içerik, kaynak sahiplenme, hesap/oturum, exploit veya otomatik DNS düzeltmesi yapmama.
- Şema 15'i doğrulanmış yedekten sonra boş CNAME geçmişiyle işlemsel olarak şema 16'ya taşıma; hata geri alma, salt-okunur eski sürüm ve backup/restore desteği.
- `surface exposures KÖK` ile son kayıtlı web, posta ve servis kanıtından açıklanabilir inceleme adayları çıkarma.
- TLS bağlantı/doğrulama sorunu; MX kullanan domainde eksik/çoğul SPF-DMARC; `22/3389` uzak erişim ve `8080/8443` alternatif web portu adaylarını ayrı tür/kategorilerle gösterme.
- Her adayda kanıt seviyesi, kimliği, zamanı/güncelliği, doğrudan olgu, iddia sınırı ve insan sonraki adımını koruma; adayın zafiyet veya ihlal olmadığını açıklama.
- Null MX için eksik e-posta politikası adayı üretmeme; eski ve zamanı tutarsız kanıtı güncel göstermeme; kısmi/başarısız/alınmamış kanıtı güvenli sonuç saymama.
- Sayfa içeriği/banner olmadığı için açık panel kimliğini `unsupported` tutma; CNAME hedef NXDOMAIN olsa da sağlayıcı alınabilirliğini veya gerçek takeover sonucunu kanıtsız üretmeme.
- Son web/posta/servis/CNAME kanıtını mevcut tek SQLite anlık görüntüsünden salt okuma; ağ, yazma, sahiplenme, exploit veya düzeltme yapmama.
- `storage readiness` ile kayıt klasörü/disk kullanımı, yönetilen yedek, saklama önizlemesi ve yerel kurtarma hazırlığını tek salt-okunur görünümde birleştirme.
- En az 64 MiB veya SQLite mantıksal boyutunun iki katı ihtiyatlı çalışma payı; toplam/kullanılabilir disk alanını terminal ve JSON'da açıklama.
- `backups/*.db` yönetilen yedeklerini sınırlı sayma; en yeni yedeği XTI şeması, SQLite quick check ve yabancı anahtar bütünlüğüyle salt okunur doğrulama.
- Varsayılan yedi gün ve 1–3650 gün seçilebilir yedek güncellik eşiği; eksik, bozuk, eski veya zamanı tutarsız son yedeği ayrı gösterme.
- Varsayılan 90 gün ve 7–3650 gün seçilebilir bağlantısız gözlem saklama önizlemesi; uygun, korunan ve zamanı sorunlu kayıt sayılarını otomatik silmeden açıklama.
- Kayıt klasörü dışındaki/ayrı ortam yedeğini `unknown`, geri yükleme tatbikatını `not_recorded` tutma; dosya varlığını felaket kurtarma kanıtı saymama.
- Sembolik bağlantı izlemeyen 10.000 dosya/1.000 yedek sınırı; ağ, dosya yazma/silme, yedek alma veya restore başlatmama. Yeni tablo olmadan şema 15'i kullanma.
- `surface discovery-status KÖK` ile son pasif keşifte kaynağın çalıştığını, eksik yanıt verdiğini, başarısız olduğunu veya hiç çalıştırılmadığını ayrı gösterme.
- Kaynak durumundan bağımsız `candidates_observed/none_observed/unknown` veri sonucu; yalnız uyarısız tamamlanmış sıfır adaylı çalışmada `empty_result_confirmed=true` verme.
- Tamamlanmış bulunan/boş, kısmi bulunan/boş, başarısız ve hiç çalışma yok sonuçlarını ayrı `outcome` değerleriyle terminal ve JSON'da açıklama.
- Kısmi boş sonucu veya kaynak kesintisini “veri yok” saymama; bulunan kısmi adayları korurken başka sonuçların eksik olabileceğini görünür tutma.
- Son çalışma için varsayılan 24 saat ve 1–8760 saat seçilebilir güncellik eşiği; eski ve gelecekteki/tutarsız zamanı sonuç durumundan ayrı gösterme.
- Mevcut eklemeli keşif geçmişini salt okuma; crt.sh veya hedef bağlantısı, yeni keşif, onarım ya da veritabanı yazısı yapmama. Yeni tablo olmadan şema 15'i kullanma.
- `surface inventory KÖK` ile pasif alt alan adı adayını, kullanıcının sahiplik kararını, ayrı varlık kaydını ve aktif kontrol kapsamını tek salt-okunur görünümde birbirinden ayırma.
- `pending/owned/rejected` aday kararını, `registered/unregistered` kayıt durumunu ve `active/revoked/not_approved/not_applicable` kapsam durumunu bağımsız alanlar olarak terminal ve JSON'da açıklama.
- Bir `owned` kararını otomatik varlık kaydı veya bağlantı yetkisine; varlık kaydını da otomatik aktif kapsama dönüştürmeme.
- Aday kararına göre yalnız açıklayıcı sonraki adım sunma; inceleme, kayıt ve kapsam onayını ayrı açık kullanıcı komutları olarak koruma.
- Durum filtresi ve 1–500 gösterim sınırına rağmen bütün köke ait aday/kayıt/aktif kapsam sayaçlarını aynı SQLite salt-okunur anlık görüntüsünde tutma.
- Ağ isteği, keşif, hedef kontrolü, karar, onarım veya veritabanı yazısı yapmama; yeni tablo ve migration olmadan şema 15'i kullanma.
- `surface freshness KÖK` ile son web DNS/TLS/HTTPS, posta MX/SPF/DMARC ve sınırlı TCP servis kanıtını sabit üç bölümde güncel/eski/alınmamış/zaman hatalı olarak gösterme.
- Varsayılan 24 saat, kullanıcı seçimiyle 1–8760 saat güncellik eşiği; tam saniye yaşını ve son kanıt kimliği/zamanını terminal ile JSON'da açıklama.
- Kanıt yaşını kontrolün tam/kısmi/başarısız sonucundan ayrı tutma; yeni fakat kısmi kanıtı eksiksiz saymama, eski veya alınmamış kanıttan risk/kesinti hükmü üretmeme.
- Kapsam ve son üç kanıtı aday/ilişki verisini yüklemeden tek SQLite salt-okunur anlık görüntüsünde alma; ağ isteği, onarım, yazma veya otomatik kontrol başlatmama.
- Gelecekteki/okunamayan kayıt zamanını güvenli `clock_error` sonucu yapma; şema 15'i ve mevcut kanıt geçmişlerini değiştirmeme.
- `surface monitor KÖK` ile seçilen web DNS/TLS/HTTPS, posta MX/SPF/DMARC ve isteğe bağlı kesin IP servis kontrollerini terminal açıkken tur, aralık ve toplam yeni-kontrol başlatma sınırıyla tekrarlama.
- Varsayılan `web mail` seçimi; servis kontrolünde kesin genel IP ve görünür yetki gerekçesini zorunlu tutma, mevcut etkin kapsam/DNS eşleşmesi/sabit port güvenlik kapılarını değiştirmeme.
- Her tamamlanan adımı mevcut eklemeli kanıt ve atomik değişiklik bildirimi yolunda saklama; ilk temel/değişmeyen sonucu alarm saymama ve tek final terminal/JSON özeti verme.
- `Ctrl+C`, süre sonu veya süreç kapanışında bitmiş kanıtları koruma; yarım turu tam saymama, terminal kapalıyken çalışma veya yeniden açılışta otomatik devam iddiası yapmama.
- Yeni tablo veya migration olmadan şema 15'i kullanma; ağdan önce bütün seçim, sınır, kapsam ve kesin IP doğrulaması, bütün oturum boyunca ortak yerel çalıştırma kilidi.
- DNS/TLS/HTTPS, MX/SPF/DMARC ve sınırlı TCP servis kanıtında yalnız `changed` sonucu için mevcut `inbox` kutusuna tek yerel bildirim ekleme.
- İlk temel kaydı ve aynı sonucun tekrarını alarm saymama; eklenen/kaldırılan IP'yi, değişen alanları ve TCP port geçişlerini bildirim ayrıntısında açıklama.
- Değişiklik kanıtı ve bildirimini aynı transaction içinde yazma; bildirim hatasında kanıtı da geri alma, salt okuma ve okundu işlemlerinde ağ isteği yapmama.
- Bulgu, pasif aday ve dış yüzey değişikliklerini tek artan sırada sayfalama; ortak atomik `read/unread`, durum özeti, yedek ve restore desteği.
- Şema 14'ü doğrulanmış yedekten sonra boş değişiklik bildirimi geçmişiyle şema 15'e taşıma; eski kanıtlardan alarm uydurmama.
- `surface services check` ile yalnız etkin domain kapsamı, açıkça beyan edilen kesin genel IP ve gerekçeli yetki birlikte varsa sabit 10 TCP portunu sınırlı kontrol etme.
- Onaylanan IP güncel A/AAAA cevabında yoksa, özel/yerel adres görülürse veya kapsam etkin değilse hedef portlarına bağlantı yapmama.
- Tek kesin IP, port başına bir saniye ve toplam 20 saniye sınırı; banner/veri/sürüm/parola/exploit, serbest port aralığı ve dış tarama aracı kullanmama.
- Açık, kapalı ve belirsiz sonucu ayırma; belirsizi kapalı, port etiketini doğrulanmış ürün veya açık portu zafiyet saymama.
- Her servis kontrolünü yetki gerekçesi, DNS kanıtı, sabit port planı, özet ve değişimle eklemeli saklama; `surface services show` ile internetsiz okuma.
- Şema 13'ü önce doğrulanmış yedeğe alıp bütün eski satırları koruyarak boş servis geçmişiyle şema 14'e geçiren işlemsel migration.
- `surface overview KÖK` ile kayıtlı kökü, pasif alt alan adı adaylarını, son DNS/IP/TLS sertifikasını, MX ve açık TCP kanıtını tek terminal/JSON görünümünde birleştirme.
- Alt alan adı, IP, sertifika kapsamı ve posta sunucusu ilişkilerini dayandıkları kanıt türü, kimliği ve zamanıyla açıklama.
- Aktif kapsam, son pasif keşif ve aday durum toplamlarını aynı SQLite okuma anlık görüntüsünden gösterme; aday örneğini 1–100 arasında sınırlama.
- Genel görünümde internet isteği, yeni tarama, veritabanı yazısı, sahiplik/risk/güvenlik kararı veya yeni grafik veritabanı oluşturmama.
- Bozuk son kanıtta kısmi ve yanıltıcı ilişki üretmeden güvenli hata; hiç taranmamış kayıtlı kökü geçerli boş görünüm olarak gösterme.
- `sources` ile crt.sh, urlscan, Google Public DNS, açık komutla HTTPS HEAD ve onaylı kesin IP'ye sınırlı TCP bağlantılarının amacını, erişim biçimini, ücretli anahtar bağımlılığını, hedef trafik durumunu, kullanan komutları ve sınırlarını internete çıkmadan gösterme.
- Yapılandırılmış kaynak kataloğunu son kaydedilen çalışma sonucu ve bekleme geçmişinden ayırma; “katalogda var” bilgisini anlık erişilebilirlik iddiası yapmama.
- İkinci ücretsiz pasif kaynak araştırmasında kullanım koşulu, bağımsız veri katkısı ve canlı erişim güvenilirliği kapılarını uygulama; uygun bulunmayan HackerTarget/Common Crawl/Cert Spotter/Subfinder bağlantısını çekirdeğe eklememe.
- Ücretli servis/API anahtarı/üçüncü taraf paket veya kopyalanmış kod eklemeden kaynak ve aktif bağlantı görünümü.
- `surface mail check` ile yalnız etkin ve açıkça onaylanmış kökte MX, kök SPF ve `_dmarc` DMARC kayıtlarını Google Public DNS üzerinden sınırlı sorgulama.
- `surface mail show` ile ilk temel/değişiklik yok/değişiklik var geçmişini internete çıkmadan gösterme.
- Üç sorguyu bağımsız tutma; tek sorgu hatasında diğer iki kanıtı koruyup kısmi sonuç ve çıkış kodu 3 verme.
- SPF/DMARC dışı TXT kayıtlarını politika kanıtından ayırma; birden fazla politika kaydını hüküm vermeden görünür tutma.
- DKIM seçicisi tahmin etmeme; SMTP/teslim testi, alt ad genişletmesi ve otomatik güvenlik/yanlış yapılandırma kararı yapmama.
- Ağdan önce etkin kapsam, bütün çalışma boyunca ortak yerel kilit ve yazma transaction'ında yeniden kapsam doğrulaması.
- E-posta DNS sonuçlarını özet doğrulamalı ve eklemeli saklama; yedek/restore, bozuk geçmişte güvenli hata ve salt okunur görünüm.
- Şema 12'yi önce yedekleyip bütün eski satırları koruyarak boş e-posta DNS geçmişiyle şema 13'e geçiren işlemsel migration.
- `surface watch` ile seçilen crt.sh veya theHarvester P0 alt alan adı keşfini terminal açıkken tur, aralık ve toplam yeni-tur başlatma bütçesiyle tekrarlama.
- Her tamamlanan izleme turunu mevcut keşif geçmişine ayrı kaydetme; aynı aday, kanıt ve yerel bildirimi tekrar üretmeme.
- Başarısız/kısmi kaynak turunu görünür tutup bütçe kaldığında sonraki turda yeniden deneme; tek final insan/JSON özeti.
- `Ctrl+C` veya süreç kapanışından önce bitmiş turları koruma; bulunan adaylara bağlantı, otomatik sahiplik veya aktif kapsam kararı vermeme.
- Bütün pasif izleme boyunca tek yerel çalıştırıcı sahipliği; geçersiz sınır veya bilinmeyen kökte kaynak erişiminden önce güvenli ret.
- Şema 12'yi değiştirmeden 0.20.0 keşif geçmişi, adayları ve bildirimleri doğrudan yeniden kullanma.
- İlk kez bulunan pasif alt alan adı adayını mevcut `inbox` kutusuna tek bildirim olarak ekleme; tekrar keşifte veya yeni sertifika kanıtında çoğaltmama ve okundu bilgisini sıfırlamama.
- Bulgu ve pasif aday bildirimlerini ortak, artan sırada listeleme; ikisi için de salt okunur ayrıntı ve açık, atomik `read/unread` işlemi.
- Her `surface discover` çağrısını tamamlandı/kısmi/başarısız sonucu, kaynak kapsamı, sayaçlar, uyarı veya hata ve zamanlarla kalıcı geçmişte tutma.
- `surface runs` ve `surface run` ile keşif geçmişini internete çıkmadan ve kayıt değiştirmeden gösterme.
- Başarılı/kısmi keşifte aday, kaynak kanıtı, ilk bildirim ve çalışma özetini tek transaction'da yazma; geç hatada hepsini geri alma.
- Şema 11'i önce yedekleyip eski bütün satırları koruyan, boş keşif geçmişi/bildirim tablolarıyla şema 12'ye geçen işlemsel migration.
- `surface discover` ile kayıtlı kökün kesin alt alan adlarını seçilen crt.sh sertifika ya da theHarvester Common Crawl/Wayback arşivlerinde pasif arama; bulunan hedeflere bağlantı göndermeme.
- Kökün kendisini ve aynı sertifikadaki ilgisiz adları dışarıda bırakma; joker ham adı ve kaynak URL/SHA-256/CT zamanını kanıt olarak koruma.
- Alt alan adı adayı için ilk/son görülme ve tekilleştirilmiş kaynak sayısı; yeni sertifikayı mevcut adaya eklerken kullanıcı kararını koruma.
- `surface candidates` ve `surface candidate show` ile salt okunur aday/kaynak/geçmiş görünümü.
- `surface candidate decide` ile onay bekliyor, bana ait ve reddedildi durumları; gerekçeli, silinmeyen ve tekrar güvenli karar geçmişi.
- `owned` kararını kayıtlı varlık ve aktif DNS/TLS kapsamından ayırma; açık `assets add` + `surface approve` olmadan hedef bağlantısı yapmama.
- Şema 10'u önce yedekleyip eski bütün satırları koruyan, boş pasif aday tablolarıyla şema 11'e geçen önceki migration.
- Doğrulanmış TLS oturumundan sertifika SHA-256, seri, issuer/subject, başlangıç/bitiş ve DNS ad kapsamı çıkarma.
- Sertifika DER/metin/zaman/ad sayısı sınırları; bozuk kanıtta HTTP isteğine geçmeden güvenli hata.
- Sertifika yenilenmesini dış yüzey değişimi olarak gösterme; aynı sertifika ve farklı DNS cevap sırasından sahte değişiklik üretmeme.
- `surface check/show` içinde sertifika ayrıntısı ve bitişe 30 gün veya az kaldığında salt okunur uyarı.
- Sertifika alanı olmayan eski hedef/dış yüzey kontrollerini ve v0.17 durum hash'lerini değiştirmeden okuma.
- `surface approve/check/list/show/revoke` ile kayıtlı domain için gerekçeli kullanıcı yetki kapsamı ve silinmeyen işlem geçmişi.
- Yalnız etkin kapsamdaki tam kök domaine sınırlı A/AAAA, doğrulanmış TLS ve HTTPS HEAD kontrolü; özel/yerel IP, yönlendirme, gövde, başka port ve scope genişletme yok.
- Her kontrolü ayrı kanıt olarak saklama; ilk temel, aynı durum ve gerçek DNS/IP/TLS/HTTPS değişimini ayırma.
- Eklenen/çıkan IP ve değişen durum alanlarını açıklama; zaman veya metin farkından sahte değişiklik üretmeme.
- Ağdan önce ve kayıt transaction'ında kapsamı yeniden doğrulama; yetki geri çekildiğinde sonuç yazmama.
- Şema 9'u önce yedekleyip eski satırları koruyan, boş dış yüzey tablolarıyla şema 10'a geçen işlemsel migration.
- `allowlist add` ve `allowlist add-finding` için isteğe bağlı 1–3650 günlük bitiş; seçenek verilmezse kalıcı istisna.
- Kesin UTC bitiş anında yeni adayları bastırmayı bırakan, zamanlayıcı ve okuma sırasında yazma gerektirmeyen politika.
- Etkin kaydın süre/gerekçe güncellemesi, süresi dolan kaydın aynı kimlikle yeniden etkinleştirilmesi ve bitişi taşıyan silinmeyen işlem geçmişi.
- Arama/içe aktarma anı ile bulgu transaction'ında süreyi ayrı doğrulama; bozuk tarihte kısmi kanıt bırakmadan güvenli hata.
- Şema 8'in kalıcı kayıtlarını ve olay sırasını koruyarak önce yedek alan, hata halinde geri dönen şema 9 geçişi.
- `feedback` ile internete çıkmadan ve kayıt değiştirmeden toplam/incelenen/bekleyen aday özeti.
- Son kullanıcı kararları, karar olayı ve yeniden incelenen bulgu sayısını kural sürümüne göre ayırma.
- İnsan ve JSON çıktısında yalnız toplu sayı/kural kimliği; domain, bulgu kimliği ve karar gerekçesini taşımama.
- Kullanıcı kararlarını doğrulanmış tehdit veya yanlış pozitif etiketi saymayan açık yorum sınırı.
- Bulgu durumu ile son eklemeli karar uyuşmazlığında sayı üretmeden güvenli hata.
- Yan yana harf değişimi + bilinen hizmet eki ve uzun markaya bitişik `shop` için iki dar yeni aday kuralı.
- Bilinmeyen ek, kısa sözcük içindeki `shop` ve daha uzun rastgele sözcük için açık negatif korumalar.
- Değişmeyen ASCII adaylarında `domain-rules-v1`, yalnız yeni desenlerde `domain-rules-v2`, Unicode adaylarında `idn-confusables-v1` kimliğini koruma.
- Yeni iş/sorgu yürütmesi için `domain-rules-v3`; eski sıradaki işi yeni kuralla sessizce çalıştırmama.
- `domain-evaluation-v2` içinde 47 örnek ve yeni üç negatif koruma; sıfır kaçırma, üç görünür bağlamsal yanlış alarm.
- `evaluate` ile veritabanı veya ağ kullanmadan sürümlü sentetik kalite ölçümü.
- 47 örnekte review/ignore beklentisi; doğru yakalama, doğru eleme, kaçırma ve gereksiz alarm sayıları.
- Precision, recall, yanlış alarm oranı ve toplam doğruluk; kategori ve örnek kimliğiyle görünür kalite açıkları.
- Bilinen kalite açığı ile kayıtlı başlangıç davranışından yeni değişimin ayrılması; sessiz kural sapmasının test engeli.
- Paketli veri kümesinde sabit SHA-256, katı veri düzeni ve bozulmada güvenli hata; insan ve JSON raporu.
- Sentetik etiketin tehdit kararı veya gerçek internet doğruluğu olmadığını çıktıda açıkça belirtme.
- `allowlist add/add-finding/list/show/revoke` ile yalnız tam aday adresine ve tek izlenen varlığa bağlı istisna yönetimi.
- Joker/geniş/ilgisiz istisnanın reddi; gerekçe zorunluluğu ve ekleme–kaldırma–yeniden etkinleştirme geçmişi.
- Etkin istisnada ham gözlemi saklarken yeni bulgu, kanıt bağlantısı ve bildirimi atomik olarak engelleme.
- İstisna eklenmeden önceki bulgu, karar, kanıt ve bildirimi değiştirmeme; geri alma sonrası saklı gözlemi yeniden işleyebilme.
- U-label/Punycode girdisini aynı kanonik A-label kimliğine bağlama; aynı adayın başka izlenen varlık için değerlendirmesini sürdürme.
- Şema 7'den istisna tablolarını ekleyen şema 8'e, süre alanlı şema 9'a ve dış yüzey tablolarını ekleyen şema 10'a önce yedek alan, hata halinde geri alan açık migration.
- Unicode 18.0.0 UTS #39 benzer-harf iskeleti ve konservatif UTS #46 nontransitional IDNA doğrulaması.
- Kaynak U-label/Punycode değerinin kanonik ASCII A-label olarak saklanması; güvenli Unicode açıklaması.
- `--typos` ile marka başına en fazla dört gerçek Punycode internet sorgusu; normal kaynak sonuçlarında IDN analizi her zaman açık.
- IDN kayıt kökü ve farklı kökteki IDN alt etiket ayrımı; Unicode PSL kurallarının A-label'a çevrilmesi.
- Yeni IDN kural kimliğiyle bulgu; mevcut ASCII bulgu/karar/bildirim kimliğinin önceki kural sürümünde korunması.
- Unicode referans dosyalarında sabit sürüm ve SHA-256 doğrulaması; çalışma anında kural indirmeme.
- `monitor start` ile süre/tur sınırı, seçilmiş adres/kaynaklar ve kalıcı deneme kimliği.
- Kaynak başına planlanan/başlayan/başlamayan işler, tamamlanma/kesinti ve kayıtlı sorgu sayıları.
- Yeni bulgu/gözlem sayılarının yalnız sonuç özeti olan denemelerden toplanması; eksik sonuçların ayrıca belirtilmesi.
- `monitor list/show` ile salt okunur grup geçmişi; son kaynak çalışmalarından ayrıntılı iş geçmişine geçiş.
- Bütün izleme denemesinde tek yerel çalıştırıcı; genel worker ve ayrı retry'ın izleme işlerini almaması.
- İş ve izleme bağlantısının atomik kaydı; küçük ilk deneme özetiyle sınırlı bellek kullanımı.
- Ctrl+C ile kayıtlı kapanış; zorla kapanma sonrasında `monitor recover` ile kanıtları koruyan kurtarma.
- Başlamamış işin sahte deneme üretilmeden kapatılması; süreç ölümünde bilinmeyen sürenin uydurulmaması.
- `status` ile arama güncelliği, kaynak beklemeleri, iş durumları ve okunmamış bildirimlerin tek görünümü.
- Her izlenen adres/kaynak için son deneme ve son tamamlanan aramanın ayrı gösterilmesi.
- Varsayılan 24 saatlik, değiştirilebilir güncellik eşiği; eski/hiç tamamlanmamış/tutarsız zaman ayrımı.
- Tek adres filtresi ve alfabetik sınırlı liste; global sayaç kapsamı ve gösterilmeyen adres sayısı.
- Özetin tek tutarlı okuma işleminden alınması; ağ, arama, kurtarma, kilit veya okundu değişikliği yapmaması.
- Eski işe yapılan yeni tekrarın doğru sıralanması; uzun hata geçmişinin eski tamamlanan aramayı gizlememesi.
- `inbox` ile okunmamış aday bildirimleri; filtreli liste, ayrıntı ve sonraki sayfa komutu.
- Her yeni bulguyla aynı işlemde tek bildirim; tekrar arama ve ek kaynakta çoğalmama.
- Açık okundu/okunmadı işlemi, en fazla 100 kimlikle atomik toplu işaretleme.
- Bildirim okundu bilgisinin inceleme kararından bağımsız tutulması; salt okumanın kayıt değiştirmemesi.
- Eski bulguların geçişte “Önceki kayıttan” olarak kutuya alınması; mevcut kayıt zamanlarının korunması.
- Bildirim kimliği, sıra ve okundu bilgisinin yeniden açılışta, retry ve yedekten dönüşte korunması.
- Kaynak beklemeleri ve asgari istek aralığının yeniden başlatma sonrası korunması.
- Yanıt başlıklarındaki kotanın gövde okunmadan/tekrar beklenmeden kaydedilmesi.
- `sources` içinde kalan bekleme ve en erken istek zamanının salt okunur görünümü.
- `storage status` ile dosya, SQLite içinde yeniden kullanılabilir alan ve gözlem sayıları.
- Eski bağlantısız gözlemler için salt okunur, sınırlandırılmış temizlik önizlemesi.
- Önizleme kimliğiyle açık uygulama; otomatik önceki durum yedeği, atomik silme ve temizlik geçmişi.
- Bütün bulguların ve bağlı kanıtların, kararların, hedef kontrollerinin ve iş geçmişinin korunması.
- `scan/watch --check` ile arşiv aramasından sonra sınırlı DNS/HTTPS hedef kontrolü.
- Tek bulguyu yeniden kontrol etme veya bekleyen açık adayları toplu işleme.
- İki adres ailesi doğrulaması, genel IP'ye sabit bağlantı, özel ağ ve yönlendirme engeli.
- Doğrulanmış TLS, yalnız HEAD, toplam süre/başlık/DNS yanıt sınırları.
- Her tamamlanan kontrolün ayrı geçmişi; aynı turda domain tekilleştirme ve altı saatlik tekrar sınırı.
- `triage` ile güncelliği okuma anında hesaplanan, açıklamalı inceleme sırası.
- `report` ile tutarlı bulgu/kaynak/karar/kontrol JSON raporu; mevcut dosya korunur.
- Varsayılan scan/watch: crt.sh sertifika kayıtları ve urlscan web inceleme arşivi.
- Tek kaynak seçimi, sağlayıcı başına ayrı iş/sonuç; worker ve retry kayıtlı kaynağı kullanır.
- Farklı kaynak gözlemlerinin aynı bulguya bağlanması ve önceki kararın korunması.
- urlscan anonim erişimi, görünür geçmiş/kota/sayfa sınırları; yeni tarama gönderilmez.
- Genel kayıt sayısı ve kapsam notları; eski sertifika sayılı JSON geçmişini değiştirmeden okuma.
- Her arama için kalıcı iş, ayrı denemeler ve tamamlanan sorgu/hata geçmişi.
- İş listesi/ayrıntısı, yeniden deneme ve kapanan çalıştırıcının yarım işini kurtarma.
- `scan --queue` ile erteleme; `worker --once` ile sıradaki tek işi çalıştırma.
- Aynı yerel kayıt alanında tek çalıştırıcı; zorla kapanınca kilidin serbest kalması.
- `sources` ile en son denemenin kaydedilmiş kaynak sonuçları; anlık erişilebilirlik iddiası yok.
- `scan DOMAIN`: kullanıcı yalnız izlenecek adresi verir; iki internet kaynağında isim arar, gözlem ve aday bulguları kaydeder.
- `watch DOMAIN`: terminal açıkken düzenli kontrol; kesinti sonrası sonraki turda tekrar deneme.
- DNS adı sorguları, sınırlı isteğe bağlı yazım varyantları, TLS ve yanıt boyutu/süre sınırları.
- Sağlayıcının bekleme isteğine uyma, sorgu ayrıntıları ve görünür kısmi/başarısız sonuç.
- Sertifika bağlantısı, asıl ad ve kaynak zamanı; tekrar sorgularda sabit gözlem kimliği.
- Yerel adres ekleme/listeleme, normalleştirme ve tekrar önleme.
- TXT/JSONL dosyasından sınırlandırılmış, tamamı doğrulanan içe aktarma.
- Aynı kayıt kökü, çok parçalı uzantı ve özel barındırma sınırlarının ayrılması.
- Ek sözcük, benzer yazım, yan yana harf değişimi ve yanıltıcı alt domain adayları.
- Nedenleriyle bulgu listesi, kaynak/satır/dosya özeti ve kayıtlı karar geçmişi.
- Şüpheli, normal/kapatıldı veya emin değilim kararı; durum filtresi.
- Tekrar importta tekilleştirme; yeni kaynak eklenirken eski kararın korunması.
- Şema 1–14'ten 15'e açık, önceden yedekli ve işlemsel geçiş.
- Adres/gözlem/bulgu/karar/istisna/dış yüzey ve işlem geçmişi/hedef kontrolü/iş/deneme/bekleme/temizlik/bildirim/izleme kayıtlarının tutarlı yedeği ve boş konuma restore.
- Hata durumunda yarım kayıt bırakmama; güvenli terminal ve JSON çıktıları.

## Doğrulama

0.82 testleri birleşik ad/alternatif ad/IOC aramasını, tam–başlangıç–içerme sırasını, tür filtrelerini, güncel–geçmiş ayrımını, görünüm sınırından bağımsız gizli geçmiş doğrulamasını, eksik kayıt alanını ve salt-okunur terminal/JSON akışını doğrular. Şema 35 değişmedi. Tam kontrolde 1.047 otomatik test 153,118 saniyede geçti; gerçek ağ kullanılmadı.

0.83 testleri kayıtlı tanım yaşam döngüsünü, ilk/tekrar/değişen/kaybolan sonuç farklarını, tanım değişikliğinde taban sıfırlamayı, IOC ve CTI varlığı sonuçlarını, gizli geçmiş bozulmasında kapalı kalmayı, çalışma öğesi hatasında atomik geri almayı, terminal/JSON akışını ve şema 35→36 kurtarma geçişini doğrular. Tam kontrolde 1.058 otomatik test 141,560 saniyede geçti; gerçek ağ kullanılmadı.

0.84 testleri sessiz başlangıcı, anlamlı fark bildirimini, değişmeyen tekrar ve yeni tanımda gürültü üretmemeyi, birleşik inbox list/show/read akışını, yanlış kanıt bağı bozulmasında kapalı kalmayı, bildirim hatasında çalışma+öğe geri almayı ve şema 36→37 kurtarma geçişini doğrular. Tam kontrolde 1.066 otomatik test 144,369 saniyede geçti; gerçek ağ kullanılmadı.

0.85 testleri tur, aralık ve toplam süre sınırlarını, tek kayıtlı sorguya bağlı ön plan çalışmasını, tamamlanmış tur raporlarını, bekleme sırasında `Ctrl+C` ile güvenli kesilmeyi, süreçler arası yazıcı kilidini ve terminal/JSON çıktılarını doğrular. Şema 37 değişmedi. Tam kontrolde 1.071 otomatik test 147,957 saniyede geçti; gerçek ağ kullanılmadı.

0.86 testleri etkin aramaların sabit sıralı toplu çalışmasını, geri çekilmiş aramayı dışlamayı, boş kapsamı, sınır taşmasında yazmadan durmayı, anlamlı değişikliğin yalnız ilgili aramada bildirim üretmesini, sonraki hatada tamamlanmış kanıtı korumayı ve terminal/JSON akışını doğrular. Şema 37 değişmedi. Tam kontrolde 1.077 otomatik test 151,030 saniyede geçti; gerçek ağ kullanılmadı.

0.87 testleri etiket ekleme/görünüm güncelleme/kaldırma/yeniden etkinleştirme yaşam döngüsünü, genel ve çalışma bağlı eklemeli notları, yanlış çalışma bağını reddetmeyi, fark tabanını korumayı, bozuk gizli defter geçmişinde güvenli durmayı, terminal/JSON, yedek/restore ve şema 37→38 geçişini doğrular. Tam kontrolde 1.086 otomatik test 150,106 saniyede geçti; gerçek ağ kullanılmadı.

0.81 testleri kaynaklı CTI varlıklarını, alternatif ad ve gözlem yaşam döngüsünü, aynı ilişkiye ait bağımsız kaynakları, çelişen aktör atıflarını, varlık–IOC bağını, geçersiz kenarları, bozuk gizli geçmişte güvenli durmayı, salt-okunur terminal/JSON akışını, yedek/restore'u ve şema 34→35 geçiş/geri alma yollarını doğrular. Tam kontrolde 1.043 otomatik test 141,883 saniyede geçti; gerçek ağ kullanılmadı.

0.80 testleri katı Feodo JSON/HTTP sınırlarını, çoklu satır birleştirmeyi, tam snapshot ekleme/gözlem/güncelleme/geri çekme/yeniden etkinleştirmeyi, kaynak hatasında korumayı, geçerli boş snapshot'ı, çalışma–IOC provenance'ını, bozuk gizli geçmişte güvenli durmayı, salt-okunur durumu, terminal/JSON, doctor, kaynak kataloğu, yedek/restore ve şema 33→34 geçiş/geri alma yollarını doğrular. Tam kontrolde 1035 test 180,364 saniyede geçti. Otomatik testlerde gerçek ağ kullanılmadı; ayrıca ayrı canlı kabulte Feodo yanıtı geçici dosyada 5 satır/5 IOC olarak ayrıştırıldı.

0.79 testleri yedi IOC türünün kanonikleştirilmesini, URL güvenlik sınırlarını, çoklu bağımsız kaynağı, aynı gözlemin tekilleştirilmesini, ilk/son görülme genişlemesini, geçerlilik bitişini, güncelleme/geri çekme/yeniden etkinleştirmeyi, gizli bozuk geçmişte güvenli durmayı, salt-okunur terminal/JSON, doctor, yedek/restore ve şema 32→33 geçiş/geri alma yollarını doğrular. Tam kontrolde 1024 test 118,960 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.78 testleri ağsız yerel planı, bütün kapsam sayaçlarını, dikkat öncelikli görünüm kesmesini, aynı CVE'de tek Canonical çağrısını, boş kapsamı, geçersiz limit ve bilinmeyen varlığı, limit arkasındaki bozuk ayrılmış başvurunun ağdan önce reddini ve salt-okunur terminal/JSON akışını doğrular. Şema 32 değişmedi. Tam kontrolde 1013 test 115,582 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.77 testleri değişmemiş kanıtı, kaynak değişip sonucun aynı kalmasını, fixed sınırı değişince sonucun değişmesini, bağın kaybolmasını, geri çekilmiş kaydı, yeniden doğrulanmış ve etkisiz paketi, etkisiz kanıtı, kontrol sırasında paket değişimini, ayrılmış başvurunun genel komutta reddini ve salt-okunur terminal/JSON akışını doğrular. Şema 32 değişmedi. Tam kontrolde 1009 test 110,088 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.76 testleri seçilmiş güncel Canonical sonucunun kaynak/paket özetleriyle mühürlenmesini, aynı seçimin çoğalmamasını, genel kanıt ve kuyruk görünümünü, insan kararının korunmasını, yedek/restore'u, başka varlığın ağdan önce reddini, listelenmeyen/geri çekilmiş kayıtta yazmama davranışını, paket ağ sırasında değiştiğinde atomik reddi ve terminal/JSON akışını doğrular. Şema 32 değişmedi. Tam kontrolde 1002 test 124,756 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.75 testleri dört paket üzerinde tek kaynak çağrısını, önce/eşit/sonra/listelenmiyor toplamlarını, dikkat öncelikli görünüm kesmesini, boş kapsamda kaynak çağrısı olmamasını, kayıtlı olmayan filtreyi, limit arkasındaki bozuk ana kayıt ve olay geçmişinde ağdan önce güvenli durmayı, salt-okunur terminal/JSON ve kaynak kataloğunu doğrular. Şema 32 değişmedi. Tam kontrolde 998 test 128,545 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.75 canlı terminal kabulünde aynı şema 32 kayıt alanındaki üç etkin paket, gerçek Canonical `CVE-2025-6491` kaydıyla tek toplu komutta tarandı. `php8.3` source `.4` fixed `.5` öncesi, source `.6` fixed sonrası ve `openssl` yayın/paket bağında listelenmiyor olarak ayrıldı; sayaçlar `1/0/0/1/1/0` oldu. Tarama öncesi ve sonrası veritabanı SHA-256 özeti `ce48f77e…5003` olarak aynı kaldı; sürüm `XTI 0.75.0` idi.

0.74 testleri Ubuntu binary/source kimlik yaşam döngüsünü, aynı kimlikte kanıt güncelleme ve yeniden etkinleştirmeyi, source sürümünün binary sürüm yerine karşılaştırılmasını, kaldırılmış kaydın ağdan önce reddini, bozuk gizli geçmişte güvenli durmayı, terminal/JSON ve kaynak kataloğunu, doctor sayacını, yedek/restore'u ve şema 31→32 geçiş/geri alma yollarını doğrular. Tam kontrolde 995 test 128,113 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.74 canlı terminal kabulünde temiz `/private/tmp/xti-v74-acceptance.tbXAD7` şema 32 kayıt alanına `example.com` ve `php8.3-cli=8.3.6-0ubuntu0.24.04.99.amd64 → php8.3=8.3.6-0ubuntu0.24.04.4` bağı eklendi. `doctor` bir etkin Ubuntu paketi ve `XTI 0.74.0` gösterdi. Gerçek Canonical `CVE-2025-6491` kaydı source `.4` sürümünü resmî `.5` fixed sınırından önce sınıfladı; farklı binary `.99` sürümü karşılaştırmaya katılmadı. Eşleştirme öncesi ve sonrası veritabanı SHA-256 özeti `dda40791…6fb6` olarak aynı kaldı.

0.73 testleri Debian epoch/upstream/revision, sayısal parça, baştaki sıfır ve tilde sıralamasını; düzeltme sınırından önce/eşit/sonra sonuçlarını; listelenmiyor/fixed yok/geri çekilmiş ayrımını; ağ öncesi girdi ve çıktı sınırlarını; çoğul/kanonik olmayan/beklenmeyen kaynak aralığında güvenli durmayı; eksik veri klasöründe yazmasız terminal/JSON'u ve kaynak kataloğunu doğrular. Şema 31 değişmedi. Tam kontrolde 987 test 131,178 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.73 canlı kabul denemesinde Canonical'ın `CVE-2025-6491` kaydındaki `Ubuntu:24.04:LTS/php8.3` bağı, açıkça verilen `8.3.6-0ubuntu0.24.04.4` sürümünü resmî `8.3.6-0ubuntu0.24.04.5` fixed sınırından önce sınıfladı. Kaynak 9 etkilenen sürüm, 2 USN ve `2026-10-21T20:01:27Z` son değişiklik zamanı bildirdi. Bu yalnız açık kullanıcı girdisiyle üretici sınırı karşılaştırmasıdır; gerçek makinedeki paket veya varlık maruziyeti doğrulanmadı ve veritabanına yazılmadı.

0.72 testleri Canonical URL/yıl/kimlik üretimini, tam `UBUNTU-CVE` ve upstream bağını, Ubuntu dışı ekosistem reddini, yinelenen JSON/bozuk biçim/boyut sınırını, yönlendirmesiz taşıma başlıklarını, içerik türü/kodlama/zaman aşımı davranışını, ağdan önce görünüm sınırlarını, eksik veri klasöründe yazmasız terminal/JSON'u ve kaynak kataloğunu doğrular. Şema 31 değişmedi. Tam kontrolde 981 test 118,274 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.72 canlı kabul denemesinde Canonical'ın resmî kaynağındaki `CVE-2025-6491` kaydı alındı: `UBUNTU-CVE-2025-6491` kimliği, 7 Ubuntu paket/yayın bağlamı ve 2 USN başvurusu doğrulandı. Örnek görünüm Ubuntu Pro 14.04 `php5`, Ubuntu 16.04 `php7.0` ve Ubuntu 18.04 `php7.2` kayıtlarını; ilgili düzeltilmiş sürüm sınırlarını gösterdi. Bu deneme yalnız kaynak erişimi ile önizleme davranışını kanıtlar; paketin yerelde kurulu veya varlığın etkilenmiş olduğunu kanıtlamaz ve veritabanına yazmaz.

0.71 testleri tek seçilen kaynağı, Ubuntu'nun bütün zorunlu kapıları geçmesini, Microsoft/Debian erteleme ve Cisco kimlik doğrulama engelini, bütün adayların resmî HTTPS kanıt bağlantılarını, profil sürümünü ve terminal/JSON komutunun eksik veri klasörünü oluşturmadan çalışmasını doğrular. Şema 31 değişmedi. Tam kontrolde 978 test 117,763 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.70 testleri aynı dönemde tamam/hazır/hatalı pencere ve yeniden başlatma sayılarını, hata öncelikli durum sınıflamasını, son güncelleme sırasını, kapsamla ortak anlık görüntüyü, hiç çalışma yok/tam kapsama ayrımını, son pencere sınırını, geçersiz sınırda yazmama ve terminal/JSON salt-okunur davranışını doğrular. Şema 31 değişmedi. Tam kontrolde 976 test 122,461 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.69 testleri bir komutta en fazla üç pencere ve pencere başına tek sayfa sınırını, ikinci istek öncesi 6,5 saniyelik aralığı, tam ve kısmi sayfa sonuçlarını, kalıcı imleçten devamı, ilk kaynak hatasında sonraki adayın çağrılmamasını, başarısız imlecin korunmasını, tam kapsamada kaynak gerekmemesini, 1–3 yürütme sınırını, yerel kilitli terminal/JSON akışını ve önceki davranışları doğrular. Şema 31 değişmedi. Tam kontrolde 974 test 124,147 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.68 testleri kapsama boşluklarının yedi günlük ve kısa son parça olarak bölünmesini, tamamlanmış zamanın atlanmasını, aynı tam kimlikteki başarısız pencerenin imleç/hata durumuyla korunmasını, aday toplamı/gösterilen sayı/kesilme ayrımını, tam kapsamada boş planı, sayfa ve gösterim sınırlarını, 366 günlük kapsama kapısını, salt-okunur veritabanı özeti ile terminal/JSON çıktısını doğrular. Şema 31 değişmedi ve bütün önceki davranışlar korundu. Tam kontrolde 971 test 140,267 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.67 testleri durum filtreli pencere listesini, ayrıntı ve yeniden başlatma geçmişini, örtüşen/bitişik tamamlanmış aralıkların birleşmesini, hazır/başarısız pencerelerin kapsama alınmamasını, açık boşlukları, ağsız ve salt-okunur komutlarda veritabanı özetinin değişmemesini, gerekçeli atomik yeniden başlatmayı, CVE/kaynak geçmişinin korunmasını, geçersiz gerekçede yazılmamasını, saat gerilemesi güvenlik kapısını, terminal/JSON çıktısını ve şema 30→31 geçişini doğrular. Şema 1–30'un bütün eski geçiş testleri ve önceki davranışlar korunur. Tam kontrolde 969 test 113,955 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.66 testleri tarih ve sayfa sınırlarını, kanonik URL'yi, katı NVD taşıma/ayrıştırmayı, iki sayfalı devamı, CVE+imleç atomikliğini, kaynak hatası ve plan sapmasında imleç korumasını, tamamlanmış planda ağsız tekrarı, insan kararının değişmemesini, terminal/JSON'u ve şema 29→30 geçişini doğrular. Şema 1–29'un bütün eski geçiş testleri ve önceki davranışlar korunur. Tam kontrolde 965 test 106,662 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.65 testleri aynı durumun tekilleştirilmesini, farklı kanıt durumunun yeni bildirim olmasını, küçük sınırla kalan adaylara ilerlemeyi, kapanmış/bastırılmış kapsamı, plan sapmasında tam geri almayı, bozuk durum özetinde güvenli durmayı, ortak kutu sırasını/okundu bağımsızlığını, terminal/JSON'u ve şema 28→29 geçişini doğrular. Tam kontrolde 953 test 118,521 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.64 testleri güncel/eski/saat hatalı NVD planını, aynı CVE'nin tekilleştirilmesini, kapanmış/bastırılmış kapsamı, salt-okunur planı, açık ağ yürütmesini, kaynak hatası sonrası durmayı, süreçler arası 6,5 saniyelik aralığı, insan kararı korumasını, değişikliğin yeniden değerlendirmeye yansımasını ve terminal/JSON akışını doğrular. Tam kontrolde 943 test 106,989 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.63 testleri salt-okunur boş/değişmiş planı, ürün/NVD/kontrol tarihi/etkisiz ürün tetikleyicilerini, kapanmış ve bastırılmış kapsamı, sınır arkasındaki toplamları, karar/olay korumasını, işlem içi sapmada tam geri almayı, bozuk denetim kaydında güvenli durmayı, ağsız terminal/JSON'u, yedek/restore'u ve şema 27→28 geçişini doğrular. Şema 1–27'nin bütün eski geçiş testleri ile 0.62 varlık bağlamı ve önceki davranışlar korunur. 0.63 tam kontrolünde 934 test 107,883 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

0.41 CPE testleri yapı/düğüm mantığını, doğrudan ve çevresel koşulları, tam ve aralıklı sürümleri, kaçışlı CPE bileşenlerini, gösterim kesmesini fakat tam doğrulamayı, eksik uygulanabilirlik verisini, bozuk saklı koşulda güvenli durmayı ve terminal/JSON salt okumasını doğrular. O sürümün tam kontrolünde 799 test 63,455 saniyede geçti.

0.40 yürütme testleri önceki süreçten kalan ve ardışık istekler arası 6,5 saniyelik beklemeyi, beş kayıt sınırını, ilk hatada durmayı, başarılı CVE'nin korunmasını, sonraki planın kalanlardan devamını, ağ öncesi doğrulamayı ve terminal/JSON sonucunu doğrular. Tam kontrolde 794 test 64,047 saniyede geçti. Otomatik testlerde gerçek ağ kullanılmadı.

0.39 plan testleri KEV önceliğini, KEV/EPSS tekilleştirmesini, var olan NVD kaydının dışlanmasını, 18 basamaklı eşik sınırını, terminal/JSON çıktısını, ağsız ve yazmasız okumayı, geçersiz girdi kapısını ve seçili bozuk kayıtta güvenli durmayı doğrular. Tam kontrolde 791 test 64,920 saniyede geçti. Otomatik testlerde gerçek ağ kullanılmadı.

0.38 birleşik bağlam testleri boş ve tam kapsamı, tek salt-okunur anlık görüntüyü, terminal/JSON çıktısını, ağsız ve yazmasız okumayı ve kaynaklardan biri bozukken bütün görünümün güvenli durmasını doğrular. Tam kontrolde 787 test 71,362 saniyede geçti. Otomatik testlerde gerçek ağ kullanılmadı.

0.37 NVD testleri sabit uç nokta ve taşıma sınırlarını; katı tek-CVE ayrıştırmayı; farklı CVSS kaynak/sürümlerini; ekleme, aynı kalma ve değişmeyi; kaynak hatasında eski kaydın korunmasını; bozuk saklı kayıtta güvenli durmayı; ortak kilit, terminal, yedek/restore ve şema 18→19 yollarını doğrular. Otomatik testlerde gerçek ağ kullanılmadı.

0.36 EPSS testleri sabit resmî adresi, aynı-sunucu HTTPS yönlendirmesini ve boyut/zaman sınırlarını; gzip/UTF-8/metadata/CSV tam-katalog ayrıştırmasını; bilimsel sayıları; ekleme, aynı kalma, değişme, katalogdan çıkma ve geri girişi; kaynak hatasında eski kataloğun korunmasını; bozuk saklı kayıtta güvenli durmayı; ortak kilit, terminal, yedek/restore ve şema 17→18 yollarını doğrular. Otomatik testlerde gerçek ağ kullanılmadı.

0.35 KEV testleri sabit resmî adresi ve sınırlı taşımayı; katı tam-katalog ayrıştırmayı; ekleme, aynı kalma, değişme, katalogdan çıkma ve yeniden girişi; kaynak hatasında eski kataloğun korunmasını; bozuk saklı kayıtta güvenli durmayı; ortak kilit, terminal, yedek/restore ve şema 16→17 geçiş/geri alma yollarını doğrular. Otomatik testlerde gerçek ağ kullanılmadı.

0.34 teknoloji ipucu testleri kanıt yokluğunu, açık port ipuçlarını, boş üretici/ürün/sürüm alanlarını ve kapalı CVE uygunluğunu; kısmi, başarısız, eski ve gelecekteki kanıtı; geçersiz eşiği ve terminal/JSON salt okumasını doğrular. Ağ adaptörü çağrılmadı, veritabanı baytları değişmedi ve porttan ürün ya da zafiyet sonucu üretilmedi.

0.33 CNAME testleri ilişkili iki adımlı zinciri, ilgisiz yanıt reddini, terminal NXDOMAIN ayrımını, kapsam ve ortak kilit kapılarını, temel/aynı/değişmiş geçmişi, kesin olmayan maruziyet adayını, bozuk kanıtı, backup/restore'u ve şema 15→16 geçiş/geri alma yollarını doğrular. Sahte DNS yanıtları kullanıldı; hedef site bağlantısı, sağlayıcı kaynağı sahiplenme veya gerçek kullanıcı verisine yazma yapılmadı.

0.32 maruziyet testleri kanıt yokluğunu ve desteklenmeyen panel/takeover kapsamını; TLS sorunu, eksik SPF/DMARC, açık uzak erişim/alternatif web portu adaylarını; Null MX negatif örneğini; eski ve gelecekteki kanıtı ayrı doğrular. Her aday kanıt ve sınırlama taşır. Terminal/JSON görünümü ağ adaptörlerini çağırmadı, kaynak sahiplenmedi ve veritabanı baytlarını değiştirmedi.

0.31 depolama hazırlığı testleri eksik yedek, geçerli güncel yedek, eski yedek ve en yenisi bozukken daha eski geçerli yedeğin hatayı gizlememesi durumlarını ayrı doğrular. Yönetilen yedek şema 15, SQLite quick check ve yabancı anahtar bütünlüğüyle salt okunur açıldı. Saklama önizlemesi hiçbir kayıt silmedi; sembolik bağlantı hedefi okunmadı; geçersiz politika depolara erişmeden reddedildi. Terminal/JSON görünümü veri dosyalarını değiştirmedi.

0.30 kaynak durumu testleri çalışma yok, tamamlanmış boş, tamamlanmış bulunan, kısmi boş, kısmi bulunan, başarısız, eski ve gelecekteki zaman sonuçlarını ayrı doğrular. Yalnız tamamlanmış boş çalışmada `empty_result_confirmed` doğru oldu; kısmi veya başarısız sıfır sonuç güvenilir boşluk sayılmadı. Terminal/JSON görünümü pasif kaynağı çağırmadı ve veritabanı baytları değişmedi.

0.29 envanter testleri aynı kökte bekleyen, bana ait ve reddedilmiş adayları; bunlardan ayrıca kayıtlı, kapsamı onaylanmamış ve aktif kapsamlı olanları bağımsız katmanlarda doğrular. `owned` aday yalnız açık kapsam onayından sonra izlenebilir görünür; kayıtlı ve aktif fakat hâlâ `pending` aday sessizce sahiplenilmiş sayılmaz. Filtre global sayaçları değiştirmedi. Terminal/JSON okumaları ağ adaptörlerini çağırmadı ve veritabanı baytları değişmedi.

0.28 güncellik testleri kapsam veya kanıt olmayan kayıtlı kökte üç görünür `never` bölümü; bir saatlik tam web kanıtında `current`; tam eşik anındaki kısmi posta kanıtında `stale+partial`; alınmamış serviste `never`; gelecekteki kayıtta `clock_error` ve kaldırılmış kapsam durumunu doğrular. Geçersiz eşik ve bilinmeyen kök yazmadan reddedildi. Terminal akışında web+posta kanıtı tek görünümde güncel, servis alınmamış göründü; probe sayıları ve veritabanı baytları salt okuma öncesi/sonrası değişmedi.

0.27 ön plan izleme testleri, seçili kontrollerin her turda sabit sırayla çalıştığını; tur/aralık/süre sınırlarını; süre dolduğunda yeni kontrol başlamamasını; `Ctrl+C` sonrasında tamamlanmış kanıtın kalmasını ve tekrarlı/geçersiz seçimin ağdan önce reddini doğrular. Terminal akışında varsayılan web+posta seçimi servis portlarına gitmedi; üçlü seçimde ilk tur temel kayıt oluşturdu, ikinci turdaki üç gerçek değişiklik ortak kutuya üç kanıt bağlı bildirim ekledi. Eksik servis yetkisi ve meşgul yerel kilit sıfır probe çağrısıyla sonuçlandı. Bütün denemeler sahte ağ yanıtları ve geçici veritabanlarıyla yapıldı.

0.26 değişiklik bildirimi testleri, üç kanıt ailesinde ilk temel ve değişmeyen tekrarın alarm üretmediğini; gerçek değişimin tek okunmamış bildirim oluşturduğunu; IP, alan ve port geçişlerinin açıklanabildiğini doğrular. Kanıt ve bildirim aynı transaction içindedir; kontrollü bildirim hatası üç kayıt türünde de yeni kanıtı geri alır. Bozuk veya başka kanıta yöneltilmiş bildirim güvenli hatadır. Okundu/okunmamış, ortak sıra, durum sayacı, terminal/JSON, yedek/restore ve salt okuma davranışları birlikte doğrulandı. Şema 14→15 geçişi eski kanıtları ve kurtarma yedeğini koruyup yeni tabloyu boş başlatır; kontrollü DDL hatası ana veritabanını şema 14'te bırakır.

0.25 servis envanteri testleri yalnız kesin DNS eşleşmesinde sabit 10 porta gidildiğini; özel/yerel veya eşleşmeyen IP'de sıfır hedef bağlantısını; IPv4/IPv6 sayısal sabitlemeyi; açık/kapalı/belirsiz ayrımını; kapsam yarışında kayıt yapılmamasını; değişim geçmişi, bozuk kanıt, yedek/restore, terminal ve genel görünüm ilişkisini doğrular. Şema 13→14 geçişi eski satırları ve kurtarma yedeğini korur; kontrollü DDL hatası ana veritabanını şema 13'te bırakır.

0.24 dış yüzey ilişki testleri, boş kayıtlı kökü; üç adaylı sınırlı örneği; IP, sertifika, sertifika ad kapsamı ve MX ilişkilerini; aday durum toplamlarını ve son keşif bilgisini aynı görünümde doğrular. CLI denemesinde kaynak/probe çağrıları temizlendikten sonra `surface overview` çalıştırıldı; yeni ağ isteği oluşmadı ve veritabanı baytları değişmedi. Bozuk son dış yüzey özeti kısmi ilişki üretmeden güvenli hataya dönüştü.

0.23 kaynak kataloğu testleri sabit ve tekil dört bağlantıyı, ücretli bağımlılık bulunmamasını, yalnız açık komutlu HTTPS kontrolünün hedefe doğrudan bağlandığını ve `sources` komutunun ağ/veritabanı yan etkisi üretmediğini doğrular. İkinci kaynak erişim deneyi yalnız IANA `example.com` üzerinde yapıldı; Common Crawl indeks uç noktası 504 verdi ve kullanıcı veritabanına yazılmadı.

799 otomatik test 63,455 saniyede birlikte geçti. Testler geçici dizinlerde ve sahte ağ yanıtlarıyla çalışır; gerçek kullanıcı veritabanı değiştirilmez. Eşleştirmede önceki 36 etiketli ASCII örnek korunur.

0.53 canlı VEX denemesinde `CVE-2014-0160` resmî Red Hat dosyasından alındı; belge `final/3`, önem `Important`, 85 `fixed`, 14 `known_not_affected` bileşen ve 5 `vendor_fix` başvurusu olarak doğrulandı. Kaynak özeti `41f1685774959dd85c81a53e4df96d396a50e92d36faa0954465821bf1525c66` oldu; ayrı geçici veri klasörü/veritabanı oluşmadı.

0.56 canlı seçim denemesinde şema 23 Heartbleed yedeği yeni `/private/tmp/xti-v56-live.Ovt2A7` alanına geri yüklenip yedekli olarak şema 24'e taşındı; kesin RPM kaydı korundu ve kanıt tablosu boş başladı. Resmî NVD kaydı alındı, sürüm aralığı otomatik hükme çevrilmeden insan incelemesi `investigating` açıldı. Güncel Red Hat VEX yeniden alınarak `6Client-6.5.z:openssl-0:1.0.1e-16.el6_5.7.x86_64` bağı `fixed/exact_binary_package` beyanıyla seçildi; kanıt kimliği `39a6cfcc-662d-488e-83f1-9de7729770ff`, kaynak özeti `41f1685774959dd85c81a53e4df96d396a50e92d36faa0954465821bf1525c66` oldu. Kuyruk bir `exact_vendor_package` kanıtı gösterdi, insan kararı değişmedi. Ayrıntı, kuyruk, inceleme ve doctor okumalarından önce/sonra geçici veritabanı özeti `df6ba58090650d3913e1b83a504f222748cd5607131b9f72e2cf59613cfb80e8` kaldı.

0.57 canlı güncellik kontrolünde aynı kanıt resmî Red Hat VEX kaynağına yeniden bağlandı; paket anlık görüntüsü ve kaynak SHA-256 aynı, seçilen bağ mevcut, güncel durum `fixed`, genel durum `current` bulundu. Kontrol öncesi/sonrası geçici veritabanı özeti yine `df6ba58090650d3913e1b83a504f222748cd5607131b9f72e2cf59613cfb80e8` kaldı.

0.58 canlı geçiş denemesinde bu şema 24 Heartbleed veritabanı ayrı `/private/tmp/xti-v58-live.AiEARZ` alanına kopyalandı. Açık `migrate` önce şema 24 yedeği oluşturup veriyi şema 25'e taşıdı; varlık, NVD, ürün, RPM, maruziyet ve kesin VEX kanıtı korundu, düzeltme tabloları boş başladı. Mevcut kesin kanıta bağlı plan `01fc2c3a-3aae-4e17-9ef6-841b9a17827c` olarak oluşturuldu; sentetik uygulama ve `not_observed` kontrolü üç eklemeli olayda saklandı. Kontrol sonrası maruziyet `investigating` kaldı. Salt-okunur plan ve maruziyet ayrıntılarından önce/sonra veritabanı SHA-256 özeti `4ddd19b2eec239951d11d5db3d92dc47b86df5bc11db13edf604027a20a26458` olarak değişmedi. Bu sentetik kabul akışı gerçek bir paket yükseltmesi veya zafiyet kapanma iddiası değildir.

0.59 canlı kuyruk denemesinde aynı şema 25 Heartbleed kaydı bir açık/uygulanmış plan, `not_observed` son kontrolü ve sıfır vadesi gelmiş kontrol olarak gösterildi. Kuyruk insan kararını `investigating` durumunda bıraktı; terminal ve JSON okumalarından önce/sonra veritabanı SHA-256 özeti yine `4ddd19b2eec239951d11d5db3d92dc47b86df5bc11db13edf604027a20a26458` kaldı. Ayrı boş kayıt alanında `init` ve `doctor` şema 25'i başarıyla doğruladı.

0.60 canlı süreli bastırma denemesinde aynı şema 25 Heartbleed kaydı önce `/private/tmp/xti-v58-live.AiEARZ/backups/xti.pre-v26-0dfaf7073e6841f192986ba269856049.db` yedeği alınarak şema 26'ya taşındı. Açık `investigating` inceleme bir günlük sentetik gerekçeyle bastırıldı; varsayılan liste/kuyruk sıfır, `--include-suppressed` görünümü bir kayıt gösterdi. Doctor bir etkin/bir toplam bastırma bildirdi; maruziyet kararı ve `not_observed` düzeltme sonucu değişmedi. Yazma sonrası terminal liste, kuyruk, ayrıntı ve doctor okumalarından önce/sonra SHA-256 özeti `496935e8a66fad46a4038f761969c6afe94d4985e12f0d5433c849eeec1a6def` kaldı. Bitişte yazmasız geri dönüş ayrıca denetlenebilir saatli otomatik testte doğrulandı; canlı kayıt gerçek risk kabulü değildir.

0.61 canlı SUSE VEX denemesinde `CVE-2014-0160` resmî 2023 geri-doldurma dosyasından alındı; belge `interim/29`, önem `important`, 573 `known_not_affected`, 339 `recommended` ürün bağı ve 1 `vendor_fix` kaydı olarak doğrulandı. Kaynak özeti `6458fa60faee9ed6f59ed2b650bd2da40bbd4f2a9197c07022c0aac6a17a33c9` oldu; ayrı veri klasörü/veritabanı oluşmadı. Bu sonuç yalnız SUSE ürün beyanıdır, yerel makinenin etkilenme kararı değildir.

0.62 terminal kabul denemesinde ayrı `/private/tmp/xti-v62-live.0giisU` kayıt alanı şema 27 ile oluşturuldu; `example.com` kritik iş önemi ve gerekçesiyle kaydedildi. Ayrıntı bir `set` olayı, `doctor` bir etkin/bir toplam önem kaydı gösterdi. Ayrıntı ve doctor salt okumalarından önce/sonra veritabanı SHA-256 özeti `b44cad930bb640bb251e6f2c5b1ca5d126d8984ae8865380ab4c7c0ea13ebdd7` olarak değişmedi. Güncel HTTPS+kritik varlığın açık incelemeyi `high` bandından `immediate` banda taşıdığı, eski kanıtın erişimi tekrar `unknown/stale` yaptığı ve insan kararının `investigating` kaldığı sentetik kabul testiyle doğrulandı; gerçek hedef ağına bağlanılmadı.

0.63 terminal kabul denemesinde ayrı `/private/tmp/xti-v63-live.xckCyd` kayıt alanı şema 28 ile oluşturuldu. `example.com` üzerindeki doğrulanmış `acme/agent 1.0` ürün kanıtı yenilendi; salt-okunur plan bir `product_evidence_changed` adayı buldu ve veritabanı özeti `2590e802…f2ee` olarak değişmedi. Açık çalışma 1/1 sonucu denetim geçmişine yazdı; öncesinde ve sonrasında insan kararı `affected`, gerekçesi, `updated_at` değeri ve iki karar olayı aynen kaldı. `show`, `runs` ve `doctor` okumalarından önce/sonra özet `8652023e…2d79` olarak değişmedi; doctor bir kayıtlı çalışma gösterdi. Denemede gerçek ağ kullanılmadı.

0.64 terminal kabul denemesinde ayrı `/private/tmp/xti-v64-live.36eGpE` kayıt alanındaki eski NVD kanıtı salt-okunur planda bir yenileme adayı verdi; plan öncesi/sonrası veritabanı özeti `205be032…df13` olarak değişmedi. Resmî adaptörün taşıması sahte kaynak yanıtıyla ağsız sınandı ve tam bir kaynak çağrısı yapıldı. Yenilenen NVD özeti `nvd_record_changed` yeniden inceleme nedenini üretti; insan kararı `affected`, gerekçesi, `updated_at` değeri ve iki karar olayı aynen kaldı. Son plan kaydı güncel buldu. Yenileme sonrası salt-okunur planlardan önce/sonra özet `75253bfb…6f2` olarak değişmedi; gerçek internete bağlanılmadı.

0.65 terminal kabul denemesinde ayrı `/private/tmp/xti-v65-live.CztGd1` şema 29 kayıt alanında değişmiş NVD özeti tek `vulnerability_review_required` bildirimi oluşturdu. Bildirim okundu işaretlendikten sonra aynı komut bir adayın önceden bildirildiğini gösterip sıfır yeni kayıt üretti; okundu zamanı korundu. Tekrar komutu, kutu ayrıntısı ve maruziyet okumasından önce/sonra veritabanı özeti `958bda44…eba8` olarak değişmedi. İnsan kararı `affected`, gerekçesi, `updated_at` değeri ve iki karar olayı aynen kaldı; denemede gerçek ağ kullanılmadı.

0.71 terminal kabul denemesinde `vuln source-evaluation`, var olmayan `/private/tmp/xti-v71-parent.hZKFj7/not-created` veri konumuyla JSON çalıştırıldı. Profil `official-vendor-source-gate-v1`, zorunlu kapı sayısı altı, tek seçilen kaynak `canonical-ubuntu-osv` oldu; dört adayın ölçütleri, engelleri ve resmî bağlantıları çıktı. Komut sonunda veri klasörü oluşmadı (`storage_created=false`), ağ çağrısı yapılmadı ve sürüm `XTI 0.71.0` oldu.

0.70 terminal/veritabanı kabul denemesinde `/private/tmp/xti-v69-live.h30a7257` içindeki iki tamamlanmış pencere 1–16 Ekim dönemi için ağsız özetlendi. Operasyon durumu `gaps`, pencere sayıları `2/2/0/0`, dikkat ve yeniden başlatma `0/0`, kapsama 1–15 Ekim ve tek açık dönem 15–16 Ekim oldu. Son ilerleme ikinci pencerenin sıra 1 tamamlanmasıydı; `--recent-limit 1` JSON görünümü aynı sonucu tek son pencereyle verdi. İki okuma öncesi ve sonrası SHA-256 `2a6dfdde…8f91c5` olarak değişmedi ve sürüm `XTI 0.70.0` oldu.

0.69 terminal/veritabanı kabul denemesinde temiz `/private/tmp/xti-v69-live.h30a7257` şema 31 kayıt alanındaki 15 günlük boşluğun ilk iki penceresi iki sahte resmî sayfayla işlendi. Komut önce üç aday planladı; limit 2 ile iki kaynak çağrısı yaptı, iki sayfayı ve iki pencereyi tamamladı, iki CVE ve iki kaynak çalışması kaydetti. Son plan yalnız 15–16 Ekim arasındaki bir günlük boşluğu gösterdi. Sonraki salt-okunur plan öncesi ve sonrası SHA-256 `2a6dfdde…8f91c5` olarak aynı kaldı. Terminal kodları sıfır, kaynak çağrısı tam iki ve sürüm `XTI 0.69.0` oldu; gerçek ağ kullanılmadı.

0.68 terminal/veritabanı kabul denemesinde temiz `/private/tmp/xti-v68-live.lLgYEV` şema 31 kayıt alanında 1–16 Ekim dönemi ağsız planlandı. On beş günlük tek boşluk 7+7+1 günlük üç adaya ayrıldı; `--limit 2` iki adayı ve kesilmeyi, limit 100 bütün üç adayı gösterdi. Terminal ve JSON başlangıç/bitiş, yeni durum, sıra 0 ve kanonik resmî NVD istek adreslerini aynı verdi. İki plan okumasından önce ve sonra veritabanı SHA-256 özeti `19c62ed7…2e16d` olarak değişmedi. Kaynak adaptörü çağrılmadı, pencere/CVE yazılmadı ve sürüm `XTI 0.68.0` oldu.

0.67 terminal/veritabanı kabul denemesinde 0.66 kabul kaydının kopyası `/private/tmp/xti-v67-live.JlbGQm` içinde şema 30'dan 31'e taşındı; önceki tamamlanmış pencere korundu. Gerçek saate göre oluşturulan ikinci sahte pencere tamamlandı; liste iki tamamlanmış pencereyi gösterdi ve yeni dönem kapsanmış sayıldı. Salt-okunur liste/ayrıntı/kapsama öncesi özet değişmedi. Açık gerekçeli yeniden başlatma önceki `complete` durumunu denetim olayına kaydetti, imleci sıfırladı ve pencereyi `ready` yaptı; aynı dönem yeniden boşluk olarak göründü. Dört NVD kaydı, üç kaynak çalışması ve eski değişiklik geçmişi korundu. Sonraki salt okumalar veritabanını değiştirmedi; son SHA-256 `f57cfbf9…3be8` kaldı. Yapay olarak gelecek zaman damgalı eski pencereyi yeniden başlatma denemesi saat güvenlik kapısında doğru biçimde reddedildi; kapı aşılmadı. Denemede gerçek ağ kullanılmadı.

0.66 terminal/veritabanı kabul denemesinde ayrı `/private/tmp/xti-v66-live.8ekseawt` şema 30 kayıt alanındaki bir günlük pencere iki sahte resmî taşıma sayfasında işlendi. İlk sayfa iki kaydı atomik yazıp sırayı `2` yaptı; ikinci sayfa üçüncü kaydı ekleyip pencereyi tamamladı. Üçüncü çağrı `already_complete` döndü ve kaynak çağrısı iki olarak kaldı. Üç CVE, üç eklemeli olay ve iki başarılı kaynak çalışması kaydedildi. İlk plan ile tamamlanmış tekrar çağrısı veritabanını değiştirmedi; son SHA-256 `1d6bc152…25df9` kaldı. Denemede gerçek ağ kullanılmadı.

0.52 canlı seçim denemesinde geçici Heartbleed incelemesinin CVE'si yerelden alındı; Red Hat HTTPS başvurusu güncel 118 OSV `ADVISORY` kaydı içinde doğrulandı ve `distribution_advisory` türünde açıkça eklendi. Kanıt kimliği `434b58da-56ed-4098-8820-5e52960f29ca`, kaynak özeti `714b6694aebcaa62d5f1a5bad55d08a2b8c28746f518650e84f77e118ccd8ab6` oldu. Kuyruk iki etkin kanıt gösterdi; `immediate` bandı, nedenler ve `investigating` insan kararı değişmedi. Yazma sonrası ve salt okumalardan sonra geçici veritabanı özeti `acdf8f5643f6a2d2b2d9421b9b8ca7ad9de3e40a0bb44ff437a20db555303798` kaldı.

0.51 canlı OSV denemesinde `CVE-2014-0160` resmî API'den ayrı geçici yolda alındı; OSV kaydı, zamanlar ve 118 `ADVISORY` başvurusu doğrulandı, ilk 10'u gösterildi ve kaynak özeti `714b6694aebcaa62d5f1a5bad55d08a2b8c28746f518650e84f77e118ccd8ab6` oldu. OSV'de etkilenen paket satırı bulunmaması “etkilenmiyor” olarak yorumlanmadı. Önizleme veri klasörü/veritabanı oluşturmadı.

0.50 canlı boşluk filtresi denemesinde aynı Heartbleed incelemesi `--evidence present` listesinde göründü ve `--evidence missing` listesinde görünmedi. Filtre kalıcı kaydı veya öncelik nedenlerini değiştirmedi. 0.49 bağlam denemesi bir destek kanıtlı inceleme ve bir etkin `package_inventory` kanıtı göstermişti. Bütün terminal/JSON okumalarından önce ve sonra veritabanı SHA-256 özeti `e9e4f4a1217d17e5207efc2df3bbc1e05a56577c4d08971f923641a1c25983fe` olarak aynı kaldı.

0.48 canlı destek kanıtı denemesi aynı ayrı geçici kayıt alanını önce şema 21 yedeği alarak şema 22'ye taşıdı. Heartbleed/OpenSSL `1.0.1f` incelemesine `package_inventory` türünde açıkça geçici kullanıcı beyanı bağlandı; kanıt hiçbir otomatik `affected` kararı üretmedi. Geçiş yedeği `backups/xti.pre-v22-24342e6de10e4d178ffdb88ffc8cc55b.db` olarak korundu. Liste, ayrıntı ve `doctor` okumalarından önce ve sonra veritabanı SHA-256 özeti `e9e4f4a1217d17e5207efc2df3bbc1e05a56577c4d08971f923641a1c25983fe` olarak aynı kaldı; kullanıcı kayıt alanına yazılmadı.

0.47 canlı kuyruk denemesi aynı ayrı geçici kayıt alanındaki Heartbleed/OpenSSL `1.0.1f` incelemesini “Hemen incele” bandında gösterdi. Nedenler CISA KEV'de bilinen istismar, insan durumunun araştırılıyor olması, EPSS `0.99999` değerinin `0.9` eşiğini aşması ve CVSS 3.1 `7.5 HIGH` olarak ayrı kaldı; ransomware kullanımı `Unknown` olduğundan neden sayılmadı. Kuyruk öncesi ve sonrası veritabanı SHA-256 özeti `1bc0b7aef90e07e011bdaa44365de8b8a8fb1bc55f50bcdb8291adeb0b5e98ca` olarak aynı kaldı; ağ isteği veya karar değişikliği yapılmadı.

0.46 canlı yaşam döngüsü denemesi bu kayıt alanını önce şema 20 yedeği alarak şema 21'e taşıdı. Heartbleed/OpenSSL aralık adayı “insan tarafından doğrulanacak” gerekçesi ve yedi günlük yeniden kontrolle `investigating` durumunda açıldı; otomatik `affected` hükmü verilmedi. Terminal listesi bir açık/görünür kayıt ve sıfır yeniden-inceleme uyarısı, `doctor` bir toplam kayıt gösterdi. Geçiş yedeği `/private/tmp` içindeki ayrı deneme alanında korundu; kullanıcı kayıt alanına yazılmadı.

0.44–0.45 canlı görünüm denemeleri bu ayrı geçici kayıt alanındaki OpenSSL `1.0.1f` ürünü ve Heartbleed kaydıyla yapıldı. Tek ürün görünümü NVD aralığını elle inceleme olarak tutarken CISA KEV, FIRST EPSS `0.99999`/`0.99996`, CVSS 3.1 `7.5 HIGH` ve CVSS 2.0 `5 MEDIUM` bilgilerini ayrı gösterdi. Envanter görünümü bir etkin ürün, bir aday ve bir elle inceleme sonucu verdi. Görünümler öncesi ve sonrası veritabanı SHA-256 özeti `19eac08ea5af63ebae77e6eb3d0b2f89541cce214191b2da3eec9f6650cbd174` olarak aynı kaldı.

0.43 canlı ürün karşılaştırması bu ayrı geçici kayıt alanını önce doğrulanabilir şema 19 yedeği alarak şema 20'ye taşıdı. `example.com` için kullanıcı beyanlı OpenSSL `1.0.1f` kaydı eklendi. Heartbleed değerlendirmesi NVD'nin `>=1.0.1, <1.0.1g` aralığını buldu; aralığı otomatik hesaplayıp maruziyet ilan etmek yerine “elle sürüm/bağlam incelemesi gerekli” dedi.

0.41 canlı CPE denemesi ayrı geçici kayıt alanındaki Heartbleed NVD kaydını salt okunur açtı. 54 CPE koşulunun tamamı doğrulandı: 47 `vulnerable=true` ürün koşulu ve 7 `vulnerable=false` donanım/ortam koşulu. OpenSSL aralığı ve sonraki `AND` gruplarındaki firmware+donanım ilişkileri ayrı gösterildi.

0.40 canlı yürütme denemesi ayrı geçici kayıt alanında planın ilk CVE'si Heartbleed (`CVE-2014-0160`) için yapıldı. Kısıtlı ortamın ilk bağlantı hatası ayrı başarısız kaynak çalışması olarak saklandı; ağ erişimli ikinci açık komut kaydı başarıyla aldı. Birleşik görünüm KEV, EPSS ve NVD/CVSS için `3/3` kapsam; NVD `7.5 HIGH` CVSS 3.1 ve `5 MEDIUM` CVSS 2.0 gösterdi. Sonraki çevrimdışı plan adayı 2.102'den 2.101'e, eksik güncel KEV 1.761'den 1.760'a, eksik yüksek EPSS 827'den 826'ya indi. Salt-okunur durum/plan/genel görünüm öncesi ve sonrası veritabanı SHA-256 özeti `f2eb534a731f07849acfbe335cdea6ef2c80abd196e71f3c6c9a426b1579005d` olarak aynı kaldı; kullanıcı kayıt alanına yazılmadı.

0.39 canlı plan denemesi ayrı geçici kayıt alanındaki 1.762 güncel KEV, 397.508 güncel EPSS ve tek NVD kaydı üzerinde çalıştı. `0.9` EPSS eşiğinde 2.102 benzersiz eksik NVD adayı bulundu; bunların 1.761'i güncel KEV, 827'si yüksek EPSS koşulunu karşıladı. İlk 10 kayıt yaklaşık 0,63 saniyede gösterildi. Öncesi ve sonrası veritabanı SHA-256 özeti `3959f604f8ada7928e6d5f6a244185fee4b707931f4b9f181001a1c59416310b` olarak aynı kaldı; kullanıcı kayıt alanına yazılmadı.

0.38 canlı birleşik görünüm denemesi ayrı geçici kayıt alanında Log4Shell (`CVE-2021-44228`) için KEV, EPSS ve NVD/CVSS kaynaklarının üçünü birden gösterdi. KEV güncel katalog kaydını, EPSS `0.99999` olasılık ve `1` yüzdelik değerini, NVD ise birincil CVSS 3.1 `10 CRITICAL` ile CVSS 2.0 `9.3 HIGH` bağlamını korudu. Görünüm öncesi ve sonrası veritabanı SHA-256 özeti `3959f604f8ada7928e6d5f6a244185fee4b707931f4b9f181001a1c59416310b` olarak aynı kaldı; kullanıcı kayıt alanına yazılmadı.

0.37 canlı kaynak denemesi ayrı geçici kayıt alanında Log4Shell (`CVE-2021-44228`) kaydını NVD API 2.0'dan aldı. NVD ve ikincil sağlayıcıdan iki CVSS 3.1 değerlendirmesi, bir CVSS 2.0 değerlendirmesi, dört CWE ve 103 referans korundu. İlk kontrollü ayrıştırma hatası ayrı başarısız kaynak çalışması olarak kaldı; sonraki başarı eski hatayı gizlemedi. `status/list/show` öncesi ve sonrası veritabanı SHA-256 özeti aynıydı; kullanıcı kayıt alanına yazılmadı.

0.36 canlı kaynak denemesi ayrı geçici kayıt alanında FIRST'ün resmî `v2026.06.15` modelinden 29 Ekim 2026 tarihli 397.508 puanı 5,30 saniyede atomik olarak aldı. Veritabanı 128 MiB oldu. En yüksek puan listesi, durum ve Log4Shell CVE ayrıntısı çevrimdışı açıldı; öncesi/sonrası veritabanı SHA-256 özeti aynı kaldı. Kullanıcı kayıt alanına yazılmadı. Bu tek cihaz ölçümüdür, kapasite garantisi değildir.

0.35 canlı kaynak denemesi ayrı geçici kayıt alanında CISA'nın resmî 2026.10.28 kataloğunu aldı ve 1.762 kaydı atomik olarak ekledi. Resmî akıştaki kenar/Unicode boşlukları güvenli ASCII boşluğa normalleştirildi; kontrol karakterleri reddedilmeye devam eder. `status/list/show` öncesi ve sonrası veritabanı SHA-256 özeti aynı kaldı. Kullanıcı kayıt alanına yazılmadı.

0.22 sentetik e-posta DNS denemesinde kök MX ve SPF kaydı temel kanıta alındı, `_dmarc` kaydının bulunmaması tamamlanmış gözlem olarak saklandı. İkinci aynı sonuç `unchanged`, farklı DMARC politikası üçüncü sonuçta yalnız `dmarc` değişimi oldu. Bir SPF sorgusu hata verdiğinde MX/DMARC sonucu kaybolmadı; komut kısmi ve çıkış 3 oldu. Kapsam sorgu sırasında kaldırılınca sonuç yazılmadı. Listeleme öncesi/sonrası veritabanı aynı kaldı; bozuk özet güvenli hataya dönüştü ve yedek/restore bütün kanıtları korudu. Sorgu planında yalnız kök MX, kök TXT ve `_dmarc` TXT vardı; DKIM seçici sorgusu oluşmadı. Bu doğrulamada gerçek internet isteği veya kullanıcı veri alanı kullanılmadı.

0.22 geçiş denemesinde etkin dış yüzey kapsamı taşıyan şema 12 fixture'ının bütün eski satırları korundu; geçiş öncesi şema 12 yedeği oluşturulup e-posta DNS tablosu boş başladı. Kontrollü DDL hatası ana veritabanını şema 12'de bıraktı; kurtarma yedeği geçerli kaldı. Salt okuma eski veriyi kendiliğinden dönüştürmedi.

0.21 sentetik pasif izleme denemesinde aynı sertifika yanıtı üç tur işlendi. Üç ayrı keşif çalışması korunurken yalnız bir aday, bir kaynak kanıtı ve bir yerel bildirim oluştu. Başarısız, uyarılı/kısmi ve tamamlanmış turlar tek döngüde sırasıyla işlendi ve ayrı sonuç olarak raporlandı. Süre sınırı ikinci turu başlatmadı; bekleme sırasında `Ctrl+C` ilk tamamlanan turu ve bildirimini korudu. Geçersiz sınır ve bilinmeyen kök crt.sh adaptörüne erişmeden reddedildi. CLI denemesinde aktif DNS/HTTPS probe hiç çağrılmadı. Bu doğrulamada gerçek internet isteği veya kullanıcı veri alanı kullanılmadı.

0.20 sentetik uçtan uca denemesinde iki yeni pasif aday aynı transaction içinde kaynak kanıtı, iki tekil yerel bildirim ve tamamlanmış çalışma özetiyle kaydedildi. Aynı kaynak yeniden işlendiğinde çalışma geçmişine yeni sonuç eklendi, fakat aday veya bildirim çoğalmadı ve okundu bilgisi korundu. Yeni üçüncü aday yalnız bir yeni bildirim oluşturdu. Bulgu–aday–bulgu sırası ortak `1/2/3` kimlikleriyle kararlı okundu. Kaynak hatası aday/bildirim üretmeden başarısız çalışma olarak, uyarılı yanıt kısmi çalışma olarak kaldı. Geç kayıt hatası aday/kanıt/bildirim/çalışmanın tamamını geri aldı. Yedek/restore çalışma sonuçlarını ve okundu bilgisini korudu. Bu doğrulamada gerçek internet isteği veya kullanıcı veri alanı kullanılmadı.

0.20 geçiş denemesinde bir pasif aday taşıyan şema 11 fixture'ının bütün eski satırları ve kimlikleri korundu; geçiş öncesi şema 11 yedeği oluşturulup iki yeni tablo boş başladı. Eski adaydan geriye dönük bildirim veya çalışma uydurulmadı. Kontrollü DDL hatası ana veritabanını şema 11'de bıraktı; kurtarma yedeği geçerli kaldı. Salt okuma eski veriyi kendiliğinden dönüştürmedi.

0.19 sentetik uçtan uç denemesinde crt.sh fixture'ındaki `api.example.com` ve `*.vpn.example.com` pasif aday oldu; kökün kendisi ve ilgisiz SAN elendi. İlk/son CT zamanı, ham joker ad, kaynak URL'si ve özeti saklandı. Aynı kayıt ikinci keşifte aday/kanıt çoğaltmadı; yeni sertifika mevcut adayın kaynak sayısı ve son görülme zamanını güncelledi. `owned` kararı yeni kanıtta korundu; durum/gerekçe değişiklikleri eklemeli geçmişte kaldı. Varlık ve aktif kapsam sayısı değişmedi, hedef probe çağrılmadı. Liste/ayrıntı öncesi ve sonrası veritabanı baytları aynı kaldı; bozuk kanıt güvenli hataya dönüştü; yedek/restore bütün aday, kaynak ve kararları korudu. Kaynak hatası aday üretmeden görünür başarısız sonuç oldu. Bu doğrulamada gerçek internet isteği veya kullanıcı veri alanı kullanılmadı.

0.19 geçiş denemesinde şema 10 fixture'ının kayıtlı kökü ve dış yüzey kapsamı dahil bütün eski satırları korundu, geçiş öncesi şema 10 yedeği oluşturuldu ve üç boş pasif keşif tablosuyla şema 11'e geçildi. Kontrollü DDL hatası ana veritabanını şema 10'da bıraktı; kurtarma yedeği geçerli kaldı. Salt okuma eski veriyi kendiliğinden dönüştürmedi veya aday uydurmadı.

0.18 sentetik uçtan uç denemesinde doğrulanmış TLS fixture'ından issuer/subject, seri, tarihler, iki DNS adı ve DER SHA-256 alındı. Aynı sertifika ikinci kontrolde `unchanged`, yeni parmak izi ve bitiş tarihi üçüncü kontrolde yalnız `certificate` alan değişimi oldu. 12 gün kalan sertifika terminalde uyarı verdi. Geçersiz seri, tarih, SAN ve issuer örnekleri TLS kanıtını tamamlanmamış saydı ve hedef HTTP isteği göndermedi. Sertifika alanı çıkarılmış eski kontrol JSON'u `certificate=None` olarak okundu; v0.17 sertifikasız dış yüzey hash'i aynı kaldı. Bu doğrulamada gerçek internet isteği veya kullanıcı veri alanı kullanılmadı.

0.17 sentetik uçtan uca denemesinde kayıtlı `example.com`, gerekçeli kullanıcı beyanıyla dış yüzey kapsamına alındı. İlk sahte DNS/TLS sonucu temel kayıt, aynı IP/durumla ikinci kontrol değişiklik yok, farklı IP ile üçüncü kontrol eklenen/çıkan IP ve değişen bağlantı alanı olarak saklandı. `list/show` öncesi ve sonrası veritabanı baytları aynı kaldı. Kapsam kontrol sırasında kaldırıldığında ağ sonucu kanıt tablosuna yazılmadı. Kısmi hata güvenli terminal metniyle ayrı kanıt oldu. Yedek/boş konuma restore bütün kapsam olaylarını, kontrol sonuçlarını ve hash'leri korudu. Bu doğrulamada gerçek internet isteği veya kullanıcı veri alanı kullanılmadı.

0.17 geçiş denemesinde şema 9 fixture'ının bütün eski satırları korundu, geçiş öncesi şema 9 yedeği oluşturuldu ve üç boş dış yüzey tablosuyla şema 10'a geçildi. Kontrollü DDL hatası ana veritabanını şema 9'da bıraktı; kurtarma yedeği geçerli kaldı. Salt okuma eski veriyi kendiliğinden dönüştürmedi.

0.16 sentetik uçtan uca denemesinde süreli istisna etkin olduğu anda ham gözlem korundu; bulgu ve bildirim oluşmadı. Kesin bitiş anında yalnız okumak veritabanını değiştirmedi. Aynı kaynak yeniden işlendiğinde korunmuş gözlem tek bulgu ve bildirime bağlandı. Etkin kaydın bitişi güncellendiğinde `updated`, süresi dolduktan sonra açıldığında `reactivated` olayı aynı kimliğe eklendi. Bozuk bitiş zamanı gözlem/bulgu transaction'ının tamamını geri aldı. Şema 8 fixture'ı önce doğrulanabilir yedeklenip şema 9'a taşındı; eski kayıt kalıcı, kimliği ve olay sırası aynı kaldı. Kontrollü geçiş hatası ana veritabanını şema 8'de bıraktı.

0.15 sentetik uçtan uç denemesinde `domain-rules-v1` ve `domain-rules-v2` altında üç aday oluşturuldu. İki aday incelendi; birinin kararı kapatılmıştan şüpheliye değiştirildi, diğeri kararsız bırakıldı ve üçüncüsü bekledi. `feedback` toplam 3/incelenen 2/bekleyen 1, üç karar olayı ve bir yeniden incelenen bulgu raporladı; güncel kararları doğru kural gruplarına ayırdı. Okuma öncesi/sonrası veritabanı baytları aynı kaldı. Eksik kayıt alanı oluşturulmadı; son durumla karar geçmişi yapay olarak ayrıştırıldığında rapor sayı üretmeden durdu. JSON çıktısı domain, bulgu kimliği veya gerekçe taşımadı.

0.14 ortak 44 örneklik önceki kümede iki kaçırmayı giderdi: doğru pozitif 25→27, yanlış negatif 2→0, precision `%89,29`→`%90,00`, recall `%92,59`→`%100,00`, toplam doğruluk `%88,64`→`%93,18` oldu; üç bağlamsal yanlış pozitif değişmedi. Ardından üç negatif koruma eklenerek `domain-evaluation-v2` 47 örneğe çıkarıldı. Güncel v2 sonucu 27 doğru pozitif, 17 doğru negatif, 3 yanlış pozitif, 0 yanlış negatif; precision `%90,00`, recall `%100,00`, yanlış alarm oranı `%15,00`, toplam doğruluk `%93,62` ve baseline değişimi sıfırdır. Bu sayılar sentetik küme içindir.

Kural kimliği geçiş denemesinde eski `example-support.net` adayı `domain-rules-v1` kimliğiyle aynı bulguya bağlandı ve bildirim çoğalmadı. Yalnız yeni `exampel-login.net` adayı `domain-rules-v2` kimliği aldı. Unicode aday `idn-confusables-v1` kimliğini korudu. Yeni desen etkin tam adres istisnasındayken ham gözlem kaydedildi fakat bulgu/bildirim oluşmadı.

0.13 başlangıç ölçümünde 44 sentetik örneğin 27'si incelemeye gönderme, 17'si göz ardı etme beklentisi taşıdı. Kurallar 25 beklenen adayı yakaladı, 2 birleşik deseni kaçırdı; 14 göz ardı örneğini doğru eledi, 3 sentetik bağımsız bağlamı gereksiz alarma çevirdi. Etiket kümesi precision `%89,29`, recall `%92,59`, yanlış alarm oranı `%17,65`, toplam doğruluk `%88,64` verdi. Beş açık örnek kimliği ve gerekçesiyle raporlandı; kayıtlı başlangıç davranışından beklenmeyen değişim sıfırdı. Bunlar küçük sentetik politika ölçüleridir, gerçek tehdit tespit performansı değildir.

Paketlenmiş `domain-evaluation-v2` verisinin SHA-256 özeti `f75319…18582a` olarak yükleme ve teslim kontrolünde doğrulandı. `evaluate` ayrı geçici dizinde çalıştırıldığında internet bağlantısı denemedi, veri klasörü veya veritabanı oluşturmadı. Bozuk özet kontrollü terminal hatasına dönüştü; traceback veya kısmi rapor üretmedi. Önceki v1 ölçümü ve özeti 0.13 karar kaydında tutulur.

0.12 sentetik uçtan uca denemesinde `example.com → example-support.net` istisnası etkinleştirildi. İlk arama ham gözlemi kaydetti fakat bulgu/bildirim üretmedi. İstisna kaldırılınca aynı gözlem yeniden işlendi, tek bulgu ve tek bildirim oluştu. Önceden kapatılmış bir bulguya istisna eklenen ayrı akışta eski karar ve kanıt değişmedi; yeni gözlem istisna süresince bağlantısız kaldı, geri alma sonrasında mevcut bulguya bağlandı. İkinci izlenen varlık aynı adaya eşleştiğinde yalnız seçilen varlık bastırıldı. Bu doğrulamada gerçek internet isteği yapılmadı.

0.12 geçiş denemesinde şema 7 veritabanının bütün eski satırları korundu, geçiş öncesi şema 7 yedeği oluşturuldu ve boş istisna tablolarıyla şema 8'e geçildi. Kontrollü DDL hatası ana veritabanını şema 7'de bıraktı; kurtarma yedeği geçerli kaldı. İstisnanın ekleme/kaldırma/yeniden etkinleştirme geçmişi güncel yedek ve boş konuma restore sonrasında aynı okundu.

0.11 sentetik uçtan uca denemesinde izlenen `example.com` için Kiril `е` içeren aday kanonik `xn--xample-2of.net` olarak kaynak akışından geçti. `--typos` sorgu planı bu gerçek A-label'ı internette aradı; ilk çalışma tek bulgu/bildirim oluşturdu, ikinci çalışma aynı bulguyu ve kural kimliğini korudu. ASCII adayın önceki `domain-rules-v1/psl:...` kimliği ayrı testte değişmedi. İki kaynak ayrıştırıcısı aynı U-label/A-label değerini kanonik biçimde kabul etti. Bu denemelerde gerçek kaynak isteği veya kullanıcı kayıt alanına yazma yapılmadı.

Paketlenmiş Unicode 18.0 dosyalarının SHA-256 özetleri yükleme sırasında ve teslim kontrolünde doğrulandı: confusables `6ed3ee…f5b92`, IDNA mapping `a03b1e…fced1`. Güncel düzen şema 43'tür. Şema 1–42 kayıtları açık `./xti migrate` ve geçiş öncesi yedek gerektirir; eski kayıtlar korunur, eski veriden pasif aday, kaynak kanıtı, insan kararı, düzeltme planı, süreli bastırma, varlık iş önemi, yeniden değerlendirme çalışması, zafiyet değişiklik bildirimi, NVD pencere ilerlemesi, yeniden başlatma olayı, Ubuntu paket bağı, IOC kaynak iddiası, besleme çalışması, CTI varlık/ilişkisi, kayıtlı CTI sorgusu, CTI arama bildirimi, avcılık etiketi, analist notu, webhook hedefi, teslimi, ransomware iddia snapshot'ı, kuruluş/domain izlemesi, monitor oturumu veya kimlik adayı kararı uydurulmaz.

0.10 gerçek süreç kapatma denemesi: iki ayrı SIGKILL senaryosu çalıştırıldı. İlkinde yeni bulgu/bildirim kalıcı kayda geçtikten fakat son sayı özeti yazılmadan süreç öldürüldü; iki sorgu, kanıt ve yeni bildirim korundu, rapor eksik sayı özetini ayrı gösterdi. İkincisinde iş/izleme bağlantısı yazıldıktan fakat deneme başlamadan süreç öldürüldü; normal worker bu işi almadı, ayrı retry reddedildi. Salt okuma veritabanını değiştirmedi. Kurtarma bilinmeyen süreyi boş bıraktı; başlamamış işe deneme uydurmadı. Sonraki izleme aynı verilerle yeni bulgu/bildirim çoğaltmadı; eski okundu bilgisi ve karar korundu.

0.10 geçiş denemesi: önceki şema 6 veritabanının kopyası gerçek terminal komutuyla şema 7'ye taşındı. Bütün eski tablo satırları, 1002 iş, 1001 deneme, 2 bildirim ve bildirim sıra sayacı aynen korundu; önceki sürümde yedek oluşturuldu. Geçmiş aramalardan izleme grubu uydurulmadı. İki sahte kaynakla tek yeni tur iki bağlı iş oluşturdu; yedek/restore raporu, iş bağlantılarını ve sayaçları aynı döndürdü. Bu geçiş denemesinde ağ isteği yapılmadı.

0.10 kısa canlı denemesi: `badssl.com` için yalnız urlscan arşivinde iki tur, 300 saniye aralık ve 420 saniyelik yeni iş bütçesiyle çalıştırıldı. İki sorgu da 41 arşiv kaydı döndürdü. İlk tur 41 gözlem oluşturdu; ikinci tur sıfır yeni/41 mevcut gözlem kaydetti. Son durumda 41 gözlem ve sıfır aday bulgu vardı. İki kaynak denemesi complete, iki tur tamamlandı, çıkış 0 oldu. Ölçülen toplam süre 306,006 saniye; ilk bitişten ikinci başlangıca aralık 300,026 saniyeydi. Rapor ve bağlı işler yedekten aynı biçimde okundu. Sıfır aday, sahip olunan köklerin elenmesiyle uyumludur; tespit doğruluk oranı değildir. Bu beş dakikalık doğrulama saatlerce/günlerce çalışma veya kaynak sürekliliği garantisi değildir.

Ayrı ilk deneme ağ erişimi kısıtlı çalışma ortamında bağlantı hatası verdi; iki başarısız deneme ve çıkış 3 olarak kaydedildi. Bu, urlscan'in hizmet kesintisi olarak yorumlanmadı. Canlı başarı denemesi ağ erişimi olan ortamda ayrı geçici kayıt alanıyla yapıldı; kullanıcı kayıt alanına test verisi eklenmedi.

0.9 terminal denemesi: 0.8'in şema 6 test veritabanı kopyası `migrate` gerekmeksizin okundu. Sentetik geçmişte 1002 iş/1001 deneme oluşturuldu: eski bir tam arama, ardından 1000 başarısız deneme ve başka kaynak için sırada bir iş. Gerçek `./xti status` komutu son başarısızlığı ve önceki tamamlanan aramayı birlikte gösterdi; 25 saatlik aramayı eski saydı. Yeni eklenen adresi ve sıradaki işi aranmış kabul etmedi. Önceki 2 bildirim/1 okunmamış bilgisi korundu. Özet öncesi/sonrası veritabanının SHA-256 özeti aynıydı; yedekten dönüş sayaçları ve seçilen geçmişi aynen korudu.

Bu tek küçük denemede terminal başlatıcısı dahil özet yaklaşık 0,145 saniyede okundu; veritabanı 2043904 bayttı. Bunlar sentetik geçmiş ölçümleridir; büyük ölçek veya saatlerce/günlerce canlı çalışma kanıtı değildir. Yeni gerçek internet sorgusu yapılmadı. Durum okuması büyük sonuç JSON'larını bütün geçmiş için yüklemez; geçmiş tarama süresi kayıt sayısıyla büyüyebilir.

0.8 tekrarlı çalışma denemesi: `./scripts/python scripts/verify_inbox_soak.py --cycles 30` geçici verilerle ve ağ girişimleri engellenerek tamamlandı. İki sahte kaynak 30 turda 60 iş/71 deneme üretti; 6 gözlem, 3 bulgu, 3 bildirim ve 2 okunmamış bildirim sabit kaldı. On kontrollü sorgu hatası ve kayıt sonrası bir kesintinin ardından toplam 11 tekrar denemesinde bildirim kimlikleri, okundu zamanı, kanıtlar ve inceleme kararı korundu. Gerçek alt süreç SIGKILL denemesi de hem okunmuş hem okunmamış bildirim için kurtarma/yeniden deneme sonrasında aynı kayıtları doğruladı.

Bu hızlandırılmış 30 tur yaklaşık 1,72 saniye sürdü; geçici veritabanı 290816 bayt, tüm Python sürecinin tepe belleği 39239680 bayt oldu. Bunlar küçük sentetik veriyle tek yerel ölçümdür; uzun süreli canlı kullanım veya kapasite garantisi değildir. İş ve deneme geçmişi her turda büyür. Betik ortamı, sayıları, süreyi ve sınırları JSON olarak verir; geçici kayıt alanını sonunda kaldırır.

0.8 terminal denemesi: önceki şema 5 test veritabanının kopyası gerçek `./xti` komutuyla şema 6'ya taşındı. Eski tabloların bütün satırları, 222 gözlem ve bir temizlik kaydı korundu. Mevcut bulgu “Önceki kayıttan” bildirimi aldı. Okundu işleminin tekrarı ilk zamanı değiştirmedi; yeni sentetik adayın 10 kez işlenmesi yalnız bir yeni bildirim oluşturdu. Sonuç 2 bildirim/1 okunmamış oldu. İnceleme kararı okundu durumunu değiştirmedi; yedek/restore bildirimleri, eski bulgu ayrıntısını ve bakım geçmişini aynen korudu. Bu sürüm doğrulamasında yeni gerçek internet sorgusu yapılmadı.

0.7 süreç denemesi: gerçek alt süreç, sahte HTTP 200 kota başlığını SQLite'a kaydedip yanıt gövdesini okurken zorla kapatıldı. Yeni süreç serbest kalan worker kilidini aldı; kayıtlı 60 saniyelik bekleme nedeniyle sıfır HTTP açma çağrısı yaptı. Bekleme satırı değişmedi. Bu deneyde gerçek ağ isteği yapılmadı.

0.7 terminal ve bakım denemesi: önceki sürümdeki gerçek hedef kontrolü içeren geçici şema 4 veritabanının kopyası şema 5'e taşındı; bütün eski tablo satırları korundu. Sentetik bağlantısız kayıtlarla toplam 10222 gözlemde 10020 eski aday, 200 güncel ve bir tarihi bozuk kayıt vardı; bir gözlem mevcut bulgunun kanıtıydı. Önizleme 10000 kayıt seçti ve 20 eski kaydın kalacağını gösterdi. Açık uygulama öncesinde yedek alındı; sonra tam 10000 gözlem temizlendi. Bulgu, kanıtı, kararı ve hedef kontrolü birebir korundu. Yedeği boş konuma geri yüklemek 10222 gözlemi geri getirdi.

Bu tek yerel denemede terminal önizlemesi yaklaşık 0,175 saniye, yedekli uygulama 0,291 saniye sürdü. Dosya boyutu 2043904 bayt kaldı; SQLite içinde 1855488 bayt yeniden kullanılabilir boş alan oluştu. Bunlar küçük sentetik fixture ölçümleridir; büyük ölçek, disk kotası veya uzun süreli çalışma garantisi değildir. 0.7 doğrulamasında yeni gerçek internet sorgusu yapılmadı.

0.6 gerçek ağ denemesi: kontrollü `example.com` adresinde dört DNS adresi alındı; ilk IP üzerinde TLS doğrulandı ve HTTP 200 başlık yanıtı geldi. Geçici bir test bulgusuyla gerçek terminal başlatıcısından kontrol → inceleme → karar → JSON raporu → yedek → boş konuma geri yükleme tamamlandı. Kaynak, karar, bulgu ve kontrol kayıtları birebir korundu. Bu test bulgusu açıkça sentetik doğrulama kaydıdır; canlı arşiv tespiti veya tehdit iddiası değildir. Şema 3 içeren önceki gerçek urlscan denemesinin kopyası da 36 gözlem ve bir işi tüm satırları değişmeden koruyarak şema 4'e taşındı; geçiş yedeği eski sürümde doğrulandı.

0.5 gerçek ağ denemesi: `scan badssl.com --source urlscan` anonim erişimle 36 arşiv kaydı aldı; 36 gözlem ve sıfır aday kaydetti. Durum complete, çıkış 0 oldu. Kaynak son 30 günlük geçmiş sınırı bildirdi; bu bilgi kalıcı sorgu geçmişinde ve `sources` çıktısında doğrulandı. Aday çıkmaması doğru sahip olunan kök elemesine uygundur; tespit doğruluk oranı ölçümü değildir. Kaynak erişimi ve kota sınırları değişebilir.

Gerçek alt süreç, ilk sorgusunu kaydettikten sonra zorla kapatıldı; kilidin bırakılması, salt okumanın durumu değiştirmemesi, kurtarma ve ayrı denemeyle tekrar doğrulandı. Önceki sorgu, gözlem ve kullanıcı kararı korundu. Şema 2 içeren eski geçici veritabanının kopyasında 764 gözlem/26 bulgu korunarak gerçek terminal başlatıcısıyla geçiş, sıraya alma ve yedekten dönüş doğrulandı. 0.4 doğrulamasında yeni internet isteği yapılmadı.

Önceki 0.3 sürümünde gerçek ağ üzerinden `scan howsmyssl.com` komutu bir sorgudan 341 sertifika/764 gözlem aldı ve 26 aday kaydetti. Diğer sorgu HTTP 502 verdiği için sonuç doğru biçimde kısmi, çıkış kodu 3 oldu. Bu yalnız akış doğrulamasıdır; örnek adların kötü amaçlı olduğunu göstermez. Kaynak kullanılabilirlik garantisi vermez.

Ayrıca ağdan alınan daha büyük bir yanıt (1634 sertifika, 4133 desteklenen gözlem ve bir desteklenmeyen ad) kaydedilip ağsız tekrar işlendi. İlk işleme yaklaşık 5,08 saniyede 4133 gözlem/70 aday oluşturdu; ikinci işleme 2,69 saniyede sıfır yeni gözlem/bulgu oluşturdu. Kimlikler ve kanıtlar korundu. Bu tekrar deneyi canlı arama süresi ölçümü değildir.

Sentetik örneklerin geçmesi gerçek internet doğruluk oranını göstermez. Kurulu wheel, farklı işletim sistemleri ve büyük ölçek doğrulanmadı. Paketlenmiş referans listesi ve lisansı [THIRD_PARTY.md](../THIRD_PARTY.md) içindedir.

## Açık kapsam ve sınırlar

`analyze` yalnız daha önce kaydedilmiş kanıtı okur; yeni pasif arama, DNS sorgusu, hedef bağlantısı, IOC besleme güncellemesi veya başka yazma işi başlatmaz. IOC kapsamı kök domain ile son kayıtlı web/servis IP'lerinin tam eşleşmesidir; alt alan adları, URL'ler, ilişkisel CTI grafiği ve benzerlik eşleşmesi bu ilk dilimde yoktur. Katalog boşsa sonuç değerlendirilmedi olarak gösterilir. Ürün/sürüm/paket/CVE hattı aktif kapsam dışıdır.

İzleme denemesi varsayılan üç tur, 3600 saniyelik tur sonrası aralık ve 86400 saniyelik yeni iş bütçesiyle çalışır; sınırlar README'dedir. Süre dolunca yeni kaynak işi başlamaz; başlamış kaynak araması kendi çoklu sorgu/tekrar/zaman sınırlarıyla bittiğinden toplam süre aşılabilir. Bekleme sırasında da worker kilidi tutulur: aynı kayıt alanındaki başka arama, hedef kontrolü ve bakım çalışamaz; okuma/inceleme/okundu işlemleri kullanılabilir. Tamamlanan tur bütün kaynak denemelerinin bitmesidir, hepsinin başarılı olması değildir. Yeni sonuç sayıları eksik denemeleri kapsamaz; `unknown_result_count` bunu görünür kılar. Genel worker bağlı işleri seçmez; yeniden ölçüm yeni bir `monitor start` oturumudur. Kalıcı otomatik devam veya arka plan hizmeti yoktur.

Durum özeti kayıtlı aramaları gösterir; kaynakların anlık erişimini veya worker'ın hâlâ açık olduğunu ölçmez. `current` son tamamlanan aramanın seçilen süre içinde olduğunu anlatır; yeni başarısız deneme ayrıca görünür. Çok hedefli kısmi iş, hiçbir hedefin tam arama zamanını yenilemez. Eşik yalnız görünümü etkiler, arama zamanlamasını değiştirmez. Genel sayaçlar tüm kayıt alanına aittir; ayrıntı varsayılan 20, en fazla 100 adresle sınırlıdır. Başka bir kayıtlı adres `status ALAN_ADI` ile seçilir. Çıkış 0 özetin okunmasıdır, bütün kaynakların sağlıklı olması değildir. Tam veritabanı bütünlük kontrolü için `doctor` kullanılır.

Kesintisiz CT akışı, otomatik başlayan sunucu hizmeti, dağıtık kuyruk, HTTP yanıtını kaldığı yerden sürdürme, dış bildirim teslimi, ham yanıt/kanıt dosyaları ve zamanlanmış otomatik temizlik henüz yok. IDN profili sağdan sola/ContextJ etiketleri ve bütün Unicode sorgu permütasyonlarını kapsamaz; izlenen varlık hâlâ normal ASCII olmalıdır. Bağlantısız gözlem temizliği açık bakım komutuyla yapılır; bulgular, bağlı kanıtlar, işler ve yedekler otomatik yaşlandırılmaz. Toplam disk kotası veya dosya küçültme yoktur. Kalıcı arşiv işi yeniden denendiğinde arama baştan yapılır; tekilleştirme eski bulguları korur. Hedef kontrolünde yalnız tamamlanan kayıt saklanır; yarım hedef kontrolünün ayrı kalıcı işi yoktur. Bulgular geçmiş kaynak gözlemlerine dayanan metinsel adaylardır; doğrulanmış phishing değildir. DNS/HTTPS erişimi bu kararı değiştirmez. İki kaynağın indeks, tarih ve sayfa sınırları vardır; bütün internet kapsanmaz. urlscan hesap/API anahtarı yönetimi ve ek sayfa indirme yoktur.

Bildirim kutusu yereldir; e-posta, SMS veya masaüstü bildirimi göndermez. Yeni bulgu, sürüm geçişinde eski bulgu, ilk kez bulunan pasif aday, açık kontrol komutunun kaydettiği gerçek dış yüzey değişikliği ve açık `vuln change-notify` komutundaki yeni zafiyet kanıt durumu için kayıt oluşur. İlk temel/değişmeyen kontrol, kaynak kesintisi, mevcut adaya yeni kanıt ve aynı zafiyet durumu bildirim oluşturmaz. Liste/ayrıntı okundu sayılmaz. Eski bulgular geçmiş okundu bilgisi bulunmadığı için okunmamış taşınır; eski pasif aday, dış yüzey veya zafiyet kanıtından geriye dönük bildirim üretilmez. Bir sayfa ve sayaçları tutarlı okunur; sayfalar arasında okundu değişiklikleri sonraki görünümü etkileyebilir. Webhook yalnız kullanıcının açıkça seçtiği mevcut bildirimi dışarı yollar; kutudaki her yeni kayda otomatik abone olmaz.

Webhook hedef sırrı komut satırında veya normal/JSON çıktıda gösterilmez, fakat kişisel yerel tehdit modelinde SQLite veritabanı ve yedeklerde base64 olarak saklanır; uygulama düzeyi şifreleme veya harici sır kasası yoktur. Hedef yalnız HTTPS/443 ve tamamı genel adreslere çözülen DNS ile kullanılabilir. HTTP 2xx alıcının isteği kabul ettiğini gösterir; olayın işlendiğini veya incelendiğini kanıtlamaz. Alıcı imza, zaman penceresi ve teslim kimliği tekilliğini doğrulamalıdır. Otomatik abonelik, batch/due worker, zamanlayıcı, inbound webhook, OAuth/mTLS ve sağlayıcıya özgü SIEM biçimi henüz yoktur.

`feedback` yalnız o andaki son kullanıcı kararı, toplam karar olayı ve kural sürümü dağılımını gösterir. Zaman aralığı, varlık filtresi, karar gerekçesi, örnek dışa aktarma veya bağımsız doğrulama içermez. İnceleme kapsamı kalite oranı değildir; kapatılmış bulgu otomatik yanlış pozitif, şüpheli bulgu otomatik gerçek phishing sayılmaz. Rapor otomatik kural değiştirmez veya dışarı gönderilmez.

Kalıcı bekleme aynı veritabanı/yerel çalıştırıcı kapsamındadır; başka programların veya cihazların kota kullanımını takip etmez. Yeniden başlatma sonrası cihaz UTC saatine dayanır. Mevcut süreçte görülmüş süre monotonic alt sınırla korunur. Çok uzun sağlayıcı isteği kısaltılmaz; takvim aralığını aşıyorsa maksimum tarih kaydedilir. Önceki sürümün belleğinde kalmış beklemeler geriye dönük üretilmez.

Hedef kontrolü Google Public DNS ve tek genel IP üzerinde HTTPS HEAD ile sınırlıdır. Sayfa içeriği, diğer IP'ler, portlar ve yönlendirmeler incelenmez. `103 Early Hints` gibi ek ara HTTP yanıtları tamamlanamayan kontrol sayılır. Toplu kontrolde başarısız denemeler de altı saat bekler; tek bulgu açık komutla hemen yenilenebilir. Rapor tek bulgu içindir ve 8 MiB sınırındadır. İnceleme listesi bildirim teslimi veya tehdit skoru değildir.

`surface check` aynı sınırlı ağ politikasını yalnız açıkça etkinleştirilmiş kayıtlı tam domain için kullanır. Kapsam onayı kullanıcı beyanıdır; DNS tabanlı teknik sahiplik kanıtı değildir. `surface discover/watch` seçime göre crt.sh veya theHarvester üzerinden yalnız Common Crawl/Wayback pasif arşivlerine sorgu gönderir; bulunan adlara bağlanmaz. `watch` terminal açıkken çalışır; takvim servisi veya bilgisayar kapalıyken otomatik yürütme değildir. Adayı `owned` işaretlemek varlık veya aktif kapsam oluşturmaz. Sürekli CT akışı, pasif DNS ve OCSP/CRL/CT zincir doğrulama kaydı yoktur. Her açık kontrol yeni kanıt oluşturur; `unchanged` değişim olayı olmadığını anlatır, ağ bağlantısı yapılmadığı anlamına gelmez. DNS/TLS/HTTPS, sertifika, pasif aday veya port durumu tek başına risk ya da olay kararı değildir.

`surface mail check` yalnız kullanıcı komutuyla kök MX/SPF/DMARC görünümünü alır. DKIM seçici keşfi, MTA-STS/TLS-RPT, SMTP/TLS teslim deneyi, DMARC toplu raporu, e-posta gönderimi veya arka plan zamanlaması yoktur. Kayıt varlığı/yokluğu ya da değişimi güvenlik, teslimat, sahiplik veya yanlış yapılandırma hükmü değildir. Google Public DNS harici kamu hizmetidir; erişilebilirliği ve koşulları platform tarafından garanti edilmez.

`surface services check` yalnız sabit 10 TCP portuna ve tek açıkça belirtilen genel IP'ye bağlantı dener. Banner, ürün/sürüm doğrulaması, UDP, serbest port aralığı, bütün DNS IP'leri, CVE eşleştirmesi veya zafiyet taraması yoktur. DNS eşleşmesi ve kullanıcı gerekçesi teknik IP sahiplik kanıtı değildir. Açık port yalnız o andaki TCP bağlantı kanıtıdır; “kapalı” başka IP'leri, UDP'yi veya daha sonraki zamanı kapsamaz.

`surface technologies` yalnız son servis kanıtındaki açık TCP portlarını yaygın kullanım ipucu olarak gösterir. Üretici, ürün, sürüm, CPE veya paket bilgisi doğrulamaz; hiçbir ipucu CVE maruziyeti oluşturmaz. Kapalı/belirsiz port teknoloji yokluğu, güncel ipucu da ürünün hâlâ aynı olduğu anlamına gelmez.

`surface cname check` yalnız açıkça etkinleştirilmiş tam adın genel Google DNS görünümünü sorgular. En fazla sekiz CNAME adımı ve terminal A/AAAA sonucu saklanır; DNAME, NS delegasyonu, özel DNS görünümü, sağlayıcı hesabı/kaynak alınabilirliği ve hedef HTTP içeriği incelenmez. Hedef NXDOMAIN geçici veya görünümle ilgili olabilir; tek başına takeover kanıtı değildir. İlk CNAME dilimi değişiklik bildirimi de üretmez.

`surface overview` yalnız daha önce saklanmış son kanıtları ve sınırlı aday örneğini tek okuma anında ilişkilendirir. Yeni veri toplamaz; IP'nin özel/dedike olduğunu, sertifika kapsamındaki adın sahipliğini, açık portun çalışan ürününü veya ilişkinin güvenli/kötü niyetli olduğunu söylemez. `surface inventory` aday kararı, kayıt ve kapsamı ayrı gösterir fakat teknik sahiplik doğrulamaz veya katmanları otomatik değiştirmez. Genel bir varlık grafiği ve geçmişteki bütün ilişki sürümleri henüz yoktur.

İzlenen köklerin altındaki adresler dış taklit kontrolünde atlanır. Kaynaktaki desteklenmeyen adlar sayılarak elenir; dosyada ise hatalı satır tüm importu reddeder. Önceki 0.1–0.25 kayıtları için `./xti migrate` gerekir; eski JSON geçmişi korunarak okunur. Şema 6'daki bulgu bildirim kutusu yeniden oluşturulmaz, okundu bilgisi değişmez; eski veriden istisna, dış yüzey kapsamı, pasif aday, keşif çalışması, aday/değişiklik bildirimi, e-posta DNS veya servis kontrolü uydurulmaz. Eski kalıcı istisnalar kalıcı kalır. Eski uygulamaya geri dönüş geçiş öncesi yedekledir. Varsayılan JSON `data.results` altında kaynak başına sonuç, `--check` varsa ayrıca `data.checks` içerir. `sources` ayrıca kayıtlı beklemeleri içerir. Ayrıntılar README'dedir. Kilit yerel macOS/Linux dosya sistemi içindir; Windows ve dağıtık çalıştırma desteklenmez.

R1/R2'nin yerel parçaları, kalıcı işler, iki internet kaynağı, PHI-02'nin dar ve süreli/kalıcı tam adres istisnası ve sürümlü sentetik değerlendirme kümesi ile PHI-04/05/06'nın sınırlı kontrol/inceleme/JSON rapor parçaları uygulandı. Onaylı tam domain için DNS/IP/TLS/HTTPS temel, sertifika kimliği/değişim kanıtı, kaynaklı pasif subdomain aday/karar/çalışma envanteri, kesin IP'ye sabit sınırlı TCP kanıtı, CNAME hedef kanıtı ve ürün iddiası taşımayan teknoloji ipuçları ASM-01/02/03/04/05'in dar dilimlerini ilerletti. Açıklanabilir maruziyet ve sarkan CNAME adayı ASM-05'in yalnız ilk sağlayıcı-bağımsız dilimidir; panel, delegasyon ve gerçek takeover tespiti tamamlanmış değildir. Doğrulanmış ürün yaşam döngüsü, envanter geneli NVD adayı, gerekçeli insan maruziyet geçmişi ve kontrollü toplu yeniden değerlendirme VUL-02'yi; KEV/EPSS/CVSS nedenli çalışma bantları ile insan beyanlı iş önemi ve kayıtlı erişilebilirlik bağlamı VUL-03'ü ilerletti. Varlık grubu/kalıtım politikası, güvenilir sürüm aralığı, backport/kurulum bağlamı ve zamanlanmış kaynak/değişiklik aboneliği henüz yoktur. Kalıcı bekleme, kontrollü bakım, durum özeti ve gruplu izleme denemesi R3 işletim kapsamını ilerletti. PHI-06'nın birleşik yerel kutusu ve kullanıcının seçtiği tek bildirim için manuel imzalı webhook dış teslimi çalışıyor; otomatik abonelik/toplu worker ve diğer kanallar tamamlanmış değildir. Uzun çalışma, teknik sahiplik doğrulaması, tam subdomain/servis envanteri, otomatik ürün doğrulaması, gerçek kullanım etiketleri ve tam kapsam ölçümü olmadığı için G1/G2/G3/G4'ün bütün maddeleri tamamlanmış sayılmaz. 0.133.0 kayıtlı profil için Linux zamanlama dosyalarını ve doğrulanmış yedek bakımını ekler; genel olay aboneliği ve dağıtık servis değildir. Runtime verisi, sırlar ve sanal ortam kaynak kontrolü dışındadır.

## Son doğrulama

0.138.0 tam paket **1.918 test / 673,814 saniye**: 1.917 başarılı, yalnız
Linux `systemd-analyze` kontrolü macOS'ta atlandı. Hızlı kapı **524 test /
250,402 saniye**: 523 başarılı ve aynı tek atlama. Shell sözdizimi ve
Python derlemesi de geçti. Çalışmalar boyunca 808 kod/test/script/
konfigürasyon dosyasının özetleri değişmedi. Bunlar yerel doğrulamalardır;
GitHub Actions sonucu olarak sunulmaz.

55 yeni test; on arama ailesi, gerçek toplam/sayfalama, geçerli gezinme
komutları, tek okuma kesiti, tarihî tedarikçi/insan kararı, sessiz başlangıç,
üç kaynak ayrımı, gizli bozuk geçmiş, ağ öncesi ret ve bildirim okundu
bağımsızlığını kapsar. Kaynak/izleme/bildirim yazıldıktan sonra enjekte edilen
hata ve collection receipt hatasında bütün yazımların geri alındığı görüldü.
Bozuk tedarikçi yaşam döngüsü arama ve ilişki ekranında aynı ortak okuyucuyla
reddedilir. 216 eski geçiş testi ayrıca geçti; örnek 42 komut ayrıştırıldı.

0.138.0 gerçek verinin kopyasında 63→64 geçişi **133 eski tablo / 86.843
satırın** kolon, rowid, değer ve SQL tanımlarını; sıra sayaçlarını birebir
korudu. Dört yeni tablo boştu. Benzersiz yedekten yeni dosyaya geri dönüş,
tekrarlı migrate ve ağsız yeni komutların veriyi değiştirmemesi doğrulandı.
Asıl yerel veritabanı da benzersiz yedekle 63→64 geçirildi; aynı 86.843
satır ve tüm eski tanımlar korundu. Toplam 137 tablo var; yeni dört tablo
boş. Bütünlük ve yabancı anahtar kontrolleri geçti; kişisel izleme açılmadı.


0.137.0 tam paketi **1.863 test / 628,817 saniye** ile tamamlandı: 1.862 geçti,
yalnız Linux `systemd-analyze` kontrolü macOS'ta atlandı. Testlerin başı ve
sonunda 784 kod/test/script/konfigürasyon dosyasının özetleri aynıydı.
Gerçek yerel veritabanı benzersiz yedekle 62→63 geçirildi; **133 tablo /
86.843 satırın** kolon/rowid/değerleri ve sıra ayırıcıları birebir korundu.
Bütünlük ve yabancı anahtar kontrolleri geçti; yeni olay veya izleme üretilmedi.

0.137.0 hızlı kapısı **469 test / 222,752 saniye** ile tamamlandı: 468 geçti,
yalnız gerçek Linux `systemd-analyze` kontrolü macOS'ta atlandı. Shell
sözdizimi ve Python derleme kontrolleri de geçti. Bu yerel doğrulama GitHub
Actions çalışmasının sonucu olarak sunulmaz.

0.137.0 yeni vaka kanıtı, HTML dosyası, bütünleşik rapor ve geçiş davranışları
35 yeni testle kapsandı. Kaynak sayfasının dışındaki 601. vaka kanıtı,
510 öğelik tam rapor, 52 etkin hedef, tarihî kapsam/önce-sonra ve ortak
vakanın kuruluş ayrımı doğrulandı. Hiçbir kabul internetten veri toplamadı.

0.137.0 gerçek veri kopyasında 62→63 geçişi **133 tablo / 86.843 satırın**
kolon, rowid ve değerlerini; sıra ayırıcılarını birebir korudu. Tek DDL
farkı vaka kanıtı tür kısıtıdır. Benzersiz yedekten yeni konuma şema 62
geri dönüşü ve tekrarlı geçişin değişiklik yapmaması doğrulandı.

Son HTML çıktısı yerel Chrome'da 1440 ve 390 piksel genişliğinde açıldı;
bölüm bağlantıları, kaynak boşlukları, yüzey kanıtları ve tarihî izleme
bölümleri görsel olarak incelendi. Sayfa yatay taşmadı; harici betik,
görsel veya stil dosyası yüklemedi. Örnek kayıtlar kullanıldı.


0.136.0 tam paketi **1.828 test / 597,223 saniye** ile tamamlandı: 1.827 geçti,
yalnız Linux `systemd-analyze` kontrolü macOS'ta atlandı. Testlerin başı ve
sonunda 767 kod/test/script dosyasının özetleri aynıydı. Bu yerel sonuç,
GitHub Actions çalışmasının sonucu olarak sunulmaz.

0.136.0 hızlı kapısı **434 test / 194,914 saniye** ile tamamlandı: 433 geçti,
yalnız gerçek Linux `systemd-analyze` kontrolü macOS'ta atlandı. Shell
sözdizimi ve Python derleme kontrolleri de geçti.

0.136.0 hedefli kabulünde **76 test / 28,285 saniye** geçti: yeni çekirdek,
inbox, CLI ve mevcut kamu kaynak/toplama kanıtı akışı. Ayrı migration paketi
**205 test / 45,859 saniye** ile eski 1–61 sürümlerini, eklemeli şema 62'yi,
geri alma ve yedek/restore yollarını doğruladı. Mimari katman denetimi geçti.

0.136.0 gerçek veri kopyasında 61→62 geçişi **129 eski tablo / 86.843 satırın**
tanımını, kolonlarını, rowid'lerini ve SQLite sıra sayaçlarını aynen korudu.
Dört yeni tablo boş kaldı. Benzersiz geçiş yedeği ayrı dosyaya geri yüklendi;
şema 61 ve bütün eski kayıtlar eşleşti. Ağ engellenerek 16 gerçek CLI çağrısı
çalıştırıldı; yalnız kopyada test kuruluşu/domain bağı/izleme açma-kapatma ve
kuruluş raporu doğrulandı. Asıl dosyanın SHA-256, mtime, inode ve boyutu aynı
kaldı. Bu kabulde canlı HIBP isteği ve gerçek Linux hizmeti çalıştırılmadı.

Tam kontrollerden sonra asıl veritabanı da ortak kilit altında 61→62
yükseltildi. 129 eski tablo / 86.843 satır, eski indeksler ve SQLite sıra
sayaçları korundu. Benzersiz geçiş yedeği ve ayrı dosyaya gerçek geri yükleme
özgün şema 61/veriyle eşleşti. Dört yeni tablo boş başladı; kişisel kuruluş
veya izleme eklenmedi. Veriler, yedekler ve kabul kayıtları Git dışındadır.

0.135.0 tam paketi **1.777 testle 562,841 saniyede** tamamlandı: 1.776 geçti,
yalnız Linux `systemd-analyze` kontrolü macOS üzerinde atlandı. Test boyunca
756 uygulama/test/script dosyasının özetleri değişmedi. GitHub Actions
sonucu bu yerel doğrulamanın sonucu olarak sunulmaz.

0.135.0 hızlı kapısı **383 testle 166,578 saniyede** tamamlandı: 382 geçti,
yalnız Linux `systemd-analyze` kontrolü macOS üzerinde atlandı. Shell
sözdizimi ve Python derleme kontrolleri geçti. Yeni kabul; açık HIBP seçimi,
eski profil özetleri, kaynak hatası, kesinti sonrası korunmuş sonuç, atomik
geri alma, lisans/atıf, ilk katalog ve kuruluş kapsamını birlikte sınar.

0.135.0 gerçek veri kopyasında şema 60→61 geçişi **129 tablonun 86.843
satırını**, eski alanlarını ve rowid'lerini korudu. Yalnız iki toplama
tablosunun tanımı genişledi; eski sonuçlarda yeni HIBP bağı boş kaldı.
Benzersiz geçiş yedeği ayrı dosyaya geri yüklendi ve şema 60/veri eşitliği
doğrulandı. Ağ kapalı gerçek CLI'de durum/geçmiş okumaları, yalnız kopyada
HIBP profili, planı ve zamanlama dosyası üretimi geçti. Kopya kabulü boyunca
asıl veritabanının dosya özeti, boyutu, inode'u ve değiştirilme zamanı aynıydı.
Gerçek Linux hizmeti etkinleştirilmedi; canlı kaynak bu kabulde çağrılmadı.

Tam kontrollerden sonra asıl yerel veritabanı da ortak kilit altında 60→61
yükseltildi. 129 tablo ve 86.843 satırın eski alanları/rowid'leri korundu;
benzersiz geçiş yedeği ve ayrı geçici dosyaya gerçek geri yükleme özgün
şema 60/veriyle eşleşti. Kişisel profil veya kuruluş tanımı eklenmedi;
katalog kendiliğinden indirilmedi. Yedek ve kabul kayıtları Git dışında kaldı.

0.134.0 tam paketi **1.743 testle 509,592 saniyede** tamamlandı: 1.742 geçti,
yalnız Linux `systemd-analyze` kontrolü macOS üzerinde atlandı. Tam paket
çalışırken uygulama/test girdileri değişmedi. Sonraki yedi dosya sonu boş
satır temizliğinin Python sözdizim ağacını değiştirmediği ayrıca doğrulandı.
GitHub üzerindeki CI sonucu bu yerel sonuçla doğrulanmış sayılmaz.

0.134.0 hızlı kapısı **349 testle 131,370 saniyede** tamamlandı: 348 geçti,
yalnız gerçek Linux `systemd-analyze` kontrolü macOS üzerinde atlandı.
Yeni kullanım rehberi/CLI seçenekleri bağımsız olarak karşılaştırıldı;
kapsam ve sayfalama açıklamaları çalışan davranışla eşleşti.

0.134.0 gerçek veri kopyasında şema 59→60 geçişi **127 tablonun 86.843
satırını ve eski tablo tanımlarını aynen korudu**. İki yeni tablo boş
başladı. Otomatik geçiş yedeği yeni dosyaya geri yüklendi; özgün şema 59
ve bütün eski tablo içerikleri eşleşti. Ana veritabanı bu kopya denemesinde
değişmedi. Ağ engelliyken yeni katalog durumu, kuruluş listesi, depolama
hazırlığı ve mevcut bir IOC için CTI bağlamı gerçek CLI üzerinden geçti.
Mevcut Feodo kaynağının kaynak zamanı/ilk görülme aralığı da yeni geçmiş
denetimiyle uyumlu doğrulandı; eski kayıt yeniden yazılmadı.
Ek olarak mevcut MITRE aktör/kampanya/malware kökleri ve CERT Polska IOC
kaydı gerçek CLI'de açıldı. Kaynaklı ilişkiler korundu; ilişkisiz IOC için
yeni bağ uydurulmadı. Ana/kopya dosya özetleri değişmedi.
Yeni ayrı özel kopyada dört açık hedefli bir test kuruluşu oluşturuldu;
kuruluş raporu, yedi günlük değişimler ve kaynak katkısı gerçek eski
kayıtlarla geçti. Kaynak hataları başarılı kanıtlardan ayrı kaldı; raporlar
veritabanını değiştirmedi. Bu test grubu asıl veritabanına eklenmedi.

Tam kontrollerden sonra asıl yerel veritabanı da ortak kilit altında 59→60
yükseltildi. 127 eski tablo/86.843 satır korundu; benzersiz geçiş yedeği ve
ayrı geçici dosyaya geri yükleme eski verilerle eşleşti. Yeni katalog tabloları
boş başladı; kendiliğinden kaynak yenilemesi veya üyelik oluşturulmadı.

Yeni kaynağın ayrı canlı kabulünde 1.052 kamu metadata kaydı alındı;
anahtarsız erişim, gerçek geçici SQLite ve çevrimdışı domain araması
[kaynak kabul notunda](PUBLIC_NOTICE_SOURCE_ACCEPTANCE.md) kayıtlıdır.
Kuruluş raporu/geçiş testleri canlı hedef veya saldırı çalıştırmaz.

0.133.0 tam paketi **1.649 testle 456,994 saniyede** tamamlandı: 1.648 test
geçti, yalnız Linux `systemd-analyze` testi bu macOS ortamında atlandı.
Kabuk sözdizimi, Python derleme ve mimari sınır kontrolü geçti. Test boyunca
uygulama/test girdileri değiştirilmedi. GitHub üzerindeki CI sonucu bu
yerel kontrolün yerine doğrulanmış sayılmaz.

Gerçek veritabanı kopyasında şema 56→59 geçişi 117 eski tablonun bütün
satırlarını korudu; 10 yeni tablo boş başladı. Geri dönüş yedeği ve ayrı
dosyaya kurtarma eşleşti. Aynı kopyadaki 18 CLI komutu geçti; 15 salt okunur
komutta veritabanı dosya özeti değişmedi. Kabul profili, plan, zamanlama
dosyası, doğrulanmış bakım yedeği ve CLI restore sınandı. Hiçbir ağ veya
sistem hizmeti çağrısı yapılmadı; Linux hizmeti etkinleştirilmedi.

0.133.0 için ana proje üzerinde kuruluş/dönem raporu grubu 49,
ATT&CK/kaynak katkısı/RansomLook bildirim grubu 46 odaklı testle doğrulandı.
Ek çapraz özellik kabulü gerçek geçici şema 59 veritabanında 1 testle
12,945 saniyede geçti: profil ve kuruluş bağlantıları, başlangıç toplaması,
insan incelemesi, kaynak hatası, tek RansomLook bildirimi, yalnız eksik işi
yeniden deneme ve aynı kanıtın rapor/kataloglarda görünmesi birlikte sınandı.
Kaynaklar test verisidir; gerçek ağ ve hedef bağlantısı kapalıdır. Salt okunur
komutlarda dosyaların ve sağlayıcı çağrı sayılarının değişmediği doğrulandı.
Bu odaklı sayılar yukarıdaki tam regresyona ek kanıttır; canlı kaynak veya
Linux hizmet çalıştırma kabulü iddiası değildir.

0.130.0 hızlı kapısı 198/198 testle 45,114 saniyede; son tam regresyonu
1.476/1.476 testle 556,986 saniyede geçti. Yeni testler
gerçek geçici SQLite üzerinde açık kimlik seçimini, ağ öncesi ve kilit içi
ön doğrulamayı, kaynak başına tek yenilemeyi, tam kaynak kimliği bağını,
kesintide eski snapshot'ı çalıştırmamayı, başlangıç/fark ayrımını, insan
kararlarının korunmasını ve terminal/JSON görünüm sınırlarını sınar.
Kaynak çağrıları testlerde sahtedir; doğrudan hedef ve gerçek ağ kapalıdır.

İlk tam koşuda 1.476 testten ikisi yalnız süreç kilidi test yardımcısının
5 saniyede hazır sinyali verememesi nedeniyle başarısız oldu. Aynı dokuz
kilit testi tek başına 0,479 saniyede geçti; yeni alt süreç 0,127 saniyede
başladı. Yüksek sistem yükü de ölçüldü; yeni testlerde kalan patch/ortam
değişikliği veya import zinciri farkı bulunmadı. Testin sınırlı başlangıç/
temizlik beklemesi 30 saniye yapıldı; ürün kilidi kodu değiştirilmedi.
Değişiklik sonrası dokuz kilit testi 0,106 saniyede ve ardından tam paket
1.476/1.476 testle geçti.

14 Kasım 2026 yerel kabulü: kayıtlı domainin varsayılan üç işi ile açık
seçilen iki sosyal, iki ThreatCluster ve bir RansomLook izlemesi önizlendi.
İki ThreatCluster izlemesi tek yenileme görevi altında gruplandı; toplam
yedi görev, beş izleme hedefi ve doğru Maigret/Sherlock kaynakları gösterildi.
Gerçek terminal ve JSON önizlemesinde ağ bağlantısı engellendi; veritabanı
SHA-256 özeti değişmedi. Bu kabul canlı kaynak taraması değildir; bu sürümde
gerçek kaynak yenilemesi veya kişisel izleme çalışması başlatılmadı.
Kabul çıktıları ve kişisel tanımlar Git dışındaki yerel veri alanında kalır.

0.129.1 hızlı kapısı 172/172 testle 33,650 saniyede; tam regresyonu
1.450/1.450 testle 290,234 saniyede geçti. Yeni testler
Common Crawl yanıtı bittikten sonraki aralığı, 60 saniyelik bağlantı tekrarı,
yetersiz süre/istek hakkı durumunda asıl hata nedenini ve Wayback ayrımını
doğrular. Gerçek taşıma + sahte saatli 13 indeks testi eski 90 saniyenin
12. sorguda tükendiğini; yeni bütçede 104 saniyede tamamlandığını ve
Wayback'in bağımsız bütçesinin korunduğunu gösterir.

13 Kasım 2026, 0.129.1 erişim tanısı: katalog kod değişmeden HTTP 200 döndü.
Eski bütçeyle gerçek taşıma katalog ve 11 indeksi okudu, sonraki sorguda
90 saniye tükendi. Yeni bütçeyle ilk normal CLI kabulünde Common Crawl
yaklaşık 54 saniye sonra HTTP 504 ile kısmi kaldı; Wayback yaklaşık 17
saniyede tamamlandı. Ayrı sınırlı tanıda katalog yine HTTP 200 iken ilk
indeks 504, tek tekrarı 502 verdi. Bu sonuçlar yalnız uygulama süresinin
artırılmasının sağlayıcı hatasını ortadan kaldırmadığını gösterir. İlk
bağlantı kapanmasının kesin nedeni veya IP engeli kanıtlanmış değildir.

Birkaç dakika ara verilen son normal CLI denemesinde Common Crawl yaklaşık
25 saniyede HTTP 504 nedeniyle başarısız, Wayback yaklaşık 11 saniyede
tamamlandı. Genel sonuç kısmi olarak kayıtlıdır; yeni aday oluşmadı.
Katalog erişimi geri gelmiş ve uygulamadaki süre/aralık hataları düzelmiş
olsa da Common Crawl'ın tam canlı kapsam kabulü hâlâ açıktır. Sağlayıcıdan
gelen 502/504 hataları yerel kodla ortadan kaldırılmış gibi sunulmaz.

İşlem öncesi ve sonrası tutarlı yedek alındı. Son kaynak sağlığı, aday
listesi, kaynak durumu ve doctor okumalarının tümü başarılı; veritabanı
SHA-256 özeti bu okumalar boyunca değişmedi. Şema 54 korunur. Kişisel
hedef, ham tanı ve kabul çıktıları Git dışındaki yerel veri alanında kalır.

0.129.0 hızlı kapısı 165/165 testle 33,663 saniyede; tam regresyonu
1.443/1.443 testle 280,563 saniyede geçti. Son terminal açıklaması
düzeltmesinden sonra 9 CLI bütünleşme testi 8,159 saniyede yeniden geçti.
Yeni 24 test seçim/ön doğrulama, tek kilit, bağımsız kaynak hataları,
depolama/kullanıcı kesintisi, kalıcı kaynak kimlikleri, tekrar ve insan kararı
korunumu, kaynak listesi–hedef bulgusu ayrımı ve JSON/terminal sonuçlarını
ağsız geçici veride doğruladı. Mimari bağımlılık denetimi de geçti.

13 Kasım 2026, 0.129.0 canlı kabulü: kayıtlı tek domain için iki marka
araması, crt.sh alt alan adı keşfi ve iki IOC yenilemesi aynı `collect`
çağrısında yaklaşık 12,6 saniyede tamamlandı. Beş adım ayrı kimlik/durumla
çıktıda korundu; genel sonuç `complete` ve çıkış kodu 0 oldu. Yeni marka
bulgusu veya pasif aday oluşmadı; önceki tek alt alan adı adayı korundu.
Feodo listesi 5 IP, CERT Polska listesi 19.596 domain içeriyordu; bu sayılar
hedefin bulgu sayısı değildir. Son birleşik analizde IOC eşleşmesi yoktu.
İsteğe bağlı theHarvester bu kabulde çalıştırılmadı; önceki Common Crawl
erişim sorunu çözülmüş sayılmadı.

Beş adımlı `--plan` öncesi/sonrası veritabanı özeti aynı kaldı. Canlı toplama
öncesi/sonrası yedek alındı; sonraki kaynak durumu, doctor ve analiz okumaları
da veritabanını değiştirmedi. Şema 54 değişmedi; kabul çıktıları ve kişisel
domain bilgileri Git dışında tutuldu. Tekrar/karar korunumu, kesinti ve
kısmi/tam kaynak hataları geçici verili otomatik testlerle ayrıca sınandı.

0.128.0 hızlı kapısı 141/141 testle 27,917 saniyede, tam regresyonu
1.419/1.419 testle 283,685 saniyede geçti. Yeni testler bağlantı/TLS/HTTP
hatasını başarılı boş yanıttan ayırmayı, gecikmeli tekrar ve kota davranışını,
yanıt/süre/istek sınırlarını, kayıpsız sayfalamayı, bağımsız kaynak bütçelerini
ve checkout dışından paket kurulumunu ağsız sınadı.

13 Kasım 2026, 0.128.0 canlı kabulü: aynı kayıtlı kökte iki ayrı arşiv
denemesinde Wayback sorgusu tamamlandı; alt alan adı adayı dönmedi. İlk
deneme uygulama geçmişine kısmi olarak kaydedildi; ikinci denemede işçinin
kaynak özeti ayrıca saklandı ve Wayback yaklaşık 23 saniyede tamamlandı.
Common Crawl iki denemede de HTTP yanıtı gelmeden bağlantıyı kapattı
(`connection-closed`). Bu kaynak için başarılı canlı kapsam hâlâ
doğrulanmadı; bozuk katalog veya kesin IP engeli iddiası yapılmıyor.
Genel sonuç bu nedenle başarılı boş değil, kısmi kaldı. İki kaynağın da
çözüldüğü veya gelecekte kesintisiz çalışacağı iddia edilmez.

Standart paket kurulumu gerçek ayrı ortamda tekrar çalıştırıldı ve checkout
dışındaki import/CLI kontrolü geçti. Mevcut crt.sh adayı ve kanıtları korundu;
arşivden yeni aday oluşmadı. Kaynak durumu, keşif sağlığı, aday listesi ve
doctor okumaları öncesi/sonrası veritabanı SHA-256 özeti aynı kaldı. İşlem
öncesi/sonrası yedek alındı; şema 54 değişmedi. Tanı yanıtları, kişisel hedef
ve kabul kayıtları Git dışında yerel veri alanında tutuldu.

0.127.1 hızlı kapısı 104/104 testle 26,181 saniyede, tam regresyonu
1.382/1.382 testle 294,154 saniyede geçti. Yeni testler proje içi/PATH uv
seçimini, göreli ve boşluk içeren yolları, açık dizin ayarlarını, eksik araçta
yazmadan durmayı ve iki arşivin sınırlı/doğrulanmış hata nedenlerini sınadı.
Otomatik testler gerçek interneti veya kişisel veri alanını kullanmadı.

13 Kasım 2026, 0.127.1 canlı kullanım kabulü: resmî MITRE ATT&CK Enterprise
v20.0 dosyasındaki 26.690 nesneden desteklenen 982 varlık ve 809 ilişki kişisel
kayıt alanına alındı. İkinci senkronda hepsi değişmeyen olarak sayıldı; yeni,
güncellenen veya geri çekilen kayıt oluşmadı. APT29 araması, varlık ayrıntısı
ve kaynaklı ilişkileri yerel komutlardan açıldı. Bu araştırma kataloğu varlığa
yönelik saldırı veya otomatik aktör atfı değildir.

theHarvester'ın incelenmiş commit'i ayrı Python 3.14.10 ortamında kuruldu;
yerel yardımcı uv 0.13.8 ve kilitli 41 paket kullanıldı. Düzeltmeden sonra
yalnız `./scripts/setup-harvester` ile kurulum yeniden doğrulandı. Arşiv keşfi
ise iki tam denemede başarısız kaldı; son kayıtta Common Crawl
`invalid-catalog`, Wayback `runtime-limit` nedenleri ayrı korundu. Ayrı dar
tanı isteğinde Common Crawl yanıt gelmeden bağlantıyı kapattı; tek satırlık
Wayback sorgusu boş JSON döndü. Dar isteğin başarısı tam arşiv çalışmasının
başarısı sayılmadı. Önceki crt.sh adayı/kanıtları korundu; bu denemede yeni
arşiv kapsamı veya tekilleştirilmiş canlı başarılı tekrar kanıtlanmış değildir.
Başarılı/kısmi/başarısız ayrımı ve tekrar sözleşmesi ağsız testlerde sınanır.

Kurulum ve arşiv tanı kayıtları, kişisel varlık bilgileri ve alınan MITRE
verisi Git dışında yerel alanda kaldı. CTI/aday/durum/doctor okumalarının
öncesinde ve sonrasında veritabanı SHA-256 özeti aynı kaldı; işlem öncesi ve
sonrası yedek alındı. Uygulama şeması 54 değişmedi.

13 Kasım 2026 ek canlı kullanım kabulü: mevcut Feodo, CERT Polska,
ThreatCluster ve RansomLook adaptörleri kişisel kayıt alanında güncellendi.
O andaki listelerde sırasıyla 5 IP, 19.623 domain, 1.295 ve 329 kaynak iddiası
bulunuyordu; bunlar izlenen varlığın bulgu sayıları değildir. İkinci başarılı
indirmede dört kaynakta da yeni/değişen/çıkan kayıt sıfırdı. Kaynak geçmişi,
domain IOC analizi, ThreatCluster domain/ad izlemesi ve RansomLook ad
izlemesinin ilk/tekrar sonuçları doğrulandı. Kayıtlı IP kanıtı bulunmadığından
bu deneme varlığın IP IOC karşılaştırmasını veya aktif yüzeyini doğrulamaz.

İlk kısıtlı ağ denemesinin başarısız kaydı geçmişte korundu; izinli ağ
denemesiyle Feodo başarıya geçti. Kaynak durumu kalan iki eksik bölümü
(theHarvester kurulumu ve bu kişisel alanda ATT&CK senkronu) ayrı gösterdi.
Salt okunur analiz/durum/doctor/izleme görüntüleme öncesi ve sonrası veritabanı
SHA-256 özeti aynı kaldı. Önce/sonra yedek alındı; kabul kayıtları ve izleme
kimlikleri yalnız Git dışında tutulan yerel veri alanına kaydedildi.

Bu kullanım kabulünde mevcut beş test modülündeki 30/30 hedefli test 5,642
saniyede geçti: `test_cti_feeds`, `test_certpl_warning`,
`test_ransomware_history`, `test_ransomlook_history`,
`test_source_readiness_adapter`. Bunlar ağsız/geçici veride hata korumasını,
boş başarıyı, tekrarı, kaynak ayrımını ve yedek/geri yüklemeyi sınadı.
Uygulama kodu, şema ve sürüm değişmedi; [günlük kullanım rehberine](DAILY_USE.md)
ücretsiz beslemelerin yenileme ve izleme adımları eklendi. Kaynakların gelecekte
erişilebilirliği ve daha geniş kapsamı bu tek denemeyle garanti edilmez.

0.127.0 kısa kapısı 84/84, tam regresyonu 1.374/1.374 testle 294,923
saniyede geçti. Yeni testler aynı domain/izleme kapsamındaki önceki başarıyı,
kurulum metadata/commit/katalog denetimini, eksik/bozuk kayıtları, beklemeyi,
zaman sınırlarını, önerilen komutların ayrıştırılmasını ve günlük vaka/tekrar
zincirini doğruladı. Otomatik testler ağsız geçici veride çalıştı. Ayrı gerçek
kullanım denemesinde pasif toplama ve iki sosyal kaynak tekrarı çalıştırıldı;
kanıtların tamamı yalnız yerel veri alanında tutuldu ve yedeklendi.

0.126.0 hedefli testler aktif kabul kapısı ile çalışma zamanı sağlayıcılarının
birebir eşleşmesini; Subfinder'ın katı makine sözleşmesi, kaynak sonucu ayrımı
ve bağımsız kapsam kapılarında ertelenmesini; theHarvester kanıtının depolama ve
terminal ayrıntısından okunmasını; aynı kökte crt.sh başarısı ile theHarvester
hatasının ayrı görünmesini; sağlayıcı filtresi ile birleşik sağlık görünümünün
ağsız, salt okunur çalışmasını doğruladı. Kısa kapıda 65/65, tam regresyonda
1.355/1.355 test 275,634 saniyede geçti. Otomatik testler gerçek internete ve
kullanıcı veri klasörüne dokunmadı; şema 54 değişmedi.

0.125.0 testleri `safe`/`extended`/özel platform çözümünü, iki kaynağın
30/26 öğelik izinli kapsamını, profil-site çakışmasını, terminal/JSON profil
görünümünü, kalıcı izlemede çözülmüş listenin korunmasını, kaynak ve HTTPS host
ayrımını; varsayılan/çekirdek-only kurulum sırasını ve başarısız yeniden
kurulumda önceki `.venv` ortamının geri getirilmesini doğruladı. CI ayrımı için
eklenen dört yapılandırma testi her gönderimdeki 54 testlik kısa kapıyı, dosya
değişimine bağlı temiz marka kurulumunu ve yalnız tam kontrolden sonra sürüm
oluşturulmasını sabitler. Son tam kontrolde 1.349 otomatik test 269,142 saniyede
geçti. Ayrı gerçek temiz kurulumda önce ağ
kısıtı nedeniyle başarısız indirme eski ortamı geri getirdi; resmî PyPI/GitHub
erişimiyle ikinci deneme tam sabit bağımlılıkları kurdu, `pip check`, sürüm,
commit, katalog özeti ve iki geniş geçici katalog denetimlerini geçti. Canlı
kullanıcı adı sorgusu veya veritabanı şema değişikliği yapılmadı; şema 54 kaldı.

0.124.1 testleri temiz klonda bağımlılıksız `./setup` başlangıcını, tekrar
çalıştırmayı, özel veri klasörünü ve sonrasındaki `doctor` bütünlük kontrolünü
doğruladı. Takvime bağlı iki ransomware CLI fixture'ı, 48 saat sonra kendiliğinden
bozulmayacak güncel üretim zamanı kullanacak biçimde düzeltildi. Tam kontrolde
1.340 otomatik test 241,253 saniyede geçti; testlerde internet ve kullanıcı
veritabanı kullanılmadı. Ayrı yerel kabulte mevcut şema 39 kayıt alanı açık
`migrate` ile şema 54'e taşındı; önce doğrulanmış `pre-v54` kurtarma yedeği
alındı ve 12 kayıtlı adres ile mevcut kanıtlar korundu.

0.124.0 testleri vaka oluşturma/güncelleme/durum yaşam döngüsünü; not, görev, açık görevli kapanış kapısı, sonuçlu kapatma ve yeniden açmayı; domain/marka bulgusu, insan kararlı sosyal profil, iki ayrı ransomware kaynağı ve tedarikçi inceleme kartının dondurulmuş kanıt bağını; tekrar/yenileme/çıkarma davranışını; bozuk kanıt ve güncel durum–zaman çizelgesi uyuşmazlığında güvenli durmayı; yedek–geri yüklemeyi; ağsız terminal/JSON raporunu; `doctor` sayaçlarını ve veri içeren şema 53→54 yedekli migration/rollback yolunu doğruladı. Tam kontrolde 1.339 otomatik test 269,666 saniyede geçti; testlerde internet ve kullanıcı veritabanı kullanılmadı. Ayrı geçici terminal kabulünde açık görev kapanışı engelledi, görev tamamlanınca vaka sonuçla kapandı, rapor 5 aktiviteyi gösterdi ve şema 54 doğrulandı. `.xti-data/xti.db` dosyası aynı değiştirilme zamanı, 1.454.080 bayt boyut ve şema 39 ile değişmeden kaldı.

0.96.0 testleri ilk snapshot, yeni/değişen/aynı/pencereden çıkan ayrımı, kaynak hatasında son başarılı snapshot'ın korunması, ham `.onion` adresinin kalıcı kayda girmemesi, bozuk öğe özetinde güvenli durma, ağsız durum görünümü ve şema 39→40 yedekli geçişini doğruladı. Tam kontrolde 1.137 otomatik test 171,591 saniyede geçti. Ayrı geçici canlı kabulde ilk snapshot 1.093 güvenli kayıtla başlangıç çizgisi oluşturdu; hemen sonraki snapshot 1.093 kaydı değişmemiş saydı ve sıfır yeni/değişen/çıkan ya da yinelenen öğe satırı yazdı. Kullanıcının ana veritabanına dokunulmadı.

0.97.0 testleri kuruluş tam/içerme, domain kök/alt alan adı eşleşmesi, sessiz ilk çalışma, tanım değişiminde yeni sessiz başlangıç, sonraki yeni/değişen eşleşmenin ortak kutuya girmesi, yalnız kaynak penceresinden çıkışın bildirim üretmemesi, bozuk bildirim bağlantısında güvenli durma ve şema 40→41 yedekli geçişini doğruladı. Tam kontrolde 1.145 otomatik test 179,824 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı ve kullanıcı veritabanına dokunulmadı.

0.98.0 testleri tek kaynak alımı, etkin izlemelerin kararlı sırası, geri çekilmiş tanımın atlanması, ikinci yenilemede yalnız anlamlı değişimin bildirilmesi, kaynak hatasında eski snapshot üzerinde çalışma yapılmaması, sınır aşımının ağ/yazma öncesi reddi, beklenen kaynak kimliğinin yazma öncesi doğrulanması, sonraki izleme hatasında önceki atomik kayıtların korunması ve terminal JSON sözleşmesini doğruladı. Şema 41 değişmedi. Tam kontrolde 1.155 otomatik test 170,557 saniyede geçti; otomatik testlerde gerçek ağ ve kullanıcı veritabanı kullanılmadı. Ayrı geçici canlı kabul güncel açık snapshot'taki 1.091 kaydı doğruladı; tek etkin eşleşmesiz izlemeyi aynı kaynak çalışma kimliğiyle sessiz başlangıç olarak tamamladı ve bildirim üretmedi.

0.99.0 testleri iki tur ve sonraki anlamlı değişim bildirimi, başarısız kaynak turundan sonra devam, süre sınırı, beklemede `Ctrl+C`, bozuk monoton saat, etkin izleme sınır aşımı, sessiz başlangıç/tekrarlı tur toplamı ayrımı, tek-tur terminal JSON sonucu ve kaynak hatası çıkışını doğruladı. Şema 41 değişmedi. Tam kontrolde 1.163 otomatik test 169,552 saniyede geçti; otomatik testlerde gerçek ağ ve kullanıcı veritabanı kullanılmadı. Ayrı geçici canlı kabul `watch-monitor --cycles 1` ile güncel 1.091 kayıtlı snapshot'ı aldı, tek etkin izlemeyi aynı kaynak kimliğiyle sessiz başlangıç olarak tamamladı ve sıfır bildirim üretti.

0.100.0 testleri tam ve kısmi oturum bitişini, `Ctrl+C` ile kesilmeyi, beklenmeyen hata durumunu, ani kapanma sonrası açık kaydın tamamlanmış sayılmamasını, bozuk oturumun güvenli reddini, ağsız terminal/JSON liste ve ayrıntıyı, şema 41→42 yedekli migration/rollback'i ve aynı snapshot üzerinde sonradan yapılan bağımsız izlemenin önceki tur özetini değiştirmemesini doğruladı. Şema 42 üç boş monitor tablosunu ekler; eski geçmişten oturum uydurmaz. Tam kontrolde 1.172 otomatik test 191,700 saniyede geçti. Ayrı geçici canlı kabul güncel 1.091 kayıtlı snapshot üzerinde tek oturum/tur ve aynı kaynak kimliğine bağlı tek sessiz izleme çalışmasını sakladı; ağsız liste/ayrıntı ile oturum, tur ve tur–izleme sayaçları doğrulandı. Kullanıcı veritabanı değiştirilmedi ve geçici alan kaldırıldı.

0.101.0 testleri güncel izleme tanımının bütün kayıtlı snapshot geçmişine uygulanmasını; ilk eşleşme, güncelleme, eşleşme başlangıcı/bitişi, çıkarılma ve aynı kimliğin yeniden görünmesini; değişmeyen kesin tekrarın olay değil sayaç olmasını; başarısız kaynak çalışmasının durumu değiştirmemesini; olay görünüm sınırının tam toplamları etkilememesini; geri çekilmiş izlemeyi; ağsız terminal/JSON görünümünü ve semantik olarak değiştirilmiş çıkarma kanıtında güvenli durmayı doğruladı. Şema 42 değişmedi. Tam kontrolde 1.177 otomatik test 184,545 saniyede geçti; kullanıcı veritabanı ve internet kullanılmadı.

0.102.0 testleri yalnız keşif zamanı değişen kimliği; kuruluş adı ve keşif zamanı birlikte değişirken grup+web alanının ortak kalmasını; eski veya yeni tarafın izlemeyle ilgisini; zayıf benzerlik, eşzamanlı ayrı kayıt, kesin kimliğin geri gelişi ve uzak snapshot geçişinin elenmesini; aradaki kaynak hatasının boş snapshot sayılmamasını; görünüm sınırının tam toplamı değiştirmemesini; geri çekilmiş izlemeyi ve ağsız terminal/JSON görünümünü doğruladı. Şema 42 değişmedi. Tam kontrolde 1.183 otomatik test 188,280 saniyede geçti; kullanıcı veritabanı ve internet kullanılmadı.

0.103.0 testleri ilk insan kararını, aynı karar+gerekçenin idempotent kalmasını, karar değişikliğinde önceki olaya bağlı eklemeli zinciri, karar sonrasında kaynak kimlikleri ve zaman çizelgesinin ayrı kalmasını, son kararın aday listesine taşınmasını, ağsız terminal/JSON görünümünü, yazma kilidini, bozuk zincir veya aday özetinde güvenli durmayı, yedek–geri yüklemeyi ve şema 42→43 yedekli migration/rollback'i doğruladı. `doctor` ayrı aday ve karar olayı sayılarını gösterir. Tam kontrolde 1.193 otomatik test 187,893 saniyede geçti; kullanıcı veritabanı ve internet kullanılmadı.

0.104.0 testleri sürümlü kaynak kabul kapısını, RansomLook'un asgari alan ayrıştırmasını ve güvenli boşluk normalleştirmesini; şema kayması, yinelenen alan/kayıt, bozuk zaman/kontrol karakteri ve boyut aşımında tüm sonucun reddini; sabit yönlendirmesiz taşıma sınırlarını, hata ayrıntısı sızdırmamayı, yerel arama/limiti, kaynak kataloğunu ve veritabanı oluşturmayan terminal/JSON önizlemesini doğruladı. RansomLook'ta desteklenmeyen `listed/delisted` filtresi ağdan önce reddedilir. Şema 43 değişmedi ve yeni migration gerekmez. Tam kontrolde 1.199 otomatik test 205,146 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı. Ayrı geçici canlı kabul 266 güncel kaydı doğruladı, üç sınırlı kayıt gösterdi ve veri dizini oluşturmadı; kullanıcı veritabanına dokunulmadı.

0.105.0 testleri ilk RansomLook başlangıç çizgisini; yeni, aynı ve pencereden çıkan kayıt ayrımını; değişmeyen öğelerin tekrar yazılmamasını; kaynak hatasında son başarılı snapshot'ın korunmasını; bozuk özet/geçmişte güvenli durmayı; yedek–geri yüklemeyi; ThreatCluster kaynak izolasyonunu; ağsız durum görünümünü ve şema 43→44 yedekli migration/rollback'ini doğruladı. Tam kontrolde 1.206 otomatik test 213,599 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı.

0.106.0 testleri RansomLook kuruluş başlığı için sessiz ilk çalışmayı, sonraki yeni eşleşmenin dikkat adayı olmasını, yalnız pencereden çıkışın dikkat üretmemesini, tanım değişiminde yeni başlangıç çizgisini, geri çekilen izlemenin çalıştırılamamasını, ThreatCluster izlemelerinden tam kaynak ayrımını, domain türünün yazma öncesi reddini, bozuk kayıtta güvenli durmayı, yedek–geri yüklemeyi ve şema 44→45 yedekli migration/rollback'ini doğruladı. Tam kontrolde 1.213 otomatik test 228,078 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı.

0.107.0 testleri kuruluş+grup+zaman, kuruluş+grup ve kuruluş+zaman eşleşmelerini; yalnız kuruluş ile yalnız grup/zaman çiftlerinin elenmesini; normalleştirilmiş tam metni, kararlı kimlik ve sırayı, iki özgün kaydın JSON/terminal sonucunda korunmasını, görünüm sınırının toplamı değiştirmemesini, eksik snapshot yönlendirmesini, geçersiz girdinin depolama öncesi reddini, ağsız ve salt-okunur çalışmayı, bozuk iki kaynak geçmişinde güvenli durmayı ve kaynak kataloğunu doğruladı. Şema 45 değişmedi. Tam kontrolde 1.218 otomatik test 255,541 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı.

0.108.0 testleri ilk kaynaklar arası insan kararını, aynı karar+gerekçenin idempotent kalmasını, değişiklikte önceki olaya bağlı eklemeli zinciri, ilk karar kanıtının yeni kaynak snapshot'ları sonrasında değişmemesini, iki özgün kaynak modelinin ayrı kalmasını, ağsız terminal/JSON akışını, `source-compare` görünümünün salt okunur kalmasını, bozuk olay bağı veya kanıt hash'inde güvenli durmayı, yedek–geri yüklemeyi, kaynak kataloğunu ve şema 45→46 yedekli migration/rollback'ini doğruladı. Tam kontrolde 1.227 otomatik test 213,476 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı.

0.109.0 testleri tek seçilen Maigret adaptörü kararını, bütün adayların resmî bağlantı ve engellerini, Holehe hesap-kurtarma reddini, ağsız terminal/JSON çıktısını ve var olmayan veri klasörünün oluşturulmamasını doğruladı. Şema 46 değişmedi ve migration gerekmez. Tam kontrolde 1.229 otomatik test 205,689 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı.

0.110.0 testleri kullanıcı adı/platform/süre doğrulamasını; sabit Maigret sürümü ve güvenli komut bayraklarını; sanal ortam yürütücü bulmayı; upstream site veritabanı hash'ini, seçili-platform daraltmasını ve dış host reddini; katı NDJSON şema/URL/tekrar/boyut kontrolünü; ham profil alanlarının atılmasını; zaman aşımı ve eksik/yanlış kurulum hatalarını; yazmasız terminal/JSON çıktısını doğruladı. Şema 46 değişmedi ve migration gerekmez. Canlı kabul yalnız GitHub'daki herkese açık `octocat` hesabını buldu; XTI veri klasörü oluşturulmadı. Tam kontrolde 1.237 otomatik test 197,153 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı.

0.111.0 testleri sessiz başlangıcı; yeni bulunan, profil adresi değişen, artık raporlanmayan ve değişmeyen platform ayrımlarını; kaynak hatasının son başarılı ölçümü bozmamasını; tanım değişiminde yeni başlangıcı; geri çekmeyi; atomik kaynak sonucu doğrulamasını; bozuk geçmişte güvenli durmayı; terminal/JSON akışını; doctor sayaçlarını ve şema 46→47 yedekli migration/rollback'ini doğruladı. Tam kontrolde 1.246 otomatik test 207,988 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı. Geçici canlı kabulte GitHub `octocat` profili ilk turda sessiz başlangıç, ikinci turda değişmeyen bulgu olarak kaydedildi. Kullanıcının ana veritabanına dokunulmadı.

0.112.0 testleri ilk profil kararını, aynı karar+gerekçenin idempotent kalmasını, karar değişikliğinin eklemeli zincirini, profil adresi değişince eski kararın taşınmamasını, kaynak hatasında son başarılı adayın korunmasını, raporlanmayan platform ve çalıştırılmamış yeni tanımın reddini, bozuk dondurulmuş kanıtta güvenli durmayı, terminal/JSON görünümünü, doctor sayaçlarını ve şema 47→48 yedekli migration/rollback'ini doğruladı. Tam kontrolde 1.254 otomatik test 231,941 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı. Geçici canlı kabulte önceki GitHub `octocat` kanıtı yedekli olarak şema 48'e taşındı, `known_official` kararı tam profil durumuna bağlandı ve eski çalışma görünümünde gösterildi. Kullanıcının ana veritabanına dokunulmadı.

0.113.0 testleri yalnız olası taklit kararının kutuya girmesini; karar+bildirimin atomik yazılmasını; aynı profil tekrarında tekilleştirmeyi; adres değişince ayrı bildirimi; tetikleyen karar kanıtının sonraki resmî kararda korunmasını; güncel kararın ayrıca gösterilmesini; okundu durumunun kararı değiştirmemesini; bozuk bildirim–karar bağında güvenli durmayı; terminal/JSON, ortak sayaç ve mevcut webhook uyumluluğunu; şema 48→49 yedekli migration/rollback'ini ve eski kararlardan bildirim uydurulmamasını doğruladı. Tam kontrolde 1.262 otomatik test 211,585 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı. Geçici canlı kabulte GitHub `octocat` kararı olası taklit olarak güncellendi, tek bildirim ortak kutuda tam profil ve gerekçeyle gösterildi. Kullanıcının ana veritabanına dokunulmadı.

0.114.0 testleri etkin izlemelerin sabit ad/kimlik sırasını, geri çekilmiş izlemenin dışlanmasını, boş kapsamı, sınır taşmasında kaynak ve yazı öncesi durmayı, geçersiz adet/süre sınırlarını, kaynak hatasını kaydedip sonraki izlemeye devam etmeyi, depolama hatasında tamamlanan önceki kanıtı koruyup sonraki işi başlatmamayı, terminal/JSON özetini ve kaynak hatasının çıkış kodu 3/`ok:false` ayrımını doğruladı. Şema 49 değişmedi ve migration gerekmez. Tam kontrolde 1.269 otomatik test 210,699 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı. Geçici canlı kabulte tek etkin GitHub `octocat` izlemesi toplu komutla ayrı çalışma olarak kaydedildi. Kaynak bu turda profili raporlamadı; sonuç hesap yokluğu veya kaldırılma hükmü yerine açık “artık raporlanmayan” farkı olarak korundu. Kullanıcının ana veritabanına dokunulmadı.

0.115.0 testleri iki tur arasındaki profil değişimini, kaynak hatasından sonra yeni turu, süre bütçesi dolduğunda yeni turun engellenmesini, `Ctrl+C` sırasında tamamlanan kanıtın korunmasını, etkin olmayan tanımı, geçersiz sınırları, bozuk monoton saati ve terminal/JSON çıkış kodlarını doğruladı. Her tur mevcut atomik tekil çalışma yolunu kullanır; şema 49 değişmedi ve migration gerekmez. Tam kontrolde 1.276 otomatik test 221,261 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı. Geçici canlı kabulte etkin GitHub `octocat` izlemesi monitor komutuyla tek tur çalıştı, kaynak hatası olmadan ayrı çalışma kimliği oluşturdu. Kaynak bu turda profil bildirmedi; sıfır bulgu hesap yokluğu hükmüne dönüştürülmedi. Kullanıcının ana veritabanına dokunulmadı.

0.116.0 testleri sabit katalog kanıtının bütünlük ve sayaç bağlarını, zorunlu/isteğe bağlı ölçüt ayrımını, güvenli HTTPS başvurularını, yinelenen JSON alanı reddini ve ağsız terminal/JSON görünümünü doğruladı. Şema 49 değişmedi; otomatik testlerde araç kurulumu, canlı kullanıcı adı sorgusu, internet ve kullanıcı veritabanı kullanılmadı. Tam kontrolde 1.280 otomatik test 228,006 saniyede geçti. Ayrı upstream kabulünde Sherlock v0.16.2 etiketi tam commit'e çözüldü, resmî 104.039 baytlık katalog beklenen SHA-256 özetiyle geçici alanda doğrulandı ve ağsız komut 352 ortak, 103 eşleşmeyen tanım ile 101 eşleşmeyen kayıt kökünü gösterdi. Kullanıcının ana veritabanına dokunulmadı.

0.117.0 testleri Sherlock kullanıcı adı/platform/süre doğrulamasını; sabit paket sürümü ve tam katalog özetini; sekiz platformluk geçici katalog daraltmasını; HTTPS/443 host sınırını; CLI yerine yalıtılmış kütüphane işçisini; güvenli ortamı; dört alanlı katı NDJSON şemasını; eksik, tekrarlı, bozuk ve büyük sonuç reddini; zaman aşımı ile eksik/yanlış kurulumu; yazmasız terminal/JSON yolunu ve düzeltilmiş kapsam kanıtını doğruladı. Şema 49 değişmedi. Tam kontrolde 1.288 otomatik test 240,279 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı. Ayrı canlı kabulde yalnız Carrd seçilerek upstream katalog örneği `blue`, `https://blue.carrd.co/` adresinde “bulundu, doğrulanmadı” olarak döndü. Geçici veri yolu oluşmadı; kullanıcının `.xti-data` veritabanı aynı zaman, boyut ve şema 39 ile değişmeden kaldı.

0.123.0 testleri iş önemini, kabul edilmiş güncel CNAME bağını, iki kaynaklı iddia adayını, aynı-ad belirsizliğini, eksik kaynak ile başarılı boş snapshot ayrımını ve önerilen insan adımlarını tek açıklanabilir kartta doğruladı. Pasif tedarikçi dışlama, geçersiz girdi reddi ve ağsız salt-okunur terminal/JSON yolları ayrıca sınandı. Şema 53 değişmedi. Tam kontrolde 1.329 otomatik test 262,780 saniyede geçti; testlerde internet ve kullanıcı veritabanı kullanılmadı.

0.122.0 testleri ThreatCluster/RansomLook kaynak ayrımını; tam ad ve domain dayanaklarını; aynı isimli tedarikçi belirsizliğini; tedarikçi/kaynak filtrelerini; kaynak hiç toplanmadı, kullanılabilir ve son deneme hatasından sonra eski başarılı snapshot durumlarını; pasif tedarikçi dışlamayı; bozuk kaynakta güvenli durmayı; kararlı olay kimliğini ve salt-okunur terminal/JSON görünümünü doğruladı. Şema 53 değişmedi. Tam kontrolde 1.324 otomatik test 264,783 saniyede geçti; testlerde internet ve kullanıcı veritabanı kullanılmadı.

0.121.0 testleri kayıtlı son CNAME kanıtından ağsız aday üretimini; aynı kayıt kökünün elenmesini; ayrı kaynak kanıtı ve tarihsel durum geçmişini; kabul, belirsiz, ret, geri alma ve başka tedarikçiye taşıma kararlarını; bozuk kaynak/adaya/karar zincirinde güvenli durmayı; terminal/JSON görünümünü; doctor sayaçlarını; yedek–geri yüklemeyi ve veri içeren şema 52→53 yedekli geçiş/rollback yolunu doğruladı. Tam kontrolde 1.319 otomatik test 249,261 saniyede geçti; testlerde internet ve kullanıcı veritabanı kullanılmadı.

0.120.0 testleri tedarikçi ekleme, güncelleme, pasife alma ve yeniden etkinleştirme yaşam döngüsünü; aynı isimli farklı kuruluşları; değiştirilemez ana domaini; idempotent işlemleri; bozuk olay zincirinde güvenli durmayı; ağsız terminal/JSON görünümünü; doctor sayaçlarını; yedek–geri yüklemeyi ve veri içeren şema 51→52 yedekli geçiş/rollback yolunu doğruladı. Tam kontrolde 1.311 otomatik test 251,781 saniyede geçti; testlerde internet ve kullanıcı veritabanı kullanılmadı. `.xti-data/xti.db` dosyası son kontrolde aynı değiştirilme zamanı, 1.454.080 bayt boyut ve şema 39 ile değişmeden kaldı.

0.119.0 testleri sabit theHarvester komutunu, geçici ortamı, commit doğrulamasını, katı JSONL/aktif işlem/kapsam reddini, arşiv kaynaklarının ayrı kanıtını, terminal kaynak seçimini ve veri içeren şema 50→51 yedekli geçiş/rollback yolunu doğruladı. Tam kontrolde 1.303 otomatik test 240,698 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı. Yerel ortamda `uv` bulunmadığı için canlı araç kurulumu yapılmadı.

0.118.0 testleri aynı kullanıcı adının Maigret ve Sherlock'ta ayrı sessiz başlangıcını; kaynak değiştirme ve platform karıştırma reddini; kayıtlı kaynağa tekil/toplu/ön plan yönlendirmeyi; karma toplu çalışmayı; Sherlock terminal/JSON ve tam-profil insan kararı yolunu; kaynak/platform/profil hostu bütünlüğünü ve veri içeren şema 49→50 yedekli geçişini doğruladı. Tam kontrolde 1.294 otomatik test 221,064 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı.

0.95.0 testleri katı JSON/HTTPS boyut ve zaman sınırlarını; şema, lisans, sayaç, zaman, ülke, durum, tekrar ve kaynak URL bozulmasında tüm snapshot'ın reddini; yerel arama/durum/limit davranışını; veritabanı oluşturmayan terminal/JSON yolunu ve ham `.onion` adresinin çıktıya taşınmamasını doğruladı. Ayrı canlı kabul, ThreatCluster'ın 30 günlük açık akışındaki 1.093 kaydı kullanıcı veritabanına yazmadan ayrıştırdı; `securehup.com` için bu pencere ve kaynakta sıfır eşleşme buldu. Bu sıfır sonuç güvenlik veya tarihsel yokluk hükmü değildir. Tam kontrolde 1.130 otomatik test 172,685 saniyede geçti; kullanıcı veritabanına yazılmadı ve şema 39 değişmedi.

0.94.0 testleri pasif keşfin hiç çalışmamış, tamamlanmış boş, eski, başarısız ve zamanı tutarsız durumlarını; web/e-posta/servis/CNAME sırasını; kapsam ve sonraki komutların terminal/JSON görünümünü; salt-okuma ile bozuk son keşif kaydında güvenli durmayı doğruladı. Tam kontrolde 1.125 otomatik test 148,591 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı. Kullanıcı veritabanına yazılmadı ve şema 39 değişmedi.

0.92.0 testleri katı CERT Polska metin/HTTPS sınırlarını, eski/gelecek/tekrarlı/bozuk snapshot reddini, Feodo ile kaynak izolasyonunu, ekleme/değişmeme/güncelleme/geri çekme/yeniden etkinleştirme yaşam döngüsünü, kaynak hatasında korumayı, değişmeyen çalışma–öğe satırı sıkıştırmasını, manuel yönetilen kaynak taklidinin reddini, terminal/JSON yenilemesini ve marka adayı tam eşleşmesini doğruladı. Bulgu görünüm sınırı dışındaki adayın IOC kapsamına alınması ayrıca sınandı. Tam kontrolde 1.116 otomatik test 186,443 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı. Ayrı canlı kabul, resmî son-ay listesini geçici alanda 18.764 domain olarak ayrıştırdı; ilk kayıt yaklaşık 2,23 saniye/33,7 MB, değişmeyen tekrar yaklaşık 1,83 saniye ve STIX dosyası yaklaşık 19,6 MB oldu. Canlı kabul kullanıcı veritabanını değiştirmedi.

0.93.0 testleri katı STIX ayrıştırmasını, sabit HTTPS sınırlarını, sürüm/koleksiyon/içerik dizini ve resmî başvuru doğrulamasını; ekleme/değişmeme/güncelleme/geri çekme/yeniden etkinleştirme yaşam döngüsünü; bağımsız manuel kaynağın korunmasını; bozuk geçmişte ağ öncesi durmayı; atomik geri almayı ve terminal/JSON aramasını doğruladı. Tam kontrolde 1.123 otomatik test 165,581 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı. Ayrı canlı kabul resmî 55.271.014 baytlık v20.0 dosyasında 26.690 STIX nesnesinden 982 etkin varlık ve 809 seçili ilişki çıkardı. Geçici SQLite'ta ilk kayıt yaklaşık 0,243 saniye/3.997.696 bayt, değişmeyen tekrar yaklaşık 0,333 saniye sürdü; `APT29` araması doğru aktör kaydını verdi. Kullanıcı veritabanına yazılmadı.

0.91.0 testleri açık başarılı IOC yenilemesini, yenileme sonrası tekrar analizi, kaynak hatasında önceki kataloğun korunmasını, hata–eşleşme yokluğu ayrımını, bilinmeyen hedefin ağdan önce reddini ve varsayılan analizin salt-okunur kalmasını doğruladı. Tam kontrolde 1.110 otomatik test 172,606 saniyede geçti; gerçek ağ kullanılmadı.

## Sonraki teslim

15 Kasım 2026 son kullanıcı kararıyla tanımlanan 11 mevcut motor işi,
0.140.4 (`7060cec`) üzerinde tamamlandı. Temiz kurulum, gerçek sürüm
güncelleme/kurtarma, karma kayıtların geri yüklenmesi, kesilmiş işin devamı,
gizlilik, gerçek systemd ve ölçümlü kapasite kabulü yukarıda kayıtlıdır.
[Motor planı](roadmap/ENGINE_INTEGRATION_ROADMAP.md) her işin bitiş kanıtını
ve sınırını gösterir. SQLite ile kişisel kullanım devam eder. Olay
adaylarının ilk dilimi 0.141.0'da, genel kayıtlı arama bildirimleri
0.142.0'da eklendi. Sıradaki motor işi RSS/Atom haber takibidir.
Entegrasyon için teslim hazırlığı, geniş paylaşım ve LLM en sondadır.
.NET bağlantısını, platform PostgreSQL yerleşimini ve veri geçişini
repoyu kullanan ekip yapar; bu repo motor, sözleşme, örnek ve belge sağlar.
Otomatik HTML rapor arşivi plandan çıkarılmıştır; mevcut komutla HTML
raporu kullanılabilir.


14 Kasım 2026 onaylı sekiz teslim 0.131.0–0.133.0'da tamamlandı;
Linux hizmetinin gerçek Linux üzerinde sınırlı işletim kabulü 0.140.4'te geçti.
[Sıralı plan](roadmap/ORDERED_INTEGRATION_PLAN.md) bu ayrımı gösterir.
Kuruluş birleşik raporu ve HIBP kamu kataloğu 0.134.0'da, kataloğun kayıtlı
toplama/zamanlama akışına katılması 0.135.0'da eklendi. Kuruluşa bağlı kamu
olaylarını izleme ve yerel bildirim kutusu 0.136.0'da eklendi. Tarihî kamu
olayını vakaya bağlama ve çevrimdışı HTML kuruluş raporu 0.137.0'da eklendi.
Gerçek temiz Ubuntu kurulumu, geçici veride yedekten dönüş, sürüm
güncelleme ve hizmet durdurma/yeniden çalışma zinciri doğrulandı.
7/24 hizmet seviyesi ve işletim sistemi yeniden açılışı bu kabulün dışındadır.
Common Crawl dış indeks erişimi ayrı açık konu olarak takip edilir.
[Kamu olayları devam planı](roadmap/PUBLIC_NOTICE_WORKFLOW_PLAN.md) kapsamı gösterir.

Tarihî 13 Kasım 2026 kullanıcı yönlendirmesi (güncel öncelik yukarıdadır): terminal menüsü yerine özellik
geliştirmeye devam edilecek; React arayüzü ileride ayrı projeden bağlanacak.
0.129.0 seçilen pasif toplama işlerini birleştirdi; 0.130.0 açık seçilen
sosyal ve ransomware izlemelerini bu servise ekledi. React veya REST API
henüz eklenmedi. Sonraki özellikler mevcut toplama,
CTI, tedarikçi ve vaka zincirindeki somut boşluklara göre seçilecek; kaynak
kapsamı, doğrulanmış katkı ve mevcut mimari sınırlar korunacak.

Tedarikçi ve kişisel yerel vaka çekirdekleri tamamlandı ve korunur. Gelecekteki
uygulama backend'i, ekip rolleri ve panel mevcut .NET platformundadır;
motorun kapsam/kanıt/iş sözleşmesi ayrıca doğrulanacaktır. STIX/standart
paylaşım genişlemesi en sona ertelenmiş motor yeteneğidir; yeni kaynaklar
ölçülmüş katkıya göre ele alınır. E-posta/SMS
ürün kanalları .NET tarafında; insan onaylı takedown ayrı kapsamdır.
13 Kasım 2026'da planlanan
isteğe bağlı LLM desteği en sonda değerlendirilmek üzere korunur:
kaynaklı açıklama, günlük özet, vaka taslağı
ve salt okuma soru-cevap. Henüz model kurulmadı veya harici API bağlanmadı;
[LLM planı](roadmap/LLM_PLAN.md) geçerlidir. Sunucu envanteri, ürün/sürüm,
paket ve CVE eşleştirmesi aktif plan dışındadır. Doğrudan forum/pazar/Telegram,
kimlik sızıntısı, TAXII ve takedown uygulanmadı; mevcut STIX dosya aktarımı
yalnız IOC `Indicator` nesnelerini kapsar.

Yeni sohbette bu dosya, [mimari](ARCHITECTURE.md) ve ilgili [iş paketi](roadmap/BACKLOG.md) üzerinden devam edilebilir.

