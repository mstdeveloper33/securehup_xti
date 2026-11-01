# 0101 — Ransomware kimlik adayı insan kararları

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Karar

`ransomware watch-identity-review IZLEME_KIMLIGI ADAY_KIMLIGI`, yalnız denetlenmiş yerel snapshot geçmişinde yeniden üretilebilen kimlik değişimi adayı için zorunlu gerekçeli insan kararı kaydeder. Kararlar `possible_same` (aynı olay olabilir), `different` (farklı olay) ve `uncertain` (belirsiz) değerlerinden biridir. `ransomware watch-identity-review-show ADAY_KIMLIGI` kayıtlı karar zincirini ağsız gösterir.

Aday kimliği izleme kimliği + eski claim kimliği + yeni claim kimliği + geçiş kaynak çalışmasından kararlı UUID olarak üretilir. Yazmadan önce aday bütün yerel geçmişten yeniden bulunur; kullanıcı keyfî iki kaydı ilişkilendiremez. Adayın eski/yeni güvenli claim alanları, kaynak geçişi, izleme eşleşmeleri, ortak kanıtları ve değişen kimlik alanları kanonik JSON ve SHA-256 ile her karar olayına bağlanır.

Karar olayları eklemelidir. İlk olayın önceki olay kimliği yoktur; sonraki her olay bir önceki olaya bağlıdır. Zaman geriye gidemez. Aynı karar ve aynı gerekçe tekrar verilirse yeni olay yazılmaz. Karar ya da gerekçe değişirse eski olay korunur ve yenisi eklenir. Aday listesi son kararı gösterir; ayrıntı görünümü sınırlandırılsa bile toplam olay sayısı tam geçmişten hesaplanır.

Şema 43 tek `ransomware_identity_review_events` tablosunu ekler. Şema 42 ve öncesi açık `./xti migrate` öncesi doğrulanmış yedek gerektirir. Yeni tablo boş başlar; eski adaylardan veya benzer kayıtlardan karar uydurulmaz. Migration, tablo veya doğrulama hatasında geri alınır ve geçiş öncesi yedek korunur.

## Güven ve sınırlar

Karar analist yorumudur. `possible_same` kaynak claim kimliklerini birleştirmez, geçmiş zaman çizelgesini yeniden yazmaz, bildirim üretmez ve doğrulanmış ihlal/olay özdeşliği hükmü değildir. `different` gelecekteki benzer kaydı otomatik engellemez. `uncertain` ek veri bekleyen açık değerlendirmedir. Yerel SQLite bütünlük ve zincir denetimi kasıtsız bozulmayı görünür kılar; kriptografik imzalı değiştirilemez dış denetim günlüğü değildir.
