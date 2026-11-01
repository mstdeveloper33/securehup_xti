# 0094 — Kalıcı ve sınırlı ransomware iddiası snapshot geçmişi

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Karar

Canlı, yazmasız `ransomware recent` görünümü korunur. Kullanıcı yalnız `ransomware refresh` komutunu açıkça çalıştırdığında tamamen doğrulanmış kamu snapshot'ı yerel SQLite geçmişine yazılır. Son başarılı snapshot temel alınarak yeni, değişen, aynı ve kayan kaynak penceresinden çıkan kayıtlar ayrılır. İlk başarılı snapshot yalnız başlangıç çizgisidir; yeni alarm sayılmaz.

Kaynak hatası boş snapshot değildir. Ayrı başarısız çalışma kaydedilir ve önceki başarılı snapshot korunur. `ransomware status` internet kullanmadan son denemeyi, son başarılı snapshot'ı ve sınırlı geçmişi gösterir. Bütün yazım tek transaction ve ortak yerel worker kilidi altındadır.

Kalıcı model leak-site URL'si, ham gönderi, ekran görüntüsü veya kişisel veri taşımaz. Yalnız daha önce katı biçimde doğrulanan güvenli iddia alanları, kaynak/akış zamanı, içerik özeti ve fark eylemi saklanır. Bir kaydın `removed` olması yalnız 30 günlük kaynak penceresinde artık bulunmadığını söyler; geri çekilme, ödeme, çözüm veya güvenlik kararı değildir.

Başlangıç snapshot'ı güvenli öğeleri bir kez saklar. Sonraki çalışmalarda değişmeyen üyelikler yalnız çalışma sayacında korunur; aynı öğe satırı yeniden kopyalanmaz. Yeni, değişen ve pencereden çıkan delta öğeleriyle güncel snapshot deterministik olarak yeniden kurulabilir.

Şema 39→40 geçişi önce doğrulanmış geri dönüş yedeği alır, sonra iki boş tabloyu transaction içinde oluşturur. Eski veriden ransomware iddiası veya çalışma geçmişi türetilmez. Kuruluş/domain izleme tanımı, eşleşme kararı ve yerel bildirim ayrı bir sonraki dilimdir.

## Gerekçe

Tam snapshot farkı, tek tek kayıtların kaybolmasını kaynak hatasından ayırır ve gelecekteki izleme kurallarına denetlenebilir bir temel verir. İlk snapshot'ı alarm saymamak mevcut kaynak geçmişinin binlerce sahte “yeni olay” üretmesini engeller. Ham leak-site adresini model dışında tutmak güvenlik ve veri minimizasyonu sınırını kalıcı depoda da korur.
