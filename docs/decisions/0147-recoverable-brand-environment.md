# 0147 — Marka ortamı ve XTI başlatıcısının birlikte korunması

Tarih: 15 Kasım 2026. Durum: 0.140.3, STB-02 kurulum/kurtarma dilimi.

## Sorun

Önceki marka kurucusu PID ve işaret dosyasına göre ortam/yedek siliyor;
yaşayan pip alt sürecini veya çalışan XTI komutunu ortak kilitle
korumuyordu. `.venv` hem sosyal araçların hem XTI çekirdeğinin ortamı
olabildiği için yalnız sosyal sorguya kilit eklemek yeterli değildi.

## Karar

- theHarvester'da sınanan dizin kimliği/günlük ve süreç sonlandırma
  yordamları ortak adaptör modüllerine ayrılır. Kurulumlar aynı kurtarma
  mantığını kullanır; domain/application katmanı bu işlemleri bilmez.
- Marka ortamı `.venv` yolunda oluşturulur. Önceki ve başarısız ortamlar
  UUID'li ayrı klasörlerde korunur. Günlük bilinen rename sınırlarını ve
  kısmi geri dönüşü tanır; belirsiz eski yapıların sahipliği tahmin edilmez.
- `.brand-install.lock` kalıcı inode üzerinde POSIX kilididir. Kurucu
  özel, XTI başlatıcısı ve sosyal adaptörler paylaşımlı kilit tutar.
  Çocuk süreçlere descriptor açık aktarılır; kilit dosyası silinmez.
- Kurucu ve başlatıcının ilk bölümü yönetilen ortam dışındaki temel
  Python'da çalışır. Başlatıcı `.venv` seçmeden önce kilidi alır ve hedef
  Python'a devreder. Böylece kullandığı ortam kendi altından taşınmaz.
- Yarım kurulum varsa varsayılan çekirdek başlatma temel Python'a döner;
  sosyal adaptörler günlüğü görüp durur. Aktif özel kilit başlatıcıda
  kontrollü hata üretir. Bu hata engine isteği işlenmeden önce olabilir;
  taşıma/başlatma hatası, engine veri cevabından ayrıdır.
- Doğrulayıcı, kurucunun verdiği descriptor'ı beklenen kilit dosyasıyla
  doğrular; alt araca taşır. Ayrı `verify-brand` korumalı `--check` yoludur.
  Metadata katalogları araç çalıştırmaz ve kendi kilit dosyası oluşturmaz.

## Kabul ve sınırlar

Sahte pip/Git ve gerçek sınırlı alt süreç testleri; kurulum hatası,
kesinti, önceki dosyaların korunması, kilit ömrü, başlatıcı seçimi,
legacy dosya reddi ve günlüğün kurtarma sınırlarını denetler. Ubuntu işi
gerçek kurulum ve tekrarını geçici veriyle ayrıca sınar. Tanımlı CI işi,
görülmemiş bir çalıştırmanın başarılı sayılması için yeterli değildir.
Kesin sonuçlar [STATUS](../STATUS.md) içinde kaydedilir.

Koruma desteklenen proje başlatıcısı ve adaptörler içindir; doğrudan elle
çalıştırılan harici süreçler üzerinde mutlak denetim iddiası değildir.
Geçişli bağımlılıkların tam içerik bütünlüğü, ağ dosya sistemi, disk arızası,
kalıcı Linux hizmeti ve .NET/PostgreSQL kabulü ayrı kalır. Şema 64, araç
pinleri, sosyal profiller ve mevcut kanıtlar korunur.

[İşletici rehberi](../BRAND_INSTALLATION.md).
