# XTI — Uygulanabilir İş Listesi

**15 Kasım 2026 son kapsam kararı:** Bu repo, mevcut .NET platformuna
bağlanacak XTI veri toplama ve analiz motorudur. Uygulama backend'i,
kullanıcı oturumları, roller ve web deneyimi .NET tarafındadır. Güncel
teslim sırasını [motor planındaki STB adımları](ENGINE_INTEGRATION_ROADMAP.md)
belirler; ENG kimlikleri korunur, yeni özelliklerden önce sağlamlaştırma
gelir. Gelecekteki .NET/PostgreSQL platformu mevcut SQLite kullanımını
değiştirmez; şimdi veritabanı geçişi yapılmaz. Motor özgün kanıt,
analiz, iş durumu ve güvenilir çağrı bağlamındaki kapsamı korur. Bu karar
bir bağlantıyı kurulmuş veya müşteri yalıtımını tamamlanmış saymaz.

**0.139.0 teslimi:** ENG-01'in ilk yerel okuma sınırı kullanılabilir:
`engine` üzerinden sürümlü arama, gerçek kayıt ayrıntısı ve kaynak durumu.
Mevcut CLI ve şema 64 korunur. [Kullanım/kabul sınırları](../ENGINE_CONTRACT.md).
.NET tüketicisi ve uzun iş bağlantısı ENG-05 altında açık kalır.

**0.140.0 teslimi:** ENG-02'nin mevcut üç araç temeli tamamlandı: ortak
pinler, açık kapsam ve kurulum gözlemi `components` / `components.list`
ile sunulur. Araç eksikken eski kanıt okunabilir, kurulum bilgisi kaynak
canlılığından ayrıdır. [Kullanım/kabul sınırları](../COMPONENTS.md).
Tam bağımlılık bütünlüğü ve theHarvester kurulum kesintisi/geri dönüşü
ENG-06'da açık; ENG-03 olay adayı ve kayıtlı genel arama işleri bekler.

**0.140.1 sağlamlaştırması:** Hızlı CI engine/bileşen testlerini kapsar;
araç kurulum filtreleri ve güncel komut/kaynak açıklamaları düzeltilir.
Sıradaki STB-02 temiz Linux kurulumu ve güncelleme/geri dönüş kabulüdür.
Veri/iş kurtarma, sır yönetimi ve ölçülmüş işletim devam eder; gelecekteki
.NET bağlantısı gerçek platform hazır olduğunda ayrıca doğrulanır.

**Hazır bileşen seçimi:** [Ayrı seçim planı](COMPONENT_SELECTION_PLAN.md)
mevcut kod kullanımı, ad benzerliği için RapidFuzz deneyi, haber için
feedparser ve motor paylaşım bileşenlerini kaydeder. Python'da ikinci
uygulama backend'i, oturum sistemi veya panel seçimi yapılmaz. Ölçüm,
sürüm ve gerçek entegrasyon kabulü açıktır.

14 Kasım 2026: [sekiz adımlı plan](ORDERED_INTEGRATION_PLAN.md) 0.133.0,
[kuruluş raporu ve ücretsiz devam dilimi](ORGANIZATION_WORKFLOW_PLAN.md)
0.134.0 ile uygulandı. Güncel sonuçlar [STATUS](../STATUS.md) içindedir.
0.135.0, HIBP'yi mevcut toplama/profil/zamanlama akışına bağlar;
[dört adımlı devam planının](PUBLIC_NOTICE_WORKFLOW_PLAN.md) ilk teslimidir.
0.136.0 ikinci teslimi ekler: açık kuruluş HIBP izlemesi, domain başına
sessiz başlangıç, atomik yerel bildirim ve tarihî kaynak/kapsam kanıtı.
0.137.0 kamu olayı vaka bağını ve çevrimdışı tam HTML raporunu ekler.
0.138.0 ilk üç yeni özelliği ekler: platform genelinde yerel arama, açık
tedarikçi kaynak değişim bildirimleri ve kayıtlı varlık ilişki geçmişi.
[Kullanım ve sınırlar](../SEARCH_SUPPLIERS_AND_RELATIONS.md). Otomatik HTML
rapor arşivi 15 Kasım 2026 kullanıcı kararıyla plandan çıkarıldı; eklenecek
işler arasında değildir. Mevcut komutla HTML dışa aktarımı kullanılabilir.
Gerçek Linux üzerinde klonla–kur–çalıştır kabulü entegrasyon ve pilot
doğrulamalarının açık işidir.
Kuruluş raporu, kapsamlı dönem/kaynak katkısı, önce/sonra kanıtları,
doğrudan CTI bağlamı ve HIBP kamu metadata kataloğu kullanılabilir.
Aşağıdaki eski sürüm notları tarihî kapsamı açıklar; geniş roadmap'in
tamamlandığı anlamına gelmez. Common Crawl dış indeks erişimi ve gerçek
Linux hizmet kabulü açıktır; .NET bağlantısı, LLM ve geniş marka ayrı
teslimlerdir. Mevcut toplama/monitor oturumları iş yürütme kayıtlarıdır;
kullanıcı oturumu değildir ve korunur.

**Tarihî özet (0.130, 14 Kasım 2026):** SUP-01/SUP-02 ve INT-01'in kişisel yerel çekirdeği tamamlandı. Birleşik kaynak durumu tarama, keşif, sosyal araç, IOC, ransomware ve ATT&CK kayıtlarını kapsıyor; günlük toplama–inceleme–vaka–tekrar rehberi ve bütünleşik testleri mevcut. Sıradaki iş gerçek kullanımda görülen kapsam boşluklarını ölçmek ve katkısı kanıtlanan açık kaynak adaptörlerini değerlendirmektir. Yerel API ile STIX/TAXII kullanıcı kararıyla beklemededir. Atama/rol/SLA takım ürününde; otomatik tedarikçi aboneliği/markalı rapor SUP-03 altında kalır. Sunucu envanteri, ürün/sürüm çıkarımı, paket takibi ve zafiyet eşleştirmesi aktif backlog değildir.

0.90.0, kayıtlı kanıtı değiştirmeden birleştiren `analyze DOMAIN` görünümünün ilk dilimidir. Yeni ağ işi başlatmaz; marka adayını, alt alan adı keşif durumunu, dış yüzey güncelliğini ve adaylarını, ayrıca güncel katalog varsa kesin domain/IP IOC eşleşmesini tek sonuçta gösterir.

0.91.0, açık `--refresh-ioc feodo` seçimiyle aynı kullanıcı akışında ücretsiz IOC tam listesini yeniler ve analizi yeniden üretir. Kaynak hatası önceki kataloğu korur ve eşleşme yokluğundan ayrı gösterilir; varsayılan analiz ağsız kalır.

0.92.0, CERT Polska son-ay etkin domain listesini ikinci bağımsız ücretsiz IOC kaynağı olarak ekler. Feodo IP ve CERT domain çalışmalarını/iddialarını ayırır; birleşik analiz kök domainle birlikte bütün kayıtlı marka/domain adaylarını görünüm sınırından bağımsız tam eşleşmeyle kontrol eder.

0.93.0, resmî MITRE ATT&CK Enterprise v20.0 tam STIX paketindeki etkin grup, kampanya, malware ve seçili ilişkileri kaynaklı CTI bilgi grafiğine atomik olarak alır. Teknik/taktik nesneleri, otomatik atıf, zamanlayıcı ve ayrı başarısız senkron geçmişi açık kalır.

0.94.0, pasif keşif, web, e-posta, sınırlı servis ve CNAME kanıtlarının güncel/eski/eksik/kısmi/başarısız ayrımını `surface exposures` içinde birleştirir; her boşluk için açık sonraki komutu verir. Ağ veya yazma başlatmaz.

0.95.0–0.103.0, ilk anahtarsız ransomware iddia akışını güvenli önizleme, kalıcı snapshot fark geçmişi, kuruluş/domain izlemesi, sınırlı ön plan tekrarı, denetlenebilir oturum, ağsız zaman çizelgesi, kimlik değişimi adayı ve gerekçeli insan karar zincirine dönüştürür. 0.104.0–0.108.0 ikinci RansomLook kaynağını, ayrı geçmişini, izleme ve kaynaklar arası insan incelemesini ekler. 0.109.0–0.118.0 Maigret ve Sherlock'u kabul kapısı, sınırlı önizleme, kalıcı fark, insan kararı, yerel bildirim ve kaynak-yalıtımlı izlemeye taşır. 0.119.0, theHarvester'ın yalnız Common Crawl/Wayback P0 hostname profilini mevcut pasif yüzey akışına bağlar; aktif özellikleri kapalı ve şema geçişi yedeklidir. 0.120.0–0.125.0 tedarikçi, vaka, klonla-çalıştır ve doğrulanmış sosyal araç kurulumunu tamamlar. 0.126.0, pasif yüzey için sağlayıcı bazlı kayıt sağlığı ve adaptör kabul kapısını ekler. 0.127.0 bu modeli etkin kaynak ailelerine genişletir; günlük kullanım ve tekrar/vaka testlerini ekler. Sonraki adaptörler gerçek kapsam boşluğuna göre seçilir; yerel API kullanıcı kararıyla beklemededir.

Bu liste [ana yol haritasının](MASTER_ROADMAP.md) uygulama karşılığıdır. Satırlar birer iş paketidir; büyük paketler başlamadan önce tek kullanıcı sonucuna sahip küçük görevlere ayrılır. [Kapsam matrisi](CAPABILITY_MATRIX.md) özellikleri bu kimliklere bağlar.

**Öncelik:** P0 = ilk teslim/kritik temel; P1 = sonraki ürün dilimi; P2 = kapsam genişlemesi; P3 = ürünleşme/kapasite. Öncelik bağımlılıkları geçersiz kılmaz. Örneğin geç fazdaki güvenlik işi, ilgili müşteri sürümü için zorunlu kapıdır.

**Boyut:** S = dar ve anlaşılmış; M = birkaç bileşen; L = araştırma ve çok sayıda kabul senaryosu; XL = başlamadan bölünmesi gereken program. Boyut takvim günü tahmini değildir. İlk dört döngüden sonra gerçek kapasiteyle tahmin yapılır.

**Kaynak profili:** B0 = mevcut bilgisayar; B1 = sürekli çalışma/ayrı yedek; B2 = veri erişimi/lisans/uzman operasyon ihtimali; B3 = müşteri hizmeti ve işletim bütçesi. `B0→B2` yerelde sınırlı uygulama kurulabilir, tam kapsam için dış kaynak gerekebilir anlamındadır.

Bir işin **tamamlandı** sayılması için teslimatı, aşağıdaki kabul kanıtı, gerekli testleri, kullanım açıklaması ve bilinen sınırlamaları bulunmalı. Kaynak erişimi eksikse kod bitse bile kapsam açık kalır. Önerilen kanıt konumu `docs/evidence/<iş-kimliği>/`; gerçek hassas kanıtlar repoya konmaz.

## R0–R1: Temel ve veri omurgası

| Kimlik | Teslimat | Önkoşul | Kabul kanıtı | Öncelik / boyut / kaynak |
|---|---|---|---|---|
| FND-01 | Üç kullanıcı senaryosu, kapsam, veri sözlüğü, ilk karar kayıtları | Yok | Her senaryoda girdi/çıktı/negatif örnek; G0 kontrolü | P0 / S / B0 |
| FND-02 | Python proje paketi, bağımlılık kilidi, CLI yardım ve doctor | FND-01 | Temiz ortam kurulumu ve internetsiz yardım/örnek çalıştırma | P0 / M / B0 |
| FND-03 | Workspace, varlık ekleme/listeleme, normalleştirilmiş benzersizlik | FND-02 | Tekrar domain, geçersiz değer ve kapat/aç testleri | P0 / M / B0 |
| FND-04 | Şema sürümü, migration düzeni, veri erişim sözleşmeleri | FND-03 | Eski örnek şema yükseltme; yarım geçişten kurtarma | P0 / M / B0 |
| FND-05 | Observation/Evidence/Finding/Feedback modelleri ve kayıtlı veri içeri alma | FND-04 | Kaynak→kanıt→bulgu izlenebilirliği; hatalı dosya sınırları | P0 / M / B0 |
| FND-06 | Kalıcı iş alma, lease, retry, tekrar güvenli sonuç yazımı | FND-05 | İş ortası kapanma ve eşzamanlı sahiplik denemesinde tek geçerli sonuç | P0 / L / B0 |
| FND-07 | Tutarlı backup/restore, kanıt manifesti ve doğrulama | FND-05 | Ayrı dizinde geri yükleme; kayıp/değişmiş kanıtın raporlanması | P0 / M / B0→B1 |
| FND-08 | Yapılandırma, sır ayrımı, güvenli terminal/log ve CI temel kontrolleri | FND-02 | Kontrol karakteri, sır maskeleme, dosya yolu ve kötü girdi testleri | P0 / M / B0 |
| FND-09 | Tek komutlu, ağsız ve salt-okunur birleşik dış risk analizi | PHI-05, ASM-03, CTI-01 | Marka/yüzey/IOC kanıtı tek anlık görünüm; eksik veri açık; ürün/sürüm/CVE sonucu yok | P0 / M / B0 |

## R2: Domain ve phishing adayları

| Kimlik | Teslimat | Önkoşul | Kabul kanıtı | Öncelik / boyut / kaynak |
|---|---|---|---|---|
| PHI-01 | IDN/public suffix normalleştirme ve aday üretim değerlendirme kümesi | FND-05, FND-08 | Kısa marka, alt domain, Unicode, meşru benzer ad ve bozuk girdi örnekleri | P0 / M / B0 |
| PHI-02 | Sürümlü domain benzerliği, marka eki, allowlist ve gerekçe | PHI-01 | Ayrılmış kümede precision/recall ve hata listesi; doğrulanmış phishing etiketi yok | P0 / L / B0 |
| PHI-03 | Seçilen CT kaynağı adaptörü, kayıt konumu ve kaynak durumu | FND-06, PHI-01, FND-08 | Yeniden bağlantı, bozuk kayıt, tekrar sertifika ve veri boşluğu deneyleri | P0 / L / B0→B1 |
| PHI-04 | Kontrollü DNS/TLS zenginleştirme ve URL erişim sınırları | PHI-02, FND-06, FND-08 | Zaman aşımı/özel ağ/yönlendirme/yanıt boyutu testleri | P1 / M / B0 |
| PHI-05 | Bulgu listele/göster/karar/not ve açıklanabilir öncelik | PHI-02 | Aday→inceleme→onay/ret/bilinmiyor; geri bildirim izi korunur | P0 / M / B0 |
| PHI-06 | Bildirim kaydı, kontrollü teslim, JSON dışa aktarma | PHI-05, FND-06 | Aynı fixture 10 kez işlendiğinde tekil bulgu; teslim tekrar politikası görünür | P0 / M / B0 |

## R3: Güvenilir işletim

| Kimlik | Teslimat | Önkoşul | Kabul kanıtı | Öncelik / boyut / kaynak |
|---|---|---|---|---|
| OPS-01 | Kaynak kataloğu, erişim/koşul/kota/kapsam/sağlık alanları | PHI-03 | Bozuk kaynak ile sıfır bulgu ayrı gösterilir; kaynak kapatma kaydı | P0 / M / B0 |
| OPS-02 | Kuyruk sınırı, retry/karantina, checkpoint ve kesinti görünümü | FND-06, OPS-01 | API kesintisi ve kaynak replay sınırlılığı senaryoları | P0 / L / B0 |
| OPS-03 | Retention, disk kotası, kanıt/log/yedek yaşam döngüsü | FND-07, OPS-01 | Süresi dolan kayıtlar doğru silinir; açık kanıt referansları sessizce kırılmaz | P0 / M / B0 |
| OPS-04 | Kaynak/işlem/gecikme/disk benchmark ve değerlendirme raporu | PHI-06, OPS-02 | Donanım+fixture+sürüm bilgili tekrar üretilebilir rapor | P0 / M / B0 |
| OPS-05 | Kurtarma, güncelleme, hata ve kaynak bakım runbook'ları | OPS-02, OPS-03, FND-07 | Kapatma/disk/kota/yedek tatbikatı; G3 raporu | P0 / L / B0→B1 |
| OPS-06 | İhtiyaç doğrulanırsa Textual inceleme ekranı | PHI-05, OPS-04 | CLI ile aynı sonuç; uzun işte arayüz donmaz; klavye ve iptal akışı | P2 / M / B0 |

## R4: Dış saldırı yüzeyi

| Kimlik | Teslimat | Önkoşul | Kabul kanıtı | Öncelik / boyut / kaynak |
|---|---|---|---|---|
| ASM-01 | Varlık ilişkileri, sahiplik aday/onay durumu ve keşif yolu | OPS-05 | CDN/paylaşımlı IP/aynı isimli şirket negatif örnekleri | P1 / L / B0 |
| ASM-02 | Domain/subdomain/DNS/TLS keşfi ve değişim geçmişi | ASM-01 | Kaynaklı ilk/son görülme; değişiklik tekrarında alarm çoğalmıyor | P1 / L / B0→B1 |
| ASM-03 | Sertifika süre/güven ve e-posta DNS yapılandırma kontrolleri; pasif keşif/web/e-posta/servis/CNAME boşlukları ve sonraki komutlar tek görünümde | ASM-02 | Kontrollü iyi/kötü TLS ve DNS örnekleri; eksik, eski, kısmi, başarısız ve kaynak-boş veri ayrımı | P1 / M / B0 |
| ASM-04 | İzinli kesin IP'de sınırlı port erişilebilirlik kanıtı; ürün, sürüm ve CVE çıkarımı aktif kapsam dışı | ASM-01, PHI-04 | Kapsam dışı adrese çağrı yok; açık port yalnız bağlantı kanıtı | P1 / M / B0 |
| ASM-05 | Açık panel, yanlış yapılandırma ve takeover adayları; ilk salt-okunur sınıflama ile CNAME hedef NXDOMAIN adayı var, panel/delegasyon/sağlayıcı doğrulaması açık | ASM-02, ASM-04 | Kontrol edilmiş laboratuvar; sahiplenme/exploit yapmadan kanıt seviyeleri | P2 / L / B0 |
| ASM-06 | Bulut/API/mobil varlık adayları ve dijital ayak izi görünümü | ASM-01, ASM-04 | Varlık tipi, keşif dayanağı ve sahiplik güveni görünür | P2 / L / B0→B2 |

## R5: Aktif plan dışında

Sunucu envanteri, ürün/sürüm çıkarımı, Ubuntu/Red Hat paket takibi ve CVE/KEV/EPSS eşleştirmesi kullanıcı kararıyla aktif backlog'dan çıkarıldı. Önceden uygulanmış kod ve şema kullanıcı verisi uyumluluğu için korunur; yeni teslim planı bu modülü genişletmez.

## R6: Tehdit istihbaratı ve avcılık

| Kimlik | Teslimat | Önkoşul | Kabul kanıtı | Öncelik / boyut / kaynak |
|---|---|---|---|---|
| CTI-01 | IOC alma/arama; kanonik domain/IP/URL/hash, bağımsız kaynak güveni/geçerliliği/gözlemi, geri çekme geçmişi, Feodo IP + CERT Polska domain tam-snapshot akışları ve birleşik analizde kesin domain/IP eşleşmesi var; yanlış-pozitif/suppression, otomatik yenileme ve daha geniş kaynak kapsamı açık | OPS-05 | Yerel yaşam döngüsü, iki kaynakta giriş/çıkış ve kesinti koruması, kaynak izolasyonu ve hüküm üretmeyen kesin eşleşme doğrulandı | P1 / L / B0→B2 |
| CTI-02 | Aktör, kampanya, malware ve rapor profilleri ile kaynaklı varlık/IOC ilişkileri çekirdeği ve MITRE ATT&CK v20 grup/kampanya/malware alt kümesi var; açık merge/split, zamanlı kampanya alanları ve gelişmiş grafik sorgusu açık | CTI-01 | Bağımsız kaynak, alternatif ad, çelişen atıf, geri çekme ve ATT&CK tam-snapshot yaşam döngüsü doğrulandı; otomatik birleşim/atıf yok | P1 / L / B0 |
| CTI-03 | Birleşik ağsız arama, kayıtlı sorgu, tam çalışma farkı, yerel bildirim, ön plan/toplu yenileme, yaşam döngülü etiket ve çalışma bağlı eklemeli analist notu var; kalıcı sistem zamanlaması ve dış kanal aboneliği açık | CTI-01, PHI-06 | Tanım, tam anlık görüntü, fark, bildirim, süre/tur/toplu kapsam, etiket/not bağı ve kesinti koruması doğrulandı | P1 / M / B0 |
| CTI-04 | Sürümü sabit MITRE ATT&CK grup/kampanya/malware ve seçili ilişki aktarımı var; teknik/taktik eşlemeleri ile teknik/stratejik raporlar açık | CTI-02 | v20.0 kaynak/sürüm/başvuru kanıtı doğrulandı; teknik eşleme ve kaynaksız çıkarım yapılmıyor | P2 / L / B0 |
| CTI-05 | YARA/Sigma gibi avcılık içeriğinin sürümlü kataloğu | CTI-02 | Desteklenen biçim doğrulama ve kaynak/lisans; üretim cihazında otomatik çalıştırma yok | P2 / L / B0→B2 |
| CTI-06 | Hash itibarı ve yetkili malware analiz raporu adaptörü | CTI-01, FND-08 | Numune paylaşım tercihi, sağlayıcı kotası, rapor kanıtı; otomatik yerel çalıştırma yok | P2 / L / B0→B2 |

## R7: Dark web ve kimlik bağlamı

| Kimlik | Teslimat | Önkoşul | Kabul kanıtı | Öncelik / boyut / kaynak |
|---|---|---|---|---|
| DWI-01 | İzinli kaynak bağlayıcısı, yalıtılmış toplama ve metin ayrıştırma | OPS-05, CTI-01 | Erişim/koşul kaydı; boyut/kota/kimlik bilgisi sınırları | P2 / L / B0→B2 |
| DWI-02 | Kuruluş/anahtar sözcük eşleme; haber/iddia/ilan ayrımı | DWI-01, PHI-05 | Türkçe/İngilizce, alıntı, eski tekrar ve isim benzerliği testleri | P2 / L / B0 |
| DWI-03 | Ransomware ve tehdit iddiaları; zaman çizelgesi | DWI-02, CTI-02 | İddia/teyit ayrımı; tekrar yayımlanan olay yeni ihlal sayılmıyor | P2 / M / B0→B2 |
| DWI-04 | Geçmiş arama, kaynak aboneliği, dil/kapsam ve veri boşluğu | DWI-01, CTI-03 | Yalnız mevcut tarihsel veri aranıyor; kapsanmayan dönem açık | P2 / L / B0→B2 |
| IDN-01 | Çalışan/müşteri kimlik maruziyeti ve maskeli eşleştirme | DWI-02, OPS-03 | Canlı veri öncesi minimizasyon, şifreleme/anahtar, erişim, silme ve çıktı testleri | P2 / L / B0→B2 |
| IDN-02 | Yetkili stealer/botnet verisinden cihaz/enfeksiyon/oturum/servis bağlamı | IDN-01, CTI-02 | Kanıtlı ilişki, veri minimizasyonu; parola/token kullanımı yok | P2 / XL / B2 |
| IDN-03 | Kimlik etkisi profili ve yetkili müdahale önerisi | IDN-02, CTI-02 | Kurumsal hesap/servis etkisi belirsizlikle gösterilir; salt öneri varsayılan | P2 / L / B2 |

## R8: Marka, VIP ve dolandırıcılık

| Kimlik | Teslimat | Önkoşul | Kabul kanıtı | Öncelik / boyut / kaynak |
|---|---|---|---|---|
| BRD-01 | Sayfa/görsel/logo/OCR aday analizi; yetkili sitede işaretçi/referrer telemetrisi | PHI-04, OPS-05 | Yalıtılmış inceleme; negatif örnekler; işaretçide kapsam/veri sınırı ve sahte sinyal testi | P2 / L / B0→B2 |
| BRD-02 | Doğrulanmış sabit Maigret/Sherlock kurulumu; güvenli/geniş/özel önizleme, kaynak-yalıtımlı kalıcı fark, tam profile bağlı insan kararı, olası taklit ortak kutusu ve karma toplu/ön plan yürütme var | DWI-02, OPS-01 | 6/5 güvenli ve 30/26 geniş kapsam; adres değişiminde karar taşınmıyor; kaynak kimliği değişmiyor; bildirim tekil/tarihsel; toplu/ön plan ve kurulum geri alma sınırları kanıtlı. Ek canlı kaynak doğruluğu, API erişimi/kota ve parodi ayrımı açık | P2 / L / B0→B2 |
| BRD-03 | Mağaza verisinden sahte mobil uygulama adayları | ASM-06, OPS-01 | Yayıncı, paket kimliği, marka ilişkisi ve kanıt | P2 / L / B0→B2 |
| BRD-04 | Yüzey web, yetkili kod/depo ve bulut maruziyeti | ASM-06, CTI-01, FND-08 | Sır kullanılmadan maskeli kanıt; kaynak/sahiplik/erişim sınırları | P2 / L / B0→B2 |
| BRD-05 | VIP/yönetici taklidi ve uygun veriyle dolandırıcılık göstergeleri | BRD-02, IDN-01 | Aynı isim negatifleri; canlı hassas veri öncesi erişim/şifreleme/maskeleme/silme | P2 / XL / B2 |

## R9: Tedarikçi istihbaratı

| Kimlik | Teslimat | Önkoşul | Kabul kanıtı | Öncelik / boyut / kaynak |
|---|---|---|---|---|
| SUP-01 | İnsan onaylı envanter, değiştirilemez ana domain, aynı isimli ayrı kuruluş, eklemeli geçmiş, son CNAME kanıtından teknik aday ve geri alınabilir gerekçeli kuruluş çözümleme kararı var | ASM-01, CTI-02 | Aynı isim/farklı domain, ortak kök eleme, tarihsel aday, kanıt zinciri, yalnız etkin kayıtlı tedarikçiye açık kabul ve karar geri alma doğrulandı | P2 / L / B0 |
| SUP-02 | ThreatCluster/RansomLook tam ad/domain dayanaklı iddia görünümü ve envanter+CNAME+kaynak kapsamı+iş önemi birleşik açıklanabilir inceleme kartı var | SUP-01, CTI-02, DWI-03 mevcutsa | İki kaynak ayrımı, aynı-ad belirsizliği, domain dayanağı, kesinti/eski/boş veri, kritiklik, neden/eksik veri/sonraki adım ve salt-okunur terminal/JSON doğrulandı; sayısal risk veya ihlal hükmü yok | P2 / L / B0→B2 |
| SUP-03 | İlişki zinciri, değişim uyarısı, dönemsel rapor ve kontrol çerçevesi eşlemesi | SUP-02, CTI-03 | Etki varsayımları; tekrarlanabilir rapor; çerçeve sürümü/dayanak, uygunluk iddiası yok | P2 / L / B0→B2 |

## R10: Paylaşım ve entegrasyon

| Kimlik | Teslimat | Önkoşul | Kabul kanıtı | Öncelik / boyut / kaynak |
|---|---|---|---|---|
| INT-01 | Kişisel yerel vaka, dondurulmuş kanıt, görev/not ve terminal/JSON geçmişi korunur; gelecekteki ekip atama/rol/SLA .NET platformundadır | CTI-02, PHI-05 | Mevcut vaka geçmişi ve kanıt kimlikleri korunmuş; yeni entegrasyonda asıl kayıt sorumlulukları açık | Yerel çekirdek tamam / B0 |
| INT-02 | Motor ile .NET arasında sürümlü istek/sonuç, iş durumu, hata, sayfalama ve güvenilir kapsam sözleşmesi; taşıma yolu ENG-05'te seçilir | ENG-01, OPS-05, INT-01 | Aynı örneğin .NET'te anlamı korunarak okunması; tekrar, kapsam dışı erişim, kesinti ve uzun iş kabulü | P1 / L / B0→B1 |
| INT-03 | STIX 2.1 destek matrisi ve TLP/izinli paylaşım | CTI-01, CTI-02, OPS-01 | Nesne/ilişki/zaman/marking doğrulama ve anlamlı gidiş-dönüş | P2 / L / B0 |
| INT-04 | TAXII 2.1 Collections istemci/sunucu kapsamı | INT-02, INT-03 | İkinci istemciyle sayfalama, yetki, güncelleme ve hata deneyi | P2 / L / B0→B1 |
| INT-05 | İmzalı webhook, SIEM/SOAR/talep ve istihbarat platformu adaptörleri; açık seçimli tek teslim/imza/deneme dilimi var, otomatik worker ve özel adaptörler açık | INT-02, PHI-06, INT-03 gerektiğinde | Her bağlayıcı için örnek ortam; kesinti, tekrar ve secret rotation testi | P2 / XL / B0→B2 |

## R10: Müdahale ve takedown

| Kimlik | Teslimat | Önkoşul | Kabul kanıtı | Öncelik / boyut / kaynak |
|---|---|---|---|---|
| RSP-01 | Aksiyon politikası, kanıt paketi, hak sahipliği ve onay kaydı | INT-01, PHI-05 | Alıcı/hedef/kanıt/içerik sürümü değişince onay düşer; gönderimde yeniden denetim | P2 / M / B0 |
| RSP-02 | Takedown başvuru, takip, ret/itiraz, kapanma ve tekrar kontrol | RSP-01, ilgili PHI/BRD modülü | Gönderim/kabul/kaldırılma ayrı durum; test muhatabıyla teslim | P2 / XL / B0→B2 |
| RSP-03 | Yetkili IdP/SOAR düzeltme iş akışı ve sonucun doğrulanması | RSP-01, INT-05, IDN-03 gerektiğinde | Dar yetki, dry-run, açık onay, teslim ve sonuç izi | P3 / XL / B2→B3 |

## R11: .NET platformu ile ortak işletim sınırı

Uygulama backend'i, giriş/kullanıcı oturumu ve panel bu repoda yeniden
yazılmaz. Aşağıdaki eski iş kimlikleri sorumluluk takibi için korunur.
.NET uygulama yetkisini belirler; motor doğrulanmış servis çağrısının
kapsamını iş, veri ve sonuç boyunca uygular. Yalnız bir `tenant_id`
parametresi güvenilir yetki kanıtı değildir. Mevcut kuruluş gruplaması
müşteri güvenlik sınırı sayılmaz.

| Kimlik | Teslimat | Önkoşul | Kabul kanıtı | Öncelik / boyut / kaynak |
|---|---|---|---|---|
| ENT-01 | İhtiyaç varsa PostgreSQL taşıma ve kurtarma planı | OPS-04, FND-04, INT-02 | Sayım/ilişki/özet karşılaştırması; sorgu, indeks, eşzamanlılık ve rollback | P3 / L / B1 |
| ENT-02 | .NET sorumluluğu: kullanıcı/kurum/rol, kullanıcı oturumu, MFA/SSO ve erişim iptali; motor doğrulanmış çağrı kapsamını alır | Mevcut .NET platformu, ENG-01 | Platform yetkisi ile motor kapsamının uyumu; iptal edilmiş veya kapsam dışı çağrı kabul edilmez | Platform tarafı; motor bağı ENG-05 |
| ENT-03 | Ortak sorumluluk: platform kapsamı ile motor depo/arama/dosya/cache/iş/sonuç/export ayrımı | ENG-01, ENG-05, ENT-02 | Her erişim yolunda başka kurum verisinin reddi; mevcut gruplar otomatik güvenlik sınırı sayılmaz | P1→P3 / L / B0→B3 |
| ENT-04 | .NET platformunun web/panel ve ekip inceleme deneyimi; motor veri ve analiz sözleşmesini sağlar | ENG-05, ENT-02, ENT-03 | Platformdan başlayan işin kaynaklı motor sonucuyla tamamlanması; bu repoda React/panel geliştirilmez | Platform tarafı; motor bağı ENG-05 |
| ENT-05 | Ortak denetim ve veri yaşam döngüsü; motor iş/kanıt izleri, yedek/kurtarma ve kapasite; platform kullanıcı/oturum izi ve hizmet işletimi | ENG-01, ENG-06, ENT-03 | İstek/iş kimlikleriyle izlenebilirlik; motor geri yükleme, saklama ve ortak kesinti tatbikatı | P1→P3 / L / B0→B3 |
| ENT-06 | .NET sorumluluğu: MSSP çalışma alanları, rapor markalama, abonelik ve ticari kota; motor teknik kaynak sınırı ve kapsamlı sonucu sağlar | ENT-02, ENT-03, ENG-05, ENG-06 | Müşteri geçişinde kapsam ve sonuç doğrulaması; ticari ölçüm motor kanıtını değiştirmez | Platform tarafı; motor bağı ENG-05/06 |

## R12: AI ve denetimli otomasyon

13 Kasım 2026 kullanıcı kararıyla isteğe bağlı LLM analiz desteği gelecekteki plana alındı; henüz uygulanmadı. İlk kapsam mevcut kanıtlardan açıklama, günlük özet ve vaka taslağıdır. Model kurulumu, ücretli API veya otomatik dış eylem bu plan güncellemesinin teslimi değildir. Ayrıntılar [LLM planında](LLM_PLAN.md); çekirdek LLM kapalıyken çalışır.

| Kimlik | Teslimat | Önkoşul | Kabul kanıtı | Öncelik / boyut / kaynak |
|---|---|---|---|---|
| AIM-01 | Etiketli örnekler, LLM'siz temel yöntem ve yerel model deneyi | Kayıtlı kanıt, kaynak durumu ve vaka örnekleri | Ayrılmış test kümesi; doğruluk, eksik bilgi, inceleme süresi, gecikme ve bellek ölçümü | P2 / M / B0 |
| AIM-02 | Kaynaklı bulgu açıklaması, günlük özet ve vaka taslağı | AIM-01, ilk AIM-05 kontrolleri | Kanıt atfı, belirsizlik, dış metindeki talimatlara direnç ve model kapalı/hatalı testi; insan kararı değişmez | P2 / L / B0→B2 |
| AIM-03 | Salt okuma yerel sorgu asistanı; sonrasında metinden varlık çıkarımı ve gerekçeli inceleme/ilişki önerileri | AIM-02, kapsamı sınırlı yerel okuma servisleri | Serbest SQL/kabuk yok; sorgu kapsamı, kanıt atfı, süre ve veri sınırı; REST API gerekmez | P3 / L / B0→B2 |
| AIM-04 | Ayrı kapsam kararı gerektiren araç/MCP ve onaylı çok adımlı iş akışları; ilk LLM kapsamı dışında | AIM-03; dış eylem için ayrıca kapsam ve yetki | Dar araç listesi, kayıtlı karar/onay, durdurma; onaysız dış eylem yok | P3 / XL / B2→B3 |
| AIM-05 | İlk deneyden itibaren model/prompt/kanıt sürümü, kaynak sınırı ve geri dönüş | AIM-01 ile birlikte | Kayıtlı yapılandırma, her güncellemede aynı değerlendirme, gerilemede geri dönüş; harici API ancak açık seçimle | P2 / M / B0→B2 |

## R13: Kapsam ve işletim olgunluğu

| Kimlik | Teslimat | Önkoşul | Kabul kanıtı | Öncelik / boyut / kaynak |
|---|---|---|---|---|
| COV-01 | Dil/bölge/tarihsel veri ve kaynak yedekliliği programı | OPS-01, OPS-04, ilgili modül | Kaynak katkısı, veri boşluğu, erişim koşulu ve maliyet raporu | P2 / XL / B1→B2 |
| COV-02 | Metrikle tetiklenen broker/search/object/graph ölçek geçişleri | OPS-04; ilgili yük | Önce/sonra ölçüm; taşıma, tutarlılık ve geri dönüş tatbikatı | P3 / XL / B1→B3 |
| COV-03 | Bağımlılık güvenliği, SBOM, dağıtım doğrulaması ve bağımsız inceleme | FND-08; hizmet için ENT-05 | Bağımlılık envanteri, güncelleme/kritik açık ve sürüm doğrulama kaydı | P1→P3 / L / B0→B3 |
| COV-04 | Analist hizmeti, destek, uzman kaynak operasyonu ve eşdeğerlik incelemesi | İlgili ürün kapıları | Sorumlu, hizmet hedefi, finansman, müşteri kapsamı ve tarihli matris | P3 / XL / B2→B3 |

## İlk çekilecek işler

Temel izleme, kişisel vaka/tedarikçi çekirdeği ve 0.138.0 teslimleri
kullanılabilir. Geçerli sıra [motor entegrasyon planındadır](ENGINE_INTEGRATION_ROADMAP.md):

1. **ENG-01 — ilk okuma teslimi tamam:** 0.139.0 ayrı `engine` v1 girişiyle
   arama, ayrıntı, kaynak durumu, referans, hata ve sayfalama sunar. Kapsam
   güvenilen yerel çalışma alanıdır; eski `--json` korunur. .NET tüketicisi,
   kalıcı iş/tekrar güvenliği ve ortak müşteri kapsamı ENG-05'te açıktır.
2. **ENG-02:** [Hazır bileşen tercihlerini](COMPONENT_SELECTION_PLAN.md)
   motorun küçük adaptörlerine bağlama. Yerel açık kaynak araçları öncelik;
   lisans, sürüm, kaynak sözleşmesi ve gerçek fayda deneyi gerekir.
3. **ENG-03:** Onaylı olay ilişki adayları ve kaydedilmiş genel arama
   bildirimleri. Mevcut karşılaştırma/arama desenleri kullanılır; kalıcı
   kimlik, tam sonuç farkı ve kaynak hatası ayrımı korunur.
4. **ENG-04:** Haber/RSS ve kanıtlanmış ek kaynak kapsamı. Kaynak erişimi,
   tazelik, kesinti ve gerçek sonuç yokluğu ayrı görünür.
5. **ENG-05:** Küçük .NET tüketiciyle gerçek motor sonucu okuma; dağıtım
   ihtiyacına uygun taşıma yolunu ve uzun iş/durum/tekrar davranışını
   doğrulama. Mevcut .NET backend'i veya oturum yönetimi yeniden yazılmaz.
6. **ENG-06:** İlk adımdan itibaren Linux kullanım, bağımlılık bakımı,
   kaynak/disk ölçümü, kesintide devam ve yedekten kurtarma. Entegrasyonun
   sürekli kullanımı için kabul koşuludur; sona bırakılmaz.
7. **ENG-07:** İhtiyaç oldukça kaynaklı LLM çıktısı ve STIX/TAXII gibi
   paylaşım genişlemeleri; model ve dış servisler isteğe bağlı kalır.

ENG-03 yerel kanıtlarla ilerleyebilir; bütün .NET bağlantısını veya dış
servisleri beklemek zorunda değildir. ENG-05 için ilk örnek sözleşme erken
doğrulanabilir. OpenCTI/IntelOwl zorunlu kurulum değildir. Common Crawl'ın
son kayıtlı 504 hatası tarihî sonuçtur; canlı kabul ayrıca sınanır.
Eski EIP kimlikleri plan geçmişidir; aktif teslim kimlikleri ENG'dir.

İlgili mevcut iş eşlemeleri:

| Yeni iş | Eski kapsam kimlikleri | Yeni teslim farkı |
|---|---|---|
| ENG-01 | FND-05, INT-02, ENT-03 | Motor/.NET sözleşmesi ve güvenilir kapsam |
| ENG-02 | CTI-06, INT-05, OPS-01 | Yerel bileşen ve kaynak adaptörleri |
| ENG-03 | CTI-02, CTI-03, PHI-06 | Olay adayları ve on türde kaydedilmiş genel arama |
| ENG-04 | OPS-01, DWI-02, COV-01 | Haber/RSS ve kanıtlanmış ek kaynak katkısı |
| ENG-05 | INT-02, ENT-03 | .NET tüketici ve seçilen taşıma/uzun iş kabulü |
| ENG-06 | ENT-01, ENT-05, COV-02, COV-03 | Motor işletimi, kapasite ve kurtarma |
| ENG-07 | AIM-01–05, INT-03, INT-04, INT-05 | İsteğe bağlı LLM ve paylaşım |

Geniş marka ve insan onaylı takedown ayrı teslimlerdir; uygulama
bildirim kanalları, panel ve kullanıcı oturumları .NET platformundadır.
Ürün/sürüm, paket, CVE/KEV/EPSS ve otomatik HTML arşivi yeniden açılmaz.
Yeni platformların kendi bağımlılıkları ayrı tutulur; XTI'ye ek ağır veri
altyapısı ancak hedef iş yükü ölçülerek seçilir.

Dış kaynağa bağlı işin öncesinde küçük bir erişim deneyi yapılır. Kaynak sağlanamıyorsa fixture ile sözleşme geliştirilebilir; işin canlı kapsam kabulü kapatılmaz.

## İş kartı şablonu

```text
Kimlik / faz:
Kullanıcının tamamlayacağı iş:
Kapsam / kapsam dışı:
Önkoşullar ve kaynak erişimi:
Veri modeli / sözleşme değişikliği:
Teslim edilecek davranış:
Pozitif ve negatif kabul senaryoları:
Hata / yeniden başlatma / güvenlik senaryoları:
Kaynak ve maliyet etkisi:
Test ve demo kanıtı:
Veri taşıma / geri alma:
Dokümantasyon:
Sorumlu / durum / son gözden geçirme:
Bilinen sınırlar:
```

Bir paketin tamamlanması bağlı tüm yeteneklerin olgunluk seviyesini otomatik yükseltmez. Örneğin DWI-01 tamamlanması yalnız doğrulanan kaynak adaptörünü kapsar; bütün dark web kaynaklarını kapsamaz.
