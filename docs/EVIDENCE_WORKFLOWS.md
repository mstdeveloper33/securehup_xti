# Rapor akışları, ilişki önerileri ve gerçek görülmeler

0.169.0 ekleri: `relationships queue` değişen dayanakları yeniden incelemeye
getirir; `reports fetch` izinli yayıncı ana metnini alır; `journals`
geçmişi silmeden sıkıştırma/geri alma sağlar. Çekirdek 79, ücretsiz pypdf
7.1.1; kuyruk/iş modeli korunur. [Güncel rehber](PUBLISHER_REVIEW_RETENTION.md).

19 Kasım 2026 — 0.168.0. Çekirdek 78, kuyruk 3, kaynak işi modeli 4.
Engine/platform dış sözleşmesi v1, araştırma modeli 3 ve öncelik v8 korunur.
Bu belge sekiz maddelik paketin kullanılabilir motor kapsamını anlatır.
[Teslim ve kabul tablosu](roadmap/ENGINE_EIGHT_DELIVERY.md),
[kabul sonuçları](ACCEPTANCE_REVIEW.md).

## Neler yapabilirsin?

| İş | Sonuç |
| --- | --- |
| Haber veya firma içeriklerini rapora al | Değişen metnin yeni sürümü saklanır; aynı metin çoğalmaz. |
| Bir göstergenin ilişki adaylarını incele | Aynı rapor, ortak IP veya sunulmuş sertifika üzerinden gerekçeli aday görürsün. |
| Kimlikleri birlikte gör | Kabul ettiğin eşleştirmeler tek görünümde açılır; özgün kayıtlar silinmez. |
| IP kayıt bağlamını al | RIPEstat üzerinden ilgili internet kayıt kuruluşunun seçilmiş ağ/kuruluş alanları gelir. |
| Sensör olayını kaydet | Hangi göstergenin hangi sensörde ne zaman görüldüğünü kaynak olay kimliğiyle saklarsın. |
| Kaynak işini özelleştir | Adım sırasını, rapor kaynağını/sınırını ve hata sonrası davranışı seçersin. |
| IOC kaynaklarını karşılaştır | Kaynak iddiası, geçerlilik, tarih temeli, son toplama ve yerel görülme ayrı görünür. |

Bu işler terminalden ve mevcut firma JSON girişinden aynı servislere ulaşır.
Oturum/rol yönetimi, React veya .NET uygulaması gerekmez; bunların ileride
ekleneceği platform bu sözleşmeleri çağırabilir. Yeni ücretli API veya
Python bağımlılığı eklenmedi.

## Güncelleme

Mevcut kişisel veri alanını açıkça yükselt:

```sh
./xti migrate
```

Geçiş önce eski veritabanını ayrı dosyaya yedekler. Eski tabloları ve kanıt
kimliklerini yeniden yazmaz; `evidence_journal` tablosu eklenir. Eski kodun
geri kullanılması gerekirse eski yedeği **yeni, boş bir hedefe** geri yükle.
Firma alanında yönetici önce `platform backup` alır, sonra seçili firmanın
veri dizininde `./xti --data-dir /kesin/firma/veri/dizini migrate` çalıştırır.
Kurulu kuyruk zaten 3 ise ayrıca kuyruk geçişi yoktur. Eski kuyruk 1/2 için
mevcut `platform jobs-migrate` / `source-jobs migrate` yolu korunur.

## Otomatik rapor ve iş sırası

```sh
./xti source-jobs plan 1.1.1.1 --type ipv4 \
  --source news:cisa --source ripestat-whois --source report-capture \
  --step ripestat-whois --step news:cisa --step report-capture \
  --capture-source news --capture-limit 10 --failure-policy stop
```

Komut biçimini `./xti source-jobs plan --help` ile kontrol et. Plan işlemi
internete çıkmaz. Onayladığın planı mevcut `source-jobs submit` veya firma
`sources.jobs.submit` işlemiyle kuyruğa alıp worker çalıştırırsın. Plan özeti
ve firma yazmalarında `expected_workspace_id` zorunluluğu korunur.

`source_order` seçilen her kaynağı tam bir kez içerir. Seçilmiş haber
yenilemeleri `report-capture` öncesinde olmalıdır. Son inceleme kaydı
istenmişse en sonda kalır. En çok beş kaynak ve bir inceleme adımı vardır;
mevcut süre/istek sınırları korunur. İptal ve süre denetimi adımlar arasında
yapılır; devam eden adımın yaptığı işi geri almaz.

`continue` varsayılandır: önceki kaynak başarısız olsa da sonraki adım
çalışabilir. Böyle bir rapor eski saklı kaynaktan alınabilir; belge özgün
kaynak çalışma kimliğini ve alınma zamanını taşır. `stop`, başarısız veya
kısmi adımdan sonra bekleyen adımları `dependency_failed` ile atlar.
Kuyruktaki işin mevcut son durum/tekrar/iptal kuralları değişmez.

`report-capture` kaynağı `news` veya `mentions`; sınırı 1–20 belgedir.
Seçilmiş haber sağlayıcıları varsa yalnız o sağlayıcıların kayıtları
seçilir, yoksa yerel haber kataloğu kullanılır. Son değişen kayıtlar önce
alınır. Fazlası varsa sonuç `partial` ve `has_more=true` olur; bütün
kataloğun işlendiği söylenmez. `mentions` yalnız önceden saklanmış firma
içeriklerini kullanır; Tavily isteği veya makale indirme yapmaz.

Rapor seçimi firma çalışma alanıyla sınırlıdır. **İşin kök göstergesi,
seçilen her haberin o firmayla ilgili olduğu anlamına gelmez.** Haber metni
ile özgün arama kapsamı ayrı saklanır. Yeni adım metnin özetini tekrar
doğrular; seçim sırasında değişmiş kaynak `source_changed` ile reddedilir.
İş makbuzu rapor UUID'si, belge sürümü ve içerik SHA-256'sını içerir.
Kesilen iş için açık tekrar gerekir; önceki belge kaydı korunur. Haber
yenilemesi tekrar çalışacaksa ona bağlı rapor adımı da yeniden değerlendirilir;
eski rapor başarısı yeni haberin yerine kullanılamaz.

## İlişki önerileri

```sh
./xti relationships candidates ipv4 192.0.2.10
```

İlk komut yalnız saklı kanıtta en çok iki adımlık yolları inceler. Kurallar:

- `shared_report`: aynı kayıtlı belge sürümünde iki gösterge geçer.
- `report_review_context`: göstergeyi anan rapora insanın CTI bağlantısı vardır.
- `shared_dns_address`: iki domainin saklı DNS gözlemi aynı IP'ye bağlanır.
- `shared_certificate`: iki domain kontrolünde aynı sertifika sunulmuştur.

Her adayda dayanak kenarları, kaynak/olay/çalışma kimlikleri, zamanlar ve
`evidence_sha256` vardır. `coverage_complete` ve `limitations` incelenen
pencereyi açıklar. Tarihî veya geri çekilmiş dayanak ayrıca işaretlenir.
Bu kurallar ortak saldırgan, sahiplik veya kötü niyet kararı vermez.

```sh
./xti relationships review ipv4 192.0.2.10 ADAY_SHA256 \
  --evidence-sha256 DAYANAK_SHA256 --decision accepted \
  --expected-revision 0 --idempotency-key inceleme-001 \
  --reason 'Kaynak metnindeki birlikte geçme incelendi.'
```

İlk kararda beklenen sürüm 0'dır. Sonraki kararda yanıttaki güncel sürümü
kullan. `accepted`, `rejected`, `uncertain`, `withdrawn` desteklenir.
Kararlar ayrı günlükte kalır; kabul etmek CTI ilişki tablosuna otomatik
bağlantı yazmaz. Kanıt değişirse eski karar görünür ama
`review.evidence_current=false` olur. Eski dayanakla yeni karar yazılamaz.
Görünüm dışında kalan eski kararların kimlikleri ayrıca listelenir; bunlar
`relationships show` ile okunabilir. Geri çekme önceki kararı silmez.
`relationships show ADAY_SHA256`, hakkında karar kaydedilmiş adayı ve
karar geçmişini açar. Henüz karar verilmemiş adayın dayanağı
`relationships candidates` çıktısındadır.

## Birleşik kimlik görünümü

```sh
./xti identity view KAYIT_UUID --kind entity
./xti identity view KURULUS_UUID --kind organization
```

Mevcut `investigate` kimlik öneri/karar akışındaki **kabul edilmiş** bağlar
izlenir. Özgün kayıtlar, adlar/alternatif adlar, kaynak iddiaları ve karar
geçmişleri birlikte döner. Bekleyen veya reddedilen eşleştirme gruba katmaz.
Geri çekilen bağ çıkar; başka kabul edilmiş yol varsa grup bağlı kalır.
Çevrimler tekrar üretmez. En çok 100 üye gösterilir; sınırda kapsam kısmi
işaretlenir. Farklı firma alanları veya farklı CTI türleri birleştirilmez.
Kalıcı kimlik birleştirme/silme yapılmaz.

## Gerçek görülme kayıtları

```sh
./xti sightings record ipv4 192.0.2.10 \
  --source kurum-edr --sensor ag-gecidi-1 --source-event-id olay-42 \
  --observed-at '2026-11-19T09:00:00+03:00' \
  --reference 'kurum-log:olay-42' --idempotency-key gorulme-42
./xti sightings list ipv4 192.0.2.10
./xti sightings show GORULME_UUID
./xti sightings revoke GORULME_UUID --expected-revision 1 \
  --reason 'Sensör kaydı yanlış eşleştirilmiş.' --idempotency-key geri-42
```

Örnek tarih yerine gerçek olay zamanını kullan. Motorun saatinden beş
dakikadan fazla ilerideki olay reddedilir. Eski zamanlı olaylar kabul edilir;
olayın zamanı ile motora kayıt zamanı karışmaz. Olay kimliği firma içinde
`source + sensor + source_event_id` birleşimidir. Aynı olayı tekrar göndermek
ikinci görülme yaratmaz. Aynı kimlikle farklı içerik `source_event_conflict`
verir. Farklı tekrar anahtarıyla aynı olayı göndermek yeni bir istek makbuzu
ve kayıt sürümü oluşturabilir; görülme sayısı yine birdir.

Ham log, parola veya erişim anahtarı gönderme: giriş yalnız bu küçük alanları
alır. Bu özellik SIEM/EDR'den otomatik veri çekmez; mevcut platform veya
operatör bu JSON/CLI girişine yapılandırılmış olay iletir. Sensörün
bildirdiği görülme, motorun bağımsız saldırı doğrulaması değildir.
Araştırmada `local_sighting` ve `sensor_reported_observation` olarak görünür.
Gösterge başına en çok 25 görülme kanıtı grafikte gösterilir; fazlası kısmi
işaretlenir ve `sightings list` ile sayfalanır. Sadece görülmesi olan
göstergeler de firma inceleme köklerine eklenir.

## Kaynak karşılaştırması ve IP kayıt bilgisi

```sh
./xti ioc compare ipv4 192.0.2.10
./xti enrich fetch 1.1.1.1 --type ipv4 --provider ripestat-whois
./xti enrich lookup 1.1.1.1 --type ipv4 --provider ripestat-whois
```

Karşılaştırmada her kaynak kendi iddiaları, güveni, geçerlilik durumu,
zaman temeli, özgün başvurusu ve son toplamasıyla görünür. Yerel görülme
sayısı ayrıdır. Farklı kaynak durumları oy çokluğu veya anlamsal çelişki
sayılmaz. Firma incelemesinde aynı ayrımın kısa özeti yer alır; kaynak
puanları değiştirilmez.

WHOIS adaptörü [RIPEstat'ın resmî API'sini](https://stat.ripe.net/docs/data-api/api-endpoints/whois)
tek sınırlandırılmış istekle kullanır. Hedef IP'ye bağlantı açmaz. Ağ
aralığı/prefix, kayıtlı kuruluş, ülke etiketi ve kaynak gibi seçilmiş
alanları gösterir; kayıt ülkesi fiziksel konum veya müşteri sahipliği
kanıtı değildir. `network-info` ile aynı yerel sağlayıcı bekleme kaydını
paylaşır. Geçersiz yanıt önceki başarılı yanıtı silmez. Ham sağlayıcı yanıtı
mevcut değişmez kaynak makbuzunda korunur; seçilmiş görünümde iletişim
alanlarının gösterilmemesi ham yanıtın anonimleştirildiği anlamına gelmez.
Ticari kullanıma ilişkin [N-022](../NOTES.md#n-022--ripestat-ticari-kullanım-izni)
açık kalır; API'nin anahtarsız çalışması ticari veri hakkı sağlamaz.

## JSON sözleşmesi

Engine ve platform salt okuma işlemleri:
`sightings.list`, `sightings.show`, `relationships.candidates`,
`relationships.show`, `identity.view`, `ioc.compare`.
Yazmalar yalnız terminal ve firma platformunda:
`sightings.record`, `sightings.revoke`, `relationships.review`.

```json
{
  "contract_version": 1,
  "request_id": "olay-42",
  "operation": "sightings.record",
  "parameters": {
    "expected_workspace_id": "FIRMA_CALISMA_ALANI_UUID",
    "indicator_type": "ipv4",
    "value": "192.0.2.10",
    "source": "kurum-edr",
    "sensor": "ag-gecidi-1",
    "source_event_id": "olay-42",
    "observed_at": "2026-11-19T09:00:00+03:00",
    "reference": "kurum-log:olay-42",
    "idempotency_key": "gorulme-42"
  }
}
```

Liste/aday/karşılaştırmada `offset`, `limit` (1–100) ve
`expected_snapshot` vardır. Aynı kesitte sayfalama için ilk yanıttaki
`snapshot_id` gönderilir. Kanıt/karar/güncellik sınıfı değişirse
`snapshot_changed` döner. `show` işlemleri yalnız `identifier`; kimlik
görünümü `identifier` ve `kind` alır. Bilinmeyen alanlar reddedilir;
istemciden dosya yolu veya çalıştırılacak komut alınmaz.

Bulunamayan kayıt `not_found`/exit 3; biçim hatası
`invalid_parameters`/exit 2; tekrar anahtarı, kaynak olayı, sürüm veya
kesit çakışmaları kendi kodlarıyla exit 1 döner. Motor girişinin yazma
çağrısı `unsupported_operation` olur. Firma yazmalarında yanlış
`expected_workspace_id` → `scope_mismatch`; başka veri alanına geri düşme
yoktur. Aynı tekrar anahtarı eski işlemin ilk sonucunu döndürür.

## Kapasite ve kapsam

Görülme ve ilişki karar günlüğü birlikte 20.000 olay / 64 MiB, tek kayıt
1.000 istek olayı / 2 MiB ile sınırlıdır. Dolunca kayıtlar sessizce silinmez;
yazma veya eksik okuma açık hatayla durur. Rapor günlüğünün önceki sınırları
korunur. Kimlik/grafik pencerelerinin sınırı sonuçta açıklanır.
Bunlar ölçülen SQLite başlangıç kapsamıdır; dağıtık büyük veri kapasitesi
ve 7/24 hizmet seviyesi anlamına gelmez.

Tekrarlanabilir kontrollü kabul:

```sh
./scripts/python scripts/check-evidence-acceptance.py \
  --duration 120 --events-per-company 1000 \
  --output /tmp/xti-evidence-kabul-yeni.json
```

Çıktı dosyası yeni olmalıdır. Geçici firma verileri, ölçüm sonunda
temizlenir. Testteki görülmeler müşteri ağından alınmış canlı olaylar
olarak sunulmaz. Gerçek Tavily ve yetkili Nmap kabulü kendi notlarında
bekler. Geniş STIX/TAXII ve LLM bu teslimin kapsamına alınmadı.
