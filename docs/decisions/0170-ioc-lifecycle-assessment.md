# 0170 — Kaynak zamanını koruyan IOC yaşam döngüsü değerlendirmesi

18 Kasım 2026 · 0.165.0 uygulandı. İlk uygulamanın tam regresyonu geçti
(3.065 başarılı, dört Linux ortam atlaması); son makbuz kontrolü 110
hedefli testle ayrıca doğrulandı. [Kabul kapsamı](../ACCEPTANCE_REVIEW.md).

Mevcut IOC iddiaları güven, geçerlilik, ilk/son gözlem ve eklemeli geçmiş
taşır. Bunlar yeniden oluşturulmaz. Yeni salt okunur değerlendirme kaynak
iddiasının etkinliğini, kanıt yaşını ve kaynağın son toplama sonucunu ayrı
eksenlerde gösterir. Listeyi tekrar indirmek yeni saldırı gözlemi değildir.

- Domain katmanı sürümlü, açıklanabilir yerel inceleme politikasını uygular.
  Varsayılan güncellik aralıkları ağ göstergelerinde 7/30, hashlerde 30/180
  gündür; güncel/yakın geçmiş/eski ayrımıdır, zararlılık olasılığı değildir.
  İstek bu iki eşiği ve kaynak yenileme eşiğini açıkça değiştirebilir.
- Feodo zamanı sağlayıcının bildirdiği gözlemdir; gün hassasiyeti ve IP
  üzerinde toplulaştırma sınırı açıklanır. CERT Polska zamanı kaydın alındığı
  listenin sürüm tarihidir. Eski elle kayıtların `observed_at` alanı olay zamanı
  mı varsayılan kayıt zamanı mı ayırt edilemez; bu belirsizlik korunur.
- Tek IOC'nin tüm sınırlı iddia/olay geçmişi tek SQLite read transaction
  içinde doğrulanır. Kaynak makbuzları, son deneme ve son başarılı toplama
  aynı kesitte okunur. Okuma sınırı aşılınca eksik veri tam sonuç olmaz.
- Kaynak kesintisi, kaynağın listeden kaldırması, yerel insan geri çekmesi
  ve zaman aşımı ayrı gerekçelerdir. Kaynak sayısı bağımsız doğrulama sayısı
  değildir. İnsan kararları ve geçmiş hiçbir değerlendirmeyle ezilmez.
- Terminal `ioc lifecycle` ve engine/platform `ioc.lifecycle` aynı servis,
  parametre doğrulaması ve JSON sonucunu kullanır. Firma alanını mevcut
  güvenilen platform başlatıcısı seçer; istek dosya yolu kabul etmez.
- Yeni tablo, migration, ağ isteği, ücretli kaynak veya bağımlılık gerekmez.
  Değerlendirme salt okunur ve yeniden hesaplanabilirdir. Mevcut araştırma
  öncelik v7/frozen model 3 değişmez; bu yeni değerlendirme ayrı politika
  sürümü taşır. Tam sighting günlüğü, ortamda saldırı tespiti, otomatik
  engelleme, STIX/TAXII ve LLM bu teslim değildir.

Kabul: aynı feed'in yeniden alınması gözlem yaşını yenilemez; yeni kaynak
gözlemi yeniler; başarısız toplama eski kanıtı korur; listeden kaldırma ve
elle geri çekme ayrılır; eşik/geçerlilik sınırları, kayıtlı saat belirsizliği,
bozuk geçmiş/makbuz, kapasite sınırı, terminal/JSON ve firma izolasyonu
test edilir. Geliştirme sırasında ilgili demet, teslimde bir tam paket
çalıştırılır; her dosya değişikliğinde tam paket tekrarlanmaz.
