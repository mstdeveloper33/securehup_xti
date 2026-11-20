# crt.sh — eski hata ile güncel erişimin ayrılması

20 Kasım 2026. Bu kayıt yalnız pasif crt.sh sorgusunun güncel erişimini
doğrular. Hedefe bağlantı, port taraması veya yeni tarama gönderimi yoktur.
Kişisel/şirket veritabanına yazılmaz; alınan sertifikalar repoya eklenmez.

## Tekrarlanabilir ölçüm

```sh
./scripts/python scripts/check-source-evidence.py \
  --domain securehup.com --output /tmp/xti-crtsh-yeni-deneme.json
```

Çıktı yeni ve özel izinli bir dosyadır; var olan dosya üzerine yazılmaz.
Script gerçek `CrtShSource` adaptörünü, ardından aynı URL'ye ayrı GET'i
kullanır. 429/Retry-After görülürse doğrudan ek sorgu atlanır. Yanıt boyutu
8 MiB, istek timeout'u 20 saniye; adaptörün mevcut iki deneme üst sınırı
korunur. İstek yöntemi/adresi, UTC başlangıç/bitiş, süre, HTTP kodu,
seçilmiş yanıt başlıkları, okunan byte ve SHA-256 kaydedilir. Cookie,
Authorization, API anahtarı ve ham sertifika gövdesi rapora yazılmaz.

Ölçümde temel commit `d3fd77393803d6048cd98a3bb14b794b4aacf502`, sürüm
etiketi 0.175.0, çalışma ağacı değişmişti. 0.176.0 geliştirmesindeki tanı
scripti kullanıldı; crt.sh üretim adaptörü değiştirilmedi. Python 3.13.3,
macOS arm64. Bu Linux veya kesintisiz hizmet kabulü değildir.

Tam istek:
`GET https://crt.sh/?dNSName=%25.securehup.com&match=ILIKE&output=json`

| Deneme | UTC başlangıç | UTC bitiş | Süre | Sonuç |
| --- | --- | --- | --- | --- |
| Kısıtlı ortam, motor | 09:34:03 civarı; ayrıntı yerel tanı dosyasında | Aynı saniye | <0,01 sn | DNS çözümleme `URLError`; HTTP yanıtı yok |
| Ağ erişimi verilmiş ortam, gerçek motor | 09:34:25.687998 | 09:34:30.211130 | 4,523078 sn | HTTP200; adaptör `SourceBatch` başarı |
| Aynı ortam, bağımsız HTTP GET | 09:34:30.261294 | 09:34:36.491759 | 6,230384 sn | HTTP200; geçerli JSON listesi, 23 kaynak satırı |

İki HTTP200 yanıtı: `Content-Type: application/json`, `Content-Length: 7095`,
`Server: nginx`; `Date` sırasıyla `Fri, 20 Nov 2026 09:34:30 GMT` ve
`Fri, 20 Nov 2026 09:34:36 GMT`. Okunan gövde 7095 byte; ikisinde de tamamı
okundu ve aynı SHA-256 elde edildi:
`b1085bf109d91f995897aff6add066c256af63539197b4840a6775ab42f3e699`.
23 satır, 23 ayrı domain veya tehdit demek değildir.

Yerel ayrıntılı JSON:
`/tmp/xti-crtsh-evidence-20261120-network.json`.
Kısıtlı ortam kanıtı:
`/tmp/xti-crtsh-evidence-20261120-1.json`.
Bunlar geçici tanı dosyalarıdır; Git'e alınmaz. Kalıcı teknik özet bu
belgede, yeniden üretim kodu yukarıdaki scripttedir.

## Neyin kapandığı

- **Güncel crt.sh erişim kanıtı eksikliği kapandı.** Motor ve ayrı istemci
  aynı gün başarılı oldu; yöntem/zaman/yanıt özeti mevcut.
- İlk ortamın DNS hatası **sağlayıcı kesintisi diye sınıflandırılmadı**.
  Ağ sınırının dışında aynı adresin başarılı oluşu ortam farkını gösterir.
- 16 Kasım raporundaki timeout/502 kaydı tarihîdir. O raporda belirtilen
  sonraki HTTP200'ün ham kanıtı hâlâ yoktur. Bugünkü başarı, o zamanki
  gecikmenin kesin kök nedenini ispatlamaz; tarihî neden **belirlenemedi**.
- Kaynak erişimi başarılı olsa da eski kanıtın güncelliği değişmez.
  `surface discovery-health DOMAIN` son denemeyi, önceki tamamlanmış
  yanıtı ve korunan veri durumunu ayrı gösterir. Kaynak hatasının eski
  başarılı veriyi silmemesi otomatik kontrollü testlerle doğrulanır;
  veritabanına dokunmayan bu canlı tanı aynı iddiaya kanıt sayılmaz.
- Common Crawl/Wayback'in geçmiş başarısızlıkları bu denemeyle başarılı
  işaretlenmedi; bu tur onlara yeni canlı istek gönderilmedi. Önceki
  kabul kayıtları kendi tarih/sürüm kapsamındadır.
- Eski Red Hat/Ubuntu raporlarındaki kaynak/ürün ayrımları da bu crt.sh
  ölçümüne taşınmadı; ilgili geçmiş [kabul incelemesi](ACCEPTANCE_REVIEW.md)
  korunur.

N-006 güncel kanıt işi bu kapsamla kapanır. Yeni bir gerçek hata olursa
yeni zaman/istek/yanıt kaydı açılır; sabit bir tarihî kesinti bütün gelecek
sürümler için açık hata olarak taşınmaz. Teknik başarı, ticari izin
anlamına gelmez; o karar [ticari değerlendirmede](COMMERCIAL_SOURCE_REVIEW.md)
ayrıdır.
