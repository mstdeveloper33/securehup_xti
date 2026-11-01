# 0097 — Sınırlı ön plan ransomware izlemesi

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Karar

`ransomware watch-monitor`, mevcut açık kaynak yenileme + bütün etkin izlemeleri çalıştırma akışını yalnız terminal açıkken tekrarlar. Kullanıcı 1–1000 tur, 300–86400 saniye aralık ve 1–604800 saniye toplam yeni-tur başlatma süresi seçebilir. Varsayılan değerler üç tur, bir saat aralık ve bir gündür. Etkin izleme ve öğe sınırları her turda yeniden doğrulanır; bütün etkin tanımlar sınır içine sığmıyorsa ilk ağ isteğinden önce durulur.

Her tur ayrı ve kalıcı bir kaynak çalışmasıdır. Başarılı kaynak turundaki her kuruluş/domain izlemesi mevcut ayrı atomik transaction'ını ve kaynak çalışma kimliği bağını kullanır. Kaynak hatası boş snapshot veya sıfır eşleşme sayılmaz; başarısız kaynak çalışması saklanır, o turda eski snapshot üzerinde izleme yapılmaz ve süre/tur bütçesi varsa sonraki tur denenir. Herhangi bir izleme bütünlük hatası güvenli biçimde komutu durdurur; daha önce tamamlanan kayıtlar korunur.

Süre, geriye gitmeyen süreç saatiyle ölçülür. Süre sınırı yeni tur başlatmayı engeller; başlamış ağ isteği tamamlanırken sınır aşılabilir. Bekleme en fazla bir saniyelik parçalara bölünür. `Ctrl+C` üst katmana iletilir ve 130 çıkışı üretir; tamamlanan turlar geri alınmaz. En az bir tur tamamlanmış ve hiçbir kaynak turu başarısız olmamışsa başarı, aksi durumda eksik/kaynak sonucu verilir. Sessiz başlangıç izlemeleri ayrı sayılır. Çok turlu eşleşme/fark toplamları tur bazlıdır; aynı eşleşme farklı turlarda yeniden sayılabilir ve benzersiz olay sayısı gibi sunulmaz.

## Sınırlar

Komut daemon, cron girdisi, işletim sistemi hizmeti veya görünmez zamanlayıcı kurmaz. Terminal kapanınca izleme biter. Kalıcı 7/24 çalışma, yeniden başlatma sonrası devam, hizmet sağlığı ve toplu oturum tablosu bu dilimde yoktur. Her iddia yine kamu kaynağındaki doğrulanmamış grup kaydıdır; bildirim ihlal doğrulaması değildir.

Toplu oturum tablosunun bulunmaması sınırı daha sonra [0098 numaralı kararla](0098-durable-ransomware-monitor-sessions.md) kaldırılmıştır; daemon ve otomatik devam sınırları korunur.
