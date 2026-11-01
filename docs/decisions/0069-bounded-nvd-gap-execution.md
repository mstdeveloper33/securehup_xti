# ADR 0069 — Sınırlı NVD boşluk yürütmesi

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

Boşluk planı güvenli pencere sınırlarını üretiyordu ancak kullanıcı her adayı ayrı komutla çalıştırmak zorundaydı. Bütün dönemi tek seferde veya arka planda indirmek ücretsiz anahtarsız kaynağı zorlayabilir, uzun ve görünmez bir çalışma oluşturabilir ve hatadan sonra hangi pencerelerin denendiğini belirsizleştirebilirdi.

## Karar

`vuln nvd-window-gap-fetch`, aynı salt-okunur planın kronolojik başından kullanıcının açıkça seçtiği 1–3 adayı alır. Her aday için mevcut `NvdWindowService.fetch` akışını tam bir kez çağırır; dolayısıyla pencere başına yalnız bir ve en fazla 100 kayıtlık sayfa istenir.

Komut ağdan önce parametreleri, veritabanını, kaynak geçmişini ve aday planını doğrular. Yazma aşaması yerel çalıştırma kilidi altındadır ve plan kilit alındıktan sonra yeniden üretilir. Her istek, önceki NVD kaynak çalışmasının bitiş zamanına göre en az 6,5 saniyelik anahtarsız erişim aralığını korur.

Kaynak hatası o pencere için başarısız kaynak çalışması oluşturur, imleci ilerletmez ve döngüyü hemen durdurur. Daha sonraki adaylara ağ isteği gönderilmez. Başarılı sayfa CVE kayıtları, değişiklik olayları, kaynak çalışması ve pencere imleciyle tek transaction'da yazılır. Sayfa pencereyi tamamlamadıysa aynı aday sonraki açık çalışmada kaldığı yerden devam eder.

Sonuç plan öncesini, her sayfa sonucunu, denenmiş/başarılı/başarısız sayıları, denenmeyen önceki aday sayısını ve yürütme sonrası yeniden hesaplanan boşluk planını taşır. Kapsama zaten tam ise kaynak nesnesi yapılandırılmış olsa bile çağrılmaz ve sonuç `nothing_to_do` olur. Yeni tablo yoktur; şema 31 korunur.

## Sonuçlar

- Tek komutta yapılabilecek ağ işi en fazla üç istek ve pencere başına bir sayfayla görünür biçimde sınırlıdır.
- Kesinti veya kaynak hatası daha sonraki pencerelerde belirsiz/kısmi çalışma üretmez.
- Uzun dönemler kullanıcı tarafından tekrar çağrılarla, kalıcı imleçlerden devam ederek tamamlanabilir.
- Bu akış daemon, takvim, otomatik tekrar, sınırsız indirme veya tam NVD aynası değildir.
- Otomatik zamanlama ve daha geniş kaynak orkestrasyonu ayrı kapasite/operasyon kararlarıdır.
