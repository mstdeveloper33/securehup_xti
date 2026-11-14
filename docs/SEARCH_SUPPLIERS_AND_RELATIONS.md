# Birleşik arama, tedarikçi bildirimleri ve ilişki geçmişi

0.138.0 · Şema 64. Bu üç özellik mevcut yerel kanıtları kullanır. Yeni ücretli
API, servis veya Python paketi gerektirmez. Kaynak yenilemeleri internet ve
ilgili kaynağın mevcut erişim koşullarını kullanmaya devam eder.

## Kurulum ve güncelleme

Yeni kurulumda normal `./setup` akışını kullan. Mevcut kurulumda güncel kodu
aldıktan sonra:

```sh
./xti migrate
./xti doctor
```

Geçiş mevcut veritabanının benzersiz isimli yedeğini oluşturur ve dört boş
tedarikçi izleme tablosu ekler. Eski kanıt, insan kararı ve bildirimler
değiştirilmez. Geçiş kendiliğinden izleme açmaz veya eski olaylardan alarm
üretmez. Kurtarma mevcut veritabanının üzerine yazmaz; yedek yeni bir
hedefe geri yüklenir.

## 1. Tek komutla yerel arama

```sh
./xti search example.com
./xti search Example --kind supplier --kind case
./xti search example.com --all --offset 0 --limit 50
./xti --json search example.com
```

Domain ve alt alan adayları, marka bulguları, sosyal izleme ve profil
kayıtları, ransomware kaynak iddiaları, kamu olayları, vakalar, tedarikçiler,
kuruluşlar, CTI varlıkları ve IOC kayıtları aynı komuttan aranır.

Her sonuç tür, kimlik, durum, kaynak ve zamanıyla gösterilir. İlgili ayrıntı
veya kaynak geçmişi komutu da bulunur. Önce tam metin eşleşmeleri, sonra başlangıç
ve içerme eşleşmeleri gelir. Sonuçlar bütün türlerde birlikte sayfalanır.
Kaynak kapsamı, incelenen kayıt ve eşleşme sayıları ayrıca gösterilir.

`--all` etkin olmayan veya kaynaktan çıkarılmış kayıtların son bilinen
halini de kapsar; bütün eski sürümlerde tam metin araması değildir.
Kaynağın son isteği başarısızsa önceki başarılı veri güncel kontrol gibi
sunulmaz. Bu komut internette yeni arama yapmaz ve veritabanını değiştirmez.
Yeni veri için mevcut keşif veya kaynak yenileme komutlarını çalıştır.

## 2. Tedarikçi değişim bildirimleri

Önce kullanmakta olduğun tedarikçiyi kaydet veya kimliğini listeden al:

```sh
./xti suppliers add "Örnek Bulut" --domain vendor.example --relationship cloud --criticality high --reason "Yedekleme hizmetim."
./xti suppliers list
```

Listede görünen gerçek kimliği `TEDARIKCI_ID` yerine kullan. Her kaynak
ayrı seçilir:

```sh
./xti suppliers watch enable TEDARIKCI_ID --source threatcluster --reason "Kamuya açık iddiaları izle."
./xti suppliers watch enable TEDARIKCI_ID --source ransomlook --reason "İkinci iddia kaynağını izle."
./xti suppliers watch enable TEDARIKCI_ID --source hibp --reason "Kamu olay kataloğunu izle."
./xti suppliers watch list
```

Bu komutlar yerel izlemeyi açar. Ardından ilgili kaynağı yenile:

```sh
./xti ransomware refresh
./xti ransomware refresh --source ransomlook
./xti notices refresh
./xti inbox list
```

İlk başarılı ölçüm başlangıçtır; mevcut kayıtlar için bildirim üretmez.
Sonraki başarılı yenilemede yeni veya değişen eşleşmeler varsa her tedarikçi
izlemesi için o kaynak çalışmasında tek bildirim oluşur. Aynı sonuç, yalnız çıkarılma ve kaynak
hatası bildirim üretmez. Tedarikçi kimlik tanımı değişirse veya izleme yeniden
açılırsa yeni dönem sessiz başlar. Kritiklik veya gerekçe değişikliği tek
başına karşılaştırmayı sıfırlamaz.

```sh
./xti inbox show BILDIRIM_ID
./xti inbox read BILDIRIM_ID
./xti suppliers watch show IZLEME_ID
./xti suppliers watch-run-show CALISMA_ID --offset 0 --limit 50
./xti suppliers watch disable TEDARIKCI_ID --source hibp --reason "İzlemeye ara verildi."
```

Bildirimde çalışma anındaki tedarikçi tanımı, eşleşme nedeni, kaynak,
önceki ve yeni kayıt görünür. Büyük sonuçlar çalışma görünümünde sayfalanır.
Kaynak ve tedarikçi daha sonra değişse de eski bildirim o günkü kanıtla
açılır. Okundu işareti bir ihlal veya risk kararı vermez.

ThreatCluster mağdur adını ve kayıttaki web domainini; RansomLook mağdur
adını; HIBP ise tam tedarikçi domainini eşleştirir. Aynı adlı kuruluşların
belirsizliği belirtilir. Bunlar kaynak iddiası veya kamu metadata
eşleşmeleridir; tedarikçinin kesin ihlal edildiği veya senin etkilendiğin
sonucunu vermez.

Yalnız programı kurmak arka planda sürekli çalışma başlatmaz. Mevcut
zamanlanmış toplama akışında ilgili kaynak yenileniyorsa açık tedarikçi
izlemeleri de o başarılı yenilemede değerlendirilir.

## 3. Varlıkların ilişki geçmişi

```sh
./xti surface relations example.com
./xti surface relations example.com --kind dns
./xti surface relations example.com --kind certificate --history
./xti surface relations example.com --kind cname --history
./xti surface relations example.com --kind supplier --history
./xti surface relations example.com --history --offset 50 --limit 50
```

Özet görünümü daha önce gözlenen domain→IP, domain→sertifika, CNAME
yönlendirmesi ve insan onaylı tedarikçi bağlantılarını ilk/son gözlem,
gözlem sayısı ve kanıt kimliğiyle gösterir. `--history` tek tek gözlemleri,
boş veya başarısız kontrolleri ve insan kararlarını açar.

İlk ve son gözlem arasında bağlantının kesintisiz sürdüğü varsayılmaz.
Başarısız kontrol ilişkinin ortadan kalktığı anlamına gelmez. Sertifikadaki
adlar sahiplik kanıtı sayılmaz. Eski tedarikçi kararında belirli bir CNAME
kontrolüne bağ dondurulmamışsa sonradan böyle bir bağ uydurulmaz.

Bu komut yeni DNS/TLS/HTTPS kontrolü yapmaz. Kayıtlı kanıt yoksa hangi
bölümün eksik olduğunu gösterir. Yeni kontrol gerektiğinde mevcut yetki
ve kapsam kurallarıyla ilgili kontrol komutu ayrıca çalıştırılır.

## Kapasite ve sınırlar

Sayfa sınırı yalnız gösterimi sınırlar; toplamlar tam incelenen kapsamdan
hesaplanır. Kaynağın veya yerel okuyucunun açık kapasitesi aşılırsa eksik
sonuç başarı gibi sunulmaz; işlem açıklayıcı hatayla durur. Her birleşik
okuma kendi içinde tek SQLite okuma anını kullanır.

Otomatik HTML rapor arşivleme 15 Kasım 2026 kullanıcı kararıyla plandan
çıkarıldı. Mevcut kuruluş HTML dışa aktarımı komutla kullanılabilir.
Bu sürüm web paneli, e-posta gönderimi veya yeni dış kaynak eklemez.
