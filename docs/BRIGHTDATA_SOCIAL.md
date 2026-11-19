# LinkedIn şirket hesaplarına Bright Data kanıtı ekleme

0.172.0, mevcut sosyal keşifte bulunan LinkedIn **şirket** profillerini
Bright Data üzerinden incelemeyi destekler. İlk kullanım alanı, profil
sayfası giriş ekranı/erişim engeli nedeniyle doğrulanamayan adaylardır.
Instagram/X ve kişi profilleri bu ilk bağlantının kapsamında değildir.
API anahtarı kullanıcı kararıyla sonra eklenecek; canlı sonuç ölçülmedi.

## Kurulum ve kullanım

Ek Python paketi veya sunucu kurulumu yoktur. Mevcut veritabanında bir kez:

```sh
./xti migrate
./xti brand brightdata configure
./xti brand brightdata status
```

`configure` anahtarı görünmeyen terminal girişinden alır; komut satırına
anahtar yazılmaz. Varsayılan dosya `$XDG_CONFIG_HOME/xti/brightdata.key`,
XDG tanımlı değilse `~/.config/xti/brightdata.key`; dosya izni 600'dür.
Var olan dosyanın üzerine yazılmaz. `BRIGHTDATA_API_KEY` ortam değişkeni
dosyadan önce kullanılır. Anahtar firma veritabanına veya yedeğe girmez.
Kurulum ve status internete çıkmaz, bakiye sorgulamaz.

```sh
# Önce mevcut birleşik sosyal keşif
./xti brand discover securehup.com --name SecureHup
./xti brand discoveries --domain securehup.com

# Yukarıdaki çıktının çalışma UUID'sini kullan.
# Canlı denemede zaten bulunan şirket hesabına da ek kanıt iste.
./xti brand enrichment-plan KESIF_UUID --max-profiles 5 --include-found
./xti brand enrich KESIF_UUID --max-profiles 5 --include-found --idempotency-key securehup-linkedin-1

# Sağlayıcı arka planda çalışır; çıktının ek kanıt UUID'siyle sonucu al
./xti brand enrichment-refresh EK_KANIT_UUID
./xti brand enrichment-show EK_KANIT_UUID
./xti --json brand enrichment-show EK_KANIT_UUID
./xti brand enrichments --discovery-id KESIF_UUID
```

Plan ücretsizdir. Yalnız başka kaynakların bildirdiği, henüz sayfayla
doğrulanamamış LinkedIn şirket profilleri varsayılan olarak seçilir.
Firma sitesindeki bağlantılar önce gelir. Yalnız kullanıcı adı tahmininden
oluşan ve kaynak desteği olmayan adresler gönderilmez; sayfası 404/410 veren
adresler seçilmez. Plan seçilen URL'leri ve dışarıda kalan aday sayısını
gösterir. `--include-found` sayfayla doğrulanan şirket hesaplarına da ek
kanıt istemek içindir; plan ve run'da aynı seçenekler kullanılmalıdır.

## Harcama ve tekrar davranışı

İş başına varsayılan 5, en fazla 20 profil vardır. Tek `POST /datasets/v3/trigger`
ile `gd_l1vikfnt1wgvvqz95w` şirket dataset'ine gönderilir. Her girdide en fazla
bir, toplamda seçilen profil sayısı kadar kayıt istenir. Çıktı alanları
`url|id|company_id|name|website|about` ile sınırlıdır; diğer ürünlere geçiş yoktur.

Çalışma alanı başına UTC gününde varsayılan 50 profil rezervasyonu yapılabilir.
Sunucu yöneticisi `XTI_BRIGHTDATA_DAILY_PROFILE_LIMIT` ile 1–50000 arası
bir değer seçebilir. JSON çağıran müşteri bu limiti değiştiremez. Gönderim
başarısız veya belirsiz olduğunda rezervasyon düşülmez; kaynak ücretinin
oluşmadığı varsayılmaz. Rezervasyonlar atomik olduğundan eşzamanlı istekler
bu çalışma alanının limitini birlikte aşamaz.

Bu ölçüm **hesap bakiyesi, fatura veya firmalar arası ortak para limiti
değildir**. Tüm kullanımlar için Bright Data panelinde harcama sınırı ayrıca
ayarlanmalıdır. Ücretsiz kota uygunluğu ve birim ücret sağlayıcı hesabına
bağlıdır. Veri dönmesi yüzde yüz doğru şirket eşleşmesi demek değildir.

Aynı `idempotency-key` ve kapsam kayıtlı işlemi döndürür; yeni POST yapmaz.
Farklı kapsam aynı anahtarla reddedilir. Bir işlemin sonucunu almak için
yeni `enrich` yerine `enrichment-refresh` kullanılır. Refresh bir ilerleme
GET'i ve hazırsa bir sonuç GET'i yapar; otomatik bekleme döngüsü veya
yeniden ücretli gönderim yoktur. Sonuç henüz hazır değilse daha sonra
refresh tekrar kullanılabilir. Tamamlanan sonucu tekrar okumak ağsızdır.

## Sonucun anlamı

Her hedef için önceki sayfa durumu ile yeni sağlayıcı kanıtı birlikte görünür:

| Sonuç | Anlamı |
|---|---|
| `provider_supported` | Dönen sağlayıcı kaydının profil URL/kimliği istenen hesapla eşleşiyor. |
| `conflicting` | Sağlayıcının girdi bağı aynı olsa da dönen profil kimliği farklı. |
| `unresolved` | Bu hedef için kullanılabilir sağlayıcı kaydı alınamadı; hesap yok denmez. |

Sağlayıcı kaydındaki web sitesi domainle tam eşleşirse ayrıca gösterilir.
Bu otomatik marka sahipliği veya taklit kararı değildir. Kaynak sayfası
doğrudan doğrulanmış gibi `found` durumuna yükseltilmez. Sağlayıcı URL alanı
yoksa geçerli şirket kimliğinden türetilen URL'nin dayanağı `url_basis` ile
ayrı belirtilir. İsim benzerliği farklı profil kimliğini kabul ettirmez.
Sayısal LinkedIn adresi ile ad içeren adres aynı şirket kimliğine bağlıysa
aynı sağlayıcı kanıtı ikisini de destekleyebilir; iki ayrı şirket sayılmaz.

Yalnız sınırlı profil alanları ve kaynak kaydının SHA-256 özeti saklanır.
Alım zamanı sağlayıcı verisinin son güncellenme tarihi değildir. Eski keşif
makbuzu değişmez; yeni kanıt o makbuzun kimliğine/özetine bağlanır.

## Hata ve kurtarma

Anahtar yoksa ücretli iş/kota rezervasyonu oluşmaz. 401/403, 429, HTTP hatası,
bozuk/çok büyük JSON ve süre aşımı sabit hata sınıflarıyla gösterilir;
Authorization, yanıtın ham hata gövdesi ve anahtar yazdırılmaz. HTTP
yönlendirmesi/proxy ortamı kullanılmaz; sadece sabit HTTPS API hostu,
istek başına 20 saniye ve yanıt başına 2 MiB sınırı vardır.

Snapshot kimliği kaydedildiyse bağlantı hatasından sonra refresh ile devam
edilebilir. Gönderimden sonra süreç kesilir ve kimlik kaydedilemezse durum
`reserved`/`submission_unknown` kalır; otomatik tekrar yapılmaz. Önce sağlayıcı
panelinden kontrol edilmelidir. Yeni anahtar yeni iş ve yeni ücret doğurabilir.
Sağlayıcıda silinmiş/erişilemeyen snapshot kendiliğinden yeniden üretilmez.

Şema81 → 82 açık migration mevcut yordamla önce yedek alır, yalnız ek
tablo/index oluşturur. Eski keşif ve diğer kayıtlar korunur. Tamamlanan
ek kanıt ve bekleyen snapshot kimliği normal yedek/geri dönüş kapsamındadır.
Eski yedeğe dönüş sağlayıcıdaki harcamayı geri almaz; yedek tarihinden
sonraki kullanım yerel sayaçta görünmeyebilir. Hesap genelindeki harcama
sınırı ve geri dönüş sonrası kullanım kontrolü sağlayıcı panelinde tutulur.

## Engine ve platform

Engine salt okunur işlemleri: `brand.enrichment.plan`, `.list`, `.show`.
Platform bunlara ek olarak `.run` ve `.refresh` sunar. Yazmalar
`expected_workspace_id` ve firma yazıcı kilidini kullanır. Run ayrıca
`idempotency_key` ister. API anahtarı, endpoint, dataset, harcama limiti ve
başka firma seçimi müşteri JSON parametresi değildir.

```json
{
  "contract_version": 1,
  "request_id": "linkedin-proof-1",
  "operation": "brand.enrichment.run",
  "parameters": {
    "discovery_id": "KESIF_UUID",
    "max_profiles": 5,
    "include_found": false,
    "idempotency_key": "securehup-linkedin-1",
    "expected_workspace_id": "FIRMA_WORKSPACE_UUID"
  }
}
```

UUID yer tutucuları gerçek değerlerle değiştirilmelidir. Başarılı komut
zarfı işlemin kabul edildiğini/okunduğunu belirtir; kaynağın sonuç durumunu
`data.record.state.status` ve `error` alanlarından okuyun. Pending bir iş
tamamlanmış sonuç değildir. Yalnız bu ek kanıtı okumak canlı API gerektirmez.

## Doğrulama ve açık kalanlar

Son odaklı paket 100 test / 21,978 sn; eski geçiş modülleri 78 test /
25,750 sn geçti. Genel koşu 3.296 testte beş eski şema beklentisine takıldı;
beklentiler düzeltildi, dört Linux testi macOS'ta atlandı. Tam paket
düzeltmelerden sonra tekrar edilmedi. [Ayrıntılı kabul](ACCEPTANCE_REVIEW.md#01720--bright-data-bağlantısının-yerel-kabulü).

Kontrollü testler sabit API payload'ını, HTTP/JSON sınırlarını, kimlik
çelişkisini, eksik kayıtları, gizli anahtarı, kesinti/tekrar/günlük bütçeyi,
firma ayrımını ve 81 → 82 geçiş/yedekten dönüşü kapsar. Bu kontrollü
yanıtlar canlı Bright Data kabulü değildir. Kullanıcı anahtarı sonra ekleyecek;
hesap/dataset erişimi, ücretsiz kota, gerçek veri doluluğu ve mevcut üç
LinkedIn adayında doğruluk katkısı açık kalır. [N-034](../NOTES.md).

Resmî protokol kaynakları: [şirket dataset'i ve alanlar](https://docs.brightdata.com/products/scrapers/linkedin/send-first-request.md),
[async gönderim](https://docs.brightdata.com/api-reference/rest-api/scraper/asynchronous-requests.md),
[ilerleme ve indirme](https://docs.brightdata.com/products/scrapers/scrapers-library/async-requests.md).
