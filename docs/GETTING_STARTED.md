# XTI hızlı başlangıç

XTI için Git, Python 3.11 veya daha yeni bir sürüm ve ilk kurulumda internet
bağlantısı gerekir. Global Python ortamına paket kurulmaz; Maigret ve Sherlock
proje içindeki `.venv` ortamında tutulur. İsteğe bağlı theHarvester ayrı
`.tools/theharvester` ortamını kullanır; kurulumu ve kaynakları
[günlük kullanım rehberinde](DAILY_USE.md) anlatılır.

## 1. Klonla ve hazırla

```sh
git clone https://github.com/mstdeveloper33/securehup_xti.git
cd securehup_xti
./setup
```

`./setup`, sağlıklı mevcut ortamı tekrar indirmez. Kurulum gerektiğinde
`.venv` ortamını benzersiz geri dönüş kopyası olarak koruyup sabitlenmiş
Maigret ve Sherlock ortamını aynı kararlı yolda kurar. Eski ve başarısız
kopyalar otomatik silinmez. Normal hatada önceki ortam geri getirilir;
ani veya durumu belirsiz kesintide `./scripts/setup-brand --recover`
kullanılır. Ardından `.xti-data` içindeki yerel
veritabanını hazırlar. Kullanıcı verisini silmez ve eski veritabanını
kendiliğinden taşımaz. Eski sürüm uyarısı görürsen önce:

```sh
./xti migrate
```

Komut, değişiklikten önce doğrulanmış bir kurtarma yedeği alır.

## 2. İlk domainini izle

Yalnız sana ait olan veya izleme iznin bulunan domaini ekle:

```sh
./xti assets add example.com
./xti scan example.com --typos
./xti status example.com
./xti triage
```

Kurulum ve veri durumunu tek ekranda görmek için `./xti sources status --domain
example.com` çalıştır. `--details` kaynak kapsamını ve zamanlarını açar.
Sonraki kullanım adımları [günlük kullanım rehberinde](DAILY_USE.md) bulunur.
Kayıtlar arasında tek komutla aramak, tedarikçi bildirimlerini açmak ve
domainin ilişki geçmişini görmek için
[arama ve izleme rehberini](SEARCH_SUPPLIERS_AND_RELATIONS.md) kullan.
Birden fazla domain/izlemeyi birlikte görmek için
[kuruluş raporu rehberini](ORGANIZATION_REPORT.md) kullanabilirsin; ücretsiz
kamu ihlal kataloğu ve doğrudan CTI ilişkileri de aynı rehberdedir.
Kayıtlı profili Linux'ta günlük/haftalık çalıştırmak için
[zamanlama rehberini](LINUX_SCHEDULING.md) kullanabilirsin; kurulum kendi
başına arka plan hizmeti etkinleştirmez.

`scan`, herkese açık sertifika ve geçmiş web inceleme kayıtlarını araştırır.
Bulunan kayıtlar adaydır; tek başına phishing veya kötü niyet kanıtı değildir.

İki pasif alt alan adı sağlayıcısının kayıtlı durumunu ayrı görmek için:

```sh
./xti surface discovery-health example.com
```

Bu komut yeni internet isteği yapmaz. `crt.sh` ve isteğe bağlı theHarvester'ın
son kayıtlarını tamamlandı, kısmi, başarısız veya hiç çalışmadı biçiminde ayrı
gösterir. Güncel kayıt, kaynağın o anda canlı olduğu anlamına gelmez.

## 3. Sonraki kullanımlar

Proje klasöründe şu komut yeterlidir:

```sh
./xti status
./xti scan
```

Komutların listesini ve her komutun seçeneklerini şöyle görebilirsin:

```sh
./xti --help
./xti scan --help
./xti surface source-evaluation
```

Son komut pasif kaynakların neden kabul edildiğini ve incelenip ertelenen
araçları sürümlü, ağsız bir raporda gösterir.

## Verinin konumu

Varsayılan kişisel veri klasörü `.xti-data` dizinidir. Bu klasör Git tarafından
yok sayılır ve GitHub'a gönderilmez. Başka konum kullanmak istersen:

```sh
XTI_DATA_DIR=/guvenli/bir/konum ./xti init
XTI_DATA_DIR=/guvenli/bir/konum ./xti status
```

Yedek almak için:

```sh
./xti backup
```

## Sosyal kullanıcı adı araçları

Maigret ve Sherlock normal kurulumun parçasıdır. Kurulu sürüm, resmî Git depo
adresi, tam commit ve site kataloğu özeti şu komutla ağsız doğrulanabilir:

```sh
./scripts/setup-brand --check
```

Onarım veya bilinçli temiz yeniden kurulum için `./scripts/setup-brand --force`
kullanılır. Çalışan XTI komutu varken ortam değiştirilmez; uzun izlemeyi
bitirdikten sonra yeniden kurulumu başlat. Eski kilit/yedek dosyalarını
tahmin ederek silme; [kurulum ve kurtarma rehberi](BRAND_INSTALLATION.md)
korunan dosyaları ve yarım kurulum adımlarını açıklar.
Yalnız domain, vaka, IOC, CTI, tedarikçi ve dış yüzey çekirdeğini
istiyorsan ilk kurulumda `./setup --core-only` diyebilirsin; daha sonra
`./scripts/setup-brand` ile sosyal araçları ekleyebilirsin.

Kullanıcı adı aramasında varsayılan dar kapsam `safe` profilidir. İncelenmiş
geniş kapsam için:

```sh
./xti brand profile-list
./xti brand username-preview markam --profile extended
./xti brand username-preview markam --source sherlock --profile extended
```

Tek tek seçim için bir veya daha fazla `--site` kullan. `--profile` ve `--site`
aynı komutta kullanılamaz.

## Güncelleme

Önce eski sürümle açık kalan uzun izleme/toplama komutlarını bitir.
Yeni geliştirmeleri aldıktan sonra:

```sh
git pull
./setup
```

`./setup` eski şemayı otomatik değiştirmez. Bir geçiş gerekiyorsa açıkça
`./xti migrate` çalıştırmanı ister; böylece yerel verin sessizce değiştirilmez.

## Sorun sonrası kaldığın yerden devam et

Önce `./xti doctor` ve `./xti sources status` ile yerel veri ve kaynak
durumunu oku. Kaynak hatası, hiç sonuç bulunmaması veya kurulumun yarım
kalması farklı durumlardır. Kaynak kesintisinde kayıtlarını sıfırlama.

Marka araçlarının kurulumu yarım kalmışsa:

```sh
./scripts/setup-brand --recover
./scripts/setup-brand --check
```

İsteğe bağlı theHarvester kurulumu için aynı sıra
`./scripts/setup-harvester --recover` ve `./scripts/setup-harvester --check`
şeklindedir. Kurulum başka bir komut tarafından kullanılıyorsa kilidi veya
günlük dosyasını silme; çalışan komutun bitmesini bekle. İlk kurulum
tamamlanmadan kesildiyse kurtarmanın ardından normal kurulum komutunu
yeniden çalıştır. Kurtarma geçmişte sağlıklı bir ortam yaratmış sayılmaz.

Toplama komutu kesildiyse:

```sh
./xti collections list
./xti collections recover
./xti collections show OTURUM_KIMLIGI
./xti collections resume OTURUM_KIMLIGI --plan
```

`OTURUM_KIMLIGI` yerine listeden ilgili kaydı kullan. Planı kontrol ettikten
sonra aynı `resume` komutunu `--plan` olmadan çalıştır. Bu işlem eksik
adımlar için kaynaklara yeniden bağlanabilir; tamamlanan kaynak kanıtı ve
önceki oturum geçmişi korunur. Çalışan işin kurtarılması kabul edilmez.

Yedeği mevcut dosyanın üzerine yazmadan sınamak için:

```sh
./xti backup --output ./kurtarma-yedegi.db
./xti --data-dir ./.xti-kurtarma-denemesi restore ./kurtarma-yedegi.db
./xti --data-dir ./.xti-kurtarma-denemesi doctor
```

Yedek dosyası ve geri yükleme hedefi yeni olmalıdır; sonraki denemede yeni
isim seç. Kurtarılan kayıtları bu veri alanını seçerek incele. Bu adımlar
asıl veri alanını değiştirmez; doğrulama tamamlanmadan eski kayıtları silme.
Yedeğin açılabilmesi, bütün kanıt ve kararların anlam bakımından doğru
olduğunu tek başına göstermez; kurtarılan kayıtları ilgili komutlarla incele.
Şema değiştiyse eski kodu mevcut veritabanında denemek yerine o sürüme ait
yedeği ayrı veri alanına geri yükle. Aynı şemadaki sınanmış sürüm geçişi,
bütün geçmiş/gelecek sürümlere dönüş garantisi değildir.

Yedek SQLite kayıtlarını ve kayıtlı webhook adres/anahtarlarını içerir;
paylaşılacak rapor olarak kullanılmaz. Veritabanı, yedek ve anahtar dosyası
yalnız sahibinin okuyabildiği izinlerle oluşturulur. Yedek veritabanı,
ayrıca ürettiğin HTML raporlarını veya dışarıda tuttuğun dosyaları içeren
bir klasör arşivi değildir. Ayrı diskte saklamak disk arızasına karşı
ayrıca gereklidir.

