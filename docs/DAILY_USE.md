# XTI günlük kullanım

Bu örneklerde `example.com` yerine izleyeceğin domaini, `markam` yerine marka
kullanıcı adını yaz. Komutları proje klasöründe çalıştır. İlk kez kullanıyorsan
önce `./setup`, ardından şu komut yeterlidir:

```sh
./xti assets add example.com
```

## 1. Kaynakların durumuna bak

```sh
./xti sources status --domain example.com
```

Ekran, hangi aracın kurulu olduğunu ve eldeki kayıtların durumunu gösterir.
Hiç çalıştırılmamış kaynak, hata veren kaynak ve tamamlanmış boş arama ayrı
görünür. Satırdaki sonraki komut, eksik kurulumu veya veri yenilemeyi başlatmak
içindir. Durum ekranını açmak yeni arama başlatmaz.

## 2. Domain için veri topla

```sh
./xti scan example.com
./xti surface discover example.com
```

`scan`, marka adına benzeyen adresleri sertifika ve geçmiş web inceleme
kayıtlarında araştırır. `surface discover` domainin alt alan adı adaylarını
sertifika kayıtlarından toplar. Bu iki komut internet kullanır ve sonuçları
yerel veritabanına kaydeder.

Yazım hatalı adları da aramak istediğinde `./xti scan example.com --typos`
kullanabilirsin. Daha fazla sorgu daha uzun sürebilir. Bir kaynak hata verirse
ekrandaki kısmi sonuç ve hata açıklamasını dikkate al; alınan kanıtlar korunur.

## 3. İstersen ücretsiz tehdit kaynaklarını kullan

### Zararlı IP ve domain listeleri

```sh
./xti ioc sync --source feodo
./xti ioc sync --source certpl
./xti ioc status --source feodo
./xti ioc status --source certpl
./xti analyze example.com
```

`sync` internetteki listeyi yerel kataloğa alır; `status` ve `analyze`
kayıtlı veriyi okur. Feodo IP, CERT Polska domain kayıtları sağlar.
Katalogdaki toplam kayıt sayısı senin domainindeki bulgu sayısı değildir.
Analiz, eldeki domain ve IP kanıtlarını bu kayıtlarla karşılaştırır; IP
kanıtı yoksa IP karşılaştırması için kapsam eksik kalır. Kaynak hatasında
önceki geçerli katalog korunur; hata mesajını ve son başarılı tarihi kontrol et.

### Ransomware iddiaları

Önce iki ayrı kaynağın kayıtlarını al ve güncellemenin tamamlandığını kontrol et:

```sh
./xti ransomware refresh --source threatcluster
./xti ransomware status --source threatcluster
./xti ransomware refresh --source ransomlook
./xti ransomware status --source ransomlook
```

İzlemeleri bir kez oluştur. `Markam` yerine kuruluşunun adını yaz:

```sh
./xti ransomware watch-add "Markam domain" example.com --kind domain --source threatcluster
./xti ransomware watch-add "Markam kuruluş" "Markam" --kind organization --match contains --source ransomlook
```

RansomLook domain bilgisi sağlamaz; yalnız kuruluş adı izlenir. `contains`,
adın kaynak başlığı içinde geçmesini arar ve en az 5 karakter ister.
Benzer adlı başka kuruluşlar da eşleşebilir. Yalnız tam ad eşleşmesini
istiyorsan `--match exact` kullan.

Komutların verdiği kimlikleri aşağıdaki yer tutucuların yerine yaz:

```sh
./xti ransomware watch-run THREATCLUSTER_IZLEME_KIMLIGI --source threatcluster
./xti ransomware watch-show THREATCLUSTER_IZLEME_KIMLIGI --source threatcluster
./xti ransomware watch-run RANSOMLOOK_IZLEME_KIMLIGI --source ransomlook
./xti ransomware watch-show RANSOMLOOK_IZLEME_KIMLIGI --source ransomlook
```

`watch-run` internete çıkmaz; son başarılı yerel kaynak kaydını izleme
ifadenle karşılaştırıp sonucu saklar. `watch-show` bu geçmişi gösterir.
Yenileme başarısızsa önce sorunu incele; eski başarılı kayıt üzerinden
yapılan karşılaştırmayı yeni canlı sonuç olarak değerlendirme.

İlk başarılı kaynak ve izleme çalışmaları karşılaştırma başlangıcıdır;
katalogdaki kayıtlar otomatik olarak sana ait alarm sayılmaz. İki kaynağın
geçmişi ayrıdır. ThreatCluster'ın çıktıdaki zaman penceresi ve RansomLook'un
son yedi günlük kapsamı dışında sonuç çıkarılmaz. Eşleşme bulunmaması bu
sınırlı kapsamda sonuç olmadığını söyler; güvenli olunduğunu kanıtlamaz.
Bulunanlar kaynak iddialarıdır; doğrulanmış ihlal değildir.

## 4. Marka kullanıcı adı izlemesini bir kez oluştur

```sh
./xti brand watch-add "Markam Maigret" markam --site GitHub --site Instagram
./xti brand watch-add "Markam Sherlock" markam --source sherlock --site Carrd --site Rumble
./xti brand watch-list
```

Çıktıdaki izleme kimliklerini kullanarak her izlemeyi çalıştır:

```sh
./xti brand watch-run MAIGRET_IZLEME_KIMLIGI
./xti brand watch-run SHERLOCK_IZLEME_KIMLIGI
```

`MAIGRET_IZLEME_KIMLIGI` ve `SHERLOCK_IZLEME_KIMLIGI` örnek yer tutuculardır;
komuta çıktıda gördüğün gerçek kimliği yaz. Sonraki günlerde aynı izlemeleri
yeniden oluşturman gerekmez. Her kaynak kendi çalışma geçmişini saklar.

İlk başarılı tur karşılaştırma başlangıcıdır. Sonraki tur yeni bulunan,
adresi değişen, değişmeyen veya artık raporlanmayan profilleri gösterir.
“Raporlanmadı” hesabın bulunmadığını ya da silindiğini kanıtlamaz. “Bulundu”
aynı kullanıcı adına ait bir profil işaretidir; resmî hesap veya taklit
olduğuna ilişkin karar ayrıca inceleme gerektirir.

## 5. Sonuçları incele

```sh
./xti sources status --domain example.com
./xti analyze example.com
./xti triage
./xti findings list
./xti findings show BULGU_KIMLIGI
./xti brand watch-show IZLEME_KIMLIGI
./xti inbox
```

Bu komutlar kayıtlı sonuçları okur. `analyze` domainin mevcut kanıtını bir
araya getirir; `triage` incelenecek adayları nedenleriyle sıralar. `findings
show` seçilen adayın kaynaklarını gösterir. Listedeki `BULGU_KIMLIGI` gerçek
bulgu kimliğiyle değiştirilmelidir. Birden çok domain izliyorsan `findings
list` içindeki “İzlenen” alanına bak.

Hiç aday görünmüyorsa kaynak durumunu kontrol et. Başarısız arama ile
tamamlanan aramada eşleşme bulunmaması aynı anlama gelmez.

## 6. Takip edeceğin gerçek adayı vakaya ekle

İncelemeye değer bir domain adayı varsa aşağıdaki akışı kullan. Örnekteki
başlığı, özeti ve gerekçeyi yaptığın incelemeye göre değiştir:

```sh
./xti cases create "Markam aday incelemesi" \
  --summary "Pasif kaynakta görülen benzer adresin incelenmesi" \
  --priority low --reason "Kaynak kanıtını takip etmek için"
./xti cases evidence-add VAKA_KIMLIGI --type finding \
  --evidence-id BULGU_KIMLIGI --reason "İncelenecek adayın kaynak kaydı"
./xti cases task-add VAKA_KIMLIGI "Adayın marka ilişkisini doğrula" \
  --reason "İnceleme tamamlanmadan karar verilmeyecek"
./xti cases report VAKA_KIMLIGI
```

`VAKA_KIMLIGI`, vaka oluşturma komutunun verdiği kimliktir. Vaka açılması
adayın tehdit olarak doğrulandığı anlamına gelmez. Sosyal profil kanıtı
eklemek için önce o tam profil hakkında gerekçeli insan incelemesi gerekir.
Sonuç yoksa örneği tamamlamak için kanıt veya inceleme kararı oluşturma.

## 7. Sonraki gün tekrar et

```sh
./xti sources status --domain example.com
./xti scan example.com
./xti surface discover example.com
./xti brand watch-run MAIGRET_IZLEME_KIMLIGI
./xti brand watch-run SHERLOCK_IZLEME_KIMLIGI
./xti analyze example.com
./xti inbox
./xti cases list
./xti backup
```

Ücretsiz tehdit kaynaklarını da kullanıyorsan 3. bölümdeki `ioc sync` ve
`ransomware refresh` komutlarını tekrarla. Her kaynağın durumunu ayrı kontrol
et; yenilemesi başarılı olan ransomware kaynağı için mevcut izleme
kimliğiyle `watch-run` ve `watch-show` çalıştır. İzlemeleri yeniden oluşturma.
Bu komutlar arka planda otomatik zamanlama başlatmaz; RansomLook izlemesi
de açık yenileme ve çalıştırma ister.

Aynı domain kanıtı yeniden geldiğinde mevcut aday ve karar geçmişi korunur.
Sosyal izleme son başarılı ölçümle karşılaştırılır; kaynak hatası önceki
profilleri silmez. Vaka kanıtı eklendiği andaki görünümü saklar. Kaynak
gerçekten değiştiyse inceleyip aynı `cases evidence-add` komutuyla vakadaki
görünümü yenileyebilirsin; önceki vaka hareketleri korunur.

Bu rutin komutları çalıştırdığın zaman işler. Yerel veriler `.xti-data`
klasöründedir; GitHub'a gönderilmez. Yedeği ayrıca başka bir diskte sakla.
