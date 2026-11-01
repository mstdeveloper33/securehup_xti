# 0082 — Birleşik yerel CTI araması

**Durum:** Kabul edildi · **Tarih:** 30 Ekim 2026 · **Sürüm:** 0.82.0

## Bağlam

IOC kataloğu ve CTI bilgi grafiği ayrı liste/ayrıntı komutlarıyla araştırılabiliyordu. Kullanıcının bir aktör adı, alternatif ad veya IOC parçasının hangi kayıt ailesinde olduğunu önceden bilmesi gerekiyordu. Kaydedilmiş sorgu ve aboneliklerden önce, sonucu tekrar üretilebilir tek bir salt-okunur arama davranışı gerekliydi.

## Karar

- `cti search`, NFKC ile normalize edilmiş 2–200 karakterlik ifadeyi CTI ana adı, kaynak iddialarındaki alternatif ad ve IOC kanonik değeri üzerinde arar.
- Eşleşme dereceleri tam, başlangıç ve içerme olarak ayrı tutulur; sıralama derece, kayıt ailesi, tür, kanonik görünüm ve kimlikle kararlıdır.
- Varsayılan kapsam en az bir etkin CTI kaynak iddiası veya sorgu anında geçerli IOC kaynak iddiası olan kayıtlardır. `--all`, geri çekilmiş ve süresi dolmuş geçmişi de arar; güncel kaynak sayısı yine ayrı gösterilir.
- `--kind`, varlık türü, IOC türü ve sonuç limiti uygulama katmanında doğrulanır. Çelişen filtreler veritabanına erişmeden reddedilir.
- Sonuç limiti yalnız gösterimi keser. En fazla 50.000 CTI varlığı ve 50.000 IOC, bağlı kaynak iddiaları ve olay geçmişleriyle aynı salt-okunur SQLite anında doğrulanır. İlk 10.000 sınırı 0.92.0'da [çok kaynaklı IOC kararıyla](0090-bounded-multi-source-ioc-feeds.md) yükseltilmiştir. Eşleşmeyen bir kaydın gizli geçmişi bozuksa kısmi sonuç verilmez.
- Arama internet, yazma, otomatik atıf, profil birleştirme veya tehdit hükmü üretmez.

## Veri ve ölçek sonucu

Yeni tablo veya migration yoktur; şema 35 korunur. B0 kişisel kullanımda doğruluk ve denetlenebilirlik için sınırlı tam tarama seçilmiştir. Bu tasarım büyük müşteri ölçeğinde gecikme iddiası taşımaz; ölçülen ihtiyaç oluştuğunda aynı port arkasına sürümlü bir arama indeksi adaptörü eklenebilir.

## Açık işler

Arama tanımını kaydetme, çalıştırma anını ve veri kapsamını mühürleme, önceki çalışmaya göre yeni/çıkan sonuçları ayırma, abonelik bildirimi ve gelişmiş ilişki-grafiği sorguları sonraki CTI-03 dilimleridir.
