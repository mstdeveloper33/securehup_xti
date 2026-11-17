# 0159 — Kayıtlı kanıttan gerekçeli inceleme sırası

Tarih: 17 Kasım 2026. Durum: Uygulandı (0.155.0, şema 74).

## İhtiyaç

Araştırma yolları kaynağı ve zamanı gösteriyor, fakat kullanıcının önce
hangi kayda bakması gerektiğini tek sıralı görünümde açıklamıyordu.
Kaynak güven sayısını tehdidin doğruluğu veya risk skoru saymadan,
mevcut veriden gerekçeli inceleme sırası gerekiyor.

## Karar

- `research_priority` domain kuralları sürümlüdür. Kaynak/popülerlik oyları
  veya LLM yoktur. Öncelik, kanıt türü, kaynak güveni ve etkinlik ayrı kalır.
- `ResearchService.priorities` mevcut küçük okuma portunu ve tek SQLite
  kesitini kullanır. Yeni depo, ağ çağrısı, tablo veya analist kararı yazılmaz.
- Bütün sınırlı araştırma toplanır; düğüm ve ilişkiler sıralanıp **öğe**
  olarak sayfalanır. İlk yol sayfasını sıralamak bazı önemli kayıtları
  sonraki sayfada gizleyeceği için kullanılmaz. Mevcut `research.show`
  yol sayfası sözleşmesi korunur.
- `review_first / verify / context` sırası ordinaldir. Her gerekçe özgün
  kanıta başvurur; veri/liste yokluğu gibi durum gerekçeleri ayrıca açıklanır.
  Farklı kaynak etkinlikleri semantik çelişki veya çoğunluk kararı değildir.
- Eski DNS tekrarları yeni gözlem varken önceliği yükseltmez. Başarısız
  son sorgu geçmiş başarılı yanıtı güncel saymaz; her ikisi de korunur.
- Kesit kimliği kaynak kesiti, kural sürümü, güncellik eşiği ve değerlendirilen
  durumları içerir. Salt saat ilerlemesi eşik aşmadığında sırayı bozmaz;
  eşik aşılırsa sayfa devamı reddedilir. Kalıcı eski kesit deposu yoktur.
- CLI `--priorities` ve engine/platform `research.priorities` aynı alanları
  serileştirir. Firma seçimi güvenilen başlatıcıda kalır.

## Sonuç ve sınır

Yeni bağımlılık, ücretli kaynak ve şema değişikliği yoktur. Sıralama yalnız
seçili kökün mevcut sınırlı araştırmasıdır; firma geneli kuyruk veya tehdit
kararı değildir. Kaynak/kanıt/okuma sınırları ve kaynak koşulları devam eder.
Öncelik değişim geçmişi, bildirim ve daha geniş yaşam döngüsü otomasyonu
ayrı MTR-04 dilimleridir. Kurallar değiştirilirse politika sürümü de değişir.

Testler yaşam döngüsü, zaman sınıfı, kanıt kaynakları, sayfalama, eşzamanlı
değişim, yedek ve firma ayrımını doğrular; otomatik test canlı kaynak
denemesi yerine geçmez. [Sözleşme ve kurallar](../RESEARCH_PRIORITIES.md).
