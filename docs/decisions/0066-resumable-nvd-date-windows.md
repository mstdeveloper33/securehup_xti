# ADR 0066 — Devam edilebilir ve sınırlı NVD tarih pencereleri

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

Tek-CVE ve maruziyet kapsamlı yenileme yalnız bilinen kimlikleri alıyordu. Ücretsiz resmî NVD kaynağında belirli bir dönemde yeni yayımlanan veya değişen kayıtları izlemek için kontrollü bir toplama yolu yoktu. Tam kataloğu tek seferde çekmek kişisel bilgisayarda gereksiz ağ, disk ve yeniden başlatma yükü oluşturur; yarım kalan sayfada belirsiz ilerleme de kayıt atlama veya tekrarlama riski doğurur.

NVD CVE API 2.0 değişiklik zamanını `lastModStartDate` ve `lastModEndDate` ile birlikte filtreler, sonuçları `startIndex` ve `resultsPerPage` ile sayfalar ve resmî olarak bir tarih aralığını en fazla 120 günle sınırlar. API 2.0, değişen veriyi takip etmek için veri akışlarına tercih edilen yoldur. Kaynak davranışı [NVD CVE API belgesinde](https://nvd.nist.gov/developers/vulnerabilities) ve [başlangıç rehberinde](https://nvd.nist.gov/developers/start-here) açıklanır.

## Karar

`vuln nvd-window-plan` ve `vuln nvd-window-fetch` aynı uygulama/depo portlarının iki açık girişidir. Plan salt okunurdur. Fetch yalnız planlanan tek sayfayı alır; kendi kendine döngü, arka plan hizmeti veya gizli tekrar yapmaz.

Ürün, resmî 120 günlük üst sınırdan daha sıkı kişisel sınırlar uygular:

- pencere en fazla yedi gün;
- sayfa 1–100 kayıt;
- yanıt 8 MiB, tek CVE 4 MiB;
- bağlantı 30 saniye, sabit resmî HTTPS uç noktası, yönlendirme ve sıkıştırma yok;
- anahtarsız çağrılar arasında önceki süreçteki son deneme dahil en az 6,5 saniye.

Yanıtın biçim/sürüm, başlangıç sırası, dönen/toplam kayıt sayısı ve zaman damgası doğrulanır. Her CVE kimliği, kaynak zamanı ve mevcut tek-CVE ayrıştırma sınırlarından geçer; aynı sayfadaki yinelenen veya istenen değişiklik aralığı dışındaki kayıt bütün sayfayı reddettirir. Son sayfa dışında eksik veya boş sayfa kabul edilmez.

İlerleme tam `(window_start, window_end, page_size)` anahtarıyla tutulur. Başarılı sayfadaki bütün CVE ana kayıtları, eklemeli değişiklik olayları, kaynak çalışma kaydı ve `next_start_index` tek `BEGIN IMMEDIATE` transaction'ında yazılır. Kaynak hatası ayrı başarısız kaynak çalışması olarak denetlenir ama imleç değişmez. İlk başarılı sayfadan sonra NVD `totalResults` değeri değişirse olası sayfa kaymasını gizlemek yerine işlem durur. Kullanıcı yeni bir tam pencere veya sayfa boyutuyla baştan kontrollü çalışma açabilir.

Tamamlanmış ilerleme tekrar çağrıldığında kaynak nesnesi kullanılmadan sonuç döner. Tarih penceresiyle gelen kayıtlar mevcut `nvd_cve_records`, `nvd_cve_events` ve `vulnerability_source_runs` düzenini paylaşır; ayrı, çelişen bir CVE kataloğu oluşturulmaz.

Şema 30 yalnız `nvd_window_syncs` tablosunu ekler. Şema 29→30 geçişi tabloyu boş oluşturur; eski tek-CVE kaynak geçmişinden pencere veya imleç türetmez.

## Sonuçlar

- Küçük dönemler tekrar üretilebilir biçimde ve çağrı başına sınırlı kaynak tüketimiyle alınabilir.
- Süreç kapanırsa son atomik başarılı sayfadan devam edilir; yarım sayfa ilerlemiş görünmez.
- Planı görmek ve tamamlanan pencereyi tekrar çağırmak internete çıkmaz.
- Kaynak değişikliği `investigating/affected/not_affected/fixed` insan kararını, gerekçeyi, zamanı veya olay geçmişini değiştirmez. Yeniden değerlendirme ve bildirim ayrı açık komutlardır.
- Aynı CVE farklı pencerelerde yeniden görülebilir; değişmediyse ana kayıt güncellenmiş görülme zamanı alır fakat yeni değişiklik olayı üretmez.
- Otomatik tarih dilimleme, zamanlayıcı, boşluk kapatma takvimi, tam katalog aynası ve kapasite ölçümü bu kararla eklenmez.
