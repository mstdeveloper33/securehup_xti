# URL ve dosya kimliği araştırması

17 Kasım 2026 · 0.154.0 · çekirdek şema 74 · engine/platform v1.

Bir URL'nin geçmişte nasıl gözlendiğini veya bir dosya kimliğinin hangi
bilinen dosya kaydında bulunduğunu gösterir. Dosyanın kendisi gerekmez;
MD5, SHA-1 veya SHA-256 değeri kullanılır. Kaynak yanıtı, alınma zamanı,
özgün kaynak bağlantısı ve sorgu geçmişi seçili veri alanında saklanır.

## Kullanım

Mevcut alan için önce `./xti migrate`; yeni alan için `./xti init`.
Geçiş eski veritabanını değiştirmeden önce yedek alır. Yeni bağımlılık yoktur.

```sh
./xti enrich fetch 'https://example.com/' --type url
./xti enrich lookup 'https://example.com/' --type url
./xti research 'https://example.com/' --type url

./xti enrich fetch 301c9ec7a9aadee4d745e8fd4fa659dafbbcc6b75b9ff491d14cbbdd840814e9 --type sha256
./xti research 301c9ec7a9aadee4d745e8fd4fa659dafbbcc6b75b9ff491d14cbbdd840814e9 --type sha256
./xti enrich history 301c9ec7a9aadee4d745e8fd4fa659dafbbcc6b75b9ff491d14cbbdd840814e9 --type sha256 --limit 10
./xti enrich run-show CALISMA_KIMLIGI
```

Hash örneği CIRCL dokümanındaki OpenSSL dosyasıdır; zafiyet veya zararlılık
örneği değildir. `CALISMA_KIMLIGI` yerine çıktının verdiği kimlik yazılır.
`--data-dir /secilen/alan` ve `--json` genel seçenekleri kullanılabilir.

Yalnız `fetch` sağlayıcıya URL/hash değerini gönderir. URL içindeki sorgu
parametreleri de gönderilir; özel oturum bağlantılarını bu hizmetlere
sorgulatmayın. Hedef URL açılmaz, yeni urlscan taraması gönderilmez,
dosya yüklenmez/indirilmez. `lookup`, `history`, `run-show` ve `research`
yalnız saklı kayıtları okur; API veya anahtar gerektirmez.

## Kaynaklar ve ücretsiz kullanım

| Kaynak | Sağladığı bilgi | Bu sürümün erişimi | Ticari ürün koşulu |
|---|---|---|---|
| CIRCL hashlookup | Bilinen dosya adı/boyutu, veri kaynağı, diğer dosya kimlikleri, varsa sağlayıcı güveni | Anahtarsız public HTTP API; best effort | Veriler CC-BY; CIRCL hizmet sayfasına atıf gerekir. Sayfa lisans sürümü belirtmiyor. |
| urlscan | Mevcut public tarama tarihi, başlangıç/son URL, son sayfanın IP'si, başlığı | Kimliksiz public aramada sağlayıcı kotası | Ticari ürüne veri dahil etmeden önce sağlayıcı anlaşması netleştirilmeli. |

Koşullar 17 Kasım 2026'da resmî [CIRCL hizmet sayfasından](https://www.circl.lu/services/hashlookup/),
[urlscan şartlarından](https://urlscan.io/terms/) ve
[ticari kullanım açıklamasından](https://docs.urlscan.io/pages/faq) incelendi.
Bu sürüm ücretli anahtar kullanmaz; ücretsiz erişim sınırsız erişim veya
hizmet garantisi anlamına gelmez. Kaynak şartları ileride yeniden incelenir.
CIRCL sunucusu/Python istemcisi kopyalanmadı; standart HTTP adaptörü kullanılır.

URLhaus'un güncel topluluk API'si anahtar ister; ticari kullanım için ayrıca
koşullar vardır. Bu dilime eklenmedi. PhishTank'ın arşiv şartları güncel veri
izinleri gibi kabul edilmedi. [Kaynak seçimi kararı](decisions/0158-url-hash-source-context.md).

## Sonuçların anlamı

- `never`: bu değer seçili alanda sorgulanmadı.
- `matched`: yanıtta bu kesin değer için kaynak kaydı var.
- `no_match`: sağlayıcının geçerli yanıtında eşleşme yok; internet genelinde yokluk veya güvenlik kanıtı değildir.
- `failed`: sorgu/yanıt doğrulanamadı. `successful_run` ve `records` önceki geçerli yanıtı gösterebilir.

`latest_run` son denemeyi, `successful_run` son geçerli yanıtı taşır.
Son geçerli yanıt boşsa, eski eşleşme güncel sonuç gibi gösterilmez; geçmişten
açılabilir. Aynı yanıtı tekrar almak yeni çalışma kaydı oluşturur, özgün
yanıt byte'ları SHA-256 ile tek kopya saklanır. Başarısız içerik yayımlanmaz;
hata makbuzu tutulur. Yanıt hash'i içerik bütünlüğü denetimidir, dijital imza
veya sağlayıcı doğruluk garantisi değildir.

`freshness` yanıt alınma zamanını ölçer: `fresh`, `stale`, `future`, `never`.
Varsayılan eşik 24 saat; `lookup --stale-after-hours 48` gibi değiştirilebilir.
urlscan'in tarama tarihi ayrıca `records[].observed_at` içindedir. CIRCL
dosyasının ilk görülme tarihi bilinmiyorsa `observed_at=null` kalır.

Tek `fetch` tek istek yapar; otomatik toplu sorgu veya tekrar yoktur.
Kaynak başına aynı veri alanında en az iki saniye aralık, kalıcı sağlayıcı
beklemesi ve `Retry-After` uygulanır. Bekleme uzunsa yeni istek gönderilmez.
Bu sınır farklı firma alanlarını veya sunucuları koordine eden dağıtık kota
değildir. İşletim ekibi ortak çıkış kotasını ayrıca yönetir.
HTTP bağlantı/okuma süre sınırı 20 saniye, yanıt üst sınırı 2 MiB'dir;
bu socket sınırı bütün komut için kesin duvar saati garantisi değildir.

URL için ilk 20 arşiv kaydı alınır. `has_more`, `search_date_limit_days`
ve tam URL eşleşmesi olmadığı için ayrılan `excluded_count` görünür.
Bu sürüm sağlayıcı arşivini sayfalayarak bütünüyle indirmez.
Şema/host/varsayılan port mevcut IOC kurallarıyla normalleşir; yolun harf
büyüklüğü, sorgu değeri ve HTTP/HTTPS birbirine karıştırılmaz.

## İlişki araştırması

`research --type url|md5|sha1|sha256` ve `research.show` artık bu kökleri de
destekler. Mevcut IOC/CTI iddiaları korunur. `nodes[].enrichment` son deneme,
korunan yanıt, kaynak koşulları ve kayıt ayrıntılarını içerir.

| İlişki | Kanıtın anlattığı |
|---|---|
| `provider_file_hash` | CIRCL aynı dosya kaydında bu kimlikleri bildirmiş. Alt paket/parent kimlikleri eşdeğer sayılmaz. |
| `archived_navigation` | urlscan kaydının başlangıç ve son URL'si farklı. Ara yönlendirme zinciri veya nedenine dair iddia yok. |
| `archived_page_ip` | Kaynak, son sayfa için o IP'yi bildirmiş. Başlangıç URL'sine yanlış atanmaz. |

Bu bağlantılar `source_context` türündedir. Tarihî kaynak iddiasını doğrulanmış
gözleme, IOC'ye, allowlist kararına veya otomatik alarma dönüştürmez.
Dosya hash'leri için eşit dosya hükmü verilmez; özellikle eski hash algoritmaları
çakışma güvenliği sağlamaz. Kaynak güveni XTI risk puanı değildir.

Yalnız sorgulanıp saklanmış kökün yanıtları genişletilir. Örneğin bir URL'nin
kaydında IP olması, o IP kökünden bütün URL arşivinin ters aranacağı anlamına
gelmez. Kaynak arşivindeki ek sonuçlar `enrichment_result_window` kısıtıyla
görünür. Eski başarılı yanıtın ilişkileri son sorgu başarısız olduğunda
kanıt tarihi ve kaynak durumuyla birlikte kalır.

## Engine ve firma platformu

Aynı stdin JSON hem `./xti engine` hem firma seçilmiş `platform request`
üzerinden okunur. HTTP API/oturum eklenmedi. Firma ve dosya yolu istekte
seçilemez; diğer firmanın çalışma kimliği `not_found` döndürür.

```json
{"contract_version":1,"request_id":"url-context-1","operation":"enrichment.lookup","parameters":{"indicator_type":"url","value":"https://example.com/"}}
```

| İşlem | Parametreler |
|---|---|
| `enrichment.lookup` | `indicator_type`, `value`; isteğe bağlı `provider`, `stale_after_hours` (1–8760) |
| `enrichment.history` | `indicator_type`, `value`; isteğe bağlı `provider`, `offset` (0–1.000.000), `limit` (1–100; engine varsayılanı 50, CLI 20) |
| `enrichment.run.get` | `run_id` |

`provider` URL için `urlscan`, hash için `circl`; uyumsuz seçim reddedilir.
Engine okumasının `status=complete` olması canlı kaynağın başarılı olduğu
anlamına gelmez; `data.status` ve kaynak çalışması ayrıca incelenir.
Kaynak yenilemesi yalnız işletici CLI'sindedir. Ücretli kaynak, otomatik
platform yenileme işi, sınırsız API ve geniş malware/verdict motoru bu
dilimin teslimi değildir.
