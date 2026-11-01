# 0016 — Kesin zamanda sona eren tam alan adı istisnası

**Tarih:** 29 Ekim 2026 · **Durum:** 0.16.0'da uygulandı.

## Sorun

Kalıcı istisna, doğrulanmış iş ortağı gibi uzun ömürlü durumlarda yararlıdır. Kampanya, test veya geçici hizmet için kullanıldığında ise unutulabilir ve aynı adres sonradan el değiştirirse yeni adayları süresiz bastırabilir. Otomatik sona erme gerekir; fakat kişisel terminal uygulamasında sürekli çalışan bir zamanlayıcıya güvenmek veya yalnız listeleme sırasında gizli veri değişikliği yapmak doğru değildir.

## Karar

`allowlist add` ve `allowlist add-finding`, isteğe bağlı `--expires-in-days` alır. Değer 1–3650 tam gün arasındadır. İşlem tek bir UTC anı okur ve kesin bitiş zamanını kaydeder. Seçenek verilmezse kayıt kalıcıdır ve önceki davranış korunur.

Bir kayıt, elle kaldırılmamış ve bitiş zamanı politika değerlendirme anından kesin olarak ilerideyse etkindir. Bitiş anına eşit olduğunda artık etkin değildir. Sona erme türetilmiş durumdur: arka plan işi, saat başı tarama veya okuma sırasında yazılan bir “expired” olayı yoktur. Böylece yalnız listelemek veritabanını değiştirmez ve bilgisayar kapalıyken kaçırılacak zamanlama işi oluşmaz.

Etkin kaydın aynı bitişle yeniden eklenmesi yan etkisizdir. Bitiş veya gerekçe değiştirilirse `updated`, elle kaldırılmış ya da süresi dolmuş kayıt yeniden açılırsa `reactivated` olayı aynı istisna kimliğine eklenir. Her olay o işlemdeki bitiş zamanını taşır. `added`, `updated`, `revoked` ve `reactivated` geçmişi silinmez; ilk oluşturulma zamanı korunur.

## Uygulama ve depolama sınırı

Arama ve dosya içe aktarma servisleri bir politika anı seçip o ana göre etkin çiftleri adaylardan çıkarır. SQLite bulgu adaptörü, gözlem ve bulgu yazım transaction'ı içinde güncel zamanı yeniden okuyup süreyi tekrar doğrular. Bu ikinci kontrol, uygulama filtresiyle yazım arasındaki sürede istisnanın bitmesini ve filtreyi unutan yeni bir çağrı yolunu kapsar.

Süre boyunca ham gözlem saklanır; bulgu, kanıt bağlantısı ve bildirim üretilmez. Süre dolması kendi başına yeni kayıt yazmaz. Aynı kaynak kaydı yeniden işlendiğinde veya yeni gözlem geldiğinde korunmuş gözlem mevcut ya da yeni bulguya bağlanabilir. Bozuk veya zaman dilimsiz bitiş değeri güvenli hatadır; kısmi gözlem/bulgu transaction'ı geri alınır.

## Veri geçişi ve kurtarma

Şema 9, `allowlist_entries` ve `allowlist_events` tablolarına nullable `expires_at` ekler ve olay türüne `updated` değerini katar. SQLite'ın constraint değiştirme sınırı nedeniyle şema 8 tabloları tek transaction içinde yeniden kurulur. Geçişten önce doğrulanabilir şema 8 yedeği yayımlanır; kimlikler, satır ve olay sırası, gerekçeler ve zamanlar aynen kopyalanır. Eski kayıtların bitişi `NULL` olur, yani kalıcı kalırlar. Hata ana veritabanını şema 8'de bırakır ve kurtarma yedeğini korur.

Şema 1–7 geçişleri güncel tabloları doğrudan oluşturur; eski veriden istisna veya bitiş zamanı çıkarılmaz. Güncel backup/restore bitiş zamanlarını ve bütün işlem geçmişini kapsar.

## Sonuçlar ve sınırlar

- Geçici meşru adresler unutulsa bile belirlenen anda yeni adayları bastırmayı bırakır.
- Sona erme adresin güvenli veya tehlikeli olduğunu kanıtlamaz; yalnız kullanıcı politikasının süresini bitirir.
- Süre dolduğunda geçmiş gözlem otomatik işlenmez; yeni kaynak çalışması veya açık yeniden işleme gerekir.
- İlk dilim mutlak tarih girişi, tenant/kullanıcı kapsamı, toplu güncelleme ve onay iş akışı içermez.
- Tam adres ve tek izlenen varlık sınırı, [0012 numaralı temel karardaki](0012-exact-domain-allowlist.md) gibi değişmez.
