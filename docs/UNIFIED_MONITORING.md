# Birleşik izleme politikası

XTI 0.187.0, farklı modüllerde daha önce saklanmış kanıtları tek bir
kuruluş politikası altında izler. Domain, marka, IP, anahtar kelime, kişi
ve tedarikçi hedefleri aynı politikada bulunabilir. Politika yalnız yerel
kanıtı karşılaştırır; çalıştırıldığında internete çıkmaz ve kaynakları
kendiliğinden yenilemez.

Bu ayrım bilinçlidir:

1. Collector/source-job akışları desteklenen dış kaynakları kendi kurallarıyla
   günceller.
2. Birleşik izleme, o anda saklı bulunan kayıtların tek snapshot'ını alır.
3. İlk çalışma sessiz başlangıç çizgisidir; alarm üretmez.
4. Sonraki çalışma eklenen, değişen ve kaybolan kayıtları ayrı sayar.
5. Eşik aşılırsa ortak inbox alarmı oluşur; sonuç otomatik tehdit hükmü değildir.
6. Analist alarmı `useful`, `not_useful` veya `uncertain` olarak gerekçeyle
   inceler; alarm vaka kanıtına dondurulabilir.

## Kurulum ve yükseltme

Yeni kurulum:

```sh
./setup
./xti init
```

0.186.0 / şema 95 veri alanı için:

```sh
./xti migrate
```

Geçiş önce kurtarma yedeği üretir, ardından şema 96'ya çıkar. Eski vaka,
alarm ve kaynak kanıtı korunur. Geri dönüş, geçiş yedeğinin yeni ve boş bir
veri alanına restore edilmesiyle yapılır; canlı veritabanının üzerine yazılmaz.

## Politika oluşturma

Önce kuruluş ve kapsam bağları mevcut olmalıdır. Domain hedefi serbest metin
değildir; seçilen kuruluşun etkin domain bağı olmak zorundadır.

```sh
./xti monitoring policy-add \
  --name "SecureHup birleşik izleme" \
  --organization KURULUS_KIMLIGI \
  --domain securehup.com \
  --brand SecureHup \
  --record-kind domain \
  --record-kind finding \
  --record-kind social \
  --record-kind ransomware \
  --match-mode exact \
  --match-mode prefix \
  --notify-on added \
  --notify-on updated \
  --minimum-changes 1 \
  --priority high \
  --interval-seconds 3600 \
  --actor analyst@example.com \
  --reason "Kuruluşun saklı kanıtları ortak alarm politikasına bağlandı."
```

Desteklenen hedefler: `domain`, `brand`, `ip`, `keyword`, `person`,
`supplier`. Desteklenen saklı kayıt aileleri: domain, finding, social,
ransomware, public-notice, case, supplier, organization, CTI, indicator,
news ve mention.

`exact`, `prefix` ve isteğe bağlı `contains` eşleşmeleri farklı gürültü
seviyelerine sahiptir. Varsayılan `exact` + `prefix` daha kontrollüdür.
Öncelik kullanıcının alarm yönlendirme tercihidir; risk olasılığı değildir.

## Plan, zaman ve çalışma

```sh
./xti monitoring policies
./xti monitoring policy-show POLITIKA_KIMLIGI
./xti monitoring plan POLITIKA_KIMLIGI
./xti monitoring due
./xti monitoring run POLITIKA_KIMLIGI
./xti monitoring run-show CALISMA_KIMLIGI
./xti monitoring run-matches CALISMA_KIMLIGI --limit 100
./xti monitoring run-coverage CALISMA_KIMLIGI --limit 100
./xti monitoring run-changes CALISMA_KIMLIGI --limit 100
```

`plan`, ağ erişiminin kapalı ve çalışma biçiminin `stored_evidence_only`
olduğunu açıkça gösterir. `due`, politika aralığına göre zamanı gelenleri
sayfalı ve toplam sayıyla verir. Normal çalıştırma zamanı gelmemiş politikayı
reddeder. Güvenilen operatör CLI'sı gerektiğinde `--force` kullanabilir;
bu seçenek kaynak yenilemez.

Politika tanımı değişirse sürüm artar ve yeni tanım ilk turunu yeniden sessiz
başlangıç olarak alır. Böylece kapsam değişikliği yanlış biçimde tehdit alarmı
olmaz. Aynı idempotency anahtarı aynı isteği tekrar oynatır; farklı içerikle
kullanılırsa çatışma olarak reddedilir.

Değişmeyen turlar aynı büyük snapshot gövdesini tekrar yazmaz. Yeni çalışma
makbuzu ve küçük fark raporu korunur; snapshot önceki aynı özetli dondurulmuş
kanıta güvenli referans verir. Kaynak kapsamı veya kayıt durumu değişirse yeni
snapshot saklanır.

Snapshot eşleşmeleri ağır iç arama nesnesini kopyalamaz; kayıt kimliği,
durum hash'i, kaynak, kaynak çalışma kimliği ve analistin anlayacağı sınırlı
kayıt alanlarını taşır. Çalışma özeti bütün değişiklik sayılarını korur ancak
en fazla ilk 100 değişiklik ayrıntısını gömer. Daha büyük farkın tamamı
`run-changes` ile sayfalanır; bu sınırlama veri kaybı veya sessiz kesme değildir.

## Alarm ve insan incelemesi

```sh
./xti monitoring alerts --read-state unread
./xti monitoring alert-show ALARM_KIMLIGI
./xti monitoring alert-review ALARM_KIMLIGI \
  --decision useful \
  --actor analyst@example.com \
  --reason "Yeni domain kaydı marka ekibince incelenmeli."
./xti monitoring reviews ALARM_KIMLIGI
./xti monitoring report --policy-id POLITIKA_KIMLIGI
```

Alarm sayfaları politika, öncelik, son insan kararı ve okundu durumuyla
filtrelenebilir. Okundu/okunmadı işlemi ortak `inbox` komutlarıyla yapılır;
insan kararı bundan ayrıdır. `cases evidence-add` işleminde kanıt türü
`unified_monitoring` seçilerek alarm/run hash'leri, kuruluş kapsamı, bütün
fark sayıları ve en fazla ilk 100 fark ayrıntısı kompakt vaka kanıtına
dondurulur. Tam eşleşme ve fark sayfaları özgün run kaydında korunur.

Bir süreç çalışma kaydını `running` bırakarak kesilirse otomatik başarıya
çevrilmez:

```sh
./xti monitoring recover POLITIKA_KIMLIGI \
  --actor operator@example.com \
  --reason "Kesilen yerel çalışma operatör tarafından interrupted kapatıldı."
```

## Engine ve firma platformu

Salt okunur engine v1 işlemleri:

- `monitoring.capabilities`
- `monitoring.policies`, `monitoring.policy.show`, `monitoring.plan`, `monitoring.due`
- `monitoring.runs`, `monitoring.run.show`
- `monitoring.run.matches`, `monitoring.run.coverage`, `monitoring.run.changes`
- `monitoring.alerts`, `monitoring.alert.show`, `monitoring.reviews`
- `monitoring.report`

Firma platformu v1 bunlara policy add/update/disable, run, review ve recover
yazmalarını ekler. Her platform yazması güncel `expected_workspace_id`
ister. Başka firmanın kimliği kayıt varlığını sızdırmadan `not_found` olur.
Kimlik doğrulama, kullanıcı rolü ve gerçek zamanlayıcı tüketici .NET
platformundadır; eşleştirme, eşik, snapshot, alarm ve inceleme kuralları
XTI motorunda kalır.

## Sınırlar

- Çalıştırma dış kaynağı yenilemez; eski/eksik saklı veri eski/eksik sonuç üretir.
- Metin eşleşmesi sahiplik, ihlal, phishing, taklit veya zararlılık kanıtı değildir.
- Bu paket e-posta/SMS/Slack/Teams göndermez; mevcut yerel inbox ve vaka zincirini kullanır.
- Gerçek zamanlı Kafka/streaming yoktur. Periyodik çağrı sözleşmesi vardır.
- En fazla 100 hedef/politika, 20.000 eşleşme/snapshot, özet içinde 100 fark
  ayrıntısı, sayfalı okumada 500 kayıt, 16 MiB snapshot, 4 MiB fark raporu
  ve çalışma alanı başına 128 MiB P07 kanıt gövdesi vardır.
- Kalıcı tablo sınırları dolduğunda eski kayıt sessizce silinmez; yeni yazma
  açık `capacity` hatasıyla durur.

## Doğrulama

```sh
PYTHONPYCACHEPREFIX=/tmp/xti-pyc ./scripts/python \
  -m unittest -v tests.test_unified_monitoring \
  tests.test_unified_monitoring_contract

PYTHONPYCACHEPREFIX=/tmp/xti-pyc ./scripts/python \
  scripts/check-unified-monitoring-delivery.py
```

Ayrıntılı kapsam, kapasite sonucu ve açık dış teslimler
[P07 teslim kartında](roadmap/P07_DELIVERY.md) bulunur.
