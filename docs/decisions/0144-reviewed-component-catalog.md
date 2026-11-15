# 0144 — Ortak araç kimliği ve yerel bileşen kataloğu

**Tarih:** 15 Kasım 2026 · **Teslim:** 0.140.0 / şema 64.

## Bağlam

[Motor planındaki](../roadmap/ENGINE_INTEGRATION_ROADMAP.md) ENG-02, uygun
açık kaynak araçlarını küçük adaptörlerle kullanmayı sürdürür. Mevcut
Maigret, Sherlock ve theHarvester sürüm/commit bilgileri adaptör, kurulum
denetimi ve paketleme noktalarında tekrarlanıyordu. Yeni bir güncellemede
bu noktaların ayrışması, araç kimliğini ve geçmiş sonuçların anlamını
belirsizleştirebilir. Kaynak çalışma durumu da yerel araç kurulumundan
ayrı okunmalıdır.

## Karar

- `domain.component_pins` mevcut üç aracın incelenmiş sürüm/commit,
  katalog, lisans, çalışma ortamı ve kurulum komutlarını ortak kayıtta
  tutar. Adaptörler ve kurulum doğrulayıcıları bu kimliği kullanır;
  tarihî kaynak ve bağlantı profili kimlikleri değiştirilmez.
- Paketleme, bağımsız installer ve ayrı Sherlock işçisinde gereken
  sabitler korunur. Bu dosyaların ortak kayıtla uyumu test edilir;
  henüz otomatik üretilen tek bir bağımlılık kilidi yoktur.
- `ComponentCatalogService`, küçük `ComponentInstallationInspector`
  portuyla beklenen kimliği yerel gözlemden ayırır. Somut adaptör mevcut
  proje kurulum denetimini yeniden kullanır; giriş noktası bağımlılıkları
  bağlar. Domain ve uygulama dosya/terminal/HTTP'ye bağımlı olmaz.
- `components` ve engine v1 `components.list` aynı kataloğu okur.
  `components.list` yalnız boş parametre nesnesini kabul eder; yeni alan,
  işlem ve komut yolu istekle seçilemez. Eski engine işlemleri korunur.
- Kurulum denetimi ağ, süreç, üçüncü taraf modül yükleme veya kanıt
  veritabanı gerektirmez. Sonuç `metadata_only`, `execution_tested=false`
  ve `project-managed` kapsamını açıkça taşır. `ready` çalışma testi veya
  canlı kaynak erişimi anlamına gelmez.
- Sosyal seçimler mevcut uygulama profillerinden alınır; diğer kapsam ve
  sınırların gerçek yürütmeyle uyumu test edilir. Tanımsız bileşene başka
  aracın yapılandırması uygulanmaz.
- Katalog tüm kaynakları veya geçişli bağımlılıkları kapsamaz. Kaynakların
  son deneme/başarı/güncellik bilgisi ayrı `sources.status` işleminde kalır.
  Yeni katalog tablosu veya kullanıcı verisi değişikliği gerekmez.

## Kabul ve sınırlar

Kabul; CLI ve engine çıktılarının uyumunu, eski işlemlerin çalışmasını,
kurulum yokken kayıtlı kanıtın okunmasını, veri dizini yaratılmamasını,
kurulum/araç/ağ başlatılmamasını ve güvenilmeyen metnin terminalde
kaçırılmasını kapsar. Paketleme/kurulum/işçi pinlerinin kayması ile gerçek
platform/timeout/sonuç sınırlarının katalogdan ayrılması test edilir.
Bozuk `direct_url.json` içindeki nesne dışı JSON değerleri kontrollü
doğrulama hatasına dönüştürülür.

Sosyal denetim proje `.venv` ortamına aittir; alternatif `PATH` veya
`XTI_PYTHON` çalıştırıcısının uygunluğunu kanıtlamaz. theHarvester HEAD ve
çalıştırıcı denetimi tam kaynak ağacı/geçişli bağımlılık bütünlüğü değildir.
Bütün araçları kapsayan atomik kurulum kesiti yoktur. Kurulum kilitleme,
geri dönüş ve bağımlılık doğrulamasının ileri işleri ENG-06'da açıktır.

Yeni bağımlılık, araç yükseltmesi veya şema geçişi eklenmez. Bu katalog
.NET bağlantısı, müşteri yalıtımı veya genel amaçlı plugin platformu
değildir. [Kullanım rehberi](../COMPONENTS.md) alanları ve sınırları açıklar.
