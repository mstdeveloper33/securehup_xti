# 0110 — Tam sosyal profil durumuna bağlı insan kararları

**Tarih:** 31 Ekim 2026  
**Durum:** Kabul edildi  
**Sürüm:** 0.112.0

## Bağlam

0109 numaralı karar seçili sosyal platformlarda sessiz başlangıçlı kalıcı fark
geçmişini ekledi. Bulunan profil yalnız aynı kullanıcı adına açık bir işaretti;
bilinen resmî hesap, olası taklit ve belirsiz sonuç birbirinden ayrılamıyordu.
Yalnız platform adına bağlanan bir karar da profil adresi değiştiğinde yanlış
hesaba taşınabilirdi.

## Karar

Kullanıcı, güncel izleme tanımının son başarılı çalışmasında gerçekten bulunan
platforma `known_official`, `possible_impersonation` veya `uncertain` kararı ve
zorunlu gerekçe verir. Karar kimliği izleme kimliği, tanım özeti, platform ve tam
profil durum özetinden türetilir. Profil adresi değişirse yeni aday oluşur ve
eski karar taşınmaz.

İlk kararda çalışma, kullanıcı adı, platform, tam HTTPS profil adresi, gözlem
zamanı ve bütünlük özetleri dondurulur. Aynı karar ve gerekçe idempotenttir;
değişiklik eski olayı silmeden önceki olay kimliğine bağlı yeni olay ekler. Son
kaynak denemesi başarısızsa son başarılı çalışma kullanılabilir. Son başarılı
çalışmada raporlanmayan platforma veya henüz başarıyla çalışmamış yeni tanıma
karar verilemez.

Şema 48 tek eklemeli karar olayı tablosu ekler. Şema 47 geçişi önce doğrulanmış
yedek alır, tabloyu boş oluşturur ve hata halinde geri alınır. Eski izleme
sonuçlarından karar üretilmez.

## Sonuçlar

- Bilinen resmî profil ile olası taklit insan kararıyla ayrılabilir.
- Karar değişen profil adresine veya yeni izleme tanımına sessizce taşınmaz.
- Kayıtlı çalışma görünümü tam kanıta ait son kullanıcı kararını gösterebilir.
- Karar sahipliği teknik olarak doğrulamaz; otomatik alarm, ortak kutu veya dış
  aksiyon üretmez.
- Sıradaki katman yalnız açık `possible_impersonation` kararının ortak yerel
  kutuya kaynaklı ve tekilleştirilmiş bağlanmasını ayrı kararla ele alacaktır.

## Canlı kabul

31 Ekim 2026'da geçici şema 47 GitHub `octocat` izleme veritabanı doğrulanmış
yedekle şema 48'e taşındı. Kayıtlı tam `https://github.com/octocat` profili
`known_official` olarak işaretlendi ve önceki değişmeyen çalışma görünümünde aynı
aday kimliğiyle gösterildi. Kullanıcının ana veritabanı değiştirilmedi.
