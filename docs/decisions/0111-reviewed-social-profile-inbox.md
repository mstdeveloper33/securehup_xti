# 0111 — İnsan onaylı sosyal profil bildirimleri

**Tarih:** 31 Ekim 2026  
**Durum:** Kabul edildi  
**Sürüm:** 0.113.0

## Bağlam

0110 numaralı karar, bulunan sosyal profili tam profil durumuna bağlı olarak
resmî/meşru, olası taklit veya belirsiz işaretlemeyi ekledi. Ancak olası taklit
kararı ortak çalışma kutusunda görünmüyor; kullanıcı karar geçmişini ayrıca
aramak zorunda kalıyordu. Her karar değişikliğinde yeni alarm üretmek ise aynı
tam profil için gürültü ve çelişkili geçmiş oluşturabilirdi.

## Karar

Yalnız yeni bir `possible_impersonation` karar olayı ortak yerel kutu bildirimi
oluşturur. Karar olayı ve bildirim aynı SQLite transaction'ında yazılır;
bildirim yazılamazsa karar da geri alınır. `known_official` ve `uncertain`
kararları bildirim üretmez.

Bildirim tam profil aday kimliğinde tekildir. Aynı kararın tekrarı, gerekçe
güncellemesi veya kararın değişip yeniden olası taklide dönmesi aynı aday için
yeni bildirim üretmez. Profil adresi ya da izleme tanımı değişirse farklı aday
kimliği oluştuğundan yeni kanıt ayrı bildirilebilir.

Bildirim onu oluşturan kesin karar olayına bağlıdır. Sonraki karar değişikliği
tetikleyen karar ve gerekçeyi silmez veya yeniden yazmaz; kutu ayrıntısı tarihsel
tetikleyicinin yanında güncel kullanıcı kararını da gösterir. Okundu durumu
karar geçmişinden bağımsızdır.

Şema 49 tekil aday ve karar olayı bağlantısı taşıyan ayrı bildirim tablosu ekler.
Şema 48 geçişi önce doğrulanmış yedek alır, tabloyu boş oluşturur ve hata halinde
geri alınır. Önceki olası taklit kararlarından geriye dönük bildirim üretilmez.

## Sonuçlar

- İnsan tarafından olası taklit işaretlenen profil ortak iş listesinde görünür.
- Aynı profil karar değişiklikleriyle alarm çoğaltmaz.
- Profil adresi değişimi eski karardan ve bildirimden ayrı kalır.
- Bildirim mevcut açık seçimli manuel webhook akışına verilebilir; otomatik
  teslim, e-posta/SMS veya takedown başlatılmaz.
- Bu kayıt platform doğrulaması, hukuki ihlal veya teknik sahiplik hükmü değildir.

## Canlı kabul

31 Ekim 2026'da geçici GitHub `octocat` izleme veritabanı doğrulanmış yedekle
şema 49'a taşındı. Tam profil kararı `possible_impersonation` olarak güncellendi;
tek bildirim ortak kutuda izleme adı, platform, profil adresi, tetikleyen gerekçe
ve güncel kararla gösterildi. Kullanıcının ana veritabanı değiştirilmedi.
