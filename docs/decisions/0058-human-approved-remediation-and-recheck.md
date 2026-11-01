# 0058 — İnsan onaylı düzeltme ve yeniden kontrol geçmişi

## Durum

Kabul edildi — 30 Ekim 2026.

## Bağlam

Maruziyet kaydı bir yeniden kontrol tarihi ve son insan kararı taşıyordu; fakat hangi
düzeltmenin planlandığı, ne zaman uygulandığı ve uygulama sonrası ne gözlendiği ayrı,
yapılandırılmış bir geçmişte bulunmuyordu. Bir kontrolün başarılı görünmesi de tek
başına maruziyetin kapatılması için yeterli değildir.

## Karar

- Düzeltme planı maruziyete bağlı ayrı bir kayıttır. Öneri; etkin kesin paket/VEX
  kanıtına, etkin genel maruziyet kanıtına veya açık analist notuna dayanır.
- Durumlar `planned`, `implemented`, `cancelled`; yeniden kontrol sonuçları `not_run`,
  `not_observed`, `still_present`, `inconclusive` olarak ayrı tutulur.
- Planlama, uygulama, iptal ve her yeniden kontrol eklemeli olay geçmişinde kalır. Olay;
  gerekçeyi, kanıt başvurusunu, o andaki insan kararını ve güncel NVD/ürün kanıt
  özetlerini birlikte saklar.
- Uygulama kaydı bir sonraki kontrol tarihini zorunlu kılar. `still_present` ve
  `inconclusive` sonucu da yeni kontrol tarihi olmadan kabul edilmez. `not_observed`
  sonucu takip tarihini kaldırabilir.
- Hiçbir düzeltme veya kontrol olayı maruziyetin `investigating/affected/not_affected/fixed`
  insan kararını değiştirmez. Kapatma veya yeniden açma ayrı `exposure-review` komutudur.
- Kapanmış maruziyette yeni plan veya uygulama kaydı açılmaz. Gerekirse maruziyet
  önce açık insan kararıyla yeniden incelemeye alınır.
- Liste en fazla 10.000 planı doğrular, 500 kayıt gösterir; ayrıntı en fazla 10.000
  olayı doğrular, 100 olay gösterir. Bozuk seçili kayıt kısmi güvenilir sonuç vermez.
- Şema 24→25 geçişi üzerine yazılmayan doğrulanmış yedekten sonra iki tabloyu
  boş ve işlem bütünlüğü içinde oluşturur. Eski kararlardan düzeltme uydurulmaz.

## Sonuçlar

Platform artık düzeltme niyeti, uygulama kanıtı ve sonrasındaki gözlemi birbirinden
ayırarak izleyebilir. Bu dilim otomatik paket kurmaz, hedef taramaz, üretici kaynağına
bağlanmaz veya maruziyeti otomatik kapatmaz. Laboratuvar öncesi/sonrası kanıt seti,
süreli bastırma politikası ve kapanma/yeniden açılma kabul senaryoları VUL-04 içinde
açık kalır.
