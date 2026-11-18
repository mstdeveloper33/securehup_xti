# Araştırma, kimlik incelemesi ve firma listesi

18 Kasım 2026 · 0.164.0 · çekirdek şema 76 · kuyruk şeması 3.

Bu teslim yol haritasındaki 1–7 paketinin motor kapsamını birleştirir.
Mevcut vakalar, sosyal profiller ve saklanmış firma içerikleri aynı
araştırmada açılır. Kimlik ve metinden çıkarılan gösterge adayları ayrı,
gerekçeli insan kararlarıyla incelenir. Firma inceleme listesi bu kayıtları
öncelikleri ve dayanaklarıyla bir araya getirir.

## Güncelleme ve ilk kullanım

Çalışan worker'ı bitirdikten sonra kodu güncelle. Eski çekirdek veri alanında
`./xti migrate` çalıştır: şema 75 → 76 geçişi önce doğrulanmış yedek alır.
Yeni alan `./xti init` ile kurulur. Okuma komutları kendiliğinden migration
yapmaz. Firma alanında aynı komuta seçili firmanın `--data-dir` konumu verilir;
öncesinde `platform backup` ile çekirdek ve kuyruğu birlikte yedekle.
Eski şema 1/2 kuyruğu için ayrıca `./xti source-jobs migrate`;
firma kuyruğunda `./xti platform jobs-migrate --root KOK --company FIRMA`
gerekir. Bu geçiş kuyruk yedeğini ayrı alır; eski payload/event byte'ları ve
kimlikleri korunur. Salt okuma ve eski işler yeni kodla okunabilir.

```sh
./xti migrate
./xti source-jobs migrate
./xti research securehup.com --type domain --priorities
./xti review-queue --root-limit 25 --limit 20
./xti investigate list
```

İlk iki görüntüleme, veri toplamak için internete çıkmaz. Önceden toplanan
kayıtları ve insan kararlarını okur. Yeni kaynaklar için mevcut toplama
komutlarını veya aşağıdaki yönetilen işleri kullan.

## Vakalar, sosyal profiller ve firma içerikleri

- Vaka, ilişkilendirildiği kanıtın dondurulmuş kesitiyle görünür. Kapatma,
  yeniden açma, kanıtı kaldırma ve karar gerekçesi korunur. Vaka kapanması
  kaynak iddiasının geri çekilmesi veya tehdidin giderildiği anlamına gelmez.
- Sosyal profil özgün izleme, platform, profil durumu ve insan incelemesiyle
  gösterilir. Kuruluşun açık domain/izleme bağlantısı varsa domaine bağlanır;
  aynı kullanıcı adı tek başına kurum sahipliği sayılmaz. Son kaynak hatası,
  önceki başarılı profil gözleminden ayrı gösterilir.
- Firma içeriği özgün aramada kayıtlı domainlere ve makale URL'sine bağlanır.
  İçerik araştırması yeni Tavily isteği yapmaz; kayıt yoksa içerik üretmez.
  Haber/RSS kataloğu firma araması değildir. Firma araması Tavily ile ayrı
  yürütülür; anahtarın canlı kabulü N-004'te beklemektedir.

`research-history record DOMAIN --type domain --idempotency-key ANAHTAR` mevcut kalıcı inceleme
akışıdır. Yeni politika `research-priority-v7` olur; ilk v7 incelemesi yeni
başlangıçtır. Önceki model 1/2/3 incelemeleri özgün açılır, yeniden yazılmaz.
Araştırma modelinin sürümü 3 ve dış JSON zarfı v1 kalır.

## Kimlik adayları ve insan kararı

```sh
./xti investigate candidates 'Aranan aktör adı'
./xti investigate propose --kind entity SOL_KAYIT_ID SAG_KAYIT_ID --evidence 'https://kaynak.example/rapor' --reason 'İki kaydın aynı aktöre ait olabileceğini gösteren kaynak' --idempotency-key kimlik-adayi-1
./xti investigate show INCELEME_ID
./xti investigate decide INCELEME_ID --decision accepted --reason 'Kaynaklar incelendi' --expected-revision 1 --idempotency-key kimlik-karari-1
./xti investigate decide INCELEME_ID --decision withdrawn --reason 'Yeni kanıt eşleştirmeyi desteklemiyor' --expected-revision 2 --idempotency-key kimlik-karari-2
```

Büyük harfli değerler önceki komutların verdiği gerçek kimliklerle değiştirilir.
`--kind organization` kayıtlı kuruluşlar için de kullanılabilir. İki kayıt
aynı veri alanında olmalı; CTI varlıklarının türü de aynı olmalı. Aday arama
tam ad veya kayıtlı kaynak alternatif adını kullanır; alt dize/fuzzy eşleşme
ve otomatik birleştirme yapmaz. Kaynak referansı ve gerekçe zorunludur.

Kararlar `accepted`, `rejected`, `uncertain`, `withdrawn` olabilir.
Onay bir araştırma bağlantısıdır; kaynak kayıtlarının kimliği, isimleri ve
ilişkileri yerinde kalır. Geri alma eski kararı silmez. Eski karar sürümüyle
yazma reddedilir. Aynı tekrar anahtarı aynı isteğin özgün sonucunu döndürür;
anahtarı başka parametrelerle kullanmak reddedilir.

## Kayıtlı metinden gösterge adayları

```sh
./xti news list
./xti investigate extract --source news HABER_ID --idempotency-key rapor-adayi-1
./xti investigate extract --source mentions ICERIK_ID --idempotency-key firma-icerigi-1
./xti investigate list --kind report
./xti investigate show INCELEME_ID
```

Saklı başlık/özet üzerinde URL, IPv4/IPv6, MD5/SHA-1/SHA-256 ve `example[.]com`
gibi yazılmış domain adayları çıkarılır. Özgün metin, içerik özeti, kaynak
çalışması, metindeki başlangıç/bitiş konumu ve özgün yazım saklanır. Gösterge
değeri normalleştirilir; kaynak metin değiştirilmez. Kaynak özeti daha önce
kısaltılmışsa `source_text_truncated` bunu belirtir.

Bu sürüm tam makale/PDF indirmez. Normal dosya adlarını domaine benzetmemek
için düz metindeki her noktalı sözcük domain sayılmaz. Metinde geçme ilişkisi
`report_mentions_candidate` olarak kalır; otomatik IOC, zararlılık hükmü,
aktör atfı veya alarm yaratmaz. İnsan onayı da IOC kataloğuna örtülü yazmaz.
Metin en fazla 64 KiB, tek metin en fazla 200 farklı adaydır; sınır aşımı
eksik listeyi başarılı gibi kaydetmez.

## Firma geneli inceleme listesi

```sh
./xti review-queue --root-limit 25 --limit 20
./xti --json review-queue --root-limit 25 --limit 20
./xti review-queue --root-limit 25 --offset 20 --expected-snapshot ONCEKI_SNAPSHOT
./xti review-queue --root-offset 25 --root-limit 25
```

Kayıtlı varlıklar, IOC/CTI varlıkları ve bağımsız vaka/içerik/rapor kayıtları
birlikte incelenir. Aynı kayıt ortak listede tek kez gösterilir; hangi
köklerden bulunduğu korunur. Kaynakların güncel/eski/geri çekilmiş durumları
ayrı verilir. Farklı kaynak durumu tek başına mantıksal çelişki kararı değildir.

Liste iki ayrı sayfalamaya sahiptir: `root_offset/root_limit` araştırılan
başlangıç kayıtlarını, `offset/limit` o pencerenin sonuçlarını seçer.
Varsayılan 25, en fazla 100 kök; her kökte iki adım, 30 düğüm, 60 ilişki
incelenir. `coverage_complete=false`, `limitations`, `root_has_more` ve
`next_root_offset` eksik kapsamı açıklar. İlk pencerenin sırası bütün büyük
firma kataloğunun mutlak sıralaması gibi sunulmaz. Aynı sayfaya devam ederken
veri veya güncellik sınıfı değişirse `snapshot_changed` ile yeniden başlatılır.

## Kaynak işleri ve platform sözleşmesi

```sh
./xti source-jobs plan 1.1.1.1 --type ipv4 --source ripestat --source news:ncsc --source reports --record-review
./xti source-jobs submit 1.1.1.1 --type ipv4 --source ripestat --source news:ncsc --source reports --record-review --idempotency-key kaynak-akisi-1
./xti source-jobs worker --job-id IS_ID
./xti source-jobs result IS_ID
```

Plan internet çağırmaz; worker seçilen sağlayıcılara gider. RIPEstat IP'yi
sağlayıcıya sorar, hedef IP'yi taramaz. Haber adımı yayıncı akışını alır;
`reports` seçili alandaki en yeni 20 saklı haberi yerelde ayrıştırır. Daha
fazla haber varsa `has_more` ve kısmi kapsam korunur; diğer kayıtlar açık
`investigate extract` ile işlenebilir. Aynı içerik tekrarında aday çoğalmaz.

Engine ve firma platformu salt okuma işlemleri: `company.review`,
`investigation.candidates`, `investigation.list`, `investigation.show`.
Firma yazma işlemleri: `investigation.propose`, `investigation.extract`,
`investigation.decide`. Yazmalarda `expected_workspace_id` ve
`idempotency_key`; kararda ayrıca `expected_revision` gereklidir. Parametre
adları terminalle aynıdır; `propose` iki `{kind,id}` nesnesi, `evidence`
listesi ve `reason` alır. `platform request --describe` güncel sözleşmeyi verir.
Okuma gerçek firma alanına bağlıdır; başka firmanın kimliği geçerli sayılmaz.

Karar günlüğü 10.000 olay/32 MiB sınırındadır; otomatik silinmez.
Kuyruk 3, beş kaynak + son inceleme için altı adımı ve son anda gelen iptal
dahil 16 olay kaydını taşır. Eski kuyruk sessizce yükseltilmez; yeni v3 iş
kabulü/başlatılması explicit kuyruk geçişini ister.
Araştırma okuyucuları ayrıca satır/byte sınırları uygular, aşımda kısmi kapsam
bildirir. Daha yüksek kapasite mevcut bütünlük denetimini kaldırarak açılmaz.
Yeni ücretli servis veya Python paketi eklenmedi; mevcut sabit sürümlü
feedparser ve kaynak adaptörleri yeniden kullanılır.

## Ölçüm ve geri dönüş

```sh
./scripts/python scripts/check-engine-soak.py --duration 1800 --output /tmp/xti-soak-yeni.json
./scripts/python scripts/check-engine-upgrade.py --output /tmp/xti-upgrade-yeni.json
```

İki komut da yeni, geçici firma alanları kullanır; kullanıcı verisine
dokunmaz. İkincisi önceki commit'i yerel Git nesnelerinden okur. JSON hedefi
yeni ve repo dışında olmalıdır. [Kabul kaydı](ACCEPTANCE_REVIEW.md) gerçek
ortamı, süreyi, hacmi, başarısız denemeleri ve son sonuçları saklar.

Geri dönüş eski kodla yeni şemayı açmak değildir: yükseltme öncesi birlikte
yedek eski kodla boş bir firma köküne döndürülür. Kimlikler korunur, yeni
workspace kimliği üretilir; restore edilen bekleyen işler otomatik dış istek
göndermesin diye iptal edilir. Yükseltmeden sonraki yeni kayıtlar eski yedekte
yoktur; yükseltilmiş alan ayrıca korunmalıdır. Süreli kabul 7/24 hizmet veya
ölçülmemiş üretim kapasitesi garantisi değildir.
