# P12 teslimi — sensör ve malware telemetrisi

23 Kasım 2026 · XTI 0.192.0 · çekirdek şema 99.

## Gereksinim kapsamı

| ID | Sonuç |
|---|---|
| A05 | Honeypot/sinkhole sonucunu ham sır ve komutlardan arındırılmış, kaynaklı sensör kanıtına alma motoru tamamlandı; gerçek sensör ağı işletimi dış gereksinimdir. |
| A06 | Ayrı CAPE ortamında tamamlanmış raporu güvenli davranış özeti ve IOC kanıtına alma motoru tamamlandı; XTI malware çalıştırmaz. |
| A07 | Üç telemetri kaynağı P09 manifestine erişim, hak, kota, hata ve provenance kararıyla eklendi. |
| B01-B02/J01-J03 | IOC kanonikleştirme, kaynak içi tekilleştirme, hash/provenance ve insan incelemesi mevcut motor bileşenleriyle bağlandı. |
| C01/E01/E03/G02 | Kuruluş kapsamı, ortak arama, P07 alarm politikası ve vaka kanıtı yeniden kullanıldı. |
| H01-H03-H05-H07 | Firma izolasyonu, şema geçişi, P08 süre/hold/arşiv/restore ve bütünlük kontrolleri tamamlandı; genel RBAC tüketici platformda kalır. |

## Teslim edilen yaşam döngüsü

1. Sürümlü ve etkin/pasif hale getirilebilir kuruluş telemetri kaynağı.
2. XTI Sensor JSONL, güvenli Cowrie JSONL ve tamamlanmış CAPE raporu önizleme.
3. Dosya boyutu/kayıt/JSON derinliği, no-follow ve önizleme hash'i koruması.
4. Atomik, tekrar güvenli içe alma; kaynak değişirse kesinti ve açık recovery.
5. Güncel kayıt, bütün sürümler, çalışma kalemleri ve kaynak olay geçmişi.
6. İnsan kararı ve kanıt değişiminde yeniden inceleme.
7. Global arama, Engine `record.get`, vaka kanıtı ve P07 birleşik alarm.
8. Engine v1 salt okuma ve firma platform v1 workspace çitli yazma.
9. Şema97→98 yedekli geçiş ve boş hedefe restore.
10. P08 `telemetry_records` politikası, açık hold, aktif vaka koruması,
    kayıpsız çok nesilli arşiv, saydam okuma ve yedekli geri yükleme.
11. Kaynak manifesti, kullanım, mimari, özellik kataloğu ve ticari notlar.

## Güvenlik kararı

XTI kullanıcı adı, parola, saldırgan komutu, ham mesaj, zararlı örnek, PCAP,
bellek dökümü, ekran görüntüsü veya ham sandbox raporu saklamaz. URL içine
gömülü kimlik bilgisi reddedilir. Desteklenmeyen Cowrie olayı neden sayacıyla
atlanır. CAPE çalıştırma ve örnek güvenliği XTI sürecinin dışında, ayrı
yalıtılmış altyapı sorumluluğudur.

## Kabul kanıtı

- Hedefli adapter/lifecycle/CLI/engine/platform/migration/yönetişim testleri
  ağsız çalışır.
- Gerçek terminal dosya akışı kaynak ekleme, önizleme, hash onaylı içe alma,
  idempotent tekrar ve listelemeyi doğrular.
- `scripts/check-telemetry-delivery.py` iki ayrı firma alanında firma başına
  5.000 kayıt, 10 sayfa ve üç çalışmayı doğruladı.
- Değişmeyen tur firma başına sıfır ekleme/güncelleme; tek değişim yalnız tek
  kaydı revision2 yapıp insan kararını yeniden incelemeye açtı.
- Ölçümde en yavaş 5.000 kayıt içe alma 0,706411 saniye, tepe RSS 82,38 MiB,
  veritabanları 19.476.480 ve 19.423.232 bayt, ağ isteği sıfırdı.
- `scripts/check-telemetry-retention-delivery.py` iki firma alanında firma
  başına 1.000 eski kaydı 4×250 partide arşivleyip ilk 250 kaydı geri yükledi;
  19.116.000/19.108.000 bayt kanonik gövde 989.191/988.852 bayta sıkıştı
  (oran 0,051747/0,051751), en yavaş parti 4,419557 saniye, tepe RSS
  106,42 MiB ve ağ isteği sıfırdı.
- Telemetri retention kabulü; hold, aktif vaka koruması, iki firma izolasyonu,
  iki arşiv nesli, değişiklik sonrası yeni sürüm, bozuk arşivde güvenli durma,
  saydam okuma, restore ve gerçek şema98→99 yedekli geçişi doğrular.
- P12'nin adapter, yaşam döngüsü, CLI, Engine, Platform, migration ve yönetişim
  kapsamındaki 105 hedefli testi 87,709 saniyede geçti.
- İlk tam hızlı kapıda görülen eski şema/test varsayımları güncellendikten sonra
  92 regresyon testi 115,038 saniyede; son `scripts/check-fast` kapısındaki
  2.341 test 2.056,954 saniyede hatasız geçti. macOS'ta yalnız Linux çalışma
  zamanı isteyen 4 test beklendiği gibi atlandı.
- Bütün 249 migration testi 164,076 saniyede geçti. Son `scripts/check` sürüm
  kapısındaki 3.686 test 2.990,818 saniyede hatasız geçti; aynı 4 Linux-only
  test macOS'ta beklendiği gibi atlandı.

Bu ölçüm 23 Kasım 2026 macOS yerel kabulüdür; gerçek sensör akış hızı veya
uzun süreli üretim SLO'su değildir.

## Açık dış gereksinimler

- Ayrı, güvenli ve yetkili gerçek Cowrie kurulumu ile canlı JSONL kabulü.
- Ayrı, ağ ve erişim bakımından yalıtılmış CAPE kurulumu ile gerçek tamamlanmış
  `report.json` kabulü; zararlı örnek işleme prosedürü.
- Cowrie/CAPE dağıtım biçimi ve müşteri telemetrisinin ticari saklama/gösterim
  kararı.
- Push sonrası gerçek Linux kurulum, şema yükseltme ve CI kabulü.

Bu maddeler motor kodunu yok saymaz fakat karşılanmadan Cowrie/CAPE kaynakları
“canlı üretim doğrulandı” veya P12'nin dış işletim kısmı “tamamlandı” denmez.
