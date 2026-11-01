# ADR 0061 — İkinci resmî üretici kaynağı olarak SUSE CSAF VEX

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

Red Hat VEX tek bir dağıtıcının ürün hükmünü verir. Ücretsiz kişisel kullanımda ikinci resmî kaynak gerekir; ancak farklı dağıtımın ürün durumunu yerel varlığa taşımak yanlış güven üretir. SUSE, CVE bazlı CSAF VEX 2.0 verisini ücretsiz ve CC-BY-4.0 koşuluyla yayımlar. Eski CVE geri-doldurması `2023` dizinindedir.

## Karar

- `--provider suse`, sabit `ftp.suse.com/pub/projects/security/csaf-vex` HTTPS kökünü kullanır.
- CVE yılı 2023'ten küçükse dizin `2023`, değilse CVE yılıdır. İndeks dosyası her istekte alınmaz.
- Ortak CSAF taşıma/ayrıştırma katmanı; sağlayıcıya özgü kaynak anahtarı, yayımcı adı, namespace ve URL üreticisiyle yapılandırılır.
- Yönlendirme kapalıdır; 30 saniye, 16 MiB, kimlik kodlaması ve `application/json` sınırları korunur.
- Gerçek SUSE biçimindeki boş durum kovaları atlanır; bütün kovalar boşsa belge reddedilir. Boşluk içeren ASCII ürün kimlikleri ile `cpe:/` ve CPE 2.3 kabul edilir.
- SUSE bu dilimde yalnız yazmasız önizlemedir. Red Hat RPM eşleştirmesi, kalıcı kanıt veya otomatik maruziyet kararı üretilmez.
- Şema 26 değişmez; göç ve yedek gerekmez.

## Sonuç

Platform iki bağımsız resmî dağıtıcı beyanını araştırabilir, fakat beyanlar birbiriyle veya yerel varlıkla otomatik birleştirilmez. Yeni CSAF üreticileri ortak katmana küçük, doğrulanmış sağlayıcı politikasıyla eklenebilir.
