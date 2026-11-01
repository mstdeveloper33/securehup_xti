# 0084 — Kayıtlı CTI arama değişiklik bildirimleri

**Durum:** Kabul edildi · **Tarih:** 30 Ekim 2026 · **Sürüm:** 0.84.0

## Bağlam

Kayıtlı arama çalışmaları değişimi kanıtlıyordu ancak kullanıcı her çalışma ayrıntısını tek tek açmadan anlamlı farkı göremiyordu. İlk tam sonuç doğal olarak çok sayıda `added` öğe içerir; bunu alarm saymak başlangıç gürültüsü yaratır. Çalışma kaydedilip bildirim ayrı yazılırsa iki kayıttan biri eksik kalabilir.

## Karar

- İlk çalışma ve değişen sorgu tanımının ilk çalışması sessiz başlangıçtır.
- Doğrudan önceki aynı tanım varken `added`, `updated` veya `removed` toplamı sıfırdan büyükse çalışma başına tek yerel bildirim oluşturulur. Yalnız `unchanged` içeren çalışma bildirim üretmez.
- Bildirim `run_id` ve `saved_search_id` yabancı anahtarlarıyla değişmez çalışma kanıtına bağlıdır. Çalışma, bütün öğeler ve bildirim aynı transaction'da yazılır.
- Bildirim diğer yerel bildirim aileleriyle tek artan sıra paylaşır; birleşik `inbox list/show/read/unread` akışında görünür.
- Okundu bilgisi yalnız bildirim durumudur; CTI tanımını, kaynak iddiasını, çalışmayı veya tehdit değerlendirmesini değiştirmez.
- Otomatik zamanlama, e-posta/SMS/webhook veya tehdit hükmü bu dilimin parçası değildir.

## Şema ve kurtarma

Şema 37, `cti_saved_search_notifications` tablosunu ve okundu+sıra indeksini ekler. Şema 36→37 geçişi doğrulanmış yedekten sonra tek transaction'da yapılır. Hata geri alınır; eski çalışmalardan bildirim uydurulmaz.

## Sonuçlar

Kullanıcı anlamlı CTI arama değişimini mevcut yerel kutuda görür ve değişmez çalışma ayrıntısına gidebilir. Bildirim yazma hatası çalışma kanıtını yarım bırakmaz. Dış kanallar daha sonra aynı port ve kanıt bağı üzerinden, açık kullanıcı yapılandırmasıyla eklenebilir.
