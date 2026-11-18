# XTI — Unutulmaması gereken notlar

Son güncelleme: **18 Kasım 2026**. Başlangıç kaydı: **0.154.0 / şema 74**.
Güncel çalışma: **0.157.0 / çekirdek 75 / iş kuyruğu 2**.

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

### N-004 — Tavily canlı kabulü

- **Durum:** Beklemede; kullanıcı anahtarı daha sonra ekleyecek.
  **Güncellendi:** 17 Kasım 2026.
- **Not:** Anahtar yokken doğru hata verilmesi, gerçek firma aramasının
  tamamlandığı anlamına gelmiyor.
- **Kapanma koşulu:** Anahtar hazır olduğunda seçilmiş firma/tedarikçiyle
  gerçek arama, içerik saklama, firma ayrımı ve sorgu bütçesi davranışını
  doğrulamak. Anahtar sohbet veya repoya konmayacak; beklerken diğer işler sürecek.
- **Dayanak:** [Kabul incelemesi](docs/ACCEPTANCE_REVIEW.md),
  [firma izleme grupları](docs/MENTION_GROUPS.md).

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

- **Durum:** Açık; ölçekli işletimden önce. **Güncellendi:** 17 Kasım 2026.
- **Not:** Yeni URL/hash isteklerinin aralık ve bekleme kaydı seçili veri
  alanında uygulanıyor. Farklı firma alanları/sunucular için ortak çıkış
  kotası henüz bu mekanizma tarafından yönetilmiyor.
- **Sonraki iş:** Çoklu çalıştırıcıya geçerken firma bütçeleri ile ortak
  sağlayıcı kotasını birlikte uygulamak ve eşzamanlılıkta doğrulamak.
- **Dayanak:** [Mevcut sınırlar](docs/INDICATOR_ENRICHMENT.md#sonuçların-anlamı),
  [MTR-05/06](docs/roadmap/ENGINE_INTEGRATION_ROADMAP.md#62-iş-paketleri-ve-tamamlanma-ölçütleri).

### N-009 — Araştırmanın kapsam sınırları

- **Durum:** Bilinen sınır. **Güncellendi:** 17 Kasım 2026.
- **Not:** Araştırma en fazla iki ilişki adımıyla çalışıyor. URL kaynağı
  ilk 20 arşiv sonucunu alıyor; bütün arşivde ters yönde arama yok.
  CNAME, sertifika ve tedarikçi ilişkilerinin tamamı ortak araştırmaya
  taşınmış değil. Ek sonuç ve eksik kapsam görünür tutulmalı.
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

### N-016 — Linux kabul süresindeki dalgalanma

- **Durum:** Bilinen sınır; son kabul geçti, süre dalgalanması izlenecek.
  **Güncellendi:** 18 Kasım 2026.
- **Kanıt:** `94f1d9c` ilk koşu ve aynı kodlu tekrarında toplam 120 saniye
  sınırında durdu. Python 3.13 kolu 90,547 saniyede; aynı senaryo yerelde
  38,635 saniyede geçti. Bunlar ilk başarısızlığı silmez.
- **Güncel kanıt:** Aynı motor/test kodunun `cfcfbe3` tanı güncellemesiyle
  Linux Python 3.11 kolu **80,290 saniye**, 3.13 kolu **96,601 saniye**
  ile geçti. 120 saniye toplam, 5 saniye p95, 512 MiB bellek eşikleri
  değiştirilmedi. [Başarılı koşu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44205985536).
- **Sonraki iş:** Süre aşımı tekrarlanırsa artık saklanan tamamlanmış
  ölçümler/son komutla aşamasını incelemek. İlk başarısızlıkların kesin
  kök nedeni iddia edilmiyor; uygulama hatası düzeltildi diye sunulmaz.
- **Dayanak:** [İşletim kabulü](docs/ACCEPTANCE_REVIEW.md#işletim-kabulü).

## Korunacak kararlar

17 Kasım 2026 itibarıyla mevcut kullanıcı tercihleri:

- Şimdilik ücretsiz kaynaklarla ilerliyoruz. İleride ücretli kaynak
  değerlendirmek mümkün; kendiliğinden ücretli servis açılmayacak.
- İlk ticari işletim kendi sunucularımızda olacak. Müşteri sunucusuna
  kurulum şu an ilk teslimin kapsamı değil.
- Bu repo motoru geliştiriyor. .NET/React, kullanıcı/rol/oturum ve platformun
  PostgreSQL yerleşimi tüketici ekibinde; motor firma sınırını ve veri/iş
  sözleşmelerini korumaktan sorumlu. Motor için farklı depo adaptörü
  gerektiğinde sözleşme ve geçiş ayrıca tanımlanacak.
- LLM ve geniş STIX/TAXII en son. Mevcut sınırlı STIX çıktısı korunuyor.
- Geniş marka koruması, e-posta/SMS ve diğer ertelenmiş işler sırf yeni
  kaynak eklendi diye yeniden kapsam içine alınmayacak.
- Saldırı/istismar otomasyonu hedef değil. Mevcut yetkili Nmap kapsamı
  ve pasif kaynak toplama sınırları korunacak.

## Kapanan notlar ve kanıtları

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

**Uygulandı:** 0.157.0 URL/hash/MISP yenilemesini ortak firma kuyruğuna
bağlar; açık kaynak seçimi, bütçe, ilerleme, iptal/kurtarma, tekrar ve
isteğe bağlı son inceleme kaydı vardır. N-008'in test ve kapanma kaydı
yukarıdadır. Genel akış kurucusu veya ortak sağlayıcı kotası tamamlanmış
sayılmaz. Bekleyen Tavily/Nmap girdileri N-004/N-005'te korunur.

**Sonraki öneri, henüz uygulanmadı:** Birden fazla firma birlikte iş
gönderdiğinde ortak sağlayıcı kotasını ve firma bütçesini ölçerek kurmak
(N-007); kuyruk/disk/süre ölçümlerini gerçek işletim denemesiyle kaydetmek.
Ücretli API/LLM bunun ön koşulu değildir.

Bu sıra gelişme ve kullanıcı kararlarıyla güncellenir; burada yazılması
özelliğin tamamlandığı anlamına gelmez.
