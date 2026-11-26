# P05 — Dark web ve credential kapsamı

22 Kasım 2026; 26 Kasım 2026 bakım kararı. **Durum: seçilmiş kaynak motoru,
yerel kabul ve kapasite kabulü korunuyor. XposedOrNot yeni profil, anahtar,
domain yenileme ve parola yolları 0.195.1/ADR0201 ile kapatıldı; yalnız eski
maskeli kanıt salt okunur. Canlı XposedOrNot kabulü artık bir bağımlılık
değildir. Forum/pazar kaynağı henüz seçilmediği için A02/A10'un bütünü
tamamlanmış değildir.**

## Kullanıcı sonucu ve gereksinimler

P05'in ana gereksinimleri A02, A10 ve C07'dir. A07, A12, A13, C06, E01,
E03, I03, I04, J01, J02 ve J03'ün bu pakete düşen parçalarını destekler.

Hedeflenen kullanım zinciri:

1. Kuruluş ve isteğe bağlı etkin tedarikçiler için sürümlü izleme profili.
2. Saklı RansomLook ve ThreatCluster kanıtlarının tek
   kesitte, kaynak anlamları karıştırılmadan eşleştirilmesi.
3. Tarihî HIBP/XposedOrNot maskeli credential kanıtının provider kimliği ve
   bütünlük zinciri değiştirilmeden salt okunur korunması; yeni credential
   ağı yerine Lunar toplu domain maruziyetinin kullanılması.
4. Kaynak iddiası/credential eşleşmesinin değişmez kanıt, güncel aday,
   değişiklik, insan kararı, ortak inbox ve vaka zincirine bağlanması.
5. İlk sessiz başlangıçtan sonra yalnız yeni/değişen kanıtın bildirilmesi;
   kaynak kesintisinin boş başarı sayılmaması.
6. Aynı servislerin terminal, engine v1, firma platform v1 ve yönetilen
   kaynak işinden kullanılabilmesi.

## Seçilen ve bekleyen kaynaklar

| Kaynak | Durum | Rol | Erişim / hak sınırı |
|---|---|---|---|
| RansomLook API | Seçili ve mevcut entegrasyon canlı | Kamu ransomware kaynak iddiaları | API verisi CC BY 4.0 atıfla; yazılım kodu kopyalanmaz. |
| ThreatCluster public feed | Mevcut kişisel/açık entegrasyon; ticari varsayılan değil | İkinci kamu ransomware görünümü | Ücretli üründe kullanım/yayım yazılı anlaşma gerektirebilir; profil bunu açıkça seçmelidir. |
| XposedOrNot `/v1/domain-breaches/` | Devre dışı; yalnız tarihî kayıt okuma | Eski maskeli credential kanıtının denetimi | Yeni profil, anahtar, ağ çağrısı, canlı/ticari kabul veya müşteri gösterimi yoktur. Provider kimliği yeniden etiketlenmez. |
| XposedOrNot password API | Devre dışı | Yeni rolü yok | Parola, hash veya önek sorgusu yapılmaz; önceki komut üretim yüzeyinden kaldırılmıştır. |
| HIBP P05 kaynakları | Yeni çalışmalarda devre dışı | Yalnız şema93 geçmişini veri kaybı olmadan okuma | Yeni profil/ağ çağrısı yok; eski provider kimliği yeniden etiketlenmez. |
| Genel Tor/forum/pazar crawler | Seçilmedi | A02'nin kapalı kaynak parçası | Kaynak hakkı, kimlik, izolasyon, saklama ve canlı kabul olmadan eklenmez. |
| Stealer-log sağlayıcısı | Seçilmedi | A10/C06 genişlemesi | Kaynak, bütçe, veri minimizasyonu ve yasal amaç kararı gerekir; secret alınmaz. |

## Önceden belirlenen güven sınırları

- Yalnız kuruluş kaydına tam bağlı domain ve açıkça seçilmiş etkin tedarikçi
  kimlikleri değerlendirilir. Aynı adlı bağımsız kuruluş otomatik bağlanmaz.
- Credential sonucu en fazla maskeli hesap, HMAC kimliği ve ihlal adı taşır.
  Parola, token, cookie, session, ham stealer log veya ham e-posta yoktur.
- Credential denenmez; oturum açma, parola sıfırlama, hesap varlığı probe'u,
  satın alma veya kapalı kaynağa izinsiz giriş yapılmaz.
- Ransomware/pazar/forum ilanı doğrulanmış ihlal değildir. Tarihî
  XposedOrNot kaydı da güncel hesap/parola geçerliliğini kanıtlamaz.
- Kaynak başarısızlığı başarılı boş sonuç değildir; son başarılı snapshot
  ve hata ayrı görünür. İlk tur alarm üretmez.
- Salt-okunur engine internete veya anahtar dosyasına erişmez.

## Kabul kartı

- Pozitif, negatif, aynı adlı ilgisiz, Unicode, değişmeyen, değişen, kaynak
  hatası ve eski kanıt senaryoları ayrı etiketli testlerle doğrulanacak.
- Ham alias/API anahtarı SQLite, JSON, terminal, hata mesajı ve git içinde
  bulunmayacak; bozuk/izinleri açık/symlink anahtar dosyası reddedilecek.
- Şema92→94 ve şema93→94 geçişleri yedekli, kesintide atomik ve eski veriyi koruyan biçimde
  sınanacak. Geri dönüş yükseltme öncesi yedekten yeni alana yapılacak.
- Firma yalıtımı, workspace çiti, idempotency, kesinti/recovery, vaka kopyası,
  ortak inbox, backup/restore ve kaynak işi makbuzu test edilecek.
- İki firma için hedef kapasite: firma başına 10.000 güncel aday, en az30
  değişmeyen tur; değişmeyen turda yeni kanıt/değişiklik/bildirim0. 100
  kayıtlık firma JSON sayfası p95<2 sn ve sentetik tepe RSS<256 MiB.
- XposedOrNot yeni ağ yolu bulunmadığı sözleşme ve negatif testlerle
  doğrulanacak; tarihî kayıt silinmeyecek. Forum/pazar kapsamı kaynak
  seçilmeden açık kalacak; kamu ransomware akışı bütün dark web kabulü
  sayılmayacak.

Tasarım kararları: [ADR0189](../decisions/0189-darkweb-and-credential-evidence.md),
tarihî [ADR0190](../decisions/0190-xposedornot-credential-source.md) ve onu
yeni kullanım için değiştiren [ADR0201](../decisions/0201-retire-xposedornot-new-use.md).
Kullanım: [DARKWEB_MONITORING](../DARKWEB_MONITORING.md).

## Uygulanan motor yüzeyi

- `DarkwebService` terminal, engine v1, firma platform v1 ve ortak kaynak
  işinin tek uygulama sınırıdır.
- Şema94; sürümlü profil, dondurulmuş tur, değişmez kanıt, güncel bulgu,
  gözlem/inceleme sürümü, değişiklik, bildirim, tekrar makbuzu ve maskeli
  credential geçmişini ayrı tablolarda tutar.
- RansomLook ve ThreatCluster verisi mevcut doğrulanmış
  yerel snapshot'lardan tek transaction kesitinde okunur; P05 analizi ağ
  çağrısı yapmaz. Kaynakların anlamı birbirine dönüştürülmez.
- Tarihî XposedOrNot adaptör/parser kodu eski kayıt ve geçiş kabulünü
  açıklamak için korunur; üretim composition'ı bu ağ/secret/parola
  adaptörlerini kurmaz. CLI ve platform yeni çağrı sunmaz.
- Eski SQLite/JSON/terminal kaydı yalnız maskeli hesap, kuruluşa özel HMAC
  kimliği, domain ve ihlal adlarını içerir; ham alias daha önce de kalıcı
  katmana girmemiştir.
- Credential run/değişiklik zinciri ve bütün kanıt gövdeleri hash ile
  doğrulanır. Symlink, açık izin, başka kullanıcı ve üzerine yazma secret
  dosyalarında güvenli biçimde reddedilir.
- Tam ad/kesin domain eşleşmesi aday üretir; benzer ad üretmez. Bulgular
  otomatik incident değildir. İnsan kararı kanıt ve gözlem sürümüne bağlıdır.
- İlk başarılı tur sessizdir. Sonraki yeni/değişen yüksek öncelikli kanıt
  ortak inbox'a gider; vaka kopyası değişmezdir. Kaynak hatası eski başarılı
  kanıtı silmez.
- `darkweb-monitor` kaynak işi modeli12'dir. Profil/sürüm/kapsam SHA'sını
  kabul ve worker'da doğrular, sıfır HTTP kullanır, tamamlanmış core turunu
  kesinti retry'ında tekrar kullanır. Emekli XposedOrNot kaynağını çalıştıramaz.
- `organization.content.darkweb_monitoring` profil ve kaynak durumunu,
  sayfalı bulguları ve maskeli credential kaynak durumunu firma kapsamında
  gösterir. Workspace çiti, başka firma `not_found`, idempotency ve restore
  sonrası yeni workspace davranışı kabul edilmiştir.

## Kabul sonucu

| Alan | Sonuç |
|---|---|
| Tarihî kural/gizlilik/geçiş paketi | 0.185.0'da XposedOrNot odaklı 25 test 10,291 sn'de hatasız geçti; 0.195.1 negatif sözleşme ve tarihî okuma testleri güncel kapıda doğrulanır |
| Hızlı çevrimdışı regresyon kapısı | 2.261 test 1.527,883 sn'de geçti; macOS'ta Linux'a özgü 4 beklenen atlama |
| Kaynak işi ve mevcut engine/platform regresyonu | P05 ile birlikte 101 benzersiz hedefli test; eski sürüm beklentisi düzeltildikten sonra hata yok |
| Şema geçişi | 92→94 ve 93→94 kesintide atomik; yedek ve legacy provider kimliği korunuyor |
| Geçmiş şema regresyonu | Linux yükseltme kabul sınırı 94'e çıkarıldı; ilgili geçişler hedefli ve hızlı kapıda geçti, tam kapı bu turda çalıştırılmadı |
| Backup/restore | P05 kanıtı korunuyor; restore yeni workspace kimliği üretiyor |
| Kesinti | Yarım analiz açık recovery ile `interrupted`; önceki kanıt korunuyor |
| Firma kapasitesi | 2 firma × 10.000 bulgu |
| Tekrarlı tur | Firma başına 30 değişmeyen; yeni kanıt/değişiklik/bildirim 0 |
| Kontrollü değişim | Firma başına 1 yeni kanıt, 1 değişen bulgu, 1 bildirim |
| Platform okuması | 40 × 100 kayıt; en kötü p95 0,273171 sn |
| Bellek | Tepe ana süreç RSS 147,11 MiB; sınır 256 MiB |
| Veri boyutu | Alpha 119.779.328 byte; beta 119.480.320 byte |
| Kapasite süresi/ağ | 111,280 sn; 0 ağ isteği |
| Tam repo regresyonu | 0.184.0 tabanının tarihî sonucu: 3.596 test / 2.403,692 sn; 0.185.0 için bu turda tam kapı değil, 2.261 testlik hızlı kapı çalıştırıldı |

Kapasite komutu:

```sh
./scripts/python scripts/check-darkweb-delivery.py
```

Bu kontrollü sentetik kabul gerçek sağlayıcı doğruluk oranı, bütün internet
kapsamı veya uzun süreli 7/24 hizmet seviyesi değildir.

Tam regresyon komutu:

```sh
PYTHONPYCACHEPREFIX=/tmp/xti-p05-full-green-pycache ./scripts/check
```

İlk tam tur, eski sürüm test verisi hazırlanırken şema 93'ün
`darkweb_monitoring` vaka kanıtı türünün yanlışlıkla daha eski şemalarda da
bırakıldığını gösterdi. Üretim şema doğrulaması gevşetilmedi. Test downgrade
zincirine açık 93→92 adımı eklendi, eski vaka DDL beklentileri ve Linux
yükseltme kabul yardımcısı şema93 için güncellendi. Ardından sıfırdan çalışan
son tam tur **3.596 testi 2.403,692 saniyede** tamamladı: hata/başarısızlık
yok, gerçek Linux gerektiren 4 kontrol beklenen biçimde atlandı. Bu sonuç
0.184.0 tabanının tarihî tam regresyonudur. 0.185.0 geçişinde hedefli 25 test,
2.261 testlik hızlı çevrimdışı kapı ve güncel kapasite kabulü yeniden geçti;
tam `./scripts/check` bu turda yeniden çalıştırılmadı. Yerel macOS sonucu
gerçek Linux CI veya canlı domain sağlayıcı kabulünün yerine geçmez.

## Açık dış bağımlılıklar

1. Genel forum/pazar/Tor kaynağı ve stealer-log sağlayıcısı seçilmedi.
   Erişim hakkı, yasal amaç, izolasyon, saklama/gösterme koşulu, maliyet ve
   gerçek kabul olmadan A02/A10 bütünü kapatılmaz.
2. ThreatCluster yazılı ticari izin olmadan `commercial` profilde seçilemez.
   RansomLook atfı müşteri gösteriminde korunur.
3. Push ve gerçek Linux CI/release sonucu kullanıcı kararıyla sonraya
   bırakıldı; yerel macOS kabulü Linux kabulü gibi gösterilmez.
