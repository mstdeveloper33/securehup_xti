# 0010 — Sınırlı ve kalıcı izleme denemesi

**Tarih:** 29 Ekim 2026 · **Durum:** 0.10.0'da uygulandı.

## İhtiyaç ve kapsam

`watch --cycles` düzenli arama yapar, ancak bir denemenin bütün turlarını tek kalıcı kimlik altında toplamaz. Kaynakların hangi turlarda tamamlandığını, nerede hata oluştuğunu ve kayıtlı sonuçlara göre kaç yeni bulgu üretildiğini sonradan aynı kapsamla okuyabilmek gerekir.

`monitor start` bu ölçüm için oturum oluşturur. Yalnız mevcut crt.sh/urlscan arşivlerini sorgular; yeni tarama göndermez, hedef kontrolü veya arka plan hizmeti başlatmaz. `monitor list/show` kayıtlı sonucu okur. `monitor recover` kapanmış çalışmanın kayıtlarını tamamlar; aramayı sürdürmez. Yeniden çalıştırmak yeni oturumdur.

## Sorumluluklar ve ayarlar

`MonitorSpec` hedefler, sağlayıcılar, yazım varyantı seçimi, kural sürümü, tur sayısı, aralık ve süre sınırını taşır. `MonitorRun` bunun değişmeyen kopyasını, durumunu, UTC başlangıç/bitişini ve varsa ölçülmüş süreyi içerir. Ortak modeller SQLite, terminal veya ağ bağlantısını bilmez.

`MonitorService` doğrulama, döngü, sahiplik ve özetleme işini yapar. Depo için `MonitorRepository`, arama için mevcut `JobService` kullanılır. Salt okuma servisinde çalıştırıcı bulunması gerekmez. `SQLiteMonitorRepository` kalıcı bağlantıları ve kısa işlemleri yönetir; terminal parçaları birleştirir ve dinamik metni kaçırır.

| Ayar | Varsayılan | Kabul edilen aralık |
|---|---|---|
| Tur sayısı | 3 | 1–1000 |
| Tur sonrası aralık | 3600 saniye | 300–86400 saniye |
| Yeni kaynak işi başlatma bütçesi | 86400 saniye | 1–604800 saniye |
| Hedefler | Kayıtlı adresler veya verilen adres | 1–5 tekil adres |
| Kaynaklar | crt.sh ve urlscan | Biri veya ikisi |

Adres ve sayı sınırları kayıt alanı oluşturulmadan doğrulanır. Kaynak planı, kayıtlı hedefler ve kural sürümü oturum kilidi/oluşturulmasından önce denetlenir. Domain verilmiş `monitor start`, mevcut `scan` davranışı gibi kayıt alanını ve adresi hazırlayabilir. Listeleme ve ayrıntı eksik veritabanı oluşturmaz veya eski şemayı dönüştürmez.

## Tek sahip ve atomik iş bağlantısı

Bir izleme oturumu mevcut yerel worker kilidini bütün çalışması boyunca tutar; turlar arasındaki bekleme buna dahildir. Bu tercih tek kullanıcı kurulumunda birden fazla çalıştırıcının aynı ölçüme karışmasını önler. Ağ veya bekleme sırasında SQLite transaction'ı açık tutulmaz. Kayıt okuma, inceleme kararı ve okundu işlemleri yapılabilir; aynı worker kilidini isteyen başka arama, hedef kontrolü veya bakım çalışması meşgul hatası alır.

`JobService.run`, kilidi kendisi alıp `run_owned` yolunu çağırır. Monitor ise zaten aldığı kilitle `run_owned` kullanır. Bu yardımcının sözleşmesi çağıranın aynı kilidi tutmasıdır; monitor için ikinci kez kilit alınmaz.

Her kaynak çalıştırılacağı zaman `scan_jobs` ve `monitor_jobs` bağlantısı tek yazma transaction'ında oluşturulur. Sonraki bütün turlar önceden kuyruğa konmaz. Bağlantı `(run_id, cycle, provider)` açısından tekildir; `job_id` de yalnız bir izleme çalışmasına ait olabilir. Ekleme, oturumdaki kaynak sırasını ve tur sınırını doğrular. İş yazılıp bağlantının kaybolduğu yarım işlem bırakılmaz.

Genel `worker --once` monitor'a bağlı işleri seçmez. Açık `jobs retry JOB_ID` ile bu işleri ayrıca başlatmak veya tekrar denemek reddedilir. Monitor sahibi yalnız kendi `running` oturumuna ait, `queued` durumundaki ve hiç denenmemiş işi başlatabilir. Böylece oturum öldükten sonra genel worker, ona ait başlamamış işi habersizce çalıştırmaz.

## Süre ve durma davranışı

UTC saatleri geçmiş için saklanır; çalışma bütçesi ve geçen süre monotonic saatten hesaplanır. Monotonic değer sonlu olmalı ve geriye gitmemelidir. UTC saatin geriye alınması bekleme veya yeni iş bütçesini uzatmaz.

Bütçe kaynak işini oluşturmadan ve başlatmadan önce kontrol edilir. İkisi arasında süre dolarsa oluşmuş fakat başlamamış iş, oturum kapanırken deneme kaydı uydurulmadan `interrupted` durumuna alınır. Rapor bunu başlamayan çalışma olarak sayar. Tur sonrası aralık, arama süresine eklenen beklemedir; sabit duvar saati takvimi değildir. Bekleme en fazla kalan bütçe kadar ve bir saniyeyi aşmayan adımlarla yapılır.

Sınır **yeni kaynak işi başlatma sınırıdır**. Başlamış kaynak araması birden fazla sorgu, tekrar ve kaynak beklemesi içerebilir; mevcut sorgu/zaman sınırlarıyla tamamlanır. Bu nedenle toplam oturum süresi seçilen bütçeyi aşabilir. Süre dolunca çalışan HTTP işlemini zorla kesen veya bütün oturumu kesin anda öldüren bir mekanizma değildir.

Tur sınırına ulaşınca `completed/cycles`, süre nedeniyle yeni iş başlatılmayınca `completed/duration` kaydedilir. Kaynak sonucu `partial/failed` olması sonraki kaynak ve turların başlamasını tek başına engellemez. Uygulama/depolama hatası ise oturumu `failed/error` kapatmayı dener ve hatayı iletir. Ctrl+C/SystemExit için `interrupted/cancelled` yazılması denenir. Kapanışın kendisi başarısızsa özgün hata korunur; kalan `running` kayıt daha sonra kurtarılır.

## Raporun anlamı

`monitor show` oturumu, iş bağlantılarını ve bağlı işlerin **ilk denemesini** tek okuma transaction'ından alır. Kapsam, sıra, durum ve deneme sayısı tutarlılığı denetlenir. Kayıtlı bir bozuk sonuç sessizce başka denemeyle değiştirilmez. İlk deneme seçimi, geçmişe sonradan başka deneme eklenmiş olsa bile ölçümün ona kaymasını önler; uygulamanın normal komutları bağlı iş tekrarını zaten reddeder.

Sonuç/sorgu JSON'u her iş için okunup doğrulanır, ardından küçük `MonitorAttempt` kaydına çevrilir. Özet kimlik, durum, başlangıç/bitiş, hata, sorgu sayıları ve varsa `ImportSummary` içerir. Bütün oturumun büyük JSON sonuçları aynı anda tutulmaz. En fazla 1000 tur × iki kaynak bağlantısı bulunabilir. `show` varsayılan son 20 çalışmayı, `--limit` ile 1–2000 çalışmayı gösterir; genel özet bütün oturumu kapsar. Liste varsayılan 20, en fazla 100 oturumdur.

Kaynak başına planlanan, işi oluşturulan, başlayan ve başlamayan çalışma sayısı ayrıdır. Başlamayan sayı planlanan eksi başlayandır; hiç kuyruğa eklenmemiş turları da içerir. Kaynak sonuçları ayrı `complete/partial/failed/interrupted/running` sayaçlarıdır. Tamamlanan tur, bütün seçili kaynakların denemelerinin terminal durumda olmasıdır; tüm kaynakların başarılı olduğu anlamına gelmez.

Yeni gözlem/bulgu toplamları yalnız son sayı özeti kaydedilmiş denemelerden gelir. Kesinti sırasında bazı gözlemler kaydedilmiş olsa da son özet yoksa bunlara sıfır sonuç uydurulmaz; `unknown_result_count` artar. Gösterilen bilinen toplam bu eksik denemelerin tam katkısını içermez. Kayıtlı mantıksal sorgu sayısı, gerçek HTTP çağrısı veya kaynağın erişilebilirlik oranı değildir; kota nedeniyle ağ açılmadan başarısız kalan sorgular da olabilir.

Oturum durumu ile rapor sonucu ayrıdır. `completed` oturumda en az bir deneme başlamış ve bütün başlayan denemeler `complete` durumundaysa rapor `complete`, aksi halde `partial` olur. Süre nedeniyle başlamayan çalışmalar, işleri hiç oluşturulmamış veya oluşturulup güvenle kapatılmış olsa da, bu sonucu değiştirmez. Başlamayan sayısı ayrı görünür; hiç deneme başlamadıysa rapor `partial` kalır. `running/interrupted/failed` oturum raporu aynı durumu taşır. Başlatma komutu tam raporda çıkış 0, kısmi raporda 3 verir; `list/show` çıkış 0 yalnız başarılı okumadır. Kaynakların şu anda sağlıklı olduğuna ilişkin bir karar üretilmez.

## Kurtarma ve geçmişi koruma

İlk ilerleme satırında kalıcı oturum kimliği yazılır; kesinti sonrasında `monitor list/show` ile bulunabilir. Bu okumalar kayıtları veya okundu bilgisini değiştirmez. `running`, yalnız kaydedilmiş durumdur ve canlı süreç kanıtı değildir.

`monitor recover` worker kilidini aldıktan sonra açık oturumları ve bağlı `queued/running` işleri kapatır. Gerçekten başlamış deneme `interrupted` olur; başlamamış iş için sahte deneme oluşturulmaz. Oturum `interrupted/recovered` kaydedilir. Yeni `monitor start` da aynı kilit altında önce bu kurtarmayı yapar. Normal iş kurtarması bir bağlı denemeyi daha önce yarım işaretleyebilir; oturumun kapanması monitor kurtarmasına kadar bekleyebilir.

Zorla kapatılmış sürecin monotonic başlangıcı yeni süreçte ölçüm için kullanılamaz. Kurtarma `elapsed_seconds=NULL` yazar; UTC farkından ölçülmüş süre uydurmaz. Tamamlanmış denemeler, bulgular, kanıtlar, kararlar ve bildirimler korunur. Oturum otomatik devam etmez; yeni deneme ayrı kimlik alır.

## Şema ve doğrulama

Şema 7, `monitor_runs` ve `monitor_jobs` tablolarını ekler. Açık geçiş şema 1–6 için önce özgün sürümün yedeğini alır, sonra eksik yapıları tek transaction'da ekler. Şema 6 tablo kümesi ayrı korunur. Eski aramalardan geriye dönük oturum oluşturulmaz. Bildirim kutusu yalnız şema 1–5'ten geçişte ilk kez oluşturulur; 6→7 geçişinde mevcut kimlikler ve okundu durumları değişmez. Hata yeni yapıları ve sürüm değişimini geri alır. Yedekler oturumları, bağlantıları ve denemeleri birlikte taşır; restore boş konum ister.

Servis, depolama, terminal, geçiş ve gerçek süreç kapanma testleri; tek sahipliği, kaynaklar arasında ve beklemede kesilmeyi, süre sınırını, başlamamış işin güvenli kapatılmasını, genel worker/ayrı retry engelini, kayıp sayı özetlerini, bozuk geçmişin reddini, atomik ekleme ve kurtarmayı, yedekten aynı raporu okumayı kapsar. Güncel test toplamı ve gerçek kaynak denemelerinin kanıtı [STATUS.md](../STATUS.md) içindedir. Kısa sentetik veya birkaç turluk canlı deneme, saatlerce/günlerce işletim ya da büyük ölçek başarısı sayılmaz.
