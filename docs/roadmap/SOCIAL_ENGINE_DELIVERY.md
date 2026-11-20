# Sosyal kanıt ve işletim paketi — çalışma kaydı

20 Kasım 2026. Kullanıcı altı işi birlikte onayladı. Başlangıç:
0.174.0 / `dbaf235`, çekirdek 84. Bu dosya plan ile ölçülen sonucu ayırır.

| İş | Uygulama sınırı | Kabul ölçütü | Durum |
| --- | --- | --- | --- |
| Ortak araştırma | Birleşik sosyal keşif, özgün kaynak, insan kararı ve vaka bağı | Domain/URL araştırması, geçmiş inceleme, firma ayrımı ve eski kayıt uyumu | Uygulandı; hedefli kabul geçti |
| Kaynak karşılaştırması | Aynı kayıt ve aynı anlamdaki kanıt; zaman/kapsam farkı ve erişim hatası ayrı | Kaynak yokluğu hesap silinmesi veya güvenli IOC sayılmaz; özgün kayıt açılır | Uygulandı; hedefli kabul geçti |
| Kayıtlı profil | Yeni sosyal izleme kimliğini mevcut toplama ve kurtarma akışına ekleme | Ağsız plan, aynı domain/firma, değişen/pasif izleme reddi, kesintide tekrar güvenliği | Uygulandı; gerçek süreç kesintisi geçti |
| Doğruluk ölçümü | Sabit ve etiketli olumlu/olumsuz/belirsiz örnekler | Kaçırma, yanlış bulma ve belirsizlik ayrı; ölçüm tekrar üretilebilir | 35/35 kontrollü örnek geçti |
| Geçmiş saklama | Mevcut kayıpsız arşive eski sosyal keşif gövdelerini katma | Kimlik/hash/karar/iş tekrarı korunur; önizleme, yedek, geri alma, boyut sınırları | Uygulandı; hedefli kabul geçti |
| Linux kabulü | Son kodun kurulum/yükseltme, iki firma, kesinti ve geri dönüş kontrolü | Gerçek koşu ve commit kaydı; yerel/fixture/Linux sonuçları ayrı | Otomatik akış hazır; koşu bekleniyor |

Bright Data canlı kabulü anahtar, gelişmiş Nmap canlı kabulü kesin yetkili
IP/port kapsamı bekler. Bu girdiler olmadan yapılmış sayılmaz. Ücretli
çağrı, LLM, Firecrawl, geniş STIX/TAXII ve tüketici .NET/UI kapsamı açılmaz.

Değişikliklerde ilgili testler; paket kapanışında genel kontrol yapılır.
Yeni veri anlamı gerektiren geçiş açık ve yedekli olacak; eski kayıtlar
yeniden yorumlanarak yazılmayacak.

## Ölçülen yerel sonuçlar

- macOS/Python3.13.3;45 sosyal özellik testi16,553sn,34 son teslim testi
  35,552sn geçti. İkinci paket ortak mimari, gerçek collection runner,
  migration rollback ve CI yapılandırmasını da doğrular; sayılar örtüşür.
- Gerçek eski0.174.0/`dbaf235` ile iki şema84 veri alanı üretildi.
  `scripts/check-social-upgrade.py`172'şer tablonun13/23 fixture satırını,
  özgün rowid'leri ve üç eski toplama makbuzunu85'e taşıdı. Eski motor
  yeni şemayı reddetti; iki eski yedeği yeni alana geri açtı.4,210sn.
- `scripts/check-social-quality.py`:8 found,6 not_found,21 inconclusive
  etiketi;35/35 beklenen karar,0 yanlış varlık/yokluk,0 beklenen profili
  kaçırma. SHA256:`78ff1479b0267f554d6c46e4fd5603061fba37bf9c39cdf3773b980002ddc1d5`.
  Sentetik sayfalardır; canlı keşif ya da marka sahipliği doğruluk oranı değildir.
- Son araştırma paketi **99 test / 50,786 sn** geçti. Geçmişte bulunan bir
  hesabın son sayfası404 olduğunda, kaynak artık bağlantı vermese bile
  bu son gözlemin araştırmada korunması ayrıca doğrulandı. Sayfa yokluğu
  bütün hesabın kalıcı silinmesi veya marka sahipliği kararı sayılmaz.
- Son tam yerel koşu sürüyor. Genel/Linux sonuçları kapanışta eklenecek.

## İlk Linux teslim kanıtı

`ed2b04b` üzerinde [sosyal motor kabulü](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44697161402)
Ubuntu24.04/Python3.11 ve3.13 ile geçti: gerçek süreç kesintisi,
35 etiketli örnek, şema84 → 85 yükseltme ve eski motorla yedekten dönüş.
Son araştırma düzeltmesi için yeni koşu başlatılacak; ilk commit'in
başarısı sonraki kodun kabulü gibi gösterilmez.

## Tekrar üretme

```sh
./scripts/python scripts/check-social-quality.py --output /tmp/social-quality.json
./scripts/python scripts/check-social-upgrade.py --output /tmp/social-upgrade.json
./scripts/python -m unittest tests.test_social_engine_package tests.test_collection_social_migration
```

Çıktı dosyaları yeni olmalıdır; mevcut raporun üstüne yazılmaz. GitHub'da
`XTI social engine delivery` Python3.11/3.13 ile aynı akışı çalıştırır.
`XTI full checks and release` tam testi, `XTI stabilization acceptance`
gerçek kurulum/yükseltme ve işletim kontrolünü sürüm değişiminde başlatır.
Platform iki-firma/süreç kurtarma kontrolü ayrıca çalışmaya devam eder.
