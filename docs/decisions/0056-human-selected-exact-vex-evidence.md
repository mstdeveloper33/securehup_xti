# 0056 — İnsan seçimiyle kesin RPM/VEX kanıtı

**Durum:** Kabul edildi · **Tarih:** 29 Ekim 2026

## Bağlam

0.55 etkin bir kesin Red Hat RPM kaydını doğrudan CSAF VEX ürün ilişkisiyle karşılaştırabiliyordu, fakat sonuç salt okunurdu. Var olan genel maruziyet destek kanıtı yalnız tür, bağlantı ve açıklama tutar; kesin RPM kimliğini, seçilen VEX ürün bağını ve alınan belgenin SHA-256 özetini kaybeder. Bu alanları serbest açıklama metnine gömmek doğrulanabilirliği ve sonraki kaynak sürümlerini karşılaştırmayı zorlaştırır.

## Karar

- Kalıcı seçim ayrı `VendorPackageEvidenceRepository` portu ve şema 24 tablolarında yapılandırılmış olarak tutulur.
- Kullanıcı maruziyet incelemesini, kesin RPM kaydını, `vendor-match` çıktısındaki tam VEX ürün kimliğini ve açıklamasını açıkça verir.
- CVE kullanıcıdan tekrar alınmaz; maruziyet incelemesinden gelir. İnceleme ile paket aynı varlığa ait olmalıdır.
- Güncel Red Hat VEX belgesi yeniden alınır. Seçim yalnız `exact_vendor_statement` durumundaki tek bir güncel eşleşmeye tam kimlikle karşılık gelirse yazılır. Eşleşmeme veya çelişki güvenli/etkilenmiyor hükmüne çevrilmez.
- Kaynak adresi ve SHA-256 özeti, belge sürümü/yayım zamanı, Red Hat durumu, eşleşme türü, bileşen PURL'si, bağlam ürünü/CPE'si ve paket kanıt zamanı birlikte saklanır.
- Yazma transaction'ı paketin hâlâ etkin ve seçim sırasında görülen `updated_at` değerinde olduğunu yeniden doğrular. Böylece ağ isteği sırasında değişen yerel envanter eski seçimle kaydedilmez.
- Aynı inceleme+paket+kaynak özeti+VEX ürün kimliği+durum+paket kanıt zamanı tek kimliktir. Açıklama güncellemesi, iptal ve yeniden etkinleştirme eklemeli olay geçmişinde tutulur. Yeni kaynak özeti veya yeniden doğrulanmış paket anlık görüntüsü ayrı kanıt olur.
- Maruziyet kuyruğu etkin kaydı `exact_vendor_package` türü olarak sayar. Kanıt, insan kararını, yeniden inceleme durumunu veya öncelik bandını otomatik değiştirmez.
- Şema 23→24 geçişi önce doğrulanmış, üzerine yazılmayan yedek alır; tablolar boş başlar ve geçmiş salt-okunur eşleşmelerden kanıt türetilmez.

## Sonuçlar

Seçilen üretici beyanı daha sonra kaynağı ve tam paket bağlamıyla denetlenebilir. Genel bağlantı kanıtı ile kesin paket hükmü birbirine karışmaz. Buna karşılık kullanıcı önce genel ürün+CVE incelemesini ve kesin RPM kaydını oluşturmalıdır; üretici belgesindeki değişimi kendiliğinden izleme bu karara dahil değildir.
