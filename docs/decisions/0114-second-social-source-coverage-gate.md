# 0114 — İkinci ücretsiz sosyal kaynak kapsam kapısı

**Tarih:** 31 Ekim 2026  
**Durum:** Kabul edildi  
**Sürüm:** 0.116.0

## Bağlam

İlk araç kapısı Maigret'i seçmiş, Sherlock'u aynı platformları yeniden
sorgulayabileceği ve sonuç JSON'u sunmadığı için ertelemişti. Kalıcı sosyal
izleme tamamlandıktan sonra ikinci kaynağın yalnız araç adına bakılarak tekrar
sayılması yeterli değildir. Gerçek katalog katkısı, gizli ağ isteği olmadan ve
aynı site farklı adla yazıldığında yanlış özgünlük üretmeden ölçülmelidir.

## Karar

`brand source-coverage`, paketli ve SHA-256 sabitli
`free-social-source-coverage-gate-v1` kanıtını ağsız gösterir. Birincil kaynak
Maigret 0.6.6 / `b8747b9…`, aday kaynak Sherlock 0.16.2 /
`a38ba54…` tam commit'idir. Kataloglar canlı çalışma sırasında indirilmez.

Karşılaştırmaya yalnız etkin, HTTPS kullanan doğrudan kullanıcı adı profilleri
girer. Maigret'te devre dışı, `similarSearch`, ayna/kaynak bağlı ve kullanıcı
adı dışı kayıtlar; Sherlock'ta NSFW ve HTTPS olmayan kayıtlar elenir. Aynı
normalleştirilmiş platform adı veya paketli Public Suffix List'e göre aynı kayıt
kökü ortak sayılır.

Maigret'in 8.517 katalog kaydından 6.628'i, Sherlock'un 481 kaydından 455'i bu
filtreyi geçmiştir. Sherlock tarafında 352 tanım ortak, 103 tanım eşleşmeyendir;
eşleşmeyenler 102 host ve 101 kayıt kökü oluşturur. Mevcut izinli 10 platformda
9 ortak platform vardır; Facebook yalnız Maigret'tedir ve Sherlock'a özgü
mevcut platform yoktur.

Sherlock bu nedenle mevcut 10 platformu çoğaltmak için değil, ölçülen bağımsız
genişleme için sınırlı adaptör adayı olarak kabul edilmiştir. İlk kısa liste
Carrd, CashApp, CodeSandbox, GitBook, ResearchGate, Rumble, Strava ve
Weebly'dir. Bu kabul canlı doğruluk onayı değildir. Sonraki adaptör sabit
upstream sürümü, `--local`, açık `--site`, süre sınırı ve tam CSV başlık/satır
sözleşmesi kullanmalıdır. Canlı exclusion listesi indirilmeyeceği için geniş
katalog taraması yapılmayacaktır.

## Güvenlik ve veri sınırı

- Kapı Sherlock veya Maigret çalıştırmaz ve kullanıcı adı sorgulamaz.
- Profil veritabanı açılmaz; komut veri klasörü oluşturmaz.
- Sherlock kodu ve katalog verisi XTI deposuna kopyalanmaz; yalnız sürüm,
  commit, özet ve türetilmiş sayaçlar tutulur.
- Aynı kullanıcı adı aynı marka, sahiplik veya taklit hükmü değildir.
- Otomatik karar, bildirim, webhook, takedown veya arka plan işi oluşmaz.
- Şema 49 değişmez.

## Doğrulama

Paketli profil özeti, yinelenen JSON alanı, tam alan kümeleri, HTTPS başvurusu,
kaynak rolleri, katalog/uygun/ortak/özgün sayaç bağları, zorunlu ölçütler ve
tekil kısa liste güvenli biçimde doğrulanır. Terminal ve JSON görünümleri
olmayan bir veri klasörünü oluşturmaz. Otomatik testler üçüncü taraf araç veya
internet kullanmaz.

Tam kontrolde 1.280 test 228,006 saniyede geçmiştir. Ayrı upstream kabulünde
Sherlock v0.16.2 etiketi tam commit'e çözümlenmiş; resmî 104.039 baytlık katalog
beklenen SHA-256 özetiyle yalnız geçici alanda doğrulanmıştır. Ağsız terminal ve
JSON komutları kayıtlı sayaçları üretmiş, kullanıcının ana veritabanı
değiştirilmemiştir.
