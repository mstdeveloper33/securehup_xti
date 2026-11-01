# 0098 — Kalıcı ransomware monitor oturumları

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Karar

Her `ransomware watch-monitor` çalışması, ilk ağ isteğinden önce benzersiz kimlikli ve `running` durumlu kalıcı bir oturum açar. Ayarlar; planlanan tur, tur aralığı, yeni-tur süre bütçesi, etkin izleme sınırı ve görünüm sınırlarıyla birlikte saklanır.

Her tamamlanan tur ayrı kaydedilir. Tur bir kaynak çalışma kimliğine ve o tur tarafından oluşturulan izleme çalışma kimliklerinin sıralı tam kümesine bağlıdır. Özet sayaçları bu bağlantılardan yeniden doğrulanır. Böylece aynı son kaynak snapshot'ı üzerinde daha sonra elle çalıştırılan bir izleme, geçmiş monitor turunun üyesi veya sonucu gibi görünmez.

Normal bitişte bütün tamamlanan kaynak turları başarılıysa `complete`, en az bir kaynak turu başarısızsa `partial` kullanılır. `Ctrl+C` `interrupted`, beklenmeyen uygulama veya kalıcı kayıt hatası `failed` olur. Her tamamlanan tur, sonraki beklemeden önce ayrı transaction ile saklanır. Süreç işletim sistemi tarafından aniden sonlandırılırsa son bitiş yazısı oluşmayabilir; oturum `running` kalır ve bu durum “tamamlandı” olarak yorumlanmaz.

`watch-monitor-list` ve `watch-monitor-show` ağsız ve salt okunurdur. Okuma; oturum, tur, kaynak çalışması, izleme çalışması ve bildirim bağlantılarını yeniden denetler. Bozuk, eksik, başka kaynağa bağlı veya sayaçları uyuşmayan geçmiş kısmi sonuç vermeden güvenli biçimde durur.

Şema 42 üç tablo ekler: oturum başlığı, tamamlanan tur özeti ve tur–izleme çalışma üyeliği. Şema 41 geçişi önce doğrulanmış yedek alır; yeni tablolar boş başlar ve eski kaynak/izleme geçmişinden monitor oturumu türetilmez.

## Sınırlar

Bu karar daemon, cron girdisi, işletim sistemi hizmeti, otomatik yeniden başlatma veya otomatik sahipsiz-oturum kapatma eklemez. `running`, sürecin hâlâ yaşadığını kanıtlamaz; yalnız kalıcı bir bitiş kaydı bulunmadığını söyler. Bir oturumu devam ettirmek yerine yeni açık komut yeni kimlikle başlar. Sayaçlar tur bazlıdır ve benzersiz ransomware iddiası sayısı değildir. Kaynak kayıtları doğrulanmış ihlal hükmü sayılmaz.
