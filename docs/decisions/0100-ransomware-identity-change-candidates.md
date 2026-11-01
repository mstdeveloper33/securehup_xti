# 0100 — Ransomware kimlik değişimi inceleme adayları

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Karar

`ransomware watch-identity-candidates IZLEME_KIMLIGI`, denetlenmiş yerel ransomware snapshot geçmişinde kaynak kimliği değişmiş olabilecek yakın kayıt geçişlerini salt-okunur insan inceleme adayı olarak gösterir. Komut internete bağlanmaz, alarm veya karar üretmez, kayıtları birleştirmez ve veritabanını değiştirmez. Geri çekilmiş izleme tanımı da araştırma için kullanılabilir.

Kaynak kimliği grup + kuruluş adı + kaynak keşif zamanıdır. Bir aday yalnız şu koşulların tamamında oluşur:

- eski kimlik kaynak penceresinden çıkmıştır;
- yeni ve farklı kimlik aynı veya hemen sonraki başarılı snapshot'ta eklenmiştir;
- eski veya yeni kayıttan en az biri seçilen güncel izleme tanımıyla eşleşir;
- grup, kuruluş adı, kaynak keşif zamanı ve normalleştirilmiş web alanından en az iki tanesi aynıdır.

Karşılaştırma tam ve açıklanabilirdir; bulanık metin skoru, LLM veya gizli güven puanı kullanılmaz. Birden fazla eski kayıt aynı yeni kayda uyarsa yalnız en yakın başarılı snapshot'ta çıkan kimlikler değerlendirilir. Böylece daha eski zincirlerin aynı yeni kayıt için gürültülü aday üretmesi sınırlanır.

Başarısız kaynak çalışması boş snapshot değildir ve başarılı snapshot yakınlığını bozmaz. Eşzamanlı yaşayan iki farklı kimlik, iki başarılı snapshot'tan daha uzak geçiş, yalnız tek ortak alan ve aynı kesin kimliğin yeniden görünmesi aday değildir. Aynı kesin kimliğin geri gelişi zaman çizelgesindeki `reappeared` olayı olarak kalır.

Sonuç eski/yeni kayıtları, izlemeyle ayrı eşleşme durumlarını, ortak kanıtları, değişen kimlik alanlarını ve geçiş kaynak çalışmasını taşır. Görünüm sınırı yalnız dönen son adayları daraltır; toplam aday sayısı bütün denetlenmiş yerel geçmişten hesaplanır.

## Sınırlar

Aday “aynı gerçek olay olabilir” anlamına gelir; aynı olay, ihlal, tekrar yayın veya kaynak düzeltmesi kararı değildir. Ortak web alanı teknik sahiplik kanıtı değildir. Kaynak iki alandan fazlasını aynı anda değiştirirse gerçek tekrar bulunamayabilir. Bu dilim karar kaydetmez, zaman çizelgesi kimliklerini birleştirmez ve geçmiş olayları yeniden yazmaz. Kalıcı insan kararı ayrı, açık ve denetlenebilir bir sonraki teslimdir.
