# 0166 — Firma komutunda kullanılmayan bileşenleri yüklememe

18 Kasım 2026 · 0.162.0 · kabul edildi.

Linux kabulü 120 saniyede yinelenerek durdu. 0.161.0 başarısız koşusunda
36 okumanın ortalama süreç süreleri Python 3.11 için 1,794–1,845, 3.13 için
2,025–2,098 saniyeydi. Farklı işlemlerin benzer CPU/süre tüketimi ortak
başlangıç maliyetini işaret etti. Yerel `-X importtime` ölçümünde tam CLI
yüklemesi yaklaşık 570 ms; doğrudan platform adaptörü yaklaşık 221 ms idi.
Bu ölçümler Linux çalıştırıcısındaki bütün dalgalanmanın nedenini ispatlamaz.

Yeni `interfaces.entrypoint` yalnız açık platform komutunu hafif girişe
yönlendirir. Kök argparse tanımı `interfaces.arguments` içinde paylaşılır;
platformun kendi parser ve yürütücüsü değişmez. Belirsiz veya diğer komutlar
tam CLI'ya gider. `--data-dir platform` gibi seçenek değeri komut sayılmaz.
Tam komut yeniden doğrulanır; açık veri alanı/firma kapsamı engelleri korunur.
Hem `python -m xti` hem kurulu `xti` aynı girişi kullanır. Eski CLI Python
girişi ve testlerin/adaptörlerin kullandığı bileşen adları korunur.

Engine bileşimi doğrulanmış işlemin gerektirdiği servisi kurar. Eski tüm
servisleri kurma çağrısı uyumluluk için mümkündür. Kuyruğun durum/kurtarma
okuması toplama CLI'sını yüklemez; profil hazırlama/çalıştırma gerçekten
ihtiyaç duyduğunda mevcut fabrikayı çağırır. Kaynak çalıştırıcı fabrikaları
da ihtiyaç anında yüklenir. İş kuralları, storage doğrulaması, kilitler,
tekrar/kurtarma ve firma sınırları atlanmaz.

Kabul yardımcısı ürünle aynı girişi çağırır. 36 okuma, iki şirket,
100/1.000 kayıt, iki gerçek SIGTERM sınırı ve bütün eşikler korunur.
Her komutun süre/CPU/bellek ve yüklenen modül sayısı ile iki bekleme
kapısının süresi sentetik JSON raporuna eklenir. Kaynak yanıtı, sır veya
komutun özel girdisi bu ölçüm listesine yazılmaz.

Yerel aynı senaryo ilk düzeltmeyle 40,845 → 28,288 saniye ölçüldü.
Son doğrulama ve Linux sonucu [kabul kaydında](../ACCEPTANCE_REVIEW.md),
yinelenen ilk başarısızlıklar [N-016'da](../../NOTES.md#n-016--linux-kabul-süresindeki-dalgalanma)
korunur. Süre sınırını artırmak veya başarılı tekrar ilk sonucu silmez.
