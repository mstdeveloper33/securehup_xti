# XTI — Yetenek, Kapsam ve Eksik Alan Matrisi

**Karşılaştırma tarihi:** 13 Kasım 2026 · **Sürüm:** 0.126.

**Aktif kapsam kararı:** CAP-030'un teknoloji çıkarımı ile CAP-034–041 arasındaki zafiyet, ürün/sürüm, paket ve CVE eşleştirme yetenekleri kullanıcı kararıyla aktif teslim planından çıkarıldı. Bu satırlar yalnız tarihsel karşılaştırma kaydı olarak korunur; yeni birleşik analiz bunları çalıştırmaz.

**Mevcut durum:** Bu matris hedef kapsamıdır. Yerel temel, iki kaynaktan arama, kalıcı işler/beklemeler, sınırlı hedef kontrolü, inceleme sırası, JSON rapor, kontrollü bakım ve depolama/kurtarma hazırlığı görünümü, bulgu/pasif aday/dış yüzey değişikliği için birleşik yerel bildirim kutusu ve okundu takibi, kayıtlı takibin durum ve dış yüzey kanıt güncellik özetleri, pasif kaynak/veri durumu ayrımı, pasif yüzey sağlayıcı bazlı kayıt sağlığı ve sürümlü adaptör kabul kapısı, katmanlı aday/kayıt/kapsam envanteri, tur/süre sınırlı marka, pasif yüzey ve seçili aktif yüzey izleme, CAP-015'in sınırlı LTR Unicode/IDN dilimi, CAP-016'nın süreli istisnası, sürümlü kalite ölçümü, CAP-022/023/025/026/027/028'in kaynaklı yüzey kanıtları, CAP-029'un kesin IP'ye sabitlenmiş sabit TCP dilimi, CAP-030'un ürün iddiası taşımayan port ipuçları ve CAP-031'in salt-okunur aday sınıflaması ile CNAME hedef kanıtı uygulanmıştır; doğrulanan davranışlar [STATUS.md](../STATUS.md) içindedir. Satırların bütün kabul koşulları bitmeden olgunluk seviyesi yükseltilmez. Sertifika ve web inceleme arşivleri sınırlı kapsamdadır; sonuçlar doğrulanmış tehdit sayılmaz.

0.88.0, güncel yerel IOC kaynak iddialarını yedi gösterge türünde sınırlı, ağsız ve atomik STIX 2.1 Indicator Bundle dosyasına çıkarır. CTI varlık/ilişki nesneleri, içe aktarma, paylaşım işaretleri ve TAXII açık kalır.

0.89.0, seçilen yerel bildirimi HMAC-SHA256 imzalı, hedef+bildirim bazında tekilleştirilmiş ve deneme geçmişli HTTPS webhook teslimine dönüştürür. Otomatik abonelik/toplu worker, e-posta/SMS ve sağlayıcıya özgü entegrasyonlar açık kalır.

0.90.0–0.92.0, kayıtlı marka/yüzey/IOC kanıtını tek analizde birleştirir; isteğe bağlı Feodo IP veya CERT Polska domain yenilemesini açık ağ seçimi, korunmuş önceki katalog ve ayrı kaynak hata durumuyla aynı terminal akışına ekler. İki kaynağın iddiaları ve çalışma geçmişleri ayrıdır; kalıcı otomatik zamanlama açık kalır.

0.93.0, resmî MITRE ATT&CK Enterprise v20.0 içinden etkin grup, kampanya, malware ve seçili ilişkileri kaynaklı yerel CTI grafiğine alır. Teknik/taktik nesneleri, otomatik atıf ve TAXII açık kalır.

0.94.0, pasif keşif ve dört dış yüzey kanıt ailesinin güncellik/kalite boşluklarını tek salt-okunur görünümde ayırır; tamamlanmış boş kaynağı kesintiden ayırır ve açık sonraki komutları gösterir.

Kamuya açık SOCRadar sayfaları yetenek ailelerini belirlemek için kullanıldı. Satırların “bizim teslim hedefimiz” sütunu kendi ürün tasarımımızdır; rakibin iç mimarisi, birebir uygulaması veya doğrulanmış performansı hakkında iddia değildir. Genel platform gereksinimleri ayrıca bizim tasarım kapsamımız olarak işaretlenmiştir.

**Kaynak profilleri:** B0 yerel/sınırlı; B1 sürekli çalışma ve ayrı yedek; B2 özel/tarihsel kaynak, lisans veya uzman operasyon ihtimali; B3 müşteri hizmeti. B0→B2 kodun sınırlı veride çalışabileceğini, kapsam genişletmenin dış erişime bağlı olduğunu gösterir.

**İlerleme kaydı:** Her yetenek için işlev, veri, doğruluk, güncellik, operasyon ve güvenlik ayrı değerlendirilir. Başlangıçta hepsi 0; rakibin ölçülemeyen boyutları “bilinmiyor” olarak kalır. İleride bu dosyaya kabul kanıtı bağlantısı eklenir. [Olgunluk yöntemi ve fazlar](MASTER_ROADMAP.md), [iş kimlikleri](BACKLOG.md).

## 1. Ortak platform ve kullanıcı akışı — bizim tasarım kapsamımız

| Kimlik | Yetenek | Bizim teslim hedefimiz | İş paketi | Faz / kaynak |
|---|---|---|---|---|
| CAP-001 | İzleme ihtiyaçları | Varlık, tehdit senaryosu ve beklenen karar ilişkisi | FND-01 | R0 / B0 |
| CAP-002 | Varlık kaydı | Domain, marka ve diğer varlık türlerinin sürümlü kaydı | FND-03 | R1 / B0 |
| CAP-003 | Proje/çalışma alanı | Kişisel projelerin mantıksal ayrılması; hizmet izolasyonu ayrı | FND-03 | R1 / B0 |
| CAP-004 | Kaynak yönetimi | Erişim, koşul, kota, kapsam, replay ve sağlık envanteri | OPS-01 | R3 / B0 |
| CAP-005 | Normalleştirme | Kaynaklar arasında ortak ve sürümlü gözlem modeli | FND-05 | R1 / B0 |
| CAP-006 | Kanıt ve köken | Zaman, kaynak, içerik referansı, hash ve dönüştürme izi | FND-05 | R1 / B0 |
| CAP-007 | Kalıcı iş yönetimi | Çökmede devam, retry, lease ve tekrar güvenli kayıt | FND-06 | R1 / B0 |
| CAP-008 | Bulgu yaşam döngüsü | Yeni, görüldü, inceleniyor, ertelendi, kapandı ve tekrar açıldı | PHI-05 | R2 / B0 |
| CAP-009 | Geri bildirim | Doğru/yanlış/bilinmiyor kararı ve gerekçe geçmişi | PHI-05 | R2 / B0 |
| CAP-010 | Bildirim teslimi | Bulgu/adaya/değişime bağlı yerel kutu ve seçilen tek bildirim için manuel imzalı webhook var; otomatik abonelik/toplu worker, e-posta/SMS açık | PHI-06 | R2/R10 / B0 |
| CAP-011 | Terminal deneyimi | Komut yardımı, açıklanabilir tablolar ve kararlı JSON | FND-02 | R1 / B0 |
| CAP-012 | Etkileşimli terminal | Klavye ile filtre, inceleme ve kaynak/iş sağlığı | OPS-06 | R3 / B0 |

## 2. Domain, phishing ve marka adayları

Kamuya açık referans kapsamı: phishing/marka taklidi tespiti ve içerik/görsel analiz yetenekleri. Aşağıdaki normalleştirme, test ve kanıt ayrıntıları bizim uygulama hedeflerimizdir. [SOCRadar Brand Protection](https://socradar.io/products/brand-protection/)

| Kimlik | Yetenek | Bizim teslim hedefimiz | İş paketi | Faz / kaynak |
|---|---|---|---|---|
| CAP-013 | Sertifika kaynaklı domain gözlemi | CT adaptörü; kaynağın gerçekten sunduğu kapsam ve geçmiş | PHI-03 | R2 / B0→B1 |
| CAP-014 | Benzer domain | Yazım farkı, marka sözcüğü, ek sözcük ve gerekçe | PHI-02 | R2 / B0 |
| CAP-015 | IDN/alt domain analizi | Punycode, public suffix ve yanıltıcı alt domain ayrımı | PHI-01 | R2 / B0 |
| CAP-016 | Meşru eşleşme yönetimi | Açıklamalı/süreli allowlist; kullanıcıya göre bastırma | PHI-02 | R2 / B0 |
| CAP-017 | DNS/TLS bağlamı | Adayın kontrollü, zamanlı ve sınırlı zenginleştirilmesi | PHI-04 | R2 / B0 |
| CAP-018 | Sayfa ve görüntü kanıtı | Yalıtılmış içerik/ekran görüntüsü alma; güvenli önizleme | BRD-01 | R8 / B0→B2 |
| CAP-019 | Logo ve metin benzerliği | Logo/OCR sinyali; tek başına ihlal kararı oluşturmama | BRD-01 | R8 / B0→B2 |
| CAP-020 | Aday doğrulaması | Benzerlik adayı ile doğrulanmış phishing kararını ayırma | PHI-05 | R2 / B0 |
| CAP-021 | Kampanya ve tekrar ilişkisi | İlişkili domain/bulguların kanıtlı gruplanması | CTI-02 | R6 / B0→B2 |

## 3. Dış saldırı yüzeyi

Referans kapsamı: dijital varlık keşfi, keşif ilişkileri, DNS/TLS, servis ve teknoloji, yapılandırma ve maruziyet görünümü. [SOCRadar Attack Surface Management](https://socradar.io/products/attack-surface-management/)

| Kimlik | Yetenek | Bizim teslim hedefimiz | İş paketi | Faz / kaynak |
|---|---|---|---|---|
| CAP-022 | Domain/subdomain envanteri | Kaynaklı keşif ve izlenen kapsam ilişkisi | ASM-02 | R4 / B0→B1 |
| CAP-023 | IP ve servis ilişkileri | DNS/IP/servis ilişkilerinin zamanlı saklanması; kesin IP'deki açık TCP kanıtı görünür, tam ilişki kapsamı açık | ASM-01 | R4 / B0 |
| CAP-024 | Sahiplik doğrulaması | Kuruma ait/adayı/bilinmiyor; paylaşımlı altyapı ayrımı | ASM-01 | R4 / B0 |
| CAP-025 | Keşif yolu ve tarihçe | Her varlığın hangi kanıtla bulunduğunu gösterme; son kanıt ilişkileri görünür, tam tarihçe açık | ASM-01 | R4 / B0 |
| CAP-026 | DNS değişiklikleri | Değişim, veri bayatlığı ve kaynak kesintisini ayırma | ASM-02 | R4 / B0→B1 |
| CAP-027 | TLS sertifikaları | Süre, ad eşleşmesi ve doğrulama bulguları | ASM-03 | R4 / B0 |
| CAP-028 | E-posta DNS yapılandırması | MX/SPF/DMARC değişimi; DKIM yalnız bilinen seçiciyle, kaynak ve sınır açıklaması | ASM-03 | R4 / B0 |
| CAP-029 | Port ve servis envanteri | Yalnız yetkili kapsamda sınırlı aktif kontrol; sabit 10 TCP portu var, UDP/serbest port/banner açık | ASM-04 | R4 / B0 |
| CAP-030 | Teknoloji adayları | Aktif kapsam dışında; açık porttan ürün veya sürüm çıkarılmıyor | — | Kapsam dışı |
| CAP-031 | Yapılandırma ve takeover adayları | Salt-okunur TLS/e-posta/seçili port adayları ve CNAME hedef NXDOMAIN adayı var; açık panel, delegasyon ve gerçek takeover doğrulaması açık | ASM-05 | R4 / B0 |
| CAP-032 | Bulut/API/mobil varlıklar | Kaynak erişimine göre envanter ve sahiplik adayı | ASM-06 | R4 / B0→B2 |
| CAP-033 | Dijital ayak izi ve dönemsel değerlendirme | Varlık ilişkisi, değişim ve incelenebilir risk görünümü | ASM-06 | R4 / B0→B2 |

## 4. Zafiyet istihbaratı ve öncelik — aktif kapsam dışında

Bu bölüm rakip kapsamını ve önceki yerel çalışmayı tarihsel olarak kaydeder. Sunucu envanteri, ürün/sürüm, paket, CVE, KEV ve EPSS ilişkileri aktif ürün planında değildir; aşağıdaki satırlar yeni teslim taahhüdü değildir.

| Kimlik | Yetenek | Bizim teslim hedefimiz | İş paketi | Faz / kaynak |
|---|---|---|---|---|
| CAP-034 | CVE ve üretici duyuruları | CISA KEV, tek-CVE NVD/CPE, eksik-NVD ve maruziyet kapsamlı eski-NVD planı/yürütmesi, devam edilebilir küçük tarih-pencereli NVD, OSV, Canonical Ubuntu OSV ve doğrudan Red Hat+SUSE VEX önizlemesi var; OSV duyurusu elle bağlanabiliyor, pencere kapsama takvimi ve diğer üretici kaynakları açık | VUL-01, VUL-02 | R5 / B0 |
| CAP-035 | Ürün/sürüm eşleştirmesi | NVD CPE koşulları, doğrulanmış ürün, kesin Red Hat RPM+dağıtım kanıtı, kesin Red Hat VEX/RPM ilişkisi, kalıcı Ubuntu binary→source envanteri ile tek paket ve tek çağrılı bütün-envanter Canonical fixed sınırı karşılaştırması, seçilmiş Red Hat ve Ubuntu sonuçlarının kaynak özetli kanıtı, ayrı tekil güncellik kontrolleri ve Ubuntu için ağsız plan/sınırlı toplu tarama, envanter geneli aday, insan onaylı geçmiş ve kontrollü toplu yeniden değerlendirme var; genel aralık/backport ve zamanlanmış otomasyon açık | VUL-02 | R5 / B0 |
| CAP-036 | CVSS bağlamı | İstenen CVE için bütün desteklenen skor vektörü, sürümü, türü ve sağlayıcısı ayrı korunuyor; toplu kapsam açık | VUL-01 | R5 / B0 |
| CAP-037 | EPSS ve KEV bağlamı | KEV bilinen istismar, EPSS olasılık ve NVD/CVSS teknik önem bağlamı ayrı anlamlarla tek salt-okunur CVE görünümünde uygulandı | VUL-01 | R5 / B0 |
| CAP-038 | Varlığa özgü öncelik | İnsan durumu, yeniden inceleme, KEV/EPSS/CVSS, insan beyanlı iş önemi ve güncel kayıtlı internet erişimi nedenli çalışma bantları; değişiklik planı, açık yürütme ve denetim geçmişi var; varlık grubu kalıtımı ve zamanlanmış abonelik açık | VUL-03 | R5 / B0 |
| CAP-039 | Yeni zafiyet izleme | İlgili ürün/varlık için değişim aboneliği | CTI-03 | R6 / B0 |
| CAP-040 | Düzeltme ve bastırma | Kaynaklı öneri, uygulama/yeniden kontrol kanıtı, kuyruk vadesi ve gerekçeli süreli bastırma var; kurumsal görev/SLA açık | VUL-04 | R5 / B0 |
| CAP-041 | Kapanma doğrulaması | Yapılandırılmış kontrol sonucu/kanıt, otomatik kapanmama ve insan onaylı kapanma/yeni kanıtla yeniden açılma kabulü var | VUL-04 | R5 / B0 |

## 5. CTI bilgi tabanı ve tehdit avcılığı

Referans kapsamı: IOC yönetimi, avcılık, aktör/kampanya bağlamı, rapor ve analiz içerikleri. [SOCRadar CTI](https://socradar.io/products/cyber-threat-intelligence/), [modüller](https://socradar.io/modules/)

| Kimlik | Yetenek | Bizim teslim hedefimiz | İş paketi | Faz / kaynak |
|---|---|---|---|---|
| CAP-042 | IOC içeri alma ve arama | Domain/IP/URL/hash için kanonik yerel kayıt ve arama; Feodo IP tam-snapshot alma, kesinti ve çalışma geçmişi var; diğer kaynak türleri açık | CTI-01 | R6 / B0→B2 |
| CAP-043 | IOC yaşam döngüsü | Kaynak başına güven, geçerlilik, ilk/son gözlem, güncelleme, geri çekme ve yeniden etkinleştirme var; yanlış pozitif kararı açık | CTI-01 | R6 / B0 |
| CAP-044 | Aktör profilleri | Kaynak başına alternatif ad/güven/geçmiş, çelişen atıf ilişkileri ve ATT&CK v20 grup aktarımı var; açık merge/split işlemi ve başka dış kaynaklar açık | CTI-02 | R6 / B0→B2 |
| CAP-045 | Kampanya ve malware profilleri | Kaynaklı kampanya/malware/rapor kayıtları, varlık/IOC ilişkileri ve ATT&CK v20 kampanya/malware aktarımı var; zamanlı kampanya alanları ve otomatik rapor aktarımı açık | CTI-02 | R6 / B0→B2 |
| CAP-046 | ATT&CK ilişkileri | Enterprise v20 grup/kampanya/malware ile `uses`/`attributed-to` kaynak iddiaları var; teknik/taktik eşlemeleri açık | CTI-04 | R6 / B0 |
| CAP-047 | Kaydedilmiş avcılık sorguları | Tekrar üretilebilir birleşik yerel arama, kalıcı sorgu tanımı, tam çalışma/fark geçmişi, yaşam döngülü etiket ve çalışma bağlı eklemeli analist notu var; takım işbirliği açık | CTI-03 | R6 / B0 |
| CAP-048 | Abonelik ve izleme listeleri | Yeni/değişen/kaybolan sonuç ayrımı, kanıt bağlı yerel bildirim, tek arama ön plan tekrarı ve bütün etkin aramayı sınırlı tek-sefer yenileme var; kalıcı zamanlama ve dış kanal açık | CTI-03 | R6 / B0 |
| CAP-049 | YARA/Sigma içerik kataloğu | Yetkili içeriklerin kaynak/lisans/sürüm/doğrulaması | CTI-05 | R6 / B0→B2 |
| CAP-050 | Hash ve malware analiz bağlamı | Yetkili servis raporları; kontrollü numune paylaşımı | CTI-06 | R6 / B0→B2 |
| CAP-051 | Taktik/stratejik raporlar | Kaynaklı özet, sektör/bölge ve dönem karşılaştırması | CTI-04 | R6 / B0→B2 |
| CAP-052 | İlişki araştırması | Kaynakları ezmeyen varlık–varlık ve varlık–IOC grafiği var; açık merge/split kararı ve gelişmiş grafik sorgusu açık | CTI-02 | R6 / B0 |

## 6. Dark web ve tehdit iddiaları

Referans kapsamı: deep/dark web kaynakları, mesajlaşma kanalları, geçmiş arama, sızıntı ve ransomware gözlemleri. Kaynaklara erişim ve gerçek kapsam satır bazında ayrıca doğrulanacak. [SOCRadar Dark Web Monitoring](https://socradar.io/products/dark-web-monitoring/)

| Kimlik | Yetenek | Bizim teslim hedefimiz | İş paketi | Faz / kaynak |
|---|---|---|---|---|
| CAP-053 | Forum/pazar metin gözlemi | Erişim hakkı doğrulanmış kaynak adaptörleri | DWI-01 | R7 / B0→B2 |
| CAP-054 | Mesajlaşma kaynakları | İzinli Telegram/Discord/diğer kanal adaptörleri | DWI-01 | R7 / B0→B2 |
| CAP-055 | Kuruluş ve anahtar sözcük | Çok anlamlı adlar, bağlam ve alıntı ayrımı | DWI-02 | R7 / B0 |
| CAP-056 | Sızıntı/satış/tehdit iddiası | İlan, haber ve teyit edilmiş olayın ayrı durumları | DWI-02 | R7 / B0→B2 |
| CAP-057 | Ransomware duyuruları | Kurban iddiası, zaman çizelgesi ve tekrar yayın | DWI-03 | R7 / B0→B2 |
| CAP-058 | Geçmiş arama | Elde bulunan tarihsel arşiv ve açık dönem boşlukları | DWI-04 | R7 / B0→B2 |
| CAP-059 | Kaynak/konu aboneliği | İlgili içerik değişimlerini bildirme | DWI-04 | R7 / B0→B2 |
| CAP-060 | Çok dilli inceleme | Önce Türkçe/İngilizce; dil başına değerlendirme | DWI-02 | R7 / B0→B2 |
| CAP-061 | Özel kaynak ve tarihsel derinlik | Erişim, bakım, veri hakları ve kapsam yatırım programı | COV-01 | R13 / B2 |

0.108.0 durumunda CAP-057/CAP-059'un ilk dar parçası çalışır: ThreatCluster için tam snapshot geçmişi, kuruluş/domain izleme tanımı, sessiz başlangıç, değişiklik bildirimi, toplu yenileme, sınırlı ön plan tekrar, kalıcı monitor oturum geçmişi, ağsız zaman çizelgesi, kimlik değişimi adayları ve kimlikleri birleştirmeyen insan karar geçmişi vardır. İkinci bağımsız RansomLook kaynağı ayrı modelde yazmasız önizleme, kaynak-yalıtımlı kalıcı snapshot fark geçmişi ve kuruluş-adı izlemesi olarak çalışır. İki son yerel snapshot tam kuruluş+grup/zaman kanıtıyla açıklanabilir biçimde karşılaştırılabilir; gerekçeli insan kararı dondurulmuş iki özgün claim'e bağlanır ve silinmeyen olay zincirinde tutulur. Bu karar kayıtları birleştirmez, alarm veya ihlal hükmü üretmez. RansomLook toplu yenileme/monitor/inbox, kalıcı zamanlama/7×24 hizmet, tarihsel derinlik, forum/pazar ve mesajlaşma kapsamı henüz tamamlanmış sayılmaz.

## 7. Kimlik ve erişim istihbaratı

Referans kapsamı: kimlik maruziyetinin enfeksiyon, cihaz, oturum ve kullanılan servislerle bağlamlandırılması. Bunun için gereken veri yoksa ilişkiler tahmin edilip kesin bilgi gibi sunulmaz. [SOCRadar Identity & Access Intelligence](https://socradar.io/products/cyber-threat-intelligence/identity-and-access-intelligence/)

| Kimlik | Yetenek | Bizim teslim hedefimiz | İş paketi | Faz / kaynak |
|---|---|---|---|---|
| CAP-062 | Çalışan hesabı maruziyeti | Yetkili veriyle maskeli kurumsal kimlik eşleştirme | IDN-01 | R7 / B0→B2 |
| CAP-063 | Müşteri hesabı maruziyeti | Veri minimizasyonu ve yetki kapsamıyla eşleştirme | IDN-01 | R7 / B2 |
| CAP-064 | Stealer/enfeksiyon bağlamı | Kaynağın sunduğu bulaşma zamanı ve ilişki dayanağı | IDN-02 | R7 / B2 |
| CAP-065 | Cihaz/endpoint görünümü | Yalnız yetkili kanıttaki metaveri ve belirsizlik | IDN-02 | R7 / B2 |
| CAP-066 | Oturum ve servis ilişkisi | Ham sır kullanmadan cookie/session/uygulama bağlamı | IDN-02 | R7 / B2 |
| CAP-067 | Kimlik etkisi ve müdahale | İlgili kurum/servis etkisi; onaylı düzeltme entegrasyonu | IDN-03, RSP-03 | R7/R10 / B2→B3 |

## 8. Geniş marka, VIP ve dolandırıcılık

Referans kapsamı: sosyal hesap/uygulama taklidi, yüzey web, VIP ve finansal dolandırıcılık sinyalleri. [SOCRadar Brand Protection](https://socradar.io/products/brand-protection/), [VIP Protection](https://socradar.io/solutions/vip-protection/)

| Kimlik | Yetenek | Bizim teslim hedefimiz | İş paketi | Faz / kaynak |
|---|---|---|---|---|
| CAP-068 | Sosyal hesap taklidi | Doğrulanmış sabit Maigret/Sherlock kurulumu; 6/5 güvenli, 30/26 incelenmiş geniş veya özel kapsamlı önizleme; kaynak-yalıtımlı kalıcı fark, tam profil insan kararı, tekil kutu, karma toplu ve ön plan yürütme var. Ek kaynak ve parodi doğruluğu açık | BRD-02 | R8 / B0→B2 |
| CAP-069 | Sahte mobil uygulama | Mağaza, yayıncı, paket ve marka ilişkisi | BRD-03 | R8 / B0→B2 |
| CAP-070 | Yüzey web marka gözlemi | İlgili sayfa/ilan ve zamanlı içerik kanıtı | BRD-04 | R8 / B0→B2 |
| CAP-071 | Kod/API deposu maruziyeti | Yetkili içerikte maskeli sır/kurum bağlantısı | BRD-04 | R8 / B0→B2 |
| CAP-072 | Bulut verisi maruziyeti | Yetki kapsamındaki bulut varlığında gerekli en az kanıt | BRD-04 | R8 / B0→B2 |
| CAP-073 | Yönetici/VIP taklidi | Kimlik doğruluğu, aynı isim ve kamuya açık rol bağlamı | BRD-05 | R8 / B2 |
| CAP-074 | Yönetici kimlik maruziyeti | Yetkili eşleştirme, dar erişim, silme ve maskeleme | BRD-05, IDN-01 | R8 / B2 |
| CAP-075 | Dolandırıcılık kampanyası | Marka/hesap/site ilişkilerinin incelenebilir gruplanması | BRD-05 | R8 / B2 |
| CAP-076 | Finansal veri göstergeleri | Uygun erişim ve ihtiyaç varsa maskeli eşleşme; tam veri varsayılan dışı | BRD-05 | R8 / B2 |

## 9. Tedarik zinciri ve üçüncü taraf

Referans kapsamı: tedarikçi izleme, risk analizi, raporlar ve farklı tehdit verilerinin ilişkilendirilmesi. [SOCRadar Supply Chain Intelligence](https://socradar.io/products/supply-chain-intelligence/)

| Kimlik | Yetenek | Bizim teslim hedefimiz | İş paketi | Faz / kaynak |
|---|---|---|---|---|
| CAP-077 | Tedarikçi envanteri | İnsan onaylı kuruluş adı, değiştirilemez ana domain, ilişki, iş kritiklik düzeyi ve eklemeli yaşam döngüsü; kayıtlı son CNAME'den ağsız teknik aday var | SUP-01 | R9 / B0 |
| CAP-078 | Kuruluş çözümleme | Aynı isim/ortak altyapıyı otomatik birleştirmeyen; yalnız etkin kayıtlı tedarikçiye gerekçeli kabul, belirsiz, ret ve yeniden inceleme kararı var | SUP-01 | R9 / B0 |
| CAP-079 | Tedarikçi tehdit olayları | ThreatCluster/RansomLook son yerel snapshot'larında tam ad/domain dayanaklı iddia görünümü, kaynak kimliği ve kesinti/eski veri ayrımı var; haber/teyit sınıfları ve daha geniş kaynak kapsamı açık | SUP-02 | R9 / B0→B2 |
| CAP-080 | Tedarikçi maruziyet görünümü | İnsan onaylı envanter, güncel kabul edilmiş CNAME bağı ve iki kaynaklı iddia adayı tek salt-okunur görünümde; daha geniş EASM/CTI kaynakları açık | SUP-02 | R9 / B0→B2 |
| CAP-081 | Açıklanabilir risk kartı | İş önemi, domain/ad dayanağı, kaynak kapsamı, güncellik, eksik veri, neden ve insan sonraki adımları görünür; sayısal risk/ihlal hükmü yok | SUP-02 | R9 / B0→B2 |
| CAP-082 | İlişki zinciri ve etki | Tedarikçi olayından kullanıcı etkisine açık varsayımlar | SUP-03 | R9 / B0→B2 |
| CAP-083 | Dönemsel ve markalanmış rapor | Değişim, öneri ve kaynaklar; kurumsal markalama daha sonra | SUP-03, ENT-06 | R9/R11 / B0→B3 |

## 10. Vaka, paylaşım, entegrasyon ve aksiyon

Referans kapsamı: olay/vaka işlemleri, IOC ve takedown API'leri; güvenlik ve iş akışı sistemleriyle bağlantılar. [SOCRadar API](https://socradar.io/socradar-apis/), [entegrasyonlar](https://socradar.io/integrations/), [takedown kapsamı](https://socradar.io/pricing/)

| Kimlik | Yetenek | Bizim teslim hedefimiz | İş paketi | Faz / kaynak |
|---|---|---|---|---|
| CAP-084 | Vaka yönetimi | Kişisel yerel gruplama, beş kaynak türünden dondurulmuş kanıt, görev, not, zaman çizelgesi, sonuçlu kapanış ve yeniden açma var; atama/rol/SLA takım ürünüyle gelecek | INT-01 | R10 / B0 |
| CAP-085 | Teknik/yönetici raporu | Ağsız terminal/JSON vaka çalışma özeti var; dönemsel, markalı ve yönetici şablonları açık | INT-01, SUP-03 | R10 / B0→B3 |
| CAP-086 | Sürümlü API | Yerel varsayılan; ağ için kimlik, yetki, TLS ve limit | INT-02 | R10 / B0→B1 |
| CAP-087 | STIX 2.1 | Yedi IOC türü için güncel kaynaklı Indicator Bundle dışa aktarma var; CTI nesne/ilişki kapsamı, işaretler, geri çekme sürümü ve içe aktarma açık | INT-03 | R10 / B0 |
| CAP-088 | TAXII 2.1 | Collections alışverişi ve ikinci istemci doğrulaması | INT-04 | R10 / B0→B1 |
| CAP-089 | Paylaşım ve TLP | Kaynak lisansı, işaretler ve kullanıcı kapsamını koruma | INT-03 | R10 / B0 |
| CAP-090 | Webhook ve talep sistemleri | Seçilen bildirimin imzalı/idempotent teslimi, sır döndürme ve deneme geçmişi var; otomatik abonelik/toplu worker ve talep sistemi adaptörü açık | INT-05 | R10 / B0→B2 |
| CAP-091 | SIEM/SOAR/EDR/firewall | Seçilen sistem başına test edilmiş adaptör; kontrollü aksiyon | INT-05, RSP-03 | R10 / B0→B3 |
| CAP-092 | İstihbarat platformları | MISP/OpenCTI benzeri hedeflere kapsamlı, sürümlü bağlantı | INT-05 | R10 / B0→B2 |
| CAP-093 | Kanıtlı takedown taslağı | Hak sahipliği, muhatap, hedef ve içerik sürümüne bağlı onay | RSP-01 | R10 / B0 |
| CAP-094 | Çok türde takedown takibi | Domain/sosyal hesap/app/depo; yanıt, ret, itiraz ve sonuç | RSP-02 | R10 / B0→B2 |
| CAP-095 | Düzeltme ve kimlik aksiyonu | Onaylı IdP/SOAR işlemi; sonucun ayrı doğrulanması | RSP-03 | R10 / B2→B3 |

STIX/TAXII/TLP desteği bizim açık standart hedefimizdir; bu satırlar rakibin desteklediği bütün nesne/işlem sürümleri için doğrulama iddiası içermez.

## 11. AI ve araç tabanlı iş akışları

Bu bölüm rakip/kapsam karşılaştırması olarak korunur; kullanıcı kararıyla etkin teslim hedefi değildir. Platformun çekirdek işlevleri AI olmadan geliştirilecektir.

Referans kapsamı: analiz ajanları, özelleştirilebilir iş akışları ve API/MCP araç erişimi. Araç sayıları yerine tamamlanabilen kullanıcı işleri karşılaştırılır. Belirli MCP özellikleri “yakında” olarak etiketlenebildiğinden mevcut/önizleme ayrımı korunur. [SOCRadar ATI](https://socradar.io/products/agentic-threat-intelligence/), [MCP](https://socradar.io/socradar-mcp-server/)

| Kimlik | Yetenek | Bizim teslim hedefimiz | İş paketi | Faz / kaynak |
|---|---|---|---|---|
| CAP-096 | Analiz temel yöntemi ve ölçüm | Etiketli veri, kurallı temel yöntem, maliyet/kalite karşılaştırması | AIM-01 | R12 / B0→B2 |
| CAP-097 | Kaynaklı özet | İddia başına kanıt; yeterli kanıt yoksa karar vermeme | AIM-02 | R12 / B0→B2 |
| CAP-098 | Metin ve varlık çıkarımı | Çok dil, alıntı, eski haber ve belirsizlik değerlendirmesi | AIM-02 | R12 / B0→B2 |
| CAP-099 | Sorgu asistanı | Salt okuma, sınırlandırılmış arama ve sonuç dayanakları | AIM-03 | R12 / B0→B3 |
| CAP-100 | MCP/araç bağlantısı | Dar araç listesi, yetki, şema, süre ve maliyet limiti | AIM-03 | R12 / B0→B3 |
| CAP-101 | Denetimli çok adımlı akış | Kayıtlı karar, durdurma ve dış eylemde sürüme bağlı onay | AIM-04 | R12 / B2→B3 |
| CAP-102 | Model yaşam döngüsü | Prompt/model sürümü, regresyon, veri aktarımı ve geri dönüş | AIM-04 | R12 / B0→B3 |

## 12. Takım, MSSP ve kurumsal güven

Kamuya açık referanslar: kullanıcı/kurum yönetimi ve güven programı. Aşağıdaki güvenlik/işletim mekanizmaları bizim uygulanacak tasarımımızdır; bir veritabanı değişikliğiyle tamamlanmış sayılmaz. [SOCRadar API](https://socradar.io/socradar-apis/), [Trust Center](https://trust.socradar.io/)

| Kimlik | Yetenek | Bizim teslim hedefimiz | İş paketi | Faz / kaynak |
|---|---|---|---|---|
| CAP-103 | Ekip web deneyimi | API üstünde erişilebilir arayüz ve ortak inceleme | ENT-04 | R11 / B3 |
| CAP-104 | Kimlik ve rol yönetimi | Oturum, API anahtarı, MFA/SSO ve erişim iptali | ENT-02 | R11 / B3 |
| CAP-105 | Tenant izolasyonu | Depo/arama/cache/dosya/job/export/bildirim boyunca sınır | ENT-03 | R11 / B3 |
| CAP-106 | Denetim geçmişi | Kritik işlemlerin hassas verisiz, incelenebilir izi | ENT-05 | R11 / B3 |
| CAP-107 | Müşteri veri yaşam döngüsü | Silme, taşıma, saklama ve yedek politikasının kapsamı | ENT-05 | R11 / B3 |
| CAP-108 | MSSP çalışma alanları | Yetkili müşteri geçişi, görünür kapsam, ayrılmış rapor | ENT-06 | R11 / B3 |
| CAP-109 | Kota ve ticari ölçüm | Yalnız ürünleşme kararı sonrası kullanım/abonelik ölçümü | ENT-06 | R11 / B3 |
| CAP-110 | Hizmet hedefleri ve kurtarma | Ölçülen SLO, geri yükleme, yükseltme ve olay tatbikatı | ENT-05 | R11 / B3 |
| CAP-111 | Güvenlik ve dağıtım güvencesi | SBOM, bağımlılık bakımı, sürüm doğrulama ve bağımsız inceleme | COV-03 | R1→R13 / B0→B3 |
| CAP-112 | Destek ve uzman hizmetler | Analist süreci, sorumluluk, çalışma saatleri ve finansman | COV-04 | R13 / B2→B3 |

ISO/SOC gibi bağımsız güven programları müşteriye göre ayrı proje olur. Ürün içinde bir kontrol listesi bulunması sertifikasyon veya denetim raporuna eşit değildir.

## 13. Veri kapsamı ve sürdürülebilirlik — bizim tasarım kapsamımız

Bu satırlar bütün modülleri etkiler. SOCRadar'ın kamuya kapalı verisini veya hizmet kapasitesini yazılım özelliği sayıp “tamamlandı” işaretlemeyi önler.

| Kimlik | Yetenek | Bizim teslim hedefimiz | İş paketi | Faz / kaynak |
|---|---|---|---|---|
| CAP-113 | Dil/bölge/kaynak genişletme | Kaynak başına özgün katkı, erişim hakkı ve değerlendirme | COV-01 | R13 / B1→B2 |
| CAP-114 | Tarihsel veri ve yedeklilik | Geriye dönük derinlik, kesinti boşluğu ve alternatif kaynak | COV-01 | R13 / B1→B2 |
| CAP-115 | Botnet/DDoS kampanya bağlamı | Yetkili haricî telemetriden ilişki; görünmeyen trafik için iddia yok | CTI-02, COV-01 | R6/R13 / B2 |
| CAP-116 | Kapasiteye göre veri platformu | Ölçülmüş PostgreSQL/broker/search/object/graph geçişleri | ENT-01, COV-02 | İhtiyaç halinde / B1→B3 |
| CAP-117 | Ölçüm ve bakım programı | Kaynak sağlığı, kalite, yedek ve bakım yükü raporu | OPS-04, OPS-05 | R3→R13 / B0→B3 |
| CAP-118 | Tarihli eşdeğerlik incelemesi | Altı boyutta kanıt ve açık kalan maddeler; üç aylık yenileme | COV-04 | R13 ve dönemsel / B0→B3 |

## 14. Son kapsam incelemesinde eklenen ayrıntılar

Kamuya açık özellik tablolarında itibar/blacklist takibi; tedarikçi önerisi ve çerçeve eşlemeleri; web işaretçisi/referer telemetrisi de tanıtılıyor. Bunlar mevcut iş paketlerine açık kabul davranışı olarak eklendi. [Özellik ve plan tablosu](https://socradar.io/pricing/), [tedarikçi kapsamı](https://socradar.io/products/supply-chain-intelligence/), [API kapsamı](https://socradar.io/socradar-apis/)

| Kimlik | Yetenek | Bizim teslim hedefimiz | İş paketi | Faz / kaynak |
|---|---|---|---|---|
| CAP-119 | Domain/IP itibar ve blacklist takibi | Feodo IP ve CERT Polska son-ay domain listelerinde giriş/çıkış, kaynak hatası, sağlayıcı ve çalışma tarihi var; daha geniş/coğrafi dengeli çoklu kaynak kapsamı açık | CTI-01 | R6 / B0→B2 |
| CAP-120 | Tedarikçi adayı önerisi | Dış bağımlılıktan kanıtlı öneri; ilişki için kullanıcı onayı | SUP-01 | R9 / B0→B2 |
| CAP-121 | Kontrol çerçevesi eşlemesi | NIST/ISO/CIS gibi çerçeve/sürüm/dayanak; sertifikasyon iddiası yok | SUP-03 | R9 / B0→B2 |
| CAP-122 | Yetkili web işaretçisi/referrer telemetrisi | Sahibi olunan sitede sınırlı ölçüm; veri minimizasyonu ve sahte sinyal testi | BRD-01 | R8 / B0→B2 |

## Kapsamın kapanma koşulu

Bir satır için aşağıdakiler doldurulur:

```text
Yetenek kimliği:
Tamamlanan kullanıcı senaryosu:
Desteklenen veri türü/kaynak/dil/coğrafya/tarih aralığı:
Ölçüm donanımı, veri kümesi ve sürüm:
Doğruluk ve hata örnekleri:
Kaynak/işlem gecikmesi:
Kesinti, yeniden işleme ve geri yükleme kanıtı:
Erişim, veri saklama ve paylaşım kontrolleri:
Kaynak/operasyon maliyeti ve sorumlu:
Kamuya açık karşılaştırma kaynağı ve tarihi:
Karşılaştırılamayan/bilinmeyen alanlar:
İşlev / veri / doğruluk / güncellik / operasyon / güvenlik seviyesi:
Bir sonraki eksik:
```

Yalnız bir ekranın veya endpoint'in yazılması yeterli değildir. Özel kaynak erişimi, analist doğrulaması, dış sağlayıcının takedown kararı ve hizmet kapasitesi ilgili satırın ayrı bağımlılığı olarak açık tutulur. Kodun hazır olmasıyla veri/hizmet kapsamının tamamlanması farklı durumlar olarak raporlanır.
