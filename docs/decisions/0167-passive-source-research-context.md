# 0167 — Pasif keşif çalışma durumu, aday kanıtından ayrı bağlam

18 Kasım 2026 · 0.162.0 · kabul edildi.

Araştırma adayın geçmişini gösterirken son kaynak kesintisi görünmüyordu.
Boş/başarısız yeni sorgu eski adayın doğruluğunu veya zamanını değiştiremez.
Bu nedenle kayıtlı kök domain düğümüne ayrı `discovery` alanı eklenir.

`StoredDiscoveryStatuses` araştırmanın mevcut SQLite okuma transaction'ında
`crt.sh` ve `theharvester` için son çalışma ve son **complete** çalışmayı
okur. Saat gerilemesinde sıra `sequence` ile belirlenir. Var olan decoder
ve kök/kaynak kimliği kontrolü kullanılır. Her kökte en fazla dört farklı
çalışma materyalize edilir; bütün seçili metinler decoder öncesi ölçülür,
istekte ortak 4 MiB sınırı vardır. Sınır aşıldığında `read_limited` ve
`discovery_status_read_budget` gösterilir; `never` veya boş sayılmaz.
SQL geçmiş araması mevcut varlık/sıra indeksini kullanır; bu bir çalışma
süresi garantisi veya tam geçmiş bütünlük denetimi değildir.

Kayıtlı kökün sorgulanmamış sağlayıcısı `never` olur; zaman/çalışma kimliği
uydurulmaz. Kayıtsız alt alan için kökün kaynak durumu miras alınmaz.
Sonuçlar `complete_found`, `complete_empty`, `partial_found`, `partial_empty`,
`failed` olarak ayrılır. Her sağlayıcı ve önceki complete yanıt kendi
kimliği/tarihiyle kalır. Bu alan sağlayıcının şu an erişilebilir olduğunu
söylemez; yalnız saklanmış denemeyi açıklar.

Özgün çalışma kimliği olan `surface_discovery_run/source_context` kanıtı
domain düğümünde yer alır. Zaman temeli `response_received_at`; hash kayıtlı
çalışma alanlarının özetidir, sağlayıcı payload'ının hash'i veya bağımsız
imza değildir. Aday kaynak satırının çalışmayla kesin bağı yoktur; bu yeni
kimlik adayın `source_run_id` alanına taşınmaz. Başarısız/boş çalışma
adayları, insan kararını ve aktif kontrol kapsamını değiştirmez.

52 kanıtlık düğüm sınırında son kontrol ve kaynak denemeleri IOC iddialarından
önce korunur; atlanan kanıtların gerçek toplamı görünür. Öncelik v5, başarısız
ve kısmi denemeyi doğrulama gerekçesi yapar. Sorgulanmamış isteğe bağlı
sağlayıcı ve tamamlanmış boş yanıt bağlamdır; tehdit veya güvenli hükmü değildir.

Araştırma/değerlendirme modeli 3 olur; engine/platform zarfı 1 ve DB/iş
şemaları 75/2 korunur. Eski model 1 ve 2 özgün okunur. Yeni modelin ilk
incelemesi politika başlangıcıdır. Yeni deneme kanıt değişimi, yalnız
yaşlanma zaman değişimidir. Yeni alan ve çalışma/kanıt başvuruları frozen
okumada denetlenir. Eski motor yeni incelemeyi okuyamaz; kod geri dönüşü
yükseltme öncesi uygun yedekten yapılır. Yeni ağ/API/paket yoktur.
