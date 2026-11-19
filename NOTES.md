# XTI — Unutulmaması gereken notlar

Son güncelleme: **19 Kasım 2026**. Başlangıç kaydı: **0.154.0 / şema 74**.
Güncel çalışma: **0.171.0 / çekirdek 81 / iş kuyruğu 3**.

Konuşmalarda geçen kullanım koşulları, maliyetler, bekleyen doğrulamalar ve
korunacak kararlar burada tutulur. İlk kayıtlar mevcut repo belgelerinden
ve önceki çalışmanın sonuçlarından derlendi; bu dosyaya aktarılmaları yeni
bir sağlayıcı incelemesi veya yeni test yapılmış olduğu anlamına gelmez.

Çalışan özelliklerin kaydı [STATUS](docs/STATUS.md), geliştirme sırası
[motor yol haritası](docs/roadmap/ENGINE_INTEGRATION_ROADMAP.md), ayrıntılı
bileşen bildirimleri [THIRD_PARTY](THIRD_PARTY.md) içindedir. Bu dosya,
o belgelerdeki önemli koşul ve takip maddelerinin ortak hatırlatma yeridir.

## Güncelleme düzeni

- İlgili çalışma başlarken bu dosya okunur. Yeni bilgi, değişen koşul,
  çözülen sorun veya kullanıcı kararı aynı çalışmada buraya işlenir.
- Kimlikler korunur. Her maddede durum, güncelleme tarihi, yapılacak iş
  ve dayanak bulunur. Eski bir not geçersizleşirse nedeni yazılır.
- Bir madde kanıtla tamamlanınca **Kapandı** bölümüne taşınır; silinmez.
  Kullanım boyunca korunacak yükümlülükler **Sürekli** olarak kalır.
- **Açık:** yapılacak iş var. **Beklemede:** belirtilen girdi/karar bekleniyor.
  **Bilinen sınır:** mevcut kapsamı anlatıyor; tek başına hata demek değil.
  **Sürekli:** her ilgili değişiklikte korunacak koşul.
- API anahtarı, parola, müşteri verisi veya ham test veritabanı buraya yazılmaz.

## Açık ve takip edilen notlar

### N-032 — Firecrawl değerlendirmesi ve birleşik sonuç doğruluğu

- **Durum:** Kullanıcı kararıyla ertelendi; kurulum/entegrasyon veya canlı
  Firecrawl testi yapılmadı. Öncelik mevcut kaynaklarla birleşik doğrulama.
  **Güncellendi:** 19 Kasım 2026.
- **Kullanıcı beklentisi:** Firma/domaininden yüksek doğrulukla birleşik
  sonuç üretmek; tek kaynağın kaçırdığı hesabı diğer yöntemlerle bulmak.
  Bilinen mevcut hesapları bulma, yanlış aday oranı ve erişilemeyen
  platform kapsamı ayrı ölçülmeden yüzdeye dayalı başarı iddiası yapılmaz.
- **Olası rol:** XTI'ın seçtiği açık web sayfalarından metin, metadata
  ve bağlantı alma; başka kaynakların adaylarını kontrol etme. Arama
  özelliği de var. Hesap keşfi, profil varlığı ve marka sahipliği kararları
  XTI'da kalmalı. İlk tercih temel açık sayfa alımı; gerektiren sayfalarda
  değiştirilebilir ek sağlayıcı olarak değerlendirme önerisidir.
- **Açık kaynak / bulut farkı:** Resmî v2.11.162 self-host rehberindeki
  temel stack scrape/crawl/map/search yollarını ve Fetch/Playwright
  işlemesini içeriyor. Fire-engine dahil değil; ekran görüntüsü ve sayfa
  aksiyonları varsayılan stack'te desteklenmiyor ve Fire-engine gerektiriyor.
  Agent/Browser/Interact ve diğer bulut yüzeyleri tam ücretsiz yerel
  eşdeğer sayılmaz. Temel sayfa alımı için LLM şart değil; LLM tabanlı
  çıkarım ayrı sağlayıcı yapılandırması istiyor.
- **Sosyal kaynak sınırı:** Desteklenmeyen siteler için `UNSUPPORTED_SITE`
  var. LinkedIn profil/şirket sayfaları doğrudan scrape yerine seçilmiş
  üçüncü taraf veri sağlayıcılarına yönlendiriliyor; kapsam, koşul ve
  ücret ayrı. SecureHup Instagram/X profillerinin Firecrawl ile
  bulunabildiği veya alınabildiği henüz doğrulanmadı. Genel web erişim
  oranı, sosyal hesap keşif doğruluğu değildir.
- **Maliyet:** 19 Kasım'da resmî fiyat sayfası bulutta aylık 1.000 ücretsiz
  kredi bildiriyor; basic scrape/crawl sayfa başına 1 kredi, arama 10
  sonuca 2 kredi. Ek formatlar/veri sağlayıcıları ayrıca ücretlenebilir.
  Kendi sunucusunda altyapı/bakım ve isteğe bağlı sağlayıcı maliyetleri
  kullanıcıya ait; sınırsız ücretsiz bulut hizmeti değildir.
- **Lisans:** Ana depo AGPL-3.0; README SDK'lar ve bazı UI bileşenleri
  için MIT ayrımını belirtiyor. Kapalı kaynak ticari hedefte seçilecek
  sürüm, kullanılan bileşen, değişiklik ve hizmet sunma biçimine göre
  kaynak sağlama yükümlülükleri ayrıca netleştirilmeli. AGPL madde 13
  değiştirilmiş sürümle uzaktan etkileşen kullanıcılara kaynak sağlama
  koşulu içeriyor; ayrı süreç/HTTP kullanımı otomatik lisans muafiyeti
  diye yorumlanmayacak. Hiçbir sözleşme kabulü veya satın alma yapılmadı.
- **Önerilen değerlendirme:** N-031'deki Instagram kaçırma ve Hacker
  News çelişkisi dahil, sonucu bilinen açık profil/sayfa örneklerinde
  temel alıcı ile Firecrawl'ı karşılaştırmak. API başarısının yanında
  hedef sayfa durumunu ve gerçek profil kanıtını kontrol etmek; giriş
  ekranını, engeli veya boş sonucu yokluk kararı saymamak.
- **Dayanak:** [Ana repo](https://github.com/firecrawl/firecrawl),
  [açık kaynak/bulut](https://docs.firecrawl.dev/contributing/open-source-or-cloud),
  [self-host sınırları](https://docs.firecrawl.dev/contributing/self-host),
  [scrape ve sağlayıcı yönlendirmesi](https://docs.firecrawl.dev/features/scrape),
  [hatalar](https://docs.firecrawl.dev/api-reference/errors),
  [fiyatlar](https://www.firecrawl.dev/pricing),
  [lisans](https://github.com/firecrawl/firecrawl/blob/main/LICENSE).

### N-031 — Firma adından sosyal hesap keşfi ve canlı kaynak doğruluğu

- **Durum:** Birleşik keşif/doğrulama akışı 0.171.0 ile uygulandı; geniş
  örneklemde doğruluk ölçümü sürekli değerlendirme konusu. **Güncellendi:** 19 Kasım 2026.
- **Kullanıcı beklentisi:** Firma adı/domaini başlangıç girdisi olmalı;
  hesap adaylarını bulmak için kullanıcıdan her sosyal hesap adını istemek
  ön koşul yapılmayacak. Bilinen hesaplar sonradan doğrulama girdisi olabilir.
- **Canlı kapsam:** 0.170.1 / `68812ce` üzerinde Maigret 30 ve Sherlock
  26 platform seçimiyle çalıştı; birleşimde 41 farklı platform var.
  Tavily'nin iki motor ve beş doğrudan tanı isteği 10 kredi bildirdi.
  Sonuç sayısı veya HTTP başarısı tek başına ilgili hesap bulunduğunu göstermez.
- **Gözlenen eksikler:** Maigret, aynı kullanıcı adındaki Instagram
  profiline `Not found` dedi; açık profil sayfası HTTP 200 ile profil
  türü, marka başlığı ve tam URL döndürdü. Sherlock'un Hacker News adayı
  doğrudan kontrol edilince `No such user.` yanıtı alındı. X ise Maigret
  ve alan filtreli gelişmiş Tavily sorgusunda bulundu.
- **0.170.1 ayrımı:** Motor Maigret/Sherlock adaylarını `found_unverified`,
  diğerlerini `unreported_platforms` olarak gösteriyor; sahiplik veya
  kesin yokluk hükmü vermiyor. Ancak kaynakların bu örnekteki tespit
  eksikleri çözülmüş değildir. Katalog/sürüm doğrulaması canlı doğruluk
  garantisi değildir.
- **0.171.0 uygulaması:** `brand discover` firma/domaininden adayları çıkarır;
  Maigret/Sherlock, ana sayfa, aynı domainin saklı aramaları ve açık seçimle
  Tavily advanced sorgularını birleştirir. Tekil sayfa kontrolleri, 4 eşzamanlı
  alım, toplam süre/sayfa/gövde sınırları, DNS pinning ve firma kapsamlı
  kalıcı/idempotent makbuz vardır. Yeni bağımlılık/Firecrawl yoktur.
- **Yeni canlı kanıt:** SecureHup ücretsiz koşusunda Instagram, X, GitHub,
  GitLab ve LinkedIn profil kimliği doğrulandı. LinkedIn company/showcase
  tek hesaba birleşti. HackerNews HTTP419 nedeniyle aday kaldı; eski
  `No such user.` yanıtı bugünün cevabı sayılmadı. 6,438 saniye toplam,
  0,063 saniye ağsız replay. Sahiplik veya genel yüzde doğruluk iddiası yok.
- **Sınır:** Eski `username-preview/watch-*` kaynak iddiası sözleşmesini
  korur; birleşik doğrulama yeni komutta ve `brand.discovery.*` JSON
  yüzeyindedir. Yeni advanced/alan filtreli Tavily orkestrasyonu kontrollü
  testlerde doğrulandı; bu sürümde yeni canlı ücretli sorgu yapılmadı.
  [Kullanım ve kabul](docs/SOCIAL_DISCOVERY.md), özel yeni kanıt alanı
  `/private/tmp/xti-social-0171-acceptance-4ibp8wit`.
- **Dayanak:** [Geniş canlı test](docs/TAVILY_LIVE_ACCEPTANCE.md#geniş-web-ve-sosyal-hesap-testi--19-kasım-2026),
  özel kanıt klasörü `/private/tmp/xti-social-full-8pus8z4q`.
  Ham yanıtlar, HTML ve test DB'si Git'e eklenmedi.

### N-029 — Tam yayın metni, yeniden inceleme ve günlük arşivi

- **Durum:** Uygulandı ve GitHub/Linux teslimi tamamlandı; lisans koşulları sürekli. **Güncellendi:** 19 Kasım 2026.
- **Yetki:** Kullanıcı önceki sıranın 2, 3 ve 4. maddelerini istedi.
  Sonraki 19 Kasım yönlendirmesinde GitHub/Linux teslim adımıyla devam
  edilmesini onayladı; `071a076` kodu `main` dalına gönderildi.
- **Kaynak seçimi:** CERT-FR metinleri açık lisans 2.0; NCSC metinleri
  belirtilen istisnalar dışında OGL v3 koşullarıyla sunuluyor. Kaynak,
  lisans ve özgün bağlantı korunur; üçüncü taraf/özel kısıt istisnaları
  genel yayıncı lisansı ile onaylanmış sayılmaz. Logo/görseller ayrı indirilmez
  veya işlenmez; özgün PDF bunları içerebilir, logo hakları otomatik verilmiş sayılmaz.
- **Ayrıştırıcı:** PDF için BSD-3-Clause lisanslı pypdf 7.1.1 eklendi;
  PyPI wheel SHA-256 `04c5680d4b4cfa04ab505b09393fc949860c34a4dad6565284d11a2f5c3ce8b1`.
  HTML ana metni ayrı adaptör; PDF sınırlı alt süreç. OCR, şifre çözme,
  etkin içerik ve üçüncü taraf bağlantılarını izleme kapsamda değildir.
- **Arşiv anlamı:** Özgün günlük kimliği/hash/sıra ve tekrar anahtarları
  korunur. Önizleme + yedekli açık işlem; eski gövde sıkıştırılır ve aynı
  SQLite yedeğinde saklanır. Mantıksal kayıt/okuma sınırları kaldırılmaz;
  sıkıştırma sınırsız büyüme iddiası değildir.
- **Canlı kabul:** CERT-FR CTI-010 HTML (2.807 UTF-8 bayt), aynı raporun
  PDF'si (9 sayfa / 15.968 UTF-8 bayt) ve NCSC rehber HTML'si (2.290 UTF-8
  bayt) ayrı izole alanda alındı. Ham nesne hash'i, metin ve kaynak makbuzu
  doğrulandı. Gerçek SIGKILL öncesi commit kesintisi sonrası tekrar, firma
  ayrımı, arşiv/restore ve 78 → 79 geçiş testleri geçti. Tam paket 3.186
  testte bir eski kurulum testi hatası ve dört Linux atlamasıyla bitti;
  test düzeltildi, ilgili 56 kontrol yeniden geçti. Son kod için odaklı
  test sonuçları ve tam koşudan sonraki değişiklikler
  [kabul kaydında](docs/ACCEPTANCE_REVIEW.md) ayrı tutulur.
- **Sonraki Linux teslimi:** Aynı `071a076` commit'inde altı workflow
  başarılı. Tam paket 3.187 test / 1.908,627 saniye; hızlı paket 1.890 test /
  1.264,694 saniye; hata/atlama yok. Gerçek marka/PDF/RSS ve theHarvester
  kurulumu, firma izolasyonu, 64 → 79 geçişi ve kesilen kurulumdan dönüş
  doğrulandı. Önceki macOS test düzeltmesi bu tam koşuya dahildir.
  Bu sonuç kaynakların sürekli erişilebilirliği veya 7/24 kapasite
  garantisi değildir. Toplu metin işleri, bildirim ve birikimli kapasite
  genişletmeleri 0.170.0 içinde uygulandı; ayrı kabul sonuçları N-030'da
  ve [yol haritasında](docs/roadmap/ENGINE_INTEGRATION_ROADMAP.md) izlenir.
- **Dayanak:** [Teslim planı](docs/roadmap/REPORT_REVIEW_RETENTION_DELIVERY.md),
  [CERT-FR koşulları](https://cert.cyber.gouv.fr/mentions-legales/),
  [NCSC koşulları](https://www.ncsc.gov.uk/section/about-this-website/terms-and-conditions),
  [pypdf sürümü](https://pypi.org/project/pypdf/7.1.1/),
  [ayrıştırma sınırları](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).

### N-001 — urlscan verisinin ticari üründe kullanımı

- **Durum:** Açık. **Güncellendi:** 17 Kasım 2026.
- **Not:** Mevcut kişisel kullanımda anahtarsız arşiv sorgusu çalıştı.
  Önceki kaynak incelemesinde, veriyi müşterilere sunulan ürüne dahil etme
  koşullarının sağlayıcıyla ayrıca netleştirilmesi gerektiği kaydedildi.
- **Sonraki iş:** Ticari kullanımdan önce saklama, müşteriye gösterme,
  raporlama/paylaşma ve kota haklarını somut kullanım biçimi için kaydetmek.
  Ücretsiz erişim tek başına bu hakların tamamını sağlamış sayılmayacak.
- **Dayanak:** [Kaynak kararı](docs/decisions/0158-url-hash-source-context.md),
  [urlscan koşulları](https://urlscan.io/terms/),
  [ticari kullanım açıklaması](https://docs.urlscan.io/pages/faq).

### N-002 — Nmap ve theHarvester için ticari kullanım değerlendirmesi

- **Durum:** Açık. **Güncellendi:** 17 Kasım 2026.
- **Not:** Araçların kurulması ve çalışması, ticari ürün kullanımının bütün
  koşullarının tamamlandığı anlamına gelmiyor. İlk işletim kendi
  sunucularımızda olacak; inceleme bu gerçek kullanım biçimine göre yapılacak.
- **Sonraki iş:** Ticari hizmete geçmeden önce kullanılan sürümün koşulları,
  entegrasyon/dağıtım biçimi ve gereken bildirimler için karar kaydetmek.
  Ayrı süreç kullanılması otomatik muafiyet, GPL kullanılması otomatik
  ücret veya yasak olarak yorumlanmayacak.
- **Dayanak:** [Bileşen bildirimi](THIRD_PARTY.md),
  [ürün kararları](docs/roadmap/ENGINE_INTEGRATION_ROADMAP.md#64-ticari-kullanım-dağıtım-ve-korunacak-kararlar).

### N-003 — Kaynak atıfları ve yeni kaynakların koşulları

- **Durum:** Sürekli. **Güncellendi:** 17 Kasım 2026.
- **Not:** Önceki incelemede CIRCL verileri için CC-BY ve CIRCL hizmet
  sayfasına atıf koşulu kaydedildi; sayfa lisans sürümünü belirtmiyor.
  MISP değerlendirmesi yalnız seçilmiş dört listeyi kapsıyor.
- **Yapılacak iş:** Rapor ve gelecekteki panelde kaynak/atıf bilgilerini
  korumak. Yeni liste, paket veya sağlayıcı eklenirken kod lisansını ve
  veri kullanım koşullarını ayrı incelemek. MISP koşul belgesi değiştiğinde
  güncellemeyi açmak için hash'i incelemeden değiştirmemek.
- **Dayanak:** [CIRCL ve URL kaydı](docs/INDICATOR_ENRICHMENT.md),
  [MISP koşulları ve denetimi](docs/WARNINGLISTS.md#kaynak-maliyet-ve-işletim-sınırları).

### N-005 — Gelişmiş Nmap ve platform üzerinden canlı kabul

- **Durum:** Beklemede; kesin yetkili hedef ve port kapsamı eksik.
  **Güncellendi:** 17 Kasım 2026.
- **Not:** Otomatik/kontrollü süreç testleri gerçek SYN, UDP, servis/OS ve
  seçili NSE çalıştırmasının kabulü yerine geçmez. Paylaşımlı CDN adresi,
  domain sahibi olmak nedeniyle kullanıcıya ait tarama hedefi sayılmayacak.
- **Kapanma koşulu:** İzinli IP/TCP/UDP portları ve gereken çalıştırıcı
  yetkileriyle plan → iş → çalıştırma → sonuç zincirini izole ortamda
  doğrulamak; çalışmayan seçeneği açık bırakmak.
- **Dayanak:** [Nmap kapsamı](docs/NMAP_MANAGED.md),
  [raporun açık kalanları](docs/ACCEPTANCE_REVIEW.md#diğer-sonuçların-kapsamı).

### N-006 — Kaynak erişim hatalarının kanıtı

- **Durum:** Açık; önceki crt.sh kabulündeki kök neden kanıtı eksik.
  **Güncellendi:** 17 Kasım 2026.
- **Not:** Önceki raporda zaman aşımı kanıtı var; sonraki HTTP 200 iddiasının
  komut/zaman/çıktısı yok. Kesin olarak yalnız sağlayıcı hatası denmeyecek.
  Common Crawl/Wayback gibi kaynaklarda da eski kesinti kaydı güncel durumla
  karıştırılmayacak.
- **Sonraki iş:** İlgili kaynak tekrar ele alındığında zaman, istek, HTTP
  sonucu ve eski başarılı verinin korunmasını birlikte kaydetmek. Yeni
  kanıtla düzelen madde kapatılacak; kesintisiz hizmet garantisi verilmeyecek.
- **Dayanak:** [Kaynak raporu incelemesi](docs/ACCEPTANCE_REVIEW.md#diğer-sonuçların-kapsamı),
  [kullanım kabulü](docs/FUNCTIONAL_ACCEPTANCE.md).

### N-007 — Birden fazla firma için ortak sağlayıcı kotası

- **Durum:** Backend entegrasyonuna bırakıldı; ölçekli işletimden önce.
  **Güncellendi:** 18 Kasım 2026.
- **Not:** Yeni URL/hash isteklerinin aralık ve bekleme kaydı seçili veri
  alanında uygulanıyor. Farklı firma alanları/sunucular için ortak çıkış
  kotası henüz bu mekanizma tarafından yönetilmiyor.
- **Karar:** Firma paketi, abonelik, kullanım hakkı ve ortak sağlayıcı
  kotasının tek merkezde yönetimi backendin sorumluluğudur. Motor verilen
  iş sınırını uygular ve gerçek ölçümü/belirsizliği bildirir; aynı ticari
  sayaç iki tarafta ayrı tutulmaz. Kullanıcı bu ayrımı 18 Kasım'da onayladı.
- **Sonraki iş:** Entegrasyonda backendin kota ayırma, belirsiz tüketimi
  koruma ve tekrar işlerini değerlendirme sözleşmesini belirlemek.
  0.158.0 iş başına kullanım raporu bu bağlantının motor tarafıdır;
  dağıtık kota/abonelik sistemi tamamlandı anlamına gelmez.
- **Dayanak:** [Mevcut sınırlar](docs/INDICATOR_ENRICHMENT.md#sonuçların-anlamı),
  [MTR-05/06](docs/roadmap/ENGINE_INTEGRATION_ROADMAP.md#62-iş-paketleri-ve-tamamlanma-ölçütleri).

### N-009 — Araştırmanın kapsam sınırları

- **Durum:** Bilinen sınır; CNAME/TLS, tedarikçi ve pasif aday kararları uygulandı.
  **Güncellendi:** 18 Kasım 2026.
- **Not:** Araştırma en fazla iki ilişki adımıyla çalışıyor. URL kaynağı
  ilk 20 arşiv sonucunu alıyor; bütün arşivde ters yönde arama yok.
  0.159.0 kayıtlı CNAME adımları/son hedef IP'sini ve gerçekten sunulan
  sertifikaları ortak araştırma/öncelik/incelemeye taşır. 0.160.0 kayıtlı
  tedarikçi adayını, insan kararlarını ve envanteri ayrı kanıt türleriyle
  ekler. 0.161.0 kayıtlı pasif alt alan adaylarını ve sahiplik sınıflandırmasını
  ekler. 0.162.0 pasif keşif çalışmasının son sağlık durumunu ayrı bağlam
  olarak ekledi. 0.163.0 tedarikçi kaynak iddiasını, izleme karşılaştırmasını
  ve hesaplanan inceleme kartını ekler (N-021). SAN/wildcard adı gözlenmiş
  host sayılmaz.
  Ters bağlantılar sınırlı kayıt penceresinden gelir; eksik kapsam görünürdür.
- **Kanıt:** 24 yeni test dahil 266 ilgili yerel test geçti; firma ayrımı,
  özgün kanıt, eşzamanlı okuma, sınırlar ve yedek korundu. Ek 68 CI/kaynak
  testiyle toplam 334 farklı test başarılı. Ağsız/kontrollü
  kabul [kabul belgesinde](docs/ACCEPTANCE_REVIEW.md); canlı tarama değildir.
- **0.160.0 kanıtı:** 32 yeni test dahil **337 farklı ilgili test** geçti.
  Ayrı iki firmalı gerçek süreç kabulü **40,395 saniyede** tamamlandı;
  bu yerel/kontrollü sonuç Linux veya canlı kaynak kabulü değildir.
- **0.161.0 kanıtı:** 29 yeni test dahil **351 farklı ilgili yerel test**
  geçti; kaynak/karar ayrımı, iki adım, firma ayrımı, yedek, sınırlar ve eski
  inceleme uyumu kontrol edildi. Bu yeni bir kaynak taraması değildir.
- **Sonraki iş:** Kapsam genişletirken eski kanıt kimliklerini korumak;
  bütün internetin tarandığı veya ilişkilerin sahiplik/zararlılık kanıtı
  olduğu izlenimini vermemek. Ayrıntılar ilgili modüllerde korunuyor.
- **Dayanak:** [Araştırma kapsamı](docs/RESEARCH.md),
  [URL/hash ilişkileri](docs/INDICATOR_ENRICHMENT.md#ilişki-araştırması).

### N-011 — Daha sonra seçilebilecek sağlayıcılar

- **Durum:** Beklemede; bu sürümde entegre değiller.
  **Güncellendi:** 17 Kasım 2026.
- **Not:** Önceki seçimde URLhaus anahtar/ticari kullanım koşulları nedeniyle
  bu anahtarsız pakete alınmadı. PhishTank'ın arşiv şartları güncel kullanım
  izni sayılmadı. Ücretli kaynaklar gelecekte değerlendirilebilir.
- **Sonraki iş:** Seçildikleri tarihte güncel veri katkısı, kota, maliyet,
  saklama ve müşteriye gösterme koşullarını yeniden incelemek. Bu not,
  hesap açma veya ücretli kullanım başlatma talimatı değildir.
- **Dayanak:** [Kaynak seçim kararı](docs/decisions/0158-url-hash-source-context.md).

### N-012 — Kapalı kaynak hedefi ve depo erişimi

- **Durum:** Açık; ürünün erişim/dağıtım kararı için.
  **Güncellendi:** 18 Kasım 2026.
- **Not:** Ürün hedefi kendi platformumuzun kapalı kaynak motoru.
  GitHub API kontrolünde `mstdeveloper33/securehup_xti` için
  `isPrivate=false` döndü: repo şu anda herkese açık. Görünürlük bu
  çalışmada değiştirilmedi; önceki yayın/dağıtım hakları ayrıca incelenecek.
- **Sonraki iş:** Ticari teslimden önce erişim/dağıtım kararını, mevcut
  durumu ve varsa yapılacak değişikliği somut olarak kaydetmek.
- **Dayanak:** [Korunacak ürün kararları](docs/roadmap/ENGINE_INTEGRATION_ROADMAP.md#64-ticari-kullanım-dağıtım-ve-korunacak-kararlar).

### N-013 — İnceleme geçmişinin kapsamı ve saklanması

- **Durum:** Kalıcı geçmiş uygulandı; geniş kapsam ve saklama işletimi açık.
  **Güncellendi:** 17 Kasım 2026.
- **Not:** 0.156.0 `research-history` aynı kapsamın önceki/sonraki
  incelemesini özgün kanıt, kural ve zamanıyla saklar. İlk kayıt başlangıçtır;
  zamanla eskime ile kanıt değişimi ayrılır. Bu, bütün firma için analist
  kuyruğu veya anlamsal çelişki çözümü değildir. `context` güvenli sonucu
  sayılmaz; insan kararı ve alarm değiştirilmez.
- **Saklama sınırı:** Kayıt başına 8 MiB değerlendirme + 4 MiB fark;
  otomatik eski kayıt temizliği yok. Tekrar anahtarlarının silinmemesi ve
  zincirin korunması gerekir. Hash yerel bozulma denetimidir; imza değildir.
- **Sonraki iş:** Gerçek kullanımda disk/hacim ölçmek; gerekiyorsa
  geçmişi ve tekrar güvenliğini koruyan arşivleme politikası tasarlamak.
  Yeni kural/model sürümünde eski değerlendirmeyi okuyabilmeyi korumak.
- **Dayanak:** [Kullanım ve sınırlar](docs/RESEARCH_HISTORY.md),
  [mimari karar](docs/decisions/0160-frozen-research-reviews.md),
  [yerel kabul](docs/ACCEPTANCE_REVIEW.md).

### N-015 — Kişisel iş kuyruğunun yedek kapsamı

- **Durum:** Bilinen sınır. **Güncellendi:** 18 Kasım 2026.
- **Not:** `source-jobs init` kişisel alana ayrı iş dosyası ekler. Eski
  kişisel `backup` yalnız çekirdeği kapsar; kuyrukla birleşik yedek değildir.
  Firma `platform backup/restore` iki dosyayı birlikte korur; yeni kaynak
  işleriyle kontrollü test ve canlı kaynak yedeği geçti.
- **Sonraki iş:** Kişisel kuyruk işletim ihtiyacı oluşursa birleşik yedeği
  aynı kurallarla ele almak. Şimdiki işletim yolu firma yedeğidir; tek
  dosya yedeği tam firma yedeği sayılmaz.
- **Dayanak:** [Yedek ve geri dönüş](docs/SOURCE_JOBS.md#yedek-ve-geri-dönüş).

### N-017 — Kaynak işi kullanım ölçümünün sınırları

- **Durum:** Bilinen sınır. **Güncellendi:** 18 Kasım 2026.
- **Not:** 0.158.0 yeni kaynak işlerinde HTTP açma denemelerini saklar;
  sağlayıcı faturalama birimi veya uzaktaki kesin teslim sayısı değildir.
  Ölçüm adımın sonunda yazılır. Kesintide kaydı olmayan adımın tüketimi
  `null`/üst sınırdır; sıfır sayılıp bütçe geri verilmez. Eski v1 işler
  ölçülmemiş, tekrar kullanılan kanıt bu yeni işte sıfır denemedir.
- **Uyum:** Şema aynı kalır; eski kod yeni v2 işi okuyamaz. Kod geri
  dönüşünde yükseltme öncesi birleşik firma yedeği kullanılmalı.
- **Kanıt:** 225 ilgili test, son 57 test ve gerçek CIRCL/urlscan/MISP
  kullanım kaydı geçti; kapsam [kabul belgesinde](docs/ACCEPTANCE_REVIEW.md).
- **Korunacak koşul:** Backend entegrasyonu belirsiz tüketimi ve iş
  kimliklerini korumalı; kota/faturalama kararı ölçüm kapsamını aşmamalı.
- **Dayanak:** [Kullanım raporu](docs/SOURCE_JOBS.md#işin-kullanım-raporu),
  [sürüm kararı](docs/decisions/0162-source-job-request-usage.md).

### N-018 — Araştırma modeli 2 ve tedarikçi kararının anlamı

- **Durum:** Bilinen sınır. **Güncellendi:** 18 Kasım 2026.
- **Not:** 0.160.0 araştırma/öncelik ve yeni dondurulmuş değerlendirmeyi
  model 2 olarak üretir; engine/platform istek ve zarfı v1 kalır. Eski
  model 1 incelemeleri özgün okunur, ilk yeni model/kural kaydı başlangıçtır.
  Yeni model 2 incelemeyi eski motor okuyamaz. Kod geri dönüşü için
  yükseltme öncesi uygun yedek gerekir; şema 75'in aynı kalması tek başına
  eski kodla veri uyumu anlamına gelmez.
- **Korunacak anlam:** İnsan kararında `current` son ilgili karardır;
  durum `withdrawn` veya `revoked` olabilir. Adayın `current` değeri son
  aday yenilemesine aittir. Teknik kanıtın kaybolması insan onayını silmez.
  Kararın zamanı teknik hizmet süresi değildir; işletme önemi tehdit
  puanına çevrilmez. Mevcut kayıtta bulunmayan karar sahibi uydurulmaz.
- **Kanıt:** Eski/yeni model okuması, farklı modelde başlangıç, bozuk
  kanıt reddi, tarihçe değişimi, firma ayrımı ve yedek kabul testleri geçti.
- **Dayanak:** [Kullanım ve uyum](docs/RESEARCH.md#tedarikçi-adayları-ve-insan-kararları),
  [mimari karar](docs/decisions/0164-human-supplier-research.md).

### N-019 — Pasif aday araştırmasının kanıt ve kapsam sınırları

- **Durum:** Bilinen sınır. **Güncellendi:** 18 Kasım 2026.
- **Not:** 0.161.0 kayıtlı aday ve insan sınıflandırmasını ortak araştırmada
  gösterir. Adayın `owned` olması aktif kontrol onayı veya teknik sahiplik
  doğrulaması değildir. Araştırma aday üretmez, aktif kapsam yazmaz.
- **Kanıt sınırı:** Özgün kaynak kimliği, URL, ham ad ve SHA-256 korunur.
  Bu tablolarda ham sağlayıcı payload'ı bulunmadığından içerikten hash
  yeniden hesaplanmış sayılmaz. Kaynak satırıyla keşif çalışması arasında
  kesin ilişki yoksa yalnız aynı zamana bakılarak `source_run_id` üretilmez.
  Yeni boş/başarısız çalışma eski adayın zamanını yenilemez ve adayı silmez.
- **0.161.0 uyumu:** Model 2/zarf v1/şema 75 korunur; politika v4'ün ilk incelemesi
  yeni başlangıçtır. Eski model/politika sonuçları yeniden yorumlanmaz.
- **0.162.0 güncellemesi:** Kaynak çalışma durumu ortak araştırmada ayrı
  bağlamdır (N-020). Aday satırına kesin çalışma bağı tahmin edilmez;
  yukarıdaki kanıt sınırları değişmedi.
- **Dayanak:** [Kapsam](docs/RESEARCH.md#pasif-alt-alan-adayları-ve-sahiplik-incelemesi),
  [mimari karar](docs/decisions/0165-passive-candidate-research.md).

### N-020 — Kaynak durumunun anlamı ve araştırma modeli 3

- **Durum:** Bilinen sınır. **Güncellendi:** 18 Kasım 2026.
- **Not:** `discovery` yalnız kayıtlı kökün `crt.sh`/`theharvester`
  çalışmalarını okur. Sorgulanmadı, tamamlandı/boş, kısmi ve başarısız
  ayrıdır. Son complete yanıt kendi tarihiyle korunur; canlı kaynak
  erişilebilirliği veya internetin tamamında yokluk kanıtı değildir.
- **Bütçe:** Kök başına en fazla dört farklı çalışma; seçili çalışma
  alanları için istekte ortak 4 MiB. Sınırda `read_limited`, hiç deneme
  yoksa `never`; biri diğerinin yerine kullanılmaz. `coverage_complete`
  yerel okuma kapsamıdır, bütün sağlayıcıların başarılı olması değildir.
- **Uyum:** Araştırma/değerlendirme modeli 3 ve politika v5. Eski model
  1/2 özgün okunur; ilk yeni kayıt politika başlangıcıdır. DB 75/kuyruk 2
  ve dış zarf v1 aynı; eski motor yeni model 3 incelemeyi okuyamaz.
  Kod geri dönüşü için yükseltme öncesi uygun yedek gerekir.
- **Yerel kanıt:** Geniş 414, son 97 ve frozen uyum 110 test demetleri
  geçti; **415 farklı test**, 20 yeni test, hata/atlama yok.
  [Ayrıntılı kabul](docs/ACCEPTANCE_REVIEW.md).
- **Dayanak:** [Alanlar](docs/RESEARCH.md#pasif-kaynakların-son-sorgu-durumu),
  [karar](docs/decisions/0167-passive-source-research-context.md).

### N-021 — Tedarikçi iddiası, izleme ve hesaplanan kartın sınırları

- **Durum:** Bilinen sınır / korunacak anlam. **Güncellendi:** 18 Kasım 2026.
- **Not:** 0.163.0 mevcut ThreatCluster/RansomLook iddia adayını, üç
  kaynaklı izleme karşılaştırmasını (HIBP dahil) ve ortak kurallı kartı
  araştırmaya bağlar. Kaynak iddiası, kamu metaverisi, yerel bildirim ve
  hesaplanan karar desteği ayrı kalır. İhlal, müşteri etkisi veya sayısal
  risk sonucu üretilmez. Yeni kaynak/API/ücret yoktur.
- **Kimlik:** Tek tedarikçi filtresi aynı adlı diğer etkin tedarikçileri
  belirsizlik hesabından çıkarmaz. Tarihî izleme kendi o-günkü kimliğini
  ve aynı-ad sayısını korur; pasif/yeniden adlandırılmış kapsam güncel
  eşleşme diye sunulmaz. Çıkarılma çözülmüş ihlal sayılmaz.
- **Okuma sınırı:** Ortak kaynak/kimlik doğrulaması 20.000 satır, 16 MiB
  saklı içerik ve 2.000.000 muhafazakâr iş birimiyle sınırlıdır; zaman
  garantisi değildir. Sınırda eksik kart yerine kısmi kapsam verilir.
  Tedarikçi başına 150 iddia, düğüm başına 52 kanıt ve genel graph
  sınırları geçerlidir. Büyük kataloglarda kaynak-bağlı indeksleme /
  doğrulanmış checkpoint tasarımı gerçek hacim ölçümünden sonra ele alınır;
  denetimi kaldırarak veya geçmişi silerek sınır aşılmaz.
- **Uyum:** Model 3, DB 75, kuyruk 2 korunur. Politika v6'nın ilk kaydı
  yeni başlangıçtır; eski model 1/2/3 kayıtları özgün okunur.
- **Kanıt:** 432 geniş + 86 son kontrol demetinde **435 farklı test**
  geçti (28 yeni senaryo). Yerel iki firma/süreç/kurtarma kabulü 29,331
  saniyede geçti; eşikler korunur. [Kabul kaydı](docs/ACCEPTANCE_REVIEW.md)
  canlı kaynak veya Tavily/Nmap kabulü değildir.
- **GitHub sonucu:** 18 Kasım kontrolünde `dbee4ab` için dört iş de
  başarılı tamamlandı: [hızlı kontrol](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44288340754),
  [firma izolasyonu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44288340939),
  [Linux kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44288340970),
  [marka araçları kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44288341033).
  Bu kanıt önceki sürüm içindir; 0.164.0 kabulü ayrıca kaydedilir.
- **Dayanak:** [Kullanım](docs/RESEARCH.md#tedarikçi-izleme-ve-inceleme-bağlamı),
  [mimari karar](docs/decisions/0168-supplier-monitoring-research.md).

### N-022 — RIPEstat ticari kullanım izni

- **19 Kasım ek kapsam:** 0.168.0 aynı hizmetin WHOIS kayıt bağlamını ekler.
  Anahtarsız canlı kişisel sorgu HTTP200 ile doğrulandı; ilk sandbox denemesi
  ağ erişiminde başarısızdı, sınırlama dışında aynı istek başarılı oldu.
  Bu sonuç yazılı ticari izin/yeniden dağıtım koşulunu kapatmaz.
  [Resmî WHOIS API](https://stat.ripe.net/docs/data-api/api-endpoints/whois),
  [paket kapsamı](docs/EVIDENCE_WORKFLOWS.md).

- **Durum:** Ticari ürün öncesi açık. **Güncellendi:** 18 Kasım 2026.
- **Not:** 0.164.0 `network-info` ile IP → BGP ağ bloğu → origin ASN bağlamı
  alır. Anahtarsız erişim ticari saklama/yeniden sunma izni değildir.
  İncelenen şartlar ticari kullanım için RIPE NCC yazılı izni gerektirir;
  yeniden paketleme/dağıtım koşulları ürün kullanımıyla birlikte netleşmeli.
- **Kanıt:** [Resmî uç](https://stat.ripe.net/docs/data-api/api-endpoints/network-info),
  [hizmet şartları](https://www.ripe.net/about-us/legal/ripestat-service-terms-and-conditions/).
  18 Kasım canlı kişisel kabulünde `1.1.1.1` için `1.1.1.0/24`, ASN 13335
  alındı; hedef taranmadı. İlk geliştirme denemeleri cooldown kaydı ve
  isteğin yanıtta tekrar edilmesi varsayımını ortaya çıkardı; ikisi düzeltildi.
- **Kapatma koşulu:** Kendi sunucularımızdaki ticari hizmette istenen kullanım
  için yazılı izin/uygun anlaşma veya koşulları uygun başka sağlayıcı seçimi.
  Kodun veya canlı testin bitmesi bu notu kapatmaz. Ücretli servis açılmadı.

### N-023 — 0.164.0 karar, kapsam ve sürüm sınırları

- **Durum:** Bilinen sınır / korunacak anlam. **Güncellendi:** 18 Kasım 2026.
- **Kimlik:** İnsan eşleştirmesi fiziksel kayıt birleştirme değildir; aynı
  türdeki özgün kayıtlar korunur. Kararlar geri alınabilir; eski sürüm veya
  değiştirilmiş tekrar isteği reddedilir. Rapor adayı otomatik IOC olmaz.
- **Metin:** Mevcut haber/firma başlığı ve saklı özeti incelenir; tam makale,
  PDF veya internetteki bütün raporlar değildir. 64 KiB/200 aday sınırı ve
  kaynak özetinin kısaltılma bilgisi korunur. İş adımı en yeni 20 haberi alır;
  daha fazlası kısmi kapsamdır, açık tekil extract kullanılabilir.
- **Liste:** Firma kökleri pencerelenir (varsayılan 25, en fazla 100).
  Eksik pencere tüm firmanın kesin öncelik sırası gibi sunulmaz. Farklı
  kaynak durumları ayrı görünür; otomatik anlamsal çelişki hükmü değildir.
- **Saklama:** Karar günlüğü en fazla 10.000 olay/32 MiB; otomatik silme yok.
  Araştırma okuyucuları ayrıca ön ölçümlü satır/byte bütçesi uygular.
  Bütçe aşımı eksik kapsam veya açık ret verir, kanıtı sessizce kesmez.
- **Uyum:** Çekirdek 76 açık yedekli migration; araştırma/frozen model 3,
  öncelik v7. Yeni kaynak işi v3; eski v1/v2 okunur; kuyruk 3. Eski 1/2
  kuyruk ayrıca açık yedekli migration ister; altı adım ve geç iptal
  dahil 16 olay, eski event/payload byte'ları ve rowid'ler korunur. Eski kodla
  geri dönüş yükseltme öncesi birlikte yedeğin yeni alana restore edilmesidir.
  Yükseltmeden sonraki veriler eski yedekte yoktur; yükseltilmiş alan korunur.
- **Kabul:** Yerel ve 30 dakikalık Linux hacim, saklama arşivi, yedekten
  dönüş ve gerçek eski kodla sürüm geri dönüşü geçti. Linux'ta 232 tur /
  2.784 süreç, p95 0,745487 saniye, RSS 49.979.392 bayt ölçüldü.
  Tam paket ilk Linux koşusu 30 dakika CI sınırında 2.509 test satırından
  sonra iptal oldu; test hatası görünmedi ama tam başarı sayılmaz. Yalnız
  CI tam paket iş bütçesi 60 dakika oldu; kabul eşikleri değişmedi. Yeni
  tam Linux paketi `91e5ca8` üzerinde **3.039 test / 2.067,829 saniye** ile
  geçti; hata/atlama yok. `432f530` ile motor/test kodu aynıdır.
  [Kabul kaydı](docs/ACCEPTANCE_REVIEW.md) ilk eksik koşuyu ve nihai
  [başarılı tam koşuyu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44311197271)
  ayrı korur. Sınırlı kabul 7/24 SLA veya OpenCTI eşdeğerliği değildir.

### N-024 — Geniş STIX/TAXII dış sistem alışverişini erteleme

- **Durum:** Kullanıcı kararıyla ertelendi. **Güncellendi:** 18 Kasım 2026.
- **Dayanak:** Motor kendi platformumuzda kullanılacak; kullanıcı geniş
  dış sistem içe/dışa aktarımını ve TAXII alışverişini sonraya bıraktı.
  Roadmap 1–7'nin tamamlanması, 8. adımı kendiliğinden başlatmaz.
- **Kapsam:** Geniş STIX nesne/ilişki içe-dışa aktarımı ile TAXII üzerinden
  başka güvenlik sistemleriyle alışveriş aktif geliştirme sırasından çıkarıldı.
  Mevcut sınırlı STIX dışa aktarımı ve MITRE ATT&CK gibi çalışan kaynak
  bağlantıları kullanılmaya devam eder.
- **Motor/platform:** Kendi .NET platformunun mevcut engine/platform JSON
  sözleşmesiyle bağlantısı ayrı kapsamdır; bu bağlantıyı tüketici ekip uygular.
  Veri kaynakları ve uygun açık kaynak araç adaptörleri de bu ertelemenin
  kapsamına girmez.
- **Yeniden ele alma koşulu:** Somut dış sistem veya müşteri veri alışverişi
  ihtiyacı oluştuğunda, karşı uç ve gerekli nesne/işlem kapsamı kullanıcıyla
  belirlenir. LLM ayrı bekleyen başlıktır; bu karar LLM'yi başlatmaz.
- **Dayanak plan:** [Motor yol haritası](docs/roadmap/ENGINE_INTEGRATION_ROADMAP.md).

### N-025 — IOC yaşam döngüsünün anlamı ve test kapsamı

- **Durum:** Uygulandı; sınırlı anlam korunacak. **Güncellendi:** 18 Kasım 2026.
- **Kapsam:** 0.165.0 `ioc lifecycle` / `ioc.lifecycle` kayıtlı iddiayı,
  tarihini ve son toplama durumunu ayrı değerlendirir. Feodo sağlayıcı
  gözlemi; CERT Polska liste sürümü; eski elle girişte belirsiz olay/giriş
  zamanı. Yeniden indirme yeni saldırı kanıtı sayılmaz. Kaynak kesintisi,
  listeden kaldırma ve yerel geri çekme ayrı görünür.
- **Politika:** `ioc-lifecycle-v1` yerel inceleme eşiklerini açık taşır:
  ağ göstergeleri 7/30, hashler 30/180 gün; kaynak toplaması 24 saat.
  Eşikler değiştirilebilir. Bilimsel risk/zararlılık puanı değildir;
  özgün güven ve insan kararları değişmez, otomatik geri çekme yoktur.
- **Sınır:** Tek IOC'de 500 iddia/10.000 olay/20.000 makbuz/16 MiB okuma;
  aşımda eksik başarı yerine ret. 100 iddia/sayfa; veri, politika veya
  zaman sınıfı değişince sayfa kesiti reddedilir. Kaynak adları bağımsız
  doğrulama sayısı değildir. Gerçek sighting günlüğü henüz eklenmedi.
- **Uyum:** Şema 76, kuyruk 3, araştırma/frozen model 3 ve öncelik v7
  değişmez. Yeni değerlendirme model 1; engine/platform dış zarf v1.
  Yeni migration, paket, ağ isteği ve ücretli kaynak yoktur.
- **Kabul:** Son kodun 110 farklı hedefli testi / 31,616 saniye geçti;
  33 yeni senaryo içerir. Gerçek terminal/JSON/engine süreç kabulü geçti.
  Tek kesit, firma ayrımı, bozuk kanıt, yeniden toplama ve birlikte
  yedekten dönüş sınandı. İlk uygulamanın tam regresyonu 3.069 test /
  1.338,055 saniye ile bitti: 3.065 başarılı, hata yok; dört Linux süreç/
  systemd testi macOS'ta atlandı. Son makbuz kontrolü 110 testlik demetle
  ayrıca doğrulandı; yeni Linux kabulü yapılmadı.
  [Kullanım](docs/IOC_LIFECYCLE.md), [kanıt](docs/ACCEPTANCE_REVIEW.md).
- **Test düzeni:** Kullanıcının her değişiklikte tam paket gerekip
  gerekmediği sorusu üzerine çalışma düzeni açıklaştırıldı: geliştirmede
  etkilenen davranış/bağlantılar, teslimde son kod için bir tam paket;
  yalnız belge düzeltmesi ardından gereksiz tekrar yok. CI kapatılmadı.
  [Test seçimi](docs/TESTING.md).

### N-026 — Rapor sürümleri, gözlem anlamı ve geçiş sınırı

- **Durum:** Uygulandı; aşağıdaki sınırlarla korunacak. **Güncellendi:** 18 Kasım 2026.
- **Kapsam:** 0.166.0 saklı news/mentions başlık-özeti açık capture ile
  rapora alır. Aynı içerik belge/gözlem çoğaltmaz; değişen metin sürümlenir.
  Yeni tekrar anahtarı için işlem makbuzu ayrıdır. İnsan `reports-on` bağı
  mevcut aktör/kampanya/malware/IOC'ye ve belirli belge sürümüne bağlıdır;
  metin değişince yeni belgeye taşınmaz. Eski karar da geri çekilebilir.
- **Anlam:** Metinde geçme, Feodo sağlayıcı gözlemi, CERT Polska liste
  üyeliği ve belirsiz elle kaynak iddiası ayrıdır. Yayın/toplama/kayıt
  zamanları karışmaz; müşteri ağında olay veya saldırı kanıtı sayılmaz.
  Mevcut IOC geçmişi kopyalanmaz; denetlenmiş kayıtlardan tek kesitte okunur.
- **Geçiş:** Şema 77 yeni rapor journal tablosunu açık yedekli migration
  ile ekler. Eski kimlikler/tablolar/kararlar korunur. Geri dönüş eski kod
  ve geçiş öncesi yedeğin boş alana restore edilmesidir. Kuyruk 3 kalır.
- **Sınır:** Journal 10.000 makbuz/32 MiB; tek rapor 1.000 değişiklik/2 MiB;
  sayfa en fazla 100. Hacim aşımı geçmiş silmez veya eksik başarı üretmez.
  Tam makale/PDF yoktur. Üçüncü taraf metin hakları mevcut N-003 ve ilgili
  kaynak notlarıyla izlenir; bu yerel işlem ticari yeniden dağıtım izni değildir.
- **Çıkarım uyumu:** Yeni belgelerde cümle sonundaki IP noktası
  `report-document-candidates-v2` ile ayrılır. Eski investigation v1
  önerilerinin aday listesi ve doğrulaması değiştirilmez.
- **Ayrı kalan:** 0.166.0 tesliminde kaynak işi/ortak araştırma bağlantısı
  sonraki dilimdi; araştırma kısmı 0.167.0/N-027 ile tamamlandı. Otomatik
  kaynak işi bağlantısı bekler; mevcut `reports` adımı eski investigation
  aday modelini korur. Gerçek müşteri sighting toplama, genel çıkarım,
  geniş STIX/TAXII ve LLM bu paketle tamamlanmış sayılmaz.
- **Kabul:** Firma JSON/terminal, tekrar/değişim, eski belge kararı, kaynak
  hata/bozulması, tek kesit, eşzamanlı yazma ve yedekten dönüş senaryoları
  [kabul kaydında](docs/ACCEPTANCE_REVIEW.md) ayrı belirtilir.
  194 testlik geniş demet, son ayrıştırma farkının 96 testi ve 13 gerçek
  süreç geçti. İlk tam paket 3.104 testte bir kabul-betiği hatası ve dört
  Linux atlaması verdi; hata düzeltildi, betiğin 18 testlik tekrarında
  16 başarı/iki ortam atlaması var. İlk hata sonucu korunur; düzeltme
  sonrası ikinci tam tur yoktur. Yeni Linux/7×24 kabulü yapılmadı.
  [Kullanım](docs/REPORTS_OBSERVATIONS.md),
  [mimari karar](docs/decisions/0171-report-revisions-and-observations.md).

### N-027 — Raporların ortak araştırma bağlamı

- **Tarih/durum:** 19 Kasım 2026; 0.167.0 uygulandı, kapsam sınırlı.
- **İşlev:** Belge sürümleri ortak araştırma/öncelik/kayıtlı incelemelerde
  görünür. Metin adayı, özgün arama kapsamı ve insan bağlantısı ayrıdır.
  `record.get` belge sürümüne gider; firma ayrımı korunur. Eski metin ve
  geri çekilmiş insan kararı silinmez veya yeni metne aktarılmaz.
- **Anlam:** Son kayıtlı belge canlı kaynak doğrulaması değildir.
  Raporun `observed_at` alanı `response_received_at` ile alınma zamanıdır;
  gerçek olay zamanı bilinmiyor. Aynı yayın/özetin eski aday ve yeni rapor
  kaydı bağımsız doğrulama oyu değildir. Aktör–IOC saldırı atfı üretilmez.
- **Uyum:** Model 3/zarf v1, şema 77/kuyruk 3; yeni migration/paket/API
  yoktur. Öncelik v8 ilk karşılaştırmada yeni başlangıç oluşturur; eski
  model 1–3/v7 değerlendirmelerin içeriği yeniden yazılmaz.
- **Kapasite:** Araştırmada 10.000 makbuz/16 MiB, düğüm başına 200 ilişki,
  istek boyunca 50.000 bağlantı incelemesi; tek ilişkide 52 kanıt ve gerçek
  toplam. Sınırlar açık kısmi kapsam üretir; bozuk geçmiş hata verir.
- **Açık kalan:** N-026'daki otomatik kaynak işi bağlantısı, gerçek müşteri
  sighting toplama, genel çıkarım ve tam makale/PDF bu teslimde yoktur.
  N-024 geniş STIX/TAXII ertelemesi ve LLM kararı sürer. Kaynak kullanım
  koşulları ve Tavily/Nmap canlı kabulleri bu yerel değişiklikle kapanmaz.
- **Dayanak:** [Kullanım](docs/REPORTS_OBSERVATIONS.md),
  [mimari karar](docs/decisions/0172-report-research-context.md),
  [tam test kapsamı ve sonuç](docs/ACCEPTANCE_REVIEW.md).
  Son kodda 252 ilgili test ve 11 gerçek CLI/JSON süreci geçti; yeni
  özelliğin 15 testi dahildir. Bu turda tam paket, CI veya Linux/canlı
  kaynak kabulü tekrarlanmadı. Önceki sürümün tam sonucu N-026'da korunur.

### N-028 — Sekiz maddelik paket, görülme anlamı ve ölçülen kapasite

- **Durum:** Bilinen sınır; sekiz maddelik uygulama ve tanımlı yerel kabul tamam.
  **Güncellendi:** 19 Kasım 2026.
- **Kapsam:** N-026/N-027'de bekleyen otomatik rapor işi, ilişki önerileri,
  birleşik kimlik görünümü ve gerçek görülme günlüğü bu pakette uygulandı.
  Rapor adımı global haberleri firmanın eşleşmesi saymaz. Sensör görülmesi
  müşteri tarafından iletilen olaydır; otomatik log/EDR bağlantısı değildir.
  Yeni ilişki kararı CTI atfı, kimlik görünümü fiziksel merge oluşturmaz.
- **Sınır:** Kaynak işi v4; önceki v1/2/3 okunur. Çekirdek 78 yedekli geçiş;
  kuyruk 3 korunur. Görülme/ilişki günlüğü 20.000 olay / 64 MiB, kayıt başına
  1.000 olay / 2 MiB; kimlik 100 üye, grafik 100 düğüm/200 kenar; aşım açık bildirilir.
  Bu sınırlar milyonlarca olay veya 7/24 SLA kabulü değildir.
- **İlgili testler:** Son kodda 31 yeni test / 8,394 saniye; tekrar/kuyruk
  bağlantıları 145, günlük/araştırma 104 testle geçti. Kaynak demeti 111
  test: 109 başarılı, iki Linux atlaması. Demetler örtüşür, toplamları
  benzersiz test sayısı olarak sunulmaz. Tam koşu: 3.151 test /
  1.472,761 saniye, 3.145 başarılı, iki eski test beklentisi hatası ve dört
  Linux atlaması. Beklentiler düzeltildi; 23 araştırma + 7 katalog testi
  yeniden geçti. Çalışma kodu değişmedi; test düzeltmelerinden sonra tam
  koşu tekrar edilmedi. Başlangıç/son dosya özetleri kabul kaydında korunur.
- **Son hacim kanıtı:** İki firma, toplam 2.000 başlangıç görülmesi +
  1.000 varlık, 120 saniye eşzamanlı çalışma, 922 ölçülen süreç ve 304 yeni
  görülme. Okuma p95 0,428108 saniye, RSS 56.967.168 bayt, disk 22.599.281
  bayt; iki firma yedek/restore geçti. Ölçüm macOS arm64 / Python 3.13.3 /
  SQLite 3.53.2 üzerinde; tam test paketi eşzamanlı çalışıyordu.
- **Geçiş ve girişler:** Gerçek eski kodla çekirdek 75 → 78 / kuyruk 2 → 3
  yükseltme ve yedekten dönüş geçti (2,712 saniye). Yeni komutların 15
  gerçek CLI/engine süreci geçti (11,679 saniye). Ortak platform worker
  SIGTERM/kurtarma kabulü 31,586 saniyede geçti; yeni rapor yakalama
  kesintisi kontrollü istisna testiyle doğrulandı.
- **Dış girdiler:** Tavily N-004, yetkili Nmap N-005, ticari kaynak hakları
  N-001/N-022 ayrı bekler. Geniş STIX/TAXII ve LLM açılmadı. Gerçek müşteri
  sensör verisi kullanılmadı; kabul olayları kontrollü fixture'dır.
- **Dayanak:** [Sekiz madde](docs/roadmap/ENGINE_EIGHT_DELIVERY.md),
  [kullanım](docs/EVIDENCE_WORKFLOWS.md), [mimari karar](docs/decisions/0173-evidence-workflows-and-local-sightings.md),
  [kabul kanıtları](docs/ACCEPTANCE_REVIEW.md).

## Korunacak kararlar

18 Kasım 2026 itibarıyla mevcut kullanıcı tercihleri:

- Şimdilik ücretsiz kaynaklarla ilerliyoruz. İleride ücretli kaynak
  değerlendirmek mümkün; kendiliğinden ücretli servis açılmayacak.
- İlk ticari işletim kendi sunucularımızda olacak. Müşteri sunucusuna
  kurulum şu an ilk teslimin kapsamı değil.
- Bu repo motoru geliştiriyor. .NET/React, kullanıcı/rol/oturum ve platformun
  PostgreSQL yerleşimi tüketici ekibinde; motor firma sınırını ve veri/iş
  sözleşmelerini korumaktan sorumlu. Motor için farklı depo adaptörü
  gerektiğinde sözleşme ve geçiş ayrıca tanımlanacak.
- Firma paketi/abonelik/kullanım hakkı backendde; motor iş sınırları,
  kaynak beklemeleri ve kullanım raporundan sorumludur. Ortak sağlayıcı
  kotası tek merkezden backend entegrasyonunda yönetilecek (N-007).
- Geniş STIX/TAXII dış sistem alışverişi, somut ihtiyaç oluşana kadar
  ertelendi (N-024). Kendi platformunun JSON bağlantısı ve mevcut kaynak/
  araç adaptörleri ayrı kapsamdır. Mevcut sınırlı STIX çıktısı korunuyor.
  LLM ayrı bekleyen başlıktır.
- Geniş marka koruması, e-posta/SMS ve diğer ertelenmiş işler sırf yeni
  kaynak eklendi diye yeniden kapsam içine alınmayacak.
- Saldırı/istismar otomasyonu hedef değil. Mevcut yetkili Nmap kapsamı
  ve pasif kaynak toplama sınırları korunacak.

## Kapanan notlar ve kanıtları

### N-004 — Tavily canlı kabulü

- **Durum:** Kapandı; seçilmiş SecureHup firma kapsamı. **Güncellendi:** 19 Kasım 2026.
- **Önceki durum:** 17 Kasım'da anahtar bekleniyordu; anahtarsız ret
  kontrolü canlı hizmet kabulü sayılmamıştı. Kullanıcı 19 Kasım'da anahtarla
  deneme istedi; değer bu nota veya repoya alınmadı.
- **Bulunan hata:** Tavily yanıttaki sorgunun çift tırnaklarını kaldırdı;
  motor aynı terimleri yanlışlıkla farklı sorgu sayıyordu. 0.170.1 yalnız
  bu gösterim farkını kabul eder; özgün sorgu saklanır, diğer kapsam
  değişiklikleri reddedilir. Eski kayıt ve şema değişmedi.
- **Doğrulanan:** Gerçek genel/haber araması; 10 kayıt, 9 benzersiz URL;
  anahtarsız okuma, aynı istek tekrarı, aralık sınırı ve firma ayrımı.
  Günlük bütçe gerçek rezervasyon üzerinden kontrollü saat/kapalı ağ ile
  sınandı. İlgili 148 test ve son 43 testlik demet geçti; tam paket
  tekrarlanmadı. Ayrıntılar demetlerin örtüştüğünü belirtir.
- **Kullanım:** Dört dış istek; tanı ve son iki yanıtta üç kredi bildirildi.
  İlk ayrıştırılamayan isteğin tüketimi bilinmiyor. Bu hesap bakiyesi değildir.
- **Sonraki geniş test:** Aynı gün 0.170.1 / `68812ce` ile ayrı alanda
  20 sonuç üst sınırı kullanıldı. İki motor sorgusu 21 kapsam/URL kaydı
  sakladı; beş doğrudan sağlayıcı tanısıyla birlikte yedi yeni istekte
  10 kredi bildirildi. Bu sayı önceki dört isteğin yerine geçmez.
  X hedefli gelişmiş aramada bulundu; Instagram açık profil kontrolünde
  bulundu fakat kaynak aramaları kaçırdı. Sosyal keşif eksikleri N-031'de
  açık tutulur; ilk firma araması kabulü bütün sosyal hesapların bulunması
  anlamına gelmez.
- **Anahtar:** Gizli terminal girişinden yalnız süreç belleği/ortamına
  verildi; kalıcı yapılandırma yapılmadı. Sohbette paylaşılan anahtarın
  yenilenmesi ve yenisinin yerel `mentions configure` ile kaydedilmesi önerildi.
- **Sınır:** Tedarikçi canlı sorgusu, Linux zamanlayıcısı veya uzun süreli
  işletim doğrulanmadı. Anahtar çalışması ticari yeniden dağıtım izni sayılmaz.
- **Dayanak:** [Canlı kabul ve tüm bağlantılar](docs/TAVILY_LIVE_ACCEPTANCE.md),
  [test kaydı](docs/ACCEPTANCE_REVIEW.md), [izleme grupları](docs/MENTION_GROUPS.md).

### N-030 — Yayın işleri, ilişki bildirimi ve birikimli kapasite kabulü

- **Durum:** Kapandı; aşağıdaki tanımlı kapsamda Linux teslimi tamamlandı. **Güncellendi:** 19 Kasım 2026.
- **Yetki:** Kullanıcı üç işi birlikte onayladı.
- **Korunacaklar:** Mevcut kuyruk, firma ayrımı, eski belge/karar kanıtı,
  açık insan kararı, yedekli geçiş ve yayıncı koşulları. Başarılı belgeler
  tekrar işinde yeniden indirilmez; kısmi kapsam kesin kayıp sayılmaz.
- **Alınan kanıt:** Linux'ta 22 yeni test; iki firmada 80 belge/160 sürüm,
  118 komut, gerçek SIGKILL sonrası indirmeden toparlanma, bildirim/vaka,
  arşiv ve birlikte geri yükleme geçti. Yerelde gerçek eski kodla 79 → 80
  ve 75 → 80 geçiş/geri dönüş tamamlandı.
- **Canlı kuyruk:** CERT-FR CTI-010 HTML/PDF iki HTTP denemesiyle alındı;
  aynı iş tekrarında yeni indirme/makbuz oluşmadı. 22 kararın 20+2
  bildirim penceresi ve tekrar tekilleştirmesi de doğrulandı.
- **Kabul betiği düzeltmesi:** İlk Linux yükseltme koşusu eski 79 sınırında
  durdu. Betik şema 80'in yalnız beklenen vaka CHECK genişlemesine izin
  verecek şekilde güncellendi; eski satır/rowid denetimi korunur. İlgili
  34 test geçti (iki Linux kontrolü macOS'ta atlandı); son 21 belge/
  bildirim/platform testi de geçti. Eski hızlı/tam koşular durduruldu;
  güncel `9925b5e` ile yeniden başlatıldı. Gerçek Linux 64 → 80 yükseltme
  ve kurulum kurtarması marka/theHarvester kollarında geçti.
- **Eski test verilerinin toplu kontrolü:** Şema73 etiketli iki geçiş testi
  ve şema61 manifest karşılaştırması gerçek tarihî düzene uyarlandı.
  `migrat/schema/legacy/upgrade` kapsamındaki **328 test / 100,212 s**
  hata vermedi; iki Linux denetimi macOS'ta atlandı. Motor kodu değişmedi.
  Önceki koşular bu test düzeneği düzeltmelerinin sonucu sayılmaz.
- **Son hızlı Linux kontrolü:** `ec6514a` koduyla **1.914 test /
  1.302,696 saniye**; hata/atlama yok.
- **Son tam Linux kontrolü:** Aynı `ec6514a` koduyla Python 3.13.18
  üzerinde **3.211 test / 2.244,145 saniye**; hata/atlama yok. İlk
  başarısız/durdurulan koşuların ardından bu tam paket tamamlandı.
- **Kapanış sınırı:** Kapasite yükü 135,909 saniye ve 80 belge/160 sürümdür;
  sürekli hizmet veya daha büyük yük garantisi değildir. Motor, test,
  betik ve CI dosyaları son test edilen commit ile aynı kalır; kapanış
  yalnız belge güncellemesidir. Tavily/Nmap ve ertelenen LLM/STIX ayrı kalır.
- **Kalıcı kanıt:** [Tam Linux paketi](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44490469211),
  [hızlı Linux paketi](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44490404692),
  [bütün kabul sonuçları](docs/ACCEPTANCE_REVIEW.md#01700--yayın-işleri-ilişki-bildirimi-ve-birikimli-kapasite).
- **Dayanak:** [Uygulama kararı](docs/decisions/0175-publisher-jobs-and-review-delivery.md).

### N-016 — Linux kabul süresindeki dalgalanma

- **Durum:** Kapatıldı; başlangıç yükü azaltıldı ve iki Linux kolu ilk koşuda geçti.
  **Güncellendi:** 18 Kasım 2026.
- **Kanıt:** `94f1d9c` ilk koşu ve aynı kodlu tekrarında toplam 120 saniye
  sınırında durdu. Python 3.13 kolu 90,547 saniyede; aynı senaryo yerelde
  38,635 saniyede geçti. Bunlar ilk başarısızlığı silmez.
- **Güncel kanıt:** Aynı motor/test kodunun `cfcfbe3` tanı güncellemesiyle
  Linux Python 3.11 kolu **80,290 saniye**, 3.13 kolu **96,601 saniye**
  ile geçti. 120 saniye toplam, 5 saniye p95, 512 MiB bellek eşikleri
  değiştirilmedi. [Başarılı koşu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44205985536).
  Sonraki `da2b0bb` firma izolasyonu kabulü de başarıyla tamamlandı;
  [koşu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44254840390).
- **0.159.0 kanıtı:** `1601e75` ilk Python 3.11 koşusu **120,015 saniyede**
  durdu. 36 okuma tamamlandı (p95 **1,885 saniye**); 61. komut `alpha/recover`
  başlarken toplam bütçeden **0,666 saniye** kalmıştı. Kurtarma/bütünlük
  kabulü bu ilk denemede tamamlanmadı. Python 3.13 ilk koşuda **94,359
  saniyede**, yalnız başarısız 3.11 işinin aynı commit/sınırlarla tekrarı
  **79,735 saniyede** geçti; tekrar p95 **1,186 saniye**.
  [Koşu ve tekrar](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44259846928).
- **0.160.0 kanıtı:** `de80b54` firma kabulünün iki Python kolu ilk koşuda
  geçti: 3.11 **78,487 saniye** / p95 **1,174 saniye**; 3.13 **95,733
  saniye** / p95 **1,435 saniye**. Eşikler aynı; eski süre aşımlarının kök
  nedenini bu başarılı koşu kapatmaz.
  [Koşu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44263427220).
- **0.161.0 kanıtı:** `259bc5f` Python 3.11 koşusu **120,015 saniyede**
  `TimeoutExpired` ile durdu; 61. `alpha/recover` komutuna **1,114 saniye**
  kalmıştı. Python 3.13 koşusu **120,032 saniyede** `Gated worker exceeded
  wait threshold` hatasıyla durdu; son kayıtlı 54. `alpha/jobs.submit`
  komutu tamamlanmıştı ve o komut öncesinde **3,290 saniye** kalmıştı.
  İki kabul de tamamlanmış sayılmaz. Kesin uygulama/altyapı kök nedeni
  henüz doğrulanmadı; yalnız başarılı tekrar bu maddeyi kapatmayacak.
  [Başarısız koşu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44273412771),
  geçici günlük `/tmp/xti-01610-platform-ci.log`.
- **0.162.0 düzeltmesi:** Komut başlamadan tüm terminal/toplayıcı modülleri
  yükleniyordu. Yerel import ölçümü tam CLI için yaklaşık 570 ms,
  platform için 221 ms. Firma girişi ortak parser ile hafifletildi;
  yalnız gereken engine servisi kuruluyor, kuyruk durumu/kurtarma toplama
  CLI'sını yüklemiyor. İlk aynı yerel kabul **40,845 → 28,288 saniye**;
  36 okuma ve iki gerçek SIGTERM sınırı geçti. Son düzenleme ve Linux
  kabulü ayrıca kaydedilir; bu yerel sonuç Linux'un yerine geçmez.
  [Karar](docs/decisions/0166-platform-cold-start.md).
- **Son yerel kabul:** İşleme göre engine bileşimi de eklendikten sonra
  **25,935 saniye**, 36 okuma p95 **0,308 saniye**, en yüksek okuma RSS
  **47.415.296 bayt**. Her iki SIGTERM sınırı, diğer şirketin eşzamanlı
  çalışması ve bütünlük geçti. 63 komut/kapı kaydı dış artefakttadır:
  `/tmp/xti-01620-final-acceptance.json`. Geniş regresyon 414 test /
  172,719 saniye geçti; bu sonuç tam paket veya Linux sonucu değildir.
- **Linux doğrulaması:** `dba3dbd` Python 3.11.18 kabulü **40,914 saniye**,
  okuma p95 **0,505 saniye**; Python 3.13.18 **51,655 saniye**, p95
  **0,651 saniye**. İkisi de ilk koşuda geçti. 36 okuma, 63 komut/kapı,
  iki gerçek kesinti, firma ayrımı ve bütünlük doğrulandı; 120 saniye
  toplam ve diğer eşikler aynı. [Koşu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44282646610).
  Günlük `/tmp/xti-01620-platform-ci.log`. Bu kapanış genel 7/24 garanti
  veya geniş hızlı test işinin sonucu değildir; önceki başarısızlıklar kalır.
- **İzleme:** Aynı sınırlarla normal Linux CI kabulü sürer.
  Her komutun süreç/CPU/bellek ve modül sayısı, iki kesinti kapısının
  bekleme süresi sentetik raporda tutulur. Ortak başlangıç maliyeti
  ölçüldü; çalıştırıcıdaki bütün hız dalgalanmasının tek nedeni olduğu
  iddia edilmez. Eşikler gevşetilmedi; ilk başarısızlıklar korunur.
- **Dayanak:** [İşletim kabulü](docs/ACCEPTANCE_REVIEW.md#işletim-kabulü).

### N-008 — Yeni kaynakları platformdan yenileme

- **Durum:** Kapandı; seçilmiş URL/hash/MISP kaynakları kapsamında.
  **Güncellendi:** 18 Kasım 2026.
- **Önceki durum:** Platform bu kaynakları yalnız okuyabiliyordu.
- **Kapanma kanıtı:** 0.157.0 ortak kuyrukta plan/kabul, bütçe, ilerleme,
  iptal/kurtarma ve açık tekrar ekler; isteğe bağlı inceleme kaydı vardır.
  38 yeni iş/CLI/platform testi geçti. 272 ilgili test: 270 başarılı,
  macOS'ta iki Linux atlaması; hata yok. İzole firma alanında canlı
  CIRCL/urlscan/MISP → sonuç → inceleme → idempotent tekrar → yedek geçti.
  Firma dışı kapsam ve restore sonrası eski kimlik reddedilir.
  Aynı motor kodunun Linux tam paketi **2.858 test / 1.760,284 saniye**
  ile hatasız ve atlamasız geçti; hızlı kontrol ve iki Python sürümünde
  firma işletim kabulü de başarılıdır.
  [Tam CI](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44204469910).
- **Sınır:** Ortak kota N-007'de açık; genel HTTP/.NET veya bütün motor
  işlemlerinin yazma API'si tamamlanmış sayılmaz.
- **Dayanak:** [Kaynak işleri](docs/SOURCE_JOBS.md), [kabul kaydı](docs/ACCEPTANCE_REVIEW.md).

### N-014 — 0.156.0 için tek koşuda temiz tam paket kaydı

- **Durum:** Kapandı. **Güncellendi:** 18 Kasım 2026.
- **Önceki kanıt:** macOS adayında 2.819 test; 2.814 başarılı, dört Linux
  atlaması ve tek `killpg(SIGKILL)` izin reddi. Ayrı tekrarlar ve son küçük
  düzeltmenin 115 testi önceki kabul belgesinde korunur.
- **Kapanma kanıtı:** Son 0.156.0 commit'i
  `9266fbfa4b27406cc29c09cd3404b04e3ec59559` üzerinde Ubuntu/Python 3.13
  tam paket: **2.820 test / 1.134,595 saniye; tamamı başarılı**, atlama yok.
  [Linux tam kontrol](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44200653217).
- **Ayrı CI durumu:** Aynı commit'in hızlı paketi 15 dakika iş sınırına
  takıldı; test hatası olarak sunulmaz. 0.157.0 sınırı 25 dakikaya çıkarır,
  test çıkarmaz. Yeni sürümün hızlı kontrolü 1.561 test ile geçti;
  tam paket ve firma kabulü [kabul kaydında](docs/ACCEPTANCE_REVIEW.md) ayrıdır.
- **Dayanak:** [Önceki yerel sonuçlar](docs/ACCEPTANCE_REVIEW.md#01560--kayıtlı-inceleme-ve-değişim-kabulü).

### N-010 — Son commit için tam test kabul kaydı

- **Durum:** Kapandı; 0.154.0 / `681a728` kabulü.
  **Güncellendi:** 17 Kasım 2026.
- **Önceki durum:** 2.761 test / 1.337,319 saniyelik turda iki eski
  kaynak envanteri beklentisi başarısız olmuştu. Beklentiler düzeltildikten
  sonra tam paketin yeniden çalışması bekleniyordu; o eski başarısız sonuç
  sonradan başarılı olarak değiştirilmedi.
- **Kapanma kanıtı:** `681a728c0397bba0d48172d8b0d9a1b1aacf563c` commit'inin
  ayrı, değiştirilmemiş kopyasında `umask 002; ./scripts/check`:
  **2.762 test / 1.420,951 saniye; 2.758 başarılı, dört Linux atlaması,
  hata yok**. macOS arm64/Python 3.13.3; kaynak dosya özetleri öncesi/sonrası
  aynı. Linux `/proc` ve systemd testleri bu makinede kabul edilmiş sayılmaz.
- **Dayanak:** [Sabit commit kabulü](docs/ACCEPTANCE_REVIEW.md#01540--sabit-commit-üzerinde-tam-test).
  Yerel günlük `/tmp/xti-01540-baseline-brfeg8r6/full-check.log`; geçici
  dosyadır. Bu sonuç daha sonra eklenen 0.155.0 öncelik özelliğinin tam
  paket sonucu değildir; onun 231 farklı ilgili testi ayrı kayıtlıdır.

### K-001 — Kaynak envanteri testleri ve Linux teslim kontrolleri

- **Durum:** Kapandı; yalnız aşağıdaki kapsam. **Tarih:** 17 Kasım 2026.
- Eski kaynak envanteri beklentileri `8006487` ve `681a728` ile düzeltildi;
  ilgili testler tekrar geçti. `681a728` için
  [hızlı kontrol](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44090225404),
  [Linux kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44090225389) ve
  [marka araçları kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44090225418) geçti.
- Aynı ürün kodunun `8006487` commit'inde
  [marka araçları/theHarvester yükseltme ve kurtarması](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44089725560) ile
  [firma izolasyonu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44089627844) geçti.
  `681a728` yalnız test değişikliğidir. Bunlar Nmap canlı kabulünü,
  Tavily kabulünü veya N-010'daki tam paket tekrarını kapatmaz.

## Sıradaki çalışma

**0.171.0 teslim / doğruluk çalışması — 19 Kasım:** Kullanıcı son sosyal
keşif paketinin GitHub/Linux teslimiyle ve farklı firmalarda daha geniş
doğruluk ölçümüyle devam edilmesini onayladı. Yeni keşif/taşıma testleri
her push için hızlı kontrol listesine eklendi. Gerçek hesap referansları
resmî sitelerden, motor sonucu görülmeden önce kaydedilecek; bulunan,
doğrulanan, erişilemeyen ve referans dışındaki adaylar ayrı ölçülecek.
Varsayılan ücretsiz akış; yeni Tavily harcaması, Firecrawl, LLM, geniş
STIX/TAXII veya firma izleme/vaka genişletmesi bu çalışmayla başlamaz.
GitHub ve Linux sonuçları tamamlandıkça ayrı kabul kaydı eklenecek.

**0.170.1:** Yeni özellik paketi açılmadı. Kullanıcının anahtarla denemesi
sırasında bulunan Tavily sorgu yanıtı uyumsuzluğu giderildi; seçilmiş
firma canlı kabulü N-004 ile kapandı. Nmap hedef/port girdisi N-005 ve
diğer bağımsız ticari/işletim koşulları kendi notlarında kalır.

**0.170.0 teslimi tamamlandı:** Kullanıcının birlikte istediği yayın
işleri, ilişki bildirimi/vaka bağlantısı ve iki firmalı birikimli kapasite
kabulü N-030 ile kapatıldı. Son Linux tam paketi 3.211 test, hızlı paket
1.914 test; hata/atlama yok. Kullanım ve güncelleme adımları
[yayın işleri belgesinde](docs/PUBLISHER_JOB_DELIVERY.md), ölçülen yük ve
sınırlar [kabul kaydında](docs/ACCEPTANCE_REVIEW.md) bulunur. Yeni bir
geliştirme başlığı bu kapanışla kendiliğinden başlatılmaz; aşağıdaki
önceki sürüm kayıtları ve ayrı bekleyen notlar korunur.

**0.168.0:** Kullanıcının birlikte istediği sekiz madde uygulandı; tanımlı
yerel kabul, eski kodla geçiş ve iki test beklentisinin düzeltilmesiyle
tamamlandı (N-028). Yeni Linux/CI veya canlı müşteri kabulü sayılmaz.
Güncel teslim durumu [sekiz maddelik tabloda](docs/roadmap/ENGINE_EIGHT_DELIVERY.md).
N-026/N-027'de önceki sürüm için yazılan bekleyen motor başlıkları artık
bu paketin kapsamındadır; ticari izin ve gerçek müşteri bağlantısı ayrı kalır.

**18 Kasım 2026 kullanıcı kararı:** Geniş STIX/TAXII, 1–7 sonrasında
otomatik sıradaki geliştirme olmayacak; dış sistem alışverişi ihtiyacına
kadar ertelendi (N-024). Odağımız kendi platformumuzun motorudur. Mevcut
JSON sözleşmesi, kaynaklar ve araç adaptörleri korunur. LLM ayrıca bekler.

**Önceki kabul tamamlandı:** 0.162.0 N-016'daki başlangıç yükünü azalttı;
eşikler/kurtarma testleri korundu. `dba3dbd` Linux firma kabulü iki Python
kolunda ilk koşuda geçti; N-016 kanıtlarıyla kapatıldı. Linux ve marka
kurulumu da geçti. `0c130bb` [hızlı kontrolü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44283192210)
**1.684 test / 1.070,277 saniye** ile başarılı. Önceki `dba3dbd` hızlı
kontrolü not gönderimi sonrasında `cancelled` olmuştu; test başarısızlığı
veya tamamlanmış kabul sayılmaz. 0.163.0'ın test/kabul sonucu aşağıdaki
sürümün [kabul kaydında](docs/ACCEPTANCE_REVIEW.md) ayrı tutulur. Önceki
0.161.0 iki firma kabulü süre aşımı N-016'da korunur.

**Uygulandı:** 0.157.0 URL/hash/MISP yenilemesini ortak firma kuyruğuna
bağlar; açık kaynak seçimi, bütçe, ilerleme, iptal/kurtarma, tekrar ve
isteğe bağlı son inceleme kaydı vardır. N-008'in test ve kapanma kaydı
yukarıdadır. Genel akış kurucusu veya ortak sağlayıcı kotası tamamlanmış
sayılmaz. Bekleyen Tavily/Nmap girdileri N-004/N-005'te korunur.

**Motor/backend ayrımı güncellendi:** N-007'deki merkezi kota ve abonelik
işi backend entegrasyonunda kalır. 0.158.0 motorun verilen iş sınırını
uygulamasını ve ölçülmüş/belirsiz tüketimini bildirmesini tamamlar.

**Uygulandı:** 0.159.0 N-009'un kayıtlı CNAME ve gözlenmiş TLS dilimini
ortak araştırmaya taşır; özgün kanıtlar ve firma kapsamı korunur. Yeni
API/LLM gerekmez. Öncelik v2'nin ilk incelemesi yeni politika başlangıcıdır;
eski v1 kayıtları değiştirilmez.

**Uygulandı:** 0.160.0 mevcut tedarikçi adayını, insan onayı/ret/değişim
geçmişini ve envanteri ortak araştırma/öncelik/incelemeye ekler. Yeni
sağlayıcı, API veya migration yoktur. Model 2 uyumu N-018'de korunur.

**Uygulandı:** 0.161.0 kayıtlı pasif alt alan adayını ve insan sahiplik
kararlarını ortak araştırma/öncelik/incelemeye ekler. Aktif kapsam değişmez;
yeniden keşif kararı sıfırlamaz. Kanıt ve çalışma sınırları N-019'da korunur.

**Uygulandı:** 0.162.0 pasif keşif kaynaklarının son çalışma durumunu
ortak araştırmada aday kanıtından ayrı gösterir: hiç sorgulanmadı,
başarılı/boş, kısmi veya başarısız. Önceki complete yanıt korunur (N-020).

**Uygulandı:** 0.163.0 tedarikçi kaynak iddiaları, izleme karşılaştırmaları
ve hesaplanan inceleme kartını ortak araştırma/öncelik/incelemeye bağlar.
Anlam, hacim ve eski kayıt uyumu N-021'de korunur.

**0.164.0 toplu paket tamamlandı:** Roadmap 1–7'nin tanımlanan motor kapsamı,
yerel ve 30 dakikalık Linux hacim/iptal/arşiv/yedek/eski sürüme dönüş kabulü,
tam Linux paketi (3.039 test) ve canlı pasif kaynak akışı geçti.
[Kullanım](docs/INVESTIGATION.md), [kanıt ve sınırlar](docs/ACCEPTANCE_REVIEW.md).
Geniş STIX/TAXII ve LLM bu istek kapsamında açılmadı. Tavily, yetkili Nmap
ve ticari kaynak kararları kendi notlarında bekler.
Backendin oturum/abonelik/merkezi kota yönetimi bu sıraya dahil değildir.

Bu sıra gelişme ve kullanıcı kararlarıyla güncellenir; burada yazılması
özelliğin tamamlandığı anlamına gelmez.
