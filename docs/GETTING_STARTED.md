# XTI hızlı başlangıç

XTI'nin temel kullanımı için yalnız Git ve Python 3.11 veya daha yeni bir
sürüm gerekir. Global Python ortamına paket kurulmaz; temel çekirdeğin harici
Python bağımlılığı yoktur.

## 1. Klonla ve hazırla

```sh
git clone https://github.com/mstdeveloper33/securehup_xti.git
cd securehup_xti
./setup
```

`./setup`, Python sürümünü denetler ve yalnız proje içindeki `.xti-data`
klasöründe yerel veritabanını oluşturur. Mevcut veriyi silmez veya eski bir
veritabanını kendiliğinden taşımaz. Eski sürüm uyarısı görürsen önce:

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

`scan`, herkese açık sertifika ve geçmiş web inceleme kayıtlarını araştırır.
Bulunan kayıtlar adaydır; tek başına phishing veya kötü niyet kanıtı değildir.

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
```

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

## İsteğe bağlı sosyal kullanıcı adı araçları

Maigret ve Sherlock temel kurulumun parçası değildir. Bu özelliği kullanmak
istediğinde, incelenmiş ve sabitlenmiş sürümleri ayrı yerel ortama kur:

```sh
./scripts/setup-brand
```

Bu adım internet bağlantısı kullanır ve üçüncü taraf paketleri indirir. Domain,
vaka, IOC, CTI, tedarikçi ve temel dış yüzey işlevlerini kullanmak için gerekli
değildir.

## Güncelleme

Yeni geliştirmeleri aldıktan sonra:

```sh
git pull
./setup
```

`./setup` eski şemayı otomatik değiştirmez. Bir geçiş gerekiyorsa açıkça
`./xti migrate` çalıştırmanı ister; böylece yerel verin sessizce değiştirilmez.

