# 0120 — Kaynak bağlı tedarikçi iddia görünümü

**Durum:** Kabul edildi · **Tarih:** 31 Ekim 2026 · **Sürüm:** 0.122.0

## Karar

İlk tedarikçi tehdit olayı dilimi yeni bir dış kaynak veya otomatik hüküm
üretmez. Etkin, insan onaylı tedarikçi kayıtları yalnız ThreatCluster ve
RansomLook'un son başarılı yerel snapshot'larıyla salt okunur eşleştirilir.

ThreatCluster kaydında tedarikçinin tam normalleştirilmiş kuruluş adı veya
kaynağın sağladığı ilk-taraf web hostunun tedarikçi ana domainine kesin/alt alan
adı bağı kullanılabilir. RansomLook domain sağlamadığı için yalnız tam kuruluş
adı kullanılabilir. Yaklaşık ad benzerliği, CNAME, ortak altyapı veya otomatik
kuruluş birleştirmesi bu karara dahil değildir.

Her görünür aday tedarikçi, kaynak, kaynak snapshot'ı ve kaynak kayıt kimliğine
bağlı kararlı bir görünüm kimliği taşır. Aynı isimli ayrı tedarikçiler tek
kuruluşa indirgenmez; isim eşleşmesinin kaç etkin kayda uyduğu gösterilir.

## Kaynak kapsamı

Her kaynak için hiç toplanmamış, kullanılabilir, son denemesi başarısız olduğu
için önceki başarılı snapshot'ı kullanan ve başarılı snapshot'ı olmayan hata
durumları ayrıdır. Böylece sıfır eşleşme kaynak kesintisi veya veri yokluğuyla
karıştırılmaz. İki kaynağın iddiaları ayrı kalır ve birbirini doğrulamış sayılmaz.

## Veri ve geri alma

Bu görünüm mevcut şema 53 tedarikçi ve ransomware snapshot geçmişlerini yalnız
okur. Yeni tablo, migration, ağ isteği, yazma, bildirim veya dış aksiyon yoktur.
Özellik geri alındığında kalıcı veri dönüşümü gerekmez.

## Sınır

Ransomware grup kaydı kamuya açık bir iddiadır; doğrulanmış ihlal, tedarikçinin
etkilendiği, kullanıcının etkilendiği veya risk puanı değildir. Sonraki dilim
kaynak kapsamı, tedarikçi iş önemi ve eksik kanıtı ayrı gösteren açıklanabilir
risk kartıdır; otomatik engelleme veya müdahale üretmez.
