# ADR 0040 — NVD planı küçük, ardışık ve ilk hatada duran gruplarla yürütülecek

- **Durum:** Kabul edildi
- **Tarih:** 29 Ekim 2026

## Bağlam

Çevrimdışı plan binlerce eksik NVD bağlamı gösterebilir. Anahtarsız kamu API'sine bunların tamamını arka arkaya göndermek kaynak sınırını aşabilir, uzun süren belirsiz bir iş yaratabilir ve kişisel kullanım için gereksiz veri toplayabilir. Her ağ isteği açık kullanıcı eylemine, görünür sınıra ve kaldığı yerden devam davranışına sahip olmalıdır.

## Karar

`vuln enrich-nvd` bir çalıştırmada planın başındaki en fazla beş CVE'yi alır. Ücretli hizmet veya API anahtarı kullanılmaz. İstekler paralel gönderilmez. Her NVD kaynak çalışmasının bitişinden sonra bir sonraki isteğe kadar en az 6,5 saniye beklenir; veritabanındaki son NVD çalışma zamanı farklı bir süreçten kalmış olsa da aynı kural uygulanır.

Planlama, bekleme, ağ ve kayıt ortak yerel çalışma kilidi altında yürür. İlk kaynak/bağlantı/ayrıştırma hatası ayrı başarısız çalışma olarak kaydedilir ve yeni CVE istekleri durdurulur. Başarılı CVE'ler tek tek atomik kaydedilir. Sonraki açık komut planı yeniden kurduğu için tamamlananları çıkarır ve kalanlardan devam eder. Otomatik retry, arka plan döngüsü veya sınırsız toplu indirme yoktur.

Sistem saati son kayıtlı NVD bitiş zamanının anlamlı ölçüde gerisindeyse ağ çağrısı yapılmaz. Eksik, eski veya bozuk şema da kaynak oluşturulmadan önce reddedilir.

## Sonuçlar

- Ücretsiz NVD kullanımında yük ve bekleme kullanıcı tarafından görülebilir ve sınırlıdır.
- Kaynak kesintisi peş peşe başarısız istek fırtınasına dönüşmez.
- Ctrl+C veya süreç kapanması önceki atomik başarıları bozmaz; sonraki komut kalanları planlar.
- Beş kayıt yaklaşık en az 26 saniyelik ara içerir; gerçek ağ süresi buna eklenir.
- Bu, tam NVD aynası veya tarih pencereli artımlı eşitleme değildir.
- Ürün/sürüm kanıtı olmadan maruziyet sonucu üretilmez.
