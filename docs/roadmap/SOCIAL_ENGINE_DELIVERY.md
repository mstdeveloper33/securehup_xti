# Sosyal kanıt ve işletim paketi — çalışma kaydı

20 Kasım 2026. Kullanıcı altı işi birlikte onayladı. Başlangıç:
0.174.0 / `dbaf235`, çekirdek 84. Bu dosya plan ile ölçülen sonucu ayırır.
Kapanış: **0.175.0 / çekirdek85 / kuyruk3; altı iş tamamlandı.**
Test edilen son motor kodu `ab080a7`; kapanış güncellemesi yalnız belgedir.

| İş | Uygulama sınırı | Kabul ölçütü | Durum |
| --- | --- | --- | --- |
| Ortak araştırma | Birleşik sosyal keşif, özgün kaynak, insan kararı ve vaka bağı | Domain/URL araştırması, geçmiş inceleme, firma ayrımı ve eski kayıt uyumu | Uygulandı; hedefli kabul geçti |
| Kaynak karşılaştırması | Aynı kayıt ve aynı anlamdaki kanıt; zaman/kapsam farkı ve erişim hatası ayrı | Kaynak yokluğu hesap silinmesi veya güvenli IOC sayılmaz; özgün kayıt açılır | Uygulandı; hedefli kabul geçti |
| Kayıtlı profil | Yeni sosyal izleme kimliğini mevcut toplama ve kurtarma akışına ekleme | Ağsız plan, aynı domain/firma, değişen/pasif izleme reddi, kesintide tekrar güvenliği | Uygulandı; gerçek süreç kesintisi geçti |
| Doğruluk ölçümü | Sabit ve etiketli olumlu/olumsuz/belirsiz örnekler | Kaçırma, yanlış bulma ve belirsizlik ayrı; ölçüm tekrar üretilebilir | 35/35 kontrollü örnek geçti |
| Geçmiş saklama | Mevcut kayıpsız arşive eski sosyal keşif gövdelerini katma | Kimlik/hash/karar/iş tekrarı korunur; önizleme, yedek, geri alma, boyut sınırları | Uygulandı; hedefli kabul geçti |
| Linux kabulü | Son kodun kurulum/yükseltme, iki firma, kesinti ve geri dönüş kontrolü | Gerçek koşu ve commit kaydı; yerel/fixture/Linux sonuçları ayrı | Tam ve kısa paket dahil geçti |

Bright Data canlı kabulü anahtar, gelişmiş Nmap canlı kabulü kesin yetkili
IP/port kapsamı bekler. Bu girdiler olmadan yapılmış sayılmaz. Ücretli
çağrı, LLM, Firecrawl, geniş STIX/TAXII ve tüketici .NET/UI kapsamı açılmaz.

Değişikliklerde ilgili testler; paket kapanışında genel kontrol yapılır.
Şema85 geçişi açık ve yedeklidir; eski kayıtlar yeniden yorumlanarak yazılmaz.

## Ölçülen yerel sonuçlar

- macOS / Python 3.13.3; 45 sosyal özellik testi 16,553 sn, 34 son teslim testi
  35,552 sn geçti. İkinci paket ortak mimari, gerçek collection runner,
  migration rollback ve CI yapılandırmasını da doğrular; sayılar örtüşür.
- Gerçek eski 0.174.0 / `dbaf235` ile iki şema 84 veri alanı üretildi.
  `scripts/check-social-upgrade.py` SQLite yardımcı tablosu dahil 172'şer
  tablonun 13/23 fixture satırını, özgün rowid'leri ve üç eski toplama
  makbuzunu 85'e taşıdı. Eski motor
  yeni şemayı reddetti; iki eski yedeği yeni alana geri açtı. 4,210 sn.
- `scripts/check-social-quality.py`: 8 found, 6 not_found, 21 inconclusive
  etiketi; 35/35 beklenen karar, 0 yanlış varlık/yokluk, 0 beklenen profili
  kaçırma. SHA256: `78ff1479b0267f554d6c46e4fd5603061fba37bf9c39cdf3773b980002ddc1d5`.
  Sentetik sayfalardır; canlı keşif ya da marka sahipliği doğruluk oranı değildir.
- Son araştırma paketi **99 test / 50,786 sn** geçti. Geçmişte bulunan bir
  hesabın son sayfası 404 olduğunda, kaynak artık bağlantı vermese bile
  bu son gözlemin araştırmada korunması ayrıca doğrulandı. Sayfa yokluğu
  bütün hesabın kalıcı silinmesi veya marka sahipliği kararı sayılmaz.
- İlk genel yerel koşu **3.361 test / 1.662,945 sn**: 3.342 başarılı,
  15 eski şema beklentisi hatası, 4 Linux/macOS atlaması. Bu koşu başarılı
  sayılmaz. Bir test güncel otomatik indeksi beklemiyordu; diğer 14 test
  aynı eski toplama şeması karşılaştırıcısını kullanıyordu. İki test
  yardımcısı şema85'in kesin biçimini ve yeni nullable alanı denetleyecek
  şekilde güncellendi; eski verinin karşılaştırılması gevşetilmedi.
  Genel süreç bu yardımcıların eski kopyasıyla başlamıştı. Son kodla
  etkilenen sekiz modülün tamamı **44 test / 31,615 sn** ile hatasız geçti.
  Yerel genel koşu tekrarlanmadı; son kodun temiz tam koşusu Linux'tadır.

## Linux teslim kanıtı

`ed2b04b` üzerinde [sosyal motor kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44697161402)
Ubuntu 24.04 / Python 3.11 ve 3.13 ile geçti: gerçek süreç kesintisi,
35 etiketli örnek, şema 84 → 85 yükseltme ve eski motorla yedekten dönüş.
Son araştırma düzeltmesini içeren `ab080a7` üzerinde
[Python 3.11/3.13 sosyal kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44697471642)
ve [iki firma izolasyonu/süreç kurtarma](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44697471531)
tekrar başarılı tamamlandı.

Kurulum/işletim kodu aynı olan `ed2b04b` üzerinde
[Linux kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44697161381),
[marka araçları kurulumu](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44697161343)
ve [gerçek yükseltme/işletim](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44697161293)
geçti. Son akışta marka ve theHarvester ortamlarının yükseltilmesi,
kesilmiş kurulumun kurtarılması, kaynak kesintileri, 100/1.000/5.000
domain kapasitesi, düşük disk, gerçek systemd ve 600 saniyelik dayanıklılık
senaryosu başarıyla çalıştı. Bu kontrollü kabul 7/24 hizmet garantisi değildir.

`ab080a7` [kısa Linux paketi](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44697471561)
başarılı tamamlandı (Python 3.11; iş süresi 24 dk 32 sn).
[Tam Linux testi](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44697471676)
de başarılı tamamlandı (Python 3.13; iş süresi 27 dk 36 sn;
07:47:02–08:14:38 UTC). Son kodun otomatik test envanteri 3.364'tür.
Önceki commit'in bu iki koşusu yeni gönderimle iptal edildi;
iptal, test başarısı veya test hatası olarak sayılmaz.

## Tekrar üretme

```sh
./scripts/python scripts/check-social-quality.py --output /tmp/social-quality.json
./scripts/python scripts/check-social-upgrade.py --output /tmp/social-upgrade.json
./scripts/python -m unittest tests.test_social_engine_package tests.test_collection_social_migration
```

Çıktı dosyaları yeni olmalıdır; mevcut raporun üstüne yazılmaz. GitHub'da
`XTI social engine delivery` Python 3.11/3.13 ile aynı akışı çalıştırır.
`XTI full checks and release` tam testi, `XTI stabilization acceptance`
gerçek kurulum/yükseltme ve işletim kontrolünü sürüm değişiminde başlatır.
Platform iki-firma/süreç kurtarma kontrolü ayrıca çalışmaya devam eder.

Kapanış commit'i yalnız belgeyi günceller ve `[skip ci]` taşır. Yukarıdaki
doğrulanmış motor kodu aynıdır; belge değişikliği için genel paket tekrarlanmadı.
