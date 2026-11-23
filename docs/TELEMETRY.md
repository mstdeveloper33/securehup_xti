# Sensör ve sandbox telemetrisi

23 Kasım 2026 · XTI 0.192.0 · çekirdek şema 99.

Bu modülün sade görevi şudur: Kuruluşun kendi sensörünün gördüğü bir olayı
veya ayrı bir malware sandbox'ının tamamladığı analizi, kaynağı belli ve insan
tarafından incelenebilir XTI kanıtına dönüştürür. Örneğin Cowrie bir IP'nin SSH
bağlantısını gördüğünde XTI kaynak IP, hedef port, olay zamanı ve kaynak
makbuzunu saklar; Cowrie'nin gördüğü kullanıcı adı, parola veya yazılan komutu
saklamaz.

XTI honeypot kurmaz, internete honeypot açmaz, zararlı örnek kabul etmez ve
zararlı çalıştırmaz. Cowrie ile CAPE ayrı altyapılardır. Bu sürüm yalnız yerel
dosyayı veya firma JSON sözleşmesinden gelen normalize kaydı işler.

## Hazır girdi biçimleri

| Biçim | Ne alır? | Durum |
|---|---|---|
| `xti-sensor-v1` | Kuruluş sensörü veya sinkhole için kesin XTI JSONL kaydı | Aktif; ağsız uçtan uca kabul edildi. |
| `cowrie-jsonl` | Desteklenen Cowrie bağlantı, giriş ve dosya indirme olayları | Adaptör hazır; gerçek ayrı Cowrie kurulumu ve canlı JSONL kabulü bekler. |
| `cape-report-v1` | Tamamlanmış CAPE `report.json` içindeki hash, sınırlı imza özeti ve ağ IOC'leri | Adaptör hazır; güvenli ayrı CAPE ortamı ve gerçek rapor kabulü bekler. |

Cowrie olay alanlarının resmî açıklaması
[Cowrie Output Event Code Reference](https://docs.cowrie.org/en/stable/OUTPUT.html),
CAPE çıktı düzeni ise
[CAPE Analysis Results](https://capev2.readthedocs.io/en/latest/usage/results.html)
belgelerindedir.

## Ne saklanır, ne saklanmaz?

Saklananlar:

- kaynak ve kuruluş kimliği;
- olay zamanı, güvenli kısa özet ve sonuç;
- izinli IP, port, protokol, domain, URL, hash ve IOC alanları;
- kayıt sürümleri, içe alma makbuzu, SHA-256 bütünlük bağı ve insan kararı.

Hiç saklanmayanlar:

- kullanıcı adı ve parola;
- saldırganın ham komutu veya mesajı;
- zararlı örnek dosyası;
- PCAP, bellek dökümü, ekran görüntüsü ve ham CAPE raporu;
- kaynak dosyanın ham gövdesi.

Kullanıcı adı/parola taşıyan URL reddedilir. Cowrie'deki desteklenmeyen veya
güvenli biçimde indirgenemeyen olaylar gizlice kabul edilmez; atlama nedeni ve
sayısı içe alma makbuzunda gösterilir.

## Terminal kullanımı

Önce mevcut kuruluş kimliğini seçip kaynak tanımla:

```sh
./xti telemetry capabilities
./xti telemetry source-add \
  --organization KURULUS_UUID \
  --name "Merkez sinkhole" \
  --kind sinkhole \
  --format xti-sensor-v1 \
  --description "Kuruluşun yetkili DNS sinkhole gözlemleri"
```

Dosyayı önce yazmadan doğrula. Çıktıdaki içerik SHA-256 değerini açık onay
olarak ikinci komuta ver:

```sh
./xti --json telemetry preview sensor.jsonl --format xti-sensor-v1
./xti --json telemetry import KAYNAK_UUID sensor.jsonl \
  --format xti-sensor-v1 \
  --expected-revision 1 \
  --expected-content-sha256 ONIZLEME_SHA256 \
  --idempotency-key sensor-2026-11-23-001
```

Sonucu incele:

```sh
./xti telemetry sources --organization KURULUS_UUID
./xti telemetry runs --source-id KAYNAK_UUID
./xti telemetry records --organization KURULUS_UUID
./xti telemetry record-show KAYIT_UUID
./xti telemetry report KURULUS_UUID
```

İnsan kararı otomatik tehdit hükmünden ayrıdır:

```sh
./xti telemetry review KAYIT_UUID \
  --expected-revision 1 \
  --decision suspicious \
  --reason "Kaynak ve hedef bağlamı analist incelemesi gerektiriyor." \
  --actor analyst
```

Kesinti sırasında `running` kalan çalışmalar veri toplamayı yeniden
başlatmadan açıkça kapatılır:

```sh
./xti telemetry recover KAYNAK_UUID \
  --reason "İçe alma işlemi yarıda kesildi; yeni dosyayla tekrar önizlenecek."
```

## XTI Sensor JSON v1 örneği

Dosya JSONL'dir; her satır tek ve kesin üst nesne taşır:

```json
{"format":"xti-sensor-record","version":1,"record":{"native_id":"sinkhole:event-1","kind":"dns_query","event_at":"2026-11-23T07:59:00+00:00","summary":"Sinkhole DNS observation for example.test","outcome":"observed","src_ip":"192.0.2.25","dst_ip":"192.0.2.53","src_port":5353,"dst_port":53,"protocol":"udp","domain":"example.test","url":null,"hashes":{},"indicators":[{"type":"domain","value":"example.test"}],"attributes":[{"name":"query_type","value":"A"}],"tags":["authorized-sinkhole"]}}
```

Desteklenen kayıt türleri `connection`, `authentication`, `dns_query`,
`file_download` ve `sandbox_analysis` değerleridir. Kaynak türü kayıt türünü
sınırlar; örneğin `sinkhole` kaynağı sandbox kaydı kabul etmez.

## Sınırlar ve hata davranışı

- Dosya en çok 32 MiB ve 50.000 girdi; firma JSON isteği en çok 1.000
  normalize kayıt taşıyabilir.
- Tek kayıt en çok 64 KiB; IOC ve güvenli özellik listeleri ayrı ayrı en çok
  200 öğedir.
- Dosya sembolik bağlantı üzerinden okunmaz ve önizleme sonrası içerik hash'i
  değişirse içe alma durur.
- Aynı kaynak kayıt kimliği aynı içerikle tekrar gelirse yeni kanıt kopyası
  oluşmaz; değişirse eski sürüm korunur ve önceki insan kararı yeniden
  inceleme bekler.
- Kaynak veya yerel kayıt bozuksa kısmi sonuç gösterilmez.
- Bir gözlem doğrulanmış saldırı, zararlılık, atıf veya olay değildir.

## Arama, izleme, vaka ve platform kullanımı

Normalize kayıtlar ortak `search --kind telemetry` görünümüne ve
`record.get` ayrıntısına girer. `cases evidence-add ... telemetry ...` ile
o andaki kanıt vaka içinde dondurulabilir. P07 birleşik izleme politikasında
`record_kinds=["telemetry"]` seçilerek ilk sessiz ölçümden sonraki yeni veya
değişmiş kayıtlar ortak inbox'a alınabilir.

Engine v1 bütün `telemetry.*` okumalarını sunar. Firma platformu aynı okumalara
ek olarak `telemetry.source.add`, `telemetry.source.update`,
`telemetry.ingest`, `telemetry.review` ve `telemetry.recover` işlemlerini
workspace kimliği ve tekrar anahtarıyla kullanır. Platform JSON'u sunucu dosya
yolu kabul etmez; yalnız kesin normalize kayıt listesi kabul eder. Dosya
okuma yerel işletici terminalinde kalır.

## İşletim ve canlı kabul

Kontrollü XTI, Cowrie ve CAPE örnekleri parser davranışını doğrular; bunlar
gerçek sensör/sandbox canlı kabulü değildir. Üretimde:

1. Cowrie internete doğrudan XTI süreci içinden açılmaz; ayrı, kısıtlı ve
   izlenen altyapıda işletilir.
2. CAPE zararlı çalıştırma ağı XTI ve müşteri üretim ağından ayrılır; XTI'ya
   yalnız tamamlanmış `report.json` taşınır.
3. Kaynak dosya aktarımı, klasör izinleri, saklama süresi ve operatör erişimi
   işletim politikasıyla tanımlanır.
4. Gerçek canlı dosyayla kimlik alanları, sürüm, hacim ve hata kabulü tekrar
   çalıştırılmadan ilgili kaynak “canlı doğrulandı” sayılmaz.

## Saklama, hold ve geri yükleme

Normalize P12 kayıtları artık P08'in `telemetry_records` ailesiyle yönetilir.
Politika süresini aşan sıcak gövdeler kayıpsız sıkıştırılır; `record-show`,
arama, vaka ve sürüm geçmişi aynı içeriği göstermeye devam eder. Aktif vaka
kanıtı ve açık hold otomatik korunur. Yeni bir telemetri sürümü sonradan
gelirse önceki arşiv değişmez; yeni gövde zamanı geldiğinde ayrı nesil olarak
arşivlenir ve her nesil bağımsız geri yüklenebilir.

```sh
./xti retention policy-add \
  --name "90 günlük telemetri" \
  --organization KURULUS_UUID \
  --family telemetry_records \
  --archive-after-days 90 \
  --batch-limit 250 \
  --actor privacy-operator \
  --reason "Onaylanan telemetri yaşam döngüsü" \
  --idempotency-key telemetry-retention-1
```

Bu mekanizma mantıksal kaydı otomatik silmez ve haricî soğuk depo değildir.
Sıkıştırılmış gövde aynı firma SQLite alanında, hash ve audit zinciriyle
korunur. Ayrıntılar [saklama rehberindedir](DATA_RETENTION.md).
