# P03 — Marka taklidi kanıtı

21 Kasım 2026. **Durum: uygulama, macOS kurulum, veri geçişi, kapasite
ve yerel regresyon kabulü tamam.** SecureHup canlı
çalışması kullanılabilir kanıt üretti; sosyal erişim eksikleri nedeniyle
son durum `partial`. Linux ve ticari kaynak kararları ayrı açık.
Kullanıcı geniş marka korumasını bekletme kararını kaldırıp P03'ü seçti.
Canlı marka SecureHup / securehup.com; gerçek yönetici/VIP adı verilmedi.
P01/P02'nin açık erişim ve Linux kabulü maddeleri korunur.

## Kapsam ve kullanıcı sonucu

Ana gereksinimler A08/C08 (domain, sertifika, kopya sayfa ve phishing
sayfası belirtileri), A09 (mobil uygulama adayları), A11 (marka/sosyal
profil/yönetici taklidi). B02/E01/E05/G02/J01/J03 için tekilleştirme,
tekrar izleme, insan kararı, vaka ve kaynağa izlenebilirlik bağları gerekir.
G01'in kanıt hazırlığı desteklenir; başvuru gönderimi P06'da kalır.

Kullanıcı markanın adını ve resmî domainini tanımlar. Motor internetten
ve mevcut kayıtlarından adayları toplar; resmî sayfa/logo/profil/uygulama
kimlikleriyle karşılaştırır. Her aday için kaynak, zaman, ad/domain/metin/
görsel benzerliği, belirsizlik ve karşı kanıt birlikte gösterilir.
İnceleme kararları: resmî, yetkili bayi, parodi, ilgisiz, taklit şüphesi,
kanıtla doğrulanmış taklit veya belirsiz. Otomatik eşik insan kararı değildir.

Kapsam kaynak pencereleriyle sınırlıdır: App Store ve Google Play araması,
seçili sosyal platformlar, CT/urlscan geçmişi ve açık HTTPS sayfaları.
Kit benzerliği, ortak sayfa/form/script parmak izleriyle gösterilir;
kit yazılımı indirme/çalıştırma veya aktör atfı yapılmış sayılmaz.
APK/IPA indirme ve zararlı yazılım çalıştırma bu markayla karşılaştırma
paketinin kapsamı değildir. Yönetici modeli gerçek kişi verilene kadar
kontrollü örneklerle kabul edilir; gerçek VIP kapsandı denmez.

## Seçilen araçlar ve kaynaklar

- Mevcut Maigret/Sherlock ve bağımsız profil sayfası kontrolü: sosyal
  keşif. Aynı kullanıcı adı otomatik marka aidiyeti değildir.
- [Playwright](https://playwright.dev/python/docs/network): kontrollü
  Chromium sayfa görüntüsü. Ağ tarayıcıya serbest bırakılmaz; yalnız GET
  istekleri sınırlı, DNS sonrası adresi sabitlenen taşıyıcıdan geçer.
  JavaScript/oturum/giriş/form gönderimi yok; bu görünüm statik sayfa
  görünümü olarak etiketlenir. Dinamik uygulamalar eksik gösterilir.
- [Pillow](https://github.com/python-pillow/Pillow) ve
  [ImageHash](https://github.com/JohannesBuchner/imagehash): boyut/piksel
  sınırı, güvenli PNG ve görsel parmak izi. Boş/tek renkli görselden yüksek
  benzerlik hükmü çıkarılmaz; logo ve sayfa benzerliği ayrı değerlendirilir.
- [Apple Search API](https://performance-partners.apple.com/search-api):
  mağaza/bölgeye göre uygulama kimliği, yayıncı ve kaynak bağlantısı.
- [google-play-scraper](https://github.com/JoMingyu/google-play-scraper):
  açık Google Play sonuç ayrıştırması. Resmî Google arama API'si değildir;
  yanıt değişimi/erişim engeli boş başarı değil kaynak hatasıdır.
- Mevcut CT ve urlscan adaptörleri: geçmiş domain keşfi; yeni dış tarama
  talebi oluşturulmaz. Aday sayfaya yalnız sınırlı açık HTTPS okuması yapılır.

API hesabı gerektirmeyen başlangıç seçildi. Tavily/Bright Data kullanımı
ayrı açık seçimdir; yeni ücretli çağrı varsayılan değildir. Kaynakların
veri hakları yazılım lisansından ayrıdır; yeni ticari değerlendirme N-046.

## Tam teslim zinciri

1. Sürümlü marka kimliği: domain, logo bağlantısı, resmî sosyal hesap,
   uygulama/yayıncı ve isteğe bağlı yönetici. Değişiklik eski kanıtı değiştirmez.
2. İnternet keşfi ve önceki adayların yeniden kontrolü; kaynak başına bütçe,
   pencere, sayfalama, güncel/geçmiş ayrımı, erişim ve kaynak hataları.
3. Sayfa/metin/form/ortak dosya parmak izi, logo ve sabit görünüm görüntüsü;
   kaynak/görsel SHA256, araç sürümü ve eksik kapsam.
4. Değişmez kanıt, ayrı güncel aday, kanıt/gözlem sürümüne bağlı karar;
   bayi/parodi ayrımı insan incelemesiyle; çelişki görünür.
5. İlk sessiz ölçüm, değişen kanıt/karar ihtiyacı, ortak inbox ve vaka.
   Kaybolan veya erişilemeyen sayfa otomatik temizlenmiş sayılmaz.
6. Terminal, firma JSON, kuruluş görünümü, kalıcı iş kuyruğu, iptal ve
   kesinti kurtarma. Aynı istek yeni ağ veya çift kayıt üretmez.
7. Sabit sürüm/hash kurulum, açık yedekli şema90→91, gerçek eski üreticiyle
   geri dönüş, kapasite/kabul testleri, güncel kullanım ve notlar.

## Koddan önce belirlenen kabul ölçütleri

- İki firma, firma başına 10.000 saklı aday, en az 30 değişmeyen tur;
  eski karar/kanıt korunur. Tek tur bütçesi saklı toplam tarihçe tavanı değildir.
- Değişmeyen turlarda yeni kanıt/görsel gövdesi 0. Bir aday değiştiğinde
  tek yeni kanıt/değişiklik; eski insan kararı korunur ama güncel sayılmaz.
- 40 adet 100 kayıtlık firma JSON okumasında p95 <2 sn; sentetik süreç
  RSS <256 MiB. Tarayıcı ayrı süreç/bellek bütçesiyle ölçülür.
- 40 etiketli domain/metin/görsel/uygulama/kişi örneği: olumlu, benzer ama
  ilgisiz, aynı şablon, boş görsel, resmî/bayi/parodi ve çelişkili durum.
  Benzerlikten otomatik sahte hükmü yok; bu örnek kümesi internet doğruluk
  yüzdesi olarak sunulmaz.
- SSRF/yönlendirme, görsel boyut bombası, zaman/istek/byte bütçesi,
  kaynak hatasında eski kanıt, aynı çağrı, kayıt sonrası kuyruk kesintisi,
  farklı firma/sürüm, yedek ve eski kodla dönüş ayrı test edilir.
- Canlı SecureHup resmî sayfa kontrolü ve mağaza sorguları; bilinen yayıncı
  kontrolü ayrı etiketlenir. Gerçek taklit bulunmaması başarısızlık değildir;
  kontrollü örnek hiçbir zaman gerçek saldırı bulgusu olarak gösterilmez.

## Açık bağımlılıklar

Tarayıcı işletim sistemi bağımlılıkları, kaynak erişim engelleri, gerçek
VIP kimliği, kaynakların ticari saklama/gösterme kararları ve Linux kabulü
başlangıçtan itibaren ayrı izlenir. Uygulama ve kanıt oluşmadan paket veya
bütün A08/A09/A11/C08 satırları tamamlandı olarak işaretlenmeyecek.

## Teslim edilen akış — 0.182.0

Yukarıdaki yedi adım uygulandı. Terminalde `brand protection`, engine ve
firma JSON'unda `brand.protection.*`, ortak kalıcı işlerde
`brand-protection` kaynağı kullanılır. Şema91, kaynak işi10 (eski1–9
okunur), ortak kuyruk4 ve dış JSONv1. Ayrıntılı komutlar ve örnekler
[kullanım belgesindedir](../BRAND_PROTECTION.md).

Kanıtlar, insan kararları ve görseller değişmez geçmiş olarak saklanır.
Kaynak hatası eski sonucu silmez. Resmî referans alınamadığında eski
karşılaştırma eksik referansla değiştirilmez. Aynı istek makbuzu tekrar
kullanılır; kayıt sonrasında iş kuyruğu kesilmesi yeni ağ çağrısına yol
açmaz. İlk tur sessizdir; değişiklikler ortak inbox ve vakaya bağlanır.
Kuruluş görünümünde marka adayları ve son kaynak durumu birlikte okunur.

Liste sayfaları en çok100 kayıt ve2MiB yanıt bütçesiyle ilerler; kısa
sayfada bile `next_after` varsa devam edilir. Tur bütçesi, toplam saklı
aday sayısının sınırı değildir. İnsan kararı kanıt/gözlem sürümüne bağlıdır;
önceki içeriğe dönüş eski kararı kendiliğinden güncel yapmaz.

### Kabul edilen kodun kimliği

- Temel commit: `2000b2bc12843b12c44bff72282966d8c00333eb`.
- Çalışma ağacı sürümü: `0.182.0`; bu teslim henüz commit/push değildir.
- Son kaynak/kurulum/kabul SHA256:
  `4e004b3803d6809ad1f8edcd994d3cae4b667a046c6bf00cb629d7af3e74ac20`.
- Kimlik kapsamı: `scripts/protection_acceptance_identity.py` tarafından
  listelenen838 kaynak, gereksinim, kurulum ve kabul dosyası. Testler ve
  belgeler bu SHA'ya dahil değildir; test çalıştırmaları ayrıca belirtilir.
- Ortam: macOS26.6.2 arm64, Python3.13.3, 21 Kasım2026.

### Gerçek araç ve temiz kurulum

Pillow13.0.0, ImageHash4.3.2, Playwright1.65.2, Chromium revision1255 ve
google-play-scraper1.2.7 kuruldu. Mevcut Maigret/Sherlock/profil kontrolü
ve Betterleaks1.10.1 kullanılır. Python wheel sürümleri/resmî PyPI
SHA256'ları `requirements/brand-protection.txt` içinde sabittir.

Temiz geçici repo kopyasında normal `./setup` geçti; görsel kitaplıklar,
mevcut sosyal/kod/kanal araçları ve gerçek ağsız Chromium kontrolü birlikte
doğrulandı. Log: `/tmp/xti-p03-clean-install.log`. Tarayıcı kurulumunda
kesinti/geri alma, eski kurulumun korunması ve yeniden kontrol ayrı
test edildi. Chromium için ayrı upstream arşiv SHA pini yoktur; SDK
revision, resmî TLS indirme, yerel binary SHA makbuzu ve ağsız görüntüleme
kontrolü vardır. Bu ayrım [N-046](../../NOTES.md) içinde açık tutulur.

Google ayrıştırıcısının import sırasında TLS varsayılanını değiştirdiği
gerçek paket incelemesinde görüldü. Ayrıştırıcı yalnız ağsız çocuk süreçte
çalışır; motorun HTTPS doğrulamasına taşınmaz. Canlı görüntüde bulunan
ImageHash renk izi uzunluğu sorunu düzeltildi ve gerçek Pillow/ImageHash
üzerinden regresyon kontrolü eklendi. İlk başarısız deneme kabul sayılmaz.

### Veri geçişi, kurtarma ve birikimli kapasite

Son kabul: `/tmp/xti-p03-delivery-final.json` ve aynı adlı `.log`.
`scripts/check-protection-delivery.py`,
`1e9cd488f1d164e51075d12a88a38acd8c5ff31303d45e94f8ad789da33be176`
kaynak kimliğiyle çalıştırıldı. Sonrasında yalnız sayfa/kaynak adaptöründe
referans logo seçimi daraltıldı; veri modeli, karşılaştırma kuralları,
listeleme, geçiş ve kuyruk davranışı değişmedi. Bu nedenle birikimli
kapasite ölçümü yinelenmedi; değişen adaptör hedefli/canlı yeniden sınandı.

| Kontrol | Ölçülen sonuç |
|---|---|
| Gerçek eski üretici | P03 öncesinde dondurulmuş0.181.0 / şema90 kaynak ağacı |
| Eski üretici kaynak SHA | `8a3ecd29fc0a9a185f741174d59a2fec47aaaad832b44fe531e54e51eac86ea4` |
| Açık geçiş90→91 | 197 tablo,41 kayıt ve rowid'ler korundu; P01/P02/grup/vaka kayıtları dahil |
| Geri dönüş | Eski kod91'i reddetti; özgün yedekle eski kod açıldı; yeni yedek/geri yükleme de geçti |
| Saklı aday | İki firma ×10.000 =20.000 |
| Değişmeyen izleme | Firma başına30 tur ×10 parti; yeni kanıt ve yeni görsel gövdesi0 |
| Tek değişiklik | Firma başına1 yeni kanıt/1 bildirim; eski karar korundu, yeniden inceleme açıldı |
| Firma JSON okuması | 40 gerçek platform çağrısı,100 kayıtlık sayfa; p95 **0,205478 sn** |
| Ana süreç tepe RSS | **101.990.400 byte** |
| Toplam test DB boyutu | **50.044.928 byte** |
| Kapasite çalışma süresi | **267,985 sn** |

Bu sentetik toplama/veri/inceleme testi ağsızdır; tarayıcı yükü içermez.
Gerçekten çalıştırılmış eski üretici `/tmp/xti-p03-baseline-0.181.0`
altında dondurulmuştur; PRAGMA sürümü düşürülerek üretilen yapay DB
bu eski üretici kabulünün yerine sayılmadı. Ayrı kesinti birim testi
geçiş ortasında hata enjekte ederek özgün DB ve yedeğin korunduğunu sınar.

### SecureHup canlı kabulü

Son kabul: `/tmp/xti-p03-live-logo-final.json`, veri alanı
`/tmp/xti-p03-securehup-logo-final`; `scripts/check-protection-live.py` ile
21 Kasım2026 09:00:25–09:01:13 UTC, son `4e004b38…` kaynak kimliği.
Marka SecureHup, domain securehup.com,
kişi listesi boş. Sonuç **partial**,48,119 sn,43 ölçümlü HTTPS isteği;
sosyal araçların iç istek sayısı bilinmediğinden toplam ağ sayısı denmez.
Ücretli API çağrısı0.

| Kaynak/kontrol | Gerçek sonuç | Yorum |
|---|---|---|
| Resmî HTTPS sayfa/logo/statik PNG | Tamamlandı | Önceki turdaki PNG açılıp görsel olarak kontrol edildi; son logo kümesinde yalnız favicon/marka logoları var |
| Apple TR araması | Başarılı,0 sonuç | Mağaza penceresi boş; genel güvenlik hükmü değil |
| Google Play TR araması | Başarılı,7 sonuç | Çoğu marka bağı kurulamayan arama sonucu;7 sahte uygulama değil |
| urlscan geçmişi | 1 aday: `app.securehup.com` | Son30 günlük kaynak penceresi; resmî domain kapsamı |
| crt.sh | HTTP404; `not_found` | 09:00:35 UTC isteği0,599 sn; başarılı boş sorgu sayılmadı |
| Sosyal keşif | GitHub, GitLab, Instagram, LinkedIn, X/Twitter için5 profil adayı | Bu turdaki keşif başarılı; hesap aidiyeti doğrulanmış sayılmaz |
| Aday sayfa görüntüsü | 6 deneme; GitHub ek okuması erişilemedi, GitLab404 | Ayrı keşif kanıtı korunur; erişim çelişkisi gizlenmez |
| Kalıcı sonuç | 13 aday,13 kanıt gövdesi,24 ayrı PNG | Taklit kararı verilmedi;75 görsel başvurusu hash/byte olarak doğrulandı |

Önceki `/tmp/xti-p03-live-final.json` turu aynı gün08:42 UTC'de11 aday,
20 PNG/34 ölçümlü istek üretmişti; crt.sh200/boş, sosyal3 aday/kısmi idi.
Son tur onun yerine yazılmadı. İki turun kaynak durumu farklıdır;
crt.sh veya sosyal erişimi kalıcı düzelmiş ilan edilmez. Son referans
kümesinden AWS/Bitbucket gibi iş ortağı logoları çıkarıldı; bunlar sayfa
görünümünde bulunabilir ama markanın kendi logo kanıtı sayılmaz.

Mozilla'nın resmî mobil sayfasının verdiği Firefox Focus kimlikleriyle
Apple ve Google'da ayrı olumlu kontrol yapıldı: her iki kimlik okuması
HTTP200 ve doğru uygulama/yayıncıyla sonuçlandı. Bu kontrol SecureHup
bulgusu değildir; bu ayrı kontrol `/tmp/xti-p03-live-final.json` içinde
kayıtlıdır ve logo seçimi değişikliği mağaza ayrıştırıcısını değiştirmedi.
Önceki bağımsız sosyal denemede görülen profiller son
turda kayboldu diye silinmiş/kapalı ilan edilmedi; farklı turlar birleştirilip
tek eksiksiz canlı sonuç olarak sunulmadı.

Son canlı çalışmanın `getrusage(RUSAGE_CHILDREN)` ölçümü197.918.720 byte'tır.
Bu, aynı anda çalışan bütün Chromium süreçlerinin toplam belleği veya
işletim sistemi seviyesinde zorunlu bellek tavanı değildir. Tarayıcı için
süre, dosya, kaynak ve süreç sonlandırma sınırları vardır; toplam gerçek
sunucu belleği/Linux yük kabulü ayrıca ölçülecektir.

### Test kaydı

Önceki37 P03 testi geçti. Sonradan gerçek vaka bağlama, kesintili şema
geçişi ve kurulum kurtarma kontrolleri eklendi. Karşılaştırma kümesi48
ayrı etiketli durumu, büyük harf/Unicode çeşitleriyle144 alt örneği kapsar.
Bu bir internet doğruluk yüzdesi veya bağımsız gerçek saldırı veri kümesi
değildir. Önce dört P03 modülü44 test/15,580 sn ile hatasız geçti
(`/tmp/xti-p03-final-feature-tests.log`). Logo seçimi düzeltmesinden sonra
P03'ün45 testi ve ortak HTTP/içerik kaynaklarının10 testi birlikte
**55 test/15,738 sn**, hatasız ve atlamasız geçti
(`/tmp/xti-p03-logo-focused.log`).

Tam çalışma `/tmp/xti-p03-full-suite.log`: **3.550 test /2.165,324 sn**.
İlk sonuç3 assertion hatası,6 hata kaydı ve4 Linux atlamasıydı. Hatalar6
benzersiz test metoduna aitti; aynı yükseltme testindeki4 alt senaryo
ayrı hata kaydı üretti. Tespit edilenler:

1. Linux yükseltme kabul yardımcısının sınırı90'da kalmıştı.91'in tam
   incelenmiş vaka DDL'i eklendi; eski satır/rowid/kanıt eşitliği korunur.
   Kabul testi79/80/82/88 yanında89/90 başlangıçlarını da sınar.
2. Eski şema54–62 testinin beklenen yeni tablo kümesinde P03 tabloları yoktu.
3. Platform manifest testinin beklenen ağ işlemleri listesinde
   `brand.protection.run` yoktu.
4. Kurulum sıra testinin beklediği adımlarda `protection-install` yoktu.
5. Kurulum kilidi testi, yeni görsel bağımlılıkları için geçici sanal
   ortam konumu yerine gerçek ortam metadata'sını kullanıyordu; kontrollü
   test verisi düzeltildi. Gerçek kurulum doğrulaması gevşetilmedi.

Bu düzeltmelerden sonra etkilenen beş modül yeniden çalıştı:
**81 test /57,557 sn;79 başarılı,2 Linux'a özgü atlama, hata yok**
(`/tmp/xti-p03-regression-fixes.log`). Linux kabul yardımcısının son
dosya SHA256'sı
`82fa0612283470f3b23e6b31adeb2a761f75af7d62917ef30ea83e560aa4fd22`.

Güncel envanter **3.558 test**. Tam tur başladıktan sonra eklenen8 test
ve son logo seçimi değişikliği55 testlik son özellik paketinde kapsandı.
Sonrasında motor kaynak kodu değişmedi;81 kontrol kabul yardımcısı ve
eski test beklentilerinin düzeltmelerini kapsar. Tam tur yeniden
çalıştırılmadı; bu sonuçlar tek bir hatasız tam koşu gibi sunulmaz.
Python derleme kontrolü, `git diff --check` ve yeni belgelerin yerel
bağlantı kontrolü geçti. Canlı kaydedilmiş sosyal adaylar terminalden de
açıldı (`/tmp/xti-p03-cli-live-results.log`).

### Kapanmayan koşullar

- Ubuntu/Python3.11–3.13 için `.github/workflows/brand-protection.yml`
  hazırlandı; bu çalışma sırasında Linux'ta çalıştırılmadı.
- Gerçek VIP canlı kabulü kullanıcı yalnız markayı seçtiği için yapılmadı.
  Kişi kimliği/kapsamı ve insan incelemesi kontrollü testlerle doğrulandı.
- Sosyal erişim engelleri, JavaScript kapalı statik görünüm, seçili mağaza
  bölgesi/penceresi ve tüm interneti kapsamama açık sınırlardır.
- Görsellerde OCR/secret/kişisel veri maskelemesi yoktur; metin ve URL
  taraması başarısızsa aday gövdesi saklanmaz.
- Mağaza ve sayfa kanıtlarının ticari saklama/gösterme hakları, gerçek
  sunucu kapasitesi ve uzun süreli pilot kabulü kapatılmadı.
- Geniş A08 kit kapsamı, bütün sosyal/VIP kapsamı ve sürekli küresel CT
  akışı bu kabulün sonucu değildir. Ana plandaki birleşik gereksinimler
  bu nedenle bütünüyle tamamlandı olarak işaretlenmez.
