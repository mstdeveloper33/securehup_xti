# 0142 — XTI motoru ve .NET uygulaması sorumlulukları

**Tarih:** 15 Kasım 2026 · **Durum:** Kullanıcı kararı; uygulama bekliyor.
**Mevcut sürüm:** 0.138.0 / şema 64.

## Bağlam

Kullanıcı uygulama backend'i ve oturum yönetiminin mevcut .NET platformuna
ait olacağını netleştirdi. Bu repo o ürüne entegre edilecek istihbarat
kaynağı/motoru olarak geliştirilecek. Dış servislere bağımlılık sınırlı
olmalı; uygun açık kaynak parçalar kullanılmaya devam edilmeli.

## Karar

- Python XTI toplama, normalleştirme, analiz, kaynaklı kanıt, CTI ilişkisi,
  izleme ve iş geçmişinin sahibidir. Yerel terminal çalışır durumda kalır.
- Uygulama backend'i, kullanıcı/giriş oturumu, rol ve web deneyimi mevcut
  .NET platformundadır. Bu repoda ikinci auth/backend/panel geliştirilmez.
- Motor ile platform sürümlü istek/sonuç ve kalıcı iş sözleşmesiyle bağlanır.
  .NET motorun veritabanı şemasına doğrudan bağımlı yapılmaz. Taşıma biçimi
  dağıtım ortamı görülünce seçilir; iş mantığına HTTP/gRPC/süreç ayrıntısı girmez.
- İlk kabul salt okunur arama, ayrıntı ve kaynak durumudur. Mevcut CLI JSON
  dış sözleşme sürümü veya genel istek tekrar güvenliği sağlamış sayılmaz.
  Uzun işler için kabul/kimlik/durum/sonuç ve iptal/kurtarma ayrı teslimdir.
- .NET kimlik/rol kararını verir; motor güvenilen çağıran ve izinli kapsam
  sınırını uygular. Serbest tenant etiketi veya dosya yolu yetki değildir.
  Mevcut kuruluş gruplaması müşteri izolasyonu olarak sunulmaz.
- Tek istihbarat kayıt merkezi ilkesi korunur. Dış araç sonucu, asıl
  kaynak ve zaman bilgisiyle motor modeline alınır; yardımcı değişince
  geçmiş kaybolmaz. .NET'in ürün kayıtları ayrı sorumluluktur; aynı durum
  iki yerde bağımsız değiştirilmez. Mevcut vaka ve karar kayıtları silinmez.
- Yerel açık kaynak kütüphane/araçlar tercih edilir. OpenCTI/IntelOwl veya
  ücretli hizmet temel çalışmanın zorunlu koşulu değildir. Yeni kaynak
  toplama internet gerektirir; kayıtlı veri analizi kaynak kesintisinde sürer.
- FastAPI/Pydantic, Keycloak ve Cytoscape.js için önceki backend/panel
  tercihleri bu repo için geri çekilir. İleride ince iç servis adaptörü
  gerekmesi ayrı teknoloji kararıdır; kullanıcı oturumu Python'a taşınmaz.

## Önceki kararlarla ilişki

[0141](0141-enterprise-integration-first.md)'in bağımsız bileşen, kaynaklı
kanıt, sürüm ve tekrar güvenliği ilkeleri korunur. Kullanıcı arayüzü,
oturum/backend ve bütün ürün kaydını bu repoya verme kısımları bu kararla
değişir. Güncel uygulama sırası [motor yol haritasıdır](../roadmap/ENGINE_INTEGRATION_ROADMAP.md).
Önceki kaldırılmış HTML arşivi ve CVE/ürün/envanter kapsamı açılmaz.

## Kabul

Sözleşme uyumu, tam/kısmi/hatalı sonuç, eski kayıtların korunması, gerçek
.NET tüketicisi, iş tekrarı/kesinti, kapsam ve Linux kurtarma kanıtları
gerekir. Bu belge yalnız karar/plan değişikliğidir; kurulum, yeni özellik,
servis çağrısı veya veri taşıması yapılmadı.
