# 0135 — Kuruluş kapsamındaki kanıtların tutarlı okunması

Durum: kabul edildi; 0.134.0. Tarih: 14 Kasım 2026.

Kullanıcı kişisel terminal ürünü içinde kuruluş raporu ve ücretsiz devam
işlerini istedi. Domain raporunu kuruluş adı aramasıyla genişletmek, karma
oturumlardaki ilgisiz kayıtları bir kuruluşa taşıyabilirdi. Yeni raporlar
yalnız mevcut açık kuruluş bağlantılarıyla kapsam belirler.

## Karar

- `OrganizationScope` ortak domain modelidir. SQLite okuma yardımcısı
  kullanıcının kuruluş/bağlantı yaşam döngüsünü aynı bağlantıda doğrular.
  Etkin kuruluş + etkin bağlantı + etkin hedef birlikte gerekir.
- `OrganizationReportService`, `OrganizationContributionService` ve
  `PeriodicChangesService` küçük okuma portları kullanır. Uygulama/domain
  katmanı SQLite, HTTP, terminal veya başka uygulama arayüzüne bağımlı olmaz.
- Kuruluş görünümü, dönem kapsamı ve bir kuruluş katkı sayfası kendi içinde
  tek salt okunur transaction'dır. Eski tazelik/katkı adaptörlerinden aynı
  bağlantıda okunabilen yardımcılar çıkarıldı; dış API'leri korundu.
- Bağımsız kaynak/izleme denemesi, son başarı, tanım özeti ve kaynak
  yenilemesi ayrılır. Başarısızlık eski başarıyı değiştirmez. İlk ölçüm yeni
  tehdit değildir. Görünüm sayfası gerçek toplamları değiştirmez.
- Vaka projeksiyonu yalnız ilgili tam kanıt bağı, vaka kimliği/durum ve
  gezinme verir. Bağın güncel satırı kendi snapshot ve yaşam döngüsüyle
  tutarlı olmalıdır; ilgisiz vaka içeriği rapora katılmaz.
- Dönem raporu güncel üyelikten tarihî sahiplik üretmez. Ortak toplama
  oturumlarında yalnız seçilen adımlar; ortak kaynak hataları açık ortak
  bağlam olarak görünür. Önce/sonra değerleri yalnız kayıtlı kanıttandır.
- `CtiContextService` tam kanonik IOC veya kayıtlı entity kimliğinden
  doğrudan ilişkileri okur. Kaynak iddiaları birleştirilmez. Her güncel durum
  olay geçmişiyle doğrulanır; dolaylı çıkarım ve otomatik atıf yoktur.
- HIBP kamu metadata kaynağı [0136 kararı](0136-public-breach-metadata.md)
  ile eklenir. Kuruluş/periodik görünüm aynı bağlantıdan denetlenen katalog
  geçmişini okur; tam kaynak domaini, kaynak bayrakları, atıf ve lisans korunur.

## Sonuç

Raporların ayrı kalıcı kopyası veya yeni framework gerekmez. Şema 60 yalnız
kamu katalog çalışmaları/farkları için iki tablo ekler; eski kanıtlardan
kuruluş üyeliği veya bildirim türetilmez. React/API ileride aynı servisleri
çağırabilir; bu teslim web/API katmanı veya tenant yetkilendirmesi değildir.

Sınır kontrolleri eksik sonucu tam toplam gibi sunmak yerine açık hata
verir. Kaynak koleksiyonu veya aktif kontrol yeni rapor komutlarında yoktur.
Ağsız kabul; kapsam, sayfalama, eşzamanlı snapshot, kesinti, bozuk geçmiş,
insan kararlarının korunması ve CLI gezinmesini sınar.
