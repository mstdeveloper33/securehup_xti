# Kuruluş raporu: günlük kullanım

0.136.0 · şema 62. Eski kurulumda önce `./xti migrate` çalıştır; komut
geçişten önce benzersiz geri dönüş yedeği oluşturur.

Raporda kuruluşa ait kamu olay izlemesinin tarihî bölümü de bulunur. Bu
bölüm kesin kuruluş kimliğine aittir; güncel domain bölümlerinden ayrıdır.
Domain bağlantısını kaldırmak eski izleme sonuçlarını silmez. İzleme açmak
için `./xti notices watch enable KURULUS_KIMLIGI` kullan;
[ayrıntılı rehber](PUBLIC_NOTICE_WATCHES.md) ilk sessiz ölçümü ve bildirimleri açıklar.

## 1. Kayıtlarını bir kez grupla

```sh
./xti organizations add "Örnek kuruluş"
./xti organizations list
./xti organizations link KURULUS_KIMLIGI --kind domain --value example.com
./xti organizations link KURULUS_KIMLIGI --kind username-watch --value IZLEME_KIMLIGI
./xti organizations link KURULUS_KIMLIGI --kind ransomware-watch --value IZLEME_KIMLIGI
./xti organizations link KURULUS_KIMLIGI --kind ransomlook-watch --value IZLEME_KIMLIGI
```

Büyük harfli alanları önceki komutların verdiği gerçek kimlikle değiştir;
kullanmadığın izleme satırlarını atla. Domain ve izlemeler önceden kayıtlı
olmalı. Gruplama veri toplamaz; sahiplik veya ihlal doğrulaması değildir.
Toplama için mevcut `collect`/profil komutlarını kullanmaya devam edersin.

## 2. Birleşik sonucu aç

```sh
./xti organizations report KURULUS_KIMLIGI
./xti --json organizations report KURULUS_KIMLIGI
```

| Bölüm | Göreceğin bilgi |
| --- | --- |
| Domain | Gerçek bulgu adresleri, inceleme durumu, pasif alt alan adayları |
| Dış yüzey | Saklanmış DNS/TLS/web/posta/servis/CNAME değerleri ve kontrol zamanı |
| Sosyal izleme | Seçilen kullanıcı adı, platformlar, profil adresleri ve mevcut insan kararı |
| Ransomware | ThreatCluster ve RansomLook kayıtları; kaynak ve izleme kimlikleri ayrı |
| Kamu ihlal kataloğu | HIBP'nin domain alanıyla birebir eşleşen olay metaverisi |
| Kaynak durumu | Son deneme, son başarılı kayıt, hata ve eski/eksik veri ayrımı |
| İnceleme | İlgili mevcut bildirim ve vaka kimliklerine geçiş komutları |

Rapor internete çıkmaz ve yeni veri üretmez. Başarısız son deneme önceki
başarılı veriyi güncel başarıya dönüştürmez. İzleme tanımı değiştiyse eski
tanımın sonucu yeni sorgunun sonucu gibi sunulmaz. Kaynak yenilemesi ile
izleme çalışması ayrı gösterilir. Varsayılan güncellik eşiği 24 saattir;
`--stale-after-hours` yalnız raporun yaş değerlendirmesini değiştirir.

Yalnız **şu an etkin** kuruluş, bağlantı ve hedefler kapsamı oluşturur.
`organizations show` geri çekilmiş bağlantıları ve geçmişi de açar. Bu
kişisel gruplamadır; takım/müşteri erişim yetkilendirmesi sağlamaz. Bir vaka
birden fazla gruba ait kanıt içeriyorsa rapor yalnız eşleşen bağlantının
vaka kimliği/durumunu gösterir; diğer kanıtları rapora kopyalamaz.

Çok kayıt varsa sayfala:

```sh
./xti organizations report KURULUS_KIMLIGI --target-offset 50 --target-limit 50
./xti organizations report KURULUS_KIMLIGI --item-offset 50 --item-limit 50
```

Hedef sayfası ve bölüm içi sayfa bağımsızdır. Görünüm sınırı toplam sayıları
değiştirmez; sonraki sayfa çıktıda belirtilir. Ağ/işleme güvenlik sınırları
gösterim sayfasından ayrıdır; bütünlük denetimi sınırı aşılırsa komut bunu
açık hata olarak bildirir, eksik toplamı tam sonuç gibi sunmaz.

## 3. Son günün veya haftanın farklarını incele

```sh
./xti changes --organization KURULUS_KIMLIGI --days 1
./xti changes --organization KURULUS_KIMLIGI --days 7
./xti changes --organization KURULUS_KIMLIGI --days 7 --offset 100 --limit 100
```

Pencere son 24 veya 168 saatin **yerel kayıt zamanı** üzerindedir. Kaynağın
olay/gözlem tarihi ayrıca korunur. Her bölümde ilk ölçüm, gerçek değişim ve
hata ayrı listelenir. Gösterim sınırı her kategori ve kapsama listesine ayrı
uygulanır; aile toplamları benzersiz tehdit toplamı olarak toplanmaz.

DNS adresi, sertifika, HTTPS, posta, port veya CNAME değeri gerçekten
değiştiyse kayıtlı önce/sonra değerlerini ve iki kanıtın kimliğini görürsün.
Sorgu hatası “adres silindi” gibi yorumlanmaz. Başarılı DNS kaydı yokluğu
ile DNS isteğinin başarısız olması ayrıdır. Eski kontrol geçmişi komutu son
100 kaydı açar; dönem raporundaki eski kayıt kimliği ve değerler ayrıca
saklanır, bu komut sınırsız geçmiş erişimi gibi sunulmaz.

Kuruluş filtresi geçmişi güncel etkin üyelikle süzer; geçmiş tarihteki
sahipliği kanıtlamaz. Karma toplama oturumunda yalnız ilgili kaynak/izleme
adımları gösterilir. HIBP bütün kuruluşlarca kullanılan ortak katalogdur;
kaynak hatası tek ortak satırdır, seçilen domainin olayı sayılmaz.

## 4. Kaynakların katkısını karşılaştır

```sh
./xti sources contribution --organization KURULUS_KIMLIGI
./xti sources contribution --organization KURULUS_KIMLIGI --offset 20 --limit 20
./xti sources contribution --organization KURULUS_KIMLIGI --detail-offset 50 --detail-limit 50
```

Her domain, kaynak ve arama kuralı ayrı kalır. Ortak/farklı gerçek adresleri,
kanıtları ve tamamlanan denemelerin pay/paydasını görürsün. Domain sayfası
ile kanıt sayfası bağımsızdır. Sonuç kaynak doğruluğu veya bütün internet
kapsama yüzdesi değildir; geçmiş yoksa karşılaştırma yetersiz görünür.
HIBP olay kataloğu bu domain keşif karşılaştırmasına karıştırılmaz.

## 5. Ücretsiz kamu olaylarını araştır

```sh
./xti notices refresh
./xti notices status
./xti notices search --domain example.com
./xti notices search "kuruluş adı" --offset 0 --limit 20
./xti notices show OLAY_ADI_KIMLIGI
./xti notices run-show CALISMA_KIMLIGI --offset 20 --limit 20
```

Bu `notices` komutları içinde yalnız `refresh` internetten tek kamu kataloğunu alır. `--limit` indirme
kapsamını kısmaz; gösterilen değişim sayısını belirler. API anahtarı veya
ücretli hesap aranmaz. `search` ve diğer görünümler yereldir; sınırsız ve
kesintisiz dış servis erişimi taahhüt edilmez. Geçmişteki tüm olayları ilk
alımda “bugün gerçekleşen ihlaller” diye işaretlemeyiz; ilk alım tabandır.

Kaynak: [Have I Been Pwned](https://haveibeenpwned.com),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Kaynağın doğrulanmış/uydurma/spam/hassas/geri çekilmiş/malware/stealer-log
işaretleri korunur. Bunlar XTI'nin verdiği kararlar değildir. E-posta,
parola, oturum bilgisi veya ham sızıntı içeriği alınmaz. Olayın veri kategori
adlarının gösterilmesi, içeriğinin indirildiği anlamına gelmez.

Hata son başarılı kataloğu korur; hata ve kullanılan eski çalışma kimliği
görünür. Kaynaktan çıkarılan kayıt çözülmüş olay sayılmaz. `show` güncel
kataloğu, `run-show` seçilen çalışmanın başlangıç/değişim/hata kanıtını açar;
çıkarılmış eski olay da orada okunur. Kuruluş raporuna yalnız tam domain
eşleşmeleri girer; isim araması araştırma adayıdır.

0.135.0 ile `collect example.com --task notices-hibp` aynı yenilemeyi
kayıtlı toplama oturumuna bağlar. Profilin tam `--task` seçimine bu işi
ekleyebilir, mevcut Linux zamanlayıcısıyla çalıştırabilirsin. Başarılı kaynak
kaydı ile tamamlanma bağı aynı işlemde saklanır; kesintide başarılı kayıt
korunur. `--plan`, profil kaydetme ve zamanlama hazırlığı kaynak sorgulamaz.
HIBP ortak katalogdur; seçili domainin hedefte sorgulandığı anlamına gelmez.
0.136.0'da bildirim için ayrıca `notices watch enable KURULUS_KIMLIGI`
seçilebilir; açık izlemeler bu ortak yenilemede değerlendirilir. Kamu olayı
vaka kanıtı ve HTML rapor ayrı gelecek işlerdir.

## 6. Bir göstergenin kayıtlı CTI ilişkilerini aç

```sh
./xti cti context --type domain --value example.com
./xti cti context --type ip --value 192.0.2.15
./xti cti context --entity CTI_VARLIK_KIMLIGI
./xti cti context --entity CTI_VARLIK_KIMLIGI --all --offset 50 --limit 50
./xti cti context --entity CTI_VARLIK_KIMLIGI --source-offset 20 --source-limit 20
```

Tam IOC veya açık varlık kimliği seçilir. Bir adım uzaklıktaki kayıtlı
ilişkiler ve her kaynak iddiası ayrı gösterilir; komuttaki sonraki varlık
kimliğiyle devam edebilirsin. İlişki ve kaynak sayfaları ayrıdır. Varsayılan
etkin ilişkiler; `--all` geri çekilmişleri de gösterir. IOC geçerlilik zamanı
ile ilişki iddiasının etkinliği ayrı kavramlardır. Kaynak güven puanı ürünün
verdiği risk puanı değildir. Geçmiş ve güncel satır uyuşmazsa komut durur.

Bu görünüm yeni aktör atfı veya dolaylı ilişki çıkarmaz. ATT&CK teknik/taktik
kataloğu kendi `cti attack-search/show` komutlarıyla araştırılır. Kayıt
bulunmaması “temiz” sonucu değildir.
