# XTI günlük kullanım

Bu belge 0.147.1 / çekirdek şema 69 kullanımını kapsar. Eski kayıt alanında
önce `./xti doctor` ile durumu kontrol et. Geçiş gerekiyorsa açık
`./xti migrate` komutu önce geri dönüş yedeği alır; şema 69 için yeniden
geçiş gerekmez. Çok firmalı kurulum ve kalıcı profil işleri
[platform rehberindedir](PLATFORM_ENGINE.md).

Kuruluşa özel HIBP bildirimleri için `./xti notices watch enable KURULUS_KIMLIGI`
ile açık izleme seçilir. Katalog yenilenince ilk ölçüm sessizdir; sonraki
ilgili yeni/değişen kayıtlar `./xti inbox` içinde görünür. Tam domain kapsamı,
önce/sonra kanıtı ve kapatma [kamu olay izlemesi rehberindedir](PUBLIC_NOTICE_WATCHES.md).

Bu örneklerde `example.com` yerine izleyeceğin domaini, `markam` yerine marka
kullanıcı adını yaz. Komutları proje klasöründe çalıştır. İlk kez kullanıyorsan
önce `./setup`, ardından şu komut yeterlidir:

```sh
./xti assets add example.com
```

## 1. Kaynakların durumuna bak

```sh
./xti sources status --domain example.com
```

Ekran, hangi aracın kurulu olduğunu ve eldeki kayıtların durumunu gösterir.
Hiç çalıştırılmamış kaynak, hata veren kaynak ve tamamlanmış boş arama ayrı
görünür. Satırdaki sonraki komut, eksik kurulumu veya veri yenilemeyi başlatmak
içindir. Durum ekranını açmak yeni arama başlatmaz.

### İstersen kayıtlarını kuruluş altında grupla

```sh
./xti organizations add "Markam"
./xti organizations link KURULUS_KIMLIGI --kind domain --value example.com
./xti organizations link KURULUS_KIMLIGI --kind ransomlook-watch --value IZLEME_KIMLIGI
./xti organizations show KURULUS_KIMLIGI
```

Kuruluş kimliğini `add`, izleme kimliğini ilgili `watch-list` çıktısından al.
Yalnız önceden kaydedilmiş domain ve izlemeleri bağlayabilirsin. Gruplama
internet sorgusu başlatmaz; sahiplik veya doğrulanmış ihlal anlamına gelmez.
Toplama için aşağıdaki profili ayrıca seçersin.

Grupladıktan sonra kayıtlı sonuçlarını birlikte görmek için:

```sh
./xti organizations report KURULUS_KIMLIGI
./xti changes --organization KURULUS_KIMLIGI --days 7
./xti sources contribution --organization KURULUS_KIMLIGI
```

İlk komut adresleri, profilleri, iddiaları, kaynak hatalarını ve ilgili vaka
bağlantılarını açar. İkinci komut haftalık önce/sonra değişimleri, üçüncü
komut domain bazında kaynak katkısını gösterir. Hiçbiri internet sorgulamaz.

Ücretsiz HIBP kamu olay kataloğunu ayrıca yenileyebilirsin:

```sh
./xti notices refresh
./xti notices search --domain example.com
```

Yalnız ilk komut internete çıkar. Olay metadata kayıtları tam domain
eşleşmesiyle kuruluş raporuna katılır; e-posta/parola sorgulanmaz.
İlk alımdaki tarihî olaylar yeni yaşanmış ihlaller değildir. Kullanım,
sayfalama ve CTI ilişkilerine geçiş [kuruluş rehberindedir](ORGANIZATION_REPORT.md).

### Haber ve güvenlik duyurularını oku

```sh
./xti news sources
./xti news refresh --source ncsc
./xti news list "example.com"
./xti search "example.com" --kind news
./xti news status
```

`refresh` internetten seçili yayını alır; diğerleri kayıtları okur.
`cisa` ve `cert-fr` diğer kaynaklardır. Yayınların eski haberleri akıştan
çıkarması yerel kanıtı silmez. Kaynak hatası önceki başarıdan ayrı görünür.

```sh
./xti search-watch add "Markam haberleri" "example.com" --kind news
./xti search-watch run ARAMA_KIMLIGI
```

Kimliği `add` çıktısından al. İlk çalışma sessiz başlangıçtır. Daha sonra
haber kaynağını yenile ve aynı aramayı yeniden çalıştır; yeni/anlamlı
değişmiş eşleşmeler `./xti inbox` içinde görünür. Kaynak toplama ve yerel
karşılaştırma ayrı komutlardır. Tam kullanım, kurulum ve sınırlar
[haber rehberindedir](../README.md#rss-ve-atom-haberlerini-topla).

## 2. Domain için veri topla

Marka aramalarını ve alt alan adı keşfini tek çalışmada yapmak için:

```sh
./xti collect example.com --plan
./xti collect example.com
```

İlk komut yalnız planı gösterir. İkinci komut iki marka kaynağını ve crt.sh
alt alan adı keşfini çalıştırır; her kaynağın sonucundan sonra birleşik analiz
verir. Bu komut kayıtlı domain ister ve aktif hedef kontrolü yapmaz. Kaynak
hatasında diğer kaynaklar devam eder; sonuç “kısmi” ise hatalı bölümü boş
arama olarak değerlendirme.

Aynı akışta iki IOC listesini de yenilemek için bütün istediğin işleri belirt:

```sh
./xti collect example.com \
  --task scan-crtsh --task scan-urlscan --task discover-crtsh \
  --task ioc-feodo --task ioc-certpl
```

`--task` varsayılan listeye ekleme yapmaz, onun yerine geçer. Arşiv kaynağı
isteğe bağlı `discover-theharvester` işidir ve ayrı kurulumu gerekir.

Kamu ihlal kataloğunu da aynı çalışmada yenilemek için `notices-hibp` işini
tam seçimine ekle:

```sh
./xti profiles save gunluk example.com \
  --task scan-crtsh --task scan-urlscan --task discover-crtsh --task notices-hibp
./xti collect --profile gunluk --plan
./xti collect --profile gunluk
```

Aynı adla `save` tam seçimi değiştirir; önceki profilindeki IOC, arşiv veya
izlemeleri de istiyorsan bu komutta açıkça belirt. Yalnız katalog istersen
`./xti collect example.com --task notices-hibp` yeterlidir; domain önceden
kayıtlı olmalıdır. Kaynak bir kez sorgulanır. Liste bütün kamu kataloğudur;
çıktıdaki toplam olay sayısı senin domainine ait olay sayısı değildir.

İlk başarılı alım başlangıçtır. Katalog/sonuç bağı birlikte kaydedildiği için
kesintiden sonra `collections resume` tamamlanan HIBP kaydını korur. Hata
durumunda eski katalog kalır ve yalnız başarısız iş yeniden denenebilir.
Kaynak atfı/lisansı çalışma geçmişinde de görünür. Profil mevcut Linux
zamanlayıcısıyla kullanılabilir; HIBP için ayrı zamanlayıcı kurulmaz.

Kayıtlı kullanıcı adı ve kuruluş izlemelerini de aynı çalışmaya ekleyebilirsin.
Kimlikleri `./xti brand watch-list`, `./xti ransomware watch-list` ve
`./xti ransomware watch-list --source ransomlook` çıktısından al. Sonra
kullanmak istediğin seçenekleri ekle:

```sh
./xti collect example.com \
  --username-watch SOSYAL_IZLEME_KIMLIGI \
  --ransomware-watch THREATCLUSTER_IZLEME_KIMLIGI \
  --ransomlook-watch RANSOMLOOK_IZLEME_KIMLIGI --plan
```

Büyük harfli yerleri gerçek kimliklerle değiştir; kullanmadığın seçenekleri
çıkar. `--plan` kaldırıldığında çalışma başlar. Bu seçenekler temel domain
işlerine eklenir ve birden fazla izleme için tekrarlanabilir. Domain adına
bakarak başka kullanıcı adı veya kuruluş izlemesi otomatik seçilmez.

Çıktı profil adreslerini, eşleşen iddiaları ve değişimlerini ayrı gösterir.
İlk ölçüm bir başlangıç kaydıdır. Ransomware kaynağı yenilenemezse o kaynağın
izlemeleri çalıştırılmaz; diğer işler devam eder. `--watch-item-limit 500`
ile her izlemede gösterilen öğeleri artırabilir, çıktıda verilen ayrıntı
komutuyla kayıtlı çalışmayı açabilirsin. Bu seçenek veri toplama sınırı değil,
sonuç görüntüleme sınırıdır.

Seçimlerin hazır olduğunda bir adla kaydedebilirsin:

```sh
./xti profiles save gunluk example.com --task scan-crtsh --task discover-crtsh
./xti profiles show gunluk
./xti collect --profile gunluk --plan
./xti collect --profile gunluk
```

`save` internet sorgulamaz; istediğin izleme kimliklerini aynı komuta
ekleyebilirsin. Profilde verilmeyen seçenekler varsayılan değerleriyle
kaydedilir. Aynı adla yeniden kaydettiğinde **tam seçim değiştirilir**;
eski seçim ve değişiklik sırası `profiles show` geçmişinde kalır. `--json`
çıktısı her eski tanımı tam gösterir. `collect --profile` ile ayrıca domain
veya seçenek verilmez; ayarı değiştirmek için profili yeniden kaydet.

`profiles list` etkin profilleri, `profiles list --all` geri çekilenleri de
gösterir. `profiles revoke gunluk --reason "Takibi duraklattım"` kaydı
silmeden çalıştırmayı kapatır. Bir izleme sonradan geri çekilirse profil
okunabilir kalır, fakat çalıştırma başlamaz. Profil kendi başına zamanlanmaz.
Linux'ta günlük/haftalık çalışma için `schedule generate` ile dosya üretip
açıkça etkinleştirebilirsin; yedek ve kurtarma adımları
[Linux zamanlama rehberindedir](LINUX_SCHEDULING.md).

Toplama çıktısındaki oturum kimliğiyle neyin tamamlandığını görebilirsin:

```sh
./xti collections list
./xti collections show OTURUM_KIMLIGI
./xti collections resume OTURUM_KIMLIGI --plan
./xti collections resume OTURUM_KIMLIGI
```

Son iki komut yalnız eksik işleri seçer. Tamamlanan izleme tekrar çalışmaz;
ransomware için eksik üyeler önce yeni kaynak yenilemesi ister. Kaynak
yenilenemezse eski liste yeni sonuç olarak kullanılmaz. Devam, eski sonucu
değiştirmeden yeni oturum oluşturur; bir sonraki denemede son oturum kimliğini
kullan. Profil veya eksik izlemenin ayarı değişmişse güncel seçimle yeni
`collect` başlat. Hiçbir sonuç sessizce yeni ayara uyarlanmaz.

Elektrik kesintisi sonrası oturum çalışıyor görünüyorsa `collections recover`
kayıtları kapatır; gerçek çalışan bir toplama varsa ortak kilit buna izin
vermez. `show` geçmişi okur, yeni analiz üretmez. Devam sonunda gösterilen
analiz bugünkü yerel kayıtlardandır. Eski sürümdeki toplamalar yeni birleşik
geçmişe geriye dönük eklenmez; eski kaynak geçmişleri yerinde kalır.

İşleri ayrı ayrı çalıştırmak da mümkündür:

```sh
./xti scan example.com
./xti surface discover example.com
```

`scan`, marka adına benzeyen adresleri sertifika ve geçmiş web inceleme
kayıtlarında araştırır. `surface discover` domainin alt alan adı adaylarını
sertifika kayıtlarından toplar. Bu iki komut internet kullanır ve sonuçları
yerel veritabanına kaydeder.

Yazım hatalı adları da aramak istediğinde `./xti scan example.com --typos`
kullanabilirsin. Daha fazla sorgu daha uzun sürebilir. Bir kaynak hata verirse
ekrandaki kısmi sonuç ve hata açıklamasını dikkate al; alınan kanıtlar korunur.

### İsteğe bağlı ek arşiv kaynağı

theHarvester için `git` ve ücretsiz `uv` kurulu olmalı. `uv` PATH'te veya
proje içindeki `.tools/uv/bin/uv` konumunda olabilir. Bir kez çalıştırılan
kurulum, aracı incelenmiş sürümüyle ayrı Python ortamına yerleştirir:

```sh
./scripts/setup-harvester
./xti surface discover example.com --source theharvester
./xti surface discovery-health example.com
./xti surface candidates example.com --status all
```

Bu profil yalnız Common Crawl ve Wayback Archive kayıtlarında alt alan adı
arar; hedef siteye aktif test yapmaz. `discovery-health` her sağlayıcının son
kayıtlı sonucunu ayrı gösterir; `candidates` bulunan adayları listeler.
Kısmi sonuç veya kaynak hatası, alt alan adı bulunmadığı anlamına gelmez.
Kurulumun tamamlanması arşivlerin o anda erişilebilir olduğunu garanti etmez.

Arşiv v3 sorgusu aynı domain için tekrarlı kapsam sorgusu göndermez; küçük
sayfalarla ilerler. Kaynaklardan biri kesilirse diğerinin doğrulanan sonucu
korunur. Süre/sonuç sınırında kalan çalışma “kısmi” görünür. Kota veya sunucu
bekleme bildirimi varsa komutu art arda çalıştırma; gösterilen nedeni ve
bekleme bilgisini dikkate al. Kaynak hatası hiçbir zaman “aday yok” değildir.

Common Crawl'ın çok sayıda arşiv dönemini sırayla yanıtlaması zaman alabilir:
bu kaynağa 150 saniye, ardından Wayback'e ayrı 90 saniye ayrılır. Her Common
Crawl yanıtından sonra en az bir saniye beklenir. Bağlantı kesilirse bütçe
yeterli olduğunda tek tekrar öncesinde 60 saniye beklenir; komut bu sırada
çalışmaya devam eder. İki arşivin toplam süreç sınırı 270 saniyedir.

## 3. İstersen ücretsiz tehdit kaynaklarını kullan

### Zararlı IP ve domain listeleri

```sh
./xti ioc sync --source feodo
./xti ioc sync --source certpl
./xti ioc status --source feodo
./xti ioc status --source certpl
./xti analyze example.com
```

`sync` internetteki listeyi yerel kataloğa alır; `status` ve `analyze`
kayıtlı veriyi okur. Feodo IP, CERT Polska domain kayıtları sağlar.
Katalogdaki toplam kayıt sayısı senin domainindeki bulgu sayısı değildir.
Analiz, eldeki domain ve IP kanıtlarını bu kayıtlarla karşılaştırır; IP
kanıtı yoksa IP karşılaştırması için kapsam eksik kalır. Kaynak hatasında
önceki geçerli katalog korunur; hata mesajını ve son başarılı tarihi kontrol et.

### Ransomware iddiaları

Önce iki ayrı kaynağın kayıtlarını al ve güncellemenin tamamlandığını kontrol et:

```sh
./xti ransomware refresh --source threatcluster
./xti ransomware status --source threatcluster
./xti ransomware refresh --source ransomlook
./xti ransomware status --source ransomlook
```

İzlemeleri bir kez oluştur. `Markam` yerine kuruluşunun adını yaz:

```sh
./xti ransomware watch-add "Markam domain" example.com --kind domain --source threatcluster
./xti ransomware watch-add "Markam kuruluş" "Markam" --kind organization --match contains --source ransomlook
```

RansomLook domain bilgisi sağlamaz; yalnız kuruluş adı izlenir. `contains`,
adın kaynak başlığı içinde geçmesini arar ve en az 5 karakter ister.
Benzer adlı başka kuruluşlar da eşleşebilir. Yalnız tam ad eşleşmesini
istiyorsan `--match exact` kullan.

Komutların verdiği kimlikleri aşağıdaki yer tutucuların yerine yaz:

```sh
./xti ransomware watch-run THREATCLUSTER_IZLEME_KIMLIGI --source threatcluster
./xti ransomware watch-show THREATCLUSTER_IZLEME_KIMLIGI --source threatcluster
./xti ransomware watch-run RANSOMLOOK_IZLEME_KIMLIGI --source ransomlook
./xti ransomware watch-show RANSOMLOOK_IZLEME_KIMLIGI --source ransomlook
```

`watch-run` internete çıkmaz; son başarılı yerel kaynak kaydını izleme
ifadenle karşılaştırıp sonucu saklar. `watch-show` bu geçmişi gösterir.
Yenileme başarısızsa önce sorunu incele; eski başarılı kayıt üzerinden
yapılan karşılaştırmayı yeni canlı sonuç olarak değerlendirme.

İlk başarılı kaynak ve izleme çalışmaları karşılaştırma başlangıcıdır;
katalogdaki kayıtlar otomatik olarak sana ait alarm sayılmaz. İki kaynağın
geçmişi ayrıdır. ThreatCluster'ın çıktıdaki zaman penceresi ve RansomLook'un
son yedi günlük kapsamı dışında sonuç çıkarılmaz. Eşleşme bulunmaması bu
sınırlı kapsamda sonuç olmadığını söyler; güvenli olunduğunu kanıtlamaz.
Bulunanlar kaynak iddialarıdır; doğrulanmış ihlal değildir.

İlk RansomLook ölçümünden sonraki yeni/değişen eşleşmeler yerel kutuda
çalışma başına tek bildirim oluşturur:

```sh
./xti inbox
./xti inbox show BILDIRIM_KIMLIGI
./xti ransomware watch-run-show CALISMA_KIMLIGI --source ransomlook
./xti inbox read BILDIRIM_KIMLIGI
```

İlk ölçüm, değişmeyen tekrar, yalnız pencereden çıkış ve kaynak hatası
bildirim üretmez. Okundu işareti iddiayı doğrulamaz; kaynakların kimlikleri
ayrı kalır. Eski çalışmalara geriye dönük bildirim eklenmez.

### Genel aramayı kaydet ve bildirim al

Mevcut toplayıcılarla verileri yeniledikten sonra:

```sh
./xti search-watch add "Markam" "example.com"
./xti search-watch run ARAMA_KIMLIGI
./xti search-watch monitor ARAMA_KIMLIGI --cycles 10 --interval 60 --duration 600
./xti inbox
./xti inbox show BILDIRIM_KIMLIGI
./xti search-watch run-show CALISMA_KIMLIGI --limit 50
```

Arama kimliği `add` çıktısındadır. İlk çalışma sessizdir; sonraki yeni veya
değişen eşleşmeler tek yerel bildirimde toplanır. Yalnız artık eşleşmeyen
kayıtlar geçmişe yazılır, bildirim oluşturmaz. Her iki durumun eski/yeni
kanıtı gösterilir. Bu, yerel kayıt değişimidir; yeni ihlal hükmü değildir.

`monitor` kaynakları internetten yenilemez; terminal açıkken karşılaştırır.
İnternet toplayıcılarını ayrı çalıştırabilirsin. Aynı adla `add` tanımı
günceller; yeni tanım veya yeniden etkinleştirme sessiz başlangıç yapar.
`search-watch disable ARAMA_KIMLIGI --reason "İzleme tamamlandı"` geçmişi
silmeden durdurur. Eski kurulumda önce `./xti migrate` gerekir.
[Kapsam, sayfalama ve sınırlar](../README.md#genel-aramayı-kaydet-ve-değişiklikleri-izle).

### Farklı kaynaklardaki olayları birlikte incele

Ransomware kaynaklarını yukarıdaki komutlarla, kamu ihlal kataloğunu
`./xti notices refresh` ile yeniledikten sonra:

```sh
./xti events candidates
./xti events candidates --domain example.com --limit 20
```

`example.com` yerine ilgili domaini yaz. Bu görünüm yalnız kayıtlı veriyi
okur; sonuçtaki kaynak zamanı verinin ne kadar güncel olduğunu gösterir.
Henüz toplanmamış veya son denemesi hatalı kaynaklar ayrıca yazılır.

- **Aynı olay olabilir:** İki ransomware kaynağında kuruluş adı ve grup
  eşleşir, kaynak keşif zamanları en fazla 72 saat aralığındadır.
- **Ortak kuruluş/domain bağlamı:** Örneğin kamu kataloğundaki eski bir
  olayla yeni ransomware iddiasında aynı domain geçer; bu, aynı olay demek
  değildir. Tarihler kendi anlamlarıyla yan yana gösterilir.

Komut her çiftin kaynak bağlantısını, özgün kayıtlarını ve gerekçesini
gösterir. Güncel kaynak kaydı eski kararın dondurulmuş kanıtından farklıysa
bunu belirtir.
Kayıtları birleştirmez, alarm veya yeni insan kararı yazmaz. Diğer sayfa
varsa çıktının sonundaki komutu kullan. [Kural ve kapsam ayrıntıları](../README.md#kaynaklar-arası-olay-adaylarını-incele).

### MITRE tehdit bilgi tabanı

Tehdit grubu, kampanya, zararlı yazılım, teknik ve taktik kayıtlarını araştırmak için:

```sh
./xti cti attack-sync
./xti cti attack-status
./xti cti attack-search "DNS"
./xti cti attack-show T1059.001
./xti cti attack-show T1105 --relationship-limit 500 --relationship-offset 500
./xti cti search "APT29" --kind entity
./xti cti entity-list --type threat-actor --limit 20
```

`attack-sync` resmî MITRE kaynağından sürümü sabitlenmiş Enterprise ATT&CK
v20.0 verisini alır. Arama ve listeleme komutları yerel kayıtları okur;
internete çıkmaz. Bir kaydın bağlantılarını görmek için arama veya listeleme
çıktısındaki gerçek kimliği `VARLIK_KIMLIGI` yerine yaz:

```sh
./xti cti entity-show VARLIK_KIMLIGI
./xti cti relation-list --entity VARLIK_KIMLIGI --limit 20
```

Teknikler, alt teknikler ve taktikler kesin ATT&CK kimlikleriyle ayrı
katalogda saklanır; aynı adlı kayıtlar karışmaz. `attack-search DNS --limit 50 --offset 50` arama sayfasını, `--relationship-offset` ilişki sayfasını ilerletir.
Teknik–taktik alan bağı, kaynakta verilen STIX ilişkisinden ayrı gösterilir.
Bütün STIX veri türleri bu kapsamda değildir. Bir grubun
katalogda bulunması domainine saldırdığı anlamına gelmez. Senkron yalnız
komutu çalıştırdığında yapılır; otomatik zamanlama veya sürüm yükseltme yoktur.

## 4. Marka kullanıcı adı izlemesini bir kez oluştur

```sh
./xti brand watch-add "Markam Maigret" markam --site GitHub --site Instagram
./xti brand watch-add "Markam Sherlock" markam --source sherlock --site Carrd --site Rumble
./xti brand watch-list
```

Çıktıdaki izleme kimliklerini kullanarak her izlemeyi çalıştır:

```sh
./xti brand watch-run MAIGRET_IZLEME_KIMLIGI
./xti brand watch-run SHERLOCK_IZLEME_KIMLIGI
```

`MAIGRET_IZLEME_KIMLIGI` ve `SHERLOCK_IZLEME_KIMLIGI` örnek yer tutuculardır;
komuta çıktıda gördüğün gerçek kimliği yaz. Sonraki günlerde aynı izlemeleri
yeniden oluşturman gerekmez. Her kaynak kendi çalışma geçmişini saklar.

İlk başarılı tur karşılaştırma başlangıcıdır. Sonraki tur yeni bulunan,
adresi değişen, değişmeyen veya artık raporlanmayan profilleri gösterir.
“Raporlanmadı” hesabın bulunmadığını ya da silindiğini kanıtlamaz. “Bulundu”
aynı kullanıcı adına ait bir profil işaretidir; resmî hesap veya taklit
olduğuna ilişkin karar ayrıca inceleme gerektirir.

## 5. Sonuçları incele

```sh
./xti sources status --domain example.com
./xti analyze example.com
./xti triage
./xti findings list
./xti findings show BULGU_KIMLIGI
./xti brand watch-show IZLEME_KIMLIGI
./xti inbox
```

Bu komutlar kayıtlı sonuçları okur. `analyze` domainin mevcut kanıtını bir
araya getirir; `triage` incelenecek adayları nedenleriyle sıralar. `findings
show` seçilen adayın kaynaklarını gösterir. Listedeki `BULGU_KIMLIGI` gerçek
bulgu kimliğiyle değiştirilmelidir. Birden çok domain izliyorsan `findings
list` içindeki “İzlenen” alanına bak.

Hiç aday görünmüyorsa kaynak durumunu kontrol et. Başarısız arama ile
tamamlanan aramada eşleşme bulunmaması aynı anlama gelmez.

### Günlük değişimi ve kaynak katkısını gör

```sh
./xti changes --days 1
./xti changes --days 7
./xti changes --days 7 --domain example.com
./xti sources contribution example.com
./xti sources contribution example.com --detail-limit 50 --detail-offset 50
./xti --json sources contribution example.com
```

İlk iki komut bütün yerel izlemelerin son 24/168 saatte kaydedilen
başlangıçlarını, değişimlerini ve kaynak hatalarını ayrı gösterir. Domain
filtresi marka, dış yüzey ve tam domain eşleşmeli kamu olaylarını seçer.
`--organization KURULUS_KIMLIGI` güncel etkin domain ve izlemeleri birlikte
seçer. `--offset` ile sonraki sayfaya ulaşabilirsin.

Katkı görünümü sayaçların yanında gerçek ortak/ayrı domainleri ve kanıt
kimliklerini verir. `--family brand` veya `--family surface` bir alanı seçer.
Yüzde, kayıtlı denemelerin tamamlanmasıdır; kaynağın doğruluğu veya internetin
kapsanma oranı değildir. Sayfalar toplamı değiştirmez. Bu komutların tamamı
internetsiz ve yazmasızdır; insan inceleme kararları korunur.

Domain keşfi/marka aramasına yeni sağlayıcı eklenmedi; HIBP ayrı bir kamu
olay kataloğudur. Mevcut ölçümler bağımsız katkı göstermeden yeni domain
sağlayıcısı seçilmeyecek. Common Crawl'ın dış erişim sorunu açık kalır;
kaynak hatası, hiç adres bulunmadığı anlamına gelmez.

## 6. Takip edeceğin gerçek adayı vakaya ekle

İncelemeye değer bir domain adayı varsa aşağıdaki akışı kullan. Örnekteki
başlığı, özeti ve gerekçeyi yaptığın incelemeye göre değiştir:

```sh
./xti cases create "Markam aday incelemesi" \
  --summary "Pasif kaynakta görülen benzer adresin incelenmesi" \
  --priority low --reason "Kaynak kanıtını takip etmek için"
./xti cases evidence-add VAKA_KIMLIGI --type finding \
  --evidence-id BULGU_KIMLIGI --reason "İncelenecek adayın kaynak kaydı"
./xti cases task-add VAKA_KIMLIGI "Adayın marka ilişkisini doğrula" \
  --reason "İnceleme tamamlanmadan karar verilmeyecek"
./xti cases report VAKA_KIMLIGI
```

`VAKA_KIMLIGI`, vaka oluşturma komutunun verdiği kimliktir. Vaka açılması
adayın tehdit olarak doğrulandığı anlamına gelmez. Sosyal profil kanıtı
eklemek için önce o tam profil hakkında gerekçeli insan incelemesi gerekir.
Sonuç yoksa örneği tamamlamak için kanıt veya inceleme kararı oluşturma.

## 7. Sonraki gün tekrar et

```sh
./xti sources status --domain example.com
./xti scan example.com
./xti surface discover example.com
./xti brand watch-run MAIGRET_IZLEME_KIMLIGI
./xti brand watch-run SHERLOCK_IZLEME_KIMLIGI
./xti analyze example.com
./xti inbox
./xti cases list
./xti backup
```

Ücretsiz tehdit kaynaklarını da kullanıyorsan 3. bölümdeki `ioc sync` ve
`ransomware refresh` komutlarını tekrarla. Her kaynağın durumunu ayrı kontrol
et; yenilemesi başarılı olan ransomware kaynağı için mevcut izleme
kimliğiyle `watch-run` ve `watch-show` çalıştır. İzlemeleri yeniden oluşturma.
Bu komutlar arka planda otomatik zamanlama başlatmaz; RansomLook izlemesi
de açık yenileme ve çalıştırma ister.

Aynı domain kanıtı yeniden geldiğinde mevcut aday ve karar geçmişi korunur.
Sosyal izleme son başarılı ölçümle karşılaştırılır; kaynak hatası önceki
profilleri silmez. Vaka kanıtı eklendiği andaki görünümü saklar. Kaynak
gerçekten değiştiyse inceleyip aynı `cases evidence-add` komutuyla vakadaki
görünümü yenileyebilirsin; önceki vaka hareketleri korunur.

Bu rutin komutları çalıştırdığın zaman işler. Yerel veriler `.xti-data`
klasöründedir; GitHub'a gönderilmez. Yedeği ayrıca başka bir diskte sakla.

## Tarihî kanıtı vakaya bağla ve HTML raporu al

`cases evidence-add` tam kaynak/izleme çalışma kimliği ve olay adını seçer.
`organizations export KURULUS_KIMLIGI --output rapor.html` bütün kuruluş
raporunu yeni bir dosyaya yazar. [Adım adım kullanım](PUBLIC_NOTICE_CASES_AND_EXPORT.md).
