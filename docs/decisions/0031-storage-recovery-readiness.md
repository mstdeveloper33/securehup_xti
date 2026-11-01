# 0031 — Disk, saklama ve kurtarma hazırlığını tek görünümde açıklama

**Durum:** Kabul edildi  
**Tarih:** 29 Ekim 2026

## Bağlam

`storage status` veritabanı, WAL/journal ve SQLite içinde yeniden kullanılabilir alanı; `storage cleanup` bağlantısız eski gözlemlerin kontrollü önizlemesini gösterir. `backup` ve `restore` tutarlı, üzerine yazmayan akışlardır. Ancak kullanıcı diskte ne kadar çalışma payı kaldığını, yönetilen bir yedeğin bulunup bulunmadığını, en yeni yedeğin okunabilirliğini ve saklama ihtiyacını farklı komutlardan çıkarmak zorundadır.

Bir yedek dosyasının varlığı onun geçerli, güncel, ayrı ortamda veya geri yüklenmiş olduğunu kanıtlamaz. Bu ayrımlar görünür olmadan “kurtarmaya hazır” sonucu verilmemelidir.

## Karar

`storage readiness`, aşağıdaki kanıtları salt okunur tek operasyon raporunda birleştirir:

- Mevcut veritabanı/WAL/journal/mantıksal/yeniden kullanılabilir alanı.
- Kayıt klasörünün sınırlı ve sembolik bağlantı izlemeyen toplam dosya kullanımı.
- Dosya sisteminin toplam ve kullanılabilir alanı.
- Yalnız kayıt klasöründeki `backups/*.db` yönetilen yedek envanteri.
- En yeni yönetilen yedeğin XTI şeması, SQLite quick check ve yabancı anahtar bütünlüğü.
- Seçilen saklama gününe göre bağlantısız gözlem temizlik önizlemesi.

Çalışma payı politikası, en az 64 MiB veya mevcut SQLite mantıksal boyutunun iki katından büyük olanıdır. Bu eşik kesin yedek boyutu, kapasite garantisi veya otomatik kota değildir; küçük kişisel kurulumda yeni yazma ve yerel yedek için erken uyarıdır.

Yedek güncellik eşiği varsayılan yedi gün, 1–3650 gün arası seçilebilir. Saklama önizlemesi varsayılan 90 gün, 7–3650 gün arası seçilebilir. En yeni yönetilen yedek bozuksa daha eski bir dosya sessizce “son sağlıklı” olarak seçilmez. Ayrı ortam kopyası `unknown`, geri yükleme tatbikatı `not_recorded` kalır; çünkü bu sürüm bunların kanıt günlüğünü tutmaz.

Dosya adaptörü en fazla 10.000 düzenli dosyayı ve 1.000 yönetilen yedeği işler; sembolik/özel girdileri takip etmez. Sınıra ulaşılırsa tarama eksik olarak işaretlenir. Görünüm dosya oluşturmaz, silmez, yedek almaz, geri yüklemez veya internete bağlanmaz. Yeni tablo ve migration yoktur; şema 15 değişmez.

## Sınırlar

- Kayıt klasörü dışına `--output` ile alınmış yedek otomatik envantere dahil değildir.
- Aynı diskteki geçerli yedek disk arızasına karşı koruma değildir.
- Quick check ve şema doğrulaması gerçek geri yükleme tatbikatının yerine geçmez.
- Dosya sistemi boş alanı başka süreçlerin eşzamanlı kullanımından hemen sonra değişebilir.
- Saklama sonucu yalnız önizlemedir; otomatik silme veya yedek temizleme yoktur.

## Sonuçlar

Kullanıcı disk baskısını, yedek eksikliği/bozukluğu/eskiliğini ve saklama ihtiyacını tek komutta görür; fakat doğrulanmamış dış kopya ya da restore tatbikatı hakkında yanlış güven oluşmaz. Dosya sistemi adaptörü ve uygulama politikası ayrıdır; gelecekte yedek tatbikat günlüğü veya farklı depolama hedefleri eklenebilir.
