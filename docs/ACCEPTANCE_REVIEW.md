# Linux kullanım raporunun değerlendirilmesi

16 Kasım 2026. Kullanıcı kendi Linux VM denemesini paylaştı: sürüm
0.147.1, çekirdek şema 69, bildirilen Python 3.14.7; gerçek domain ile
kontrollü örnek kayıtların birlikte kullanıldığı izole veri alanı.
Rapor 50 komut ailesine dokunulduğunu ve 2.603 testte bir hata olduğunu
bildiriyor. Ham test günlüğü ve veri alanı bu çalışma ortamında yoktur.
Bu sayılar kullanıcı raporudur; burada yeniden ölçülmüş sonuç değildir.

İnceleme 0.150.0 / şema 72 çalışma ağacında yapıldı. Önceki rapor sonraki
Nmap teslimlerini kapsamaz. Yeni düzeltmeler veritabanı geçişi, bağımlılık
veya platform sözleşme sürümü değişikliği gerektirmez.

## Doğrulanan ve düzeltilenler

| Bulgu | Yerel doğrulama | Sonuç |
| --- | --- | --- |
| CTI izleme ekleme/listeleme hatası | Tam ve kontrollü CERT Polska biçiminde 10.001 IOC eklendi; dar aktör izlemesi aynı kapsam hatasıyla durdu. | Kayıtlı arama denetimi artık yalnız çalışma sonuçlarının başvurduğu kayıtların varlığını indeksli sorguyla kontrol eder. İlgisiz katalog büyüklüğü izleme sayısı sınırına sayılmaz. Ekleme, iki ardışık çalışma ve listeleme geçti. |
| Zamanlı yedek testi `umask 002` altında kırılıyor | Bildirilen test aynı izin hatasıyla yeniden üretildi. | Test kendi klasörünü `0700` ile oluşturur. Üretim kodunun ortak yazılabilir klasörü reddetmesi korunur. |
| Yeni veri/yedek klasörünün izinleri umask'a bağlı | `000`, `002`, `022`, `077` maskeleriyle oluşturma, yedekleme ve geri yükleme sınandı. | Yeni klasörler ve oluşturulan ara klasörler `0700`, veritabanı/yedek dosyaları `0600`. Mevcut klasörlerin izinleri otomatik değiştirilmez. |
| Eski klasörlerin geniş izinlerinin görünmemesi | Veri klasörü `0775`, yedek klasörü `0755` yapıldı; byte'lar ve izinler okuma öncesi/sonrası karşılaştırıldı. | `storage readiness` sahibi/mod bitleri ve erişim durumunu terminal/JSON içinde gösterir. Riskli veya doğrulanmamış izinlerde yerel kurtarma durumu `attention` olur. |

CTI denetiminde gerçek kopuk sonuç bağlantıları, bozuk geçmiş ve tutarsız
hash'ler hata vermeye devam eder. “Listeleme hiçbir koşulda hata vermesin”
önerisi uygulanmadı: bozuk kanıtı sağlıklı liste gibi sunmuyoruz. Ayrı bir
tanılama görünümü gerekirse bozuk kayıtları açıkça işaretleyebilir.
Kayıtlı arama/geçmiş/sonuç sınırları ve CTI aramasının kendi kapsam
sınırları korunur; bu değişiklik sınırsız arama iddiası değildir.

İzin kontrolü veri alanı, `backups` ve `scheduled-backups` klasörlerinin
POSIX sahibi ve mod bitleriyle sınırlıdır. ACL, tüm üst dizinler veya
uzak dosya sistemi yetkileri için eksiksiz güvenlik denetimi sayılmaz.
Firma alanının mevcut daha sıkı erişim doğrulaması ayrı kalır.

## Kalan rapor maddelerinin kararı

| Rapor maddesi | Değerlendirme | Sonraki kabul ölçütü |
| --- | --- | --- |
| Kısmi kanıtın “başarılı kayıt yok” ile karışması | Görünüm iyileştirmesi açık. `sources status` son deneme ve son başarıyı ayırıyor; kısmi kanıtın varlığı daha açık olmalı. | Tam/kısmi kanıt, eski başarı ve hiç kayıt yok ayrımı aynı veride terminal ve JSON'da sınanmalı; kayıtlar silinmemeli. |
| Uzun collect/search/kuruluş raporu | Kısa görünüm ihtiyacı kabul edildi; yeni bayraklar henüz eklenmedi. Aramada mevcut `--kind` ve `--limit` kullanılabilir. | Varsayılan veya açık kısa görünüm hedefe odaklanmalı; kaynak hataları ve gizlenen öğe sayısı görünür kalmalı; tam kanıta ulaşılabilmeli. |
| Tavily yapılandırma durumu | Anahtar yokken çalışmanın durması beklenen davranış. İçerik görünümünde `not_checked`, `check_failed`, `no_content`, `content_found`, eski/belirsiz durumlar zaten var; ayrı anahtar hazırlık bilgisi yok. | Gizli anahtar okunup çıktılanmadan yapılandırma hazırlığı gösterilmeli; “kontrol yapılmadı” ve “kontrol başarılı, boş” ayrımı korunmalı. Canlı Tavily kabulü hâlâ bekliyor. |
| Platform iş yanıtı biçimi | Mevcut v1 sözleşmesinde belgeli: submit/status/cancel için `data.job_id`; result için `data.job` ve `data.result`. | [Platform belgesindeki](PLATFORM_ENGINE.md) biçim korunur. Değişiklik gerekirse sürümlü geçiş yapılır; yalnız görünüm birliği için mevcut istemci kırılmaz. |
| Schedule parametreleri | `--output` / `--at` README'de mevcut. Günlük kullanım rehberine doğrudan örnek eklendi. | [Günlük kullanım](DAILY_USE.md) örneği geçerli; `--output-dir` desteklenen bayrak olarak gösterilmez. |
| crt.sh 502 ve bekleme | Kaynak hatası doğrulanmış boş sonuç değildir. Adaptörde sınırlı timeout tekrarı, `Retry-After` ve 429 beklemesi zaten var. 502'nin kendiliğinden düzeleceği garanti edilemez. | Önceki başarı ve tekrar önerisinin gösterimi iyileştirilmeli. `Retry-After` bulunmayan 5xx için hata/bekleme metni ve sınırlı tekrar politikası ayrıca test edilmeli. |
| Webhook özel IP kaydında erken uyarı | Gönderim anındaki engel raporda çalışmış. Kayıt anı uyarısı ayrı kullanım iyileştirmesi olarak açık. | Erken uyarı olsa da gönderim anındaki adres doğrulaması korunmalı; kayıt sırasında ağ isteği gerekmemeli. |

## Raporun sonuçlarını yorumlama sınırı

- Komut ailesine dokunmak, bütün alt komutların ve bütün hata yollarının
  kabul edildiği anlamına gelmez. Başarılı, boş, yapılandırma engelli ve
  kontrollü örnek verili denemeler ayrı tutulur.
- Kontrollü ürün/CVE ve CTI örnekleri hedef firmada gerçek zafiyet ya da
  aktör ilişkisi kanıtı değildir. Sosyal profil ve sahiplik kararları da
  otomatik tehdit doğrulaması sayılmaz.
- Raporda Cloudflare olarak belirtilen IP'nin portları, firmanın kaynak
  sunucusunun port envanteri sayılmaz. Kesin IP seçimi ve domain DNS
  eşleşmesi, IP üzerinde tarama yetkisinin ayrıca doğrulanmasının yerini
  tutmaz. Bu incelemede aktif hedef trafiği üretilmedi.
- “Kritik açık bulunmadı” bu denemenin gözlemidir; eksiksiz güvenlik
  denetimi, üretim kapasitesi veya sonraki sürümün bütün kabulü değildir.

## Tekrar doğrulama

Önce bildirilen CTI ve umask sorunları mevcut kodda yeniden üretildi.
Düzeltmelerden sonra `umask 002` ile CTI izleme, depolama, izin görünümü ve
zamanlı yedek testlerinin 44'ü 12,473 saniyede geçti. Yeni testler hızlı
kontrol listesine de eklendi. Son kodun tam turu aynı `umask 002` altında
2.665 testi 1.145,005 saniyede tamamladı: 2.661 başarılı, macOS'ta Linux'a
özgü dört atlama, hata yok. Ortam macOS 26.6.2 arm64 / Python 3.13.3.
[İşlevsel kabul kaydı](FUNCTIONAL_ACCEPTANCE.md) bu sonucu önceki
sürüm ve canlı kaynak denemelerinden ayrı tutar.

```sh
umask 002
./scripts/check
```

Bu komut yerel testleri çalıştırır. Testler içinde `000`, `002`, `022` ve
`077` maskeleri ayrı geçici klasörlerle doğrulanır. Kullanıcının VM'inde
son kodla tekrar kabul ve gerçek Nmap çalışması ayrıca gereklidir.
