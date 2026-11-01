# 0025 — Onaylı ve kesin IP'ye sabitlenmiş servis envanteri

**Tarih:** 29 Ekim 2026  
**Karar:** İlk servis envanteri yalnız etkin domain kapsamı, açıkça beyan edilen kesin genel IP ve güncel DNS eşleşmesi birlikte varsa sabit küçük TCP planını çalıştıracak.

## Neden

Bir domainin kullanıcı tarafından yönetildiğinin beyan edilmesi, DNS'te görünen her IP'nin aynı kullanıcıya ait olduğunu kanıtlamaz. CDN, barındırma ve paylaşımlı altyapı adreslerinde geniş port taraması komşu sistemlere istek gönderebilir. Bu nedenle yalnız `surface approve DOMAIN` onayı, servis kontrolü için yeterli kabul edilmedi.

Ayrıca açık bir port ürün, sürüm veya zafiyet kanıtı değildir. İlk dilimde banner toplamak, protokol komutu göndermek, sürüm tahmin etmek veya nmap/masscan gibi dış süreç çalıştırmak gereksiz kapsam ve işletim riski oluşturur.

## Karar

Kullanıcı şu bilgileri aynı açık komutta verir:

- daha önce kaydedilmiş ve etkin dış yüzey kapsamındaki tam domain;
- yönetmeye yetkili olduğunu beyan ettiği kesin genel IPv4 veya IPv6 adresi;
- bu IP'yi kontrol etme yetkisinin görünür gerekçesi.

Program önce Google Public DNS üzerinden domainin A ve AAAA görünümünü alır. Belirtilen IP bu güncel cevapta yoksa hiçbir hedef portuna bağlanmaz. Cevapta özel, yerel veya özel kullanım adresi varsa bütün hedef bağlantıları engeller. En fazla 16 DNS adresi kabul edilir; yalnız açıkça belirtilen tek IP kontrol edilir.

İlk sabit plan `22, 25, 53, 80, 443, 587, 993, 3389, 8080, 8443/tcp` portlarıdır. Her porta en fazla bir saniyelik TCP bağlantısı denenir; toplam çalışma 20 saniyeyle sınırlıdır. Uygulama verisi, HTTP isteği, TLS el sıkışması, banner, karşılama metni veya kimlik bilgisi gönderilmez. Kullanıcı bu sürümde serbest port aralığı veremez.

Sonuçlar yalnız üç durum taşır:

- `open`: TCP bağlantısı kuruldu;
- `closed`: bağlantı açıkça reddedildi;
- `unknown`: süre veya yerel/ağ hatası içinde kesin sonuç alınamadı.

`unknown`, kapalı kabul edilmez. Port yanındaki SSH/HTTP gibi ad yalnız yaygın port kullanımına dayalı “aday” etiketidir; gerçek çalışan ürünü doğrulamaz.

## Kayıt ve değişim

Her çalışma domain, açıkça onaylanan IP, gerekçe, DNS kanıtı, kontrol edilen kesin IP, sabit port sonuçları, politika sürümü ve zamanlarla eklemeli saklanır. Sonuç özeti SHA-256 ile doğrulanır. İlk kayıt temel; aynı durum değişiklik yok; DNS/IP/port durumu farklıysa açıklanabilir değişiklik olur. Önceki kanıt üzerine yazılmaz.

Yazma transaction'ı etkin domain kapsamını yeniden denetler. Kapsam ağ çalışırken kaldırılmışsa sonuç kaydedilmez. `surface services show` ve `surface overview` yalnız saklanmış kanıtı okur; yeni bağlantı yapmaz. Şema 13 önce doğrulanmış yedeğe alınarak şema 14'e geçirilir ve servis geçmişi boş başlar. Eski veriden servis sonucu uydurulmaz.

## Açık sınırlar

Bu özellik ağ tarayıcısı, zafiyet tarayıcısı veya teknoloji parmak izi değildir. UDP, serbest port aralığı, bütün DNS IP'leri, banner/sürüm, CVE eşleştirmesi, parola denemesi, exploit, sayfa içeriği ve otomatik arka plan çalışması yoktur. Açık port bulgusu otomatik alarm veya risk kararı üretmez.

Teknoloji doğrulaması ileride eklenirse protokol başına ayrı güvenlik sınırı, gönderilecek kesin baytlar, yanıt boyutu, lisans ve laboratuvar testleri gerektirecek. Genel port taraması ancak IP sahipliği/kapsam modeli ayrıca güçlendirilirse değerlendirilecek.
