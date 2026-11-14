# Yerel Uygulamanın Mimarisi

**14 Kasım 2026 — 0.135.0, şema 61 ana proje yapısı.**
Uzun vadeli hedefler [ana roadmap](roadmap/MASTER_ROADMAP.md) içindedir.

Uygulama tek projedir; görevleri ayrı bölümlerdedir. İnternet araması, yerel kayıt, eşleştirme, hedef kontrolü, inceleme, bildirim kutusu, durum özeti, sınırlı izleme denemesi ve rapor ortak modelleri ve küçük sözleşmeleri kullanır.

`OrganizationScope`, etkin açık kullanıcı bağlantısını ortak domain modeli
olarak taşır. Kuruluş birleşik raporu, kuruluş katkı görünümü ve dönem
raporu ayrı küçük okuma portları üzerinden kendi içinde tek SQLite okuma
kesiti kullanır. Tazelik ve katkı okumalarının bağlantı alan yardımcıları
mevcut dış arayüzleri değiştirmez. Vaka bağlantısı tam kanıt ve yaşam döngüsü
üzerinden doğrulanır; rapora yalnız kimlik/durum/ilgili bağ yansıtılır.
`CtiContextService` tam gösterge/varlık kimliğinden doğrudan ilişkileri,
güncel iddia ile olay geçmişini karşılaştırarak gösterir. Kaynak iddiaları
ve bağımsız geçerlilik durumları korunur; dolaylı atıf yapılmaz.
[0135 kararı](decisions/0135-composed-organization-evidence.md).

`PublicNoticeService`, küçük kaynak/depo portlarını kullanır; HTTP adaptörü
yalnız sabit HIBP kamu katalog yolunu çağırır. CLI yenilemede ortak kilidi
alır; depo ağ öncesi doğrulanır. Şema 60 çalışma ve kompakt fark tabloları
ekler. Son başarılı katalog doğrulanan geçmişten oluşturulur; hata önceki
kataloğu silmez. Kuruluş/dönem raporu aynı bağlantıdan tam domain eşleşmeleri
okur; kaynak sınıfları/atıf/lisans kaybolmaz. Readiness genel katalog
durumunu, domain eşleşme sayısından ayırır. Harici kütüphane gerekmez.
[0136 kararı](decisions/0136-public-breach-metadata.md).

0.135.0, HIBP'yi açık `notices-hibp` toplama birimi yapar. Kaynak servisi/depo
portu isteğe bağlı `CollectionOperationToken` taşır; kaynak run/farkları ile
sonuç makbuzu aynı SQLite transaction'da yazılır. Şema 61, kaynak türü ve
doğrudan `public_notice_runs` yabancı anahtarını mevcut toplama tablolarına
ekler. Eski şema 56–60 tanımları ayrı doğrulanır; yedekli yeniden kurma eski
alanları, rowid'leri ve kaynak bağlarını korur. Eski profil/plan sürümü ve
özetleri değişmez. Ortak katalog kapsamı ile domain analizi ayrıdır; yeniden
deneme yalnız eksik birimleri yürütür. [0137 kararı](decisions/0137-public-notice-collection.md).

`SchedulingService`, profil/plan, ortak kilit, kurtarma, dosya üretimi ve
yedek portlarını birleştirir. `SystemdScheduleWriter` yalnız yeni dosya
üretir; etkinleştirmez. Sabit `/bin/sh` mevcut başlatıcıyı ayrı argv ile
çağırır; üretilmiş shell ifadesi yoktur. Yedek adaptörü ayrı yönetilen
havuzda UUID/boyut/özet ve oluşturuluyor/tutuluyor/emekli durumlarıyla kesinti
kurtarması yapar. Geri yükleme doğrulanmadan ve manifest/dizin kalıcı
yazılmadan eski yedek silinmez. Şema değişmez. [0134 kararı](decisions/0134-linux-scheduling-and-owned-backups.md).

Kuruluş/rapor/katalog/kaynak katkısı/bildirim sınırları
[0133 kararında](decisions/0133-evidence-preserving-personal-workflow.md) açıklanır.

`OrganizationService`, açık kullanıcı gruplamasını küçük kuruluş deposu ve
ortak yürütme kilidiyle yönetir. Şema 57 kuruluş/bağlantı durumunu ve tam
revizyon geçmişini tutar; domain/watch hedefleri gerçek yabancı anahtarlardır.
Yazma anında hedef ve geçmiş aynı işlemde denetlenir. Kuruluş ilişkisi kaynak
verisini kopyalamaz, sahiplik veya toplama kapsamı çıkarmaz; hedef geri
çekildiğinde bağlantı geçmişi okunabilir kalır.

`PeriodicChangesService`, 1/7 günlük UTC penceresini bir kez belirler.
`SQLitePeriodicChangesRepository` bütün aileleri tek salt okunur transaction
ile okur; yerel kayıt zamanı ile kaynak gözlem zamanı ayrı tutulur. Başlangıç,
değişim ve hata satırları ayrı sayılır. Domain filtresi marka, dış yüzey ve
kamu olaylarını kapsar; kuruluş filtresi güncel etkin açık üyeliği kullanır.
Kaydedilmiş kontrol değerleri son başarılı ölçümle karşılaştırılır; hatalar
boş değer değişimi sayılmaz. Yeni rapor tablosu veya ağ çağrısı
bulunmaz. Tarihî sorgu/ad eksikse güncel tanımdan tahmin edilmez.

`SourceContributionService`, açık provider ve gerçek iş/aday kanıtlarından
tekil domain kümeleri ile kayıtlı deneme oranlarını hesaplar. SQLite portu
tek salt okunur kesit verir; marka adaylarında tek hedef + kural + typos
sınırı korunur. Serbest kaynak metninden sağlayıcı atfı yapılmaz; çok hedefli
ve sonuçsuz denemeler görünür biçimde ayrılır. Gösterim sayfalaması toplamları
etkilemez. Bu karşılaştırma yeni domain keşif sağlayıcısı seçmez; ölçüm ve
[karar notu](roadmap/SOURCE_PROVIDER_EVALUATION.md) ekler.

`AttackCatalogService` yerel kimlikli ATT&CK kataloğunu okur. Resmî yanıt tek
kez alınır/ayrıştırılır; ek katalog ile eski CTI kaynak iddiaları aynı SQLite
transaction içinde güncellenir. Şema 58 kanonik STIX/dış kimlik, kaynak metni,
ilişkiler, alan kaynaklı teknik–taktik üyelikleri ve denetlenebilir değişim
geçmişi tutar. Aynı adlı teknikler ayrıdır; eski CTI satırları yeniden
biçimlendirilmez. Ayrıntıda eski CTI bağı verilecekse o kanıt da aynı okuma
kesitinde doğrulanır. Görünüm servisleri ağ veya somut depoya bağımlı değildir.

Şema 59 `ransomlook_watch_notifications` tablosunu ekler. RansomLook çalışma,
sonuç öğeleri, bildirimi ve varsa toplama receipt'i aynı transaction'dadır.
İlk ölçüm sessizdir; sonraki `added + updated > 0` tek çalışma bildirimi verir.
Kaynak kimliği ThreatCluster'dan ayrı kalır; iki kaynak ortak kutunun sırasını
paylaşır. Aynı çalışmanın tekrarı veya yalnız çıkarılma bildirim oluşturmaz;
geçmiş çalışmalara geriye dönük bildirim eklenmez.

`CollectionHistoryService`, mevcut toplama servislerini kaynak birimleriyle
yürütür. Şema 56 oturum, adım ve gerçek kaynak sonucuna bağlı completion
receipt tutar. İsteğe bağlı işlem kimliği küçük kaynak sözleşmelerinden
geçer; SQLite yardımcı yordamı kaynak sonucu ile receipt'i aynı transaction'da
yazar. Toplama scan işi sahipliği enqueue sırasında bağlanır. Genel kuyruk
bu işleri sahiplenmez; oturum kurtarması tamamlanan receipt'leri korur.
Yeni devam yürütmesi yalnız eksik üyeleri ve gereken taze ransomware
yenilemesini çalıştırır. Final analiz günceldir; tarihî çıktı diye sunulmaz.
[0132 kararı](decisions/0132-durable-collection-sessions.md) ayrıntıları açıklar.

`CollectionProfileService`, küçük depo/kilit sözleşmeleri ve seçili toplama
servisi fabrikası üzerinden adlandırılmış tanımları yönetir. Şema 55 güncel
profil ve değiştirilemez tam tanım olaylarını ekler; sürüm/özet ve yaşam
döngüsü denetlenir. Kaydetmede/çalıştırmada ağ öncesi plan doğrulanır; çalışma
kilidi altında profil tekrar okunur. Eski profil geçmişi, bağlı izleme artık
etkin değil diye silinmez. Profil, sahiplik ilişkisi veya çalışma oturumu
yerine geçmez. [0130 kararı](decisions/0130-versioned-collection-profiles.md)
ayrıntıları açıklar.

`CollectionService`, seçilen mevcut `JobService`, `SurfaceDiscoveryService`
ve `CtiFeedService` işlemlerini tek çalışma kilidi altında seri yürütür.
Kaynak sonuçları kendi depolarında saklanır; son `UnifiedAnalysisService`
görünümü bu kayıtlardan okunur. Donmuş plan/adım/sonuç modelleri terminal ve
JSON tarafından kullanılır. Servis CLI, HTTP veya SQLite import etmez;
ilerideki React/API katmanı aynı işlevi çağırabilir. Genel workflow motoru
yoktur; CLI, 0.132.0'dan itibaren kalıcı oturum ve açık devam için bu çekirdeği
`CollectionHistoryService` ile kullanır. Kendiliğinden tekrar başlatma yapılmaz.
Ayrıntılar [0127 numaralı karardadır](decisions/0127-explicit-passive-collection.md).

0.130.0, `CollectionWatchService` üzerinden açık kimlikle seçilen sosyal ve
ransomware izlemelerini aynı kilit altında bu akışa ekler. Plan, kayıtlı
kaynak/tanım/platformları taşır; domainle ilişki çıkarmaz. Bütün seçili
depolar ağ öncesi ve kilit altında doğrulanır. Her ransomware sağlayıcısı
bir kez yenilenir, seçilen izlemeler tam yenileme kimliğine bağlanır;
yenileme hatasında eski snapshot üzerinde yeni izleme çalışması yazılmaz.
RansomLook `run` servisi bu amaçla isteğe bağlı beklenen kaynak kimliğini
yazmadan önce doğrular. İlk ölçüm/değişim ve mevcut insan karar zinciri
korunur. İzleme raporları `CollectionStep` içinde kendi tür/kimlikleriyle
taşınır; `UnifiedAnalysisReport` domain kapsamını korur. Şema ve dış kaynak
bağımlılığı değişmez. Ayrıntılar [0129 numaralı karardadır](decisions/0129-explicit-collection-watches.md).

`SourceReadinessService`, küçük `SourceReadinessRepository` sözleşmesinden
yerel kurulum ve kayıt geçmişini alır. SQLite/kurulum adaptörü mevcut kayıt
doğrulamalarını kullanır; servis tek saat üzerinden kayıt yaşını ve beklemeyi
hesaplar. Terminal kısa tablo ve isteğe bağlı ayrıntı, JSON tam rapor üretir.
Domain filtresi tarama/keşfe uygulanır. Son kayıt bütün varlıkların durumuna
genellenmez; ATT&CK'de tutulmayan başarısız senkron geçmişi bilinmiyor kalır.
Komut kaynak istemcilerini çalıştırmaz, depolama oluşturmaz veya değiştirmez.

Aktif ürün yönü savunmacı OSINT/dijital risk izlemedir. Ürün, sürüm, paket ve CVE modülleri geçmiş veri ve şema uyumluluğu için kod tabanında korunur; `analyze` bileşimine ve yeni teslim sırasına dahil edilmez. Bu ayrım veri silmez ve eski komutların sonuçlarını yeni dış risk kanıtı gibi sunmaz.

**Planlanan, henüz uygulanmamış LLM sınırı:** İsteğe bağlı analiz servisi mevcut uygulama servislerinden kapsamı sınırlı kanıtları okuyacak; küçük bir model sözleşmesi üzerinden değiştirilebilir yerel/harici sağlayıcı adaptörünü çağıracaktır. Domain kuralları model kütüphanesine bağlı olmayacak. İlk sürümün kanıt, insan kararı veya dış eylem üzerinde yazma yetkisi olmayacak; taslak model çıktısı kanıttan ayrı, kaynak kimlikleri ve model/prompt sürümüyle gösterilecek. LLM hatası mevcut toplama/inceleme akışını durdurmayacak. Bu sınır aşağıdaki uygulanmış yapı diyagramına dahil değildir; ayrıntılar [LLM planındadır](roadmap/LLM_PLAN.md).

```text
Terminal → Uygulama servisi
              ├─ Alan adı kuralları ← sürümlü Unicode/IDNA profili
              ├─ Kalite değerlendirmesi ← SHA-256 sabitli sentetik veri kümesi
              ├─ İnceleme geri bildirimi ← salt okunur SQLite anlık görüntüsü
              ├─ Kayıt sözleşmesi ← SQLite adaptörü
              ├─ Kaynak sözleşmesi ← crt.sh / theHarvester P0 / urlscan adaptörleri
              ├─ Kaynak kataloğu ← sabit amaç / erişim / maliyet / hedef trafik sınırları
              ├─ Marka aracı kabul kapısı ← sürümlü/ağsız Maigret-Sherlock ve kapsam dışı araç kararı
              ├─ İkinci sosyal kaynak kapsam kapısı ← sabit katalog özetleri / PSL kayıt kökü / ağsız Sherlock katkı ölçümü
              ├─ Sosyal kullanıcı adı önizlemesi ← sabit commit'li Maigret ve Sherlock / geçici seçili-site veritabanları / yazmasız NDJSON
              ├─ Sosyal kullanıcı adı izlemesi ← değiştirilemez Maigret/Sherlock kaynak kimliği / ayrı SQLite başlangıç ve fark zinciri
              ├─ Sosyal toplu yürütme ← etkin izlemeler / kararlı sıra / taşmada ağ öncesi ret / ortak kilit
              ├─ Sosyal ön plan izleme ← tek tanım / monoton süre / sınırlı tur-aralık / tamamlanan kanıtı koruma
              ├─ Sosyal profil insan kararı ← tam tanım+platform+profil durumu / dondurulmuş kanıt / eklemeli zincir
              ├─ Sosyal profil bildirimi ← yalnız olası taklit insan kararı / tekilleştirilmiş ortak kutu / açık okundu
              ├─ Ransomware iddia akışı ← ThreatCluster açık HTTPS / yazmasız arama / SQLite tam-snapshot fark geçmişi
              ├─ Hedef kontrol sözleşmesi ← Sınırlı DNS / HTTPS HEAD adaptörü
              ├─ Kontrol kaydı sözleşmesi ← SQLite / tutarlı rapor okuması
              ├─ Bekleme / bakım sözleşmeleri ← SQLite / sınırlı, yedekli temizlik
              ├─ Bildirim kutusu sözleşmesi ← SQLite / bulgu, aday, kanıt değişimi / açık okundu
              ├─ Tam adres istisnası sözleşmesi ← SQLite / süreli politika ve işlem geçmişi
              ├─ Dış yüzey sözleşmesi ← SQLite / onay kapsamı, DNS/TLS temel ve değişim kanıtı
              ├─ Yüzey ilişki görünümü ← tek SQLite snapshot / salt okunur kanıt izdüşümü
              ├─ Maruziyet aday görünümü ← son kanıt / açıklanabilir kurallar / salt okunur
              ├─ E-posta DNS sözleşmesi ← Google DNS / SQLite MX-SPF-DMARC temel ve değişim kanıtı
              ├─ CNAME DNS sözleşmesi ← Google DNS / onaylı tam adres / SQLite hedef kanıtı
              ├─ Tedarikçi adayı ← son kayıtlı CNAME / sürümlü PSL kayıt kökü / geri alınabilir insan kararı
              ├─ teknoloji ipucu sözleşmesi ← son servis kanıtı / ürün-sürüm iddiası yok
              ├─ Zafiyet kataloğu sözleşmeleri ← CISA KEV + FIRST EPSS + NVD/CVSS
              ├─ Üretici kaynak kapısı ← sürümlü ölçütler / resmî kanıt bağlantıları / ağsız seçim
              ├─ Ubuntu OSV önizlemesi ← sabit Canonical tek-kayıt yolu / ortak katı OSV ayrıştırması
              ├─ Ubuntu paket karşılaştırması ← açık yayın+kaynak paket+sürüm / Debian Policy sıralaması / yazmasız aday
              ├─ Ubuntu paket envanteri ← kullanıcı doğrulamalı binary→source bağı / eklemeli geçmiş / salt-okunur eşleştirme
              ├─ Ubuntu envanter taraması ← tek Canonical kayıt / bütün etkin paketler / durum sayaçları / yazmasız görünüm
              ├─ Ubuntu maruziyet kanıtı ← açık insan seçimi / kaynak+paket özeti / atomik yeniden doğrulama
              ├─ Ubuntu kanıt güncelliği ← güncel paket+Canonical karşılaştırması / yazmasız durum ayrımı
              ├─ Ubuntu kanıt toplu kontrolü ← ağsız plan / CVE başına önbellekli sınırlı tarama
              ├─ Yerel IOC kataloğu ← kanonik gösterge / bağımsız kaynak iddiası / eklemeli geçmiş
              ├─ Birleşik dış risk analizi ← kayıtlı yüzey + marka adayı + kesin IOC / varsayılan ağsız ve yazmasız
              ├─ Açık IOC yenilemeli analiz ← Feodo IP + CERT Polska domain snapshot / kesinti koruması / yeniden okuma
              ├─ STIX 2.1 IOC çıktısı ← güncel salt-okunur anlık görüntü / atomik JSON dosyası
              ├─ Webhook teslimi ← açık bildirim seçimi / değişmez kuyruk / HMAC / güvenli HTTPS
              ├─ Çok kaynaklı IOC akışı ← kaynak politikası / sınırlı tam snapshot / çalışma + provenance / kesinti ayrımı
              ├─ CTI bilgi grafiği ← aktör / kampanya / malware / rapor / IOC ilişkileri
              ├─ MITRE ATT&CK senkronu ← sabit Enterprise v20 / katı STIX / atomik kaynak iddiası yaşam döngüsü
              ├─ İlgili NVD yenileme planı ← maruziyet kapsamı / kaynak güncelliği / sınırlı yürütme
              ├─ NVD tarih penceresi ← operasyon anlık görüntüsü / ağsız boşluk planı / sınırlı çoklu tek-sayfa yürütme / atomik imleç / kapsama ve denetimli yeniden başlatma
              ├─ Doğrulanmış ürün ve zafiyet görünümleri ← tek ürün / tüm envanter, salt okunur
              ├─ Varlık iş önemi sözleşmesi ← insan beyanı / SQLite güncel durum ve karar geçmişi
              ├─ Tedarikçi envanteri ← insan onayı / değiştirilemez ana domain / eklemeli SQLite geçmişi
              ├─ Tedarikçi iddia görünümü ← yerel ThreatCluster/RansomLook snapshot'ı / tam ad-domain dayanağı / salt okunur
              ├─ Tedarikçi inceleme kartı ← envanter + kabul edilmiş CNAME + kaynak kapsamı + açıklanabilir insan önceliği
              ├─ Yerel vaka yönetimi ← kaynak-denetimli dondurulmuş kanıt / görev / not / durum / tek zaman çizelgesi
              ├─ İnternet erişim bağlamı ← son web/izinli servis kanıtı / salt okunur
              ├─ Toplu zafiyet yeniden değerlendirmesi ← yerel plan / değişmez denetim geçmişi
              ├─ Servis kontrol sözleşmesi ← kesin IP / sabit TCP planı / SQLite değişim kanıtı
              ├─ Pasif yüzey keşfi/izlemesi ← crt.sh veya theHarvester P0 / SQLite aday, kaynak, çalışma ve bildirim geçmişi
              ├─ Durum özeti sözleşmesi ← SQLite / tutarlı geçmiş okuması
              ├─ İzleme denemesi sözleşmesi ← SQLite / oturuma bağlı işler ve özetler
              └─ Çalıştırma kilidi sözleşmesi ← Yerel işletim sistemi kilidi
```

| Bölüm | Sorumluluk | Bağımlılık sınırı |
|---|---|---|
| domain | Varlık/gözlem/bulgu/iş/kontrol/bildirim/istisna/dış yüzey/e-posta DNS/servis/pasif aday, ransomware iddiası ve kuruluş/domain izlemesi, tedarikçi ilişkisi ve kaynak bağlı iddia görünümü, yerel vaka/kanıt/görev/aktivite, maruziyet, iş önemi, IOC, CTI varlık/ilişki, webhook hedef/teslim, birleşik analiz, internet erişim bağlamı, teknoloji ipucu ve zafiyet kaynak modelleri ile keşif çalışması/kaynak kataloğu/değerlendirme/durum/izleme modelleri, aday ve inceleme sırası kuralları | Terminal, dosya okuma ve veritabanını bilmez |
| ports | Kayıt, kaynak, vaka/kanıt çözümleme, sosyal kullanıcı adı önizleme kaynağı, hedef/servis kontrolü, ransomware iddia kaynağı/snapshot geçmişi/kuruluş-domain izleme ve monitor oturum deposu, zafiyet kaynağı/deposu, IOC, CTI bilgi grafiği ve tam-snapshot besleme deposu, bildirim kutusu, webhook deposu/taşıması, tam adres istisnası, dış yüzey/e-posta DNS/pasif keşif/ilişki görünümü, durum özeti, izleme ve yürütme kilidi sözleşmeleri | Yalnız ortak modeller |
| application | Arama/iş/izleme yaşam döngüsü, yerel vaka ve kaynak-denetimli kanıt orkestrasyonu, kaynak kataloğu, sosyal kullanıcı adı girdi/platform sınırları, sınır kontrollü toplu yürütme ve ön plan tekrarı, açık ransomware iddiası yerel araması, tam-snapshot fark yaşam döngüsü, kuruluş/domain izleme ve tedarikçiyle ağsız tam ad/domain ilişkilendirmesi, açık yenileme+toplu çalışma ve sınırlı ön plan tekrar orkestrasyonu, kalite ve geri bildirim ölçümü, istisna, dış yüzey/e-posta DNS/servis kapsamı, kayıtlı yüzey+marka+kesin IOC birleşik analizi, kaynaklı IOC yaşam döngüsü ve STIX 2.1 IOC dönüşümü, açık seçimli webhook kuyruk/imza/teslim akışı, CTI varlık/ilişki yaşam döngüsü ve denetlenebilir tam-snapshot besleme senkronu, insan beyanlı iş önemi, KEV/EPSS/NVD katalog yaşam döngüsü, sürümlü üretici kaynak değerlendirmesi, açık ve envanterden Ubuntu paket sınırı karşılaştırması, devam edilebilir NVD tarih penceresi, kapsama/boşluk ve operasyon anlık görüntüsü, salt-okunur boşluk bölme planı, sınırlı çoklu tek-sayfa yürütme, denetimli yeniden başlatma ve birleşik zafiyet bağlamı, kanıt ilişkileri, açıklanabilir maruziyet ve teknoloji ipuçları, sınırlı pasif alt alan adı keşfi/izlemesi, kontrol seçimi, tekilleştirme, inceleme, okundu işlemleri, güncellik ve rapor | Kurallar ve sözleşmeler |
| adapters | SQLite, migration, vaka/aktivite depolaması ve mevcut kaynakların bütünlük denetimli vaka anlık görüntüsü, kilit, sabit commit'li Maigret CLI ve CLI sürüm isteğini kullanmayan sabit Sherlock kütüphane işçisi ile katı NDJSON dönüşümü, ransomware iddia çalışma/öğe geçmişi ve kuruluş/domain izleme kanıtları, kaynaklı IOC/CTI bilgi grafiği, Feodo Tracker/CERT Polska tam-snapshot kaydı, ThreatCluster ransomware iddia akışı ve MITRE ATT&CK Enterprise STIX kaynağı, arşiv/HTTPS/sabit TCP kontrolü, genel-IP'ye sabit webhook HTTPS taşıması, CISA KEV, FIRST EPSS, tek-CVE/tarih-pencereli NVD ve Canonical Ubuntu OSV HTTPS/SQLite adaptörleri, sürümlü değerlendirme verisi, atomik STIX/gizli anahtar/dosya/JSON raporu ve PSL | Dış veri biçimleri ve ortak sözleşmeler |
| interfaces | Komut, çıktı ve başlangıçta parçaları bağlama | Servis ve başlangıçta somut adaptör |
| config | Veri konumunu belirleme | Dosya oluşturmaz |

Terminal değişikliği alan adı kurallarını değiştirmeyi gerektirmez. Depoyu değiştirmek için başka adaptör yazılabilir; veri taşıma ve davranış testleri ayrıca gerekir.

## Veri ve güvenilirlik

- Veritabanı açık init/restore veya alan adı verilen scan/watch/monitor start başlangıcında oluşturulur. Listeleme/tanılama eksik veritabanı yaratmaz; import veya adres verilmemiş arama eksik veritabanında başlamaz.
- Şema 17: şema 16'ya ek olarak CISA KEV kaynak çalışmalarını, güncel/geçmiş katalog kayıtlarını ve eklemeli değişiklik olaylarını tutar. Şema 16'nın bütün kayıtları migration sırasında korunur; KEV tabloları boş başlar.
- Şema 18: şema 17'ye FIRST EPSS güncel puan kataloğunu ekler. Eski kayıtlar ve KEV geçmişi korunur; EPSS tablosu boş başlar ve geçmiş veriden puan türetilmez.
- Şema 19: şema 18'e açıkça istenen NVD CVE güncel kaydını ve eklemeli kaynak-nesnesi değişiklik geçmişini ekler. Eski kayıtlar, KEV ve EPSS korunur; NVD tabloları boş başlar.
- Şema 20: şema 19'a varlığa bağlı kullanıcı doğrulamalı ürün kayıtlarını ve eklemeli yaşam döngüsü olaylarını ekler. Önceki bütün kayıtlar korunur; ürün tabloları boş başlar ve port ipuçlarından ürün türetilmez.
- Şema 21: şema 20'ye ürün+CVE insan incelemesinin güncel durumu ile eklemeli karar geçmişini ekler. Önceki bütün kayıtlar korunur; yeni tablolar boş başlar ve eski eşleşmelerden insan kararı türetilmez.
- Şema 22: şema 21'e maruziyet incelemesine bağlı güncel destek kanıtı ile eklemeli kanıt geçmişini ekler. Önceki kayıtlar korunur; yeni tablolar boş başlar ve eski karar veya eşleşmelerden kanıt türetilmez.
- Şema 23: şema 22'ye dağıtım bağlamlı kesin Red Hat RPM kanıtı ile eklemeli yaşam döngüsü geçmişini ekler. Eski genel ürün kayıtlarından paket kimliği türetilmez; yeni tablolar boş başlar.
- Şema 24: şema 23'e maruziyet+kesin RPM+VEX ürün bağına bağlı yapılandırılmış Red Hat kanıtını ve eklemeli yaşam döngüsü geçmişini ekler. Eski salt-okunur eşleşmelerden kanıt türetilmez; yeni tablolar boş başlar.
- Şema 25: şema 24'e kaynaklı düzeltme planının güncel durumu ile uygulama/yeniden kontrol olay geçmişini ekler. Eski maruziyetlerden plan veya kontrol sonucu türetilmez.
- Şema 26: şema 25'e gerekçeli, kesin bitişli maruziyet bastırması ile etkinleştirme/uzatma/yeniden etkinleştirme/geri alma geçmişini ekler. Eski süresiz bastırmalardan bitiş uydurulmaz.
- Şema 27: şema 26'ya insan beyanlı varlık iş öneminin güncel durumunu ve eklemeli karar geçmişini ekler. Eski varlık, ürün veya maruziyet kayıtlarından önem türetilmez.
- Şema 28: şema 27'ye kontrollü toplu zafiyet yeniden değerlendirme çalışmalarını ve her çalışmanın sabit sonuçlarını ekler. Eski maruziyetlerden geriye dönük çalışma veya sonuç türetilmez.
- Şema 29: şema 28'e kanıt durumuyla tekilleştirilmiş yerel zafiyet değişiklik bildirimlerini ekler. Eski maruziyetlerden geriye dönük bildirim türetilmez.
- Şema 30: şema 29'a tam tarih aralığı ve sayfa boyutuyla tekilleşen NVD pencere imlecini ekler. Eski tek-CVE geçmişinden pencere, toplam veya tamamlanma durumu türetilmez.
- Şema 31: şema 30'a NVD pencere yeniden başlatmalarının önceki imleç, toplam, durum, kaynak çalışma bağları, gerekçe ve zamanını taşıyan eklemeli denetim olaylarını ekler. Mevcut pencere ilerlemesi korunur; eski işlemler için olay uydurulmaz.
- Şema 32: şema 31'e kullanıcı doğrulamalı Ubuntu binary→source paket bağının güncel kaydını ve eklemeli yaşam döngüsü geçmişini ekler. Eski varlık veya ürünlerden paket kimliği türetilmez; yeni tablolar boş başlar.
- Şema 33: şema 32'ye kanonik IOC kimlikleri, bağımsız kaynak iddiaları ve eklemeli iddia olaylarını ekler. Eski domain, bulgu veya zafiyet kayıtlarından IOC türetilmez; yeni tablolar boş başlar.
- Şema 34: şema 33'e IOC besleme çalışmalarını ve her çalışmanın kaynak iddiası işlem bağını ekler. Eski IOC'lerden çalışma geçmişi türetilmez; yeni tablolar boş başlar.
- Şema 35: şema 34'e kaynaklı CTI varlıkları, varlık iddiaları/olayları, varlık veya IOC hedefli ilişkiler ve ilişki iddiaları/olaylarını ekler. Eski IOC, bulgu veya raporlardan bilgi grafiği türetilmez; yeni tablolar boş başlar.
- Şema 36: şema 35'e kayıtlı CTI sorgu tanımı/olayları ile tam çalışma ve sonuç-öğe geçmişini ekler. Eski arama kullanımlarından sorgu veya çalışma türetilmez; yeni tablolar boş başlar.
- Şema 37: şema 36'ya tam CTI arama çalışmasına bağlı yerel değişiklik bildirimini ekler. Eski çalışmalardan bildirim türetilmez; tablo boş başlar.
- Şema 38: şema 37'ye kayıtlı CTI araması için güncel etiket durumu, eklemeli etiket olayları ve isteğe bağlı çalışma bağı taşıyan eklemeli analist notlarını ekler. Eski sorgu veya çalışmalardan etiket/not türetilmez; tablolar boş başlar.
- Şema 39: şema 38'e özel webhook hedefi, eklemeli hedef olayı, değişmez ve tekilleştirilmiş teslim gövdesi ile sıralı teslim denemelerini ekler. Eski bildirimlerden hedef veya teslim türetilmez; tablolar boş başlar.
- Şema 40: şema 39'a açık ransomware iddiası tam-snapshot çalışma ve güvenli öğe geçmişini ekler. Eski veriden iddia veya çalışma türetilmez; tablolar boş başlar.
- Şema 41: şema 40'a ransomware kuruluş/domain izleme tanımı, yaşam döngüsü olayı, tam fark çalışması ve ortak kutu bildirimini ekler. Eski snapshot'tan izleme veya bildirim türetilmez; tablolar boş başlar.
- Şema 42: şema 41'e ransomware monitor oturumu, tamamlanan tur ve turun tam izleme-çalışması üyelik bağını ekler. Eski kaynak veya izleme geçmişinden oturum/tur türetilmez; tablolar boş başlar.
- Şema 43: şema 42'ye ransomware kimlik değişimi adayının kanonik kanıt anlık görüntüsünü ve gerekçeli insan karar zincirini taşıyan eklemeli olay tablosunu ekler. Eski adaylardan karar uydurulmaz; tablo boş başlar.
- Şema 44: şema 43'e RansomLook çalışma ve sıkıştırılmış snapshot fark tablolarını ekler. Tablolar boş başlar; ThreatCluster geçmişi veya önceki canlı önizlemeler dönüştürülmez.
- Şema 45: şema 44'e RansomLook kuruluş izleme tanımı, olayları, çalışmalar ve tam çalışma sonuçlarını taşıyan dört ayrı tablo ekler. Eski snapshot'lardan izleme veya eşleşme uydurulmaz.
- Şema 46: şema 45'e kaynaklar arası karşılaştırmanın dondurulmuş kanıtını ve gerekçeli, eklemeli insan karar zincirini taşıyan tek tablo ekler. Eski karşılaştırmalardan karar uydurulmaz.
- Şema 47: şema 46'ya sosyal kullanıcı adı izleme tanımı/olayı, başarılı veya başarısız çalışma ve platform sonucu taşıyan dört tablo ekler. Eski yazmasız önizlemelerden izleme veya çalışma uydurulmaz.
- Şema 48: şema 47'ye tam sosyal profil kanıtı, karar, gerekçe, zaman ve önceki olay bağını taşıyan eklemeli karar tablosunu ekler. Eski izleme sonuçlarından karar uydurulmaz.
- Şema 49: şema 48'e yalnız olası taklit karar olayına bağlı, aday başına tekil ortak kutu bildirimi ve bağımsız okundu durumu ekler. Eski kararlardan bildirim uydurulmaz.
- Şema 50: şema 49'daki her sosyal kullanıcı adı izlemesine değiştirilemez Maigret/Sherlock kaynak kimliği ekler. Eski izlemeler Maigret'e bağlanır; çalışma, profil kararı ve bildirim kanıtı yeniden yazılmaz.
- Şema 51: şema 50'nin pasif keşif kaynak denetimini `crt.sh` ve sınırlı `theharvester` sağlayıcılarını ayrı kabul edecek biçimde genişletir; mevcut kanıtı ve çalışma sırasını korur.
- Şema 52: şema 51'e insan onaylı tedarikçi güncel kaydını ve tam anlık görüntülü eklemeli yaşam döngüsü olaylarını ekler. Eski varlık, CTI veya ağ kanıtından tedarikçi ilişkisi uydurulmaz; tablolar boş başlar.
- Şema 53: şema 52'ye kayıtlı son CNAME kanıtından türetilen tedarikçi adayını, kaynak kanıt zincirini ve geri alınabilir insan çözümleme kararlarını ekler. Eski CNAME kayıtlarından migration sırasında aday üretilmez; tablolar boş başlar ve yalnız açık `candidate-refresh` ile dolar.
- Şema 54: şema 53'e vaka güncel durumu, dondurulmuş kaynak kanıt bağı, takip görevi ve tek sıralı eklemeli aktivite tablolarını ekler. Eski bulgu, profil, ransomware veya tedarikçi kayıtlarından vaka üretilmez; tablolar boş başlar.
- 0.89.0–0.95.0 şema 39'u, 0.96.0 şema 40'ı, 0.97.0–0.99.0 şema 41'i, 0.100.0–0.102.0 şema 42'yi, 0.103.0–0.104.0 şema 43'ü, 0.105.0 şema 44'ü, 0.106.0–0.107.0 şema 45'i, 0.108.0–0.110.0 şema 46'yı, 0.111.0 şema 47'yi, 0.112.0 şema 48'i, 0.113.0–0.117.0 şema 49'u, 0.118.0 şema 50'yi, 0.119.0 şema 51'i, 0.120.0 şema 52'yi, 0.121.0–0.123.0 şema 53'ü ve 0.124.0–0.126.0 şema 54'ü kullanır. 0.122.0 tedarikçi iddia görünümü, 0.123.0 inceleme kartı, 0.124.1 klonla-çalıştır başlangıcı, 0.125.0 sosyal araç kurulumu/profilleri ve 0.126.0 pasif kaynak sağlık/kabul görünümü migration gerektirmez. Her dış yüzey değişiklik bildirimi tam olarak bir değişmiş web/posta/servis kanıtına yabancı anahtarla bağlıdır; kanıt ve bildirim aynı transaction içinde yazılır. İlk CNAME dilimi bildirim üretmez.
- Şema 55: tam sürümlü toplama profilleri ve değişmez tanım geçmişi.
- Şema 56: toplama oturumu, adımları ve gerçek kaynak sonuçlarına bağlı receipt kayıtları.
- Şema 57: açık kuruluş grupları, hedef bağlantıları ve revizyon olayları.
- Şema 58: STIX kimlikli ATT&CK kataloğu, başarılı senkron ve değişim geçmişi.
- Şema 59: ayrı RansomLook izleme bildirimi, ortak kutu sırası ve okundu durumu.
- Şema 60: HIBP kamu metadata kataloğu çalışmaları ve kompakt fark geçmişi.
- Şema 61: açık HIBP toplama birimi ve atomik, doğrudan kaynak sonuç bağı.
  Bu ek tablolar eski kayıtlardan tahminle doldurulmaz; mevcut kaynak kanıtları korunur.
- 0.131.0 şema 55, 0.132.0 şema 56 kullanır; 0.133.0 şema 59, 0.134.0 şema 60, 0.135.0 şema 61'dir.
- Şema 1–60 kayıtları açık `migrate` gerektirir. Önceki aramalardan geriye dönük vaka, tedarikçi veya tedarikçi adayı, izleme oturumu, sosyal kullanıcı adı izlemesi, profil kararı veya sosyal profil bildirimi, istisna, dış yüzey onayı/kontrolü, pasif aday, keşif çalışması, aday/değişiklik bildirimi, e-posta DNS/servis/CNAME kontrolü, KEV/EPSS/NVD, doğrulanmış ürün, insan maruziyet kararı, düzeltme planı, süreli bastırma, iş önemi, yeniden değerlendirme çalışması, zafiyet değişiklik bildirimi, NVD pencere ilerlemesi, yeniden başlatma olayı, IOC, IOC besleme çalışması, CTI varlık/ilişkisi, kayıtlı CTI sorgusu, CTI arama bildirimi, avcılık etiketi, analist notu, webhook hedefi/teslimi, ransomware iddia snapshot'ı, ransomware izlemesi, monitor oturumu, kimlik kararı veya kaynaklar arası karar üretilmez. Şema 6/7'den geçişte bulgu bildirimleri yeniden oluşturulmaz; kimlik ve okundu bilgileri korunur. Şema 8'in kalıcı istisnaları güncel düzende kalıcı kalır.
- Domain tekilliği uygulama normalleştirmesi ve veritabanı kısıtıyla korunur.
- Biçim işareti application_id=0x58544901; bu bir güven/özgünlük imzası değildir.
- Eski şemadan geçiş açık migrate komutuyla yapılır. Yazma kilidi altında önce özgün sürümün yedeği alınır. Gerekli ara tablolar ve şema 17'nin zafiyet tabloları tek transaction içinde oluşturulur; yalnız şema 1–5'ten geçişte önceki bulguların bildirimleri oluşturulur. Hata geri alınır; bilinmeyen şema değiştirilmez. Önceki sürümlerin tablo kümeleri sabittir.
- SQLite yazıları transaction içindedir. Ağ beklerken yazma transaction'ı açık tutulmaz. Arşiv adaptörleri crt.sh/urlscan'i sorgular; hedef bağlantısı ayrı kontrol adaptörüne aittir. Yeni urlscan taraması gönderilmez.
- Yedek SQLite backup API ile tutarlı alınır, kontrol edilir ve mevcut hedefi ezmeden yayımlanır.
- Geçici dosya hedefle aynı klasördedir; atomik, üzerine yazmayan hard-link işlemi kullanılır. Desteklemeyen dosya sisteminde işlem hata verir.
- Restore boş hedefe yapılır; kaynak şeması ve bütünlüğü kontrol edilir.
- Dosya tamamen doğrulanıp adaylar hesaplandıktan sonra gözlemler, etkin tam adres istisnası kontrolü, bulgular, bağlantılar ve yeni bulgu bildirimleri tek transaction içinde yazılır. Herhangi bir hata tamamını geri alır.
- Gözlem tekilliği dosya SHA-256 + satır; bulgu tekilliği varlık + domain + kural/referans sürümüdür. Aynı dosyanın farklı adı tekrar kanıt üretmez.
- İnternet gözlemleri sağlayıcı/kaynak kaydı/asıl ad/kaynak zamanı özetiyle tek kayıtlı belgelere dönüşür; sorgu sırası veya örtüşen sonuçlar tekrar üretmez. Sabit sağlayıcı bağlantıları, asıl ad ve kaynak zamanı korunur.
- Aramada tüm yanıtlar ve adaylar yazımdan önce doğrulanır; gözlemler tek tek atomik yazılır. Kesinti tamamlanmış gözlemleri silmez; yeniden çalışma tekilleştirme sayesinde sürdürülebilir.
- Yeni kaynak mevcut bulguya eklenirken karar korunur. Karar geçmişi append-only ve ekleme sırasındadır; saat gerilemesi sıralamayı bozmaz.
- Arama başlatılmadan kalıcı iş oluşturulur; her yeniden çalışma ayrı denemedir. Tamamlanan sorgular, son adım ve sonuç/hata geçmişi saklanır. Bitmiş denemelere geç güncelleme reddedilir.
- Yerel dosya kilidi tüm deneme boyunca tutulur; ağ beklerken SQLite transaction'ı tutulmaz. Yeni çalıştırıcı ancak kilidi aldıktan sonra önceki running işleri interrupted yapar. Salt okumalar kurtarma yapmaz.
- İş, hedefleri ve kural/kaynak sürümünü saklar. Yeniden deneme aramayı baştan yapar; sayılar o denemeye aittir. Yarım denemeye eksik sonuç sayısı uydurulmaz.
- Her sağlayıcı ayrı iştir. Worker kilit altında işi aldıktan sonra kayıtlı sağlayıcıya uygun servisi seçer. Sorgu planlayıcısı kaynağa göre bağlanır; eşleştirme ve bulgu kuralları ortaktır. İkinci kaynak aynı bulguya yeni gözlem ekler, kararı sıfırlamaz.
- Kaynak erişim/yanıt hataları diğer kaynağın sonuçlarını silmez. Genel doğrulama/depolama hataları işi durdurabilir. Her sağlayıcının geçmişi ayrı görünür.
- Ortak sorgu sayısı `record_count`, bilgi amaçlı kapsam `coverage_notes` alanındadır. Önceki şemadan taşınan `certificate_count` JSON'u değiştirilmeden okunur. Yeni kayıtlar eski uygulama ile okunamaz; eski sürüme dönüş yedek gerektirir.
- Tamamlanan hedef kontrolü, bulguya bağlı ayrı append-only kayıttır; insan kararı, arşiv gözlemi ve last_seen_at değiştirilmez. Son kontrol ekleme sırasıyla seçilir; saat gerilemesi geçmişi ters çevirmez.
- Rapor bulgu, gözlem, karar ve kontrolleri tek okuma transaction'ından alır. JSON dosyası boyut sınırlıdır, 0600 geçici dosya üzerinden mevcut hedefi ezmeden yayımlanır.

Kalıcı yerel kuyruk ve geçmiş vardır; dağıtık kuyruk, ham kanıt dosyaları ve çok kullanıcılı yetkilendirme yoktur. watch terminal açıkken döngüyü çalıştırır; kapandıktan sonra otomatik çalışmaz. Kilit aynı yerel kayıt dosyası içindir; dağıtık dosya sistemi garantisi yoktur. Yerel dosyaların gizliliği cihaz/disk güvenliğine de bağlıdır; uygulama düzeyinde şifreleme bulunmaz.

Kaynak görünümü en son denemenin kayıtlı sorgularından üretilir, anlık ağ erişimini ölçmez. İş/denemeler yedeklere dahildir; eski kayıtlardan geriye dönük arama geçmişi üretilmez. Ayrıntılar [kalıcı işler kararı](decisions/0004-durable-scan-jobs.md) içindedir.

## Girdi ve çıktı

İzlenen varlık normal ASCII domain biçiminde kontrol edilir. Varlık ekleme ve arşiv araması sahiplik veya mevcut erişim doğrulamaz. Kaynak U-label/A-label girdisi, paketlenmiş Unicode 18.0 UTS #46 profiliyle kanonik ASCII A-label'a çevrilir; UTS #39 iskeleti yalnız aday karşılaştırmasında kullanılır. Sağdan sola ve birleştirme denetimli etiketler bu profilde reddedilir. Kayıt sınırları, paketlenmiş Public Suffix List'in ICANN/PRIVATE ve wildcard/exception kurallarıyla ayrılır; Unicode PSL kuralları aynı profile göre A-label olur. SQL değerleri parametrelerle iletilir. Terminalde dinamik metnin kontrol karakterleri kaçırılır; JSON çıktısı kontrol dizisi üretemeyecek şekilde kodlanır.

Yeni işlerin yürütme sürümü `domain-rules-v3/psl:.../unicode:18.0.0` değeridir. Değişmeyen ASCII adayları eski `domain-rules-v1/psl:...` bulgu kimliğini korur; yalnız 0.14'te eklenen dar desenler `domain-rules-v2/psl:...`, IDN iskelet adayları ise `idn-confusables-v1/.../unicode:18.0.0` kimliği taşır. Böylece eski bulgu, karar ve bildirimler çoğalmaz; önceki yürütme sürümüyle sıraya alınmış bir iş yeni kuralla sessizce çalıştırılmaz. `--typos` sınırlı Punycode ve ASCII yazım varyantı sorgularını açar; kaynaktan zaten gelen geçerli aday her zaman analiz edilir. Ayrıntılar [Unicode/IDNA](decisions/0011-unicode-idn-homographs.md) ve [dar kural genişletme](decisions/0014-bounded-rule-expansion.md) kararlarındadır.

Dosya okuyucu yalnız normal UTF-8 TXT/JSONL dosyalarını, 2 MiB/5000 satır/8192 bayt satır sınırlarıyla alır. Tüm giriş ve karşılaştırma sınırı geçmeden veritabanına yazılmaz. Kaynak zamanı ile sisteme alınma zamanı ayrıdır; eksik tarih uydurulmaz.

crt.sh adaptörü sabit HTTPS adresi, TLS doğrulaması, yönlendirme reddi, 8 MiB/5000 satır sınırı ve sınırlı yeniden denemeyle çalışır. Sağlayıcının bekleme isteği sonraki sorgularda da korunur. Hata, boş veya kısmi sonuçla karıştırılmaz. Her kaynak çalıştırmasında beş izlenen varlık, 10.000 belge ve 250.000 karşılaştırma sınırı vardır. Teknik ayrıntılar [internet araması kararı](decisions/0003-public-certificate-search.md) içindedir.

urlscan 2 MiB/100 kayıt, ön ek araması ve anonim erişimin bildirdiği geçmiş sınırıyla çalışır. Tarih kapsamı bilgi notudur; alınmayan sayfa veya hata kısmi durumdur. Tam URL yolları, içerik ve ekran görüntüleri kaydedilmez. İstek kotası başlıkları artık aynı veritabanında süreçler arasında korunur. Kaynak düzeni [ikinci kaynak kararında](decisions/0005-independent-archive-source.md), kalıcı bekleme [bakım kararında](decisions/0007-durable-waits-and-maintenance.md) açıklanır.

## Açık ransomware iddiası önizlemesi

`RansomwareClaimService`, yalnız `RansomwareClaimSource` portuna bağlıdır. Uygulama servisi isteğe bağlı kuruluş/domain/grup/ülke/sektör ifadesini ve `listed/delisted` filtresini doğrular; tamamen doğrulanmış snapshot üzerinde tam, başlangıç ve içerme eşleşmesini sıralar. Görünüm sınırı 1–100'dür ve toplam eşleşme sayısını daraltmaz.

`ThreatClusterRansomwareSource` yalnız sabit kamu JSON adresini yönlendirmesiz ve sıkıştırmasız TLS ile okur. Yanıt 30 saniye, 8 MiB, 10.000 kayıt ve 48 saat güncellikle sınırlıdır. Akış/lisans kimliği, sayaç, zaman, alan kümesi, ülke, ilan durumu, isteğe bağlı zamanlar ve kaynak gönderi URL biçimi bütün sonuç üretilmeden doğrulanır. Bilinmeyen şema veya yinelenen iddia kısmi görünüm üretmez.

Domain modeli leak-site `post_url` değerini içermez; yalnız kaynak gönderisinin mevcut olduğu boolean işaretini taşır. Adaptör Tor'a veya gönderi adresine bağlanmaz, ham metin/ekran görüntüsü almaz. `ransomware recent` veritabanı oluşturmaz veya yazmaz. `RansomwareClaimHistoryService` açık `refresh` işleminde kaynak hatasını başarısız çalışma olarak ayırır; `SQLiteRansomwareClaimRepository` önceki son başarılı tam snapshot ile yeni snapshot'ı tek transaction içinde karşılaştırıp yeni/değişen/aynı/pencereden çıkan güvenli öğeleri saklar. İlk başarılı çalışma başlangıç çizgisidir; `status` ağsızdır.

`RansomwareSourceEvaluationService`, ikinci açık kaynağı eklemeden önce sürümlü ve çevrimdışı bir kabul kapısı uygular. Zorunlu ölçütler etkin bakım, anahtarsız ücretsiz erişim, yapılandırılmış dar çağrı, açık yeniden kullanım koşulu, bağımsız toplama ve güvenli asgari içeriktir. 30 Ekim 2026 değerlendirmesinde RansomLook bütün ölçütleri geçti; arşivlenmiş RansomWatch güncel akış için uygun bulunmadı, Darkfield ise anahtarsız dar sözleşme ve üst kaynak çakışması netleşene kadar ertelendi. Rapor çalışma anında internet veya depolama kullanmaz.

`BrandSourceEvaluationService`, dış araç kurulmadan önce sürümlü `free-brand-osint-tool-gate-v2` kapısını ağsız uygular. Doğrulanmış upstream, bakım, ücretsiz/hesapsız temel kullanım, sonuç JSON'u, çalışma sınırı, kod lisansı, hesap-kurtarma yoklaması kullanmama ve güncel kapsam zorunludur. Maigret'in sınırlı CLI adaptörü ile theHarvester'ın yalnız iki P0 arşiv adaptörü seçilmiştir; Sherlock sonraki bağımsız kapsam kapısında küçük bir listeye kabul edilmiş, Web-Check, Holehe ve olası telefon aracı elenmiştir. Bu servis araç çalıştırmaz, kullanıcı adı/domain aramaz, depolama açmaz ve üçüncü taraf kodunu çekirdeğe dahil etmez. Ayrıntılar [ücretsiz marka OSINT aracı kararında](decisions/0107-free-brand-osint-tool-gate.md) ve [theHarvester sınır kararında](decisions/0117-bounded-theharvester-archive-discovery.md) bulunur.

`SurfaceSourceEvaluationService`, pasif alt alan adı adaptörlerini sürümlü
`passive-surface-source-gate-v4` kapısıyla ağsız değerlendirir. Aktif kimlikler
domain katmanındaki tek `SURFACE_DISCOVERY_PROVIDERS` sözleşmesiyle birebir
eşleşir; SQLite kanıt okuma/yazma doğrulaması ve sağlık görünümü aynı sırayı
kullanır. Subfinder v2.17.0 normal CLI'si, sağlayıcı hatalarını makine-okunur
JSONL sonuçta korumadığı ve mevcut ücretsiz kaynaklardan bağımsız ölçülmüş katkı
göstermediği için ertelenmiştir. `SurfaceDiscoveryStatusService.health`, her
sağlayıcının son kayıtlı çalışmasını tek UTC değerlendirme anında ayrı
sınıflandırır; canlı ağ sağlığı iddiası üretmez, yazmaz ve migration istemez.
Ayrıntılar [pasif kaynak bütünlüğü kararındadır](decisions/0124-passive-source-integrity-and-adapter-gate.md).

`BrandSourceCoverageService`, ikinci kaynak kararını düzeltilmiş ve sabitlenmiş `free-social-source-coverage-gate-v2` kanıtından ağsız üretir. Paketli kanıt tam SHA-256, boyut, tekrar alan reddi, alan kümeleri, HTTPS başvuruları, kaynak rolleri ve çapraz sayaç bağlarıyla doğrulanır. Maigret ve Sherlock'un sabit kataloglarından geliştirme zamanında türetilen ölçüm yalnız etkin HTTPS kullanıcı adı tanımlarını alır; normalleştirilmiş ad veya paketli Public Suffix List kayıt kökü ortak sayılır. Sherlock'un 455 uygun tanımından 103'ü/101 kayıt kökü eşleşmeyen kapsamdır. İlk kabul sekiz platformluk kısa listeyle yapılmıştır; 0.125.0'da iki kaynak için URL/host bazında yeniden incelenen geniş profiller eklenmiştir. v2 kanıtı CLI'ın gizli sürüm isteğini kabul etmez; yalnız seçilen yerel katalog nesneleriyle yalıtılmış kütüphane işçisini ve XTI NDJSON sözleşmesini kaydeder. Servis üçüncü taraf aracı çalıştırmaz, katalog indirmez ve depolama açmaz. Ayrıntılar [ikinci sosyal kaynak kapsam kararında](decisions/0114-second-social-source-coverage-gate.md) ve [doğrulanmış kurulum/profil kararında](decisions/0123-verified-brand-toolchain-and-profiles.md) bulunur.

`setup-brand`, mevcut `.venv` ortamını sabit adlı proje-içi geri dönüş kopyasına
taşır ve yeni ortamı kararlı `.venv` yolunda kurar. Paket bağımlılıklarını,
dağıtım sürümünü, resmî depo adresini, istenen ve çözülen tam Git commit'ini,
katalog dosyası türü/boyutu/SHA-256 özetini, bütün geniş profil URL izinlerini
ve Maigret çalıştırıcısını doğrular. Geçişli bağımlılıklar sürümlü constraint
dosyasına bağlıdır; yalıtılmış pip çalışması resmî PyPI indeksini ve Git
yapılandırmasından yalıtılmış resmî GitHub URL'lerini kullanır. Başarısızlık
veya yakalanan sinyalde kısmi
ortam kaldırılıp eski ortam geri konur. PID kilidi eşzamanlı kurulumu engeller;
yetim işaretli kurulum sonraki denemede geri alınır. Çalıştırıcı, kurulum
işaretli `.venv` yerine sistemdeki desteklenen Python'a düşer. Geçerli ortam
tekrar indirilmez. `./setup` bunu varsayılan çalıştırır; `--core-only`,
`--check` ve `--force` açık alternatiflerdir.

`BrandUsernamePreviewService`, tek kullanıcı adını, `safe`/`extended`/özel
platform seçimini ve süre sınırını dış adaptörden önce doğrular. Maigret'in
güvenli profili 6, geniş profili 30 elle incelenmiş HTTPS tanım içerir.
`MaigretUsernameSource`, resmî
reponun sabit commit'inden kurulan 0.6.6 CLI'ı kabuksuz ayrı süreçte çalıştırır.
Paketli site veritabanının sabit SHA-256 özeti ve seçilen platformların HTTPS
hostları doğrulanır; her çalışma için yalnız bu tam platformları taşıyan geçici
bir Maigret veritabanı oluşturulur. Adaptör yalnız doğrulanmış NDJSON'dan
platform+profil URL+`found_unverified` alır, ham ve çıkarılmış alanları atar.
Tor/proxy, otomatik güncelleme, özyineleme, domain arama ve yapay zekâ kapalıdır.
Önizleme XTI deposunu açmaz ve yazmaz. Ayrıntılar [sınırlı Maigret
kararındadır](decisions/0108-bounded-maigret-username-preview.md).

`SherlockUsernamePreviewService`, Sherlock'un 5 platformluk güvenli veya 26
platformluk geniş profilini ve özel seçimini ağdan önce doğrular.
`SherlockUsernameSource`, resmî tam
commit'ten kurulan 0.16.2 paketinin sürümünü ve katalog SHA-256 özetini
doğrulayıp yalnız seçilen platformları geçici kataloğa ayırır. Sherlock CLI'ın
ek GitHub sürüm isteğini çalıştırmaz; sabit `sherlock()` kütüphane işlevini
yalıtılmış işçide çağırır. İşçi kendi dört alanlı NDJSON raporunu yazar; ana
süreç raporu kullanıcı adı, platform, durum ve HTTPS/443 host sınırıyla tekrar
doğrular. Ham yanıt ve profil ayrıntısı alınmaz. Sonuç veritabanını açmaz veya
yazmaz. Kalıcı izleme profil adını değil çözülen tam platform listesini saklar.
Ayrıntılar [sınırlı Sherlock kararında](decisions/0115-bounded-sherlock-username-preview.md)
ve [0.125.0 profil kararında](decisions/0123-verified-brand-toolchain-and-profiles.md)
bulunur.

`BrandUsernameWatchBatchService`, etkin sosyal kullanıcı adı izlemelerini
`BrandUsernameWatchService.list_window` üzerinden görünen ad ve kimliğe göre
kararlı sırada alır. Açık sınırdan bir fazla kayıt okuyarak bütün etkin kapsamın
sığıp sığmadığını kaynak çağrısından önce belirler; taşmada hiçbir çalışma
başlatmaz. Her izleme mevcut tekil `run` yolundan geçtiği için kaynak hatası,
son başarılı temel, fark ve atomik kayıt kuralları çoğaltılmaz. Kaynak hatası
başarısız çalışma olarak saklanıp sonraki izlemeye geçilir; depolama veya
bütünlük hatası akışı durdurur fakat önce tamamlanan ayrı transaction'ları geri
almaz. CLI bütün toplu işlem boyunca ortak yerel çalışma kilidini tutar. Yeni
toplu oturum tablosu, zamanlayıcı veya daemon yoktur; şema 49 değişmez.
Ayrıntılar [sınırlı sosyal toplu çalışma
kararındadır](decisions/0112-bounded-social-watch-batch.md).

`BrandUsernameWatchMonitorService`, tek etkin tanımı başlamadan doğrular ve
mevcut `BrandUsernameWatchService.run` yolunu monoton saatle sınırlı ön planda
tekrarlar. Tur sayısı, en az beş dakikalık aralık, toplam yeni-tur başlatma
bütçesi ve platform istek süresi kaynak çağrısından önce doğrulanır. Her
tamamlanan tur bağımsız çalışma kaydıdır; kaynak hatası başarısız tur olarak
korunur ve bütçe kaldığında sonraki tur denenir. En fazla bir saniyelik uyku
parçaları `Ctrl+C` kesintisini geciktirmez. Süre sınırı başlamış Maigret işini
zorla kesmez, yalnız yeni turu engeller. CLI bütün monitor boyunca ortak yerel
kilidi tutar. Kalıcı monitor oturumu, otomatik devam, zamanlayıcı veya daemon
yoktur; şema 49 değişmez. Ayrıntılar [sınırlı sosyal ön plan izleme
kararındadır](decisions/0113-bounded-foreground-social-watch.md).

`RansomLookRansomwareSource`, yalnız sabit `https://www.ransomlook.io/api/posts?days=7` adresini yönlendirmesiz, sıkıştırmasız ve 30 saniye/2 MiB/10.000 kayıt sınırlarıyla okur. Yanıt tam `{posts}` şemasında olmalı; her kayıtta yalnız `group_name`, `post_title` ve `discovered` bulunmalıdır. Yinelenen JSON alanı/kayıt, kontrol karakteri, pencere dışı UTC zamanı ve şema kayması bütün önizlemeyi güvenli biçimde durdurur. Uygulama servisi grup ve başlıkta yerel arama yapar; bilinmeyen ülke, sektör, domain veya ilan durumu üretmez.

RansomLook için ayrı domain modeli ve port kullanılır. Çünkü kaynak ThreatCluster kimliğini, ilan durumunu, ülke/sektörü veya domaini sağlamaz; ortak modele zorlamak yanlış kanıt üretirdi. `ransomware recent --source ransomlook` yazmasız canlı önizlemedir. `refresh --source ransomlook` ise yalnız açık çağrıda ayrı `ransomlook_claim_runs` ve `ransomlook_claim_run_items` tablolarına atomik fark geçmişi yazar; ilk snapshot başlangıç çizgisidir, değişmeyen kayıtlar tekrar yazılmaz ve kaynak hatası son başarılı durumu silmez. Yedi günlük pencereden çıkış yalnız kaynak görünürlüğü değişimidir. RansomLook tablolarının ThreatCluster snapshot, izleme, bildirim veya kimlik tablolarına yabancı anahtarı yoktur. Hiçbir akış Tor/leak-site adresine bağlanmaz veya ham içerik indirmez. Ayrıntılar [ikinci kaynak önizleme kararında](decisions/0102-ransomlook-second-source-preview.md) ve [kalıcı geçmiş kararında](decisions/0103-ransomlook-source-isolated-history.md) bulunur.

`RansomLookWatchService`, yalnız `organization` türünü ve kaynak başlığında `exact/contains` eşleşmesini kabul eder. Tanım, eklemeli yaşam döngüsü, çalışma ve sonuçlar `ransomlook_watch_*` tablolarında tutulur. Her çalışma son başarılı RansomLook snapshot kimliğine bağlıdır ve yazma anında tam snapshot kanıtı yeniden doğrulanır. Aynı tanımın ilk çalışması sessiz başlangıçtır; sonraki yeni/değişen kayıtlar `attention_count` içinde insan inceleme adayıdır. Çıkarılma yalnız kayan kaynak penceresidir. Bu tablolardan ThreatCluster izleme/bildirim/kimlik tablolarına bağ yoktur; ortak inbox şema 59 ile ayrı RansomLook bildirimi okur; iki kaynak otomatik tek olaya dönüştürülmez. Ayrıntılar [RansomLook izleme kararında](decisions/0104-ransomlook-organization-watch.md) bulunur.

`RansomwareSourceComparisonService`, iki ayrı repository portundan son başarılı yerel snapshot'ları alır. Domain katmanı NFKC+casefold+boşluk normalleştirmesi sonrası kuruluş adının tam eşitliğini ve ayrıca grup adı veya kanonik keşif zamanından en az birinin eşitliğini ister. Aynı kuruluş+grup+zaman, kuruluş+grup ve kuruluş+zaman sonuçları ayrı açıklama temelleridir; yalnız kuruluş, yalnız grup/zaman ve yaklaşık metin benzerliği elenir. Sonuç her iki özgün claim'i ve kararlı çift kimliğini taşır; ağ, yazma, alarm, inbox veya kimlik birleştirme yoktur. Şema 45 değişmez. Ayrıntılar [kaynak karşılaştırma kararında](decisions/0105-explainable-ransomware-source-comparison.md) bulunur.

`RansomwareSourceReviewService`, yalnız güncel `RansomwareSourceComparisonService` sonucunda yeniden bulunabilen kararlı karşılaştırma kimliğine `possible_same`, `different` veya `uncertain` kararı ve zorunlu gerekçe kabul eder. `SQLiteRansomwareSourceReviewRepository`, ilk karardaki iki kaynak çalışma kimliğini, iki özgün claim'i ve karşılaştırma temelini kanonik JSON+SHA-256 ile dondurur. Her değişiklik önceki olaya bağlanan yeni satırdır; aynı karar+gerekçe idempotenttir. Okuma ve yazma iki tam kaynak geçmişini, snapshot üyeliğini, kanıt özetini, olay zincirini ve zaman sırasını yeniden denetler. Yeni kaynak snapshot'ları eski karar kanıtını değiştirmez. Karar claim birleştirmez, alarm/inbox üretmez ve ihlal doğrulaması değildir. Şema 45→46 açık yedekli migration ile boş karar geçmişi ekler. Ayrıntılar [kaynaklar arası insan kararı kararında](decisions/0106-cross-source-ransomware-human-review.md) bulunur.

`RansomwareWatchService`, sürümlü kuruluş/domain tanımını son başarılı yerel snapshot ile birleştirir. Kuruluş eşleştirmesi yalnız `victim`, domain eşleştirmesi yalnız normalleştirilmiş `website` hostu üstündedir. SQLite adaptörü tanım olayını, kaynak snapshot kimliğini, tam sonuç farkını ve gerekirse bildirimi tek transaction'da saklar. İlk veya değişmiş tanım çalışması sessiz baseline'dır; sonraki `added/updated` yerel kutuya girer, tek başına `removed` girmez. Ortak bildirim sırası ve okundu durumu korunur; bildirim kanıtı doğrudan değişmez çalışma kaydına bağlıdır.

`RansomwareWatchRefreshService`, bütün etkin tanımların sınıra sığdığını ağdan önce doğrular, kaynağı bir kez yeniler ve yalnız tamamlanmış yeni snapshot kimliğiyle kararlı sırada izleme çalıştırır. Kaynak hatasında eski snapshot kullanılmaz. Her izleme ayrı transaction olduğundan sonraki hata tamamlanan işi geri almaz; akış güvenli biçimde durur. Komut ön planda tek seferliktir ve şema 41'e yeni tablo eklemez. Her kayıt kaynak grubunun doğrulanmamış iddiasıdır; eşleşme yokluğu, pencereden çıkma veya `delisted` durumu güvenlik/ihlal/ödeme kararı değildir. Ayrıntılar [önizleme kararında](decisions/0093-bounded-public-ransomware-claim-preview.md), [kalıcı snapshot kararında](decisions/0094-durable-ransomware-claim-snapshots.md), [kuruluş/domain izleme kararında](decisions/0095-ransomware-organization-domain-watches.md) ve [toplu yenileme kararında](decisions/0096-explicit-ransomware-refresh-all-watches.md) bulunur.

`RansomwareWatchMonitorService`, aynı açık akışı 1–1000 tur, en az beş dakika aralık ve en fazla yedi günlük yeni-tur bütçesiyle terminal ön planında tekrarlar. Monoton saat gerilemesi ağdan önce veya turlar arasında güvenli durur. Kaynak hatası kalıcı başarısız çalışma olarak tur özetine girer ve eski snapshot kullanılmadan sonraki tur beklenir. Süre sınırı/`Ctrl+C` tamamlanmış kaynak ve izleme kayıtlarını geri almaz.

`RansomwareMonitorSessionService`, monitor başlamadan şema 42'de `running` oturum açar ve her tamamlanan turu hemen kaydeder. Tur, kaynak çalışmasına ek olarak kendi oluşturduğu izleme çalışma kimliklerine ayrı bağlantı satırlarıyla bağlıdır; aynı snapshot üzerinde sonradan yapılan bağımsız `watch-run` eski tur özetine katılmaz. Normal bitiş `complete/partial`, `Ctrl+C` `interrupted`, beklenmeyen uygulama/depolama hatası `failed` olur. Sürecin zorla kapanması satırı `running` bırakır; salt okuma bunu tamamlama veya canlı süreç kanıtı saymaz. Oturum listesi/ayrıntısı bütün kaynak, izleme, bildirim ve bağlantı sayaçlarını tek okuma anında yeniden denetler. Ayrıntılar [ön plan izleme kararında](decisions/0097-bounded-foreground-ransomware-monitor.md) ve [kalıcı oturum kararında](decisions/0098-durable-ransomware-monitor-sessions.md) bulunur.

`RansomwareWatchTimelineService`, güncel izleme tanımını `RansomwareClaimHistoryEvidence` içindeki denetlenmiş kompakt fark geçmişine uygular. Uygulama katmanı aktif claim ve aktif eşleşme kümelerini tek geçişte yeniden kurar; değişmeyen üyelik satırı saklanmasa bile dokunulmamış aktif eşleşmeleri tekrar gözlem olarak sayar. Kaynak kimliği ilk kez eşleştiğinde `first_seen`, alanı değiştiğinde `updated`, domain ilişkisi güncellemeyle başladığında/bittiğinde `match_started/match_ended`, pencereden çıktığında `removed`, aynı kimlik geri geldiğinde `reappeared` üretir. Görünüm sınırı yalnız dönen son olayları daraltır; bütün geçmiş önce denetlenir ve toplamlar tam kapsamdan hesaplanır. Güncel tanım geçmişe geriye dönük uygulanır; eski tanım sürümü gibi sunulmaz. Kimlik grup + kuruluş + kaynak keşif zamanına bağlı olduğundan bu alanları değiştiren kaynak kayıtları kanıtsız birleştirilmez. Şema 42 değişmez. Ayrıntı [ağsız zaman çizelgesi kararında](decisions/0099-offline-ransomware-claim-timeline.md) bulunur.

`RansomwareWatchIdentityCandidateService`, aynı denetlenmiş geçmişte yalnız kimlik çıkarma ve yeni kimlik ekleme geçişlerini karşılaştırır. Eski kayıt aynı veya hemen önceki başarılı snapshot'ta kaybolmuş olmalı; başarısız kaynak çalışması boş snapshot sayılmaz. Grup, kuruluş, keşif zamanı ve normalleştirilmiş web alanından en az iki ortak açıklanabilir çapa gerekir. Birden fazla eski kayıt uyarsa yalnız en yakın başarılı snapshot'ta kaybolanlar değerlendirilir; eşzamanlı kayıtlar, uzak geçişler ve kesin kimliğin geri gelişi aday değildir. Sonuç salt-okunur insan inceleme görünümüdür: kimlik, zaman çizelgesi, izleme sonucu veya bildirim değiştirilmez. Şema 42 değişmez. Ayrıntı [kimlik değişimi adayı kararında](decisions/0100-ransomware-identity-change-candidates.md) bulunur.

`RansomwareIdentityReviewService`, yalnız güncel denetlenmiş geçmişte yeniden bulunabilen kararlı aday kimliği için `possible_same`, `different` veya `uncertain` kararı ve zorunlu gerekçe kabul eder. `SQLiteRansomwareIdentityReviewRepository`, adayın kanonik güvenli anlık görüntüsünü her kararla birlikte özet bağlı olarak saklar; olaylar önceki olay kimliğine bağlanır ve zaman sırası, kaynak geçişi, izleme ilgisi, ortak/değişen alanlar her okumada yeniden denetlenir. Aynı karar+gerekçe idempotenttir; değişiklik yeni olay ekler. Aday listesi son kararı ayrı durum olarak gösterir, fakat karar kaynak claim kimliğini, zaman çizelgesini veya bildirimi değiştirmez. Şema 42→43 açık yedekli migration ile boş karar geçmişi ekler. Ayrıntı [insan kararı kararında](decisions/0101-ransomware-identity-candidate-decisions.md) bulunur.

## Eşleştirme kalite değerlendirmesi

`EvaluationService` yalnız `DomainMatcher` ve ortak değerlendirme modellerine bağlıdır; ağ, SQLite veya terminal bilmez. Her örneğin izlenen adresini ve adayını üretimdeki normalleştirme, Public Suffix ve Unicode profiliyle işler. Beklenti `review` veya `ignore` değeridir. `review`, insan incelemesine gitme beklentisidir; doğrulanmış phishing etiketi değildir.

Paketli `domain-evaluation-v2` JSON'u 256 KiB ve 1000 örnek üst sınırı, tam alan kümesi, tekil kimlik, görünür metin, bilinen etiket ve sabit SHA-256 ile adaptörde doğrulanır. Veri bozuksa değerlendirme başlamaz ve kısmi metrik üretilmez. Küme 47 sentetik örnektir; gerçek olay veya alan adı sahipliği verisi içermez. İki önceki kaçırma yeni dar kuralların baseline'ına alınmış, aşırı genişlemeyi önleyen üç negatif örnek eklenmiştir. Terminal `evaluate` komutunda bu adaptörü servisle bağlar; kayıt dizinine erişmez ve kaynak adaptörü çağırmaz.

Rapor confusion matrix sayılarını, precision/recall/yanlış alarm/toplam doğruluk oranlarını, kategori özetlerini ve hatalı örnekleri verir. Her örnekte ayrıca mevcut kuralın kayıtlı `baseline` sonucu bulunur. Beklentiden sapıp baseline ile aynı kalan sonuç bilinen kalite açığıdır. Güncel tahmin baseline'dan ayrılırsa kalite iyileşmiş olsa bile davranış değişimi ayrıca görünür; otomatik test bu değişimin sessiz kalmasını engeller. Veri veya beklenti bilinçli değiştirildiğinde küme sürümü ve SHA-256 birlikte yenilenmelidir.

Metrikler yalnız bu küçük, seçilmiş kümenin davranışıdır. Kaynak kapsamı, gerçek marka dağılımı, saldırgan davranışı ve meşru üçüncü taraf sıklığı ölçülmediği için ürün doğruluk iddiasına dönüştürülemez. Ayrıntılar [değerlendirme](decisions/0013-versioned-matching-evaluation.md) ve [0.14 kural genişletme](decisions/0014-bounded-rule-expansion.md) kararlarındadır.

## Kullanıcı inceleme geri bildirimi

`FeedbackService`, yalnız `FeedbackRepository` anlık görüntüsüne bağlıdır. SQLite adaptörü bulgu durumlarını, eklemeli karar geçmişini ve kural sürümü gruplarını tek salt okunur transaction içinde toplar. Son kayıtlı durum son karar olayıyla uyuşmuyorsa, bilinmeyen durum/kural grubu varsa veya toplamlarda çelişki görülürse rapor üretilmez. Okuma veritabanını oluşturmaz, onarmaz veya migrate etmez.

`feedback` toplam/incelenen/bekleyen adayları, son kullanıcı kararlarını, karar olayı ve yeniden incelenen bulgu sayısını kural sürümüne göre verir. İnsan ve JSON raporu domain, bulgu kimliği, gerekçe ya da ham kanıt taşımaz. İnceleme kapsamı yalnız iş akışının ne kadarının ele alındığını gösterir. `suspicious`, `dismissed` ve `uncertain` kullanıcı kararları doğrulanmış tehdit/yanlış pozitif etiketi değildir; bunlardan precision veya recall hesaplanmaz. Ayrıntılar [geri bildirim kararında](decisions/0015-review-feedback-summary.md) bulunur.

## Tam alan adı istisnası

`AllowlistService`, kayıtlı izlenen varlığı ve tam aday alan adını mevcut `DomainMatcher` ile doğrular; joker, ilgisiz adres veya izlenen kökün kendisi için kayıt oluşturmaz. Unicode aday aynı sürümlü profil üzerinden kanonik ASCII A-label olur. Politika anahtarı `asset_id + domain` olduğu için aynı adayın başka izlenen varlıktaki değerlendirmesi etkilenmez. Etkinlik mevcut bulgu kural sürümünden bağımsızdır; tam adres için sonraki kural sürümlerini de kapsar.

`allowlist_entries` güncel etkinlik, gerekçe ve isteğe bağlı kesin UTC bitişini; `allowlist_events` ekleme/güncelleme/kaldırma/yeniden etkinleştirme işlemlerini ekleme sırasıyla tutar. Bitiş verilmezse kayıt kalıcı, verilirse 1–3650 gün sonrasıdır. Etkin kaydı aynı değerlerle tekrar eklemek değişiklik veya yeni olay üretmez. Süre/gerekçe değişikliği `updated`; kaldırılan veya süresi dolan kaydın açılması aynı kimlikle `reactivated` olayıdır. İlk oluşturulma zamanı korunur. Silme komutu yoktur. Listeleme ve ayrıntı salt okunurdur; gerekçe 1–1000 görünür karakterdir.

Arama ve dosya içe aktarma uygulama katmanında tek bir politika anına göre etkin çiftleri adaylardan çıkarır. Kayıt, elle kaldırılmamış ve bitişi bu andan kesin olarak ilerideyse etkindir; tam bitiş anında etkisizdir. Sona erme türetilmiş ve salt okunur durumdur, zamanlayıcı veya otomatik yazma yoktur. Depolama adaptörü güncel zamanı kullanarak aynı kontrolü bulgu transaction'ı içinde tekrar yapar; böylece uygulama kontrolüyle yazma arasında sürenin dolması veya unutulmuş filtre yeni bulgu/bildirim oluşturamaz. Bozuk bitiş değeri kısmi kayıt bırakmadan güvenli hatadır.

Gözlem etkin istisna sırasında yine kaydedilir. Mevcut bulguya yeni bağlantı eklenmez ve `last_seen_at` değiştirilmez. Önceden var olan bulgu, inceleme, kanıt ve bildirim değişmez. İstisna kaldırıldıktan veya süresi dolduktan sonra aynı kaynak kaydı yeniden işlendiğinde saklı gözlem mevcut/yeni bulguya bağlanabilir; yalnız sürenin dolması kendiliğinden bulgu yazmaz.

Şema 7→8 geçişi istisna tablolarını eklemişti. Şema 8→9, önce kurtarma yedeği yayımlar ve iki tabloyu tek transaction içinde bitiş alanlarıyla yeniden kurar; eski kayıtların bitişini boş bırakarak onları kalıcı tutar. Güncel yedek/restore kayıtları, bitişleri ve işlem geçmişini kapsar. Ayrıntılar [tam adres istisnası](decisions/0012-exact-domain-allowlist.md) ve [süreli istisna](decisions/0016-expiring-exact-domain-allowlist.md) kararlarındadır.

## Onaylı dış yüzey ve pasif alt alan adı keşfi

`SurfaceService`, yalnız `AssetRepository`, `SurfaceRepository` ve isteğe bağlı `TargetProbe` sözleşmelerine bağlıdır. `surface approve`, kayıtlı tam domaini gerekçeli kullanıcı yetki beyanıyla kapsama alır. Teknik sahiplik doğrulaması yapmaz. Etkinlik ve güncel gerekçe `surface_scopes`; onay, güncelleme, kaldırma ve yeniden etkinleştirme olayları `surface_scope_events` içinde ekleme sırasıyla tutulur. Silme yoktur.

`surface check`, kapsamı ağ çağrısından önce doğrular. Var olan `HttpsTargetProbe` güvenlik sınırlarıyla yalnız tam kök domainin Google Public DNS A/AAAA görünümünü ve ilk genel IP üzerindeki doğrulanmış TLS + HTTPS HEAD durumunu ölçer. Aynı doğrulanmış TLS oturumundan DER SHA-256, seri, issuer/subject, geçerlilik tarihleri ve kanonik DNS ad kapsamı alınır. Özel/yerel IP, başka port/yol, yönlendirme, gövde, alt domain genişletme ve doğrulamasız TLS yoktur. Kontrol yerel çalıştırma kilidi içindedir. Sonuç yazılırken kapsam aynı transaction içinde tekrar doğrulanır; arada kaldırıldıysa kanıt yazılmaz.

Her sonuç `surface_checks` içinde append-only saklanır. Kanonik durum; DNS durumu, sıralı IP'ler, TLS/HTTPS durumu, bağlanılan IP ve varsa doğrulanmış sertifika kimliğinden oluşur. SHA-256 özeti kayıtla birlikte doğrulanır. İlk sonuç `baseline`, aynı durum `unchanged`, farklı durum `changed` olur; eklenen/çıkan IP'ler ve değişen alanlar ayrı kaydedilir. Zaman, hata açıklaması ve not değişimi sahte yüzey değişikliği üretmez. Sertifikasız v0.17 sonuçları eski hash girdisiyle doğrulanır; yeni sertifika kanıtı görünür değişikliktir. Kısmi/başarısız kontrol de kaynağı ve sınırıyla kanıt olarak kalır, güvenlik veya kesinti kararı sayılmaz.

`surface list/show` salt okunur tutarlı anlık görüntüdür; ağ çağrısı, onarım veya kapsam değişikliği yapmaz. Sertifika bitiş uyarısı görünüm anında hesaplanır ve kanıtı değiştirmez. Şema 9→10 geçişi yedekten sonra üç yeni tabloyu boş oluşturur; eski veriden yetki uydurmaz. 0.18 veri tabanı şemasını değiştirmez. Backup/restore kapsam, olaylar, sonuçlar, sertifika kanıtı, özetler ve değişim kaydını birlikte taşır. Ayrıntılar [dış yüzey](decisions/0017-approved-surface-baseline.md) ve [sertifika kanıtı](decisions/0018-verified-certificate-evidence.md) kararlarındadır.

`SurfaceOverviewService`, `SurfaceOverviewRepository` sözleşmesinden aldığı tek anlık görüntüyü açıklanabilir ilişkilere dönüştürür. SQLite adaptörü kayıtlı varlığı, güncel kapsamı, son kök DNS/TLS, e-posta DNS ve sınırlı servis kontrolünü, son pasif keşif çalışmasını, aday durum toplamlarını ve sınırlı aday örneğini tek salt okunur transaction içinde okur. Uygulama katmanı `discovered_subdomain`, `resolves_to`, `presents_certificate`, `certificate_covers`, `uses_mail_exchange` ve `offers_tcp_service` ilişkilerini kaynak kanıt kimliği/zamanıyla hesaplar. Ayrı ilişki tablosu veya grafik veritabanı yoktur; append-only kanıtlar kaynak gerçek olarak kalır. `surface overview` ağ çağrısı ve yazma yapmaz, bozuk kanıtta kısmi ilişki yayımlamaz, ilişkiyi sahiplik veya güvenlik hükmüne dönüştürmez. Ayrıntılar [ilişki görünümü kararında](decisions/0024-stored-surface-relationship-overview.md) bulunur.

`SurfaceMailService`, aynı kayıtlı varlık ve açık `surface approve` kapsamını `MailDnsProbe` ile `SurfaceMailRepository` sözleşmelerine bağlar. `surface mail check` yalnız kök MX, kök TXT ve `_dmarc.kök` TXT için sabit Google DNS HTTPS sorguları yapar; TXT içinden yalnız SPF/DMARC sürüm etiketlerini seçer. DKIM seçicisi tahmin edilmez, SMTP/teslim deneyi veya alt ad genişletmesi yapılmaz. Üç sorgu bağımsızdır: tek hata diğer kanıtı silmez. Sonuç ağdan önce ve yazma transaction'ında kapsam doğrulamasından geçer; ortak yerel çalıştırıcı kilidini kullanır.

`surface_mail_checks` her kanonik kayıt kümesini, durum özetini ve `baseline/unchanged/changed` farkını eklemeli saklar. Değişim yalnız MX/SPF/DMARC durum ve kayıtlarından hesaplanır; zaman/not/hata metni sahte değişim üretmez. `missing/nxdomain` tamamlanmış gözlem, `failed` eksik sorgudur. Çoklu politika kaydı kanıt olarak kalır; güvenlik, teslimat, sahiplik veya yanlış yapılandırma hükmü verilmez. `surface mail show` salt okunurdur. Şema 12→13 geçişi tabloyu kurtarma yedeğinden sonra boş oluşturur. Ayrıntılar [e-posta DNS kararında](decisions/0022-approved-mail-dns-baseline.md) bulunur.

`SurfaceServiceScanService`, kayıtlı varlık ve etkin domain kapsamına ek olarak kesin genel IP ile görünür yetki gerekçesi ister. `BoundedServicePortProbe` Google DNS A/AAAA cevabında bu IP'yi arar; eşleşme yoksa veya herhangi bir özel/yerel adres varsa hedefe bağlanmaz. Eşleşmede yalnız belirtilen tek IP'nin sabit 10 TCP portuna, port başına bir saniye ve toplam 20 saniye içinde bağlantı dener. DNS sonrası işletim sistemi ad çözümlemesi, serbest port, UDP, banner, protokol verisi, ürün/sürüm veya dış tarama süreci yoktur.

`surface_service_checks` yetki gerekçesi, DNS kanıtı, kesin IP, açık/kapalı/belirsiz port durumları, politika sürümü, özet ve değişimi eklemeli saklar. `unknown` kapalı sayılmaz. Değişim DNS, adres, kontrol edilen IP ve port geçişlerini ayırır. Yazma transaction'ı kapsamı yeniden doğrular; arada kaldırılırsa sonuç yazılmaz. `surface services show` salt okunurdur. Şema 13→14 geçişi kurtarma yedeğinden sonra tabloyu boş oluşturur. Ayrıntılar [sınırlı servis kararı](decisions/0025-approved-pinned-service-inventory.md) içindedir.

`SurfaceDiscoveryService`, kayıtlı kök varlık, `DomainSource` ve ayrı `SurfaceCandidateRepository` sözleşmelerine bağlıdır. `surface discover`, seçilen adaptöre yalnız `%.kök` desenini verir ve doğrulanmış yanıttan kökün kesin altındaki kanonik adları seçer. Varsayılan crt.sh adaptörü sertifika kayıtlarını kullanır. İsteğe bağlı theHarvester adaptörü sabit commit'teki ayrı Python 3.14 ortamında yalnız Common Crawl ve Wayback Archive P0 kaynaklarını tek işçiyle çalıştırır; geçici HOME kullanır ve yalnız katı JSONL hostname kanıtını kabul eder. DNS, e-posta, kişi, screenshot, takeover ve doğrudan hedef işlemleri kapalıdır. Kökün kendisi ve kapsam dışı adlar aday olmaz; bulunan hedefe bağlanılmaz.

0.127.1 kurulum düzeltmesi PATH'teki `uv` aracına öncelik verir; yoksa proje
içindeki `.tools/uv/bin/uv` kullanılır. Yönetilen Python ve önbellek varsayılan
olarak `.tools` altında tutulur, açık ortam ayarları korunur. İki arşiv de
başarısızsa şema/kapsam doğrulamasından geçmiş kaynak adları, durumları ve
200 karakterle sınırlı durma nedenleri `SourceError` içinde korunur; ham
araç tanılaması aktarılmaz. Model, kayıt şeması ve başarılı/kısmi keşif
davranışı değişmez.

0.128.0, sabit üçüncü taraf dosyalarına dokunmadan arşiv bağlantısını ayrı XTI
işçisine taşır. İşçi kurulu upstream seçim/ayrıştırma yardımcılarını çağırır;
`archive_http` yalnız iki resmî HTTPS sunucusunu ve kayıtlı kök sorgusunu
kabul eder. HTTP/bağlantı/boş sonuç ayrımı, kaynak başına ayrı bütçe ve
devamlı sayfalama uygulanır. `p0-archives-v2` profilinde sınırda durma kısmi
sonuçtur; iki çalışmamış kaynak genel başarısızlık verir. Standart paket
kurulumu `.pth` üzerinden editable yükleme gerektirmez. Detaylar
[0126 numaralı karardadır](decisions/0126-bounded-archive-transport.md).

0.129.1 arşiv profili `p0-archives-v3`, kabul kapısı v4'tür. Common Crawl
istek aralığı yanıt bitişinden itibaren en az bir saniyedir. Bağlantı
hatasında bütçe/istek hakkı varsa tek tekrar 60 saniye sonra yapılır;
hak kalmadığında asıl hata nedeni korunur. Common Crawl'ın yıllık indeks
sorguları için 150, Wayback için bağımsız 90 saniye; süreç için 270 saniye
ayrılır. İstek/yanıt/sonuç sınırları ve şema değişmez. Önceki profilin
kanıtları korunur; yeni profil yeni kaynak özeti üretir. Gerekçe ve kapsam
[0128 numaralı karardadır](decisions/0128-commoncrawl-request-pacing.md).

`surface_candidates` güncel `pending/owned/rejected` durumunu ve kaynak gözlem aralığını; `surface_candidate_sources` sağlayıcı/kaynak/özet/ham ad/zaman kanıtını; `surface_candidate_events` ilk keşif ile bütün gerekçeli kullanıcı kararlarını tutar. Aday + kaynak özeti tekildir. Tekrar kaynak kullanıcı kararını sıfırlamaz; yeni pasif kanıt ilk/son görülme aralığını genişletir. Liste/ayrıntı tek salt okunur anlık görüntüdür. `owned` kararı varlık kaydı veya aktif kapsam oluşturmaz; hedef kontrolü için ayrı `assets add` ve `surface approve` gerekir.

`surface_discovery_runs`, her çağrının tamamlandı/kısmi/başarısız sonucunu, zamanını, kaynak kapsamını, uyarı/hata ve çıktı sayaçlarını ekleme sırasıyla saklar. Başarılı/kısmi çağrıda aday, yeni kaynak kanıtı, ilk aday bildirimi ve çalışma özeti tek yazma transaction'ındadır. Başarısız kaynak çağrısı yalnız hata taşıyan çalışma kaydı oluşturur. `surface runs/run` salt okunurdur. Yeni aday için `surface_candidate_notifications` tablosuna tek bildirim yazılır; tekrar veya yeni sertifika bunu çoğaltmaz.

`SurfaceWatchService`, aynı keşif servisini monotonic süre, tur ve bekleme sınırları içinde tekrarlar. Kalıcı ikinci bir oturum modeli oluşturmaz: tamamlanan her tur zaten `surface_discovery_runs` içinde bağımsız ve atomik bir kanıttır. Böylece `Ctrl+C` veya süreç kapanışı önceki turları bozmaz; o anda bitmemiş kaynak çağrısı için sonuç uydurulmaz. Terminal bütün döngü boyunca mevcut yerel çalıştırma kilidini tutar, fakat ağ ve bekleme sırasında SQLite yazma transaction'ı açık değildir. Kaynak hatası sonraki turu engellemez. İzleme terminal açıkken çalışır; arka plan hizmeti, takvim zamanlayıcısı veya yeniden açılışta otomatik devam değildir.

`SurfaceMonitorService`, kullanıcı tarafından seçilen `web`, `mail` ve isteğe bağlı `services` çalıştırıcılarını tek ön plan döngüsünde düzenler. Uygulama katmanı yalnız tur, süre, sıra ve sonuç özetini bilir; her çalıştırıcı mevcut `SurfaceService`, `SurfaceMailService` veya `SurfaceServiceScanService` doğrulama ve kayıt yolunu kullanır. Böylece kapsam, kesin IP, transaction, fark ve bildirim kuralları çoğaltılmaz. Bütün hedefler ve sınırlar ağdan önce hazırlanır; terminal döngü boyunca ortak yerel kilidi tutar, fakat beklerken SQLite transaction'ı açık değildir. Süre bütçesi yeni kontrol başlamasını engeller, başlamış sınırlı kontrolü yarıda kesmez. `Ctrl+C` yayılır; tamamlanan kanıtlar kalır.

İzleme oturumu için yeni tablo yoktur. Tek final rapor geçicidir; kalıcı geçmiş, her kontrol ailesinin mevcut eklemeli kanıtı ve ortak `inbox` bildirimidir. Bu seçim kişisel kullanımda ikinci bir oturum kaydını ve migration yükünü önler. Süreç kapanınca otomatik devam, işletim sistemi zamanlayıcısı, daemon veya dış teslim yoktur. Ayrıntılar [ön plan dış yüzey izleme kararındadır](decisions/0027-bounded-foreground-surface-monitor.md).

`SurfaceFreshnessService`, `SurfaceFreshnessRepository` üzerinden etkin kapsam ile son web, posta ve servis kanıtını tek salt-okunur anlık görüntüde alır. Aynı depo anlık görüntüsü maruziyet görünümü için son CNAME kanıtını ve son pasif keşif çalışmasını da taşır; güncellik servisi kendi sabit üç kanıt ailesi sözleşmesini korur. İlişki görünümünün aday listesi veya ağ adaptörleri bu yola dahil değildir. Uygulama katmanı enjekte edilen UTC saatle kanıt yaşını hesaplar; seçilen eşikten küçük yaş `current`, eşit veya büyük yaş `stale`, kanıt yokluğu `never`, okunamayan ya da gelecekteki zaman `clock_error` olur. Kontrolün `complete/partial/failed` sonucu yaştan ayrı tutulur; güncel fakat eksik kanıt yanlışlıkla tam sayılmaz.

`surface freshness` ağ isteği, yazma, onarım veya zamanlama yapmaz. Eşik yalnız rapor politikasıdır ve saklanan kanıtı değiştirmez. Bu özellik kendi tablosunu eklemez; güncel düzen şema 35'tir. Ayrıntılar [dış yüzey kanıt güncelliği kararındadır](decisions/0028-surface-evidence-freshness.md).

`SurfaceExposureService`, aynı `SurfaceFreshnessRepository` anlık görüntüsünü kullanarak son pasif keşif, web, posta, servis ve CNAME kanıtının kapsam durumunu; son dört aktif kanıt ailesinden de geçici inceleme adaylarını üretir. Pasif `complete+0`, yalnız o kaynak yanıtında aday görülmediğini; `partial+0` bilinmeyen kapsamı; `failed` kaynak hatasını anlatır. TLS aşaması tamamlanamaması kesin nedeni bilinmeyen bir adaydır; MX kabul eden domainde eksik/çoğul SPF-DMARC doğrudan DNS olgusu olarak, seçili açık uzak erişim ve alternatif web portları yalnız TCP erişilebilirliği olarak açıklanır. `present + target nxdomain` CNAME kanıtı yalnız kesin olmayan sarkan hedef adayıdır. Her aday kanıt kimliği, zaman/güncellik, olgu, sınır ve insan sonraki adımını taşır.

Her güncel olmayan veya tamamlanmamış kapsam öğesi yalnız öneri olan kesin terminal komutunu taşır; etkin kapsam yoksa kapsam onayı ayrı ilk adım olur. Uygulama katmanı içerik veya banner bulunmadığında açık panel kararı üretmez. CNAME hedef NXDOMAIN olsa da sağlayıcı alınabilirliği veya gerçek takeover sonucu üretmez; delegasyon ve sağlayıcıya özgü doğrulama açık kalır. `surface exposures` ağ, yazma, sahiplenme, exploit veya onarım yapmaz. Ayrıntılar [açıklanabilir maruziyet adayları](decisions/0032-explainable-surface-exposure-candidates.md), [CNAME hedef kanıtı](decisions/0033-approved-cname-target-evidence.md) ve [birleşik kanıt boşlukları](decisions/0092-unified-surface-evidence-gaps.md) kararlarındadır.

`TechnologyService`, aynı salt-okunur anlık görüntüden yalnız son servis kanıtındaki `open` portları kullanım ipucuna dönüştürür. İpucu `confidence=hint` ve `detection_method=tcp_connect_only` taşır; üretici, ürün ve sürüm bilinmiyorsa `null`, CVE eşleştirme uygunluğu `false` kalır. Kapalı veya belirsiz port teknoloji yokluğu sayılmaz. `surface technologies` ağ, banner/protokol konuşması, zafiyet taraması veya yazma yapmaz; kendi tablosunu eklemez. Ayrıntılar [teknoloji ipucu sınırı kararındadır](decisions/0034-conservative-technology-hints.md).

`SurfaceCnameService` kayıtlı tam varlığı ve etkin `SurfaceScope` kaydını ağdan önce doğrular. `GoogleCnameDnsProbe`, sabit Google DNS JSON uç noktasına doğrulanmış bağlantıyla yalnız CNAME ve terminal hedef A/AAAA sorgusu yapar. CNAME zinciri sekiz adım, adresler 16 kayıtla sınırlıdır; ilgisiz, döngülü, çelişen veya kesilmiş yanıt başarısızdır. Hedef siteye bağlantı, HTTP, banner, içerik veya sağlayıcı kaynak işlemi yoktur.

`SQLiteSurfaceCnameRepository` kapsamı yazma transaction'ında yeniden doğrular ve her sonucu özet/değişim alanlarıyla eklemeli saklar. `surface cname show` salt okunurdur. Şema 15→16 geçişi önce kurtarma yedeği yayımlar, boş `surface_cname_checks` tablosunu işlemsel ekler; eski veriden kanıt uydurmaz.

`SurfaceInventoryService`, `SurfaceInventoryRepository` portundan kök kapsamını, aday durum toplamlarını ve her adayın olası kayıtlı varlık/kapsam bağlantısını tek anlık görüntüde alır. Uygulama katmanı pasif `pending/owned/rejected` kararını, `registered/unregistered` varlık durumunu ve `active/revoked/not_approved/not_applicable` kapsam durumunu birbirine dönüştürmeden raporlar. Sonraki adım alanı yalnız açıklamadır; yazma komutu değildir.

SQLite adaptörü adayları domain değerinden mevcut varlık kaydına, oradan varsa kapsam kaydına salt okunur transaction içinde bağlar. Filtre ve sınır yalnız gösterilen aday satırlarına uygulanır; kökün bütün adaylarına ait durum ve katman sayaçları aynı anlık görüntüde kalır. `surface inventory` ağ, karar, kayıt, kapsam onayı veya onarım yapmaz. Bu özellik kendi tablosunu eklemez; güncel düzen şema 35'tir. Ayrıntılar [katmanlı dış yüzey envanteri kararındadır](decisions/0029-layered-surface-inventory.md).

`SurfaceDiscoveryStatusService`, mevcut `SurfaceCandidateRepository` sözleşmesinden son keşif çalışmasını alır ve kaynak durumunu veri sonucundan ayırır. Uyarısız `complete` çalışma kaynak yanıtının tamamlandığını; `partial` eksik kapsamı; `failed` kaynak erişimi veya doğrulama başarısızlığını; kayıt yokluğu ise hiç çalışılmadığını anlatır. Aday sayısı ayrı yorumlanır: yalnız `complete+0` tamamlanmış boş sonuçtur; `partial+0` veya `failed` veri yokluğu değildir.

Servis son çalışma zamanını enjekte edilen UTC saat ve kullanıcı eşiğiyle `current/stale/clock_error/never` olarak sınıflandırır. `surface discovery-status` yeni kaynak çağrısı, hedef bağlantısı, onarım veya yazma yapmaz. Mevcut keşif geçmişi kaynak gerçek olarak kalır; bu özellik kendi tablosunu eklemez ve güncel düzen şema 35'tir. Ayrıntılar [pasif kaynak durumu kararındadır](decisions/0030-passive-discovery-source-status.md).

Şema 10→11 geçişi üç pasif keşif tablosunu; şema 11→12 geçişi iki çalışma/bildirim tablosunu kurtarma yedeğinden sonra boş oluşturur. Şema 50→51 yalnız kaynak ve çalışma provider denetimlerini `theharvester` için genişletir; crt.sh kanıtı ile çalışma sıra numaralarını korur ve yeni geçmiş uydurmaz. Diğer dış yüzey geçişleri ilgili sürüm kararlarında kayıtlıdır. Backup/restore bütün bu kayıtları birlikte taşır. Ayrıntılar [dış yüzey](decisions/0017-approved-surface-baseline.md), [CNAME hedef kanıtı](decisions/0033-approved-cname-target-evidence.md) ve [theHarvester arşiv kararı](decisions/0117-bounded-theharvester-archive-discovery.md) dahil ilgili karar kayıtlarındadır.

## Resmî zafiyet kataloğu

`KevCatalogService`, yalnız `KevSource` ve `KevRepository` portlarına bağlıdır. `CisaKevSource`, sabit resmî CISA HTTPS JSON adresini TLS doğrulamasıyla, yönlendirmesiz ve sınırlı olarak okur. Yanıt 16 MiB ve 10.000 kayıtla sınırlıdır; sıkıştırma, beklenmeyen içerik türü, yinelenen JSON anahtarı/CVE, bozuk tarih veya tutarsız toplam bütün anlık görüntüyü reddeder.

`SQLiteKevRepository` tam anlık görüntüyü tek yazma transaction'ında uygular. Güncel kayıtlar `kev_entries`, ekleme/değişme/katalogdan çıkma/yeniden girme olayları `kev_entry_events`, başarılı veya başarısız kaynak denemeleri `vulnerability_source_runs` içinde tutulur. Kaynak hatası önceki kataloğu değiştirmez. Katalogdan çıkan CVE silinmez, etkisiz işaretlenir. Durum JSON'u ve SHA-256 özeti okuma sırasında yeniden doğrulanır.

Terminal güncellemeden önce mevcut şemayı ve ortak yerel çalıştırma kilidini doğrular; ağ beklerken SQLite transaction'ı açık kalmaz. `vuln status/list/show` salt okunurdur. KEV kaydı izlenen varlığın etkilendiğine dair kanıt değildir; ürün/sürüm eşleştirmesi, CVSS, EPSS ve risk kararı ayrı katmanlardır. Şema 16→17 geçişi önce yedek alır ve boş zafiyet tabloları oluşturur. Ayrıntılar [resmî CISA KEV kararındadır](decisions/0035-official-cisa-kev-catalog.md).

`FirstEpssSource` sabit günlük FIRST gzip dosyasını yalnız aynı resmî HTTPS sunucusu içindeki yönlendirmelerle ve sıkıştırılmış/açılmış boyut sınırlarıyla alır. Metadata, model, puan tarihi, CSV başlığı, CVE ve `[0,1]` değerleri tam dosya kabulünden önce doğrulanır. `SQLiteEpssRepository` güncel tam kataloğu tek transaction'da uygular; kaynak hatası önceki puanları korur. Günlük her-CVE zaman serisi disk büyümesini sınırlamak için yerelde çoğaltılmaz, kaynak çalışma geçmişi tutulur. EPSS 30 günlük nüfus düzeyi olasılık tahminidir; önem, CVSS, KEV, tam risk veya varlık maruziyeti değildir. Şema 17→18 geçişi önce yedek alır ve boş EPSS tablosu oluşturur. Ayrıntılar [FIRST EPSS kararındadır](decisions/0036-first-epss-current-catalog.md).

`NvdCveSource` yalnız açıkça istenen CVE için NVD API 2.0'ın sabit resmî HTTPS uç noktasına tek istek gönderir. Sayfa/kimlik/zaman, CVSS, CWE ve referans sınırları bütün kayıt kabulünden önce doğrulanır; NVD ve ikincil sağlayıcı skorları ayrı tutulur. `SQLiteNvdRepository` normalleştirilmiş özeti ve tam kanonik kaynak nesnesini atomik günceller; yalnız ekleme/değişme olaylarında tam önceki kaynak kanıtı eklemeli geçmişe girer. Bu tam NVD aynası değildir; gizli toplu indirme yapmaz. CVSS, EPSS, KEV ve varlık maruziyeti ayrı anlamlardır. Şema 18→19 geçişi önce yedek alır ve boş NVD tabloları oluşturur. Ayrıntılar [NVD tek-CVE kararındadır](decisions/0037-nvd-single-cve-context.md).

`OsvAdvisoryPreviewService`, yalnız `OsvAdvisorySource` portuna bağlı yazmasız bir araştırma akışıdır. `OsvDevAdvisorySource`, açıkça seçilen tek CVE için sabit OSV.dev HTTPS uç noktasını yönlendirmesiz, 30 saniye ve 8 MiB sınırıyla okur; JSON kimliği, CVE bağı, zamanlar, paket/aralık olayları ve başvuruların tamamını doğrular. Terminal görünümü paketleri ve `ADVISORY` başvurularını ayrı 1–200 sınırlarıyla kesebilir. Önizleme veri klasörü, veritabanı, maruziyet kararı veya destek kanıtı oluşturmaz; OSV bir toplayıcıdır ve eksik paket bağlamı “etkilenmiyor” sayılmaz. Şema 22 değişmez. Ayrıntılar [OSV duyuru önizlemesi kararındadır](decisions/0051-explicit-osv-advisory-preview.md).

`OsvAdvisoryEvidenceService`, maruziyet okuma, OSV kaynağı ve destek kanıtı yazma portlarını sırayla koordine eder. Tür, HTTPS başvurusu ve açıklama önce doğrulanır; incelemenin CVE kimliği yerelden salt okunur alınır; güncel OSV kaydı ağ transaction'ı olmadan getirilir. Yalnız tam adres güncel `ADVISORY` kümesinde bulunursa mevcut destek kanıtı deposuna yazılır. Kaynak hatası, bilinmeyen inceleme veya listede olmayan adres kalıcı değişiklik üretmez. OSV üyeliği içerik/sahiplik/maruziyet hükmü değildir ve kanıt önceliği değiştirmez. Ayrıntılar [insan seçimiyle OSV kanıtı kararındadır](decisions/0052-human-selected-osv-advisory-evidence.md).

`VendorAdvisoryPreviewService`, doğrudan üretici kaynağını küçük `VendorAdvisorySource` portu arkasında tutar. `CsafVexSource` ortak taşıma ve ayrıştırmayı; sağlayıcı politikası sabit kaynak kimliği, beklenen yayımcı ve CVE'den türetilen resmî HTTPS yolunu taşır. `RedHatCsafVexSource` CVE yılını, `SuseCsafVexSource` ise 2023 öncesi CVE'ler için SUSE geri-doldurma dizinini kullanır. Her ikisi yönlendirmesiz, 30 saniye ve 16 MiB sınırıyla çalışır; CSAF VEX 2.0, tek CVE, belge zamanları/geçmişi, ürün ağacı, çelişmeyen ürün durumları ve düzeltme hedefleri tümden doğrulanır. Görünüm durum sayılarını ve sınırlı örnekleri gösterir; yazma veya sağlayıcı dışına hüküm taşıma yoktur. SUSE dilimi yalnız önizlemedir; Red Hat'e özel kesin RPM kanıt akışı SUSE'ye uygulanmaz. Ayrıntılar [Red Hat VEX](decisions/0053-direct-red-hat-csaf-vex-preview.md) ve [ikinci resmî SUSE VEX](decisions/0061-second-official-suse-csaf-vex-source.md) kararlarındadır.

`VulnerabilityContextService`, tek bir CVE'nin mevcut KEV, EPSS ve NVD kayıtlarını `VulnerabilityContextRepository` portundan ister. SQLite adaptörü üç tabloyu tek salt-okunur transaction içinde okur; ağ çağrısı veya yazma yapmaz. Eksik kaynak açıkça eksik kalır ve güvenli/sıfır risk olarak yorumlanmaz. Saklı kayıtlardan herhangi birinin bütünlük doğrulaması başarısızsa görünümün tamamı güvenli biçimde durur. Birleştirme yeni tablo veya kopya üretmez; üç kaynağın farklı anlamları korunur ve varlık maruziyeti çıkarılmaz. Ayrıntılar [birleşik zafiyet bağlamı kararındadır](decisions/0038-unified-vulnerability-context.md).

`NvdEnrichmentPlanService`, kullanıcıdan yalnız EPSS eşiği ve en fazla 100 sonuçluk sınır alır. SQLite plan adaptörü tek salt-okunur transaction içinde NVD kaydı olmayan güncel KEV ve eşik üstü EPSS kimliklerini birleştirir; KEV adaylarını önce gösterir ve aynı CVE'yi tekilleştirir. Olasılık karşılaştırması 18 ondalık basamağa kadar sabit genişlikli anahtarla yapılır; kayan nokta sınır hatası seçim politikasını değiştirmez. Seçilen kaynak satırları mevcut bütünlük doğrulamasından geçer. Plan ağ çağrısı, iş kaydı veya indirme yapmaz ve varlık maruziyeti değildir. Ayrıntılar [NVD zenginleştirme planı kararındadır](decisions/0039-offline-nvd-enrichment-plan.md).

`NvdEnrichmentBatchService`, aynı plan portunu ve tek-CVE NVD kaynak/depo portlarını kullanır. Açık terminal komutu bir seferde en fazla beş adayı işler. Anahtarsız istekler ardışıktır ve her kaynak çalışmasının bitişinden sonra en az 6,5 saniye beklenir; önceki süreçteki son çalışma da kaynak geçmişinden okunur. Ortak süreç kilidi bütün planlama/bekleme/ağ/yazma dilimini kapsar. İlk başarısız kaynak çalışması kaydedilir ve döngü durur. Başarılar CVE bazında atomik olduğu için süreç kesilirse sonraki plan yalnız eksikleri seçer. Ayrı batch tablosu veya gizli retry yoktur. Ayrıntılar [sınırlı NVD plan yürütme kararındadır](decisions/0040-bounded-nvd-plan-execution.md).

`TrackedNvdRefreshService`, mevcut insan maruziyetleriyle ilişkili NVD kayıtlarının kaynak güncelliğini ayrı plan portundan okur. SQLite adaptörü kapanmış/bastırılmış kapsam politikasını uygular, bütün ilgili maruziyet ve bağlı ürün/NVD kayıtlarını doğrular, aynı CVE'yi tekilleştirir ve son başarılı NVD kontrolünü kullanıcı eşiğiyle `current/stale/clock_error` olarak ayırır. Plan salt okunurdur. Açık yenileme yalnız `stale` ilk beş CVE'yi mevcut `NvdCatalogService` üzerinden alır; önceki süreç dahil 6,5 saniyelik anahtarsız aralık, CVE başına atomik kayıt ve ilk hatada durma korunur. İnsan kararı yazılmaz; kaynak özeti değişikliği yeniden değerlendirme planına bırakılır. Yeni tablo yoktur. Ayrıntılar [maruziyet kapsamlı NVD yenileme kararındadır](decisions/0064-exposure-scoped-official-nvd-refresh.md).

`NvdWindowService`, açık başlangıç/bitiş ve sayfa boyutunu `NvdWindowRepository` üzerinden önce salt okunur planlar. En fazla yedi günlük pencere ve 100 kayıtlık tek sayfa, `NvdWindowSource` tarafından resmî API'nin `lastModStartDate/lastModEndDate/startIndex/resultsPerPage` alanlarıyla alınır. `SQLiteNvdWindowRepository` kaynak çalışma kaydını, bütün CVE ekleme/değişikliklerini ve sonraki sıra imlecini aynı yazma transaction'ında uygular. Kaynak hatası denetlenir fakat imleç ilerlemez; toplam sonuç çalışma ortasında değişirse olası sayfa kayması gizlenmez. Tamamlanan plan yeni kaynak çağrısı yapmaz. Ayrıntılar [devam edilebilir NVD tarih penceresi kararındadır](decisions/0066-resumable-nvd-date-windows.md).

Aynı servis bütün kalıcı pencereleri durum filtresiyle listeler, tam kimliği ve yeniden başlatma geçmişini gösterir ve en fazla 366 günlük istek için kapsama/boşluk hesabı yapar. Yalnız tamamlanmış pencereler kapsama sayılır; örtüşen veya uç uca gelen tamamlanmış aralıklar birleştirilir. Açık gerekçeli yeniden başlatma önceki durumu eklemeli olaya kaydedip yalnız pencere imlecini sıfırlar; CVE, NVD değişiklik olayı ve kaynak çalışma geçmişini korur. Saat son kalıcı ilerleme zamanından geriyse yazım reddedilir. Liste, ayrıntı ve kapsama komutları ağsız ve salt okunurdur. Ayrıntılar [NVD pencere kapsamı ve denetlenebilir yeniden başlatma kararındadır](decisions/0067-nvd-window-coverage-and-audited-restart.md).

`gap_plan`, kapsama raporundaki her açık yarı-açık aralığı kronolojik, en fazla yedi günlük adaylara böler ve gösterilecek ilk 1–100 adayı mevcut pencere planı okumasından geçirir. Böylece aynı tam kimlikteki hazır veya başarısız pencerenin ilerlemesi görünür; tamamlanmış zaman dilimleri aday olmaz. Toplam aday sayısı limitten bağımsız hesaplanır. Akış kaynak adaptörüne ulaşmaz ve depo sözleşmesinin hiçbir yazma yöntemini çağırmaz. Ayrıntılar [salt-okunur NVD boşluk planı kararındadır](decisions/0068-read-only-nvd-gap-plan.md).

`gap_fetch`, kilit altında güncel boşluk planının ilk 1–3 adayını seçer ve her biri için `fetch` akışını yalnız bir kez çalıştırır. Her tur kalıcı son NVD çalışmasından en az 6,5 saniyelik aralığı yeniden hesaplar. Kaynak hatası başarısız çalışma kaydıyla imleci korur ve döngüyü keser; sonraki adaylara ulaşılmaz. Sonuç hem önceki hem güncel planı taşıdığı için tamamlanan pencere, kısmi imleç ve denenmeyen aday ayrımı görünür. Ayrıntılar [sınırlı NVD boşluk yürütmesi kararındadır](decisions/0069-bounded-nvd-gap-execution.md).

`operations`, istenen dönemle kesişen en fazla 10.000 pencereyi ve bunların yeniden başlatma olay sayısını tek salt-okunur transaction'da alır. Aynı doğrulanmış satır kümesinden durum sayıları, son güncelleme sırası ve kapsama üretilir. Hata öncelikle `attention`, ardından tam kapsama `covered`, hazır iş `in_progress`, yalnız açık zaman `gaps` ve kayıtsız dönem `no_activity` olur. Görünüm kaynak çağrısı veya onarım yapmaz. Ayrıntılar [NVD pencere operasyon anlık görüntüsü kararındadır](decisions/0070-nvd-window-operations-snapshot.md).

`VendorSourceEvaluationService`, sabit `official-vendor-source-gate-v1` profilinde resmî üretici, ücretsiz/anahtarsız erişim, yapılandırılmış biçim, tek-kayıt sınırı, ürün bağlamı ve açık yeniden kullanım koşullarını zorunlu kapılar olarak taşır. Kanıt açıklamaları ile resmî HTTPS bağlantıları paketlenmiştir; çalışma anında ağ veya depolama kullanılmaz. Tek seçilen kaynak Canonical Ubuntu OSV'dir; diğer karar ve engeller görünür kalır. Ayrıntılar [resmî üretici zafiyet kaynağı kapısı kararındadır](decisions/0071-official-vendor-source-gate.md).

`UbuntuOsvAdvisorySource`, CVE yılından Canonical deposundaki tek `UBUNTU-CVE` raw JSON yolunu üretir. Yönlendirmesiz TLS, 30 saniye, 8 MiB, identity ve JSON/text sınırlarından sonra ortak katı OSV ayrıştırmasını kullanır; tam Ubuntu kayıt/upstream bağı ile yalnız `Ubuntu:*` ekosistemlerini ayrıca zorunlu kılar. `UbuntuOsvPreviewService` ortak görünümü üretici kapsam notlarıyla döndürür; depoya bağlı değildir. Ayrıntılar [Canonical Ubuntu OSV önizleme kararındadır](decisions/0072-canonical-ubuntu-osv-preview.md).

`UbuntuPackageMatchService`, CVE ile açıkça verilen tam Ubuntu ekosistemi, Debian kaynak paket adı ve sürümü ağdan önce doğrular; aynı Canonical adaptörü üzerinden tam tek kaydı alır. Tam yayın+paket bağı yok/tekil/çoğul olarak ayrılır. Yalnız `ECOSYSTEM`, `introduced: 0`, en fazla bir `fixed` ve `last_affected` olmayan aralık karşılaştırılır. `compare_debian_versions` haricî `dpkg` kullanmadan epoch, upstream, revision, sayısal parça ve tilde sırasını uygular. Sonuç geri çekilmiş/listelenmiyor/fixed yok/önce/eşit/sonra durumlarından biridir; depo portu, yazma veya maruziyet kararı yoktur. Ayrıntılar [açık Ubuntu paket sürümü karşılaştırma kararındadır](decisions/0073-explicit-ubuntu-package-version-comparison.md).

`UbuntuAssetPackageService`, kayıtlı varlığa tam Ubuntu OSV ekosistemi, binary paket/sürüm/mimari ve kaynak paket/sürüm bağını `UbuntuAssetPackageRepository` portuyla kaydeder. SQLite adaptörü güncel kayıt ve `added/updated/reactivated/revoked` olayını aynı transaction'da tutar; liste/ayrıntı bütün seçili geçmişi doğrular ve bozuk gizli olayda kısmi görünüm vermez. `UbuntuInventoryMatchService` yalnız etkin kaydın doğrulanmış kaynak sürümünü mevcut `UbuntuPackageMatchService` içine verir; binary sürüm karşılaştırmaya katılmaz. Eşleştirme yazmaz, maruziyet veya güvenli sonucu üretmez. Şema 31→32 doğrulanmış yedekten sonra iki tabloyu boş oluşturur. Ayrıntılar [doğrulanmış Ubuntu paket envanteri kararındadır](decisions/0074-verified-ubuntu-binary-source-inventory.md).

`UbuntuInventoryScanService`, isteğe bağlı varlık filtresini ve 1–500 görünüm sınırını ağdan önce doğrular. Depo portu en fazla 10.000 etkin paket ile bunlara bağlı 100.000 olayı tek salt-okunur anlık görüntüde tümden doğrular; görünüm limitinin arkasındaki bozuk kanıt da bütün taramayı durdurur. Boş kapsam kaynak çağırmaz. Dolu kapsam tek Canonical anlık görüntüsünü alır, ortak `compare_ubuntu_package_snapshot` işleviyle bütün source sürümlerini karşılaştırır, durum sayaçlarını bütün envanterden hesaplar ve yalnız görünümü keser. Yazma, otomatik maruziyet veya zamanlama yoktur; şema 32 değişmez. Ayrıntılar [tek-kayıtlı Ubuntu envanter taraması kararındadır](decisions/0075-single-fetch-ubuntu-inventory-scan.md).

`UbuntuExposureEvidenceService`, maruziyet ve etkin Ubuntu paketini ağdan önce okuyup aynı varlık bağını zorunlu kılar; CVE'yi maruziyet kaydından alır ve güncel Canonical eşleşmesini yeniden hesaplar. Yalnız tek `affected` yayın+kaynak paket bağına dayanan dört sürüm durumu seçilebilir; `not_listed` ve `record_withdrawn` kalıcı kanıt değildir. `UbuntuExposureEvidenceRepository` portunun SQLite uygulaması maruziyet/CVE/varlık bağını ve paket anlık görüntüsü SHA-256 özetini `BEGIN IMMEDIATE` içinde yeniden doğrular. Genel `vulnerability_exposure_evidence` tablosuna `package_inventory` türünde CVE, paket kimliği, paket özeti, Canonical içerik özeti ve durumdan oluşan kanonik başvuruyu yazar; ayrı şema oluşturmaz. İnsan kararı veya olay geçmişi değişmez. Ayrıntılar [insan seçimiyle Ubuntu destek kanıtı kararındadır](decisions/0076-selected-ubuntu-exposure-evidence.md).

`UbuntuEvidenceCheckService`, genel kanıt kaydındaki sürümlü `ubuntu-osv-v1` başvurusunu kanonik olarak ayrıştırır; kanıtın `package_inventory` türünü, maruziyet CVE'sini ve paket-varlık bağını doğrular. Etkisiz kanıt/pakette dış kaynak çağırmaz. Etkin kayıtta `UbuntuInventoryMatchService` ile güncel Canonical sonucunu alır ve paket kaydını kaynak dönüşünden sonra yeniden okuyarak kontrol sırasındaki değişimi görünür kılar. Durumlar kaynak özeti, paket özeti, kayıtlı/güncel eşleşme ve bağ varlığına göre ayrılır; hiçbir depo yazımı yoktur. Genel kanıt ekleme servisi ayrılmış öneki kabul etmez. Ayrıntılar [Ubuntu kanıt güncellik kontrolü kararındadır](decisions/0077-ubuntu-evidence-currency-check.md).

`UbuntuEvidencePlanService`, SQLite adaptörünün tek anlık görüntüde doğruladığı bütün etkin `ubuntu-osv-v1` kanıtlarını paket ve maruziyet portları üzerinden yeniden bağlar; yerel paket özetini kayıtlı özetle karşılaştırır ve etkisiz/değişmiş/aynı durumlarını bütün kapsam için sayar. `UbuntuEvidenceScanService`, plan görünümünü en fazla 20 kayıtla sınırlar ve tekil kontrol servisini CVE anahtarlı bellek içi kaynak önbelleği üzerinden çağırır. Önbellek yalnız aynı komut ömründedir; başarısız kaynağı kalıcı başarı saymaz. Plan ve tarama yazmaz; şema 32 değişmez. Ayrıntılar [toplu Ubuntu kanıt denetimi kararındadır](decisions/0078-bounded-ubuntu-evidence-scan.md).

`CtiIndicatorService`, gösterge türünü ve değerini domain/IP/URL/hash kurallarıyla kanonikleştirir; kaynak adı/başvurusu, 0–100 güven, açıklama, geçerlilik ve gözlem zamanını `CtiIndicatorRepository` portuna iletir. SQLite adaptörü tek kanonik göstergeyi her `source_name + source_reference` iddiasından ayırır; ilk/son görülme aralığı ile `added/observed/updated/reactivated/revoked` olayını aynı transaction'da saklar. Aynı kaynak ve aynı gözlem idempotenttir. Liste yalnız sorgu anında geçerli iddiası olanları varsayılan gösterir; ayrıntı görünüm sınırı arkasındaki bütün bağlı kayıtları güvenli üst sınıra kadar doğrular. Okumalar ağsız ve salt okunurdur; güven puanı zararlılık veya varlık etkisi değildir. Şema 32→33 doğrulanmış yedekten sonra üç tabloyu boş oluşturur. Ayrıntılar [kaynaklı yerel IOC yaşam döngüsü kararındadır](decisions/0079-sourced-local-ioc-lifecycle.md).

`StixExportService`, aynı `CtiIndicatorRepository` portundan sorgu anında geçerli kaynak iddialarının tam ve sınırlı anlık görüntüsünü alır. Domain/IP/URL/hash türleri STIX 2.1 Indicator pattern'lerine; yerel IOC UUID'si kararlı Indicator kimliğine; kaynak güveni, zamanları ve başvuruları standart alanlara çevrilir. `SQLiteCtiIndicatorRepository.export_snapshot`, en fazla 50.000 IOC ve 50.000 bağlı iddiayı tek salt-okunur transaction'da doğrular; kapsam taşarsa veya ilgili kayıt bozuksa kısmi anlık görüntü vermez. `stix_json` adaptörü en fazla 32 MiB JSON'u aynı klasörde özel geçici dosyaya yazıp fsync sonrasında üzerine yazmayan atomik bağlantıyla yayımlar. İlk dilim CTI varlık/ilişkisi, içe aktarma, TLP ve TAXII içermez; ağ/veritabanı yazımı veya tehdit hükmü üretmez ve şema 38'i değiştirmez. Ayrıntılar [sınırlı STIX 2.1 IOC dışa aktarma kararındadır](decisions/0088-bounded-stix-ioc-export.md); 50.000 kayıt değişikliği [çok kaynaklı IOC kararında](decisions/0090-bounded-multi-source-ioc-feeds.md) belgelenmiştir.

`WebhookService`, birleşik `NotificationRepository` portundan açıkça seçilen bildirimin kanıtını okur ve hedefe özgü değişmez kanonik JSON teslimi oluşturur. `WebhookRepository`, hedef yaşam döngüsü, hedef+bildirim tekilliği, gövde SHA-256 bağı, durum özeti ve sıralı denemeleri transaction'larla korur; ağ çağrısı sırasında yazma transaction'ı açık değildir. Her deneme UTC zaman damgası ve ham gövde üzerinde HMAC-SHA256 ile imzalanır. `SafeHttpsWebhookSender`, HTTPS/443 hedefinin bütün DNS sonuçlarını genel adres politikasıyla doğrular, seçilen sayısal IP'ye doğrudan bağlanırken TLS SNI/sertifika adını özgün host ile doğrular; proxy, redirect ve düz metin geri dönüşü kullanmaz. Tam URL ve sır çıktı modellerinde bulunmaz; sır 0600 dosyadan alınır fakat kişisel tehdit modelinde SQLite/yedek içinde base64 olarak saklandığı açıkça belgelenir. Otomatik abonelik/worker ve çok kiracılı sır kasası yoktur. Ayrıntılar [açık seçimli imzalı webhook kararındadır](decisions/0089-explicit-signed-webhook-outbox.md).

`CtiFeedService`, yalnız açık senkron komutunda `CtiFeedSource` portundan tam snapshot alır; `SourceError` durumunu boş başarıya çevirmeden başarısız çalışma olarak depoya iletir. `FeodoTrackerSource`, sabit saldırgan-olmayan 30 günlük JSON adresini yönlendirmesiz ve boyut/kayıt sınırlı alır, bütün alanları katı doğrular ve IP başına satırları deterministik birleştirir. `CertPlWarningSource`, CERT Polska'nın son-ay etkin domain listesini sabit yönlendirmesiz HTTPS üzerinden alır; metin başlığını, snapshot zamanını, kanonik domainleri ve tekrarları bütün liste kabulünden önce doğrular. `SQLiteCtiFeedRepository`, sabit kaynak politikasıyla kaynak kimliği/türü/güven/zaman/geçmiş davranışını ayırır; aynı kanonik IOC üzerindeki bağımsız iddiaları birbirini ezmeden saklar. Yalnız başarılı tam snapshot eksik kaynak üyeliğini geri çeker. CERT tekrarında değişmeyen üyelikler için çalışma–öğe satırı çoğaltılmaz; çalışma özeti ve içerik SHA-256 kanıtı korunur. Ransomware için eklenen şema 40 tablolarından bağımsızdır. Ayrıntılar [Feodo kararında](decisions/0080-audited-feodo-complete-snapshot.md) ve [çok kaynaklı IOC kararında](decisions/0090-bounded-multi-source-ioc-feeds.md) bulunur.

`CtiKnowledgeService`, CTI varlık türünü/adını, alternatif adları, kaynak iddiasını ve varlık/IOC hedefli ilişkiyi domain kurallarıyla doğrulayıp `CtiKnowledgeRepository` portuna iletir. SQLite adaptörü kanonik tür+ad varlığını kaynak iddialarından; kaynak–ilişki–hedef kenarını ilişki iddialarından ayırır. Her iddia ilk/son gözlem ve `added/observed/updated/reactivated/revoked` olay geçmişi taşır; bir kaynağın geri çekilmesi diğerini etkilemez. Çelişen atıflar ayrı kenarlar olarak korunur, alternatif adlar otomatik birleşim anahtarı olmaz. Liste/ayrıntı/arama ağsız ve salt okunurdur; bozuk gizli geçmişte kısmi sonuç verilmez. Şema 34→35 doğrulanmış yedekten sonra altı tabloyu boş oluşturur. Ayrıntılar [kaynakları koruyan yerel CTI bilgi grafiği kararındadır](decisions/0081-source-preserving-cti-knowledge-graph.md).

`AttackSyncService`, `AttackSource` ve `AttackSyncRepository` portlarını bağlar. Önce yönetilen kaynak geçmişini salt-okunur denetler; böylece bozuk yerel geçmiş ağdan yeni veriyle örtülmez. `MitreAttackSource`, yalnız sürümü sabitlenmiş Enterprise v20.0 tam STIX paketini sabit HTTPS adresinden alır ve boyut, nesne sayısı, koleksiyon dizini, kimlik, zaman, resmî başvuru, tür ve ilişki yönünü doğrular. Yalnız etkin grup/kampanya/malware ile seçili `uses`/`attributed-to` ilişkileri ortak CTI modellerine çevrilir. SQLite adaptörü tüm ekleme/güncelleme/geri çekmeleri tek transaction'da uygular ve işlem sonunda yönetilen geçmişi yeniden denetler. Ek teknik/taktik katalog aynı yanıttan üretilir ve eski CTI ile birlikte kaydedilir. Katalog başarılı senkron geçmişini tutar; başarısız indirme ayrı kalıcı çalışma olarak tutulmaz. Şema 41'deki diğer kaynak iddiaları korunur. Ayrıntılar [sürüme sabit MITRE ATT&CK kararı](decisions/0091-pinned-mitre-attack-cti-subset.md) içindedir.

Birleşik CTI arama yolu aynı depo portunun salt-okunur işlevidir. NFKC/casefold sorgu anahtarını CTI ana adı, seçili kaynak iddialarının alternatif adları ve IOC kanonik değeriyle karşılaştırır; tam/başlangıç/içerme derecesini hesapladıktan sonra kararlı biçimde sıralar. Etkin kapsam IOC geçerlilik penceresini enjekte edilen UTC sorgu zamanında değerlendirir. Sonuç limiti yalnız gösterimi keser; en fazla 50.000 CTI varlığı ve 50.000 IOC ana kaydının bütün iddia/olay geçmişi önce doğrulanır. Arama indeksi veya yeni tablo yoktur; kişisel ölçekte güvenli tam tarama kullanılır ve şema 35 değişmez. Ayrıntılar [birleşik yerel CTI arama kararındadır](decisions/0082-unified-local-cti-search.md); güncel sınır [çok kaynaklı IOC kararında](decisions/0090-bounded-multi-source-ioc-feeds.md) belirlenmiştir.

`CtiSavedSearchService`, birleşik aramanın sorgu ve filtrelerini adlandırılmış bir tanım olarak `CtiSavedSearchRepository` portuna iletir. SQLite adaptörü tanım yaşam döngüsünü eklemeli olaylarla tutar. Açık çalışma `BEGIN IMMEDIATE` ile başka yazarı dışladıktan sonra ayrı salt-okunur bağlantıda tam arama anlık görüntüsünü alır; çalışma başlığıyla bütün güncel/kaybolan öğeleri aynı transaction'da yazar. En son çalışma farklı tanıma aitse karşılaştırma tabanı sıfırlanır; aksi halde kimlik+durum özeti üzerinden yeni/değişen/aynı/kaybolan ayrılır. Bütün gizli geçmiş okuma öncesi sınırlandırılıp doğrulanır. Otomatik zamanlama, ağ çağrısı veya tehdit hükmü yoktur. Şema 35→36 doğrulanmış yedekten sonra dört tabloyu boş oluşturur. Ayrıntılar [kayıtlı CTI araması kararındadır](decisions/0083-durable-cti-saved-search-diffs.md).

Anlamlı CTI çalışma farkı bildirimi aynı kayıtlı-arama transaction'ının son adımıdır. İlk çalışma ve yeni tanım sessiz başlangıçtır; doğrudan önceki aynı tanım varken `added`, `updated` veya `removed` sayısı sıfırdan büyükse global bildirim sırasından bir kimlik ayrılır. Bildirim `run_id` ve `saved_search_id` yabancı anahtarlarıyla değişmez çalışma kanıtına bağlıdır. Birleşik inbox adaptörü bu kanıtı aynı okuma anlık görüntüsünde doğrular; okundu durumu yalnız bildirim satırını değiştirir. Bildirim eklenemezse çalışma başlığı ve öğeleri de geri alınır. Şema 36→37 yalnız boş bildirim tablosu ekler. Ayrıntılar [CTI arama bildirim kararındadır](decisions/0084-cti-saved-search-change-notifications.md).

`CtiSavedSearchMonitorService`, tek etkin kayıtlı aramayı süre hesabı için monoton saat kullanarak ön planda tekrarlar. Başlamadan tur/aralık/süre/sonuç sınırlarını ve arama durumunu doğrular. Her tur bağımsız olarak mevcut `CtiSavedSearchService.run` yoluna gider; yeni depolama veya paralel fark mantığı yoktur. Aralar en fazla bir saniyelik kesilebilir uyku parçalarıdır. Süre sınırı yeni tur başlangıcını engeller; kesinti tamamlanmış turları geri almaz. CLI bütün izleme ömründe ortak yerel çalışma kilidini tutar. Ayrıntılar [ön plan CTI izleme kararındadır](decisions/0085-bounded-foreground-cti-watch.md).

`CtiSavedSearchBatchService`, etkin kayıtlı aramaları `CtiSavedSearchService.list_window` ile sabit ad sırasına alır. Bir fazla kayıt okuyarak açık sınırın bütün etkin kapsamı içerdiğini yazmadan önce doğrular; taşma varsa hiçbir çalışma başlatmaz. Her seçilen aramayı mevcut tekil `run` yolundan geçirir, bu nedenle tanım tabanı, tam fark, atomik kayıt ve yerel bildirim kuralları çoğaltılmaz. Aramalar arası tek büyük transaction yoktur: sonraki hata önce tamamlanan bağımsız kanıtı geri almaz. CLI toplu çalışmanın tamamında ortak yerel çalışma kilidini tutar. Şema 37 değişmez. Ayrıntılar [toplu CTI yenileme kararındadır](decisions/0086-bounded-all-cti-watch-refresh.md).

`CtiHuntingJournalService`, etiket ve not girdilerini doğrulayıp ayrı `CtiHuntingJournalRepository` portuna iletir. Etiketin kanonik anahtarı güncel durumu tekilleştirir; her ekleme/görünüm güncelleme/kaldırma/yeniden etkinleştirme olayı eklemeli saklanır. Notlar düzenlenmez ve genel aramaya ya da aynı aramaya ait bir çalışma kimliğine bağlanır. SQLite adaptörü bütün gizli etiket/not geçmişini sınırlandırıp yaşam döngüsü, zaman ve yabancı bağları doğrular. Defter verisi sorgu tanım özetine katılmaz ve çalışma farkı tabanını değiştirmez. Şema 37→38 doğrulanmış yedekten sonra üç boş tabloyu transaction içinde oluşturur. Ayrıntılar [CTI avcılık defteri kararındadır](decisions/0087-append-only-cti-hunting-journal.md).

`NvdApplicabilityService`, yalnız CVE kimliği ve gösterim sınırını `NvdApplicabilityRepository` portuna iletir. SQLite adaptörü doğrulanmış kanonik NVD kaynak nesnesindeki `configurations` alanını okur; CPE 2.3 bileşenlerini, sürüm sınırlarını, UUID'leri ve yapı/düğüm mantığını katı/boyut sınırlı ayrıştırır. En fazla 500 satır gösterilse de bütün kaynak koşulları doğrulanır. `vulnerable=false` çevresel koşullar korunur. Çıktı yeni tablo oluşturmaz, ağ veya yazma yapmaz. Ayrıntılar [NVD CPE uygulanabilirlik kararı](decisions/0041-nvd-cpe-applicability-view.md) içindedir.

`AssetProductService`, yalnız `AssetProductRepository` portuna bağlıdır. SQLite adaptörü kayıtlı varlığa kullanıcı doğrulamalı CPE türü, üretici, ürün ve kesin sürümü bağlar; aynı kimliği tekilleştirir ve ekleme/güncelleme/kaldırma/yeniden etkinleştirme olaylarını silmeden tutar. Port/teknoloji ipuçlarından otomatik ürün oluşmaz. Şema 19→20 geçişi önce yedek alır ve boş ürün tablolarını tek transaction'da oluşturur. Ayrıntılar [doğrulanmış ürün kararı](decisions/0042-user-verified-asset-products.md) içindedir.

`ProductVulnerabilityService`, ürün kimliği, CVE ve gösterim sınırını depo portuna iletir. SQLite adaptörü ürün ile NVD kaydını tek salt-okunur anlık görüntüde alır ve mevcut katı CPE ayrıştırıcısını kullanır. Tam tür/üretici/ürün ile basit kesin sürüm eşleşmesi yalnız adaydır; aralık, joker, `AND`, tersleme ve çevresel bağlar elle inceleme durumunda kalır. Komut ağ, yazma, risk skoru veya kalıcı maruziyet üretmez. Ayrıntılar [temkinli ürün/NVD kararı](decisions/0043-conservative-product-nvd-assessment.md) içindedir.

`ProductVulnerabilityOverviewService`, bir doğrulanmış ürün ile bir CVE'nin yerel KEV, EPSS, NVD/CVSS ve CPE koşulunu tek SQLite okuma anında birleştirir. Bilinen gerçek istismar, 30 günlük olasılık, teknik şiddet ve ürün koşulu ayrı alanlar olarak kalır; tek risk puanına veya maruziyet hükmüne dönüşmez. NVD yoksa mevcut KEV/EPSS kanıtı gösterilir, bozuk herhangi bir kaynakta ise bütün görünüm durur. Ayrıntılar [ürün zafiyet görünümü kararı](decisions/0044-product-vulnerability-overview.md) içindedir.

`ProductVulnerabilityInventoryService`, tek yerel NVD kaydını etkin doğrulanmış ürün envanterinin tamamıyla karşılaştırır. Varsayılan çıktı yalnız kesin-koşul ve elle-inceleme adaylarıdır; `--all` eşleşmeyenleri de gösterir. Sayımlar gösterim sınırından önce bütün etkin envanterde hesaplanır, 10.000 ürün sınırı vardır ve CPE koşulları kimlik/yapılandırma bağına göre bir kez indekslenir. Hiçbir aday otomatik maruziyet, alarm veya yazma oluşturmaz. Ayrıntılar [envanter geneli eşleştirme kararı](decisions/0045-inventory-wide-product-matching.md) içindedir.

`VulnerabilityExposureService`, temkinli ürün/NVD değerlendirme portu ile ayrı maruziyet kayıt portuna bağlıdır. Yeni kayıt yalnız kesin-koşul veya elle-inceleme adayından, açık gerekçeyle `investigating` durumunda açılır. `affected`, `not_affected` ve `fixed` yalnız insan kararıdır; bastırma ve yeniden kontrol tarihi durumu kendiliğinden değiştirmez. SQLite adaptörü ana kayıt ile eklemeli olayı aynı transaction'da yazar ve karar anındaki ürün güncelleme zamanı, NVD özeti ve aday sınıfını sabitler. Ürün/NVD değerlendirme ile yazım arasında değişirse işlem durur; daha sonra değişirse eski karar korunup `review_required` gerekçesi üretilir. Şema 20→21 geçişi doğrulanmış yedekten sonra boş tabloları işlemsel oluşturur. Ayrıntılar [insan onaylı maruziyet yaşam döngüsü kararı](decisions/0046-human-reviewed-vulnerability-exposure-lifecycle.md) içindedir.

`AssetCriticalityService`, yalnız kayıtlı varlığa açık kullanıcı seviyesi ve gerekçesi bağlar. SQLite adaptörü güncel `low/medium/high/critical` durumunu, kaldırmayı ve yeniden etkinleştirmeyi eklemeli olaylarla aynı transaction'da saklar. Aynı karar idempotenttir. Şema 26→27 doğrulanmış yedekten sonra tabloları boş oluşturur; geçmiş varlık veya maruziyetten önem türetmez. Ayrıntılar [varlık önemi ve erişilebilirlik kararındadır](decisions/0062-human-asset-criticality-and-recorded-reachability.md).

`VulnerabilityExposureQueueService`, kullanıcı EPSS eşiğini, yüzey kanıtı güncellik eşiğini, kapanmış/bastırılmış kapsam seçimini, `all/present/missing` destek kanıtı filtresini ve gösterim sınırını salt-okunur kuyruk portuna iletir. SQLite adaptörü seçili maruziyetleri, ürünleri, NVD'yi, yalnız ilgili KEV/EPSS satırlarını, etkin destek kanıtlarını, bağlı bütün düzeltme planlarını, süreli bastırmaları, varlık önemini, etkin yüzey kapsamını ve son web/servis kanıtını tek transaction anında okur. Tek sayısal risk skoru yerine `immediate/high/normal/monitored` bantları ile insan durumu, yeniden inceleme, KEV, ransomware, EPSS, CVSS, iş önemi ve doğrulanmış internet erişimi nedenlerini ayrı tutar. İş önemi insan beyanıdır; internet bağlamı yalnız güncel kayıtlı HTTPS yanıtı veya açık izinli TCP servis kanıtından çıkarılır. Yalnız DNS, doğrulanamayan erişim, eski/eksik kanıt ve kapsam yokluğu ayrı kalır; hiçbiri güvenli/internete kapalı hükmü değildir. Destek kanıtı sayı/tür bağlamı ve çalışma filtresi olarak görünür fakat bandı değiştirmez. İptal edilmemiş düzeltmelerin sayısı, durum/sonuç kümeleri ve vadesi gelen kontrol sayısı görünür; vadesi gelen plan `remediation_recheck_due` nedeniyle kaydı en az `high` banda taşır fakat insan kararını değiştirmez. Yüksek/kritik iş önemi veya doğrulanmış güncel erişim açık inceleme bandını yükseltebilir, fakat insanın maruziyet durumunu yazmaz. Süresi gelmemiş bastırma varsayılan görünümden çıkar; kesin bitiş anında hiçbir yazma olmadan geri döner. Kapanmış karar kaynak puanı veya varlık bağlamı nedeniyle kendiliğinden açılmaz; değişmiş ürün/NVD kanıtı yeniden inceleme bandına çıkar. Bütün seçili incelemeler, en fazla 10.000 etkin destek kanıtı, iptal edilmişler dahil en fazla 10.000 düzeltme planı, 10.000 süreli bastırma ve her bağlam ailesinde 10.000 varlık satırı doğrulanır; en fazla 500 inceleme gösterilir. Ağ veya otomatik karar yoktur. Ayrıntılar [açıklanabilir maruziyet kuyruğu kararı](decisions/0047-explainable-vulnerability-exposure-queue.md), [kuyrukta destek kanıtı bağlamı kararı](decisions/0049-exposure-evidence-queue-context.md), [destek kanıtı boşluk filtresi kararı](decisions/0050-exposure-evidence-gap-filter.md), [kuyrukta düzeltme bağlamı kararı](decisions/0059-remediation-context-in-exposure-queue.md), [süreli bastırma kararı](decisions/0060-expiring-exposure-suppression-and-remediation-acceptance.md) ve [varlık önemi/erişilebilirlik kararı](decisions/0062-human-asset-criticality-and-recorded-reachability.md) içindedir.

`VulnerabilityReassessmentService`, planlama ile açık çalıştırmayı ayrı tutar. Plan adaptörü maruziyet, doğrulanmış ürün, güncel NVD özeti ve bastırmayı tek salt-okunur SQLite anında karşılaştırır; ürünün etkisizleşmesi, ürün/NVD kanıt değişimi ve gelmiş kontrol tarihi ayrı tetikleyicilerdir. Varsayılan yalnız açık ve görünür kayıtlar, açık seçeneklerle kapanmış/bastırılmış kayıtlar da kapsanır. Çalıştırma güncel yerel ürün/NVD koşulunu mevcut değerlendirme portuyla yeniden hesaplar; ağ kullanmaz. Yazma transaction'ı planın ürün, NVD, karar, bastırma ve tetikleyici anlık görüntüsünü yeniden doğrular; tek kayıt değişmişse ebeveyn ve bütün sonuçlar geri alınır. Sonuç geçmişi eklemelidir ve insan maruziyet kaydı/olay tablosu yazılmaz. Şema 27→28 doğrulanmış yedekten sonra boş çalışma/sonuç tablolarını işlemsel oluşturur. Ayrıntılar [kontrollü toplu yeniden değerlendirme kararındadır](decisions/0063-controlled-bulk-vulnerability-reassessment.md).

`VulnerabilityExposureEvidenceService`, seçilmiş bir maruziyet incelemesine üretici/dağıtım duyurusu, yerel paket envanteri veya analist notu bağlar. Duyuru başvuruları yalnız sınırlı HTTPS adresi olarak doğrulanır; adaptör bağlantıyı açmaz veya içeriği kopyalamaz. Aynı inceleme+tür+kaynak tek kimliktir; açıklama güncellemesi, iptal ve yeniden etkinleştirme güncel kayıtla birlikte eklemeli olay geçmişinde tutulur. Kanıt varlığı insan kararını, önceliği veya yeniden inceleme durumunu kendiliğinden değiştirmez. Ana kayıt ve olay aynı transaction'dadır; şema 21→22 geçişi doğrulanmış yedekten sonra boş tabloları oluşturur. Ayrıntılar [maruziyet destek kanıtı kararı](decisions/0048-vulnerability-exposure-supporting-evidence.md) içindedir.

`AssetPackageService`, yalnız doğrulanmış varlığa Red Hat/RPM paket adı, epoch, sürüm, release, mimari, dağıtım CPE'si ve isteğe bağlı kaynak RPM bağlar. PURL domain katmanında doğrulanmış alanlardan üretilir; depo okurken yeniden hesaplanarak bozuk veya elle değiştirilmiş değer reddedilir. Kimlik alanları değişmez; kaynak RPM/kanıt güncellemesi, iptal ve yeniden etkinleştirme ana kayıtla aynı transaction'daki eklemeli olaydır. Liste/ayrıntı ağsız ve yazmasızdır. Şema 22→23 doğrulanmış yedekten sonra boş tablolar oluşturur; genel ürün kayıtlarından RPM üretmez. Ayrıntılar [kesin Red Hat RPM kararı](decisions/0054-exact-redhat-rpm-evidence.md) içindedir.

`VendorPackageMatchService`, etkin kesin paketi depo portundan okuyup bağlantıyı kapattıktan sonra açık seçilen CVE'yi `VendorAdvisorySource` üzerinden alır. CSAF adaptörü ürün yardımcılarındaki PURL/CPE değerlerini ve tam ürün ilişkilerini korur. Tam ikili bağ aynı NEVRA+PURL+CPE; kaynak paket bağı kaynak RPM adı+`arch=src` PURL+CPE ister. Farklı durumlara çıkan birden çok kesin bağ `conflicting_vendor_context` olarak kalır. Sonuç ağdan gelen Red Hat beyanıdır; veritabanı, maruziyet, kanıt veya öncelik yazılmaz. Ayrıntılar [kesin RPM/VEX eşleştirme kararındadır](decisions/0055-exact-redhat-vex-package-match.md).

`VendorPackageEvidenceService`, inceleme/paket/ürün kimliği/açıklamayı ağdan önce doğrular; inceleme ile kesin paketin aynı varlığa ait olmasını ister ve CVE'yi incelemeden alır. Güncel VEX yeniden getirilir; yalnız tekil ve çelişkisiz kesin eşleşmedeki açıkça seçilmiş tam ürün bağı yazılır. Depo transaction'ı paket etkinliğini ve `updated_at` değerini yeniden kontrol ederek ağ sırasındaki yerel değişikliği reddeder. Kaynak özeti, belge sürümü/zamanı, durum, bileşen PURL'si ve dağıtım CPE'si ana kayıtla aynı transaction'daki eklemeli olaya bağlanır; yeni kaynak özeti veya yeniden doğrulanmış paket anlık görüntüsü ayrı kimliktir. Kuyruk bu kaydı `exact_vendor_package` türü olarak sayar, fakat karar veya bandı değiştirmez. Şema 23→24 önce doğrulanmış yedek alır ve geçmiş salt-okunur sonuçlardan kanıt üretmez. Ayrıntılar [seçilmiş kesin VEX kanıtı kararındadır](decisions/0056-human-selected-exact-vex-evidence.md).

`VendorPackageEvidenceCheckService`, kayıtlı kanıtı ve bağlı kesin paketi depolardan salt okunur alır. Etkisiz pakette dış kaynak çağrılmaz. Etkin pakette aynı `VendorPackageMatchService` güncel VEX'i yeniden değerlendirir; kaynak özeti, paket `updated_at` değeri, seçilen tam ürün kimliği, durum ve ilişki alanlarını eski kanıtla karşılaştırır. `current`, aynı beyanlı kaynak yenilemesi, paket anlık görüntüsü değişimi, beyan değişimi, kayıp ilişki ve çelişen bağlam ayrı kalır. Sonuç hiçbir tabloyu, kanıtı, kararı veya kuyruğu yazmaz; şema 24 değişmez. Ayrıntılar [kesin kanıt güncellik kararı](decisions/0057-read-only-exact-vex-evidence-check.md) içindedir.

`VulnerabilityRemediationService`, açık maruziyet için insanın seçtiği kaynaklı öneriyi planlar; uygulama, iptal ve yeniden kontrol geçişlerini küçük bir depo portuna iletir. SQLite adaptörü kaynak kanıtın aynı maruziyete ait ve etkin olduğunu yazma transaction'ında doğrular. Ana plan son durumu, olay tablosu eklemeli geçmişi taşır; her olay güncel NVD/ürün özeti ile o andaki insan kararını saklar. Uygulama ve süren/belirsiz risk bir sonraki kontrol tarihini zorunlu kılar. Kontrol sonucu maruziyet tablosunu yazmaz; kapanma ayrı insan kararıdır. Şema 24→25 geçişi tabloları boş oluşturur. Ayrıntılar [insan onaylı düzeltme kararı](decisions/0058-human-approved-remediation-and-recheck.md) içindedir.

`VulnerabilityExposureSuppressionService`, açık maruziyet kimliği, gerekçe ve 1–3650 günlük süreyi ayrı depo portuna iletir. SQLite adaptörü süresiz bastırılmış ve kapanmış kayıtları reddeder; güncel tek kaydı etkinleştirme/uzatma/yeniden etkinleştirme/geri alma olaylarıyla aynı transaction'da tutar. Etkinlik, `active` bayrağı ile UTC bitişin okuma zamanından ileride olması birlikte değerlendirilerek hesaplanır; süre dolması yazma veya sahte olay üretmez. Liste, ayrıntı, kuyruk ve doctor aynı politikayı kullanır. Şema 25→26 doğrulanmış yedekten sonra tabloları boş oluşturur. Ayrıntılar [süreli bastırma ve düzeltme kabulü kararındadır](decisions/0060-expiring-exposure-suppression-and-remediation-acceptance.md).

`VulnerabilityNotificationService`, yeniden değerlendirme planını en fazla 10.000 kayıtlık doğrulanmış kapsamda alır ve kullanıcı sınırı kadar yeni durumu `VulnerabilityNotificationRepository` üzerinden yerel kutuya ekler. SQLite adaptörü bütün adayları aynı yazma transaction'ında yeniden doğrular; maruziyet kararı, bastırma, ürün kanıtı, NVD özeti veya tetikleyici değişmişse kısmi kayıt bırakmaz. Durum özeti maruziyet kimliği, sıralı tetikleyiciler, ürün etkinliği/kanıt zamanı, NVD özeti ve yeniden kontrol tarihinden hesaplanır. `(exposure_id, state_sha256)` tekilliği aynı durumun tekrarını engeller; önceden bildirilmiş durumlar yeni sınırını tüketmediği için sonraki çalıştırma kalan yeni adaylara ilerler. Bildirim insan kararını ve olay geçmişini yazmaz. Ayrıntılar [zafiyet değişiklik aboneliği kararındadır](decisions/0065-deduplicated-vulnerability-change-notifications.md).

## Hedef kontrolü ve rapor

`TargetProbe` pasif kaynak sözleşmesinden ayrıdır. Sabit Google DoH üzerinden iki DNS adres ailesi kontrol edilir; bütün adresler uygun olmadan hedefe bağlanılmaz. Bağlantı doğrulanan genel IP'ye sabitlenir, asıl domain TLS/Host için kullanılır. Yalnız HTTPS HEAD / yapılır; yönlendirme, gövde ve doğrulamasız bağlantı yoktur. Doğrulanmış oturumun eş sertifikası 64 KiB ve 128 DNS adı sınırıyla kimlik kanıtına dönüşür. Her bağlantı 8 saniye, bütün kontrol 25 saniye; başlık 16 KiB, DNS JSON 64 KiB sınırındadır. İlk genel IP örneklenir; diğer IP'lerin erişimi ölçülmez. HTTP 103 gibi ek ara yanıtlar bu sürümde başarısız kontrol olabilir.

Uygulama tamamlanan sonuçları kaydeder. Terminal aynı yerel kilitle kontrolü ve arşiv çalıştırmasını birbirinden ayırır. Toplu kontrol en fazla 20 bulguya uygulanır, güncel denemeler altı saat yeniden kullanılabilir; aynı turdaki aynı aday için bir ağ kontrolü yapılır. Kesinti önceki tamamlanan kontrolleri korur. Hedef kontrollerinin ayrı kalıcı iş/ilerleme kuyruğu henüz yoktur.

`ReviewQueueService` inceleme sırasını o anki saat ve son kayıtla hesaplar. Yanıt veya kullanıcı şüpheli kararı sırayı öne alabilir; durum otomatik kapatılmaz, risk skoru üretilmez. `FindingReportService` tutarlı bir bulgu anlık görüntüsünden format sürümlü JSON üretir. Dosya yayımlama somut adaptöre aittir. Ayrıntılar ve birincil kaynaklar [kontrol/rapor kararında](decisions/0006-controlled-checks-and-reports.md) bulunur.

## Kaynak beklemesi ve bakım

Kaynak adaptörlerine enjekte edilen `SourceCooldownGate`, her HTTP denemesinden önce `CooldownRepository` üzerinden kayıtlı beklemeyi okur. İstek aralığını açılıştan önce, sağlayıcı kota başlıklarını gövde/tekrar beklemesinden önce kaydeder. Depo en geç bitiş zamanını atomik olarak korur; kayıt hatasında yeni ağ isteği yapılmaz. Aynı süreçte monotonic alt sınır, yeniden açılışta kayıtlı UTC zaman kullanılır. Bütün üretim çağrıları aynı veritabanının worker kilidi altındadır; farklı veritabanı veya cihaz için kota garantisi yoktur.

`MaintenanceService` kullanım, önizleme, açık uygulama ve geçmiş işlemlerini `MaintenanceRepository` üzerinden yürütür. Yalnız hiçbir bulguya bağlı olmayan ve ilk yerel kaydı kesimden eski gözlemler seçilir. Hatalı/gelecek tarihler ve bütün bağlı kanıtlar korunur. Önizleme kimliği kanonik veritabanı konumuna, UTC güne, seçeneklere ve uygun gözlemlerin içeriğine bağlıdır. Uygulama worker kilidi ve SQLite yazma kilidi altında seçimi yeniden doğrular, önce yedek alır, sonra en fazla 10000 gözlem siler ve günlük kaydeder. Silme/günlük aynı transaction içindedir. İş özetleri tarihsel sonuçlar olarak korunur.

Kullanım görünümündeki SQLite boş sayfaları yeniden kullanılabilir alandır; dosyanın diskten küçüldüğü anlamına gelmez. Yedek/rapor dizinleri bu ölçüme dahil değildir; otomatik temizlik, VACUUM veya toplam disk kotası yoktur. Bekleme ve bakım kayıtları güncel yedeklere dahildir. Bildirimler temizlik kapsamına girmez. Sınırlar ve kurtarma yöntemi [karar belgesinde](decisions/0007-durable-waits-and-maintenance.md) açıklanır.

`StorageReadinessService`, mevcut bakım portundan veritabanı kullanımı ve saklama önizlemesini; ayrı `StorageReadinessRepository` portundan sınırlı klasör taraması, disk kapasitesi ve yönetilen yedek bilgisini alır. Uygulama politikası en az 64 MiB veya SQLite mantıksal boyutunun iki katı çalışma payı ister. Yedek yaşı ve saklama günü kullanıcı tarafından sınırlandırılır; bunlar otomatik işlem başlatmaz.

Dosya sistemi adaptörü sembolik bağlantı izlemeden en fazla 10.000 düzenli dosya ve `backups/` altında 1.000 `.db` yedeği sayar. En yeni yönetilen yedeği legacy şemalara izin veren salt-okunur bağlantıyla şema, quick check ve yabancı anahtar bütünlüğünden geçirir. Bozuk yeni yedek yerine eski dosyayı sessizce seçmez. Ayrı ortam kopyası ve restore tatbikatı kanıtı tutulmadığından `unknown/not_recorded` kalır. Görünüm yazmaz; bu özellik kendi tablosunu eklemez ve güncel düzen şema 35'tir. Ayrıntılar [depolama hazırlığı kararındadır](decisions/0031-storage-recovery-readiness.md).

## Yerel bildirim kutusu

`InboxService`, listeleme, ayrıntı ve açık okundu/okunmadı işlemlerini `NotificationRepository` üzerinden yürütür. `SQLiteInboxRepository` depolama adaptörüdür; terminal bu parçaları başlangıçta bağlar. Bulgu bildirimi `SQLiteFindingRepository.save_import`, aday bildirimi pasif keşif, dış yüzey değişiklik bildirimi ilgili kontrol kanıt yazımıyla aynı transaction'a aittir. Zafiyet değişiklik bildirimi ayrı açık `vuln change-notify` transaction'ında güncel planı yeniden doğrular. Ayrı bir dış teslim süreci yoktur.

Her bulgu için bir `finding_created`, her ilk pasif aday için bir `surface_candidate_discovered`, her değişmiş dış yüzey kontrolü için bir `surface_evidence_changed` ve her yeni maruziyet kanıt durumu için bir `vulnerability_review_required` bildirimi vardır. İlk `baseline` ve `unchanged` yüzey sonuçları bildirilmez. Dış yüzey bildirimi tek bir `surface_checks`, `surface_mail_checks` veya `surface_service_checks` satırına; zafiyet bildirimi bir maruziyete yabancı anahtarla bağlanır ve kendi kanıt anlık görüntüsünü saklar. Aynı kanıt durumu, yeniden tarama veya kutuyu tekrar üretme okundu bilgisini sıfırlamaz. `origin=new` yeni yerel kayıt anlamındadır; yeni başlamış veya doğrulanmış tehdit anlamına gelmez.

Şema 1–5'ten geçişte bildirim kutusu ilk kez oluşturulurken, kapatılmış olanlar dahil önceki tüm bulgulara `origin=existing` ve `read_at=NULL` ile bildirim eklenir. Bildirimdeki `created_at` tek UTC geçiş zamanıdır; bulgunun eski `created_at` ve `last_seen_at` değerleri değişmez. Önceki kararından bildirimi okuduğu sonucu çıkarılmaz. Terminal bu kayıtları "Önceki kayıttan" diye gösterir. Şema 6'dan 7'ye geçiş mevcut kutuyu ve okundu zamanlarını aynen korur.

Bildirim UUID'si kullanıcı işlemleri içindir. Eski bulgu tablosundaki `sequence INTEGER PRIMARY KEY AUTOINCREMENT` korunur; aday, dış yüzey değişikliği ve zafiyet değişikliği bildirimleri ayrı tablolarda dört tablonun ortak en büyük değerinden sonraki sıra numarasını alır. Yeni bulgu yazımı da dört tablonun en büyük sırasını dikkate alır. Adaptör sıra çakışmasını bozuk kayıt sayar. Birleşik liste yeni eklenenden eskiye ilerler; sonraki sayfa `sequence < before` koşuluyla alınır. Saat gerilemesi ve yeni kayıt gelişi eski sayfanın sınırını kaydırmaz. Şema doğrulaması dört tablonun sütun, SQL, tekillik, bağlantı ve indekslerini denetler.

Liste varsayılan olarak 20 okunmamış kayıt gösterir; sayfa sınırı 1–100'dür. Dört bildirim tablosunun toplamı, okunmamış ve seçilen durum sayısı ile birleşik sayfa satırları aynı okuma transaction'ından gelir. Durum sayısı bütün kutuya aittir; yalnız `before` sınırından kalanları saymaz. Her sayfa ayrı okuma işlemidir: sayfalar arasında yeni kayıtlar, okundu bilgisi ve inceleme kararları değişebilir. Bu düzen bütün gezinme boyunca dondurulmuş bir görünüm sağlamaz. Ayrıntı bildirimi, ilgili bulgu, aday veya değişmiş kanıtı aynı okuma transaction'ından alır. Değişiklik görünümü saklı anlık görüntüden üretilir; yeni ağ çağrısı yapmaz.

Liste ve ayrıntı salt okunurdur. Okundu işlemi en fazla 100 açık kimlik kabul eder; tekrarları tekilleştirir. Adaptör `BEGIN IMMEDIATE` altında tüm seçimi doğrular ve tamamını birlikte günceller. Eksik/bozuk bir bildirim veya yazma hatası bütün işlemi geri alır. Zaten okunmuş bir kayıt yeniden işaretlenince zamanı değişmez; okunmadı işlemi `read_at` değerini temizler. Sonraki okundu işlemi yeni UTC zamanı kaydeder. Saat gerilese bile açık kullanıcı eylemi korunur; sıralama zamana bağlı değildir. Okundu bilgisi bulgunun inceleme kararını değiştirmez ve geçmiş okundu işlemlerinin ayrı günlüğü tutulmaz.

Bildirimler, okundu bilgisi ve sıra sayaçları yedek/boş konuma restore kapsamındadır. Şema 14→15 dış yüzey değişiklik tablosunu, şema 28→29 zafiyet değişiklik tablosunu boş başlatır; eski kanıtlardan alarm çıkarmaz. Birleşik yerel terminal kutusuna ek olarak yalnız kullanıcının seçtiği tek bildirimi açık komutla gönderen imzalı webhook kuyruğu vardır; otomatik abonelik, e-posta, SMS, işletim sistemi bildirimi veya alıcının olayı işlediğine ilişkin dış onay bulunmaz. Ayrıntılar [yerel bildirim](decisions/0008-local-inbox.md), [pasif keşif bildirimi](decisions/0020-passive-discovery-history-and-notices.md), [dış yüzey değişikliği](decisions/0026-atomic-surface-change-notifications.md), [zafiyet değişikliği](decisions/0065-deduplicated-vulnerability-change-notifications.md) ve [imzalı webhook](decisions/0089-explicit-signed-webhook-outbox.md) kararlarındadır.

## Takibin durum özeti

`StatusService`, `StatusRepository.snapshot` ile genel sayaçları ve sınırlı varlık geçmişini tek seferde alır. `SQLiteStatusRepository` bunları tek `BEGIN` okuma transaction'ından üretir. Varlık/gözlem/bulgu/iş/bildirim sayıları, seçilen varlıkların denemeleri ve kaynak beklemeleri aynı veritabanı görünümüne aittir. Servis okuma sonrasında tek UTC zamanı alıp bütün güncellik ve bekleme hesaplarında kullanır.

Arama kapsamı varlık + sağlayıcı olarak ayrılır. Hedef eşleşmesi `scan_jobs.targets` içindeki tam domain üyeliğidir; aynı marka parçası veya sağlayıcı genelinde başka bir adresin başarısı kullanılmaz. Her eşleşme için son deneme ve son `complete` deneme, `scan_attempts.rowid` ekleme sırasıyla ayrı seçilir. Eski bir işin yeni retry kaydı böylece son deneme olabilir. Tarihe göre `MAX` alınmaz. Birden fazla hedefli kısmi işte hedef başına kesin tamamlanma bilgisi bulunmadığından hiçbir hedefin tamamlanmış arama zamanı yenilenmez.

`current`, son tamamlanan aramanın seçilen saat eşiğinin içinde; `stale`, eşikte veya daha eski olduğunu anlatır. `never` tamamlanmış kayıt bulunmadığı, `clock_error` son deneme veya son tamamlanan denemenin zamanının okunamadığı, gelecekte olduğu veya başlangıç/bitiş sırasının tutarsız olduğu durumdur. Varsayılan eşik 24 saat, sınır 1–8760 saattir; yalnız görünümü etkiler. Yeni başarısız/kısmi/yarım deneme önceki başarıyı silmez ve ayrı gösterilir. Bu bilgiler cihaz saatine ve kayıtlı zamanlara dayanır; saat doğruluğu veya anlık kaynak erişimi ölçülmez.

`status` varsayılan olarak alfabetik ilk 20 varlığın iki kaynak geçmişini gösterir; `--limit` 1–100 arasındadır. Gösterilmeyen varlık sayısı açıkça belirtilir. `status DOMAIN` normalleştirilmiş, kayıtlı domaini tam eşleşmeyle seçer. Genel sayaçlar ve kaynak beklemeleri filtreden etkilenmez. İş durumu sayıları tarihsel kayıtları kapsar; güncel kesinti sayacı değildir. `running` yalnız kayıt durumudur; canlı çalıştırıcı kanıtı sayılmaz.

Özet ağ isteği, worker kilidi, kurtarma, yeni veritabanı veya indeks oluşturma yapmaz; bildirim/inceleme durumlarını değiştirmez. Başarılı çıktıdaki çıkış 0 ve JSON `ok:true`, özetin okunabildiğini belirtir; genel sağlık kararı değildir. Tam bütünlük kontrolü `doctor` komutuna aittir. İş hedefleri ve küçük geçmiş alanları akış halinde okunur; sonuç/sorgu JSON'ları yalnız seçilen denemeler için yüklenir. SQLite JSON uzantısı gerekmez. Uzun geçmiş okuma maliyetini artırabilir; bu sınırlı çıktı tüm geçmişin sabit sürede okunacağını garanti etmez. Ayrıntılar [durum özeti kararında](decisions/0009-monitoring-status.md) açıklanır.

## Sınırlı izleme denemeleri

`MonitorService`, `MonitorRepository` üzerinden sabit hedef/kaynak/kural ve çalışma sınırlarıyla kalıcı oturum oluşturur. `monitor start` yalnız mevcut crt.sh/urlscan arşiv aramalarını kullanır; aktif hedef kontrolü veya yeni kaynak eklemez. Varsayılan 3 tur, tur sonrasında 3600 saniye bekleme ve 86400 saniyelik yeni iş başlatma bütçesidir. Sınırlar 1–1000 tur, 300–86400 saniye aralık, 1–604800 saniye bütçe ve en fazla beş hedeftir.

Oturum, beklemeler dahil mevcut yerel worker kilidini tutar. `JobService.run_owned` çağıranın bu kilidi aldığını varsayarak mevcut arama akışını yürütür; normal `run` kilidi almaya devam eder. Ağ veya bekleme sırasında SQLite yazma transaction'ı açık kalmaz. Bu kişisel kurulumda aynı kayıt alanındaki diğer arama, hedef kontrolü ve bakım çalışmaları meşgul hatası alır. Salt okuma ve kısa inceleme/okundu işlemleri ayrı çalışabilir.

Her kaynak işi çalıştırılacağı zaman oluşturulur; `scan_jobs` ve `monitor_jobs` bağlantısı aynı transaction'da yazılır. Genel worker bağlı işleri seçmez; açık `jobs retry` ile ayrı çalıştırma da reddedilir. Oturum sahibi yalnız kendi açık oturumuna ait, henüz denenmemiş işi başlatabilir. Rapor her bağlı işin ilk denemesini kullanır. Kaynak denemesi sonuçları tek tek doğrulanıp küçük `MonitorAttempt` kayıtlarına çevrilir; bütün oturumun büyük sorgu/sonuç JSON'ları bellekte birlikte tutulmaz.

Süre monotonic saatle ölçülür; kaynak işi oluşturmadan ve çalıştırmadan önce kontrol edilir. Bekleme kalan bütçeyi aşmaz ve en fazla bir saniyelik adımlarla ilerler. Başlamış kaynak araması birden çok sorgu/tekrar içerebilir ve kendi sınırlarıyla tamamlanır; toplam süre bütçeyi aşabilir. Bu bir kaynak işi başlatma sınırıdır, sert süreç veya tek HTTP isteği zaman aşımı değildir. Saatin geri gitmesi/sonlu olmaması hata olarak durdurulur; UTC başlangıç/bitişi gerilese bile ölçülen süre bundan bağımsızdır.

Oturumun `completed/interrupted/failed` durumu ile kaynakların `complete/partial/failed/interrupted` sonuçları ayrıdır. Tamamlanan tur bütün seçili kaynakların denemesinin bitmesidir; hepsinin başarılı olduğu anlamına gelmez. Yeni gözlem/bulgu sayıları yalnız kayıtlı son sayı özetlerinden toplanır; özeti bulunmayan başlanmış denemeler ayrıca sayılır. Planlanıp başlamayan işler başarısız kaynak yanıtı kabul edilmez. Kayıtlı sorgu sayısı HTTP çağrısı veya anlık erişilebilirlik ölçümü değildir.

`monitor list/show` salt okunurdur; `show` özet ve sınırlı son çalışma listesini aynı okuma snapshot'ından üretir. Ctrl+C oturumu kapatmayı dener; zorla kapanma sonrasında `monitor recover` veya yeni `monitor start`, worker kilidi altında önceki oturumu ve bağlı bekleyen işleri yarım olarak kapatır. Zorla kapanmış süreç için monotonic süre yeniden üretilemez; `elapsed_seconds=NULL` kalır. Normal iş kurtarması bağlı ilk denemeyi yarım işaretlese bile oturum kaydı monitor kurtarmasına kadar açık kalabilir. Otomatik devam veya arka plan hizmeti yoktur. Geçiş, raporlama ve kurtarma ayrıntıları [izleme kararında](decisions/0010-bounded-monitoring.md) açıklanır.

## Doğrulama ve değişiklik

İzleme testleri tüm oturum boyunca tek sahipliği, monotonic süre/tur sınırını, kaynaklar arasında veya beklemede iptali, genel worker ve ayrı retry engelini, işlem ortası zorla kapanmayı, eksik sonuç sayılarını, atomik bağlantı ve kurtarmayı, şema 6→7→8 geçiş zincirini ve yedekten aynı raporun okunmasını kapsar. Süre sonunda başlamadan kapatılan iş ile hiç oluşturulmamış iş, aynı başlamış deneme sonuçlarını farklı başarı sonucuna dönüştürmez.

`./scripts/check-fast` shell sözdizimi, Python derleme, bağımlılık yönü,
kurulum geri alma, marka adaptörü sınırları ve temel CLI/depo davranışlarını
ağsız kısa kapıda doğrular. `./scripts/check` girdi/ağ sınırlarını, 36 etiketli
ad örneğini, kaynak hatalarını, kalıcılığı, tekrarları, kararları,
yedek/restore, migration rollback, iş geçmişini, kilit yarışını, gerçek süreç
ölümü sonrası kurtarmayı ve bekleme korumasını, hedef erişim sınırlarını,
güncelliği, tutarlı raporu, yedekli temizliği, atomik bildirimleri, okundu
bağımsızlığını, sayfalamayı, terminal sözleşmesini ve bağımlılık yönünü tam
regresyon olarak kontrol eder. Durum özeti testleri varlık/kaynak ayrımını,
başarıdan sonraki hata görünümünü, saat sınırlarını, geçmişin kesilmeden
seçilmesini, eşzamanlı yazma sırasında tutarlı okumayı ve yan etkisiz terminal
kullanımını ekler. Testler geçici dizinlerde sahte ağ kaynaklarıyla çalışır.
Her gönderimde kısa kapı; ilgili dosya değişikliklerinde temiz marka kurulumu;
elle veya `v*` sürüm etiketinde tam paket çalışır. Etiketli GitHub sürümü yalnız
tam paket başarılı olduktan sonra oluşturulur. Güncel test toplamı ve gerçek
kaynak denemelerinin doğrulanan kapsamı [STATUS.md](STATUS.md) içindedir.
Sentetik örnekler gerçek internet doğruluğunun ölçümü değildir.

Ağsız 30 tur denemesinde üç bulgu için üç bildirim oluştu; ikisi okunmamış kaldı. Zorla süreç kapatma (SIGKILL) sonrası tamamlanmış okundu/okunmadı kayıtları korundu. Bunlar tekrar ve kesinti davranışı doğrulamalarıdır; büyük ölçek veya canlı kaynaklarla uzun süreli çalışma ölçümü değildir.

Python 3.13.3 üzerinde doğrulandı. Minimum Python 3.11; diğer ortamlar ölçülmeden destek garantisi verilmez. Yeni özellik ortak modele/uygulama servisine, gerekli dış bağlantı adaptöre eklenir. Şema değişikliği eski veri testi ve kurtarma planıyla gelir. Kararlar: [yerel temel](decisions/0001-local-foundation.md), [çevrimdışı analiz](decisions/0002-offline-domain-analysis.md).

