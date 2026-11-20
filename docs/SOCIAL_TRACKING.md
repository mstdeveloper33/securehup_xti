# Firma sosyal hesaplarını inceleme ve düzenli takip

0.175.0 ortak araştırma, kayıtlı toplama profili ve kayıpsız sosyal arşivi
ekler. 0.174.0 önceki hesap adreslerini dönüşümlü kontrol eder ve sosyal takibi
ortak iş kuyruğu/worker'a bağlar. 0.173.0, birleşik sosyal keşfi firma incelemesi, gerekçeli insan kararı,
donmuş vaka kanıtı ve düzenli değişiklik takibine bağlar. Terminal ve
firma kapsamlı JSON aynı servisleri kullanır. Bright Data anahtarı gerekmez.

Mevcut kurulumda önce `./xti migrate` çalıştırılır. Çekirdek 84 → 85
geçişi önce yedek alır; toplama tabloları genişler, eski satır/rowid ve
hash'ler korunur. Eski motor yeni alanı açamaz; geri dönüş eski yedekten
yeni bir alana yapılır.
İş kuyruğu 3, engine/platform sözleşmesi v1 değişmez; kaynak işi modeli 6'dır.

## Kayıtlı toplama profili ve ortak araştırma

Önce `brand tracking-add` ile izleme oluşturulur. Aşağıdaki `<izleme-kimliği>`
yerine onun kimliği yazılır; izleme ve profil aynı domaine ait olmalıdır.
Domain önceden `assets add` ile kayıtlı olmalıdır.

```sh
./xti profiles save "Firma sosyal" securehup.com --only-social --social-watch <izleme-kimliği>
./xti collect --profile "Firma sosyal" --plan
./xti collect --profile "Firma sosyal" --summary
./xti research securehup.com --type domain
./xti journals status
./xti journals archive-plan --older-than-days 90
```

Plan ağ isteği yapmaz. Çalıştırma kayıtlı platform/sayfa/süre sınırlarını
kullanır. Aynı profil mevcut `jobs.submit`/worker yoluyla da çalışır.
Zamanı gelmemiş izleme `not_due` olarak atlanır; yeni kontrol sayılmaz.
İzleme değiştiyse eski iş yeni kapsamda sessizce çalışmaz; yeni plan gerekir.

Araştırmada domain → profil → URL ve vaka bağlantısı görünür. Örneğin
Sherlock adresi bildirmiş, sayfa404 dönmüşse iki sonuç tarihleriyle birlikte
gösterilir. Timeout,404 ile aynı sayılmaz. Sahiplik/taklit kararı insandadır.

Arşiv önizlemesinin verdiği `archive-apply` komutu önce yedek alır, seçilen
eski gövdeleri kayıpsız sıkıştırır. Son tamamlanmış keşif korunur. Liste,
ayrıntı, vaka ve tekrar anahtarları aynı kanıtı okur. İşlem kimliğiyle
`journals restore` sıkıştırmayı geri alır; kayıt silmez. Bu işlem saklama
politikasını sınırsız yapmaz ve SQLite dosyasının hemen küçülmesini vaat etmez.

Keşif kuralı v2 X kullanıcı adını tam eşleştirir. Eski v1 kayıtlar kendi
kuralıyla okunur; yeni kontrol için yeni bir keşif/tur çalıştırılmalıdır.

## 1. Bulunan hesapları birlikte inceleme

```sh
./xti brand discover securehup.com --name SecureHup
./xti brand review-list --domain securehup.com
./xti review-queue
```

Her profilde şunlar ayrı görünür:

- Profil adresi, hangi kaynakların bulduğu ve sayfa kontrolünün sonucu.
- Varsa bu keşfe bağlı Bright Data sonucu; bekleyen veya başarısız durumlar dahil.
- İnsan kararı ve gerekçesi; karar eski keşfe aitse açıkça belirtilir.
- Vakaya ekleme için kullanılacak tam kanıt kimliği.

`review-list` her domainin en son **tamamlanmış** keşfini gösterir.
Devam eden çalışma önceki kanıtı silmez. Sayfayla doğrulanmış profiller
ve kaynakların desteklediği adaylar inceleme listesine girer. Önceden
görülen adresin son kontrolü başarısız veya yokluk yanıtlıysa bu ayrım da
listede görünür. Yalnız
türetilmiş, kanıt bulunmamış kullanıcı adı denemeleri özgün
`brand discovery-show KESIF_UUID` sonucunda kalır.

```sh
./xti brand review-show KESIF_UUID --url https://instagram.com/securehup
./xti brand review-decide KESIF_UUID --url https://instagram.com/securehup \
  --decision official --reason 'Firma yetkilisi bu adresi doğruladı.' \
  --expected-revision 0 --idempotency-key securehup-instagram-review-1
```

Kararlar: `official` (resmî), `legitimate` (meşru ilişki),
`suspected_impersonation` (taklit şüphesi), `unrelated` (ilgisiz),
`uncertain` (belirsiz). Bu kararlar kullanıcı değerlendirmesidir;
profilin bulunması otomatik resmî hesap veya taklit kararı değildir.

İlk kararda sürüm 0 kullanılır. Sonraki değişiklikte `review-show` içindeki
güncel sürüm verilir. Eski kararlar korunur; başka bir karar araya girdiyse
yanlışlıkla üzerine yazılmaz. Aynı işlem anahtarı ve aynı istek tekrar
karar üretmez. Karar firma domaini ve **tam profil adresine** bağlıdır.

Liste `--offset/--limit` ile sayfalanır. `review-queue` sosyal bölümü
`--social-offset/--social-limit` ile bağımsız sayfalanır; eksik sayfa kapsamı
açık gösterilir. Keşfin son 20 ek sağlayıcı işlemi incelenir ve profile
ait olanlar gösterilir; pencere kısmi ise belirtilir. Daha eski kayıtlar
`brand enrichments --discovery-id ...` ile açılır.

## 2. Seçilen kanıtı vakaya ekleme

```sh
./xti cases create 'SecureHup sosyal hesap incelemesi' \
  --summary 'Seçilen hesap bağlantılarının incelenmesi.' \
  --reason 'Analist tarafından inceleme açıldı.'
./xti cases evidence-add VAKA_UUID --type social_discovery \
  --evidence-id KANIT_KIMLIGI --reason 'Seçilen profilin mevcut kanıtını sakla.'
./xti cases evidence-show VAKA_UUID KANIT_BAGI_UUID
```

`KANIT_KIMLIGI`, `review-list/show` çıktısında verilir: keşif UUID'si ve
profil adresinin özeti. Bir vaka tek bir profili seçer. Sayfa kanıtı,
o anda görünen sağlayıcı kanıtı ve karar geçmişi birlikte dondurulur.
Yeni tarama, yeni insan kararı veya sağlayıcı işinin sonradan tamamlanması
bu kopyayı değiştirmez. Kanıtı yenilemek açık bir `evidence-add` seçimidir;
vaka işlem geçmişinde kaydedilir. Başka firmanın kayıt kimliği kullanılamaz.

## 3. Ücretsiz düzenli takip

```sh
./xti brand tracking-add KESIF_UUID --name 'SecureHup sosyal hesapları' \
  --interval-seconds 86400 --idempotency-key securehup-social-watch
./xti brand tracking-show IZLEME_UUID
./xti brand tracking-run IZLEME_UUID --idempotency-key securehup-social-day-1
./xti brand tracking-monitor IZLEME_UUID --max-cycles 7 --max-duration-seconds 604800
```

Tanım, seçilen keşfin firma adı/domaini, platformları, sayfa ve süre
sınırlarını alır. Düzenli takipte Tavily ve Bright Data **çağrılmaz**;
başlangıç keşfi Tavily kullanmış olsa bile tekrar ücretli arama açılmaz.
Varsayılan aralık 24 saat; izin verilen aralık 5 dakika–7 gündür.
Tanımın kapsamını değiştirmek yeni bir izleme tanımı ve yeni başlangıç
gerektirir. İsim aynı çalışma alanında tekildir.

`tracking-run` zamanı geldiyse bir tur çalıştırır. İsteğe bağlı `--force`
yalnız bu tur için bekleme aralığını atlar. Yeni gerçek tarama için yeni
işlem anahtarı gerekir; eski anahtar saklanan çalışmayı döndürür.

`tracking-monitor` terminal açıkken en fazla 1.000 tur / 7 günlük yeni-tur
bütçesiyle tekrarlar. Beklerken veritabanı yazıcı kilidini tutmaz. `Ctrl+C`
tamamlanan turları korur; başlamış bir turun durumu aşağıdaki kurtarma
kurallarına göre gösterilir. Arka plan servisi kurmaz. Sunucu platformu
kendi zamanlayıcısıyla `brand.tracking.run` çağırabilir.

```sh
./xti brand tracking-set IZLEME_UUID --pause --expected-revision 1 \
  --idempotency-key securehup-social-pause
./xti brand tracking-list
./xti brand tracking-run-show TUR_UUID
./xti inbox list
./xti inbox show BILDIRIM_UUID
```

Yeniden açmak için güncel sürümle `--enable` kullanılır.

## Değişikliklerin anlamı

İlk sonuç başlangıç kaydıdır; bildirim üretmez. Tamamen kontrol edilemeyen
ilk turlar başlangıcı tamamlanmış sayılmaz. Sonraki turların bildirimleri:

| Durum | Gösterilen anlam |
| --- | --- |
| `new_profile` | Bu izlemede ilk kez bulunan veya kaynakla desteklenen profil. Hesabın yeni açıldığı iddiası değildir. |
| `profile_found` | Önceden doğrulanamamış veya bu adreste bulunamamış profil artık sayfa kanıtıyla bulundu. |
| `profile_changed` | Doğrulanan profilin başlığı, açıklaması veya firma web bağlantıları değişti. |
| `profile_unavailable` | Önceden bulunan tam adres açık yokluk yanıtı verdi; hesabın kesin silindiği söylenmez. |

Zaman aşımı, erişim engeli, eksik sayfa bütçesi veya bu turda hiç
keşfedilmeyen URL **hesap kaybı değildir**. Son doğrulanabilir gözlem
korunur. Sonraki başarılı kontrol aynı bilgiyi verirse yeni değişiklik
üretilmez. Sırf sayfanın gövde hash'i değişti diye bildirim oluşmaz.

Önceki kaynak destekli veya sayfayla bulunmuş adresler, yeni kaynak
yanıtında yer almasa da yeniden kontrol edilir. Her tur sayfa bütçesinin
yarısı (en az bir) bu adreslere ayrılır; kalan adresler sonraki turlara
döner. Yeni bulunan adresler eklense de son-adres imleci eski adresleri
atlamaz. Bir sayfalık bütçede saklı adres varsa yeni aday kontrolü o tur
yapılamayabilir. `tracking-run-show` seçilen/toplam eski adres sayısını,
`discovery-show` tek tek sonuçlarını gösterir. `retained_profile` güncel
kaynak veya sahiplik kanıtı değildir. Tam kaynak hataları yine korunur.
Bright Data kayıtlarının değişimi bu ücretsiz takipte otomatik sorgulanmaz.

Bir turun farkları, kalıcı sonucu ve bildirimleri tek veritabanı işleminde
yazılır. Tekrar çağrıda bildirim çoğalmaz ve okundu durumu sıfırlanmaz.
Bildirim kutusundaki durum insan kararından bağımsızdır.

## Ortak iş kuyruğuyla çalıştırma

Mevcut izlemenin `tracking-show` çıktısındaki kimlik/sürümü kullanılır.
Yerel kuyruk daha önce kurulmadıysa bir kez `./xti source-jobs init`
çalıştırılır; var olan kuyruk3 yeniden oluşturulmaz.

```sh
./xti source-jobs plan securehup.com --type domain --source social-tracking \
  --social-watch IZLEME_UUID --social-revision 1
./xti source-jobs submit securehup.com --type domain --source social-tracking \
  --social-watch IZLEME_UUID --social-revision 1 --idempotency-key securehup-social-job-1
./xti source-jobs worker --job-id IS_UUID
./xti source-jobs result IS_UUID
```

Plan ve kabul ağsızdır. `--social-force` yalnız bu tur için aralık
beklemeyi atlar; duraklatma/sürüm/firma sınırını atlamaz. İptal, durum,
tekrar, ilerleme ve kurtarma mevcut `source-jobs` akışındadır. İşin
adım makbuzundan özgün sosyal tur ve keşif kaydı açılır. Sıradaki iş
çalışırken izleme duraklatılmış veya sürümü değişmişse yeni istek gönderilmez.
Zamanı gelmemiş/busy iş açık gerekçe taşır; otomatik sürekli servis kurulmaz.

Firma platformunda aynı `sources.plan` / `sources.jobs.submit` işlemleri
`sources:["social-tracking"]`, `social_watch_id`, `social_watch_revision`
ve isteğe bağlı `social_force` alanlarını alır. Submit ayrıca güncel
`expected_workspace_id`, plan hash'i ve tekrar anahtarı ister.
Mevcut `platform worker` aynı işi yürütür. Yeni backend/API yazılması gerekmez.

Toplam araç trafiği ölçülmediğinden `max_requests` sosyal turun tamamını
sınırlamaz; diğer ölçümlü kaynak adımlarına uygulanır. Sosyal kapsam kendi
sayfa/süre/platform sınırını korur. Plan `maximum_external_requests=null`,
sonuç toplam HTTP `attempts=null` verir; bilinen sayfa denemeleri ayrı
`recorded_social_page_http_requests` alanındadır. Bu ayrım [kuyruk
sözleşmesinde](SOURCE_JOBS.md) açıklanır. Tavily/Bright Data çağrılmaz.

Kuyruk kesintisinde `source-jobs retry IS_UUID --idempotency-key YENI_ANAHTAR
--allow-uncertain` açık kabul ister. Kaydedilmiş core sonucu varsa yeniden
taranmadan bağlanır; kaydedilmiş kısmi turun yeni retry'si yeni turdur.
Keşif rezervasyonu öncesinde duraklatılmış eski tur ağsız kapanır;
izleme `busy` olarak kalmaz. Başlamış isteği iptal geri alamaz; iptal
ve işin toplam süre denetimi adımlar arasında yapılır.

## Kesinti ve kapasite

Tur başlamadan işlem kimliği saklanır. Keşif kaydedildikten sonra süreç
kesilirse **aynı tekrar anahtarıyla** `tracking-run` sonucuna devam edilir;
keşif yeniden çağrılmaz. Keşfin kendisi tamamlanmadan kesilmişse aynı
anahtarla sonuç `interrupted` olur; otomatik yeniden tarama yapılmaz.
Yeni tur açıkça yeni anahtar ister. `tracking-run-show` çalışma anahtarını
gösterir; önceki tur toparlanmadan farklı anahtarla ikinci tur açılmaz.

Çalışma alanı başına işlem geçmişi toplam 10.000 olay / 32 MiB, bildirim 10.000,
izlemelerin son gözlemleri toplam 5.000 profil ile sınırlıdır. Mevcut keşif
ve ek kanıtın kendi saklama sınırları da geçerlidir. Kapasite aşımı veri
silmez; tamamlanmış keşif korunur ve işlem hata verir. Bu sınırlar büyük
ölçekli veya kesintisiz hizmet garantisi değildir.

## Engine ve platform

Yeni takip turları `version=2`, `watch_revision` ve `tracking` alanı taşır.
`tracking.urls` o tur için seçilmiş eski adresleri, `total` bütün saklı
adres sayısını gösterir. Keşif kapsamındaki aynı bağlam scope/hash'e dahildir.
Eski tur kayıtlarında bu alanlar yoktur; eski JSON yeniden yazılmaz.

| İşlem | Parametreler |
| --- | --- |
| `brand.review.list` | İsteğe bağlı `domain`, `offset`, `limit`. |
| `brand.review.show` | `discovery_id`, `url`. |
| `brand.review.decide` | `discovery_id`, `url`, `decision`, `reason`, `expected_revision`. |
| `brand.tracking.add` | `discovery_id`, `name`, isteğe bağlı `interval_seconds`. |
| `brand.tracking.set` | `identifier`, `enabled`, `expected_revision`. |
| `brand.tracking.run` | `identifier`, isteğe bağlı `force` (varsayılan false). |
| `brand.tracking.list` | İsteğe bağlı `offset`, `limit`. |
| `brand.tracking.show`, `brand.tracking.run.show`, `brand.change.show` | `identifier`. |

`decide/add/set/run` platform yazmaları ayrıca `expected_workspace_id` ve
`idempotency_key` ister; engine yalnız okumaları kabul eder. Yeni işlemlerden
yalnız `brand.tracking.run` ağa çıkar. Firma/path/API anahtarı serbest JSON
seçeneği değildir. `company.review` aynı okuma kesitindeki sosyal listeyi
`data.social` altında döndürür; mevcut araştırma maddeleri korunur.

```json
{"contract_version":1,"request_id":"social-run-1","operation":"brand.tracking.run","parameters":{"identifier":"IZLEME_UUID","expected_workspace_id":"WORKSPACE_UUID","idempotency_key":"social-run-2026-11-19"}}
```

İşlem zarfının başarılı olması kaynak kapsamının tam olduğu anlamına gelmez:
turun `data.record.status`, `baseline`, `unchecked_count`, `changes` alanları
okunur. `not_due`, `busy`, `revision_conflict`, `idempotency_conflict`,
`invalid_state`, `not_found` ayrı hata kodlarıdır. İlk beşi çıkış 1,
`not_found` çıkış 3; biçim/kapsam doğrulama hataları çıkış 2'dir.

## Doğrulama

Kontrollü sayfa/kaynak yanıtlarıyla insan kararı, sağlayıcı ayrımı,
başlangıç, değişiklik, hata sonrası toparlanma, aynı işin tekrarı, eşzamanlı
yazma, kutu okundu durumu, tarihî vaka, firma ayrımı, gerçek CLI/JSON ve
eski/yeni yedekli geçişler test edilir. Kontrollü testler canlı doğruluk
ölçümü değildir. Koşu sonuçları [kabul kaydında](ACCEPTANCE_REVIEW.md),
altı yeni kuruluş ve gerçek kuyruk ölçümü [ayrı belgede](SOCIAL_TRACKING_ACCEPTANCE.md) tutulur.
