# 0015 — Kullanıcı inceleme geri bildirimini toplu ve etiketsiz özetleme

**Tarih:** 29 Ekim 2026 · **Durum:** 0.15.0'da uygulandı.

## Sorun

Sentetik değerlendirme kuralların bilinen örneklerdeki davranışını gösterir, fakat kullanıcının günlük inceleme yükünü göstermez. Mevcut karar geçmişinde `suspicious`, `dismissed` ve `uncertain` değerleri vardır. Bunları doğrudan doğru pozitif/yanlış pozitif etiketi saymak hatalıdır: şüphe kararı doğrulanmış phishing, kapatma kararı bağımsız olarak kanıtlanmış meşruiyet değildir.

Kural iyileştirmesi için yine de kaç adayın incelendiğini, kararların hangi kural sürümünde yoğunlaştığını ve kaç bulgunun yeniden değerlendirildiğini görmek gerekir. Bu görünüm inceleme nedenlerini veya aday adresleri gereksiz yere dışa taşımamalıdır.

## Karar

`feedback` komutu, mevcut bulguların son durumunu ve eklemeli inceleme geçmişini tek salt okunur SQLite anlık görüntüsünde toplar. Şunları raporlar:

- toplam, incelenen ve bekleyen aday sayısı ile inceleme kapsamı;
- son `suspicious`, `dismissed` ve `uncertain` karar sayıları;
- toplam karar olayı ve birden çok kez incelenen bulgu sayısı;
- aynı sayıların tam bulgu kural sürümüne göre dağılımı.

İnsan ve JSON çıktısı yalnız bu toplu sayıları ve kural sürümünü içerir. Domain, bulgu kimliği, gerekçe, kaynak bağlantısı ve ham kanıt bu rapora alınmaz. Komut ağ isteği, kayıt oluşturma, migration, onarım, okundu değişikliği veya karar yazımı yapmaz.

Bulgunun güncel durumu karar geçmişindeki son olayla uyuşmuyorsa ya da bilinmeyen durum, bozuk kural kimliği, çelişkili toplam veya 100'den fazla kural grubu görülürse rapor güvenli biçimde durur. Sessiz düzeltme yapılmaz.

## Yorum sınırı

İnceleme kapsamı bir iş akışı ölçüsüdür, model kalitesi değildir. Kullanıcı kararlarından precision, recall, yanlış alarm veya kaçırma oranı hesaplanmaz. Bu oranlar ancak etiket kaynağı, doğrulama yöntemi, tarih ve kapsamı ayrıca tanımlanmış bir veri kümesinde üretilebilir. `feedback`, hangi kural gruplarının daha fazla kullanıcı dikkatine ihtiyaç duyduğunu araştırmak için başlangıç sinyalidir.

## Kalıcılık ve sonuçlar

- Şema 8 değişmez; 0.12.0–0.14.0 kayıtları migration olmadan okunur.
- Önceki karar ve bulgu kimlikleri değiştirilmez.
- JSON çıktı açık kullanıcı işlemiyle alınabilir ve veri minimizasyonu uygular.
- İlk dilim zaman aralığı, varlık filtresi, dış gönderim veya otomatik kural değiştirme içermez.
- Sonraki kural değişikliği yalnız bu toplu sayılara dayanmaz; örnekler ayrı ve kaynaklı biçimde incelenir.
