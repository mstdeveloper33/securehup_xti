# 0143 — Sürümlü salt okunur engine sözleşmesi

**Tarih:** 15 Kasım 2026 · **Teslim:** 0.139.0 / şema 64.

## Bağlam

[0142 kararı](0142-xti-engine-dotnet-host.md), XTI'yı mevcut .NET platformuna
bağlanacak veri toplama ve analiz motoru olarak sınırlar. Mevcut CLI JSON
çıktılarında ortak dış sözleşme sürümü yoktur; başarı ve hata farklı
akışlarda bulunabilir. İç model veya terminal metnine bağlanan bir istemci,
uygulama değiştiğinde yanlış anlamlı sonuç okuyabilir.

İlk ihtiyaç saklanan veride arama, kayıt ayrıntısı ve kaynak durumudur.
Bu işlemler için yeni sunucu, kimlik altyapısı veya veritabanı geçişi gerekmez.

## Karar

- `engine` girişi tek stdin JSON isteği alır. `search`, `record.get` ve
  `sources.status` işlemleri salt okunurdur; ağ, araç veya worker başlatmaz.
  Mevcut toplama ve terminal komutları çalışmaya devam eder.
- Sözleşme sürümü `1`, engine uygulama sürümünden ve şema sürümünden
  ayrıdır. İstek kimliği yalnız cevap eşleştirmesidir; iş kimliği veya
  kalıcı tekrar güvenliği değildir.
- Başlatıcı sabit çalıştırıcı/argümanlarla güvenilen yerel veri alanını
  seçer. İstekten dosya yolu, komut, kullanıcı veya tenant yetkisi alınmaz.
  Mevcut kuruluş grupları güvenlik yalıtımı değildir.
- İstek ortak alanları ve işlem seçenekleri açık listeyle doğrulanır.
  Tek UTF-8 JSON, boyut/derinlik sınırı, yinelenen anahtar ve sonlu sayı
  denetimi depoya erişmeden uygulanır.
- Geçerli CLI çağrısındaki başarı ve işlem hataları aynı sürümlü cevap
  zarfında stdout'a bir kez yazılır. CLI yardım/kullanım hataları eski
  terminal davranışını korur. Eski `--json` çıktıları değiştirilmez.
- `complete`, okumanın tamamlanmasıdır. Kaynak hatası, eski veri, boş
  eşleşme ve hiç çalışmamış kaynak kendi alanlarıyla korunur. Kaynak
  kesintisi tehdit yokluğu veya başarılı yeni toplama sayılmaz.
- Dış alanlar açık projeksiyonla seçilir. İç dataclass'a eklenen alan
  sözleşmeye kendiliğinden girmez. Bilinçli ek alanlar geriye uyumlu olabilir;
  kaldırma, tip veya anlam değişikliği yeni sözleşme sürümü gerektirir.
- Kayıt referansı `kind + record_type + namespace + record_id` birleşimidir.
  Ransomware kaynakları aynı kimliği taşıyabilir; CTI `source` gösterimi
  birden çok adı birleştirebilir. Bunlar tek `record_id` veya gösterimden
  türetilen kaynak kimliğinin yetersiz olduğu karşı örneklerdir.
- Kayıt ayrıntısı mevcut denetimli kanıt okuyucularıyla kendi salt okunur
  kesitinde çözülür. Arama navigation metni çalıştırılmaz. Yapılandırılmış
  ana kayıt, kaynak kanıtı ve sayfalı geçmiş bölümleri ayrı sunulur.
- Arama tek istek içinde tutarlıdır; ayrı sayfalar veya sonraki ayrıntı
  isteği önceki kesiti dondurmaz. Kaynak durumu mevcut bağımsız feed
  okumalarını kullanır; bütün kaynaklar için atomik kesit iddiası yoktur.
- Sosyal çalışma öğesi kendi tarihî çalışmasına bağlıdır. Çıkarılmış
  kaynak kimlikleri son bilinen içerik ve çıkarılma geçmişiyle okunur.
  Kayıt güncelliği veya insan kararı türetilip değiştirilmez.

## Sorumluluklar

Domain katmanı sözleşme isteğini ve kayıt referansını doğrular. Uygulama
servisi mevcut arama/kaynak durumu servislerini ve küçük kayıt ayrıntısı
portunu kullanır. SQLite adaptörü mevcut kaynak/geçmiş doğrulamasını
yeniden kullanır. Giriş noktası bağımlılıkları bağlar, JSON taşımasını ve
işlem hatalarını yönetir. Domain ve uygulama katmanı CLI veya HTTP'ye
bağımlı olmaz.

## Kabul ve sınırlar

Kabul testleri gerçek geçici SQLite verisiyle arama–referans–ayrıntı
zincirini; kaynak hatasında önceki kanıtı; çıkarılmış/tarihî kaydı;
sayfalama toplamını; bozuk geçmişin reddini; geçersiz girdide depoya
ulaşılmamasını; ağ/araç/yazma olmamasını ve eski CLI uyumunu sınar.

Şema 64 ve kullanıcı verisi korunur; yeni bağımlılık gerekmez. Bu karar
gerçek .NET tüketicisini, servis kimliğini, müşteri yalıtımını, uzak HTTP
taşımasını veya kalıcı iş başlatmayı tamamlanmış saymaz. Bunlar
[motor planındaki](../roadmap/ENGINE_INTEGRATION_ROADMAP.md) ayrı kabul
işleridir. Kullanım ve hata sözleşmesi [engine rehberindedir](../ENGINE_CONTRACT.md).
