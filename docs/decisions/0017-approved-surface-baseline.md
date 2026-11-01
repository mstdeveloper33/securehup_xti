# 0017 — Kullanıcı onaylı DNS/TLS dış yüzey temel kaydı

**Tarih:** 29 Ekim 2026 · **Durum:** 0.17.0'da uygulandı.

## Sorun

Marka taklidi araması kuruma benzeyen dış domainleri bulur, fakat kurumun kendi internet yüzeyindeki değişiklikleri göstermez. Bir kök domainin IP adresi veya TLS/HTTPS durumu değiştiğinde bunun yeni mi, beklenen mi, yoksa incelenmesi gereken bir sapma mı olduğu geçmiş olmadan anlaşılamaz.

Aktif bağlantı yapan bir özellik, sıradan varlık kaydından daha dar yetki sınırı gerektirir. XTI'nin kayıtlı bir adresi otomatik olarak kullanıcıya ait sayması, alt domain veya port aralığına kendiliğinden genişlemesi kabul edilmez. İlk dilim saldırı veya zafiyet taraması değil, sınırlı bir dış görünüm temel kaydı olmalıdır.

## Karar

`surface approve`, yalnız önceden `assets add` ile kaydedilmiş tam domaini kullanıcı gerekçesiyle etkin kontrol kapsamına alır. Bu işlem teknik DNS sahiplik kanıtı değil, yerel kullanıcı yetki beyanıdır. `approved`, `updated`, `revoked` ve `reactivated` işlemleri aynı varlık kimliğine bağlı eklemeli geçmişte saklanır. Kalıcı silme yoktur.

`surface check`, ağ bağlantısından önce kapsamın etkin olduğunu doğrular. Kontrol bitince kayıt transaction'ı içinde kapsamı yeniden doğrular; arada yetki geri çekilmişse sonuç kaydedilmez. Yerel çalıştırma kilidi, aynı kayıt alanındaki tarama, hedef kontrolü, bakım ve dış yüzey kontrolünün çakışmasını engeller.

Ağ adaptörü mevcut sınırlı kontrol politikasını yeniden kullanır:

- Google Public DNS üzerinden yalnız tam domain için A ve AAAA;
- özel, yerel, ayrılmış veya özel kullanım IP'sinde hedef bağlantısını engelleme;
- yalnız ilk doğrulanmış genel IP'ye 443/TLS ve `HEAD /`;
- TLS hostname ve sertifika zinciri doğrulamasını zorunlu tutma;
- yönlendirme, GET gövdesi, başka yol, port, IP, alt domain veya doğrulamasız bağlantı olmaması;
- toplam ve istek başına süre, kayıt ve yanıt boyutu sınırları.

## Kanıt ve değişiklik modeli

Her tamamlanan kontrol, başarısız veya kısmi olsa da ayrı `surface_checks` kanıtıdır. Sonuç; domain, politika sürümü, başlangıç/bitiş, DNS durumu, IP'ler, bağlanılan IP, TLS ve HTTPS durumu, güvenli hata ve yorumları taşır. Kayıt zamanına ek olarak güvenlik açısından anlamlı durumun kanonik SHA-256 özeti saklanır.

İlk ölçüm `baseline`, aynı kanonik durum `unchanged`, farklı durum `changed` olur. Değişim kaydı eklenen/çıkan IP'leri ve farklılaşan DNS, TLS, HTTPS, durum kodu veya bağlanılan IP alanlarını açıklar. Zaman ve açıklama metni durumu yapay olarak değiştirmez. Aynı sonuç yeniden ölçüldüğünde yeni kanıt oluşur fakat sahte değişiklik üretilmez.

`surface list` ve `surface show` tek salt okunur anlık görüntü kullanır; ağ isteği, kapsam değişikliği veya onarım yapmaz. Bozuk sonuç, özet hash'i veya değişim kaydı güvenli hatadır. Backup/restore kapsamı, bütün işlem olaylarını ve kontrol kanıtlarını kapsar.

## Veri geçişi

Şema 10; `surface_scopes`, `surface_scope_events` ve `surface_checks` tablolarını ve varlık/kapsam yabancı anahtarlarını ekler. Şema 9→10 geçişi yazma kilidi altında önce doğrulanabilir şema 9 yedeği yayımlar, yeni tabloları tek transaction içinde oluşturur ve bütünlüğü yeniden denetler. Hata ana veritabanını şema 9'da bırakır. Eski adreslerden yetki veya geçmiş kontrol türetilmez; tablolar boş başlar.

## Sonuçlar ve sınırlar

- Bu özellik dijital risk izlemenin dış saldırı yüzeyi ayağındaki ilk güvenli temeldir.
- Geçerli TLS veya HTTP yanıtı güvenlik; hata ise kesinti ya da risk kanıtı değildir.
- İlk dilim yalnız kayıtlı kök domaini kapsar. Otomatik subdomain keşfi ve sahiplik doğrulaması yoktur.
- Bu sürümde sertifika issuer, seri/parmak izi, SAN ve bitiş tarihi saklanmıyordu; bunlar 0.18.0'da [0018](0018-verified-certificate-evidence.md) ile eklendi.
- Port/servis taraması, teknoloji tespiti, zafiyet eşleştirmesi, exploit ve içerik indirme yoktur.
- Otomatik periyodik çalışma yoktur; her ölçüm açık `surface check` komutuyla başlar.
