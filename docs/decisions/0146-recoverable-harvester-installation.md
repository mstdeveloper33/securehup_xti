# 0146 — theHarvester kurulumunda koruma, kilit ve kurtarma

Tarih: 15 Kasım 2026. Durum: 0.140.2'de uygulandı; STB-02'nin araç dilimi.

## Sorun

Önceki betik çalışan checkout'u yerinde değiştiriyor, bağımlılık kurulumu
veya açılış kontrolü başarısız olduğunda önceki ortamı geri getirmiyordu.
Kurulum ile arşiv işçisi arasında ortak kilit ve kesinti günlüğü yoktu.

## Karar

- İncelenen araç kimliği `domain.component_pins.HARVESTER_PIN` içinden
  alınır. Shell başlatıcı proje Python seçimini kullanır; kurulum yordamı
  standart kütüphaneli ayrı betiktedir. Domain/application katmanına
  dosya sistemi veya süreç yönetimi eklenmez.
- Kalıcı inode üzerindeki POSIX `flock`, kurulum için özel, arşiv işçisi
  için paylaşımlıdır. Kilit dosyası silinmez. Çocuk süreçlere descriptor
  aktarılır; üst sürecin ölümü yaşayan çocuğun kilidini bırakmaz.
- Önceki checkout benzersiz yedeğe ayrılır. Yeni sanal ortam son konumunda
  kurulur; hazırlanmış sanal ortamın taşınmasıyla mutlak shebang yolları
  bozulmaz. Yakalanan hata ve kesintide eski klasör geri gelir.
- Sınırlı ve katı JSON günlük UUID, işlem evresi ve dizin dev/inode
  kimliklerini saklar. Kalıcı günlük rename adımlarından önce yayımlanır;
  doğrulama sonrası committed evresi kaydedilir. Kurtarma yalnız tanınan
  dizin düzenlerini değiştirir; bilinmeyen dosyalar korunur.
- Git/uv/yardım komutları zaman sınırlıdır. Yakalanabilen kesintide sahibi
  olduğumuz süreç grubu durdurulur ve beklenir; SIGKILL sonrası çocuk
  çalışıyorsa kurtarma ortak kilitle engellenir.
- `--check`, `--recover` ve `--force` ayrı işletici seçimleridir. Sağlıklı
  seçeneksiz tekrar indirme yapmaz. Eski/başarısız ortamlar otomatik silinmez.
- Kaynak hazırlık ve bileşen kataloğu yalnız metadata okur. Bekleyen
  işlem/meşgul kilit hazır sayılmaz; açık `--check` araç çalıştıran ayrı
  doğrulamadır. Canlı kaynak erişimi bundan ayrı kalır.

## Doğrulama ve sınır

İzole sahte Git/uv testleri başarısız kurulum, sinyal, yarım işlem,
kimlik/path reddi ve tekrar davranışını sınar. Gerçek alt süreç testleri
paylaşımlı/özel kilit ile üst süreç öldükten sonra kilidin tutulmasını
doğrular. Ubuntu kabul işi gerçek sabit aracı kurup yerel kullanım ve
tekrarı ayrıca sınar; çalıştırılmamış iş başarılı kabul sayılmaz.
Kesin çalıştırma sonuçları [STATUS](../STATUS.md) içinde tutulur.

Şema, mevcut kanıtlar, araç sürümleri ve P0 arşiv kapsamı değişmez.
Bu değişiklik tüm bağımlılık bütünlüğü, güç kaybı/disk arızası, 7/24 hizmet
veya .NET/PostgreSQL kabulü değildir. [İşletici rehberi](../HARVESTER_INSTALLATION.md).
