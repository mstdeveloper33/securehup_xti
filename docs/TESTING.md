# Değişikliğe göre test seçimi

Her küçük düzenlemede bütün test paketi çalıştırılmaz. Test kapsamı,
değişen davranışın etkilediği alanlara göre seçilir; tam paket teslim
öncesinde veya ortak altyapı değişikliği gerektirdiğinde çalıştırılır.

| Değişiklik | Kontrol |
| --- | --- |
| Yalnız belge/metin | İlgili örnek, bağlantı ve `git diff --check`; yeni davranış testi gerekmez. |
| Domain kuralı veya bir kaynak adaptörü | Sınır/hata senaryoları dahil ilgili test modülleri. |
| CLI / engine / platform sözleşmesi | Davranış testi, JSON/CLI uyumu, olumsuz parametreler ve ilgili firma izolasyonu. |
| Depolama / migration / kuyruk / ortak parser | İlgili entegrasyon, yedek/kurtarma/eski kayıt testleri ve bir tam paket. |
| Yeni özellik teslimi | Geliştirmede ilgili demet ve teslim öncesi bir tam regresyon. Sonradan değişen dar modülün etkilenen davranışları yeniden sınanır; yalnız belge değişirse tekrar gerekmez. |

IOC yaşam döngüsü için hedefli demet:

```sh
./scripts/python -m unittest -v \
  tests.test_ioc_lifecycle tests.test_ioc_lifecycle_contract \
  tests.test_cti_indicators tests.test_cti_feeds tests.test_certpl_warning \
  tests.test_cti_context tests.test_engine_contract \
  tests.test_platform_engine tests.test_platform_isolation tests.test_architecture
```

Tam paket:

```sh
./scripts/check
```

Rapor/gözlem değişikliği için ilgili demet:

```sh
./scripts/python -m unittest -v \
  tests.test_reports tests.test_report_observations tests.test_report_contract \
  tests.test_ioc_lifecycle tests.test_ioc_lifecycle_contract \
  tests.test_investigation tests.test_investigation_platform \
  tests.test_research_history tests.test_migrations \
  tests.test_news_migration tests.test_mentions_migration \
  tests.test_architecture tests.test_platform_engine \
  tests.test_platform_isolation tests.test_engine_contract tests.test_platform_backup
```

Şema 77 tesliminde ayrıca bir tam paket ve geçici alanda gerçek eski kodla
`scripts/check-engine-upgrade.py --output /tmp/YENI_KABUL_DOSYASI.json`
çalıştırılır. Bu script yerel eski commit'ten şema 75/kuyruk 2 hazırlar,
güncel şemaya yükseltir ve eski yedek + eski kodla geri dönüşü doğrular.
76 → 77'nin yalnız rapor tablosu eklemesi ilgili migration testindedir.

Tam koşu başladıktan sonra tek bir yeni modüle ek kontrol gelirse o modülün
ve bağlantılarının testleri son kodda yeniden çalıştırılır. Ortak şema,
kuyruk veya bütün işlemleri etkileyen değişiklikte tam koşuyu yenilemek
gerekebilir. Rapor hangi kodun tam paketle, son farkın hangi hedefli
testlerle doğrulandığını açıkça belirtir; önceki tam sonucu yeni kodun
birebir tam kabulü gibi göstermez.

`scripts/check-fast`, push CI'sinin seçilmiş ve zaman içinde büyümüş
regresyon demetidir; her yerel dosya değişikliğinin zorunlu kontrolü değildir.
Tam paket workflow'u elle veya sürüm etiketiyle çalışır. Bu düzenleme
mevcut CI kontrollerini kapatmaz. Yeni yaşam döngüsü testleri push demetine
de dahildir.

Raporların ortak araştırmaya bağlanması için iki yeni test modülü
`tests.test_research_reports` ve `tests.test_research_report_contract`
kullanılır. Belge/karar geçmişi, JSON/terminal uyumu, firma ayrımı,
aynı okuma kesiti, okuma/iş sınırları ve yedekten dönüşü kapsar.
Ortak araştırma/öncelik/geçmiş ve engine kayıt demetiyle birlikte
çalıştırılır; CI `check-fast` listesinde de bulunurlar.

Her kabul notunda kullanılan Python/ortam, komut, test sayısı ve sonuç
ayrı belirtilir. Örtüşen demet sayıları farklı test sayısı gibi toplanmaz.
Kontrollü test başarısı canlı sağlayıcı erişimini, 7/24 SLA'yı veya tüm
olası koşullarda hatasızlığı kanıtlamaz. Tavily/Nmap gibi ayrıca giriş veya
yetkili hedef gerektiren canlı kabuller kendi notlarında açık kalır.

## Sekiz maddelik kanıt paketi

`tests.test_evidence_delivery` ve `tests.test_source_workflows_v4`; eski
dayanak, tekrar/çakışma, firma sınırı, kesilen rapor işi, doğal kaynak olay
kimliği, migration ve kaynak hatası korumasını denetler. Günlük/iş şeması
etkilendiğinden bu paket için tam test bir kez çalıştırılır; her doküman
veya basit çıktı düzeltmesinden sonra yeniden çalıştırılmaz.

`scripts/check-evidence-acceptance.py` iki geçici firmada domain tarafından
doğrulanmış toplu fixture üretir. Ölçülen okuma/yazmalar ve kaynak işi
platform girişinden ayrı süreçlerle yürür; eşzamanlı okuma/yazma ve
iki firma yedek/restore kapsamı vardır. Varsayılan 1000 olay/firma,
500 varlık/firma; 10–600 saniye ve 100–5000 olay/firma aralıkları açıktır.
Tüm senaryonun ağ/tool erişimi child harness içinde kapalıdır; sonuç gerçek
müşteri telemetrisi veya 7/24 SLA olarak yorumlanmaz. Çıktı yeni ve repo
dışındaki dosyaya yazılır. Hata durumunda eşikler yükseltilmeden neden
incelenir. Kalıcı sonuçlar `ACCEPTANCE_REVIEW.md` içinde tutulur.


Tam metin, yeniden inceleme ve günlük arşivi için:

```sh
./scripts/python -m unittest -v \
  tests.test_publisher_documents tests.test_relationship_review_queue \
  tests.test_journal_storage tests.test_document_delivery_contract \
  tests.test_reports tests.test_evidence_delivery tests.test_research_reports \
  tests.test_brand_runtime tests.test_setup_brand tests.test_news_installation
```

PDF testleri gerçek pypdf alt sürecini kullanır; CI öncesi incelenen
`requirements/reports.txt` paketi kurulur. Geliştirme ortamında normal
`./setup` aynı sabit sürümü kurar. Arşiv testi gerçek SIGKILL + aynı planla
tekrar ve standart SQLite/platform yedeğinden dönüş içerir. Canlı yayıncı
kabulü ayrı izole veri alanında yapılır; otomatik testler internet istemez.
