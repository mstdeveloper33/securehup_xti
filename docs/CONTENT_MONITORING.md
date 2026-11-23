# Firma ve tedarikçi içerik izlemesi — P02

0.190.0. P02 temel yaşam döngüsü + P10 Bluesky kaynağı. A01/A04/A07/A12;
A13/I04 için çok dilli isimler ve kaynak dil/bölge
tanımları. Bu akış **firmanla ilgili bulunan içeriği** gösterir: başlık,
kısa metin, bağlantı, tarih, eşleşme nedeni ve inceleme kararı.
Bir adın geçmesi tek başına tehdit veya aynı firma olduğunun kanıtı değildir.
[P02 temel teslimi](roadmap/P02_DELIVERY.md),
[P10 Bluesky teslimi](roadmap/P10_DELIVERY.md).

## Kurulum ve ilk kullanım

Yeni klonda `./setup` yeterlidir. Mevcut kurulumda bağımlılıkları yenile,
ardından kendi veri alanını açıkça yükselt:

```sh
./scripts/setup-brand
./scripts/setup-code
./xti migrate
./xti content providers
```

Çekirdek şema89→90 önce benzersiz yedek alır. Önceki sürümlerden geçiş
zinciri de korunur. Kurulum eski Python ortamını saklar. `--core-only`
kanal/akış bağımlılıklarını kurmaz; eksik araç çalışıyor gibi gösterilmez.

Bir açık yayın ekle. Çıktıdaki kimliği sonraki komutta `KAYNAK_ID` yerine yaz:

```sh
./xti content source-add --provider rss --preset ncsc --language en --region UK
./xti content source-add --provider rss --preset cert-fr --language fr --region FR
./xti content sources
./xti content watch-add --name "SecureHup içerikleri" --company SecureHup --domain securehup.com --source KAYNAK_ID
./xti content plan IZLEME_ID
./xti content run IZLEME_ID
./xti content list --watch-id IZLEME_ID
./xti content show ESLESME_ID
```

Bir izlemeye birden çok `--source` verilebilir. `plan` internete çıkmaz;
`run` seçilen kaynakları gerçekten okur. `list/show` kayıtlı sonuçları
okur ve yeniden arama yapmaz. `source-add --provider rss --locator
https://yayinci.example/feed --category blog` ile kendi açık RSS/Atom
kaynağını ekleyebilirsin. Forumun RSS/Atom yayını da aynı yolla seçilebilir.
Bu genel web sitesi kazıyıcısı veya tüm forumlara erişim değildir.

### Bluesky genel gönderileri

Anahtar veya hesap gerekmeden resmî Bluesky genel aramasını ekleyebilirsin:

```sh
./xti content source-add --provider bluesky --name "Bluesky genel arama" --language und --region global
./xti content watch-add --name "SecureHup Bluesky" --company SecureHup --domain securehup.com --source KAYNAK_ID
./xti content plan IZLEME_ID
./xti content run IZLEME_ID
./xti content list --watch-id IZLEME_ID
```

Basit örnek: herkese açık bir gönderinin metninde `SecureHup` veya
`securehup.com` geçerse aday kaydedilir; bağlantısı, tarihi ve hangi kelimeyle
eşleştiği gösterilir. Bu kayıt otomatik olarak “tehdit”, “resmî hesap” veya
“doğru iddia” sayılmaz; analist incelemesi gerekir.

Her hedef için ad, domain ve açıkça verdiğin alternatif adlar sorgulanır.
Bunlar çalışma sırasında Bluesky'ye gönderilir. İlk tur mevcut pencereyi
sessiz başlangıç olarak saklar; sonraki turdaki yeni/değişmiş gönderi mevcut
inbox ve inceleme akışına girer. Bütçe bütün sorgulara yetmezse checkpoint
sıradaki sorguyu saklar ve sonraki çalışma oradan devam eder. Hedef kaydı
değişirse aynı ada sahip olsa bile yeni sessiz başlangıç yapılır.

Yalnız genel gönderinin metni ve kaynak zamanı alınır. Görsel/video, profil
biyografisi, takipçi, beğeni listesi, özel hesap, DM ve firehose alınmaz.
Her sorgunun yalnız en güncel sonuç sayfası okunur; cursor görülse bile tam
tarihsel arşiv iddiası yapılmaz. `public.api.bsky.app` erişilemezse yalnız
diğer resmî `api.bsky.app` AppView denenir; üçüncü taraf proxy kullanılmaz.
429 ve erişim hataları başarılı boş sonuç gibi gösterilmez.

İçerik yoksa `run-show` ile kaynak durumunu birlikte incele:

```sh
./xti content runs --watch-id IZLEME_ID
./xti content run-show CALISMA_ID
./xti content report --domain securehup.com
```

Başarılı boş pencere, anahtar/izin eksikliği, kaynak kesintisi ve kısmi
toplama ayrı kaydedilir. Eski içerik son kaynak hatasıyla silinmez.
Yayıncıya ait kontrol örnekleri firma eşleşmesi olarak sayılmaz.

## Kayıtlı kuruluş ve tedarikçi

Yeni bir firma adı yerine mevcut envanter kimliklerini kullanabilirsin:

```sh
./xti content watch-add --name "Firma ve tedarikçi" --organization KURULUS_ID --supplier TEDARIKCI_ID --source KAYNAK_ID
./xti organizations content KURULUS_ID
./xti organizations report KURULUS_ID
```

İsim/domainler envanterden alınır. `--alias` açık alternatif isim ekler;
çeviri veya otomatik şirket birleştirmesi yapılmaz. Firma, tedarikçi veya
kaynak tanımı değişirse eski çalışma güncel kapsam başarısı sayılmaz.
`watch-update IZLEME_ID --name "Firma ve tedarikçi"` güncel tanımları
yeniden bağlar. Önceki kanıt ve kararlar korunur. İsim eşleşmesi aday,
tam domain eşleşmesi ayrı gerekçe olarak gösterilir; ikisi de otomatik
zararlılık hükmü değildir.

Kuruluş içerik görünümündeki `monitored_content` yeni akışın kayıtlarıdır.
Var olan web araması henüz yapılmadıysa, açık yayın eşleşmesi web
aramasını başarılıya çevirmez; toplam durum bu nedenle `partial` olabilir.
Her kaynağın kendi durumu ve saklı içeriği görülebilir.

## İnsan incelemesi, değişiklik ve vaka

```sh
./xti content review ESLESME_ID --evidence-id KANIT_ID --decision ordinary_news --reason "Firmanın normal duyurusu"
./xti content reviews ESLESME_ID
./xti content evidence KANIT_ID
./xti content changes --watch-id IZLEME_ID
./xti inbox list
./xti cases evidence-add VAKA_ID --type content_match --evidence-id ESLESME_ID --reason "İncelenen içerik"
```

Kararlar: `relevant`, `unrelated`, `ordinary_news`, `threat_claim`,
`uncertain`. Karar kanıt ve gözlem sürümüne bağlıdır. İçerik değişirse
eski karar saklanır, yeniden inceleme gerekir. Önceki metne geri dönüş
eski kararı otomatik canlandırmaz. İlk pencere sessiz başlangıçtır;
sonraki yeni/değişmiş içerik ortak kutuya bir kez yazılır. Geçmiş kanal
sayfasından ilk kez bulunan eski içerik yeni haber alarmı oluşturmaz.
Vakaya alınan kanıt sonraki taramayla değişmez.

Betterleaks1.10.1, ilgili metin ve bağlantıyı çevrimdışı tarar. Eşleşen
satırlar maskelenir; kaynak kimliği SHA256 olarak tutulur. Araç çalışmazsa
metin ve bağlantı gösterilmeden yalnız kontrol edilmemiş metaveri kaydı
üretilir; durum kısmi olur. Bu, bütün olası kişisel verileri veya her
secret biçimini tespit etme garantisi değildir. Ham cevap, token,
oturum, ek dosya ve medya gövdesi içerik kanıtına alınmaz.

## Düzenli çalışma ve kuyruk

İzlemeyi durdurmak için `content watch-update IZLEME_ID --disable`
kullanılır. Kaynak sonradan kapatılmış olsa da izleme durdurulabilir;
yeniden açma ve kapsam değiştirme güncel kaynak bağlarını doğrular.
Bildirim kutusu, genel durum ve depolama özeti içerik/kod bildirimlerini
aynı toplam ve okunma durumuyla sayar.

```sh
./xti content watch-update IZLEME_ID --interval-seconds 3600 --max-items 200 --max-operations 30 --budget-seconds 120
./xti content monitor IZLEME_ID --cycles 24
```

Terminal döngüsü açık kaldığı sürece çalışır; kurulum kendiliğinden
7/24 hizmet başlatmaz. Hemen yeniden kontrol için `run --force` açık
seçimdir. Uzun işleri mevcut kalıcı kuyruğa da koyabilirsin:

```sh
./xti source-jobs init
./xti source-jobs plan securehup.com --type domain --source content-monitor --content-watch IZLEME_ID --content-revision 1 --max-requests 30 --max-seconds 120
./xti source-jobs submit securehup.com --type domain --source content-monitor --content-watch IZLEME_ID --content-revision 1 --max-requests 30 --max-seconds 120 --idempotency-key securehup-content-001
./xti source-jobs worker --job-id IS_ID
./xti source-jobs result IS_ID
```

`--content-revision` güncel izleme sürümüdür. Domain izlenen kapsamda
olmalıdır. Domainsiz isim izlemesi için JSON planında `indicator_type=sha256`
ve kayıtlı `bindings` değerinin kanonik SHA256'sı kullanılabilir.
Kaynak işi modeli9 eski1–8 makbuzlarını okur; kuyruk şeması4 aynı kalır.

İşlem içerik verisini kaydettikten sonra kuyruk kesilirse aynı makbuz
yeniden kullanılır, kaynak çağrısı tekrarlanmaz. Tamamlanıp tamamlanmadığı
bilinmeyen dış çağrılar otomatik başarı sayılmaz. Çalıştırıcının bittiğini
doğruladıktan sonra kesilmiş içerik çalışmasını `content recover CALISMA_ID`
ile işaretle; ardından yeni anahtarla veya kuyruğun açık retry akışıyla
devam et. Eski anahtar aynı sonucu tekrar okur.

## Kaynaklar ve kanal kurulumu

| Kaynak | Kullanılan parça | Okunan kapsam |
|---|---|---|
| RSS/Atom | feedparser6.0.14 | Yayıncının sunduğu mevcut akış penceresi. |
| local-news | Mevcut XTI haber kataloğu | Kayıtlı haber metinleri, yeni ağ çağrısı yok. |
| local-mentions | Mevcut XTI firma aramaları | Önceden saklanmış Tavily sonuçları, yeni kredi harcaması yok. |
| local-reports | Mevcut XTI rapor kanıtı | Saklı güncel metin sürümü; uzun metnin sınırlı bölümü açık işaretlenir. |
| Bluesky | Resmî public AppView `searchPosts` | Firma/tedarikçi hedefli en güncel genel metin gönderisi sayfaları. |
| Telegram | Telethon1.46.0 | Seçilmiş açık yayın kanalı; kullanıcının oturumu gerekir. |
| Discord | Resmî RESTv10 | Botun okuyabildiği seçilmiş metin/duyuru kanalı. |
| IRC | irctokens2.0.2 ve TLS | Seçilmiş kanalda bağlantı sırasında görülen mesajlar. |

Kayıtlı veriyi kullanmak için `source-add --provider local-news` (veya
`local-mentions`/`local-reports`) ekle. Eski katalogların kendi bütünlük ve
okuma bütçeleri korunur; kaynak sorununda sessiz eksik başarı üretilmez.

Telegram hesabın hazır olduğunda, bu çalışma alanında gizli terminal girişi:

```sh
./xti content telegram-login --profile firmam
./xti content source-add --provider telegram --locator KANAL_KULLANICI_ADI --credential-profile firmam --category channel
```

API id/hash hesabına ait Telegram uygulamasından gelir. Telefon, doğrulama
kodu ve varsa iki aşamalı parola terminalde görünmez. Oturum ekrana
yazılmaz. Mevcut StringSession varsa `content configure telegram` de
kullanılabilir. Davet bağlantısı, kişi hesabı veya otomatik kanal katılımı
genel kanal aramasının yerine geçmez.

Discord için kendi bot anahtarını gizli girişte kaydet:

```sh
./xti content configure discord --profile firmam
./xti content source-add --provider discord --locator SUNUCU_ID/KANAL_ID --credential-profile firmam --category channel
```

Bot, kanal/sunucu eşleşmesi, Message Content ve VIEW_CHANNEL /
READ_MESSAGE_HISTORY izinleri doğrulanır. DM, thread ve Discord forum
başlıklarını otomatik genişletme yoktur. Eksik izin, boş başarılı sonuç
sayılmaz. Bir Discord turu izin kontrolleri dahil en az6 HTTP işlemi
gerektirir; geçmiş sayfası için en az7 işlem ve2 öğe bütçesi gerekir.

Telegram ve Discord her turda önce en yeni mesaj penceresini okur.
Bütçe varsa ayrı cursor ile eski sayfayı işler; böylece geçmiş taraması
yeni mesajı bekletmez. Pencere dışında kalan eski düzenlemeler ancak
geçmiş döngüsünde görülür. Tam arşiv garantisi yoktur.

```sh
./xti content source-add --provider irc --locator 'ircs://SUNUCU:6697/%23KANAL' --category channel
```

IRC bağlantısı en çok60 saniyelik bir pencereyi izler. Çevrimdışı aralık
ve geçmiş eksikliği açık gösterilir. Sunucu mesaj kimliği vermiyorsa aynı
metinli farklı mesajlar otomatik birleştirilmez. Sohbet mesajı gönderilmez.

Erişim dosyaları seçilen veri alanının `content-credentials/` klasöründe,
yalnız kullanıcı tarafından okunur. Anahtarı komuta, JSON'a veya Git'e
yazma. Mevcut profile üzerine yazılmaz; yeni profil kaydet ve kaynakta
`source-update --credential-profile YENI_PROFIL` seç. Firma yedeği içerik
ve iş kayıtlarını kapsar; bu erişim dosyalarını taşımaz. Restore sonrası
erişimi yeni firma alanında yeniden yapılandır.

## Firma JSON sözleşmesi

CLI ve platform aynı uygulama servislerini kullanır. Okuma işlemleri:
`content.providers`, `content.sources`, `content.source.show`,
`content.watches`, `content.watch.show`, `content.plan`, `content.runs`,
`content.run.show`, `content.matches`, `content.match.show`,
`content.evidence.show`, `content.reviews`, `content.changes`, `content.report`.

Yazma işlemleri: `content.source.add/update`, `content.watch.add/update`,
`content.run`, `content.recover`, `content.review`. Yazmalar
`expected_workspace_id` ve `idempotency_key` ister; güncelleme/çalıştırma
güncel sürümü, inceleme ayrıca kanıt ve gözlem sürümünü ister.

```json
{
  "contract_version": 1,
  "request_id": "content-page-001",
  "operation": "content.matches",
  "parameters": {"limit": 20, "after": 0, "domain": "securehup.com"}
}
```

Bu JSON `./xti platform request --root PLATFORM_KOKU --company FIRMA`
komutunun stdin'ine verilir. Sonraki sayfa `next_after` ile alınır.
Kimliği bilinmeyen/farklı firma hiçbir zaman kişisel alana düşmez.
`organization.content` ve kuruluş raporu saklı içerikleri gösterir.
Yeni REST sunucusu, oturum yönetimi veya .NET kodu eklenmedi.

## Kapasite, hata ve sınırlar

Bir tur: en çok20 hedef,10 kaynak,100 kaynak işlemi,1.000 öğe ve600 saniye.
Bir okuma sayfası en çok100 kayıt. Bunlar saklanmış toplam geçmiş için
kayıt tavanı değildir. Birikmiş veri disk/yedek planlaması gerektirir;
bu modül eski kanıtları kendiliğinden silmez.

Kaynak işlemi HTTP isteğiyle aynı şey değildir: RSS/Bluesky/Discord için gerçek
HTTP denemeleri; Telegram için sınırlı mantıksal çağrılar; IRC için bağlantı
penceresi sayılır. Telegram/IRC alt ağ isteği sayısı bilinmiyorsa `null`
kalır. İzinli sağlayıcı kotasını kaldırmaz. 429/cooldown, timeout, eksik
erişim, geçersiz cevap ve pencere eksikliği ayrı raporlanır.

RU/ZH/AR/TR/PT için isim ve Unicode davranışı etiketli örneklerle sınanır.
Dil/bölge kaynak tanımıdır; otomatik çeviri veya o bölgedeki bütün yeraltı
kaynaklarına erişim anlamına gelmez. Ticari veri saklama/gösterme kararları
[N-045](../NOTES.md#n-045--p02-kaynak-kanal-ve-teslim-kapsamı) altında açık.
