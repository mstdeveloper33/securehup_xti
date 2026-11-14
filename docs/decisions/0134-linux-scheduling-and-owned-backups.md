# 0134 — Linux zamanlaması ve doğrulanmış, sahipliği kayıtlı yedekler

**Durum:** Kabul edildi · **Tarih:** 14 Kasım 2026 · **Uygulama:** 0.133.0

Kişisel kullanımda sürekli açık bir Python döngüsü veya ayrı sunucu ürünü
kurmak yerine Linux kullanıcı zamanlayıcısı mevcut profil komutunu çağırır.
Çekirdek uygulama systemd'ye bağlı değildir: `SchedulingService` profil,
plan, kurtarma, kilit, dosya üretimi ve yedek portlarını kullanır. Yeni
veritabanı şeması veya dış bağımlılık gerektirmez.

`schedule generate` etkin profil ve pasif planı ağsız doğrular, yalnız yeni
klasöre `.service`, `.timer` ve o bilgisayara özel kullanım notu yazar.
Birimin adı profil UUID'sidir; görünen ad dosya adına dönüştürülmez. Otomatik
etkinleştirme, servis yöneticisi çağrısı veya linger değişikliği yapılmaz.

Üretilen komut sabit `/bin/sh` ile projenin mevcut POSIX `xti` dosyasını
argüman olarak çalıştırır; `-c` veya üretilmiş kabuk ifadesi kullanılmaz.
Kullanıcı değerleri ayrı argümanlardır. systemd ortam açılımı `:` önekiyle
kapalıdır; `%`, tırnak ve ters eğik çizgi systemd kurallarına göre kaçırılır.
Bu yaklaşım, executable yolu için systemd'nin ek karakter kısıtlarını
veri/proje yollarına taşımadan boşluk, `$` ve tırnak içeren yolları korur.
Başlatıcı zaten kendi klasörüne göre çalıştığından `WorkingDirectory` yoktur.

Hizmet tek çalışmalıktır. Ön hazırlık başarılı olmadan toplama başlamaz.
Zamanlayıcı yeniden başlatma fırtınası üretmez; kısmi kaynak sonucu ve kilit
meşgul çıkışları başarıya çevrilmez. Her tur profilin güncel revizyonunu
kullanır. Günlük/haftalık saat ve IANA saat dilimi açıktır. Kaçan zamanın
telafisi her kaçırılan turu tekrar etmez. Üretim ve uygulama testleri Linux
hizmetinin bu macOS ortamında etkinleştirildiği anlamına gelmez.

`schedule prepare` ortak çalışma kilidi altında profili tekrar okur,
seçimleri ve disk payını doğrular, kesilmiş toplama oturumlarını kapatır.
Sonra yeni UUID'li SQLite yedeği alıp yeni geçici konuma geri yükleyerek
doğrular. Mevcut veritabanı veya yedek üzerine yazılmaz. Hazırlık ve toplama
aynı işlem değildir; aralarında başka iş kilidi alırsa toplama meşgul olarak
durabilir, devam eden işi zorlamaz.

Saklama azaltması yalnız `scheduled-backups/` içindeki sahiplik kaydıyla
eşleşen yedekleri kapsar. Kanonik kayıt, dosya adı/UUID, sıra, zaman, kaynak
profil, boyut ve SHA-256 doğrulanır. Kayıp veya değiştirilmiş tutulacak
yedekte silme yapılmaz. Bağlantı/özel dosya ve yol taşması reddedilir;
tanınmayan dosyalar korunur ve görünür uyarı üretilir. `backups/` ve elle
alınmış kopyalar bu bakımın dışında kalır.

Kesinti kurtarmasında yedek önce geçici konumda hazırlanıp doğrulanır.
Bilinen dosya özetiyle `creating` rezervasyonu diske kalıcı yazılır, dosya
benzersiz hedefe yayımlanır, sonra kayıt `retained` olur. Yeniden hazırlık
tam eşleşen yayımlanmış dosyayı tamamlar; yayımlanmamış rezervasyonu emekliye
ayırır. Silinecek yedek önce `retired` olarak kalıcı kaydedilir, ardından
silinir; kesinti sonrası aynı silme güvenle tamamlanır. Dosya ve klasör
fsync sırası yeni yedek kalıcı olmadan eskisinin budanmasını önler.

Testler gerçek geçici SQLite üzerinde yedek/restore, veri ve profil
değişimi, disk yetersizliği, dosya/manifest bozma, kesinti sınırları,
sahipsiz dosyaların korunması ve ortak kilidi kapsar. Linux'ta ayrıca
`systemd-analyze verify` üretilen dosyaları ayrıştırır; bu araç olmayan
ortamda ilgili test açıkça atlanır. Günlük kullanım
[Linux rehberinde](../LINUX_SCHEDULING.md) anlatılır.
