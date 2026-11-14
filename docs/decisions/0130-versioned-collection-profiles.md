# 0130 — Sürümlü toplama profilleri

**Durum:** Kabul edildi · **Tarih:** 14 Kasım 2026

**Uygulama:** 0.131.0; şema 55.

Kullanıcı aynı domain, kaynak ve kayıtlı izleme seçimini tekrar yazmadan
çalıştırmak istiyor. Profil bir toplama tarifidir; kuruluş/sahiplik kanıtı
veya kendiliğinden çalışan abonelik değildir.

`profiles save AD DOMAIN` tam seçimi kaydeder. Verilmeyen seçenekler bugünkü
varsayılanlarına çözülür ve açık olarak saklanır. Aynı adla yeniden save,
seçimin tamamını değiştirir; eski seçeneklerle örtük birleştirme yapmaz.
İşler ve izleme kimlikleri kararlı sıraya getirilir. Aynı tanımın tekrarı
yeni revizyon yaratmaz. Geri çekilen profil aynı kimlikle etkinleşebilir.

Şema 55 iki ek tablo getirir: güncel profiller ve eklemeli değişiklik geçmişi.
Her değişiklik tam tanımı, revizyonunu ve SHA-256 özetini taşır. JSON tanımı
sürümlüdür; bilinmeyen alan/sürüm, bozuk özet, kopuk geçmiş ve geçersiz yaşam
döngüsü okumada reddedilir. Geçmişi okurken eski izleme hâlâ etkin olmalıdır
diye bir koşul aranmaz; izleme kapatılması tarihî kanıtı bozmaz.

Kaydetme ve çalıştırma öncesinde domain ve seçili izlemeler mevcut toplama
servisiyle ağsız doğrulanır. Yazma/çalıştırma ortak kilidi kullanır. Çalışma
kilidi alındığında profil revizyonu tekrar okunur; arada değişmişse kaynak
isteği ve iş kaydı başlamadan durulur. `collect --profile AD` ile ad hoc
domain/seçenek birlikte verilmez; kaydedilen ayar sessizce aşılmaz.

Profil servisinin küçük depo ve kilit sözleşmeleri vardır; uygulama katmanı
SQLite, terminal veya HTTP import etmez. Kullanım katmanı seçili kaynakları
oluşturur. Dış bağımlılık ve ücretli API eklenmez. `collect DOMAIN` eski
varsayılan davranışını korur. Profil listesi, ayrıntı ve plan salt okunurdur.

Geçiş açık `./xti migrate` komutuyla, mevcut geri dönüş yedeği mekanizmasıyla
yapılır. Eski kayıtlar silinmez, yedek üzerine yazılmaz, DDL hatasında geçiş
geri alınır. Birleşik çalışma oturumu ve eksik işi sürdürme sonraki teslimdir.
