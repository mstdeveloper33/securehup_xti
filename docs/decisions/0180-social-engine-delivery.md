# 0180 — Sosyal kanıtı ortak motor akışlarına bağlama

20 Kasım 2026 · Kabul edildi · 0.175.0 / çekirdek85 / kuyruk3.

## Karar

- Yeni birleşik keşif, eski kullanıcı adı tarayıcısından ayrı kimlikle
  ortak araştırmaya bağlanır. Firma/domain + tam profil URL kimliği
  kullanılır. Sayfa, araç iddiası, Bright Data ve insan kararı ayrı kanıttır.
- Aynı transaction içindeki sosyal okuma 5.000 satır/16MiB ön denetim ve
  1.000 benzersiz profil sınırına uyar. Sınırda kapsam eksik gösterilir.
  Son kesin gözlem erişim belirsizliğinde korunur; eski insan kararı
  yeni keşfin kararı gibi gösterilmez.
- `source-comparison-v1` profil varlığı veya CTI iddiasının yaşam döngüsü
  gibi aynı anlamdaki bilgileri karşılaştırır. Kaynak/referans başına son
  gözlem seçilir; tarih, güncellik ve kapsam tamlığı verilir. Oy çokluğu,
  resmî hesap, taklit veya otomatik zararlılık sonucu üretilmez.
- Yeni takip seçimi `CollectionSocial` portundan mevcut profil/plan ve
  collection işine bağlanır. Profil/plan v3 yalnız sosyal seçim varsa
  kullanılır; eski v1/v2 kanonik JSON ve hash'leri korunur. Kayıtlı izleme
  sürümü, domaini ve kapsamı yürütmede yeniden kontrol edilir.
- Tur anahtarı toplama adımına bağlıdır. Bitiş günlüğü, değişiklik bildirimi
  ve kaynak makbuzu aynı transaction'da yazılır. Commit edilmiş keşif
  kesintide tekrar toplanmaz. Henüz keşfi kaydolmamış tur ağsız interrupted
  kapanır. Zamanı gelmemiş izleme skipped/not_due olur.
- Mevcut journals arşivi social_discovery_runs.report_json gövdesini
  kapsar. Domainin son tamamlanmış kaydı ve devam eden kayıt korunur.
  Arşiv marker'ı + orijinal hash ile okuma, idempotency ve vakalar aynıdır.
  Sıkıştırılmış gövde, mantıksal okuma/yazma sınırını azaltmaz.
- Etiketli örneklem X başlığında benzer kullanıcı adı yanlış eşleşmesini
  yakaladı. `social-discovery-v2` tam @kullanıcı_adı ister. v1 yalnız
  geçmişi doğrulamak için korunur. Rezervasyon hash'i politikayı bağlar;
  farklı politikayla bitiş reddedilir. Yeni sosyal vaka kopyası v2 açık
  discovery_policy taşır; v1 kopya eski kuralla okunur.

## Geçiş ve kurtarma

Şema84 → 85 açık `migrate` komutuyla, benzersiz eski sürüm yedeğinden
sonra yapılır. collection_session_steps CHECK genişler;
collection_step_receipts nullable/unique/FK social_tracking_run_id kazanır.
Eski sütunlar, rowid'ler, ilişkiler ve kaynak sonuçları korunur. Bütün
kopyalama bir transaction içindedir. Eski motor yeni şemayı reddeder;
geri dönüş eski yedekten boş/yeni alana yapılır.

Yeni servis/daemon, ağ kaynağı veya bağımlılık eklenmez. Bright Data canlı
anahtarı ve Nmap yetkili hedefi ayrı kabul girdileridir. Ölçüm kontrollü
örneklemdir; canlı internet için yüzde100 doğruluk veya 7/24 SLA değildir.

Kanıtlar: `test_social_engine_package`, `test_collection_social_migration`,
`test_social_quality`, `scripts/check-social-upgrade.py` ve
[teslim kaydı](../roadmap/SOCIAL_ENGINE_DELIVERY.md).
