# Kanıta dayalı CTI analizi

XTI 0.183.0, daha önce saklanmış CTI varlıklarını, IOC ilişkilerini,
kuruluş domainlerini ve yerel MITRE ATT&CK kataloğunu ağ isteği yapmadan
birlikte değerlendirir. Çıktılar inceleme adayıdır; otomatik kimlik
birleştirme, aktör atfı, saldırı, ihlal veya zararlılık hükmü değildir.

P04 yeni ücretli API, LLM veya dış araç gerektirmez. Analizin kalitesi,
önceden kaydedilmiş kaynaklı CTI/IOC kanıtının ve yerel ATT&CK kataloğunun
kapsamıyla sınırlıdır. Boş sonuç bütün internette kayıt olmadığını göstermez.

## Ne üretir?

| Aday | Anlamı | Tek başına kanıtlamadığı şey |
|---|---|---|
| `identity` | Aynı türde iki CTI kaydının veya CTI ile ATT&CK kaydının ad/alias benzerliği | Aynı varlık oldukları |
| `technique` | Açık ATT&CK teknik kimliği ya da kabul edilmiş CTI–ATT&CK kimliği üzerinden TTP önerisi | Aktörün tekniği gerçekten kullandığı |
| `attribution` | Açık kaynak ilişkisi veya bağımsız çoklu kanıt üzerinden ilişkilendirme adayı | Kesin aktör atfı; tek ortak IP yeterli değildir |
| `tag` | Kaynak metninde kontrollü coğrafya/sektör ifadesi | Gerçek köken, kurban veya hedef sektör |
| `priority` | Kuruluşa ait tam domain/alt-domain/URL IOC ilişkisi ve kuruluş önemine göre inceleme önceliği | İhlal veya zararlılık olasılığı |

Her aday; kuralı, sinyalleri, özgün kaynak başvurularını, kısa kanıt
parçalarını, skor bileşenlerini, sınırlamaları ve insan karar geçmişini taşır.
Skor yalnız inceleme sırasıdır; olasılık değildir.

## İlk hazırlık

Yeni kurulum:

```sh
./setup
```

Mevcut kurulum:

```sh
./xti migrate
```

Analiz için önce kuruluş, kuruluşun domain bağı ve kaynaklı CTI/IOC kayıtları
olmalıdır. ATT&CK eşlemesi isteniyorsa resmî katalog açıkça alınır:

```sh
./xti organizations add "Örnek Şirket"
./xti organizations link KURULUS_KIMLIGI --kind domain --value example.com
./xti cti attack-sync
```

CTI/IOC ekleme ve ilişkilendirme örnekleri README'deki `cti entity-add`,
`ioc add` ve `cti relation-add` bölümündedir. P04 internetten yeni CTI
toplamaz; kayıtlı kanıtı analiz eder.

## Profil oluşturma ve çalıştırma

Kaynak güveni açıkça yapılandırılabilir. Aynı yayıncının iki farklı adı
bağımsız iki kaynak gibi sayılmamalıdır; bu nedenle `independence_group`
aynı verilmelidir.

```sh
./xti cti analysis-profile-add \
  --name "Örnek Şirket CTI" \
  --organization KURULUS_KIMLIGI \
  --criticality high \
  --identity-threshold 88 \
  --minimum-independent-sources 2 \
  --alert-score-min 60 \
  --trend-new-threshold 5 \
  --source-policy-json \
  '{"source_name":"analyst-report","reliability":80,"independence_group":"publisher-a"}'

./xti cti analysis-plan PROFIL_KIMLIGI
./xti cti analysis-run PROFIL_KIMLIGI --expected-revision 1 \
  --idempotency-key example-analysis-1
```

`analysis-plan` ağsızdır ve ortak kuyruğa verilecek `queue_scope_sha256`
değerini döndürür. İlk tamamlanan tur sessiz başlangıçtır: adaylar kaydedilir
ama geçmiş olmadığı için bildirim üretilmez.

## Sonuçları okuma

```sh
./xti cti analysis-report --profile-id PROFIL_KIMLIGI
./xti cti analysis-candidates --profile-id PROFIL_KIMLIGI --limit 100
./xti cti analysis-candidate-show ADAY_KIMLIGI
./xti cti analysis-evidence-show KANIT_KIMLIGI
./xti cti analysis-graph --profile-id PROFIL_KIMLIGI
./xti cti analysis-timeline --profile-id PROFIL_KIMLIGI
./xti cti analysis-trends --profile-id PROFIL_KIMLIGI
./xti cti analysis-source-quality --profile-id PROFIL_KIMLIGI
```

Listeler sequence cursor ile sayfalanır, en fazla 100 kayıt ve 2 MiB yanıt
bütçesi kullanır. Graf tur snapshot'ına bağlıdır; devam sayfasında
`--expected-snapshot` verilirse arada değişen graf sessizce karıştırılmaz.
Motor en fazla 100 düğüm ve 200 kenar döndürür. Ham CTI kaynak ilişkileri
`source_claim`, motor önerileri `candidate` olarak ayrı kalır.

Adayların gözlem durumu ayrıca gösterilir:

- `observed_in_latest_complete_run`: son başarılı turda yeniden görüldü.
- `retained_not_observed_in_latest_complete_run`: son başarılı turda yoktu;
  geçmiş ve karar silinmedi.
- `latest_run_failed_previous_observation_retained` ve benzerleri: son tur
  kapanmadı; önceki geçerli gözlem korunuyor.

Bir adayın görünmemesi otomatik çözülme veya yanlış alarm kararı değildir.

## İnsan incelemesi

```sh
./xti cti analysis-review ADAY_KIMLIGI \
  --evidence-id KANIT_KIMLIGI \
  --expected-revision 0 \
  --observation-revision 1 \
  --decision uncertain \
  --reason "Kaynaklar henüz yeterli değil" \
  --idempotency-key example-review-1
```

Genel kararlar `accepted`, `rejected`, `uncertain`; kimlik adayları için
`same_entity` ve `different_entity` seçenekleridir. Karar kanıt ve gözlem
sürümüne bağlanır. Kanıt değişince eski karar denetim geçmişinde kalır ama
güncel karar sayılmaz; `needs_review=true` olur.

Kabul edilmiş bir CTI–ATT&CK kimlik adayı, sonraki turda resmî ATT&CK `uses`
ilişkilerinden teknik adayı üretmek için kullanılabilir. Bu da yine otomatik
gerçek değildir.

## Trend ve bildirim anlamı

- `silent_baseline`: ilk tamamlanan tur.
- `stable`: kaynak kapsamı aynı ve değişim eşiği aşılmadı.
- `early_warning`: yeni/değişmiş aday sayısı profil eşiğine ulaştı.
- `coverage_changed`: gözlenen kaynak adları, kaynak politikası, ATT&CK
  snapshot'ı, kuruluş domaini veya analiz bütçesi değişti.

Kaynak kapsamı değişimi tehdit artışı diye sunulmaz. Alarm eşiğini aşan yeni
veya değişmiş adaylar ortak inbox'a girer. Aynı kanıtla tekrar çalışma yeni
kanıt, değişiklik veya bildirim üretmez. Tazelik gün düzeyinde hesaplanır;
worker'ın saat farkı sahte kanıt değişimi oluşturmaz.

Bir aday vakaya `cti_analysis` kanıt türüyle bağlandığında o anki aday,
kanıt ve inceleme durumu dondurulur; sonraki analiz vaka geçmişini değiştirmez.

```sh
./xti cases evidence-add VAKA_KIMLIGI --type cti_analysis \
  --evidence-id ADAY_KIMLIGI --reason "CTI incelemesine alındı"
```

## Ortak kuyrukla çalışma

Üretim benzeri kullanımda doğrudan `analysis-run` yerine mevcut kalıcı
kuyruk kullanılabilir. Önce `analysis-plan` çıktısındaki kapsam hash'ini al:

```sh
./xti source-jobs plan KAPSAM_SHA256 \
  --type sha256 --source cti-analysis \
  --analysis-profile PROFIL_KIMLIGI --analysis-revision 1

./xti source-jobs submit KAPSAM_SHA256 \
  --type sha256 --source cti-analysis \
  --analysis-profile PROFIL_KIMLIGI --analysis-revision 1 \
  --idempotency-key example-queue-1

./xti source-jobs worker --job-id IS_KIMLIGI
./xti source-jobs result IS_KIMLIGI
```

Bu adımın dış HTTP isteği üst sınırı ve gerçekleşen HTTP denemesi sıfırdır.
Kuyruk makbuzu özgün analiz turuna bağlanır. Profil sürümü veya kapsam hash'i
değişirse eski plan çalıştırılmaz.

## Kesinti, tekrar ve kurtarma

- Aynı idempotency anahtarı ve aynı istek önceki makbuzu döndürür.
- Aynı anahtar farklı istekle kullanılırsa işlem reddedilir.
- Kesilmiş `running` analiz kendiliğinden tekrar edilmez.
- Operatör `analysis-recover TUR_KIMLIGI` ile onu `interrupted` durumuna
  getirir; yeni çalıştırma yeni anahtar ister.
- Başarısız/kesilmiş tur eski tamamlanmış adayları silmez.
- Kaynak işi retry zinciri tamamlanmış makbuzu doğrular; belirsiz sonucu
  başarılı gibi göstermez.

## Firma platformu ve entegrasyon

Engine v1 bütün ağsız `cti.analysis.*` okumalarını; firma platformu v1
okuma ve yazmaları sunar. Platform yazmalarında `expected_workspace_id`,
idempotency anahtarı ve ilgili revision alanları zorunludur. Firma seçimi
istek JSON'undan değil güvenilen platform başlatıcısından gelir. Başka firma
kimliğiyle kayıt gösterilmez.

`organization.content` çıktısındaki `cti_analysis` alanı profil, son tur,
kaynak kapsamı, trend ve sayfalı adayları taşır. Bu motor kullanıcı/rol/oturum
yönetmez; .NET platformu güvenilir firma bağlamını ve yetkiyi sağlar.

## Kalıcı veri ve sınırlar

- Çekirdek şema: 92; kaynak işi yürütme modeli: 11; dış engine/platform JSON:
  v1; kuyruk şeması: 4.
- Dondurulmuş tur girdisi en fazla 64 MiB'dır.
- Profil başına en fazla 10.000 CTI varlığı, 50.000 ilişki ve 10.000 aday;
  daha küçük sınırlar profil içinde seçilebilir.
- Yerel ATT&CK okuması ayrıca varlık/ilişki/faz üst sınırlarına tabidir.
- Yedek/geri dönüş tur, kanıt, karar, inbox ve vaka bağlarını korur; geri
  dönen firma alanı yeni workspace kimliği alır.
- Genel STIX/TAXII, LLM özeti/çevirisi, otomatik attribution, credential
  doğrulama, web grafiği/harita çizimi ve yeni ücretli feed P04 kapsamında
  değildir.

Tasarım kararı: [ADR 0188](decisions/0188-cti-analysis-candidates.md).
Kabul ölçümleri: [P04 teslim kartı](roadmap/P04_DELIVERY.md).
