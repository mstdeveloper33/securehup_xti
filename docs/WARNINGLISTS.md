# MISP warninglists: domain ve IP için kaynaklı bağlam

17 Kasım 2026 · 0.153.0 · çekirdek şema 73 · engine/platform v1.

Bir IP'nin ortak altyapıda, özel ağda veya örnek adres aralığında bulunması;
bir domainin özel kullanım için ayrılmış olması araştırmayı yorumlamaya
yardımcı olur. Motor bu bilgiyi MISP'in açık kaynak listelerinden alır.
Eşleşmenin hangi liste ve hangi kayıt üzerinden oluştuğunu gösterir.
Bir eşleşme otomatik güvenli/zararlı kararı vermez; bulguları, IOC kayıtlarını,
istisna listesini veya analist kararlarını değiştirmez.

## Kullanım

Mevcut veri alanı eski şemadaysa önce `./xti migrate` çalıştırılır. Bu açık
işlem değişiklikten önce yedek alır. Yeni kurulum `./setup` ile hazırlanır.

```sh
./xti warninglists sync
./xti warninglists status
./xti warninglists lookup 104.21.6.71 --type ip
./xti warninglists lookup www.example.com --type domain
./xti research 104.21.6.71 --type ip
```

Yalnız `sync` internete çıkar. Örnek IP'ye veya domaine bağlantı kurulmaz;
incelediğin değerler MISP/GitHub'a gönderilmez. Okumalar indirilmiş kayıtları
kullanır. Tek listeyi yenilemek için `sync --list cloudflare`; birkaç liste
için `--list` tekrar edilebilir. Aynı listeyi tekrar seçmek reddedilir.

```sh
./xti warninglists history cloudflare --limit 10
./xti warninglists run-show CALISMA_KIMLIGI --offset 0 --limit 100
./xti --data-dir /operatorun/sectigi/alan --json warninglists status
```

`CALISMA_KIMLIGI` yerine çıktının verdiği kimlik kullanılır. Ayrıntı;
kaynak bağlantısı, commit, içerik SHA-256 özeti, liste sürümü, indirme zamanı
ve özgün liste üyelerini taşır. Eski çalışmalar da açılabilir; sayfalama
komutları seçili veri alanını korur.

## İlk dört liste

| Kimlik | Kaynağın sağladığı bağlam | Eşleşme |
|---|---|---|
| `cloudflare` | Cloudflare IP ağları | IPv4/IPv6 adresinin CIDR içinde olması |
| `rfc1918` | Özel IPv4 ağları | IPv4 adresinin CIDR içinde olması |
| `rfc3849` | Dokümantasyon için ayrılmış IPv6 ağı | IPv6 adresinin CIDR içinde olması |
| `rfc6761` | Özel kullanım domainleri | Tam hostname veya DNS etiketi sınırında alt domain |

Örneğin `www.example.com`, kaynakta bulunan `example.com` ile eşleşir;
`notexample.com` eşleşmez. IP sorgusu tek adres olmalıdır; CIDR sorgusu,
URL/hash, serbest liste URL'si ve regex bu ilk dilimde desteklenmez.
Domain sorgusu mevcut ASCII tam domain kuralını kullanır. Domain için
DNS çözümlemesi yapılıp örtülü IP eşleştirmesi eklenmez.

Kaynağın `known` / `false_positive` kategorisi özgün metadata olarak
korunur; XTI'nın o kayıt için verdiği bir hüküm değildir. Bu dört liste
bütün ortak altyapıları, tüm özel amaçlı adresleri veya interneti kapsamaz.

## Güncellik, hata ve geçmiş

Liste durumu `never`, `complete` veya `failed`; indirme güncelliği ayrı
`never`, `fresh`, `stale`, `future` alanıdır. Varsayılan eşik 168 saattir;
`status` ve `lookup --stale-after-hours` ile 1–8.760 saat seçilebilir.
Sayısal kaynak sürümü tarih olarak yorumlanmaz. Sabit bir RFC listesinin
eski sürüm numarası, yeni başarılı indirmenin eski olduğu anlamına gelmez.

- `matched`: eldeki geçerli listede eşleşme var. Liste eski veya son
  yenileme başarısız olabilir; eşleşmeyle birlikte bu durum da görünür.
- `no_match`: sorgu türüyle ilgili seçilmiş listeler yakın zamanda başarıyla
  alınmış, eldeki listelerde eşleşme yok. Güvenlik garantisi değildir.
- `incomplete`: eşleşme yok fakat ilgili liste hiç alınmamış, eski,
  gelecekte görünen saate sahip veya son denemesi başarısız.

`lookup.coverage_complete` yalnız sorgu türüne uygulanabilen bu listelerin
durumudur. Araştırmadaki `warninglists.coverage_complete` dört listenin
tamamını değerlendirir; araştırmanın üst düzey kanıt bütçesi
`coverage_complete` alanından ayrıdır.

Bozuk, boş, eksik, sınırı aşan veya sürümü gerileyen indirme önceki geçerli
listeyi değiştirmez. Başarısız deneme ayrı kaydedilir. Yeni geçerli listede
çıkarılan üye güncel eşleşmeden kalkar; eski içeriği ve çalışma kaydı kalır.
Aynı içerik tekrar indirilirse bir içerik kopyası, ayrı çalışma kayıtları
tutulur. Her liste bağımsız tamamlanır; dört listeden biri başarısızsa
toplam `sync` sonucu `partial` olur. Bir sert süreç kesintisi tamamlanmış
listeleri korur; henüz yazılmamış deneme için kalıcı iş/receipt garantisi yoktur.

Kaynak koşulları `./xti sources` kataloğunda; kayıtlı durumlar `sources status` ve `sources.status` içinde
`warninglist:LISTE_KIMLIGI` olarak da görünür. O genel görünümün güncellik
eşiği kendi `stale_after_hours` seçimidir; warninglists'in 168 saatlik
varsayılanını otomatik devralmaz.

## Engine ve firma platformu

Üç salt okunur işlem aynı firma veri alanını kullanır:

| İşlem | Parametreler | Sonuç |
|---|---|---|
| `warninglists.status` | İsteğe bağlı `stale_after_hours` | `checked_at`, eşik, dört liste ve notlar |
| `warninglists.lookup` | `indicator_type`, `value`; isteğe bağlı `stale_after_hours` | Kanonik sorgu, eşleşmeler, kaynaklar, kapsam ve veri durumu |
| `warninglists.run.get` | `run_id`; isteğe bağlı `offset`, `limit` | Çalışma, özgün liste üyelerinin sayfası, kaynak/lisans bilgisi |

`indicator_type`: `domain`, `ip`, `ipv4`, `ipv6`. Platform/engine ayrıntı
sayfası varsayılan 50; CLI varsayılan 100 üyedir. Sınır 1–500, başlangıç
0–1.000.000. İstek firma veya dosya yolu seçemez. Örnek:

```json
{"contract_version":1,"request_id":"liste-1","operation":"warninglists.lookup","parameters":{"indicator_type":"ip","value":"104.21.6.71"}}
```

`matches[]`: `list_id`, `run_id`, `snapshot_sha256`, `matched_entries`,
`matching_type`, `category`. `lists[]` son denemeyi ve son geçerli kaynağı
ayrı taşır: `latest_status`, `latest_run_id`, `last_attempt_at`, `error`,
`success_run_id`, `fetched_at`, `freshness`, `source_url`, `revision`,
`snapshot_sha256`, `source_version`, `entry_count`, `license`,
`license_reference`; ayrıca etiket, tür ve desteklenen sorgu türleri vardır.
`run.get` başarısız bir çalışmayı da açar; böyle bir çalışmanın liste
içeriği ve sürümü yoktur. Yerel çalışma kimliği kaybolmaz.

`research.show` sonucuna `nodes[].warninglist_matches` ve `warninglists`
eklenmiştir. Aynı okuma kesitindeki liste durumu araştırma `snapshot_id`
kimliğine katılır; yenileme/güncellik değişimi eski sayfa anahtarını
geçersiz kılabilir. Sırf liste eşleşti diye IOC/CTI ilişkisi üretilmez.
Örneğin başka kanıtı olmayan Cloudflare IP'si `not_recorded` araştırma
durumunda kalırken liste bağlamı yine görülebilir.

Güncelleme güvenilen işletici tarafından seçili alanda yapılır:

```sh
./xti --data-dir "$PWD/.xti-platform/firma-a" warninglists sync
./xti platform request --root "$PWD/.xti-platform" --company firma-a
```

İkinci komuta yukarıdaki JSON stdin üzerinden verilir. Firma listesi yoksa
kişisel veya başka firma kataloğuna dönülmez. 0.157.0 [kaynak işleri](SOURCE_JOBS.md)
seçili listeleri aynı firma kuyruğunda açıkça yeniler; okuma otomatik
yenileme başlatmaz. Her firma alanı ayrı kalır.

Başarılı okuma çıkışı 0'dır; eksik/eski kaynak normal veri durumu olarak
görünür. Kısmi/başarısız `sync`: `ok=false`, çıkış 3. Geçersiz seçenek:
CLI `validation_error` / 2, engine/platform `invalid_parameters` / 2.
Geçerli ama seçili alanda bulunmayan çalışma: `not_found` / 3. Bozuk veya
eski şemalı depolama: `storage_error` / 1. CLI `--json` zarfı ile engine
v1 zarfı ayrı sözleşmelerdir.

## Kaynak, maliyet ve işletim sınırları

Kaynak [MISP/misp-warninglists](https://github.com/MISP/misp-warninglists).
Seçilen veri ve kaynak koşulları
[`40e2b570fda2e5443a2d6fa1d1db16c37ab0a956`](https://github.com/MISP/misp-warninglists/tree/40e2b570fda2e5443a2d6fa1d1db16c37ab0a956)
üzerinde incelendi. Deponun [veri lisansı beyanı](https://github.com/MISP/misp-warninglists/blob/40e2b570fda2e5443a2d6fa1d1db16c37ab0a956/README.md#license)
CC0-1.0'dır ve kaynak bazlı koşullara dikkat çeker. X4BNet gibi ek koşul
bildiren listeler bu seçime alınmadı. Bu değerlendirme bütün MISP deposu
veya gelecekteki listeler için toplu ticari kullanım onayı değildir.

Her `sync` önce güncel commit'i çözer ve bütün dosyaları o commit'ten
ister. İncelenmiş commit değişirse o sürümün README içeriği de doğrulanır:
SHA-256 `6f107071dcc8ee3918db3d3b7182adb5c47a7fb2e110a46b03696c98acab3808`.
Kaynak/koşul belgesi değişmişse yeni inceleme yapılana kadar yenileme
durur ve önceki liste korunur. Bu kontrol README'deki zararsız bir değişimde
de durabilir; yeni hash körlemesine kabul edilmemelidir.

API anahtarı, ücretli abonelik veya MISP sunucusu gerekmez. GitHub'ın
erişim ve hız sınırları geçerlidir; ücretsiz olmak kesintisiz veya sınırsız
indirme garantisi vermez. Yerel aramalar sağlayıcı kotası tüketmez.

- Bir commit isteği, gerekirse bir README isteği ve seçilen en fazla dört
  liste isteği. Otomatik yeniden deneme yoktur; açık `sync` tekrar denenir.
- HTTPS, sabit resmî adresler, yönlendirme reddi, ortam proxy'si kullanılmaz.
  İstek başına socket zaman aşımı en fazla 15 saniye; 60 saniyelik toplam
  bütçe istekler/okumalar arasında kontrol edilir. Devam eden bir socket
  okuması kendi zaman aşımına kadar sürebilir; bu katı süreç sonlandırma süresi değildir.
- Commit yanıtı en fazla 256 KiB, README 128 KiB, liste 1 MiB / 10.000 üye.
  Sıkıştırılmış, eksik, yinelenen anahtarlı veya desteklenmeyen biçim reddedilir.
- Son iyi içerik ve tüm yenileme kayıtları saklanır. Otomatik geçmiş silme
  politikası yoktur; disk kullanımı mevcut depolama araçlarıyla izlenir.

Yeni Python bağımlılığı eklenmedi. PyMISPWarningLists değerlendirilmiştir;
bu dar seçim için depo verisi küçük kaynak adaptöründen alınır.
İndirilmiş veri dosyaları Git'e eklenmez. Şema 73 yalnız
`warninglist_snapshots` ve `warninglist_runs` tablolarını ekler; mevcut
kanıtları yeniden yazmaz. Normal ve platform yedekleri bu tabloları da
korur; eski kodla dönüş, önceki yedeğin ayrı boş alana açılmasını gerektirir.

[Mimari karar](decisions/0157-curated-warninglist-context.md) ·
[Kabul kaydı](ACCEPTANCE_REVIEW.md#01530--misp-warninglists-kabulü).
