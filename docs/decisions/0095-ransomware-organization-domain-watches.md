# 0095 — Ransomware kuruluş/domain izlemeleri ve sessiz başlangıç

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

Kalıcı kamu snapshot geçmişi değişiklikleri kaynak düzeyinde ayırır; fakat kullanıcının ilgilendiği kuruluş veya domaini bütün akıştan güvenli biçimde ayırmaz. Serbest metindeki her benzerliği alarm yapmak yanlış pozitif üretir. İlk kez çalıştırılan bir tanımda geçmiş pencerenin tamamını “yeni olay” saymak da yanıltıcıdır.

## Karar

Kullanıcı benzersiz adla `organization` veya `domain` izlemesi kaydeder. Kuruluş yalnız kaynaktaki kuruluş (`victim`) alanında varsayılan tam eşleşmeyle aranır; kullanıcı açıkça seçerse en az beş karakterli içerme eşleşmesi kullanılabilir. Domain yalnız kaynaktaki web bilgisinden çıkarılan normalleştirilmiş hostta aynı kök veya alt alan adı olarak eşleşir. Grup, ülke, sektör ve diğer serbest metin alanları otomatik alarm kapsamı değildir.

Çalışma yalnız son başarılı yerel snapshot'ı kullanır ve internete çıkmaz. Tanımın ilk çalışması veya tanım değişikliği sessiz baseline'dır. Aynı tanımın sonraki çalışmalarında yeni ve değişen eşleşmeler ortak yerel bildirim kutusuna girer. Kayan kaynak penceresinden çıkma sonuç geçmişinde korunur fakat kapatma kanıtı sayılmaz ve tek başına bildirim üretmez.

Tanım yaşam döngüsü, kaynak snapshot kimliği, tam çalışma sonucu ve bildirim bağlantısı SQLite'ta denetlenir. Bildirim ile çalışma aynı transaction içindedir; okundu durumu iddianın inceleme/doğruluk durumundan bağımsızdır. Ham leak-site adresi ve içeriği izleme tablolarına taşınmaz.

## Sonuçlar

Kullanıcı terminalden ücretsiz ve tekrar üretilebilir bir kuruluş/domain erken uyarı akışı kurabilir. Sonuç hâlâ grubun kamu iddiasıdır; doğrulanmış ihlal değildir. Kaynak kapsamı yalnız kayan dönemdir. Otomatik yenileme, bütün etkin izlemeleri toplu çalıştırma, ikinci açık kaynak, tarihsel tekrar çözümleme, e-posta/SMS ve web paneli bu kararla eklenmez.

Şema 40→41 geçişi önce doğrulanmış geri dönüş yedeği alır, sonra beş boş tabloyu transaction içinde oluşturur. Eski snapshot'tan izleme tanımı, baseline, eşleşme veya bildirim türetilmez.
