# 0145 — Yeni özelliklerden önce mevcut motoru sağlamlaştırma

**Tarih:** 15 Kasım 2026 · **Mevcut uygulama:** 0.140.1 / şema 64.
**Durum:** Öncelik kararı; ilk CI/belge düzeltmeleri uygulandı, işletim ve
gelecekteki platform kabulleri açık.

## Bağlam

Kullanıcı yeni özelliklerden önce mevcut motorun kurulabilir, kararlı ve
kendi platformuna bağlanabilir hale gelmesini istedi. Gelecekteki .NET ve
PostgreSQL bilgisinin şimdi veritabanı geçişi başlatma talebi olmadığını
ayrıca açıkladı. Bugünkü deneme ve kişisel kullanım SQLite ile devam eder.

## Karar

- Yeni istihbarat modülleri bekler. Mevcut davranış, test, kurulum,
  güncelleme, kurtarma, veri güvenilirliği ve belgeler önceliklidir.
- İlk dilim, yeni engine/bileşen testlerini hızlı CI'a dahil eder;
  ortak araç pinleri ve başlatıcı değişikliklerini kurulum kontrolüne
  bağlar. Yanlış komut ve güncel kodla çelişen kapsam açıklamaları düzeltilir.
- Tam test paketi ile her gönderimdeki hızlı paket ayrı kalır; hangi
  kontrolün nerede çalıştığı ve hangi ortam testinin atlandığı açık yazılır.
- Sonraki kabul temiz Linux kurulum, güncelleme ve geri dönüşüdür. Veri
  ve iş kurtarması, sır yönetimi ve ölçülmüş işletim bunu izler. Yalnız
  test sayısından üretim hazırlık yüzdesi veya hizmet seviyesi çıkarılmaz.
- [0142](0142-xti-engine-dotnet-host.md) sorumluluk ayrımı korunur: Python
  motoru kaynaklı kanıt/analiz/iş geçmişini, .NET platformu kullanıcı,
  oturum, rol ve ürün deneyimini yönetir. İletişim sürümlü sözleşmeyledir.
- PostgreSQL gelecekteki platform bilgisidir. Bugün motorun SQLite verisi
  taşınmaz ve yeni veritabanı bağımlılığı eklenmez. Fiziksel yerleşim,
  motorun taşıma kapsamı ve sürücü gerçek platform incelendiğinde seçilir.
- Gerekli bir veri geçişinde kimlik/kanıt/karar geçmişi, olay sırası,
  atomik kaynak/bildirim/iş kayıtları, eşzamanlı çalışma ve geri dönüş
  doğrulanır. Ortak veritabanı sunucusu iki tarafın birbirinin tablolarını
  düzenleme yetkisi sağlamaz. .NET'teki kimlik yönetimi motor kapsam
  denetiminin yerine geçmez.

## Kabul ve kapsam

Güncel STB-01–06 sırası [motor yol haritasında](../roadmap/ENGINE_INTEGRATION_ROADMAP.md)
tek yerde tutulur. ENG iş kimlikleri korunur; eski numara sırası teslim
önceliği değildir. Yerel motor kabulü ile gerçek .NET/PostgreSQL dağıtım
kabulü ayrı kaydedilir; gelecekteki ortam SQLite sağlamlaştırmasının ön
koşulu yapılmaz.

0.140.1 yeni istihbarat kaynağı, DB şeması, .NET servisi veya PostgreSQL
kurulumu eklemez. Güncel doğrulama kanıtı [STATUS](../STATUS.md) içindedir.
