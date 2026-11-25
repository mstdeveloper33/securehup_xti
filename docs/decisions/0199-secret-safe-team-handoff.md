# ADR 0199 — Anahtarsız ve sır güvenli ekip teslim kapısı

- **Tarih:** 25 Kasım 2026
- **Durum:** Kabul edildi
- **Sürüm:** 0.194.0

## Bağlam

XTI'nin yüzlerce yeteneği ve bazı isteğe bağlı dış kaynakları vardır. Yeni bir
ekip üyesinden bütün API hesaplarını hazırlamasını istemek temel kurulumu
gereksiz yere kırılgan yapar; yalnız `doctor` çalıştırmak ise sabit araçları,
yedek/geri dönüşü ve eksik dış gereksinimleri tek sonuçta göstermez.

## Karar

Repo kökünde `./handoff` adlı ayrı bir teslim adaptörü kullanılacaktır. Bu
adaptör mevcut kurulum, CLI JSON sözleşmesi, bileşen kataloğu ve kaynak
manifestlerini orkestre eder; yeni alan kuralı, veritabanı tablosu veya ağ
kaynak adaptörü oluşturmaz.

- `--plan` dosya, katalog ve dış gereksinimleri ağsız gösterir.
- Normal kontrol seçilen çalışma alanını yalnız `doctor` ile okur.
- Yazma/yedek/restore kabulü özel izinli geçici alanda yapılır ve silinir.
- İsteğe bağlı secret dosyalarının yalnız varlığı okunur; değer rapora girmez.
- Sonuçlar `pass`, `blocked_requirement`, `not_implemented`, `fail` olarak
  ayrılır; yalnız zorunlu kontroller genel teslim sonucunu belirler.
- Normal `full` profil yönetilen araçları zorunlu sayar; bilinçli hafif kurulum
  için `core` profili ayrıdır.
- İç içe kurulum denetleyicileri çalıştırılmaz. Aynı kurulum kilidinde bekleme
  riski yerine sabit bileşen kayıtları, tam paket sürümleri ve çevrimdışı
  capability kontrolleri okunur.

## Güvenlik ve veri kararı

Teslim aracı ücretli istek, canlı kaynak sorgusu, yeni tarama veya aktif hedef
kontrolü yapmaz. Kullanıcı verisini taşımak, eski şemayı kendiliğinden geçirmek
ve mevcut raporun üzerine yazmak yasaktır. JSON raporu yeni dosyaya `0600`
izniyle yazılır. Alt süreç kabul ortamından desteklenen secret ortam
değişkenleri ve kullanıcı config dizini çıkarılır.

## Reddedilen seçenekler

- Bütün API anahtarlarını kurulum ön koşulu yapmak.
- Canlı internet ve aktif Nmap taramasını genel teslim smoke testine eklemek.
- Aynı bilgiyi ikinci bir kaynak/özellik kataloğunda çoğaltmak.
- `doctor` içine dış araç kuran veya kullanıcı verisini değiştiren davranış
  eklemek.
- Kurulum kilidi altından tekrar exclusive installer denetimi başlatmak.

## Sonuçlar

Yeni ekip üyesi anahtarsız çekirdeği hemen kullanabilir; ürün sahibi hangi
özelliğin neden beklediğini tek raporda görür. Yapılandırma varlığı canlı
kaynak kabulü değildir. Temiz Linux, tam repo testi ve gerçek dış kaynak
kabulleri kendi kanıt kapılarında kalır.
