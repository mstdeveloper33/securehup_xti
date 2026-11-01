# 0027 — Seçili dış yüzey kontrollerini sınırlı ön plan oturumunda tekrarlama

**Durum:** Kabul edildi  
**Tarih:** 29 Ekim 2026

## Bağlam

DNS/TLS/HTTPS, MX/SPF/DMARC ve kesin IP'ye sınırlı TCP kontrolleri ayrı komutlarla kalıcı kanıt ve gerçek değişiklik bildirimi üretiyor. Kişisel kullanımda bunları belirli aralıklarla elle tekrarlamak değişikliklerin geç fark edilmesine yol açabilir. Buna karşılık daemon, işletim sistemi zamanlayıcısı veya kalıcı iş kuyruğu; kapanma kurtarma, yapılandırma, güvenlik ve işletim yükünü bu aşamada gereksiz büyütür.

Kontrollerin yetki ve güvenlik kapıları farklıdır. Özellikle servis kontrolü etkin domain kapsamına ek olarak kesin genel IP, güncel DNS eşleşmesi ve görünür yetki gerekçesi ister. Ortak izleme özelliği bu kuralları kopyalamamalı veya gevşetmemelidir.

## Karar

`surface monitor KÖK`, seçilen `web`, `mail` ve isteğe bağlı `services` kontrollerini terminal açıkken tekrarlar. Varsayılan seçim `web mail`; servis kontrolü ancak `--checks services`, `--service-address` ve `--service-reason` birlikte verilirse eklenir.

Kullanıcı üç bağımsız sınır verir: en fazla tur 1–1000, tamamlanan turlar arası bekleme 300–86400 saniye ve yeni kontrol başlatma süresi 1–604800 saniye. Varsayılanlar 3 tur, 3600 saniye ve 86400 saniyedir. Süre monotonic saatle ölçülür. Bütçe dolduğunda yeni kontrol başlamaz; başlamış ve kendi içinde zaten süreli olan kontrol tamamlanabilir.

Orkestratör küçük bir `SurfaceMonitorRunner` sözleşmesine bağlıdır. Web, posta ve servis çalıştırıcıları mevcut uygulama servislerini çağırır. Kapsam, IP, sonuç doğrulama, eklemeli kanıt, değişim ve atomik bildirim davranışı tek kontrol komutlarıyla aynı kalır. Bütün seçimler, sınırlar, etkin kapsam ve varsa kesin IP ağ bağlantısından önce doğrulanır.

Terminal bütün oturum boyunca ortak yerel çalıştırma kilidini tutar. Ağ isteği ve bekleme sırasında SQLite yazma transaction'ı açık tutulmaz. `Ctrl+C` normal biçimde sürece yayılır; daha önce tamamlanan kontrol kanıtı ve bildirim geri alınmaz.

İzleme oturumu için yeni kalıcı tablo oluşturulmaz ve şema 15 değişmez. Final terminal/JSON özeti geçicidir. Kalıcı gerçek, mevcut üç kontrol geçmişi ve ortak gelen kutusudur. Bu nedenle yarım oturum otomatik devam ettirilmez; kullanıcı yeni bir komut başlatır.

## Sınırlar

- Bu bir daemon, arka plan servisi, cron işi veya bilgisayar kapalıyken çalışan izleme değildir.
- Kaynak/kontrol istisnası sonraki kontrolü otomatik denemek için yakalanmaz; komut güvenli hata ile durur, önceki kanıtlar kalır.
- İlk temel kayıt ve değişmeyen tekrar alarm değildir; `changed` sonucu da tek başına saldırı, kesinti veya zafiyet kararı değildir.
- Servis kontrolü sabit 10 TCP portunu aşmaz; banner, ürün/sürüm, UDP, serbest port veya exploit yoktur.
- E-posta, SMS, webhook veya masaüstü teslimi yoktur.

## Sonuçlar

Kullanıcı ücretsiz yerel kurulumda tek komutla onaylı dış yüzeyini sınırlı süre izleyebilir. Mevcut kanıt ve bildirim modelleri yeniden kullanıldığı için yeni özellik eklemek ayrı bir çalıştırıcıyla mümkün olur; depolama ve güvenlik kuralları orkestratöre dağılmaz. Sürekli çalışma gerektiğinde kalıcı zamanlama, kurtarma ve kaynak sağlığı ayrı bir ürün dilimi olarak tasarlanmalıdır.
