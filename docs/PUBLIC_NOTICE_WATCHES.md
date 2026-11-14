# Kuruluş için kamu olay bildirimleri

Bu izleme HIBP'nin ücretsiz kamu olay kataloğunu kullanır. Kaynağın
bildirdiği domain, kuruluşuna bağladığın domainle tam eşleşirse ilgili
kayıt sayılır. Hesap/e-posta/parola sorgusu yapmaz. Kaynakta eşleşme bulunması
tek başına XTI'nin doğruladığı bir ihlal kararı değildir.

## 1. Kuruluş ve domain bağlantısını seç

Mevcut kuruluşlarını görmek için:

```sh
./xti organizations list
```

Yeni kuruluş gerekiyorsa:

```sh
./xti assets add example.com
./xti organizations add "Örnek Şirket"
```

Çıktıdaki kuruluş kimliğini sonraki komutlarda `KURULUS_KIMLIGI` yerine yaz:

```sh
./xti organizations link KURULUS_KIMLIGI --kind domain --value example.com
./xti notices watch enable KURULUS_KIMLIGI
./xti notices watch show KURULUS_KIMLIGI
```

Açma işlemi internete çıkmaz. İlk başarılı katalog yenilemesi bu izlemenin
başlangıcını oluşturur; geçmişteki kayıtlar yeni bildirim gibi kutuya atılmaz.
İzleme açılmadan önce indirilmiş katalog varsa da aynı kural geçerlidir.

## 2. Kataloğu yenile

```sh
./xti notices refresh
./xti inbox list
```

Sonraki yenilemelerde ilgili yeni/değişen kayıtlar varsa kuruluş başına,
çalışma başına bir bildirim oluşur. Tekrar indirme aynı kaydı tekrar
bildirmez. Bildirimin içinde hangi olayların değiştiği ayrı ayrı görülür.

`collect DOMAIN --task notices-hibp` veya bu işi içeren kayıtlı/zamanlanmış profil
de aynı izleme yolunu çalıştırır. Tek katalog yenilemesi bütün açık kuruluş
izlemelerini ilerletir; `collect` komutundaki domainle sınırlı değildir.
İzleme açmak kendi başına zamanlayıcı kurmaz veya kaynak indirmez.

## 3. Sonucu ve kanıtı aç

```sh
./xti notices watch show KURULUS_KIMLIGI
./xti notices watch-run-show IZLEME_CALISMA_KIMLIGI
./xti inbox show BILDIRIM_KIMLIGI
./xti organizations report KURULUS_KIMLIGI
```

İzleme ayrıntısında kapsamın domainleri, kaynak çalışması ve önce/sonra
kayıtları bulunur. Bildirim ayrıntısı yeni/değişenler önce olmak üzere ilk
20 çalışma kaydını gösterir; devamı için
çıktıdaki `watch-run-show ... --offset 20` komutunu kullan. Çalışma ayrıntısı
başlangıç kayıtlarını, listeden çıkanları ve değişmeyen kayıtları da gösterir.
Toplam kayıt sayısı yeni alarm sayısı değildir; kayıttan çıkma sorunun
çözüldüğünü göstermez.

Eski çalışmalar ve açma/kapatma geçmişi de sayfalanır:

```sh
./xti notices watch show KURULUS_KIMLIGI --run-offset 20 --run-limit 20
./xti notices watch show KURULUS_KIMLIGI --event-offset 20 --event-limit 20
```

Kuruluş raporunda `--item-offset` bu iki geçmiş bölümünü de ilerletir.

Görünümleri açmak bildirimi okundu yapmaz:

```sh
./xti inbox read BILDIRIM_KIMLIGI
./xti inbox unread BILDIRIM_KIMLIGI
```

Okundu işareti tehdit/ihlal doğrulaması değildir. Bütün okuma komutları
yerel kayıtları kullanır; yeni internet sorgusu yapmaz.

## Kapsam değişirse

- Kuruluşa yeni domain bağlarsan ilk ölçümü sessizdir. Daha önce izlenen
  diğer domainlerin yeni/değişen kayıtları bildirilmeye devam eder.
- Domain bağlantısını kaldırırsan sonraki çalışmada izlenmez. Yeniden
  bağlarsan o domain için yeni sessiz başlangıç yapılır.
- Kuruluş adını veya bağlantı açıklamasını değiştirmek başlangıcı sıfırlamaz.
- Kuruluşu kapatıp yeniden açmak yeni sessiz başlangıç gerektirir.
- Kaynak hatası önceki başarılı kanıtı silmez. Son deneme ile son başarılı
  değerlendirme ayrı gösterilir; hata sıfır eşleşme anlamına gelmez.
- Eski bildirimler kendi zamanındaki kuruluş/kapsam/kaynak kanıtını korur.
  Aynı domaini iki kuruluşa açıkça bağladıysan her açık izleme ayrı bildirim
  oluşturabilir; bunlar iki farklı ihlal sayısı değildir.

## İzlemeyi kapat

```sh
./xti notices watch disable KURULUS_KIMLIGI --reason "Şimdilik takip edilmeyecek."
./xti notices watch list --all
```

Kapatmak geçmişi veya bildirimleri silmez. Yeniden `enable` dersen sonraki
başarılı değerlendirme sessiz başlangıçtır. İlk açılışta veya yükseltmede
hiçbir kuruluş kendiliğinden izlemeye alınmaz.

Kaynak: [Have I Been Pwned](https://haveibeenpwned.com),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Ücretli API anahtarı gerekmez; dış kaynağın erişim koşulları geçerlidir.
