# IOC yaşam döngüsü ve kanıt güncelliği

18 Kasım 2026 · 0.165.0 · sonuç modeli 1 · politika `ioc-lifecycle-v1`.

Bir IP/domain/URL/hash için kayıtlı kaynak iddialarını değerlendirir:
iddia etkin mi, geçerlilik süresi dolmuş mu, tarih neyi ifade ediyor,
son toplama başarılı mı, inceleme neden gerekli? Mevcut kaynak güven
puanı değişmez; sonuç zararlılık olasılığı veya otomatik engelleme değildir.

## Terminal kullanımı

Önce mevcut katalogdan gösterge seç:

```sh
./xti ioc list
./xti ioc lifecycle ipv4 192.0.2.10
./xti --json ioc lifecycle ipv4 192.0.2.10
./xti ioc lifecycle domain example.com --fresh-days 3 --stale-days 14 --source-stale-hours 48
```

IP/domain örnektir; listendeki gerçek değerle değiştir. `lifecycle` kayıtlı
veriyi okur. Kayıt yoksa `not_recorded` döner; güvenli olduğu söylenmez.
Yeni kaynak verisi gerektiğinde mevcut `./xti ioc sync --source feodo`
ve `./xti ioc sync --source certpl` toplama komutları ayrı çalıştırılır.
Bu kaynakların kullanım koşulları ve erişim durumu değişmez.

Çıktıda her iddianın kaynağı, referansı, özgün güveni, tarihleri, son
başarılı/başarısız toplaması, inceleme gerekçeleri ve kanıt kimlikleri vardır.

## Tarihler ve kararlar

| Alan / durum | Anlamı |
| --- | --- |
| `provider_reported_observation` | Feodo'nun bildirdiği IP gözlemi; `last_online` gün hassasiyetinde, birden çok port/kayıt IP altında toplulaşabilir. Kurumda saldırı gözlemi değildir. |
| `provider_list_version` | CERT Polska kaydının alındığı listenin sürüm tarihi. Aynı etkin kaydın yeni listede bulunması tekil olay tarihi üretmez. |
| `unspecified_assertion_time` | Eski elle kayıt, açık gözlem tarihi ile varsayılan giriş zamanını ayırmıyor. Gerçek olay zamanı tahmin edilmez. |
| `reported_observation_at` | Yalnız desteklenen sağlayıcı gözlem zamanı; diğer durumlarda `null`. Özgün `assertion_first_seen_at` / `assertion_last_seen_at` ayrıca korunur. |
| `claim_state` | `active`, `expired`, `not_yet_valid`, `revoked`; güncellikten ayrı geçerlilik durumu. |
| `revocation_basis` | `feed_absence`: son tam listeden kaldırılmış; `local_decision`: yerel geri çekme. Diğer durumlarda `null`. İkisi de güvenli hükmü değildir. |
| `collection` | Kaynak geneline ait son deneme ve son başarılı toplama. Tekil yeni saldırı kanıtı değildir. |
| `needs_review` | En az bir kaynak bağlamında eski/belirsiz tarih, başarısız/eski toplama veya saat tutarsızlığı var. Gerekçeler kaynak satırındadır. |
| `current_context` | İncelenen etkin iddia, kaynak zamanı ve toplama yerel eşiklerde güncel. Doğrulanmış tehdit anlamına gelmez. |
| `historical_only` | İddialar geri çekilmiş, süresi dolmuş veya henüz geçerlilik aralığına girmemiş. Geçmiş korunur. |

Varsayılan kanıt yaşı eşikleri IP/domain/URL için 7/30, hash için 30/180
gündür. İlk eşikten küçük yaş `recent`, ilk eşikten itibaren `aging`, ikinci
eşikten itibaren `stale` olur. Bunlar yerel inceleme tercihidir, sağlayıcının
garantisi veya bilimsel risk puanı değildir. `fresh_days < stale_days`
ve her ikisi en fazla 3650 olmalı. Kaynak toplama için varsayılan 24 saat;
`source_stale_hours` 1–8760 olabilir. Saatten ilerideki kayıtlar ayrıca
`clock_anomaly` gerekçesiyle değerlendirilir.

Yeni indirme zamanı, kayıtlı sağlayıcı gözleminin yerini almaz. Son deneme
başarısızsa önceki başarılı toplama ve iddia korunur. Farklı kaynak adları
bağımsız doğrulama sayısı değildir; güven puanları toplanmaz. Aynı kaynak
birden çok iddia taşıyabilir; kaynak ve iddia sayıları ayrı verilir.
Feodo/CERT Polska kayıtlarındaki 50/100, mevcut XTI nötr kaynak politikasıdır;
sağlayıcının ölçtüğü bir olasılık veya bu değerlendirmenin yeni puanı değildir.

## Engine ve firma sözleşmesi

```sh
./xti engine <<'JSON'
{"contract_version":1,"request_id":"ioc-review-1","operation":"ioc.lifecycle","parameters":{"indicator_type":"ipv4","value":"192.0.2.10"}}
JSON
```

Aynı JSON, `./xti platform request --root KOK --company FIRMA` ile seçili
firma alanında çalışır. JSON dosya yolu/firma seçemez. Bilinmeyen veya
kapalı firma kişisel çalışma alanına düşmez. .NET/React ekibi aynı işlemi
kullanabilir; yeni HTTP sunucusu veya oturum yönetimi eklenmedi.

Parametreler `indicator_type`, `value`, `fresh_days`, `stale_days`,
`source_stale_hours`, `offset`, `limit`, `expected_snapshot` olur. Türler
`domain`, `ipv4`, `ipv6`, `url`, `md5`, `sha1`, `sha256`.
Varsayılan 50, en fazla 100 iddia sayfalanır. Toplamlar tüm doğrulanmış
tekil IOC kapsamınadır. Devam sayfasına önceki `snapshot_id` değerini
`expected_snapshot` olarak ver. Veri, eşikler veya güncellik sınıfı
değişmişse `snapshot_changed` alınır; yalnız birkaç saniye geçmesi
sayfalamayı bozmaz. Snapshot kimliği bağımsız dijital imza değildir.

## Saklama, sınırlar ve sürüm uyumu

İddia/olay ve kaynak makbuzları aynı salt okuma transaction'ında
doğrulanır. Tek IOC için en fazla 500 iddia, 10.000 olay, 20.000 makbuz ve
toplam 16 MiB saklı okuma bütçesi vardır. Sınır aşımı `storage_error`
verir; eksik kapsam tam sonuç gibi sunulmaz. Başka IOC'nin büyük kataloğu
seçilen IOC kapsamına katılmaz. Okuma kayıt alanı oluşturmaz.

Çekirdek şema 76, kuyruk 3 ve dış JSON zarfı v1 kalır; 0.164.0'dan
bu sürüme yeni migration gerekmez. Değerlendirme kayıtları değiştirmez,
ayrı kalıcı geçmiş oluşturmaz. Mevcut araştırma/firma kuyruğu öncelik v7
ve eski dondurulmuş incelemeler aynı kalır. Bu teslim gerçek sighting
günlüğü, otomatik olay atfı veya zamanla güven puanı azaltma motoru değildir.

[Mimari karar](decisions/0170-ioc-lifecycle-assessment.md),
[kabul kaydı](ACCEPTANCE_REVIEW.md), [test çalışma düzeni](TESTING.md).
