# Firma ve tedarikçi hakkında internette içerik arama

0.145.0 / şema 68; tekil arama 0.144.0'da eklendi. `mentions search`, seçtiğin firma için Tavily üzerinden
gerçek web veya haber araması yapar. `mentions list/show/run-show/status`
kaydedilen sonuçları internet ve API anahtarı olmadan okur.

## Kurulum ve ilk kullanım

[Tavily hesabından](https://app.tavily.com/) kendi API anahtarını al.
15 Kasım 2026'da belgelenen ücretsiz hak ayda 1.000 kredidir; temel
arama 1 kredi tüketir. Güncel hak ve ücretleri [sağlayıcı belgesinden](https://docs.tavily.com/documentation/api-credits)
kontrol et. Anahtarı GitHub'a, komut argümanına veya sohbet mesajına yazma.

Mevcut kayıt alanını güncelliyorsan önce `./xti migrate` çalıştır.
Geçiş benzersiz yedek alır ve eski kayıtları korur. Yeni kurulumda normal
`./setup` yeterlidir; yalnız bu modül için ek Python paketi gerekmez.
Şema 68'den eski koda dönerken yedeği yeni veri dizinine aç;
[kurulum ve güncelleme rehberini](GETTING_STARTED.md) kullan.

```sh
./xti mentions configure
./xti mentions plan --name "Örnek Firma" --domain example.com
./xti mentions search --name "Örnek Firma" --domain example.com
./xti mentions search --name "Örnek Firma" --domain example.com --topic news
./xti mentions list
./xti mentions status
```

`configure` anahtarı görünmeyen terminal girdisiyle alır; varsayılan
`~/.config/xti/tavily.key` dosyasına yalnız sahibinin okuyabileceği izinle
kaydeder. Mutlak `XDG_CONFIG_HOME` tanımlıysa onun `xti/tavily.key` yolu
kullanılır. Dosya repodan ve kanıt veritabanından ayrıdır. Var olan anahtarın
üzerine yazılmaz. Kurulum internet isteği yapmaz. Özel dosya konumu:

```sh
./xti mentions configure --api-key-file /guvenli/konum/tavily.key
./xti mentions search --name "Örnek Firma" --api-key-file /guvenli/konum/tavily.key
```

Bu yol örnektir. Anahtar önceliği açık `--api-key-file`, `TAVILY_API_KEY`
ortam değişkeni, sonra varsayılan özel dosyadır. Dosya normal bir dosya
olmalı ve başkalarına okuma izni vermemelidir (`chmod 600`). Anahtarı
yenilemek için yeni özel dosya oluşturup onu seçebilirsin. XTI veritabanı
yedeği API anahtarını içermez.

`plan` yalnız gönderilecek sorguyu, hedefi ve belgelenen tüketimi gösterir;
arama yapmaz, kredi tüketmez, kayıt yazmaz. Firma adı doğrudan verilirse
plan için kayıt alanı da gerekmez. `search` açık bir dış sorgudur:
firma adı/domainler Tavily'ye gönderilir; tüm tedarikçi envanteri gönderilmez.

## Kayıtlı kuruluş ve tedarikçiyi seç

```sh
./xti organizations list
./xti suppliers list
./xti mentions plan --organization KURULUS_KIMLIGI
./xti mentions search --organization KURULUS_KIMLIGI --topic news
./xti mentions search --supplier TEDARIKCI_KIMLIGI
./xti mentions list --organization KURULUS_KIMLIGI
./xti mentions status --supplier TEDARIKCI_KIMLIGI
```

Kimlikleri liste çıktısından al. Kuruluş adı ve etkin domain bağlantıları,
tedarikçinin adı ve ana domaini mevcut kayıtlardan alınır. Geri çekilmiş
hedefte yeni arama yapılmaz; eski sonuçlar okunur. `--domain` yalnız
doğrudan `--name` ile kullanılır. En çok 10 domain ve 400 karakterlik
sorgu kabul edilir; büyük kapsam sessizce daraltılmaz.

Her tekil komut seçilen bir hedefi arar. Tedarikçi seçmek onu bir kuruluşa
otomatik bağlamaz; müşteri/tenant ayrımı oluşturmaz. 0.145.0'daki
[izleme grupları](MENTION_GROUPS.md), kuruluş ve seçilmiş tedarikçileri
birlikte bütçeli toplar ve zamanlama dosyaları üretir.

## Çıktı, geçmiş ve yeni içerik

Her sonuç başlık, özgün bağlantı, en fazla 2.000 karakter açıklama,
sağlayıcının varsa yayın/güncelleme tarihi tahmini, sorgu ve hedef
bilgisiyle saklanır. İlk görülme, son görülme ve son anlamlı değişim
ayrıdır. Kaynak puanı uygunluk puanıdır; tehdit skoru değildir.

Görünür başlık/açıklama/URL içinde ad veya domain bulunursa eşleşen terim
ve alan gösterilir. Görünür eşleşme yoksa sonuç yalnız sağlayıcının
önerdiği aday olarak gösterilir. Aynı adlı başka şirket, normal haber ve
tehdit iddiası için insan incelemesi gerekir. Tam makale, görsel, hedef
web sayfası veya LLM cevabı indirilmez.

```sh
./xti mentions list --offset 0 --limit 20
./xti mentions show KAYIT_KIMLIGI
./xti mentions run-show CALISMA_KIMLIGI
./xti --json mentions list
./xti search "example.com" --kind mention
```

`list --limit` yalnız görüntüleme sınırıdır; toplamı ve sonraki sayfa
komutunu verir. `search --max-results 1..20` gerçekten toplanacak sonuç
sayısıdır; varsayılan 10'dur. Her çalışma en çok 20 sonuç içerdiğinden
`run-show` bütün sonuçlarını, aynı kayıtlar dahil, gösterir. Yeni/değişen/aynı
ayrımı ve değişen içeriğin önceki hali o günkü kanıttan okunur.

Aynı hedef tanımı, konu ve toplama sınırında aynı URL tekrar geldiğinde
aynı kayıt güncellenir; yalnız puan değişmesi anlamlı içerik değişimi
sayılmaz. Hedef adı/domaini, konu veya toplama sınırı değişirse ayrı sorgu
bağlamı oluşur. Aynı bağlantı farklı hedefler altında ayrı kaynak bağı
taşıyabilir. URL parametreleri keyfî silinmez.

Genel arama ve engine v1'in `search`/`record.get` işlemleri bu kayıtları
`mention/company_mention`, `tavily` namespace'iyle okuyabilir. Dört engine
işlemi korunur. Eski kayıtlı aramaların kapsamı otomatik genişlemez.

```sh
./xti search-watch add "Firma içerikleri" "example.com" --kind mention
./xti search-watch run ARAMA_IZLEME_KIMLIGI
./xti inbox list
```

İzleme kimliğini `add` çıktısından al. İlk karşılaştırma sessiz başlangıçtır;
sonraki karşılaştırmalar yeni/anlamlı değişen yerel eşleşmeleri bildirir.
`mentions search` izlemeyi kendiliğinden çalıştırmaz. Arama sonuçlarında
görünmemek eski kanıtı silmez veya olayın çözüldüğünü söylemez.

## Kredi ve hata davranışı

- Her `search` tek `basic` isteği gönderir; gelişmiş arama, otomatik
  parametre seçimi, tekrar deneme veya gizli ikinci sorgu yoktur.
- `status` yalnız bu veri alanındaki isteklerde Tavily'nin bildirdiği
  kredileri toplar. Bu, hesap bakiyesi veya fatura değildir. Ücretsiz
  bakiyeyi kontrol etmez; ücretli hesabın varsa çağrı o bakiyeyi kullanabilir.
- Anahtar/kapsam/şema hatası ve yazıcı kilidi, HTTP isteğinden önce
  durdurulur. Başarısız HTTP isteği zaten kredi tüketmiş olabilir;
  hata kayıtlarının kullanımı sıfır yerine bilinmiyor olarak gösterilir.
- Başarılı boş sonuç ile erişim/kota hatası ayrıdır. Önceki başarı korunur.
  HTTP hata gövdesi ve kimlik doğrulama bilgisi kaydedilmez.
- Yanıt 2 MiB ile sınırlıdır; bağlantı zaman aşımı 20 saniye, yanıt okuma
  son tarihi 45 saniyedir. Socket bekleyişi nedeniyle bu kesin duvar saati
  garantisi değildir. Yönlendirme ve ortamdan otomatik proxy seçimi yoktur.
- Yerel tarihçe 10.000 çalışma, 50.000 benzersiz kapsam/URL kaydı,
  çalışma başına 512 KiB ve toplam 64 MiB kanıtla sınırlıdır. Kapasite
  aşımında geçmiş silinmez. Yeni istek öncesi depolama payı kontrol edilir.

Tavily sonuç saklamaya izin verdiğini, birden fazla müşteriye aynı
saklanmış sonuçları paylaşmak için destekle görüşülmesini belirtiyor.
Yayıncı içeriğinin hakları ayrıdır. [Saklama açıklaması](https://help.tavily.com/articles/1612400809-storing-caching-retaining-output).
Bu kişisel engine teslimi kurumsal yeniden dağıtım anlaşması veya
kesintisiz hizmet taahhüdü oluşturmaz.
