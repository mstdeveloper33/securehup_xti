# Planlı haber toplama ve yerel bildirim

0.146.0 / şema 69, mevcut CISA, UK NCSC ve CERT-FR haberlerini `collect`
profillerine ekler. Profil önce seçilen yayıncıların RSS/Atom akışlarını
alır, ardından seçilmiş kayıtlı haber aramalarını karşılaştırır. Yeni veya
anlamlı biçimde değişen eşleşmeler mevcut `inbox` içinde görünür.

## İlk kullanım

Güncel kodu aldıktan sonra eski veri için `./xti migrate` çalıştır. Geçiş
önce ayrı yedek alır; kullanıcı kayıtlarını silmez. Yeni kurulum normal
`./setup` yolunu kullanır. Ek API anahtarı veya yeni paket gerekmez;
RSS okuyucusu normal kurulumda zaten vardır. `--core-only` kurulumda
haber okuyucusu kurulmamış olabilir.

```sh
./xti assets add example.com
./xti search-watch add "Firma haberleri" "example.com" --kind news
./xti profiles save haberler example.com --only-news --news-source cisa --news-source ncsc --news-source cert-fr --search-watch ARAMA_KIMLIGI
./xti collect --profile haberler --plan
./xti collect --profile haberler
./xti inbox
```

Domain zaten kayıtlıysa ilk adımı atla. `ARAMA_KIMLIGI` yerine ikinci
komutun verdiği kimliği kullan. Arama metni domain yerine firma adı da
olabilir. `profiles save` seçimleri kaydeder; `--plan` yalnız önizler.
İnternet isteğini `collect` başlatır. Kaynaklar yayıncının döndürdüğü
haberlerle sınırlıdır; bütün internette firma araması değildir. Bunun
ayrı yolu [Tavily firma araması](MENTIONS.md) ve [grup izlemesidir](MENTION_GROUPS.md).

İlk başarılı arama mevcut kayıtları sessiz başlangıç olarak saklar.
Sonraki yeni/anlamlı değişen eşleşmeler bildirim üretir. Aynı haberin
yeniden alınması bildirim üretmez. Bir adın haber içinde geçmesi tek
başına ihlal veya tehdit kararı değildir.

## Seçimler

- `--news-source cisa|ncsc|cert-fr` tekrarlanabilir; yalnız seçilen kaynaklar alınır.
- `--only-news` varsayılan domain arşivi işlerini kapatır. En az bir haber
  kaynağı gerekir; başka görev veya sosyal/sızıntı izlemesiyle birlikte seçilemez.
- `--only-news` verilmezse eski varsayılan üç domain arşivi işi korunur.
- `--search-watch ID` yalnız etkin, sadece `news` kapsamlı ve `--all`
  kullanmayan normal kayıtlı aramalar içindir. Tavily grubunun yönettiği
  izlemeler kendi grup yolundan çalışır.
- Haber aramaları bütün yerel haber kataloğunu karşılaştırdığı için bu
  otomasyonda üç haber kaynağı da açıkça seçilmelidir. Bu, yalnız tek
  kaynağı yenileyip diğerlerini güncel saymayı önler.
- Bütün sosyal/sızıntı/haber araması seçimlerinin toplam sınırı 50'dir.
  `--watch-item-limit` yalnız gösterilen kanıtı sınırlar; alınan haberleri
  veya karşılaştırma kapsamını kesmez.

Yalnız bir yayıncıyı alıp arama çalıştırmamak için:

```sh
./xti collect example.com --only-news --news-source cisa
```

Profilin domaini mevcut yerel analiz bağlamıdır. Yayıncının toplam haber
sayısı domainin bulgu sayısı değildir. Haber toplama hedef sitenin
sayfalarını, görsellerini veya eklerini açmaz.

## Hata, geçmiş ve devam

```sh
./xti collections show OTURUM_KIMLIGI
./xti collections resume OTURUM_KIMLIGI --plan
./xti collections resume OTURUM_KIMLIGI
./xti news run-show HABER_CALISMA_KIMLIGI
./xti search-watch run-show ARAMA_CALISMA_KIMLIGI
```

Kaynaklardan biri hata verirse başarılı kayıtlar korunur; bağlı arama
`dependency_failed` nedeniyle atlanır. Eski katalog üzerinden yeni bir
başarı/bildirim üretilmez. Başarılı boş kaynak yanıtı ise hata değildir.

Kaynak sonucu ile toplama kaydı birlikte yazılır. Arama sonucu, fark ve
bildirim de birlikte yazılır. Kesinti sonrası `collections recover`,
tamamlanmış kanıtı koruyarak açık oturumu kapatır. `resume` yeni yürütmede
yalnız eksik adımları çalıştırır; tamamlanmış kaynakları tekrar indirmez.
Eksik arama, o oturumda kaydedilmiş kaynak çalışmalarının tarihî kesitini
kullanır. Sonradan alınan başka haberler bu eski çalışmaya karışmaz.

İzleme tanımı değişmişse veya aynı arama daha yeni kaynaklarla ilerlemişse
eski kesitten geriye dönük yanıltıcı fark üretmek yerine açık uyuşmazlık
hatası verilir. Güncel seçimi yeni bir `collect` çalışmasıyla başlat.
Eski oturumun kanıtı okunabilir kalır.

## Linux zamanlama

```sh
./xti schedule generate haberler --output ./.xti-data/zamanlama-haberler --at 09:00 --timezone Europe/Istanbul --keep 7
```

Bu komut hizmeti açmaz; yeni klasöre dosyaları ve etkinleştirme talimatını
yazar. Mevcut kilit, kesilmiş oturum ve doğrulanmış yedek kontrolleri
kullanılır. [Linux zamanlama rehberi](LINUX_SCHEDULING.md) geçerlidir.

## Veri ve uyumluluk

Şema 69 iki toplama geçmişi tablosuna haber/arama bağlantılarını ekler.
Önceki kayıtlar, satır kimlikleri, tanım/plan metinleri ve kanıt özetleri
korunur. Haber seçimi olmayan profil eski v1 tanımını kullanır; yeni
seçimler v2 tanımıyla saklanır. Eski varsayılanlar yeni kaynak başlatmaz.
Geri dönüşte eski sürümün yedeği yalnız yeni bir veri dizinine açılır;
mevcut veritabanının üzerine yazılmaz.

Bu çalışma yeni ücretli servis, e-posta, web paneli veya engine v1 işlemi
eklemez. Mevcut `news refresh` tek başına arama çalıştırmaz; otomatik
karşılaştırma yalnız açıkça seçilmiş toplama akışındadır.
