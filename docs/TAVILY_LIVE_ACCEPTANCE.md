# Tavily — SecureHup canlı kullanım kabulü

## 25 Kasım 2026 — 0.194.0 ekip teslim anahtarı kabulü

Kullanıcının açık onayıyla Tavily anahtarı komut argümanına, repoya veya
veritabanına konmadan `./xti mentions configure` gizli terminal girişiyle
`~/.config/xti/tavily.key` dosyasına kaydedildi. Dosya `0600` izinlidir;
değeri hiçbir durum, handoff veya kabul çıktısında gösterilmedi. `./handoff`
Tavily gereksinimini `PASS` olarak gördü.

İlk kabul, mevcut eski şemalı `.xti-data` değiştirilmeden güncel şemalı ayrı
geçici alanda yapıldı. `SecureHup` ve `securehup.com` için `general`,
`max_results=5` kapsamındaki tek sağlayıcı isteği **1 kredi** bildirdi ve
çalışma `complete` oldu. Beş kayıt saklandı ve ağsız `mentions list` ile
tekrar okundu.

Ardından kullanıcının açık onayıyla kalıcı `.xti-data` için yedekli geçiş
yapıldı. Şema 64'ten 100'e çıktı; geçiş öncesi yedek
`.xti-data/backups/xti.pre-v100-29e753fb28aa4f609a3e66db050f54e0.db`
olarak korundu. Ana veritabanı ve yedek ayrı ayrı SQLite bütünlük kontrolünden
`ok` aldı; `doctor` güncel alanı `ready` gösterdi. Veri ve yedek klasörleri
`0700`, veritabanı ve yedek dosyaları `0600` yapıldı. Yedek ayrıca boş geçici
alana aynı SHA-256 ile geri yüklendi, yeniden şema100'e taşındı ve ikinci
`doctor` kontrolünde `ready / integrity=ok` verdi.

Kalıcı alanda aynı kapsamla yapılan ikinci canlı istek de **1 kredi**,
`complete` ve 5 yeni kayıt sonucu verdi. Kayıtlar süreç bittikten sonra
`mentions list` ile kalıcı veritabanından yeniden okundu. Her iki kabulde
görülen içerik türleri şunlardır:

- Tavily SecureHup şirket profili
- SecureHup ana sitesi
- SecureHup MSSP çözüm sayfası
- Türkiye Innovation Week konulu SecureHup LinkedIn paylaşımı
- SSRF konulu SecureHup LinkedIn paylaşımı

Bu bağlantılar firma içeriği adaylarıdır; tehdit, ihlal veya hesap sahipliği
hükmü değildir. Anahtar sohbet içinde paylaşılmış geçici kabul anahtarıdır;
üretim veya ekip tesliminde kullanılmadan önce sağlayıcı panelinden
yenilenmeli ve yeni değer yalnız gizli `mentions configure` girişine
kaydedilmelidir. Bu kabul temiz Linux klon kurulumunun yerine geçmez.

19 Kasım 2026 · 0.170.1 · macOS arm64 / Python 3.13.3.
Çekirdek 80 ve kuyruk 3 değişmedi. Başlangıç commit'i `262bfc4`;
çalışan kaynak ve sürüm değişikliğinin diff SHA-256 değeri:
`7a9b2ea74064a3651d1793e2b44ae059a80f091c779e7ec358eea8a09e7b8b0a`.

Kullanıcı anahtarla canlı denemeyi onayladı. Önceden seçilmiş `SecureHup`
ve `securehup.com` için yeni, izole firma alanı kullanıldı. İkinci firma
yalnız erişim ayrımını kontrol etmek için oluşturuldu; adına dış sorgu
yapılmadı. Mevcut kullanıcı verileri ve kalıcı anahtar ayarı değişmedi.

## Bulunan uyumsuzluk

Gönderilen sorgu `"SecureHup" OR "securehup.com"` idi. Tavily yanıtının
`query` alanında `SecureHup OR securehup.com` döndü. Eski adaptör metnin
birebir aynı olmasını beklediği için geçerli yanıtı reddediyordu.

Adaptör artık yalnız özgün sorguyu veya çift tırnakları kaldırılmış aynı
sorguyu kabul eder. Farklı sözcük, domain, bağlaç, eksik terim veya kısmen
kaldırılmış tırnak hâlâ reddedilir. İletilen ve saklanan sorgu özgün
tırnaklı biçimde kalır; sonuçların ad/domain eşleşmesi ayrıca hesaplanır.
Şema, kimlikler ve eski kayıtlar değişmez.

Canlı biçimi temsil eden yeni test düzeltmeden önce aynı hatayla durdu.
Düzeltmeden sonra adaptör, saklama, grup, terminal ve firma içeriklerinin
**148 testi / 49,239 saniye** hata/atlama olmadan geçti. Son sürüm/engine
kontrolü ayrıca kabul kaydında belirtilir; tam paket bu turda tekrarlanmaz.

## Sonuçlar

| Kontrol | Sonuç |
| --- | --- |
| Genel web araması | Başarılı; 5 sonuç / bildirilen 1 kredi. Kaynak çalışma kimliği `4d27f8b6-79d5-4309-9559-8b3af6413f04`. |
| Haber konulu arama | Başarılı; 5 sonuç / bildirilen 1 kredi. Kaynak çalışma kimliği `a4b169c8-d05f-4dd1-8d03-e6416873da5a`. |
| Saklama ve anahtarsız okuma | 10 kapsam/URL kaydı terminal ve `record.get` üzerinden yeniden okundu. |
| Aynı istek kimliğiyle tekrar | İki grupta eski çalışma döndü; olmayan anahtar dosyasıyla çalıştı, yeni dış istek olmadı. |
| Erken yeni tur | İki grupta `not_due`; anahtar okunmadan aralık sınırı uygulandı. |
| Sorgu bütçesi | Gerçek çalışmada her grubun tek hakkı kullanıldı. Aynı UTC gününde iki saat ileri kontrollü saat ve kapalı ağ ile `daily_budget` reddi doğrulandı; DB değişmedi. Bu son kontrol canlı saat bekleyişi değildir. |
| Firma ayrımı | Diğer firma 10 kaydın tamamında `record.get: not_found / 3` aldı; araması sıfır eşleşme döndürdü. |
| Firma içerik görünümü | Kendi alanında açıldı; diğer alandaki kuruluş isteği mevcut v1'e göre `invalid_parameters / 2`, `data=null` döndürdü. |

İlk kabul yardımcısı kuruluş okumasında da çıkış 3 beklediği için durdu.
[Mevcut sözleşme](PLATFORM_ENGINE.md) çıkış 2'yi belgeliyordu; yalnız
yardımcı kontrol düzeltildi. Yeni HTTP veya motor hata kodu değişikliği yoktur.

## Dönen bağlantıların tamamı

Genel ve haber ayrı kapsamdır. Aynı Tavily profili ikisinde de geldiği
için **10 kayıt, 9 benzersiz URL** vardır. `news` seçimi her sonucun haber
makalesi olduğunu garanti etmez. Eşleşme saklı başlık/özet/URL metnidir;
hesap sahipliği veya tehdit hükmü değildir.

| Bağlantı | Arama | Görünür ad/domain eşleşmesi |
| --- | --- | --- |
| [Tavily SecureHup profili](https://tavily.com/knowledge/company/bkKokqlQ9TfL) | Genel + haber | Var |
| [SecureHup sitesi](https://securehup.com) | Genel | Var |
| [SecureHup LinkedIn sayfası](https://www.linkedin.com/showcase/securehup) | Genel | Var |
| [Novus BT SecureHup ürün sayfası](https://www.novusbt.com/en/teknolojiler/securehup) | Genel | Var |
| [SecureAuth sitesi](https://secureauth.com) | Genel | Yok; sağlayıcı önerisi |
| [SecureHup LinkedIn paylaşımı](https://www.linkedin.com/posts/securehup_cybersecurity-appsec-vulnerabilitymanagement-activity-7524464856100679681-jVRw) | Haber | Var |
| [SecureHup başlıklı LinkedIn paylaşımı](https://www.linkedin.com/posts/securehup_securehup-activity-7518944326060564480-qgvQ) | Haber | Başlıkta var; özet başka isimler de içeriyor |
| [Novus BT — Hermes Agent güvenlik analizi](https://www.novusbt.com/insights/agentic-ai-guvenligi-hermes-agent-pentest-analizi) | Haber | Özette SecureHup var; sağlayıcı tarihi 27 Ekim 2026 |
| [PHP güncellemesi LinkedIn paylaşımı](https://www.linkedin.com/posts/securehup_securehup-php-appsec-activity-7518666519762006016-npSd) | Haber | Mevcut terim sınırı kuralında eşleşme yok; sağlayıcı önerisi |

Sonuç sayfaları ayrıca indirilmedi. Bunlar Tavily arama yanıtlarıdır;
tam makale incelemesi, ihlal tespiti veya bütün internet kapsamı değildir.

## Kullanım ve anahtar

Toplam **4 dış arama isteği**: ilk başarısız ayrıştırma, tek tanı isteği
ve düzeltme sonrası iki başarılı arama. Son üç yanıtta toplam **3 kredi**
bildirildi. İlk yanıt reddedildiği için o çalışmanın tüketimi bilinmiyor;
sıfır sayılmaz. Bu hesap bakiyesi veya fatura değildir.

Anahtar gizli terminal girdisiyle yalnız süreç belleğine ve çağrı ortamına
verildi; yapılandırma dosyasına, komut argümanına veya repoya eklenmedi.
Sohbette paylaşılan anahtar kullanımdan sonra yenilenmelidir. Yeni anahtar
yerel bilgisayarda `./xti mentions configure` ile gizli girişten kaydedilebilir.

Geçici kanıtlar: `/private/tmp/xti-tavily-live-15kzh7qb` ilk hata/tanı;
`/private/tmp/xti-tavily-accepted-g3chn5f4` başarılı aramalar, kayıt/izolasyon,
kontrollü bütçe ve `summary.json`. Ham metinler, anahtar ve test DB'leri
repoya alınmaz. N-004'ün seçilmiş firma kapsamı tamamlandı; tedarikçi canlı
sorgusu, Linux zamanlayıcısı ve uzun süreli hizmet ölçülmedi.

Protokol: [Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search).

## Geniş web ve sosyal hesap testi — 19 Kasım 2026

Önceki beş sonuçlu kabulden sonra kullanıcı daha geniş test istedi.
Çalışan kod `68812ce23842d8f2c436f50eb9c8f0d07716114c` / 0.170.1;
kod, sürüm ve şema değiştirilmedi. Ayrı veri alanında iki motor sorgusu
20 sonuç üst sınırıyla çalıştı. Firma adı SecureHup ve domain
securehup.com kullanıldı; kullanıcı ayrıca sosyal hesap adı vermedi.

| Deneme | Dönen kayıt | İlgili görünür terim | Bildirilen kredi |
| --- | ---: | ---: | ---: |
| Motor genel / basic | 20 | 10 | 1 |
| Motor haber / basic | 1 | 1 | 1 |
| Doğrudan sağlayıcı genel / advanced | 20 | 8 | 2 |
| Instagram alan filtresi / basic | 0 | 0 | 1 |
| Instagram alan filtresi / advanced | 13 | 0 | 2 |
| X/Twitter alan filtresi / basic | 0 | 0 | 1 |
| X/Twitter alan filtresi / advanced | 11 | 1 | 2 |

Yedi yeni Tavily isteği **10 kredi** bildirdi; toplam 65 yanıt satırı,
58 benzersiz URL var. Yalnız ilk iki sorgu motor içinde çalıştı ve
21 kapsam/URL kaydı sakladı; anahtarsız durum/liste tekrar okundu.
Diğerleri aynı sorguyu kullanan tanı çağrılarıdır. Mevcut motor CLI'sına
`advanced` veya domain filtresi eklenmiş sayılmaz. Tanı eşleşmeleri
görünür metindeki firma terimidir; tehdit, marka sahipliği veya sayfanın
esas konusuna ilişkin karar değildir. İlgisiz sonuçlar ayrıca ayrıldı.

Haber konusu bu koşuda 1 sonuç döndürdü; önceki kabuldeki 5 sonuçla
farklı zaman/veri kesitidir. 20 üst sınırdır, 20 ilgili sonuç garantisi değildir.

### Sosyal araçlar ve açık sayfa karşılaştırması

`./scripts/verify-brand` kurulu Maigret 0.6.6 / Sherlock 0.16.2 ve
kataloglarını doğruladı; indirme yapılmadı. `extended` profili Maigret'te
30, Sherlock'ta 26 platform seçti: birleşimde 41 farklı platform.
Bu seçim sayısı, her platformda kesin varlık/yokluk kararı alınabildiği
anlamına gelmez. Diğer platformlar `unreported_platforms` içinde kaldı.

| Platform | Gözlenen |
| --- | --- |
| X / Twitter | Maigret aday bildirdi; X alan filtreli gelişmiş Tavily sorgusu da aynı profili ve marka/domain metnini döndürdü. Genel/basic sorgularında çıkmadı. |
| Instagram | Tavily ve Maigret aday bildirmedi. Firma adından türetilen kullanıcı adının açık sayfası HTTP 200, `og:type=profile`, SecureHup başlığı ve tam profil URL'si döndürdü. |
| GitHub / GitLab | Maigret profil adayları bildirdi; sahiplik kararı verilmedi. |
| LinkedIn | Tavily marka sayfasını ve paylaşımları döndürdü. Maigret'in kişisel `/in/` yolu marka `/showcase/` sayfasıyla aynı kapsam değildir. |
| Hacker News | Sherlock aday bildirdi; aynı açık profil adresi doğrudan kontrol edilince `No such user.` döndü. Doğrulanmış hesap olarak sayılmadı. |

Instagram/X'e özel ikinci Maigret tanısında yalnız konsol hata/yokluk
görünürlüğü açıldı; katalog, tespit kodu ve kapsam genişletilmedi.
Instagram için `Not found!` yazdığı görüldü. Motor bunu kesin yokluk
diye sunmuyor, ancak bu örnekteki gerçek profili kaynak kaçırıyor.
Sherlock'un çelişen adayıyla birlikte N-031 açık tutulur.

Firma ana sayfası HTTP 200 verdi; alınan HTML içinde sosyal profil
bağlantısı yoktu. Twitter kart meta etiketleri profil bağlantısı değildir.
Açık Instagram sayfası bu test yardımcısıyla kontrol edildi; standart
motorun otomatik keşif özelliği olarak sunulamaz. Hesap adı kullanıcıdan
ön koşul olarak istenmeden keşif yapılması beklentisi N-031'e kaydedildi.

### Tekrar ve kanıt

```sh
./xti --data-dir /private/tmp/AYRI-TEST-ALANI init
./xti --data-dir /private/tmp/AYRI-TEST-ALANI mentions search --name SecureHup --domain securehup.com --topic general --max-results 20
./xti --data-dir /private/tmp/AYRI-TEST-ALANI mentions search --name SecureHup --domain securehup.com --topic news --max-results 20
./xti brand username-preview securehup --source maigret --profile extended --timeout 30
./xti brand username-preview securehup --source sherlock --profile extended --timeout 30
```

Tavily anahtarı yine yalnız gizli giriş/süreç belleği ve motor çağrı
ortamında tutuldu; kalıcı anahtar ayarı yapılmadı. Yedi isteğin tamamı
yanıt verdi; yeni kullanım önceki dört isteğe ektir. Bakiye okunmadı.
Ham yanıtlar, HTML, test DB'si ve bütün bağlantı/platformları içeren
`TAM_KAPSAM_RAPORU.md`, özel `/private/tmp/xti-social-full-8pus8z4q`
klasöründedir. `summary.json` ve dosya SHA-256 manifesti üretilmiştir;
toplanan ham kanıtlar Git'e eklenmez. Bu tur canlı davranış testidir;
tam otomatik paket yeniden çalıştırılmadı.
