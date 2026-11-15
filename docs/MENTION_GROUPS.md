# Firmanı ve tedarikçilerini birlikte izle

0.145.0 / şema 68. Bu özellik, seçtiğin kuruluş ve tedarikçiler için
Tavily web/haber aramalarını bir grupta çalıştırır. Sorgu bütçesini ve
aralığını korur; başarılı toplamanın ardından mevcut `search-watch → inbox`
karşılaştırmasını yapar. Sonuçlar kaynaklı içerik adaylarıdır, otomatik
ihlal veya tehdit kararı değildir.

## İlk kurulum

Mevcut kurulumda `git pull --ff-only` ardından `./xti migrate` çalıştır.
Geçiş önce benzersiz yedek alır. Yeni kurulumda `./setup` yeterlidir.
Tavily anahtarını bir kez `./xti mentions configure` ile gizli terminal
girişinde kaydet. Ek Python paketi gerekmez.

Kuruluş ve tedarikçi kimliklerini mevcut kayıtlarından seç:

```sh
./xti organizations list
./xti suppliers list
./xti mentions groups save "Firmam ve tedarikçilerim" \
  --organization KURULUS_KIMLIGI \
  --supplier TEDARIKCI_KIMLIGI \
  --topic news --interval-hours 23 --run-queries 2 --daily-queries 2
./xti mentions groups list
```

Kimlik alanları örnektir; listelerdeki gerçek UUID'leri kullan. Tedarikçi
seçeneği tekrarlanabilir veya çıkarılabilir. Grup bir kuruluş ve en çok
19 seçilmiş tedarikçi içerir. Kuruluşun etkin domain bağlantıları ve
tedarikçilerin kayıtlı ana domainleri kullanılır. Bütün tedarikçi envanteri
kendiliğinden seçilmez. Bu grup izleme ilişkisi kurar; müşteri yetki
yalıtımı veya başka tedarikçi modüllerinin kapsamını değiştirmez.

Aynı grup adıyla `save`, tanımın **tamamını** sürümlü değiştirir; önceki
tedarikçiler/seçenekler otomatik eklenmez. Her çağrıda tam istediğin seçimi
ver. Kesilmiş çalışma varsa önce onu tamamla. Grup kimliği, geçmişi,
günlük kullanımı ve önceki çalışma zamanı korunur; güncellemek veya
kapatıp açmak bütçeyi sıfırlamaz.

## Planla, çalıştır, bütün sonuçları gör

`GRUP_KIMLIGI`, `save/list` çıktısındaki kimliktir:

```sh
./xti mentions groups plan GRUP_KIMLIGI
./xti mentions groups run GRUP_KIMLIGI
./xti mentions groups show GRUP_KIMLIGI
./xti mentions groups runs GRUP_KIMLIGI
./xti mentions groups run-show CALISMA_KIMLIGI --details
./xti inbox list
```

`plan` bütün seçili hedefleri, gönderilecek sorguları, bir turun kaç
sorgu gerektirdiğini, kalan günlük hakkı ve bekleme nedenini gösterir.
İnternete çıkmaz. `run`, zamanı ve bütçesi uygunsa her hedef için tek
temel istek gönderir. Her çalışma hedef adını/domainlerini ve grup
sürümünü dondurur; sonraki ad değişikliği geçmiş kanıtı değiştirmez.

`run-show --details`, aynı olanlar dahil her hedefin bütün sınırlı kaynak
sonuçlarını, önce/sonra farklarını ve bağlantılarını gösterir. Kaynak
çalışması ile bildirim karşılaştırmasının kimlikleri ayrıdır. `list/runs`
görünümleri sayfalıdır; `--offset` ve `--limit` yalnız ekranda gösterilen
kısmı değiştirir. Okumalar API anahtarı veya internet gerektirmez.

## Sorgu bütçesi ve aralık

- `--run-queries`: bir tur için üst sınır, 1–20. Hedef sayısı sınırı
  aşıyorsa grup sessizce kesilmez; arama başlamadan hata verilir.
- `--daily-queries`: grup başına UTC takvim gününde en çok 1–1.000 sorgu.
  Turun bütün hedefleri için yeterli hak yoksa yeni tur başlamaz.
- `--interval-hours`: iki yeni turun başlangıcı arasında en az 1–8.760
  saat. Varsayılan 23 saattir. Elle tekrar çağırmak bu aralığı atlamaz.
- Her HTTP isteğinden **önce** kalıcı bir sorgu hakkı ayrılır. Hata,
  zaman aşımı veya kesinti hakkı geri vermez; istek kredi tüketmiş olabilir.
  UTC günü her istekte yeniden değerlendirilir.
- İlk kaynak hatasında kalan hedefler o turda atlanır; eski başarılar
  korunur. Sonraki normal tur kayıtlı aralık dolduktan sonra çalışabilir.

Bu yerel sınır **Tavily hesabının toplam harcama sınırı değildir**.
Başka gruplar, başka veri dizinleri, doğrudan `mentions search` ve başka
uygulamalar kendi sorgularını yapabilir. Bütçe temel istek sayısını
sınırlar; gerçek bakiye, fatura ve sağlayıcı tarifesini doğrulamaz.
Kaynağın bildirdiği kredi kullanımı `mentions status` içinde ayrıca görünür.

Yerel grup geçmişi 100 grup, 10.000 çalışma, 100.000 olay ve toplam 64 MiB
olay kanıtıyla sınırlıdır. Tekil içerik ve mevcut bildirim depolarının
sınırları ayrıca uygulanır. Kapasite dolduğunda eski kanıt silinmez;
yeni işlem açıklamalı hatayla durur. Bilinen kapasite sorunları sorgudan
önce kontrol edilir; gelecek yanıtın büyüklüğü önceden garanti edilemez.

## Bildirim nasıl oluşur?

Her grup ve kesin sorgu kapsamında ilk başarılı toplama sessiz başlangıçtır.
Sonraki başarılı toplamalarda yeni bağlantı veya anlamlı içerik değişimi
mevcut yerel bildirim kutusuna düşer. Yalnız kaynak sıralama puanı veya
son görülme zamanı değişmesi bildirim oluşturmaz. Arama penceresinden
düşen eski içerik silinmez; kaynak hatası “içerik yok” anlamına gelmez.

Sorgu kapsamı hedef türü/kimliği, ad/domain, konu ve sonuç sınırını içerir.
Başka hedef/sorgu için toplanmış yerel kayıtlar bu karşılaştırmaya katılmaz.
Tavily aynı adlı başka şirketin haberini yine aday getirebilir; insan
incelemesi gerekir. Kapsam değişirse yeni bir başlangıç oluşur.
Grup bütçesini değiştirip aynı sorguyu korumak
izleme geçmişini sıfırlamaz. Bildirim, ilgili kaynak çalışmasının o günkü
kanıtına bağlıdır; sonradan yapılan başka arama eski bildirimi değiştirmez.

Otomatik oluşturulan kayıtlı aramalar `search-watch list` içinde görülebilir.
Bu kayıtların çalıştırılması ve kapatılması grup tarafından yönetilir;
genel `search-watch run/monitor/disable` komutları bu kayıtlarda reddedilir.
Okuma ve bildirimlerin okundu işlemleri açıktır. Grubu durdurmak için:

```sh
./xti mentions groups disable GRUP_KIMLIGI --reason "İzlemeye ara verildi."
```

## Kesilirse kaldığın yerden devam et

```sh
./xti mentions groups runs GRUP_KIMLIGI
./xti mentions groups run-show CALISMA_KIMLIGI --details
./xti mentions groups resume CALISMA_KIMLIGI
```

Yeni tur, açık kalan önceki çalışma varken başlamaz. `resume`:

1. Sorgusu ayrılmış fakat sonucu kesinleşmemiş isteği **belirsiz** olarak
   kaydeder ve tekrar göndermez.
2. Kaynak sonucu kaydedilmişse yalnız eksik bildirim aşamasını tamamlar.
   Aynı bildirim işlemi ikinci bildirim oluşturmaz; bu adım anahtarsızdır.
3. Henüz sorgulanmamış hedefleri, güncel hedef seçimi ve günlük bütçe
   uygunsa çalıştırır. Hedefler değişmiş/kapanmışsa bekleyenleri atlar.

Tamamlanmış çalışmanın `resume` çağrısı yalnız önceki sonucu döndürür.
Entegrasyon çağrılarında `run --request-id UUID`, aynı kimlikle tekrar
çağrının ikinci toplama başlatmasını engeller. Açık kalmış iş yine
`resume` ile açıkça devam ettirilir. Kimlik başka grupta kullanılamaz.

## Düzenli çalıştırma

Terminal açıkken sınırlı izleme:

```sh
./xti mentions groups monitor GRUP_KIMLIGI \
  --cycles 24 --interval-seconds 3600 --duration-seconds 86400
```

Bu kontrol sıklığı grup aralığını veya bütçesini geçersiz kılmaz.
En fazla 100 tur, en az 60 saniye kontrol aralığı kullanılır. Ctrl+C
kalıcı kanıtı silmez. Bu komut arka plan hizmeti kurmaz.

Linux'ta günlük/haftalık çalıştırma dosyalarını üret:

```sh
./xti mentions groups schedule GRUP_KIMLIGI \
  --at 09:00 --timezone Europe/Istanbul --keep 7 \
  --output ./firma-izleme-zamanlamasi
```

Çıktı klasörü yeni olmalı. Haftalık takvim için `--weekday Mon` eklenebilir.
Üretilen `README.txt`, dosya doğrulama, `systemctl --user` ile etkinleştirme,
durum, günlük ve durdurma komutlarını içerir. **Dosya üretmek zamanlayıcıyı
etkinleştirmez.** Makinenin açık olması gerekir; oturum dışında çalışma
Linux kullanıcı hizmeti/linger ayarlarına bağlıdır.

Zamanlayıcı anahtarın mutlak dosya yolunu kullanır; anahtar değerini unit'e
yazmaz ve terminal ortam değişkenini devraldığını varsaymaz. Özel dosya
için `--api-key-file /mutlak/guvenli/tavily.key` kullan. Ön hazırlık mevcut
doğrulanmış yedek mekanizmasını kullanır, yalnız kendi sahiplik kaydındaki
yedekleri yönetir. Elle alınmış/geçiş yedeklerine dokunmaz. Kesilmiş grup
çalışması varsa hizmet yeni sorgu yapmadan durur; `resume` gerekir.
Grup aralığı sonradan güncellenirse hazırlık adımı takvimle uyumu her
çalıştırmada yeniden denetler; uyumsuzlukta yeni arama başlamaz.

Takvim çalışma saatidir; grup aralığı ayrıca uygulanır. Günlük takvimde
grup aralığı 24 saatten, haftalıkta 168 saatten kısa olmalıdır; eşit veya
daha uzun aralıkla dosya üretimi reddedilir. Varsayılan 23 saat günlük
takvimde küçük başlama gecikmelerine pay bırakır. Manuel ek çalışma,
uzun makine kesintisi veya saat diliminin yaz/kış saati geçişi beklemeye
yol açabilir. Planın en erken zamanı **güncel grubun son çalışmasına**
aittir; tarihî çalışma ayrıntısı görüntülendiğinde de bu anlamı korur.

Bu teslim RSS toplama profillerini değiştirmez; .NET/backend, paylaşılmış
müşteri yetkisi, e-posta, SMS veya LLM eklemez. [Tekil arama rehberi](MENTIONS.md),
[mimari karar](decisions/0150-budgeted-company-monitoring.md).
