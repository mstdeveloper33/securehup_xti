# Değişiklik Kaydı

## 0.172.0 — 19 Kasım 2026

- Bright Data LinkedIn şirket kanıtı: ağsız plan, sınırlı async gönderim,
  kalıcı snapshot ile sonuç alma ve firma kapsamlı CLI/JSON yüzeyi.
- Gizli API anahtarı kurulumu, işlem/günlük profil sınırı ve kesintide
  otomatik tekrar harcamasını engelleyen kalıcı rezervasyon.
- Sağlayıcı kanıtı eski profil sayfası kontrolünden ayrı gösterilir.
  Şema 81 → 82 ek tablo/index geçişi açık ve yedeklidir.
- Kullanıcı anahtarı sonra ekleyecek; canlı sağlayıcı doğruluğu/kotası
  henüz ölçülmedi. [Kullanım ve doğrulama](docs/BRIGHTDATA_SOCIAL.md).

## 0.153.0 — 17 Kasım 2026

- Dört seçilmiş MISP warninglist: Cloudflare IP ağları, RFC1918 özel IPv4,
  RFC3849 örnek IPv6 ve RFC6761 özel kullanım domainleri. İnternetten
  `warninglists sync`; kaynaklı yerel `lookup/status/history/run-show`.
- Commit'e bağlı indirme, kaynak koşulu değişiminde inceleme, içerik hash'i,
  güncellik, son başarısız deneme ve korunan son iyi liste ayrı görünür.
  Özgün içerik/yenileme geçmişi korunur; yeni bağımlılık veya anahtar yoktur.
- `research.show` düğümlerine liste bağlamı; engine/platform v1'e
  `warninglists.status`, `warninglists.lookup`, `warninglists.run.get`.
  Firma ayrımı korunur; otomatik allowlist, alarm kapatma veya IOC yazımı yoktur.
- Şema 73 iki tablo ekler. Açık yedekli migration ve mevcut yedek/restore
  akışları kapsamı korur. [Kullanım](docs/WARNINGLISTS.md).
- Gerçek kaynak kabulünde aynı commit'ten dört liste / 51 üye alındı;
  yerel IP/domain eşleşmesi ve CLI/engine tutarlılığı doğrulandı.
  Tam tur 2.732 test çalıştırdı; iki eski işlem envanteri beklentisi
  düzeltilerek ilgili son 64 test hatasız geçti. Dört Linux kontrolü
  macOS'ta atlandı. [Tam tur ve tekrarların ayrımı](docs/ACCEPTANCE_REVIEW.md#01530--misp-warninglists-kabulü).

## 0.152.0 — 17 Kasım 2026

- `research VALUE --type domain|ip` ve engine/platform `research.show`:
  kayıtlı DNS/IOC/CTI kanıtlarından en fazla iki adımlı araştırma yolları.
  Kaynak, özgün kayıt/iddia/olay/çalışma kimliği, tarih, etkinlik ve
  güncellik korunur. Ortak IP'den sahiplik veya saldırgan sonucu çıkarılmaz.
- Tek okuma kesiti, firma alanı sınırı, açık düğüm/bağ/kaynak okuma
  bütçeleri, yol sayfalaması ve değişen kanıt için `expected_snapshot`.
  Eski veya geri çekilmiş kanıt saklı ayrıntıya bağlantısıyla görünür.
- Yeni ağ isteği, zorunlu ücretli API, bağımlılık veya tablo yoktur.
  Şema 72 ve yedek biçimi korunur; mevcut engine/platform v1'e yeni okuma
  işlemi eklenir. [Kapsam ve kullanım](docs/RESEARCH.md).
- `umask 002` altında 110 ilgili test 44,354 saniyede geçti; 23 yeni
  araştırma kabulü dahil. Firma ayrımı, büyük IOC kataloğu, eşzamanlı
  değişim ve yedekten dönüş doğrulandı; tam paket/canlı Linux kabulü değildir.

## 0.151.0 — 17 Kasım 2026

- Kaynak durumu ve kuruluş terminal/HTML raporu kısmi kanıtı, tam sonuç
  yokluğunu, başarısız denemeyi ve önceki sonucun güncelliğini açık ayırır.
- `collect`, `search` ve `organizations report` için `--summary` kısa
  görünümü. Kaynak hataları, kapsam, sayfalama ve saklı ayrıntıya erişim
  korunur; genel haber listesi hedef özeti içine dökülmez.
- Kuruluş özeti bölüm başına ilk üç kaydı ve gösterilmeyen toplamı sunar.
  Yeni ayrıntı komutları özel veri klasörünü ve seçili filtreleri korur.
- Sadece gösterim değişir: aynı toplama işi, tam JSON, aynı hata/çıkış
  davranışı. Şema 72, engine/platform v1 ve bağımlılıklar değişmedi.
  [Günlük kullanım](docs/DAILY_USE.md#kısa-görünüm-ve-kayıt-ayrıntıları).
- İlgili kaynak/toplama/arama/kuruluş ve engine/platform regresyonlarının
  211 testi `umask 002` altında 227,090 saniyede geçti; hata veya atlama
  yok. Tam paket ve canlı Linux kabulü ayrı kalır.

## 0.150.0 kabul düzeltmeleri — 675ad79

- CSAF VEX ürün kimliklerinin başındaki/sonundaki boşluklar korunur.
  Red Hat Log4Shell belgesinin geçerli ürün kimliğini reddeden ayrıştırma
  hatası giderildi. Ürün kimliği seçimi, kalıcı kanıt ve yeniden kontrol
  aynı kesin değeri kullanır; PURL/CPE doğrulaması ve boyut sınırları korunur.
- Gerçek Red Hat `CVE-2021-44228` belgesiyle hata yeniden üretildi;
  düzeltme sonrası canlı `vendor-preview` başarılı JSON verdi. `umask 002`
  altında 32 ilgili test 6,951 saniyede geçti; kimlik ayrımı, kalıcılık,
  yedekten dönüş ve kanıtın maruziyet CVE'sine bağlılığı kapsandı.
- Nmap/kaynak raporundaki farklı CVE karşılaştırması ve canlı kabul
  sınırları belgelendi. Bu sonuçlar bütün Nmap seçeneklerinin canlı
  kabulü veya tam test turu olarak sunulmaz.

- `brand watch-add` ve `brand watch-revoke` tekrarlarında `unchanged`
  eyleminin terminal/JSON çıktısını çökertmesi giderildi; mevcut tanım,
  karar ve olay geçmişi değişmez. İki CLI regresyon testi eklendi.
- Ortak arama notu kişisel veya firma alanı için “seçili çalışma alanı”
  ifadesini kullanır; veri kapsamı ve JSON sözleşmesi değişmedi.
- Platform süreç çıkış kodları ve bulunamayan kuruluş/profil/iş için
  mevcut v1 davranışı açıkça belgelendi.
- Platform Nmap ön hazırlığı ve plan → iş bağlantısı belgelendi. Kabul
  testi hedefi yönetici CLI'siyle kurar; kontrollü çalıştırıcıyla platform
  worker, sayfalı sonuç, tekrar güvenliği ve firma ayrımı doğrulanır.
- Kullanıcının `888f403` Linux raporu, kalan canlı kabul ve şema 69 kişisel
  alanın geçiş gereksinimi [kabul değerlendirmesine](docs/ACCEPTANCE_REVIEW.md)
  kaydedildi. Şema 72, sürüm 0.150.0 ve v1 sözleşmesi korunur.
- `umask 002` ile sosyal izleme, genel arama ve platform/Nmap kabulünün
  39 testi 21,727 saniyede geçti; bu tur tam suite tekrarı değildir.

## 0.150.0 kabul düzeltmeleri — 888f403

- CTI izleme denetimi ilgisiz IOC/varlık kataloğunu 10.000 izleme sınırına
  saymaz; kaynaklı geçmiş ve kopuk bağlantı denetimi korunur.
- Yeni veri/yedek/geri yükleme klasörleri ve eksik ara klasörler `0700`
  oluşturulur. Eski izinler otomatik değiştirilmez; `storage readiness`
  klasör izinlerini terminal/JSON'da ve kurtarma hazırlığında gösterir.
- Zamanlı yedek testinin `umask 002` altında kırılması giderildi; büyük
  IOC kataloğu ve farklı umask değerleri için regresyon testleri eklendi.
- Günlük kullanımda doğru `schedule generate --output ... --at ...`
  örneği; [Linux raporu değerlendirmesi](docs/ACCEPTANCE_REVIEW.md).
- Tam test turu `umask 002` ile: 2.665 test, 2.661 başarılı, macOS'ta
  Linux'a özgü dört atlama; hata yok. Çekirdek şema 72 değişmedi.

## 0.150.0 — 16 Kasım 2026

- Yetkili Nmap planları için kalıcı iş kabulü, tekrar önleme anahtarı,
  hedef başına kayıt, iptal, kesinti kurtarması ve yalnız hiç başlanmamış
  hedefleri devam ettirme. Yeni kayıt yoluna taşınmış eski işler tekrar
  çalıştırılamaz. Şema 72 iki tablo ekler; açık geçiş önce yedek alır.
- V1 plan byte/hash'i korunur. V2 TCP connect/SYN/UDP, servis/sürüm,
  OS tahmini, seçili NSE ve ayrı süre seçeneklerini dondurur. Raw socket
  seçenekleri yetkili worker gerektirir; otomatik sudo yoktur.
- NSE kataloğu: banner, ssh-hostkey, ssl-cert ve TCP 445'e bağlı
  smb-vuln-ms17-010 yanıt kontrolü. Ham argüman, genel NSE kategorileri,
  parola denemesi ve exploit eklenmedi. Kaynak çıktısı kesin risk kararı değildir.
- Firma kapsamlı platform JSON plan/kuyruk/sonuç işlemleri; ayrı açık
  `platform nmap-worker`. Temiz subprocess ortamı, sınırlı stdout/stderr,
  çocuk sürece taşınan kilit ve normal iptalde süreç grubu temizliği.
- Port durumlarında UDP belirsizliği korunur; ayrıntı sınırında kısmi kanıt
  açık gösterilir. Gerçek Nmap'in dış varlıksız DOCTYPE bildirimi her iki
  XML adaptöründe kabul edilir; özel DTD/entity reddedilir.
- Genel `check-fast`: 1.311 test, 1.307 başarılı, dört Linux atlaması.
  Son XML/süreç düzenlemeleri sonrasında 77 Nmap/platform testi geçti.
  Gerçek Nmap kurulu olmadığı için canlı gelişmiş tarama kabulü yapılmadı.
- [Kullanım](docs/NMAP_MANAGED.md), [mimari karar](docs/decisions/0155-managed-nmap-execution.md).

## 0.149.0 — 16 Kasım 2026

- Kayıtlı ve etkin domain dış yüzeyi altında adlandırılmış kesin genel IP/CIDR
  hedef envanteri; kapsam içi hariç tutmalar, gerçek hedef sayısı ve hash'i,
  yetki gerekçesi, geri çekme ve eklemeli sürüm geçmişi.
- Hedefin kesin sürümünü port, süre, hız, retry, gecikme, paralellik, host
  grubu, hedef ve probe bütçesiyle donduran değiştirilemez Nmap dry-run planı.
  16'dan fazla hedef ve 1024'ten fazla port açık onay ister; ham Nmap argümanı
  kabul edilmez.
- Şema 71 üç bütünlük denetimli tablo ekler; 70→71 geçişi yedek alır. Bu sürüm
  geniş CIDR planını çalıştırmaz; kalıcı iş/worker, ilerleme, iptal ve kesinti
  kurtarması sonraki çalıştırma katmanının ön koşuludur.
- `check-fast`: 1.287 test, 1.283 başarılı, macOS'ta beklenen dört Linux
  atlaması, hata yok. Canlı hedef trafiği üretilmedi.
  [Karar](docs/decisions/0154-managed-nmap-targets-and-plans.md),
  [durum](docs/STATUS.md).

## 0.148.0 — 16 Kasım 2026

- İsteğe bağlı Nmap TCP-connect adaptörü; güvenli/uzatılmış/tam/özel TCP port
  profilleri ile süre, azami hız, retry, hedef ve yaklaşık probe sınırları.
- Yalnız kayıtlı domainin güncel DNS yanıtındaki en fazla 16 kesin genel IP
  çalıştırılabilir. Ham argüman, UDP, SYN/root, NSE, sürüm/banner ve işletim
  sistemi keşfi yoktur; sonuçlar ayrı ve eklemeli kanıt olarak saklanır.
- Nmap kurulumu ayrı ve tekrar güvenli betikle yapılır; şema 70 önceki kanıtı
  koruyan yedekli geçiştir.
  [Karar](docs/decisions/0153-bounded-authorized-nmap-adapter.md).

## 0.145.0 — 15 Kasım 2026

- `mentions groups`: bir kuruluş ve açıkça seçilmiş tedarikçiler için
  sürümlü izleme, tam sorgu planı, çalışma geçmişi ve bütün kaynak sonuçları.
- Çalışma/gün sorgu sınırı ve aralık; HTTP öncesi kalıcı rezervasyon,
  kesintide belirsiz sorguyu tekrar etmeyen devam, aynı istek kimliğiyle
  tekrar güvenliği. Kaynak hatasında kalan çağrılar yapılmaz.
- Başarılı toplama mevcut `search-watch → inbox` yoluna kesin hedef/sorgu
  kapsamıyla bağlanır. İlk kapsam sessizdir; yeni/anlamlı değişen içerik
  bildirilir. Kaynak ve bildirim aşamaları ayrı kurtarılabilir.
- Sınırlı terminal izlemesi; güvenli günlük/haftalık systemd dosyaları,
  takvim/aralık uyumu, açık anahtar dosyası yolu ve doğrulanmış yedek hazırlığı.
  Zamanlayıcı kendiliğinden etkinleştirilmez.
- Şema 68: grup olayları, idempotent bildirim bağları ve opsiyonel tipli
  kayıtlı arama kapsamı. Eski tanım/kanıt JSON/hash korunur; açık geçiş
  benzersiz yedek alır. Yeni paket veya engine v1 işlemi yoktur.
- Linux hızlı kontrolü önceki teslimde 9 dakika 51 saniye sürdüğü için
  yeni testlerle iş süre sınırı 10'dan 15 dakikaya çıkarıldı; testler çıkarılmadı.
  [Kullanım](docs/MENTION_GROUPS.md), [karar](docs/decisions/0150-budgeted-company-monitoring.md).

## 0.144.0 — 15 Kasım 2026

- Tavily ile firma, kayıtlı kuruluş ve tedarikçi hakkında gerçek web/haber
  araması: `mentions configure/plan/search/list/show/status/run-show`.
  Her komut tek temel istek gönderir; otomatik tekrar veya LLM cevabı yoktur.
- API anahtarı repodan ve veritabanından ayrı özel dosyada veya ortamda
  tutulur. Gizli terminal girişi, anahtar sızdırmayan hata mesajları,
  sabit HTTPS adresi, yanıt ve süre sınırları uygulanır.
- Sorgu/hedef, başlık, bağlantı, sınırlı açıklama ve eşleşme gerekçesi
  kaydedilir. Tekrar, değişen içerik ve geçmiş kanıt korunur; boş başarı
  erişim/kota hatasından ayrıdır. Kredi bilgisi hesap bakiyesi değildir.
- Genel arama, kayıtlı arama ve engine v1'e `mention/company_mention`
  eklenir. Önceki izleme kapsamları değişmez; engine'in dört işlemi korunur.
- Şema 67 tek eklemeli çalışma tablosu ve açık yedekli geçiş ekler. Yeni
  Python bağımlılığı, müşteri/oturum backend'i veya otomatik tarama yoktur.
  [Kullanım](docs/MENTIONS.md), [karar](docs/decisions/0149-tavily-company-mentions.md).

## 0.143.0 — 15 Kasım 2026

- `news sources/refresh/list/show/status/run-show`: CISA, UK NCSC ve
  CERT-FR sabit HTTPS yayınları; gerçek `feedparser` ile RSS/Atom okuma.
  Yayıncı kimliği/atıfı, başlık, sınırlı düz metin özet, özgün bağlantı,
  ham ve ayrıştırılmış kaynak tarihleri ayrı tutulur.
- Akış penceresinden düşen haberler korunur. Kaynak kimliğiyle tekilleştirme,
  tarihî önce/sonra kanıtı, aynı haber tekrarında değişiklik üretmeme,
  son deneme/son başarı ayrımı ve sayfalı terminal/JSON çıktısı.
- Genel aramaya `news`, engine'in mevcut dört işlemine haber kayıt türü
  eklenir. Mevcut kayıtlı arama/inbox yolu yeniden kullanılır; eski on türün
  kayıtlı kapsamı ve kanıtı değiştirilmez. Toplama ve izleme ayrı komutlardır.
- Şema 66 üç boş haber tablosu ekler; açık geçiş yedek alır. Normal kurulum
  `news` ek bağımlılıklarını mevcut kurtarılabilir araç ortamına kurar;
  önceki ortam korunur. `--core-only` paket indirmez. Sabit sürümler ve
  lisanslar [üçüncü taraf kaydında](THIRD_PARTY.md).
- Haber bağlantıları/ekleri takip edilmez; DTD/entity, yönlendirme,
  bozuk XML, yanıt/saklama sınırı ve hatada kısmi kayıt reddedilir.
  [Kullanım](README.md#rss-ve-atom-haberlerini-topla),
  [doğrulama kapsamı](docs/STATUS.md).

## 0.142.0 — 15 Kasım 2026

- `search-watch add/list/show/disable/run/run-show/monitor`: on yerel kayıt
  ailesi için kayıtlı genel arama, tam sonuç farkı, tarihî kanıt ve sınırlı
  terminal izlemesi. İlk çalışma, yeni tanım ve yeniden etkinleştirme
  sessiz başlangıçtır; sonraki yeni/anlamlı değişen sonuçlar yerel kutuya
  çalışma başına tek bildirim üretir. Yalnız çıkarılma geçmişte gösterilir.
- Sosyal profilde kalıcı izleme/tanım/platform kimliği; kaynak kimlikleri
  ve çalışma/zaman kanıtları ayrı tutulur. Toplama zamanı veya çalışma
  kimliği değişmesi tek başına bildirim üretmez.
- Tanım, tam sonuç, kaynak kapsamı ve önce/sonra farkı saklanır. Aynı
  kanıt görüntüsü içerik özetiyle tekrar kullanılır; sayfalama saklanan
  sonucu kesmez. Bildirim okundu durumu, genel sayaçlar, yedek/geri dönüş
  ve mevcut açık webhook kuyruğu yeni türü destekler.
- Şema 65 beş boş tablo ekler; `./xti migrate` benzersiz yedekle açık
  geçiştir. Eski kodun yeni şemayı reddi ve geçiş öncesi yedeğin yeni veri
  dizinine geri yüklenmesi kabul akışına eklenir. Otomatik geçiş yoktur.
- Kayıtlı arama yazılarının zamanı ortak kilit alındıktan sonra alınır;
  eşzamanlı başka işlem geçerli yazıyı eski zamanlı hale getirmez.
- Yeni paket, ücretli API veya engine v1 işlemi eklenmedi. Kullanım
  [README](README.md#genel-aramayı-kaydet-ve-değişiklikleri-izle), gerçek
  doğrulama sonuçları [STATUS](docs/STATUS.md) içindedir.

## 0.141.0 — 15 Kasım 2026

- `events candidates`: ThreatCluster, RansomLook ve HIBP'nin mevcut yerel
  kanıtlarını tek okuma anında birlikte inceleme; tam domain filtresi,
  sayfalama, ayrı tür sayaçları ve terminal/JSON çıktısı.
- Aynı ad/grup ve en fazla 72 saat keşif farkı olan ransomware kayıtları
  olay adayıdır. Yalnız noktalama/boşluk/harf farkı da desteklenir. HIBP ile
  tam domain ortaklığı ayrı bağlam türüdür; aynı olay iddiası oluşturmaz.
- İki özgün kayıt, kaynak/çalışma kimlikleri, tarihlerin ayrı anlamları,
  eşleşme nedeni ve sınırları görünür. Eski insan kararları özgün kanıtına
  bağlı kalır; güncel kanıt değişmişse belirtilir. Otomatik birleştirme,
  karar veya alarm kaydı eklenmez.
- Aday okuması son katalogları ve eski kararların gerekli kanıtlarını
  tutar; her tarihî kataloğun tam kopyasını bellekte çoğaltmaz. Kaynak
  geçmişi ve eski karar zincirinin doğrulanması sürer. Kapasite aşımı
  kısmi sonuç yerine açık hata verir.
- Yeni bağımlılık, ücretli API, tablo veya engine v1 işlemi yoktur.
  Şema 64 ve mevcut kaynak karşılaştırması/kararları korunur. Kullanım
  [README](README.md#kaynaklar-arası-olay-adaylarını-incele), doğrulama
  kapsamı [STATUS](docs/STATUS.md) içindedir.

## 0.140.4 — 15 Kasım 2026

- On kayıt ailesinin birlikte kurtarılması, üç gerçek süreç kesintisi,
  rakip komutlar, eksik işin devamı ve bozuk kanıtın reddi için kabul zinciri.
- Sırlar terminal/JSON/HTML ve hata çıktılarında; yedek ve dosya izinleri
  gerçek komutlarla sınanır. Anahtar dosyası yerine FIFO verilince oluşan
  bekleme giderildi.
- Python 3.11 kurulumunda NumPy 2.4.6, daha yeni Python'da mevcut 2.5.4
  koşullu sabitlenir; bağımlılık doğrulaması aynı seçimi denetler. Temiz
  marka kurulumu gerçek Python 3.11 ve 3.12 ile ayrı çalışır.
- Önceki sürümden gerçek araç güncelleme/kurtarma ve gerçek Linux
  zamanlayıcısı, kaynak kesintisi, disk ve ölçülü çalışma kabul betikleri;
  ağır kontroller ayrı, elle başlatılan GitHub işindedir.
- Başlangıç rehberine kesinti ve yedekten dönüş adımları eklendi.
  Tanımlanan 11 maddelik mevcut motor paketi tamamlandı: `7060cec`
  üzerinde Ubuntu genel paketinde 2.107, hızlı pakette 687 testin tamamı
  geçti. Gerçek araç yükseltme/kurtarma, systemd, düşük disk ve 600
  saniyelik işletim kabulü başarılı; 5.000 sentetik domaine kadar ölçüldü.
  Gerçek çalıştırma kapsamı ve sonuçları [STATUS](docs/STATUS.md) içindedir.
  Maigret/Sherlock/theHarvester commitleri, engine v1 ve şema 64 korunur.

## 0.140.3 — 15 Kasım 2026

- Maigret/Sherlock ortamında kalıcı kilit, kimlik günlüğü ve `--recover`;
  önceki/başarısız ortamların korunması ve belirsiz eski yapıların reddi.
- XTI başlatıcısı Python ortamını seçmeden kilit alır; çalışan komutun
  kullandığı ortam değiştirilmez. Yarım kurulumda çekirdek temel Python'a
  döner, sosyal araçlar kurtarma tamamlanana kadar çalışmaz.
- Harvester ve marka kurulumları ortak süreç ve kurtarma bileşenlerini
  kullanır. Alt süreçlerde kilit korunur, belirsiz sonlandırmada geri
  dönüş yapılmaz. İncelenmiş araç pinleri ve şema 64 değişmedi.
- Marka Ubuntu kabulü geçici veride kurulum, tekrar, engine ve yedekten
  dönüş zincirini kapsar. Gerçek çalıştırma sonuçları [STATUS](docs/STATUS.md)
  içinde ayrıca kaydedilir; [kullanım rehberi](docs/BRAND_INSTALLATION.md).
- Genel test turu: 2.069 test, 2.068 başarılı, macOS'ta bir Linux kontrolü
  atlandı. Son düzeltmeler ayrıca güncel 18 runtime ve 26 kurulum testiyle geçti.

## 0.140.2 — 15 Kasım 2026

- theHarvester kurulumunda eski ortamı koruma, hata sonrası geri dönüş,
  ani kesinti için günlük ve `--recover`; ayrı `--check` ve `--force`.
- Kurulum ve çalışan arşiv işçisini koordine eden, çocuk süreçte de tutulan
  kalıcı kilit. Meşgul veya yarım kurulum kaynak hazırlığında gösterilir.
- Sağlıklı tekrar indirme yapmaz. Eski/başarısız araç klasörleri saklanır;
  SQLite kanıtları ve araç pinleri değişmez. Şema 64 korunur.
- Gerçek Ubuntu kurulum/tekrar kabul işi ve kesinti testleri eklendi.
  Genel turda 2.024 testten 2.023 geçti, bir Linux kontrolü atlandı;
  son kurulum düzeltmelerinden sonra ayrıca 33 kurulum testi geçti.
  Çalıştırma kapsamı ve açık Linux kabulü [STATUS](docs/STATUS.md) içinde.

## 0.140.1 — 15 Kasım 2026

- Engine/bileşen testleri hızlı CI kapsamına, ortak pinler marka kurulum
  filtrelerine alındı; komut ve kaynak kapsamı açıklamaları düzeltildi.
- Yeni özelliklerden önce mevcut SQLite motorunu sağlamlaştırma sırası
  kaydedildi; gelecekteki .NET/PostgreSQL bağlantısı ayrı kabul olarak kaldı.

## 0.140.0 — 15 Kasım 2026

- Üç entegre araç için ortak incelenmiş pin ve yerel kurulum kataloğu;
  `components` ve engine `components.list`. Kurulum gözlemi canlı kaynak
  başarısından ayrı gösterilir. Şema değişmedi.

## 0.139.0 — 15 Kasım 2026

- Yerel engine v1 JSON okuma sözleşmesi: `search`, `record.get` ve
  `sources.status`. Kayıt/kanıt referansları ve açık hata biçimleri; mevcut
  CLI korunur. .NET tüketicisi veya ağ servisi eklenmedi.

## 0.138.0 — 15 Kasım 2026

- `search QUERY`: on tür yerel kaydı tek komuttan arama, tür filtresi,
  tam/başlangıç/içerme sırası, kaynak durumu, sayfalama ve ayrıntıya geçiş.
- Tedarikçi için ayrı ThreatCluster/RansomLook/HIBP izlemesi; sessiz
  başlangıçtan sonra yeni/değişen eşleşmelerde yerel bildirim. Tarihî
  tedarikçi, kaynak ve önce/sonra kanıtı korunur. Kaynak/izleme/bildirim ve
  toplama bağı aynı işlemde kaydedilir.
- `surface relations DOMAIN`: kayıtlı IP, sertifika, CNAME ve insan onaylı
  tedarikçi ilişki geçmişi. Tek tek gözlemler, hatalar, boş kontroller,
  ilk/son gözlem ve kanıt kimlikleri görünür.
- Şema 64 dört boş tablo ekler; yedekli açık geçiş ve yeni dosyada geri
  dönüş vardır. Yeni ücretli API veya paket bağımlılığı eklenmedi.
- Tam paket: 1.918 test, 1.917 başarılı ve bir Linux kontrolü macOS'ta
  atlandı. Hızlı kapı: 524 test, aynı tek atlama. 55 yeni test eklendi.
- Kullanım: [arama, tedarikçi ve ilişki rehberi](docs/SEARCH_SUPPLIERS_AND_RELATIONS.md).

## 0.137.0 — 15 Kasım 2026

- Tarihî kamu olayı ve kuruluş izleme kanıtını vakaya bağlama; tek vaka
  kanıtını görünüm sınırından bağımsız açma.
- Kuruluş raporunun bütün kayıtlarını çevrimdışı, bağımsız HTML dosyasına
  aktarma; mevcut dosyanın üzerine yazmama ve güvenli metin gösterimi.
- Şema 63 vaka kanıtı tür kısıtını genişletir; eski rowid ve kanıtları korur.
  Tam paket 1.863 testte 1.862 başarılı, Linux kontrolü macOS'ta atlandı.

## 0.136.0 — 15 Kasım 2026

- Kuruluş başına açık HIBP izleme: açma/kapatma, tam domain kapsamı,
  kaynak durumu ve sayfalı çalışma/tanım geçmişi. Aynı HIBP yenilemesi bütün
  açık izlemeleri ilerletir; ek ağ isteği veya ücretli API yoktur.
- İlk ölçüm ve yeni/yeniden etkin domain sessizdir; mevcut kapsamın yeni
  veya değişen kaydı çalışma başına tek yerel bildirim üretir. Tekrar,
  kaynak hatası ve yalnız çıkarılma bildirim oluşturmaz.
- Kaynak, izleme, bildirim ve toplama bağı aynı işlemde kaydedilir. Bildirim
  tarihî kuruluş/link olaylarına ve gerçek önce/sonra metadata kanıtına
  bağlıdır. Tüm kayıtlar sayfalanır; atıf/lisans ve okundu durumu korunur.
- Kuruluş raporunda kesin kuruluş kimliğiyle ayrı tarihî izleme bölümü
  bulunur. Durum ekranı artık mevcut RansomLook bildirimlerini de toplamına
  katar; inbox, doctor ve status sayaçları tutarlıdır.
- Şema 61→62 dört boş tablo ekler; benzersiz yedek ve eski sürüme yeni
  dosyada geri dönüş vardır. Kişisel kuruluş/izleme kendiliğinden oluşturulmaz.
- Tam paket: 1.828 test / 597,223 saniye; 1.827 başarılı, bir Linux kontrolü
  macOS'ta atlandı. Hızlı kapı: 434 test / 194,914 saniye, aynı tek atlama.
  Gerçek verinin kopyasında ve asıl verinin yedekli geçişinde 129 tablo /
  86.843 satır korundu; geri dönüş şema 61 ve özgün kayıtlarla eşleşti.

## 0.135.0 — 14 Kasım 2026

- HIBP kamu katalog yenilemesi `--task notices-hibp` ile mevcut toplama,
  kayıtlı profil ve Linux zamanlama akışına katılır. Varsayılan üç iş aynıdır;
  seçim açık yapılır ve kayıtlı domain gerekir. Yeni HTTP kaynağı, ücretli
  API veya paket bağımlılığı eklenmedi.
- Kaynak run/farkları ve toplama tamamlanma bağı aynı işlemde kaydedilir.
  Başarıdan sonra üst komut kesilirse devam aynı kataloğu yeniden indirmez;
  hata son başarılı kataloğu korur, eksik işler ayrıca tekrar edilir.
- Katalog toplamı domainin bulgu sayısı olarak gösterilmez. İlk alım,
  kaynak atfı/lisansı, gerçek run kimliği ve ayrıntıya geçiş; terminal,
  JSON ve korunmuş geçmişte görünür. Önizleme/plan/zamanlama hazırlığı ağsızdır.
- Şema 60→61 yedekli yeniden kurma ile toplama adım/sonuç bağlantısını
  genişletir; önceki kayıtlar, profil ve plan özetleri korunur. Yeni HIBP
  bildirimleri, vaka bağlama ve HTML rapor sonraki ayrı teslimlerdir.
- Tam paket: 1.777 test / 562,841 saniye; 1.776 başarılı, bir Linux kontrolü
  macOS'ta atlandı. Hızlı kapı: 383 test / 166,578 saniye, aynı tek atlama.
  Gerçek verinin kopyasında ve asıl verinin yedekli yükseltmesinde 129 tablo,
  86.843 satırın eski alanları/rowid'leri korundu; yedekten ayrı dosyaya
  geri dönüş şema 60 ve özgün verilerle eşleşti.

## 0.134.0 — 14 Kasım 2026

- `organizations report ID`: etkin açık domain/izleme bağlantılarına göre
  birleşik yerel kanıt; gerçek kayıtlar, sayfalama, son deneme/son başarı,
  eski/eksik veri ayrımı ve ilgili bildirim/vakalara geçiş.
- `changes --organization ID`: günlük/haftalık dönem ve karma oturumlarda
  yalnız ilgili adımlar. DNS/TLS/web/posta/servis/CNAME ve sosyal değişimlerde
  kayıtlı önce/sonra değerleri; başarısız sorgu boş başarı sayılmaz.
  `--offset` ile kategori ve kapsama sayfaları; toplamlar korunur.
- `sources contribution --organization ID`: domain/kural/kaynak bazında
  bağımsız kanıtlar ve gerçek deneme pay/paydasını tek okuma anında gösterme.
- `cti context`: tam domain/IP/URL/hash veya CTI varlık kimliğinin doğrudan
  kayıtlı ilişkileri; kaynak, geçerlilik, geri çekilme ve sayfalama. Kaynaksız
  veya dolaylı atıf yoktur; güncel iddialar geçmişleriyle doğrulanır.
- HIBP kamu ihlal metadata kataloğu: anahtarsız tek yenileme, yerel
  arama/ayrıntı, başlangıç/fark ve hata geçmişi. Kaynak bayrakları, atıf ve
  lisans görünür. E-posta/hesap/parola veya ham sızıntı içeriği sorgulanmaz.
  Kuruluş/dönem raporunda tam domain eşleşmeleri, kaynak durumunda genel
  katalog görünür. Canlı kabulde 1.052 kayıt ve yerel `adobe.com` araması geçti.
- Şema 59→60 iki tablo ekler; benzersiz geçiş yedeği ve açık migration.
  Üyelik, insan kararı veya bildirim geçmişi eski veriden türetilmez.
- Bağımsız incelemede bulunan güncel CTI iddiası/geçmiş ve vaka kanıt
  bağı/geçmiş tutarsızlıkları artık açık hata verir; yanıltıcı etkinlik veya
  kuruluş ilişkisi gösterilmez. Raporlar ağsız, yazmasız, terminalden bağımsız
  servisler üzerinden çalışır. Ücretli API veya yeni paket bağımlılığı yoktur.
- Tam paket: 1.743 test / 509,592 saniye; 1.742 başarılı, bir Linux kontrolü
  macOS'ta atlandı. Hızlı kapı: 349 test / 131,370 saniye, aynı tek atlama.
  Gerçek veri kopyasında ve asıl verinin yedekli yükseltmesinde 127 eski tablo,
  86.843 satır korundu; geri dönüş yedeği yeni dosyaya kurtarılarak doğrulandı.
  Mevcut CTI kaynakları ve dört hedefli özel test kuruluşu gerçek CLI'de geçti.

## 0.133.0 — 14 Kasım 2026

- `organizations` ile kayıtlı domain ve seçili izlemeleri açık kullanıcı
  kararıyla gruplama; tam değişiklik geçmişi ve kaynak bağlantıları.
- `changes --days 1|7` ile başlangıç ölçümleri, gerçek değişimler, kaynak
  hataları ve kapsama boşlukları. Domain filtresi yalnız marka/dış yüzeydir;
  kaynak kimlikleri ve gösterilmeyen kayıt sayıları görünür kalır.
- Aynı MITRE indirmesinden eski CTI ve kesin kimlikli ATT&CK teknik/alt
  teknik/taktik kataloğunu atomik kaydetme. `cti attack-status/search/show`,
  ilişki sayfalaması, kaynak açıklamaları ve yaşam döngüsü geçmişi eklendi.
- `sources contribution DOMAIN` gerçek ortak/ayrı adresleri, kanıtları ve
  deneme oranlarını gösterir. Ölçülmüş ek katkı bulunmadan yeni sağlayıcı
  seçilmedi; ücretli API eklenmedi. Common Crawl dış erişim sorunu açık kalır.
- RansomLook yeni/değişen izleme eşleşmeleri tek yerel bildirim oluşturur;
  başlangıç, tekrar ve hata sessiz kalır. Bildirim, izleme ve toplama bağı
  aynı transaction'da kaydedilir; dış gönderim kendiliğinden başlamaz.
- `schedule generate/prepare`: Linux kullanıcı zamanlaması dosyaları,
  açık etkinleştirme, ortak kilit, kesilmiş oturum kurtarması, disk payı,
  benzersiz yedek ve yeni dosyaya geri yükleme doğrulaması. Yalnız sahipliği
  doğrulanan yönetilen yedeklerde saklama; yarıda kalan yayın/silme toparlanır.
  Özel karakterli yollar ve kaynak/kilit hata kodları korunur. Gerçek Linux
  hizmeti macOS üzerinde etkinleştirilmedi; Linux'a özel kontrol burada atlanır.
- Şema 56→59 yalnız 10 tablo ekler. Gerçek veritabanı kopyasında önceki 117
  tablonun bütün satırları korundu; yeni tablolar boş kaldı, geri dönüş yedeği
  ve yeniden kurtarma doğrulandı. Eski kanıttan yeni ilişki/bildirim türetilmez.
- Birleşik CLI kabulü kuruluş→profil→kaynak hatası→tek bildirim→yalnız eksik
  işi tekrar etme→dönem/kaynak raporu→ATT&CK ayrıntı zincirini ağsız sınar.
  Hızlı CI sınırı 10, büyüyen tam paket sınırı 30 dakikadır.
- Tam paket 1.649 testle 456,994 saniyede tamamlandı: 1.648 geçti, yalnız
  Linux systemd ayrıştırıcı testi bu macOS ortamında atlandı. Gerçek veri
  kopyasında 18 terminal komutu ve yedekten dönüş geçti; 15 salt okunur
  komut veritabanını değiştirmedi. Ağ/hizmet çağrısı yapılmadı.

## 0.132.0 — 14 Kasım 2026

- `collect` ve profil çalıştırmaları artık kalıcı toplama oturumu üretir.
  `collections list/show`, salt okunur `resume --plan`, eksik işleri yeni
  yürütmede tekrar eden `resume` ve açık kesinti kurtarması `recover` eklendi.
- Şema 56: dondurulmuş seçim/profil revizyonu, kaynak birimleri ve gerçek
  kaynak çalışmasıyla aynı transaction'da yazılan tamamlanma bağlantıları.
  Kaynak kaydı commit olup dış komut kapanamasa da başarı korunur.
- Ransomware yenilemesi ve izleme üyeleri ayrı kaydedilir; tamamlanan üye
  tekrar edilmez. Eksik üyeler yeni başarılı kaynak yenilemesine bağlanır;
  hata halinde eski snapshot kullanılmaz. Eski kısmi sonuç yeniden yazılmaz.
- Toplamaya ait scan işleri genel kuyruk/kurtarma işleminden ayrılır; yalnız
  kendi oturumu çalıştırır/kapatır. Bağımsız kaynak komutları korunur.
- Geçmiş okuması yeni analiz üretmez. Devam sonundaki güncel analiz açıkça
  ayrılır; analiz hatasında kaynaklar korunur. Açık migration önce geri dönüş
  yedeği alır, önceki kaynak kayıtlarından oturum geçmişi uydurmaz.
- Tam kontrol 1.536/1.536 testle geçti. Gerçek veritabanı kopyasında 114 eski
  tablonun içeriği geçişte korundu; kontrollü kaynak kesintisi sonrası yalnız
  iki eksik iş tekrarlandı, diğer kaynağın başarılı çalışması yerinde kaldı.
  Kabul denemesi ağsızdı; asıl veritabanını ve kaynak kayıtlarını değiştirmedi.

## 0.131.0 — 14 Kasım 2026

- Toplama seçimlerini `profiles save AD DOMAIN` ile kaydetme, listeleme,
  ayrıntı/geçmiş gösterme ve gerekçeyle geri çekme eklendi.
  `collect --profile AD [--plan]` kaydedilen tam seçimi kullanır.
- Varsayılanlar kayda açık yazılır; aynı adla save tam seçimi değiştirir.
  Değişmeyen seçim yeni revizyon yaratmaz. Domain/seçenek ile profilin
  aynı komutta karıştırılması reddedilir. Profil değişirse çalışma kilidi
  altında kaynak isteği başlamadan durulur.
- Şema 55 profil ve tam tanım geçmişi tablolarını ekler. Kanonik sürümlü
  tanım, SHA-256 ve yaşam döngüsü doğrulanır. Açık migration önce geri dönüş
  yedeği alır; mevcut kanıt ve inceleme kayıtları korunur.
- Profil gruplaması sahiplik bağlantısı oluşturmaz; kapatılmış izlemeye
  bağlı profil geçmişi okunabilir kalır, yeni çalışma engellenir. Dış API
  veya bağımlılık eklenmedi. Sekiz teslimin uygulanma sırası belgelendi.
- theHarvester'ın türetilmiş kanıt özeti artık normalleştirilmiş toplama
  zamanını da içerir. Aynı hostname daha sonra yeniden gözlendiğinde eski
  kayıtla çakışmaz; önceki kanıt/insan kararı korunur, aday çoğalmaz.
- Profil teslimi için tam paket 1.500/1.500 testle geçti. Gerçek veritabanı
  kopyasında 54→55 geçişi 112 eski tablonun içeriklerini korudu; profil ve
  önizleme ağsız doğrulandı. Son arşiv düzeltmesi ayrı ilgili testlerle sınandı.

## 0.130.0 — 14 Kasım 2026

- `collect` komutuna tekrarlanabilir `--username-watch`, `--ransomware-watch`
  ve `--ransomlook-watch` seçenekleri eklendi. Kayıtlı izlemeler açık kimlikle
  seçilir; temel `--task` seçimine veya varsayılan üç işe eklenir. Domain
  adından kullanıcı adı/kuruluş ilişkisi türetilmez.
- Bütün seçili izlemeler ağ öncesi ve ortak kilit altında doğrulanır.
  Her ransomware kaynağı bir kez yenilenir; yalnız seçilen izlemeler tam
  yenileme kimliğine bağlanır. Yenileme başarısızsa izlemeler atlanır;
  eski snapshot yeni sonuç gibi çalıştırılmaz, bağımsız kaynaklar devam eder.
- RansomLook izleme servisi beklenen kaynak kimliğini yazmadan önce
  doğrulayabilir. Mevcut başlangıç/fark, insan kararı ve bildirim davranışı
  korunur; yeni şema, bağımlılık veya dış kaynak eklenmez.
- Plan kaynak/ad/platformları, sonuçlar gerçek profil/iddia satırlarını,
  başlangıç/değişim ayrımını ve çalışma kimliklerini gösterir. En fazla 50
  izleme seçilebilir; `--watch-item-limit` 1–500 görünüm sınırıdır. Sonuçlar
  domain analizinden ayrı kalır; örtüşen kayıtlar benzersiz toplam sayılmaz.
- Yoğun makinede yardımcı Python işleminin geç başlaması nedeniyle iki
  süreç kilidi testi 5 saniyelik hazırlık sınırına takıldı. Testin süreç
  başlangıç/temizlik sınırı 30 saniyeye çıkarıldı; dışlama, serbest bırakma
  ve süreç ölümü sonrası kurtarma denetimleri korunur.
- Hızlı kontrol 198/198, son tam regresyon 1.476/1.476 testle geçti.
  Kayıtlı beş izleme ve varsayılan üç domain işi ağsız terminal/JSON
  önizlemesinde doğrulandı; veritabanı değişmedi. Çalıştırma, kesinti ve
  tekrar senaryoları geçici veride sahte kaynaklarla sınandı.

## 0.129.1 — 13 Kasım 2026

- Common Crawl'ın seçilen yıllık arşiv dönemleri için süre bütçesi 90'dan
  150 saniyeye çıkarıldı; Wayback'in ayrı 90 saniyesi korunur. İki kaynağı
  kapsayan dış süreç sınırı 270 saniye oldu.
- Common Crawl'da aralık istek başlangıcından değil, yanıtın bitişinden
  hesaplanır. Her istek sonrası en az bir saniye; bağlantı/zaman aşımı
  hatasında bütçe yeterliyse tek tekrar öncesinde 60 saniye beklenir.
  İstek/süre hakkı yoksa beklemeden asıl hata nedeni korunur.
- Common Crawl'da bekleme talimatı olmayan geçici 5xx için tekrar aralığı iki saniyedir;
  429/503 ve TLS davranışı değişmez. Profil v3, kabul kapısı v4;
  bağımlılıklar, upstream commit, kullanıcı kanıtları ve şema 54 korunur.
- Sahte saatli gerçek taşıma testi eski 90 saniyelik bütçenin 13 indeksli
  kapsamı yarıda kestiğini, yeni bütçenin tamamladığını doğrular. Kaynak
  sunucusunun 502/504 hatası başarı veya boş sonuç olarak gösterilmez.
- Hızlı kapı 172/172, tam regresyon 1.450/1.450 testle geçti. Katalog
  erişimi HTTP 200 ile geri geldi; son normal canlı denemede Common Crawl
  HTTP 504 ile başarısız, Wayback tamamlandı. Genel sonuç kısmi; Common
  Crawl'ın tam canlı kapsam kabulü açık kalır.

## 0.129.0 — 13 Kasım 2026

- `collect DOMAIN` kayıtlı domainin crt.sh/urlscan marka aramalarını ve
  crt.sh pasif keşfini aynı akışta çalıştırır; sonunda birleşik analiz verir.
  `--task` seçimi varsayılan listenin yerine geçer; isteğe bağlı arşiv ve
  Feodo/CERT Polska yenilemesi de seçilebilir. `--plan` ağsız ve yazmasızdır.
- Seçili işler ağ öncesinde doğrulanır; mevcut kaynak servisleri tek çalışma
  kilidini paylaşır. Kaynak hatasında diğer adımlar sürer, tamamlanan kayıtlar
  ve insan kararları korunur. Her kaynak kendi kimliği/sayacıyla gösterilir;
  kısmi/başarısız toplama son analizle başarıya dönüştürülmez.
- İş mantığı terminalden bağımsızdır; aynı modeller JSON çıktısında kullanılır.
  Şema 54 değişmez; hedefe aktif kontrol, dış bildirim, React/API veya kalıcı
  birleşik oturum eklenmez.
- Hızlı kapı 165/165, tam regresyon 1.443/1.443 testle geçti. Canlı kabulte
  beş seçili toplama adımı tamamlandı; mevcut aday korundu, yeni bulgu/aday
  oluşmadı. Common Crawl erişimi bu kabulde yeniden sınanmadı.

## 0.128.0 — 13 Kasım 2026

- theHarvester arşivleri için ayrı XTI işçisi ve sınırlandırılmış HTTPS
  taşıması eklendi. Sabit upstream seçim/ayrıştırma yardımcıları kullanılır;
  kurulu üçüncü taraf kaynak dosyaları değiştirilmez.
- Yutulan bağlantı hatasının boş sayfa/bozuk katalog olarak görünmesi
  giderildi. HTTP/TLS/kesinti/zaman aşımı ayrılır; 429/503 anında tekrarlanmaz,
  bekleme bilgisi korunur. Gerçek boş sonuç yalnız doğrulanmış yanıttır.
- Wayback tek domain sorgusu ve küçük devamlı sayfalar kullanır. Common
  Crawl sayfasındaki ilk 50 kayıt sonrasını atlayan davranış kaldırıldı.
  Bütçe ve sonuç sınırları kısmi kapsam olarak gösterilir; önceki sayfalar
  korunur. Profil v2, kabul kapısı v3; şema 54 değişmez.
- theHarvester standart paket olarak kurulur; editable `.pth` dosyasının
  gizli işaretlendiği ortamda import hatası önlenir. Kurulum kontrolü araç
  checkout'u dışında yapılır.
- Hızlı kapı 141/141, tam regresyon 1.419/1.419 testle geçti. İki canlı
  denemede Wayback tamamlandı; Common Crawl HTTP yanıtı vermeden bağlantıyı
  kapatmayı sürdürdü. Kaynak erişimi sorunu açık, genel sonuç kısmi kaldı.

## 0.127.1 — 13 Kasım 2026

- theHarvester kurulum betiği PATH'te `uv` yoksa proje içindeki
  `.tools/uv/bin/uv` aracını kullanır. Python ve önbellek varsayılan olarak
  `.tools` içinde tutulur; açık ortam ayarları korunur. Çekirdek Python
  ortamı ve sabit upstream commit/bağımlılık kilidi değişmez.
- İki arşiv de başarısız olduğunda doğrulanmış kaynak adı, durum ve durma
  nedeni hata açıklamasında korunur; başarısız çalışma boş sonuç sayılmaz.
- Günlük kullanım rehberine MITRE bilgi tabanı ve isteğe bağlı pasif arşiv
  kurulumu/keşfi eklendi. Şema 54 değişmez.
- Hızlı kapı 104/104, tam regresyon 1.382/1.382 testle geçti. Ayrı canlı
  kullanımda MITRE ilk/tekrar senkronu ve theHarvester kurulumu doğrulandı;
  arşiv kaynaklarının tam keşfi başarısız kaldığı için canlı kapsam kabulü
  açık tutuldu.

## 0.127.0 — 13 Kasım 2026

- `sources status`, 11 kaynak/iş akışının kurulumunu, son denemesini, son
  başarılı kaydını, güncelliğini, beklemesini ve sonraki komutunu tek terminal
  tablosunda gösterir. `--domain` tarama/keşfi daraltır; `--details` kanıtı açar.
- Kurulum ve geçmiş ağsız okunur; eksik veritabanı oluşturulmaz. MITRE ATT&CK
  için tutulmayan deneme geçmişi bilinmiyor kalır. Şema 54 korunur.
- Günlük kullanım rehberi ve bütünleşik toplama → inceleme → vaka → tekrar
  testleri eklendi. Aynı kanıt ve vaka hareketi gereksiz çoğalmaz; kaynak
  hatasından sonra son başarılı sosyal ölçümle karşılaştırma sürer.
- Hızlı kapı 84/84, tam regresyon 1.374/1.374 testle geçti.

## 0.126.0 — 13 Kasım 2026

- Pasif keşif sağlayıcıları domain katmanındaki tek `crt.sh`/`theharvester`
  sözleşmesine bağlandı. theHarvester ile kaydedilen adayın kaynak ayrıntısını
  ve ilgili bildirim yolunu açarken oluşan sağlayıcı doğrulama hatası giderildi;
  kullanıcı metinleri sağlayıcıdan bağımsız “pasif kaynak kanıtı” yapıldı.
- `surface discovery-health KÖK`, iki sağlayıcının son kayıtlı çalışmasını ayrı
  tamamlanma, veri, güncellik, hata ve sonraki komut bilgisiyle ağsız/salt
  okunur gösterir. `surface discovery-status KÖK --source ...` tek sağlayıcıyı
  seçer; eski varsayılan davranış korunur.
- `surface source-evaluation`, aktif adaptörlerin çalışma zamanı sağlayıcı
  kümesiyle birebir eşleşmesini zorunlu kılan sürümlü kabul kapısını ekledi.
  Subfinder v2.17.0 normal CLI'si, kaynak hatası ile tamamlanmış boş sonucu
  makine-okunur JSONL'de ayıramadığı ve bağımsız ücretsiz kapsam katkısı
  göstermediği için ertelendi; araç kurulmadı veya dağıtılmadı.
- Yeni görünüm ve kabul kararı veritabanı şemasını değiştirmez; şema 54 kalır.
- Kısa ağsız kapı 65/65, tam regresyon 1.355/1.355 testle geçti.

## 0.124.1 — 1 Kasım 2026

- Temiz bir klondan `./setup` ile global Python ortamını değiştirmeden yerel XTI
  kayıt alanını hazırlayan başlangıç komutu eklendi. Temel kullanım yalnız
  Python 3.11+ ister ve harici paket kurmaz.
- README'nin başına kısa klonlama, domain ekleme ve tarama akışı eklendi;
  `docs/GETTING_STARTED.md` veri konumu, yedek, güncelleme, açık migration ve
  isteğe bağlı Maigret/Sherlock kurulumunu tek sayfada toplar.
- GitHub Actions, `main` gönderimi ve pull request üzerinde Python 3.11 ile tam
  ağsız kontrol paketini salt-okunur izin ve 15 dakikalık üst sınırla çalıştırır.
- Kurulum eski veritabanını sessizce taşımaz; mevcut migration ve doğrulanmış
  kurtarma yedeği sözleşmesi korunur. Kullanıcı verisi ve yerel araç ortamları
  kaynak kontrolüne alınmaz.
- Temiz ve tekrarlı kurulum ile güncel-tarihli ransomware CLI fixture'ı dahil
  tam kontrolde 1.340 otomatik test 241,253 saniyede geçti. Testler interneti
  ve kullanıcı veritabanını kullanmadı.

## 0.124.0 — 31 Ekim 2026

- `cases create/list/show/update/status`, kişisel yerel vakayı başlık, özet, öncelik, açık durum ve zorunlu gerekçeyle yönetir. Çözme/kapatma sonuç açıklaması ister; kapatma açık görev varken reddedilir ve yeniden açma geçmişi korunur.
- `cases note-add`, `task-add/task-update` ve tek eklemeli zaman çizelgesi; gözlem/aksiyon/karar/kapanış notlarını ve açık/tamamlanmış/iptal görevleri vaka altında tutar. Kapalı vakada kanıt ve görev değişikliği önce açık yeniden açma ister.
- `cases evidence-add/remove`, mevcut domain/marka bulgusu, insan kararlı sosyal profil, ThreatCluster iddiası, RansomLook iddiası veya açıklanabilir tedarikçi kartının bütünlüğü denetlenmiş anlık görüntüsünü bağlar. Kaynak kaydı değiştirilmez; tekrar tekilleşir, değişen kaynak yenilenir ve çıkarılan bağ geçmişten silinmez.
- `cases report`, etkin kanıt, açık görev, durum, öncelik ve sonuç özetini ağsız terminal/JSON olarak üretir. Kayıtlar birleştirilmez; vaka otomatik saldırı, ihlal, sahiplik veya tedarikçi etkisi hükmü vermez.
- Şema 53→54, boş vaka, kanıt bağı, görev ve eklemeli aktivite tablolarını doğrulanmış yedekli transaction içinde ekler. Eski kayıtlardan vaka uydurulmaz; hata ana veritabanını şema 53'te bırakır. `doctor` vaka, açık vaka, etkin kanıt, açık görev ve aktivite sayılarını gösterir.
- Yaşam döngüsü, görevli kapanış kapısı, yeniden açma, notlar, beş kanıt türü, kaynak ayrımı, dondurulmuş kanıt, bozuk kayıtta güvenli durma, yedek–geri yükleme, terminal/JSON ve şema 53→54 migration/rollback yolları doğrulandı. Tam kontrolde 1.339 otomatik test 269,666 saniyede geçti; testler internet veya kullanıcı veritabanını kullanmadı.

## 0.123.0 — 31 Ekim 2026

- `suppliers risk-list`, etkin tedarikçi envanterini, insan tarafından kabul edilmiş güncel CNAME bağlarını, ThreatCluster/RansomLook kaynak kapsamını ve son yerel iddia adaylarını tek ağsız, salt-okunur terminal/JSON raporunda birleştirir.
- Her tedarikçi için iş önemi, iddia adayı ve eşleşen kaynak sayısı, domain/ad dayanağı, aynı-ad belirsizliği, güncel teknik bağımlılık sayısı, en yeni iddia/snapshot zamanı ve eksik/eski veri ayrı gösterilir.
- Açıklanabilir durumlar `priority_review`, `review`, `identity_review`, `insufficient_data` ve `no_current_match` olarak sınırlıdır. Yüksek/kritik iş önemi yalnız açıklanabilir ve kuruluş bağı belirsiz olmayan kaynak adayı varsa incelemeyi öne alır; aynı isim belirsizliği önce kimlik incelemesine gider.
- `suppliers risk-show`, kartın bütün nedenlerini, eksik veri listesini, önerilen insan adımlarını, kaynak kapsamını, CNAME aday kimliklerini ve kaynak iddiası kimliklerini gösterir. Kayıtlar birleşmez ve özgün kanıt kimliklerini korur.
- Kart sayısal risk skoru, doğrulanmış ihlal, kullanıcı etkisi, alarm veya dış aksiyon değildir. Başarılı boş kaynak sonucu ile hiç/başarısız kaynak verisi ayrı kalır. Şema 53 değişmedi ve migration gerekmez.
- İş önemi, CNAME bağı, iki kaynaklı iddia, aynı-ad belirsizliği, eksik/başarılı-boş kaynak ayrımı, pasif tedarikçi dışlama, girdi doğrulama ve ağsız salt-okunur terminal/JSON yolları doğrulandı. Tam kontrolde 1.329 otomatik test 262,780 saniyede geçti; testler internet veya kullanıcı veritabanını kullanmadı.

## 0.122.0 — 31 Ekim 2026

- `suppliers event-list`, etkin insan onaylı tedarikçileri ThreatCluster ve RansomLook'un son başarılı yerel snapshot'larıyla ağsız eşleştirir. `--supplier` ve `--source` filtreleri ile terminal/JSON görünümü vardır; komut kaynak yenilemez ve hiçbir kayıt yazmaz.
- ThreatCluster için tam normalleştirilmiş kuruluş adı ve kaynağın sağladığı ilk-taraf web domaini; RansomLook için yalnız tam normalleştirilmiş kuruluş adı kullanılır. Yaklaşık benzerlik yoktur. Aynı isimli ayrı tedarikçiler ayrı adaylar olarak kalır ve ad belirsizliği açıkça gösterilir.
- `suppliers event-show`, kararlı olay adını, özgün kaynak/snapshot/kayıt kimliğini ve özetini, grup/kuruluş/zamanı, eşleşme alanlarını ve tedarikçi iş önemini gösterir. Kaynak kayıtları birleştirilmez; iddia doğrulanmış ihlal, tedarikçi etkisi, alarm veya risk puanı sayılmaz.
- Kaynağın hiç toplanmaması, başarılı snapshot, son deneme hatasından sonra kullanılan eski başarılı snapshot ve başarılı snapshot bulunmayan hata ayrı kapsama durumlarıdır. Bozuk tedarikçi veya kaynak geçmişi kısmi sonuç üretmeden reddedilir.
- Şema 53 değişmedi ve migration gerekmez. Bu dilim mevcut tedarikçi ve ransomware geçmişlerini yalnız salt okunur kullanır.
- İki kaynak ayrımı, aynı isim belirsizliği, domain ve ad dayanaklarının ayrılması, tedarikçi/kaynak filtreleri, eksik ve eski-hata kapsamı, pasif tedarikçi dışlama, bozuk kaynakta güvenli durma, kararlı kimlik, salt-okunur terminal/JSON ve önceki tedarikçi/ransomware davranışları doğrulandı. Tam kontrolde 1.324 otomatik test 264,783 saniyede geçti; testler internet veya kullanıcı veritabanını kullanmadı.

## 0.121.0 — 31 Ekim 2026

- `suppliers candidate-refresh`, etkin ve açıkça onaylanmış dış yüzey kapsamındaki son kayıtlı CNAME kanıtlarını ağsız inceler. Kaynak ve hedef Public Suffix List kayıt kökleri farklıysa yalnız teknik dış hizmet adayı oluşturur; aynı kökü eler, kuruluş adı veya sahiplik tahmin etmez.
- Adaylar varlık + dış hizmet kayıt köküyle tekilleştirilir. Yeni CNAME kontrolleri ayrı kaynak kanıtı olarak eklenir; son kanıtta görünmeyen ilişki silinmeden tarihsel duruma geçer. Kullanılan PSL sürümü ve SHA-256 özeti her türetmede saklanır.
- `candidate-list/show/review`, bekleyen, kabul edilen, belirsiz ve reddedilen durumları terminal/JSON olarak sunar. Kabul yalnız önceden insan tarafından eklenmiş etkin tedarikçiye bağlanabilir; karar başka tedarikçiye taşınabilir, belirsiz/ret/bekleyen duruma döndürülebilir ve bütün kararlar gerekçeli geçmişte korunur.
- CNAME hedefi kuruluş, sözleşme, güven veya risk kanıtı sayılmaz. Otomatik birleştirme, risk puanı, alarm, internet isteği ve dış aksiyon yoktur. Bozuk aday, kaynak kanıtı veya karar zinciri kısmi sonuç ya da sessiz onarım üretmeden reddedilir.
- Şema 52→53 üç boş aday/kanıt/karar tablosunu doğrulanmış yedekli transaction içinde ekler; tedarikçi envanterini ve bütün eski veriyi korur. `doctor` güncel/bekleyen/toplam aday, kanıt ve karar sayılarını gösterir.
- Aday üretimi, kanıt geçmişi, tarihsel duruma geçiş, insan kararı ve geri alma, bozuk kayıtta güvenli durma, terminal/JSON, doctor sayaçları, yedek–geri yükleme ve veri içeren şema 52→53 migration/rollback yolları doğrulandı. Tam kontrolde 1.319 otomatik test 249,261 saniyede geçti; testler internet veya kullanıcı veritabanını kullanmadı. Bu sürüm mevcut `.xti-data` veritabanını kendiliğinden taşımaz; açık `./xti migrate` gerekir.

## 0.120.0 — 31 Ekim 2026

- `suppliers add/list/show/update/revoke`, insanın açıkça onayladığı tedarikçi ilişkisini kuruluş adı, değiştirilemez ana domain, ilişki türü, iş önemi ve gerekçeyle yerel olarak yönetir. Komutlar ağ isteği, otomatik aday, risk puanı veya alarm üretmez.
- Aynı isim farklı ana domainlerde ayrı kuruluş kaydıdır; ana domain tekildir ve ortak isim ya da altyapı otomatik birleşim sebebi değildir. Etkin aynı domainin farklı kuruluş bilgisiyle yeniden eklenmesi sessizce üzerine yazılmaz.
- Ekleme, güncelleme, pasife alma ve yeniden etkinleştirme olayları tam alan anlık görüntüsüyle eklemeli geçmişte korunur. Aynı istek idempotenttir; liste ve ayrıntı salt okunurdur. Bozuk güncel kayıt–olay zinciri kısmi görünüm üretmeden reddedilir.
- Şema 51→52, boş tedarikçi ve olay tablolarını doğrulanmış yedekli transaction içinde ekler; mevcut bütün veriyi korur ve hata halinde şema 51'e geri döner. `doctor` etkin/toplam tedarikçi ve değişiklik olayı sayılarını gösterir.
- Tedarikçi yaşam döngüsü, aynı isimli ayrı kuruluşlar, doğrulama ve bozuk geçmiş, yedek–geri yükleme, terminal/JSON ve şema 51→52 migration/rollback testleri eklendi. Tam kontrolde 1.311 otomatik test 251,781 saniyede geçti; testler internet veya kullanıcı veritabanını kullanmadı. Bu sürüm mevcut `.xti-data` veritabanını kendiliğinden taşımaz; açık `./xti migrate` gerekir.

## 0.119.0 — 31 Ekim 2026

- `./scripts/setup-harvester`, güncel theHarvester upstream'ini tam `6790b147f52309e4eee22ed941db1d285ab2ec23` commit'ine sabitlenmiş ayrı Python 3.14/`uv` ortamına isteğe bağlı kurar. Üçüncü taraf kodu XTI çekirdeğine veya varsayılan bağımlılıklara eklenmez.
- `surface discover/watch KÖK --source theharvester`, yalnız Common Crawl ve Wayback Archive P0 hostname kaynaklarını çalıştırır. DNS çözümleme/brute force, e-posta ve kişi toplama, screenshot, takeover, API scan, proxy ve doğrudan hedef işlemleri kapalıdır.
- Adaptör sabit iki kaynak, 250 sonuç, tek işçi, geçici HOME/veri alanı, 180 saniye ve çıktı boyutu sınırı kullanır. Checkout commit'i ile çalıştırılabilir dosyanın konumu her çağrıda doğrulanır.
- JSONL özeti ve bulguları tekrar alan, tam alan kümesi, UTC zaman, kaynak durum/sayaç, boş aktif işlem, sonuç türü ve kesin alt alan adı kapsamıyla doğrulanır. Beklenmeyen veri kısmi kaydedilmeden reddedilir; iki kaynak da başarısızsa boş başarı üretilmez.
- Common Crawl ve Wayback gözlemleri aynı aday altında ayrı kaynak kanıtı olur. Sağlayıcı kimliği çalışma geçmişinde, terminalde ve JSON'da korunur; mevcut aday kararı, tekil bildirim ve salt-okunur inceleme yolları yeniden kullanılır.
- Kaynak kataloğu, ücretsiz araç kabul kapısı, kullanım belgesi ve GPL-2.0-only üçüncü taraf bildirimi güncellendi. Arşiv kaydı sahiplik, güncel erişilebilirlik veya risk hükmüne çevrilmez.
- Şema 50→51 yalnız pasif kaynak ve çalışma provider denetimlerini genişletir. Mevcut crt.sh kanıtları, çalışma sıraları ve bildirimler doğrulanmış yedekli transaction içinde korunur; hata halinde canlı şema 50'ye geri alınır.
- Tam kontrolde 1.303 otomatik test 240,698 saniyede geçti. Testler internet kullanmadı; gerçek `.xti-data` veritabanı açılmadı veya değiştirilmedi. Canlı theHarvester kurulumu yerel ortamda `uv` bulunmadığı için yapılmadı; kurulum betiği kabuk sözdizimi, adaptör ise sahte süreç ve katı fixture sözleşmesiyle doğrulandı.

## 0.118.0 — 31 Ekim 2026

- `brand watch-add ... --source maigret|sherlock`, kalıcı sosyal kullanıcı adı izlemesini oluşturulduğu kaynağa değiştirilemez biçimde bağlar. Varsayılan Maigret'tir; Sherlock yalnız kendi sekiz platformluk kısa listesini kabul eder.
- Aynı kullanıcı adı iki farklı yerel izleme adıyla iki kaynakta izlenebilir. Her izleme kendi sessiz başlangıcını, başarılı/başarısız çalışma zincirini ve farklarını taşır; Maigret sonucu Sherlock başlangıcıyla karşılaştırılmaz.
- `watch-run`, `watch-run-all` ve `watch-monitor`, kaynak seçimini kayıtlı izleme tanımından yapar. Karma toplu çalışma her kaydı doğru adaptöre yollar; terminal ve JSON tanım/çalışma/toplu sonuçlarında kaynak kimliği korunur.
- Sherlock'ta bulunan tam profiller de mevcut gerekçeli `known_official`, `possible_impersonation` ve `uncertain` insan kararlarını kullanır. Profil adresi değiştiğinde kararın yeni kanıta taşınmaması ve yalnız olası taklit kararının yerel bildirim üretmesi kuralları değişmez.
- İzleme kaynağı aynı ad altında değiştirilemez; kullanıcıdan farklı izleme adı istenir. Kaynak, platform ve profil hostu uyumsuzluğu kayıt öncesinde veya bütünlük denetiminde kapalı biçimde reddedilir.
- Şema 49→50 geçişi, mevcut bütün izlemeleri geçmiş çalışmaları ve insan kararlarını yeniden yazmadan `maigret` kaynağına bağlar. Geçiş önce doğrulanmış şema 49 yedeği üretir; yeni Sherlock geçmişi uydurulmaz.
- Otomatik testlerde kaynak yalıtımı, karma toplu yönlendirme, kaynak değiştirme reddi, Sherlock karar zinciri ve veri içeren şema 49 geçişi doğrulandı. Tam kontrolde 1.294 otomatik test 221,064 saniyede geçti; testler internet kullanmadı ve kullanıcının `.xti-data` veritabanına dokunulmadı.

## 0.117.0 — 31 Ekim 2026

- `brand username-preview KULLANICI_ADI --source sherlock`, Sherlock 0.16.2 ile yalnız Carrd, CashApp, CodeSandbox, GitBook, ResearchGate, Rumble, Strava ve Weebly arasından seçilen en fazla sekiz herkese açık platformda canlı ve yazmasız önizleme yapar. Varsayılan kapsam Carrd, CodeSandbox, GitBook, Rumble ve Weebly'dir.
- `./scripts/setup-brand`, Sherlock'u resmî `sherlock-project/sherlock` deposunun tam `a38ba54fda799cd786a2ab67a50143e1a63169e6` commit'inden Maigret ile birlikte isteğe bağlı `.venv` ortamına kurar. Çekirdek kurulum bu bağımlılıkları almaz.
- Kurulu Sherlock sürümü ve 104.039 baytlık site kataloğunun `3fdfc669…a9fb30` SHA-256 özeti her çalışmada doğrulanır. Yalnız seçilen tanımlar geçici kataloğa alınır; URL alanları incelenmiş HTTPS/443 host listesiyle sınırlandırılır.
- Sherlock CLI, yerel katalog seçilmiş olsa da ek GitHub sürüm isteği yaptığı için kullanılmaz. Sabit `sherlock()` kütüphane işlevi yalıtılmış işçide çağrılır; geniş katalog, canlı katalog/exclusion, proxy, Tor/I2P, toplu kullanıcı adı, türetme ve profil çıkarımı kapalıdır.
- İşçi, upstream rapor dosyaları yerine yalnız kullanıcı adı, platform, profil adresi ve durum taşıyan XTI NDJSON çıktısını oluşturur. Ana süreç alan kümesi, tekrar, boyut, kullanıcı/platform bağı, durum ve HTTPS/443 profil hostunu yeniden doğrular; ham HTTP yanıtını veya profil ayrıntısını tutmaz.
- Yalnız `Claimed`, `found_unverified` olarak gösterilir. Diğer durumlar “raporlanmadı” kalır; hesap yokluğu, sahiplik veya taklit hükmü üretilmez. Önizleme XTI veritabanını açmaz veya yazmaz.
- Kapsam kanıtı `free-social-source-coverage-gate-v2` olarak düzeltildi: eski CLI/CSV varsayımı kaldırıldı; uygulanan yalıtılmış kütüphane işçisi, XTI NDJSON sözleşmesi ve sıradaki kaynak-yalıtımlı kalıcı sosyal fark açıkça kaydedildi.
- Şema 49 değişmedi ve migration gerekmez. Tam kontrolde 1.288 otomatik test 240,279 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı. Ayrı canlı kabulde yalnız Carrd seçilerek upstream katalog örneği `blue`, `https://blue.carrd.co/` adresinde “bulundu, doğrulanmadı” olarak raporlandı. Geçici veri yolu oluşmadı; kullanıcının `.xti-data` veritabanına dokunulmadı.

## 0.116.0 — 31 Ekim 2026

- `brand source-coverage`, sabit Maigret 0.6.6 ve Sherlock 0.16.2 kataloglarının bağımsız sosyal kullanıcı adı kapsamını ağsız, salt-okunur ve sürümlü kanıtla gösterir.
- Sherlock resmî v0.16.2 etiketi tam `a38ba54fda799cd786a2ab67a50143e1a63169e6` commit'ine; katalog 104.039 bayt ve `3fdfc669…a9fb30` SHA-256 özetine sabitlenmiştir. Maigret'in mevcut incelenmiş katalog özeti ve güncel paketli Public Suffix List profili karşılaştırmaya bağlanır.
- Etkin/HTTPS/doğrudan kullanıcı adı filtresinde Maigret 6.628, Sherlock 455 uygun tanım taşır. Normalleştirilmiş ad veya kayıt kökü eşleştirmesinde Sherlock'un 352 tanımı ortak; 103 tanımı, 102 hostu ve 101 kayıt kökü eşleşmeyen kapsamdır.
- Mevcut güvenli 10 platformun 9'u ortaktır; Facebook yalnız Maigret'tedir ve Sherlock mevcut listeye yeni platform eklemez. Bağımsız genişleme kanıtı nedeniyle Sherlock bütün katalog yerine sekiz platformluk elle incelenmiş kısa liste için sınırlı adaptör adayı olarak kabul edilmiştir.
- Profil tam alan kümesi, tekrar alan reddi, boyut, sabit SHA-256, HTTPS başvuruları, kaynak/karşılaştırma sayaç bağları, zorunlu ölçütler ve tekil kısa listeyle güvenli biçimde doğrulanır. Terminal ve JSON komutları internet, araç kurulumu, kullanıcı adı sorgusu veya veri klasörü kullanmaz.
- Şema 49 değişmedi ve migration gerekmez. Tam kontrolde 1.280 otomatik test
  228,006 saniyede geçti. Ayrı upstream kabulünde Sherlock v0.16.2 etiketi tam
  commit'e çözüldü, resmî katalog geçici alanda 104.039 bayt ve beklenen
  SHA-256 özetiyle doğrulandı; ağsız terminal/JSON kapısı beklenen sayaçları
  verdi. Kullanıcının `.xti-data` veritabanına dokunulmadı.

## 0.115.0 — 31 Ekim 2026

- `brand watch-monitor IZLEME_KIMLIGI`, tek etkin sosyal kullanıcı adı izlemesini yalnız terminal açıkken sınırlı tur, aralık ve toplam yeni-tur başlatma bütçesiyle tekrarlar.
- Varsayılan 3 tur, 3600 saniye aralık ve 86400 saniye bütçe; zorunlu sınırlar 1–1000 tur, 300–86400 saniye aralık ve 1–604800 saniye bütçedir. Platform istek süresi mevcut 5–30 saniye sınırını korur.
- Her tamamlanan tur mevcut tekil `watch-run` yolunda ayrı atomik çalışma olarak saklanır. Kaynak hatası hesap yokluğu sayılmadan başarısız tur olur ve bütçe kaldığında sonraki tur denenir.
- Süre monoton saatle ölçülür. Süre dolunca yeni tur başlamaz; başlamış kaynak işi kendi sınırıyla tamamlanabilir. `Ctrl+C` tamamlanan turları silmez.
- Terminal ve JSON planlanan/tamamlanan, başarılı/kaynak hatalı tur sayılarını ve her çalışma kimliğini gösterir. Herhangi bir kaynak hatası çıkış kodu 3 ve JSON `ok:false` üretir.
- Bütün monitor boyunca ortak yerel çalışma kilidi tutulur. Zamanlayıcı, daemon, otomatik devam, taklit kararı veya bildirim eklenmez. Şema 49 değişmedi ve migration gerekmez.
- Tam kontrolde 1.276 otomatik test 221,261 saniyede geçti. Geçici canlı
  kabulte tek etkin GitHub `octocat` izlemesi yeni monitor komutuyla bir tur
  çalıştı ve ayrı çalışma kimliği kaydedildi. Kaynak hatası oluşmadı; kaynak bu
  turda profil bildirmediği için sistem hesap yokluğu hükmü üretmeden sıfır
  bulgu gösterdi. Kullanıcının `.xti-data` veritabanına dokunulmadı.

## 0.114.0 — 31 Ekim 2026

- `brand watch-run-all`, bütün etkin sosyal kullanıcı adı izlemelerini görünen ad ve kimliğe göre kararlı sırada tek kez çalıştırır. Geri çekilmiş izlemeler kapsama alınmaz.
- Varsayılan en fazla 10, açık seçimle en fazla 100 izleme çalıştırılabilir. Etkin izlemelerin tamamı sınıra sığmıyorsa hiçbir kaynak çağrısı veya çalışma kaydı başlamadan açık hata verilir.
- Her izleme mevcut tekil `watch-run` yolundan geçer ve ayrı atomik kanıt oluşturur. Bir Maigret kaynak hatası başarısız çalışma olarak saklanır, önceki başarılı ölçümü silmez ve sonraki izlemeyi engellemez; depolama/bütünlük hatası yeni izleme başlatmayı durdurur.
- Terminal ve JSON özeti planlanan/tamamlanan, başarılı/kaynak hatalı izleme sayılarını ve her izleme çalışma kimliğini ayrı gösterir. Kaynak hatası bulunan toplu çalışma çıkış kodu 3 ve JSON `ok:false` üretir.
- Toplu komut bütün ömründe ortak yerel çalışma kilidini tutar; zamanlayıcı, daemon, otomatik taklit kararı veya bildirim oluşturmaz. Şema 49 değişmedi ve migration gerekmez.
- Tam kontrolde 1.269 otomatik test 210,699 saniyede geçti. Geçici canlı kabulte tek etkin GitHub izlemesi yeni toplu komutla çalıştırıldı ve ayrı çalışma kimliği kaydedildi. Kaynak bu turda profili raporlamadığı için sonuç açıkça “artık raporlanmayan” olarak kaldı; hesap yokluğu veya kaldırılma hükmü üretilmedi. Kullanıcının `.xti-data` veritabanına dokunulmadı.

## 0.113.0 — 31 Ekim 2026

- Yeni bir tam sosyal profil `possible_impersonation` olarak gerekçeli biçimde işaretlendiğinde karar olayı ve ortak yerel kutu bildirimi aynı transaction içinde yazılır. Bildirim yazılamazsa karar da geri alınır.
- `known_official` ve `uncertain` kararları bildirim üretmez. Aynı tam profil adayı en fazla bir bildirim oluşturur; aynı karar tekrarı veya gerekçe/karar değişikliği alarm çoğaltmaz. Profil adresi değişirse farklı kanıta bağlı yeni bildirim oluşturulabilir.
- `inbox list/show/read/unread`, olası taklit bildiriminin izleme adı, platformu, tam profil adresi, bildirimi oluşturan karar/gerekçe ve güncel kullanıcı kararını gösterir. Sonraki karar değişikliği tarihsel bildirim kanıtını silmez veya yeniden yazmaz; okundu durumu karardan bağımsızdır.
- Bildirim mevcut manuel webhook dışa teslimiyle uyumludur fakat otomatik dış teslim, e-posta/SMS veya takedown başlatmaz. Şema 48→49 açık `migrate` ile doğrulanmış yedek alıp boş bildirim tablosu ekler; eski olası taklit kararlarından geriye dönük bildirim uydurulmaz.
- Tam kontrolde 1.262 otomatik test 211,585 saniyede geçti. Geçici canlı kabulte GitHub `octocat` kararı olası taklit olarak güncellendi, tek ortak kutu bildirimi oluştu ve terminal ayrıntısı tam profil/karar bağıyla doğrulandı. Kullanıcının `.xti-data` veritabanına dokunulmadı.

## 0.112.0 — 31 Ekim 2026

- `brand watch-review IZLEME_KIMLIGI PLATFORM`, son başarılı güncel izleme sonucunda bulunan tam profil için zorunlu gerekçeli `known_official`, `possible_impersonation` veya `uncertain` insan kararı kaydeder. `watch-review-show` dondurulmuş kanıtı ve silinmeyen karar zincirini ağsız gösterir.
- Karar izleme tanımı, platform ve profil durum hash'ine bağlanır. Profil adresi değişince yeni aday kimliği oluşur; eski “resmî” kararı yeni adrese taşınmaz. Aynı karar+gerekçe idempotenttir, değişiklik önceki olaya bağlı yeni kayıt ekler.
- `watch-run` ve `watch-run-show`, tam profil durumu için varsa kullanıcı kararını, gerekçeyi ve zamanı gösterir. Kaynak hatası son başarılı adayı silmez; son başarılı çalışmada raporlanmayan platforma veya henüz çalıştırılmamış yeni tanıma karar verilemez.
- Bu katman otomatik alarm, ortak gelen kutusu, sahiplik doğrulaması veya dış aksiyon üretmez. Şema 47→48 açık `migrate` ile doğrulanmış yedek alıp boş karar olayı tablosu ekler; eski sonuçlardan karar uydurulmaz.
- Tam kontrolde 1.254 otomatik test 231,941 saniyede geçti. Geçici canlı kabulte önceki iki turlu GitHub `octocat` kanıtı şema 48'e taşındı; tam profil `known_official` işaretlendi ve kayıtlı çalışma görünümünde karar gösterildi. Kullanıcının `.xti-data` veritabanına dokunulmadı.

## 0.111.0 — 31 Ekim 2026

- `brand watch-add/list/show/revoke/run/run-show`, seçili Maigret platformları için kalıcı kullanıcı adı izleme tanımı, silinmeyen yaşam döngüsü ve ağsız geçmiş görünümü ekler.
- İlk başarılı çalışma sessiz başlangıçtır. Sonraki çalışmalar yeni bulunan, profil adresi değişen, artık raporlanmayan, bulunup değişmeyen ve raporlanmayıp değişmeyen platformları ayrı kanıt olarak saklar. Bu durumlar sahiplik, taklit veya hesap silinmesi hükmü değildir.
- Kaynak hatası ayrı başarısız çalışma olarak saklanır; önceki başarılı çalışma korunur ve boş sonuç gibi karşılaştırılmaz. Sonuçlarda yalnız platform, doğrulanmamış profil HTTPS adresi, durum ve bütünlük özeti tutulur; ham Maigret yanıtı saklanmaz.
- Şema 46→47 açık `migrate` ile önce doğrulanmış yedek alır ve dört boş sosyal kullanıcı adı izleme tablosu ekler. Eski önizlemelerden geçmiş uydurulmaz; başarısız geçiş tümüyle geri alınır.
- `doctor`, etkin/toplam izleme, toplam çalışma ve kaynak hatası sayılarını gösterir. Tam kontrolde 1.246 otomatik test 207,988 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı.
- Geçici canlı kabulte GitHub `octocat` profili ilk turda sessiz başlangıç, ikinci turda `bulundu, değişmedi` olarak kaydedildi. Kullanıcının `.xti-data` veritabanına dokunulmadı.

## 0.110.0 — 31 Ekim 2026

- `./scripts/setup-brand`, Maigret 0.6.6'yı resmî `soxoj/maigret` reposunun tam `b8747b98820f4df9d1baf23235db7b2cb55d0198` commit'inden proje içindeki `.venv` ortamına kurar. Çekirdek kurulum bu geniş bağımlılık ağacını zorunlu almaz.
- `brand username-preview KULLANICI_ADI`, yalnız açıkça seçilen en fazla on herkese açık platformda canlı ve yazmasız kullanıcı adı önizlemesi yapar. Terminal ve JSON, yalnız platform, profil HTTPS adresi ve `found_unverified` durumunu gösterir; aynı kullanıcı adı sahiplik veya taklit kanıtı değildir.
- Maigret kabuksuz ayrı süreçte, sabit sürüm, süre/çıktı boyutu, kapalı proxy/AI/özyineleme/domain arama/otomatik güncelleme ve geçici HOME ayarlarıyla çalışır. Ham yanıt, çıkarılmış profil alanları ve üçüncü taraf kimlikleri XTI modeline alınmaz.
- Upstream site veritabanı sabit SHA-256 ile doğrulanır ve her çalışmada yalnız tam seçilen platformlara geçici olarak daraltılır. Böylece upstream ayna/kaynak davranışı seçilmeyen yan sitelere istek göndermez; platform adresleri ayrı HTTPS host allowlist'iyle doğrulanır.
- Canlı kabulte yalnız GitHub seçilerek kamuya açık `octocat` profili bulundu ve XTI veri klasörü oluşturulmadı. Şema 46 değişmedi; migration gerekmez.
- Tam kontrolde 1.237 otomatik test 197,153 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı.

## 0.109.0 — 31 Ekim 2026

- `brand source-evaluation`, Maigret, Sherlock, theHarvester, Web-Check, Holehe ve olası telefon hesabı aracını sürümlü, ağsız ve yazmasız kabul kapısında karşılaştırır.
- Maigret'in dar ayrı CLI adaptörü seçildi. Sherlock yinelenen ilk kaynak; theHarvester domain genişlemesi olarak ertelendi. Web-Check kapsam çakışması, Holehe ve telefon hesabı yoklama yaklaşımı ise hesap-kurtarma/kişisel veri etkisi nedeniyle bu dilime alınmadı.
- Rapor terminal ve kararlı JSON ile veri dizini oluşturmadan çalışır. Şema 46 değişmedi ve migration gerekmez. Tam kontrolde 1.229 otomatik test 205,689 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı.

## 0.108.0 — 30 Ekim 2026

- `ransomware source-review KARSILASTIRMA_KIMLIGI`, son yerel kaynak karşılaştırmasındaki iki özgün claim için gerekçeli `possible_same`, `different` veya `uncertain` insan kararı kaydeder. Karar kaynak kayıtlarını birleştirmez, alarm/inbox oluşturmaz ve ihlal doğrulaması değildir.
- `ransomware source-review-show`, ilk kararda dondurulan kaynak snapshot/claim kanıtını ve silinmeyen karar zincirini ağsız gösterir. Aynı karar+gerekçe idempotenttir; değişiklik önceki olaya bağlanan yeni olaydır.
- `ransomware source-compare`, varsa güncel insan kararını ve gerekçesini adayın yanında gösterir; karşılaştırma görünümü salt okunur kalır. Yeni kaynak snapshot'ları önceki karar kanıtını değiştirmez.
- Karar yazımı güncel karşılaştırma adayını ve iki kaynak geçmişini transaction içinde yeniden denetler. Bozuk kaynak, özet, kanıt hash'i, olay bağı veya gerileyen saat kısmi yazma ve sessiz onarım olmadan güvenli biçimde durur.
- Şema 45→46 açık `migrate` ile önce doğrulanmış yedek alır ve boş `ransomware_source_review_events` tablosunu ekler. Eski snapshot'lardan karar uydurulmaz; başarısız geçiş geri alınır.
- Karar ekleme/güncelleme/idempotent tekrar, kanıt dondurma, yeni snapshot sonrası eski kanıtı koruma, terminal/JSON, salt-okunur görünüm, bozuk zincir/hash, yedek–geri yükleme, kaynak izolasyonu ve şema 45→46 migration/rollback doğrulandı. Tam kontrolde 1.227 otomatik test 213,476 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı.

## 0.107.0 — 30 Ekim 2026

- `ransomware source-compare`, son başarılı yerel ThreatCluster ve RansomLook snapshot'larını internete çıkmadan ve kayıt yazmadan karşılaştırır. İki kaynak çalışma bağlamı ve iki özgün claim sonuçta ayrı kalır.
- Sonuç için kuruluş adı normalleştirilmiş biçimde tam aynı olmalı; ayrıca grup adı veya kanonik keşif zamanı eşleşmelidir. Aynı/farklı ortak alanlar ve kararlı karşılaştırma kimliği terminal/JSON sonucunda açıklanır; yalnız isim, yalnız grup/zaman ve fuzzy benzerlik elenir.
- Görünüm sınırı tam toplamı değiştirmez. Bozuk kaynak geçmişi tüm karşılaştırmayı güvenli durdurur; 100.000 aday başvurusu ve 50.000 sonuç işlem sınırı sessiz kırpılmaz.
- Komut kaynak claim'lerini birleştirmez, alarm/inbox kaydı veya ihlal hükmü üretmez. Şema 45 değişmedi ve migration gerekmez.
- Üç açıklanabilir eşleşme temeli, zayıf çiftlerin elenmesi, kararlı kimlik/sıra, iki özgün kaydın korunması, görünüm sınırı, eksik snapshot yönlendirmesi, ağsız ve salt-okunur terminal/JSON akışı, bozuk geçmişte güvenli durma ve kaynak kataloğu doğrulandı. Tam kontrolde 1.218 otomatik test 255,541 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı.

## 0.106.0 — 30 Ekim 2026

- `ransomware watch-add ... --kind organization --source ransomlook`, RansomLook'un yalnız kaynakta bulunan gönderi/kuruluş başlığı üzerinde tam veya sınırlı içerme eşleşmeli kalıcı izleme tanımlar. Kaynak domain sağlamadığı için domain türü yazma ve ağ öncesi reddedilir.
- `watch-list/show/revoke/run/run-show --source ransomlook`, ThreatCluster'dan ayrı tanım, olay, çalışma ve sonuç geçmişini terminal/JSON üzerinden yönetir. İlk çalışma ve değişen tanım sessiz başlangıçtır; sonraki yeni/değişen eşleşmeler kalıcı çalışmada insan inceleme adayı olarak ayrılır.
- RansomLook izlemesi yalnız son başarılı yerel snapshot üzerinde ağsız çalışır. Kaynak penceresinden çıkış dikkat adayı, çözüm veya kapatma sayılmaz. Bu dar sürüm ortak gelen kutusu, toplu yenileme, monitor veya otomatik kaynaklar arası birleştirme eklemez.
- Şema 44, açık `migrate` ve doğrulanmış yedek sonrası şema 45'e çıkar. Dört yeni kaynak-yalıtımlı izleme tablosu boş başlar; başarısız DDL geri alınır ve geçiş öncesi yedek korunur.
- Sessiz başlangıç, sonraki yeni eşleşme, yalnız pencereden çıkış, tanım değişimi, geri çekme, kaynak izolasyonu, bozuk kayıtta güvenli durma, yedek–geri yükleme ve şema 44→45 migration/rollback davranışları doğrulandı. Tam kontrolde 1.213 otomatik test 228,078 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı.

## 0.105.0 — 30 Ekim 2026

- `ransomware refresh --source ransomlook`, katı doğrulanmış yedi günlük RansomLook snapshot'ını ThreatCluster'dan ayrı çalışma ve fark tablolarına kaydeder. İlk başarılı snapshot yalnız başlangıç çizgisidir; sonraki çalışmalarda yeni, aynı ve pencereden çıkan kayıtlar ayrılır.
- `ransomware status --source ransomlook`, son deneme, son başarılı snapshot ve sınırlı çalışma geçmişini internete bağlanmadan gösterir. Kaynak hatası ayrı başarısız çalışma olarak denetlenir; önceki başarılı durum silinmez.
- RansomLook geçmişi yalnız kaynağın sunduğu grup, başlık ve keşif zamanını taşır. Pencereden çıkış silinme/çözüm hükmüne çevrilmez; ThreatCluster kayıtları, izlemeleri, bildirimleri ve kimlikleriyle yabancı anahtar veya otomatik birleştirme kurulmaz.
- Şema 43, açık `./xti migrate` ve doğrulanmış yedek sonrası şema 44'e çıkar. İki yeni tablo boş başlar; geçmiş önizlemelerden kayıt uydurulmaz. Başarısız tablo oluşturma geri alınır ve geçiş öncesi yedek korunur.
- Snapshot farkı, değişmeyen tekrarın sıkıştırılması, hata denetimi, bozulmada güvenli durma, yedek/geri yükleme, kaynak seçimi, çevrimdışı durum ve 43→44 migration/rollback davranışları doğrulandı. Tam kontrolde 1.206 otomatik test 213,599 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı.

## 0.104.0 — 30 Ekim 2026

- `ransomware source-evaluation`, ikinci açık ransomware kaynağını bakım, anahtarsız ücretsiz erişim, yapılandırılmış dar çağrı, açık yeniden kullanım koşulu, bağımsız toplama ve güvenli asgari içerik ölçütleriyle çalışma anında internete çıkmadan değerlendirir. RansomLook 6/6 zorunlu kapıyla seçildi; 3 Mart 2026'da arşivlenen RansomWatch güncel akış için elendi, Darkfield ise anahtar/şema ve üst kaynak çakışması netleşene kadar ertelendi.
- `ransomware recent --source ransomlook`, RansomLook'un açık son-yedi-gün API'sini güvenli ve yazmasız önizler. Arama grup/gönderi başlığında cihaz içinde yapılır; yalnız kaynakta bulunan grup, başlık ve keşif zamanı gösterilir. Ülke, sektör, domain, ilan durumu, ihlal hükmü veya eksik alan uydurulmaz.
- Adaptör yalnız sabit HTTPS uç noktasına yönlendirmesiz/sıkıştırmasız tek istek gönderir; 30 saniye, 2 MiB ve 10.000 kayıt sınırı uygular. Tam alan kümesi, yinelenen JSON anahtarı/kayıt, görünür metin ve UTC zaman penceresi bütün sonuçtan önce doğrulanır. Kaynak hatası veya şema kayması kısmi sonuç üretmez.
- RansomLook modeli ve portu ThreatCluster'ın daha zengin claim modeliyle bilinçli olarak ayrıdır. Önizleme veritabanı oluşturmaz, snapshot/izleme geçmişine yazmaz, kaynaklar arası kimlik birleştirmez, Tor veya leak-site adresine bağlanmaz ve ham içerik taşımaz.
- RansomLook API/veri CC BY 4.0 atfı üçüncü taraf bildirimlerine eklendi; sağlayıcı yazılım kodu kopyalanmadı veya gömülmedi. Geçici canlı kabulde 266 güncel API kaydı doğrulandı, üç güvenli kayıt gösterildi ve veri dizini oluşturulmadı.
- Kabul kapısı, katı ayrıştırma, taşıma sınırları, yerel arama, terminal/JSON, yazmasızlık, kaynak kataloğu ve bütün önceki davranışlar sınandı. Tam kontrolde 1.199 otomatik test 205,146 saniyede geçti; otomatik testlerde internet ve kullanıcı veritabanı kullanılmadı. Şema 43 değişmedi ve 0.104.0 yeni migration gerektirmez.

## 0.103.0 — 30 Ekim 2026

- `ransomware watch-identity-review IZLEME_KIMLIGI ADAY_KIMLIGI`, yalnız güncel denetlenmiş geçmişte yeniden bulunan kimlik değişimi adayı için gerekçeli `possible_same`, `different` veya `uncertain` insan kararı kaydeder.
- Aynı karar+gerekçe yeni olay üretmez. Karar veya gerekçe değişikliği önceki olayı silmeden, önceki olay kimliğine bağlı yeni bir olay ekler. `watch-identity-review-show` tam karar sayısını ve sınırlı olay geçmişini ağsız gösterir; aday listesi son kararı taşır.
- Her olay adayın kanonik eski/yeni claim anlık görüntüsünü, kaynak geçişini, izleme ilgisini, ortak/değişen alanlarını ve SHA-256 özetini korur. Bozuk kanıt, zincir, zaman, kaynak veya izleme bağlantısında okuma/yazma güvenli biçimde durur.
- `possible_same` dahil hiçbir karar claim kimliğini birleştirmez, zaman çizelgesini yeniden yazmaz, alarm üretmez veya iddiayı doğrulanmış ihlal saymaz.
- Şema 42, doğrulanmış yedek sonrası tek boş eklemeli karar tablosuyla şema 43'e taşınır. Eski adaylardan karar uydurulmaz; başarısız DDL geri alınır ve yedek korunur.
- İlk karar, aynı kararın idempotent tekrarı, değişen karar zinciri, ayrı kalan zaman çizelgesi kimlikleri, terminal/JSON okuması, yazma kilidi, bozuk zincir/özet, yedek–geri yükleme ve şema 42→43 migration/rollback sınandı. Tam kontrolde 1.193 otomatik test 187,893 saniyede geçti; kullanıcı veritabanı ve internet kullanılmadı.

## 0.102.0 — 30 Ekim 2026

- `ransomware watch-identity-candidates IZLEME_KIMLIGI`, denetlenmiş yerel snapshot geçmişinde eski kimlik kaybolurken aynı veya hemen sonraki başarılı snapshot'ta beliren farklı kimlikleri ağsız insan inceleme adayı olarak gösterir.
- Aday için grup, kuruluş adı, kaynak keşif zamanı ve normalleştirilmiş web alanından en az ikisinin aynı olması gerekir. Eski/yeni kaydın izlemeyle ayrı eşleşme durumu, ortak kanıtlar, değişen kimlik alanları ve kaynak geçişi terminal/JSON sonucunda açıklanır.
- Yalnız tek ortak alan, eşzamanlı yaşayan kayıtlar, uzak geçişler ve aynı kesin kimliğin normal geri dönüşü elenir. Birden fazla eski kayıt uyduğunda yalnız en yakın başarılı snapshot'ta kaybolanlar değerlendirilir; başarısız kaynak turu boş snapshot sayılmaz.
- Komut internete bağlanmaz, alarm veya insan kararı üretmez, kimlikleri birleştirmez ve veritabanına yazmaz. Görünüm sınırı toplamı değiştirmez; geri çekilmiş izleme araştırılabilir. Şema 42 değişmedi ve migration gerekmez.
- Keşif zamanı değişimi, kuruluş adı+zaman değişimi, eski/yeni izleme ilgisi, zayıf benzerlik, eşzamanlı kayıt, kesin yeniden görünme, uzak geçiş, aradaki kaynak hatası, görünüm sınırı, geri çekilmiş izleme ve ağsız terminal/JSON sınandı. Tam kontrolde 1.183 otomatik test 188,280 saniyede geçti; kullanıcı veritabanı ve internet kullanılmadı.

## 0.101.0 — 30 Ekim 2026

- `ransomware watch-timeline IZLEME_KIMLIGI`, seçilen güncel kuruluş/domain izleme tanımını bütün denetlenmiş yerel kaynak snapshot geçmişine ağsız uygular.
- İlk eşleşme, kaynak alanı güncellemesi, eşleşmenin başlaması/bitmesi, kaynak penceresinden çıkış ve aynı iddia kimliğinin yeniden görünmesi ayrı olaylardır. Değişmeden sonraki snapshot'ta kalan aynı kimlik yeni olay oluşturmaz; tekrar gözlem sayacında görünür.
- Kimlik kaynak grup adı + kuruluş adı + kaynak keşif zamanından oluşur. Kaynak bu alanları değiştirirse kanıtsız otomatik birleştirme yapılmaz; zaman çizelgesi yalnız yerelde saklanan snapshot dönemini kapsar.
- Komut toplam ve gösterilen olay sayılarını ayırır; başarılı/başarısız kaynak çalışma kapsamını, ayrı/aktif iddia kimliklerini, tekrarları ve yeniden görünmeleri terminal/JSON çıktısında gösterir. Geri çekilmiş izleme de araştırılabilir; okuma ağ ve yazma yapmaz.
- Çıkarma satırının güvenli claim durumu önceki aktif durumla artık ayrıca karşılaştırılır; semantik olarak değiştirilmiş geçmiş güvenli biçimde reddedilir. Şema 42 değişmedi ve migration gerekmez.
- Zaman çizelgesi yaşam döngüsü, kesin tekrar, alan güncellemesi, domain eşleşmesinin başlaması/bitmesi, başarısız kaynak çalışması, çıkarılma, yeniden görünme, olay görünüm sınırı, geri çekilmiş izleme, ağsız terminal/JSON ve bozuk çıkarma kanıtı sınandı. Tam kontrolde 1.177 otomatik test 184,545 saniyede geçti; kullanıcı veritabanı ve internet kullanılmadı.

## 0.100.0 — 30 Ekim 2026

- `ransomware watch-monitor`, başlamadan kalıcı oturum kimliği oluşturur ve tamamlanan her turu kaynak çalışma kimliğiyle birlikte saklar. Tur, yalnız kendi ürettiği kuruluş/domain izleme çalışma kimliklerine bağlıdır; aynı snapshot üzerinde sonradan yapılan elle çalışma eski oturum özetini değiştirmez.
- `ransomware watch-monitor-list` son oturumları, `watch-monitor-show OTURUM_KIMLIGI` seçilen oturumun ayarlarını, bitiş nedenini, tur kanıtlarını, kaynak hatalarını ve bildirim/fark sayaçlarını ağsız gösterir. JSON görünümleri aynı kalıcı modelleri taşır.
- Normal başarı, bir veya daha fazla kaynak hatasıyla kısmi bitiş, `Ctrl+C`, beklenmeyen uygulama/depolama hatası ve ani kapanma sonrası açık kalan durum ayrıdır. Açık oturum kendiliğinden tamamlandı sayılmaz; bu sürüm daemon, otomatik devam veya otomatik sahipsiz-oturum kapatma eklemez.
- Şema 41, açık `migrate` öncesi doğrulanmış yedekle şema 42'ye taşınır; boş oturum, tur ve tur–izleme bağlantı tabloları eklenir. Eski kaynak/izleme geçmişinden monitor oturumu uydurulmaz.
- Başarı, kısmi kaynak sonucu, kesme, beklenmeyen hata, ani kapanma, bozuk durum, ağsız liste/ayrıntı, yedekli migration ve sonradan aynı snapshot'ta yapılan bağımsız çalışma sınırları doğrulandı. Tam kontrolde 1.172 test 191,700 saniyede geçti. Ayrı geçici canlı kabul 1.091 kayıtlı snapshot üzerinde bir oturum, bir tur ve bir bağlı sessiz izleme çalışmasını kalıcılaştırdı; ağsız liste/ayrıntı ve şema 42 sayaçları doğrulandı. Kullanıcı veritabanı değiştirilmedi.

## 0.99.0 — 30 Ekim 2026

- `ransomware watch-monitor`, açık kaynak yenileme ve bütün etkin kuruluş/domain izlemelerini terminal açıkken 1–1000 tur, 300–86400 saniye aralık ve 1–604800 saniye yeni-tur bütçesiyle tekrarlar.
- Her tur ayrı kaynak çalışmasıdır. Başarısız kaynak turu boş sonuç sayılmaz, eski snapshot üzerinde izleme çalıştırmaz ve bütçe varsa sonraki tur denenir.
- Süre geriye gitmeyen süreç saatiyle ölçülür. Süre sınırı veya beklemede `Ctrl+C` tamamlanan kaynak/izleme kanıtlarını silmez. Komut daemon, cron girdisi veya kalıcı zamanlayıcı kurmaz.
- Terminal/JSON başarılı-başarısız kaynak turlarını, tamamlanan izleme sayısını, fark/bildirim toplamlarını, bitiş nedenini, süreyi ve kaynak çalışma kimliklerini gösterir. Herhangi bir kaynak turu başarısızsa çıkış 3, `Ctrl+C` için 130 döner.
- Şema 41 değişmedi. Testler iki turda değişiklik bildirimi, başarısız kaynaktan sonra devam, süre sınırı, kesme, bozuk saat, ağ öncesi sınır reddi, sessiz başlangıç/tekrarlı toplam ayrımı ve CLI sonuç sözleşmesini kapsar. Tam kontrolde 1.163 test 169,552 saniyede geçti. Ayrı geçici canlı kabul güncel 1.091 kayıtlı snapshot üzerinde tek başarılı monitor turunu doğruladı.

## 0.98.0 — 30 Ekim 2026

- `ransomware watch-refresh-all`, ThreatCluster açık snapshot'ını bir kez yeniler ve yalnız tam başarı sonrasında bütün etkin kuruluş/domain izlemelerini adlarına göre kararlı sırada çalıştırır.
- Geçersiz sınır, bozuk geçmiş veya etkin izlemelerin tamamının `--watch-limit` içine sığmaması ağ isteğinden önce durur. Kaynak hatası ayrı kaydedilir; eski başarılı snapshot üzerinde izleme çalıştırılmaz.
- Her izleme az önce tamamlanan kaynak çalışma kimliğini başlamadan doğrular ve ayrı atomik transaction kullanır. Sonraki hata tamamlanan kaynak/izleme kanıtını geri almaz; toplu akış durur.
- Terminal ve JSON tek sonuçta kaynak çalışmasını, planlanan/tamamlanan izleme sayısını, fark/bildirim toplamlarını ve çalışma kimliklerini gösterir. Komut zamanlayıcı veya daemon kurmaz.
- Şema 41 değişmedi. Yeni toplu akış testleri tek alım, sabit sıra, geri çekilmiş tanım, anlamlı değişim bildirimi, kaynak hatası, sınır aşımı, kaynak kimliği ve kısmi ilerleme korumasını kapsar. Tam kontrolde 1.155 test 170,557 saniyede geçti. Ayrı geçici canlı kabul güncel 1.091 kayıtlı snapshot'ı ve aynı kaynak kimliğine bağlı sessiz izleme başlangıcını doğruladı.

## 0.97.0 — 30 Ekim 2026

- `ransomware watch-add/list/show/revoke`, kuruluş veya domain için sürümlü ve geri alınabilir yerel izleme tanımı oluşturur. Kuruluş yalnız `victim` alanında exact/isteğe bağlı contains; domain yalnız normalleştirilmiş `website` hostunda kök/alt alan adı ilişkisiyle eşleşir.
- `ransomware watch-run`, son başarılı yerel snapshot üzerinde ağsız çalışır; `watch-run-show` değişmez sonucu yeniden gösterir. İlk çalışma ve tanım değişimi sessiz baseline'dır.
- Yalnız baseline sonrasındaki yeni/değişen eşleşme ortak `inbox` sırasına girer. Salt 30 günlük kaynak penceresinden çıkış bildirim üretmez ve kapatma/çözüm sayılmaz.
- Şema 40, açık `migrate` öncesi doğrulanan yedekle şema 41'e taşınır; beş boş izleme tablosu eklenir, eski snapshot'tan izleme veya alarm uydurulmaz.
- Tam kontrolde 1.145 otomatik test 179,824 saniyede geçti; otomatik testlerde gerçek ağ ve kullanıcı veritabanı kullanılmadı.

## 0.96.0 — 30 Ekim 2026

- `ransomware refresh [--limit 1..500]`, katı doğrulanmış ThreatCluster tam snapshot'ını açık kullanıcı seçimiyle yerel geçmişe kaydeder ve son başarılı snapshot'a göre `added`, `updated`, `unchanged`, `removed` ayrımını üretir. `removed` yalnız kayan kaynak penceresinden çıkışı anlatır.
- İlk başarılı snapshot başlangıç çizgisidir ve alarm üretmez. Kaynak hatası ayrı başarısız çalışma olarak saklanır; önceki başarılı snapshot ve öğeleri korunur. `ransomware status [--limit 1..100]` bu geçmişi ağsız/salt-okunur gösterir.
- Kalıcı öğeler grup, kuruluş, güvenli web bilgisi, ülke/sektör, kaynak durumu ve zaman kanıtını taşır; ham leak-site URL'si/metni/ekran görüntüsü tutulmaz. Bozuk kimlik, zaman, özet, sayaç veya bağlantı bütün görünümü güvenli biçimde durdurur.
- Şema 39, açık `migrate` öncesinde doğrulanan yedekle şema 40'a taşınır ve iki boş ransomware snapshot tablosu eklenir; eski veriden iddia veya çalışma uydurulmaz.
- Geçici canlı kabulde ilk snapshot 1.093 kayıtla başlangıç çizgisi oluşturdu; ikinci snapshot 1.093 kaydı değişmemiş saydı ve sıfır ek fark satırı yazdı. Tam kontrolde 1.137 otomatik test 171,591 saniyede geçti.

## 0.95.0 — 30 Ekim 2026

- `ransomware recent [ARAMA] [--status all|listed|delisted] [--limit 1..100]`, ThreatCluster'ın anahtarsız son-30-gün kamu JSON akışını bir kez alır; kuruluş, kaynaktaki web bilgisi, grup, ülke ve sektörü cihaz içinde filtreler.
- Her sonuç açıkça grubun yayımladığı doğrulanmamış iddia olarak gösterilir. `delisted` ihlal, ödeme veya çözüm sonucu değildir; sıfır eşleşme güvenlik veya tarihsel yokluk hükmü değildir.
- Kaynak adaptörü sabit HTTPS adresi, yönlendirme/sıkıştırma reddi, 30 saniye, 8 MiB, 10.000 kayıt, 48 saat güncellik ve katı JSON/şema/lisans/sayaç/zaman/durum/tekrar doğrulaması uygular. Bilinmeyen biçim kısmi sonuç üretmez.
- XTI Tor veya leak-site adresine bağlanmaz. Kaynak `post_url` değeri modele, normal terminale ve JSON çıktısına taşınmaz; ham gönderi metni, ekran görüntüsü ve kişisel veri alınmaz.
- Kaynak/akış/alım zamanı, gün penceresi, kayıt sayısı, içerik SHA-256 ve CC BY 4.0 ThreatCluster atfı korunur. Komut veritabanı oluşturmaz/yazmaz; geçmiş, otomatik izleme ve bildirim bu dilimde yoktur. Şema 39 değişmediği için migration gerekmez.
- Canlı kabul 1.093 açık kaynak kaydını kullanıcı veritabanına yazmadan doğruladı; `securehup.com` için o pencere/kaynakta sıfır eşleşme bulundu. Tam kontrolde 1.130 otomatik test 172,685 saniyede geçti.

## 0.94.0 — 30 Ekim 2026

- `surface exposures DOMAIN`, pasif alt alan adı keşfini web, e-posta, sınırlı servis ve CNAME kanıtlarıyla aynı salt-okunur görünümde birleştirir. Güncel, eski, kısmi, başarısız, hiç çalışmamış ve zamanı tutarsız durumlar ayrı kalır.
- Tamamlanmış sıfır adaylı crt.sh yanıtı yalnız o kaynak yanıtının boş olduğunu söyler. Kısmi sıfır yanıt veya kaynak hatası boş/güvenli sonuç sayılmaz.
- İlgi isteyen her kanıt ailesi tam sonraki terminal komutunu taşır. Etkin kapsam yoksa önce açık `surface approve` adımı gösterilir; komutlar kendiliğinden çalıştırılmaz.
- Pasif keşif çalışması mevcut kanıtlarla tek SQLite okuma transaction'ında alınır. Bozuk son çalışma bütün görünümü güvenli biçimde durdurur; yeni tablo, migration, ağ çağrısı veya veri yazımı yoktur. Şema 39 korunur.
- 1.125 otomatik test 148,591 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

## 0.93.0 — 30 Ekim 2026

- `cti attack-sync`, resmî MITRE ATT&CK Enterprise v20.0 STIX 2.1 paketindeki etkin 178 grup, 57 kampanya, 747 malware ve seçili 809 ilişkiyi ücretsiz yerel CTI bilgi grafiğine ekler. ATT&CK `intrusion-set` nesnesi araştırma etiketi olarak `threat-actor` türüne eşlenir; otomatik atıf hükmü verilmez.
- Kaynak adresi ve sürüm sabittir. Yönlendirme/sıkıştırma reddi, 60 saniye, 64 MiB, 30.000 STIX nesnesi, kanonik kimlik/zaman, koleksiyon dizini, resmî ATT&CK başvurusu ve varlık/ilişki yönü bütün paket yazılmadan önce doğrulanır.
- Senkron tek SQLite transaction'ındadır. İlk ekleme, değişmeme, gözlem, güncelleme, geri çekme ve yeniden etkinleştirme kaynak iddiası geçmişiyle korunur; elle veya başka kaynaktan eklenen iddialar etkilenmez. Bozuk yönetilen geçmiş ağ isteğinden önce durur.
- Kaynak hatası boş snapshot sayılmaz ve önceki kayıtları değiştirmez. İlk dilimde otomatik zamanlayıcı, ayrı senkron çalışma tablosu, ATT&CK teknik/taktik nesneleri, TAXII veya otomatik tehdit hükmü yoktur. Şema 39 değişmediği için migration gerekmez.
- Gerçek resmî v20.0 dosyası 55.271.014 bayt ve SHA-256 `81113ba98afa2928f3dcff62022539f7ce30c315c32e14422f11ff95ce534352` olarak geçici alanda doğrulandı. 26.690 STIX nesnesinden 982 varlık ve 809 ilişki ayrıştırıldı; ilk kayıt yaklaşık 0,243 saniye/3.997.696 bayt, değişmeyen tekrar 0,333 saniye sürdü. Kullanıcı veritabanı değiştirilmedi.
- 1.123 otomatik test 165,581 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

## 0.92.0 — 30 Ekim 2026

- `ioc sync/status --source certpl` ve `analyze DOMAIN --refresh-ioc certpl`, CERT Polska Warning List'in son-ay etkin domain listesini ikinci bağımsız ve ücretsiz IOC kaynağı olarak ekler. Kaynak Polonya/son-ay kapsamıyla açıkça etiketlenir; küresel phishing kapsamı veya otomatik zararlılık hükmü sayılmaz.
- Yeni adaptör sabit HTTPS adresi, yönlendirme reddi, sıkıştırmasız metin, 30 saniye, 8 MiB, 50.000 kayıt, katı başlık/zaman/domain ve 48 saat güncellik sınırlarını uygular. Hata önceki iddiaları korur; yalnız başarılı tam snapshot ekleme, yeniden etkinleştirme ve geri çekme üretir.
- IOC besleme deposu kaynak politikalarıyla genelleştirildi. Feodo ve CERT aynı kanonik IOC ana kaydını paylaşabilir fakat kaynak iddiaları, çalışmalar ve geri çekmeler birbirini etkilemez. CERT tekrarlarında değişmeyen binlerce öğe satırı çoğaltılmaz; çalışma özeti ve içerik SHA-256 kanıtı korunur.
- Birleşik analiz artık kök domainin yanında kayıtlı bütün marka/domain adaylarını ve son kanıt IP'lerini tam değerle kontrol eder. `--finding-limit` yalnız görünümü sınırlar; IOC kapsamını sessizce daraltmaz.
- Yerel CTI arama ve STIX IOC dışa aktarma sınırı CERT dilimini kapsamak için 50.000 kayda yükseltildi; STIX'in 32 MiB dosya sınırı değişmedi. Şema 39 değişmedi ve migration gerekmez.
- Canlı kabul geçici alanda 18.764 domaini ayrıştırdı; ilk kayıt yaklaşık 2,23 saniye ve 33,7 MB SQLite, tekrar yaklaşık 1,83 saniye, STIX çıktısı 19,6 MB olarak ölçüldü. Kullanıcı veritabanı değiştirilmedi.
- 1.116 otomatik test 186,443 saniyede geçti; otomatik testlerde gerçek ağ kullanılmadı.

## 0.91.0 — 30 Ekim 2026

- `analyze DOMAIN --refresh-ioc feodo`, kullanıcının açık seçimiyle ücretsiz Feodo Tracker listesini yeniler ve birleşik analizi güncel yerel katalog üzerinden tekrar üretir. Varsayılan `analyze` ağsız ve salt-okunur kalır.
- Domain ve bütün yerel analiz sınırları dış istekten önce doğrulanır. Yenileme, ortak yerel çalışma kilidi ve mevcut sınırlı tam-snapshot IOC yaşam döngüsünü yeniden kullanır.
- Kaynak başarısızlığı ayrı çalışma olarak kaydedilir, önceki etkin IOC iddiaları korunur ve sonuç “eşleşme yok” gibi sunulmaz. Terminal ve JSON çıktısı yenileme kanıtı ile analiz kanıtını ayrı taşır; başarısız yenileme çıkış kodu 3'tür.
- Ürün, sürüm, paket, CVE sonucu veya otomatik engelleme eklenmedi; şema 39 değişmedi.
- 1.110 otomatik test 172,606 saniyede geçti; gerçek ağ kullanılmadı.

## 0.90.0 — 30 Ekim 2026

- `analyze DOMAIN`, kayıtlı marka/domain adaylarını, pasif alt alan adı keşfini, DNS/TLS/HTTPS, e-posta, izinli servis ve dış yüzey kanıtını tek ağsız ve salt-okunur terminal görünümünde birleştirir.
- Kök domain ile son kayıtlı web/servis IP'leri, yerel katalogdaki güncel IOC kaynak iddialarıyla yalnız tam değer üzerinden karşılaştırılır. Boş katalog, eşleşme bulunmaması ve bulunan kaynak iddiası birbirinden ayrılır.
- Eksik veya eski kanıtlar için açık sonraki komutlar gösterilir; görünüm sınırları ve güncellik eşiği doğrulanır. Birleşik analiz hiçbir tarama başlatmaz ve veriyi değiştirmez.
- Ürün, sürüm, paket ve CVE çıkarımı aktif ürün kapsamından kaldırıldı. Eski komutlar mevcut kullanıcı verisi ve şema uyumluluğu için korunur; birleşik analize ve ileri teslim sırasına katılmaz.
- Yol haritası ücretsiz, kişisel ve savunmacı OSINT sırasına göre güncellendi: IOC beslemeleri ve CTI, yüzey boşlukları, yasal açık kaynak sızıntı/ransomware takibi, marka koruması, tedarikçi riski ve insan onaylı entegrasyonlar.
- 1.107 otomatik test 165,073 saniyede geçti; gerçek ağ kullanılmadı.

## 0.89.0 — 30 Ekim 2026

- `webhook secret-generate/target-add/list/show/secret-set/revoke`, özel anahtar dosyasını üzerine yazmadan 0600 izinle üretir; hedefin tam URL'sini ve sırrını hiçbir normal/JSON çıktısında göstermez. Hedef yaşam döngüsü eklemeli olaylarla korunur.
- `webhook queue`, kullanıcının seçtiği birleşik yerel bildirimi en fazla 256 KiB'lik kanonik ve SHA-256 bağlı değişmez JSON gövdesine dönüştürür. Aynı hedef+bildirim çifti tek teslim kimliğini korur.
- `webhook deliver/delivery-list/delivery-show`, ham gövdeyi zaman damgasıyla HMAC-SHA256 imzalar; 2xx, geçici ve kalıcı sonuçları ayrı deneme geçmişine kaydeder. Başarılı teslim yeniden gönderilmez; her yeniden deneme açıktır ve otomatik worker yoktur.
- HTTPS adaptörü yalnız port 443 ve tamamı genel IP'lere çözülen hedeflere bağlanır; IP'yi DNS kontrolünden sonra sabitler, TLS host doğrulamasını korur, proxy/yönlendirme izlemez ve uzak yanıt gövdesini saklamaz.
- Şema 39 hedef, hedef olayı, değişmez teslim ve deneme tablolarını ekler. Şema 1–38 açık `migrate`, doğrulanmış geçiş öncesi yedek ve hata halinde geri alma ile yükselir; eski bildirimlerden teslim uydurulmaz.
- 1.103 otomatik test 164,020 saniyede geçti; gerçek ağ kullanılmadı.

## 0.88.0 — 30 Ekim 2026

- `cti stix-export DOSYA [--indicator-type ...]`, güncel domain/IPv4/IPv6/URL/MD5/SHA-1/SHA-256 IOC kaynak iddialarını STIX 2.1 Bundle içindeki kanonik `Indicator` pattern'lerine ağsız ve salt-okunur dönüştürür.
- Yerel IOC kimliği, oluşturma/güncelleme/geçerlilik zamanları, en yüksek güncel kaynak güveni ve bağımsız kaynak başvuru/açıklamaları korunur. `unknown` gösterge türü ve açık açıklama otomatik zararlılık veya varlık etkisi hükmünü engeller.
- En fazla 10.000 IOC ve 10.000 ilgili iddia tek SQLite anlık görüntüsünde doğrulanır; bozuk veya taşan kapsam kısmi paket üretmez. İsteğe bağlı tür filtresi sessiz kesme yapmaz.
- En fazla 32 MiB JSON özel geçici dosya, `fsync` ve üzerine yazmayan atomik yayınla oluşturulur; mevcut dosya/symlink korunur. CTI nesne/ilişkileri, içe aktarma, TLP ve TAXII kapsam dışıdır; şema 38 değişmez.
- 1.092 otomatik test 171,769 saniyede geçti; gerçek ağ kullanılmadı.

## 0.87.0 — 30 Ekim 2026

- `cti watch-tag-add/remove`, kayıtlı aramaları 2–40 karakterlik etiketlerle sınıflandırır; ekleme, görünüm güncelleme, kaldırma ve yeniden etkinleştirme geçmişi silinmez.
- `cti watch-note-add`, gözlem/hipotez/sonuç/takip notunu genel aramaya veya aynı aramaya ait değişmez çalışma kanıtına bağlar. Notlar eklemelidir; tespit veya tehdit hükmü değildir.
- `cti watch-journal`, etkin etiketleri, sınırlı etiket olaylarını ve analist notlarını ağsız/salt-okunur gösterir. Etiket ve notlar sorgu tanımına katılmaz, fark tabanını sıfırlamaz.
- Şema 38 üç avcılık defteri tablosu ekler. Şema 1–37 açık `migrate`, doğrulanmış yedek ve hata halinde geri alma ile yükselir; eski aramalardan etiket veya not uydurulmaz.
- 1.086 otomatik test 150,106 saniyede geçti; gerçek ağ kullanılmadı.

## 0.86.0 — 30 Ekim 2026

- `cti watch-run-all`, etkin kayıtlı CTI aramalarının tamamını adlarına göre sabit sırada tek sefer çalıştırır; her arama mevcut tam sonuç/fark/bildirim yolunu kullanır.
- Arama sayısı açık `--search-limit` sınırına sığmıyorsa hiçbir çalışma başlatılmaz. Geri çekilmiş aramalar atlanır; boş etkin kapsam geçerli sıfır çalışma raporudur.
- Her arama ayrı atomik kayıttır. Sonraki arama başarısız olursa önce tamamlanan kanıt korunur, başarısız ve sonraki aramalar tamamlanmış gösterilmez.
- Toplu komut bütün ömründe ortak yerel çalışma kilidini tutar; ağ, daemon, dış bildirim kanalı veya yeni şema eklemez. Şema 37 değişmez.
- 1.077 otomatik test 151,030 saniyede geçti; gerçek ağ kullanılmadı.

## 0.85.0 — 30 Ekim 2026

- `cti watch-monitor`, tek kayıtlı CTI aramasını terminal açıkken 1–1000 tur, 300–86400 saniye aralık ve 1–604800 saniye yeni-tur süresi sınırıyla tekrarlar.
- Her tamamlanan tur mevcut tam sonuç/fark/bildirim yolunu kullanır. Süre dolması yeni turu durdurur; `Ctrl+C` tamamlanmış çalışma kanıtlarını korur.
- İzleme ortak yerel çalışma kilidini kullanır; görünmez daemon, işletim sistemi görevi, ağ çağrısı veya yeni şema eklemez. Şema 37 değişmez.
- 1.071 otomatik test 147,957 saniyede geçti; gerçek ağ kullanılmadı.

## 0.84.0 — 30 Ekim 2026

- Kayıtlı CTI aramasının ilk çalışması sessiz başlangıçtır; sonraki çalışmada yeni, değişen veya artık eşleşmeyen sonuç varsa birleşik yerel kutuya tek bildirim eklenir.
- Bildirim çalışma kimliğine bağlıdır; arama adı/sorgusu ile yeni, değişen, aynı ve kaybolan sayıları `inbox list/show` üzerinden kanıtıyla görünür. Okundu bilgisi CTI kaydını değiştirmez.
- Çalışma, tam sonuç öğeleri ve bildirim aynı transaction'da yazılır. Bildirim sıra/yazma hatası bütün çalışmayı geri alır; değişmeyen tekrarlar ve yeni sorgu tanımının başlangıcı bildirim gürültüsü üretmez.
- Şema 37 CTI arama değişiklik bildirim tablosunu ekler. Şema 1–36 açık `migrate`, doğrulanmış yedek ve hata halinde geri alma ile yükselir; eski çalışmalardan geriye dönük bildirim uydurulmaz.
- 1.066 otomatik test geçti; gerçek ağ kullanılmadı.

## 0.83.0 — 30 Ekim 2026

- `cti watch-add/list/show/run/run-show/revoke`, birleşik yerel CTI sorgularını adlandırıp tanım yaşam döngüsü ve tam çalışma geçmişiyle saklar.
- Her açık çalışma aynı tanımın son çalışmasına göre yeni, değişen, aynı kalan ve artık eşleşmeyen varlık/IOC kayıtlarını ayırır; tanım değişikliği karşılaştırma tabanını sıfırlar.
- Arama anlık görüntüsü ile çalışma başlığı/öğeleri tek yazma rezervasyonu altında kaydedilir. Eksik sonuç, plan kayması, bozuk gizli geçmiş veya öğe yazma hatası bütün çalışmayı geri alır.
- Şema 36 dört kayıtlı-arama tablosunu ekler. Şema 1–35 yalnız açık `migrate`, doğrulanmış yedek ve hata halinde geri alma ile yükselir; eski veriden sorgu ya da çalışma uydurulmaz.
- 1.058 otomatik test geçti; gerçek ağ kullanılmadı.

## 0.82.0 — 30 Ekim 2026

- `cti search QUERY`, aktör/kampanya/malware/rapor ana adları ve kaynaklı alternatif adları ile yerel domain/IP/URL/hash IOC değerlerini tek salt-okunur anlık görüntüde arar.
- Tam, başlangıç ve içerme eşleşmeleri kararlı sırada ayrılır. `--kind`, `--entity-type`, `--indicator-type`, `--limit` ve `--all` kapsamı açıkça sınırlar; varsayılan yalnız etkin CTI ve sorgu anında geçerli IOC iddialarını kullanır.
- En fazla 10.000 CTI varlığı ve 10.000 IOC'nin ana kayıt, kaynak iddiası ve olay geçmişi görünüm sınırından bağımsız doğrulanır. Eşleşmeyen gizli bir kayıtta bozuk geçmiş varsa kısmi arama sonucu verilmez.
- Arama internete çıkmaz, veritabanını yazmaz, otomatik atıf/birleştirme veya tehdit hükmü üretmez. Yeni tablo yoktur; şema 35 korunur.
- Ad/alias/IOC sıralaması, etkin–geçmiş ayrımı, filtre/limit doğrulaması, bozuk gizli geçmiş, eksik veritabanı ve terminal/JSON salt-okuma yolları doğrulandı. Tam kontrolde 1.047 otomatik test 153,118 saniyede geçti; gerçek ağ kullanılmadı.

## 0.81.0 — 30 Ekim 2026

- `cti entity-add/list/show/lookup/revoke`, aktör, kampanya, malware ve raporları kaynak adı/başvurusu, alternatif ad, güven, açıklama ve gözlem aralığıyla yerel bilgi tabanında yönetir.
- `cti relation-add/list/show/revoke`, bir CTI varlığını başka bir varlığa veya yerel IOC'ye sekiz sınırlı ilişki türüyle bağlar. Öz ilişki, hedefsiz/çift hedefli ilişki ve bulunmayan hedef atomik olarak reddedilir.
- Aynı varlık veya ilişki için her `kaynak + başvuru` bağımsız kalır; ekleme, gözlem, güncelleme, geri çekme ve yeniden etkinleştirme olayları silinmeden tutulur. Bir kaynağın geri çekilmesi diğer kaynağı etkilemez; çelişen aktör atıfları ayrı korunur.
- Liste/ayrıntı/arama komutları ağsız ve salt okunurdur. Alternatif ad otomatik birleştirme; ilişki otomatik aktör atfı, nedensellik veya tehdit doğrulaması değildir.
- Şema 35 altı CTI varlık/ilişki ve olay tablosunu ekler. Şema 1–34 açık `migrate`, doğrulanmış yedek ve hata halinde geri alma ile yükselir; eski IOC veya raporlardan bilgi grafiği uydurulmaz. Doctor, yedek/restore ve gizli bozuk geçmiş kapıları güncellendi.
- CTI varlık/ilişki yaşam döngüsü, bağımsız ve çelişen kaynaklar, IOC bağı, terminal/JSON, bozuk geçmişte güvenli durma, yedek/restore ve şema 34→35 geçişi doğrulandı. Tam kontrolde 1.043 otomatik test 141,883 saniyede geçti; gerçek ağ kullanılmadı.

## 0.80.0 — 30 Ekim 2026

- `ioc sync --source feodo`, abuse.ch Feodo Tracker'ın anahtarsız, saldırgan olmayan 30 günlük botnet C2 JSON listesini sabit HTTPS adresinden sınırlı ve katı biçimde alır. `ioc status --source feodo` kaynak sağlığını ve çalışma geçmişini ağsız gösterir.
- Aynı IP'nin farklı port/malware satırları tek kanonik IPv4/IPv6 kaynağına birleşir. Her IOC sabit kaynak başvurusu, ilk/son gözlem, içerik ve durum SHA-256 özeti taşır; 50/100 puan kaynak verisi değil açık yerel nötr politikadır.
- Her tam snapshot `added/observed/updated/unchanged/reactivated/revoked` sayaçları ve IOC başına çalışma bağıyla atomik kaydedilir. Kaynak/JSON/alan hatası başarısız çalışma olur ve etkin kayıtları geri çekmez; yalnız başarılı tam listeden çıkış geri çekme üretir.
- Kaynak 30 saniye, 8 MiB ve 50.000 satırla sınırlıdır; yönlendirme, sıkıştırılmış/beklenmeyen içerik, yinelenen JSON alanı/kayıt ve kanonik olmayan değerler bütün snapshot'ı reddeder. IOC otomatik engelleme veya varlık etkisi kararı değildir.
- Şema 34 iki besleme çalışma/provenance tablosunu ekler. Şema 1–33 açık `migrate`, doğrulanmış yedek ve hata halinde geri alma ile yükselir; eski veriden çalışma geçmişi uydurulmaz. Doctor, kaynak kataloğu, yedek/restore ve bozuk gizli geçmiş kapıları güncellendi.
- 1.035 otomatik test 180,364 saniyede geçti. Ayrıca canlı Feodo yanıtı geçici dosyada 5 satır/5 IOC olarak katı ayrıştırıcıyla doğrulandı; kullanıcı veritabanına yazılmadı.

## 0.79.0 — 30 Ekim 2026

- `ioc add/list/show/lookup/revoke`, domain, IPv4, IPv6, HTTP(S) URL, MD5, SHA-1 ve SHA-256 göstergelerini yerel terminalden yönetir. Tür/değer kanonikleştirmesi, güvenli URL sınırları ve kararlı JSON çıktısı vardır.
- Tek kanonik IOC birden çok bağımsız `kaynak + başvuru` iddiası taşıyabilir. Güven, açıklama, isteğe bağlı geçerlilik, ilk/son görülme ve etkinlik ayrı kalır; kaynaklar birbirini ezmez.
- Aynı gözlem tekrar güvenlidir; yeni gözlem aralığı genişletir, değişen kaynak bilgisi güncellenir, geri çekilen iddia geçmiş silinmeden yeniden etkinleştirilebilir. `added/observed/updated/reactivated/revoked` olayları eklemeli tutulur.
- Liste varsayılan olarak geçerliliği süren en az bir kaynak iddiası olan göstergeleri getirir; `--all` sona ermiş ve geri çekilmiş geçmişi de gösterir. Okuma yolları ağsız ve salt okunurdur; IOC kaydı otomatik zararlılık veya varlık etkisi kararı değildir.
- Şema 33 üç IOC tablosunu ekler. Şema 1–32 açık `migrate`, doğrulanmış geçiş öncesi yedek ve hata halinde geri alma ile yükselir; eski veriden IOC veya kaynak iddiası uydurulmaz. Doctor, yedek ve restore yeni kayıtları kapsar.
- 1.024 otomatik test 118,960 saniyede geçti; kanonik türler, çoklu kaynak, geçerlilik, gözlem tekilleştirme, geri çekme/yeniden etkinleştirme, gizli bozuk geçmiş, salt-okunur terminal/JSON, doctor, yedek/restore, şema 32→33 ve bütün eski geçişler doğrulandı.

## 0.78.0 — 30 Ekim 2026

- `vuln ubuntu-evidence-plan [--domain ...]`, etkin seçilmiş Ubuntu kanıtlarının yerel paket anlık görüntülerini ağsız inceler; yerel aynı, paket değişmiş ve paket etkisiz sayılarını bütün kapsam için verir.
- Plan en fazla 10.000 etkin kanıt ve bunların 100.000 olayını tek salt-okunur SQLite anında doğrular. Bilinmeyen varlık, bozuk ayrılmış başvuru veya eksik olay geçmişi görünüm limitinin arkasında olsa bile kısmi plan üretmez.
- `vuln ubuntu-evidence-scan [--domain ...] [--limit 1..20]`, planın dikkat öncelikli ilk kanıtlarını güncel Canonical kayıtlarıyla salt okunur kontrol eder. Aynı CVE'ye bağlı seçili kanıtlar tek kaynak çağrısını paylaşır; boş kapsam ağa çıkmaz.
- Toplu tarama güncel, değişmiş ve etkisiz/atlanan sonuç sayılarını verir; kanıtı, paketi veya insan kararını yazmaz. Değişen sonucu kalıcılaştırmak yine açık `ubuntu-evidence-add` seçimi gerektirir.
- Yeni tablo veya migration yoktur; şema 32 korunur.
- 1013 otomatik test 115,582 saniyede geçti; ağsız plan, tek-CVE kaynak paylaşımı, sınırlar, gizli bozuk kayıt, terminal/JSON ve önceki davranışlar doğrulandı.

## 0.77.0 — 30 Ekim 2026

- `vuln ubuntu-evidence-check KANIT_KIMLIGI`, seçilmiş Ubuntu destek kanıtını güncel yerel paket anlık görüntüsü ve yeniden alınan Canonical tek-CVE kaydıyla salt okunur karşılaştırır.
- Güncel; Canonical belgesi değişmiş/sonuç aynı; paket yeniden doğrulanmış/sonuç aynı; karşılaştırma sonucu değişmiş; yayın+paket bağı kaybolmuş; kayıt geri çekilmiş; paket veya kanıt etkisiz ve paket kontrol sırasında değişmiş durumları ayrı raporlanır.
- Etkisiz paket veya kanıtta Canonical kaynağı çağrılmaz. Etkin kontrolde CVE ve varlık bağı yeniden doğrulanır; kontrol veritabanına yazmaz, kayıtlı kanıtı yenilemez ve insan maruziyet kararını değiştirmez.
- `ubuntu-osv-v1` kaynak biçimi ayrılmıştır; genel serbest `exposure-evidence-add` komutu bu biçimde sahte paket kanıtı oluşturamaz. Kanonik ayrıştırıcı CVE, paket UUID'si, iki SHA-256 özeti ve seçilebilir kayıtlı durumu tümden doğrular.
- Yeni tablo veya migration yoktur; şema 32 korunur.
- 1009 otomatik test 110,088 saniyede geçti; bütün güncellik durumları, kontrol içi paket değişimi, ayrılmış başvuru kapısı, salt-okunur terminal/JSON ve önceki davranışlar doğrulandı.

## 0.76.0 — 30 Ekim 2026

- `vuln ubuntu-evidence-add INCELEME_KIMLIGI UBUNTU_PAKET_KIMLIGI --summary ...`, güncel Canonical Ubuntu OSV sonucunu yeniden alır ve kullanıcının açık seçimiyle mevcut maruziyet incelemesine `package_inventory` destek kanıtı olarak bağlar.
- Yalnız aynı varlıktaki etkin paket ve maruziyet, aynı CVE'nin tek `affected` yayın+kaynak paket bağıyla eşleştiğinde yazım yapılır. Listelenmeyen veya geri çekilmiş kayıt kanıt sayılmaz; kaynak çağrısından önce kimlik, açıklama ve varlık bağı doğrulanır.
- Kanıt başvurusu CVE, Ubuntu paket kimliği, tam paket anlık görüntüsü SHA-256 özeti, Canonical içerik SHA-256 özeti ve karşılaştırma durumunu birlikte mühürler. Aynı seçim çoğalmaz; değişmiş paket veya kaynak ayrı kanıt olur.
- Ağ isteği sırasında paket kanıtı değişirse SQLite yazma transaction'ı güncel anlık görüntüyü yeniden doğrular ve eski seçimi kısmi kayıt bırakmadan reddeder. İnsan maruziyet durumu, gerekçesi, önceliği ve olay geçmişi değişmez.
- Yeni tablo veya migration yoktur; mevcut genel kanıt yaşam döngüsü, liste/ayrıntı/kaldırma, vaka kuyruğu, yedek ve restore akışları kullanılır. Şema 32 değişmedi.
- 1002 otomatik test 124,756 saniyede geçti; seçim, tekilleştirme, başka varlık ve listelenmeyen/geri çekilmiş kaynak kapıları, ağ sırasında paket değişimi, terminal/JSON, kuyruk, insan kararı ve yedek/restore doğrulandı.

## 0.75.0 — 30 Ekim 2026

- `vuln ubuntu-inventory-scan CVE [--domain ...]`, seçilen kapsamdaki bütün etkin Ubuntu paket kanıtlarını Canonical'ın tek-CVE OSV kaydını yalnız bir kez alarak topluca karşılaştırır.
- Bütün envanter için geri çekilmiş, listelenmiyor, fixed sınırı yok, sınırdan önce/eşit/sonra sayaçları hesaplanır; dikkat gerektiren kayıtlar önce, en fazla 500 paketle gösterilir. Görünüm limiti toplamları değiştirmez.
- Kaynaktan önce bütün etkin kayıtlar ve olay geçmişleri doğrulanır; kayıtlı olmayan varlık, bozuk limit arkası kanıt veya 10.000 paket/100.000 olay sınırı kısmi sonuç üretmeden durur. Boş kapsam Canonical'a istek göndermez.
- Tarama veritabanını, paket kanıtını veya insan maruziyet kararını yazmaz. `not_listed` güvenli sayılmaz; aynı kaynak kaydı her paket için tekrar indirilmez. Şema 32 değişmedi.
- 998 otomatik test 128,545 saniyede geçti; tek kaynak çağrısı, bütün durum sayaçları, öncelikli kesme, boş kapsam, varlık filtresi, gizli bozuk kayıt/geçmiş, terminal/JSON ve önceki davranışlar doğrulandı.
- Canlı kabulde üç etkin paket tek Canonical `CVE-2025-6491` kaydıyla tarandı: bir fixed-öncesi, bir fixed-sonrası ve bir listelenmeyen kayıt doğru sayıldı. Tarama öncesi/sonrası veritabanı SHA-256 özeti aynı kaldı.

## 0.74.0 — 30 Ekim 2026

- `ubuntu-packages add/list/show/revoke`, kayıtlı bir varlığa kullanıcı doğrulamalı Ubuntu binary paket adı/sürümü/mimarisi ile kaynak paket adı/sürümü arasındaki kesin bağı ekler; güncel kayıt ile silinmeyen olay geçmişini ayrı tutar.
- `vuln ubuntu-inventory-match PAKET_KIMLIGI CVE`, etkin envanter kaydını Canonical'ın tek-CVE OSV kaydıyla salt okunur karşılaştırır. OSV kaynak paket düzeyinde olduğu için yalnız doğrulanmış source sürümü kullanılır; farklı görünen binary sürümü hükme katılmaz.
- Aynı kesin paket kimliği çoğaltılmaz; kanıt güncelleme, kaldırma ve yeniden etkinleştirme atomik ve eklemeli geçmiş olarak saklanır. Geçersiz girdi, bilinmeyen varlık, kaldırılmış kayıt veya bozuk gizli geçmiş ağ/yazım öncesinde güvenli biçimde durur.
- `doctor` etkin Ubuntu paket kanıtı sayısını gösterir. Yedek/restore ana kayıtla bütün geçmişi korur; liste, ayrıntı ve eşleştirme otomatik maruziyet, güvenli, etkilenmiyor veya düzeltildi kararı üretmez.
- Şema 32 iki Ubuntu paket kanıtı tablosunu ekler. Şema 1–31 açık `migrate`, doğrulanmış geçiş öncesi yedek ve hata halinde geri alma ile yükselir; eski veriden paket bağı uydurulmaz.
- 995 otomatik test 128,113 saniyede geçti; yaşam döngüsü, source sürüm seçimi, ağ öncesi kapılar, gizli bozuk geçmiş, terminal/JSON, doctor, yedek/restore, şema 31→32 ve bütün eski geçişler doğrulandı.
- Canlı kabulde bilerek farklı verilen `php8.3-cli` binary `.99` sürümü ayrı kaldı; doğrulanmış `php8.3` source `.4` sürümü Canonical'ın `.5` fixed sınırından önce bulundu. Eşleştirme öncesi/sonrası veritabanı SHA-256 özeti aynıydı.

## 0.73.0 — 30 Ekim 2026

- `vuln ubuntu-match`, açıkça verilen Ubuntu OSV ekosistemi, Debian kaynak paket adı ve sürümünü Canonical'ın tek `UBUNTU-CVE` kaydıyla yazmasız karşılaştırır.
- Debian Policy 5.6.12 uyumlu yerel karşılaştırıcı epoch, upstream sürüm, Debian revision, sayısal parçalar, baştaki sıfırlar ve tilde sıralamasını uygular; sistemde `dpkg` bulunmasına bağlı değildir.
- Sonuçlar geri çekilmiş kayıt, affected bölümünde listelenmiyor, fixed sınırı olmayan kayıt ve düzeltme sınırından önce/eşit/sonra olarak ayrılır. Hiçbiri otomatik varlık maruziyeti veya insan kararı değildir.
- Girdi ve 1–200 duyuru sınırı ağdan önce doğrulanır; aynı yayın+paketin yinelenmesi, Canonical dışı/kanonik olmayan kimlik ve beklenmeyen OSV aralığı kısmi hüküm yerine işlemi durdurur. Şema 31 değişmedi.
- Canlı `CVE-2025-6491`, Ubuntu 24.04 LTS `php8.3` sürümü `8.3.6-0ubuntu0.24.04.4` için resmî `8.3.6-0ubuntu0.24.04.5` düzeltme sınırından önce sınıflandı; 9 sürüm ve 2 USN göründü. 987 test 131,178 saniyede geçti.

## 0.72.0 — 30 Ekim 2026

- `vuln ubuntu-preview CVE-YIL-SAYI`, Canonical'ın resmî `ubuntu-security-notices` deposundaki tek `UBUNTU-CVE` OSV kaydını yazmasız önizler. Yıl/kayıt yolu yalnız doğrulanmış CVE kimliğinden üretilir.
- Sabit HTTPS, yönlendirme reddi, 30 saniye, 8 MiB, kimlik kodlaması ve JSON/metin içerik türü sınırları uygulanır. Kayıt kimliği, upstream CVE bağı, OSV zaman/şema/URL/range yapısı ve yalnız `Ubuntu:*` paket ekosistemi tümden doğrulanır.
- Terminal Ubuntu yayınını, kaynak paketi, bildirilen sürüm sayısını, düzeltilmiş sürüm sınırını ve ADVISORY/USN başvurularını 1–200 görünüm sınırıyla gösterir. Tam kaynak özeti JSON çıktısında bulunur.
- Önizleme veritabanı oluşturmaz/yazmaz, yerel paket eşleştirmez ve maruziyet kararı üretmez. Ubuntu Pro/ESM bağlamı ücretsiz paket erişimi olarak yorumlanmaz; şema 31 değişmedi.
- Canlı `CVE-2025-6491` kaydı 7 paket/yayın bağlamı ve 2 USN başvurusuyla doğrulandı. 981 otomatik test 118,274 saniyede geçti; kimlik/ekosistem, taşıma, sınırlar, yazmasız terminal/JSON, kaynak kataloğu ve önceki davranışlar birlikte doğrulandı.

## 0.71.0 — 30 Ekim 2026

- `vuln source-evaluation`, ek resmî üretici zafiyet kaynaklarını sürümlü `official-vendor-source-gate-v1` profiliyle ağsız ve veritabanısız karşılaştırır.
- Zorunlu kapılar resmî üretici, ücretsiz/kimlik doğrulamasız erişim, yapılandırılmış biçim, sınırlı tek-kayıt erişimi, ürün/yayın bağlamı ve açık yeniden kullanım koşuludur; her sonuç kanıt açıklaması ve resmî bağlantıları taşır.
- Canonical Ubuntu OSV 6/6 ile tek seçilen sonraki kaynak oldu. Microsoft MSRC CVRF ve Debian Security Tracker 4/6 ile ertelendi; Cisco openVuln OAuth istemci kimliği/sırrı istediği için ücretsiz profil için reddedildi.
- Seçim ağ çağrısı, veri indirme, kaynak eşdeğerliği veya yerel maruziyet kararı üretmez. Bir sonraki uygulama yalnız tek `UBUNTU-CVE` kaydının sınırlı/yazmasız önizlemesidir; şema 31 değişmedi.
- 978 otomatik test 117,763 saniyede geçti; tek seçim, bütün zorunlu kapılar, erteleme/engel nedenleri, HTTPS kanıt bağlantıları, boş klasörde yazmasız terminal/JSON ve önceki davranışlar birlikte doğrulandı.

## 0.70.0 — 30 Ekim 2026

- `vuln nvd-window-operations`, en fazla 366 günlük seçili dönemle kesişen NVD pencerelerini tek salt-okunur anlık görüntüde tamam/hazır/hatalı olarak sayar; dikkat bekleyen toplamı ve yeniden başlatma olaylarını gösterir.
- En son güncellenen pencere ile `--recent-limit 1..100` son pencere, kalıcı sıra/toplam/hata bağlamıyla görünür. Zaman sırası doğrulanmış UTC kayıtlarından hesaplanır.
- Aynı sonuç yalnız tamamlanmış pencerelerden birleşik kapsama ve açık aralıkları üretir; operasyon durumu `no_activity`, `in_progress`, `attention`, `gaps` veya `covered` olarak açıklanır. Hatalı pencere, başka bir örtüşen pencere dönemi kapatsa bile gizlenmez.
- Komut internet isteği, onarım, yeniden başlatma veya SQLite yazımı yapmaz. 10.000 kesişen pencere ve 366 günlük dönem sınırları korunur; şema 31 değişmedi.
- 976 otomatik test 122,461 saniyede geçti; boş/hazır/hatalı/tam durumlar, yeniden başlatma, son ilerleme sırası, kapsama, sınırlar, salt-okunur terminal/JSON ve önceki davranışlar birlikte doğrulandı.

## 0.69.0 — 30 Ekim 2026

- `vuln nvd-window-gap-fetch`, kapsama boşluğu planının başındaki açıkça seçilmiş 1–3 pencerenin her birinden yalnız bir NVD sayfası alır. Sayfa başına mevcut 1–100 kayıt sınırı korunur.
- Komut ağdan önce bütün aday sayısını ve seçilen sınırı planlar; yerel çalıştırma kilidi altında her pencereyi yeniden doğrular, anahtarsız NVD istekleri arasında en az 6,5 saniye bırakır ve ilk kaynak hatasında durur.
- Her başarılı sayfa kendi CVE değişiklikleri, kaynak çalışması ve pencere imleciyle atomik yazılır. Kısmi pencere sonraki açık komuta kalır; başarısız pencerenin imleci ilerlemez ve sonraki adaylara istek gönderilmez.
- Sonuç denenmiş/başarılı/başarısız sayfa sayılarını, bu çalışmada denenmeyen önceki adayları ve yürütme sonrasındaki güncel boşluk planını ayrı gösterir. Tam kapsanmış dönem ağsız `nothing_to_do` sonucudur.
- Yeni tablo veya zamanlayıcı eklenmedi; şema 31 korundu. 974 otomatik test 124,147 saniyede geçti; çoklu tek-sayfa sınırı, kota beklemesi, kısmi devam, ilk hatada durma, tam kapsama, terminal/JSON ve önceki davranışlar birlikte doğrulandı.

## 0.68.0 — 30 Ekim 2026

- `vuln nvd-window-gap-plan`, en fazla 366 günlük kapsama incelemesindeki açık dönemleri kronolojik olarak en fazla yedi günlük NVD pencerelerine böler. Sayfa boyutu 1–100, gösterim sınırı 1–100 arasındadır.
- Her aday mevcut pencere planı üzerinden yeni/hazır/başarısız durumunu, kalıcı sonraki sırayı, bilinen toplamı ve hata bilgisini taşır; aynı tam pencere kimliğiyle yarım kalan çalışma kaybolmaz.
- Tamamlanmış dönemler aday üretemez. Aday toplamı, gösterilen sayı ve limit nedeniyle kesilme ayrı gösterilir; tam kapsanmış dönem boş plan döndürür.
- Boşluk planı yalnız kapsama ve pencere planı okumalarını kullanır; internet isteği, SQLite yazımı, otomatik yürütme veya zamanlayıcı başlatmaz. Şema 31 değişmedi.
- 971 otomatik test 140,267 saniyede geçti; yedi günlük bölme, tamamlanmış dönemi atlama, başarısız pencere devamı, limit/kesilme, tam kapsama, geçersiz sınırlar, salt-okunur terminal/JSON ve önceki davranışlar birlikte doğrulandı.

## 0.67.0 — 30 Ekim 2026

- `vuln nvd-window-list/show`, kayıtlı NVD pencerelerini yeni/hazır/başarısız/tamamlanmış durum, sıra/toplam/kalan ve yeniden başlatma geçmişiyle internete çıkmadan gösterir. Durum filtresi ve 1–500 kayıt sınırı vardır.
- `vuln nvd-window-coverage`, en fazla 366 günlük inceleme döneminde yalnız tamamlanmış pencereleri kapsama sayar; örtüşen/uç uca dönemleri birleştirir, hazır veya başarısız pencereleri ayrı sayar ve açık zaman aralıklarını gösterir.
- `vuln nvd-window-restart`, var olan pencereyi zorunlu 5–500 karakterlik gerekçeyle baştan hazırlar. Önceki sıra, toplam, durum, başarı/hata ve kaynak çalışma bağı eklemeli olayda korunur; CVE kayıtları, NVD değişiklik olayları ve kaynak çalışmaları silinmez.
- Yeniden başlatma yerel çalıştırma kilidi ve tek transaction kullanır; sistem saati son pencere kaydından gerideyse reddedilir. Salt-okunur liste/kapsama/ayrıntı yolları veritabanını değiştirmez.
- Şema 31 eklemeli `nvd_window_restart_events` geçmişini ekledi. Şema 1–30 açık `migrate`, doğrulanmış geçiş öncesi yedek ve hata halinde geri alma ile yükselir; eski ilerleme korunur ve geçmişten yeniden başlatma olayı uydurulmaz.
- 969 otomatik test 113,955 saniyede geçti; durum filtreleri, örtüşen/bitişik kapsama ve boşluklar, ağsız/salt-okunur görünüm, gerekçeli yeniden başlatma, geçmiş/CVE koruması, saat kapısı, terminal/JSON, şema 1–31 geçişleri ve önceki davranışlar birlikte doğrulandı.

## 0.66.0 — 30 Ekim 2026

- `vuln nvd-window-plan`, kullanıcı tarafından verilen saat dilimli ve en fazla yedi günlük NVD son-değişiklik aralığının sıradaki sayfasını internete çıkmadan gösterir. Yeni/hazır/başarısız/tamamlanmış durum, sonraki sıra, bilinen toplam, kalan kayıt ve ağ gereksinimi ayrı görünür.
- `vuln nvd-window-fetch`, resmî ücretsiz NVD CVE API 2.0'dan çağrı başına yalnız bir ve en fazla 100 kayıtlık sayfa alır. Sabit HTTPS uç noktası, yönlendirme reddi, 30 saniye, 8 MiB, kimlik/zaman/sayfa sınırları, yinelenen CVE ve pencere dışı kayıt doğrulamaları uygulanır.
- Sayfadaki CVE ekleme/değiştirme olayları ile kalıcı sonraki-sayfa imleci tek transaction'da yazılır. Kaynak veya ayrıştırma hatası, toplam sayının çalışma sırasında değişmesi, plan sapması ya da yarım sayfa imleci ilerletmez; önceki geçerli NVD kayıtları korunur.
- Tamamlanan pencere yeniden çağrıldığında ağ isteği yapılmaz. Anahtarsız NVD çağrıları süreçler arasında da en az 6,5 saniye aralıklıdır. Tarih penceresi tam ayna, otomatik zamanlayıcı, ürün keşfi veya maruziyet hükmü değildir; insan kararı ve olay geçmişi değişmez.
- Şema 30 kalıcı `nvd_window_syncs` ilerleme tablosunu ekledi. Şema 1–29 açık `migrate`, doğrulanmış geçiş öncesi yedek ve hata halinde geri alma ile yükselir; eski NVD kayıtlarından tamamlanmış pencere veya imleç uydurulmaz.
- 965 otomatik test 106,662 saniyede geçti; pencere/sayfa sınırları, katı taşıma, atomik iki sayfalı devam, hata ve plan sapmasında imleç koruması, insan kararı koruması, ağsız plan, terminal/JSON, şema 1–30 geçişleri ve önceki davranışlar birlikte doğrulandı.

## 0.65.0 — 30 Ekim 2026

- `vuln change-notify`, açık ve görünür maruziyetlerdeki ürün etkisizleşmesi, ürün kanıtı/NVD özeti değişimi ve gelmiş yeniden kontrol tarihini mevcut yerel bildirim kutusuna taşır. Kapanmış ve bastırılmış kapsam yalnız açık seçeneklerle eklenir.
- Bildirim durumu maruziyet, tetikleyiciler, ürün etkinliği/kanıt zamanı, NVD özeti ve yeniden kontrol tarihinin kanonik SHA-256 özetiyle tekilleştirilir. Aynı durum tekrar çalıştırıldığında bildirim veya okundu bilgisi çoğalmaz; farklı kanıt durumu yeni bildirim olur.
- Bir çalışmada en fazla 100 yeni bildirim eklenir; önceden bildirilmiş durumlar atlanarak sonraki adaylara ilerlenir. Plan ile transaction arasında kanıt, karar veya bastırma değişirse kısmi yazma olmadan durulur.
- Birleşik `inbox`, bulgu, pasif aday, dış yüzey değişikliği ve zafiyet değişikliği bildirimlerini ortak artan sırada listeler. Liste/ayrıntı salt okunur; okundu işlemi insanın maruziyet kararını, gerekçesini veya olay geçmişini değiştirmez.
- Şema 29 zafiyet değişiklik bildirim tablosunu ekledi. Şema 1–28 açık `migrate`, doğrulanmış geçiş öncesi yedek ve hata halinde geri alma ile yükselir; eski maruziyetlerden geriye dönük bildirim uydurulmaz.
- 953 otomatik test 118,521 saniyede geçti; durum tekilleştirme/ilerleme, kapsam, işlem sapması, bozuk özet, ortak kutu/okundu davranışı, terminal/JSON, şema 1–29 geçişleri ve önceki davranışlar birlikte doğrulandı.

## 0.64.0 — 30 Ekim 2026

- `vuln tracked-nvd-plan`, açık ve görünür maruziyetlerle ilişkili benzersiz CVE'lerin son başarılı NVD kontrol zamanını ağsız inceler. Güncel, yenileme zamanı gelmiş ve sistem saatinden ileride görünen kayıtları ayırır; kapanmış/bastırılmış kapsam yalnız açık seçeneklerle eklenir.
- `vuln tracked-nvd-refresh`, yalnız zamanı gelen ilgili CVE'lerden en fazla beşini resmî NVD tek-CVE API'sinden yeniler. Ücretsiz anahtarsız erişimde önceki süreçteki son NVD denemesini de hesaba katan en az 6,5 saniyelik aralık korunur; her CVE atomik kaydedilir ve ilk kaynak hatasında durulur.
- Aynı CVE'ye bağlı birden çok maruziyet tek ağ isteğinde gruplanır. Kaynak yenilemesi insan kararını veya olay geçmişini değiştirmez; değişmiş kaynak kaydı mevcut `reassessment-plan` akışında ayrı inceleme nedeni olur. Saat hatası olan kayıt için ağ isteği gönderilmez.
- Yeni tablo, ücretli servis veya API anahtarı eklenmedi; 0.63.0'ın şema 28 düzeni korunuyor.
- 943 otomatik test 106,989 saniyede geçti; güncel/eski/saat hatalı plan, CVE tekilleştirmesi, kapsam, ağ sınırı, kaynak hatası, süreçler arası istek aralığı, insan kararı koruması, terminal/JSON ve önceki davranışlar birlikte doğrulandı.

## 0.63.0 — 30 Ekim 2026

- `vuln reassessment-plan`, değişmiş doğrulanmış ürün kanıtı, değişmiş NVD kaynak kaydı, etkisizleşmiş ürün ve gelmiş yeniden kontrol tarihini bütün ilgili maruziyetlerde yerel ve salt okunur olarak planlar. Varsayılan açık/görünür kayıt kapsamı `--include-closed` ve `--include-suppressed` ile açıkça genişletilebilir.
- `vuln reassessment-run`, planlanan en fazla 500 adayı güncel yerel ürün/NVD koşullarıyla yeniden değerlendirip değişmez çalışma ve sonuç geçmişine yazar. İnsan `investigating/affected/not_affected/fixed` kararı, gerekçesi, güncelleme zamanı ve olay geçmişi değiştirilmez; eşleşmenin kaybolması güvenli hükmü üretmez.
- `vuln reassessment-runs/show` denetim geçmişini internete bağlanmadan gösterir. Plan ile yazım arasında ürün, NVD, insan kararı, bastırma veya tetikleyici değişirse bütün çalışma geri alınır; plan sınırı ve seçilen/toplam aday sayıları ayrı korunur.
- Şema 28 toplu yeniden değerlendirme çalışma/sonuç tablolarını ekledi. Şema 1–27 açık `migrate`, geçiş öncesi doğrulanmış yedek ve hata halinde geri alma ile yükselir; eski maruziyetlerden geriye dönük çalışma veya sonuç uydurulmaz. Yedek/restore denetim geçmişini korur.
- 934 otomatik test 107,883 saniyede geçti; plan tetikleyicileri, kapsam/sınır, karar ve olay koruması, işlem içi sapma, bozuk kayıt, terminal/JSON, yedek/restore, şema 1–28 geçişleri ve önceki davranışlar birlikte doğrulandı.

## 0.62.0 — 30 Ekim 2026

- Kayıtlı varlıklara gerekçeli `low/medium/high/critical` iş önemi tanımlayan `assets criticality-set/show/clear` komutları eklendi. Güncel durum ve `set/updated/reactivated/cleared` olay geçmişi ayrı tutulur; aynı kararın tekrarı yeni olay üretmez.
- `vuln exposure-queue`, insan beyanlı iş önemini ve son kayıtlı web/izinli servis kanıtından çıkarılan internet erişilebilirliğini aynı salt-okunur anlık görüntüde gösterir. Güncel HTTPS yanıtı ve açık TCP servis kanıtı, yalnız DNS, doğrulanamayan erişim, eski/eksik kanıt ve etkin olmayan kapsam birbirinden ayrılır.
- Yüksek/kritik iş önemi veya doğrulanmış güncel internet erişimi açık incelemenin çalışma bandını yükseltebilir; insanın maruziyet kararını değiştirmez. Kanıt yokluğu veya erişimin doğrulanamaması güvenli/internete kapalı hükmü üretmez.
- `--surface-stale-hours` ile kuyrukta 1–8760 saatlik açık güncellik eşiği eklendi; terminal ve JSON çıktısında bağlam, sayılar ve nedenler görünür oldu. Kuyruk ağ isteği veya yeni yüzey kontrolü yapmaz.
- Şema 27 iş önemi güncel durumunu ve eklemeli karar geçmişini ekledi. Şema 1–26 açık `migrate`, geçiş öncesi doğrulanmış yedek ve hata halinde geri alma ile yükselir; eski veriden önem kaydı uydurulmaz.
- 919 otomatik test 96,796 saniyede geçti; karar yaşam döngüsü, saat gerilemesi, güncel/eski/eksik erişim ayrımı, kuyruk önceliği, bozuk bağlamda güvenli durma, terminal/JSON, şema 1–27 geçişleri ve önceki davranışlar birlikte doğrulandı.

## 0.61.0 — 30 Ekim 2026

- `vuln vendor-preview CVE-YIL-SAYI --provider suse` ile SUSE Product Security Team'in resmî, ücretsiz ve tek-CVE CSAF VEX 2.0 belgesini yazmasız önizleme eklendi.
- Eski CVE'lerin SUSE'nin 2023 geri-doldurma dizininden, 2023 ve sonrasının CVE yılı dizininden alınması; sabit HTTPS yolu, yönlendirmesiz 30 saniye, 16 MiB ve JSON içerik türü sınırları uygulandı.
- Red Hat ve SUSE için ortak, sağlayıcı kimliğiyle yapılandırılan CSAF ayrıştırıcısı oluşturuldu. Yayımcı/CVE bağı, zamanlar, geçmiş, ürün ağacı, ilişkiler, durum çelişkileri, CPE/PURL ve düzeltme hedefleri aynı güvenli kurallarla doğrulanıyor.
- SUSE'nin gerçek belgelerinde kullandığı boş durum kovaları, boşluk içeren ürün kimlikleri ve CPE 2.3 değerleri güvenli biçimde destekleniyor; tüm durumların boş olması yine reddediliyor.
- SUSE önizlemesi yerel SUSE paketi veya varlık maruziyeti hükmü üretmiyor. Red Hat'e özel kesin RPM eşleştirme/kanıt akışı SUSE'ye taşınmadı; şema 26 değişmedi ve göç gerekmiyor.
- Canlı `CVE-2014-0160` belgesi 573 `known_not_affected`, 339 `recommended` ürün bağı ve 1 düzeltme kaydı olarak doğrulandı; kaynak özeti `6458fa60…a17a33c9` oldu, geçici veri klasörü oluşmadı.
- 906 otomatik test 122,720 saniyede geçti; ortak ayrıştırıcı, SUSE yolu/kimliği, gerçek belge biçimleri, taşıma, yazmasız terminal, kaynak kataloğu ve önceki davranışlar birlikte doğrulandı.

## 0.60.0 — 30 Ekim 2026

- `vuln exposure-suppress INCELEME_KIMLIGI --days 1..3650 --reason ...` ile yalnız açık maruziyete gerekçeli ve kesin bitişli geçici bastırma eklendi.
- `exposure-unsuppress` erken kaldırmayı; `exposure-suppression-show` etkinlik, bitiş ve eklemeli etkinleştirme/uzatma/yeniden etkinleştirme/geri alma geçmişini gösteriyor.
- Kesin bitiş anında kayıt veritabanına yazma, sahte geçmiş olayı veya insan kararı değişikliği olmadan varsayılan maruziyet listesi ve kuyruğuna geri dönüyor. `--include-suppressed` henüz etkin kayıtları açıkça dahil ediyor.
- Kapanmış veya süresiz bastırılmış kayda süreli bastırma eklenmiyor. Bozuk zaman/geçmiş listeyi ve kuyruğu güvenli durduruyor; doctor etkin/toplam süreli bastırma sayısını gösteriyor.
- Laboratuvar kabulü `not_observed` kontrolünün otomatik kapatmadığını, ayrı `fixed` insan kararını ve yeni NVD kanıtında gerekçeli `investigating` yeniden açılışını doğruluyor.
- Şema 25→26 geçişi doğrulanmış yedekten sonra iki boş tabloyu işlem bütünlüğüyle kuruyor; eski süresiz kararlardan bitiş uydurmuyor ve kontrollü hatada geri alıyor.
- 902 otomatik test 98,671 saniyede geçti; süreli yaşam döngüsü, kesin bitiş, salt-okunur geri dönüş, liste/kuyruk, bozuk kayıt, terminal/JSON, geçiş ve insan onaylı kapanma/yeniden açılma birlikte doğrulandı.

## 0.59.0 — 30 Ekim 2026

- `vuln exposure-queue` her incelemede iptal edilmemiş düzeltme planı sayısını, plan durumlarını, son kontrol sonuç kümelerini ve kontrol tarihi gelmiş plan sayısını gösteriyor.
- Kontrolü gelen plan `remediation_recheck_due` nedenini ekleyerek kaydı en az yüksek banda taşıyor; daha güçlü mevcut nedenler korunuyor. Plan veya sonuç insan kararını yine de değiştirmiyor.
- Maruziyet, KEV/EPSS/NVD, destek kanıtı ve düzeltme bağlamı aynı salt-okunur SQLite anında okunuyor. En fazla 10.000 plan doğrulanıyor; iptal edilmiş bozuk plan dahi gizlenmeden bütün kuyruk güvenli duruyor.
- Yeni tablo veya geçiş yok; şema 25 korunuyor.
- 894 otomatik test 89,877 saniyede geçti; düzeltme kuyruk bağlamı, vade önceliği, iptal, bozuk kayıt, salt-okunur terminal/JSON ve önceki davranışlar birlikte doğrulandı.

## 0.58.0 — 30 Ekim 2026

- `vuln remediation-plan` ile açık maruziyete etkin kesin paket/VEX kanıtı, genel destek kanıtı veya açık analist notu kaynaklı insan onaylı düzeltme planı bağlama eklendi.
- `remediation-implement/recheck/cancel/list/show` ile planlanan düzeltme, uygulama kanıtı, sonraki kontrol tarihi ve `not_observed/still_present/inconclusive` sonuçları eklemeli geçmişte ayrı tutuluyor.
- Uygulama sonrası kontrol tarihi zorunlu; riskin sürdüğü veya sonucun belirsiz olduğu kontrolde yeni tarih verilmeden kayıt yapılmıyor. Vadesi gelen planlar `remediation-list --due-only` ile görülüyor.
- Hiçbir plan veya yeniden kontrol maruziyetin insan kararını otomatik değiştirmiyor. `not_observed` sonucu bile ayrı `exposure-review --status fixed` kararı olmadan kapatma yapmıyor.
- Her olay o andaki maruziyet durumu ile güncel NVD/ürün kanıt özetlerini saklıyor; bozuk kayıt/geçmişte kısmi sonuç yerine güvenli duruluyor.
- Şema 24→25 geçişi doğrulanmış yedekten sonra boş düzeltme/olay tablolarını işlem bütünlüğüyle kuruyor; eski maruziyetlerden düzeltme kaydı uydurmuyor ve hata durumunda geri alıyor.
- 892 otomatik test 87,490 saniyede geçti; düzeltme yaşam döngüsü, kaynak bağı, vade, otomatik kapatmama, bozuk veri, terminal/JSON, geçiş, backup/restore ve önceki davranışlar birlikte doğrulandı.

## 0.57.0 — 29 Ekim 2026

- `vuln vendor-evidence-check KANIT_KIMLIGI` ile kayıtlı kesin RPM/VEX kanıtını güncel yerel paket anlık görüntüsü ve yeniden alınan Red Hat belgesiyle salt okunur karşılaştırma eklendi.
- Tamamen güncel, yalnız kaynak dosyası değişmiş ama beyan aynı, paket yeniden doğrulanmış, beyan değişmiş, seçilen bağ kaybolmuş, çelişen bağlam ve etkisiz paket durumları ayrı raporlanır.
- Etkisiz pakette dış kaynağa bağlanılmaz. Hiçbir sonuç yeni kanıt, maruziyet kararı, yeniden inceleme kaydı veya öncelik değişikliği yazmaz; şema 24 değişmez.
- Canlı Heartbleed kanıtı resmî Red Hat VEX kaynağına karşı `current/fixed` bulundu; kontrol öncesi ve sonrası veritabanı SHA-256 özeti aynı kaldı.
- 885 otomatik test 91,088 saniyede geçti; güncel, kaynak yenilenmiş, paket değişmiş/etkisiz, beyan değişmiş ve ilişki kaybolmuş senaryoları ile terminal/JSON, kaynak kataloğu ve önceki davranışlar birlikte doğrulandı.

## 0.56.0 — 29 Ekim 2026

- `vuln vendor-evidence-add INCELEME_KIMLIGI PAKET_KIMLIGI --vex-product-id ...` ile insanın seçtiği güncel ve kesin Red Hat RPM/VEX ilişkisini kalıcı, yapılandırılmış kanıta dönüştürme eklendi.
- Maruziyet ve RPM aynı varlığa ait olmalı; CVE incelemeden alınır. Kaynak yeniden çekilir ve seçilen tam VEX ürün kimliği güncel, tekil ve çelişkisiz kesin eşleşmelerde bulunmadan yazma yapılmaz.
- CVE, kesin paket, kaynak SHA-256, belge sürümü/yayım zamanı, üretici durumu, eşleşme türü, bileşen PURL'si ve dağıtım CPE'si birlikte saklanır. Ağ sırasında paket değişirse eski seçim atomik yazma kapısında reddedilir; yeni kaynak özeti eski kanıtı ezmez.
- `vendor-evidence-list/show/revoke` ile etkin/etkisiz kayıt ve eklemeli geçmiş görünür. Aynı kaynak ve ürün bağı çoğalmaz; açıklama güncellemesi ve yeniden etkinleştirme geçmişte kalır.
- Kesin üretici kanıtı maruziyet kuyruğunda `exact_vendor_package` türü olarak sayılır ve kanıt boşluğu filtresine katılır; insan kararı veya öncelik bandı otomatik değişmez.
- Şema 23→24 geçişi önce doğrulanmış, üzerine yazılmayan yedek oluşturur; yeni tablolar boş başlar, eski eşleşmeden kanıt uydurmaz ve DDL hatasında tüm değişikliği geri alır.
- 880 otomatik test 99,599 saniyede geçti; kesin seçim, aynı-varlık/CVE kapısı, ağ sırasındaki paket değişimi, kaynak ve paket anlık görüntüsü ayrımı, kuyruk bağlamı, bozuk veri, terminal/JSON, şema 23→24 geçişi, backup/restore ve önceki davranışlar birlikte doğrulandı.

## 0.55.0 — 29 Ekim 2026

- `vuln vendor-match PAKET_KIMLIGI CVE-YIL-SAYI` ile etkin kesin Red Hat RPM kanıtını resmî tek-CVE CSAF VEX belgesiyle salt okunur karşılaştırma eklendi.
- VEX ürün ağacındaki PURL/CPE yardımcıları ve `default_component_of` ilişkileri katı ve sınırlı ayrıştırılır. Tam ikili paket eşleşmesi aynı NEVRA+PURL+dağıtım CPE; kaynak paket bağlamı doğrulanmış kaynak RPM adı+PURL+CPE gerektirir.
- Farklı epoch, release, mimari veya dağıtım bağlamı eşleşmez. Eşleşme yokluğu “güvenli”, kaynakta eksiklik “etkilenmiyor” sayılmaz; çelişen üretici bağlamı tek duruma indirgenmez.
- Sonuç yalnız Red Hat'in VEX beyanıdır; maruziyet incelemesi, destek kanıtı, öncelik veya insan kararı yazılmaz/değiştirilmez. Kaldırılmış paket kaynak isteğinden önce reddedilir.
- Gerçek `CVE-2014-0160` belgesinde `openssl-0:1.0.1e-16.el6_5.7.x86_64`, aynı RHEL 6 Client bağıyla tek `fixed` kaydına eşleşti; salt okuma veritabanı özetini değiştirmedi.
- 871 otomatik test 92,244 saniyede geçti; kesin VEX ilişkileri, farklı dağıtım/NEVRA sınırları, kaynak paket bağlamı, salt-okunur terminal/JSON ve önceki davranışlar birlikte doğrulandı.

## 0.54.0 — 29 Ekim 2026

- `packages add/list/show/revoke` ile kayıtlı varlığa kesin Red Hat RPM kimliği bağlama eklendi: paket adı, epoch, sürüm, release, mimari ve dağıtım CPE'si birlikte zorunludur; kaynak RPM biliniyorsa ayrıca tutulur.
- Red Hat VEX ile aynı ailede kullanılacak PURL kullanıcı metninden değil doğrulanmış alanlardan üretilir. Epoch ayrı korunur; başka dağıtımın veya başka ürün bağlamının hükmü pakete taşınmaz.
- Aynı kesin paket kimliği çoğaltılmaz; kanıt/kaynak RPM güncellemesi, iptal ve yeniden etkinleştirme ana kayıtla birlikte eklemeli olay geçmişinde tutulur. Liste ve ayrıntı salt okunurdur.
- Şema 22→23 geçişi önce doğrulanabilir ve üzerine yazılmayan yedek alır, paket tablolarını boş oluşturur ve eski genel ürün kayıtlarından RPM uydurmaz. Hata bütün DDL'yi geri alır; backup/restore paket geçmişini korur.
- `doctor` etkin kesin RPM sayısını gösterir. Paket kaydı tek başına CVE etkilenmesi, düzeltildi veya etkilenmiyor kararı üretmez; doğrudan VEX eşleştirmesi sonraki ayrı salt-okunur katmandır.
- 866 otomatik test 86,579 saniyede geçti; paket yaşam döngüsü, katı doğrulama, bozuk veri, terminal/JSON, şema 22→23 geçişi, backup/restore ve önceki davranışlar birlikte doğrulandı.

## 0.53.0 — 29 Ekim 2026

- `vuln vendor-preview CVE-YIL-SAYI --provider redhat` ile Red Hat'in resmî, tek-CVE CSAF VEX 2.0 belgesini ücretsiz ve yazmasız önizleme eklendi.
- Sabit yıl/CVE HTTPS yolu, yönlendirmesiz 30 saniye, 16 MiB, JSON içerik türü ve kimlik kodlaması sınırları uygulanır; yayımcı, CVE, belge zamanları/sürümü, ürün ağacı ve durum kümeleri tümden doğrulanır.
- `fixed`, `known_affected`, `known_not_affected`, `under_investigation` ve diğer CSAF durumları çelişmeyecek biçimde ayrılır; ürün kimlikleri anlaşılır adlarla, düzeltmeler hedef sayısı ve başvurusuyla sınırlı gösterilir.
- VEX beyanı yalnız Red Hat ürünlerine uygulanır; yerel paket kimliği olmadan başka dağıtım veya varlığa taşınmaz, otomatik karar/kanıt/öncelik üretmez. Şema 22 değişmedi.
- Gerçek `CVE-2014-0160` belgesi 85 `fixed`, 14 `known_not_affected` bileşen ve 5 `vendor_fix` başvurusu olarak doğrulandı; kaynak özeti `41f16857…25c66` oldu, geçici veri klasörü oluşmadı.
- 856 otomatik test 83,393 saniyede geçti; katı CSAF ayrıştırma, taşıma, ürün/durum çelişkileri, yazmasız CLI, kaynak kataloğu ve önceki davranışlar birlikte doğrulandı.

## 0.52.0 — 29 Ekim 2026

- `vuln advisory-evidence-add` ile OSV önizlemesindeki tek bir HTTPS `ADVISORY` başvurusunu açık insan seçimiyle mevcut maruziyet incelemesine bağlama eklendi.
- Komut incelemenin CVE kimliğini yerelden doğrular, güncel OSV kaydını yeniden alır ve verilen tam adresin o kayıtta bulunduğunu denetler; yalnız bundan sonra `vendor_advisory` veya `distribution_advisory` kanıtı yazar.
- Geçersiz tür/HTTPS/açıklama, bilinmeyen inceleme, kaynak hatası ve güncel listede bulunmayan adres hiçbir kalıcı kanıt oluşturmaz. Ağ beklerken SQLite transaction'ı açık tutulmaz.
- OSV üyeliği yalnız kaynak bağlantısını doğrular; içerik doğruluğu, sahiplik, etkilenme, insan kararı veya öncelik hükmü üretmez. Mevcut eklemeli kanıt yaşam döngüsü ve şema 22 korunur.
- Geçici Heartbleed incelemesinde güncel OSV kaydından seçilen Red Hat HTTPS başvurusu `distribution_advisory` olarak eklendi; kanıt kimliği `434b58da…29ca`, kaynak özeti `714b6694…ccd8ab6` oldu. Kuyruk iki kanıt gösterdi fakat bant/karar değişmedi.
- 852 otomatik test 80,576 saniyede geçti; seçim üyeliği, ağ-yazma sırası, atomik hata yolları, CLI, kaynak kataloğu ve önceki davranışlar birlikte doğrulandı.

## 0.51.0 — 29 Ekim 2026

- `vuln advisory-preview CVE-YIL-SAYI` ile seçilen tek CVE için ücretsiz OSV.dev duyuru, paket ve sürüm sınırı bağlamı eklendi; API anahtarı gerekmez.
- OSV bağlantısı sabit HTTPS uç noktası, yönlendirmesiz 30 saniye, 8 MiB, JSON içerik türü ve kimlik kodlaması sınırlarıyla çalışır; istenen CVE ile uyuşmayan, yinelenen alanlı veya bozuk yanıtın tamamı reddedilir.
- OSV kaydı yalnız araştırma önizlemesidir: üretici hükmü, varlık maruziyeti veya otomatik destek kanıtı üretmez; eksik paket verisi “etkilenmiyor” sayılmaz.
- Paket ve `ADVISORY` başvuruları sınırlı gösterilir; HTTP başvuruları yalnız bağlamdır, duyuru destek kanıtında mevcut HTTPS şartı korunur.
- Önizleme veritabanı/veri klasörü oluşturmaz ve yazmaz. Kaynak hataları güvenli `source_error` çıktısına dönüşür; traceback veya uzak hata ayrıntısı sızmaz. Bu sürümde otomatik kanıt aktarımı yoktur ve şema 22 değişmedi.
- Resmî API üzerinde `CVE-2014-0160` canlı önizlemesi ayrı geçici yolda tamamlandı; kaynak özeti `714b6694…ccd8ab6` oldu, kalıcı kayıt oluşturulmadı.
- 848 otomatik test 81,745 saniyede geçti; katı OSV ayrıştırma/taşıma, sınırlar, terminal/JSON, yazmasız çalışma, hata görünümü ve önceki davranışlar birlikte doğrulandı.

## 0.50.0 — 29 Ekim 2026

- `vuln exposure-queue --evidence all|present|missing`: bütün incelemeleri, etkin destek kanıtı olanları veya kanıtı olmayanları ayrı çalışma listesi olarak gösterme.
- Kuyruk özetinde seçili kapsam içindeki kanıtlı ve kanıtsız inceleme sayılarını ayrı verme.
- Kapanmış ve bastırılmış seçimlerini kanıt filtresiyle birlikte uygulama; filtreyi risk veya karar anlamına dönüştürmeme.
- Geçersiz filtreyi depoya erişmeden reddetme; terminal ve JSON çıktısında uygulanan filtreyi açık gösterme.
- Yeni tablo, ağ, yazma veya bant değişikliği olmadan şema 22 üzerinde çalışma.
- Geçici Heartbleed kaydı `present` listesinde göründü, `missing` listesinde görünmedi; salt okuma özeti `e9e4f4…983fe` kaldı.
- 844 otomatik test 74,294 saniyede birlikte geçti; filtre dalları mevcut kuyruk, kanıt ve mimari testleri içinde doğrulandı.

## 0.49.0 — 29 Ekim 2026

- `vuln exposure-queue` içinde her incelemenin etkin destek kanıtı sayısını ve türlerini aynı salt-okunur veritabanı anında gösterme.
- Kuyruk toplamında destek kanıtı bulunan inceleme sayısı ile etkin kanıt sayısını ayrı verme.
- Destek kanıtını yalnız bağlam sayma; tür veya sayıdan yeni öncelik nedeni, bant ya da insan kararı üretmeme.
- Kapanmış/bastırılmış filtrelerini kanıtlara da tam uygulama; yalnız seçili incelemelerin etkin kanıtlarını yükleme.
- Seçili bütün etkin kanıtları 10.000 kayıt sınırına kadar doğrulama; bozuk ilgili kanıtta kısmi kuyruk vermeden durma.
- Yeni tablo, ağ veya yazma olmadan şema 22 üzerinde çalışma.
- Geçici Heartbleed kuyruğu bir yerel paket envanteri kanıtını gösterdi; salt okuma öncesi/sonrası özet `e9e4f4…983fe` kaldı.
- 844 otomatik test 75,026 saniyede geçti; kanıt bağlamı, filtre, bozuk veri, terminal/JSON ve önceki davranışlar doğrulandı.

## 0.48.0 — 29 Ekim 2026

- `vuln exposure-evidence-add`: bir maruziyet incelemesine üretici duyurusu, dağıtım duyurusu, yerel paket envanteri veya analist notunu kaynak başvurusu ve açıklamayla bağlama.
- `vuln exposure-evidence-list/show/revoke`: etkin kanıtları listeleme, bütün eklemeli geçmişi gösterme ve yanlış/eski kanıtı silmeden etkisizleştirme.
- Aynı inceleme+tür+kaynak başvurusunu tek kimlikte tutma; açıklama güncellemesini, iptali ve yeniden etkinleştirmeyi ayrı olaylarla koruma.
- Duyuru başvurularında yalnız kimlik bilgisi/parça içermeyen HTTPS adreslerini kabul etme; ekleme ve okuma sırasında hiçbir kaynağı kendiliğinden açmama.
- Kanıtı yalnız karar desteği sayma; varlığından otomatik `affected`, `not_affected`, `fixed`, öncelik veya yeniden inceleme sonucu üretmeme.
- Ana kayıt ve olayın tek transaction'da yazılması; bilinmeyen inceleme, bozuk kayıt/geçmiş ve geçersiz girdide kısmi yazmadan durma.
- Şema 21→22 geçişinde doğrulanabilir yedek, boş destek-kanıtı tabloları, işlemsel geri alma ve eski kayıtlardan kanıt uydurmama.
- `doctor` içinde etkin maruziyet destek kanıtı sayısı; yedek/restore, saat gerilemesi ve salt-okunur liste/ayrıntı desteği.
- Geçici Heartbleed incelemesine yerel OpenSSL paket beyanı eklendi; şema 21 yedeği korundu ve salt okumalar sonrası veritabanı özeti `e9e4f4…983fe` olarak değişmeden kaldı.
- 842 otomatik test 85,439 saniyede geçti; yaşam döngüsü, kaynak sınırları, bozuk veri, terminal/JSON, migration ve önceki davranışlar birlikte doğrulandı.

## 0.47.0 — 29 Ekim 2026

- `vuln exposure-queue`: açık insan maruziyet incelemelerini ürün, NVD, CISA KEV, FIRST EPSS ve birincil CVSS bağlamıyla tek salt-okunur veritabanı anında sıralama.
- Tek risk puanı yerine `immediate`, `high`, `normal`, `monitored` bantları ve her bant için ayrı insan kararı/yeniden inceleme/KEV/ransomware/EPSS/CVSS nedenleri.
- Varsayılan yalnız görünür `investigating/affected`; `--include-closed` ve `--include-suppressed` ile açık kapsam genişletme.
- Kullanıcı ayarlı tam ondalıklı `--min-epss`, kapanmış kararın yalnız kaynak puanı nedeniyle yeniden açılmaması ve değişmiş kanıtta yeniden inceleme bandı.
- En fazla 10.000 seçili kaydı ve ilgili kaynakları tam doğrulama, 500 sonuç gösterme; bozuk ilgili kaynakta kısmi kuyruk vermeden durma.
- Yeni tablo, ağ, yazma veya karar değişikliği olmadan şema 21 üzerinde çalışma.
- Geçici Heartbleed kaydı KEV, EPSS `0.99999` ve CVSS 3.1 `7.5 HIGH` nedenleriyle “Hemen incele” bandında göründü; salt okuma veritabanı özetini değiştirmedi.
- 834 otomatik test 88,107 saniyede geçti; kuyruk politikası, filtreler, eşik, bozuk kaynak, terminal/JSON ve önceki davranışlar birlikte doğrulandı.

## 0.46.0 — 29 Ekim 2026

- `vuln exposure-open`: yalnız kesin-koşul veya elle-inceleme ürün+CVE adayını açık gerekçeyle `investigating` durumunda kalıcı insan incelemesine alma.
- `vuln exposure-review`: `investigating`, `affected`, `not_affected` ve `fixed` insan kararlarını zorunlu gerekçe, isteğe bağlı bastırma ve yeniden kontrol tarihiyle kaydetme.
- `vuln exposure-list/show`: varsayılan görünür kayıtları, bastırılmış dâhil filtreyi, karar geçmişini ve yeniden inceleme nedenlerini ağsız gösterme.
- Karar anındaki ürün kanıt zamanı, NVD kaynak özeti ve aday sınıfını saklama; ürün etkisizleşmesi, ürün kanıtı/NVD değişimi veya yeniden kontrol tarihinin gelmesini eski kararı silmeden görünür kılma.
- Değerlendirme ile yazım arasında ürün/NVD değişirse işlemi durdurma; ana kayıt ile eklemeli olayı tek transaction'da yazma ve saat gerilemesinde ana zamanı geriye taşımama.
- Şema 20→21 geçişinde doğrulanabilir yedek, boş maruziyet/olay tabloları, işlemsel geri alma ve eski eşleşmelerden insan kararı uydurmama.
- `doctor` içinde toplam ve açık/görünür maruziyet inceleme sayıları; yedek/restore ve bozuk kanıtta güvenli durma.
- 830 otomatik test 75,375 saniyede geçti; yaşam döngüsü, kaynak değişimi, yeniden kontrol, bastırma, saat gerilemesi, terminal/JSON, migration ve önceki davranışlar birlikte doğrulandı.

## 0.45.0 — 29 Ekim 2026

- `vuln match-products CVE-YIL-SAYI`: tek yerel NVD kaydını bütün etkin kullanıcı doğrulamalı ürün envanteriyle ağsız karşılaştırma.
- Varsayılan olarak yalnız kesin koşul ve elle inceleme adaylarını; `--all` ile ürün/sürüm koşulu eşleşmeyen kayıtları da gösterme.
- Etkin ürün, toplam aday, kesin aday, elle inceleme, ürün koşulu yok, sürüm uyuşmuyor ve NVD koşulu yok sayılarını ayrı verme.
- Bütün etkin ürünleri doğrulama; bozuk fakat gösterim sınırının dışında kalan ürün kaydını da sessizce atlamadan tüm görünümü durdurma.
- En fazla 10.000 etkin ürün, 500 gösterim ve ürün başına 20 koşul sınırı; CPE listesini ürün kimliği ve `AND` yapı bağlamına göre bir kez indeksleyerek tekrar taramayı önleme.
- Yeni tablo, ağ, alarm, risk skoru veya otomatik maruziyet kaydı olmadan çalışma.
- 822 otomatik test 74,580 saniyede geçti; yeni tek-ürün ve envanter görünümleriyle bütün önceki davranışlar birlikte doğrulandı.

## 0.44.0 — 29 Ekim 2026

- `vuln asset-overview ÜRÜN_KİMLİĞİ CVE-YIL-SAYI`: doğrulanmış ürün koşulu, CISA KEV, FIRST EPSS ve NVD/CVSS bağlamını tek ekranda gösterme.
- Ürün koşulu, gerçek dünyada bilinen istismar, 30 günlük nüfus düzeyi olasılığı ve teknik önem/etki anlamlarını tek risk puanında eritmeden ayrı tutma.
- NVD eksikken mevcut KEV/EPSS bilgisini koruma ve ürün koşulunu “değerlendirilemedi” gösterme; eksik kaynağı güvenli/sıfır risk saymama.
- Ürün ve üç zafiyet kaynağını tek salt-okunur SQLite anlık görüntüsünden alma; bozuk tek kaynakta kısmi güvenilir görünüm vermeden durma.
- Geçici canlı Heartbleed/OpenSSL örneğinde yerel kaynak kapsamı 3/3 gösterildi ve görünüm veritabanı özetini değiştirmedi.

## 0.43.0 — 29 Ekim 2026

- `vuln assess-product ÜRÜN_KİMLİĞİ CVE-YIL-SAYI`: kullanıcı doğrulamalı ürün kaydını yerel NVD CPE koşullarıyla tek salt-okunur anlık görüntüde karşılaştırma.
- Tür, üretici ve ürün kimliğini tam eşleştirme; kesin sürüm eşleşmesini yalnız “NVD koşulu adayı” sayma, otomatik zafiyet/maruziyet hükmü vermeme.
- Sürüm aralığı, joker/uygulanamaz sürüm, `AND`, `negate` ve çevresel `vulnerable=false` bağlarını otomatik sonuca indirmeden “elle inceleme gerekli” tutma.
- Ürün koşulu yok, kesin sürüm uyuşmuyor, NVD koşulu yok ve etkisiz ürün kaydı durumlarını birbirinden ayırma; hiçbirini “güvenli” sonucu saymama.
- İlgili `AND` grubundaki farklı donanım/ortam koşullarını kaybetmeden gösterme; görüntüyü 1–500 satırla sınırlama ve saklı NVD koşullarının tamamını doğrulama.
- Ağ isteği, yeni tablo, bulgu/alarm yazımı veya otomatik risk skoru olmadan çalışma; bozuk ürün/NVD kanıtında kısmi sonuç vermeden durma.
- 814 otomatik test 67,649 saniyede geçti; kesin/aralıklı/uyuşmayan/eksik/etkisiz koşullar, çevresel `AND` bağı, terminal/JSON, salt-okunurluk ve önceki davranışlar birlikte doğrulandı.
- Geçici canlı Heartbleed örneğinde doğrulanmış OpenSSL `1.0.1f`, NVD'nin `>=1.0.1, <1.0.1g` aralığı nedeniyle otomatik hüküm yerine elle incelemeye ayrıldı; değerlendirme veritabanı özetini değiştirmedi.

## 0.42.0 — 29 Ekim 2026

- `products add/list/show/revoke`: kayıtlı domaine kullanıcı tarafından doğrulanmış CPE türü, üretici, ürün, kesin sürüm ve açıklayıcı kanıt bağlama.
- Port/servis ipuçlarını otomatik ürün kaydına dönüştürmeme; yalnız açık kullanıcı işlemiyle `user_verified` kanıt oluşturma.
- Aynı varlık+ürün+sürüm kimliğini çoğaltmayan; kanıt güncelleme, kaldırma ve yeniden etkinleştirmeyi eklemeli olay geçmişinde koruyan yaşam döngüsü.
- Etkin/kaldırılmış filtreleri, varlığa göre kesin kapsam, güvenli terminal/JSON görünümü ve `doctor` etkin ürün sayacı.
- Şema 19→20 geçişinde doğrulanabilir yedek, iki ürün kanıt tablosunu boş ve işlemsel oluşturma, hata geri alma, eski veriden ürün/sürüm uydurmama.
- Yedek/restore, bozuk kayıtta güvenli durma, eski şemanın kendiliğinden değişmemesi ve çok-varlık ayrımı testleri.
- Şema ve ürün dilimi sonrasında bütün 808 test 69,171 saniyede geçti; sonraki 0.43 kontrolleriyle toplam 814 teste ulaşıldı.

## 0.41.0 — 29 Ekim 2026

- `vuln applicability CVE-YIL-SAYI`: yerel NVD kaydındaki CPE 2.3 ürün, işletim sistemi, donanım ve sürüm koşullarını internete çıkmadan gösterme.
- NVD yapı/düğüm `AND`/`OR` operatörlerini, isteğe bağlı terslemeyi, `vulnerable=true/false` ayrımını ve kaynak sırasını koruma.
- Tam sürüm, başlangıç/bitiş dahil-hariç sınırlarını ve kaçış karakterli CPE bileşenlerini katı biçimde ayrıştırma; ham CPE ve `matchCriteriaId` kanıtını koruma.
- `vulnerable=false` satırlarını güvenli ürün diye atmak yerine donanım/ortam bağlayıcı koşulu olarak görünür tutma.
- Gösterimi 1–500 satırla sınırlarken toplam kaydın tamamını doğrulama ve gerçek toplamları verme; 2.000 yapı, 10.000 düğüm ve 20.000 eşleşme güvenlik sınırı.
- Uygulanabilirlik verisi olmayan NVD kaydını “koşul yok” olarak gösterme; bundan ürünün etkilenmediği veya varlığın güvenli olduğu sonucunu çıkarmama.
- Bozuk saklı CPE mantığı, UUID, tür, sürüm sınırı veya biçimde kısmi çıktı vermeden güvenli durma.
- Yeni tablo/migration veya kopya CPE kataloğu eklemeden NVD'nin kanonik kaynak nesnesinden salt-okunur görünüm üretme.
- 799 otomatik test 63,455 saniyede geçti; CPE grupları, sürüm aralıkları, kaçışlar, ortam koşulları, eksik/bozuk veri, terminal/JSON, salt-okunurluk ve önceki davranışlar birlikte doğrulandı.
- Canlı Heartbleed kaydında 54 CPE koşulu doğrulandı: 47 doğrudan etkilenen ürün ve 7 ortam/bağlayıcı koşul; görünüm veritabanı özetini değiştirmedi.

## 0.40.0 — 29 Ekim 2026

- `vuln enrich-nvd`: çevrimdışı plandaki ilk kayıtları yalnız açık kullanıcı komutuyla NVD API 2.0'dan alma.
- Ücretsiz ve anahtarsız kullanımda bir çalıştırmayı en fazla beş CVE ile sınırlama; her tamamlanan isteğin ardından en az 6,5 saniye bekleme.
- Önceki süreçteki son NVD çalışma zamanını da hesaba katma; ortak yerel çalışma kilidiyle eşzamanlı kaynak isteklerini engelleme.
- İlk kaynak hatasında yeni istek göndermeyi durdurma; başarılı kayıtları ve başarısız çalışma kanıtını ayrı ayrı koruma.
- Sonraki çalıştırmada NVD'si alınmış CVE'leri otomatik plandan çıkararak kalanlardan devam etme; ayrı toplu durum tablosu oluşturmama.
- Eksik/eski/bozuk veritabanını ve geçersiz limit/eşiği ağ isteğinden önce reddetme; sistem saati son çalışma zamanının gerisindeyse güvenli durma.
- Terminal/JSON sonucunda planlanan, denenen, başarılı/başarısız kayıtları ve sabit bekleme ilkesini gösterme.
- 794 otomatik test 64,047 saniyede geçti; önceki/ardışık istek aralığı, limit kapısı, ilk hatada durma, devam planı, terminal/JSON ve önceki davranışlar birlikte doğrulandı.
- Canlı tek-kayıt denemesinde ilk kısıtlı bağlantı hatası geçmişte korundu; ağ erişimli tekrar Heartbleed (`CVE-2014-0160`) kaydını aldı ve sonraki plan adayı 2.102'den 2.101'e düştü.

## 0.39.0 — 29 Ekim 2026

- `vuln plan`: güncel CISA KEV veya kullanıcı eşiğini geçen FIRST EPSS kayıtları arasından NVD bağlamı eksik CVE'leri çevrimdışı sıralama.
- Güncel KEV adaylarını önceleme, aynı CVE'nin KEV/EPSS nedenlerini tek satırda birleştirme ve NVD kaydı zaten bulunanları çıkarma.
- `--min-epss 0–1` ve `--limit 1–100` sınırları; ondalık eşiği kayan nokta yuvarlamasına bırakmadan 18 basamağa kadar kararlı karşılaştırma.
- Uygun toplam, NVD'si eksik güncel KEV ve NVD'si eksik yüksek EPSS sayılarını terminal/JSON çıktısında ayrı gösterme.
- Planlamayı tek salt-okunur SQLite anlık görüntüsünde yapma; internet isteği, NVD indirme, sıra kaydı veya veri değişikliği oluşturmama.
- Seçilen saklı KEV/EPSS kanıtlarını yeniden doğrulama; bozuk seçili kayıtta güvenli durma.
- Yeni tablo veya migration eklemeden şema 19 üzerinde çalışma; planı varlık maruziyeti veya otomatik risk sonucu saymama.
- 791 otomatik test 64,920 saniyede geçti; plan seçimi, eşik sınırı, tekilleştirme, terminal/JSON, salt-okunurluk, bozuk kayıt ve önceki davranışlar birlikte doğrulandı.
- Ayrı geçici alandaki canlı katalogda 2.102 uygun CVE bulundu; ilk 10 kayıt yaklaşık 0,63 saniyede gösterildi ve veritabanı SHA-256 özeti değişmedi.

## 0.38.0 — 29 Ekim 2026

- `vuln overview CVE-YIL-SAYI`: aynı CVE'nin yerel CISA KEV, FIRST EPSS ve NVD/CVSS bağlamını tek terminal/JSON görünümünde birleştirme.
- KEV'in doğrulanmış geçmiş istismarı, EPSS'nin 30 günlük nüfus düzeyi olasılığı ve CVSS'nin teknik önem/etki anlamını ayrı başlıklarla koruma; hiçbirinden ürün/sürüm veya varlık maruziyeti sonucu üretmeme.
- Üç kaydı tek salt-okunur SQLite anlık görüntüsünden alma; görünüm sırasında internete bağlanmama ve veritabanını değiştirmeme.
- Alınmamış kaynakları açıkça “yerel kayıtta yok” gösterme; eksik veriyi sıfır risk veya güvenli durum saymama.
- Üç kaynaktan biri bozuksa kısmen güvenilir görünen bir sonuç vermek yerine bütün birleşik görünümü güvenli biçimde durdurma.
- Yeni tablo veya migration eklemeden şema 19 üzerinde çalışma; mevcut KEV, EPSS ve NVD yaşam döngülerini değiştirmeme.
- 787 otomatik test 71,362 saniyede geçti; birleşik anlık görüntü, terminal/JSON, salt-okunurluk, bozuk kayıt ve önceki davranışlar birlikte doğrulandı.
- Ayrı geçici alandaki canlı doğrulamada Log4Shell için üç kaynağın üçü birlikte gösterildi; görünüm öncesi ve sonrası veritabanı SHA-256 özeti aynı kaldı.

## 0.37.0 — 29 Ekim 2026

- `vuln sync --source nvd --cve CVE-YIL-SAYI`: açıkça istenen tek CVE'yi NIST NVD API 2.0'dan anahtarsız ve ücretsiz alma.
- Sabit resmî HTTPS uç noktası, yönlendirme reddi, 30 saniye/8 MiB yanıt ve 4 MiB tek-kayıt sınırı; kimlik, sayfa, zaman, metin, CWE, referans ve CVSS doğrulaması.
- NVD ve diğer sağlayıcıların CVSS 4.0/3.1/3.0/2.0 kaynak, tür, vektör, taban/etki/istismar edilebilirlik skorlarını tek skora indirgemeden saklama.
- İngilizce açıklama, NVD durumu, yayın/son değişiklik zamanı, CWE ve referans sayısını terminalde gösterme; tam kanonik CVE nesnesini sonraki CPE/ürün çalışması için koruma.
- Yeni ve değişen CVE kaynak nesneleri için atomik güncel kayıt ve eklemeli olay geçmişi; aynı kaydı çoğaltmama.
- Kaynak başarısızlığını kaydederken önceki geçerli CVE kaydını koruma.
- `vuln status/list/show --source nvd`: internete bağlanmadan kaynak durumu, yerel CVE listesi, bütün CVSS değerlendirmeleri ve değişiklik geçmişi.
- İlk dilimi açıkça tek-CVE, tam ayna olmayan kapsamda tutma; CVSS'yi EPSS, KEV, risk veya varlık maruziyeti saymama.
- Kaynak kataloğunda NIST NVD bağlantısını ücretsiz, anahtarsız ve izlenen hedefe bağlanmayan kaynak olarak gösterme.
- Şema 18→19 geçişinde önce doğrulanabilir yedek, işlemsel NVD tablo/olay oluşturma, hata geri alma ve eski veriden CVE/CVSS uydurmama.
- 784 otomatik test 64,710 saniyede geçti; NVD ayrıştırma/taşıma, yaşam döngüsü, terminal, yedek/restore, migration ve önceki davranışlar birlikte doğrulandı.
- Ayrı geçici alandaki canlı NVD denemesinde Log4Shell kaydı; iki CVSS 3.1 değerlendirmesi, bir CVSS 2.0 değerlendirmesi, dört CWE ve 103 referansla alındı. Çevrimdışı görünümler veritabanı özetini değiştirmedi.

## 0.36.0 — 29 Ekim 2026

- `vuln sync --source epss`: FIRST'ün sabit günlük HTTPS/gzip kataloğundan anahtarsız ve ücretsiz EPSS alma.
- Model sürümü, puan tarihi, CVE, 30 günlük olasılık ve yüzdelik dilimini katı tam-dosya doğrulamasıyla saklama; bilimsel sayı gösterimini güvenli ondalığa normalleştirme.
- Yalnız aynı resmî sunucuya HTTPS yönlendirmesi; 30 saniye, 16 MiB sıkıştırılmış, 64 MiB açılmış ve 1.000.000 kayıt sınırı.
- Kaynak hatasını boş katalogdan ayırma; başarısız çalışmayı kaydederken önceki geçerli puanları koruma.
- Güncel puanları atomik yenileme; yeni, değişen, aynı kalan, katalogdan çıkan ve geri giren kayıt sayılarını gösterme.
- `vuln status/list/show --source epss`: internete bağlanmadan kaynak durumu, yüksek puanlar ve tek CVE ayrıntısı; okumada veritabanını değiştirmeme.
- EPSS'yi önem, etki, tam risk veya varlık maruziyeti saymama; KEV ve EPSS anlamlarını ayrı tutma.
- Kişisel disk kullanımını sınırlamak için her CVE'nin günlük puan kopyalarını biriktirmeme; güncel katalog ve kaynak çalışma geçmişini tutma.
- Kaynak kataloğunda FIRST EPSS bağlantısını ücretsiz, anahtarsız ve izlenen hedefe bağlanmayan kaynak olarak gösterme.
- Şema 17→18 geçişinde önce doğrulanabilir yedek, işlemsel tablo oluşturma, hata geri alma ve eski veriden EPSS puanı uydurmama.
- 772 otomatik test 60,093 saniyede geçti; EPSS taşıma/ayrıştırma, yaşam döngüsü, terminal, kilit, yedek/restore, migration ve önceki davranışlar birlikte doğrulandı.
- Ayrı geçici alandaki canlı FIRST denemesinde 29 Ekim 2026 tarihli 397.508 kayıt 5,30 saniyede alındı; 128 MiB veritabanındaki çevrimdışı görünümler dosya özetini değiştirmedi.

## 0.35.0 — 29 Ekim 2026

- `vuln sync --source kev`: CISA'nın sabit resmî HTTPS JSON akışından Known Exploited Vulnerabilities kataloğunu açık komutla indirme.
- 16 MiB/10.000 kayıt sınırı; yönlendirme, sıkıştırma, beklenmeyen içerik türü, yinelenen anahtar/CVE, bozuk tarih ve tutarsız toplamı tüm katalog için güvenli reddetme.
- Yeni, değişen, katalogdan çıkan ve yeniden eklenen CVE kayıtları için atomik anlık görüntü ve eklemeli olay geçmişi.
- Kaynak başarısızlığını boş katalogdan ayırma; başarısız çalışmayı kaydederken önceki geçerli kataloğu koruma.
- `vuln status/list/show`: internete bağlanmadan kaynak durumu, etkin/geçmiş KEV kayıtları ve değişiklik geçmişi.
- KEV bilgisini varlık maruziyeti saymama; otomatik ürün/sürüm veya CVE eşleştirmesi yapmama.
- Kaynak kataloğunda CISA KEV bağlantısı; anahtarsız, ücretsiz ve izlenen hedefe bağlanmayan kaynak olarak açık gösterim.
- Şema 16→17 geçişinde önce doğrulanabilir yedek, işlemsel tablo oluşturma, hata geri alma ve eski veriden zafiyet uydurmama.
- 760 otomatik test 58,143 saniyede geçti; KEV ayrıştırma/taşıma, katalog yaşam döngüsü, terminal, kilit, yedek/restore, migration ve önceki davranışlar birlikte doğrulandı.
- Ayrı geçici alandaki canlı CISA denemesinde 2026.10.28 tarihli 1.762 kayıt başarıyla alındı; çevrimdış görünümler veritabanını değiştirmedi.

## 0.34.0 — 29 Ekim 2026

- `surface technologies DOMAIN`: son kayıtlı sınırlı TCP servis kanıtından salt-okunur teknoloji kullanım ipuçları.
- Yalnız açık portları gösterme; kapalı veya belirsiz porttan teknoloji yokluğu sonucu çıkarmama.
- Her ipucunda kanıt kimliği/zamanı/güncelliği, uç nokta, yaygın kullanım ipucu, `confidence=hint` ve `detection_method=tcp_connect_only`.
- Üretici, ürün ve sürümü kanıt yokken açıkça `null` tutma; port numarasını ürün veya sürüm gibi sunmama.
- Bütün port ipuçlarında `cve_match_eligible=false`; doğrulanmış ürün ve sürüm olmadan CVE maruziyeti üretmeme.
- Kontrol edilmemiş, başarısız, kısmi, eski ve zamanı tutarsız servis kanıtını ayrı gösterme.
- Ağ, banner/protokol konuşması, oturum, zafiyet taraması, veri yazma, yeni tablo veya migration yok; şema 16 değişmedi.
- 748 otomatik test 63,656 saniyede geçti; teknoloji sınırı, salt okuma, terminal/JSON ve önceki bütün davranışlar birlikte doğrulandı.

## 0.33.0 — 29 Ekim 2026

- `surface cname check/show DOMAIN`: yalnız kayıtlı ve etkin kapsamlı tam adres için Google Public DNS üzerinden sınırlı CNAME zinciri ve terminal hedef A/AAAA kanıtı.
- En fazla sekiz ilişkili CNAME adımı ve 16 hedef IP; ilgisiz/çelişen/döngülü/kesilmiş/beklenmeyen kayıtları güvenli reddetme.
- `present/absent/nxdomain/failed` takma ad ve `resolved/no_address/nxdomain/failed/not_applicable` hedef durumlarını birbirine karıştırmama.
- Hedef NXDOMAIN olduğunda yalnız kesin olmayan `dangling_cname_target_nxdomain` adayı; alınabilirlik, sağlayıcı hesabı veya gerçek takeover iddiası yok.
- Hedef site bağlantısı, HTTP, banner, kaynak sahiplenme, hesap açma, oturum deneme, exploit veya otomatik DNS düzeltmesi yok.
- Eklemeli CNAME geçmişi, durum özeti ve değişim alanları; salt-okunur geçmiş/maruziyet görünümü; backup/restore desteği.
- Şema 15→16 geçişinde önce doğrulanabilir yedek, boş CNAME geçmişi, işlemsel DDL ve hata geri alma; eski veriden CNAME kanıtı uydurmama.
- 744 otomatik test 54,091 saniyede geçti; DNS ayrıştırma, kapsam/kilit, negatif adaylar, geçmiş, yedek/restore, migration ve önceki bütün davranışlar birlikte doğrulandı.

## 0.32.0 — 29 Ekim 2026

- `surface exposures DOMAIN`: son kayıtlı web, posta ve servis kanıtından açıklanabilir, salt-okunur maruziyet adayları çıkarma.
- TLS bağlantı/doğrulama sorunu; MX kullanan domainde eksik/çoğul SPF-DMARC; seçili açık uzak erişim ve alternatif web portları için dar kural kümesi.
- Her adayda kanıt seviyesi, kimliği, zamanı/güncelliği, doğrudan olgular, iddia sınırları ve önerilen insan adımı.
- Null MX için yanlış eksik politika adayı üretmeme; eski ve zamanı tutarsız kanıtı güncel göstermeme; kısmi/başarısız/alınmamış kapsamı ayrı tutma.
- İçerik/banner yokken açık paneli, CNAME/delegasyon/sağlayıcı yanıtı yokken takeover'ı `unsupported` gösterme; veri yokluğunu güvenli sonuç saymama.
- Ağ, yazma, sahiplenme, exploit, otomatik düzeltme, yeni tablo, migration, ücretli servis ve Python paketi yok; şema 15 değişmedi.
- 735 otomatik test 54,715 saniyede geçti; aday/negatif örnekler, kanıt yaşı, kapsam boşlukları, salt okuma ve önceki bütün davranışlar birlikte doğrulandı.

## 0.31.0 — 29 Ekim 2026

- `storage readiness`: disk, kayıt klasörü, veritabanı, yönetilen yedek, saklama ve yerel kurtarma hazırlığını tek salt-okunur görünümde birleştirme.
- En az 64 MiB veya SQLite mantıksal boyutunun iki katı ihtiyatlı boş alan eşiği; toplam ve kullanılabilir disk kapasitesi.
- `backups/*.db` yedek envanteri; en yeni yönetilen yedeğin XTI şeması, quick check, yabancı anahtar bütünlüğü ve yaş doğrulaması.
- Bozuk yeni yedek yerine eski dosyayı sessizce sağlıklı saymama; ayrı ortam kopyası ve restore tatbikatını kanıt yokken bilinmiyor/kaydedilmedi tutma.
- Seçilebilir 7–3650 günlük saklama önizlemesi; bağlantısız uygun, bağlı korunan ve zamanı sorunlu gözlemleri yazmadan açıklama.
- Sembolik bağlantı izlemeyen 10.000 dosya/1.000 yedek sınırı; ağ, yazma, silme, yedek alma veya restore yok. Yeni tablo, migration, ücretli servis ve Python paketi yok; şema 15 değişmedi.
- 729 otomatik test 54,529 saniyede geçti; eksik/geçerli/eski/bozuk yedek, disk politikası, saklama önizlemesi, sembolik bağlantı güvenliği, salt okuma ve önceki bütün davranışlar birlikte doğrulandı.

## 0.30.0 — 29 Ekim 2026

- `surface discovery-status DOMAIN`: son pasif keşfin kaynak durumunu veri sonucundan ve güncellikten ayrı gösterme.
- Tamamlanmış bulunan/boş, kısmi bulunan/boş, başarısız ve hiç çalışma yok sonuçları; yalnız `complete+0` için doğrulanmış kaynak-boşluğu.
- Kısmi veya başarısız sıfır sonucu “aday yok” saymama; kısmi bulunan adayları korurken olası eksik kapsamı görünür tutma.
- Varsayılan 24 saat, 1–8760 saat arası rapor eşiği; eski ve zaman bilgisi tutarsız çalışmayı veri sonucundan ayrı sınıflandırma.
- Son çalışma uyarı, hata, kimlik ve sayaçlarını güvenli terminal/JSON çıktısında açıklama; yalnız kayıtlı geçmişi okuma, ağ veya yazma yok.
- Mevcut keşif deposu portunu yeniden kullanma; yeni tablo, migration, ücretli servis veya Python paketi yok. Şema 15 değişmedi.
- 723 otomatik test 54,601 saniyede geçti; tamamlanmış/kısmi/başarısız/hiç çalışma yok ayrımı, güncellik, salt okuma ve önceki bütün davranışlar birlikte doğrulandı.

## 0.29.0 — 29 Ekim 2026

- `surface inventory DOMAIN`: pasif aday kararı, ayrı varlık kaydı ve aktif kontrol kapsamını tek salt-okunur görünümde ayırma.
- `pending/owned/rejected`, `registered/unregistered` ve `active/revoked/not_approved/not_applicable` durumlarını birbirine dönüştürmeden terminal ve JSON'da açıklama.
- `owned` kararının varlık kaydı veya bağlantı yetkisi olmadığını; kayıtlı varlığın da ayrıca gerekçeli kapsam onayı gerektirdiğini görünür tutma.
- Filtrelenmiş aday sayfasının yanında kökün bütün aday durum, kayıtlı varlık ve aktif kapsam toplamlarını tek SQLite okuma anlık görüntüsünde verme.
- Yalnız öneri niteliğinde sonraki güvenli adım; ağ isteği, karar, kayıt, kapsam açma, onarım veya yazma yok.
- Küçük domain modeli, uygulama portu, SQLite adaptörü ve terminal sunumu; yeni tablo, migration, ücretli servis veya Python paketi yok. Şema 15 değişmedi.
- 717 otomatik test 51,507 saniyede geçti; katman bağımsızlığı, filtre/sayaçlar, salt okuma, ağsız terminal akışı ve önceki bütün davranışlar birlikte doğrulandı.

## 0.28.0 — 29 Ekim 2026

- `surface freshness DOMAIN`: kayıtlı web, posta ve servis kanıtını tek salt-okunur güncellik görünümünde birleştirme.
- Varsayılan 24 saat, 1–8760 saat arası seçilebilir eşik; `current/stale/never/clock_error` durumları ve tam saniye yaşı.
- Kanıt yaşını `complete/partial/failed/not_checked` sonuç kalitesinden ayırma; güncel kısmi sonucu tam kanıt gibi göstermeme.
- Etkin/kaldırılmış/onaysız kapsamı; son kanıt kimliği, zamanı ve değişim türünü terminal/JSON çıktısında açıklama.
- Yalnız kapsam ve son üç kanıtı tek SQLite anlık görüntüsünde okuyan küçük depo portu; aday/ilişki yükleme, ağ isteği, yazma veya onarım yok.
- Gelecekteki ya da okunamayan zamanı güvenli hata durumunda gösterme; yeni tablo, migration, ücretli servis veya Python paketi eklememe. Şema 15 değişmedi.
- 712 otomatik test 52,533 saniyede geçti; yaş eşiği, sonuç kalitesi ayrımı, zaman hatası, salt okuma ve önceki bütün davranışlar birlikte doğrulandı.

## 0.27.0 — 29 Ekim 2026

- `surface monitor DOMAIN`: seçili web DNS/TLS/HTTPS, posta MX/SPF/DMARC ve isteğe bağlı kesin IP TCP servis kontrollerini terminal açıkken tekrarlama.
- Varsayılan `web mail`; servis seçilirse kesin genel IP ve görünür yetki gerekçesi zorunlu. Mevcut etkin kapsam, DNS eşleşmesi ve sabit 10 port sınırını aynen koruma.
- 1–1000 tur, 300–86400 saniye aralık ve 1–604800 saniye yeni-kontrol başlatma süresi; varsayılan 3/3600/86400.
- Her tamamlanan kontrolü mevcut eklemeli kanıt yoluna yazma; gerçek değişikliği ortak `inbox` kutusuna atomik ekleme, temel/değişmeyen kayıtta alarm üretmeme.
- Final insan/JSON özetinde tam tur, kontrol durumları, kanıt kimlikleri, değişiklik ve bildirim sayısı; yarım turu başarılı saymama.
- `Ctrl+C`, süre sonu veya süreç kapanışından önce tamamlanan kanıtları koruma; bilgisayar kapalıyken çalışma veya otomatik devam yok.
- Küçük çalıştırıcı sözleşmesiyle kontrol ailelerini orkestrasyondan ayırma; yeni tablo, migration, ücretli servis, API anahtarı veya Python paketi eklememe. Şema 15 değişmedi.
- Kaynak kataloğunda `surface monitor` tarafından kullanılan Google Public DNS, açık HTTPS HEAD ve isteğe bağlı TCP bağlantı yollarını görünür yapma.
- 707 otomatik test 51,081 saniyede geçti; zaman/tur sınırları, kesinti, yetki/kilit kapıları, üçlü değişiklik bildirimi ve önceki bütün davranışlar birlikte doğrulandı.

## 0.26.0 — 29 Ekim 2026

- DNS/TLS/HTTPS, MX/SPF/DMARC ve sınırlı TCP servis kanıtlarında yalnız gerçek `changed` sonucu için ortak yerel `inbox` bildirimi.
- İlk temel kayıtta ve değişmeyen tekrarda alarm üretmeme; servis port geçişini, eklenen/kaldırılan IP'yi ve değişen kanıt alanlarını bildirim ayrıntısında açıklama.
- Değişiklik kanıtı ile bildirimi aynı transaction içinde yazma; bildirim hatasında kanıtı da geri alma ve her kanıt için tek bildirim.
- Phishing bulgusu, pasif alt alan adı adayı ve dış yüzey değişikliklerini ortak artan sırada listeleme; hepsinde aynı atomik `read/unread` davranışı.
- `surface check`, `surface mail check` ve `surface services check` JSON sonucunda `notification_created`; insan çıktısında yerel kutu yönlendirmesi.
- Şema 14'ü doğrulanmış yedekten sonra boş değişiklik bildirimi geçmişiyle şema 15'e taşıma; eski kanıtlardan geriye dönük alarm uydurmama.
- E-posta/SMS/masaüstü teslimi, arka plan zamanlaması veya kaynak kesintisi alarmı yok; bildirimler yalnız açık kontrol komutlarının sakladığı değişikliklere dayanır.
- 695 otomatik test 49,758 saniyede geçti; üç değişiklik ailesi, atomiklik, bozuk kanıtta güvenli duruş, yedek/restore, terminal ve migration dahil önceki davranışlar birlikte doğrulandı.

## 0.25.0 — 29 Ekim 2026

- `surface services check DOMAIN --address IP --reason GEREKÇE`: yalnız etkin domain kapsamı ve ayrıca açıkça onaylanan kesin genel IP için sınırlı TCP servis envanteri.
- Onaylanan IP güncel A/AAAA cevabında yoksa, herhangi bir özel/yerel adres görülürse veya domain kapsamı etkin değilse hedef portlarına sıfır bağlantı.
- Yalnız `22, 25, 53, 80, 443, 587, 993, 3389, 8080, 8443/tcp`; tek IP, port başına bir saniye ve toplam 20 saniye sınırı; serbest port aralığı yok.
- Yalnız TCP bağlantı kanıtı; banner, uygulama verisi, ürün/sürüm tahmini, parola denemesi, exploit, nmap veya masscan yok.
- Açık/kapalı/belirsiz durumlarını ayırma; belirsizi kapalı saymama ve port etiketiyle doğrulanmış servis/zafiyet hükmünü ayırma.
- `surface services show` ile eklemeli temel/değişiklik geçmişini internetsiz gösterme; yazma anında domain kapsamını yeniden doğrulama.
- Açık TCP kanıtlarını `surface overview` içinde kaynak kayıt kimliği ve zamanıyla ilişkilendirme; `sources` kataloğunda aktif hedef trafiğini açıkça belirtme.
- Şema 13'ü doğrulanmış yedekten sonra boş servis geçmişiyle şema 14'e taşıma; kontrollü hatada tam geri alma ve eski kanıtlardan servis sonucu uydurmama.
- Ücretli servis, API anahtarı veya yeni Python paketi yok.
- 687 otomatik test 67,297 saniyede geçti; servis güvenlik sınırları, şema geçişi ve önceki bütün davranışlar birlikte doğrulandı.

## 0.24.0 — 29 Ekim 2026

- `surface overview KÖK`: kök domain, pasif alt alan adı adayları, son DNS/IP/TLS sertifikası ve MX kanıtını tek terminal/JSON görünümünde birleştirme.
- Aday, IP, sertifika ad kapsamı ve posta sunucusu ilişkilerinin kaynak kanıt türü, kimliği ve gözlem zamanıyla açıklanması.
- Aktif kapsam, son pasif keşif ve aday durum toplamlarını aynı görünümde gösterme; aday örneğini varsayılan 20, en fazla 100 kayıtla sınırlama.
- Bütün bölümleri tek salt okunur SQLite transaction anlık görüntüsünden alma; ağ isteği, gizli tarama, onarım veya veritabanı yazısı yapmama.
- Yeni grafik veritabanı, ilişki tablosu, ücretli servis, API anahtarı veya Python paketi eklememe; mevcut eklemeli kanıtları kaynak gerçek olarak koruma.
- Bozuk son kanıtta yanıltıcı kısmi özet üretmeden güvenli hata; ilişkiyi sahiplik, risk veya güvenlik hükmü saymama.
- Şema 13 değişmedi; 0.22.0 ve 0.23.0 kayıtları migration gerektirmeden kullanılabilir.
- 670 otomatik test 49,125 saniyede geçti; tek anlık görüntü, sınırlı örnek, kanıt ilişkileri, boş görünüm, bozuk kanıtta güvenli duruş ve CLI ağ/yazma yan etkisizliği dahil bütün önceki davranışlar doğrulandı.

## 0.23.0 — 29 Ekim 2026

- `sources` çıktısına crt.sh, urlscan, Google Public DNS ve açık komutla HTTPS HEAD kontrolünü ayrı açıklayan kaynak kataloğu.
- Her bağlantı için amaç, erişim biçimi, ücretli anahtar bağımlılığı, hedefe doğrudan trafik durumu, kullanan komutlar, sınırlar ve resmî başvuru adresi.
- Kaynak kataloğu ile son kaydedilen çalışma sağlığını ayırma; komutun ağ isteği veya veritabanı değişikliği yapmamasını koruma.
- HackerTarget, Common Crawl, Cert Spotter ve Subfinder için erişim, kullanım koşulu, veri bağımsızlığı ve güvenilirlik değerlendirmesi; uygun olmayan kaynağı çekirdeğe eklememe kararı.
- Yeni ücretli servis, API anahtarı, üçüncü taraf kodu veya Python paketi yok; şema 13 değişmedi.
- 665 otomatik test; katalog bütünlüğü, ücretli bağımlılık yokluğu, pasif/aktif hedef trafik ayrımı ve `sources` komutunun ağ/veritabanı yan etkisizliği dahil bütün önceki davranışlar doğrulandı.

## 0.22.0 — 29 Ekim 2026

- `surface mail check KÖK`: yalnız açıkça onaylanmış kök için Google Public DNS üzerinden MX, kök SPF ve `_dmarc` DMARC kayıtlarını sınırlı biçimde sorgulama.
- `surface mail show KÖK`: kaydedilmiş ilk temel/değişiklik yok/değişiklik var geçmişini internete çıkmadan gösterme.
- MX/SPF/DMARC sorgularını birbirinden ayırma; tek sorgu başarısız olduğunda diğer iki kanıtı koruyup sonucu kısmi ve çıkış kodu 3 yapma.
- SPF/DMARC dışındaki TXT kayıtlarını politika kanıtına katmama; birden fazla politika kaydını hüküm vermeden görünür tutma.
- DKIM seçicisi tahmin etmeme; güvenlik, teslimat, sahiplik veya yanlış yapılandırma kararı üretmeme.
- Ağdan önce etkin kapsam doğrulaması, ortak yerel çalıştırıcı kilidi ve kayıt transaction'ında kapsamın yeniden denetlenmesi.
- Her sonucu eklemeli, özet doğrulamalı kanıt olarak saklama; bozuk geçmişte güvenli hata ve yedek/restore koruması.
- Şema 12'yi önce doğrulanmış yedeğe alıp eski bütün kayıtları koruyarak boş e-posta DNS geçmişiyle şema 13'e yükseltme; hatada tam geri alma.
- Ek ücretli API veya Python paketi yok; açık kullanıcı komutu dışında otomatik/ağ etkinliği yok.
- 661 otomatik test; katı DNS yanıtı, sorgu sınırı, kısmi hata, değişim, kapsam yarışı, CLI, migration rollback ve yedek/restore sahte ağ/geçici verilerle doğrulandı.

## 0.21.0 — 29 Ekim 2026

- `surface watch KÖK`: pasif crt.sh alt alan adı keşfini terminal açıkken tur, aralık ve toplam yeni-tur başlatma sınırlarıyla tekrarlama.
- Varsayılan 3 tur/3600 saniye aralık/86400 saniye süre; 1–1000 tur, 300–86400 saniye aralık ve 1–604800 saniye süre doğrulaması.
- Her tamamlanan turu mevcut `surface_discovery_runs` geçmişine ayrı yazma; yeni oturum tablosu veya yinelenen aday/bildirim üretmeme.
- Başarısız veya kısmi kaynak turundan sonra bütçe kaldığı sürece sonraki tura devam etme; sonuçları tek final insan/JSON özetinde ayırma.
- `Ctrl+C` ve süreç kapanışında daha önce tamamlanan tur/aday/kanıt/bildirimleri koruma; sonraki çalıştırmada geçmişi `surface runs` ile açabilme.
- Bütün izleme boyunca mevcut yerel çalıştırıcı kilidini kullanma; bulunan adaylara DNS/TLS/HTTPS bağlantısı, otomatik sahiplik veya aktif kapsam kararı vermeme.
- Şema 12 değişmedi; 0.20.0 verileri migration gerektirmeden kullanılabilir.
- 641 otomatik test; çok tur, süre, kaynak hatası, `Ctrl+C`, tekrar güvenliği ve aktif probe ayrımı sahte ağ/geçici verilerle doğrulandı.

## 0.20.0 — 29 Ekim 2026

- Pasif sertifika keşfinde ilk kez bulunan her alt alan adı adayı için mevcut yerel bildirim kutusuna tek bildirim; aynı aday tekrar görüldüğünde bildirim çoğalmaz.
- Bulgu ve alt alan adı bildirimlerini tek, kararlı sırada gösteren; açık `read/unread` işlemini iki kayıt türünde de koruyan birleşik terminal kutusu.
- Her `surface discover` çalışması için tamamlandı/kısmi/başarısız sonucu, kaynak kapsamı, sayaçlar, uyarı veya hata ve zamanları saklayan kalıcı geçmiş.
- `surface runs KÖK` ve `surface run KİMLİK` salt okunur geçmiş komutları; başarısız kaynak çağrıları boş başarı gibi gösterilmez.
- Aday, kaynak kanıtı, tek bildirim ve başarılı çalışma özeti aynı işlemde kaydedilir; geç hata hepsini geri alır.
- Şema 11'i önce yedekleyip eski bütün kayıtları koruyan şema 12 geçişi; eski adaylardan geriye dönük bildirim veya keşif çalışması uydurulmaz.
- 634 otomatik test; sahte ağ yanıtları ve geçici veritabanlarıyla doğrulandı.

## 0.19.0 — 29 Ekim 2026

- `surface discover`: kayıtlı kökün kesin alt alan adlarını crt.sh Certificate Transparency kayıtlarında pasif arama; bulunan hedeflere bağlantı yok.
- `surface candidates` ve `surface candidate show`: kaynak URL'si/özeti, ham ad, CT zamanı, ilk/son görülme ve kanıt sayısıyla salt okunur envanter.
- `surface candidate decide`: onay bekliyor, bana ait ve reddedildi durumları; gerekçeli, silinmeyen ve tekrar güvenli karar geçmişi.
- Kök adresi, aynı sertifikadaki ilgisiz adları ve joker kökün kendisini dışarıda bırakma; tekrar sertifikayı tekilleştirip yeni kanıtı mevcut adaya ekleme.
- Sahiplik sınıflandırmasını varlık kaydı ve aktif DNS/TLS kapsamından ayırma; kullanıcı onayı olmadan hedef bağlantısı, otomatik varlık veya kapsam yok.
- Kaynak ve işlem sınırları, bozuk/çelişkili kanıtta atomik geri alma, salt okunur liste/ayrıntı, yedek/restore ve kaynak hatası testleri.
- Şema 10'dan önce kurtarma yedeği alan işlemsel şema 11 geçişi; önceki bütün dış yüzey kanıtları korunur ve pasif aday tabloları boş başlar.

## 0.18.0 — 29 Ekim 2026

- Zaten doğrulanmış TLS oturumundan sertifika SHA-256 parmak izi, seri numarası, subject, issuer, geçerlilik başlangıç/bitişi ve DNS ad kapsamını alma.
- Sertifika DER boyutu, taraf alanları, zamanlar, seri numarası ve en fazla 128 kanonik DNS adı için katı sınır/doğrulama; bozuk kanıtta HTTP isteğine geçmeden güvenli hata.
- `https-head-public-v2` kontrol politikası; ek ağ bağlantısı, doğrulamasız TLS veya sertifika indirme yolu yok.
- Dış yüzey durum hash'ine doğrulanmış sertifika kimliğini katma; aynı sertifikada değişiklik yok, yenilenme/değişimde açıklanabilir `TLS sertifikası` farkı.
- `surface check/show` çıktısında issuer, subject, tarih, DNS kapsamı, parmak izi ve bitişe 30 gün veya az kaldığında uyarı.
- Eski sertifikasız hedef/dış yüzey kanıtlarını ve v0.17 durum hash'lerini değiştirmeden okuma.
- Şema 10 değişmedi; 0.17.0 kayıtları migration gerektirmez.

## 0.17.0 — 29 Ekim 2026

- `surface approve/check/list/show/revoke`: kayıtlı ve kullanıcı tarafından yetkili olduğu beyan edilen domainler için ilk dış saldırı yüzeyi akışı.
- Kapsam gerekçesi ile onay/güncelleme/kaldırma/yeniden etkinleştirme işlemlerini silinmeyen geçmişte tutma.
- Yalnız etkin kapsamdaki tam kayıtlı domaine; Google Public DNS A/AAAA ve doğrulanmış TLS üzerinden sınırlı HTTPS HEAD kontrolü.
- Özel/yerel IP, yönlendirme, sayfa gövdesi, başka port, alt domain genişletmesi ve doğrulamasız TLS bağlantısını reddeden mevcut ağ güvenlik sınırlarını yeniden kullanma.
- Her kontrolü ayrı kanıt olarak saklama; ilk temel, değişiklik yok ve DNS/IP/TLS/HTTPS değişimini deterministik biçimde ayırma.
- Kontrol sırasında kapsam geri çekilirse sonucu kaydetmeden durma; bozuk geçmişte salt okunur güvenli hata.
- Şema 9'dan önce kurtarma yedeği alan işlemsel şema 10 geçişi; eski bütün kayıtlar korunur ve yeni dış yüzey tabloları boş başlar.

## 0.16.0 — 29 Ekim 2026

- `allowlist add` ve `allowlist add-finding` için isteğe bağlı `--expires-in-days 1..3650`; seçenek yoksa önceki kalıcı davranış.
- Kesin UTC bitiş anında kendiliğinden etkisizleşen, okuma veya zamanlayıcı yazısı gerektirmeyen süreli istisna.
- Süre güncelleme, süresi dolan kaydı aynı kimlikle yeniden etkinleştirme ve bitiş zamanını içeren eklemeli işlem geçmişi.
- Süre boyunca ham gözlemi koruma; bitişten sonraki yeniden işleme veya yeni kaynak kaydında bulgu/bildirim üretimini yeniden açma.
- Uygulama filtresine ek olarak bulgu transaction'ında süreyi tekrar denetleyen depolama savunması; bozuk tarihte kısmi kanıt yazmadan güvenli hata.
- Şema 8'den önce kurtarma yedeği alan işlemsel şema 9 geçişi; eski kalıcı istisnalar kalıcı ve bütün kimlik/geçmiş sırası korunur.

## 0.15.0 — 29 Ekim 2026

- `feedback`: kullanıcı inceleme kararlarını internetsiz ve salt okunur toplu özetleme.
- Toplam/incelenen/bekleyen adaylar, inceleme kapsamı, son kararlar ve yeniden incelenen bulgu sayısı.
- Son kararları bulgu kural sürümüne göre ayırma; eski ve yeni eşleştirme davranışını karıştırmama.
- İnsan ve JSON çıktısında yalnız toplu sayı/kural kimliği; domain, bulgu kimliği ve karar gerekçesini dışarı vermeme.
- Kullanıcı kararını doğrulanmış tehdit veya yanlış pozitif etiketi saymayan açık yorum sınırları.
- Bulgu durumu ile son eklemeli karar geçmişi uyuşmazsa güvenli hata; okuma sırasında onarım veya yazma yok.
- Şema 8 değişmedi; 0.12.0–0.14.0 kayıtları migration gerektirmez.

## 0.14.0 — 29 Ekim 2026

- Yan yana harf değişimi ardından bilinen hizmet eki ve uzun markaya bitişik `shop` için iki dar aday kuralı.
- Bilinmeyen ekleri, kısa sözcük içindeki `shop` parçasını ve daha uzun rastgele sözcükleri dışarıda tutan negatif korumalar.
- Değişmeyen ASCII bulgularında `domain-rules-v1`, yalnız yeni desenlerde `domain-rules-v2`, IDN bulgularında `idn-confusables-v1` kimliği.
- Yeni işlerde `domain-rules-v3` yürütme sözleşmesi; eski sıradaki işi farklı kuralla sessizce çalıştırmama.
- 47 örnekli `domain-evaluation-v2`: 27 doğru yakalama, 17 doğru eleme, 3 bağlamsal gereksiz alarm ve 0 kaçırma.
- Tam adres istisnasının yeni desenleri de atomik bastırması; ham gözlemin korunması ve eski bulgu/bildirimlerin çoğalmaması.
- Şema 8 değişmedi; 0.12.0–0.13.0 kayıtları migration gerektirmez.

## 0.13.0 — 29 Ekim 2026

- `evaluate`: veritabanı ve ağ kullanmadan sürümlü sentetik eşleştirme ölçümü.
- 44 review/ignore örneği; Unicode, public/private suffix, typo, hizmet eki ve meşru bağlam kapsamı.
- Doğru yakalama/eleme, kaçırma, gereksiz alarm, precision, recall ve yanlış alarm oranı.
- Bilinen kalite açıklarını örnek kimliğiyle gösterme; başlangıç davranışından değişimi ayrı raporlama.
- Sabit SHA-256 ve katı veri sözleşmesi; bozulmada kısmi sonuç veya traceback yerine kontrollü hata.
- İnsan ve JSON çıktısı; sentetik etiketlerin tehdit kararı veya gerçek internet doğruluğu olmadığını belirtme.
- Şema 8 değişmedi; 0.12.0 kayıtları migration gerektirmez.

## 0.12.0 — 29 Ekim 2026

- `allowlist add/add-finding/list/show/revoke`: izlenen varlığa bağlı tam aday adresi istisnası.
- Joker, ilgisiz veya geniş kapsamlı istisnaları reddeden mevcut eşleştirme doğrulaması.
- Zorunlu gerekçe ve silinmeyen ekleme/kaldırma/yeniden etkinleştirme işlem geçmişi.
- Ham gözlemi korurken yeni bulgu, kanıt bağlantısı ve bildirimi atomik olarak bastırma.
- Eski bulgu, kanıt, karar ve bildirimi değiştirmeme; geri alma sonrası yeniden işleme.
- Unicode U-label/Punycode istisnalarının kanonik A-label kimliğinde tekilleştirilmesi.
- Şema 1–7'den önce yedekli şema 8 geçişi; rollback ve yedek/restore doğrulaması.
- Tam adres istisnası kullanıcı doğrulamasıdır; zararsızlık veya sahiplik kanıtı değildir.

## 0.11.0 — 29 Ekim 2026

- Paketlenmiş Unicode 18.0 UTS #39/UTS #46 profiliyle kanonik U-label/A-label işleme.
- Unicode benzer-harf adayları için ayrı, sürümlü kural kimliği ve açıklanabilir neden.
- Public Suffix List içindeki Unicode kurallarının aynı profile göre değerlendirilmesi.
- `--typos` altında marka başına en fazla dört gerçek Punycode arama varyantı.
- ASCII bulgu/karar/bildirim kimliklerinin korunması; şema 7'nin değişmemesi.
- Sağdan sola/ContextJ kapsamı ve gerçek dünya doğruluk ölçümü bu sürüme eklenmedi.

## 0.10.0 — 29 Ekim 2026

- `monitor start`: tur ve süre sınırı, kaynak seçimi ve kalıcı izleme grubu.
- Kaynak başına çalışma/sorgu/sonucu bilinen yeni bulgu sayıları; eksik sonucun görünür ayrımı.
- `monitor list/show/recover`: kayıtlı ölçümü açma ve kapanmış süreci güvenle kapatma.
- Bütün denemede tek yerel çalıştırıcı; izleme işlerinin normal worker ve ayrı retry'dan korunması.
- İş/oturum bağlantısının atomik kaydı; sabit ilk deneme üzerinden küçük sonuç özeti.
- Süre sınırında yeni kaynak işi başlatmama; başlamış aramanın kendi sınırlarıyla tamamlanması.
- Şema 1–6'dan yedekli şema 7 geçişi; bildirim ve inceleme geçmişinin korunması.
- Gerçek süreç öldürme ve kurtarma testleri; otomatik arka plan hizmeti eklenmedi.

## 0.9.0 — 29 Ekim 2026

- `status`: adres başına son arama, kaynak beklemesi, iş sayıları ve bildirimlerin ortak özeti.
- Son deneme ve son tamamlanan arama ayrı; başarısız/kısmi deneme önceki başarıyla gizlenmez.
- Varsayılan 24 saatlik, ayarlanabilir güncellik görünümü; okunamayan/gelecek zaman açıkça belirtilir.
- Tek adres filtresi ve sınırlı alfabetik liste; sayaçların global kapsamı görünür.
- Bütün özet tek okuma işleminden gelir; ağ, kurtarma, iş başlatma veya okundu değişikliği yapmaz.
- Büyük sonuç geçmişi yalnız seçilen denemelerde yüklenir; kayıt şeması 6 olarak kalır.
- Yeni bağımlılık, otomatik servis veya arama zamanlayıcısı eklenmedi.

## 0.8.0 — 29 Ekim 2026

- `inbox`: yeni bulgular için kalıcı yerel bildirim kutusu ve okunmamış sayacı.
- Bildirim yeni bulguyla aynı işlemde yazılır; kaynak tekrarları ve yeni kanıt bildirimi çoğaltmaz.
- Salt okunur liste/ayrıntı, sıralama sınırıyla sayfalama ve açık toplu okundu/okunmadı işlemleri.
- İnceleme kararı ile okundu durumu birbirinden bağımsız; yeniden arama önceki okundu zamanını korur.
- Şema 1–5'ten yedekli şema 6 geçişi; eski bulgular açık etiketle bildirim kutusuna alınır.
- Bildirim kimliği, sıra ve okundu bilgisi yedek/restore kapsamındadır.
- Ağsız, geçici verili, tekrarlanabilir 30 tur doğrulama betiği; gerçek süreç kapanma testinde okundu koruması.
- Dış bildirim teslimi veya otomatik tehdit kararı eklenmedi.

## 0.7.0 — 28 Ekim 2026

- Kaynak beklemeleri ve asgari istek aralığı aynı kayıt alanında yeniden başlatma sonrası korunur.
- Bekleme başlıkları yanıt okunmadan/tekrar beklenmeden kaydedilir; kayıt hatasında istek gönderilmez.
- `sources` kayıtlı beklemeyi, kalan süreyi ve en erken istek zamanını gösterir.
- `storage status` dosya, SQLite içinde yeniden kullanılabilir alan ve gözlem sayılarını gösterir.
- `storage cleanup` eski bağlantısız gözlemleri yalnız önizler; `--apply TOKEN` seçimi tekrar doğrular.
- Temizlik öncesi otomatik yedek, sınırlı ve atomik silme, korunmuş bulgu kanıtları ve `storage history`.
- Şema 1/2/3/4'ten yedekli şema 5 geçişi; yeni kayıtlar yedek/restore kapsamındadır.
- Otomatik arka plan temizliği veya veritabanı dosyası küçültme eklenmedi.

## 0.6.0 — 28 Ekim 2026

- `scan/watch --check`: internetten aday bulma ve sınırlı güncel DNS/HTTPS kontrolü aynı akışta.
- `findings check`: tek bulguyu yeniden kontrol etme veya bekleyen açık adayları toplu işleme.
- Hedefe yalnız doğrulanmış genel IP üzerinden HTTPS HEAD; özel IP, yönlendirme ve doğrulamasız TLS engeli.
- Süre/başlık/DNS yanıt sınırları, aynı turda domain tekilleştirme ve altı saatlik tekrar aralığı.
- Kontrol geçmişi ayrı tutulur; kaynak gözlemleri ve kullanıcı kararları korunur.
- `triage`: zamanla güncellenen, gerekçeli inceleme sırası; tehdit kararı veya risk puanı üretmez.
- `report`: tek tutarlı kayıttan kaynak, karar ve kontrol geçmişli JSON raporu; mevcut dosya ezilmez.
- Şema 1/2/3'ten önceden yedekli şema 4 geçişi; hedef kontrolleri yedeklere dahil.

## 0.5.0 — 28 Ekim 2026

- İkinci bağımsız kaynak: urlscan'in mevcut, herkese açık web inceleme kayıtları.
- Varsayılan scan/watch iki kaynağı kullanır; `--source` ile tek kaynak seçilebilir.
- Kaynak başına ayrı iş ve hata geçmişi; worker/retry kayıtlı sağlayıcıya yönlendirilir.
- İki kaynaktan gelen gözlemler mevcut bulguya bağlanır, inceleme kararı korunur.
- urlscan kota/geçmiş sınırları ve eksik sonuçlar görünür; yeni tarama gönderilmez.
- Genel `record_count` ve `coverage_notes`; eski sertifika sayılı geçmiş değişmeden okunur.
- JSON: varsayılan çok kaynaklı sonuç `data.results`; tek kaynak seçimi tek sonuçtur.
- SQL şeması 3 olarak kalır. Eski uygulamaya dönüş için sürüm öncesi yedek gerekir.

## 0.4.0 — 28 Ekim 2026

- Arama istekleri ve ayrı denemeler için kalıcı kuyruk/geçmiş.
- Tamamlanan sorguların, hata nedenlerinin ve başlangıç/bitişin saklanması.
- İş listesi/ayrıntısı, yeniden deneme, yarım iş kurtarma ve son kaynak sonucu.
- `scan --queue` ve sıradaki tek işi çalıştıran `worker --once`.
- Yerel işlem kilidiyle eşzamanlı çalıştırmayı önleme; zorla kapanma sonrası güvenli kurtarma.
- Şema 1/2'den yedekli şema 3 geçişi; iş geçmişini kapsayan yedek/restore.
- Eski bulgular ve kararlar korunur; tekrar deneme aramayı baştan yapar ve kaynak kayıtlarını tekilleştirir.

## 0.3.0 — 28 Ekim 2026

- Tek komutla crt.sh üzerinden gerçek internet araması; adres listesi hazırlamak gerekmez.
- Terminal açıkken düzenli kontrol, sınırlı ek harf değişimi araması.
- HTTPS, boyut/zaman/istek sınırları, kaynak bekleme sürelerine uyma ve görünür hata durumları.
- Sertifika bağlantısı, asıl ad, kaynak zamanı ve sorgular arasında sabit gözlem kimliği.
- Kısmi sonuçları ve kaynak hatasını boş sonuçtan ayıran terminal/JSON çıktısı.
- Eski kararlar ve gözlemler korunur; veritabanı şeması 2 olarak kalır.
- Gerçek kaynak erişimi ile sahte kaynak kullanan otomatik testler ayrı doğrulanır.

## 0.2.0 — 28 Ekim 2026

- TXT/JSONL dosyasından sınırlı ve atomik gözlem alma.
- Çevrimdışı Public Suffix List ve açıklanabilir domain aday kuralları.
- Bulgu listesi, kaynak ayrıntıları, durum filtresi ve karar geçmişi.
- Dosya/satır ve bulgu tekrarlarını önleme; kararları koruyarak yeni kaynak ekleme.
- Şema 1→2 geçişi öncesinde otomatik kurtarma yedeği; hata halinde rollback.
- Bulguları ve kararları kapsayan backup/restore doğrulaması.
- 60 test; 36 sentetik eşleştirme örneği. Canlı kaynak ve doğrulanmış phishing kararı henüz yok.

## 0.1.0 — 28 Ekim 2026

- Python ve SQLite ile ayrılmış ilk yerel temel.
- Terminalden adres ekleme, listeleme ve kayıt kontrolü.
- Mevcut dosyayı koruyan yedekleme ve geri yükleme.
- Kalıcılık, girdi, yedek, terminal ve mimari davranış testleri.
- Kullanım, güncel durum ve mimari karar belgeleri.

Canlı tehdit toplama ve tespit bu sürüme dahil değildir.

