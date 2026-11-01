# 0028 — Dış yüzey kanıt yaşını kontrol sonucundan ayrı gösterme

**Durum:** Kabul edildi  
**Tarih:** 29 Ekim 2026

## Bağlam

Web DNS/TLS/HTTPS, MX/SPF/DMARC ve sınırlı TCP servis kontrolleri ayrı eklemeli geçmişler üretir. Kullanıcı hangi bölümün yakın zamanda kontrol edildiğini anlamak için üç geçmiş ekranını tek tek açmak zorunda kalmamalıdır. Ancak son kontrolün yeni olması onun eksiksiz veya başarılı olduğu; eski olması da varlığın riskli olduğu anlamına gelmez.

Genel `status` komutu pasif marka aramalarının kaynak bazlı güncelliğini gösterir. Aktif ve onaylı dış yüzey kanıtı farklı kapsam ve sonuç sözleşmelerine sahip olduğundan aynı modele karıştırılmamalıdır.

## Karar

`surface freshness KÖK`, etkin kapsam ile son web, posta ve servis kanıtını tek SQLite salt-okunur anlık görüntüsünden alır. Sabit üç kanıt ailesi her zaman raporda yer alır; hiç çalıştırılmamış bölüm saklanmaz veya görünmez olmak yerine `never` gösterilir.

Kullanıcı 1–8760 saat arasında rapor eşiği seçebilir; varsayılan 24 saattir. Kanıt yaşı eşikten küçükse `current`, eşit veya büyükse `stale` olur. Kanıt yoksa `never`; zaman okunamıyor veya gelecekteyse `clock_error` olur. Hesap enjekte edilen UTC saat ve tam saniye yaşıyla yapılır.

Kanıt yaşı ile kontrol sonucu bağımsız alanlardır. Web, posta ve servis için mevcut `complete/partial/failed` kuralları yeniden kullanılır. Kanıt yokluğunda sonuç `not_checked` olur. Böylece yeni fakat kısmi bir sorgu “güncel tam kanıt” gibi sunulmaz.

Güncellik deposu yalnız gerekli kapsam ve son üç kanıtı okur. Aday alt alan adlarını, ilişki listesini veya ağ adaptörlerini yüklemez. Komut ağ isteği, yazma, onarım veya otomatik kontrol başlatmaz. Yeni tablo ve migration yoktur; şema 15 değişmez.

## Sınırlar

- Eşik otomatik çalışma sıklığı veya hizmet seviyesi değildir.
- `stale`, `never` veya `clock_error` saldırı, kesinti ya da zafiyet hükmü değildir.
- Sonucun başarısız olması varlığın artık bulunmadığını veya güvende olduğunu kanıtlamaz.
- Bu görünüm pasif crt.sh/urlscan arama güncelliğinin yerine geçmez; onlar `status` komutundadır.
- Yeni kanıt yalnız açık tek kontrol veya `surface monitor` komutuyla alınır.

## Sonuçlar

Kullanıcı dış yüzey görünürlüğündeki boşlukları tek komutta görebilir ve hangi kontrolü yenileyeceğine karar verebilir. Yaş, sonuç kalitesi ve kapsam durumu ayrı tutulduğu için eksik veri yanlış güven veya yanlış alarm üretmez. Salt-okunur küçük port, ileride çok varlıklı toplu görünüm eklenirken aynı politika modelinin yeniden kullanılmasını sağlar.
