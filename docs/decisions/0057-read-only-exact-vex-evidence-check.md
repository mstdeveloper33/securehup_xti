# 0057 — Kesin VEX kanıtını salt okunur yeniden değerlendirme

**Durum:** Kabul edildi · **Tarih:** 29 Ekim 2026

## Bağlam

0.56 seçilen kesin RPM/VEX ilişkisini kaynak özeti ve paket anlık görüntüsüyle saklar. Zaman içinde Red Hat belgesi, üretici durumu veya yerel RPM kanıtı değişebilir. Eski kanıtı sessizce güncellemek denetim izini bozar; her kontrolde yeni kanıt yazmak ise insan seçimini otomatikleştirir.

## Karar

- `vendor-evidence-check` tek kayıtlı kanıtı ve bağlı kesin RPM kaydını salt okunur alır.
- RPM etkisizse dış kaynağa bağlanılmaz ve durum açıkça `package_inactive` olur.
- Etkin pakette güncel Red Hat VEX aynı kesin eşleştirme servisiyle alınır.
- Kaynak özeti, paket kanıt zamanı, seçilen tam VEX ürün kimliği, üretici durumu ve ilişki alanları ayrı karşılaştırılır.
- Tam güncel, kaynak değişmiş/beyan aynı, paket yeniden doğrulanmış/beyan aynı, beyan değişmiş, seçilen bağ kaybolmuş ve çelişen bağlam durumları birbirine indirgenmez.
- Kontrol yeni kanıt, olay, insan kararı, yeniden inceleme veya öncelik yazmaz. Kullanıcı gerekirse güncel bağı 0.56 seçim komutuyla ayrıca kanıta dönüştürür.
- Yeni tablo yoktur; şema 24 değişmez.

## Sonuçlar

Kullanıcı eski kanıt ile bugünkü üretici kaynağı arasındaki farkı görebilir ve denetim geçmişi korunur. Periyodik zamanlama, toplu kontrol ve değişiklik bildirimi bu dar dilimin dışındadır.
