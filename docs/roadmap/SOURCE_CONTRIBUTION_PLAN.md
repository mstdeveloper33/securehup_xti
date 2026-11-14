# Kaynak Katkısı ve Ücretsiz Kaynak Genişlemesi

**Durum: ÖLÇÜM VE KARAR NOTU TAMAMLANDI — 0.133.0.**
14 Kasım 2026. `sources contribution DOMAIN` terminal/JSON görünümü ve
salt okunur servis uygulanmıştır; yeni şema veya zorunlu ücretli API yoktur.
**Yeni sağlayıcı eklenmedi:** bağımsız katkı ve erişim/lisans koşulları
kanıtlanmadan adaptör seçilmedi. [Değerlendirme notu](SOURCE_PROVIDER_EVALUATION.md)
bu koşullu kararı açıklar. Common Crawl dış erişim sorunu açık kalır.
Çalışan kapsam [STATUS](../STATUS.md) dosyasındadır.

## İlk somut teslim

Kayıtlı bir domain için, **yalnız eldeki yerel kanıtı** okuyarak şunları
göstermek: her kaynağın getirdiği farklı aday adresleri, başka kaynaklarda
da görülen adresleri, yalnız o kaynakta kayıtlı adresleri ve kaydedilmiş
çalışmaların tamamlanma durumları. Ayrıntıda adresler ve dayanak kayıt
kimlikleri bulunur; yalnız sayaç gösterilmez.

Alt alan adı keşfi ile benzer marka/domain araması ayrı kalır. Bu rapor
internetin yüzde kaçının tarandığını, kaynağın kaçırdığı gerçek tehditleri,
bir kaynağın doğruluk oranını veya tek başına kaldırılabileceğini ölçmez.

## Mevcut kayıtların sağladığı ve sağlamadığı kanıt

| Mevcut yapı | Güvenilir ölçüm | Sınır |
| --- | --- | --- |
| [source_readiness.py](../../src/xti/adapters/source_readiness.py), `_scan_rows`, `_surface_rows` | Son kayıt, son başarı, eski/eksik kaynak durumunu gösteren yaklaşım yeniden kullanılabilir. | Yalnız son kayıt oran hesaplamaya yetmez. IOC okumaları ayrı bağlantılardadır; tüm görünüm tek çapraz-kaynak snapshot değildir. |
| [schema.py](../../src/xti/adapters/schema.py), `surface_candidates` ve `surface_candidate_sources` | Kök + kanonik aday domain + açık `provider` ile tekil aday kümeleri ve kesişimleri. | Kaynak kanıtında `discovery_run_id` yoktur. `recorded_at` yeni kanıtın ilk eklenme zamanıdır; aynı kanıtın her görülme zamanı değildir. |
| Aynı şemadaki `surface_discovery_runs` | crt.sh/theharvester için saklanan complete/partial/failed sayıları ve tamamlanmış boş sonuçlar. | Çalışma satırında aday üyeleri yoktur. Başlangıçta running satırı yazılmaz; sert kesintiyle hiç yazılamayan deneme bu geçmişten bulunamaz. |
| [sqlite_jobs.py](../../src/xti/adapters/sqlite_jobs.py), `ScanJob`/`ScanAttempt` ve `ScanResult` | İşteki provider, hedefler, typos, kural sürümü; deneme durumu ve sonuçtaki `candidate_domains`. | Birden fazla hedefli sonuç adayları hedef bazında ayırmaz. Sonucu olmayan kesilmiş denemede daha önce yazılmış adayları denemeye kesin bağlayan anahtar yoktur. |
| `observations` / `finding_observations` | Kaynak başvurusu ve bulgu kanıtı ayrıntıları. | `observations` tablosunda provider veya attempt yabancı anahtarı yoktur; yalnız serbest `source_name` önekinden güvenilir çalıştırıcı atfı yapılmaz. Bağlantısız gözlemler bakımda temizlenebilir. |
| [theharvester_archive.py](../../src/xti/adapters/theharvester_archive.py), `parse_theharvester_jsonl` | Kaynak adı `theHarvester:commoncrawl@COMMIT` / `theHarvester:waybackarchive@COMMIT` olarak korunur. | Kaynak başına tamamlanma kayıtları yapısal alt çalışma olarak saklanmaz; uyarı metni ayrıştırılarak ayrı başarı oranı üretilmez. |
| ATT&CK kaynak iddiaları | Saklanan bilgi sayıları. | Ek katalog başarılı senkronları tutar; başarısız indirme geçmişi olmadığından bundan başarı oranı çıkarılmaz. ATT&CK bu domain katkısı ölçümünün dışındadır. |

## Ölçüm kuralları

### Alt alan adı katkısı

İlk kabul, `surface:crt.sh` ile `surface:theharvester` arasındadır. Aynı
kök için bir domainin birden çok sertifika/kanıt satırı olması tekil aday
sayısını artırmaz. `pending`, `owned`, `rejected` adaylar toplam kayıtlı
katkıda korunur; güncel insan kararı ayrıca gösterilir. Kaynak sayısı
tehdit sayısı veya doğrulanmış sahiplik sayısı değildir.

Her kaynak için kanonik domain kümesi `S_k` olsun:

- Kaynağın farklı adayları: `|S_k|`.
- En az bir başka kayıtlı kaynakta da görülenler:
  `|S_k ∩ union(S_diger)|`.
- Yalnız bu kaynağın yerel kayıtlarında görülenler:
  `|S_k - union(S_diger)|`.
- Kaynak çifti örtüşmesi: `|S_a ∩ S_b|`; toplam farklı domain:
  `|union(S_k)|`. Kaynak satırlarının toplamı tekil genel toplam değildir.

Karşılaştırılan diğer kaynak hiç çalışmamış veya yalnız hata vermişse
karşılaştırma yeterliliği açıkça `insufficient_history` kalır. Yerel küme
farkı bir üstünlük puanına dönüştürülmez. Kaynakların tarih aralıkları ve
çalıştırılma sayıları farklıysa bu görünür olur.

Common Crawl/Wayback ayrımı, sonraki küçük dilimde **kanıt bileşeni** olarak
verilebilir: yalnız bilinen tam kaynak adı/commit biçiminde çözümlenir;
tanınmayan kaynak başvurusu ayrı tutulur. Bu alt toplamlar theHarvester
üst toplamına tekrar eklenmez ve ayrı sağlayıcı başarı oranı taşımaz.

### Marka araması katkısı

Yalnız `scan_jobs.targets == (istenen_domain,)` olan, sonucu saklanan
denemelerdeki `candidate_domains` kullanılacak. Kaynak atfı işteki açık
provider'dan gelir. Karşılaştırma grubu domain + `rule_version` + `typos`
seçimidir; farklı eşleştirme kuralları tek bir kaynak sıralamasına katılmaz.

Çok hedefli veya sonucu bulunmayan denemeler ayrı sayaçlarla gösterilir;
adayları domainlere tahminen dağıtılmaz. Kısmi sonucun gerçekten kaydedilen
adayları kullanılabilir; kapsam eksikliği korunur. Bu görünüm geçmişte
bulunan adaylarındır; bugün hâlâ geçerli tehdit veya insan kararına göre
doğrulanmış phishing listesi olarak adlandırılmaz.

### Deneme sonucu

`complete`, `partial`, `failed`, `interrupted`, `running` ayrı sayılır;
kuyrukta bekleyen iş henüz deneme değildir. Tamamlanma oranı
`complete / (complete + partial + failed + interrupted)` olur; payda ve
pay birlikte gösterilir. `running` paydaya girmez; payda sıfırsa oran
`null` olur. Surface geçmişinde yalnız bulunan üç terminal durum kullanılır.

Tamamlanmış boş sonuç başarılı çalışma sayılır; failed/partial sıfır kayıt
sonucu “veri yok” sayılmaz. Bu oran uygulamanın **saklanan denemeleri**
içindir; canlı kaynak erişilebilirliği veya sağlayıcının hizmet seviyesi
değildir. Yerel kesinti de bir denemeyi etkileyebilir.

İlk dilimde aday kümeleri saklanan tüm geçmişten hesaplanır; tarih aralığı
filtrelenmiş “yeniden keşif” iddiası eklenmez. Kaynak tarihi `observed_at`,
yerel kayıt tarihi ve deneme zamanı birbirinin yerine kullanılmaz.

## Şemasız mimari ve servis sözleşmesi

Uygulanan sözleşmeler:

```python
SourceContributionRepository.snapshot(asset_value, *, family) -> SourceContributionSnapshot
SourceContributionService.show(domain, *, family="all", detail_offset=0, detail_limit=100)
```

Snapshot; kayıtlı varlık kimliğini, doğrulanmış aday/kaynak üyeliklerini,
kapsamları ve ilgili deneme sonuçlarını donmuş modellerle taşır. Küme
hesabı, oran politikası ve yeterlilik kararı domain/uygulama katmanındadır.
Depolama, terminal veya ağ kütüphanesi bu katmanlara girmez.

Yeni `SQLiteSourceContributionRepository` yalnız `mode=ro` bağlantısında
**tek `BEGIN` snapshot** açar. Seçili kökü doğrular, mevcut SQLite kayıt
çözücülerini aynı bağlantıda kullanır ve gerekli çapraz alan kontrollerini
yapar: aday kökü, provider, deneme/iş bağı, sonuç hedefleri/durumu ve kanonik
domain. Hazır servisleri çağırıp farklı bağlantılardan sayaç toplamaz.

Okuma satır/JSON/bellek sınırları açık ve testli olur. İç okuma sınırının
aşılmasında eksik veriden kesin oran veya örtüşme sonucu üretilmez. Ayrıntı
sayfalaması hesaplanan toplamları etkilemez; kararlı sıralama, offset,
gösterilen/toplam adet ve `has_more` taşır.

Terminal yolu `sources contribution DOMAIN` ve `--family
surface|brand|all` seçimi; JSON aynı rapor modelinden üretilir. Komut
kaynağı çalıştırmaz, araç kurmaz, çalışma kilidi oluşturmaz veya migration
başlatmaz. Eksik veritabanı/kayıtsız kök açıklayıcı hata verir. İleride React
bağlantısı aynı uygulama servisini kullanabilir; REST teslimi bu aşamada yok.

## Önceden giderilen tekrar toplama sorunu

14 Kasım 2026 incelemesinde geçici SQLite ve sentetik theHarvester çıktısıyla
mevcut bir tekrar sorunu doğrulandı: aynı hostname/kaynak için digest aynı
kalırken parser `observed_at` alanına yeni `completed_at` yazıyor.
[sqlite_surface_candidates.py](../../src/xti/adapters/sqlite_surface_candidates.py),
`_save_validated` bunu aynı özet altında çelişen kanıt olarak reddediyor.
İlk çalışma iki aday/üç kanıtla kaydoldu; bir saat sonraki eşdeğer çalışma
reddedildi ve ikinci çalışma satırı oluşmadı. Bu ilk incelemeden sonra
0.131.0 düzeltmesi gözlem zamanını kaynak özetine dahil etti; eski kanıtlar
ve insan kararları korundu. Bu modül düzeltmeyi tekrar uygulamaz.

Tekrar edilen hostname yeni zamanda ayrı kaynak kanıtı olabilir; aday
kimliği ve tekil domain sayısı çoğalmaz. Genel çelişki denetimi korunur.
Bu yerel düzeltme, Common Crawl dış erişim sorununu çözmüş sayılmaz.

## Yeni ücretsiz kaynak kararı

Bu tasarım **yeni bir sağlayıcı seçmiyor**. Bilinen Common Crawl erişim
eksikliği tamamlanmış boş sonuç değildir; aynı arşivi başka araçtan çağırmak
bağımsız veri katkısı sayılmaz. Önce mevcut kaynakların gerçek katkısı ve
tekrar çalışabilirliği ölçülmeli. Mevcut
[pasif kaynak kabul kararı](../decisions/0124-passive-source-integrity-and-adapter-gate.md)
Subfinder CLI'ını hata/boş-sonuç ayrımı ve kanıtlanmamış bağımsız katkı
nedeniyle ertelemiştir; bu belge o kararı değiştirmez.

Ölçüm somut boşluk gösterirse sonraki adaptör için resmî endpoint, güncel
erişim/anahtar/kota koşulu, veri kullanma/dağıtma izni, lisans, pasif kapsam,
makine-okunur hata ayrımı ve örnek bağımsız katkı doğrulanacak. Koşulları
doğrulanmamış bir kaynak “ücretsiz/sınırsız” diye plana eklenmeyecek.
Bu incelemede yeni sağlayıcıya istek veya lisans araştırması gerekmedi.

## Kabul testleri ve sıra

1. Tek kök fixture'ı: A={a,b}, B={b,c}; toplam 3, kaynak başına 2,
   ortak 1, yalnız-kaynak katkısı 1. Aynı domainin çoklu sertifikası ve
   tekrarlanan çalışması toplamı artırmaz; başka kökün kayıtları sızmaz.
2. İnsan kararları korunur; rejected/owned/pending dağılımı kaynağa göre
   açıklanır. Eski ve yeni kayıt aynı domain kimliğinde sayılır.
3. complete-empty, partial-empty, failed, interrupted, running ve hiç
   deneme durumları farklıdır; oran paydası ve `null` davranışı doğrulanır.
4. Marka aramasında tek hedef/kural/typos grubu; çok hedefli ve sonuçsuz
   denemelerin dışarıda kalması; yalnız source_name'i bilinen bir adrese
   benzetilen gözlemin provider atfı yaratmaması doğrulanır.
5. Eksik/bozuk kanıt, yanlış ilişki, geçersiz zaman, beklenmeyen provider,
   okuma sınırının aşılması; yanıltıcı kısmi toplam yerine açık hata.
6. Ağ/süreç/kurulum/kilit çağrılarının yapılmaması; dosyaların değişmemesi;
   eşzamanlı yazmada tek SQLite snapshot tutarlılığı; ayrıntı sayfası
   değişirken toplamların ve terminal/JSON anlamının korunması.
7. Önce surface ölçümleri, sonra marka deneme-kaynağı ölçümleri; ardından
   gerçek yerel kullanım kabulü. Yeni ücretsiz adaptör ancak ölçülen boşluk
   ve resmî koşul incelemesi sonrasında ayrı teslim olur.
