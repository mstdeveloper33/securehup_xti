# P03 — Markayla karşılaştırma ve taklit incelemesi

Marka/domain, açık sayfa, logo/sabit ekran görüntüsü, sosyal profil,
isteğe bağlı yönetici ve uygulama mağazası adayları için ortak motor.
A08/A09/A11/C08; ilgili vaka, bildirim ve izlenebilirlik bağları.

## Başlat

Yeni klonda `./setup` Python araçlarını, Betterleaks'i ve kontrollü
Chromium'u kurar. Yalnız çekirdek kurulumu `./setup --core-only` ile
mümkündür; geçmiş marka kanıtı görsel araçlar olmadan da okunabilir.

```sh
./scripts/setup-brand --check
./scripts/setup-protection --check
./xti brand protection capabilities
```

Linux'ta tarayıcı için sistem kitaplıkları eksikse Playwright'ın
[resmî kurulum adımını](https://playwright.dev/python/docs/browsers#install-system-dependencies)
yönetici olarak uygula; ardından `./scripts/setup-protection` komutunu
tekrarla. XTI yerel kurulumda kendiliğinden `sudo` çalıştırmaz.
Kesilmiş tarayıcı kurulumunda `./scripts/setup-protection --recover`
eski dizini geri getirir; başarısız aday dosyalarını silmez.

Mevcut veri için önce `./xti migrate` gerekir. Şema90→91 açık ve
yedeklidir. Normal yedek/geri yükleme PNG kanıtlarını da içerir; mevcut
bir veritabanının üzerine geri yükleme yapılmaz.

## Kullan

```sh
./xti brand protection identity-add --name SecureHup --domain securehup.com
./xti brand protection watch-add --identity MARKA_KIMLIGI
./xti brand protection plan IZLEME_KIMLIGI
./xti brand protection run IZLEME_KIMLIGI
./xti brand protection candidates --watch-id IZLEME_KIMLIGI
./xti brand protection candidate-show ADAY_KIMLIGI
./xti brand protection run-show CALISMA_KIMLIGI
```

Büyük harfli kimlikler önceki komutun döndürdüğü gerçek UUID'lerle
değiştirilir. `plan`, listeleme ve ayrıntı okumaları internete çıkmaz.
`run` internete çıkar; yalnız seçili kaynaklar ve bütçeler kullanılır.
Sonuç ayrıntıları kaynak, URL, başlık, karşılaştırma gerekçesi, marka
bağı, kanıt ve inceleme durumunu gösterir. Mağazanın döndürdüğü her sonuç
markayla ilgili değildir; `brand_link_state=unestablished` bunu belirtir.
Sosyal profil varlığı da hesap sahibini veya taklidi kanıtlamaz.

Kimliğe isteğe bağlı resmî bilgiler eklenebilir:

```sh
./xti brand protection identity-update MARKA_KIMLIGI --logo https://example.com/logo.png
./xti brand protection identity-update MARKA_KIMLIGI --profile https://github.com/example
./xti brand protection identity-update MARKA_KIMLIGI --app-json '{"store":"google","id":"com.example.app","developer_id":"publisher-id"}'
./xti brand protection identity-update MARKA_KIMLIGI --person-json '{"name":"Örnek Yönetici","role":"Genel müdür","profiles":[]}'
./xti brand protection watch-update IZLEME_KIMLIGI --enable
```

Bu örnek kişi gerçek bir araştırma hedefi değildir. Kimlik değişince
izlemenin güncel kimliğe açıkça yeniden bağlanması gerekir; son komut
bunu yapar. `--organization KURULUS_KIMLIGI`, marka kimliğini kuruluşun
`organization.content` çıktısına bağlar. Domain üyeliği bulunan kuruluş
raporunda ayrı marka bölümü ve son kaynak durumu görünür.

Tekrar edilen liste seçenekleri **o alanın tamamını değiştirir**; örneğin
iki logo için aynı komutta iki `--logo` verilir. Firma JSON'unda `[]`
ile alan temizlenebilir. Terminal genel JSON arayüzü de aynı işlemi sunar.

## Kaynak ve bütçe

Kaynaklar: `web`, `social`, `apple`, `google`, `urlscan`, `crt.sh`, `stored`.
Apple/Google Play ve CT/urlscan kamu araması API anahtarı istemez.
Kaynak koşulları ve erişim sınırları geçerlidir; “ücretsiz ve sınırsız”
garantisi yoktur. Ücretli Tavily/Bright Data çağrısı bu akışta yapılmaz.

```sh
./xti brand protection watch-update IZLEME_KIMLIGI --source web --source apple --source google --source social --country TR --country US --max-requests 100 --max-seconds 480 --max-items 100 --max-pages 10
./xti brand protection monitor IZLEME_KIMLIGI --cycles 3
```

`monitor` ilk turu hemen dener, sonraki turlar arasında kayıtlı aralığı
bekler. Az önce `run` yaptıysan ilk tur `not_due` dönebilir; izleme
aralığının dolmasını bekleyerek başlat. Bilinçli erken tek kontrol için
`run IZLEME_KIMLIGI --force` kullanılabilir.

Varsayılan: 60 ölçümlü HTTPS isteği, 240 sn, 100 aday, 8 aday sayfası,
1 saat aralık. Üst sınırlar: 200 istek, 600 sn, 1.000 aday, 30 sayfa.
En fazla 3 mağaza bölgesi, 10 sosyal platform, 50 açık aday URL'si.
`--url` bilinen bir adayı ayrıca ekler; otomatik internet keşfi devam eder.
Resmî ilk domain sayfası, karşılaştırma referansı olarak her canlı turda
okunur; yalnız mağaza seçildiğinde de bu referans okuması yapılır.

Bütçeler tek tur içindir; saklı aday sayısının üst sınırı değildir.
Resmî sayfadaki iş ortağı görselleri marka logosu sayılmaz. Açıkça verdiğin
logo URL'leri önceliklidir; aksi halde site ikonu, marka adıyla etiketli
görsel veya genel logo dosya adı referans seçilir. Otomatik seçim logo
sahipliğini doğrulamaz; belirli logo gerekiyorsa kimliğe ekleyebilirsin.
Önceki adaylar küçük sırayla yeniden kontrol edilir; mağaza penceresinden
çıkan uygulama kimliğiyle tekrar sorgulanır. Mağazalar yalnız seçilen
bölgenin güncel arama penceresini verir. Başka bölgeler, ücretli veri,
özel hesaplar veya bütün mağaza kataloğu taranmış sayılmaz.

Maigret/Sherlock içindeki bütün HTTP istekleri bu sayaçta ölçülemez.
Sosyal bölüm kendi süre/platform/sayfa sınırını kullanır; toplam ağ
istek sayısı JSON'da bilinmiyorsa `null` olarak kalır. HTTPS 429/bekleme
bilgisi firma veri alanında saklanır. İstek/yanıt zamanları, HTTP kodu ve
SHA256 çalışma kaydındadır; sırlar veya tam HTTP gövdeleri loglanmaz.

`partial`: bazı kanıtlar var ama tüm seçili kontroller tamamlanmadı.
`failed`: bu tur kullanılabilir sonuç oluşmadı. Önceki kanıt silinmez.
Resmî referans erişilemiyorsa eski karşılaştırma eksik referansla
değiştirilmez. İlk ölçüm sessizdir; sonraki yeni/değişmiş kanıt inbox'a
düşer. Bir kaynağın kayıt bulamaması tehdit olmadığı anlamına gelmez.

## İncele, görseli al, vakaya bağla

```sh
./xti brand protection review ADAY_KIMLIGI --evidence-id KANIT_KIMLIGI --decision uncertain --reason "Kaynak ve marka ilişkisi henüz yeterli değil"
./xti brand protection reviews ADAY_KIMLIGI
./xti brand protection artifact-get PNG_SHA256 --output aday.png
./xti cases evidence-add VAKA_KIMLIGI --type brand_protection --evidence-id ADAY_KIMLIGI --reason "İncelemeye alınan marka kanıtı"
./xti inbox list
```

Kararlar: `official`, `authorized_reseller`, `parody`, `unrelated`,
`suspected_impersonation`, `confirmed_impersonation`, `uncertain`.
Otomatik karşılaştırma bunlardan taklit kararı üretmez. İnceleme özgün
kanıt ve gözlem sürümüne bağlıdır; değişiklikte eski karar saklanır ama
“yeniden inceleme” açılır. Eski metne geri dönülmesi eski kararı canlandırmaz.
PNG dosyası varsa üzerine yazılmaz. Vaka tarihî kanıt kopyasını korur.

Görsel benzerlik, uygulama/geliştirici kimliği farkı, giriş formu veya
ortak şablon ayrı ipuçlarıdır. Ortak script/form parmak izi kit veya
aktör atfı değildir. APK/IPA/kit indirme, giriş yapma, form gönderme ve
başvuru gönderme yoktur; takedown başvurusu P06'dadır.

Görüntüleme yalnız önceden alınmış kaynaklardan yapılır; Chromium dış
ağa çıkmaz. JavaScript kapalıdır. Dolayısıyla bu **statik görünüm**dür;
oturum açmış kullanıcı ekranı veya dinamik uygulamanın bütün durumları
değildir. Görsellerde otomatik OCR/kişisel veri/secret maskelemesi yoktur.
Metin/URL kontrolü Betterleaks ile yapılır; kontrol başarısız olursa
aday gövdesi saklanmaz. Ham sayfa betikleri yürütülmez.

## Firma JSON ve kalıcı işler

Okumalar `brand.protection.*` altında engine/platform JSONv1'e bağlıdır.
Yazmalar platform kapsamında `expected_workspace_id`, tekrar anahtarı
ve güncel kayıt sürümü gerektirir. `candidate.show`, `evidence.show`,
`artifact.get`, `run.show` detay verir. Listeler `after`/`limit` kullanır;
`next_after` varsa devam edilir. Bayt sınırı nedeniyle sayfa `limit`ten
kısa olabilir; hiçbir kayıt sessizce atlanmaz.

Kalıcı iş kaynağı `brand-protection`, kaynak iş modeli10'dur; eski1–9
okunur. `sources.plan` parametreleri: `indicator_type=domain`, marka
domaini `value`, `sources=["brand-protection"]`, `protection_watch_id`,
`protection_watch_revision`, `protection_identity_revision`, `max_requests`,
`max_seconds`. İş bütçesi kayıtlı izleme bütçesinden küçük olamaz.
Firma backend'i aynı planı `sources.jobs.submit` ile kuyruğa alır;
`platform worker` çalıştırır. Kabul ve çalıştırmada kapsam tekrar doğrulanır.

Tamamlanan core makbuzu kuyruk kesilse de yeniden kullanılır. Belirsiz
`running` kayıt için `brand protection recover CALISMA_KIMLIGI`, ardından
normal açık iş tekrar yolu kullanılır. Yeni ağ isteği kendiliğinden
tekrarlanmaz. İptal yeni adımları durdurur; gönderilmiş isteği geri alamaz.

[Teslim ve ölçümler](roadmap/P03_DELIVERY.md), [ticari/açık koşullar](../NOTES.md#n-046--p03-marka-koruması-görsel-kanıt-ve-mağaza-kaynakları).
