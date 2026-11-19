# 0178 — Kaynaklı sosyal inceleme, düzenli takip ve vaka kanıtı

Tarih: 19 Kasım 2026. Sürüm: 0.173.0, çekirdek 83, kuyruk 3.

Birleşik sosyal keşif ve isteğe bağlı sağlayıcı kanıtı ayrı makbuzlardır.
İnsan kararı domain + tam profil adresine bağlı, sürümlü ve gerekçelidir.
Yeni keşif eski kararı veya kaynak sonucunu güncellemez; kararın hangi
keşfe dayandığı görünür kalır. Firma incelemesi aynı SQLite okuma kesitinde
ayrı sayfalanmış sosyal bölümü sunar.

`SocialTrackingService` küçük depo portuna ve mevcut keşif servisine
bağlıdır. Kimlik normalizasyonu, değişiklik karşılaştırması ve günlük replay'i
domain katmanında kalır. Terminal/JSON yalnız bileşim ve sunum yapar.
Yeni dış bağımlılık veya sağlayıcı yoktur.

Şema 83, işlem anahtarı ve kanıt bağı içeren eklemeli bir günlük ile
bildirim tablosu ekler. Günlük hash zinciri, silinmiş kuyruk sonu ve özgün
keşif özeti okuma sırasında doğrulanır. Başlangıç rezervasyonu ağdan önce,
fark ve ortak inbox teslimi aynı son transaction içinde kaydedilir.
Keşif commit'i ile teslim arasındaki kesinti özgün işlem anahtarıyla
toparlanır. Bitmemiş keşif tekrar ücret/istek üretmez; kesinti açık gösterilir.

Sosyal takip her turda önceki doğrulanabilir profil gözlemini kullanır.
Erişim hatası veya eksik kapsam yokluk sayılmaz. Başlık/açıklama/firma
bağlantısı anlamlı farktır; tüm HTML hash farkı değildir. İlk tur sessizdir.
Bildirim sahiplik veya taklit hükmü değildir. Düzenli takip ücretli kaynak
çağırmaz. Ücretli ek kanıtın düzenli yenilenmesi ayrı açık karar gerektirir.

Vaka `social_discovery` türü tek profilin, sağlayıcı kanıtının ve insan karar
geçmişinin seçildiği andaki kopyasını saklar. Kaynak aynı firma içindeki
transaction'da yeniden doğrulanır. Mevcut `case_evidence` CHECK genişlemesi
satır ve rowid'leri koruyan kopyayla açık/yedekli migration içindedir.

Foreground monitor her tur için kilit alır; beklerken kilit tutmaz.
Süre/tur/okuma/saklama sınırları açıktır. Zamanlama dış platformun veya
işleticinin sorumluluğudur; bu değişiklik dağıtık worker veya daemon kurmaz.
Mevcut kullanıcı adı izlemeleri, kaynak makbuzları, iş kuyruğu sözleşmeleri
ve eski dondurulmuş vakalar korunur.
