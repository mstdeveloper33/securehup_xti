# Linux kullanım raporunun değerlendirilmesi

## 0.170.0 — Yayın işleri, ilişki bildirimi ve birikimli kapasite

19 Kasım 2026. Uygulama ve Linux kabul kodu:
[`53a2eaf0d7eae81f18870680b87710ee16bcddce`](https://github.com/mstdeveloper33/securehup_xti/commit/53a2eaf0d7eae81f18870680b87710ee16bcddce).
Çekirdek 80, kuyruk 3, kaynak işi modeli 5. Önceki iş modelleri 1–4
ve dış JSON sözleşmesi 1 korunur. İstenen üç işin
[kullanımı ve sınırları](PUBLISHER_JOB_DELIVERY.md) ayrı belgelenmiştir.

| Kontrol | Sonuç ve kanıt |
| --- | --- |
| Yeni davranışlar, mimari ve engine sözleşmesi | İlk kodda yerelde **46 test / 17,587 s**, hata/atlama yok. Yeni dört modül ilk commit'te 22, ek çok pencereli bildirim kontrolüyle 23 test içerir. |
| Linux yayın işi kabulü | **Başarılı.** Ubuntu 24.04 x86_64 / Python 3.13.18 / SQLite 3.45.1; 22 yeni test **11,553 s**. [Çalışma](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44485446767). |
| İki firmalı HTML/PDF kapasite ve kurtarma | Aynı Linux çalışmasında **135,909267 s**, 118 ölçülen komut, 80 belge / 160 sürüm. Ölçümler aşağıdadır. |
| Gerçek 0.169.0 koduyla geçiş ve geri dönüş | `484976bd92eb54cec39c077e495022f49ba3d71a` ile üretilmiş veri: **79 → 80**, 167 eski tablonun 17 satırı ve rowid'leri aynı; iki belge sürümü, insan kararı, eski vaka kanıtı ve v4 iş payload'u korundu. Yeni bildirim eski vakaya bağlandı. Eski kod yeni şemayı reddetti; eski yedekten yeni workspace kimliğiyle dönüldü. **3,056007 s**, macOS/Python 3.13.3. |
| Daha eski gerçek kodla geçiş | `dbee4ab18349656177fc90aee65e8c7ddffdb10d`: çekirdek **75 → 80**, kuyruk **2 → 3**; v2 iş ve kimlikler korundu. Eski kodla özgün yedeğe dönüş geçti; **1,577572 s**. |
| Normal kurulum ve theHarvester | Başarılı. [Marka/PDF/RSS kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44485401780), [theHarvester kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44485401635). |
| Firma izolasyonu ve gerçek süreç kurtarması | Python 3.11 / 3.13 kolları başarılı. [Çalışma](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44485401541). |
| Hızlı Linux regresyonu | Güncel koşu bekleniyor; ilk koşu eski kabul betiği nedeniyle durduruldu. |
| Tam Linux paketi | Güncel koşu bekleniyor; ilk koşu eski kabul betiği nedeniyle durduruldu. |

Test demetleri örtüşür; sayıları toplanmaz. Yerelde geliştirme sırasında
başlatılan bir tam koşu, altı adım sınırı kesinleştirilirken durduruldu;
tamamlanmış veya başarılı paket sayılmaz. Teslimin tam sonucu yukarıdaki
Linux çalışmasıdır; bitmeden başarılı kabul edilmez.

**Kabul betiği düzeltmesi:** İlk [Linux yükseltme çalışması](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44486436950)
iki araçta da aday şema kontrolünde durdu: test betiği yalnız 64–79'u
tanıyordu. Yeni 80 açıkça eklenir; yalnız tanımlı `case_evidence` CHECK
genişlemesi kabul edilir, eski bütün satır/rowid/diğer DDL denetimi korunur.
Bozuk satır ve beklenmeyen CHECK değişikliği yeni testte reddedilir.
Eski betiği içeren [hızlı](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44485401533)
ve [tam](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44485435285)
koşular tamamlanmadan durduruldu; başarılı paket sayılmaz.
Son betik/migration/CI demeti **34 test / 13,154 s**: hata yok, iki
Linux `/proc` kontrolü macOS'ta atlandı. Son belge/bildirim/platform demeti
**21 test / 10,962 s**, hata/atlama yok. Motorun `src` kodu, bağımlılıklar
ve kapasite betiği `53a2eaf` ile aynıdır.

**Canlı yayın işi:** Ayrı `/tmp` alanında seçilmiş CERT-FR CTI-010 HTML ve
PDF, gerçek `./xti source-jobs` plan → submit → worker → result yoluyla
alındı. **7,867149 s / iki HTTP denemesi**; aynı anahtarlı submit aynı
işi döndürdü, tamamlanmış worker tekrarında yeni alım yapılmadı.
İş `89ff513f-3d0e-4d26-8779-509fcaa29ec1`; HTML makbuzu
`a679df84-165e-45ea-92a6-fb0e4d12fbc2`, PDF makbuzu
`7da9988b-bc8d-4337-999c-45161402021a`. Bu tek yayıncıdaki iki belgeyi
doğrular; genel firma web araması veya tüm kaynakların canlı kabulü değildir.
Geçici kanıt `/tmp/xti-01700-live-publisher.json`.

### Ölçülen yük ve sonuç

İki firma; firma başına 40 seçilmiş belge, belge başına iki sürüm.
HTML ve gerçek pypdf ile ayrıştırılan PDF sayıları eşittir. Belgeler
kontrollü ve sıkıştırılabilir; HTML yaklaşık 128 KB dolgu ve 4 KB metin,
PDF yaklaşık 4 KB metin içerir. Kaynak yanıtı kontrollüdür; ayrıştırıcı,
terminal/platform süreçleri, kuyruk, veri tabanı, arşiv ve yedek gerçek
uygulamadır. Dış ağ kapalıdır; internetteki sağlayıcı kapasitesi ölçülmez.

| Ölçüm | Linux x86_64 | macOS arm64 |
| --- | --- | --- |
| Python / SQLite | 3.13.18 / 3.45.1 | 3.13.3 / 3.53.2 |
| Mantıksal CPU | 4 | 10 |
| Kabul süresi | 135,909267 s | 127,767968 s |
| Ölçülen komut | 118 | 118 |
| Seçilmiş okumaların p95 süresi | 0,486813 s | 0,444293 s |
| Beş belgeli worker p95 süresi | 4,877962 s | 4,561898 s |
| En yüksek tek süreç RSS | 55.951.360 bayt | 67.256.320 bayt |
| Yedekler/geri yüklemeler dahil geçici alan | 29.665.906 bayt | 29.665.895 bayt |
| Kontrollü HTTP denemesi / dış ağ isteği | 161 / 0 | 161 / 0 |

Önceden tanımlı kabul eşikleri: okuma p95 ≤ 5 s, worker p95 ≤ 60 s,
tek komut ≤ 90 s, tek süreç RSS ≤ 512 MiB, yedekler dahil alan ≤ 512 MiB.
RSS aynı anda çalışan süreçlerin toplamı değildir. Okuma p95 yalnız
bu senaryonun `reports.list`, `relationships.candidates` ve
`sources.jobs.result` çağrılarını kapsar; bütün motor işlemlerine genellenmez.

İki koşunun başlangıç ve son kaynak/betik özeti aynıdır:
`c35e3b22999c2550f8314f0bd88066a850dcf598eec8372e04709252b238f386`.
Bu özet `src/**/*.py`, `pyproject.toml` ve kapasite betiğini kapsar.

### Doğrulanan davranış ve kalan sınırlar

- Plan/kabul ağ kullanmaz; seçilmiş URL ve belge adımı terminalde görünür.
  HTML/PDF, yönlendirme, 429/503, kısmi tekrar, süre ve iptal sınandı.
  En fazla beş belge / altı toplam adım plan aşamasında doğrulanır.
  Altıncı adım sonundaki iptal mevcut kuyruk 3 olay sınırına sığar.
- Belge core commit'inden sonra, ilerleme makbuzu öncesi **gerçek SIGKILL**
  uygulandı. Açık recover/retry başarılı belgeyi yeniden indirmeden buldu;
  eski kesilmiş işin bilinmeyen tüketimi sıfır olarak gösterilmedi.
- Bildirim aynı karar sürümü/kanıt değişiminde tekilleşti; okundu durumu
  korundu. Eksik kapsam kesin kayıp sayılmadı. Bozuk/silinmiş makbuz başarı
  gibi sunulmadı. Başka firmanın bildirimi okunamadı veya vakaya bağlanamadı.
- Eski/yeni kanıt vaka içinde donduruldu. Yeni insan kararı ve günlük
  arşivi eski vaka kanıtını değiştirmedi. İki firma için çekirdek+kuyruk
  yedeğinden belge sürümleri, bildirimler ve iş sonuçları geri geldi.
- Gerçek **64 MiB özgün nesne sınırı**, sekiz adet 8 MiB kontrollü nesneyle
  ayrıca sınandı: dokuzuncu kayıt reddedildi; mevcut nesne ve makbuzlar
  değişmedi. Normal hacim ölçümü sınırın üstüne çıkma denemesi değildir.
- Bu yaklaşık iki dakikalık birikimli kabul, uzun süreli 7/24 hizmet veya
  bütün kaynaklarda başarı garantisi değildir. Yayıncı allowlist'i, atıf,
  32 MiB rapor günlüğü ve 32 MiB/10.000 bildirim sınırları korunur.
  Tavily, yetkili Nmap, geniş STIX/TAXII ve LLM ayrı notlarında kalır.

Geçici kanıtlar: `/tmp/xti-01700-publisher-capacity-final.json`,
`/tmp/xti-01700-linux-publisher.json`,
`/tmp/xti-01700-real79-upgrade-final.json`,
`/tmp/xti-01700-engine-upgrade.json` ve ilgili test logları.
Kalıcı kanıt bu kayıt, sürümlü test/betikler ve GitHub çalışma loglarıdır;
test veri tabanları ve ham yayın metinleri repoya eklenmez.

## 0.169.0 — GitHub ve Linux teslimi

19 Kasım 2026. Teslim edilen kod:
[`071a076778c0f1f6e297c91e76dbc918cda21d92`](https://github.com/mstdeveloper33/securehup_xti/commit/071a076778c0f1f6e297c91e76dbc918cda21d92).
Önceki 0.165–0.169 yerel değişiklikleri birlikte `main` dalına gönderildi.
Çekirdek 79, kuyruk 3; aşağıdaki sonuçlar bu kesin commit'e aittir.
Kaynak kodundan sonraki güncelleme komutları/belge düzeltmeleri ayrı tutulur.

| Linux kontrolü | Sonuç ve kanıt |
| --- | --- |
| Normal kurulum; Python 3.11.18 / 3.12.16 | **Başarılı.** Her Python sürümünde 125 kurulum testi; gerçek `./setup`, tekrar kurulumda aynı ortam/veri, engine okuması ve yeni dizine yedekten dönüş. Maigret, Sherlock, feedparser ve pypdf kurulum doğrulayıcısından geçti. [Çalışma](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44475782480). |
| theHarvester temiz kurulumu; Python 3.11.18 | **Başarılı.** 104 ilgili test; sabit araç kurulumu, indirme engellenmiş tekrar, mevcut veri hash'lerinin korunması ve yedekten dönüş. [Çalışma](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44475782382). |
| Firma izolasyonu; Python 3.11 / 3.13 | **Başarılı.** İki firma, 100/1.000 kayıt ve Python başına 36 okuma; kuyruk çekişmesi ve gerçek SIGTERM sonrası kurtarma. p95 süreç süresi sırasıyla 0,827677 / 0,967448 saniye. [Çalışma](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44475782373). |
| Eski sürümden yükseltme ve kurulum kesintisi | **Başarılı.** Marka araçları ve theHarvester için eski gerçek kurulumdan 64 → 79 yedekli geçiş; eski satır/kimlik/kanıtların korunması, eski kodun yeni şemayı reddetmesi, ayrı dizine eski yedekten dönüş ve gerçek kurulum alt süreci kesintisinden kurtarma. [Çalışma](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44475855410). |
| Hızlı regresyon; Python 3.11 | **Başarılı.** 1.890 test / 1.264,694 saniye; hata ve atlama yok. [Çalışma](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44475782389). |
| Tam paket; Python 3.13.18 | **Başarılı.** 3.187 test / 1.908,627 saniye; hata ve atlama yok. [Çalışma](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44475846163). |

Bunlar Ubuntu 24.04 x86_64 üzerindeki tanımlı kurulum/yerel veri
senaryolarıdır. Gerçek müşteri taraması, Tavily canlı sorgusu, gelişmiş
Nmap canlı kabulü veya uzun süreli 7/24 hizmet ölçümü olarak sunulmaz.
Tam paket tek işte çalıştırılır; yükseltme workflow'unda yalnız `upgrade`
seçildiği için oradaki ikinci tam paket ve işletim işi bilerek çalıştırılmaz.
Örtüşen demet sayıları toplanmaz.

Altı workflow'un tamamı aynı `071a076` koduyla başarılı tamamlandı.
Yeni yayıncı/yeniden inceleme/arşiv modüllerinin 36 testi hızlı Linux
paketinde de geçti. Aşağıdaki önceki macOS koşusunda görülen test düzeneği
hatasının düzeltmesi, bu tamamlanmış Linux tam koşusunda yer alır.
Belge kapanışında kaynak, test, kurulum ve CI dosyalarının test edilen
commit ile aynı olduğu ayrıca doğrulanır; yalnız Markdown belgeleri değişir.

Yerel kanıtlar `/tmp/xti-01690-linux-delivery.json`,
`/tmp/xti-01690-linux-runs.json` ve ilgili `linux-*.log` dosyalarıdır.
Kalıcı kanıt, yukarıdaki GitHub çalışma bağlantıları ve bu kabul kaydıdır;
geçici loglar, sırlar ve test veritabanları repoya eklenmez.

## 0.169.0 — Yayıncı metni, yeniden inceleme ve günlük arşivi

İlk uygulama turunun yerel kaydı: 19 Kasım 2026; macOS arm64 / Python 3.13.3.
Bu aşamada çalışma ağacı yereldi;
önceki 0.165–0.168 değişiklikleri korunmuştur. Bu turda commit/push veya
Linux teslimi yapılmadı. Çekirdek 79, kuyruk 3, kaynak işi 4.

| Kontrol | Sonuç |
| --- | --- |
| İlgili geniş regresyon | 191 test / 58,846 s; başarılı, iki Linux ortamına özgü atlama. |
| Son yayıncı/rapor/araştırma/karar/arşiv demeti | 80 test / 28,465 s; hata/atlama yok. |
| Son kodla sınırlar ve kurulum sözleşmesi | 44 test / 16,408 s; hata/atlama yok. |
| Kurulum kilidi ve paket doğrulaması | 56 test / 26,408 s; hata/atlama yok. |
| Kurulu gerçek ortam doğrulayıcısı | Mutlak `.venv` yoluyla Maigret 0.6.6, Sherlock 0.16.2, feedparser 6.0.14 ve pypdf 7.1.1 birlikte doğrulandı; dış kaynak taranmadı. |
| Gerçek terminal kabulü | 17 ayrı CLI/engine süreci / 12,346056 s; değişen dayanak → yeni karar → arşiv → restore → eski belge/ilk makbuz aynı. Kontrollü yerel belge, ağ yok. |
| Gerçek süreç kesintisi | Arşiv gövdeleri taşındıktan sonra, commit öncesi SIGKILL; aynı planla tekrar ve iki ayrı kurtarma yedeği doğrulandı. |
| Çekirdek 78 → 79 | Önceki günlük satırları/hash'leri korunuyor; geçiş öncesi yedek ve yeni arşiv işlemi geçti. |
| Gerçek eski kodla geçiş/geri dönüş | `dbee4ab18349656177fc90aee65e8c7ddffdb10d` ile oluşturulmuş alan; çekirdek 75 → 79, kuyruk 2 → 3, eski iş ve kimlikler korundu; eski kod yeni şemayı reddetti ve özgün yedekten yeni alana döndü. 1,654699 s. |
| Çok firmalı kabul | Aynı yayıncı URL/tekrar anahtarı ayrı kayıtlar; yanlış workspace ağ çağırmadan reddedilir. Soğuk gövde ve kaynak nesnesi platform yedeğiyle döner, eski workspace reddedilir. |

Test demetleri örtüşür; sayıları toplanıp tek test sayısı olarak sunulmaz.
Saklı belgeler yeni kurulum pin'i veya aktif yayıncı kapsamı değiştiğinde
eski `publisher-text-v1` politikasıyla okunur; bu tarihî kapsam yeni ağ
isteğine izin vermez. PDF eksik/bozuk/şifreli/boş/süre sınırı, URL/DNS/
yönlendirme, kaynak hatası, idempotency çatışması, atomik geri alma,
arşiv hash/boyut/olay zinciri ve salt okuma sınırları ayrıca sınandı.

**Tam paket:** `./scripts/check` tamamlandı: **3.186 test / 1.429,020 s;
3.181 başarılı, bir eski test düzeneği hatası, dört Linux atlaması**.
Koşu exit 1 ile bitti; başarılı tam koşu diye sunulmaz. Tek hata
`test_verifier_passes_install_lock_to_its_child_without_unlocking` içindeydi:
sahte kurulum dizini kullanan kilit testi, yeni PDF doğrulayıcısını
taklit etmiyordu. Testin odağı korunarak bu bağımlılık da taklit edildi;
kurulumla ilgili 56 test yeniden geçti. Gerçek kurulu ortam doğrulayıcısı
da ayrıca geçti. Atlamalar Linux `/proc` ve systemd gerektirir.

Tam koşu başladıktan sonra saklı yayınların eski politika/sürümle okunması
güçlendirildi ve buna bir test eklendi. Son kodun 44 testlik sınır demeti,
80 testlik rapor demeti ve 56 kurulum testi yukarıda ayrı kayıtlıdır;
sayıları toplanmaz. Yeni dört test modülü toplam 36 test içerir; bunların
35'i tam koşu başlangıcında vardı. Ayrıca yükseltme betiğinin sonuç şema
alanı ve kurulum hata önerisindeki komut düzeltildi. Son çalışma ağacı
için ikinci tam koşu başlatılmadı.

Tam koşu logu `/tmp/xti-01690-full.log`; başlangıç/son girdiler ve
değişen sekiz dosya `/tmp/xti-01690-full-input.json` ile
`/tmp/xti-01690-current-input.json` içindedir. 1.135 dosyalık başlangıç
manifest SHA-256:
`1c5957a2b3e0447ffe194a0cfcc49f19e4d34a40840f9d01761feaf318010192`.
Son kod manifest SHA-256:
`00bcfd387ae8fc38a35290b94bf67b5e013a09a7b6092f10f4a1f693a4dd7e03`.
Son ilgili testlerden sonra çalışma/test/betik kodunun değişmediği
doğrulandı. Toplu yerel kanıt kaydı `/tmp/xti-01690-verification.json`.

### Canlı yayıncı kabulü

Gerçek müşteriye tarama yapılmadı. Yayıncıların açık içerikleri yalnız
`/tmp/xti-01690-live` alanında alındı; ham içerik repoya konmadı.

| Kaynak | Özgün gövde | Çıkarılmış UTF-8 metin | Kanıt |
| --- | --- | --- | --- |
| [CERT-FR CTI-010 HTML](https://cert.cyber.gouv.fr/cti/CERTFR-2026-CTI-010/) | 22.365 bayt | 2.807 bayt | Çalışma `01da7399-dfc0-46c7-b3c4-aa8ff6fa9123`; HTML ana metni. |
| [Aynı CERT-FR raporunun PDF'si](https://cert.cyber.gouv.fr/uploads/CERTFR-2026-CTI-010.pdf) | 1.192.133 bayt | 15.968 bayt | Çalışma `df0bc212-e455-46e9-8116-7b672051ef34`; pypdf 7.1.1, 9 sayfa. |
| [NCSC rehber HTML'si](https://www.ncsc.gov.uk/collection/top-tips-for-staying-secure-online) | 230.787 bayt | 2.290 bayt | Son çalışma `78c7ce49-943c-4c88-bcab-9b8e40d03f9b`; SVG ikon başlığı ana başlığa karışmıyor. |

PDF özgün SHA-256:
`a6cf6915cec82d65b1e2f91595a39ebc749b40c4fcd2b01c3c16561aeb94bb19`.
Metin SHA-256:
`7eb3a992a48eb7098f794e8069e19cf2cdd70188da1ee0785a08fb7e4d45dce9`.
Bütün alım zamanları, gövde/metin hash'leri ve çalışma kimlikleri
`/tmp/xti-01690-live-evidence.json` içindedir. NCSC PDF'si ayrıca canlı
sınanmadı; PDF ayrıştırması CERT-FR gerçek dosyası ve kontrollü gerçek
PDF alt süreciyle sınandı. Her yayıncı içeriği veya gelecekteki erişim
kesintisi için başarı garantisi verilmez.

Diğer yerel artefaktlar: `/tmp/xti-01690-regression.log`,
`/tmp/xti-01690-final-reports.log`, `/tmp/xti-01690-final-current.log`,
`/tmp/xti-01690-install-final.log`, `/tmp/xti-01690-cli-acceptance.json`,
`/tmp/xti-01690-upgrade.json`, `/tmp/xti-01690-installed-runtime-final.log`. Bunlar geçici çalışma dosyalarıdır; kalıcı
repo kanıtı bu özet, ilgili testler ve kaynak kodudur.

### Bu teslimin sınırı

Arşiv aynı SQLite yedeğine dahildir, mantıksal kayıtları silmez veya
mevcut okuma/kapasite sınırlarını kaldırmaz. Yedekler ek disk kullanır;
SQLite dosyasının anında küçülmesi iddia edilmez. PDF OCR değildir;
Linux adres alanı sınırı macOS'a genellenmez. Genel kaynak iş kuyruğuna
otomatik tam URL çalıştırması eklenmedi. Geniş STIX/TAXII, LLM, .NET/UI,
Tavily canlı kabulü ve yetkili Nmap canlı denemesi ayrı bekler.
[Kullanım ve sözleşme](PUBLISHER_REVIEW_RETENTION.md).

## 0.168.0 — Sekiz maddelik motor paketi

19 Kasım 2026; macOS 26.6.2 arm64 / Python 3.13.3 / SQLite 3.53.2.
Çekirdek 78, kuyruk 3, kaynak işi 4; eski iş 1/2/3 okuyucusu korunur.
Bu kayıt yerel çalışma ağacının kabulüdür; GitHub push/CI veya yeni Linux
kabulü değildir. Kullanıcı veri alanları değiştirilmedi. Testler geçici
firma alanlarında ve kontrollü fixture ile çalıştı; aşağıdaki RIPEstat
isteği canlı sağlayıcı denemesi olarak ayrıca belirtilir.

| Kontrol | Sonuç |
| --- | --- |
| `umask 002; ./scripts/check` tam koşu | **3.151 test / 1.472,761 saniye: 3.145 başarılı, iki eski test beklentisi hatası, dört Linux atlaması; düzeltmeler aşağıda** |
| Yeni iki modül: `test_evidence_delivery`, `test_source_workflows_v4` | **31 test / 8,394 saniye; OK** |
| Kaynak işi tekrarları, kuyruk ve platform bağlantıları | **145 test / 50,484 saniye; OK** |
| Kanıt/rapor/araştırma/kimlik/mimari demeti | **104 test / 35,109 saniye; OK** |
| Kaynak kataloğu/adaptör/sağlayıcı/upgrade demeti | **111 test / 31,349 saniye; 109 başarılı, iki Linux atlaması** |
| Tam koşuda görülen eski kapsam-sırası test varsayımı düzeltildikten sonra araştırma demeti | **23 test / 8,943 saniye; OK** |
| Tam koşuda görülen ikinci eski kaynak listesi düzeltildikten sonra katalog demeti | **7 test / 0,001 saniye; OK** |
| Son kodda gerçek terminal ve engine JSON girişi | **15 süreç / 11,679 saniye; OK** |
| İki firma hacim, eşzamanlı okuma/yazma, rapor işi ve yedekten dönüş | **922 ölçülen süreç / 130,053 saniye toplam; OK** |
| Gerçek eski kodla yükseltme/geri dönüş | **2,712 saniye; OK** |
| Ortak platform worker'ında gerçek SIGTERM, izolasyon ve kurtarma | **31,586 saniye; OK** |
| RIPEstat WHOIS, tek kamu IP'si için pasif kayıt sorgusu | **HTTP 200, bir kapsamı doğrulanmış kayıt; PASS** |

Demetler örtüşür; sayıları benzersiz test sayısı gibi toplanmaz.
Testler sırasında bulunan haber-yenileme/rapor-tekrar sınır durumu
düzeltildi: başarısız haber adımı tekrar çalışacaksa önceki rapor yakalama
başarısı yeniden kullanılmıyor. Değişen haber yeni belge sürümü oluşturur;
önceki rapor makbuzu korunur. Aynı haber sağlayıcısına ait olmayan belge
makbuzu reddedilir. Kayıt başına 2 MiB sınırı commit öncesinde denetlenir.

**Tam koşu kaydı:** İlk tam koşu yeni `ripestat-whois` kaynak girdisini
beklemeyen eski katalog testinde hata gösterdi; koşu kesildi (exit 130).
Bu tamamlanmış veya başarılı tam test değildir. Katalog beklentisi
güncellendi, ilgili 111 testlik demet geçti. Son üretim/test/betik kodu
sabitlendikten sonra yukarıdaki ikinci tam koşu başlatıldı. Başlangıç
dosya özetleri `/tmp/xti-01680-full-final-input.json` içindedir.

İkinci tam koşuda `test_dns_window_does_not_claim_exhaustive_reverse_lookup`
ilk kapsam satırının daima DNS olduğunu varsaydığı için başarısız oldu.
Yeni `local_sightings` satırı öne gelmişti; gerçek DNS satırının
`kind=dns`, `scope=workspace_recent_checks`, `complete=false` olduğu ve
sonucun `partial` / `dns_history_window` taşıdığı ayrıca doğrulandı.
Test, satırı tür/kapsamla seçip okunan kayıt/sınır sayılarını da denetleyecek
şekilde düzeltildi. İlgili 23 testin tamamı yeniden geçti; uygulama kodu
değişmedi. `test_source_catalog` içindeki ikinci eski kaynak listesi de
`enrichment:ripestat-whois` girdisini beklemediği için başarısız oldu;
kesin liste beklentisine yeni girdi eklendi ve katalog demeti geçti.
Tam koşunun dosya özetine göre fark yalnız bu iki test dosyasındadır.
Bu dar test düzeltmeleri için üçüncü tam koşu başlatılmadı; ilk/ikinci koşu
logları başarılıymış gibi yeniden adlandırılmaz.
Atlanan dört kontrol Linux `/proc` süreç sahipliği veya systemd ortamı
gerektirir. Son kodda düzeltilmiş iki test demeti geçti; açık test hatası
kalmadı. Üçüncü tam koşu veya yeni Linux/CI sonucu varmış gibi sunulmaz.
Python 3.11 sözdizimi 76 değişen Python dosyasında, 626 yerel belge bağlantısı
ve `git diff --check` doğrulandı. Başlangıç/son dosya manifestleri ile çıktı
özetleri `/tmp/xti-01680-verification.json` içindedir; çalışma kodunun tam
koşu boyunca değişmediği doğrulandı. Başlangıç manifest SHA-256:
`7cc884d9d5d2cd400ecc77fccac5c9375fca8c63e681b43c1ddde41647ad5ced`;
iki test düzeltmesinden sonraki manifest:
`0687d680ac7932ba417b475ae607b521bcb58471fc392733e4814ae122743273`.

**Yeni davranışların kabulü:** Kaynak olayının aynı kimlikle tekrarında
tek görülme; çelişen olayda ret; geri çekme/sürüm/idempotency geçmişi;
gelecek ve geçmiş gözlem zamanlarının ayrılması; kaynak iddiası sayısı ile
sensör görülmesinin ayrılığı; firma dışı kayıt için `not_found` ve yanlış
workspace için ret doğrulandı. İlişki adayının dört kuralı, eski dayanakla
karar reddi, kimlik çevrimi/alternatif yol/geri çekme, kuruluş kimliği,
salt okunur kesit, bozuk günlük ve kapasite aşımı da test edildi.
Rapor işinin `news` ve saklı `mentions` seçimi, kaynak sırası/hata politikası,
belge kaydından sonra kontrollü kesinti ve açık tekrarda sürüm çoğalmaması
test edildi. Bu kesinti testi kontrollü istisnadır; aşağıdaki gerçek
SIGTERM testi ortak platform worker'ına aittir.

**Ölçülen hacim:** İki firmada başlangıçta toplam 2.000 sensör görülmesi
ve 1.000 varlık. Fixture üretimi domain doğrulamasından geçen toplu
hazırlıktır; ölçülen okumalar/yazmalar gerçek platform girişli ayrı
süreçlerdir. 120 saniyelik eşzamanlı çalışma 152 tur, 304 yeni görülme,
922 ölçülen süreç üretti. Okuma p50 **0,371781**, p95 **0,428108 saniye**;
en yüksek ölçülen alt süreç RSS **56.967.168 bayt**, disk **22.599.281
bayt**. Süreç başlatma okuma süresine dahildir. Tam test paketi aynı
makinede eşzamanlı çalışıyordu. 5 saniye p95 / 256 MiB RSS / 512 MiB disk
eşikleri değiştirilmedi. Her iki firma yedek/restore, görülme sayıları,
rapor ve inceleme korunması, yeni workspace kimliği ve SQLite bütünlüğü
kontrollerini geçti. Bu sonuç 7/24 SLA, milyonlarca olay veya PostgreSQL
kapasite kanıtı değildir.

**Geçiş ve kurtarma:** `dbee4ab18349656177fc90aee65e8c7ddffdb10d` gerçek
eski checkout'u ile çekirdek 75/kuyruk 2 hazırlandı; yeni kodla çekirdek
78/kuyruk 3'e yükseltildi. Eski işler/kimlikler korundu, eski kod yeni
DB'yi reddetti; eski yedek boş hedefe geri yüklendi ve eski kodla okundu.
Workspace kimliği yenilendi, korunmuş iş iptal edilebildi. 77 → 78'in
yalnız yeni kanıt günlüğünü eklemesi ayrıca migration testindedir.
Ortak platform worker'ı kaynak çağrısından önce ve kalıcı makbuzdan sonra
SIGTERM ile kesildi; ikinci worker/kurtarma canlı süreçte `busy` döndü,
diğer firma çalıştı. Kurtarma aynı kesilmiş işi korudu; 0/1 kaynak çağrısı
ve 0/1 kalıcı makbuz beklenen biçimde sayıldı. Yeni rapor adımında ayrıca
gerçek SIGTERM testi yapıldığı iddia edilmez.

**Canlı kaynak:** `ripestat-whois` ile `1.1.1.1` yalnız RIPEstat'a
sorgulandı; hedef IP'ye bağlantı/tarama yapılmadı. İlk sandbox denemesi
ağ hatası verdi. İzinli ağ erişimiyle UTC **18 Kasım 22:01:17.006715–
22:01:17.629209** aralığında HTTP 200 alındı; çalışma
`c861b7d7-9453-4994-88b8-d436c626c419`, ham yanıt SHA-256
`b4313d2e7fc5826fb2fa42ba42ac968a11ae805c694f2792e328f433c3c4716b`.
Geçersiz IPv4/IPv6 kapsamı ve hatada eski başarının korunması kontrollü
testlerle doğrulandı. Bu canlı kayıt sorgusu N-022 ticari iznini kapatmaz.

Tekrarlanabilir komutlar:

```sh
umask 002
./scripts/check
./scripts/python scripts/check-evidence-acceptance.py \
  --duration 120 --events-per-company 1000 --output /tmp/YENI_HACIM.json
./scripts/python scripts/check-engine-upgrade.py --output /tmp/YENI_GECIS.json
./scripts/python scripts/check-platform-acceptance.py --output /tmp/YENI_PLATFORM.json
```

Yerel kanıtlar: `/tmp/xti-01680-full-final.log`,
`/tmp/xti-01680-full-final-input.json`,
`/tmp/xti-01680-evidence-final.json`, `/tmp/xti-01680-upgrade-final.json`,
`/tmp/xti-01680-platform.json`, `/tmp/xti-01680-cli-acceptance.json`,
`/tmp/xti-01680-ripe-live-retry.json`, `/tmp/xti-01680-verification.json`
ve ilgili demet logları. Bunlar geçici
yerel çıktılardır; kalıcı sonuç özeti bu belgede tutulur, ham runtime
verileri repoya girmez. Tavily anahtarı, yetkili Nmap hedefi, ticari
izinler ve gerçek müşteri sensör bağlantısı ayrı takip edilir. Geniş
STIX/TAXII ve LLM bu paketle açılmadı.

## 0.167.0 — Raporların ortak araştırma ve inceleme geçmişine bağlanması

19 Kasım 2026; macOS / Python 3.13.3. Çekirdek 77, kuyruk 3,
rapor modeli 1, araştırma modeli 3 ve dış zarf v1 korunur; öncelik v8.
Kullanıcı veri alanı değiştirilmedi; ağ/sırlar yerine geçici, kontrollü
kaynak kayıtları kullanıldı. Bu canlı sağlayıcı kabulü değildir.

| Kontrol | Sonuç |
| --- | --- |
| İlk araştırma/öncelik/geçmiş, engine kayıt/sözleşme ve mimari demeti | **129 test / 47,717 saniye; OK** |
| Son kodda rapor/araştırma, yüzey/tedarikçi/keşif/vaka/içerik bağlantıları, investigation, platform ayrımı/yedek ve CI demeti | **252 test / 109,566 saniye; OK, atlama yok** |
| Yeni özelliğin 15 testi, son bağlantı inceleme bütçesi dahil | **15 test / 8,744 saniye; OK**; yukarıdaki 252'nin alt kümesidir |
| Gerçek `./xti` süreçleri: yakalama, bağlama, araştırma, öncelik, engine ayrıntısı, tekrar, yeni/eski belge | **11 süreç / 8,767 saniye; tamamı exit 0** |
| Sözdizimi ve belgeler | Python 3.11 sözdizimi, compileall, yerel belge hedefleri ve `git diff --check` geçti |

**Doğrulanan davranış:** İki adımlı IP → belge sürümü → kampanya/aktör
yolu, türü korunmuş URL/hash/IPv6/domain adayları, metinde geçmeden insan
tarafından bağlanan mevcut IOC, özgün arama domaininin metin eşleşmesinden
ayrılması, farklı firmaların aynı IP'si, firma dışı belge ayrıntısının
`not_found` olması ve salt okumada dosyanın değişmemesi. Eski belgeye yeni
bağın taşınmaması, geri çekme geçmişi, no-op yakalama/başarısız yenilemede
aynı kesitin korunması, değişimde sayfa reddi, v7 → v8 başlangıcı, eski
incelemenin aynen kalması ve yedekten dönüşte kimliklerin korunması sınandı.

Okuma/komşuluk/toplam bağlantı inceleme bütçelerinde açık kısmi kapsam,
52 kanıt sınırında son karar ve gerçek toplam, bozuk günlükte ret ve
eşzamanlı kaynak yazılırken tek SQLite okuma kesiti ayrıca doğrulandı.
Yeni testler `test_research_reports.py` ve
`test_research_report_contract.py`; hızlı CI demetine eklendi.

**Test seçimi:** Bu turda tam paket tekrarlanmadı; önceki tam sonuç bir
önceki sürümün aşağıdaki kaydında tutulur. Yeni okuma adaptörü/ilişki
modeli için ilgili demetler seçildi; şema/iş kuyruğu değişmedi. İlk geniş
komut listesinde mevcut olmayan `tests.test_company_review` adı nedeniyle
bir loader hatası oluştu; 252 gerçek test geçti. Yanlış modül kaldırılarak
son kodda temiz 252 testlik koşu tamamlandı; bu ürün arızası sayılmadı.
Örtüşen demet sayıları benzersiz test sayısı olarak toplanmaz.

Yerel kanıtlar: `/tmp/xti-01670-research-tests.log`,
`/tmp/xti-01670-integration-final.log`, `/tmp/xti-01670-report-final.log`,
`/tmp/xti-01670-process-acceptance.json`,
`/tmp/xti-01670-verification.json`. Bunlar geçici yerel çıktılardır;
repo veya müşteri verisi değildir. CI/Linux ve canlı kaynak kabulü bu
turda yapılmadı. Tavily, yetkili Nmap, kullanım koşulları, 7/24 işletim ve
geniş ölçek doğrulamaları kendi takip notlarında açık kalır.

## 0.166.0 — Rapor sürümleri, insan bağlantıları ve gözlem anlamları

18 Kasım 2026; macOS arm64, Python 3.13.3. Çekirdek şema 77, kuyruk 3;
araştırma/frozen model 3 ve öncelik v7 korunur. Kullanıcı `.xti-data`
alanı değiştirilmedi; bütün denemeler geçici fixture alanlarındadır.

- Geniş ilgili demet: **194 test / 62,818 saniye**, hata/atlama yok.
  Migration, eski investigation/araştırma geçmişi, IOC lifecycle, engine,
  firma ayrımı, backup/restore ve mimari bağımlılıklar dahil.
- İlk tam regresyon: **3.104 test / 1.333,225 saniye**; 3.099 başarılı,
  bir kabul-betiği hatası, dört Linux `/proc`/systemd atlaması. Hata ve
  düzeltme sonrası ilgili tekrar aşağıda ayrı korunur; ilk turun sonucu
  sonradan başarılı olarak yeniden adlandırılmaz.
- Gerçek terminal denemesinde cümle sonundaki noktanın IP adayını
  atlatması görüldü. Yeni rapor çıkarımı v2 ile düzeltildi; eski
  investigation v1 kayıtları yeniden yorumlanmadı. Son dar fark üç
  dosyadır: `report_extraction.py`, `reports.py`, `test_reports.py`.
- Son ayrıştırma ve eski sürüme bağlı karar geri çekme dahil **96 test /
  22,925 saniye** geçti. Yeni rapor/gözlem dosyaları toplam **33** test
  içerir; örtüşen test demetleri farklı testler gibi toplanmaz.
- Gerçek `./xti` süreç kabulü: **13 süreç / 7,469 saniye**, başarılı.
  Aynı içerik unchanged; değişen metin belge 2; belge 1 korunuyor;
  terminal/engine aynı kayıt; cümle sonundaki IP metin adayı; olay zamanı
  null; okuma DB özetini değiştirmiyor. Firma capture/show, başka firma
  kaydında not_found ve yanlış workspace'te scope_mismatch doğrulandı.
  Kaynak fixture'dır; yeni canlı internet sorgusu değildir.
- Gerçek eski kodla yükseltme/geri dönüş: **1,465 saniye**, başarılı.
  `dbee4ab18349656177fc90aee65e8c7ddffdb10d` ile hazırlanan çekirdek
  75/kuyruk 2 → çekirdek 77/kuyruk 3. Özgün varlık/iş kimlikleri korundu;
  eski kod yeni DB'yi reddetti. Eski yedek boş hedefe restore edildi;
  eski kodla okuma ve korunan işi iptal başarılı, workspace kimliği yeni.
  76 → 77'nin yalnız yeni journal eklemesi ayrıca migration testinde geçti.
- Tam pakette eski Linux yükseltme kabul betiğinin, incelenmiş eski
  collection tablo dönüşümünü yalnız şema 76'ya kadar kabul ettiği görüldü.
  Şema 77 sınırı eklendi; özgün satır/rowid ve beklenen DDL denetimleri
  korunur. Betiğin **18 testi / 2,300 saniye** yeniden çalıştırıldı:
  16 başarılı, iki gerçek Linux `/proc` kontrolü macOS'ta atlandı.
  İlk tam turdaki hata silinmez; düzeltme sonrası bu demet ayrı kanıttır.

Denetlenen sınırlar: aynı anahtarın özgün sonuç tekrarı; aynı içerikte yeni
anahtarın yalnız makbuz olması; A→B→A metin geçmişi; eski belge insan
bağının geri çekilmesi; yayın günü/saat dilimi belirsizliği; kaynak hatası
ve bozulmasında donmuş belge; CTI hedef türü/aktif kaynak/firma sınırı;
bozuk payload/hash/zincir/silinen journal sonu; commit öncesi kapasite
reddi; iki eşzamanlı yazar; WAL sırasında aynı kesitte rapor+IOC okuması.

Yerel geçici kanıtlar: `/tmp/xti-01660-targeted-final.log`,
`/tmp/xti-01660-parser-final.log`, `/tmp/xti-01660-process-acceptance.json`,
`/tmp/xti-01660-upgrade-rollback.json`, `/tmp/xti-01660-upgrade-final.log`,
`/tmp/xti-01660-full.log`. Tam koşu son dar ayrıştırma farkını içermez;
bu fark 96 testle, kabul betiğinin düzeltmesi 18 testle ayrıca doğrulandı.
Ortak şema kodu tam koşu sırasında değişmedi. Son dar farklar sonrasında
ikinci tam paket çalıştırılmadı. İlk ve son dosya özetleri
`/tmp/xti-01660-verification.json` içinde kayıtlıdır. Bu yerel çalışma
henüz GitHub'a gönderilmiş bir commit veya yeni Linux CI kabulü değildir.
Yeni Linux, canlı Tavily/Nmap veya 7×24/hacim kabulü iddia edilmez.
[Kapsam ve kullanım](REPORTS_OBSERVATIONS.md).

## 0.165.0 — IOC yaşam döngüsü değerlendirmesi

18 Kasım 2026, yerel Python 3.13.3. Çekirdek 76, kuyruk 3; veri geçişi yok.

- Son kodun hedefli demeti: **110 test / 31,616 saniye / OK**; 33 yeni
  senaryo içerir. Günlük `/tmp/xti-01650-targeted-final.log`.
- İlk geliştirme demeti 105 test / 29,317 saniye ve sonrasında iki
  kapsam/yedekten dönüş testi 0,883 saniye ile geçmişti; bunlar son demetle
  örtüşür, farklı test sayısı gibi toplanmaz.
- `umask 002` altında `./scripts/check`: ilk uygulamanın tam regresyonu
  **3.069 test / 1.338,055 saniye / OK (skipped=4)**. 3.065 test başarılı,
  0 hata/başarısızlık. macOS'ta iki Linux `/proc` süreç sahipliği ve iki
  `systemd-analyze` kontrolü ortam gerekçesiyle atlandı; başarılı sayılmadı.
  Günlük `/tmp/xti-01650-full.log`.
- Tam koşu başladıktan sonra yalnız yeni IOC okuyucusuna bozuk geri çekme
  makbuzunu yerel karar saymama ve değişmeyen makbuzun önceki durumunu
  denetleme eklendi; aynı zaman damgalı tekrarlar korunur. Bu son değişiklik
  ve üç ek senaryo 110 testlik son demetle doğrulandı. Son kod için ikinci
  bir tam paket çalıştırılmadı; doğrulamanın bu ayrımı korunur.
- Son hedefli kabulden sonra runtime/test kodları değişmedi. Dosya özetleri
  `/tmp/xti-01650-final-code.json` içinde; belge güncellemeleri bu kapsamın
  dışındadır. Bu kabul çalışma alanındaki 0.165.0 içindir, yeni bir Linux CI
  koşusu veya yayımlanmış sürüm etiketi değildir.
- Gerçek üç `./xti` süreci (terminal, `--json`, engine): **0/0/0 çıkış**,
  aynı kesit, değişmeyen DB özeti. Kontrollü eski IP kanıtı + son kaynak
  hatası birlikte gösterildi, önceki başarı korundu. Yeni internet çağrısı
  yok. Kanıt `/tmp/xti-01650-acceptance.json`; çalışma alanı geçicidir.

Doğrulananlar: tekrar indirmede gözlem tarihi sabit; yeni sağlayıcı gözlemi
ayrı; başarısız toplamada önceki başarı korunur; listeden kaldırma ve yerel
geri çekme ayrılır; CERT Polska liste sürümü gerçek olay tarihi olmaz.
Güncellik/geçerlilik eşikleri, belirsiz elle kayıt zamanı, saat tutarsızlığı,
geçmiş/makbuz bozulması, okuma bütçesi, sayfa kesiti, terminal/JSON uyumu,
iki firma ve aynı gösterge, bilinmeyen firma, birlikte backup/restore ile
özgün kanıt kimlikleri test edildi. WAL üzerinde okuma sürerken yeni kaynak
sonucu yazılması eski kesite karışmadı. Testler izole geçici alanlardadır.

Bu pakette yeni canlı kaynak çağrısı yok; kontrollü snapshot'lar gerçek
parser/depo üzerinden işlendi. Yeni Linux/30 dakika hacim/7×24 kabulü
iddia edilmez; 0.164.0 ölçümleri aşağıda kendi kodlarıyla korunur.
[Test düzeni](TESTING.md), [kapsam](IOC_LIFECYCLE.md).

## 0.164.0 — Roadmap 1–7 motor paketi

18 Kasım 2026; kod commit'i `432f530c64c64614c6c4418eaa05e959d06c65ab`.
Başlangıç sürümü `dbee4ab` / 0.163.0. Son teslim çekirdek 76, kuyruk 3,
araştırma/frozen model 3, öncelik v7, kaynak işi v3 (eski 1/2 okunur).
Kullanıcı `.xti-data` alanı değiştirilmedi. Kabul alanları geçicidir.

**Son durum: Aşağıdaki kapsamla 1–7 tamamlandı.** Tam Linux paketi,
hızlı kontrol, iki Python sürümünde firma kabulü, 30 dakikalık hacim
koşusu, yedekten/eski sürüme dönüş ve canlı pasif kaynak akışı geçti.
Canlı Tavily/yetkili Nmap doğrulamaları ve ticari kaynak izinleri kendi
açık notlarında kalır. Geniş STIX/TAXII ve LLM ertelidir.

### İstenen yedi adımın karşılığı

| Adım | Teslim edilen davranış | Tekrar üretilebilir kanıt |
|---|---|---|
| 1. Vaka ve insan kararları | Vaka durumu, gerekçe ve özgün kanıt ortak araştırmada; kapatma kaynak geri çekilmesi olmaz | [Vaka/içerik testleri](../tests/test_research_case_content.py); kalıcı inceleme kapanış farkı ve eski dondurulmuş incelemenin değişmemesi ayrıca doğrulandı |
| 2. Mevcut sosyal/firma içerikleri | Sosyal gözlem ve insan kararı; firma aramasının özgün domain/URL bağı; son hata ile önceki olumlu kanıt ayrı | [Vaka/içerik testleri](../tests/test_research_case_content.py); yeni Tavily isteği yapılmaz |
| 3. Kimlik incelemesi | Kayıtlı ad/alternatif ad adayları; kanıtlı onay, ret, belirsiz ve geri alma; kaynak kimlikleri korunur | [Kimlik ve günlük testleri](../tests/test_investigation.py), [firma yazma/restore testleri](../tests/test_investigation_platform.py) |
| 4. Kaynak ve metin kapsamı | RIPEstat IP/prefix/ASN bağlamı; saklı metinden özgün konumuyla gösterge adayları | [Kaynak testleri](../tests/test_extended_source_jobs.py), [metin sınırları](../tests/test_investigation.py); canlı pasif RIPEstat ve NCSC akışı |
| 5. Firma inceleme listesi | Pencereli kökler, gerekçeli öncelik, bağımsız vakalar ve kaynak durumları; eksik kapsam açık | [İnceleme listesi testleri](../tests/test_investigation.py), [hacim/sayfalama kabulü](../scripts/check-engine-soak.py) |
| 6. Yönetilen akışlar | RIPEstat, yayıncı ve metin adımları; bütçe, kalıcı sonuç, tekrar, iptal ve eski iş uyumu | [Altı adım/geç iptal/kuyruk geçişi testleri](../tests/test_extended_source_jobs.py); canlı firma plan → worker → sonuç zinciri |
| 7. Kapasite ve işletim | Hacim, gerçek süreç tekrarı, kuyruk, arşiv, restore ve eski kodla geri dönüş | [Hacim kabulü](../scripts/check-engine-soak.py), [sürüm geri dönüşü](../scripts/check-engine-upgrade.py); yerel/firma kabulü, 30 dakikalık Linux koşusu ve tam paket geçti |

Vaka kapanışından sonra yeni kalıcı inceleme bir değişim kaydetti;
`withdrawn_assertion_ids` boş kaldı ve önceki incelemenin saklı içeriği
değişmedi. Kanıt: `/tmp/xti-01640-case-history-acceptance.json`.

### Tam Linux paketinin nihai sonucu

`91e5ca80489e98974ee617321846bdee87c67905` için
[tam paket](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44311197271)
Python 3.13'te **3.039 test / 2.067,829 saniye / OK** ile tamamlandı:
**0 hata, 0 başarısız, 0 atlama**. `./scripts/check` bütün paketi baştan
sona çalıştırdı. Günlük: `/tmp/xti-01640-linux-full-final.log`.

Bu commit'te `432f530` üzerine yalnız CI süre bütçesi ve kabul belgeleri
değişir; motor, testler, çalıştırma betikleri ve bağımlılıklar aynıdır.
Dolayısıyla aşağıdaki `432f530` hacim/firma/canlı kaynak kanıtları aynı
motor sürümüne aittir. İlk tam koşunun süre aşımı aşağıda korunur.

### Son kodun hızlı Linux kontrolü

`432f530` için [hızlı kontrol](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44305422546)
Python 3.11'de **1.742 test / 1.146,589 saniye**, hata ve atlama olmadan
geçti. Günlük: `/tmp/xti-01640-linux-quick-final.log`. Bu demet tam paketle
örtüşür; sayıları toplanarak farklı test sayısı gibi verilmez.

### Uzun Linux hacim ve geri dönüş kabulü

`432f530` için [30 dakikalık Linux kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44305506952)
ilk koşuda geçti: Ubuntu 24.04 / Linux 7.0.0-1014-aws, x86_64, 4 CPU,
Python 3.13.18, SQLite 3.45.1. 1.800 saniyelik tekrar penceresiyle toplam
**1.812,966 saniye**, **232 tur / 2.784 gerçek süreç çağrısı** çalıştı.
Okuma p95 **0,745487 saniye**, en yüksek RSS **49.979.392 bayt**,
disk **18.104.785 bayt**. Temizlik arşivi, karar günlüğünün korunması,
firma ayrımı ve birlikte yedekten dönüş geçti. Eşikler değişmedi.

Aynı Linux işinde gerçek 0.163.0 kodu/çekirdek 75/kuyruk 2 üzerinden
0.164.0/76/3 yükseltme ve eski kodla eski yedekten boş alana geri dönüş
**1,628 saniye** ile geçti. Eski kod yeni şemayı reddetti; özgün kimlikler
korundu, yeni workspace üretildi ve bekleyen iş iptal kaldı.
Günlük: `/tmp/xti-01640-linux-soak-final.log`.

### Tam Linux paketinin süre sınırı

`432f530` [ilk tam Linux koşusu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44305518106)
12:36:24–13:06:38 UTC arasında çalıştı; GitHub'ın 30 dakikalık iş süresi
dolduğu için iptal edildi. Günlükte 2.509 tamamlanan test satırı bulunur;
FAIL/ERROR testi yoktur, fakat nihai paket özeti de yoktur. Bu koşu tam
paket başarısı sayılmaz. Günlük: `/tmp/xti-01640-linux-full-first.log`.

Üç binin üzerindeki tam regresyon için yalnız CI iş süresi 60 dakikaya
çıkarıldı; test listesi, assert'ler ve motorun komut/p95/RSS/disk/kurtarma
eşikleri değişmedi. Runtime kodu aynı `432f530` sürümüdür. Yeni CI
bütçesiyle baştan çalıştırılan tam paket yukarıdaki 3.039 testle geçti;
ilk eksik koşu ayrıca başarılı sayılmadı.

İptal sınırındaki `test_stabilization_data` modülünden son modüle kadar
**531 test** yerelde ayrıca çalıştırıldı: **216,564 saniye / OK**, hata
ve atlama yok. `/tmp/xti-01640-full-tail-local.log`. Bu demet saklama,
geçiş, doğrulama ve geri dönüş son bölümünü kapsar; Linux tam paket sonucu
yerine sayılmaz ve önceki kısmi koşunun sayısıyla toplanmaz.

### Son kodun Linux firma kabulü

`432f530` için [firma izolasyonu kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44305422658)
iki Python sürümünde ilk koşuda geçti. Ubuntu 24.04.5, x86_64, 4 CPU,
SQLite 3.45.1; iki geçici firmada 100/1.000 kayıt, 36 okuma ve 63 süreç/kapı.

| Python | Toplam süre | Okuma p95 | En yüksek okuma RSS | Disk |
|---|---:|---:|---:|---:|
| 3.11.18 | 41,022 sn | 0,510990 sn | 46.710.784 bayt | 5.427.747 bayt |
| 3.13.18 | 51,369 sn | 0,644509 sn | 47.054.848 bayt | 5.431.843 bayt |

Kaynak öncesi ve kalıcı sonuç sonrası gerçek SIGTERM, aynı firmada ikinci
worker ve eşzamanlı kurtarma reddi, diğer firmada tamamlanan iş ve aynı
kesilmiş işin tekrar anahtarıyla korunması geçti. Toplam 120 saniye,
okuma p95 5 saniye, RSS 512 MiB ve disk 128 MiB sınırları değiştirilmedi.
Günlük: `/tmp/xti-01640-linux-platform-final.log`.

### Hacim testinin ölçtüğü iş yükü

Hacim testi iki firmada toplam 6.000 varlık (1.000 ve 5.000), kayıtlı
DNS/IOC/aktör bağları, bir kimlik kararı, firma başına 10 vaka ve bir saklı
rapor metni kullanır. Her turda 10 köklük inceleme penceresinin ilk ve
ikinci sayfası, bağımsız vaka penceresi, kaynak planı ve yeni iş çalıştırılır;
turlar sırayla worker tamamlama ve kuyrukta iptal yolunu kullanır.

Bu ölçüm 6.000 kökü tek istekte dolaşmaz. Kök ve sonuç sayfaları ayrı
kalır; eksik kapsamın görünmesi, aynı kesitte sayfaya devam etme, yinelenen
metnin yeni aday çoğaltmaması ve firma ayrımı kontrol edilir. Test sonunda
100 eski bağlantısız gözlem yedeklenerek temizlenir; karar günlüğü aynı
kalır. Çekirdek/kuyruk birlikte yedekten boş alana döndürülür ve veritabanı
bütünlüğü doğrulanır. Gerçek internet kaynakları bu tekrar yüküne katılmaz;
canlı kaynak kabulü aşağıda ayrı verilir.

### Son kuyruk ve canlı birleşik kabul

İlk canlı firma işinde üç kaynak + inceleme tamamlandığı halde eski
üç-adım sonuç doğrulayıcısı finalizasyonu reddetti. Özgün dört makbuz
korundu, iş `interrupted` kaldı; başarılı sayılmadı. Düzeltme v3 sonuçta
altı adımı, kuyruk 3'te geç iptal dahil 16 olayı açıkça destekler.
Kuyruk 1/2 → 3 migration eski JSON/hash/rowid'leri ve doğrulanmış yedeği
korur. Önceki geliştirme adayının v3 işi eski kuyrukta okunur; worker
migration öncesi dış isteğe başlamaz. Bu senaryolar kalıcı depoyla test edilir.

Son geniş kuyruk demeti **102 test / 24,258 saniye**, hata/atlama olmadan
geçti: `/tmp/xti-01640-queue3.log`. En büyük beş kaynak + inceleme işi hem
başarı hem son adımda iptal durumunda tamamlandı; iptal geçmişi tam 16
olayla doğrulandı. Son ek eski-aday testi ayrıca çalıştırıldı.

Kuyruk 3 ile tekrar edilen yerel hacim kabulü **38,355 saniye**, 84 komut,
okuma p95 **0,429715 saniye**, RSS **66.060.288 bayt**, disk **14.687.652
bayt**; temizlik arşivi ve restore geçti. Gerçek SIGTERM/firma kabulü
**30,800 saniye**, 36 okuma p95 **0,445244 saniye**, RSS **61.931.520
bayt** ile geçti. Core 75 → 76 ve kuyruk 2 → 3 gerçek eski kod yükseltme /
eski yedekten geri dönüşü **1,528 saniye** ile geçti. Artefaktlar:
`/tmp/xti-01640-volume-queue3.json`, `/tmp/xti-01640-platform-queue3.json`,
`/tmp/xti-01640-upgrade-final.json`.

**Canlı platform akışı PASS:** yeni geçici firmada plan → kabul → worker →
sonuç → firma inceleme listesi. İş `48452ac1-8056-4ae6-96d7-20da7c260869`
NCSC, 20 saklı metnin aday çıkarımı, RIPEstat ve son incelemeyi `complete`
bitirdi. Gerçek worker 2,778 saniye; kaynaklar için toplam iki HTTP denemesi,
yerel adımlar için sıfır. Araştırma adayları zararlı IOC olarak eklenmedi.
`/tmp/xti-01640-live-platform-2.json`. Bu Tavily anahtar kabulü değildir.

İlk yerel tam paket **3.030 test / 1.392,213 saniye**, 2 başarısız + 1 hata
ve 4 ortam atlamasıyla tamamlandı: iki eski katalog beklentisi ve eski Linux
migration hedefi. Hepsi düzeltildi; kaynak kataloğu/CLI son demeti **21 test /
12,329 saniye** ile geçti. İlk tam paket temiz kabul sayılmaz. `c2ccb05`
için önce başlatılmış tam Linux ve uzun hacim işleri, son kuyruk düzeltmesi
geldiği için iptal edildi; bunlar da tamamlanmış kabul sayılmaz. Son kodun
başarılı tam paket ve uzun Linux sonuçları bu bölümün başında kayıtlıdır.

### Önceki geliştirme diliminin ölçümleri

Aşağıdaki ilk ölçümler kuyruk 2 adayına aittir; son kuyruk 3 kabulünün
yerine kullanılmaz. Hatalar ve sonraki düzeltmeler üstte korunur.

Yeni/ilgili entegrasyon demeti **68 test / 22,246 saniye** ile geçti:
vaka kapanışı/kaldırılmış kanıt, kamu kaynakları ve ransomware vaka bağı,
sosyal son hata/önceki kanıt, saklı firma içeriği, kimlik kararının geri
alınması ve stale revision, tekrar anahtarı, farklı tür/alan reddi, bozuk
günlük, rapor metin konumları, gerçek firma protokolü ve restore,
RIPEstat parser/HTTP/cooldown bileşimi ve kaynak işi v1/v2 uyumu.
Son ek öncelik/terminal kontrolleri ayrıca raporlanır; demetler toplanmaz.
Günlük: `/tmp/xti-01640-integration-final.log`.

Son kod değişikliklerinden sonra mimari, ortak araştırma/öncelik/geçmiş,
firma yazmaları ve kaynak işi kullanımıyla birlikte **102 test / 29,285
saniye**, hata/atlama olmadan geçti; `/tmp/xti-01640-final-code.log`.
Gerçek iki firma/kesinti kabulü **30,550 saniye** ile geçti: 36 okuma p95
**0,401374 saniye**, en yüksek okuma RSS **61.915.136 bayt**, disk
**5.427.747 bayt**. Kaynak öncesi ve makbuz sonrası SIGTERM'de ikinci worker
ve eşzamanlı recover reddedildi; diğer firma işini tamamladı. Eşikler
değişmedi. `/tmp/xti-01640-platform-acceptance.json`.

**Yerel hacim kabulü:** macOS 26.6.2 arm64, Python 3.13.3, SQLite 3.53.2,
10 CPU. İki firmada 1.000/5.000 varlık, kayıtlı DNS/IOC/aktör ilişkileri,
kimlik kararı, firma başına 10 vaka ve rapor metni. 30 saniyelik tekrar
penceresi dahil toplam **38,431 saniye**, 7 tur / **84 gerçek süreç çağrısı**;
okuma p95 **0,451580 saniye**, en yüksek RSS **65.945.600 bayt**, disk
**14.679.415 bayt**. Sayfa kesiti, firma ayrımı, rapor tekrarının aynı adayı
döndürmesi, worker/iptal, 100 eski bağlantısız gözlemin yedekli temizliği,
karar günlüğünün değişmemesi ve boş alana birlikte restore geçti.
Sabit eşikler: komut 30 saniye, okuma p95 10 saniye, RSS 512 MiB,
disk 256 MiB. `/tmp/xti-01640-volume-final-2.json`.

**Gerçek sürüm geri dönüşü:** Git'teki 0.163.0 `dbee4ab` kaynakları ayrı
geçici alanda çalıştırıldı. Eski çekirdek 75 ve kuyruk v2 işi oluşturuldu;
birlikte yedek alındı. Güncel kodla 76'ya explicit migration eski varlık
kimliğini ve v2 işi korudu. Eski kod yükseltilmiş şemayı reddetti. Eski
kodla eski birlikte yedek yeni alana açıldı; özgün kimlikler korundu,
workspace yenilendi, bekleyen iş restore politikasıyla iptal kaldı.
**1,568 saniye / PASS**, `/tmp/xti-01640-upgrade-2.json`.
Bu geri dönüş yükseltmeden sonraki yazmaları eski şemaya taşımaz.

**Canlı pasif kaynak:** RIPEstat `network-info` için `1.1.1.1` GET sonucu
`matched`, prefix `1.1.1.0/24`, ASN 13335; araştırmada IP/prefix/ASN
düğümleri üretildi. Çalışma `eb330c4e-63cb-40be-9462-f14034332748`,
`/tmp/xti-01640-ripe-live-3.json`. Hedef IP taranmadı. Ticari izin N-022'de
ayrı açık. Yeni Tavily veya yetkili hedef Nmap kabulü yapılmış sayılmaz.

**Geliştirme sırasında düzeltilenler:** İlk canlı RIPEstat denemesi yeni
provider'ın cooldown kaydının eksikliğini, ikinci deneme resmî yanıtta
`query_params` tekrarının zorunlu olmadığını ortaya çıkardı. Her ikisi
gerçek adapter testine eklendi. İlk hacim harness'inde cancel workspace
parametresi, son genişletmede test modülü import yolu düzeltildi. Eski
koda dönüş harness'i restore sonrası bekleyen işin iptal edilmesini yanlış
olarak queued bekliyordu; test mevcut güvenli restore politikasıyla düzeltildi.
Başarısız denemeler başarılı kabul yerine sayılmaz.

Tam paket ilk çalışmasında eski Linux upgrade harness'inin şema üst sınırı
ve kaynak kataloğu testinin RIPEstat beklentisi güncellendi. Son ayrı demet
**32 test / 14,752 saniye**, 2 Linux'a özel atlama ile geçti;
`/tmp/xti-01640-compatibility.log`. Bu ilk geliştirme diliminden sonraki
başarılı tam paket ve uzun Linux kabulü yukarıda kayıtlıdır. Süreli kabul
7/24 hizmet, sınırsız hacim veya OpenCTI eşdeğerliği değildir.

## 0.163.0 — Tedarikçi izleme ve inceleme bağlamı

18 Kasım 2026, macOS arm64/Python 3.13.3; `0c130bb` üzerine çalışma
ağacı. Araştırma modeli 3, DB 75, iş şeması 2, engine/platform zarfı v1
korunur; öncelik v6. Canlı ağ, API anahtarı ve kullanıcı çalışma verisi
kullanılmadı; geçici fixture alanları kullanıldı.

`umask 002` altında **432 test / 154,226 saniye**, hata/atlama olmadan
geçti. Araştırma/öncelik/geçmiş, keşif, tedarikçi envanteri/aday/kart/
izleme, kaynak geçmişleri, izleme migration/entegrasyonu, engine/platform,
firma ayrımı, yedek, kaynak işleri, mimari ve CI yapılandırması kapsandı.
Günlük `/tmp/xti-01630-regression.log`. Son değişiklikte kartın dayanak
tarihine insanın bağımlılık kararı da katıldı; bunun ayrı son testi aşağıda
kaydedilir. Demetler ve tekrarlar tek toplam gibi toplanmaz.

Son kart tarihi ve üç ek anlam kontrolünden sonra araştırma önceliği/
geçmişiyle birlikte **86 test / 33,074 saniye** geçti; hata/atlama yok.
İki demetin birleşimi **435 farklı test**, **28 yeni tedarikçi bağlam
senaryosu** içerir. Son günlük `/tmp/xti-01630-final-focus.log`.
Son sürüm/AST, göreli belge bağlantıları ve `git diff --check` de geçti.

Özel kabul; iki adımda özgün olay/claim/run kimliği, bağımsız kartla aynı
kural, kaynak ayrımı, HIBP metaverisi, filtrede aynı-ad belirsizliği,
sessiz başlangıç ve sıfır eşleşmeli yeniden açılış, güncelleme/çıkarılma,
yerel bildirim, son hata/önceki başarı, kimlik değişimi/pasif izleme,
bozuk kaynak veya izleme bağında güvenli ret, decoder öncesi byte/satır/
iş bütçesi, 150 olay/52 kanıt sınırı, tek WAL okuma kesiti, sayfa koruması,
eski frozen politika, iki firma ve yedek korunmasını kapsar. Terminalin
ürettiği ayrıntı komutları seçili fixture alanında gerçekten çalıştırıldı.

İlk odaklı turlarda seçili-audit parametresini gölgeleyen yerel değişken ve
80 karakteri aşan yeni ilişki kimliği düzeltildi; RansomLook fixture alanı/
tarihi de kaynak sözleşmesine uyarlandı. Bu başarısız geliştirme turları
başarılı kabul sayılmadı; yukarıdaki geniş paket bu düzeltmelerden sonradır.

### Gerçek yerel süreç kabulü

`PYTHONDONTWRITEBYTECODE=1 ./scripts/python scripts/check-platform-acceptance.py`
aynı iki geçici firma ve aynı eşiklerle **29,331 saniyede** geçti.
36 okuma p95 **0,521 saniye**, en uzun okuma **0,552 saniye**, okuma
süreçlerinde en yüksek RSS **47.742.976 bayt**, fixture disk
**5.390.883 bayt**. 63 komut/kapı ölçümü saklandı.

Kaynak öncesi ve makbuz sonrası SIGTERM senaryolarında ikinci worker ve
eşzamanlı recover `busy`; diğer firma kendi işini tamamladı. Kaynak
öncesinde sıfır, makbuz sonrasında bir özgün makbuz korundu. Otomatik
kaynak tekrarı olmadı ve iki SQLite bütünlük denetimi geçti. Süre/bellek
sınırı yükseltilmedi, test çıkarılmadı. Artefaktlar
`/tmp/xti-01630-platform-acceptance.json` ve `.log`; ham fixture repoya girmez.

Bu yerel/kontrollü sonuç tam test paketi, yeni Linux kurulumu, Tavily/Nmap
canlı kabulü veya 7/24 hizmet kabulü değildir. Önceki 0.162.0 Linux sonucu
ayrı bölümde tutulur; yeni commit'in GitHub sonucu henüz alınmamıştır.

## 0.162.0 — Firma başlangıç süresi ve pasif kaynak durumu

18 Kasım 2026, macOS arm64/Python 3.13.3; `259bc5f` üzerine çalışma ağacı.
DB 75, iş şeması 2 ve engine/platform zarfı v1 korunur. Araştırma ve
değerlendirme modeli 3, öncelik v5; eski model 1/2 incelemeler özgün okunur.

`umask 002` altında geniş regresyon **414 test / 172,719 saniye**, hata
ve atlama olmadan geçti. Araştırma/öncelik/geçmiş, keşif/kaynak durumu,
tedarikçi/envanter, engine/platform, firma ayrımı, yedek, profil/kaynak
işleri, giriş/kurulum, mimari ve CI yapılandırması kapsandı. Yeni manifest
regresyonu ve son sürüm bildirimi için ayrı son kontrol aşağıda tutulur.
Günlük `/tmp/xti-01620-regression.log`; ilk odaklı kontrol **103 test /
40,265 saniye** idi ve toplam sayıya tekrar eklenmez.

Son sürüm/manifest ve firma girişi kontrolü **97 test / 33,797 saniye**
ile geçti. Frozen model 3'ün eksik kaynak bağını ve eski model etiketiyle
sunulmasını da reddeden son düzenlemeden sonra ilgili **110 test / 43,704
saniye** geçti; hata/atlama yok. Geniş ve son demetlerin birleşiminde
**415 farklı test** vardır; 20 yeni test dahildir, tekrarlar toplanmaz.
Son günlükler `/tmp/xti-01620-final-tests.log`,
`/tmp/xti-01620-frozen-final.log`. Sürüm, AST, göreli doküman bağlantıları
ve `git diff --check` de geçti.

### Aynı yerel gerçek süreç kabulünün karşılaştırması

İki sentetik şirket, 100/1.000 kayıt, 36 okuma; kaynak öncesi ve makbuz
sonrası iki gerçek süreç SIGTERM kesintisi. Ağ ve dış araçlar kapalıdır.
120 saniye toplam, 5 saniye okuma p95, 512 MiB süreç belleği ve diğer
eşikler değişmedi. Senaryo veya assertion çıkarılmadı.

| Ölçüm | 0.161.0 başlangıcı | 0.162.0 son kabul |
|---|---:|---:|
| Toplam süre | 40,845 sn | 25,935 sn |
| 36 okumanın p95'i | 0,629 sn | 0,308 sn |
| En uzun okuma | 0,932 sn | 0,317 sn |
| Okuma süreçlerinde en yüksek RSS | 71.024.640 bayt | 47.415.296 bayt |
| Şirket sayısı / bütünlük | 2 / geçti | 2 / geçti |

Son kabulde 63 komut/kapı ölçümü vardır. Her iki kesinti sınırında
ikinci worker ve eşzamanlı recover `busy` döndü; diğer şirket işini
tamamladı. Açık kurtarma aynı işi `interrupted` yaptı; kaynak otomatik
tekrarlanmadı. Kaynak öncesinde 0, makbuz sonrasında 1 özgün makbuz
korundu. Disk 5.394.979 bayttı. Okuma ortalamaları search 0,302,
organization.content 0,285, jobs.status 0,263 saniye.

Yerel `-X importtime` tam CLI yüklemesinde yaklaşık 570 ms, platform
adaptöründe 221 ms ölçtü. Ortak parser ile hafif giriş, yalnız gereken
engine servisinin kurulması ve kuyrukta ertelenen toplama bileşimi
uygulandı. İlk ara düzeltme kabulü 28,288 saniyeydi. Yeni sentetik rapor
komutların süreç/CPU/bellek, modül sayısı ve kapıya ulaşma süresini saklar.
Çalıştırıcıdaki bütün dalgalanma tek nedene bağlanmaz; başarılı yerel
ölçüm yeni Linux kabulünün yerine geçmez (N-016).

Artefaktlar `/tmp/xti-01620-before.json`, `/tmp/xti-01620-dispatch.json`,
`/tmp/xti-01620-final-acceptance.json`; ham fixture repoya alınmaz.

```sh
PYTHONDONTWRITEBYTECODE=1 ./scripts/python scripts/check-platform-acceptance.py --output /tmp/xti-new-acceptance.json
```

Kaynak durumu kabulünde hiç sorgulanmadı/boş/kısmi/başarısız ayrımı,
eski complete yanıtın tarihi, iki sağlayıcı, saat gerilemesi, ilgisiz kök,
bozuk seçili kayıt, decoder öncesi boyut sınırı, aynı okuma kesiti,
kanıt sınırı, sayfa kimliği, frozen kaynak bağlantısı, firma ayrımı ve
yedek doğrulandı. Sorgulanmamış sağlayıcıya tarih uydurulmadı; yeni deneme
adayın arşiv tarihini/insan kararını değiştirmedi. Bu kontrollü kabul,
Tavily/Nmap canlı kabulü, tam test paketi veya 7/24 üretim garantisi değildir.

### 0.162.0 Linux kabulü

`dba3dbd596134acf5bfd70f65dc85673b1c25a50` için
[firma kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44282646610)
**iki Python kolunda ilk koşuda başarılıdır**. Tekrar çalıştırma yapılmadı.

| Linux | Toplam | 36 okuma p95 | En yüksek okuma RSS |
|---|---:|---:|---:|
| Python 3.11.18 | 40,914 sn | 0,505 sn | 46.661.632 bayt |
| Python 3.13.18 | 51,655 sn | 0,651 sn | 46.866.432 bayt |

Her kolda 63 komut/kapı kaydı, iki SIGTERM sınırı, ikinci worker/recover
`busy`, diğer şirketin eşzamanlı tamamlanması, otomatik kaynak tekrarı
olmaması ve SQLite bütünlüğü geçti. Disk 5.382.691 bayt. 120 saniye
toplam, 5 saniye p95, 512 MiB bellek ve diğer eşikler değiştirilmedi.
N-016 önceki başarısızlıkları korunarak düzeltme/kanıt ile kapatılır.

[Linux kurulum kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44282647213)
ve [marka kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44282646938)
geçti. `dba3dbd` [hızlı kontrolü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44282647271)
sonraki dokümantasyon push'u nedeniyle `cancelled` oldu. Aynı ürün kodunun
`0c130bb4a378922b5edbae57f9a284e151d7fcf7` commit'indeki
[hızlı kontrol](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44283192210)
**1.684 test / 1.070,277 saniye**, hata/atlama olmadan başarılıdır.
Önceki iptal test başarısızlığı veya başarılı kabul diye yeniden yazılmadı.
Günlükler `/tmp/xti-01620-platform-ci.log`, `/tmp/xti-01620-quick-ci.log`;
bunlar 0.163.0'ın yeni kodunun sonucu değildir.

### 0.161.0 GitHub sonucunun kaydı

`259bc5f` hızlı kontrol **1.664 test / 1.096,802 saniye** ile geçti;
[hızlı kontrol](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44273412701),
[marka kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44273412688),
[Linux kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44273412705)
başarılı. [Firma kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44273412771)
iki Python kolunda tamamlanmadı: 3.11, 120,015 saniyede son recover öncesi
1,114 saniye kalmışken `TimeoutExpired`; 3.13, 120,032 saniyede kapı
beklemesi toplam bütçeyi aştı. 36 okumanın ortalamaları sırasıyla
1,794–1,845 ve 2,025–2,098 saniyeydi. Bu sonuçlar tekrar ile silinmedi.

## 0.161.0 — Pasif alt alan adayı ve sahiplik sınıflandırması

18 Kasım 2026, macOS arm64/Python 3.13.3; `de80b54` üzerine çalışma ağacı.
Çekirdek 75, kuyruk 2, araştırma/değerlendirme modeli 2 ve dış zarf v1
değişmedi. Öncelik politikası `research-priority-v4`; ilk v4 incelemesi
politika başlangıcıdır, önceki değerlendirme yeniden hesaplanmaz.

| Doğrulama | Sonuç |
|---|---|
| `umask 002`; araştırma/öncelik/geçmiş, tedarikçi, pasif keşif/geçmiş/envanter, varlık ilişkileri, engine/platform, firma ayrımı/yedek, kaynak işleri, mimari ve CI yapılandırması | **350 test / 134,945 saniye; OK, atlama yok** |
| Son metin alanı boyut ön kontrolü ve ek regresyondan sonra yeni modül | **29 test / 15,226 saniye; OK, atlama yok** |

İki demette **351 farklı test**; tekrarlar toplanmaz. 29 yeni test hızlı
CI listesine eklendi. İlk 26 test / 14,435 saniye geliştirme koşusu da geçti;
bu sayı yeniden toplamda sayılmaz. Kabul gerçek SQLite ve mevcut
CLI/engine/platform sözleşmesiyle kontrollü fixture kullanır. Araştırma
testlerinde ağ/dış süreç açma assertion ile engellendi.

Doğrulanan davranışlar:

- Pasif kaynak, insan sınıflandırması ve aktif kontrol kapsamının ayrılığı;
  otomatik ilk keşfin insan kararı olmaması, `owned` ile kapsam açılmaması.
- Onay → ret → yeniden açma ve aynı durumda gerekçe güncellemesi;
  özgün olay kimlikleri, yalnız son kararın güncel sayılması.
- Aynı arşiv kaydının tekrarı, yeni eski gözlemin ithali, eksik kaynak
  tarihi ve iki sağlayıcının kanıtı; eski gözlem saatinin yenilenmemesi.
- Boş/başarısız sonraki keşifte adayın ve insan kararının korunması;
  bu görünümün son kaynak çalışması sağlığı diye sunulmaması.
- Kök → aday → kayıtlı DNS IP'si, ters yönün özgün yönü koruması,
  kayıtsız ad son ekinden ilişki çıkarılmaması; iki kökün aynı adayının
  farklı kararlarının ve iki firmanın kayıtlarının ayrılığı.
- Aktif kapsamı bulunan adayın reddinin bağımsız kapsamı değiştirmemesi.
- Satır/bayt/olay ön bütçeleri, bütün metin alanlarının decoder öncesi
  ölçülmesi, ilgisiz büyük kaydın yüklenmemesi, açık kısmi kapsam.
- Elli kanıt sınırında toplamın ve son kararın korunması; eski arşivin
  geç ithalinin yeni gözlemi gösterim dışında bırakmaması.
- Bozuk kök/domain, kayıp ilk keşif/kaynak, yanlış projeksiyon/geçiş,
  geçersiz hash biçimi ve eksik kök kaydının reddi.
- Saat gerilemesinde olay ekleme sırası, eşzamanlı yazmada tek okuma
  kesiti ve sayfa işaretinin karar değiştiğinde reddedilmesi.
- Gerçek aday `record.get` başvurusu, çalışan ayrıntı komutları, salt
  okumada dosyaların değişmemesi; yeni kararın inceleme farkına yansıması,
  IOC geri çekmesi üretilmemesi; eski v3 kaydı ve yedeğin korunması.

Günlükler `/tmp/xti-01610-regression.log`,
`/tmp/xti-01610-final-tests.log`; ham test verisi repoya alınmaz. Bu kabul
tam test paketi, yeni Linux CI, canlı kaynak, Tavily/Nmap veya büyük veri
kapasite kabulü değildir. Kaynak SHA-256 özgün kayıtla korunur; saklanmayan
sağlayıcı payload'ının doğrulandığı iddia edilmez. N-019 kapsamı belgeler.

```sh
umask 002
./scripts/python -m unittest tests.test_research tests.test_research_surface tests.test_research_suppliers tests.test_research_discovery tests.test_research_priority tests.test_research_history tests.test_surface_discovery tests.test_surface_discovery_history tests.test_surface_inventory tests.test_periodic_surface_history tests.test_asset_relations tests.test_supplier_candidates tests.test_engine_contract tests.test_engine_records tests.test_platform_engine tests.test_platform_isolation tests.test_platform_backup tests.test_source_jobs tests.test_source_jobs_usage tests.test_source_jobs_platform tests.test_architecture tests.test_ci_configuration
./scripts/python -m unittest tests.test_research_discovery
```

İlk komutun 350 sayısı son tek ek regresyondan öncedir; güncel dosya
aynı komutta 351 test seçer. Eşikler test geçmesi için gevşetilmedi.

## 0.160.0 — Tedarikçi adayı ve insan kararı araştırması

18 Kasım 2026, macOS arm64/Python 3.13.3; `1601e75` üzerine çalışma ağacı.
Çekirdek 75 ve kuyruk 2 değişmedi. Araştırma/değerlendirme modeli 2,
`research-priority-v3`; eski model 1 özgün okunur. İlk yeni model/kural
kaydı yeni başlangıçtır. Bu kabul kayıtlı veriyi okur; yeni ağ kaynağı yoktur.

| Doğrulama | Sonuç |
|---|---|
| `umask 002`; araştırma/öncelik/geçmiş, tedarikçi envanteri/adayı/izlemesi/riski, varlık ilişkileri, engine/platform, firma ayrımı, yedek, kaynak işleri, mimari ve CI | **336 test / 132,661 saniye; OK, atlama yok** |
| Son bozuk tedarikçi kimliğinin `storage_error` olarak sınıflanmasından sonra yeni araştırma, tedarikçi risk ve tehdit olayları | **42 test / 18,566 saniye; OK, atlama yok** |
| Ayrı iki firmalı gerçek süreç kabulü | **40,395 saniye; passed**; 36 okuma, p95 **0,578 saniye**, en yüksek alt süreç belleği **71.188.480 bayt** |

İki test demetinde **337 farklı test** vardır; tekrarlar toplanmaz.
32 yeni araştırma testi hızlı CI listesine dahil edildi. İlk 125 eski
regresyon ve 29 geliştirme testi bu toplama tekrar eklenmez.

Yeni kabulün kapsadığı davranışlar:

- Bekleyen/reddedilen/belirsiz adaydan tedarikçi onayı üretilmemesi;
  özgün CNAME kanıtı, kayıtlı PSL ve insan kararı kimliklerinin korunması.
- Onay → ret/yeniden açma, başka sağlayıcıya geçiş ve yeniden kabul;
  eski bağlantının özgün yeni kararla kaldırılmış gösterilmesi.
- Teknik kanıtın kaybolması, envanterin pasifleştirilmesi ve insan
  kararının ayrı kalması; yeni DNS kontrolünün adayı sessizce yenilememesi.
- İsim değişiminde kimlik/geçmişin korunması; aynı isimden birleştirme
  yapılmaması; teknik aday domaini ile envanter domaininin ayrılması.
- İki adımlı ters araştırma, gerçek `record.get` tedarikçi başvurusu,
  doğru ayrıntı komutları, firma ayrımı ve yedekten aynı kanıtı okuma.
- Seçili geçmişi doğrulama; ilgisiz büyük envanter içeriklerini yüklememe;
  satır/bayt sınırı öncesi ölçüm, kısmi kapsam ve gösterilmeyen kanıt sayısı.
- Eksik yaşam döngüsü, bozuk kimlik/kapsam/hash ve geçmişte silinmiş
  tedarikçi başvurusunu reddetme; dar geçmişi firma watermark'ı saymama.
- Eşzamanlı yazmada tek okuma kesiti; değişen sayfa işaretinin reddi;
  50'den fazla kararda son karar ve teknik kanıtın birlikte korunması.
- İnsan kararını ağ gözlemi/IOC iddiası gibi kabul etmeme, yaşını tehdit
  puanı yapmama; gerçek karar değişimini yalnız saat değişiminden ayırma.
- Model 1 geçmişinin değişmeden okunması, model 2'nin yanlışlıkla model 1
  olarak saklanmasının reddi ve yeni modelde karşılaştırma başlangıcı.

Yeni araştırma testleri ağ ve dış süreç başlatmayı assertion ile engeller.
Ayrı platform kabulü ise iki geçici firmada gerçek yerel süreçleri kullanır:
kaynak öncesi ve makbuz sonrası `SIGTERM`, çalışan işe ikinci worker/kurtarma
reddi, diğer firmanın çalışabilmesi, kalıcı kanıt ve aynı kesilmiş işe dönüş
doğrulandı. SQLite bütünlüğü geçti. Eşikler 120 saniye toplam, 5 saniye p95,
512 MiB alt süreç belleği ve 128 MiB disk olarak korundu. Bu kontrollü yük,
7/24 kapasite veya yeni tedarikçi grafiğinin büyük veri performans ölçümü değildir.

Geçici kanıtlar: `/tmp/xti-01600-regression.log`,
`/tmp/xti-01600-final-tests.log`, `/tmp/xti-01600-platform-acceptance.json`.
Son JSON SHA-256:
`bd543ebc4c26bfff41acdd3b1808ce1f59f1d2efaeb4b9ad6254d7ae4a489a9b`.
Ham test veritabanları repoya dahil değildir. Bu sonuç tam test paketi,
Linux veya Tavily/Nmap canlı kabulü değildir; N-004/N-005 açık kalır.
Kod geri dönüşünde yeni model 2 incelemelerinin eski motorla okunamayacağı
N-018'de kaydedildi; otomatik veri downgrade yapılmaz.

```sh
umask 002
./scripts/python -m unittest tests.test_research tests.test_research_surface tests.test_research_suppliers tests.test_research_priority tests.test_research_history tests.test_suppliers tests.test_supplier_candidates tests.test_supplier_watches tests.test_supplier_watch_integration tests.test_supplier_threat_events tests.test_supplier_risk tests.test_asset_relations tests.test_engine_contract tests.test_engine_records tests.test_platform_engine tests.test_platform_isolation tests.test_platform_backup tests.test_source_jobs tests.test_source_jobs_usage tests.test_source_jobs_platform tests.test_architecture tests.test_ci_configuration
./scripts/python -m unittest tests.test_research_suppliers tests.test_supplier_risk tests.test_supplier_threat_events
./scripts/python scripts/check-platform-acceptance.py --output /tmp/xti-01600-platform-acceptance.json
```

İlk komutun 336 sayısı son kimlik testi eklenmeden öncedir; aynı komut
güncel dosyayla 337 test seçer. Rapor dosyası zaten varsa kabul çalıştırıcısı
üstüne yazmaz; yeniden denemede yeni bir çıktı yolu seçilmelidir.

### 0.160.0 GitHub kabulünün sonucu

18 Kasım 2026'da `de80b54315ebb08d225676bd273dd0aeadaa7c1a` için dört
çalışma ilk koşuda başarılı tamamlandı:

- [Hızlı kontrol](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44263427247):
  Linux/Python 3.11, **1.635 test / 685,685 saniye; OK, atlama yok**.
- [Marka araçları kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44263427221).
- [Linux kurulum kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44263427297).
- [Firma izolasyonu/kurtarma kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44263427220):
  3.11.18 **78,487 saniye**, p95 **1,174 saniye**; 3.13.18 **95,733 saniye**,
  p95 **1,435 saniye**. İkisinde 36 okuma ve SQLite bütünlüğü başarılı.
  Eşikler değişmedi; N-016'daki eski başarısız koşuların kanıtı korunur.

Geçici günlükler `/tmp/xti-01600-quick-ci.log` ve
`/tmp/xti-01600-platform-ci.log`. Önceki tur sonunda hâlâ çalışan hızlı
kontrolün nihai sonucu bu turda okundu. Bu 0.160.0 commit'inin kabulüdür;
yeni 0.161.0 veya tam test paketi sonucu değildir.

## 0.159.0 — Kayıtlı CNAME ve TLS ilişki araştırması

18 Kasım 2026, macOS arm64/Python 3.13.3; `da2b0bb` üzerine çalışma ağacı.
Çekirdek 75, kuyruk 2 ve inceleme modeli 1 değişmedi. Öncelik politikası
`research-priority-v2`; eski v1 incelemeler korunur.

`umask 002` altında **266 test / 103,381 saniye; OK, atlama yok**.
Bu 24 yeni yüzey araştırma testi ile eski araştırma/öncelik/geçmiş,
DNS/CNAME/varlık ilişkileri, engine/platform sözleşmesi, firma izolasyonu,
yedek, kaynak işleri/kullanımı ve mimari kontrollerini içerir.
Günlük `/tmp/xti-01590-regression.log`; ham test DB'leri repoya dahil değildir.

Ek CI yapılandırması, URL/hash ve MISP regresyonu **68 test / 21,340
saniye; OK, atlama yok**. Günlük `/tmp/xti-01590-source-ci.log`.
İki demette toplam **334 farklı test** vardır; ilk dar tekrar bu toplama
yeniden eklenmez. Yeni yüzey araştırma testleri hızlı CI listesine eklendi.

Yeni kabul gerçek SQLite/CLI/JSON üzerinden kontrollü kayıtlarla yapıldı:

- CNAME her adımının yönü, yalnız son hedefe IP eklenmesi, kayıtsız hedef
  ve IPv6'dan ters araştırma, başarısız/kısmi/yok sonuçlarının ayrılması.
- Aynı bağlantının tekrarlarında tek ilişki ve ayrı özgün kanıtlar;
  değişen CNAME veya sertifikada eski gözlemlerin korunması.
- İki hostun gerçekten aynı sertifikayı sunması; SAN/wildcard/issuer
  benzerliğinden host veya sahiplik türetilmemesi; dosya IOC ayrımı.
- Son TLS/CNAME hatası, sertifika geçerlilik gerekçeleri ve yalnız zamanla
  değişen değerlendirme; yeni tehdit veya iddia geri çekmesi üretilmemesi.
- Satır/boyut/bağlantı/kanıt sınırları ve açık kısmi kapsam; büyük yeni
  kayıt okunamadığında eski kaydın son kontrol olarak gösterilmemesi.
- 50 IOC iddiası + son DNS/TLS/CNAME kontrolünde 52 kanıt sınırı;
  gösterilmeyen iddianın toplamı ve eksik kapsamın korunması.
- Bozuk hash/kapsam reddi, değişen sayfa işareti, eşzamanlı yazmada tek
  okuma kesiti, iki firmanın aynı sertifikasında izolasyon, yedekten okuma.
- V1 incelemenin özgün okunması ve v2'nin `policy_baseline` oluşturması;
  terminalin özgün ayrıntı komutlarının aynı veri alanında çalışması.

Yeni araştırma testlerinde ağ ve alt süreç başlatma assertion ile
engellendi; test süresince gerçek hedef sorgulanmadı. İlk geliştirme
koşularındaki üç hata test hazırlığındaydı: eski politika testinin v2'yi
"sonraki sürüm" sayması, engine komutuna olmayan `request` alt komutunun
eklenmesi ve firma fixture'ında kuyruk başlatmasının eksik olması.
Fixture/gelecek sürüm örneği düzeltildi; üretim sınırları gevşetilmedi.

Bu sonuç bütün test paketi, yeni Linux CI veya canlı hedef kabulü değildir.
Tavily ve gelişmiş Nmap N-004/N-005'te bekler. Mevcut CNAME/TLS kayıtlarını
ortak modelde okumak onların bugün tekrar doğrulandığı anlamına gelmez.
Tedarikçi kararları/pasif adaylar bu araştırma diliminde henüz yoktur.

```sh
umask 002
./scripts/python -m unittest tests.test_research tests.test_research_surface tests.test_research_priority tests.test_research_history tests.test_surface tests.test_cname tests.test_asset_relations tests.test_architecture tests.test_engine_contract tests.test_engine_records tests.test_platform_engine tests.test_platform_isolation tests.test_platform_backup tests.test_source_jobs tests.test_source_jobs_usage tests.test_source_jobs_platform
./scripts/python -m unittest tests.test_ci_configuration tests.test_indicator_enrichment tests.test_warninglists
```

### 0.159.0 GitHub kabulünün sonucu

18 Kasım 2026, `1601e75d625db6bddb0dc9a3400937841d8035bd`:

- [Hızlı kontrol](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44259845900),
  [marka kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44259845978)
  ve [Linux kurulum kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44259845890)
  ilk koşuda başarılı.
- [Firma kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44259846928):
  Python 3.13.18 ilk koşuda **94,359 saniye** / p95 **1,408 saniye** ile geçti.
  Python 3.11.18 ilk koşuda **120,015 saniyede** toplam süreyi tüketti.
  Tamamlanmış 36 okumanın p95'i **1,885 saniye**, eşik altındaydı;
  61. `alpha/recover` komutu başlarken **0,666 saniye** kalmıştı.
  Bu ilk koşuda kurtarma ve son bütünlük kabulü tamamlanmadı.
- Yalnız başarısız 3.11 işi **aynı commit ve aynı eşiklerle bir kez**
  tekrarlandı: **79,735 saniye**, p95 **1,186 saniye**, en yüksek alt süreç
  belleği **67.125.248 bayt**; kesinti/kurtarma ve bütünlük dahil başarılı.
  3.13 başarıyla tamamlandığı için yeniden çalıştırılmadı.

İlk koşu `/tmp/xti-01590-platform-ci.log`, tekrar
`/tmp/xti-01590-platform-ci-rerun.log` içinden ayrı okundu. Bu ölçümler
toplam bütçenin hangi aşamada tükendiğini gösterir; kesin altyapı veya
uygulama kök nedeni kanıtlamaz. N-016 açık/bilinen sınır olarak korunur.
Bu önceki sürümün sonucudur; 0.160.0 veya bütün paketin sonucu değildir.

## 0.158.0 — İş başına kullanım ve backend sınırı

18 Kasım 2026, macOS arm64/Python 3.13.3; `233b657` üzerine çalışma ağacı.
Çekirdek şema 75 ve kuyruk şeması 2 değişmedi. Yeni kaynak işi yürütme/sonuç
sürümü 2; eski v1 kayıtları ve kanonik istek anahtarları korunur.

| Doğrulama | Sonuç |
|---|---|
| `umask 002`; kullanım, kaynak işleri/platform, URL/hash/MISP, eski kuyruk, bekleme, firma ayrımı, yedek, CI ve mimari | **225 test / 73,971 saniye; OK, atlama yok** |
| Son sürüm bilgisi ve ortak istek tavanı hesabından sonra kullanım, kaynak işleri/platform ve mimari | **57 test / 17,544 saniye; OK, atlama yok**; önceki tura ek farklı test sayısı değildir |
| Yeni testler | 17 kullanım + 1 platform testi; mevcut firma restore testi gerçek HTTP adaptörüyle sayaç korunmasını da doğrular |

İlk yeni test denemesinde iki tekrar fixture'ının saati kaynak bekleme
süresince ilerlemiyordu; motor doğru şekilde yeni HTTP isteğini durdurdu.
Fixture saati üç saniye ilerletildi; üretim bekleme kuralı değiştirilmedi.
Kaynak tarafının 60 saniyelik 429 beklemesinde sıfır yeni istek ayrıca
sınandı. Ham ilk sonuç `/tmp/xti-01580-first-tests.log`; başarılı kayıtlar
`/tmp/xti-01580-regression.log` ve `/tmp/xti-01580-final-tests.log`.

Testler plan üst sınırı/gerçek HTTP açma sayısı, MISP ek koşul isteği,
manifest hatasında çoğalmayan tüketim, transport hatası/429, istek açılmadan
bütçe reddi, iptal, adımlar arası süre sınırı, makbuz commit öncesi kesinti,
çalışırken bilinmeyen kullanım, eski v1/aynı anahtar/açık v2 retry,
tekrarda eski kaynağı yeniden saymama, bozuk sayaç, kuyruk/yürütme süresi,
CLI/platform eşitliği, başka firma reddi ve backup/restore kapsamını içerir.

### Gerçek kaynak kabulü

İzole `xti-01580-live-91ya4cp7` firma alanında **17 platform çağrısı**
exit 0/boş stderr ile tamamlandı. İki iş de `complete`; sonuç ve aynı
anahtarla replay aynı kalıcı kullanım kaydını döndürdü. Firma yedeği alındı.

| İş | Planın en kötü istek sayısı | Ölçülmüş HTTP denemesi | Gözlem |
|---|---:|---:|---|
| `https://example.com/`, urlscan + MISP `rfc6761` + inceleme | 4 | **3** | MISP commit + liste: 2; urlscan: 1; inceleme: 0. urlscan `has_more=true` korundu |
| Önceki kabulün OpenSSL SHA-256 değeri, CIRCL + inceleme | 1 | **1** | CIRCL `matched`; inceleme: 0 |

URL işi `6571d7fa-8ce5-4797-8763-c76ecff8d22b`, hash işi
`7d5120f1-39fd-4b8e-a01a-9061ea37ec77`. İkisinde de ölçüm tam, transport
hatası/429/bütçe reddi sıfırdı. Bunların başarısızlık senaryoları kontrollü
testtedir; canlı ortamda bu hataları oluşturduğumuz iddia edilmez.
Geçici `evidence.json` SHA-256:
`6feddde8cd480de887b22ac9b076289964da9ddfaaece3cdd1ee7a5be567abcf`.
Günlük `/tmp/xti-01580-live.log`; ham çalışma verisi repoya dahil değildir.

Bu kabul hedef taraması, Tavily, gelişmiş Nmap, merkezi kota veya
faturalama doğrulaması değildir. HTTP açma denemesi sağlayıcıya teslim
veya ücretlendirilme garantisi vermez. Kesilen adım `null`/üst sınırla
gösterilir. Yeni sürümün tam test paketi ve Linux CI sonucu bu yerel
sonuçlardan çıkarılmaz; önceki 0.157.0 sonucu aşağıda ayrı korunur.

### 0.158.0 GitHub kabulünün sonucu

18 Kasım 2026 kontrolünde `da2b0bb42e3b2f2c82e4ec971ec5a03d3fc1b44c`
için aşağıdaki dört çalışma `completed/success` durumundaydı:

- [Hızlı kontrol](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44254840360).
- [Marka araçları kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44254840331).
- [Linux kurulum kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44254840411).
- [Firma izolasyonu kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44254840390).

Bu sonuç önceki 0.158.0 commit'ine aittir; 0.159.0 veya bütün test
paketinin tamamlandığı iddiası değildir. İlk başarısız eski Linux süre
ölçümleri ve takip notu N-016 silinmedi.

## 0.157.0 — Ortak kuyrukta kaynak yenilemesi

18 Kasım 2026, macOS arm64/Python 3.13.3; `9266fbf` üzerine çalışma ağacı.
Çekirdek şema 75 değişmedi; iş kuyruğu şema 2 açık/yedekli geçiştir.

- `umask 002` altında kaynak işleri/platform, eski kuyruk/profil,
  firma izolasyonu/yedek, URL/hash/MISP, inceleme geçmişi, engine,
  yükseltme, CLI, CI ve mimari: **272 test / 97,228 saniye; 270 başarılı,
  macOS'ta iki Linux atlaması, hata yok**. 38 yeni kaynak işi testi dahil.
- Gerçek SQLite/CLI/JSON üzerinde iptal yarışları, geçerli makbuzu yeniden
  kullanma, başarısız kaynağın eski veriyi koruması, kesinti sonrası açık
  tekrar, bütçe, yanlış firma/plan, bozuk olay, 32 tekrar sınırı,
  şema 1→2 yedek/rollback ve iki dosyalı restore doğrulandı.
- Yerel günlük `/tmp/xti-01570-regression.log`; geçici artefakttır.
  Linux tam paket sonucu aşağıda ayrı commit/CI kaydıyla verilir.
- Son saat gerilemesi/ebeveyn bağı denetimi ve CI süre ayarından sonra
  kaynak işleri, firma girişi, eski kuyruk ve CI'nin **70 testi / 19,274
  saniye** yeniden geçti; hata/atlama yok. Bu son tekrar önceki 272'ye
  ek farklı test sayısı olarak toplanmaz.

### Gerçek kaynaklarla platform kabulü

İzole `xti-01570-live-rq0x9_v8` geçici firma alanında 17 platform çağrısı
exit 0 ve boş stderr ile tamamlandı. İki kaynak işi de `complete` oldu.

| Kaynak | Gözlem |
|---|---|
| MISP `rfc6761` | Resmî kaynak listesi alındı; makbuz ayrı okunabildi |
| urlscan `https://example.com/` | `matched`, ilk yanıt sayfası; `has_more=true` korundu |
| CIRCL önceki kabulün OpenSSL SHA-256 değeri | `matched`, kayıtlı kaynak makbuzu okunabildi |
| İsteğe bağlı inceleme | İki ayrı kök için `baseline`; URL kapsam sınırı görünür |
| Aynı anahtar/plan | Tamamlanmış aynı iş döndü, ikinci kaynak sorgusu yapılmadı |
| Firma yedeği | Kaynak kanıtları ve kuyruk birlikte yedeklendi |

URL işi `b6c65620-18d4-4678-8f85-302308ed816b`, hash işi
`99741db7-0a8f-4c7d-b8ce-c22bd04ffd0c`. URL incelemesi
`9d7bb073-0990-4cb8-9633-c7dc959884ac`; hash incelemesi
`b74eb8e0-581f-43ad-858c-393003ccab9a`.
Ham istek/yanıt/zaman/çıkış kaydı geçici `evidence.json` içinde; dosya SHA-256:
`e495c1dfd8da9cb5255c9ce07549eedbafbacc4157128ab89fe9b7a3c35edf46`.
İlk deneme macOS `/var` yol takma adı nedeniyle `scope_unavailable` ile
durdu; hiçbir sorgu yapılmadı. Gerçek `/private/var` yolu ile yukarıdaki
izole koşu geçti. Ürün kapsam kontrolü gevşetilmedi. Hedef taraması,
dosya yükleme/indirme, Tavily veya Nmap çalıştırması yapılmadı.

Gerçek `./xti` alt süreçleriyle aynı yedek başka bir firma köküne geri
yüklendi: **10 çağrı** beklenen sonuçları verdi. İki tamamlanmış işin
özgün sonuçları, kaynak makbuzları ve incelemeleri aynen okundu. Yeni
workspace kimliği üretildi; eski kimlikle gönderilen iki yazma isteği
`scope_mismatch` / çıkış 1 aldı. Asıl alanın bütün dosya hash'leri aynı
kaldı. Geçici `restore-evidence.json` SHA-256:
`409064aae50ba381c0bb9d7617cd84e44d32a47bcbd368d08f62e3a155f90153`.

### Yerel kuyruk ölçümü

Ayrı geçici kuyruk, macOS arm64/Python 3.13.3; yalnız sırada kaynak
işleri, ağ/worker yok. Tek ölçüm örnekleridir; p95 veya SLA değildir.

| Bekleyen iş | Kuyruk byte | Tek durum okuma | İlk 20 işi listeleme | Bütün kuyruk doğrulama |
|---|---:|---:|---:|---:|
| 10 | 36.864 | 0,377 ms | 0,804 ms | 0,625 ms |
| 100 | 135.168 | 0,328 ms | 1,485 ms | 3,779 ms |
| 1.000 | 1.118.208 | 0,536 ms | 1,523 ms | 36,475 ms |

Tamamlanmış iş geçmişi, büyük kanıtlar, HTTP gecikmesi, firmalar arası
ortak kota ve eşzamanlı sunucu yükü bu ölçüme dahil değildir. Geçici
artefakt `xti-01570-queue-measure-3cgmqkw0/result.json`.

### İşletim kabulü

`94f1d9c95493633cf587d2233e50f3aed917345c` üzerinde Ubuntu/Python 3.13
tam çevrimdışı test paketi **2.858 test / 1.760,284 saniye; OK, atlama yok**
ile tamamlandı. [Tam CI](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44204469910).
Yerel günlük `/tmp/xti-01570-linux-full.log`; geçici artefakttır.
Sonraki `cfcfbe3` yalnız kabul betiğinin hata tanısını, ilgili workflow'u
ve belgeleri değiştirir. `git diff 94f1d9c cfcfbe3 -- src tests
pyproject.toml scripts/check scripts/check-fast` boştur; tam paket aynı
motor ve test kodunu kapsar. Tanı betiğinin ayrı kabulü aşağıdadır.

`94f1d9c` Linux/Python 3.11 hızlı paketi **1.561 test / 626,319 saniye**
ile hatasız ve atlamasız geçti.
[Hızlı CI](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44204405515).
Tanı güncellemesi `cfcfbe3` için
[son hızlı CI](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44205985460)
da başarılı tamamlandı.

`94f1d9c` üzerinde aynı ağsız iki firmalı alt süreç/kesinti kabulü yerelde
**38,635 saniyede geçti**; 120 saniye toplam, 5 saniye okuma p95 ve
512 MiB alt süreç bellek eşikleri değiştirilmedi. Gerçek SIGTERM,
rakip worker/recovery, diğer firmanın çalışması ve özgün makbuzların
korunması bu senaryonun parçalarıdır. Yerel artefakt
`/tmp/xti-01570-platform-local-processes.json`.

Linux kabulünün ilk Python 3.13 kolu 90,547 saniyede geçti; Python 3.11
kolu 120,011 saniyede `TimeoutExpired` ile toplam sınırda durdu. Aynı
commit ve aynı sınırlarla yalnız başarısız kol tekrar çalıştırıldı; ikinci
koşu da toplam süre sınırında durdu. Kesin kök neden henüz kanıtlanmadı.
Kabul aracı artık hatada tamamlanmış ölçümleri ve son komutu da saklar;
bu tanı davranışı kontrollü `TimeoutExpired` ile sınandı. Kabul eşikleri
değişmedi. [İlk koşu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44204405387/attempts/1),
[ikinci koşu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44204405387/attempts/2).

Tanı güncellemesi `cfcfbe3` ile, motor kodu/testleri ve kabul eşikleri
değişmeden **iki Linux kolu da geçti**:

| Python | Toplam | 36 okuma için p95 | En yüksek alt süreç RSS |
|---|---:|---:|---:|
| 3.11 | 80,290 saniye | 1,189 saniye | 67.096.576 byte |
| 3.13 | 96,601 saniye | 1,437 saniye | 66.527.232 byte |

[Başarılı kabul](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44205985536).
Tanı değişikliğinin 13 CI testi 8,801 saniyede geçti. Önceki süre aşımının
kök nedeni bu başarıyla kanıtlanmış sayılmaz; N-016 süre dalgalanmasını
takip eder. Bu koşu bütün dış sağlayıcılar veya 7/24 hizmet kabulü değildir.

### Önceki sürümün Linux doğrulaması

0.156.0'ın `9266fbfa4b27406cc29c09cd3404b04e3ec59559` commit'i Ubuntu/Python
3.13 tam paketinde **2.820 test / 1.134,595 saniye; OK, atlama yok**.
[Tam CI](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44200653217).
N-014 kapandı. Hızlı iş aynı commit'te GitHub'ın açık 15 dakika sınırına
takılarak iptal edildi; annotation `maximum execution time of 15m0s`.
0.157.0 sınırı 25 dakikaya çıkarır ve 38 yeni testi hızlı pakete ekler;
hiçbir test atılmaz. Yeni sürümün başarılı hızlı/tam CI sonuçları yukarıdadır.

## 0.156.0 — Kayıtlı inceleme ve değişim kabulü

17 Kasım 2026, macOS arm64/Python 3.13.3, çekirdek şema 75, başlangıç
commit'i `681a728` üzerine 0.156.0 çalışma ağacı. Kullanıcı veri alanında
geçiş yapılmadı. Yeni bölüm ağ/ücretli API/LLM gerektirmez.

| Tur | Sonuç |
|---|---|
| Yeni inceleme geçmişi | 31 test / 10,448 saniye; hata/atlama yok |
| Şema yükseltme/kurtarma kabulü | 18 test / 2,134 saniye; 16 başarılı, macOS'ta iki Linux atlaması |
| Tam paket, `umask 002; ./scripts/check`, son bağlantı düzeltmesi öncesi sabit aday | 2.819 test / 1.248,276 saniye; 2.814 başarılı, dört Linux atlaması, bir süreç sonlandırma izin hatası |
| Son bağlantı düzeltmesi: geçmiş/öncelik/araştırma/engine/platform/mimari | 115 test / 35,566 saniye; hata/atlama yok; geçmişin 32 testi dahil |
| İzin hatası veren kurulum testinin sandbox dışında tekrarı | Üç tekrar / 7,255 saniye; üçü de başarılı |

Yeni testler ilk başlangıç, 20 öğeden büyük incelemenin tamamını saklama,
zamanla eskime/süre dolumu, açık kaynak geri çekmesi, kaynak hatası,
kısmi kapsamda görünümden çıkma, normalize kapsam/yeni kural başlangıcı,
arşiv makbuzu değişirken aynı ilişkiyi koruma, MISP listelerinin eskimesi,
idempotent tekrar, eşzamanlı kayıt yarışı, yazma kesintisi, saat gerilemesi,
liste kesiti/sabit ayrıntı sayfaları, bozuk/taşan içerik, backup/restore,
74→75 geçişi/kesintisi, sahte eski şema, terminal güvenli gösterim,
engine salt okuma ve firma izolasyonu/restore sonrası yazma sınırını kapsar.

Tekrar komutları:

```sh
./scripts/python -m unittest tests.test_research_history -v
./scripts/python -m unittest tests.test_linux_upgrade_acceptance -v
./scripts/python -m unittest tests.test_research_history tests.test_research_priority tests.test_research tests.test_engine_contract tests.test_platform_engine tests.test_architecture -v
umask 002
./scripts/check
```

İlk geliştirme turunda yakalanan CLI parser isim çakışması düzeltildi.
Yükseltme aracının şema üst sınırı ve eski kabul beklentileri 75'e
taşındı; eski tablo/satır/kanıt korunması denetimi kaldırılmadı.
Başarısız geliştirme turları başarılı nihai kabul gibi sayılmaz.

**Tam paket sınırı:** Kod/test/betik hash'leri geniş koşu boyunca değişmedi.
Tek hata, mevcut theHarvester kurulumunun kendi alt süreç grubunu kapatırken
`os.killpg(..., SIGKILL)` çağrısında aldığı `PermissionError: [Errno 1]`
idi. Kod güvenle durdu; izin reddini yok sayan bir değişiklik yapılmadı.
Aynı test kısıtlı ortamda tek tekrarında 2,520 saniyede, ayrıca onaylı
sandbox dışı üç tekrarında geçti. Bu, ortam etkisini destekler; ilk tam
koşunun başarısızlığını sonradan başarılı saydırmaz. Güncel kod için tek
koşuda temiz Linux/tam paket kaydı N-014'te açık tutulur.

Tam koşu sonrasında yalnız yeni karşılaştırma kuralında bir uç durum
düzeltildi: Önceden kanıtı olmayan IP'ye DNS bağı gelmesi `time_only`
sayılmamalı. İlişkili bağların kararlı kimlikleri artık kanıt bağlamına
dahildir; arşiv makbuzu yenilenmesi aynı bağı kopmuş saydırmaz. Özel
regresyon testi eklendi. İlgili 115 test son kodla geçti; geniş koşu bu
son iki dosyalık değişikliğin ardından yeniden başlatılmadı. Böylece
tam paket sonucu ile son değişikliğin doğrulaması ayrı ve izlenebilir kalır.

### Önceden alınmış gerçek kaynak yanıtıyla terminal kabulü

`/tmp/xti-01540-live/xti.db` yalnız okunarak ayrı özel klasöre kopyalandı.
Kopya açık `migrate` ile yedeklenip 74→75 geçirildi. Gerçek `./xti`
başlatıcısıyla `https://example.com/` için ilk kayıt, ikinci kayıt,
aynı anahtarla tekrar, geçmiş, öğe sayfası ve devam sayfası çalıştırıldı.
Hepsi exit 0 ve boş stderr verdi. Engine `research.review.get` ile CLI
JSON öğe sayfası eşitti. 51 öğe tamamıyla saklandı; üç öğelik sayfada
`enrichment_result_window` ve kısmi kapsam görünür kaldı.
İlk sonuç `baseline`, ikinci `unchanged`; tekrar aynı kaydı döndürdü.

Asıl veritabanının önce/sonra SHA-256 değeri değişmedi:
`f566a32702ab783a00637a3cc1f2b33aaf31ce058f42fe7b81f9f2ccf6396087`.
İlk inceleme `4522441d-2104-44be-ac0f-11397242a945`, sonraki
`de32c741-e3b0-4cb3-b836-dc6e096a4669`. Bu saklı gerçek kaynak verisiyle
okuma/kayıt kabulüdür; yeni canlı kaynak sorgusu veya hedef güvenlik
testi değildir. Tavily, gelişmiş canlı Nmap ve kaynak kullanım hakkı
konularının açık kayıtlarını kapatmaz.

Yerel artefaktlar (repoyla dağıtılmaz):

- `/tmp/xti-01560-history-final.log`
- `/tmp/xti-01560-upgrade-tests.log`
- `/tmp/xti-01560-full-tests.log`
- `/tmp/xti-01560-full-manifest.json`: tam paket öncesi kaynak/test/betik
  hash'leri ve bitişte aynı kaldıklarının denetimi.
- `/tmp/xti-01560-final-regression.log`: son kodun 115 ilgili testi.
- `/tmp/xti-01560-harvester-recheck.log` ve
  `/tmp/xti-01560-harvester-unsandboxed.log`: tek/üç ayrı tekrar.
- `/tmp/xti-01560-final-validation.json`: son kod hash'leri, ilk koşudan
  değişen iki dosya ve bütün doğrulama sonuçları. Son kodla önceki gerçek
  kaynak incelemesi tekrar okundu; özgün JSON aynen korundu.
- `/private/var/folders/jm/lvrm0h653sb692bmcp431j580000gn/T/xti-01560-saved-acceptance-0wvepfj4/`:
  ayrı veri, geçiş yedeği, ham CLI çıktıları ve `result.json`.

Son kod/test/betik manifestinin SHA-256 değeri:
`5a6222b9a9e56219d70d63d4847fdc0975aedb080591c66b700d44c4aab90bff`.

## 0.155.0 — Gerekçeli inceleme sırasının yerel kabulü

17 Kasım 2026, macOS arm64/Python 3.13.3, `umask 002`, şema 74.
Başlangıç commit'i `681a728`; 0.155.0 çalışma ağacı. Yeni ağ kaynağı,
bağımlılık veya şema değişikliği yok. Doğrulama iki ilgili turda yapıldı:

| Tur | Sonuç |
|---|---|
| Yeni öncelik + mevcut araştırma + mimari | 50 test / 24,285 saniye; hata ve atlama yok |
| Engine/kayıt/platform/izolasyon/yedek, URL/hash, warninglist, bileşen, haber ve CI uyumu | 181 test / 69,097 saniye; hata ve atlama yok |

İlk tur 26 yeni öncelik kabulünü içerir. İkinci turdan sonra yapılan
küçük bağlam sıralama/gösterim düzenlemesi ilk turda yeniden doğrulandı.
Son terminal kapsam açıklamasının Türkçeleştirilmesi ayrıca üç ilgili
gösterim testinde 1,147 saniyede hatasız doğrulandı; bunlar aynı 26 testin
tekrarıdır, farklı test toplamına eklenmez.
Bu **231 farklı ilgili test**tir; 0.155.0'ın bütün test paketinin tekrar
çalıştırıldığı iddiası değildir. Tam paket kaydı aşağıda ayrı commit için tutulur.

Doğrulanan davranışlar: bütün sınırlı araştırmayı yol sayfasından önce
sıralama, kararlı öğe sayfalaması, kaynak durum farklarının ayrı kalması,
güven puanı/tekrar sayısıyla oy üretmeme, güncellik sınırı ve değişen
kesitin reddi, gelecek zaman, eski DNS sonrası başarısızlık/yeni başarı,
bilinen eşleşme yokluğu ve sonra kaynak kesintisi, MISP+IOC bağlamı,
URL gözlem tarihi ile dosya yanıt tarihinin ayrımı, kesilen kanıtı gösterme,
JSON/terminal tutarlılığı, kontrol karakterlerinin güvenli gösterimi,
kayıp/bozuk veri ve cevap boyutu sınırı, iki firma, devre dışı/bilinmeyen
firma, eşzamanlı kaynak geri çekme, salt okuma ve yedekten aynı sıra.
Testlerde beklenmeyen ağ ve alt süreç çağrıları engellidir.

Tekrar komutları:

```sh
umask 002
./scripts/python -m unittest tests.test_research_priority tests.test_research tests.test_architecture -v
./scripts/python -m unittest tests.test_engine_contract tests.test_engine_records tests.test_platform_engine tests.test_platform_isolation tests.test_platform_backup tests.test_indicator_enrichment tests.test_warninglists tests.test_components tests.test_component_pins tests.test_news_integration tests.test_ci_configuration -v
```

Yerel günlükler `/tmp/xti-01550-priority-tests.log` ve
`/tmp/xti-01550-integration-tests.log`; repoyla dağıtılmaz. Öncelik testi
`scripts/check-fast` listesine eklendi. Bu kayıt Linux veya yeni bir GitHub
koşusunun sonucu değildir.

### Önceden saklanmış gerçek kaynak yanıtıyla kullanım

`/tmp/xti-01540-live` içindeki önceki gerçek urlscan yanıtı, gerçek `./xti`
başlatıcısı üzerinden terminal/JSON/engine ile okundu. `https://example.com/`
kökünde 51 düğüm+ilişki öğesi toplandı; `--limit 3` yalnız üç öğeyi gösterdi,
devam sayfası ve `enrichment_result_window` kısmi kapsamı korundu. CLI ve
engine aynı öncelik kesitini/öğe sırasını verdi; veri dosyalarının önce/sonra
SHA-256 değerleri değişmedi. Bu arşiv kaydıyla okuma kabulüdür; yeni canlı
API sorgusu veya `example.com` güvenlik bulgusu değildir. Kaynak koşulları
ve Tavily/Nmap canlı kabulünün açık maddeleri devam eder.

Son kayıtlı okuma artefaktları `/tmp/xti-01550-final-read-16p37cgl/`;
CLI/engine kesiti
`e7e839763d0cef39897a3e22d0a272ccb712d35811025c4e210fe2d0970aaba2`.
Terminalin son sade kapsam açıklaması `/tmp/xti-01550-final-terminal.txt`
ile ayrıca görüldü. Bu geçici dosyalar repo içeriği değildir.

## 0.154.0 — Sabit commit üzerinde tam test

17 Kasım 2026, **`681a728c0397bba0d48172d8b0d9a1b1aacf563c`**.
N-010'u kapatmak için `git archive` ile ayrı bir çalışma kopyası alındı;
bu kopyada test sırasında kod/test değiştirilmedi. Yeni 0.155.0 çalışması
ana dizinde ilerledi ve bu tam turla karıştırılmadı.

- Ortam: macOS arm64, Python 3.13.3, `umask 002`; uygulama 0.154.0/şema 74.
- Komut: kopyanın kökünde `./scripts/check`.
- Başlangıç/bitiş: **14:00:13–14:23:58 UTC**.
- Unittest sonucu: **2.762 test / 1.420,951 saniye**, exit 0;
  **2.758 başarılı, dört atlama, hata yok**.
- Dört atlama: Linux `/proc` süreç sahipliği için iki test ve
  `systemd-analyze` için iki test. Linux'a özgü kabul iddia edilmedi.
- Öncesi/sonrası kaynak dosya SHA-256 değerleri aynı. Python'un yüklediği
  `xti` yolu bu ayrı kopyanın `src/xti/__init__.py` dosyası, sürüm 0.154.0.

Yerel kopya ve günlük:
`/tmp/xti-01540-baseline-brfeg8r6/checkout`,
`/tmp/xti-01540-baseline-brfeg8r6/full-check.log`,
`/tmp/xti-01540-baseline-brfeg8r6/result.json`.
Başlatıcı dahil ölçüm 1.425,575 saniyedir; üstteki süre unittest ölçümüdür.
Geçici artefaktlar repoyla taşınmaz. Commit/sürüm/komut ve sonuç burada kalır.

Bu tur iki eski kaynak envanteri beklentisi düzeltildikten sonraki tam
paket kabulüdür. Önceki 2.761 testlik başarısız tur, eski kayıtta korunur.
0.155.0 özelliğinin yukarıdaki ilgili testleriyle birleştirilip tek bir
0.155.0 tam paket sonucu diye sunulmaz; Tavily/Nmap canlı kapsamı değişmez.

## 0.154.0 — URL/hash kaynak bağlamı kabulü

17 Kasım 2026, Python 3.13.3/macOS, `umask 002`, çekirdek şema 74.
İlgili son tur **125 test / 37,136 saniye**, 123 başarılı ve Linux'a özgü
iki süreç kontrolü atlamasıyla tamamlandı; hata yok. Yeni kaynak bölümü
29 test içerir. Ham yerel günlük `/tmp/xti-01540-targeted.log`; dosya
makineye özgüdür ve repoya dahil edilmez. Bu sayılar tam paket kabulü değildir.

Kapsam: URL/hash doğrulaması, kesin URL yol/sorgu/HTTP ayrımı, dış yanıt
kimliği, kaynak statüsü, JSON/kayıt bozulması, hata sonrası eski iyi yanıt,
sonraki boş yanıt, çalışma geçmişi, salt okuma, şirket ayrımı, schema73→74
yedekli geçiş/kesinti, restore, araştırma kesiti ve yönlendirme/IP bağı.
Önceki araştırma, warninglist, kaynak kataloğu/durumu, CLI, mimari ve Linux
güncelleme kabulünün yerel yardımcı testleri de bu turdadır.

Gerçek API kabulü ayrı `/tmp/xti-01540-live` alanında yapıldı:

| Sorgu | Gerçek sonuç |
|---|---|
| CIRCL dokümanındaki OpenSSL SHA-256 | HTTP 200, dosya metadata kaydı ve iki diğer hash bağlantısı |
| urlscan `https://example.com/` | HTTP 200, ilk 20 public arşiv kaydı; ek sonuç sınırı görünür |
| Sıfırlardan oluşan MD5, SHA-1, SHA-256 | Üç HTTP 404, geçerli `no_match` yanıtı |

Kaynak sorgularında hedef web sitesi açılmadı; dosya yüklenmedi/indirilmedi.
URL arşivinin o andaki kayıtları değişebilir; bulgular güvenlik kararı değildir.
CIRCL dosya tarihi bilinmediğinde gözlem tarihi uydurulmadı. Kaynak koşulları
ve [kullanım sınırları](INDICATOR_ENRICHMENT.md) ayrı kayıtlıdır.

**Önceki 0.153.0 GitHub kontrolü:** `58e388c` için Linux kurulum, marka
kurulumu ve platform izolasyonu başarılı oldu. [Hızlı kontrol](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44085249292)
1.436 testte tek envanter beklentisiyle başarısızdı: `test_multi_source_cli`
dört yeni MISP kaynağını beklemiyordu. Gerçek günlük incelendi; beklenti
bu teslimde MISP ve yeni URL/hash kaynaklarıyla güncellendi, ilgili CLI
kabulü geçti. Önceki başarısız koşu sonradan başarılı olarak sunulmaz.

## Önceki raporlar

16 Kasım 2026. Kullanıcı kendi Linux VM denemesini paylaştı: sürüm
0.147.1, çekirdek şema 69, bildirilen Python 3.14.7; gerçek domain ile
kontrollü örnek kayıtların birlikte kullanıldığı izole veri alanı.
Rapor 50 komut ailesine dokunulduğunu ve 2.603 testte bir hata olduğunu
bildiriyor. Ham test günlüğü ve veri alanı bu çalışma ortamında yoktur.
Bu sayılar kullanıcı raporudur; burada yeniden ölçülmüş sonuç değildir.
Sonraki bölümler **0.150.0 / `888f403` ikinci Linux raporunu**, ardından
Nmap/kaynak raporunu ve bunlardan sonra yapılan yerel düzeltmeleri ayrı
değerlendirir.

İnceleme 0.150.0 / şema 72 çalışma ağacında yapıldı. Önceki rapor sonraki
Nmap teslimlerini kapsamaz. Yeni düzeltmeler veritabanı geçişi, bağımlılık
veya platform sözleşme sürümü değişikliği gerektirmez.

## 0.153.0 — MISP warninglists kabulü

17 Kasım 2026. `16650117` sonrası çalışma ağacı, uygulama 0.153.0,
çekirdek şema 73; macOS/Python 3.13.3, `umask 002`.

Yeni warninglist testleri kontrollü kaynakla gerçek SQLite/CLI/engine/platform
sınırlarını çalıştırır. İstenmeyen ağ/alt süreç başlatma reddedilir.
Kapsam: CIDR/hostname sınırları, yanlış domain eşleşmesi, bozuk/eksik veri,
HTTP boyut/süre/yönlendirme, değişen kaynak koşulları, başarısız yenilemede
son iyi içeriği koruma, kaynak atfı ve tekilleştirme, geçmiş/sayfalama,
firmalar arası ayrım, salt okuma ve araştırma sayfa kimliği, yedek/restore,
şema 72→73 geçişi ve kesintide geri alma. Eski şemadan geçiş yardımcıları
da 73'e güncellendi; diğer tablolardaki kanıtlar korunur.

İlk geniş ilgili turda 197 test çalıştı: yeni dört kaynak ve şema 73 için
iki eski envanter beklentisinin güncellenmesi gerekti. Düzeltme ve kaynak
koşulu kontrolünden sonraki warninglists/kaynak/upgrade turu:
**55 test / 11,880 saniye, hata yok, Linux `/proc` gerektiren iki atlama**.
Günlükler `/tmp/xti-warninglists-regression.log` ve
`/tmp/xti-warninglists-followup.log` dosyalarındadır; repoya eklenmez.

Son kaynak kataloğu, CLI ayrıntısı ve v1 işlem envanteri düzenlemeleriyle
warninglists/components/news/source-catalog/CLI/architecture kontrolü:
**64 test / 27,807 saniye, hata ve atlama yok**. Yeni warninglist
dosyasının 26 testi bu tura dahildir. Kaynak kataloğunda dört referans
listesinin anahtarsız, zorunlu ücreti olmayan ve hedefe bağlanmayan
niteliği de doğrulandı. Günlük:
`/tmp/xti-warninglists-final-compatibility.log`.

### Tam paket ve son tekrarların ayrımı

`umask 002; ./scripts/check` turu **2.732 test / 1.231,703 saniye**
çalıştırdı: 2.726 başarılı, iki test beklentisi hatası, dört atlama.
İki hata `test_components` ve `test_news_integration` içinde, engine
işlem listesinin yalnız dört eski işlemden oluşmasını bekleyen
assertion'lardı; eklenen araştırma/warninglist işlemlerini reddediyordu.
Bu beklentiler önceki işlemleri koruyup yeni işlemlere izin verecek
şekilde düzeltildi. Yeni warninglist işlemlerinin manifestte bulunması
ayrıca açıkça denetlenir. İlgili iki dosya yukarıdaki son **64 testin
tamamı geçen** tekrarına dahildir. Son CLI gösterimi/kaynak kataloğu
düzenlemeleri de o tekrarda ve gerçek CLI çıktısında doğrulandı.

Tam paketin ham günlüğü `/tmp/xti-warninglists-full.log` dosyasındadır.
Düzeltmelerden sonra bütün paket yeniden çalıştırılmadı; bu nedenle ham
tam tur sonucu `FAILED (failures=2, skipped=4)` olarak korunur, tek bir
tamamen yeşil tur diye sunulmaz. Güncel test envanterine eklenen kaynak
kataloğu testi son ilgili turdadır. Açık kalan atlamalar: Linux `/proc`
ile süreç sahipliği/timeout için iki test, `systemd-analyze` ile iki
zamanlama dosyası testi. Bu ortamda Linux kabulü iddia edilmez.

### Gerçek kaynak kabulü

Gerçek `warninglists sync` ayrı
`/tmp/xti-warninglists-live-20261117-01530` alanında çalıştırıldı.
2026-11-17 10:38:01–10:38:04 UTC, dört listenin tamamı başarılı;
upstream commit `40e2b570fda2e5443a2d6fa1d1db16c37ab0a956`.

| Liste | Kaynak sürümü | Üye | Ham içerik SHA-256 |
|---|---|---:|---|
| Cloudflare | 20261014 | 22 | `5871c8b2bd48356dff7a6a601a1a10c9e170d649e4c8ed06a1edef32549cdcfa` |
| RFC1918 | 20220705 | 3 | `ef1374626d6d98ddac70e6bcdc533e4f76eee744c46ba99e3e6eddbc14e169a3` |
| RFC3849 | 20220705 | 1 | `54a82c687e3efa5ab64cd33dd719bcd8f01c0f41f6bce43a1f82dbf10612b7d0` |
| RFC6761 | 20261022 | 25 | `d1a1d87ab67a2e08bd040bfa17270338effde7477e9e1b5cfb3ad3fa880f8b56` |

Gerçek indirilen 51 üye üzerinde yapılan yerel okumalar:

| Sorgu | Doğrulanan sonuç |
|---|---|
| `104.21.6.71` / IP | Cloudflare, `104.16.0.0/13` |
| `10.1.2.3` / IP | RFC1918, `10.0.0.0/8` |
| `2001:db8::1` / IP | RFC3849, özgün `2001:DB8::/32` |
| `www.example.com` / domain | RFC6761, `example.com` |
| `notexample.com` / domain | Eşleşme yok; alt metin yanlış eşleşmesi oluşmadı |

CLI ve engine aynı kaynak/çalışma kimlikli eşleşmeyi verdi. Araştırma
kökü için yalnız liste bağlamı bulundu: `not_recorded`, sıfır ilişki;
liste üyeliği IOC veya aktör bağı üretmedi. Okumalardan önce/sonra veri
alanındaki dosyaların hash'leri aynı kaldı. Hiçbir örnek IP/domain aktif
olarak sorgulanmadı. Kullanıcının mevcut veri alanı taşınmadı/değiştirilmedi.

Yerel kanıtlar: `/tmp/xti-warninglists-live-sync.json`,
`/tmp/xti-warninglists-live-acceptance.json`. Bu geçici alanlar ve indirilmiş
kaynak dosyaları Git'e alınmaz. Sonuç bu kaynak sürümünün kabulüdür;
gelecekteki sağlayıcı erişimi, Linux dağıtımı veya üretim kapasitesi garantisi değildir.

## 0.152.0 — İlişkili kanıt araştırmasının yerel kabulü

17 Kasım 2026. `f2bb818` sonrası çalışma ağacı, uygulama 0.152.0,
çekirdek şema 72; macOS/Python 3.13.3, `umask 002`. Yeni ağ kaynağı veya
aktif hedef sorgulanmadı. Yeni testler ağ bağlantısını ve alt süreç
başlatmayı hata veren mock'larla kapatır; gerçek SQLite kayıtları kullanır.

```sh
umask 002
./scripts/python -m unittest tests.test_research tests.test_architecture \
  tests.test_engine_contract tests.test_engine_records tests.test_platform_engine \
  tests.test_platform_isolation tests.test_cti_context tests.test_asset_relations -v
```

Sonuç: **110 test / 44,354 saniye, hata ve atlama yok**. Ham yerel günlük:
`/tmp/xti-research-acceptance-final.log` (repoya alınmaz). Yeni araştırma dosyasında
23 kabul testi vardır. Ana senaryolar:

- Domain → IP → CTI kaydı iki adım; özgün ilişki yönü ve kaynak/iddia/olay
  kimlikleri; kanonik domain/IOC tek düğümde, özgün referanslar korunur.
- İki firma aynı IP'yi kullanırken özel kanıtları birbirine görünmez.
  Bilinmeyen veya kapalı firma kişisel alana yönelmez.
- Ortak IP'den sahiplik/aktör ilişkisi üretilmez. Farklı aktör iddiaları,
  eski DNS + son başarısız kontrol, geri çekilmiş ve süresi dolmuş kaynaklar
  ayrı durumlarla görünür. Döngüler iki adımlı basit yolu uzatmaz.
- Kararlı yol sayfası, kanıt değişince `snapshot_changed`, tek SQLite
  okuma işlemine rağmen ayrı yazıcının eşzamanlı commit'iyle karışmayan kesit.
- DNS/CTI penceresi, düğüm/bağ/yol, kaynak gösterimi ve byte sınırları
  eksik kapsamı açık verir. Bozuk DNS hash'i veya çarpıtılmış CTI etkinliği
  sağlıklı kanıt diye okunmaz. Kaynak geçmişi bütçesi aşılırsa sonuç yoktur.
  Byte bütçesine sığmayan son DNS kontrolünün yerine eski olumlu kontrol
  “son kontrol” diye gösterilmez; eski gözlem yalnız tarihî bağda kalır.
- Yönetilen IOC beslemesinin gerçek makbuz kimliği korunur. Yerel geri
  çekme kararı için besleme çalışması uydurulmaz.
- 10.001 kontrollü ilgisiz CERT Polska IOC kaydı dar araştırmayı engellemez.
- Terminalde verilen ayrıntı/devam komutları boşluk içeren seçili veri
  alanında gerçekten çalıştırılır. CLI ve engine kayıt okumaları byte'ları
  değiştirmez. `record.get` referansları açılır. Yedekten geri dönüş aynı
  düğüm/kanıt/yol kimliklerini ve sonucu verir.

İlk test geliştirme turunda yeni platform fixture'ının macOS geçici yolundaki
symlink kökü reddedildi; test yolu `resolve()` ile düzeltildi, üretim koruması
korundu. Büyük katalog fixture'ının eski yayın tarihi de gerçek kaynak
güncellik kuralınca reddedildi; fixture test saatine getirildi. Son tur
yukarıdaki 110 testin tamamını bu düzeltmelerle çalıştırdı.

Gerçek varsayılan veri alanında `research securehup.com --type domain`
ayrıca denendi. Alan önceki şemada olduğundan mevcut kontrol `storage_error`
ve yedekli `./xti migrate` yönlendirmesi verdi. Kaynak veya veri geçişi
çalıştırılmadı; bu deneme SecureHup için başarılı canlı araştırma sayılmaz.
Yeni özellik şema değişimi gerektirmez, fakat mevcut motor gibi güncel
şema 72 alanı ister. Tavily, gelişmiş canlı Nmap ve Linux güncel sürüm
kabulünün önceki açık koşulları bu testlerle tamamlandı sayılmaz.

## Doğrulanan ve düzeltilenler

| Bulgu | Yerel doğrulama | Sonuç |
| --- | --- | --- |
| CTI izleme ekleme/listeleme hatası | Tam ve kontrollü CERT Polska biçiminde 10.001 IOC eklendi; dar aktör izlemesi aynı kapsam hatasıyla durdu. | Kayıtlı arama denetimi artık yalnız çalışma sonuçlarının başvurduğu kayıtların varlığını indeksli sorguyla kontrol eder. İlgisiz katalog büyüklüğü izleme sayısı sınırına sayılmaz. Ekleme, iki ardışık çalışma ve listeleme geçti. |
| Zamanlı yedek testi `umask 002` altında kırılıyor | Bildirilen test aynı izin hatasıyla yeniden üretildi. | Test kendi klasörünü `0700` ile oluşturur. Üretim kodunun ortak yazılabilir klasörü reddetmesi korunur. |
| Yeni veri/yedek klasörünün izinleri umask'a bağlı | `000`, `002`, `022`, `077` maskeleriyle oluşturma, yedekleme ve geri yükleme sınandı. | Yeni klasörler ve oluşturulan ara klasörler `0700`, veritabanı/yedek dosyaları `0600`. Mevcut klasörlerin izinleri otomatik değiştirilmez. |
| Eski klasörlerin geniş izinlerinin görünmemesi | Veri klasörü `0775`, yedek klasörü `0755` yapıldı; byte'lar ve izinler okuma öncesi/sonrası karşılaştırıldı. | `storage readiness` sahibi/mod bitleri ve erişim durumunu terminal/JSON içinde gösterir. Riskli veya doğrulanmamış izinlerde yerel kurtarma durumu `attention` olur. |

CTI denetiminde gerçek kopuk sonuç bağlantıları, bozuk geçmiş ve tutarsız
hash'ler hata vermeye devam eder. “Listeleme hiçbir koşulda hata vermesin”
önerisi uygulanmadı: bozuk kanıtı sağlıklı liste gibi sunmuyoruz. Ayrı bir
tanılama görünümü gerekirse bozuk kayıtları açıkça işaretleyebilir.
Kayıtlı arama/geçmiş/sonuç sınırları ve CTI aramasının kendi kapsam
sınırları korunur; bu değişiklik sınırsız arama iddiası değildir.

İzin kontrolü veri alanı, `backups` ve `scheduled-backups` klasörlerinin
POSIX sahibi ve mod bitleriyle sınırlıdır. ACL, tüm üst dizinler veya
uzak dosya sistemi yetkileri için eksiksiz güvenlik denetimi sayılmaz.
Firma alanının mevcut daha sıkı erişim doğrulaması ayrı kalır.

## Kalan rapor maddelerinin kararı

| Rapor maddesi | Değerlendirme | Sonraki kabul ölçütü |
| --- | --- | --- |
| Kısmi kanıtın “başarılı kayıt yok” ile karışması | 0.151.0 kaynak tablosu ve kuruluş terminal/HTML görünümünde düzeltildi. Son deneme, tam sonuç ve güncellik birlikte açıklanır. | Kısmi kanıt, tamamlanmış boş sonuç, eski başarı ve hiç çalışma yok ayrımı doğrulanır. JSON'un ayrı durum/zaman alanları korunur. |
| Uzun collect/search/kuruluş raporu | 0.151.0'da açık `--summary` eklendi; ayrıntılı varsayılan görünüm korunur. | Kaynak hataları/kapsam notları, sayfalama ve özette gösterilmeyen sayılar açık kalır; aynı veri alanında kayıt ayrıntısı açılır. |
| Tavily yapılandırma durumu | Anahtar yokken çalışmanın durması beklenen davranış. İçerik görünümünde `not_checked`, `check_failed`, `no_content`, `content_found`, eski/belirsiz durumlar zaten var; ayrı anahtar hazırlık bilgisi yok. | Gizli anahtar okunup çıktılanmadan yapılandırma hazırlığı gösterilmeli; “kontrol yapılmadı” ve “kontrol başarılı, boş” ayrımı korunmalı. Canlı Tavily kabulü hâlâ bekliyor. |
| Platform iş yanıtı biçimi | Mevcut v1 sözleşmesinde belgeli: submit/status/cancel için `data.job_id`; result için `data.job` ve `data.result`. | [Platform belgesindeki](PLATFORM_ENGINE.md) biçim korunur. Değişiklik gerekirse sürümlü geçiş yapılır; yalnız görünüm birliği için mevcut istemci kırılmaz. |
| Schedule parametreleri | `--output` / `--at` README'de mevcut. Günlük kullanım rehberine doğrudan örnek eklendi. | [Günlük kullanım](DAILY_USE.md) örneği geçerli; `--output-dir` desteklenen bayrak olarak gösterilmez. |
| crt.sh 502 ve bekleme | Kaynak hatası doğrulanmış boş sonuç değildir. Adaptörde sınırlı timeout tekrarı, `Retry-After` ve 429 beklemesi zaten var. 502'nin kendiliğinden düzeleceği garanti edilemez. | Önceki başarı ve tekrar önerisinin gösterimi iyileştirilmeli. `Retry-After` bulunmayan 5xx için hata/bekleme metni ve sınırlı tekrar politikası ayrıca test edilmeli. |
| Webhook özel IP kaydında erken uyarı | Gönderim anındaki engel raporda çalışmış. Kayıt anı uyarısı ayrı kullanım iyileştirmesi olarak açık. | Erken uyarı olsa da gönderim anındaki adres doğrulaması korunmalı; kayıt sırasında ağ isteği gerekmemeli. |

## Raporun sonuçlarını yorumlama sınırı

- Komut ailesine dokunmak, bütün alt komutların ve bütün hata yollarının
  kabul edildiği anlamına gelmez. Başarılı, boş, yapılandırma engelli ve
  kontrollü örnek verili denemeler ayrı tutulur.
- Kontrollü ürün/CVE ve CTI örnekleri hedef firmada gerçek zafiyet ya da
  aktör ilişkisi kanıtı değildir. Sosyal profil ve sahiplik kararları da
  otomatik tehdit doğrulaması sayılmaz.
- Raporda Cloudflare olarak belirtilen IP'nin portları, firmanın kaynak
  sunucusunun port envanteri sayılmaz. Kesin IP seçimi ve domain DNS
  eşleşmesi, IP üzerinde tarama yetkisinin ayrıca doğrulanmasının yerini
  tutmaz. Bu incelemede aktif hedef trafiği üretilmedi.
- “Kritik açık bulunmadı” bu denemenin gözlemidir; eksiksiz güvenlik
  denetimi, üretim kapasitesi veya sonraki sürümün bütün kabulü değildir.

## Tekrar doğrulama

Önce bildirilen CTI ve umask sorunları mevcut kodda yeniden üretildi.
Düzeltmelerden sonra `umask 002` ile CTI izleme, depolama, izin görünümü ve
zamanlı yedek testlerinin 44'ü 12,473 saniyede geçti. Yeni testler hızlı
kontrol listesine de eklendi. Son kodun tam turu aynı `umask 002` altında
2.665 testi 1.145,005 saniyede tamamladı: 2.661 başarılı, macOS'ta Linux'a
özgü dört atlama, hata yok. Ortam macOS 26.6.2 arm64 / Python 3.13.3.
[İşlevsel kabul kaydı](FUNCTIONAL_ACCEPTANCE.md) bu sonucu önceki
sürüm ve canlı kaynak denemelerinden ayrı tutar.

```sh
umask 002
./scripts/check
```

Bu komut yerel testleri çalıştırır. Testler içinde `000`, `002`, `022` ve
`077` maskeleri ayrı geçici klasörlerle doğrulanır. Kullanıcının VM'inde
son kodla tekrar kabul ve gerçek Nmap çalışması bu ilk inceleme sırasında
açıktı. Aşağıdaki ikinci rapor daha sonraki kullanıcı denemesidir.

## 0.150.0 / 888f403 ikinci Linux raporu

Kullanıcı 16 Kasım 2026'da tam SHA
`888f4033209d5af71e7292d43c6faa0f2a2f07a2` için yeni rapor iletti.
Rapor; Linux x86_64, Python 3.14.7, `umask 002`, yeni şema 72 alanlarında
2.665 testin 1.366,371 saniyede hatasız ve atlamasız geçtiğini bildiriyor.
400 yardım bölümü, 399 komut yolu, 357 uç komut, dört engine ve 20 platform
işlemi güncel envanterle uyumludur. 97 senaryonun 84'ü başarılı, biri
başarısız ve 12'si engelli olarak bildirilmiştir. Ham `commands.jsonl`,
matrisler ve kanıt dosyaları kullanıcının Linux makinesindedir; bu ortamda
yalnız rapor metni incelendi. Bu sayılar yeni yerel ölçüm değildir.

### Bulgu kararları ve yerel düzeltmeler

| Bulgu | Karar |
|---|---|
| O-1, platform search içindeki kişisel alan ifadesi | Ortak arama notu “seçili çalışma alanı” olarak düzeltildi; hem kişisel hem firma kapsamına uygundur. `scope.mode` ve veri ayrımı değişmedi. |
| O-5, tekrar `brand watch-revoke` çökmesi | `unchanged` çıktısı eklendi. Aynı sorun aynı tanımla tekrar `watch-add` için de yeniden üretildi ve düzeltildi. Terminal/JSON yanıtları başarılıdır; tekrarlar karar/tanım geçmişine yeni olay eklemez. |
| O-2/O-3, bulunamayan kuruluş/profil kodları | Mevcut v1 davranışı korundu ve işlem bazında belgelendi. Biçimi doğru bilinmeyen/yabancı kuruluş ve bilinmeyen profil `invalid_parameters/2`; bilinmeyen genel iş `not_found/3`; farklı profil sürümü `profile_changed/1` döndürür. Ayrı geçici firma alanlarıyla tekrar doğrulandı. |
| O-4, platform çıkış kodları | [Platform belgesine](PLATFORM_ENGINE.md#hata-ve-süreç-çıkış-kodları) çıkış ve hata kodu tabloları eklendi. Engine belgesindeki mevcut tablo korunur. |
| CTI 10.001 IOC sınırı | Yeni kullanıcı raporu hem regresyon testinin hem dar aktör izlemesinin geçtiğini bildiriyor; eski katalog sorunu bu commit için açık hata olarak taşınmaz. |
| Platform Nmap başarı yolu için hedef bulunmaması | Boş alanda beklenen ön koşul eksikliğidir. Hedef/izin mevcut yönetici CLI'siyle aynı firma alanına eklenebilir; SQL düzenlemesi gerekmez. Hazırlık ve plan → iş örneği [belgelendi](PLATFORM_ENGINE.md#nmap-işleri-ve-arayüz-seçenekleri). |

Nmap kabul testi artık iki firmayı ve hedeflerini ürünün CLI komutlarıyla
hazırlar. Yeni test platformdan plan/kabul, açık worker, dört hedefin
sayfalı kanıtı, aynı isteğin tekrarı, tamamlanmış işin yeniden
çalıştırılmaması ve yabancı firma sonucu reddini doğrular. Yalnız Nmap
çalıştırıcı yanıtı kontrollüdür; gerçek ağ ve yeni subprocess başlatma
engellidir. Bu, canlı Nmap başarısı veya ayrı bir yeni platform işlemi
teslimi değildir. Çekirdek şema 72 ve v1 sözleşme sürümü korunur.

### Açık kabul sınırları

- 400 yardım ekranı ve 97 senaryo, 357 uç komutun bütün başarılı/hatalı
  yollarının kabulü değildir. O-1 ve O-5 iki bulgudur; senaryo özetindeki
  tek FAIL ile bağlantıları ham matriste ayrıca gösterilmelidir.
- Kullanıcı TCP-connect/partial Nmap sonucu bildiriyor; SYN, UDP, OS ve
  seçili NSE canlı kabulü yapılmış sayılmaz. Cloudflare edge gözlemi
  origin envanteri veya IP tarama yetkisinin kanıtı değildir. Yetkili
  kontrollü hedefte gerçek platform worker kabulü ayrıca gerekir.
- Tavily anahtarı kullanıcı tercihiyle sonraya bırakılmıştır. crt.sh
  502 erişim sorunudur. Supplier/ransomware adayının bulunmaması başarı
  yolunu sınamak için ayrı kontrollü veri gerektirir; ürün bugı değildir.
- Vendor evidence/source hataları ve uygun olmayan exposure girdisi
  için tam girdi, hata yanıtı ve senaryo kanıtı henüz bu ortamda yoktur.
  Sağlayıcı kesintisi, geçersiz ürün kimliği ve ayrıştırıcı hatası tek
  `source_error` başlığında doğrulanmış ürün hatası sayılmaz.
- Kullanıcının asıl `.xti-data/xti.db` dosyası raporda şema 69, yeni test
  alanları şema 72'dir. Kod güncellemesi eski alanı kendiliğinden taşımaz.
  Kişisel alanda normal kullanıma geçmeden `./xti migrate` çalıştırılır;
  komut geçiş öncesi yedek alır. Özel alan için `--data-dir` açık seçilir.

Son yerel doğrulamada `umask 002` altında 39 ilgili test 21,727 saniyede
geçti; hata veya atlama yok. Bu tur tam suite yerine aşağıdaki kapsamı
çalıştırdı. Kullanıcının 2.665 testlik sonucu, bu yeni çalışma ağacının
tam test sonucu olarak sunulmaz. Bilinmeyen/yabancı kuruluş, bilinmeyen
profil, değişmiş profil sürümü ve bilinmeyen iş cevapları ayrıca geçici
firma alanlarında doğrulandı.

```sh
umask 002
./scripts/python -m unittest tests.test_brand_username_watches tests.test_global_search tests.test_platform_engine tests.test_nmap_execution.PlatformNmapTests -v
```

## Nmap/kaynak raporunun incelenmesi — 17 Kasım 2026

Kullanıcının `XTI_NMAP_KAYNAK_RAPORU.md` içeriği yine temiz `888f403`
checkout'unda çalıştırıldığını bildiriyor. Bu rapor yukarıdaki yeni yerel
düzeltmelerin kabulü değildir. Linux veri alanı burada bulunmadığı için
UUID'lerle verilen kayıtların içeriği doğrudan doğrulanamadı.

### Gerçek Red Hat belgesiyle doğrulanan ayrıştırma hatası

Raporda `CVE-2021-44228` belgesindeki
`"Red Hat JBoss Enterprise Application Platform "` ürün kimliğinin
sonundaki boşluk sağlayıcı hatası olarak sınıflandırılmış. Bu gerekçe
doğru değil: [CSAF 2.0 şemasında](https://docs.oasis-open.org/csaf/csaf/v2.0/os/schemas/csaf_json_schema.json)
ürün kimliği önceden tanımlı biçimi olmayan, en az bir karakterlik
metindir. Boşluk tek başına kimliği geçersiz yapmaz. XTI'nin kimliği
`strip()` sonucuyla karşılaştırıp reddetmesi uyumluluk hatasıydı.

Resmî [Red Hat belgesi](https://security.access.redhat.com/data/csaf/v2/vex/2021/cve-2021-44228.json)
bu ortamda indirildi: HTTP 200, 3.622.781 byte, belge sürümü `3`, SHA-256
`fb1a0ea32097ac50dab59b3b441550c0e1fe8e92ced4a4c7581c248e711a4d06`.
Aynı değiştirilmemiş byte'lar eski ayrıştırıcıda rapordaki hatayı verdi.
Düzeltmeden sonra hem yerel ayrıştırma hem gerçek kaynak adaptörünü
kullanan CLI önizlemesi başarılı oldu:

```sh
./xti --data-dir /tmp/xti-vex-live-review-20261117 --json vuln vendor-preview CVE-2021-44228 --provider redhat
```

JSON `ok: true`, aynı kaynak özeti ve `fixed: 122`, `known_affected: 4`,
`known_not_affected: 2254`, 26 düzeltme kaydı gösterdi; stderr boştu.
Bunlar üretici belgesindeki ürün bağlamlarıdır, SecureHup varlıklarına
ait zafiyet sayıları değildir. Kaynak byte'ları/CLI çıktısı yalnız `/tmp`
altında tutuldu; repo veya kullanıcı veritabanına eklenmedi.

Kimlik başındaki/sonundaki boşluklar artık aynen korunur. Bu kural ürün
ağacı, ilişki, durum ve düzeltme başvuruları ile kanıt seçimi, kalıcı
okuma/yazma ve yeniden kontrolde tutarlıdır. `id` ve `id ` birleştirilmez.
PURL/CPE doğrulamaları, kontrol karakteri yasağı ve uzunluk sınırı
korunur. Şema 72 ve bağımlılıklar değişmedi; eski kayıtlar yeniden yazılmaz.

### Rapordaki F-1 için eksik karşılaştırma

`vendor-match` açıkça `CVE-2014-0160` ile çağrılmış. `vendor-evidence-add`
ise CVE parametresi almaz; `58fa5887-64f7-4987-86ac-0e2d6dfadbf4`
maruziyetinin CVE'sini kullanır. Raporda aynı maruziyet Log4Shell Ubuntu
ve danışma kanıtı işlemlerinde de geçiyor. Bu nedenle iki çağrının aynı
CVE/dokümanı kullandığı kanıtlanmış değil; farklı belge kullanılması
olası açıklamadır. Maruziyet kaydının çıktısı olmadan bağımsız bir
`vendor-evidence-add` hatası doğrulandı sayılamaz.

Aynı Linux test alanında eksik bağı gösterecek salt okunur komut:

```sh
./xti --data-dir /tmp/xti-net-full --json vuln exposure-show 58fa5887-64f7-4987-86ac-0e2d6dfadbf4
```

Karşılaştırma ancak bu kaydın CVE'si, aynı etkin paket ve aynı belge
özetiyle yapılmalı. Yerel regresyon testi iki CVE için ayrı kaynak
sonuçları kullanır; önceki bağımsız eşleştirmeye rağmen kanıt ekleme
işleminin maruziyet CVE'sini, URL'sini ve kaynak özetini koruduğunu doğrular.

### Diğer sonuçların kapsamı

- Kesin yetkili IP/TCP/UDP portları verilmediğinden gelişmiş Nmap ve canlı
  platform Nmap başarı yolu açık kalır. Readiness/katalog ve boş alan
  retleri gerçek taramanın kabulü değildir. Yukarıdaki kontrollü platform
  testi hazırlık → plan → iş → worker → sayfalı sonucu kapsar; gerçek
  Nmap çalıştırmasıyla karıştırılmaz. Cloudflare IP'si hedef seçilmedi.
- crt.sh için gömülü kanıt XTI ve curl zaman aşımını gösteriyor. Sonraki
  HTTP 200 denemesinin komut/zaman/çıktısı raporda yok. Geçici sağlayıcı
  veya ağ gecikmesi olasıdır; yalnız sağlayıcı kök nedeni kesinleşmez.
  Timeout'ın doğru gösterilmesi başarılı veri alımı anlamına gelmez.
- `php8.3/not_listed` ve etkisiz ürün reddi bildirilen koşullarda beklenen
  davranıştır. Ubuntu/advisory `action: unchanged` yanıtları tekrar
  kullanımını gösterir; bu tur yeni kanıt oluşturulduğunu göstermez.
- `/tmp/xti-net-full` için “read-only” ifadesi kullanılan
  `*-evidence-add` komutlarıyla garanti edilemez. Sonuç `unchanged` olsa
  bile bunlar yazabilen işlemlerdir. Yeni kabul bağımsız, yeterli disk
  alanına sahip bir kopyada; önce/sonra durum karşılaştırmasıyla yapılmalı.
- Tavily anahtarı, tedarikçi ve ransomware aday eksiklikleri bu dar
  incelemeyle giderilmiş sayılmaz. Canlı hedef yetkisi veya anahtar
  gerektiren bir işlem bu turda çalıştırılmadı.

### Yerel doğrulama

Önce iki yeni kimlik/kalıcılık testi eski kodda aynı kaynak hatasıyla
kırıldı. Düzeltmeden sonra `umask 002` ile 32 ilgili test 6,951 saniyede
geçti; hata veya atlama yok. Testler kimliklerin ayrılmasını, yanlış
kırpılmış başvurunun reddini, kontrol karakteri ve PURL/CPE sınırlarını,
kalıcı kayıt/tekrar/yeniden kontrol/yedekten dönüşü ve CVE bağını kapsar.
Önceki 2.665 testlik Linux sonucu bu yerel yamanın tam test sonucu değildir.

```sh
umask 002
./scripts/python -m unittest tests.test_vendor_advisory tests.test_suse_vendor_advisory tests.test_vendor_package_match tests.test_vendor_package_evidence tests.test_vendor_package_evidence_check tests.test_vendor_package_evidence_migration -v
```

## 0.151.0 — Kısmi kanıt ve kısa görünüm kabulü

Bu dilim yalnız gösterimi değiştirir. JSON'un kayıt/durum/kapsam alanları,
veritabanı şeması, kaynak çağrıları ve profil tanımı korunur. Mevcut engine
ve platform protokol sürümleri aynı kalır; motor sürümü 0.151.0 olur.

- `sources status` tamamlanmış sıfır sonuç, henüz çalıştırılmamış kaynak,
  son denemenin kısmi kanıtı, başarısız deneme ve korunan eski tam sonucu
  ayrı gösterir. `freshness=never` artık bütün kanıtın yokluğu gibi
  anlatılmaz. Sayılar kaynak satırının kapsamındadır.
- Kuruluş terminal/HTML raporunda kısmi web kanıtı varken tam başarı
  bulunmaması açık görünür; son kontrol kimliği ve hata korunur.
- `collect --summary` aynı kaynağı aynı biçimde çalıştırır. Genel yayıncı
  haberlerini dökmeden kaynak durumunu, varsa seçilmiş arama sonucunu,
  başlangıç ölçümünü ve başarısız yenileme nedeniyle atlanan karşılaştırmayı
  gösterir. Kısmi/başarısız toplama yine çıkış kodu 3 verir.
- `search --summary` sayfadaki bütün sonuçları kısa sunar; kapsam/hata
  notları ve sonraki sayfada filtreler korunur. Tam JSON kısaltılmaz.
- `organizations report --summary` bölüm başına mevcut sayfanın ilk üç
  kaydını, toplamı ve gösterilmeyen sayıyı verir. Tam sayfayı açma komutu
  veri klasörü, hedef/öğe sayfalaması ve güncellik eşiğini korur.
- Yeni ayrıntı komutları çalıştırılarak aynı veri alanındaki kaydı
  açtıkları, kaynak çağırmadıkları ve mevcut veritabanı byte'larını
  değiştirmedikleri doğrulanır. `analyze` güncel yerel veriden hesaplar;
  tarihî analizin dondurulmuş kopyası gibi sunulmaz.

Kontrollü RSS örneğinde aynı toplama sonucu ayrıntılı görünümde 124,
kısa görünümde 30 standart çıktı satırı üretti. NCSC zaman aşımı ve bu
nedenle atlanan haber araması her iki görünümde de kaldı. Bu yapay kaynak
örneğidir; canlı NCSC erişim veya gerçek firma araştırması sonucu değildir.
Tavily ve gelişmiş Nmap canlı kabulü bu teslimle tamamlanmış sayılmaz.

Son yerel tur `umask 002` altında **211 testi 227,090 saniyede** tamamladı;
hata veya atlama yok. Kaynaklar kontrollü örneklerdi. Bu ilgili regresyon
kapsamıdır; bütün test paketi veya Linux canlı kaynak kabulü değildir.
Kuruluş raporu testleri hızlı kontrol listesine de eklendi.

Doğrulama komutu:

```sh
umask 002
./scripts/python -m unittest tests.test_architecture tests.test_source_readiness tests.test_source_readiness_adapter tests.test_surface_discovery_status tests.test_surface_freshness tests.test_global_search tests.test_collection_cli tests.test_collection_news_cli tests.test_collection_watch_cli tests.test_collection_public_notice_cli tests.test_collection_profile_cli tests.test_collection_history_cli tests.test_organization_report tests.test_organization_content_report tests.test_organization_export tests.test_organization_workflow_cli tests.test_engine_contract tests.test_engine_records tests.test_platform_engine -v
```
