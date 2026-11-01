# 0105 — Ransomware kaynakları açıklanabilir ve salt-okunur karşılaştırılacak

- **Durum:** Kabul edildi
- **Tarih:** 30 Ekim 2026
- **Sürüm:** 0.107.0

## Bağlam

ThreatCluster ve RansomLook ayrı şema, kaynak kimliği ve pencere süresiyle kalıcı snapshot geçmişi tutar. İki kaynakta benzer kuruluş başlıkları bulunması araştırmaya yardımcı olabilir; ancak yalnız isim benzerliği aynı olay, gerçekleşmiş ihlal veya bağımsız teyit kanıtı değildir. RansomLook domain, ülke, sektör ve ilan durumu sağlamadığı için bu alanlarla ortak karşılaştırma yapılamaz.

## Karar

`ransomware source-compare`, iki kaynağın yalnız son başarılı ve tamamen denetlenmiş yerel snapshot'ını kullanır. Ağ isteği göndermez ve veritabanına yazmaz. Kuruluş adı NFKC, harf duyarsızlaştırma ve boşluk birleştirme sonrasında tam aynı olmalıdır. Buna ek olarak normalleştirilmiş grup adı veya kanonik kaynak keşif zamanı da aynı olmalıdır. Yaklaşık metin benzerliği, yalnız kuruluş, yalnız grup/zaman ve tek kaynakta bulunan alanlar kullanılmaz.

Her sonuç iki özgün claim'i, iki kaynak çalışma bağlamını, aynı ve farklı ortak alanları, karşılaştırma temelini ve kaynak claim kimliklerinden türetilen kararlı karşılaştırma kimliğini taşır. Sıra önce üç ortak alanı, sonra kuruluş+grubu, ardından kuruluş+zamanı gösterir. Görünüm sınırı tam toplamı değiştirmez. İşlem 100.000 aday başvurusu ve 50.000 sonuçla sınırlıdır; aşım sessiz kırpma yerine güvenli hata üretir.

Şema 45 değişmez ve migration gerekmez.

## Sonuçlar

Kullanıcı iki kaynağın neden benzer görüldüğünü özgün kayıtları yan yana görerek değerlendirebilir. Sonuç kayıtları birleştirmez, izleme geçmişini değiştirmez, alarm veya ortak gelen kutusu girdisi üretmez ve aynı olay ya da gerçekleşmiş ihlal hükmü değildir. Sonraki adım, bu salt-okunur karşılaştırmadan ayrı yaşam döngüsü ve insan kararı olan inceleme adaylarını tasarlamaktır.
