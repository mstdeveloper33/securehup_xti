# Dark web, ransomware iddiası ve maskeli credential izlemesi

XTI 0.185.0 seçilmiş kaynaklardaki kuruluş/tedarikçi kayıtlarını tek bir
kanıt ve inceleme akışında gösterir. Bu özellik genel Tor tarayıcısı değildir.
Bir ransomware ilanı veya maskeli XposedOrNot eşleşmesi
**kaynak iddiasıdır**; otomatik olarak doğrulanmış ihlal, aktif hesap ya da
geçerli parola anlamına gelmez.

## Desteklenen kaynaklar

| Kaynak | Motorun kullandığı veri | Ağ nerede kullanılır? | Durum |
|---|---|---|---|
| RansomLook | Önceden saklanmış kamu ransomware iddiası | Mevcut `ransomware refresh` akışında | Seçili; atıf ve veri koşulları korunur |
| ThreatCluster | Önceden saklanmış kamu ransomware iddiası | Mevcut `ransomware refresh` akışında | Kişisel/açık profil; yazılı izin olmadan ticari profilde kapalı |
| XposedOrNot verified-domain | Maskeli e-posta ve ihlal adları | Yalnız açık `credential-refresh` çağrısında | Kod kabulü var; canlı domain kabulü API anahtarı ve sağlayıcıda doğrulanmış domain bekliyor |
| XposedOrNot password corpus | Parolanın görülme sayısı | Yalnız açık `password-check` çağrısında | Parola yerelde hashlenir; sonuç kalıcı değildir |

Eski şema93 HIBP kayıtları veri kaybını önlemek için okunabilir. HIBP yeni
P05 profillerinde seçilemez, varsayılan değildir ve verified-domain ağ
adaptörü kurulmaz. Ayrı tarihî `notices` modülü bu kararla yeniden
etiketlenmez; P05 yeni çalışmaları onu kullanmaz.

Genel forum/pazar/Tor crawler ve stealer-log sağlayıcısı seçilmedi. Bu
kaynaklar eklenmeden “bütün dark web taranıyor” denmez.

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
  --organization KURULUS_ID --source ransomlook --source xposedornot_domain
./xti darkweb plan PROFIL_ID
./xti darkweb run PROFIL_ID
```

İlk başarılı tur sessiz başlangıçtır. Sonraki turlar yalnız yeni veya
kanıtı değişen kayıt için değişiklik üretir. Kaynak hatası boş başarıya
dönüştürülmez; önceki başarılı snapshot görünür kalır.

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

## XposedOrNot verified-domain credential görünümü

Bu yol yalnız XposedOrNot hesabında önceden doğrulanmış ve XTI kuruluşuna açıkça
bağlanmış domain içindir. Anahtarları sohbete, komut argümanına veya repoya
yazma. Terminal gizli girişi ve ayrı kuruluş pseudonym anahtarı kullanılır:

```sh
./xti darkweb xposedornot-configure
./xti darkweb xposedornot-identity-create KURULUS_ID
./xti darkweb xposedornot-status KURULUS_ID
```

Profilde `xposedornot_domain` seçildikten sonra canlı çağrı açıkça yapılır:

```sh
./xti darkweb credential-refresh PROFIL_ID example.com
./xti darkweb credential-runs --profile-id PROFIL_ID
./xti darkweb report --profile-id PROFIL_ID
```

API anahtarı ve pseudonym anahtarı kullanıcı config klasöründe 0600,
klasörü 0700 izinle tutulur. Symlink, başka kullanıcıya ait veya grup/dünya
yazılabilir yol reddedilir. SQLite, JSON ve terminalde ham alias, ham e-posta,
parola, token, cookie veya session bulunmaz. Yalnız maskeli görünüm,
kuruluşa özel HMAC kimliği, domain ve ihlal adları saklanır. Credential
hiçbir hesapta denenmez. Pseudonym anahtarı kaybolursa eski maskeli kanıt
okunur; yeni turda aynı kimliklerle güvenilir değişim hesabı yapılamaz.

Sağlayıcı API'si anahtara bağlı tüm doğrulanmış domainleri tek yanıtta
döndürebilir. Adaptör yalnız komutta istenen ve kuruluş kapsamına bağlı kesin
domainin satırlarını kabul eder; diğer domainlerin adresleri motor sınırını
geçmez.

## Parola maruziyet kontrolü

```sh
./xti darkweb password-check
```

Parola komut satırı argümanı olarak verilmez; terminalde gizli alınır.
Legacy Keccak-512 özeti yerelde hesaplanır ve yalnız ilk 10 hexadecimal
karakter XposedOrNot parola API'sine gönderilir. Parola, tam hash, önek ve
sağlayıcının uzunluk/karakter bileşimi bilgisi SQLite'a, loga veya JSON
sonucuna yazılmaz. Kontrol zamanlanmaz ve geçmiş oluşturmaz. Önek sınırlı
bilgi sızdırdığı için özellik “sıfır bilgi” olarak sunulmaz. Sonucun boş
olması parolanın güvenli olduğunu kanıtlamaz.

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
makbuzu kesilirse açık retry aynı turu yeniden kullanır; XposedOrNot çağrısı
bu işe otomatik eklenmez.

## Firma platformu ve engine

Salt-okunur engine v1 işlemleri:

- `darkweb.capabilities`
- `darkweb.profiles`, `darkweb.profile.show`, `darkweb.plan`
- `darkweb.runs`, `darkweb.run.show`
- `darkweb.findings`, `darkweb.finding.show`, `darkweb.evidence.show`
- `darkweb.reviews`, `darkweb.changes`
- `darkweb.credential.runs`, `darkweb.credential.run.show`
- `darkweb.report`

Platform aynı okumaları ve firma-çitli `profile.add/update`, `run`, `review`,
`recover`, `credential.refresh` yazmalarını destekler. Yazmalar güvenilen
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

Yarım kalan analiz veya credential turu otomatik tekrar edilmez:

```sh
./xti darkweb recover TUR_ID
```

Bu işlem turu `interrupted` kapatır ve önceki kanıtı korur. Firma kurulumunda
`platform backup/restore` çekirdek ile iş kuyruğunu birlikte taşır; restore
yeni workspace kimliği üretir ve eski kapsamlı yazma isteklerini reddeder.
Anahtar dosyaları bilinçli olarak SQLite yedeğine dahil değildir; ayrı güvenli
secret yedeği işletici sorumluluğundadır.

## Sınırlar ve kabul

- Profil başına en fazla 10.000 güncel bulgu, kaynak kesitinde 100.000 kayıt,
  1.000 kuruluş/tedarikçi hedefi ve 64 MiB dondurulmuş girdi vardır.
- Okuma sayfası en fazla 100 kayıt ve 2 MiB'dir.
- Kuruluş/domain eşleşmesi tam normalleştirilmiş ad veya kesin domain bağıdır;
  benzer ad tek başına eşleşmez.
- İki firmada ayrı ayrı 10.000 bulgu ve 30 değişmeyen tur kabul edildi.
  Değişmeyen tur yeni kanıt/değişiklik/bildirim üretmedi. Tek değişiklik
  firma başına yalnız bir kanıt, bulgu değişimi ve bildirim üretti.
- 40 gerçek platform okumasında 100 kayıt sayfası için en kötü p95
  0,273171 saniye; tepe ana süreç belleği 147,11 MiB ölçüldü.
- Bu sentetik kapasite kabulü canlı XposedOrNot domaini, forum/pazar kapsamı, bütün internet
  doğruluğu veya hukuk/uyumluluk sertifikası değildir.

Şema92→94 ve şema93→94 geçişleri önce doğrulanmış yedek alır ve transaction
kesilirse eski veritabanı değişmez. Şema93 HIBP provider kimliği değiştirilmez;
yeni XposedOrNot kayıtları doğru provider adıyla yazılır. Eski koda dönüş,
yükseltme öncesi yedeği yeni boş alana
restore ederek yapılır. Tasarım kararı [ADR0189](decisions/0189-darkweb-and-credential-evidence.md),
sağlayıcı değişikliği [ADR0190](decisions/0190-xposedornot-credential-source.md),
ölçüm ve açık dış bağımlılıklar [P05 teslim kartında](roadmap/P05_DELIVERY.md),
kaynak/ticari kararlar [NOTES N-048](../NOTES.md#n-048--p05-dark-web-ve-credential-kaynaksaklama-sınırı)
tutulur.
