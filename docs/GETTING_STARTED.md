# XTI hızlı başlangıç

XTI için Git, Python 3.11 veya daha yeni bir sürüm ve ilk kurulumda internet
bağlantısı gerekir. Global Python ortamına paket kurulmaz; üçüncü taraf araçlar
yalnız proje içindeki `.venv` ortamında tutulur.

## 1. Klonla ve hazırla

```sh
git clone https://github.com/mstdeveloper33/securehup_xti.git
cd securehup_xti
./setup
```

`./setup`, mevcut `.venv` ortamını geçici geri dönüş kopyası olarak koruyup
sabitlenmiş Maigret ve Sherlock ortamını aynı kararlı yolda kurar. Bütün
doğrulamalar geçerse eski kopyayı kaldırır; indirme veya doğrulama yarıda
kalırsa önceki ortamı geri getirir. Ardından `.xti-data` içindeki yerel
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
kullanılır. Yalnız domain, vaka, IOC, CTI, tedarikçi ve dış yüzey çekirdeğini
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

Yeni geliştirmeleri aldıktan sonra:

```sh
git pull
./setup
```

`./setup` eski şemayı otomatik değiştirmez. Bir geçiş gerekiyorsa açıkça
`./xti migrate` çalıştırmanı ister; böylece yerel verin sessizce değiştirilmez.

