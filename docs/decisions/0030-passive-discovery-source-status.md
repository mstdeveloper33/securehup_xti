# 0030 — Tamamlanmış boş pasif sonucu kaynak kesintisinden ayırma

**Durum:** Kabul edildi  
**Tarih:** 29 Ekim 2026

## Bağlam

Pasif sertifika keşfi tamamlanabilir, kısmi kalabilir, kaynak hatasıyla başarısız olabilir veya henüz hiç çalıştırılmamış olabilir. Bu durumların hepsinde aday sayısı sıfır görünebilir. Yalnız sayıya bakmak, “kaynak yanıtında aday yok” ile “kaynağa erişilemediği için bilmiyoruz” sonuçlarını karıştırır ve yanlış güven üretir.

Mevcut keşif geçmişi çalışma durumunu, uyarıyı, hatayı ve aday sayılarını eklemeli saklar. Yeni bir kaynak sorgusu başlatmadan bu kanıtın kullanıcıya tek ve açık bir sonuç olarak sunulması gerekir.

## Karar

`surface discovery-status KÖK`, yalnız son kayıtlı pasif keşif çalışmasını okur ve üç bağımsız boyut üretir:

- Kaynak durumu: hiç çalışmadı, çalıştı, sonuç eksik veya çalışmadı.
- Veri sonucu: aday görüldü, aday görülmedi veya bilinmiyor.
- Güncellik: güncel, eski, hiç yok veya zaman bilgisi tutarsız.

Tamamlanmış ve sıfır adaylı çalışma `complete_empty` olur; yalnız bu durumda `empty_result_confirmed=true` verilir. Bu alan, seçilen kaynak sorgusunun tamamlandığını ve yanıtında aday bulunmadığını ifade eder. Kısmi sıfır sonuç `partial_empty` olur ve boşluk doğrulanmış sayılmaz. Kısmi bulunan sonuç yararlı adayları korur fakat kapsamın eksik olabileceğini açıklar. Başarısız ve hiç çalıştırılmamış durumda veri sonucu `unknown` kalır.

Kullanıcı 1–8760 saat arasında rapor güncellik eşiği seçebilir; varsayılan 24 saattir. Son çalışma eşiği geçtiyse önceki sonuç silinmez fakat yeni durum için tekrar önerilir. Gelecekteki veya okunamayan zaman `clock_error` olur.

Servis mevcut `SurfaceCandidateRepository` üzerinden yalnız son çalışma kaydını alır. Ağ adaptörü yoktur; yeni keşif, onarım veya yazma yapmaz. Yeni tablo veya migration yoktur; şema 15 değişmez.

## Sınırlar

- Tamamlanmış boş sonuç yalnız crt.sh sorgusunun o andaki yanıtıyla sınırlıdır; internette hiç alt alan adı veya risk olmadığını kanıtlamaz.
- `complete` sağlayıcının kapsadığı evrenin eksiksiz olduğu anlamına gelmez; yalnız bilinen sorgu/yanıt işleminin uyarısız tamamlandığını anlatır.
- Güncellik eşiği otomatik çalışma sıklığı veya hizmet seviyesi değildir.
- Görünüm kaynak erişimini canlı olarak sınamaz; kayıtlı son çalışmayı yorumlar.

## Sonuçlar

Kullanıcı sıfır aday sayısını tek başına başarı saymaz. Kesinti, eksik kapsam, eski sonuç ve gerçek tamamlanmış boş yanıt görünür biçimde ayrılır. Aynı uygulama modeli ileride başka pasif kaynaklar eklendiğinde kaynak bazlı sağlık ve veri sonucunu karıştırmadan genişletilebilir.
