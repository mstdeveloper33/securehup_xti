# XTI özellik kataloğu

**Güncel sürüm:** 0.193.0 · **Çekirdek şema:** 100 · **Son güncelleme:**
24 Kasım 2026.

Bu dosya platformda bugün gerçekten kullanılabilen bütün kullanıcı
yeteneklerinin sade envanteridir; planlanan bir özellik kodu, testi ve gerekli
canlı kabulü tamamlanmadan “aktif” bölümüne yazılmaz.

Bu sürüm için katalog, terminaldeki **71 ana komut ailesi** ve **651 uç komut**
ile karşılaştırılmıştır; bir satır aynı amaca hizmet eden listeleme, ayrıntı,
geçmiş ve güncelleme komutlarını tek anlaşılır özellik altında birleştirebilir.

| Güncel bölüm | Özellik sayısı |
|---|---:|
| Aktif ve kullanılabilir | 401 |
| Kodu hazır, gereksinim bekliyor | 78 |
| Beklemede, ertelenmiş veya kapsam dışı | 63 |
| Toplam izlenen özellik/durum | 542 |

## Katalog nasıl güncellenecek?

- Kullanıcıya yeni bir yetenek kazandıran her geliştirmede bu dosya aynı
  değişiklik içinde güncellenecektir.
- Özellik normal kurulumla çalışıyorsa **Aktif**, hesap, anahtar, izinli hedef,
  haricî hizmet veya belirli işletim sistemi bekliyorsa **Gereksinim bekleyen**
  bölümünde tutulacaktır.
- Henüz yazılmamış veya kullanıcı kararıyla ertelenmiş işler **Beklemede**
  bölümünde kalacak ve aktifmiş gibi anlatılmayacaktır.
- Kaynaktan gelen kayıt adaydır; sosyal profil, açık port, ihlal kaydı veya
  benzer görsel tek başına doğrulanmış tehdit anlamına gelmez.

---

# 1. Aktif ve şu anda kullanılabilen özellikler

## A. Kurulum, kayıt alanı ve güvenli çalışma

| Özellik adı | Tek cümlelik açıklama |
|---|---|
| Yönetilen proje kurulumu | `./setup` gerekli Python ortamını ve sabitlenmiş normal bağımlılıkları kontrollü biçimde kurar. |
| Yerel kayıt alanı oluşturma | `init` seçilen klasörde motorun kullanacağı özel izinli SQLite kayıt alanını oluşturur. |
| Sistem sağlık kontrolü | `doctor` sürüm, şema, dosya izinleri ve temel kayıt alanı sorunlarını değişiklik yapmadan gösterir. |
| Birleşik çalışma durumu | `status` kaynak güncelliğini, bekleyen işleri, bildirimleri ve dikkat isteyen durumları tek görünümde toplar. |
| İnsan tarafından okunabilir terminal çıktısı | Bütün ana işlevler sade terminal görünümüyle kullanılabilir ve dış metinler terminal komutu çalıştıramaz. |
| Otomasyon için JSON çıktısı | Desteklenen terminal işlemleri `--json` ile aynı sonucu makine tarafından okunabilir biçimde verir. |
| Seçilebilir veri klasörü | `--data-dir` ile kişisel, test veya firma kayıt alanları birbirinden ayrı tutulabilir. |
| Yerel ve çevrimdışı kayıt okuma | Saklanmış kanıtların büyük bölümü yeni internet isteği yapılmadan araştırılabilir. |
| Açık şema yükseltme | `migrate` eski kayıt alanını kendiliğinden değiştirmek yerine açık komutla ve önce yedek alarak yükseltir. |
| Tutarlı yedek alma | `backup` canlı veritabanının doğrulanabilir bir kopyasını yeni bir hedefe oluşturur. |
| Güvenli geri yükleme | `restore` doğrulanmış yedeği yalnız boş bir kayıt alanına açar ve mevcut verinin üzerine yazmaz. |
| Depolama boyutu görünümü | `storage status` veritabanı boyutunu ve yeniden kullanılabilir alanı gösterir. |
| Kurtarma hazırlığı kontrolü | `storage readiness` disk, izin, yedek, saklama ve geri dönüş hazırlığını birlikte denetler. |
| Eski bağlantısız kayıt temizleme önizlemesi | `storage cleanup` silme uygulamadan önce hangi bağlantısız gözlemlerin temizlenebileceğini gösterir. |
| Temizlik geçmişi | `storage history` tamamlanmış bakım çalışmalarını ve bunların yedeklerini gösterir. |
| Tek yazıcı koruması | Yerel çalışma kilidi aynı kayıt alanına çakışan iki yazma işleminin zarar vermesini engeller. |
| Tekrar güvenli işlemler | Aynı işlem anahtarıyla yinelenen desteklenen istekler ikinci ağ çağrısı veya çift kayıt üretmez. |
| Kesinti sonrası açık kurtarma | Yarım kalan işler otomatik olarak yeniden ağ isteği göndermek yerine açık `recover` işlemiyle güvenli duruma alınır. |
| Sayfalı büyük geçmiş | Büyük kayıt listeleri toplam sayıyı kaybetmeden devam anahtarıyla küçük sayfalarda okunabilir. |
| Kanıt bütünlüğü kontrolü | Kritik kayıtlar kimlik ve SHA-256 bağlarıyla doğrulanır, içerik değiştirilmişse sistem işlem yapmadan durur. |
| Kaynağın nereden geldiğini koruma | Bulgular kaynak adı, kaynak kaydı, zaman ve çalışma kimliğiyle geriye doğru izlenebilir. |
| Kaynak durumlarını ayırma | Hiç çalıştırılmamış, başarılı boş, kısmi, başarısız ve eski başarılı sonuçlar birbirinden farklı gösterilir. |
| Kaynak bekleme ve kota koruması | Sağlayıcı bekleme süreleri ve oran sınırı kayıtlı tutulur, erken veya gizli tekrar istekleri engellenir. |
| Pasif kaynak çalışma geçmişi | Son crt.sh/urlscan sorguları ve kayıtlı sağlayıcı beklemeleri `sources history` ile ağsız okunabilir. |
| Tek sürümlü kaynak manifesti kataloğu | Mevcut 55 connector amaç, erişim, maliyet, kapsam ve sürüm bilgisiyle tek çevrimdışı katalogda listelenir; `sources` aynı sözleşmenin `sources catalog` kısayoludur. |
| Kaynak hazırlık durumu | Teknik olarak aktif, açık gereksinim bekleyen ve kullanıcı kararıyla kapalı kaynaklar birbirine karıştırılmadan filtrelenebilir. |
| Kaynak veri hakkı görünümü | Ticari kullanım, saklama, müşteriye gösterme ve yeniden dağıtım kararı her kaynakta ayrı görülebilir. |
| Dil ve bölge kaynak filtresi | Manifestler BCP47 dil ve ISO/global bölge alanlarıyla filtrelenebilir; alanın varlığı canlı kapsam iddiası değildir. |
| Ortak kayıt ve provenance sözleşmesi | Her connector ürettiği anlam ailesini ve kaynak kimliği, başvuru, zaman, sürüm ile kanıt özetini açıkça ilan eder. |
| Kaynak kataloğu bütünlük doğrulaması | Manifest şeması, benzersiz kimlik, sıralama ve kanonik katalog SHA-256 özeti ağsız doğrulanabilir. |
| Manifestten ayrı kayıtlı sağlık | İsteğe bağlı görünüm yalnız son yerel çalışma kanıtını manifeste bağlar ve canlı kaynak isteği başlatmaz. |
| Gizli anahtar dosyası koruması | Desteklenen API anahtarları terminalde görünmeden özel izinli dosyada saklanır ve çıktılara yazılmaz. |
| Bağlı bileşen kataloğu | `components` Maigret, Sherlock ve theHarvester gibi bağlı araçların beklenen sürümünü ve kurulum durumunu gösterir. |
| Eşleştirme kuralı değerlendirmesi | `evaluate` eşleştirme kurallarını sürümlü kontrollü örneklerle ağsız olarak ölçer. |
| Kullanıcı geri bildirimi özeti | `feedback` faydalı, faydasız ve belirsiz insan kararlarını kural sürümüne göre özetler. |

## B. Varlık, kuruluş ve firma ayrımı

| Özellik adı | Tek cümlelik açıklama |
|---|---|
| Domain varlığı kaydetme | `assets add` izlenecek domaini kanıt alanına ekler. |
| Varlık envanteri listeleme | `assets list` kayıtlı domainleri ağ isteği yapmadan gösterir. |
| Toplu domain içe alma | `import domains` sınırlandırılmış TXT veya JSONL dosyasındaki domainleri doğrulayarak alır. |
| Varlık iş önemi | Bir varlığa insan onaylı önem seviyesi atanabilir, değiştirilebilir ve geçmişiyle kaldırılabilir. |
| Kuruluş oluşturma | Kuruluş kaydı firma adıyla oluşturulur ve veri toplamadan ayrı bir kimlik kazanır. |
| Kuruluş yaşam döngüsü | Kuruluş adı değiştirilebilir, geçmiş silinmeden kapatılabilir ve yeniden etkinleştirilebilir. |
| Kuruluş–domain bağlantısı | Önceden kayıtlı domain açık gerekçeyle doğru kuruluşa bağlanabilir veya bağlantısı geri çekilebilir. |
| Kuruluş–izleme bağlantısı | Sosyal, ransomware ve diğer desteklenen izlemeler açık seçimle kuruluşa bağlanabilir. |
| Bağlantı geçmişi | Kuruluş bağlantısının eklenme, değişme ve kaldırılma geçmişi tek kayıtta görülebilir. |
| Kuruluş içerik görünümü | Kuruluş ve seçilmiş tedarikçileriyle ilgili saklı içerikler sade ve ağsız biçimde gösterilir. |
| Birleşik kuruluş raporu | Domain, yüzey, içerik, sosyal, olay, vaka, CTI ve kaynak durumları tek kuruluş raporunda birleştirilir. |
| Kuruluş HTML dışa aktarma | Tam kuruluş raporu dış metinleri güvenli biçimde kaçırarak yeni bir HTML dosyasına yazılır. |
| Dönemsel kuruluş değişiklikleri | Son gün veya haftadaki eklenen, değişen ve kaybolan kayıtlar kaynak boşluklarıyla birlikte gösterilir. |
| Kaynak katkısı karşılaştırması | Her kaynağın getirdiği tekil ve ortak domainler ile çalışma başarısı ayrı ayrı gösterilir. |
| Birleşik domain analizi | `analyze` bir domainin saklı dış risk kanıtlarını yeni ağ isteği olmadan tek görünümde birleştirir. |
| Bütün kayıt türlerinde yerel arama | `search` domain, bulgu, sosyal profil, olay, vaka, haber, CTI ve IOC kayıtlarında ortak arama yapar. |
| Kayıtlı toplama profilleri | Kaynak ve izleme seçimleri adla kaydedilebilir, sürümlü değiştirilebilir ve geçmiş silinmeden kapatılabilir. |
| Birleşik pasif toplama | `collect` seçilmiş tarama, keşif, feed ve izleme adımlarını çalıştırıp kaynak sonuçlarından ortak analiz üretir. |
| Toplama oturumu geçmişi | Her toplama oturumunun kaynak adımları, sonucu ve eksik kalan bölümleri saklanır. |
| Eksik toplama adımını sürdürme | `collections resume` tamamlanmış kaynakları tekrarlamadan yalnız eksik adımları yeni yürütmede dener. |
| Kesilmiş toplama kurtarma | `collections recover` yarım oturumu kanıtı koruyarak kapatır ve kendiliğinden internet araması başlatmaz. |
| Firma çalışma alanı oluşturma | `platform provision` her firma için ayrı çekirdek veri ve iş kuyruğu alanı oluşturur. |
| Firma verisi izolasyonu | Bir firmanın workspace kimliğiyle diğer firmanın kayıtlarına erişim veya yazma reddedilir. |
| Firma alanını kapatma | `platform disable` yeni firma erişimini durdurur ancak geçmiş verileri silmez. |
| Firma yedeği ve geri dönüşü | Platform yedeği çekirdek kanıtla iş kuyruğunu birlikte korur ve geri dönüşte yeni workspace bağı üretir. |

## C. Domain, phishing adayı ve dış saldırı yüzeyi

| Özellik adı | Tek cümlelik açıklama |
|---|---|
| Sertifika geçmişinde marka arama | `scan --source crt.sh` sertifika kayıtlarında marka veya domain benzerliği taşıyan adayları arar. |
| Web tarama geçmişinde marka arama | `scan --source urlscan` mevcut urlscan kayıtlarında aday domain ve URL'leri arar, yeni tarama göndermez. |
| Unicode ve IDN güvenliği | Benzer görünen farklı alfabe karakterleri, geçersiz IDN ve şaşırtıcı domain biçimleri güvenli biçimde ayrılır. |
| Yazım benzerliği adayları | Domain adları sınırlı benzerlik kurallarıyla adaylaştırılır ancak otomatik phishing hükmü verilmez. |
| Kalıcı bulgu kimliği | Aynı gözlem tekrar geldiğinde yeni kopya yerine mevcut bulgunun kanıt geçmişi güncellenir. |
| Bulgu listesi ve ayrıntısı | Aday bulgular kaynakları, durumları ve insan kararlarıyla listelenip açılabilir. |
| Bulgu DNS/HTTPS kontrolü | Kayıtlı adayın DNS ve HTTPS erişim durumu kontrollü olarak yeniden gözlemlenebilir. |
| Açıklamalı inceleme sırası | `triage` bulguları neden bakılması gerektiğini açıklayan ağsız bir sırada gösterir. |
| Bulgu insan kararı | Analist bulguyu doğrulanmış, reddedilmiş veya belirsiz gibi gerekçeli durumlarla işaretleyebilir. |
| Bulgu karar geçmişi | Yeni kanıt eski insan kararını silmez ve bütün karar değişiklikleri görülebilir. |
| Tam domain istisnası | Meşru bir tam domain bulgusu süreli veya kalıcı istisna listesine alınabilir. |
| İstisna geçmişi | İstisna ekleme ve kaldırma işlemleri eski bulguları değiştirmeden saklanır. |
| Bulgu raporu | Tek bulgunun bütün kaynakları, kanıtı ve karar geçmişi ağsız raporlanır. |
| Sınırlı internet izleme | `watch` terminal açıkken aynı pasif aramayı belirlenen tur ve süre sınırıyla tekrarlar. |
| Aktif kontrol onayı | Bir domain, gerekçe kaydedilmeden DNS/TLS veya servis kontrolü kapsamına alınamaz. |
| Aktif kapsamı geri çekme | Onaylanan domain aktif kontrolden çıkarılabilir ve eski kontrol geçmişi korunur. |
| DNS/TLS/HTTPS temel kaydı | Yetkili domainde DNS cevapları, HTTPS durumu ve TLS sertifika bilgisi sınırlı biçimde kaydedilir. |
| Dış yüzey genel görünümü | Kök domain, alt alan adı, IP, sertifika, posta ve servis kanıtı tek görünümde birleştirilir. |
| Kanıt güncellik görünümü | Web, posta ve servis kanıtının güncel, eski, başarısız veya hiç kontrol edilmemiş olduğu ayrı gösterilir. |
| Katmanlı yüzey envanteri | Kayıtlı varlık, pasif aday ve aktif kontrol kapsamı birbirine karıştırılmadan gösterilir. |
| Açıklanabilir maruziyet adayları | Açık görünen servis veya yapılandırma yalnız kanıt ve eksik kapsamıyla inceleme adayı olarak gösterilir. |
| Muhafazakâr teknoloji ipuçları | Port ve protokol kanıtından ürün veya sürüm kesinliği iddia etmeyen teknoloji ipuçları çıkarılır. |
| Yüzey ilişki geçmişi | IP, sertifika, CNAME ve tedarikçi bağlantıları kaynak ve zamanlarıyla gösterilir. |
| Pasif alt alan adı keşfi | `surface discover` crt.sh veya desteklenen arşiv kaynağından alt alan adı adayları toplar. |
| Pasif kaynak sağlık ayrımı | Gerçek boş sonuç, zaman aşımı, eksik yanıt ve önceki başarılı sonuç ayrı durumlarda gösterilir. |
| Alt alan adı aday kararı | Pasif aday bekliyor, kuruluşa ait veya reddedildi olarak insan kararıyla işaretlenebilir. |
| Pasif keşif geçmişi | Her keşif çalışmasının kaynak sonucu ve aday değişiklikleri silinmeden saklanır. |
| Pasif keşif izleme | Alt alan adı keşfi terminal açıkken sınırlı tur ve kaynak bütçesiyle tekrarlanabilir. |
| CNAME kanıtı | Google Public DNS üzerinden sınırlı CNAME zinciri alınır ve geçmişiyle saklanır. |
| CNAME risk adayı | Çözülemeyen veya değişen CNAME yalnız inceleme adayı olarak gösterilir, ele geçirilme hükmü verilmez. |
| E-posta DNS duruşu | MX, SPF ve DMARC temel kayıtları alınır ve önceki durumla karşılaştırılır. |
| Sabit güvenli TCP kontrolü | Yetkili kesin IP'de önceden belirlenmiş 10 TCP portu banner almadan kontrol edilebilir. |
| Yüzey monitörü | Seçili DNS, TLS, posta, CNAME ve servis kontrolleri sınırlı döngüde çalıştırılabilir. |

## D. Haber, yayın, şirket içeriği ve kod maruziyeti

| Özellik adı | Tek cümlelik açıklama |
|---|---|
| RSS/Atom kaynak kataloğu | Desteklenen NCSC, CISA ve CERT-FR yayınları kaynak ve atıf bilgileriyle gösterilir. |
| RSS/Atom yenileme | Seçili yayın akışı tek seferde alınır ve tam makale sayfası açılmadan yerel kataloğa kaydedilir. |
| Yerel haber arama | Saklanan haberlerde başlık, özet ve bağlantı üzerinden firma veya kelime aranabilir. |
| Haber kaynak sağlığı | Son deneme, son başarı, eski kayıt ve kaynak hatası birbirinden ayrı gösterilir. |
| Haber değişim geçmişi | Yayından çıkan veya değişen haber eski kanıtı silmeden önceki ve sonraki haliyle saklanır. |
| Kayıtlı haber araması | Haber sorgusu kaydedilip ilk sessiz ölçümden sonra yeni veya değişen sonuçları karşılaştırabilir. |
| Kamu ihlal metadata kataloğu | HIBP'nin ücretsiz kamu olay kataloğu e-posta veya parola sorgulamadan alınabilir. |
| Kamu olayında domain arama | Yerel katalogda tam domain ve olay adı eşleşmeleri aranabilir. |
| Kamu olay izleme | Kuruluş domainlerinin katalogdaki yeni veya değişen eşleşmeleri sessiz başlangıç sonrası izlenebilir. |
| Kamu olay geçmişi | Olay metadata değişiklikleri, kaynak çalışması ve kuruluş kapsamı değişmez biçimde okunabilir. |
| İzinli yayıncı kataloğu | Tam metin alınmasına izin verilen yayıncıların lisans ve belge sınırları gösterilir. |
| İzinli HTML/PDF alma | Seçilmiş CERT-FR ve NCSC belgelerinin ana metni sınırlandırılmış biçimde alınabilir. |
| PDF metni çıkarma | İzinli PDF içeriği ayrı, süre ve boyut sınırlı işlemde metne dönüştürülebilir. |
| Yayıncı belge işi | Seçilmiş HTML/PDF belgeleri kalıcı kuyrukta ayrı ayrı işlenir ve başarısız belge diğer başarılı belgeyi silmez. |
| Sürümlü rapor belgesi | Toplanmış haber veya firma metni değiştiğinde eski metin korunarak yeni belge sürümü oluşturulur. |
| Rapor–CTI bağlantısı | Belirli bir rapor sürümü aktör, kampanya veya başka CTI kaydına insan gerekçesiyle bağlanabilir. |
| Gözlem türlerini ayırma | Metinde geçme, liste üyeliği, sağlayıcı iddiası ve gerçek sensör görülmesi ayrı anlamlarda tutulur. |
| İçerik kaynak tanımı | RSS, Atom ve desteklenen kanal kaynağı isim, dil, bölge ve kapsamıyla sürümlü kaydedilebilir. |
| Firma/tedarikçi içerik izlemesi | Kuruluş ve seçilmiş tedarikçi adları kaynak içeriğinde açık eşleşme gerekçesiyle aranabilir. |
| Çok dilli kesin metin desteği | Türkçe, Rusça, Çince, Arapça ve Portekizce Unicode adlar bozulmadan eşleştirilebilir. |
| İçerik kanıtı | Başlık, kısa metin, bağlantı, kaynak zamanı ve eşleşme nedeni değişmez kanıt olarak saklanır. |
| İçerik insan incelemesi | İçerik ilgili, ilgisiz veya belirsiz gibi gerekçeli kararla işaretlenebilir. |
| İçerik değişiklik takibi | İlk sessiz ölçümden sonra yeni veya değişen içerikler eski kararları silmeden gösterilir. |
| İçerik raporu | Bir izleme için güncel içerik, kaynak hatası, karar ve geçmiş tek raporda gösterilir. |
| İçerik sınırlı monitörü | Kayıtlı içerik izleme aralığına uyarak terminalde sonlu sayıda tur çalıştırılabilir. |
| Bluesky genel gönderi izlemesi | Firma veya tedarikçi adı, domaini ve alternatif adlarıyla eşleşen genel Bluesky metin gönderileri mevcut kanıt ve inceleme akışında izlenebilir. |
| Anahtarsız GitHub kamu depo keşfi | Firma adı veya domain geçen herkese açık GitHub depo ve sınırlı dosya adayları bulunabilir. |
| Anahtarsız GitLab kamu proje keşfi | Firma adı veya domain geçen herkese açık GitLab proje adayları bulunabilir. |
| Betterleaks secret aday taraması | Alınan izinli metin Betterleaks ile aktif doğrulama yapılmadan secret adayı açısından taranır. |
| Secret maskeleme | Bulunan gizli değer adayının ham içeriği kalıcı kayda yazılmadan türü ve maskeli kanıtı saklanır. |
| Kod maruziyeti izlemesi | Firma/domain için kaynak, depo ve dosya kapsamı olan sürümlü kod izleme tanımı oluşturulabilir. |
| Kod arama planı | Kullanılacak kaynak, erişim, dosya bütçesi ve eksik kapsam internet isteğinden önce gösterilir. |
| Kod bulgu geçmişi | Marka geçişi ve secret adayı kaynak dosya ve değişmez kanıt kimliğiyle listelenebilir. |
| Kod bulgusu insan kararı | Analist maskeli kod bulgusunu kanıta bağlı gerekçeli kararla inceleyebilir. |
| Kod değişiklik karşılaştırması | İlk sessiz ölçümden sonra eklenen, değişen veya kaybolan kod kanıtı gösterilir. |
| Kod maruziyeti raporu | Domain için kaynak sonucu, maskeli kanıt, insan kararı ve eksik kapsam birleştirilir. |
| Kod izleme monitörü | Kayıtlı kod izlemesi sınırlı sayıda periyodik turla çalıştırılabilir. |

## E. Marka, sosyal profil, görsel ve uygulama adayları

| Özellik adı | Tek cümlelik açıklama |
|---|---|
| Sosyal araç uygunluk kontrolü | Maigret ve Sherlock sürümü, katalog kapsamı ve kurulum bilgisi çalıştırmadan doğrulanabilir. |
| Sosyal platform profilleri | Güvenli ve geniş Maigret/Sherlock platform seçimleri ağsız olarak görülebilir. |
| Kullanıcı adı önizlemesi | Maigret veya Sherlock seçilmiş herkese açık platformlarda yazmasız profil adayı arayabilir. |
| İki sosyal kaynağın kapsam karşılaştırması | Aynı kullanıcı adı için Maigret ve Sherlock sonuçları kaynakları karıştırılmadan karşılaştırılır. |
| Kalıcı kullanıcı adı izlemesi | Bir marka kullanıcı adı için kaynak seçimi ve kapsamı olan izleme tanımı oluşturulabilir. |
| Sosyal izleme çalışması | Kayıtlı kullanıcı adı izlemesi çalıştırılır ve her kaynağın sonucu ayrı saklanır. |
| Sosyal profil insan kararı | Bulunan profil resmî, taklit, ilgisiz veya belirsiz gibi gerekçeli kararla işaretlenebilir. |
| Sosyal izleme geçmişi | Profil sonucu ve insan kararı değişmeden önceki çalışmalarla birlikte görülebilir. |
| Toplu sosyal izleme | Bütün etkin kullanıcı adı izlemeleri kaynak bütçeleri korunarak tek turda çalıştırılabilir. |
| Sosyal izleme monitörü | Terminal açıkken kullanıcı adı izlemeleri sınırlı aralık ve tur sayısıyla tekrarlanabilir. |
| Birleşik sosyal keşif | `brand discover` araç, arama ve doğrudan sayfa kontrolünden gelen profil adaylarını tek sonuçta birleştirir. |
| Firma domaininden kullanıcı adı çıkarma | Marka adı verilmediğinde uygun domain kökünden kontrollü kullanıcı adı adayı üretilebilir. |
| Doğrudan profil sayfası doğrulama | Sosyal profil URL'si açılarak gerçek profil, giriş engeli, erişim hatası ve yumuşak 404 ayrılır. |
| Sosyal keşif kanıtı | Her profil için kaynak URL, gözlem zamanı, doğrulama yöntemi ve belirsizlik saklanır. |
| Sosyal keşif inceleme görünümü | Firma profilleri kaynak kanıtı ve önceki insan kararıyla tek inceleme ekranında gösterilir. |
| Sosyal profil karar kaydı | Bir profil için gerekçeli insan kararı saklanır ve sonraki kaynak değişikliği eski kararı silmez. |
| Ücretsiz sosyal takip tanımı | Bulunan profil kapsamından ücretsiz, sürümlü ve duraklatılabilir takip oluşturulabilir. |
| Sessiz sosyal başlangıç | Sosyal takibin ilk başarılı turu alarm üretmeden karşılaştırma başlangıcı olur. |
| Sosyal profil değişiklik bildirimi | Sonraki turlardaki yeni, değişen veya erişilemeyen profil kanıtı yerel kutuya kaydedilir. |
| Eski sosyal hedefi yeniden kontrol | Kaynak artık bildirmese bile önceden doğrulanmış profil adresleri dönüşümlü olarak yeniden kontrol edilir. |
| Marka kimliği yönetimi | Resmî domain, logo, sosyal hesap, uygulama yayıncısı ve isteğe bağlı kişi bilgisi sürümlü saklanır. |
| Marka koruma izlemesi | Bir marka kimliği için domain, sayfa, görsel, sosyal ve mağaza kapsamı olan izleme tanımı oluşturulabilir. |
| Marka koruma planı | Kaynaklar, istek sınırları, kanıt türleri ve eksik kapsam ağ isteğinden önce gösterilir. |
| Benzer domain adayı | CT, urlscan ve saklı kayıtlardan marka adına benzeyen domainler aday olarak çıkarılır. |
| Statik web sayfası kanıtı | Aday HTTPS sayfasının JavaScript kapalı güvenli görüntüsü ve sınırlı metni kaydedilebilir. |
| Ekran görüntüsü kanıtı | Uygun aday sayfanın PNG görüntüsü hash ve kaynak kimliğiyle değişmez kanıt olarak saklanır. |
| Logo benzerliği | Güvenli görsel boyut sınırları içinde marka logosu ile aday görselin parmak izi karşılaştırılır. |
| Sayfa görsel benzerliği | Resmî sayfa ve aday ekran görüntüsü karşılaştırılır ancak sonuç otomatik taklit hükmü sayılmaz. |
| Form ve şablon ipuçları | Ortak form, metin ve dosya işaretleri olası klon sayfa göstergesi olarak açıklanır. |
| Apple uygulama adayı | Seçili ülke mağazasında marka adı, uygulama kimliği ve yayıncı bilgisiyle aday aranabilir. |
| Google Play uygulama adayı | Seçili Google Play sonuçlarında marka adı ve yayıncı farkı olan uygulama adayları aranabilir. |
| Uygulama yayıncı karşılaştırması | Aday uygulamanın yayıncısı resmî marka yayıncısıyla karşılaştırılıp belirsizliğiyle gösterilir. |
| VIP/yönetici kimliği modeli | İsteğe bağlı kişi adı ve rolü marka kimliğine eklenerek taklit adayları için kullanılabilir. |
| Marka kanıt ayrıntısı | Adayın metin, görsel, sosyal, mağaza ve kaynak kanıtları tek tek açılabilir. |
| Marka kanıt dosyası alma | Saklanmış güvenli PNG gibi kanıt dosyaları kimliği doğrulanarak dışarı alınabilir. |
| Marka adayı insan incelemesi | Aday resmî, bayi, parodi, ilgisiz, şüpheli, doğrulanmış taklit veya belirsiz olarak işaretlenebilir. |
| Marka değişiklik geçmişi | Kaynak, aday veya görsel değişikliği eski kanıt ve insan kararını koruyarak gösterilir. |
| Marka koruma raporu | Kimlik, kaynak kapsamı, adaylar, kanıt ve kararlar tek marka raporunda birleştirilir. |
| Marka koruma monitörü | Marka koruma izlemesi kaynak bütçesi ve zaman sınırıyla sonlu döngüde çalıştırılabilir. |
| Marka çalışması kurtarma | Kesilmiş marka çalışması yeni ağ çağrısı yapılmadan açıkça kapatılabilir. |

## F. Ransomware, dark web iddiaları ve credential kanıtı

| Özellik adı | Tek cümlelik açıklama |
|---|---|
| RansomLook kaynak yenileme | RansomLook kamu ransomware iddiaları kaynak atfıyla alınarak yerel snapshot'a kaydedilebilir. |
| ThreatCluster kaynak yenileme | ThreatCluster kamu snapshot'ı kişisel/açık kullanım profilinde ayrı kaynak kimliğiyle alınabilir. |
| Kaynak bazlı ransomware geçmişi | Her ransomware kaynağının başarılı, boş, değişen ve başarısız çalışmaları ayrı saklanır. |
| Ransomware son kayıtları | Son kaynak iddiaları kuruluş hükmü verilmeden tarih ve kaynaklarıyla listelenir. |
| İki ransomware kaynağını karşılaştırma | Aynı isim veya olay iki kaynakta eşleşse bile kaynak iddiaları birleştirilmeden yan yana gösterilir. |
| Ransomware kaynak insan kararı | Kaynaklar arası aday eşleşmesi aynı, farklı veya belirsiz gibi gerekçeli kararla işaretlenebilir. |
| Kuruluş ransomware izlemesi | Kuruluş adı için kaynağın sağladığı alanlara uygun kalıcı izleme oluşturulabilir. |
| Domain ransomware izlemesi | Yalnız domain bilgisi sağlayan desteklenen kaynaklarda tam domain eşleşmesi izlenebilir. |
| Ransomware sessiz başlangıç | İzlemenin ilk başarılı sonucu alarm üretmeden karşılaştırma başlangıcı olur. |
| Ransomware değişiklik izlemesi | Sonraki turlardaki yeni veya değişen iddialar önceki kaynak snapshot'ıyla karşılaştırılır. |
| Bütün izlemeleri yenileme | Etkin ransomware izlemeleri kaynak başına tek yenileme kullanılarak çalıştırılabilir. |
| Ransomware monitör oturumu | Terminalde sınırlı süre çalışan izleme oturumları ve sonuçları kalıcı saklanır. |
| Ransomware zaman çizelgesi | Bir izleme için kaynak iddiaları ve değişiklikler zaman sırasıyla gösterilir. |
| Ransomware kimlik değişimi adayı | Adı veya sitesi değişmiş olabilecek kaynak kaydı otomatik birleştirilmeden inceleme adayı yapılır. |
| Ransomware kimlik kararı | Kimlik değişimi adayı insan tarafından gerekçeli ve geri alınabilir kararla incelenebilir. |
| Dark web izleme profili | Kuruluş, tedarikçi, kaynak ve eşleşme sınırları sürümlü bir profil olarak kaydedilebilir. |
| Saklı dark web analiz planı | Kullanılacak mevcut ransomware ve ihlal kanıtı ağ isteği olmadan planlanabilir. |
| Dark web analiz çalışması | Saklı kaynak kanıtı tek firma kapsamında taranarak değişmez çalışma sonucu oluşturulur. |
| Dark web bulguları | Firma veya tedarikçiyle kesin ad/domain eşleşen iddialar kaynak ve eşleşme gerekçesiyle listelenir. |
| Dark web kanıt ayrıntısı | Bulguyu oluşturan kaynak snapshot'ı ve maskeli kanıt değişmez kimliğiyle açılabilir. |
| Dark web insan incelemesi | Kaynak iddiası doğrulanmış olay sayılmadan analist tarafından kabul, ret veya belirsiz olarak işaretlenebilir. |
| Dark web değişiklik takibi | İlk sessiz çalışmadan sonra eklenen ve değişen bulgular kaynak kesintisinden ayrı gösterilir. |
| Dark web raporu | Profil, kaynak durumu, bulgular, maskeli credential kanıtı ve kararlar birlikte raporlanır. |
| Dark web monitörü | Kayıtlı profil sınırlı turda çalıştırılabilir ve canlı credential çağrısı gizlice başlatılmaz. |
| Dark web kesinti kurtarma | Yarım analiz açıkça `interrupted` durumuna alınır ve eski kanıt korunur. |
| Credential veri minimizasyonu | Hesap aliası bellekte maskelenir ve kalıcı alana yalnız maskeli değer, HMAC kimliği, domain ve ihlal adı yazılır. |
| Kuruluşa özel pseudonym anahtarı | Aynı hesabın kuruluş içinde takip edilmesini sağlayan ayrı gizli HMAC anahtarı üretilebilir. |
| Zararsız parola maruziyet kontrolü | Parola yerelde Keccak-512 ile işlenip yalnız 10 karakterlik önek gönderilerek tek seferlik maruziyet sayısı alınabilir. |
| Eski HIBP credential geçmişini okuma | Önceki şemalarda saklanan HIBP provider kayıtları yeniden sorgulanmadan ve adı değiştirilmeden okunabilir. |
| Anahtarsız toplu domain maruziyeti | Lunar/Webz.io üzerinden kuruluşa bağlı kesin domainin son 12 aylık employee/client ve breach/infostealer sayı/tarihleri bireysel credential alınmadan yenilenebilir. |
| Lunar hazırlık ve hata ayrımı | Hazırlanan rapor, başarılı sıfır, yetkisiz, kota, kaynak hatası ve korunan son başarılı snapshot birbirine karıştırılmaz. |
| P11 kaynak çalışma geçmişi | Lunar ve AIL kaynak turları durum, kapsam, sayı, zaman, hata ve hash zinciriyle sayfalı okunabilir. |
| P11 kaynak kayıt ayrıntısı | Güncel toplu maruziyet veya yeraltı iddiası kaydı kaynak, gövde özeti, aktiflik ve ilk/son görülme bilgisiyle açılabilir. |
| AIL zarfı yazmasız önizleme | Güvenilen işletici AIL 7.x metadata zarfını kapsam, alan, boyut, hash ve firma eşleşmesi bakımından kayıt oluşturmadan doğrulayabilir. |
| AIL zarfı atomik içe alma | Önizleme SHA-256 değeri aynı kalan en fazla 1.000 minimize AIL kaydı idempotent olarak firma alanına alınabilir. |
| P11 kaynak turu kurtarma | Yarım kalan Lunar veya AIL turu yeni ağ çağrısı ya da veri kaybı olmadan `interrupted` durumuna kapatılabilir. |

## G. IOC, CTI, ATT&CK ve kaynaklı araştırma

| Özellik adı | Tek cümlelik açıklama |
|---|---|
| IOC ekleme | Domain, IP, URL veya hash için bağımsız kaynak iddiası kanonik değerle kaydedilebilir. |
| IOC listeleme ve arama | Yerel IOC kataloğu tür, değer ve durumla ağsız listelenip aranabilir. |
| IOC kaynak geçmişi | Aynı IOC'nin farklı kaynak iddiaları birbirini ezmeden zaman ve güven bilgisiyle saklanır. |
| IOC kaynağını geri çekme | Tek kaynak iddiası geçmiş silinmeden etkisizleştirilebilir. |
| Ücretsiz IOC beslemesi yenileme | Feodo Tracker ve CERT Polska listeleri güvenli tam snapshot olarak yenilenebilir. |
| IOC besleme sağlığı | Her feed'in son denemesi, son başarısı, kayıt sayısı ve hatası ayrı gösterilir. |
| IOC yaşam döngüsü | Bir IOC'nin kaynak yaşı, geçerlilik zamanı, son toplama ve insan kararı gerekçeli biçimde değerlendirilir. |
| IOC kaynak karşılaştırması | Bir IOC hakkındaki kaynak iddiaları ile gerçek yerel sensör görülmeleri birbirine karıştırılmadan karşılaştırılır. |
| IOC toplu dosya önizleme | CSV, JSON veya sınırlı STIX dosyası yazma yapmadan bütünüyle doğrulanabilir. |
| IOC toplu içe alma | Doğrulanmış en fazla 50.000 IOC tek işlem ve tekrar anahtarıyla atomik olarak alınabilir. |
| IOC toplu dışa aktarma | Güncel IOC kaynak iddiaları yeni CSV, JSON veya XTI-STIX dosyasına çıkarılabilir. |
| MISP warninglist yenileme | Seçili MISP warninglist kaynakları atomik olarak indirilip önceki başarılı liste korunabilir. |
| Warninglist bağlam araması | Domain veya IP'nin CDN, özel ağ ve benzeri liste bağlamı internete sorgu göndermeden gösterilir. |
| Warninglist geçmişi | Liste sürümü, kaynak çalışması ve değişiklik geçmişi saklanır. |
| URL/hash kaynak zenginleştirmesi | Desteklenen resmî kaynakta URL veya hash sorgulanıp sınırlı yanıt kanıtı saklanabilir. |
| IP/ASN ağ bağlamı | RIPEstat üzerinden sınırlı ağ, ASN ve WHOIS alanları kaynak atfıyla alınabilir. |
| Zenginleştirme geçmişi | Her sorgunun kaynak makbuzu ve değişmez sonucu ağsız yeniden açılabilir. |
| MITRE ATT&CK kataloğu | Sabit Enterprise ATT&CK grup, kampanya, malware, teknik ve taktik kataloğu atomik yenilenebilir. |
| ATT&CK yerel arama | Teknik, taktik, grup, kampanya veya yazılım yerel katalogda aranabilir. |
| ATT&CK kayıt ayrıntısı | Teknik kodu veya STIX kimliğiyle resmî kaynak kaydı ve ilişkileri gösterilebilir. |
| CTI varlık kaydı | Aktör, kampanya, malware, araç veya rapor için kaynaklı varlık iddiası eklenebilir. |
| CTI varlık yaşam döngüsü | Varlık listelenebilir, aranabilir, geçmişiyle açılabilir ve tek kaynak iddiası geri çekilebilir. |
| CTI ilişki kaydı | Bir CTI varlığından başka varlığa veya IOC'ye kaynaklı ilişki eklenebilir. |
| CTI ilişki yaşam döngüsü | İlişki listelenebilir, geçmişiyle açılabilir ve kaynak iddiası silinmeden geri çekilebilir. |
| CTI bağlam görünümü | Tam IOC veya CTI varlığının bütün kayıtlı bağlantıları kaynaklarıyla birlikte gösterilir. |
| Birleşik CTI arama | CTI varlıkları, ilişkileri ve IOC kayıtları tek yerel aramada bulunabilir. |
| Sınırlı STIX 2.1 IOC çıktısı | Güncel IOC kaynak iddiaları STIX 2.1 JSON paketi olarak dışarı verilebilir. |
| CTI kayıtlı arama | Bir IOC veya CTI sorgusu sonraki yerel karşılaştırmalar için kaydedilebilir. |
| CTI arama farkı | Kayıtlı arama ilk sessiz çalışmadan sonra eklenen, güncellenen ve kaldırılan kayıtları gösterir. |
| CTI arama etiketleri | Kayıtlı aramaya geçmişi korunan etiketler eklenebilir veya kaldırılabilir. |
| CTI analist notları | Kayıtlı aramaya silinmeyen analist notları yazılabilir ve günlükte gösterilebilir. |
| CTI arama monitörü | Kayıtlı CTI araması terminal açıkken kaynak toplamadan sınırlı aralıklarla tekrarlanabilir. |
| CTI analiz profili | Kuruluş, kaynak güveni, eşikler, kritik önem ve bütçeler sürümlü analiz profiline kaydedilebilir. |
| CTI analiz planı | Kullanılacak saklı CTI, IOC, ATT&CK ve kuruluş kapsamı ağ isteği olmadan gösterilir. |
| Kimlik eşleştirme adayı | Aynı türde benzer ad veya alias taşıyan varlıklar otomatik birleştirilmeden aday yapılır. |
| Kanıtlı TTP adayı | Açık teknik kimliği veya kabul edilmiş ATT&CK bağı olan kanıttan teknik kullanım adayı üretilir. |
| Açıklanabilir atıf adayı | Açık atıf ya da bağımsız çoklu kanıt varsa aktör ilişkisi adayı gösterilir. |
| Coğrafya/sektör kaynak iddiası | Metindeki coğrafya ve sektör ifadeleri gerçek köken hükmü yerine alıntılı kaynak iddiası olarak etiketlenir. |
| Kuruluşa özel CTI önceliği | Kuruluş domain/URL bağı ve insan tarafından belirlenmiş önem analist sırasını açıklamak için kullanılır. |
| CTI aday insan kararı | Kimlik ve analiz adayı kabul, ret, belirsiz, aynı varlık veya farklı varlık olarak işaretlenebilir. |
| CTI değişiklik görünümü | Kanıt değişikliği ile yalnız kaynak kapsamı değişikliği birbirinden ayrı gösterilir. |
| CTI ilişki grafı | Kaynaklı aktör, malware, altyapı, IOC ve rapor bağlantıları sınırlı ve sayfalı graf olarak döner. |
| CTI zaman çizelgesi | Kaynak iddiaları ve analiz değişiklikleri özgün zaman anlamları korunarak sıralanır. |
| CTI trend görünümü | Kampanya sinyali, kaynak değişimi ve sabit durum otomatik olay hükmü verilmeden karşılaştırılır. |
| CTI kaynak kalite görünümü | Kaynak güveni, bağımsızlık grubu, destek sayısı ve tazelik açıklanabilir bileşenler halinde gösterilir. |
| CTI analiz raporu | Profil, kapsam, adaylar, kararlar, trend ve eksik kanıt tek kuruluş raporunda birleştirilir. |
| CTI analiz monitörü | Saklı kanıt kullanan analiz profili sınırlı döngüde ağsız olarak çalıştırılabilir. |
| CTI analiz kurtarma | Kesilmiş analiz turu yeniden çalıştırılmadan açıkça kapatılabilir. |

## H. Ortak araştırma, ilişkiler ve kanıt grupları

| Özellik adı | Tek cümlelik açıklama |
|---|---|
| Domain kanıt yolları | `research` kayıtlı domainden IP, sertifika, CTI, rapor ve diğer kanıtlara giden yolları gösterir. |
| IP kanıt yolları | Kayıtlı IP'nin domain, ağ, IOC, sertifika ve kaynak bağlantıları ağsız araştırılabilir. |
| URL kanıt yolları | URL'nin domain, IOC, rapor ve sağlayıcı kanıt bağlantıları kaynaklarıyla gösterilebilir. |
| Dosya hash kanıt yolları | Dosya hashinin IOC, zenginleştirme ve CTI bağlantıları yerel kayıtlardan araştırılabilir. |
| Araştırma kapsam sınırı | Düğüm, kenar, derinlik ve kayıt sınırına ulaşılması boş sonuç yerine açık kısmi kapsam olarak gösterilir. |
| Araştırma öncelikleri | Saklı kanıtlar nedenleriyle birlikte analistin önce bakacağı kayıtlar olarak sıralanabilir. |
| Araştırma geçmişi kaydetme | Seçilen kapsamın o andaki inceleme görünümü değişmez kayıt olarak saklanabilir. |
| Araştırma değişim karşılaştırması | Yeni inceleme önceki kayıtla karşılaştırılarak gerçek kanıt değişimi ile yalnız yaşlanma ayrılır. |
| Kaynak çelişkileri | Aynı kayıt hakkında farklı kaynakların karşıt iddiaları ve erişim sorunları yan yana gösterilebilir. |
| Kimlik adayı bulma | Ad ve kaynak aliası üzerinden olası aynı kimlikler otomatik birleştirme olmadan bulunabilir. |
| Elle kimlik adayı oluşturma | İki mevcut kayıt arasında kanıta dayalı eşleştirme adayı analist tarafından oluşturulabilir. |
| Metinden IOC adayı çıkarma | Saklı haber veya firma metninden domain, IP, URL ve hash adayları yazma yapmadan çıkarılabilir. |
| Kimlik/IOC adayı kararı | Aday için gerekçeli insan kararı kaydedilir ancak özgün kayıtlar birleştirilmez. |
| Birleşik kimlik görünümü | Kabul edilmiş kimlik bağları özgün varlıkları ve karar geçmişini kaybetmeden birlikte gösterilir. |
| Açıklanabilir olay adayları | Farklı saklı kaynak kayıtları birleştirilmeden ortak kimlik ve zaman ipuçlarıyla olay adayı olarak gösterilir. |
| Gerçek sensör görülmesi kaydı | Bir sensörün gerçekten gördüğü domain, IP, URL veya hash kaynak listelerinden ayrı kaydedilebilir. |
| Görülme yaşam döngüsü | Sensör görülmesi listelenebilir, kanıtıyla açılabilir ve geçmiş silinmeden geri çekilebilir. |
| İlişki adayları | Saklı kanıttan ortak IP, sertifika, rapor veya kimlik bağları açıklanabilir aday olarak çıkarılır. |
| İlişki insan kararı | İlişki adayı kabul, ret veya belirsiz kararla işaretlenebilir. |
| İlişki değişim sırası | Dayanak kanıtı değişen daha önce incelenmiş ilişkiler yeniden inceleme sırasında gösterilir. |
| İlişki bildirimi | Dayanak değişikliği yerel bildirim kutusuna tekrarsız kanıtla eklenebilir. |
| Kanıt grubu önizleme | Ortak IP, sertifika veya rapor bağlantılı kayıtlar yazmadan grup adayı olarak gösterilir. |
| Kanıt grubu yakalama | Seçilen araştırma kapsamı değişmez grup snapshot'ı olarak saklanabilir. |
| Güncel grup görünümü | Grubun güncel üyeleri, kaynakları ve insan kararları bütün geçmişi yeniden işlemden okunabilir. |
| Grup geçmişi | Grup tanımı, çalışmalar, üyeler ve kararlar kayıpsız sayfalanabilir. |
| Grup değişiklikleri | Üye ve kanıt farkları önceki/sonraki değerlerle gösterilir. |
| Grup bütünlük denetimi | Grup olay zinciri, indeksleri ve özgün kanıt bağları denetlenebilir. |
| Grup indeksini yeniden kurma | Doğrulanmış olay geçmişinden güncel grup görünümü yedekli biçimde yeniden oluşturulabilir. |
| Grup inceleme sırası | Değişmiş veya kararsız gruplar gerekçeli analist sırasına alınabilir. |
| Grup kararı | Grup veya üye ilişkisi için kanıta bağlı insan kararı saklanabilir. |
| Grup yerel yeniden kontrolü | Grup yalnız saklı kanıtta yeniden değerlendirilerek kaynak toplama yapmadan değişiklik üretebilir. |
| Grup bildirimleri | Grup değişiklikleri ortak bildirim sırasına ve vaka kanıtına bağlanabilir. |
| Grup sınırlı monitörü | Kayıtlı grup belirlenen aralıkta sonlu sayıda yerel yeniden kontrole alınabilir. |
| Firma genel inceleme kuyruğu | `review-queue` vaka, sosyal, CTI ve araştırma adaylarını firma sınırında gerekçeleriyle toplar. |

## I. Tedarikçi yönetimi

| Özellik adı | Tek cümlelik açıklama |
|---|---|
| Tedarikçi envanteri | Bir kuruluş domain, ilişki türü ve iş önemiyle açıkça tedarikçi olarak kaydedilebilir. |
| Tedarikçi yaşam döngüsü | Tedarikçi bilgisi güncellenebilir veya geçmiş silinmeden pasife alınabilir. |
| CNAME'den tedarikçi adayı | Kayıtlı CNAME kanıtından dış hizmet sağlayıcı adayları yerel olarak üretilebilir. |
| Tedarikçi aday incelemesi | CNAME adayı insan tarafından tedarikçi, ilgisiz veya belirsiz olarak işaretlenebilir. |
| Tedarikçi kaynak olayları | Tedarikçiyle eşleşen kayıtlı haber, ransomware ve diğer kaynak iddiaları gösterilebilir. |
| Tedarikçi risk kartı | Kanıt, eksik veri, kaynak durumu ve önerilen sonraki adım tek açıklanabilir kartta gösterilir. |
| Tedarikçi izlemesini açma | Seçilen tedarikçi için kaynak iddialarını karşılaştıran izleme etkinleştirilebilir. |
| Tedarikçi izleme geçmişi | İlk sessiz ölçüm, değişiklikler ve kaynak hataları tedarikçi kimliğiyle saklanır. |
| Tedarikçiyi kuruluş içeriğine katma | Yalnız açıkça seçilen etkin tedarikçiler kuruluş içerik ve rapor görünümüne eklenir. |
| Tedarikçi araştırma bağlamı | Tedarikçi, aday, kaynak iddiası ve insan kararının kanıt yolları ortak araştırmada görülebilir. |

## J. Vaka, runbook, rapor paketi ve takedown kaydı

| Özellik adı | Tek cümlelik açıklama |
|---|---|
| Vaka oluşturma | Analist otomatik tehdit hükmü olmadan başlık, özet ve öncelikle vaka oluşturabilir. |
| Vaka yaşam döngüsü | Vaka bilgileri ve açık, kapalı veya yeniden açılmış durumu gerekçeyle değiştirilebilir. |
| Vaka zaman çizelgesi | Not, kanıt, görev ve durum olayları tek kronolojik görünümde gösterilir. |
| Analist notu | Vakaya değişmez ve zaman damgalı analist notu eklenebilir. |
| Donmuş vaka kanıtı | Mevcut yerel bulgu veya adayın doğrulanmış o anki görüntüsü vakaya bağlanabilir. |
| Vaka kanıt ayrıntısı | Vakaya alınan tarihî kanıt sonraki kaynak değişikliklerinden etkilenmeden açılabilir. |
| Vaka kanıtını etkisizleştirme | Kanıt kaydı silinmeden etkin vaka bağından çıkarılabilir. |
| Vaka görevi | Vakaya takip görevi eklenebilir, tamamlanabilir, iptal edilebilir veya yeniden açılabilir. |
| Vaka yönetim raporu | Vakanın kaynak sınırlı yönetici özeti ağsız oluşturulabilir. |
| Savunma runbook planı | Vaka kanıt türlerine göre sürümlü ve yazmasız bir savunma adımları planı üretilebilir. |
| Runbook görevlerini uygulama | Görülmüş plan aynı vaka kanıtına bağlı, atomik ve tekrar güvenli görevlere dönüştürülebilir. |
| Runbook makbuzu | Uygulanan planın sürümü, kanıt hash'i ve ürettiği görevler ağsız doğrulanabilir. |
| Teknik vaka paketi | Donmuş vaka görünümünden teknik JSON ve kanıt CSV'si yeni özel izinli klasöre yazılabilir. |
| Yönetici HTML raporu | Aynı vaka görünümünden dış metinleri güvenli biçimde kaçıran yönetici HTML özeti oluşturulabilir. |
| İsteğe bağlı PDF raporu | Kurulu Chromium kullanılarak ağsız yönetici PDF'i oluşturulabilir. |
| Paket bütünlük manifesti | Her vaka paketindeki dosya adı, boyut ve SHA-256 değeri manifestte saklanır. |
| Vaka paketi doğrulama | Paket dosyaları değiştirilmiş veya eksikse doğrulama güvenli biçimde başarısız olur. |
| Takedown taslağı | Uygun etkin vaka kanıtından hiçbir yere gönderilmeyen kapatma talebi taslağı oluşturulabilir. |
| Takedown insan onayı | Taslak yalnız açık ve gerekçeli insan kararıyla onaylanabilir. |
| Dış başvuruyu kaydetme | İnsan tarafından dışarıda yapılan başvuru referansı motor içinde `submitted` olarak kaydedilebilir. |
| Takedown alındı kaydı | Sağlayıcının başvuruyu aldığını bildiren referans zaman çizelgesine eklenebilir. |
| Takedown sonuç kaydı | Başvuru çözüldü, reddedildi veya iptal edildi olarak insan kanıtıyla kapatılabilir. |
| Takedown olay geçmişi | Taslak, onay, başvuru ve sonuç adımlarının tamamı değiştirilemez olay zincirinde gösterilir. |

## K. İzleme, alarm, bildirim ve iş kuyrukları

| Özellik adı | Tek cümlelik açıklama |
|---|---|
| Kayıtlı genel arama | Yerel ortak arama daha sonra karşılaştırılmak üzere sürümlü kaydedilebilir. |
| Genel arama değişiklik alarmı | İlk sessiz çalışmadan sonra eklenen veya değişen eşleşmeler yerel bildirim oluşturabilir. |
| Genel arama monitörü | Kayıtlı arama kaynak toplamadan terminalde sınırlı turda tekrar çalıştırılabilir. |
| Birleşik izleme politikası | Domain, marka, IP, kelime, kişi ve tedarikçi hedefleri tek kuruluş politikasında tanımlanabilir. |
| Çoklu kayıt ailesi izleme | Politika saklı domain, bulgu, sosyal, ransomware, olay, vaka, tedarikçi, CTI, IOC, haber ve mention kayıtlarında çalışır. |
| İzleme eşik ayarı | Eklendi, değişti ve kayboldu türleri ile minimum değişiklik ve öncelik sürümlü ayarlanabilir. |
| İzleme planı | Politikanın hedef, kayıt türü, eşleşme biçimi ve kapsamı yazmadan gösterilir. |
| Zamanı gelen politikalar | `monitoring due` kayıtlı aralığa göre çalışması gereken politikaları listeler. |
| Sessiz izleme başlangıcı | Politikanın ilk tamamlanan çalışması alarm üretmeden karşılaştırma başlangıcı olur. |
| Birleşik izleme farkı | Sonraki çalışmada eklenen, değişen ve kaybolan kayıtlar hash bağlı biçimde gösterilir. |
| İzleme kapsam görünümü | Kaynakların eksik, eski veya başarısız bölümleri alarm sonucundan gizlenmez. |
| Birleşik alarm | Eşik aşılırsa kuruluş ve çalışma kimliğine bağlı alarm ortak bildirim sırasına eklenir. |
| Alarm insan geri bildirimi | Alarm faydalı, faydasız veya belirsiz olarak gerekçeyle işaretlenebilir. |
| Alarm–vaka bağlantısı | Alarmın sınırlı kanıt özeti vakaya donmuş kanıt olarak eklenebilir. |
| Birleşik izleme raporu | Politika, son çalışma, kapsam, fark, alarm ve inceleme tek raporda gösterilir. |
| İzleme kesinti kurtarma | Yarım kalan birleşik çalışma yeniden çalıştırılmadan `interrupted` yapılabilir. |
| Yerel bildirim kutusu | Bulgu, sosyal, içerik, CTI, ransomware, grup ve izleme bildirimleri ortak kutuda listelenir. |
| Bildirim kanıt ayrıntısı | Bildirimin hangi kaynak, değişiklik ve kayıt nedeniyle oluştuğu ağsız açılabilir. |
| Okundu/okunmadı yönetimi | Bildirimler insan inceleme kararından bağımsız olarak okundu veya yeniden okunmadı yapılabilir. |
| Genel arama iş kuyruğu | Pasif internet aramaları kalıcı iş olarak sıraya alınabilir ve ayrı worker ile çalıştırılabilir. |
| İş deneme geçmişi | Her işin denemeleri, kaynak sorguları, sonuçları ve hataları silinmeden gösterilir. |
| İş yeniden deneme | Yarım veya hatalı iş önceki denemeyi koruyan yeni bir denemeyle çalıştırılabilir. |
| İş kurtarma | Ölen worker'dan kalan iş otomatik ağ tekrarı olmadan kesilmiş olarak işaretlenebilir. |
| Ortak kaynak işi kuyruğu | Haber, içerik, sosyal, CTI, marka ve dark web gibi kaynak işleri ortak firma kuyruğunda yürütülebilir. |
| Kaynak işi planı | İşin kaynakları, adımları, kullanım sınırları ve tahmini kapsamı çalıştırmadan gösterilir. |
| Kaynak işi kapasitesi | Etkin kuyruk kapasitesi tamamlanmış tarihî işlerden ayrı gösterilir. |
| Kaynak işi denetimi | İş olay zinciri ve kuyruk indekslerinin bütünlüğü ağsız denetlenebilir. |
| Kaynak işi kullanım ölçümü | HTTP istek, yanıt baytı ve sağlayıcıya özgü sayaçlar kalıcı iş sonucunda gösterilir. |
| Sınırlı kaynak monitörü | `monitor` pasif kaynakları belirlenen süre ve tur sayısıyla çalıştırıp sonuçlarını saklayabilir. |

## L. Saklama, arşiv ve denetim

| Özellik adı | Tek cümlelik açıklama |
|---|---|
| Rapor günlüğü arşiv planı | Eski büyük rapor/araştırma günlüklerinin hangilerinin sıkıştırılacağı yazmadan gösterilebilir. |
| Rapor günlüğü kayıpsız arşivi | Seçilen eski günlük gövdeleri yedek sonrası sıkıştırılır ve mantıksal geçmiş korunur. |
| Arşivlenmiş günlük okuma | Sıkıştırılmış rapor ve araştırma kaydı normal ayrıntı görünümünde şeffaf açılır. |
| Günlük arşivini geri yükleme | Arşivlenmiş günlük gövdesi bütünlüğü doğrulanarak sıcak kayda geri alınabilir. |
| Kuruluş saklama politikası | Kuruluş için 7–3650 günlük yaş ve 1–1000 kayıtlık parti sınırı olan politika tanımlanabilir. |
| Saklama amacı ve dayanağı | Her politika işleme amacı ve saklama dayanağını açık metin olarak taşır. |
| Saklama planı | Hangi eski P07 izleme ve P12 telemetri gövdelerinin arşivlenebileceği aile bazında veri değiştirmeden gösterilir. |
| Yedekli kayıpsız gövde sıkıştırma | Seçilen eski izleme veya telemetri gövdeleri işlem öncesi yedek alınarak zlib ile kayıpsız sıkıştırılır. |
| Şeffaf arşiv okuma | Arşivlenmiş P07 izleme veya P12 telemetri sonucu normal kullanıcı görünümünde otomatik açılıp hash ile doğrulanır. |
| Kuruluş koruma kilidi | Bir kuruluştaki bütün yönetilen kayıtlar legal, case, investigation veya contractual hold ile korunabilir. |
| Tek kayıt koruma kilidi | Belirli izleme çalışması veya telemetri kaydı bağımsız bir koruma kilidiyle arşiv planı dışında bırakılabilir. |
| Çoklu bağımsız koruma | Aynı kayıt üzerindeki farklı koruma kilitleri ayrı ayrı kaldırılır ve biri kalırsa koruma devam eder. |
| Aktif vaka kanıtı koruması | Etkin vakaya bağlı izleme çalışması veya telemetri kaydı otomatik olarak arşiv planından çıkarılır. |
| Arşiv geri yükleme | Sıkıştırılmış gövde yeni yedek alındıktan sonra sıcak SQLite kaydına geri konabilir. |
| Saklama çalışma geçmişi | Plan, arşiv, restore, hata ve kesinti çalışmaları kimlik ve sonuçlarıyla listelenebilir. |
| Zincirli saklama audit'i | Politika, hold, arşiv, restore ve recovery yazmaları aktör, gerekçe ve önceki hash ile kaydedilir. |
| Saklama kesinti kurtarma | Yarım saklama çalışması veri işlemini tekrarlamadan açıkça `interrupted` durumuna alınabilir. |
| Saklama veri ailesi kataloğu | Motorun hangi veri ailesini güvenli biçimde arşivleyebildiği ve sınırları açıkça gösterilir. |

## M. Engine ve firma platformu bağlantı yüzeyi

| Özellik adı | Tek cümlelik açıklama |
|---|---|
| Salt okunur Engine JSON sözleşmesi | `engine` standart giriş/çıkış zarfıyla kayıt arama, ayrıntı, kaynak durumu ve bileşen kataloğunu değişiklik yapmadan sunar. |
| Kayıt kimliğiyle ayrıntı alma | Engine arama sonucundaki güvenli kayıt başvurusu aynı kanıtın yapılandırılmış ayrıntısını döndürür. |
| Firma kapsamlı Platform JSON sözleşmesi | `platform request` aynı motor yeteneklerini güvenilir firma ve workspace sınırı içinde sunar. |
| Platform işlem manifesti | `--describe` desteklenen işlem, parametre, sonuç ve yazma yetkisi sınırlarını makineye okunur biçimde açıklar. |
| Firma kapsamlı yazma çiti | Platform yazmaları beklenen workspace, revision ve tekrar anahtarı uyuşmadan uygulanmaz. |
| Firma iş kuyruğu | Uzun süren desteklenen işlemler firma kuyruğuna eklenip platform worker ile çalıştırılabilir. |
| Platform iş sonucu | Kuyruktaki işin durumu, kalıcı sonucu, hatası ve iptal bilgisi JSON üzerinden okunabilir. |
| Platform iş iptali | Başlamamış desteklenen firma işi iptal edilebilir ve tamamlanmış iş yeniden çalıştırılmaz. |
| Platform kesinti kurtarma | Kesilmiş firma işleri açık recovery ile güvenli son duruma alınabilir. |
| Platform iş kuyruğu yükseltme | Firma iş şeması çekirdek kanıtı değiştirmeden yedekli biçimde yükseltilebilir. |
| Ortak terminal/Engine/Platform mantığı | Terminal, salt okunur Engine ve firma Platform yüzeyi aynı uygulama servislerini kullanır. |
| Dış istemciye hazır sayfalama | JSON listeleri toplam sayı, devam anahtarı ve açık kapsam bilgisiyle UI veya .NET tarafından tüketilebilir. |
| Kaynak yönetişimi JSON sözleşmesi | Kaynak kataloğu, tek manifest ve çevrimdışı doğrulama yerel engine ile firma platformundan aynı sınırlı servisle okunabilir. |

## N. Sensör ve tamamlanmış sandbox telemetrisi

| Özellik adı | Tek cümlelik açıklama |
|---|---|
| Kuruluş telemetri kaynakları | Honeypot, sinkhole veya sandbox kaynağı kuruluş altında sürümlü tanımlanabilir, güncellenebilir ve geçmişiyle pasife alınabilir. |
| XTI Sensor JSONL alımı | Yetkili sensörün `xti-sensor-v1` kayıtları güvenli ve kesin alan sözleşmesiyle ağsız alınabilir. |
| Cowrie güvenli dönüştürme | Desteklenen Cowrie JSONL olayları kullanıcı adı, parola ve ham komut saklanmadan bağlantı veya dosya kanıtına indirgenebilir. |
| CAPE tamamlanmış rapor dönüştürme | Tamamlanmış CAPE `report.json` dosyasındaki izinli hash, davranış özeti ve ağ IOC'leri ham rapor ya da örnek saklanmadan alınabilir. |
| Yazmasız dosya önizleme | Telemetri dosyası boyut, biçim, kayıt sayısı, atlama nedeni ve içerik SHA-256 değeriyle veri yazmadan doğrulanabilir. |
| Hash onaylı atomik içe alma | Yalnız önizlemede görülen içerik hash'i, güncel kaynak sürümü ve tekrar anahtarı uyuştuğunda bütün kayıtlar tek işlemde alınır. |
| Tekilleştirilmiş sürümlü kanıt | Aynı kaynak kimliği ve aynı içerik kopya oluşturmaz; değişen içerik eski sürümü koruyarak yeni revision üretir. |
| Telemetri çalışma geçmişi ve kurtarma | Her içe alma sayımları ve kayıt eylemleriyle saklanır, yarım çalışma veri toplamadan açıkça kesilmiş duruma getirilebilir. |
| Telemetri insan incelemesi | Güncel kanıt ilgili, zararsız, şüpheli veya belirsiz olarak gerekçeyle işaretlenebilir ve kanıt değişince yeniden inceleme açılır. |
| Kuruluş telemetri raporu | Kaynak, çalışma, kayıt, inceleme ve eksik kapsam sayıları tek ağsız kuruluş raporunda gösterilir. |
| Ortak telemetri araması | Normalize kayıtlar ortak `search --kind telemetry` ve `record.get` ayrıntı akışında kaynaklarıyla bulunabilir. |
| Vaka telemetri kanıtı | Telemetri kaydının doğrulanmış anlık görüntüsü mevcut vaka kanıtı yaşam döngüsüne bağlanabilir. |
| Birleşik telemetri alarmı | P07 politikası ilk sessiz ölçümden sonra yeni veya değişmiş telemetri kaydını ortak inbox ve alarm akışına alabilir. |
| Telemetri Engine okumaları | Kaynak, çalışma, kayıt, inceleme ve rapor sayfaları ağsız salt-okunur Engine v1 işlemleriyle tüketilebilir. |
| Firma kapsamlı telemetri yazmaları | Kaynak yönetimi, normalize kayıt alımı, inceleme ve recovery firma Platform v1'de workspace çiti ve tekrar anahtarıyla yürür. |
| Telemetri saklama politikası | `telemetry_records` ailesi için 7–3650 günlük süre ve 1–1000 kayıtlık arşiv partisi tanımlanabilir. |
| Telemetri hold ve vaka koruması | Tek kayıt veya bütün kuruluş açık hold ile, aktif vaka kanıtı ise otomatik olarak arşiv dışında tutulur. |
| Kayıpsız ve saydam telemetri arşivi | Eski güncel/sürüm gövdeleri sıkıştırılırken `record-show`, arama, vaka ve sürüm okumaları aynı kanıtı döndürür. |
| Çok nesilli telemetri arşivi | Arşivden sonra değişen kayıt yeni revision ve ayrı geri alınabilir arşiv nesli üretir; eski nesil değiştirilmez. |
| Yedekli telemetri geri yükleme ve kapasite | Her arşiv/restore öncesi SQLite yedeği alınır; iki firma, 1.000 kayıt ve 250'lik partilerle ağsız kapasite kabulü vardır. |

---

# 2. Kodu hazır olan fakat kullanım için gereksinim bekleyen özellikler

Bu bölümdeki özelliklerin motor kodu vardır; ancak belirtilen anahtar, hesap,
izin, araç, doğrulanmış envanter veya işletim sistemi sağlanmadan canlı sonuç
üretmeleri beklenmez.

## A. Hesap, API anahtarı veya kaynak erişimi isteyenler

| Özellik adı | Beklenen gereksinim |
|---|---|
| GitHub genel kod araması | GitHub hesabı ve izinli kişisel erişim anahtarı olmadan bütün kod indeksinde arama yapılamaz. |
| GitLab genel kod araması | GitLab hesabı, anahtar ve hesap planının izin verdiği arama kapsamı gerekir. |
| Pastebin içerik izlemesi | Kullanılabilir erişim yöntemi, güncel kullanım koşulu ve ticari saklama kararı seçilmelidir. |
| Tavily firma/tedarikçi araması | Kullanıcının Tavily API anahtarı ve yeterli ücretsiz veya ücretli kredisi gerekir. |
| Tavily izleme grupları | Başarılı arama geçmişi için anahtar, günlük bütçe ve seçilmiş kuruluş/tedarikçi hedefleri gerekir. |
| Tavily grup zamanlaması ve devam | Linux zamanlayıcısı veya açık monitor ile anahtar, bütçe ve belirsiz isteği tekrarlamayan kalıcı grup çalışması gerekir. |
| Bright Data LinkedIn kanıtı | Kullanıcının Bright Data hesabı, API anahtarı ve ücretli dataset erişimi gerekir. |
| XposedOrNot domain ihlal araması | XposedOrNot API anahtarı ile hesapta doğrulanmış kuruluşa ait domain gerekir. |
| AIL canlı yeraltı kaynağı | Ayrı ve sertleştirilmiş AIL 7.x kurulumu, seçilmiş yasal forum/pazar/Tor kaynağı, metadata connector'ü ve gerçek tracker olayıyla canlı kabul gerekir. |
| Telegram kanal izlemesi | Telegram API bilgisi, kullanıcı oturumu ve açıkça seçilmiş erişilebilir kamu kanalı gerekir. |
| Discord kanal izlemesi | Bot token'ı, seçilmiş sunucu/kanal ve mesaj geçmişi ile içerik izinleri gerekir. |
| IRC canlı kanal izlemesi | Seçilmiş IRC sunucusu/kanalı ve motor çalışırken açık bağlantı gerekir. |
| Bluesky dışı genel sosyal gönderi izlemesi | Her yeni platform için yasal API veya açık sayfa erişimi ile hesap/kota kararı ayrıca gerekir. |
| Bluesky verisini ticari gösterme | Teknik ve anahtarsız erişim hazırdır; müşteri ürününde saklama, gösterme ve kullanım kapsamı hukuk/ürün incelemesi bekler. |
| Giriş gerektiren sosyal profil doğrulaması | Platform hesabı, izinli oturum yöntemi ve gizlilik/kullanım koşulu kararı gerekir. |
| ThreatCluster ticari profil kullanımı | Müşteriye sunulan ücretli kullanım için sağlayıcıdan yazılı saklama ve gösterim koşulu gerekir. |
| RIPEstat ticari kullanım | Ticari sunumda hizmet ve alttaki kayıt kaynaklarının koşulları ayrıca doğrulanmalıdır. |
| Yayıncı tam metnini ticari gösterme | Her yeni yayıncı için metin, görsel, saklama ve müşteriye gösterim hakkı ayrı incelenmelidir. |
| Mağaza verisini ticari gösterme | Apple ve Google Play sonuçlarının bölge, saklama ve ticari gösterim koşulları ayrıca onaylanmalıdır. |

## B. Yetkili hedef, sistem aracı veya işletim sistemi isteyenler

| Özellik adı | Beklenen gereksinim |
|---|---|
| theHarvester arşiv keşfi | Sabitlenmiş theHarvester kurulumu ile erişilebilir Common Crawl veya Wayback kaynağı gerekir. |
| Yönetilen Nmap TCP Connect | Nmap 7.x kurulumu, kullanıcıya ait kesin genel IP/CIDR ve açık izinli port kapsamı gerekir. |
| Nmap SYN taraması | Kesin yetkili hedefe ek olarak raw-socket çalıştırabilecek root/capability yetkisi gerekir. |
| Nmap UDP taraması | Kesin yetkili hedef, açık UDP port kapsamı, trafik bütçesi ve ayrıcalıklı çalışma gerekir. |
| Nmap servis/sürüm kanıtı | Kullanıcının seçtiği yetkili portlarda sürüm sorgusuna açık izin verilmesi gerekir. |
| Nmap işletim sistemi tespiti | Yetkili hedef ve ayrıcalıklı Nmap çalıştırma izni gerekir. |
| Seçili Nmap NSE kontrolleri | Yalnız katalogdaki `banner`, `ssl-cert`, `ssh-hostkey` veya açıkça izinli SMB kontrolü seçilebilir. |
| Nmap hedef ve plan yönetimi | Kesin genel IP/CIDR, hedef sınırı, port, hız ve toplam probe bütçesi önceden kaydedilmelidir. |
| Platform Nmap worker | Firma alanında onaylanmış hedef, donmuş plan ve Nmap kurulu Linux/Unix worker gerekir. |
| Linux systemd zamanlama | Gerçek Linux, systemd kullanıcı hizmeti ve hazırlık/yedek kontrolünden geçmiş kayıtlı profil gerekir. |
| Webhook HTTPS teslimi | HTTPS/443 alıcı adresi, özel imza anahtarı ve alıcının erişilebilir olması gerekir. |
| Webhook hedef yönetimi | Alıcı adresi ile özel imza anahtarı tanımlanmalı ve anahtar değişiminde hedef sürümü güncellenmelidir. |
| İmzalı webhook kuyruğu | Gönderilecek yerel bildirim seçilip değişmez gövde olarak hedef kuyruğuna açıkça eklenmelidir. |
| Webhook teslim geçmişi ve tekrar | Gerçek alıcının yanıtı gerekir ve başarısız teslim yalnız açık `deliver` işlemiyle yeniden denenir. |
| PDF rapor üretimi | Normal marka kurulumu içindeki uyumlu Playwright ve Chromium kurulumu gerekir. |
| Statik sayfa ekran görüntüsü | Playwright/Chromium kurulumu ve giriş gerektirmeyen, güvenli HTTPS üzerinden erişilebilir sayfa gerekir. |
| Gerçek VIP/yönetici takibi | İzlenecek kişinin adı, rolü, meşru hesapları ve kurum tarafından onaylanmış kapsamı gerekir. |
| Gerçek Cowrie canlı kabulü | Ayrı, yetkili ve kısıtlı Cowrie kurulumu ile gerçek JSONL dosyasının güvenli aktarım ve hata senaryoları doğrulanmalıdır. |
| Gerçek CAPE canlı kabulü | Üretim ağından ayrılmış CAPE ortamı, güvenli örnek prosedürü ve gerçek tamamlanmış `report.json` ile kabul yapılmalıdır. |
| Linux P01–P12 teslim kabulü | Mevcut yerel kodun push edilip gerçek Linux CI, kurulum ve yükseltme çalışmalarıyla doğrulanması gerekir. |

## C. Doğrulanmış ürün veya paket envanteri isteyen eski zafiyet yetenekleri

Bu araçlar kodda ve testlerde korunur ancak kullanıcı kararıyla aktif yeni
geliştirme planının dışındadır; yalnız domain adına bakarak ürün, sürüm veya
zafiyet uydurmazlar.

| Özellik adı | Beklenen gereksinim |
|---|---|
| CISA KEV kataloğu | Resmî kataloğun internetten yenilenmesi ve ilgili CVE kaydının mevcut olması gerekir. |
| FIRST EPSS kataloğu | Güncel resmî EPSS dosyasının alınması ve ilgili CVE'nin listede bulunması gerekir. |
| Zafiyet kaynak uygunluğu | Resmî kaynakların sürüm, lisans, kapsam ve kabul durumu incelenmiş olmalıdır. |
| Zafiyet katalog durumu | İlgili kaynağın daha önce başarıyla yenilenmiş yerel katalog ve çalışma geçmişi bulunmalıdır. |
| NVD tek CVE bağlamı | Açıkça seçilmiş CVE için NVD kaydının başarıyla alınması gerekir. |
| Birleşik zafiyet görünümü | Yerel NVD, KEV ve EPSS kaynaklarından en az birinde geçerli kayıt gerekir. |
| NVD zenginleştirme planı | Yerel katalogda NVD ayrıntısı eksik olan seçilmiş CVE kayıtları gerekir. |
| NVD tarih pencereleri | Tarih aralığı, sayfa bütçesi ve resmî NVD API erişimi gerekir. |
| NVD kapsama boşluğu planı | Önceden kaydedilmiş pencere ve eksik gün aralığı bulunması gerekir. |
| NVD pencere ilerleme ve restart | Kayıtlı kısmi pencere ile insanın gerekçeli yeniden başlatma kararı gerekir. |
| Maruziyet odaklı NVD yenileme | Etkin maruziyetle bağlantılı eski yerel NVD kayıtları bulunması gerekir. |
| Doğrulanmış ürün envanteri | Kullanıcının varlığa üretici, ürün ve mümkünse sürüm kanıtı eklemesi gerekir. |
| NVD CPE uygulanabilirliği | NVD kaydında kullanılabilir CPE koşulu ve doğrulanmış ürün bilgisi gerekir. |
| Ürün–CVE değerlendirmesi | Etkin doğrulanmış ürün kaydı ile ilgili NVD CVE kaydının birlikte bulunması gerekir. |
| Varlık zafiyet özeti | Doğrulanmış ürün koşulu ve mevcut KEV, EPSS veya CVSS kaynaklarından biri gerekir. |
| Bütün ürünleri CVE ile eşleştirme | Etkin doğrulanmış ürün envanteri ve seçilmiş yerel NVD kaydı gerekir. |
| OSV duyuru önizlemesi | Açıkça seçilmiş CVE için OSV'de geçerli paket veya duyuru bağı gerekir. |
| Ubuntu CVE önizlemesi | Canonical Ubuntu OSV kaynağında ilgili CVE ve paket/yayın kaydı gerekir. |
| Ubuntu paket envanteri | Kullanıcının varlığa yayın, binary paket, source paket ve sürüm kanıtı eklemesi gerekir. |
| Ubuntu paket–CVE karşılaştırması | Doğrulanmış Ubuntu paket kaydı ile Canonical'ın ilgili kaydı birlikte bulunmalıdır. |
| Ubuntu envanter taraması | Etkin Ubuntu paket kayıtları ve tek CVE için güncel Canonical yanıtı gerekir. |
| Ubuntu kanıtı ekleme ve güncellik kontrolü | Tek ve kesin affected paket bağı ile güncel Canonical sonucu gerekir. |
| Ubuntu kanıt planı ve toplu kontrol | Etkin Ubuntu kanıtı ile son envanterden farklı paket durumu bulunması gerekir. |
| RPM paket envanteri | Kullanıcının varlığa dağıtım bağlamı, paket adı, sürüm ve mimari kanıtı eklemesi gerekir. |
| Red Hat CSAF VEX önizlemesi | Geçerli Red Hat CSAF belgesi ve kullanılabilir ürün kimliği gerekir. |
| Kesin RPM/VEX eşleştirmesi | Doğrulanmış RPM kaydı ile aynı paketi gösteren kesin VEX product ID gerekir. |
| SUSE üretici VEX bağlamı | İlgili CVE için geçerli SUSE CSAF/VEX kaynağı gerekir. |
| Üretici paket kanıtı yaşam döngüsü | Geçerli VEX bağı eklendikten sonra listeleme, ayrıntı, güncellik kontrolü ve gerekçeli geri çekme kullanılabilir. |
| İnsan incelemeli maruziyet kaydı | Ürün–CVE çiftinin yerel koşullarda gerçek inceleme adayı olması gerekir. |
| Maruziyet inceleme kuyruğu | Açık maruziyet kayıtları ile KEV, EPSS ve CVSS bağlamı bulunması gerekir. |
| Maruziyet insan kararı | Açılmış maruziyet kaydı ve analistin kanıtlı affected, not_affected veya belirsiz kararı gerekir. |
| Maruziyet destek kanıtı | Mevcut maruziyet kaydı ve insanın seçtiği kaynaklı kanıt gerekir. |
| Maruziyet kanıtı yaşam döngüsü | Eklenen destek kanıtı listelenebilir, ayrıntısıyla açılabilir ve geçmişi silinmeden geri çekilebilir. |
| Maruziyet bastırma | Açık maruziyet ve belirli bitiş zamanı olan gerekçeli bastırma kararı gerekir. |
| Düzeltme planı ve yeniden kontrol | Açık maruziyet, insan onaylı plan ve uygulama sonrası yeni kanıt gerekir. |
| Düzeltme yaşam döngüsü | Planlanmış düzeltme uygulanabilir, yeniden kontrol edilebilir, iptal edilebilir ve geçmişiyle gösterilebilir. |
| Toplu yeniden değerlendirme | Ürün veya NVD kanıtı değişmiş etkin maruziyet kayıtları gerekir. |
| Yeniden değerlendirme denetim kaydı | Çalıştırılmış toplu planın değişmez sonuç ve kayıt geçmişi bulunması gerekir. |
| Zafiyet değişiklik bildirimi | Önceki değerlendirmeden farklı doğrulanmış ürün/NVD kanıtı gerekir. |

---

# 3. Beklemede, ertelenmiş veya henüz platformda bulunmayan özellikler

Bu bölümdeki maddeler bugün kullanılabilen özellik değildir; yol haritasında
veya kullanıcı kararlarında görünür tutuldukları için burada ayrıca listelenir.

| Özellik adı | Tek cümlelik durum açıklaması |
|---|---|
| Web yönetim paneli | React veya başka bir web arayüzü henüz bu motor reposunda bulunmaz. |
| Rol bazlı SOC/CISO/yönetim ekranları | Motor verisi hazır olsa da rol bazlı dashboard tüketici platform tarafından yapılacaktır. |
| Özelleştirilebilir widget paneli | Kullanıcının sürükleyip düzenleyebileceği dashboard bileşenleri henüz yoktur. |
| Tema ve web erişilebilirliği | Karanlık/aydınlık tema ile web erişilebilirlik kabulü UI geliştirmesine bırakılmıştır. |
| REST veya GraphQL sunucusu | Motorun JSON sözleşmesi vardır ancak doğrudan HTTP API sunucusu bilinçli olarak ertelenmiştir. |
| .NET oturum ve kullanıcı yönetimi | Giriş, oturum, kullanıcı ve rol yönetimi motoru kullanacak .NET platform ekibine aittir. |
| PostgreSQL uygulama veritabanı | Motor bugün SQLite kullanır ve gelecekteki .NET/PostgreSQL bağlantısı ayrı tasarlanacaktır. |
| Tam RBAC ve ince yetkilendirme | Firma sınırı vardır ancak kullanıcı/rol bazlı işlem yetkileri henüz motor içinde yoktur. |
| SSO ve SCIM | Kurumsal kimlik sağlayıcısı ve kullanıcı eşitlemesi tüketici platform kapsamındadır. |
| Platform geneli okuma audit'i | P08 yazma audit'i vardır ancak kimin hangi kaydı görüntülediği henüz genel olarak kaydedilmez. |
| Güvenilir oturumdan actor üretimi | P08 aktör alanı hazırdır ancak gerçek kullanıcı kimliğini .NET backend sağlamalıdır. |
| E-posta bildirimi | E-posta alıcısı, şablon, teslim ve hata takibi henüz eklenmemiştir. |
| SMS bildirimi | SMS sağlayıcısı, maliyet ve teslim kaydı seçilmediği için özellik yoktur. |
| Slack veya Teams bildirimi | Kanal aboneliği ve teslim yaşam döngüsü henüz uygulanmamıştır. |
| Mobil push bildirimi | Mobil uygulama ve push sağlayıcısı bulunmadığı için özellik yoktur. |
| Gerçek zamanlı Kafka/Redpanda akışı | Sistem bugün kuyruklu ve periyodik çalışır, genel streaming altyapısı kurulmamıştır. |
| OpenSearch/Elasticsearch veri gölü | Kişisel motor SQLite kullanır ve büyük ölçekli arama kümesi henüz eklenmemiştir. |
| Petabyte ölçekli depolama | Ölçülmüş böyle bir iş yükü ve veri gölü mimarisi henüz yoktur. |
| Çoklu bölge bulut | Bölgesel çoğaltma, felaket kurtarma ve gecikme hedefleri henüz tasarlanmamıştır. |
| Müşteriye on-prem kurulum ürünü | İlk ticari kullanım kendi sunucularımızda planlandığı için müşteri dağıtım paketi beklemededir. |
| Tam air-gapped dağıtım | Çevrimdışı kullanım parçaları vardır ancak bağımlılık ve güncelleme dahil tam kapalı ağ paketi yoktur. |
| Haricî soğuk depo | P08 sıkıştırmayı SQLite içinde yapar, S3/Blob veya başka object storage bağlantısı yoktur. |
| Bütün veri aileleri için retention | P08 bugün P07 izleme ve P12 telemetri gövdelerini yönetir; diğer veri aileleri ayrı koruma/restore/kapasite kabulü bekler. |
| Otomatik mantıksal veri silme | Saklama süresi dolunca otomatik silme güvenlik ve hukuk kararı alınana kadar kapalıdır. |
| Otomatik VACUUM | Fiziksel SQLite küçültme kesinti ve yedek politikası belirlenmeden çalıştırılmaz. |
| Veri yerleşimi politikası | Verinin hangi ülkede veya bölgede tutulacağını zorlayan platform politikası henüz yoktur. |
| GDPR/KVKK/CCPA uygunluk kararı | Teknik amaç ve saklama alanları vardır ancak hukuk onayı olmadan uygunluk iddiası yapılmaz. |
| Tam STIX/TAXII 2.1 hizmeti | Sınırlı STIX IOC çıktısı vardır ancak genel nesne alışverişi ve TAXII sunucusu ertelenmiştir. |
| Tam MISP olay eşitlemesi | Warninglist ve IOC dosyaları vardır ancak çift yönlü MISP event senkronizasyonu yoktur. |
| Splunk/Sentinel/QRadar bağlayıcıları | SIEM bağlayıcıları kullanıcı kararıyla P06 kapsamından çıkarılmıştır. |
| SOAR/XSOAR playbook tetikleme | Haricî SOAR yürütmesi ve geri dönüş kaydı henüz yoktur. |
| Jira/ServiceNow eşitlemesi | Vaka ile ticket kimliği ve kapanış durumunu çift yönlü eşitleyen bağlayıcı yoktur. |
| EDR veya firewall otomatik engelleme | Otomatik block işlemi mevcut güvenli OSINT motor hedefinin dışındadır. |
| Otomatik takedown gönderimi | Motor yalnız taslak ve insanın dış başvuru kaydını tutar, sağlayıcıya kendisi göndermez. |
| LLM destekli özetleme | Yerel veya ücretli model, veri gönderimi ve kanıt doğruluğu kararı verilmediği için LLM yoktur. |
| Doğal dil intel copilot | Kanıta bağlı sohbet sorgusu ve izin modeli LLM/UI paketiyle birlikte beklemektedir. |
| Otomatik çok dilli çeviri | Özgün metni ve çeviri sürümünü güvenli koruyan çeviri katmanı henüz yoktur. |
| AI ile yanlış alarm azaltma | İnsan geri bildirimi saklanır ancak model otomatik öğrenip alarm kararını değiştirmez. |
| AI açıklanabilirlik katmanı | Gelecek model çıktıları için kaynak ve gerekçe zorunluluğu planlıdır ancak model kullanılmamaktadır. |
| Geniş genel Tor/forum/pazar crawler | AIL için güvenli metadata bağlantısı hazırdır; fakat kaynak, yasal kapsam, izolasyon ve saklama hakkı seçilmeden geniş/kendiliğinden crawler üretimde açılmayacaktır. |
| Stealer-log sağlayıcısı | Credential kaynağı, veri minimizasyonu, bütçe ve yasal amaç seçilmediği için yoktur. |
| Bütün sosyal medya gönderilerini tarama | Platform API erişimleri ve ticari koşullar olmadan genel sosyal akış izleme yoktur. |
| Bütün interneti tarama | Motor seçilmiş kaynak ve yetkili hedeflerle sınırlıdır, küresel internet crawler değildir. |
| Dinamik/giriş yapılmış sayfa görüntüsü | P03 yalnız JavaScript kapalı statik görünüm alır ve oturum açılmış sayfayı yakalamaz. |
| Bütün uygulama mağazalarını kapsama | Seçili Apple/Google bölge araması vardır ancak tüm mağaza ve ülkeler kapsanmaz. |
| APK/IPA indirme ve analiz | Marka koruması çalıştırılabilir mobil paket indirmez veya zararlı analiz etmez. |
| Phishing kit indirme/çalıştırma | Sayfa işaretleri karşılaştırılır ancak kit yazılımı indirilmez veya yürütülmez. |
| Honeypot ve sinkhole ağı | XTI güvenli normalize sensör sonucunu alabilir; sensörleri internete açan, yöneten ve ham telemetriyi taşıyan gerçek ağ henüz kurulmamıştır. |
| Malware sandbox işletimi | XTI tamamlanmış CAPE sonucunu güvenli alabilir; zararlı örneği yalıtılmış ortamda çalıştırma bilinçli olarak ayrı CAPE altyapısının görevidir ve henüz canlı doğrulanmamıştır. |
| Cloud yanlış yapılandırma taraması | S3, Blob, container veya registry envanteri ve yanlış yapılandırma kontrolü henüz yoktur. |
| SBOM bağımlılık analizi | Genel CycloneDX/SPDX alma ve bağımlılık zafiyet akışı aktif değildir. |
| OT/ICS/IoT cihaz istihbaratı | Özel cihaz veri kaynağı ve cihaz sınıflandırması henüz yoktur. |
| Kripto cüzdan/ransomware ödeme takibi | Blockchain veri kaynağı ve işlem ilişkilendirme motoru henüz yoktur. |
| Deepfake ses/video tespiti | Uzman medya modeli ve etiketli doğruluk kabulü bulunmadığı için özellik yoktur. |
| Otomatik pentest veya exploit | Genel saldırı ve istismar otomasyonu bilinçli olarak ürün kapsamı dışındadır. |
| Otomatik yama yükleme | Motor varlık üzerinde yazılım değiştirmez veya yama kurmaz. |
| Coğrafi tehdit haritası | Kaynak iddiası verisi kısmen vardır ancak doğrulanmış konum kaynağı ve harita UI'si yoktur. |
| Etkileşimli ilişki grafiği | Motor sınırlı graf verisi verir ancak görsel web gezgini tüketici platformda yapılacaktır. |
| Çoklu para birimi ve faturalama | Ticari abonelik, fatura ve para birimi motor kapsamı dışında platform işidir. |
| White-label MSSP yönetimi | Firma izolasyonu vardır ancak marka özelleştirmesi ve MSSP müşteri yönetim ekranı yoktur. |
| Firecrawl entegrasyonu | Firecrawl değerlendirilmiş ancak kullanıcı kararıyla şimdilik platforma bağlanmamıştır. |
| HIBP verified-domain sorgusu | Yeni credential çalışmalarında HIBP kapalıdır ve seçilen kaynak XposedOrNot'tur. |
| Genel Exploit-DB entegrasyonu | Exploit-DB kaynağı mevcut aktif zafiyet kapsamına eklenmemiştir. |

---

## Kapsam doğrulama özeti

- Aktif liste; `init` ile `webhook` arasındaki 71 ana terminal ailesinin
  bugün çalışan yerel, kaynaklı veya normal kurulumla kullanılabilir
  yeteneklerini kapsar.
- Gereksinim bekleyen liste; kodu hazır olduğu halde anahtar, hesap, yetkili
  hedef, sistem aracı, Linux veya doğrulanmış ürün/paket bilgisi isteyen
  yolları kapsar.
- Beklemede listesi; 76 maddelik ana yol haritasındaki henüz teslim edilmemiş,
  bilinçli ertelenmiş veya ürün hedefi dışında bırakılmış başlıkları kapsar.
- Ayrıntılı çalışma durumu [STATUS](STATUS.md), açık koşullar [NOTES](../NOTES.md)
  ve geliştirme sırası [MASTER_ROADMAP](roadmap/MASTER_ROADMAP.md) içinde
  tutulur.

<!-- verified-cli-families: init doctor evaluate feedback analyze collect code content profiles schedule changes notices collections organizations search research investigate reports observations journals groups sightings relationships identity review-queue research-history source-jobs warninglists enrich search-watch news mentions engine platform components events darkweb action monitoring retention brand ransomware vuln status monitor migrate assets cases suppliers products ioc cti packages ubuntu-packages allowlist surface backup restore import scan watch jobs worker sources findings triage report storage inbox webhook -->
