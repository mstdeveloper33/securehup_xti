# Ortak kanıta dayanan inceleme grupları

0.176.0 · çekirdek86 · grup modeli1 / `research-groups-v1` · dış JSONv1.

Birbirine bağlanan domain, IP veya raporları tek tek takip etmek yerine
ortak dayanağı olan kayıtları bir grup altında inceleyebilirsin. Örneğin
iki domain aynı IP'de gözlenmişse hangi kontrollerin bu bağı kurduğunu ve
gözlemlerin yakın tarihlerde olup olmadığını görürsün. Grup kararı, aynı
saldırgan veya doğrulanmış tehdit kararı değildir.

Bu akış saklı motor verisini kullanır. İnternetten yeni bilgi mevcut
`collect`, kaynak ve yüzey kontrolleriyle alınır; ardından grup yeniden
değerlendirilir. `groups` çalıştırmak yeni tarama veya ücretli API çağrısı
başlatmaz. Firma ayrımı mevcut çalışma alanı/JSON girişinden gelir.

## Araştırma ve önizleme

```sh
./xti research securehup.com --type domain --max-hops 4
./xti groups preview domain securehup.com --max-hops 3 --time-window-hours 24
./xti --json groups preview domain securehup.com
./xti research securehup.com --type domain --groups --max-hops 3
```

Araştırmanın varsayılanı iki, izinli üst sınırı dört adımdır. Doğrudan
`groups preview` varsayılanı üç adım; `research --groups` araştırmanın
seçilen adımını kullanır. Aynı ayarlar aynı sonucu üretir. Grup görünümü
100 düğüm/200 bağlantı ve mevcut kaynak okuma bütçelerini kullanır;
`research --groups` ile bu sabitlerin dışında düğüm/kenar/güncellik ayarı
verilirse sessizce yok saymak yerine hata döner.

Gruplar üç açık kuraldan oluşur:

| Dayanak | Neyi gösterir? | Neyi çıkarmaz? |
| --- | --- | --- |
| Aynı DNS IP adresi | Domainlerin saklı DNS kontrollerindeki ortak adres | Aynı sahiplik, aynı kampanya veya zararlılık |
| Aynı sunulmuş TLS sertifikası | En az iki domain kontrolünde gerçekten görülen sertifika | Yalnız sertifika SAN alanındaki adlardan sahiplik |
| Aynı rapor metni | IP/domain/URL/hash adaylarının aynı saklı metinde geçmesi | Metinde geçen her değerin tehdit olması |

Her grup tek ortak dayanağa bağlıdır. A–B aynı IP, B–C başka IP kullanıyorsa
iki grup kalır; A/B/C tek kampanya diye birleştirilmez. Benzer marka/aktör
adı tek başına grup oluşturmaz. Aynı metnin farklı URL'lerdeki kopyaları
tam metin SHA-256 ile birleştirilir; özgün belge kimlikleri ve kaynakları
korunur. Başlığı/çıkarılan metni farklı benzer haberler otomatik kopya
sayılmaz. Kaynak veya kopya sayısıyla güven oylaması yapılmaz.

Zaman sonuçları `near_observations`, `separated_observations`, `unknown`.
Her üyenin gerçek gözlem noktalarını içeren en dar zaman aralığı hesaplanır.
Varsayılan yakınlık 24 saat, seçilebilir aralık 0–168 saat. Bir üyenin olay
zamanı bilinmiyorsa sonuç bilinmiyor kalır. Yayın tarihi veya belgenin
indirilme zamanı olay zamanı sayılmaz. İlk ve son görülme arasındaki bütün
günlerde faal olduğu varsayılmaz; yakın gözlem kesintisiz eşzamanlılık değildir.

## Kaydetme, karar ve değişiklik

Önizleme `id`, `evidence_sha256`, `root` ve `scope` döndürür. Aşağıdaki
`GRUP` ve `KANIT` yerlerine bu çıktının kimlikleri yazılır; kapsam ayarları
önizlemeyle aynı olmalıdır.

```sh
./xti groups capture domain securehup.com GRUP \
  --max-hops 3 --time-window-hours 24 --evidence-sha256 KANIT \
  --expected-revision 0 --idempotency-key ilk-grup-kaydi
./xti groups show GRUP
./xti groups review GRUP --decision uncertain \
  --reason 'Ortak barındırma olabilir; bağımsız kanıt gerekiyor.' \
  --evidence-sha256 KANIT --expected-revision 1 --idempotency-key ilk-inceleme
./xti groups refresh GRUP --expected-revision 2 --idempotency-key yeni-kontrol-1
./xti groups queue --limit 20
./xti groups list --limit 20
```

Kararlar `accepted`, `rejected`, `uncertain`, `withdrawn`. Gerekçe zorunlu.
`accepted`, bu donmuş grup dayanağını analistin kabulüdür. Eksik kapsamın
kabul edilmesi reddedilir. Aynı işlem anahtarı ilk sonucu ağsız/yazmasız
getirir; yeni kontrol için yeni anahtar gerekir. Aynı anahtarla farklı
istek veya eski `expected_revision` reddedilir.

`refresh` yeni üye, görünümden çıkan üye, kanıt özeti ve zaman değişikliğini
kaydeder. Eski kanıt ve kararlar silinmez. Kanıt değiştiğinde eski karar
`review_current=false` olur; önce yeni kanıtı gösterip tekrar karar verilir.
Kararı geri çekmek eski gerekçeyi silmez. Eski kararın aynısı değişmemiş
kanıtla yeniden doğrulanırsa güncel olabilmesi korunur.

- `current`: son tam kontrolde grup mevcut.
- `indeterminate`: son okuma eksik; önceki grup korunur, silindi denmez.
- `not_in_view`: seçilen kök/adım ve mevcut kayıtlarda grup görünmüyor;
  gerçek dünyada kaybolduğu anlamına gelmez.
- `captured`: ilk kaydedilmiş grup.

`groups queue` kayıtlı grupları güncel yerel kanıtla karşılaştırır; kendi
başına veritabanını değiştirmez. Sayfalama **incelenen kayıtlı gruplar**
üzerindendir: ilk sayfada bekleyen grup sıfır olsa bile `has_more=true`
olabilir. `next_offset` ve `expected_snapshot` ile devam edilir. Kesit
koruması kayıtlı listeyi sabitler; kaynak kanıtı her sayfada yeniden okunur.

```sh
./xti groups monitor GRUP --rounds 3 --interval-seconds 60
```

Monitor en fazla 100 tur ve tur arası 1–3600 saniyeyle sınırlıdır; beklerken
yazıcı kilidi tutmaz. Her tamamlanan tur `refresh` geçmişine yazılır. Yeni
kaynak verisi geldiyse fark görünür. Yeni daemon veya dış kaynak toplama
zamanlayıcısı değildir. Süreç kesilirse commit edilmiş turlar korunur;
bu komut aynı turu sürdürme kimliği değil yeni takip çalışması oluşturur.

## Mevcut akışlarla kullanım

`review-queue` / `company.review` kayıtlı grupları ayrı `groups` bölümünde
gösterir. `group_offset/group_limit` ile sayfalanır. Bu bölüm son saklı
durumdur; anlık değişiklik karşılaştırması için `groups.queue` kullanılır.
Kuruluş raporu, açıkça bağlanan domain kökünün gruplarını ve bunların
vaka bağlantılarını içerir; grup içindeki her domaini otomatik kuruluş
varlığı yapmaz. HTML dışa aktarımı aynı bölümü içerir.

```sh
./xti cases evidence-add VAKA --type research_group --evidence-id GRUP \
  --reason 'Bu grup kanıtı olay incelemesiyle ilgili.'
```

Vaka, grup/karar/zamanın o anki kopyasını saklar. Sonraki `refresh` vaka
kanıtını kendiliğinden değiştirmez. Vaka ayrıntısı gruptaki üyeleri,
kaynak kanıtlarını ve bağlanma anındaki kararı açar. Kayıtlı vaka bağlantısı
ortak araştırmada görünür, kaynak iddiası haline gelmez.

## JSON sözleşmesi

`engine` salt okumaları; `platform request` aynı okumaları ve firma
yazmalarını sunar. Motor hizmeti/depo portu aynıdır. Platform yazmalarında
`expected_workspace_id` zorunlu, kimlik doğrulama platform ekibindedir.

| İşlem | Parametreler | Sonuç |
| --- | --- | --- |
| `groups.preview` | `indicator_type,value`; isteğe bağlı `max_hops,time_window_hours,offset,limit,expected_snapshot` | Aday gruplar, özgün kanıt, zaman/yanıltıcı bağlam, kapsam ve saklı karar özeti |
| `groups.list` | `offset,limit,expected_snapshot` | Saklı grupların son kayıt özeti |
| `groups.show` | `identifier` | Tam donmuş kanıt, karar, sürüm ve değişiklik geçmişi |
| `groups.queue` | `offset,limit,expected_snapshot` | Güncel kanıtla fark / yeniden inceleme penceresi |
| `groups.capture` | `indicator_type,value,identifier,evidence_sha256,expected_revision,idempotency_key`; isteğe bağlı `max_hops,time_window_hours` | Yeni donmuş grup veya ilk işlemin tekrar sonucu |
| `groups.review` | `identifier,evidence_sha256,decision,reason,expected_revision,idempotency_key` | Dayanağa bağlı insan kararı |
| `groups.refresh` | `identifier,expected_revision,idempotency_key` | Yerel yeniden kontrol ve kalıcı fark |

Sayfa 1–20 grup. En fazla 50 üye, 200 bağlantı ve 192 KiB grup kanıtı.
Sığmayan grup `omitted_group_count` ve `group_size_limit` ile belirtilir;
sessiz başarı veya tam tarama sayılmaz. Kaynak kayıt okuma limitleri de
`limitations` içinde taşınır. Tek grubun geçmişi 1.000 olay/4 MiB, tüm
çalışma alanının grup günlüğü 10.000 olay/64 MiB ile sınırlı. Sınırda eski
kayıt silinmez; yeni yazma reddedilir. Otomatik arşiv/purge bu sürüme
eklenmedi; döngü sıklığı ve disk sınırı bu kayıt maliyetiyle seçilir.

Geçerli ama bulunamayan kimlik `not_found`; eski sürüm `revision_changed`,
değişmiş kanıt `source_changed`, farklı aynı anahtar `idempotency_conflict`,
yanlış firma kimliği `scope_mismatch`. Bozuk günlük veya silinmiş kuyruk
sonu hata verir; kalan kayıtlar tam liste diye gösterilmez.

## Güncelleme ve kurtarma

```sh
git pull --ff-only
./xti migrate
./xti doctor
```

`migrate` önce benzersiz eski şema yedeğini alır; grup günlüğünü ekler,
vaka kanıt türünü tek transaction'da genişletir. Eski kayıt, rowid ve hash
korunur. Eski motor şema86'yı okuyamaz. Geri dönüş gerekiyorsa geçiş öncesi
yedek eski kodla **yeni/boş** veri alanına açılır; güncel veritabanı üstüne
yazılmaz. Geçiş sonrası yeni grup olayları eski yedekte bulunmaz.

[Sabit kapsam ve test sonuçları](roadmap/RELATIONSHIP_GROUP_DELIVERY.md),
[mimari karar](decisions/0181-evidence-backed-research-groups.md),
[ticari kaynak kararları](COMMERCIAL_SOURCE_REVIEW.md).
