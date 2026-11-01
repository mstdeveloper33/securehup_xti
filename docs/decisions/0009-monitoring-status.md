# 0009 — Kayıtlı takibin tutarlı durum özeti

**Tarih:** 29 Ekim 2026 · **Durum:** 0.9.0'da uygulandı.

## İhtiyaç ve sınır

Kullanıcı son aramaları, bekleyen işleri, kaynak bekleme sürelerini ve okunmamış bildirimleri tek komutla görebilmelidir. Başka bir adresin başarılı araması yeni eklenen adresi güncel göstermemeli; yeni başarısızlık da önceki tamamlanmış aramanın zamanını gizlememelidir.

`./xti status` kayıtlı geçmişi özetler. Kaynağa bağlanmaz, arama başlatmaz, yarım işi kurtarmaz ve worker kilidi almaz. Çıkış 0 ve JSON `ok:true` yalnız özetin okunabildiğini bildirir. Genel bir “sağlıklı” sonucu veya tehdit kararı üretilmez. `doctor` tam veritabanı bütünlük kontrolü için ayrı kalır.

## Sorumluluklar ve tek görünüm

Ortak modeller `StatusSnapshot`, `StatusAttempt` ve varlık/kaynak geçmişlerini; çıktı modelleri güncellik ve bekleme değerlendirmelerini taşır. `StatusService` küçük `StatusRepository` sözleşmesine bağlıdır. `SQLiteStatusRepository`, mevcut SQLite adaptörünün salt okunur bağlantısını kullanır. Terminal bu parçaları bağlar ve dinamik metni kaçırır.

Genel varlık/gözlem sayıları, bütün bulgu ve iş durum sayıları, toplam/okunmamış bildirimler, seçilen varlıklar, ilgili denemeler ve kaynak beklemeleri aynı `BEGIN` okuma transaction'ından gelir. Başka bir işlem arada kayıt eklese bile farklı anlara ait sayaçlar ve geçmiş birleştirilmez. İşlem sonunda okuma transaction'ı kapatılır.

Servis görünümü aldıktan sonra tek saat dilimli zamanı UTC'ye çevirir; bütün süre hesapları bu anı kullanır. Saati okumadan önce snapshot almak, eşzamanlı tamamlanan bir kaydın eski değerlendirme anına göre birkaç milisaniye gelecekte görünmesini önler. Bu sıra cihaz saatinin doğruluğunu ölçmez. Hatalı servis saati raporu reddeder; kayıtlı deneme saatinin sorunu görünümde ayrıca belirtilir.

## Varlık ve kaynak kapsamı

Kaynaklar bu sürümde `crt.sh` ve `urlscan`'dir. Bir işin hedefleri JSON listesinden okunur ve seçilen domainle tam üyelik karşılaştırması yapılır. Alt metin/marka benzerliği veya sağlayıcı genelinde başka adresin son başarısı kapsam kanıtı olarak kullanılmaz.

Her varlık/kaynak çifti için üç bilgi vardır:

- Son eklenen deneme; durumu, başlangıcı/bitişi, sorgu sayıları ve varsa hata özeti.
- Son eklenen `complete` deneme; önceki başarı zamanı ve kimliği ayrıca korunur.
- Bu varlık/kaynak için sıradaki iş sayısı.

Denemeler `scan_attempts.rowid` azalan sırasıyla seçilir. UTC tarihlerinin en büyüğünü veya işin oluşturulma sırasını kullanmak, saat gerilemesini veya eski bir işe yapılan yeni retry'ı yanlış sıralayabilir. Son denemenin başarısız/kısmi/yarım olması önceki tamamlanmış denemeyi silmez; iki kayıt birlikte görünür.

Tamamlanmış çok hedefli iş bütün hedeflerine uygulanır. Kısmi işte hangi hedefin tam olarak bittiğini kesin ayıran kayıt bulunmadığı için hiçbir hedefin tamamlanmış zamanı yenilenmez. Sıraya alma ve `running` kayıtları da tamamlanma sayılmaz. `running` canlı süreç kanıtı değildir; özet bunu “Çalışıyor olarak kayıtlı” diye gösterir.

Seçilen denemeler mevcut JSON doğrulayıcısıyla okunur. Sonuç hedefleri, iş/deneme bağlantısı ve durum tutarlılığı kontrol edilir. Seçilen her iş için deneme sayısı ve en büyük deneme numarası kayıtlı `attempt_count` ile; son denemenin durumu işin durumuyla karşılaştırılır. Eksik veya tutarsız geçmiş reddedilir. Tamamlanmış denemede sorgu bulunmaması ya da başarısız/kısmi sorgu bulunması kabul edilmez; böyle bir kayıt güncel arama sayılmaz. Bir bozuk seçili kayıt sessizce eski başarıyla değiştirilmez. Bu kontroller bütün veritabanı veya bütün geçmiş içeriğinin tam denetimi değildir.

## Güncellik ve saat davranışı

Varsayılan eşik 24 saattir. `--stale-after-hours` 1–8760 arasında bir tam sayı alır ve yalnız bu görünümün değerlendirmesini değiştirir; çalışma zamanlaması veya kayıtlı ayar oluşturmaz.

| Değer | Anlamı |
|---|---|
| `current` | Son tamamlanan aramanın bitişinden beri geçen süre eşikten küçüktür. |
| `stale` | Bu süre eşiğe eşit veya daha büyüktür. |
| `never` | Varlık/kaynak için tamamlanmış deneme yoktur. |
| `clock_error` | Son deneme veya son tamamlanan denemenin zamanı okunamıyor, saat dilimsiz, gelecekte veya başlangıç/bitiş sırası tutarsızdır. |

`running` denemede geçerli, gelecekte olmayan başlangıç ve boş bitiş beklenir. Diğer durumlarda başlangıç ≤ bitiş ≤ değerlendirme zamanı olmalıdır. Güncellik hatasında yaş alanı `null` olur; negatif süre sıfıra çevrilip güncel sayılmaz. Geçerli yaş tam saniyeye aşağı yuvarlanır, ancak güncellik sınırı tam zaman farkıyla karşılaştırılır.

Yakın zamanda tamamlanmış aramadan sonra başarısız deneme gelebilir. Bu durumda tamamlanmış aramanın güncelliği ve son denemenin başarısızlığı birlikte görünür. “Güncel” anlık kaynak erişimi, yeni içerik garantisi veya bütün internetin tarandığı anlamına gelmez. Kaynakların tarih, indeks ve sayfa sınırları devam eder. Saat alanları cihazın kayıtlı zamanlarına dayanır; ayrı saat eşitleme/sağlık kontrolü yoktur.

Bekleme kayıtları aynı görünümden gelir. Geçerli kalan süre pozitifse yukarı yuvarlanır; dolmuş satır silinmez. Gelecekteki kayıt zamanı veya tutarsız zamanlarda `clock_error=true` gösterilir. Bu durumda `active=false` ve `remaining_seconds=0` yer tutucudur; “bekleme doldu” sonucu olarak yorumlanmaz. Terminal önce saat hatasını gösterir.

## Çıktı sınırları ve maliyet

Varsayılan ayrıntı alfabetik ilk 20 varlıktır; `--limit` 1–100 arasındadır. Toplam/gösterilen sayı ve dışarıda kalan varlıklar açıkça gösterilir. Bu görünüm cursor ile sayfalanmaz; `status DOMAIN` ile kayıtlı bir adres tam eşleşmeyle seçilebilir. Bilinmeyen adres doğrulama hatasıdır. Filtre genel sayaçları veya kaynak beklemelerini daraltmaz.

İş sayıları geçmiş dahil bütün kayıtlı işlerin mevcut durumlarına aittir. Bunlar açık arıza veya anlık kaynak kesintisi sayacı değildir. Bildirim okundu durumu ve bulgu inceleme kararı ayrı gösterilir; salt okuma ikisini de değiştirmez.

İşlerin hedef listesi ve küçük deneme alanları akış halinde işlenir. Sonuç/sorgu JSON'ları yalnız seçilen son denemeler ve son tamamlanan denemeler için yüklenir; bütün retry geçmişi belleğe alınmaz. SQLite JSON uzantısına ihtiyaç duyulmaz, okuma sırasında indeks veya başka kayıt oluşturulmaz. İlgili başarı çok eskiyse geçmişin tamamına kadar gidilebilir; en kötü okuma işi geçmiş boyutuyla büyür. Bu düzen büyük ölçek veya sabit yanıt süresi garantisi değildir.

## Uyumluluk ve doğrulama

Şema 6 değişmez; 0.8.0 kayıtları yeni migration gerektirmeden okunur. Eksik veritabanı oluşturulmaz, eski şema kendiliğinden dönüştürülmez. Yeni bağımlılık, ücretli hizmet veya dış hesap gerekmez.

Durum özeti için 21 servis, 19 depolama ve 10 terminal testi vardır. Bunlar yeni varlığın eski kaynak başarısını kullanmamasını, başarı sonrası hatayı, 100'den fazla denemeden eski başarıyı bulmayı, eski işin yeni retry'ını, saat sınırlarını, çok hedefli kısmi işi, eksik/tutarsız geçmişi, sorgusuz tamamlanmış kaydın reddini, WAL altında eşzamanlı yazmada tek görünümü, değişmeyen okundu/karar/iş kayıtlarını, kaçırılmış terminal metnini ve yedekten dönüşü kapsar. Mimari testi uygulamanın somut adaptöre bağımlı olmadığını kontrol eder. 0.9.0 için toplam 477 test geçti; güncel doğrulama ve canlı çalışma sınırları [STATUS.md](../STATUS.md) içinde tutulur.
