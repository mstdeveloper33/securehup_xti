# 0033 — Onaylı tam adres için CNAME hedef kanıtı

**Tarih:** 29 Ekim 2026 · **Durum:** 0.33.0'da uygulandı.

## Sorun

0.32 maruziyet görünümü, CNAME/delegasyon kanıtı olmadığı için takeover değerlendirmesini desteklenmiyor gösteriyordu. Yalnız sertifika geçmişinde bir alt alan adının görünmesi, onun kullanıcıya ait olduğunu veya aktif DNS sorgusuna izin verildiğini kanıtlamaz. Öte yandan CNAME hedefinin NXDOMAIN olması da üçüncü taraf kaynağın başkası tarafından alınabilir olduğunu tek başına kanıtlamaz.

DNS terminolojisinde CNAME sahibi bir takma ad, kayıt değeri karşılık gelen kanonik addır. NXDOMAIN ise sorgulanan adın DNS'te bulunmadığını anlatır. Bu iki olgudan sağlayıcı hesabının alınabilirliği veya gerçek takeover sonucu doğrudan çıkarılamaz. [RFC 8499](https://www.rfc-editor.org/info/rfc8499/), [RFC 8020](https://www.rfc-editor.org/info/rfc8020/)

## Karar

`surface cname check DOMAIN` yalnız önceden `assets add` ile kaydedilmiş ve `surface approve` ile etkinleştirilmiş tam adres için çalışır. Pasif aday, `owned` kararı veya kök kapsamı alt adreslere otomatik yetki vermez. Ağdan önce tam kapsam doğrulanır; çalışma ortak yerel kilit altındadır; kayıt transaction'ında kapsam tekrar doğrulanır.

Adaptör sabit Google Public DNS JSON DoH uç noktasına doğrulanmış TLS ve sayısal IP sabitlemesiyle gider. Yalnız CNAME; zincir varsa terminal hedef için A ve AAAA sorgulanır. HTTP 200 ile DNS RCODE ayrı değerlendirilir; kesilmiş, çelişen, ilgisiz, döngülü, sekiz adımı veya 16 adresi aşan yanıt güvenli hatadır. DNSSEC doğrulaması kapatılmaz ve EDNS istemci alt ağı `0.0.0.0/0` olur. [Google Public DNS JSON API](https://developers.google.com/speed/public-dns/docs/doh/json), [Google DoH](https://developers.google.com/speed/public-dns/docs/doh)

Takma ad durumu `present/absent/nxdomain/failed`; terminal hedef durumu `resolved/no_address/nxdomain/failed/not_applicable` olarak ayrı saklanır. Zincir, terminal hedef, IP'ler, politika sürümü, zaman, hata/notlar, durum özeti ve değişen alanlar eklemeli kanıttır. İlk sonuç `baseline`, aynı durum `unchanged`, anlamlı fark `changed` olur.

`surface exposures`, yalnız `present + target nxdomain` sonucunu kesin olmayan `dangling_cname_target_nxdomain` adayı yapar. Aday; kanıt kimliği/zamanı, zincir, terminal hedef ve şu sınırları taşır: alınabilirlik kanıtlanmadı, özel DNS/sağlayıcı hesap durumu bilinmiyor, kaynak sahiplenilmedi ve hedefe HTTP bağlantısı yapılmadı.

## Veri geçişi ve güvenlik

Şema 16 `surface_cname_checks` tablosunu ve varlık indeksini ekler. Şema 15→16 geçişi yazma kilidi altında önce doğrulanabilir şema 15 yedeği yayımlar, tabloyu tek transaction'da boş oluşturur, şema/bütünlük/yabancı anahtar kontrolünden sonra tamamlar. Hata ana veritabanını şema 15'te bırakır. Eski kanıtlardan CNAME geçmişi veya aday uydurulmaz.

Hedef site bağlantısı, HTTP, banner, içerik, sağlayıcı hesabı, kaynak sahiplenme, kimlik bilgisi, oturum açma, exploit ve otomatik DNS değişikliği yoktur. CNAME değişiklikleri bu ilk dilimde ortak bildirim kutusuna eklenmez; geçmiş ve salt-okunur maruziyet görünümünde kalır.

## Sonuçlar

ASM-05/CAP-031 sağlayıcıdan bağımsız ilk sarkan CNAME kanıtına ilerler. Delegasyon/NS vakaları, sağlayıcıya özgü imzalar, yanlış alarm ölçümü, tekrar politikası ve insan onaylı düzeltme iş akışı açık kalır. Ücretli servis, API anahtarı veya yeni Python paketi yoktur.
