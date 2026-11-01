# 0122 — İnsan yönetimli yerel vaka yaşam döngüsü

**Durum:** Kabul edildi  
**Tarih:** 31 Ekim 2026

## Bağlam

Domain/marka bulguları, insan kararlı sosyal profiller, iki ayrı ransomware
kaynağı ve tedarikçi inceleme kartları ayrı kimlik ve sınırlara sahiptir. Tek
kullanıcı bunları ortak bir inceleme altında takip etmek, görev ve not eklemek,
sonucu gerekçeyle kapatmak ve daha sonra neden yeniden açıldığını görebilmek
istiyor. Kaynak kayıtlarını birleştirmek veya vaka açılmasını tehdit hükmüne
dönüştürmek kanıtın anlamını bozar.

## Karar

- Vaka; başlık, özet, öncelik, durum, sonuç ve zamanlarla ayrı güncel kayıt olarak tutulur.
- `open`, `investigating`, `monitoring`, `resolved` ve `closed` durumları kullanılır. Çözme/kapatma sonuç ister; açık görev varken kapatma reddedilir.
- Notlar, görev değişiklikleri, kanıt bağları ve vaka yaşam döngüsü tek sıralı, eklemeli aktivite akışına yazılır.
- Kanıt kaynağı yerinde kalır. Vaka bağlantısı kaynağın bütünlüğü denetlenmiş, boyut sınırlı kanonik JSON anlık görüntüsünü ve SHA-256 özetini saklar.
- Aynı vaka+kaynak türü+kaynak kimliği tekildir. Değişmeyen tekrar satır üretmez; değişen kaynak anlık görüntüyü yeniler; çıkarma bağı pasif yapar ve geçmişi silmez.
- Desteklenen ilk kaynaklar domain/marka bulgusu, insan kararlı sosyal profil, ThreatCluster ve RansomLook iddiaları ile tedarikçi inceleme kartıdır. İki ransomware kaynağı ayrı türler olarak korunur.
- Liste, ayrıntı ve rapor ağsızdır. Vaka hiçbir kaynak iddiasını doğrulanmış saldırı/ihlal, sahiplik veya kullanıcı etkisi saymaz.
- Şema 54 dört boş tablo ekler. Şema 53 geçişi önce doğrulanmış yedek alır, tek transaction içinde ilerler ve eski kayıtlardan vaka üretmez.

## Sonuçlar

Kişisel terminal kullanımında kanıt, görev, not, kapanış ve yeniden açma tek
denetlenebilir yerde izlenebilir. Kaynakların özgün anlamı ve kimliği korunur.
Atama, rol, müşteri ayrımı, SLA, web paneli ve ekip raporlaması bu kararla
uygulanmış sayılmaz; takım ürününe geçildiğinde ayrı yetki ve denetim kararı
gerektirir.
