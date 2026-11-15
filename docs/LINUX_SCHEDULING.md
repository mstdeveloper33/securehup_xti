# Linux'ta kayıtlı profili zamanlama

0.140.4'ün gerçek Ubuntu kabulünde üretilen systemd hizmeti, durdurma ve
yeniden çalışma, çakışma reddi ve kaçırılmış zamanın tek telafisi geçti.
[Süreli kullanım ve disk ölçümleri](STATUS.md) test ortamıyla kaydedilir;
işletim sistemi yeniden açılışı veya 7/24 hizmet seviyesi bu kabulden
çıkarılmaz. Kendi makinenizde etkinleştirme aşağıdaki açık adımlarla yapılır.

Bu özellik kişisel Linux bilgisayarında bir profili günlük veya haftalık
çalıştırır. Ücretli servis gerektirmez. Bilgisayar açık ve internete bağlı
olmalıdır; kaynakların erişim sınırları devam eder. Linux ve systemd 247+
kullanıcı hizmetleri gerekir. macOS'ta dosyalar hazırlanabilir; Linux
hizmetinin gerçekten çalıştığı bu işlemle doğrulanmış olmaz.

## 1. Profili kontrol et

Önceden kayıtlı domain için örnek:

```sh
./xti profiles save gunluk example.com
./xti collect --profile gunluk --plan
```

`example.com` yerine kayıtlı domainini kullan. İlk komut aynı adlı profil
varsa seçimini tamamen değiştirir. Sosyal/ransomware izlemeleri yalnız açık
kimlikle profile eklenir; kendiliğinden tüm izlemeler çalıştırılmaz.

HIBP kamu olay kataloğunu da aynı profile eklemek için tam seçimi yaz:

```sh
./xti profiles save gunluk example.com --task scan-crtsh --task scan-urlscan --task discover-crtsh --task notices-hibp
./xti collect --profile gunluk --plan
```

Bu örnek varsayılan üç işe HIBP'yi ekler. Yalnız HIBP istersen tek
`--task notices-hibp` kullan. HIBP sayıları ortak katalog toplamıdır;
domainine ait olayların sayısı değildir. Profil kaydı ve plan ağ kullanmaz;
katalog, profili çalıştırdığında veya zamanlanan hizmet çalıştığında yenilenir.

## 2. Zamanlama dosyalarını üret

Her gün Türkiye saatiyle 09.00:

```sh
./xti schedule generate gunluk --output ./.xti-data/zamanlama-gunluk --at 09:00 --timezone Europe/Istanbul --keep 7
```

Haftalık kullanım için aynı komuta `--weekday Mon` ekle; günler
`Mon Tue Wed Thu Fri Sat Sun` olabilir. `--keep` son kaç **yönetilen** yedeğin
tutulacağını belirtir; 1–30 arasındadır. Çıktı klasörü yeni olmalıdır.

Komut internetten veri toplamaz ve hizmeti etkinleştirmez. Ürettiği
`README.txt` dosyasında bu bilgisayarın tam yollarına göre hazırlanmış
kontrol, etkinleştirme, durum, günlük ve durdurma komutları vardır. Linux'ta
dosyaları inceleyip bu komutları sırayla çalıştır. Üretilen dosyaları veya
repo klasörünü etkinleştirdikten sonra taşımak hizmet yolunu bozar.

Kullanıcı oturumu kapalıyken çalışma için sistemin kullanıcı hizmetlerini
açık tutması gerekir. Gerekiyorsa Linux üzerinde `loginctl enable-linger`
ayarı ayrıca yapılır; XTI bunu değiştirmez. Bilgisayar kapalıyken kaçan her
tur tek tek çalıştırılmaz; yeniden açılışta bir telafi çalışması olabilir.

## 3. Sonuçları oku

```sh
./xti collections list
./xti changes --days 1
./xti inbox list
```

Ayrıntı için `collections show OTURUM_KIMLIGI`; yalnız eksik adımları tekrar
etmeden önce `collections resume OTURUM_KIMLIGI --plan` kullan. Kaynak hatası
başarı gibi gösterilmez. Zamanlayıcı hata sonrası peş peşe tekrar denemez;
bir sonraki planlı zaman veya açık kullanıcı komutu beklenir.

Profil yeniden kaydedilirse sonraki çalışma güncel seçimi kullanır. Profil
geri çekilirse çalışma başlamaz. Durdurma komutları üretilen `README.txt`
içindedir. Aynı profilin saatini değiştirmek için önce eski zamanlayıcıyı
durdur; yeni klasöre dosya üret, aynı birim adının bağlantısını yeni dosyalara
güncelle ve `daemon-reload` sonrasında tekrar etkinleştir.

## Çalışma öncesinde yapılan bakım

Elle denemek için:

```sh
./xti schedule prepare gunluk --keep 7
```

Bu komut toplama başlatmaz. Ortak çalışma kilidi altında profil ve disk
alanını kontrol eder, gerçekten kesilmiş toplama oturumlarını kapatır,
SQLite yedeği alır ve onu yeni geçici dosyaya geri yükleyerek doğrular.
Yedek/geri dönüş başarısızsa zamanlanmış toplama başlamaz. Meşgul çalışma
zorla durdurulmaz. Başarılı geçmiş ve tamamlanan kaynak kanıtı korunur.

Yedekler veri klasörünün `scheduled-backups/` bölümündedir. XTI yalnız
kendi sahiplik kaydı ve dosya özeti doğrulanan eski yedeklerini azaltır.
Bu havuz aynı veritabanının bütün profillerince paylaşılır; `--keep 7`
profil başına yedi değil, havuzun son yedi yedeğini tutar. Birden çok profili
zamanlarken aynı saklama sayısını kullan.
Elle alınmış yedekler, `backups/` içindeki geçiş yedekleri ve ilgisiz
dosyalar silinmez. Kayıp/değişmiş yönetilen yedekte işlem açıklayıcı hatayla
durur. Sahiplik kaydını veya yönetilen dosyaları elle değiştirme.

Aynı diskte yedek, disk arızasına karşı koruma sağlamaz. Ayrı bir ortama
kopyalama kişisel bakımın parçasıdır. `storage readiness` mevcut `backups/`
envanterini gösterir; zamanlanmış yedeğin ayrı kurtarma sonucu `schedule
prepare` çıktısındadır. Birindeki kontrol diğerinin sonucu diye sunulmaz.

Uygulama güncellemesinde zamanlayıcıyı durdur, devam eden çalışmanın bitmesini
bekle, kodu güncelle ve gerekiyorsa `./xti migrate` çalıştır. Ardından
`collect --profile gunluk --plan` ile kontrol edip zamanlayıcıyı etkinleştir.
