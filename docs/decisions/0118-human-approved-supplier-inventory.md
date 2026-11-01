# 0118 — İnsan onaylı yerel tedarikçi envanteri

**Durum:** Kabul edildi · **Tarih:** 31 Ekim 2026 · **Sürüm:** 0.120.0

## Karar

İlk tedarikçi dilimi yalnız kullanıcının açıkça tanımladığı kuruluş ilişkisini
yerel olarak saklar. Kuruluş adı, ana domain, ilişki türü, iş önemi ve gerekçe
zorunludur. Ana domain kuruluş kaydının değiştirilemez kimlik kanıtıdır; aynı
isim farklı ana domainlerde ayrı kayıtlar olarak kalır.

Ekleme, güncelleme, pasife alma ve yeniden etkinleştirme tam alan anlık
görüntüsüyle eklemeli olay geçmişine yazılır. Etkin aynı domain farklı bilgiyle
yeniden eklenirse kayıt sessizce değiştirilmez; açık güncelleme komutu gerekir.
Pasif aynı domain yeniden eklenebilir ve önceki kimlik/geçmiş korunur.

Bu dilimde ağ kaynağı, dış bağımlılıktan aday önerisi, otomatik kuruluş
birleştirme, tedarikçi olayı, risk puanı, alarm veya dış aksiyon yoktur.
Envanter beyanı kuruluşun güvenli ya da riskli olduğuna kanıt sayılmaz.

## Gerekçe

Tedarikçi olayını kullanıcı etkisine bağlamadan önce ilişkinin kim tarafından,
hangi gerekçeyle ve hangi iş önemiyle kabul edildiği bilinmelidir. Domaini
değiştirilebilir bir alan yapmak iki farklı kuruluşun geçmişini yanlışlıkla
birleştirebilir. İsim tekilliği uygulamak ise aynı isimli meşru ayrı kuruluşları
birleştirir. Bu nedenle tekillik ana domaindedir; isim yalnız görünüm ve arama
anahtarıdır.

## Veri ve geri alma

Şema 52 `suppliers` ve `supplier_events` tablolarını ekler. Şema 51 geçişi önce
doğrulanmış, üzerine yazılmayan yedek üretir; tablolar tek transaction içinde
boş oluşturulur ve hata halinde canlı veritabanı şema 51 olarak kalır. Eski
varlık, CTI veya ağ kayıtlarından tedarikçi ilişkisi uydurulmaz.

## Sonraki sınır

Sonraki teslim, mevcut dış bağımlılık kanıtından yalnız “aday” üretmeli ve bu
adayı tedarikçi ilişkisine dönüştürmek için açık kullanıcı onayı istemelidir.
Kuruluş birleştirme/ayırma gerekçeli, denetlenebilir ve geri alınabilir olmalıdır.
