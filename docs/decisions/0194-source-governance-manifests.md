# ADR0194 — Kaynak manifesti kontrol düzlemi

**Durum:** Kabul edildi
**Tarih:** 23 Kasım 2026
**Sürüm:** 0.189.0

**0.189.1 eki:** Çıplak `sources` eski bağımsız terminal kataloğunu sunmaz;
`sources catalog` ile aynı `SourceGovernanceService` yolunun kısayoludur.
Kayıtlı sağlık `sources status`, tekil pasif tarama denemesi `jobs` altında
kalır. Böylece geriye dönük komut adı korunurken iki katalog sözleşmesi
sürdürülmez. Benzer adlı izleme özellikleri veri anlamı bakımından
birleştirilmez; yalnız kopyalanmış foreground saat/bütçe koruması ortak
uygulama yardımcısına taşınır.

## Bağlam

XTI kaynakları farklı özelliklerde büyüdü: bazıları kamu snapshot'ı, bazıları
hesaplı arama, bazıları yerel araç, bazıları da yalnız açık yetkiyle hedefe
temas eden kontroldür. Eski kaynak kataloğu amaç, komut ve kısa sınırları
gösteriyordu; erişim, maliyet, dil/bölge, veri hakkı, kota/tekrar, ortak kayıt
türü ve provenance alanlarını zorunlu tek sözleşmede birleştirmiyordu.

Bu eksiklik yeni connector eklerken koşulların unutulmasına ve teknik olarak
hazır bir kaynağın canlı/ticari olarak da hazır sanılmasına yol açabilirdi.

## Karar

Her kaynak için değişmez `SourceManifest` kullanılır. Manifest:

- katı enum ve metin sınırlarıyla doğrulanır;
- benzersiz kimlik ve manifest sürümü taşır;
- erişim, credential, maliyet ve hedef temasını ayırır;
- dil/bölge ile normalleştirilmiş kayıt türlerini açıklar;
- `source_id`, `source_reference`, `observed_at`, `recorded_at`,
  `connector_version` ve `evidence_sha256` alanlarını zorunlu tutar;
- kota, retry ve kaynak hatasında kanıt koruma politikasını açıklar;
- ticari kullanım, saklama, müşteri gösterimi ve yeniden dağıtımı ayrı
  kararlar olarak kaydeder;
- canlı erişimden ayrı, isteğe bağlı kayıtlı sağlık kanıtına bağlanır;
- ön koşulları ve sonucun neyi kanıtlamadığını kullanıcıya gösterir.

Katalog kimliğe göre sıralanır ve kanonik JSON SHA-256 özeti üretir. Terminal,
yerel engine ve firma platformu aynı uygulama servisini kullanır. Engine
okumaları ağ ve alt süreç başlatmaz.

## Seçilmeyen yollar

- **Her kaynağı tek generic HTTP connector ile çalıştırmak:** Kaynakların
  kimlik doğrulama, sayfalama, kısmi cevap ve kanıt kuralları farklıdır;
  mevcut güvenli adaptör sınırlarını zayıflatır.
- **Manifesti veritabanına yazıp kullanıcıya değiştirtmek:** Connector ve
  veri hakkı sözleşmesinin kod sürümünden kopmasına, firma alanları arasında
  farklı anlamlara ve denetlenmeyen ağ davranışına yol açar.
- **`active` durumunu canlı sağlık saymak:** Yapılandırma ile anlık sağlayıcı
  erişimini karıştırır. Sağlık yalnız açık `include_health` ile kayıtlı
  geçmişten eklenir.
- **Araç lisansını veri kullanım izni saymak:** Yazılım lisansı sağlayıcı
  verisinin saklama/gösterim/yeniden dağıtım hakkını belirlemez.

## Sonuçlar

- Yeni bir kaynak, önce manifest doğrulamasından geçmeden katalogda yer alamaz.
- Koşullu/kapalı kaynaklar aktif özelliklerle karıştırılmaz.
- UI ve .NET tüketicisi kaynak koşullarını Python mantığını yeniden yazmadan
  sürümlü JSON ile okuyabilir.
- Manifest değişikliği katalog/hash değişimidir ve kaynak kabulünde
  incelenebilir.
- Mevcut veri tabloları ve kaynak-özel adaptörler korunur; P09 veri migrasyonu
  yapmaz.
- Yeni connector yine kendi toplama, kalıcı kanıt, insan inceleme, kurtarma,
  kapasite ve canlı kaynak kabulünü tamamlamak zorundadır.
