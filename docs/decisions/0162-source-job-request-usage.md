# 0162 — Motorun iş başına istek kullanımı ve backend sınırı

- Tarih: 18 Kasım 2026
- Durum: Uygulandı; 0.158.0, çekirdek 75, kuyruk 2

## Karar

Firma paketi, abonelik ve ortak sağlayıcı kotasının tek merkezde yönetimi
backend sorumluluğudur. Motor verilen iş sınırını uygular, kayıtlı kullanım
ve belirsizlik bilgisi verir. İkinci bir ticari kota/veritabanı kurulmaz.

Yeni `sources.refresh` payload/result sürümü 2'dir. Kaynak HTTP
adaptörlerinin opener'ı küçük bir ölçüm adaptörüyle sarılır. Saf domain
sayacı adım tavanını deneme öncesi uygular; yanıt, taşıma hatası, 429 ve
engellenen ek denemeyi sayar. Adım tavanlarının toplamı kabul edilmiş
plan bütçesini aşamaz. Yeni bağımlılık yoktur.

Ölçüm HTTP açma denemesidir; sağlayıcı faturalaması veya ağda teslim edilen
paket sayısı değildir. Kaynak beklemesi isteği açılmadan durdurursa sıfır
deneme vardır. MISP commit/koşul/listeleri ayrı HTTP denemeleridir; hata
nedeniyle oluşturulan birden çok kaynak kaydı tüketimi çoğaltmaz.

Adımın küçük `usage` kaydı mevcut değişmez kanıt başvurusuyla aynı kuyruk
olayına yazılır. Beklenmedik kesintide sayaç bellekte kaybolabilir; o adım
bilinmiyor olarak sunulur, sıfır veya kesin gönderilmiş kabul edilmez.
Kurtarma dış isteği tekrar etmez. Retry tamamlanmış adımın kanıtını korur
ve bu işte yeni tüketim saymaz; eski kullanım ebeveyn işte kalır.

`EngineJob.to_dict()` kaynak işlerinde sürümlü `execution` okuma modelini
üretir. Terminal/platform aynı kaydı okur. Donmuş sonuç JSON'u bu güncel
sunum için yeniden yazılmaz. Kuyruk beklemesi ve sonlanmış işin UTC kayıt
süresi ayrı sunulur; bu bir monotonic süre, CPU ölçümü veya SLA değildir.

## Uyumluluk ve doğrulama

V1 payload/sonuç/hash ve yürütme biçimi korunur; ölçülmeyen eski kullanım
`legacy_unmeasured` olur. Aynı istek niyetinin kanonik request v1 anahtarı
korunarak eski anahtar yeni iş yaratmaz. Açık retry v2 kabul edilir.
Veritabanı DDL'i değişmez. Eski kod v2 işi okuyamaz; kod geri dönüşünde
yükseltme öncesi iki dosyalı firma yedeği gerekir.

Kontrollü HTTP + gerçek SQLite testleri sayaç, bütçe, bekleme, 429,
kesinti, iptal, tekrar, eski kayıtlar, firma sınırı ve yedekten dönüşü
sınar. Kesin test/kabul sonuçları [kabul kaydında](../ACCEPTANCE_REVIEW.md),
sözleşme ve kapsam [kullanım belgesinde](../SOURCE_JOBS.md#işin-kullanım-raporu).
