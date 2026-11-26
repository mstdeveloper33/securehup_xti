# XTI ekip teslim rehberi

**Sürüm 0.195.1 · çekirdek şema 101.** Bu rehber, yeni ekip üyesinin repoyu
klonlayıp hangi bölümlerin çalıştığını tek akışta doğrulaması içindir. Dış API
anahtarlarını peşinen istemez.

## 1. Temiz klonda ilk kabul

```sh
git clone https://github.com/mstdeveloper33/securehup_xti.git
cd securehup_xti
./handoff --plan
./setup
./handoff --profile full
```

`--plan` ağ isteği veya veri değişikliği yapmadan teslim dosyalarını ve dış
gereksinimleri gösterir. `./setup` normal araçları kurup yeni veri alanını
hazırlar. Son komut şunları birlikte doğrular:

- repo, Python, özellik kataloğu ve 59 kaynak manifesti;
- sabitlenmiş Maigret, Sherlock, Betterleaks, haber, PDF ve kanal paketleri;
- seçilen veri alanının şeması ve bütünlüğü;
- kullanıcı verisinden ayrı geçici alanda kurulum, örnek kayıt, yedek, boş
  alana geri dönüş ve geri dönen kaydı okuma;
- yerel marka koruma araçları;
- isteğe bağlı hesap, yetki ve dış altyapıların ayrı durumu.

RDAP ve `security.txt` abuse iletişim kaynakları anahtarsızdır. Yerel WHOIS
yalnız RDAP iletişim vermediğinde kullanılan isteğe bağlı fallback'tir;
`./xti action contact-capabilities` kurulum durumunu gösterir ve eksik olması
temel teslimi bozmaz.

XposedOrNot yeni kullanımda kapalıdır. Handoff bu kaynak için anahtar aramaz;
eski maskeli kayıtların okunması yeni ağ erişimi gerektirmez.

Teslim kontrolü canlı kaynak sorgusu, ücretli çağrı, Nmap taraması veya dış
sisteme yazma yapmaz. Geçici kabul alanı işlem bitince silinir. Seçilen
`.xti-data` yalnız `doctor` ile okunur.

## 2. Sonuç nasıl okunur?

| Sonuç | Anlamı | Ne yapılır? |
|---|---|---|
| `PASS` | Seçilen profil bu makinede kabulden geçti. | Günlük kullanım başlayabilir. |
| `GEREKSİNİM BEKLİYOR` | Kod bozuk değildir; eski şema, eksik anahtar, araç, yetkili hedef veya dış altyapı vardır. | Çıktıdaki tek çözüm adımını uygula ve yeniden çalıştır. |
| `UYGULANMADI` | Özellik bilinçli olarak kapalı, ertelenmiş veya henüz ürün kapsamına alınmamıştır. | Yol haritası/ürün kararı olmadan etkin sayma. |
| `FAIL` | Zorunlu dosya, sözleşme, kurulum veya geçici kabul gerçekten başarısızdır. | Çıktıyı koru; düzeltmeden teslimi onaylama. |

Çıkış kodları sırasıyla `0`, `3`, `4` ve `1` değerleridir. İsteğe bağlı bir
anahtarın eksikliği tek başına genel sonucu başarısız yapmaz.

## 3. Eski veriyle yükseltme

`./handoff` mevcut veri alanını sessizce değiştirmez. Şema eskiyse:

```sh
./xti migrate
./handoff --profile full
```

`migrate` önce doğrulanmış kurtarma yedeği alır. Yedek başarısızsa geçiş
uygulanmaz. Veri alanını elle silmek veya yeni boş veritabanıyla değiştirmek
teslim yöntemi değildir.

## 4. Hafif ve ayrıntılı kullanımlar

Yalnız Python çekirdeği bilerek kurulduysa:

```sh
./setup --core-only
./handoff --profile core
```

Normal ekip teslim standardı `full` profildir. Günlük hızlı tekrar için
geçici smoke zincirini atlamak mümkündür:

```sh
./handoff --profile full --no-smoke
```

Bu kısa kontrol tam teslim kanıtı değildir. Bütün koşullu kaynakları görmek
için `--details` kullanılır.

## 5. Makinece okunabilir kanıt

```sh
./handoff --profile full --json
./handoff --profile full --output handoff-report.json
```

Dosya biçimi `xti-team-handoff`, sözleşme sürümü `1`'dir. Rapor yeni dosyaya
`0600` izniyle yazılır; mevcut dosyanın üzerine yazılmaz. Anahtar değeri,
cookie, kullanıcı oturumu veya toplanmış müşteri kanıtı rapora eklenmez.

## 6. İsteğe bağlı kaynağı açma

Örneğin firma içerik araması gerekiyorsa ekip üyesi Tavily anahtarını
sohbete yazmadan çalıştırır:

```sh
./xti mentions configure
./handoff --profile full --no-smoke
```

Yeni sonuç yalnız “yapılandırma mevcut” demektir. Canlı hesap, kota ve gerçek
arama kabulü ilgili özellik rehberindeki kontrollü senaryoyla ayrıca yapılır.
Diğer hesaplar ve komutlar [gereksinim tablosundadır](../REQUIREMENTS.md).

## 7. Teslimi kapatma ölçütü

Bir sürüm ancak aşağıdakiler kanıtlandığında ekip teslimine hazır denir:

1. Temiz desteklenen Linux klonunda `./setup` başarılıdır.
2. `./handoff --profile full` zorunlu kontrolleri geçirir.
3. Eski veri için yedekli `migrate` ve tekrar kabul geçer.
4. `./scripts/check` sürümün tam repo kapısını geçirir.
5. En az bir eksik ve bir yapılandırılmış isteğe bağlı kaynak durumu sır
   sızdırmadan doğrulanır.
6. `FEATURE_CATALOG.md`, `NOTES.md`, `docs/STATUS.md` ve bu rehber aynı sürümü
   anlatır.

Mevcut 0.195.0 yerel kabul sonucu [durum kaydında](STATUS.md), açık kapılar
ise [N-057 notunda](../NOTES.md) tutulur.
