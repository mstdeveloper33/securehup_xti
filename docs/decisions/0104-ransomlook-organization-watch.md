# 0104 — RansomLook için yalnız kuruluş-adı izlemesi

- **Durum:** Kabul edildi
- **Tarih:** 30 Ekim 2026
- **Sürüm:** 0.106.0

## Bağlam

RansomLook kaydı yalnız grup, gönderi/kuruluş başlığı ve keşif zamanı taşır. Domain, ülke, sektör veya ilan durumu sağlamaz. ThreatCluster izleme tablolarını yeniden kullanmak bu iki farklı kanıt sözleşmesini karıştırırdı.

## Karar

RansomLook için ayrı izleme tanımı, eklemeli tanım olayları, çalışma başlıkları ve çalışma sonuçları tutulur. Yalnız `organization` türü desteklenir; eşleşme kaynak başlığında tam veya en az beş karakterli içerme biçimindedir. Domain türü yazma ve ağ başlamadan reddedilir.

Çalışma yalnız son başarılı yerel RansomLook snapshot'ını kullanır ve yazma anında snapshot zincirini yeniden doğrular. Bir tanımın ilk çalışması sessiz başlangıçtır. Sonraki yeni/değişen eşleşmeler kalıcı çalışmada insan inceleme adayı olarak sayılır. Yedi günlük pencereden çıkış çözüm, kapatma veya yanlış iddia kanıtı değildir ve dikkat adayı oluşturmaz.

Şema 44 açık `./xti migrate` ve doğrulanmış yedek sonrasında şema 45'e çıkar. Dört yeni tablo boş başlar; eski snapshot'lardan izleme sonucu üretilmez. Hata halinde DDL geri alınır ve geçiş öncesi yedek korunur.

## Sonuçlar

RansomLook kuruluş izlemesi ThreatCluster'dan bağımsız, ağsız ve denetlenebilirdir. Bu dar teslim ortak gelen kutusu, toplu yenileme/monitor veya iki kaynak arasında otomatik olay birleştirme yapmaz. Sonraki adım, iki kaynağın özgün kayıtlarını koruyan açıklanabilir kaynaklar arası karşılaştırmadır.
