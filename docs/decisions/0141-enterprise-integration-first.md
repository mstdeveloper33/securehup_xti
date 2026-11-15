# 0141 — Kurumsal hedef ve entegrasyon önceliği

**Tarih:** 15 Kasım 2026 · **Durum:** Hedef mimari kabul edildi; uygulama bekliyor.
**Mevcut sürüm:** 0.138.0 / şema 64; bu karar sürümü veya şemayı değiştirmez.

**Aynı gün netleştirme:** Kullanıcı tek ana ürün/geliştirme deposu ve kayıt
merkezi olarak XTI'yı istiyor. OpenCTI/IntelOwl ayrı kullanıcı hedefleri
veya zorunlu ürün çekirdekleri değildir. Aşağıdaki karar bu netleştirmeyi
içerir; ilk plandaki bağımsız platform görev paylaşımını daraltır.

## Bağlam

Kullanıcı gelecekte kurumsal/profesyonel ürün istediğini ve OpenCTI,
IntelOwl gibi platformların yeteneklerinden entegrasyonlarla yararlanmayı
açıkça belirtti. Önceki kişisel kullanım odağı başlangıç profili olarak
korunur; nihai hedef değildir. [Teslim planı](../roadmap/ENTERPRISE_INTEGRATION_PLAN.md)
bu kararın sırasını, kaynaklarını ve kabul koşullarını içerir.

## Karar

- XTI izleme, kanıt, CTI ilişkisi/raporu, analiz sonucu, insan kararı ve
  vaka kaydının sahibidir. Bütün kullanıcı işleri XTI'dan tamamlanır.
  Uygun bağımsız açık kaynak kütüphane/araçlar öncelikle değerlendirilir;
  OpenCTI/IntelOwl ancak ek yararı doğrulanırsa değiştirilebilir arka plan
  sağlayıcısı olarak kullanılır. Kaynağın kökeni her zaman korunur.
- Hazır platform çekirdeği ana repoya kopyalanmaz. Desteklenen API ve
  uygun istemci sürümü küçük adaptörlerin arkasında kullanılır. Dış servis
  veritabanına doğrudan erişim veya SDK'ya bağımlı domain modeli kurulmaz.
- Okuma, analiz başlatma ve paylaşım ayrı sözleşmelerdir. İlk teslim dar
  veri yönleriyle yapılır; bütün alanlar çift yönlü eşitlenmez. Uzak kimlik,
  asıl kaynak, aracı servis, sürüm, zaman ve kapsam birlikte korunur.
- Yerel işlem ve uzak yazma tek transaction değildir. Kalıcı yürütme ve
  teslim kaydı, tekrar güvenliği ve belirsiz sonuç uzlaştırması gerekir.
  Uzak kaynak hatası eski kanıtı silmez veya temiz sonuç sayılmaz.
- OpenCTI çıkarımları ve IntelOwl çıktıları dış kanıttır; yerel tarihî
  kanıtı veya insan kararını değiştirmez. Aynı kaynağın farklı yollardan
  gelmesi bağımsız teyit gibi sayılmaz. Uzak silme yerel geçmişi silmez.
- Yerel ücretsiz kurulum korunur. Bileşen sürüm, yapılandırma ve kurulum
  tanımları bu projeden yönetilir. Kullanıcıdan başka proje geliştirmesi
  beklenmez. Servisli deneme ancak seçimden sonra yapılır; standart
  kurulum bütün platformları yüklemez.
- Kaynak/analizci, dışa aktarıcı ve veri paylaşımı açık seçilir. Boş
  eklenti listelerinin güvenli varsayılan olduğu kabul edilmez. Platformun
  kurulması aktif hedef kontrolü veya dosya gönderimi yetkisi oluşturmaz.
- Mevcut kuruluş gruplaması müşteri güvenlik sınırı değildir. API/React,
  kimlik/rol ve denetim; ardından müşteri ayrımı aşamalı geliştirilir.
  Dış servisler dahil erişim ve veri yalıtımı doğrulanır. OpenCTI CE/EE
  ayrımı ve IntelOwl/istemci lisansları dağıtım kararında kayıt altındadır.
- Veri altyapısı hedef iş yüküyle seçilir. Sırf kurumsal hedef kondu diye
  Kafka/OpenSearch veya bütün verinin PostgreSQL'e taşınması başlatılmaz.
- Önceden onaylanan olay adayları ve kaydedilmiş genel aramalar yeni
  entegrasyon sınırlarıyla tamamlanır. Genel CTI grafik/analiz motorları
  için hazır bileşenler değerlendirilir; XTI araştırma/veri modeli dış
  ürüne devredilmez. Haber toplama ayrı teslimdir.
- Otomatik HTML arşivi, envanter/ürün/sürüm/paket/CVE genişlemesi ve saldırı
  işleri yeniden kapsama alınmaz. İsteğe bağlı LLM'nin önceki sınırları kalır.

## Sonuçlar ve kabul

Kurumsal ilerleme, dış ürünün kurulması veya test sayısıyla ilan edilmez.
Her yetenek için gerçek uçtan uca kullanım, veri kapsamı, hata/yeniden
başlatma, erişim, sürüm uyumluluğu ve kurtarma kanıtı gerekir. Lisans,
kota, donanım ve bakım maliyeti kaynak/servis başına görünürdür. Sahiplik
ve durum sözleşmeleri belgelenmeden yeni bir genel altyapı yazılmaz.
Kullanıcı işi için ayrı ürün paneli gerektiren, sonucu ortak XTI modeline
alamayan veya geçmişi yalnız uzak serviste tutan bağlantı kabul edilmez.
Yardımcı bileşen kaldırıldığında mevcut XTI kanıt ve kararları korunur;
yeni analiz üretme yeteneğindeki eksiklik açıkça gösterilir.

Bu değişiklik yalnız plan/karar belgeleridir. Henüz servis bağlantısı,
paket kurulumu, ağda hedef analizi veya kullanıcı verisi aktarımı yoktur.
