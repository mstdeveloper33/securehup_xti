# Dark web, ransomware iddiası ve toplu domain maruziyeti

XTI 0.195.1 seçilmiş kaynaklardaki kuruluş/tedarikçi kayıtlarını tek bir
kanıt ve inceleme akışında gösterir. Bu özellik genel Tor tarayıcısı değildir.
Bir ransomware ilanı, toplu Lunar sonucu veya AIL metadata eşleşmesi
**kaynak iddiasıdır**; otomatik olarak doğrulanmış ihlal anlamına gelmez.

## Desteklenen kaynaklar

| Kaynak | Motorun kullandığı veri | Ağ nerede kullanılır? | Durum |
|---|---|---|---|
| RansomLook | Önceden saklanmış kamu ransomware iddiası | Mevcut `ransomware refresh` akışında | Seçili; atıf ve veri koşulları korunur |
| ThreatCluster | Önceden saklanmış kamu ransomware iddiası | Mevcut `ransomware refresh` akışında | Kişisel/açık profil; yazılı izin olmadan ticari profilde kapalı |
| XposedOrNot verified-domain | Yalnız geçmiş maskeli kayıtlar | Yeni ağ kullanımı yok | 26 Kasım 2026 kararıyla kapalı; eski provider/kanıt salt okunur |
| XposedOrNot password corpus | Yeni veri alınmaz | Ağ kullanımı yok | 26 Kasım 2026 kararıyla kapalı; müşteri akışına sunulmaz |
| Lunar/Webz.io Domain Exposure | Son 12 aylık toplu employee/client ve breach/infostealer sayı/tarihleri | Yalnız açık `lunar-refresh` çağrısında | Anahtarsız ve canlı doğrulandı; bireysel credential/PII alınmaz |
| AIL Framework tracker | Hash bağlı nesne, zaman, ağ/tür ve kesin firma eşleşmesi | Ayrı AIL sistemi toplar; XTI yalnız yerel normalize zarfı alır | Motor bağlantısı hazır; gerçek AIL kurulumu, yasal kaynak ve canlı olay kabulü bekliyor |

Eski şema93 HIBP ve şema94+ XposedOrNot kayıtları veri kaybını önlemek için
okunabilir. İki kaynak da yeni profillerde seçilemez; verified-domain ve parola
ağ adaptörleri üretim composition'ında kurulmaz. Ayrı tarihî `notices` modülü
bu kararla yeniden etiketlenmez.

AIL yeraltı toplama sistemi olarak seçildi; fakat XTI AIL'i kurmaz, Tor'a
bağlanmaz ve giriş/CAPTCHA aşmaz. Gerçek AIL kurulumu ile forum/pazar/Tor
kaynağının erişim ve veri işleme hakkı henüz seçilmedi. Ham stealer-log
sağlayıcısı da eklenmedi. Bu dış gereksinimler tamamlanmadan “bütün dark web
taranıyor” denmez.

## İlk kullanım

Mevcut kurulumda önce şemayı yükselt:

```sh
./xti migrate
```

Kuruluş ve domain daha önce eklenmediyse:

```sh
./xti organizations add "Örnek Şirket" --reason "Açık izleme kapsamı"
./xti organizations link KURULUS_ID --kind domain --value example.com \
  --reason "Kuruluşa ait doğrulanmış domain"
```

Ransomware kaynak snapshot'larını mevcut toplayıcıyla güncelle, ardından P05
profilini oluştur:

```sh
./xti ransomware refresh --source ransomlook
./xti darkweb profile-add --name "Örnek dark web izlemesi" \
  --organization KURULUS_ID --source ransomlook
./xti darkweb plan PROFIL_ID
./xti darkweb run PROFIL_ID
```

İlk başarılı tur sessiz başlangıçtır. Sonraki turlar yalnız yeni veya
kanıtı değişen kayıt için değişiklik üretir. Kaynak hatası boş başarıya
dönüştürülmez; önceki başarılı snapshot görünür kalır.

## Anahtarsız toplu domain maruziyeti

Profilde `lunar_domain` seç ve kuruluşa bağlı kesin domain için açık çağrı yap:

```sh
./xti darkweb profile-add --name "Örnek maruziyet izlemesi" \
  --organization KURULUS_ID --source lunar_domain
./xti darkweb lunar-refresh PROFIL_ID example.com
./xti darkweb source-runs --profile-id PROFIL_ID --provider lunar_domain
./xti darkweb source-records --profile-id PROFIL_ID --provider lunar_domain
```

Sonuç yalnız `total`, `employee`, `client`, `infostealer`, `data_breach`
sayıları ile rapor dönemi ve ilk/son tarihi taşır. Kişi, e-posta, parola,
login URL'si veya ham sağlayıcı yanıtı saklanmaz. `pending`, raporun henüz
hazırlanmakta olduğunu söyler; sıfır olay anlamına gelmez. `complete` ve
sıfır olay da yalnız bu kaynak/pencere için başarılı boş sonuçtur, domainin
güvenli olduğunu kanıtlamaz.

## Ayrı AIL sistemiyle yeraltı eşleşmesi

AIL ayrı bir sunucuda seçilmiş ve yetkili kaynakları toplar. İşletici
connector'ü ham içeriği XTI'a göndermez; yalnız `xti-ail-v1` metadata zarfı
üretir. Örnek biçim [examples/ail-tracker-envelope.json](../examples/ail-tracker-envelope.json)
dosyasındadır. Önce yazmasız doğrula, sonra aynı hash ile al:

```sh
./xti darkweb profile-add --name "Örnek AIL izlemesi" \
  --organization KURULUS_ID --source ail_tracker
./xti darkweb ail-preview PROFIL_ID examples/ail-tracker-envelope.json
./xti darkweb ail-import PROFIL_ID examples/ail-tracker-envelope.json \
  --expected-content-sha256 ONIZLEME_SHA256
./xti darkweb source-runs --profile-id PROFIL_ID --provider ail_tracker
./xti darkweb source-records --profile-id PROFIL_ID --provider ail_tracker
./xti darkweb run PROFIL_ID
```

Örnek zarf yalnız biçimi gösterir; gerçek kaynak sonucu değildir. Zarf en
fazla 2 MiB/1.000 kayıt olabilir ve yalnız AIL 7.x sürüm/commit'i, hash bağlı
nesne/kanıt, tür, ağ sınıfı, zaman, kuruluş kapsamındaki ad/domain eşleşmesi
ile iddia türünü taşır. Ham içerik, alıntı, kaynak/Tor adresi, credential,
cookie, kullanıcı hesabı veya dosya alanı eklenirse bütün zarf reddedilir.

## Sonuçları görme ve inceleme

```sh
./xti darkweb findings --profile-id PROFIL_ID --limit 100
./xti darkweb finding-show BULGU_ID
./xti darkweb evidence-show KANIT_ID
./xti darkweb report --profile-id PROFIL_ID
./xti darkweb changes --profile-id PROFIL_ID
./xti inbox list
```

Bir analist, bulgunun güncel kanıt ve gözlem sürümüne karar bağlar:

```sh
./xti darkweb review BULGU_ID --evidence-id KANIT_ID \
  --observation-revision GOZLEM_SURUMU --decision uncertain \
  --reason "Kaynak iddiası bağımsız doğrulama bekliyor"
```

Kararlar `relevant`, `unrelated`, `uncertain`, `confirmed_incident` veya
`resolved` olabilir. `confirmed_incident` bile otomatik atanmaz; insan
kararıdır. Kanıt değişirse eski karar korunur fakat bulgu yeniden inceleme
ister. Bir bulguyu vakaya dondurmak için:

```sh
./xti cases evidence-add VAKA_ID --type darkweb_monitoring \
  --evidence-id BULGU_ID --reason "İncelenen kaynak iddiasını dondur"
```

## Tarihî XposedOrNot kayıtları

XposedOrNot yeni müşteri kullanımına kapalıdır. Yeni profil, API anahtarı,
kuruluş anahtarı, domain yenilemesi veya parola sorgusu oluşturulamaz. Daha
önce alınmış maskeli credential kanıtları silinmez ve yalnız şu yollarla
okunabilir:

```sh
./xti darkweb credential-runs --profile-id PROFIL_ID
./xti darkweb credential-run-show TUR_ID
./xti darkweb report --profile-id PROFIL_ID
```

Eski bir profil `xposedornot_domain` içeriyorsa profil ve kanıt geçmişi
görüntülenir fakat yeni tur `source_retired` sonucu verir. Düzenli izlemeye
devam etmek için profili `ransomlook`, `lunar_domain` veya kurulum şartları
tamamlanmışsa `ail_tracker` gibi etkin bir kaynakla güncelle. Kesinti anında
`running` kalmış eski credential turu yeni ağ isteği yapılmadan `darkweb
recover` ile `interrupted` kapatılabilir.

Önceki sürümlerde oluşturulmuş XposedOrNot secret dosyaları veri kaybı veya
hesap erişimi riski yaratmamak için yükseltme sırasında otomatik silinmez.
İşletici sağlayıcı anahtarını sağlayıcı tarafında iptal etmeli ve artık
gerekmeyen yerel secret dosyasını kendi secret yönetimi prosedürüyle
kaldırmalıdır. Şema ve provider kimliği tarihî kanıtın bütünlüğü için korunur;
eski HIBP kaydı XposedOrNot verisiymiş gibi yeniden etiketlenmez.

## Ortak kuyrukla düzenli analiz

`darkweb-monitor` yalnız saklı kaynakları analiz eder ve dış HTTP denemesi
sıfırdır. `./xti darkweb plan PROFIL_ID` çıktısındaki
`queue_scope_sha256` değerini kullan:

```sh
./xti source-jobs plan KAPSAM_SHA256 --type sha256 \
  --source darkweb-monitor --darkweb-profile PROFIL_ID \
  --darkweb-revision PROFIL_SURUMU --darkweb-force
./xti source-jobs submit KAPSAM_SHA256 --type sha256 \
  --source darkweb-monitor --darkweb-profile PROFIL_ID \
  --darkweb-revision PROFIL_SURUMU --darkweb-force \
  --idempotency-key p05-periodic-001
./xti source-jobs worker --job-id IS_ID
./xti source-jobs result IS_ID
```

Plan, submit, durum ve sonuç ağ kullanmaz. Worker profil kimliğini, sürümünü
ve kapsam hash'ini yeniden doğrular. Çekirdek tur tamamlandıktan sonra kuyruk
makbuzu kesilirse açık retry aynı turu yeniden kullanır. Emekli XposedOrNot
kaynağı bu işten veya başka bir üretim composition'ından çağrılamaz.

## Firma platformu ve engine

Salt-okunur engine v1 işlemleri:

- `darkweb.capabilities`
- `darkweb.profiles`, `darkweb.profile.show`, `darkweb.plan`
- `darkweb.runs`, `darkweb.run.show`
- `darkweb.findings`, `darkweb.finding.show`, `darkweb.evidence.show`
- `darkweb.reviews`, `darkweb.changes`
- `darkweb.credential.runs`, `darkweb.credential.run.show`
- `darkweb.source.runs`, `darkweb.source.run.show`
- `darkweb.source.records`, `darkweb.source.record.show`
- `darkweb.ail.preview`
- `darkweb.report`

Platform aynı okumaları ve firma-çitli `profile.add/update`, `run`, `review`,
`recover`, `lunar.refresh` ve `ail.import` yazmalarını destekler.
`credential.refresh` 0.195.1'de sözleşmeden kaldırılmıştır. `lunar.refresh`
açık ağ operasyonudur; AIL önizleme/içe alma dış
ağ kullanmaz. Platform genel JSON isteği 65.536 baytla sınırlıdır; daha büyük
ama 2 MiB altındaki güvenilen işletici zarfı yerel CLI dosya akışında alınır.
Yazmalar güvenilen
backend'in verdiği güncel `expected_workspace_id` ve tekrar anahtarını ister.
`platform request --describe` makine sözleşmesini döndürür.
`organization.content` yanıtındaki `darkweb_monitoring` alanı profil/kaynak
durumunu ve sınırlı bulgu sayfasını sağlar. Kimlik doğrulama, kullanıcı rolü
ve HTTP endpoint'i tüketici .NET/backend ekibinin sorumluluğundadır; analiz
kurallarını yeniden yazması gerekmez.

## Hata, kurtarma ve yedek

- `not_checked`: kaynak hiç çalıştırılmadı.
- `complete`: bu kaynak için başarılı snapshot var; boş sonuç güvenlik kanıtı değildir.
- `failed` / `interrupted`: son deneme tamamlanmadı; önceki başarılı kanıt korunur.
- `retained_not_observed_in_latest_complete_run`: bulgu geçmişte görüldü,
  son başarılı turda görülmedi; otomatik silinmez.

Yarım kalan analiz veya P11 kaynak turu otomatik tekrar edilmez. Tarihî bir
credential turu da yeni ağ isteği yapılmadan kesilmiş duruma alınabilir:

```sh
./xti darkweb recover TUR_ID
```

Bu işlem turu `interrupted` kapatır ve önceki kanıtı korur. Firma kurulumunda
`platform backup/restore` çekirdek ile iş kuyruğunu birlikte taşır; restore
yeni workspace kimliği üretir ve eski kapsamlı yazma isteklerini reddeder.
Etkin kaynakların anahtar dosyaları bilinçli olarak SQLite yedeğine dahil
değildir; ayrı güvenli secret yedeği işletici sorumluluğundadır. Emekli
XposedOrNot secret'ı yedek gereksinimi değildir.

## Sınırlar ve kabul

- Profil başına en fazla 10.000 güncel bulgu, kaynak kesitinde 100.000 kayıt,
  1.000 kuruluş/tedarikçi hedefi ve 64 MiB dondurulmuş girdi vardır.
- Kuruluş başına en fazla 10.000 P11 kaynak turu, 100.000 güncel kaynak kaydı
  ve 1.000.000 kaynak değişikliği vardır; AIL zarfı en fazla 1.000 kayıttır.
- Okuma sayfası en fazla 100 kayıt ve 2 MiB'dir.
- Kuruluş/domain eşleşmesi tam normalleştirilmiş ad veya kesin domain bağıdır;
  benzer ad tek başına eşleşmez.
- İki firmada ayrı ayrı 10.000 bulgu ve 30 değişmeyen tur kabul edildi.
  Değişmeyen tur yeni kanıt/değişiklik/bildirim üretmedi. Tek değişiklik
  firma başına yalnız bir kanıt, bulgu değişimi ve bildirim üretti.
- 40 gerçek platform okumasında 100 kayıt sayfası için en kötü p95
  0,273171 saniye; tepe ana süreç belleği 147,11 MiB ölçüldü.
- P11 kabulünde iki firma alanında firma başına1.000 AIL kaydı üç turda
  işlendi: ilk tur1.000 yeni, ikinci tur1.000 değişmeyen, üçüncü tur yalnız1
  güncelleme üretti. En yavaş içe alma0,412378 sn, analiz0,408525 sn, tepe
  RSS70,16 MiB ve ağ isteği0 ölçüldü.
- `securehup.com` canlı Lunar çağrısı 2025-11-01–2026-10-31 döneminde sıfır
  toplu olayla tamamlandı; bu domainin güvenli olduğunun kanıtı değildir.
- Bu sentetik kapasite kabulü gerçek AIL forum/pazar kapsamı, bütün internet
  doğruluğu veya hukuk/uyumluluk
  sertifikası değildir.

Şema99→100 geçişi de önce doğrulanmış yedek alır, mevcut P05 kimlik/sequence
değerlerini korur ve kesilirse eski veritabanını değiştirmez. Şema92→94 ve
şema93→94 tarihî geçişleri aynı güvenlik sınırını korur. Şema93 HIBP ve daha
sonraki XposedOrNot provider kimlikleri değiştirilmez; 0.195.1 yeni
XposedOrNot kaydı üretmez. Eski koda dönüş, yükseltme öncesi yedeği yeni boş alana
restore ederek yapılır. Tasarım kararı [ADR0189](decisions/0189-darkweb-and-credential-evidence.md),
tarihî sağlayıcı kararı [ADR0190](decisions/0190-xposedornot-credential-source.md),
güncel emeklilik kararı [ADR0201](decisions/0201-retire-xposedornot-new-use.md),
ölçüm ve açık dış bağımlılıklar [P05 teslim kartında](roadmap/P05_DELIVERY.md),
kaynak genişlemesi [P11 teslim kartında](roadmap/P11_DELIVERY.md),
tasarım [ADR0198](decisions/0198-minimized-underground-source-intake.md),
kaynak/ticari kararlar [NOTES N-048](../NOTES.md#n-048--p05-dark-web-ve-credential-kaynaksaklama-sınırı)
tutulur.
