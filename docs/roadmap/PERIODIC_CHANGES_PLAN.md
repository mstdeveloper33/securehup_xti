# Günlük / haftalık yerel değişim raporu — Aşama 4

**Durum: TAMAMLANDI — 0.133.0.**

**14 Kasım 2026.** İlk teslim mevcut bulgu, dış yüzey, sosyal izleme,
ThreatCluster ve RansomLook geçmişini tek salt okunur kesitte raporlar;
yeni tablo veya şema geçişi gerekmez. Varsayılan tüm yerel ailelerdir;
`--domain` yalnız marka/dış yüzeyi kapsar. **Kuruluş filtresi uygulanmadı**;
aşağıdaki kuruluş filtresi ve genişletilmiş model notları gelecek tasarımıdır.
Çalışan kapsam [STATUS](../STATUS.md) dosyasındadır.

## Kullanıcının göreceği sonuç

Çalışan komutlar:

```text
xti changes --days 1
xti changes --days 7
xti changes --days 7 --domain example.com
xti --json changes --days 7
```

Komut mevcut yerel kayıtları okur. Kaynak yenilemesi, internet sorgusu, analiz
çalıştırma, bildirim oluşturma veya okundu işaretleme yapmaz. Rapor,
"son 24 / 168 saatte sisteme hangi yeni kayıtlar ve değişiklikler işlendi?"
sorusunu yanıtlar; o sürede internette olan her olayı bildiğini iddia etmez.

1. Yeni marka/domain adayları ve yeni dış yüzey adayları.
2. Sosyal izlemelerde yeni görülen, değişen veya artık raporlanmayan profiller.
3. ThreatCluster ve RansomLook izlemelerinde eklenen, güncellenen ve kaynak
   listesinden çıkan iddia satırları; iki kaynak ayrı gösterilir.
4. İlk ölçümler: gerçek değişimden ayrı başlangıç tablosu.
5. Hata, kısmi sonuç, kesinti, atlanan kontrol ve dönem içindeki kapsam boşlukları.

Aynı domain, platform veya iddia birden fazla kaynakta/izlemede geçebilir.
Kaynak/izleme başına sayı ve tekil kayıt kimlikleri korunur. Bölümler toplanıp
"toplam benzersiz tehdit" sayısı üretilmez. İlk ölçüm veya kaynakta yeni görülen
satır, yeni gerçekleşmiş ihlal ya da doğrulanmış sahte hesap anlamına gelmez.

## Zaman sözleşmesi

- `--days` ilk sürümde yalnız `1` veya `7`; bool dahil diğer değerler reddedilir.
- Servis saatini bir kez alır; `window_end = generated_at = aware UTC now`,
  `window_start = window_end - timedelta(days=days)`.
- Aralık **başlangıç dahil, bitiş hariç** `[window_start, window_end)` olur.
  Terminal açık başlangıç/bitiş saatlerini ve UTC'yi gösterir. Bu, yerel takvimde
  "dün" veya "bu hafta" filtresi değildir; yaz/kış saati gün uzunluğunu değiştirmez.
- Filtre yerel kayıt/çalışma zamanına uygulanır. Harici sertifika tarihi,
  profil içerik tarihi veya ransomware `discovered_at` değeri sadece ayrı
  kaynak tarihi olarak gösterilir; pencereye dahil edilme kararı değildir.
- Saat bozukluğu nedeniyle gelecekte kalan kayıtlar bugüne taşınmaz.
  Erişilebilir dönem kanıtlarında saptanan saat tutarsızlığı ayrı kapsam notudur.
  Son çalışma seçerken kaynakların sıra alanları kullanılır; saat gerilemesi
  daha eski sequence'i son sonuç yapmaz.

| Bölüm | Kanonik zaman ve kimlik | Anlam / veri kaynağı |
| --- | --- | --- |
| Yeni marka/domain bulgusu | `findings.created_at`, `findings.id` | Yerelde ilk oluşturulan bulgu. `last_seen_at` yeni bulgu tarihi değildir. Kural sürümü korunur. |
| Yeni dış yüzey adayı | `surface_candidate_events.created_at`, event `id`, `action='discovered'` | `candidate_id` ve domain görünür; `first_seen_at` harici eski kayda dayanabileceği için pencere saati yapılmaz. |
| Dış yüzey inceleme değişimi | Aynı events tablosu; owned/rejected/reopened | İnsan kapsam kararıdır; yeni keşif sayısına katılmaz. İlk sürümde ayrı küçük alt bölüm veya ayrıntı. |
| Sosyal izleme | `brand_username_watch_runs.recorded_at`, run `id` + item `id` | `checked_at` ayrı ölçüm zamanı; güncel izleme adı eski ölçümün tanımı yapılmaz. |
| ThreatCluster izlemesi | `ransomware_watch_runs.executed_at`, run `id` + item `id` | Tam `source_run_id` görünür. `discovered_at` iddianın kaynak tarihidir. |
| RansomLook izlemesi | `ransomlook_watch_runs.executed_at`, run `id` + item `id` | ThreatCluster ile birleştirilmez; tam kaynak çalışma bağı korunur. |
| Kaynak çalışma hatası | Scan attempt `finished_at`; discovery/feed/claim run `finished_at`; sosyal run `recorded_at` | Kaynak durumu, çalışma kimliği, hedef/kapsam ve güvenli hata metni. |
| Toplama kesintisi / atlama | Session/step `finished_at`, session/step kimliği | Aşama 2 varsa kesin seçilmiş işin neden çalışmadığı gösterilebilir. Running iş açık kayıt olarak ayrıca gösterilir. |

Aynı kapsamda farklı `rule_version` ile oluşmuş iki marka kaydı saklı kalır.
İstenirse bölümde `(asset_value, domain)` bazında "farklı domain" sayısı ayrıca
verilir; bulgu satırı sayısından farklı etiketlenir. Dış yüzeyde aynı adayın
birden çok kaynağı yeni aday sayısını artırmaz; kaynak kanıtları ayrıntıdır.

## İlk ölçüm ve değişim ayrımı

Sosyal run `previous_complete_run_id is None` ise başlangıçtır.
`baseline_found` / `baseline_unreported` değişim tablosuna taşınmaz. Diğer
çalışmalarda yalnız `newly_found`, `changed`, `no_longer_reported` kullanıcı
odaklı değişimdir; değişmeyen ve raporlanmayan satırların sayaçları bağlamdır.
"Artık raporlanmadı" hesabın silindiğini veya ele geçirildiğini ispatlamaz.

İki ransomware ailesinde `previous_run_id is None` ilk ölçümdür. İlk çalışmanın
`added` satırları başlangıç bölümüne gider. Sonraki `added/updated/removed`
gerçek çalışma farklarıdır; `unchanged` ayrıntı bağlamı olabilir. `removed`
sızıntının ortadan kalktığını ispatlamaz, kaynak listesindeki değişikliği anlatır.

Karşılaştırılan önceki çalışma pencerenin dışında olabilir. Önceki kimlik ve
tarih bağlam olarak okunur, önceki öğeler pencereye yeniden sayılmaz. Tanım
özeti değişmiş çalışmanın önceki zinciri mevcut kaynak repository'sinin kuralına
göre yeniden başlar; dönem raporu kendi benzerlik/eşleştirme algoritmasını eklemez.

## Tarihsel doğruluk

- Varsa Aşama 2 receipt → step → frozen unit bağı, o çalışmada kullanılan ad,
  sorgu, platformlar, sözleşme sürümü ve profil revizyonunu sağlar.
- Bağımsız komutla üretilmiş sosyal run zaten username, platformlar ve tanım
  özeti taşır. Geçmiş izleme adı saklanmıyorsa ID + bu alanlar kullanılır.
- Eski bağımsız ransomware run yalnız tanım özeti taşıyorsa geçmiş sorgu/ad
  tahmin edilmez. Watch ID, definition SHA, kaynak çalışma kimliği ve kayıtlı
  eşleşme satırı gösterilir. Güncel ad gösterilecekse açıkça "bugünkü ad" denir.
- Güncel insan kararı eski olayın o günkü kararı gibi gösterilmez. İnceleme
  kararı dahil edilecekse olay anına ait event kullanılmalı; bu mümkün değilse
  bugünkü karar ayrı etiketlenmeli veya ilk sürümde çıkarılmalıdır.
- Tarihsel rapor bugünkü `analyze` çıktısını eski snapshot diye sunmaz.

## Hata ve kapsam boşluğu

Bir kaynak için dört farklı durum korunur:

| Durum | Gösterilecek anlam |
| --- | --- |
| Başarılı kontrol, sıfır değişim | Kayıtlı kontrol tamamlandı; yeni değişim bulunmadı. |
| Kısmi / başarısız / kesilmiş kontrol | Bu dönem tam görünürlük sağlanamadı; çalışma kimliği ve kaynak durumu gösterilir. |
| Dönemde kontrol yok, daha eski başarılı kayıt var | Dönem içinde kontrol edilmedi; son başarılı sıra/tarih ayrıca gösterilir. |
| Hiç geçerli geçmiş yok | Bilgi yok; "temiz" veya "kaynak çalışmıyor" denmez. |

Başarısız ransomware refresh ortak kaynağa aittir. Aşama 2 adım bağı yoksa
tek başına bu hata belirli bir watch'ın çalıştırılmak istendiğini kanıtlamaz.
Atlanan watch yalnız seçilmiş session step kanıtıyla böyle etiketlenir.

Dönemdeki son başarılı kayıt tek başına 24/168 saat boyunca kesintisiz kapsama
kanıtı değildir. Linux zamanlama dosyaları ayrı özellik olarak üretilir;
rapor bu dosyalardan beklenen tur sayısı çıkarmadığından "kaç kontrol
kaçırıldı" sayısı uydurulmaz. IOC/claim genel kaynak yenilemeleri
hedefe özel arama gibi sunulmaz; aynı kaynak hatası her watch için tekrar sayılmaz.

Temizlenmiş ham observations için `cleanup_runs` bağlamı ayrıca okunabilir.
Mevcut temizlik yalnız bağlı olmayan eski gözlemleri kaldırır; bu, bulgu/run
geçmişinin silindiği anlamına gelmez. Kapsam bütünlüğü hakkında kanıt yoksa
"tüm tarihçe mevcut" garantisi verilmez.

## Kapsam ve sonraki kuruluş filtresi

İlk varsayılan bütün yerel kayıtlı varlık/izleme kapsamıdır. `--domain` yalnız
kesin asset bağlantısı olan marka/dış yüzey kayıtlarını seçer; aynı isimden
sosyal veya ransomware izlemesi sahipliği çıkarılmaz.

**Henüz uygulanmayan genişleme:** `--organization`, bugünkü etkin açık domain/watch bağlantılarının
ID kümesini alır. Domain ve watchlar kendi ailelerine uygulanır; paylaşılan
varlık/izlemeler başka kuruluşa aitmiş gibi yeniden etiketlenmez. Rapor,
"bugünkü kayıtlı kapsamın son 1/7 günlük yerel kayıtları" diye açıklanır;
kuruluş bağlantısının tüm dönemde etkin olduğu iddia edilmez. `scope_resolved_at`
ve kullanılan link/target kimlikleri JSON'da yer alır. Kuruluş/domain filtreleri
ilk sürümde birlikte kullanılmaz. Tarihsel ilişki üyeliği filtresi ayrı ileriki
özelliktir; mevcut ilişki event'leri bunu kanıtlamadan geçmiş kapsam kurulmaz.

Genel feed/claim sağlığı seçili kapsam için sadece bağlamdır; başka kuruluşun
ilgisiz claim/watch satırları rapora taşınmaz. Kuruluş ilişkisi sahiplik veya
çok müşterili erişim yetkisi kanıtı değildir.

## Küçük okuma sözleşmesi

Çalışan servis `PeriodicChangesService.show(days=1, domain=None, limit=100)`
ve küçük `PeriodicChangesRepository.read(window, scope, limit_per_section)`
portudur. Kesin alanlar `domain/periodic_changes.py` içindedir. Aşağıdaki
geniş model listesi ilk tasarım notudur; kuruluş alanları henüz uygulanmadı:

- `PeriodicWindow(start_at, end_at, days)`.
- `PeriodicScope(kind, organization_id, asset_values, username_watch_ids,
  ransomware_watch_ids, ransomlook_watch_ids, resolved_at, link_ids)`.
- `PeriodicChangeEvidence(family, source, record_id, run_id, item_id,
  asset_value, watch_id, action, local_recorded_at, source_observed_at,
  previous_run_id, source_run_id, definition_sha256, display_value,
  evidence_reference, historical_definition_available)`.
- `PeriodicSourceCoverage(source, scope_kind, scope_id, last_run_id,
  last_run_sequence, last_status, last_recorded_at, last_complete_run_id,
  last_complete_recorded_at, window_run_count, complete_count, partial_count,
  failed_count, interrupted_count, coverage_state)`.
- `PeriodicSection(family, changes, baselines, failure_evidence,
  total_change_count, total_baseline_count, total_failure_count,
  shown_count, omitted_count)`.
- `PeriodicChangesReport(window, scope, sections, coverage, generated_at,
  notes, schema_version)`; tek bir global threat_count yoktur.

Tek küçük port: `PeriodicChangesRepository.read(window, scope,
limit_per_section) -> PeriodicChangesSnapshot`. Uygulama servisi pencere/kapsam
ve rapor sınıflandırmasını kurar. SQLite adaptörü mevcut source row
validator'larını kullanır; SQL/JSON ayrıştırma terminale veya domain'e sızmaz.
İlk sürümde yeni genel sorgu motoru, materialized view veya kalıcı rapor tablosu
kurulmaz. Gelecekteki `--organization` kapsam çözümü mevcut küçük ilişki
portundan yararlanabilir; bugünkü komut bu seçeneği kabul etmez.

Bütün aileler **tek read-only SQLite transaction** içinde okunur. Örneğin rapor
sosyal run'ı görüp aynı transaction'ın item'larını görmemek gibi karışık kesit
üretmez. Giriş noktası port/adaptörleri bağlar; ağ adaptörüne ihtiyaç duyulmaz.

## Sınırlar ve doğruluk

- Varsayılan bölüm görünüm sınırı 100; `--limit` 1–500. Bu kaynak tarama sınırı
  değildir; yalnız mevcut raporun gösterilen satır sayısını belirler.
- Toplamlar pencere/kapsam/eylem filtresinin tamamına göre hesaplanır.
  `LIMIT` uygulanmış satırlardan tam toplam türetilmez. Her bölüm gösterilen ve
  gösterilmeyen satır sayılarını belirtir; JSON da kesintiyi gizlemez.
- Baseline, değişim ve hata bölümleri ayrı sayılır. Kaynaklar arası veya aynı
  kuruluşun çoklu watch'ları arasında örtüşme global tekilleştirme diye sunulmaz.
- Savunmacı başlangıç sınırı: bir kapsamda 10.000 seçili run / 50.000 seçili
  item semantik doğrulaması. Taşma sessiz truncation veya boş başarı değildir;
  açık sınır hatası ve domain/kuruluş filtresi önerisi verir. Sınırlar ölçümle
  değişebilir; uzun süren SQL için yapılandırılmış süre/iptal sınırı düşünülür.
- Bozuk seçili kayıt, kopuk previous/source run veya hash uyuşmazlığı raporu
  durdurur. Beklenen kaynak hatası geçerli veri olarak hata bölümünde kalır.
- Yeni indeks gerekirse gerçek sorgu/kapasite ölçümüyle ayrı küçük migration
  yapılır; bu plan sırf varsayımla yeni şema zorunluluğu oluşturmaz.

## Kabul testleri

1. Başlangıç tam dahil / bitiş tam hariç; 24 ve 168 saat; timezone/naive saat ve
   bool days reddi; zaman bir kez okunur; farklı kaynak saati yerel saati değiştirmez.
2. Yeni finding ile tekrar observed ayrımı; aynı domainin iki kural sürümü ve
   çoklu kaynak kanıtları; kaynak/aday sayıları birbirine karıştırılmaz.
3. Sosyal baseline ayrımı; önceki run pencere dışında; failed run'ın boş başarı
   olmaması; artık raporlanmayan profilin "silindi" diye etiketlenmemesi.
4. TC/RL ilk ölçüm ve sonraki added/updated/removed; kaynaklar ayrı; exact
   `source_run_id`; eski kaynak snapshot'ından yeni fark uydurulmaması.
5. Kaynak başarısızlığı, partial, interrupted, dönemde kontrol yok ve hiç kayıt
   yok birbirinden ayrılır. Ortak refresh hatası watch sayısı kadar çoğaltılmaz.
6. Tarihsel ad/sorgu veya review kararı güncel veriden uydurulmaz; frozen plan
   varsa doğru snapshot, yoksa açık kimlik/hash ve sınırlılık gösterilir.
7. Kuruluş filtresi yalnız açık etkin ilişkileri kullanır; paylaşılmış watch
   örtüşmesi global uniq sayılmaz; ilgisiz kuruluşun kayıtları karışmaz.
8. Exact total / omitted_count görünüm limitinden bağımsız; eşit timestamp
   sıralaması deterministiktir; aşırı sınır ve bozuk kayıt açıkça reddedilir.
9. Başka bağlantıdan rapor sırasında yazma denenince tek tutarlı okuma kesiti;
   DB byte karşılaştırması, ağ istemcisi spy, inbox/read_at değişmezliği.
10. CLI/JSON başarılı-sıfır, baseline, değişim, hata ve eksik kapsam örnekleri;
    terminal kontrol/markup karakterleri güvenli gösterilir. İlgili testler ve
    `./scripts/check` geçmeden özellik tamamlandı diye yayımlanmaz.
