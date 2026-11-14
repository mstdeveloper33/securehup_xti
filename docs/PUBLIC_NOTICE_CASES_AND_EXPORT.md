# Kamu olayını vakaya bağlama ve HTML rapor

0.137.0 · 15 Kasım 2026 · şema 63. Eski kurulumda önce `./xti migrate`
çalıştır. Geçiş benzersiz bir geri dönüş yedeği alır; mevcut vaka ve
kaynak kayıtlarını korur. Bu iki özellik yeni paket veya ücretli API istemez.

## 1. İncelenecek tarihî kaydı seç

Kuruluşa özel bir bildirimden ilerliyorsan:

```sh
./xti inbox
./xti inbox show BILDIRIM_KIMLIGI
./xti notices watch-run-show IZLEME_CALISMA_KIMLIGI
```

Çıktıdaki izleme çalışma kimliğini ve olayın `Name` kimliğini kullan.
Olay başlığı veya domaini olay kimliği yerine yazma. İzleme kullanmadan
genel katalogdaki bir olayı seçmek için `notices status` ve
`notices run-show KAYNAK_CALISMA_KIMLIGI` kullanılabilir. Kaynak çalışması
ile kuruluş izleme çalışması farklı kimliklerdir.

## 2. Vakaya kanıtı ekle

Önce mevcut vakanı seç veya yeni vaka aç:

```sh
./xti cases list
./xti cases create "Kamu olayını incele" --summary "Kaynak kaydı değerlendirilecek." --reason "İnsan incelemesi."
```

Kuruluş izlemesinden bağlamak için:

```sh
./xti cases evidence-add VAKA_KIMLIGI \
  --type public_notice_watch \
  --evidence-id 'IZLEME_CALISMA_KIMLIGI:OLAY_ADI_KIMLIGI' \
  --reason "Bu tarihî kaynak kaydını incelemek için."
```

Genel katalog çalışmasından bağlamak için tür `public_notice`, kimlik
`KAYNAK_CALISMA_KIMLIGI:OLAY_ADI_KIMLIGI` olur. Büyük harfli yer tutucuları
çıktıdaki gerçek değerlerle değiştir. İki nokta üst üste ayıracı korunmalı.

Bu işlem ağa çıkmaz. Seçilen çalışmadaki önce/sonra bilgi, kaynak sınıfları,
atıf/lisans ve varsa olayla ilgili tarihî kuruluş kapsamı saklanır. Başlangıç,
yeni, değişen, çıkarılan ve değişmeyen kayıtlar ayrılır. Aynı olayın aynı
çalışmadaki birden fazla kapsam etkisi birlikte korunur. Kaynak daha sonra
değişse bile vakadaki kanıt değişmez. Yeni tarih için yeni çalışma kimliğiyle
ayrı kanıt eklenir; mevcut insan kararları otomatik değiştirilmez.

```sh
./xti cases show VAKA_KIMLIGI
./xti cases evidence-show VAKA_KIMLIGI KANIT_BAGLANTISI_KIMLIGI
./xti --json cases evidence-show VAKA_KIMLIGI KANIT_BAGLANTISI_KIMLIGI
```

`evidence-show` tek kaydı, vaka ekranının sayfa sınırından bağımsız açar.
JSON'da tam donmuş içerik `snapshot_json`, özeti `snapshot_sha256` alanındadır.
Kapsam çok genişse vakaya yalnız olayla ilgili üyeler kopyalanır; tam
kapsamın özeti ve üye sayısı ayrıca saklanır. Bu ayrım çıktıdaki alanlarda
belirtilir. Olay kaydı tek başına doğrulanmış ihlal veya çalınmış hesap
kanıtı değildir; e-posta/parola ya da ham sızıntı alınmaz.

## 3. Kuruluşun raporunu dosyaya al

```sh
./xti organizations list
./xti organizations export KURULUS_KIMLIGI --output rapor-2026-11-15.html
```

Oluşan dosyayı tarayıcıda aç. İnternet, sunucu, React veya ek kurulum
gerekmez. Dosya okunabilir ve yazdırılabilir; kaynak bağlantılarına ancak
sen tıklarsan internet erişimi gerekir. Gezinme komutları kendiliğinden
çalışmaz. `--json` sonucu dosya yolu, boyutu ve SHA-256 özetiyle verir.

Rapor bütün etkin hedefleri ve her bölümün tüm kayıtlarını içerir; terminaldeki
50/500 kayıtlık sayfaya bağlı değildir. Kaynak hataları, eski/eksik veri,
kamu olayları, bildirim/vaka bağlantıları ve kuruluşun tarihî kamu olay
izleme kayıtları ayrı görünür. Dış yüzey kartları son DNS/TLS/web/posta/
servis/CNAME kontrolünü ve son başarı durumunu gösterir; bütün eski kontrol
serisini içermez. Ortak vakanın özel başlık/notları ve başka kuruluşa ait
kanıtları rapora taşınmaz. Bu, kişisel gruplamadır; çok kullanıcılı erişim
kontrolü değildir.

Mevcut dosyanın üzerine yazılmaz; her rapora yeni bir ad ver. Hedef klasör
önceden var olmalı ve yol sembolik bağlantı içermemeli. Dosya yerel özel
izinlerle oluşturulur; otomatik yüklenmez veya gönderilmez.
Yazım tamamlandıktan sonra klasörün kalıcı kaydı doğrulanamazsa komut bunu
ayrıca bildirir; tam dosya mevcut olabilir. Yeniden denemeden önce belirtilen
dosyayı kontrol et. Mevcut rapor hiçbir durumda yeni raporla değiştirilmez.

Tam dışa aktarım sınırları 1.000 etkin hedef, toplam 50.000 rapor kaydı ve
32 MiB HTML'dir. Sınır veya veri doğrulama hatasında eksik dosya üretilmez;
komut açık hata verir. Rapor almak veritabanını değiştirmez, kaynak yenilemez
ve bildirimleri okundu yapmaz. Yenileme için mevcut toplama/profil akışı
kullanılır.
