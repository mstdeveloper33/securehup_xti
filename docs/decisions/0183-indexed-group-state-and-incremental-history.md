# 0183 — Biriken grup geçmişini güncel okumadan ayırma

Tarih: 20 Kasım 2026. Durum: uygulama ve kabul sürüyor.

Grup listesi, ayrıntısı, bildirim kutusu ve her yeni kontrol bütün grup
günlüğünü okuyordu. Değişmeyen kontrol bile aynı kanıtı tekrar saklıyordu.
1000 olay/grup ve 10000 olay/alan sınırı, düzenli takibi sonunda durduruyordu.

Şema88 özgün günlükleri değiştirmeden indeksli son durum, olay sonuçları ve
donmuş değişiklik kanıtları ekler. Her yeni işlem bunları aynı transaction
içinde günceller. Sonuç veya idempotency tekrarı olay kimliğiyle bulunur.
Kayıtlı karar sonraki kontrol tarafından değiştirilmez.

v1 olayları ve SHA değerleri aynen kalır. Yeni v2 olaylarında durum SHA'sı
`identity('research-group-state-v2', previous_state_sha, event_payload_sha)`
ile ilerler. Kanıt tamamen aynıysa snapshot, önceki kanıtın kanonik JSON
SHA'sına başvurur. Kanıtı değiştiren olay gövdeyi korur. Her kontrolün zamanı,
isteği ve tekrar anahtarı saklanır; kayıpsızlık gereği disk büyümesi sıfır olmaz.

`groups current` ve SQL'de sayfalanan `groups history/changes` yeni okuma
yüzeyidir. Eski `groups show` tam geçmiş davranışı korunur; tek yanıt sınırı
aşılınca açık sayfalama hatası verir, sessizce eksiltmez. Yazma sözleşmesine
isteğe bağlı `response_mode=current` eklenir. Eski isteklerde full varsayımı
korunur; terminal ve yönetilen işler current kullanır.

Özgün günlükten türetilen durum tek başına yeni doğruluk kaynağı değildir.
SQL tetikleyicileri olağan işlem dışı güncellemeyi kirli işaretler; normal
okuma bu durumda durur. Seçilen kanıtın SHA, kapsam, sürüm ve zincir bağı
kontrol edilir. `groups audit` geçmişi akış halinde yeniden doğrular;
`groups rebuild` önce yedek alır, türetilen tabloları transaction içinde yeniden
kurar. Eski v1 öneklerinin doğrulaması eski 1000 olay/4 MiB bütçesi içindedir.
Bu, veritabanına tam erişimi olan saldırgana karşı imzalı doğrulama değildir.

Normal istek geçmiş hacminden bağımsız sınırlı gövde okur. SQL COUNT/OFFSET
ve açık bakım işlemleri hâlâ veri hacminden etkilenebilir. Diğer modüllerin
araştırma ve kaynak bütçeleri korunur. Sınırsız kapasite iddiası yoktur.

Geçiş, kaynak günlüklerini, eski vaka JSON'unu, bildirim kimliği/okunma
durumunu veya eski iş makbuzlarını yeniden yazmaz. Yedek eski kodla geri
okunur. Kabul ölçümü ve sınırlar teslim belgesine kaydedilecektir.
