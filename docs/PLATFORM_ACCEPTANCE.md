# Çok firmalı motor kabulü — 0.147.0

16 Kasım 2026. Çekirdek şema 69; ayrı platform iş veritabanı şema 1.
Bu kayıt [platform sözleşmesinin](PLATFORM_ENGINE.md) doğrulama kapsamıdır.
.NET uygulaması, gerçek müşteri ortamı ve kesintisiz hizmet kabulü değildir.

## Gerçek süreçlerle yerel kabul

`scripts/check-platform-acceptance.py`, iki geçici firma alanını gerçek
CLI süreçleriyle oluşturur. Her firmada önce 100, sonra 1.000 örnek varlık
bulunur. Arama, firma içeriği ve iş durumu için toplam 36 okuma yapılır.
Kaynak çağrısı yerine kontrollü yerel yanıt kullanılır; internete çıkılmaz.

Son çalıştırma ortamı: macOS 26.6.2 / arm64, Python 3.13.3, SQLite 3.53.2,
10 mantıksal CPU. Aynı makinede genel testler de çalışıyordu. Süreler
süreç başlatma ve yanıt okuma dahil duvar saati ölçümüdür.

| Ölçüt | Çalışmadan önce belirlenen sınır | Ölçülen sonuç |
|---|---:|---:|
| Toplam kabul süresi | 120 saniye | 38,516 saniye |
| Okuma isteklerinin %95'i | 5 saniye | 0,545 saniye |
| En yavaş okuma | Komut başına 15 saniye | 0,586 saniye |
| En yüksek alt süreç belleği | 536.870.912 bayt | 68.009.984 bayt |
| Geçici veri alanlarının toplam diski | 134.217.728 bayt | 5.046.819 bayt |

Her iki firmanın çekirdek ve iş kayıtlarının SQLite bütünlük kontrolü
geçti. Salt okuma turları kayıt dosyalarını değiştirmedi.

## Kesinti ve eşzamanlılık

İşçi gerçek `SIGTERM` ile iki ayrı noktada durduruldu:

| Durma noktası | Kaynak çağrısı | Korunan kaynak makbuzu | Kurtarma ve tekrar istek |
|---|---:|---:|---|
| Kaynak çağrısından önce | 0 | 0 | Aynı kesilmiş iş; yeni çağrı yok |
| Kaynak makbuzu kaydedildikten sonra | 1 | 1 | Aynı kesilmiş iş; ikinci çağrı yok |

Her senaryoda aynı firmanın ikinci işçisi ve canlı işçiye kurtarma
girişimi `busy` döndü. Diğer firmanın işçisi kendi örnek toplamasını
tamamladı. Böylece tek firma kilidinin diğer firmanın çalışmasını
engellemediği de denendi.

Bu sonuç, başarısı belirsiz bir dış isteği yeniden deneme garantisi
vermez. Motor böyle bir işi otomatik tekrarlamaz; eldeki kanıtı korur ve
durumu açık bırakır. Sonuç özeti yazılmadan kesilen işin kaynak makbuzları
korunurken kuyruktaki sonuç özeti boş kalabilir.

## Regresyon kapsamı

Yeni testler gerçek geçici veritabanlarıyla şunları doğrular:

- Başka firmanın kayıt, kuruluş ve iş kimliğiyle erişim reddi; aynı UUID
  veya tekrar anahtarının iki firmada bağımsız kalması.
- JSON içinden firma/dosya yolu seçimi reddi; bozuk, eksik, kapalı veya
  izinleri güvensiz alandan kişisel kayıt alanına geri dönüş olmaması.
- Profil sürümü, izleme tanımı veya kaynak planı değişirse eski işin
  kaynak çağırmadan durması; çift işçi ve kaybolan yanıtta tekrar güvenliği.
- Güncel/geçmiş firma içeriklerinin ve tedarikçi ilişkilerinin ayrımı;
  başarılı boş arama, kaynak hatası, eski veya hiç toplanmamış veri.
- Çekirdek ve kuyruk dosyalarının birlikte yedeklenmesi; değiştirilmiş,
  eksik veya başka firmaya ait yedeğin reddi; mevcut verinin üzerine
  yazılmaması; bekleyen işlerin geri yüklemede otomatik çalışmaması.
- Geri yüklenen alanın yeni kimliğiyle eski iş kabul isteklerinin reddi.

Son kodun genel test turu 2.595 testi 1.009,038 saniyede tamamladı:
2.591 başarılı, bu macOS ortamında Linux'a özel dört test atlandı;
hata yok. [Güncel durum kaydı](STATUS.md). Son hedefli
platform/firma/yedek/mimari turunda 58 test 17,589 saniyede geçti.
Komut kısaltmalarında gizli girdinin hata çıktısına taşınmasını önleyen
son düzeltmenin testi ayrıca geçti.

## Linux ve tekrar çalıştırma

[Platform kabul iş akışı](https://github.com/mstdeveloper33/securehup_xti/actions/workflows/platform-acceptance.yml)
aynı betiği Ubuntu 24.04 üzerinde Python 3.11 ve 3.13 ile çalıştırır.
Gerçek sonuç, eşikler ve makine ölçümleri her çalışmanın günlük ve
özetinde bulunur. Bir iş akışının tanımlı olması testinin geçtiği anlamına
gelmez; tüketici ekip kullanacağı commit'in başarılı sonucunu kontrol eder.
[Hızlı regresyonlar](https://github.com/mstdeveloper33/securehup_xti/actions/workflows/check.yml)
ve mevcut temiz kurulum kabulleri ayrıca korunur.

Yerelde mevcut olmayan bir çıktı adıyla çalıştırma:

```sh
./scripts/python scripts/check-platform-acceptance.py --output /private/tmp/xti-platform-acceptance-yeni.json
```

macOS için gerçek `/private/tmp`, Linux için `/tmp` kullanılabilir.
Çıktı repo dışında ve daha önce oluşturulmamış olmalıdır. Testler kullanıcı
kayıtlarını kullanmaz; üretilen JSON sentetik kabul ölçümleridir.

## Açık sınırlar

Tavily anahtarı kullanıcı tercihiyle sonraya bırakıldı; bu kabul canlı
Tavily erişimini veya arama kalitesini doğrulamaz. İlk platform kuyruğu
kayıtlı toplama profillerini destekler; Tavily grupları mevcut bütçeli
akışını kullanır. Tam .NET/PostgreSQL entegrasyonu tüketici ekipte kalır.
Geniş STIX/TAXII ve LLM bu teslimin dışındadır. Bu sınırlı ölçümden
7/24 hizmet, sınırsız kapasite veya tüm dış kaynakların erişilebilirliği
sonucu çıkarılmaz.
