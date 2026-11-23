# P02 — Firma ve tedarikçi içerik/kanal izlemesi

21 Kasım 2026. Kullanıcı P01'in dış erişim bekleyen parçaları açık kalırken
P02'ye geçilmesini istedi. Canlı denemede **mevcut açık yayınlar** seçildi.
Bu belge 0.181.0 uygulama/kabul kaydıdır. Açık yayın akışı ile hesap gerektiren
kanalların canlı kabulü ayrı değerlendirilir; paketin bütün kaynakları
tamamlandı olarak işaretlenmez.

## Gereksinim ve kullanıcı sonucu

Ana kapsam A01 (haber, blog, forum ve kanal içeriği), A04 (Telegram,
Discord, IRC), A12 (tedarikçi içerikleri); A13/I04 için RU/ZH/AR/TR/PT
metinleri ve açık dil/bölge seçimi. A07'nin seçilen kaynak normalizasyonu,
B02'nin kesin içerik gruplaması, E01/E05'in izleme parçası, G02/J01/J03'ün
vaka/kanıt/insan kararı desteklenir. Birbirinden farklı kanal türleri veya
yeraltı kaynakları bu destekle bütünüyle tamamlandı sayılmaz.

Kullanıcı kuruluşunu ve seçtiği tedarikçilerini tanımlar; motor ilgili
içerikleri başlık, kısa metin, kaynak, yayın/gözlem zamanı ve eşleşme
gerekçesiyle gösterir. Normal haber, aynı adlı başka firma ve tehdit
iddiası insan incelemesine açık adaylardır. Genel haber sayısı ana çıktı
olmaz. Yeni/değişen içerik takip edilir; kaynak kesintisi eski kanıtı silmez.

## Kaynak ve bileşen seçimi

| Parça | Yol / durum | Kabul sınırı |
| --- | --- | --- |
| RSS/Atom haber, blog, forum | Mevcut sabit `feedparser 6.0.14` yeniden kullanıldı; iki açık yayın canlı doğrulandı. | Yayıncının sunduğu akış penceresi; tam internet veya tam makale arşivi değil. |
| Mevcut Tavily/haber/yayın metni | Kayıtlı sonuçlar ortak izlemeye bağlandı; mevcut toplama komutları korundu. | Yeni ücretli Tavily çağrısı bu çalışma kapsamında yok. |
| Telegram | Telethon1.46.0 seçildi; hash sabitli paket normal kuruluma eklendi, gerçek ortamda kuruldu. | Açıkça seçilmiş kamu kanalı ve kullanıcının oturumu; canlı hesap yok. Bot API'nin izinli bot güncellemeleri genel kanal araması yerine geçmez. |
| Discord | Resmî REST API'ye sınırlı okuma adaptörü. | Seçilmiş sunucu/kanal, bot erişimi ve içerik izni gerekli. Erişim eksikliği boş başarılı arama değildir. |
| IRC | `irctokens2.0.2` seçildi; hash sabitli paket normal kuruluma eklendi, gerçek ortamda kuruldu. | Seçilen sunucu/kanal, yalnız bağlantı sırasında görülen mesajlar. Geçmiş/çevrimdışı pencere ayrıca açık gösterilir. |

Resmî dayanaklar: [feedparser](https://feedparser.readthedocs.io/en/latest/),
[Telethon](https://github.com/LonamiWebs/Telethon),
[Telegram hesap gereksinimi](https://docs.telethon.dev/en/stable/basic/signing-in.html),
[Discord mesaj erişimi](https://docs.discord.com/developers/resources/message#get-channel-messages),
[irctokens](https://github.com/jesopo/irctokens).
Discord içerik izni ve geçmiş okuma izni ayrı kontrol edilir. Telegram
oturumu, Discord token'ı ve diğer sırlar firma JSON'una/kanıta/Git'e girmeyecek.
Araç lisansı yayıncı veya kanal verisinin ticari gösterim izni değildir.

## Uygulama sırası ve mimari

1. Sürümlü kaynak tanımı ve firma/tedarikçi izleme kapsamı; açık maliyet,
   dil/bölge ve içerik penceresi. Var olan kimlikler yeniden oluşturulmaz.
2. Ayrı kaynak portları: RSS/Atom, kayıtlı mevcut içerik, Telegram,
   Discord, IRC. Kaynak hatası, eksik erişim, boş cevap ve eksik pencere ayrılır.
3. Unicode ve açık alternatif isimlerle eşleştirme; domain eşleşmesi ile
   yalnız isim adayını ayırma. Otomatik çeviri/aktör atfı/LLM eklenmez.
4. Değişmez içerik kanıtı, güncel eşleşme ve insan kararı; kopya içerik
   bağımsız doğrulama sayılmaz. Değişmeyen tur gövde kopyalamaz.
5. İlk ölçüm, yeni/değişmiş içerik, kararın eskimesi, ortak inbox ve vaka.
   Akıştan çıkma veya erişim kaybı otomatik giderildi/silindi sayılmaz.
6. CLI ve firma JSON aynı servislere bağlanır; kuruluş/tedarikçi görünümü
   mevcut içerikle birlikte çalışır. Kuyruk, kesinti kurtarma ve tekrar
   güvenliği ilk teslimin içindedir.
7. Kurulum, açık yedekli geçiş, eski veri/kararların korunması, kullanım
   belgesi ve bağımsız kabul kanıtı.

## Koddan önce belirlenen kapasite ve doğruluk kabulü

- İki ayrı firma; her birinde 100 kaynak tanımı, 10.000 saklı eşleşme,
  30 değişmeyen tekrar ve kontrollü değişen içerik. Gerçek sitelere bu
  yük gönderilmeyecek. Geçmiş için toplam kayıt sayısı tavanı konmayacak.
- Tek tur/istek bütçeleri, kayıtlı geçmiş kapasitesinden ayrı: en çok
  100 kaynak işlemi, 600 saniye, 1.000 işlenecek öğe; sayfa en çok 100.
  Kaynak başına pencere/ilerleme kaydı korunacak. Kapsam sessiz kırpılmayacak.
- 100 kayıtlık 40 firma JSON okumasında p95 <2 saniye; sentetik ölçümde
  süreç RSS <256 MiB ve iki firma DB toplamı <256 MiB. Araç alt süreçleri
  ve gerçek ağ maliyeti ayrı raporlanacak.
- Değişmeyen 30 turda yeni içerik kanıt gövdesi sıfır; önceki inceleme
  korunacak. Gerçek değişiklik yeni kanıt ve yeniden inceleme oluşturacak.
- TR/RU/ZH/AR/PT için en az 40 bağımsız etiketli eşleşme örneği; olumlu,
  benzer fakat ilgisiz isim ve belirsiz ad ayrımı. Etiketli kümede beklenen
  sonuçların tamamı gerekli; bu genel internet doğruluk yüzdesi değildir.
- Farklı firma kimliği, eski izleme sürümü, aynı çağrının tekrarı,
  kayıt sonrası kuyruk kesintisi, kaynak kesintisi, iptal, yedek/geri
  dönüş ve sayfalanan birikmiş geçmiş ayrı doğrulanacak.

## Açık bağımlılıklar

Telegram hesabı/API bilgisi, Discord botu/izinli kanal ve belirli IRC
kanalı verilmedi. Kullanıcı şimdilik mevcut açık yayınlarla ilerlemeyi
seçti; bu kanallar için kontrollü test canlı kabul yerine geçmez.
Yeni Tavily harcaması, hesap açılması veya dışarıya mesaj gönderimi yok.
Linux kabulü ve yeni kaynakların ticari veri kararları ayrıca açık.

## Güncel durum

Toplama, maskeleme, kalıcı kanıt, inceleme, tekrar izleme, değişiklik,
inbox/vaka, kuruluş raporu, firma JSON, kuyruk/kurtarma ve kullanım
akışı uygulandı. [Kullanım belgesi](../CONTENT_MONITORING.md).
Kaynak/kanal hesabına bağlı canlı kabul ve ticari kaynak kararları açık.

Son hedefli kabul içinde P02'ye özgü 40 içerik/kanal/yerel katalog/firma/
yedek/CLI kontrolü geçti. TR/RU/ZH/AR/PT için 40 etiketli eşleştirme
örneği bu kontrollerin alt senaryolarıdır; genel internet doğruluk
yüzdesi veya ayrı 40 canlı kaynak testi değildir. Kuruluş HTML raporu
ve ortak eski akışlar da son gerileme demetinde doğrulandı.

## Canlı açık yayın kabulü

- NCSC ve CERT-FR: HTTP200; toplam2 kaynak HTTP denemesi.
- Yayıncı kimliğiyle oluşturulan kontrol hedeflerinde20 ve40 kayıt.
  Bunlar SecureHup sonucu veya tehdit bulgusu değildir.
- SecureHup: incelenen iki yayın penceresinde0 eşleşme.
- Aynı çalışma anahtarıyla tekrar: kayıtlı sonuç döndü, yeni çağrı yok.
- Ücretli çağrı0; Telegram/Discord/IRC canlı hesabı kullanılmadı.
- Ham HTTP gövdesi rapora alınmadı. Zaman, durum, yanıt boyutu ve SHA256
  kaynak çalışma kaydında tutuldu. Gerçek Betterleaks ile maskeleme yolu
  çalıştı; sırlar ve ek dosya/medya içeriği saklanmadı.
- Son canlı artefakt: `/tmp/xti-p02-public-live-release-20261121.json`.

Bu sonuç bütün internetin veya diğer yayınların tarandığı anlamına gelmez.

## Geçiş ve kapasite

Gerçek önceki0.180.0/şema89 üreticisi, P01 kod kanıtı ve insan kararı ile
eski araştırma/vaka kanıtını oluşturdu. Şema90'a açık geçişte185 tablo ve
29 kayıt/rowid korundu; eski kod yeni şemayı reddetti; özgün yedek eski
kodla geri yüklendi. Yeni içerik kaynağının yedek/restore kontrolü geçti.
Bu, yalnız `user_version` düşürülerek üretilmiş bir kabul değildir.

Kapasite kabulünde iki firma × 100 kaynak × 10.000 eşleşme ve 30 tekrar
geçti. Değişmeyen turlarda yeni kanıt 0; firma başına değişen tek içerik
yeni kanıt 1 ve inceleme ihtiyacı oluşturdu. 40 adet 100 kayıtlık platform
okumasında p95 **0,171233 sn**, tepe RSS **105.857.024 byte**, iki DB toplam
**68.538.368 byte** ölçüldü. Süre 478,21 sn; HTTP 0. Kaynak ve maskeleme
kontrollü örnek, uygulama/depolama/firma JSON yolu gerçek uygulamadır.
Son artefakt `/tmp/xti-p02-delivery-release-20261121.json`;
ilk ölçüm `/tmp/xti-p02-delivery-20261121.json` tarihî tutulur.

Gerçek önceki üreticinin dondurulmuş kimliği:
`41363b9a6e5a2772976e7cd307d7b55343e44459d1f3b1a064e92f5a7914efd0`.
Ana commit `2000b2bc12843b12c44bff72282966d8c00333eb`;
P01 ve P02 çalışma ağacı değişiklikleridir, yeni Git commit'i gibi
sunulmaz. Yük kabulü `scripts/check-content-delivery.py --previous-root`
ile gerçek önceki kaynak kopyasını kullanır. Linux'ta çalıştırılmış
sayılmaz; CI hazırlığı Linux sonucu değildir.

Canlı yayın, geçiş/kapasite ve tam gerileme çalışmasının ortak kaynak SHA256'sı:
`f5375667e3d68d8a018453c3aaa48d919b0881b577e306ddb1b93ca00fa2c62d`.
Bu kimlik motor Python dosyaları, P02 kurulum listeleri ve kabul
betiklerini kapsar; Git commit'i veya bütün deponun hash'i değildir.

## Kurulum kabulü

Hash sabitli kanal paketleri gerçek sanal ortama kuruldu. Mevcut
Maigret0.6.6, Sherlock0.16.2, feedparser6.0.14, pypdf7.1.1 ve yeni
Telethon1.46.0/irctokens2.0.2 aynı doğrulayıcıdan geçti; `pip check`
bağımlılık uyuşmazlığı bulmadı. Erişim hesabı doğrulaması yapılmadı.

Eski ortam kontrolünde süre aşımı görüldü. İlk kurulumun proje wheel
adımı uzayınca süreç kontrollü durduruldu; eski ortam aynen geri alındı.
Proje paketi temiz geçici kaynak ağacından oluşturularak kurulum
tekrarlandı ve geçti. Önceki ortam yedeği silinmedi; veri alanına
kurulum tarafından migration uygulanmadı. Son log:
`/tmp/xti-p02-install-isolated.log`.

## Son gerileme kaydı

Tam envanter **3.513 benzersiz test** olarak dört ayrık parçada çalıştı.
Parçaların toplamı ile güncel test envanterinin eşitliği, tekrar eden
test bulunmaması ve her parçanın kaynak kimliğinin çalışma boyunca
değişmemesi doğrulandı. İlk sonuç: **3.504 başarı, 5 eski test beklentisi
hatası, 4 Linux atlaması**. İlk başarısız sonuçlar silinmedi.

Beş beklenti yeni kanal doğrulayıcı mock'u, şema90 vaka DDL'si (üç test)
ve firma manifestindeki yeni `content.run` işlemi için güncellendi.
Bunlar üretim korumalarını gevşetmeden ilgili tekrar kontrollerinden geçti.
Son kullanım denetiminde iki gerçek davranış da düzeltildi: içerik/kod
bildirimlerinin genel toplamdan düşmesi ve kaynağı kapatılmış izlemenin
durdurulamaması. Üç ilgili senaryo önce hatayı üretti, sonra geçti.

Bu düzeltmeleri, beş eski beklentiyi ve ortak akışları içeren **300 hedefli
test, 177,245 saniyede hatasız ve atlamasız geçti**. Son hedefli çalışmanın
kaynak SHA256'sı:
`8a3ecd29fc0a9a185f741174d59a2fec47aaaad832b44fe531e54e51eac86ea4`.
Son çalışma boyunca kaynak kimliği değişmedi. Tam çalışma ile hedefli
tekrar birleştirildiğinde 3.509 benzersiz testin başarılı sonucu vardır;
dört Linux testi açık kalır. Bu, son kaynak ağacında tam paketin yeniden
çalıştırıldığı iddiası değildir. Kapasite/canlı kabulü önceki `f537…` kaynak
kimliğindedir; son fark bildirim toplamı ve izlemeyi durdurma akışıdır.

Artefaktlar:

- `/tmp/xti-p02-suite-verified-1.json` … `-4.json`: tam envanter ve ilk sonuç.
- `/tmp/xti-p02-consistency-before.log`: iki davranışın üç senaryoda tekrar üretimi.
- `/tmp/xti-p02-final-recheck-20261121.json`: envanter eşitliği ve son 300 test.
- `/tmp/xti-p02-final-recheck.log`: son testlerin tek tek sonuçları.

Atlananlar iki gerçek Linux süreç sahipliği/kesinti testi ve iki systemd
ayrıştırıcı testidir. macOS üzerindeki karşılıklar Linux kabulü sayılmadı.
Gerçek `./xti --version`, `content --help` ve `content providers` kontrolleri
geçti; sağlayıcı durum okuması ağ/veri alanı oluşturmadan çalıştı. Shell
sözdizimi, Markdown bağlantıları, 76 benzersiz gereksinim kimliği ve
`git diff --check` de doğrulandı.

P01'in önceki kanıtı [kendi teslim kaydında](P01_DELIVERY.md) korunur.
Telegram/Discord/IRC canlı erişimi, Linux kabulü ve ticari veri kararları
bu kod teslimiyle kendiliğinden kapanmaz.
