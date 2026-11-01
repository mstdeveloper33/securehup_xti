# 0080 — Denetlenebilir Feodo Tracker tam-snapshot IOC beslemesi

**Durum:** Kabul edildi · **Tarih:** 30 Ekim 2026 · **Sürüm:** 0.80.0

## Bağlam

Yerel IOC kataloğu kaynak iddialarını saklıyordu ancak ücretsiz bir dış beslemeyi, kaynak kesintisini ve listeden gerçek çıkışı ayırarak güncelleyemiyordu. Kişisel/ücretsiz profil anahtarsız, yeniden kullanımı açık, hedefe temas etmeyen ve sınırlı alınabilen bir başlangıç kaynağı gerektiriyordu.

## Karar

- Feodo Tracker'ın saldırgan olmayan 30 günlük `ipblocklist.json` tam listesi yalnız açık `ioc sync --source feodo` komutuyla alınır. Saldırgan/aggressive liste kullanılmaz.
- Sabit HTTPS adresi dışında konuma gidilmez; yönlendirme ve içerik sıkıştırması reddedilir. Yanıt 30 saniye, 8 MiB ve 50.000 ham satırla sınırlıdır; JSON ve her alan katı doğrulanır.
- Aynı IP'nin çoklu port/malware satırları deterministik tek IOC iddiasına birleşir. Kaynak sayısal güven vermediğinden 50/100 değeri `XTI yerel nötr politikası` olarak açıkça etiketlenir.
- Başarılı snapshot, kanonik IOC/idda/olay güncellemesi, çalışma özeti ve IOC başına çalışma bağıyla tek SQLite transaction'ında saklanır. Tam listeden çıkan etkin iddia geçmiş silinmeden geri çekilir; yeniden görünürse aynı kimlikle etkinleşir.
- Taşıma, HTTP, biçim veya doğrulama hatası yalnız başarısız çalışma kaydı üretir. Önceki IOC iddiaları değiştirilmez. Geçerli boş JSON listesi ise başarılı tam snapshot sayılır ve önceki Feodo iddialarını geri çeker.
- Okuma yolları internetsiz ve salt okunurdur. Besleme IOC'si otomatik engelleme, zararlılık veya varlık etkisi kararı değildir.

## Veri ve geri alma

Şema 34, `cti_feed_runs` ve `cti_feed_run_items` tablolarını ekler. Şema 33→34 geçişi önce doğrulanmış yedek alır; DDL ve sürüm aynı transaction'da uygulanır, hata halinde geri alınır. Eski kayıtlardan besleme çalışması uydurulmaz. Eski uygulamaya dönüşte geçiş öncesi yedek kullanılır.

## Sonuçlar ve açık işler

İlk ücretsiz IOC kaynağında giriş/çıkış, kaynak hatası ve eksiksiz provenance ayrılmıştır. Kaynak çeşitliliği, yanlış-pozitif/suppression modeli, domain/URL/hash beslemeleri, aktör–kampanya–malware ilişkileri ve zamanlama ayrı iş paketleridir.
