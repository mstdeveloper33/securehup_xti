# 0064 — Maruziyet kapsamlı resmî NVD yenilemesi

**Tarih:** 30 Ekim 2026  
**Durum:** Kabul edildi

## Bağlam

Tek-CVE NVD alımı ve KEV/EPSS kaynaklı eksik-NVD zenginleştirmesi çalışıyordu. Bir CVE insan maruziyet incelemesine alındıktan sonra NVD kaydı zamanla değişebilir; ancak hangi ilgili kayıtların eski olduğunu görmek ve yalnız bunları kontrollü yenilemek için ayrı bir akış yoktu. Bütün NVD kataloğunu kişisel bilgisayara aynalamak bu ihtiyaca göre gereksiz ağ, disk ve operasyon yükü oluşturur.

## Karar

- `tracked-nvd-plan`, varsayılan olarak açık ve görünür maruziyetleri tek salt-okunur SQLite anında okur. Kapanmış ve bastırılmış kayıtlar yalnız açık seçeneklerle dahil edilir.
- Aynı CVE'ye bağlı birden çok maruziyet benzersiz CVE altında gruplanır. Son başarılı NVD kontrolü `nvd_cve_records.last_seen_at` değeridir; başarısız kaynak denemesi başarı zamanı gibi kullanılamaz.
- Kullanıcı eşiği 1–8760 saattir; varsayılan yedi gün/168 saattir. Kayıtlar `current`, `stale` ve saat gerilemesi durumunda `clock_error` anlamlarıyla ayrılır. Saat sorunu görünür kalır fakat ağ adayı yapılmaz.
- Plan en fazla 100 dikkat satırı gösterir; incelenen maruziyet, benzersiz CVE, güncel, zamanı gelmiş ve saat hatalı toplamları gösterim sınırından önce hesaplanır. Plan ağ, kilit veya yazma yapmaz.
- `tracked-nvd-refresh` açık komutla en fazla beş zamanı gelmiş CVE'yi mevcut resmî NVD tek-CVE adaptöründen alır. Önceki süreçteki son NVD denemesi dahil anahtarsız istekler arasında en az 6,5 saniye bırakılır.
- Her CVE mevcut NVD deposunda ayrı atomik kaynak çalışmasıdır. İlk kaynak/ayrıştırma hatası kaydedilir ve sonraki CVE çağrılmaz; önceki başarılar korunur. Yeniden çalıştırma güncellenmiş kayıtları yeni plana göre dışarıda bırakır.
- Yenileme insan maruziyet ana kaydını ve olay geçmişini yazmaz. Kaynak özeti değişmişse mevcut kontrollü yeniden değerlendirme planı bunu `nvd_record_changed` olarak gösterir.

## Güvenlik ve işletim sınırları

Komut yalnız NIST'in sabit resmî HTTPS tek-CVE uç noktasını kullanır; izlenen hedefe bağlanmaz, API anahtarı veya ücretli servis istemez. Kayıt alanı ve plan ağdan önce doğrulanır; ortak yerel çalışma kilidi paralel kaynak kullanımını engeller. Bu akış arka plan servisi, tam NVD aynası, tarih pencereli genel eşitleme veya otomatik insan kararı değildir.

## Veri etkisi

Yeni tablo ve migration yoktur. Başarılı/başarısız denemeler mevcut `vulnerability_source_runs`, güncel NVD kaydı ve değişiklik olaylarında tutulur. 0.64.0 şema 28'i kullanır.
