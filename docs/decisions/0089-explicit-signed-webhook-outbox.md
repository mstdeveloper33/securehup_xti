# ADR 0089 — Açık seçimli imzalı webhook teslim kuyruğu

## Durum

Kabul edildi — 30 Ekim 2026.

## Karar

İlk dış bildirim kanalı, birleşik yerel kutudaki bir bildirimin ve bir hedefin kullanıcı tarafından açıkça seçilmesiyle değişmez bir teslim kaydı oluşturur. Aynı hedef+bildirim çifti tekilleştirilir. Ağ beklenirken SQLite transaction'ı tutulmaz; her sonuç daha sonra ayrı ve sıralı deneme kanıtı olarak kaydedilir. Başarılı teslim yeniden gönderilmez, başarısız teslim yalnız açık komutla yeniden denenir.

Gövde kanonik JSON ve SHA-256 ile bağlıdır. Her istek, gönderim zaman damgası ve ham gövde üzerinde HMAC-SHA256 ile imzalanır; teslim kimliği alıcının tekrar önleme anahtarıdır. Sır komut satırından alınmaz, 0600 normal dosyadan okunur, çıktılarda tam URL/sır gösterilmez. Yerel SQLite ve yedekler sırrı içerir; uygulama düzeyi şifreleme iddiası yoktur.

Taşıma yalnız HTTPS/443'tür. DNS'in bütün sonuçları genel internet adresi olmalıdır; bağlantı kontrol edilen sayısal IP'ye sabitlenirken TLS adı özgün host ile doğrulanır. Proxy, yönlendirme, düz metin geri dönüşü ve uzak yanıt gövdesi saklama yoktur.

## Sonuçlar ve sınırlar

Kesinti teslim kaydını kaybettirmez, gövde denemeler arasında değişmez ve yeniden deneme görülebilir. HTTP 2xx yalnız alıcının isteği kabul ettiğini gösterir; olayın incelendiğini veya işlendiğini kanıtlamaz. Alıcı imzayı, zaman penceresini ve teslim kimliği tekilliğini doğrulamalıdır.

Bu dilim otomatik abonelik, toplu/due worker, daemon, işletim sistemi zamanlaması, inbound webhook, e-posta/SMS, sağlayıcıya özgü SIEM biçimi, OAuth/mTLS veya çok kiracılı sır kasası içermez. Bunlar ayrı güvenlik ve işletim kararlarıdır.
