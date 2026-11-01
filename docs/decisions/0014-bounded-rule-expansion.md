# 0014 — Ölçümlü dar alan adı kuralı genişletmesi

**Tarih:** 29 Ekim 2026 · **Durum:** 0.14.0'da uygulandı.

## Sorun

0.13.0 değerlendirmesi `exampel-login.net` gibi marka içinde yan yana iki harfi değişmiş ve ardından bilinen hizmet eki almış adayı, ayrıca `exampleshop.net` gibi markaya bitişik mağaza sözcüğünü kaçırıyordu. Aynı kümedeki `north-star.net`, `green-market.net` ve `catalog-data.net` ise yalnız sözcüksel biçimden gerçek sahiplik veya meşruiyet anlaşılamadığı için gereksiz alarma dönüşüyordu.

Genel benzerlik eşiğini düşürmek kaçırmaları kapatabilir, fakat çok daha fazla ilgisiz adı inceleme sırasına taşır. Üç bağlamsal alarmı yalnız yazıma bakarak bastırmak da gerçek bir taklit adayını gizleyebilir.

## Karar

Yalnız ölçülen iki boşluğu kapatan iki desen eklendi:

- Marka gövdesinde yalnız bir **yan yana harf değişimi** varsa ve aday bundan sonra mevcut bilinen hizmet eklerinden birini ayrı etiket parçası olarak taşıyorsa incelemeye alınır.
- En az altı karakterli marka gövdesinin başına veya sonuna yalnız tam `shop` sözcüğü, tire olmadan bitişmişse incelemeye alınır.

Bilinmeyen hizmet eki, kısa sözcüğün içindeki `shop` harfleri ve `shopping` gibi daha uzun bir sözcük bu kuralları tetiklemez. Bu sınırlar üç yeni negatif değerlendirme örneği ve doğrudan birim testleriyle korunur.

Üç bağlamsal gereksiz alarm otomatik bastırılmaz. Sahiplik veya iş ilişkisi biliniyorsa kullanıcı mevcut tam adres istisnasını gerekçeyle ekleyebilir. İleride gerçek kullanım geri bildirimi ayrı köken ve sürümle ölçülmeden genel eşik değiştirilmez.

## Sürüm ve kalıcılık

- Yeni iş ve sorgu planı yürütme sözleşmesi: `domain-rules-v3/psl:.../unicode:18.0.0`.
- Önceden de eşleşen ASCII aday bulgusu: `domain-rules-v1/psl:...`.
- Yalnız bu karardaki yeni desenle eşleşen ASCII aday bulgusu: `domain-rules-v2/psl:...`.
- IDN iskelet adayı: `idn-confusables-v1/.../unicode:18.0.0`.

Bu ayrım eski bulgunun, kararın ve bildirimin çoğalmasını önler. Eski yürütme sürümüyle sıraya alınmış iş yeni kuralla sessizce çalıştırılmaz; yeni davranış isteniyorsa yeni iş oluşturulur. Şema 8 değişmez ve migration gerekmez. Tam adres istisnası yeni desenleri de bastırır; ham gözlem saklanır.

## Ölçüm

`domain-evaluation-v2`, 44 tarihsel örneğe üç negatif koruma ekleyerek 47 sentetik örnek taşır. Sabit SHA-256 özeti `f7531925dbd72884519d56b251c5a6247ed10bc696a003f1a97fcad12c18582a` değeridir.

Sonuç: 27 doğru yakalama, 17 doğru eleme, 3 gereksiz alarm ve 0 kaçırma; precision `%90,00`, recall `%100,00`, yanlış alarm oranı `%15,00`, toplam doğruluk `%93,62`. Baseline değişimi yoktur. Ortak 44 örnekte önceki sürüme göre iki kaçırma giderilmiş, yeni gereksiz alarm oluşmamıştır.

Bu sayılar küçük sentetik kümenin davranışıdır; gerçek dünya tehdit doğruluğu, kaynak kapsamı veya sahiplik kararı değildir. `exampel-login.net` gibi sorgu varyantlarının arşiv kaynağında ayrıca aranması için kullanıcı `--typos` seçeneğini açmalıdır; kaynak aday adresi zaten döndürürse eşleştirme her zaman yapılır.

## Sonuçlar

- Ölçülen iki boşluk genel benzerlik eşiği değiştirilmeden kapanır.
- Eski bulgu kimlikleri ve kullanıcı kararları korunur.
- Aşırı genişleme örneklerle engellenir; bağlamla çözülebilecek alarmlar dürüstçe görünür kalır.
- Sonraki adım, kullanıcının gerçek inceleme kararlarını otomatik gerçek etiket saymadan ölçülebilir geri bildirim üretmektir.
