# 0007 — Kalıcı kaynak beklemesi ve kontrollü yerel bakım

**Tarih:** 28 Ekim 2026 · **Durum:** 0.7.0'da uygulandı.

## İhtiyaç

Kaynak kota bilgisi yalnız süreç belleğinde tutulduğunda yeniden başlatma erken isteğe yol açabilir. Uzun süre kullanılan kişisel kurulumda bir bulguya bağlanmamış gözlemler de birikir. Beklemeyi sürdürmek, kayıt alanını ölçmek ve gerekli kanıtı koruyarak sınırlı temizlik yapmak gerekir.

## Bekleme modeli

`SourceCooldown` sağlayıcı, UTC `not_before`, UTC `recorded_at` ve neden kodunu taşır. `CooldownRepository` get/list/extend sözleşmesidir. SQLite adaptörü uzatmayı kısa `BEGIN IMMEDIATE` içinde yapar; eski veya yeni kayıttan daha geç biten süreyi korur. Eşit/kısa talep önceki kaydın nedenini ve zamanını değiştirmez. Tarih/saat dilimi, sağlayıcı, neden ve bitişin kayıt zamanından önce olmaması doğrulanır. Bozuk kayıt okunurken veya yazılırken işlem hata verir.

`SourceCooldownGate` crt.sh ve urlscan adaptörlerine enjekte edilir. Her gerçek HTTP denemesinden önce kayıt yeniden okunur; gerekiyorsa en fazla beş saniye beklenir ve yeniden kontrol edilir. Daha uzun beklemede `SourceError` oluşur ve o deneme istek göndermez. İstek açılmadan crt.sh için bir, urlscan için iki saniyelik asgari aralık kaydedilir. Ağ sırasında SQLite transaction'ı açık tutulmaz.

Retry-After ve urlscan kota başlıkları yanıtın gövdesinden ve tekrar beklemesinden önce kalıcı kayda geçer. HTTP 200 gövde hatası veya 403 yanıtı bekleme bilgisini silmez. Bozuk Retry-After, eksik süreli HTTP 429 veya tükenmiş kotanın okunamayan sıfırlama zamanı için ihtiyatlı 60 saniye varsayımı kullanılır; geçerli çok uzun süre kısaltılmaz. Takvim aralığını aşan süre UTC maksimum tarihe kaydedilir; aynı süreçte istenen sürenin monotonic alt sınırı korunur. Sonsuz sayıya dönüşmüş talepte bu alt sınır da sonsuzdur. Kayıt hatası SourceError'a veya boş sonuç gibi gösterilen başarıya çevrilmez; arama işi hata durumuna geçer.

Aynı süreçte daha önce görülen beklemenin monotonic alt sınırı korunur; saat ileri alınarak bu süre kısaltılmaz. Süreç yeniden başladıktan sonra UTC saatine güvenilir. Cihaz kapalıyken saat yanlış ileri alınmışsa kalan süre hatalı görünebilir; bu düzen saatten bağımsız dağıtık kota sayacı değildir. Aynı veritabanının yerel worker kilidi bütün üretim çağrılarını seri hale getirir. Başka kayıt klasörleri/cihazlar/programlar bu kotaya dahil değildir.

Bitmiş bekleme satırı salt okuma sırasında silinmez. Sonraki daha geç talep satırı günceller; bu tablo bütün eski beklemelerin günlüğü değildir. Kaynak görünümü kayıtlı son sonucu ve UTC saate göre kalan beklemeyi gösterir; anlık kaynak sağlığı ölçümü yapmaz. Önceki sürümün yalnız bellekte kalmış bekleme bilgisi migration ile üretilemez.

## Temizlik politikası

`MaintenanceService` kullanım, önizleme, açık uygulama ve geçmiş işlemlerini küçük kayıt sözleşmesiyle yürütür. Politika `unlinked-observations-v1`:

- Yalnız `finding_observations` bağlantısı olmayan gözlemler adaydır. Kapatılmış bulgular dahil tüm bağlı kanıtlar korunur.
- Yaş `ingested_at`, yani ilk yerel kayıt zamanıdır. Kaynak tarihi veya son tekrar görülme zamanı değildir. Tekrarlanan import bu alanı güncellemez.
- Varsayılan 90 gün, 7–3650 gün aralığı; kesim UTC gün başlangıcı eksi gün sayısıdır. Kesime eşit kayıt korunur.
- Saat dilimsiz, okunamayan veya gelecekteki tarihler korunur ve ayrı sayılır. Tarihler metinsel sıralamayla değil, saat dilimleriyle karşılaştırılır.
- En fazla 10000 gözlem seçilir; tüm uygun kayıtlar akış halinde sayılır ve kalan sayı gösterilir. Silinecek kimliklerin bellekteki listesi sınırlıdır.
- Varlık, bulgu, bağlantı, karar, hedef kontrolü, iş/deneme ve bekleme kayıtları silinmez.

Önizleme yalnız okur. Kimlik; politika, kanonik veritabanı yolu, kesim günü, gün/sayı seçenekleri ve bütün uygun gözlemlerin içeriğinden SHA-256 ile üretilir. Bir gizli anahtar veya kullanıcı yetkilendirmesi değildir; seçimin değişmediğini kontrol eder. Aynı kayıt alanı/UTC gününde değişmemiş seçim uygulanabilir. Yeni bağlantı, içerik değişimi, başka klasör veya gün değişimi yeniden önizleme gerektirir.

Uygulama önce yerel worker kilidini, ardından SQLite yazma kilidini alır. Seçim ve kimlik yeniden hesaplanır. Eşleşirse ayrı okuma bağlantısıyla değişiklik öncesi tutarlı yedek yayımlanır. Sonra sınırlı DELETE ve `cleanup_runs` kaydı aynı transaction içinde tamamlanır. Her silmede bağlantısız olma koşulu yeniden SQL koşuludur; silinen sayı seçime eşit olmalıdır. Her hata/iptalde transaction geri alınır. Yedek oluşturulamadıysa silme başlamaz; sonradan hata olursa alınmış yedek korunur. Boş seçimde yedek ve günlük yazılmaz.

Temizleme yaşını veya kapsamını otomatik uygulayan bir watch görevi yoktur. Önizlemenin yazdığı açık `--apply TOKEN` komutu gereklidir. Yeni kaynak aramasında silinmiş bağlantısız kayıt tekrar gelirse yeni gözlem kimliği/sayısı oluşabilir. Önceki iş özetleri tarihsel çalışma sonuçları olarak korunur.

## Boyut ve kurtarma

Kullanım görünümü ana dosya, WAL ve rollback journal boyutunu; SQLite page_count/page_size ve freelist_count üzerinden mantıksal ve yeniden kullanılabilir alanı gösterir. Mantıksal sayımlar tek okuma snapshot'ından, fiziksel boyutlar o andaki dosya gözleminden gelir. SHM, yedekler, raporlar ve toplam disk kapasitesi bu sayılara dahil değildir. Dosya türü lstat ile kontrol edilir; beklenmeyen symlink/dizin izlenmez.

DELETE dosyayı hemen küçültmez; sayfalar sonraki kayıtlar için tekrar kullanılabilir. VACUUM yoktur. Önceki yedeği almak ek disk alanı gerektirir; otomatik yedek silme veya toplam disk kotası uygulanmaz. Temizlik günlüğü yedek konumunu kaydeder; yedek boş bir kayıt alanına restore edilebilir. Temizlik öncesi yedek henüz yapılmamış temizliğin günlük satırını içermez.

## Şema ve doğrulama

Şema 5 `provider_cooldowns` ve `cleanup_runs` tablolarını ekler. Şema 1–4 açık migration ile, eski sürüm yedeği alınarak taşınır. Sürüm 4 tablo kümesi sabit tanımlıdır; yeni tablolar eski şema doğrulamasına yanlışlıkla eklenmez. Mevcut gözlem/bulgu/karar/kontrol/iş satırları korunur. Eski uygulamaya dönüş migration öncesi yedekle yapılır.

Testler farklı adaptör/süreç örneklerinde bekleme, başlık sonrası zorla süreç kapatma, uzun/eşit/kısa süreler, saat davranışı, kayıt hatası, sağlayıcı ayrımı, önizleme değişimi, kanıt koruma, yedekleme/silme/audit hatalarında geri alma ve restore davranışını kapsar. Kontrollü 10222 gözlemli yerel bakım denemesi STATUS.md içinde kayıtlıdır; bu küçük fixture milyonlarca kayıt veya uzun süreli işletim ölçümü değildir.

Birincil protokol kaynakları: [urlscan kota başlıkları](https://docs.urlscan.io/pages/api-rate-limits), [HTTP Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after). Yerel backup/transaction davranışı mevcut adaptör ve otomatik testlerle doğrulanır.
