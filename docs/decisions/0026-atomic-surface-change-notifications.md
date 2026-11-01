# 0026 — Dış yüzey değişikliklerini yerel kutuya atomik bağlama

**Durum:** Kabul edildi  
**Tarih:** 29 Ekim 2026

## Bağlam

DNS/TLS/HTTPS, MX/SPF/DMARC ve sınırlı TCP servis kontrolleri eklemeli geçmiş ve açıklanabilir `baseline/unchanged/changed` farkı üretiyor. Kullanıcının her geçmiş ekranını elle açması değişiklikleri kaçırmasına yol açabilir. Buna karşılık ilk temel kaydı veya aynı sonucun tekrarını alarm yapmak kişisel kullanımda gereksiz gürültü üretir.

Projede marka bulguları ve ilk pasif alt alan adı adayları için kalıcı, okunmuş/okunmamış durumu olan yerel bir `inbox` zaten vardır. Ayrı bir değişiklik kutusu ortak sıralama, yedekleme ve inceleme davranışını çoğaltır.

## Karar

Yalnız saklanan farkın türü `changed` olduğunda `surface_evidence_changed` olayı oluşturulacak. İlk `baseline` ve `unchanged` kayıtları bildirim üretmeyecek. DNS/TLS/HTTPS, e-posta DNS ve servis kontrolü aynı kuralı kullanacak.

Yeni `surface_change_notifications` satırı tam olarak bir `surface_checks`, `surface_mail_checks` veya `surface_service_checks` satırına yabancı anahtarla bağlı olacak. Bu üç seçenekten tam birinin dolu olması SQLite kısıtıyla zorunlu tutulacak. Kanıt ve bildirim aynı yazma transaction'ında oluşturulacak; bildirim yazılamazsa yeni kanıt da geri alınacak. Her kontrol kimliği en fazla bir bildirimle bağlanabilecek.

Üç bildirim tablosu ortak artan `sequence` alanını paylaşacak. Bulgu, pasif aday ve değişiklik bildirimleri tek terminal listesinde sayfalanacak; aynı açık `read/unread` işlemi hepsine uygulanacak. Ayrıntı görünümü saklı değişim özetinden değişen alanı, eklenen/kaldırılan IP'yi veya TCP port geçişini gösterecek ve internete bağlanmayacak.

Şema 14→15 geçişi önce doğrulanmış kurtarma yedeği oluşturacak ve yeni tabloyu boş başlatacak. Eski kanıtlardan geriye dönük bildirim üretilmeyecek; geçmiş bir değişimin o zaman görülüp görülmediği bilinemez.

## Sınırlar

- Bildirim yalnız kullanıcı ilgili kontrol komutunu çalıştırdığında oluşur; arka plan zamanlayıcısı değildir.
- `changed` sonucu saldırı, kesinti, yanlış yapılandırma veya zafiyet hükmü değildir.
- Belirsiz ya da başarısız ağ sonucu, önceki kanonik durumdan farklıysa görünür değişim olabilir; otomatik kapanış veya risk kararı üretmez.
- E-posta, SMS, webhook, masaüstü bildirimi ve dış teslim onayı yoktur.
- Kaynak kesintileri ve pasif adaya eklenen yeni sertifika kanıtı bu olay türüne dönüştürülmez.

## Sonuçlar

Kullanıcı tek gelen kutusundan marka adayı, yeni pasif alt alan adı ve kendi dış yüzeyindeki açıklanabilir değişiklikleri izleyebilir. Tek transaction ve yabancı anahtarlar yarım ya da kanıtsız bildirimi önler. Ortak sıra ve okundu davranışı yeni kanal eklemeden korunur. Sürekli izleme ve dış teslim sonraki, ayrı yetki ve operasyon kararları olarak kalır.
