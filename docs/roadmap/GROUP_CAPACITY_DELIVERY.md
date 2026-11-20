# Grup kapasitesi — sabit teslim kapsamı

20 Kasım 2026 · 0.178.0 / çekirdek88. Durum: kabul sürüyor.

Kapsam: indeksli güncel durum ve geçmiş sayfalama; aynı kanıtı tekrar
saklamayan kontrol; seçilen bildirim kanıtı; idempotent kuyruk/kurtarma;
özgün geçmiş denetimi ve yedekli yeniden kurma; şema87 geçişi/geri dönüş;
iki firmada büyüyen yük; geliştirme sırasında birikimli kullanım ölçütü.

Yeni kaynak, ücretli çağrı, .NET/PostgreSQL uygulaması veya başka özellik
paketi bu teslimin parçası değildir.

Kabul bütçesi: iki firmada 100'er grup; 1000, 10000 ve 100000'er olay.
Çoğunluğu değişmeyen kontrol, kontrollü yokluk/geri dönüş de içerir.
Gerçek platform CLI/JSON alt süreçlerinde okumalar için p95 ≤5 saniye,
tepe RSS ≤128 MiB. Bu eşikler bütün kaynak toplama motorunun SLA'sı değildir.

Kanıt aracı `scripts/check-group-capacity.py`; gerçek eski üretici
`11e4206e8de15a6ac0c93053e1ca0ae7c8e0a0e1` (0.177.0/87).
Ham ölçüm dosyaları geçici alanda/CI çıktısında tutulur; müşteri verisi
veya test veritabanı repoya eklenmez.

## Yerel kabul — macOS / Python3.13.3

`check-group-capacity.py` 224,735 saniyede geçti. Şema87→88 geçişinde
174 eski tablonun 27 satırı/rowid'i, arşivli kanıt, okunmuş bildirim,
eski iş makbuzu ve donmuş vaka korundu; eski kodla yedeğe dönüş geçti.
Önceden var olan tablolara yalnız tanımı doğrulanmış koruma tetikleyicileri
eklendi. İlk kabul denemesi bu yeni tetikleyicileri tanımayan eski manifest
karşılaştırmasında durdu; karşılaştırma yalnız tam eşleşen yeni tetikleyici
tanımlarına izin verecek şekilde genişletildi. Satır/DDL değişikliği ve
bilinmeyen tetikleyici hâlâ reddedilir.

| Firma başına birikim | Alpha DB | Beta DB |
| --- | ---: | ---: |
| 1.000 olay | 5.083.136 byte | 5.091.328 byte |
| 10.000 olay | 22.417.408 byte | 22.429.696 byte |
| 100.000 olay | 201.875.456 byte | 201.928.704 byte |

36 gerçek platform CLI/JSON okumasında p95 **0,543845 saniye**, medyan
0,348653 saniye, tepe RSS **47.349.760 byte**. Her firmada 100 grup ve
600 donmuş değişiklik/bildirim vardı. Tam geçmiş denetimi alpha için
71,006, beta için 67,263 saniye sürdü; iki denetim de geçti. Tam bakımın
normal sayfa okumasından daha pahalı olduğu açıkça ölçüldü.

Bu veri kontrollü fixture'dır; canlı kaynak toplama veya ticari SLA
ölçümü değildir. Yeni testler tek grupta 1.101 olayı, bunun ardından gerçek
kuyruk/worker ile 1.102'nci kontrolü, eski tekrar sonucunu, bozuk projeksiyon
ve özgün günlük ayrımını da kapsar.
Ortak kuyruğun 10.000 saklı iş sınırı değişmedi; ölçülen 100.000 olay/firma,
100.000 kuyruk işi kabulü değildir. Bu sınır geliştirme kabulünde açıkça
kaydedildi; genel motor kapasitesiyle grup geçmişi kapasitesi karıştırılmadı.

59 grup/arşiv/geçiş testi ve 125 entegrasyon/mimari testi geçti; ikinci
pakette Linux'a özgü iki kontrol macOS'ta atlandı. 246 geçiş testinin ilk
koşusunda bir testin beklenen tetikleyici listesi eskiydi; düzeltilen
geçiş testi ilgili paket içinde tekrar geçti. Son bağlantı kontrolünde
76 test/77,695 saniye geçti. Son temizlikte eksilen bir `NOTES` importu da
hedefli pakette yakalandı; bu son temiz 76 test koşusundan önce düzeltildi.
Yerel kapasite ölçümü geliştirme çalışma ağacında alındı; sabit gönderim
commit'inin Linux kabulü ayrıca izlenir. Gerçek85 ve86 üreticileri
ile eski kabul araçları da şema88'e geçiş/geri dönüşü doğruladı.

Linux sonucu ve son commit için kabul henüz bekleniyor. Bu yerel sonuçlar
tam Linux paketinin geçtiği anlamına gelmez.

## Linux süresi düzeltmesi

`0efb3e0` grup kabulü iki Python sürümünde ve altı ilgili GitHub iş akışında
başarılı. İlk hızlı kontrol 25 dakikalık iş süresiyle iptal oldu; GitHub
annotation'ı `The job has exceeded the maximum execution time of 25m0s`
nedeni verdi. Bu koşu başarılı veya test hatası sonucu sayılmadı.

Hızlı kapının mevcut modül listesi değiştirilmeden iki ayrık parçaya
bölündü. Yerel `scripts/check-fast` hâlâ tam hızlı listeyi çalıştırır;
yalnız CI `XTI_CHECK_SHARD=1/2` ve `2/2` kullanır. Her parça 25 dakika
bütçeli; kapasite/performans kabul eşikleri aynı. Eksik, örtüşen veya
geçersiz parça seçimi denetimi ve 14 CI yapılandırma testi geçti.
Motor kodu bu süre düzenlemesinde değişmedi; devam eden tam paket
gereksiz yere yeniden başlatılmadı.
