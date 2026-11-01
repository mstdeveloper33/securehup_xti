# 0106 — Kaynaklar arası ransomware karşılaştırması ayrı insan kararı taşıyacak

- **Durum:** Kabul edildi
- **Tarih:** 30 Ekim 2026
- **Sürüm:** 0.108.0

## Bağlam

`ransomware source-compare`, ThreatCluster ve RansomLook'un iki özgün kaydını yalnız güçlü ortak alanlarla yan yana gösterir. Bu karşılaştırma araştırma adayıdır; aynı olay, bağımsız teyit veya gerçekleşmiş ihlal anlamına gelmez. Analistin değerlendirmesini yalnız terminal dışında tutmak gerekçeyi, değişiklik geçmişini ve kullanılan kaynak kanıtını kaybettirirdi. Kaynak snapshot'ları zamanla değiştiği için eski kararın dayanağını güncel görünümle sessizce değiştirmek de yanlış olurdu.

## Karar

`ransomware source-review`, yalnız son başarılı iki yerel snapshot'ta yeniden bulunabilen kararlı karşılaştırma kimliği için `possible_same`, `different` veya `uncertain` kararı ve 2–500 görünür karakterlik gerekçe kabul eder. Komut ağ kullanmaz. Yazma başlamadan karar, gerekçe, UTC saat ve güncel karşılaştırma doğrulanır; transaction içinde iki kaynak geçmişi ve snapshot üyeliği yeniden denetlenir.

İlk kararda iki kaynak çalışma kimliği, iki özgün claim, karşılaştırma temeli ve aynı/farklı alanlar kanonik JSON ve SHA-256 ile dondurulur. Yeni kaynak snapshot'ları bu kanıtı değiştirmez. Karar veya gerekçe değişirse önceki olaya bağlanan yeni satır eklenir; aynı karar+gerekçe yeni olay üretmez. Okumada kaynak geçmişleri, kanıt özeti, olay bağı ve zaman sırası baştan denetlenir; bozuklukta kısmi sonuç veya otomatik onarım yapılmaz.

`source-review-show` dondurulmuş kanıtı ve sınırlı karar geçmişini ağsız gösterir. `source-compare` yalnız varsa güncel karar durumuyla süslenir ve salt okunur kalır.

Şema 45→46 geçişi önce doğrulanmış kurtarma yedeği alır, ardından boş `ransomware_source_review_events` tablosunu tek transaction içinde ekler. Eski karşılaştırmalardan karar türetilmez.

## Sonuçlar

Analist bir karşılaştırmayı neden nasıl değerlendirdiğini kaybetmeden izleyebilir ve kararını geri alınabilir biçimde değiştirebilir. İnsan kararı iki kaynak claim'ini birleştirmez, kaynak geçmişini yeniden yazmaz, alarm veya ortak gelen kutusu kaydı üretmez ve doğrulanmış ihlal sayılmaz. Otomatik olay birleştirme ile dış bildirim ayrı ve gelecekte açık kabul koşulları gerektiren işlerdir.
