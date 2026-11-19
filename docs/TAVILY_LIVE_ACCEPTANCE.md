# Tavily — SecureHup canlı kullanım kabulü

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
