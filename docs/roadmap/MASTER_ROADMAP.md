# XTI — Ana geliştirme ve özellik tamamlama planı

**Tarih:** 24 Kasım 2026 · **Plan:** 1 · **Başlangıç motoru:** 0.179.0 · **P01 çalışması:** 0.180.0 · **P02 çalışması:** 0.181.0 · **P03 çalışması:** 0.182.0 · **P04 çalışması:** 0.183.0 · **P05 çalışması:** 0.185.0 · **P06 çalışması:** 0.186.0 · **P07 çalışması:** 0.187.0 · **P08 çalışması:** 0.188.0/0.192.0 · **P09 çalışması:** 0.189.0 · **P10 çalışması:** 0.190.0 · **P11 çalışması:** 0.193.0 · **P12 çalışması:** 0.191.0/0.192.0.

Bu belge yeni çalışmalar için tek ana plandır. Kullanıcının A–K listesindeki
**76 gereksinimin tamamını** kaydeder; hiçbir satır sessizce kaldırılmaz.
İlk planlama sonrasında P01/A03 uygulamasına başlandı. Yeni kod/paste
akışı ve Betterleaks entegrasyonu [teslim kaydında](P01_DELIVERY.md)
izlenir; dış erişim gerektiren kaynaklar ve Linux kabulü hâlâ açıktır.
Kullanıcının 21 Kasım seçimiyle P02 uygulandı; NCSC/CERT-FR açık yayınlarıyla
canlı kabul yapıldı. Hesap/kanal gerektiren canlı denemeler ayrı açıktır. [P02 teslim kartı](P02_DELIVERY.md).
Kullanıcı aynı gün P03 ertelemesini kaldırdı; marka kimliği, sayfa/logo,
mağaza ve sosyal adayların kanıt/inceleme/izleme/firma JSON zinciri uygulandı.
SecureHup canlı denemesi kısmi kaynak erişimiyle kanıt üretti. Linux ve
ticari kararlar açık; gerçek VIP kullanıcı seçimiyle canlı kapsamda yok.
[P03 kapsam ve kabul kartı](P03_DELIVERY.md).
P04'ün LLM gerektirmeyen motor kapsamı; kaynaklı CTI/IOC ve yerel ATT&CK
üzerinde aday, açıklanabilir skor, graf/zaman/trend, insan kararı, inbox,
vaka, firma JSON'u ve ağsız kuyruk olarak uygulandı. Yerel kapasite kabulü
ve3.577 testlik tam regresyon geçti. Push sonraya bırakıldığı için gerçek
Linux CI/release kaydı açık.
[P04 kapsam ve kabul kartı](P04_DELIVERY.md).
P05'in seçilmiş kaynak motoru uygulandı: saklı kamu iddiaları ile yalnız
doğrulanmış kuruluş domainine ait XposedOrNot sonuçları kaynaklı, maskeli,
insan incelemeli ve firma-izole yaşam döngüsünde birleşir. Açık parola kontrolü
kalıcı secret/hash bırakmadan yerel önek kullanır. HIBP verified-domain yeni
çalışmalarda kapalı, şema93 geçmişinde salt okunurdur. XposedOrNot canlı domain
kabulü API anahtarı/doğrulanmış domain; genel forum/pazar kapsamı seçilmiş
sağlayıcı beklediğinden A02/A10 bütünü tamamlandı sayılmaz.
[P05 kapsam ve kabul kartı](P05_DELIVERY.md).
P06'nın kullanıcı tarafından seçilen yerel motor kapsamı uygulandı:
sürümlü vaka runbook'u, doğrulanabilir kanıt/yönetici paketi, insan
onaylı ve otomatik gönderimsiz takedown yaşam döngüsü ile atomik
CSV/JSON/STIX IOC alışverişi. Kullanıcı P06 listesindeki haricî
SIEM/SOAR/ticket bağlayıcı maddesini kapsamdan çıkardı. Tam repo ve gerçek
Linux CI kabulü açıktır. [P06 kapsam ve kabul kartı](P06_DELIVERY.md).
P07'nin birleşik yerel motor kapsamı uygulandı: altı hedef türü ve 12 saklı
kayıt ailesi tek kuruluş politikasında; sessiz baseline, sürümlü eşik/
öncelik, açıklanabilir fark, inbox, insan kararı, vaka, firma JSON'u,
due sözleşmesi, kurtarma ve snapshot tekilleştirme aynı zincirdedir. Yeni
dış kaynak/ücretli API yoktur. E02 haricî kanallar ve E04 streaming
açılmadı; E05'in gerçek platform scheduler/teslimi tüketici platformda
kalır. İki firmalı 5.000 eşleşme/32 çalışma kapasite kabulü geçti. CI ile aynı
iki parçalı hızlı kapı toplam 2.294 testte, tam repo kapısı 3.635 testte
hatasız tamamlandı; macOS'ta Linux'a özgü 4 test beklendiği gibi atlandı.
[P07 kapsam ve kabul kartı](P07_DELIVERY.md).
P08'in kuruluş bazlı retention temeli uygulandı: P07 izleme gövdeleri için
sürümlü yaş/parti politikası, açık hold, aktif vaka koruması, yazmasız plan,
yedekli kayıpsız arşiv/restore, recovery ve zincirli mutasyon audit'i aynı
firma sınırındadır. Bütün kayıt aileleri, otomatik mantıksal silme, okuma
audit'i, güvenilir platform actor/RBAC ve mevzuat uygunluğu tamamlandı
sayılmaz. İki firmalı kapasite ve 2.303 testlik hızlı kapı geçti; tam repo ve
3.644 testlik tam repo kapısı hatasız geçti. Push sonrası gerçek Linux kabulü
açıktır. [P08 kapsam ve kabul kartı](P08_DELIVERY.md).
P09 kaynak/feed kontrol düzlemi 49 connector ile uygulandı; P10–P12
eklemeleriyle güncel katalog 55 kaynağa çıktı. Erişim,
maliyet, secret, dil/bölge, ortak kayıt türü, provenance, kota/tekrar/hata,
veri hakkı ve sağlık sözleşmesiyle tek manifest kataloğunda görünürdür.
Terminal, engine ve firma platformu aynı ağsız okuma servisini kullanır.
Bu teslim her kaynağın canlı/ticari kabulü veya bütün verilerin tek fiziksel
formata taşındığı anlamına gelmez; geniş A07 satırı kısmi kalır.
[P09 kapsam ve kabul kartı](P09_DELIVERY.md).
P10 mevcut içerik yaşam döngüsünü çoğaltmadan Bluesky genel gönderi
aramasını ekledi. P11 anahtarsız Lunar toplu domain maruziyetini ve ayrı AIL
7.x sistemi için ham içeriksiz metadata zarfını mevcut P05 yaşam döngüsüne
bağladı. Lunar canlı doğrulandı; gerçek AIL kurulumu, seçilmiş yasal kaynak
ve canlı tracker olayı açık kaldığından geniş A02/A10 tamamlanmış sayılmaz.
P12 ise güvenli normalize sensör/sandbox telemetrisini
aynı firma, kanıt, inceleme, izleme ve vaka zincirine bağladı. 0.192.0 ile
P08'in kayıpsız saklama/hold/restore motoru P12 telemetri gövdelerini de
yönetir. Cowrie ve CAPE bu motora kurulmaz veya bu motor tarafından
çalıştırılmaz; gerçek sensör/sandbox işletimi ayrı ve şu an açık değildir.
[P10 teslim kartı](P10_DELIVERY.md), [P11 teslim kartı](P11_DELIVERY.md),
[P12 teslim kartı](P12_DELIVERY.md).

Gerçekte çalışan kapsam ve kabul kanıtı [STATUS](../STATUS.md), kaynak
koşulları ve dış girdiler [NOTES](../../NOTES.md), mimari sınırlar
[ARCHITECTURE](../ARCHITECTURE.md) üzerinden doğrulanır. Eski planlar
tarihî başvuru olarak korunur; bu belgedeki sıra ile yarışan aktif planlar
değildir. [Önceki ana plan](MASTER_ROADMAP_HISTORY_2026_11_20.md).

## 1. Kullanıcının istediği çalışma biçimi

Bir özellik seçildiğinde yalnız toplama komutu veya önizleme teslim edilmez.
O özelliğin anlaşılmış kapsamı; kurulum, gerçek veri alma, işleme, kalıcı
sonuç, inceleme, izleme, firma JSON bağlantısı, test ve kullanım belgesiyle
birlikte tamamlanır. Bunlar ayrı ayrı “devam edelim mi?” adımları değildir.

- Seçilen paket içindeki rutin tasarım, uygulama, düzeltme ve doğrulama
  işleri mevcut yetki kapsamında sürdürülür; kullanıcıdan her alt adım
  için yeniden onay istenmez. İlerleme kısa ve somut biçimde paylaşılır.
- API hesabı, harcama, yeni hedef yetkisi veya insan kararı gerekiyorsa
  bu bağımlılık geliştirme başında belirlenir. Erişim ve bütçe varmış gibi
  davranılmaz; bağımsız işler tamamlanır, bağlı kabul açık bırakılır.
- Bir paketin seçilmesi diğer paketleri, ertelenmiş tercihleri veya ücretli
  kaynakları otomatik açmaz. Push/yayın işlemleri mevcut kullanıcı
  yetkisine göre yürütülür ve gerçek gönderim durumu ayrıca belirtilir.
- İç geliştirme adımlara bölünebilir. Ancak kullanıcıya tamamlanmış ürün
  özelliği olarak sunulan teslim, bütün kullanım zinciridir.
- “Tamamlandı”, belirlenmiş kaynak/işlev/kapasite kapsamının kabulünden
  geçmesi demektir; bütün internetin kapsanması, hiç yeni hata bulunmaması
  veya yüzde100 gerçek dünya doğruluğu anlamına gelmez.
- Kapsam teslim sonunda daraltılarak başarı üretilmez. Değişiklik gerekirse
  etkilenen gereksinim, neden ve kapanmayan ihtiyaç açıkça kaydedilir.
  Özellikle bir birleşik A–K satırının yalnız bir parçası bitince satırın
  bütünü tamamlanmış sayılmaz.

### Başlangıç, ilerleme ve kapanış bilgilendirmesi

Kullanıcı hangi gereksinimin nasıl geliştirildiğini süreç boyunca görebilmeli.
Her paket başlarken kısa ve anlaşılır bir başlangıç bildirimi verilir:

| Başlık | Kullanıcıya açıklanacak bilgi |
|---|---|
| Başlanan iş | Paket kimliği/adı ve A–K listesindeki gereksinim kimlikleri/adları; asıl hedef ile yalnız desteklenen parçalar ayrı. |
| Beklenen sonuç | Kullanıcının iş bittiğinde yapabileceği somut işlem. |
| Repo/araç/kaynak | Proje veya sağlayıcı adı ve resmî bağlantısı; hangi işi yapacağı, neden seçildiği, incelenmiş sürüm ve varsa hesap/maliyet ihtiyacı. |
| Seçim durumu | Aday, seçilmiş, kurulmuş, entegre edilmiş ve canlı doğrulanmış durumları ayrı. Seçilmemiş araç kesin kullanılacak gibi anlatılmaz. |
| Bizim geliştireceğimiz | Mevcut motordan kullanılacak parçalar, yazılacak bağlantı/iş kuralları ve sonuçların nasıl birleşeceği. |
| Uygulama sırası | Kaynak incelemesi → entegrasyon → kalıcı sonuç/inceleme → takip/bildirim → JSON bağlantısı → kabul ve belge. |
| Tamamlanma | Paket kabulünde ne gösterileceği ve önceden bilinen dış bağımlılıklar. |

Çalışma sırasında hangi adımın tamamlandığı, ne öğrenildiği ve sıradaki
adımın neyi doğrulayacağı kısa güncellemelerle paylaşılır. Araç veya yöntem
değişirse nedeni ve kullanıcı sonucuna etkisi açıklanır. Araç seçimi başlangıçta
henüz bitmemişse önce adaylar, seçim sonrası gerçek karar bildirilir.
Bu bilgilendirmeler rutin alt adım onayları değildir; yetkilendirilmiş
paketin işi sürdürülür.

Kapanışta aynı gereksinim kimlikleriyle tamamlanan/açık kalan parçalar,
fiilen kullanılan araçlar ve sürümleri, doğrulama sonuçları ve kullanım
örneği verilir. Kaynak denemesi veya fixture sonucu tam özellik teslimi
gibi sunulmaz. Güncel durum ilgili paket kaydına ve gerektiğinde NOTES'a işlenir.

## 2. Sorumluluk ve uygulama yolu

| Alan | Sorumluluk | Uygulama yolu |
|---|---|---|
| Toplama, kaynak kanıtı, firma eşleştirmesi, analiz, izleme ve vaka | XTI motoru | Mevcut servisleri genişlet; yeni kaynak ve araçları adaptörle bağla. |
| Secret tespiti, sayfa alma, metin çıkarma, benzerlik gibi uzman işler | XTI tarafından yönetilen bileşen | Hazır açık kaynak adaylarını aynı veriyle karşılaştır; uygun sürümü sabitle. |
| Özel veri erişimi, ücretli beslemeler, kapalı kaynak kapsamı | XTI adaptörü + veri sağlayıcısı + işletici | Kaynak erişimi, gösterme/saklama kapsamı ve bütçe belli olmadan canlı kabulü kapatma. |
| React ekranları, .NET HTTP API, kullanıcı/rol/SSO, fatura | Tüketici platform ekibi | Motorun sürümlü JSON işlemlerini kullan; analiz mantığını yeniden yazma. |
| Firma sınırı, güvenilir kullanıcı bağlamı, denetim ve veri politikaları | Paylaşılan sorumluluk | Backend kimliği/yetkiyi sağlar; motor kapsamı ve ilgili veri/iş kurallarını uygular. |
| Sunucu işletimi, bölge, yedek hedefi, hizmet seviyesi | İşletici + platform + motor | Gerçek iş yüküyle kabul; motor değişikliği ve altyapı değişikliğini ayrı izleme. |

XTI ana kayıt ve iş yönetim sistemi olarak kalır. Bir dış araç, kendi
görevini yapar; sonuçlar kaynağı ve sürümüyle XTI'ya bağlanır. Üçüncü taraf
kodunu topluca kopyalamak veya başka bir platformu zorunlu ana sistem
yapmak varsayılan yöntem değildir. Python motor, farklı dilde yazılmış
bir aracı da yönetebilir. Araç değiştiğinde geçmiş kanıt ve insan kararı
korunur; sürüm farkı görünür olur.

.NET'in ileride PostgreSQL kullanması, motor depolarının otomatik taşındığı
anlamına gelmez. Motor deposunda değişiklik gerekirse veri geçişi, sorgu
kabulü ve geri dönüş bu repoda ayrıca tasarlanır. Bugün SQLite korunur.

## 3. On beş ürün paketi ve önerilen sıra

Bu tablo geliştirme önerisidir; bütün paketleri çalıştırma yetkisi değildir.
**21 Kasım 2026: P01 / A03 uygulamasına başlandı.** [Teslim kaydı](P01_DELIVERY.md)
canlı erişim bağımlılıklarını ve her kapanış ölçütünü izler; paket henüz tamamlanmadı.
Başlangıç incelemesinde kaynak erişimi karşılanmıyorsa engel kaydedilir;
başka bir pakete geçiş görünür sıra değişikliği olur.

### Paket tekrarını önleme kapısı

Yeni paket için kod yazılmadan önce mevcut terminal komutları, engine/platform
işlemleri, uygulama servisleri, veri tabloları, kaynak adaptörleri, testler ve
özellik kataloğu gereksinim satırıyla eşleştirilir. Sonuç `var`, `kısmi` veya
`yok` olarak kanıtıyla kaydedilir. `Var` olan davranış yeniden yazılmaz;
`kısmi` davranış mevcut servis ve veri yaşam döngüsü genişletilerek tamamlanır.
Yeni paralel komut, tablo, izleme modeli veya aynı işi yapan ikinci adaptör
ancak mevcut yapı teknik olarak kullanılamıyorsa ve bu karar ADR ile
kanıtlanıyorsa açılabilir. Kaynak seçilmemiş veya yalnız canlı kabul eksikse
soyut bir özellik kopyası yazılmaz; dış gereksinim açık tutulur.

| Sıra | Paket | Kullanıcıya teslim edilecek sonuç | Başlangıç bağımlılığı / durum |
|---|---|---|---|
| 1 | **P01 — Kod deposu ve paste maruziyeti** | Kuruluş/domain ile ilişkili kod ve açık içeriklerde marka/secret adaylarını internetten bul, maskeli kanıtla göster, değişimi izle ve vakaya bağla. | Uygulama ve yerel kabul tamam. Betterleaks 1.10.1 seçildi/kuruldu; GitHub/GitLab kamu keşfi canlı denendi. Hesaplı kod araması, Pastebin erişimi, ticari kaynak kararı ve Linux kabulü açık. |
| 2 | **P02 — Firma ve tedarikçi içerik/kanal izlemesi** | Desteklenen haber, blog, forum ve kanallarda firmayla ilgili yeni/değişmiş içeriği bul, doğru firmayla ilişkilendir ve bildir. | Akışın yerel kabulü ve RSS/Atom canlı kabulü tamam. Hesap/kanal gerektiren Telegram/Discord/IRC canlı kabulü, Linux ve ticari kaynak kararları açık. [Teslim kartı](P02_DELIVERY.md). |
| 3 | **P03 — Marka taklidi kanıtı** | Sahte domain/sayfa, logo, sosyal profil, VIP ve uygulama adaylarını özgün markayla karşılaştır; meşru bayi/parodi ayrımını incelemeye sun. | Akış, macOS temiz kurulum, gerçek eski üreticiden geçiş/geri dönüş ve birikimli kapasite kabulü uygulandı. SecureHup son canlı sonuç kısmi:13 aday/24 PNG. VIP modeli kontrollü kabul edildi; gerçek kişi kullanıcı seçimiyle izlenmedi. Linux, kaynak erişim eksikleri ve ticari kararlar açık. [Teslim kartı](P03_DELIVERY.md). |
| 4 | **P04 — CTI analiz derinliği** | Aynı varlığın farklı adlarını ayır/birleştirme adayı yap; rapordan kanıtlı ilişki/TTP/etiket öner; kampanya değişimini ve firma önceliğini göster. | LLM gerektirmeyen motor akışı uygulandı; yerel davranış/geçiş/firma/kuyruk/yedek, iki firma20.000 aday kapasite kabulü ve3.577 testlik tam regresyon geçti. Push sonrası gerçek Linux CI/release kabulü açık. Geniş STIX/TAXII ve credential doğrulama dahil değil. [Teslim kartı](P04_DELIVERY.md). |
| 5 | **P05 — Dark web ve credential kapsamı** | Seçilen yeraltı/veri sağlayıcılarında firma ve tedarikçi iddialarını kaynaklarıyla izle; credential eşleşmesini maskeli ve kapsamlı göster. | Seçilmiş kaynak motoru, yerel/geçiş/firma/kuyruk/kurtarma/yedek ve iki firma20.000 bulgu kapasite kabulü uygulandı. XposedOrNot odaklı25 test,2.261 testlik hızlı çevrimdışı kapı, güncel kapasite ve zararsız parola uç noktası kabulü geçti.0.184.0 tabanının son tam regresyonu3.596 testte hatasızdır;0.185.0 tam kapısı bu turda yeniden çalıştırılmadı. XposedOrNot canlı domain kabulü API anahtarı/doğrulanmış domain; forum/pazar kapsamı seçilmiş sağlayıcı bekliyor. Kamu ransomware akışı bütün dark web kabulü değildir. [Teslim kartı](P05_DELIVERY.md). |
| 6 | **P06 — Aksiyon ve paylaşım** | Kanıtlı rapor, vaka prosedürü, insan onaylı takedown ve toplu IOC alışverişi. | Seçilen yerel motor kapsamı uygulandı: G01/G03/G04/G05 ve G02 desteği. Tam repo/Linux kabulü açık. LLM, geniş STIX/TAXII, e-posta/SMS ertelendi; SIEM/SOAR/ticket bağlayıcıları kullanıcı kararıyla kapsam dışı. [Teslim](P06_DELIVERY.md). |
| 7 | **P07 — Birleşik izleme ve alarm politikası** | Domain, marka, IP, kelime, kişi ve tedarikçiyi saklı kanıtta ortak politika, sessiz başlangıç, fark, alarm, inceleme ve vaka zincirinde izle. | Yerel motor, firma JSON'u, recovery ve kapasite kabulü tamam; haricî bildirim ve gerçek scheduler platform/işletimde açık. [Teslim](P07_DELIVERY.md). |
| 8 | **P08 — Saklama, hold ve audit temeli** | Eski büyük izleme gövdelerini kuruluş politikasıyla kayıpsız arşivle, hold/vaka kanıtını koru ve mutasyon zincirini denetle. | P07 izleme ve P12 telemetri gövdeleri tamam; diğer aileler, okuma audit'i, haricî soğuk depo ve mevzuat kararı açık. [Teslim](P08_DELIVERY.md). |
| 9 | **P09 — Kaynak ve feed yönetişimi** | Her connector'ü erişim, maliyet, dil/bölge, kanıt, kota, hata ve ticari veri kararıyla tek sürümlü katalogda yönet. | 49 manifest, terminal/engine/platform ve 10.000 kayıt kapasite kabulü uygulandı. Canlı kaynakların kendi kabulleri ve hukuk/ticari kararları ayrı açık. [Teslim](P09_DELIVERY.md). |
| 10 | **P10 — Mevcut içerik kaynaklarındaki gerçek kapsam boşlukları** | `news`, `mentions` ve firma/tedarikçi içerik yaşam döngüsünü yeniden yazmadan yalnız seçilmiş yeni sosyal gönderi, forum veya kanal kaynağını mevcut akışa bağla. | **Teknik teslim tamam:** Bluesky genel gönderi araması mevcut P02 akışına bağlandı; SecureHup boş sonuç ve pozitif gerçek yanıt kabulü geçti. Ticari saklama/gösterim kararı açık. [Teslim](P10_DELIVERY.md). |
| 11 | **P11 — Yeraltı ve credential kaynak genişletme** | Yasal ve seçilmiş forum/pazar/Tor veya stealer-log sağlayıcısını mevcut maskeli dark-web yaşam döngüsüne bağla. | Teknik motor teslim edildi: Lunar toplu domain maruziyeti canlı doğrulandı; AIL 7.x için ham içeriksiz/hash bağlı zarf, geçmiş, inceleme, firma JSON'u, recovery ve şema100 tamamlandı. Hedefli 49 test ile 2.354 hızlı/3.699 tam repo kapısı geçti. Gerçek AIL kurulumu, seçilmiş yasal yeraltı kaynağı ve canlı tracker olayı açık olduğundan A02/A10'un geniş dış kaynak kapsamı kısmi kalır. [Teslim kartı](P11_DELIVERY.md). |
| 12 | **P12 — Sensör ve malware telemetrisi** | Honeypot/sinkhole ve sandbox sonuçlarını sensör görülmesi, örnek davranışı ve kaynaklı kanıt olarak al. | **Teknik motor teslimi tamamlandı:** güvenli XTI/Cowrie/CAPE normalizasyonu, sürümlü kanıt, inceleme, izleme, vaka, Engine/Platform, şema99, kayıpsız retention/hold/restore ve 5.000 kayıt/firma kabulü hazır. Cowrie/CAPE kurulmadı; gerçek işletim/canlı kabul, ticari veri kararı ve Linux kabulü açık. |
| 13 | **P13 — Cloud ve uzman istihbarat modülleri** | Cloud yanlış yapılandırma, SBOM, OT/ICS/IoT ve blockchain gibi özel veri ailelerini ayrı güvenli modüllerle ekle. | Planlandı; her alt modül ayrı kaynak/yetki/doğruluk ve kapasite kabulü ister. Zafiyet/SBOM kullanıcı kararı değişmeden aktif açılmaz. |
| 14 | **P14 — Üretim ölçeği ve birlikte çalışabilirlik** | Seçilen STIX/TAXII/MISP, bildirim, veri katmanı, bölge, DR ve işletim sözleşmelerini gerçek yükle tamamla. | En sona bırakıldı. .NET HTTP/auth/UI tüketici ekipte; motor gerekli sürümlü JSON, firma ve kanıt sınırlarını sağlar. Kafka/OpenSearch iş yükü kanıtı olmadan zorunlu değildir. |
| 15 | **P15 — Kanıta bağlı LLM desteği** | Özet, çeviri, doğal dil sorgu ve analist önerisini özgün kanıt, maliyet, gizlilik ve insan onayıyla sun. | En sona bırakıldı. Model/yerel-API kararı, veri gönderimi, bütçe ve etiketli doğruluk kabulü seçilmedi; LLM otomatik tehdit hükmü vermez. |

Paket bir yönetim başlığıdır. Kaynaklar, diller ve alt yetenekler aşağıdaki
76 satıra bağlanır; paket içinde sessizce ertelenen satır olamaz. Ayrı
erişim veya platform işi gerektiren alt parçalar baştan işaretlenir.
Süre taahhüdü kaynak/araç ön incelemesi ve iş yükü belirlenmeden verilmez.

### Paketlere eşlik eden işler

- **OP — İşletim ve veri politikaları:** Kurulum, kaynak kotası, iş
  kapasitesi, geçmiş/disk büyümesi, firma ayrımı, bakım, yedek, saklama ve
  denetim her paketin kabulüne dahildir. Genel saklama/silme, eşzamanlılık,
  çoklu bölge veya yeni depo ihtiyacı ayrıca kendi gereksinimini kapatır.
  Ortak ihtiyaç çıkmadan bütün altyapıyı değiştiren ayrı bir ön proje yoktur.
- **AI — Gelecek LLM paketi:** Özetleme, çeviri, kanıta dayalı sorgu ve
  öneri desteği [LLM planına](LLM_PLAN.md) bağlıdır. Ücretli/yerel model,
  veri gönderimi ve bütçe seçilmedi; otomatik karar ve kaynak icadı kabul edilmez.
- **SP — Uzman modüller:** Honeypot/sinkhole, sandbox, cloud/SBOM, OT/ICS,
  blockchain ve deepfake ayrı kullanım ve kaynak kararlarıdır. Genel
  modüle isim ekleyerek yapılmış sayılmazlar. Her biri aynı tam teslim
  düzenini izler. Zafiyet/SBOM genişlemesi aktif kapsam dışı kararını korur.
- **PL — Platform:** UI, HTTP servis, kimlik ve ticari işletim ekranları
  tüketici ekipte. Motor tarafındaki gerekli veri/iş sözleşmesi ilgili
  paketin içinde tamamlanır; gerçek UI/SSO bağlantısı yapılmış sayılmaz.
- **DIŞ — Hedef dışında:** Genel saldırı/istismar otomasyonu ve otomatik
  engelleme mevcut motor hedefi değildir. Liste satırları görünür tutulur.

## 4. Bir özelliğin başlanmadan önce hazırlanacak kartı

Her yeni kaynak/özellik için aşağıdaki alanlar ilgili paket kaydında
doldurulur. Gelecekteki bütün kaynaklar bugün seçilmiş gibi yazılmaz.

| Alan | Önceden verilmesi gereken cevap |
|---|---|
| Kullanıcı sonucu | Kullanıcı neyi girecek, neyi görecek ve ne karar verebilecek? |
| Gereksinim | Hangi A–K satırlarını tam veya kısmen kapatıyor; hangi parçalar hâlâ açık? |
| Kaynak kapsamı | Kaynak/endpoint, veri türü, dil, tarih aralığı ve erişilebilir içerik sınırı. |
| Erişim ve maliyet | Anahtar/hesap/izin ihtiyacı, ücretsiz/ücretli koşul, kota, saklama ve müşteri gösterimi kararı. |
| Bileşen seçimi | Adaylar, bakım/lisans incelemesi, aynı örneklerde doğruluk/hız, seçilen sabit sürüm ve değiştirme yolu. |
| Veri ve sonuç | Kaynak/zaman/kimlik, maskelenen alanlar, kanıtın korunması, aday–doğrulanmış ayrımı. |
| İş akışı | Topla → eşleştir → sakla → incele → izle → değişimi bildir → vakaya/rapora bağla. |
| Tekrar ve hata | Boş yanıt, erişim hatası, eksik sayfa, iptal/kesinti, kaldığı yer, aynı çağrının tekrarı, eski başarılı veri. |
| Kapasite | Firma/varlık/kayıt/tur sayısı, güncelleme sıklığı, günlük büyüme, sayfalama, süre/bellek/disk/istek bütçeleri. |
| Doğruluk kabulü | Bağımsız etiketli örnekler, beklenen eşleşmeler ve benzer ama ilgisiz örnekler; önceden belirlenmiş ölçüm/eşik. |
| Teslim | CLI ve firma JSON, kurulacak bağımlılıklar, geçiş/geri dönüş, test ve kullanım örneği. |

Kaynak kabulü için gerekli dış girdi eksikse “uygulama/yerel kabul var,
canlı kabul bekliyor” denebilir; özelliğin tamamı kapatılmaz. Gerekli erişim
başta konuşulur, son adımda beklenmedik zorunluluk olarak ortaya çıkarılmaz.
Araç API'si veya sağlayıcı koşulları gerçekten değişirse tarih/kanıtla güncellenir.

## 5. Tamamlandı ölçütü — her pakette aynı

1. **İşlev:** Seçilen kapsam için kullanıcı girdisinden kayıtlı ve
   incelenebilir sonuca kadar gerçek kullanım zinciri çalışır. Yardım
   ekranı, önizleme veya aracın kurulmuş olması tek başına kabul değildir.
2. **Kaynak kanıtı:** Sonuç kaynağı, zamanı, kapsamı ve ayrıştırıcı/araç
   sürümüyle açıklanır. Başarısız istek başarılı boş sonuç olmaz.
3. **Doğruluk:** Zorunlu pozitif, negatif, belirsiz ve çelişkili örnekler
   beklenen davranışı verir. Etiketli kümedeki ölçüm ile canlı kaynağın
   kapsamı ayrı raporlanır; sonuçtan sonra eşik düşürülmez.
4. **Tam yaşam döngüsü:** Kaydetme, liste/ayrıntı, insan kararı, tekrar,
   değişiklik, iptal/geri çekme, geçmiş, vaka ve rapor bağlantısı ilgili
   özellik için tamamdır. Uygulanamaz bir adım varsa gerekçesi baştan yazılır.
5. **Motor bağlantısı:** CLI ve firma JSON aynı servisleri kullanır.
   Firma karışması, başka firma kimliği, eski workspace ve tekrar istekleri
   doğrulanır. UI ekibi toplama veya analiz mantığını yeniden yazmak zorunda kalmaz.
6. **Birikimli kullanım:** Değişmeyen ve değişen tekrarlı turlar ölçülür;
   geçmiş, etkin iş kapasitesini tüketmez. Sayfalama, kayıt büyümesi,
   süre/bellek/disk bütçeleri belirtilmiş iş yükünde sınanır.
7. **Kurtarma:** Süreç kesintisi, kaynak hatası ve ilgili disk/veri
   arızasında eski kanıt korunur. Geçiş varsa yedek, gerçek eski sürümden
   yükseltme ve eski yedekle geri dönüş doğrulanır.
8. **Kurulum ve kullanım:** Desteklenen Linux ortamında kurulum ve kısa
   kullanıcı senaryosu çalışır. İsteğe bağlı bileşenin eksikliği açık
   görünür. Sırlar terminale/rapora/git'e taşınmaz.
9. **Doğrulama:** Geliştirirken ilgili anlamlı testler; paket kapanışında
   değişiklik kapsamının gerektirdiği regresyon, sözleşme ve Linux kabulü
   yapılır. Her küçük değişiklikte tüm paket tekrarlanmaz; yalnız belge
   değişikliğinde link/tutarlılık denetimi yeterlidir. Zorunlu başarısız
   veya atlanan kontrol varken tam teslim denmez.
10. **Kapanış kaydı:** Kod sürümü/commit, senaryo sonuçları, canlı ve
    kontrollü kanıt ayrımı, kapasite ölçümü, kaynak maliyeti/koşulu,
    güncellenen kullanım ve NOTES, gönderim/CI durumu birlikte verilir.

**Durumlar:** planlandı → ön inceleme → uygulama → kabul → tamamlandı.
“Dış girdi bekliyor”, “ertelendi”, “platform ekibinde” ve “hedef dışında”
tamamlandı değildir. Bir alt teslim biterken ana gereksinimde açık parça
varsa ana satır kısmi kalır. Yeni ihtiyaç eski kabulü geriye dönük değiştirmez;
önceki kapsamı aşan genişleme ayrı kaydedilir. Mevcut kapsamın hatası ise
aynı teslimle ilişkilendirilerek düzeltilir.

## 6. İlk önerilen paket P01'in somut teslimi

**Hedef:** Kullanıcı kuruluş adı, domainleri ve varsa bilinen depo
hesaplarını verir. Motor desteklenen internet kaynaklarında araştırır;
ilgili içerik ve secret adaylarını maskeli kanıtla gösterir, sonraki
değişiklikleri izler. Kullanıcının dosya getirerek sistemi beslemesi
zorunlu başlangıç yöntemi değildir.

**Durum:** uygulama ve yerel doğrulama tamam. Betterleaks 1.10.1 seçildi,
kuruldu ve gerçek yerel ikiliyle test edildi. Kamu GitHub/GitLab keşfi
canlı denendi; hesaplı genel kod araması ve Pastebin erişimi açık.
Bu kaynakların kabulü sağlanmadan A03'ün bütünü tamamlandı sayılmaz. Sınırsız
platform araması veya her eski/silinmiş içeriğe erişim vaat edilmez.

| Teslim parçası | Kabulde görülmesi gereken |
|---|---|
| Firma tanımı | Domain, marka ve alternatif isim; aynı isimli ilgisiz kuruluş; firma kapsamı ve tanım değişikliği ayrımı. |
| İnternetten keşif | Kaynak bazlı arama, sayfalama, bulunan depo/içerik kimliği ve keşif nedeni. Bilinen depo taraması ile genel keşif ayrı gösterilir. |
| Depo ve paste kapsamı | Her seçilen kaynağın erişim biçimi ve desteklenen geçmişi kanıtlıdır; arşiv geçmişi bulunmaması temiz sonuç sayılmaz. |
| Secret/marka analizi | Hazır araç adayları aynı etiketli veriyle karşılaştırılır. Marka geçişi, hassas değer adayı ve firmayla bağlantı ayrı alanlardır. |
| Kanıt | Kaynak URL, depo/dosya/sürüm veya paste kimliği, zaman, maskeli bağlam; sırların düz metin rapor/log/git'e çıkmaması. |
| İnceleme | İlgili/ilgisiz/belirsiz ve çözüm durumu; gerekçe, eski karar ve kanıt korunur. Secret deseni aktif hesap erişimi doğrulaması değildir. |
| Düzenli takip | İlk ölçüm, yeni/değişen içerik, kapsam değişimi ve kaynak hatası ayrı; değişmeyen içerik yeni alarm veya sınırsız gövde kopyası üretmez. |
| Kullanıcı çıktısı | Ayrıntı, filtre, kuruluş raporu, ortak inbox, vaka bağı ve aynı firma JSON işlemleriyle gerçek kullanım senaryosu. |
| İşletim | Kota/bekleme, iptal/kesinti, tekrarlı çağrı, backup/restore ve bağımlılık güncellemesinin sonuçları korunur. |

Kalite kümesi gerçek parola kullanmadan oluşturulur: beklenen firma
eşleşmeleri, benzer isimli negatifler, örnek/test anahtarları, aynı
değerin tekrarı, farklı kaynaklarda kopya içerik, Unicode ve silinen/
erişilemeyen kayıtlar. Depo içeriği çalıştırılmaz; içerik alma, ayrıştırma
ve kanıt gösterimi güvenilmeyen veri olarak sınanır.

Kapasite kabulü iki ayrı firma, firma başına 100 depo/içerik
kapsamı, 10.000 saklı aday ve 30 tekrarlı turdur. Bu sentetik veridir;
canlı hesaplara bu yük gönderilmez. Ortam ve p95/bellek/disk/istek
eşikleri [0185](../decisions/0185-code-and-paste-exposure.md) ile koddan
önce sabitlendi. Yerel ölçüm [P01 kaydında](P01_DELIVERY.md); canlı kaynak
kapsamı veya 7/24 üretim garantisi yerine geçmez.

Kullanıcıdan gerekebilecekler: gerçekten kullanılacak kaynakların hesap/
anahtarları, özel depolar seçilirse açık kapsam, ücretli kaynak seçilirse
bütçe. Bunlar ilk kaynak incelemesinde tek bir bağımlılık listesi olur;
sırlar sohbete veya dokümana yazılmaz. Rutin alt işler için tekrar tekrar
onay istenmez.

## 7. Kullanıcının 76 maddelik gereksinim kaydı

Aşağıdaki başlangıç durumu 0.179.0 için oluşturulmuş ve 0.189.0'a kadar
teslim edilen paketlerin gerçek durumuyla güncellenmiştir.
yeni canlı kabul değildir. “Var” yalnız açıklanan mevcut kapsamı belirtir.
Birden çok paket yazılması, parçaların hepsinin gerekmesi demektir.
Ortak OP teslim koşulları yalnız OP yazan satırlarda değil bütün paketlerde
uygulanır. Mevcut yetenekler korunacak; yeniden sıfırdan yazılmayacaktır.

### A — Veri toplama (14)

| ID | Kullanıcının gereksinimi | Başlangıç durumu ve açık parça | Yol |
|---|---|---|---|
| A01 | Sosyal medya, forum, blog, haber OSINT | Kısmi: profil/arama, seçili yayıncılar ve P02 RSS/Atom akışına ek olarak P10 anahtarsız Bluesky genel metin gönderilerini firma/tedarikçi kanıt–inceleme–takip yaşam döngüsüne bağladı. Diğer genel sosyal platformlar/forumlar ve hesaplı kanal canlı kabulleri ayrı açık. | P02, P03, P10 |
| A02 | Dark/deep web, forum, pazar, ransomware | Kısmi: P05 saklı RansomLook/ThreatCluster iddialarını; P11 ise ayrı AIL 7.x tracker zarfını aynı kuruluş/tedarikçi kanıt, inceleme, değişiklik ve alarm zincirine bağlar. AIL motor bağlantısı hazırdır fakat gerçek AIL kurulumu, seçilmiş yasal forum/pazar/Tor kaynağı ve canlı olay kabulü açık; kamu ransomware kapsamı bütün dark web değildir. | P05 + P11 teknik motor; OP canlı AIL/kaynak açık |
| A03 | Paste ve GitHub/GitLab secret/kod izlemesi | Kısmi: 0.180.0 toplama, Betterleaks, maskeli kalıcı kanıt, insan kararı, izleme ve firma JSON/vaka/rapor bağlantısı var. Kamu keşfi canlı denendi; hesaplı kod araması/Pastebin ve Linux kabulü açık. | P01 |
| A04 | Telegram/Discord/IRC kanal izlemesi | P02 adaptörleri, erişim profilleri, mesaj penceresi/geçmiş cursor ve kontrollü testler var. Telegram/Discord/IRC için hesap/kanal canlı kabulü açık; bütün satır tamamlandı sayılmaz. | P02 |
| A05 | Honeypot ve sinkhole ham telemetrisi | Kısmi: P12, `xti-sensor-v1` ve güvenli Cowrie JSONL sonucunu ham parola/komut saklamadan kuruluş kapsamlı sürümlü kanıta alır; arama, insan incelemesi, P07 alarmı ve vaka akışı hazırdır. Gerçek sensör/sinkhole ağı işletimi, güvenli aktarım ve canlı kabul tamamlanmadı. | P12 teknik motor tamam; SP/OP canlı altyapı açık |
| A06 | Malware sandbox ve örnek analizi | Kısmi: P12, ayrı CAPE ortamında tamamlanmış `report.json` içindeki izinli hash, davranış özeti ve ağ IOC'sini alır; XTI örnek, PCAP, bellek veya ham rapor saklamaz ve malware çalıştırmaz. Gerçek yalıtılmış CAPE işletimi ve canlı rapor kabulü açık. | P12 teknik motor tamam; SP/OP canlı sandbox açık |
| A07 | Ticari/üçüncü taraf feed ve normalizasyon | Kısmi: P09 kontrol düzlemi P10–P12 eklemeleriyle 55 connector'ü tip, dil/bölge, erişim, hak, kota, retry/hata ve zorunlu provenance manifestinde standartlaştırır. Lunar aktif/anahtarsız, AIL koşullu/yereldir. Veri tabloları fiziksel olarak birleşmez; her yeni feed'in canlı toplama, saklama, inceleme ve müşteri gösterim kabulü ayrıca gerekir. | P09 temel; P10/P11/P12 yeni kaynaklar; P13–P15 ertelenmiş sırada |
| A08 | Phishing kit, sahte domain, typosquat | Kısmi: domain/isim/metin/logo/statik sayfa karşılaştırması, form/ortak şablon ipucu ve inceleme/izleme kanıtı var. Kit indirme/çalıştırma ve aktör atfı yok; benzerlik taklit hükmü değil. | P03 |
| A09 | Sahte mobil uygulama / mağaza taraması | Seçili Apple/Google bölge araması, kimlikle yeniden kontrol, yayıncı farkı, değişmez kanıt ve insan incelemesi uygulandı/canlı denendi. Bütün mağaza kapsamı veya otomatik sahte hükmü yok; ticari koşullar/Linux açık. | P03 |
| A10 | Credential leak toplama | Kısmi: P05 XposedOrNot verified-domain sonucunu maskeli alır ve açık parola kontrolü geçmiş oluşturmaz. P11 Lunar, bireysel credential/PII almadan son 12 aylık employee/client ve breach/infostealer toplu sayılarını canlı sağlar; AIL zarfı `credential_listing` iddiasını içeriksiz taşıyabilir. XposedOrNot canlı domain kabulü, gerçek AIL kaynağı ve ham stealer-log sağlayıcısı açık; credential denenmez. | P05 + P11 teknik motor; OP canlı kaynaklar açık |
| A11 | Sosyal mühendislik, itibar, yönetici taklidi | Kısmi: firma içeriği, marka/kişi kimliği, sosyal karşılaştırma, bayi/parodi/ilgili-belirsiz incelemesi ve tekrar izleme var. SecureHup sosyal erişimi kısmi; gerçek VIP canlı kabulü yapılmadı. Geniş itibar sınıflaması tamam değil. | P02, P03 |
| A12 | Tedarikçi/üçüncü taraf ihlal haberleri | Mevcut kaynaklarla sınırlı; P02 seçili yayın/kanalları, P10 Bluesky genel metin gönderilerini açık tedarikçi kimliği, inceleme, değişiklik, vaka ve ortak rapora bağlar. Kaynak iddiası doğrulanmış ihlal değildir. | P02, P05, P10 |
| A13 | RU/ZH/AR/TR/PT dahil çok dilli toplama | P02 Unicode/alternatif isim, P09–P12 zorunlu dil/bölge manifesti ve Bluesky `lang` filtresi vardır; TR/RU/ZH/AR/PT için40 etiketli eşleşme örneği bulunur. P11 AIL zarfı çok dilli kaynak metaverisini kaybetmez, fakat bu dillerde gerçek yeraltı kaynağı/corpus canlı kabulü yoktur; çeviri ayrıdır. | P09/P10 temel; P11 teknik zarf; OP canlı kaynaklar; P15 çeviri |
| A14 | CVE/NVD, Exploit-DB, EPSS | Eski kapsam: CVE/NVD/KEV/EPSS kodu korunuyor; Exploit-DB yok. Kullanıcı kararıyla aktif planda değil. | SP (bekleyen kapsam kararı) |

### B — İşleme ve zenginleştirme (8)

| ID | Kullanıcının gereksinimi | Başlangıç durumu ve açık parça | Yol |
|---|---|---|---|
| B01 | IOC normalizasyonu / otomatik STIX 2.1 | Kısmi: IOC normalizasyonu ve sınırlı dışa aktarım var. Genel nesne/ilişki dönüşümü ve içe alma için çift yönlü kabul eksik. | P04, P06 (geniş STIX bekler) |
| B02 | Tekilleştirme / entity resolution | P04 saklı CTI içinde aynı tür ad/alias benzerliğini, CTI–ATT&CK kimlik adayını, sürümlü kanıt ve `same_entity`/`different_entity` incelemesini sağlar; kayıtları otomatik birleştirmez. Genel çok dilli semantik çözümleme AI kapsamında kalır. | P01, P02, P04; AI |
| B03 | Kaynak güvenilirliği / confidence | P04; firma profilinde kaynak reliability/bağımsızlık grubu, kaynak confidence, günlük tazelik ve destek sayısını açıklanabilir inceleme skorunda birleştirir. İnsan sonuçlarını gösterir ama güveni otomatik öğrenip değiştirmez. | P04 tamam; AI/J04 genişlemesi ayrı |
| B04 | Otomatik MITRE ATT&CK TTP eşleme | P04 açık teknik kimliğinden veya insanın kabul ettiği CTI–ATT&CK kimliği + resmî `uses` ilişkisinden kanıtlı teknik adayı üretir. Otomatik gerçek değildir; genel serbest metin/LLM eşlemesi bekler. | P04 tamam; AI isteğe bağlı/bekleyen |
| B05 | Aktör kümeleme ve attribution | P04 açık attribution ilişkisi veya çoklu kanıt/bağımsız kaynakla açıklanabilir aday üretir; tek ortak IP'yi reddeder, karşı sınırları ve insan kararını korur. Otomatik aktör hükmü yoktur. | P04 tamamlanan motor kapsamı |
| B06 | AI destekli otomatik özet | Yok; LLM ertelendi. Özgün kanıta bağlı özet ve kaynak sadakati kabulü gerekli. | AI |
| B07 | Çoklu dil çeviri | Yok. Özgün/çevrilmiş metin ve sürüm korunmalı; dil başına anlam/isim kaybı ölçülmeli. | AI |
| B08 | Coğrafi/sektörel otomatik etiket | P04 kontrollü TR/EN sözlük ve olumsuzluk kontrolüyle özgün alıntılı `source_claim` adayı üretir; gerçek köken/hedef ilan etmez. Genel çok dilli sınıflandırma/çeviri AI kapsamında kalır. | P04 motor kapsamı tamam; AI genişlemesi ayrı |

### C — Analiz (8)

| ID | Kullanıcının gereksinimi | Başlangıç durumu ve açık parça | Yol |
|---|---|---|---|
| C01 | ASM ve müşterinin asset envanteri | Var, kayıtlı domain/yüzey kapsamında. Yeni envanter bağlantıları ve sahiplik belirsizliği aynı kanıt modeline bağlanmalı. | P04, P06 |
| C02 | Müşteriye özel risk önceliği | P04 tam kuruluş domain/alt-domain/URL IOC bağı ile sürümlü kuruluş önemini açıklanabilir inceleme önceliğine uygular. Skor risk olasılığı değildir; daha geniş etki modeli ayrı kabul ister. | P04 motor kapsamı tamam |
| C03 | Aktör–malware–altyapı–kurban grafı | P04 sınırlı kaynak-iddiası ve aday grafını kanıt hash'i,100 düğüm/200 kenar ve snapshot cursor'uyla sağlar. Etkileşimli görselleştirme tüketici platformda kalır. | P04 motor tamam; PL görsel katman |
| C04 | CVE + exploitability + maruziyet önceliği | Eski zafiyet akışları korunuyor; aktif plan dışında. Doğrulanmış envanter olmadan yeniden açılmaz. | SP (bekleyen kapsam kararı) |
| C05 | Trend/kampanya erken uyarısı | P04 sessiz baseline, sabit durum, eşik üstü değişim ve kaynak/ATT&CK kapsam değişimini ayrı raporlar; yalnız kanıt sürümü değişen aday bildirilir. Bu otomatik incident kararı değildir. | P04 motor kapsamı tamam |
| C06 | IOC/credential aktiflik ve gerçeklik doğrulaması | Kısmi: IOC yaşam döngüsü ve P05 doğrulanmış-domain eşleşmesine P11 toplu Lunar zaman/sayı kanıtı eklendi. Hiçbiri credential denemez veya hesabın/parolanın hâlâ aktif olduğu hükmünü vermez; AIL iddiası insan incelemesi bekler. | P04, P05, P11 |
| C07 | Dark web şirket içeriği tarama/alarm | P05 seçilmiş saklı kaynaklarda, P11 ise Lunar toplu maruziyeti ve AIL metadata zarfında kesin firma/tedarikçi ad-domain eşleşmesi, sessiz baseline, değişmez kanıt, insan kararı, değişiklik, inbox/vaka ve firma JSON zincirini uygular. Gerçek AIL/kaynak canlı kabulü olmadığı için geniş forum/pazar/Tor kapsamı kısmi kalır. | P05 + P11 teknik motor; OP canlı AIL açık |
| C08 | Sahte/klon domain ve sertifika izleme | CT/urlscan geçmişinden aday keşfi, statik klon sayfa/logo kanıtı, tekrar kontrol ve değişiklik bildirimi var. Son canlı arama kaynak penceresiyle sınırlı; sürekli küresel sertifika akışı yok. | P03, OP |

### D — Dashboard ve deneyim (6)

| ID | Kullanıcının gereksinimi | Başlangıç durumu ve açık parça | Yol |
|---|---|---|---|
| D01 | SOC/CISO/yönetim rol dashboard'ları | UI yok. Motorun kanıt ve özet işlemleri, platformun rol/ekran kararına bağlanacak. | PL; ilgili motor paketi |
| D02 | Özelleştirilebilir widget/rapor paneli | Yok. UI düzeni platformda; motor filtreli ve sınırlı sonuç sözleşmesini sağlar. | PL |
| D03 | Doğal dil sorgu / intel copilot | Yok; LLM ertelendi. Firma sınırı, kanıt başvurusu ve izinli sorgu davranışı birlikte kabul edilmeli. | AI, PL |
| D04 | Olay/kampanya zaman çizelgesi | P04 kaynak iddia zamanlarını tur snapshot'ına bağlı, sınırlı ve sayfalı ortak CTI zaman çizelgesi olarak verir. Görsel gezinme platformda kalır. | P04 motor tamam; PL görsel katman |
| D05 | Coğrafi tehdit haritası | P04 özgün alıntıya bağlı coğrafya `source_claim` verisini gerçek konumdan ayırır. Harita çizimi ve doğrulanmış geolocation tüketici platform/veri kaynağında eksiktir. | P04 veri sınırı tamam; PL harita |
| D06 | Tema ve erişilebilirlik | Web UI yok. Terminal kullanımı korunur; web erişilebilirlik/tema kabulü platformda. | PL |

### E — İzleme ve alarm (5)

| ID | Kullanıcının gereksinimi | Başlangıç durumu ve açık parça | Yol |
|---|---|---|---|
| E01 | Domain/marka/IP/kelime/kişi watchlist | P07 yerel motor kapsamı domain/marka/IP/kelime/kişi/tedarikçi hedeflerini saklı kayıt ailelerinde birleştirir. P11 domaini Lunar yenilemesine ve ad/domaini AIL eşleşmesine bağlar; kaynak yenileme ilgili collector'da kalır. | P07 motor tamam; P11 kaynakları bağlandı; yeni kayıt ailesi geldikçe açık adaptör kapsamı |
| E02 | Email/SMS/Slack/Teams/webhook/push | Kısmi inbox ve imzalı webhook var. Kanal aboneliği, gerçek alıcı kabulü ve teslim takibi eksik; e-posta/SMS bekler. | P06, PL |
| E03 | Alarm eşik/öncelik/yanlış alarm ayarları | P07 added/updated/removed seçimi, minimum değişiklik, öncelik, sessiz baseline, sürümlü politika ve useful/not_useful/uncertain geri bildirimini ortaklaştırır. P11 kaynak iddiasını otomatik incident yapmadan mevcut insan incelemesine sokar. Öncelik risk olasılığı değildir. | P07 motor tamam; P11 aynı karar sınırını kullanır |
| E04 | Gerçek zamanlı streaming/alarm | Periyodik/kuyruklu temel var; genel streaming yok. Olay hızı/gecikme hedefi, geri basınç ve yeniden oynatma kabulü gerekli. | OP; ilgili kaynak paketi |
| E05 | Zamanlanmış tarama raporları | P07 politika aralığı, due listesi, not-due çiti, idempotent çalışma, kesinti recovery ve birleşik rapor sözleşmesini tamamlar. Gerçek platform scheduler, kaçırılmış iş işletimi ve alıcı teslimi ayrıdır. | P07 motor desteği tamam; OP/PL işletim açık |

### F — Entegrasyon (8)

| ID | Kullanıcının gereksinimi | Başlangıç durumu ve açık parça | Yol |
|---|---|---|---|
| F01 | REST / GraphQL | Sürümlü JSON motor işlemleri var; HTTP sunucusu yok. Tüketici ekip servis ve auth katmanını yapacak. | PL; ilgili motor paketi |
| F02 | STIX/TAXII ve MISP | Kısmi STIX IOC çıktısı/MISP warninglists var. Genel nesne alışverişi, TAXII ve MISP olay eşitlemesi yok; geniş kapsam ertelendi. | P06 |
| F03 | Splunk/Sentinel/QRadar | Hazır bağlayıcı yok. Kullanıcı P06'da haricî bağlayıcı maddesini kapsamdan çıkardı; ileride açılırsa her alıcı için alan eşleme, tekrar/teslim ve sorgulanabilir kayıt kabulü gerekir. | Kullanıcı kararıyla beklemede; PL |
| F04 | SOAR/XSOAR playbook tetikleme | Yok. Kullanıcı P06 haricî bağlayıcı kapsamından çıkardı; genel webhook kabul sayılmaz. | Kullanıcı kararıyla beklemede; PL |
| F05 | Jira/ServiceNow | Yok. Kullanıcı P06 haricî bağlayıcı kapsamından çıkardı; ileride vaka–ticket kimliği ve kapanış eşitlemesi ayrı kabul ister. | Kullanıcı kararıyla beklemede; PL |
| F06 | EDR/Firewall otomatik engelleme | Yok; mevcut hedef dışında. Gerekirse ayrı kullanıcı/ürün kararı ve geri alma sözleşmesi ister. | DIŞ |
| F07 | Webhook/no-code otomasyon builder | Kısmi imzalı teslim var. Tetikleyici/abonelik/yürütme motoru ile görsel builder ayrı eksik. | P06, PL |
| F08 | SSO/SCIM | Yok. Kullanıcı/kimlik yönetimi tüketici platformda; motor gelen güvenilir firma bağlamını korur. | PL |

### G — Aksiyon alınabilirlik (5)

| ID | Kullanıcının gereksinimi | Başlangıç durumu ve açık parça | Yol |
|---|---|---|---|
| G01 | Phishing/app/sosyal takedown servisi | P06 yerel motor kapsamı tamamlandı: uygun vaka kanıtından taslak, katı insan onayı, dış başvuru referansı ve sonuç olay zinciri. Otomatik gönderim bilinçli olarak yoktur; gerçek portal/hukuk yetkisi işletme sorumluluğudur. | P03 + P06 tamamlanan motor kapsamı |
| G02 | Case/incident management | Motor vaka/görev/kanıt/geçmişi P06 runbook, paket ve takedown ile kullanılır. Ekip atama/SLA/rol UI'si tüketici platformda kalır. | Motor desteği tamam; PL açık |
| G03 | Playbook/runbook önerileri | P06'da kanıt türüne uygun sürümlü, deterministik plan; plan SHA çiti; atomik/idempotent vaka görevi ve uygulama makbuzu tamamlandı. | P06 tamamlanan motor kapsamı |
| G04 | PDF yönetici + CSV/JSON/STIX rapor | P06'da aynı donmuş vakadan teknik JSON, yönetici HTML, kanıt CSV, isteğe bağlı ağsız PDF ve hash manifesti; IOC için CSV/JSON/STIX tamamlandı. Geniş STIX/TAXII ayrı ertelenmiştir. | P06 tamamlanan motor kapsamı |
| G05 | Toplu IOC export/import | P06'da32 MiB/50.000 kayıt sınırlı kesin CSV/JSON/XTI-STIX önizleme, çelişki reddi, atomik import, makbuz/idempotency ve üzerine yazmasız export tamamlandı. | P06 tamamlanan motor kapsamı |

### H — Platform ve mimari (7)

| ID | Kullanıcının gereksinimi | Başlangıç durumu ve açık parça | Yol |
|---|---|---|---|
| H01 | Multi-tenant/MSSP/white-label | Kısmi firma alanı/iş ayrımı var. MSSP yönetimi ve white-label platformda; motor yük/izolasyon kabulü sürer. | OP, PL |
| H02 | On-prem / air-gapped | Kısmi yerel Linux ve saklı veride çevrimdışı kullanım var. Tam çevrimdışı kurulum/güncelleme ve müşteri dağıtımı bekleyen ürün kararı. | OP (bekleyen karar) |
| H03 | Çoklu bölge cloud | Yok. Bölgesel yerleşim, çoğaltma, kurtarma ve kayıp/gecikme hedefleriyle işletim kabulü gerekir. | OP, PL |
| H04 | Petabyte veri gölü/arama | Yok. İş yükü ve performans hedefi olmadan ölçek iddiası olmaz; depo/arama ve kapasite kabulü ayrı proje. | OP |
| H05 | Konfigüre retention/arşiv | P08'de P07 izleme ve P12 telemetri gövdeleri için kuruluş bazlı süre/parti, plan, hold, aktif vaka koruması, yedekli kayıpsız arşiv/restore tamamlandı. Tüm diğer kayıt aileleri, otomatik mantıksal silme ve haricî soğuk depo açık. | P08 iki aile tamam; OP genişleme |
| H06 | RBAC/ince yetkilendirme | Firma sınırı var; kullanıcı yetki motoru yok. Platform rol kararını, motor veri/iş kapsamı kontrolünü sağlar. | PL, OP |
| H07 | Kim neyi görüntüledi/değiştirdi audit | P08 retention politika/hold/archive/restore/recovery yazmaları aktör/gerekçe ve hash zinciriyle izlenir. Güvenilir oturum kimliği, platform geneli yazma ve okuma audit'i hâlâ eksik. | P08 teknik dilim; OP, PL açık |

### I — Uyumluluk ve lokalizasyon (5)

| ID | Kullanıcının gereksinimi | Başlangıç durumu ve açık parça | Yol |
|---|---|---|---|
| I01 | Çok dilli UI | Yok. Platform i18n; motor kararlı durum kodu ve çevirilebilir kullanıcı metni sözleşmesi sağlar. | PL; ilgili motor paketi |
| I02 | Veri yerleşimi | Ürün politikası yok. Saklama bölgesi ile dış kaynağa/modelle veri aktarımı ayrı kontrol edilmeli. | OP, PL |
| I03 | GDPR/KVKK/CCPA veri işleme ayarları | P08 amaç/dayanak, kuruluş saklama süresi, explicit hold, yedek ve kapalı otomatik silme sağlar. P11 Lunar'da bireysel PII almaz; AIL'de ham içerik/adres/credential kabul etmez. Erişim/aktarımı, veri sahibi talepleri, bölge ve hukuk onayı platform/işletimde açık; uygunluk iddiası yok. | P08/P11 teknik destek; OP, PL ve hukuk onayı açık |
| I04 | Bölgesel/dil bazlı feed seçimi | P09–P12 bütün55 connector'de zorunlu dil/bölge alanı ve katalog filtresi sağlar; Bluesky seçilmiş dili gerçek aramaya aktarır, AIL `mul/global` olarak gerçek kaynak dili iddia etmez. Bölgesel kaynak paketleri/canlı kapsam tamamlanmadı;40 çok dilli eşleştirme örneği kaynak erişimi değildir. | P09 kontrol düzlemi; P10 sosyal; P11 yeraltı teknik sınırı; P12 yerel telemetri; OP canlı kaynaklar |
| I05 | Para birimi/fatura formatı | Yok; motor işi değil. Platformun ticari işletim sorumluluğu. | PL |

### J — Güven ve doğrulanabilirlik (4)

| ID | Kullanıcının gereksinimi | Başlangıç durumu ve açık parça | Yol |
|---|---|---|---|
| J01 | Bulgu kaynağına izlenebilirlik | Mevcut kaynak izi korunur. P08 arşiv binding/hash ve restore'u; P09 bütün connector manifestlerinde provenance alanlarını tanımlar. P10 Bluesky; P11 Lunar kaynak/zaman/snapshot özeti ile AIL sürüm/commit/object/evidence hash'i ve hash-zincirli tur geçmişiyle yükümlülüğü doğruladı. | P08–P11 doğrulandı; tüm paketlerde sürekli |
| J02 | XAI / skor ve alarmın nedenini açıklama | P04 her adayda kural, sinyal, özgün kaynak/alinti, skor bileşeni, sınırlama ve otomatik-hüküm-yok bilgisini verir. Gelecek AI çıktısı aynı kanıt yükümlülüğüne tabidir. | P04 kurallı açıklama tamam; AI ayrı |
| J03 | İnsan onayı/etiketleme | P04 kanıt ve gözlem sürümüne bağlı karar, değişince yeniden inceleme, değişmez geçmiş, inbox ve vaka kopyasını ekledi. P11 toplu maruziyet ve yeraltı iddiasını aynı yaşama bağladı; otomatik incident yoktur. | P04/P11 ve mevcut paketlerde var; tüm paketler |
| J04 | Faydalı/faydasız geri bildirim → iyileştirme | P04 kaynak bazında kabul/ret/belirsiz sonuçlarını gösterir fakat reliability'yi sessizce değiştirmez. Denetimli kalite ölçümü/model güncellemesi ayrı ve hâlâ eksiktir. | P04 görünürlük tamam; AI/OP öğrenme ayrı |

### K — Gelişmiş modüller (6)

| ID | Kullanıcının gereksinimi | Başlangıç durumu ve açık parça | Yol |
|---|---|---|---|
| K01 | AI phishing / deepfake ses-video | Yok. Ayrı örnek/veri/uzman model ve yanlış karar ölçümü gerekir; sıradan LLM özeti bu yetenek değildir. | SP, AI |
| K02 | S3/Blob, API key, container/registry | Özel cloud modülü yok. P01 secret maruziyetinin bir parçasını sağlar; cloud envanteri/yapılandırma/registry kabulü ayrı kalır. | P01, SP |
| K03 | SBOM ve bağımlılık zafiyet istihbaratı | Genel SBOM akışı yok; eski paket kodu var. Format/bağımlılık/güncelleme ve zafiyet kapsamını açma kararı gerekli. | SP (bekleyen kapsam kararı) |
| K04 | OT/ICS/IoT, Shodan benzeri maruziyet | Özel modül yok. Yetkili port kontrolü kapsamlı cihaz telemetrisi değildir; kaynak ve cihaz sınıflandırması gerekir. | SP |
| K05 | Cüzdan ve ransomware ödeme takibi | Yok. Zincir/veri sağlayıcısı, işlem ilişkisi ve atıf belirsizliği ayrı analiz modülü. | SP |
| K06 | Otomatik pentest/istismar doğrulama | Mevcut hedef dışında. Yetkili Nmap ve seçili kontroller korunur; genel saldırı/istismar otomasyonu açılmaz. | DIŞ |

## 8. İlk ticari teslim ve dış bağımlılıklar

Altı paketin, bütün uzman modüllerin veya 76 satırın tamamı bitmeden
hiçbir kullanım olamaz diye bir koşul yoktur. Ticari sürümün adı ve
vaat ettiği satırlar açık seçilir; yalnız o kapsamın bütün kabulü tamamlanır.
“Tam kurumsal XTI”, “OpenCTI ile aynı kapsam” veya “tüm internet” gibi
genel tamamlanma iddiaları bu planla yapılmaz.

Paket kapanışına yakın yeni zorunlu işler üretmemek için kurulum, bağımlılık,
veri hakları, kapasite ve platform sözleşmesi işin başında ele alınır.
Yeni kanıtla ortaya çıkan hata saklanmaz; etkisi ve düzeltmesi ilgili
pakette kaydedilir. Yeni ürün fikri ise tamamlanan teslimi sürekli yeniden
açmaz; aşağıdaki satır veya açıkça eklenen yeni gereksinim altında tutulur.

Mevcut dış girdiler yeni planla kapanmaz: Bright Data canlı hesabı/kabulü
N-034, gelişmiş Nmap yetkili hedef kabulü N-005, ticari kaynak koşulları
N-039 ve bağlantılı notlar. Bunların bazıları ilk ticari profilde kaynak
seçimini etkiler. Önceden tamamlanan Tavily kabulü yeniden eksik gösterilmez.

**Bu planlamanın kapanışı:** 76/76 madde kaydedildi; önerilen sıra,
sorumluluk, ertelemeler ve tam teslim ölçütleri belirlendi. Yeni özellik
uygulaması ilk planlama adımında değişmedi. Kullanıcı P01'e başlamayı
onayladı; kaynak/bileşen ön incelemesi, uygulama ve kabul aynı paket içinde
yürütülüyor. Rutin devam onayı istenmez. Ön inceleme
teknik seçimi, erişim ihtiyacını ve ölçüm eşiklerini somutlaştırır; tek
başına P01'in tamamlanması değildir.
