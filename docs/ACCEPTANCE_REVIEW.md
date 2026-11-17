# Linux kullanım raporunun değerlendirilmesi

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
