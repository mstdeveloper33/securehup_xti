# 0182 — Yönetilen grup kontrolü ve kayıpsız geçmiş

Tarih: 20 Kasım 2026. Sürüm0.177.0 / çekirdek87 / kaynak işi7 / kuyruk3.

## İhtiyaç ve karar

Kayıtlı kanıt grupları mevcut işçiyle kontrol edilebilmeli, gerçek farklar
mevcut inbox'a gitmeli ve geçmiş mevcut arşivle sıkıştırılabilmelidir.
Yeni kuyruk, veri toplayıcı, daemon veya platform kimlik yönetimi eklenmez.

Saf `group_jobs` kapsam/makbuz doğrular. SourceJobService, mevcut küçük
kanıt servisini kullanarak grubun aynı köke ait olduğunu denetler.
Somut GroupRefreshStep adaptörü girişte bağlanır; domain/application
katmanına SQLite veya HTTP bağımlılığı taşınmaz. İş yeni model7'dir;
1–6 okunabilir, kuyruk3 ve dış zarfv1 değişmez.

## İşlem ve kurtarma sınırı

Worker mevcut kuyruk→çekirdek kilit sırasını korur. Grup kontrolü kısa
`BEGIN IMMEDIATE` içinde son revision'ı okur; bekleyen işten sonra verilmiş
insan kararını ezmez. Yeni kaynak adımları grup kontrolünden önce yürür.
Grup kapsamı ilk donmuş kaydından gelir; genel plan ayarları onu değiştirmez.

Kalıcı işlem anahtarı `group-job:<job-id>` olur. Core commit sonrası queue
ilerlemesi kesilirse açık retry, tamamlanmış adımı bulunmayan iş soyunda
bu anahtarı arar. Bulunan özgün olay noktasına kadar günlük yeniden okunur;
sonraki insan kararları eski makbuzu değiştirmez. Kaydedilmiş kısmi sonuçtan
retry yeni kontrol üretir; kontrol/bildirim sonucu kaybolduysa aynı sonucu
bulur. Başarılı kaynakları tekrar kullanma kuralı grup türetimine uygulanmaz.

## Bildirim ve veri geçişi

Grup günlüğünün v1 olay biçimi ve hash'leri korunur. Saf replay isteğe bağlı
olarak fark oluşan noktadaki önce/sonra kanıtını türetir. Şema87 tek ek
bildirim tablosu getirir: olay referansı, kanıt özeti, sıra/zincir ve okundu
zamanı. Büyük kanıt gövdeleri tekrar kopyalanmaz. Özgün günlük, yabancı
anahtar, hash/zincir ve silinmiş kuyruk sonu birlikte doğrulanır.

Refresh ve bildirim aynı transaction'dadır. İlk kayıt, aynı kanıt ve kısmi
kapsam sessizdir; eksik okuma kesin kayıp olmaz. Bildirim kimliği olay başına
tekildir, ortak inbox sırası kullanılır. Okundu durumu grup kararı değildir.
Eski değişikliklere geriye dönük alarm çıkarılmaz. Bildirim kapasitesi
10.000/16 MiB metadata; asıl kanıt grup günlüğünün okuma sınırına tabidir.

86→87 eski tablo/satır/rowid değiştirmeyen ek geçiştir. Şema doğrulama yeni
tabloyu tam biçimiyle denetler; eski şemada yalnız boş önceden oluşturulmuş
tabloya izin verilir. Geçiş öncesi yedek ve eski kodla geri dönüş sınanır.

## Arşiv ve sınırlar

`research_group_journal`, mevcut kayıpsız gövde arşivinin dördüncü günlüğü
olur. Gövde açıldıktan sonra özgün günlük hash/zinciri ve olay kuralları
doğrulanır. Grup, eski iş makbuzu, bildirim, vaka ve yedekten dönüş aynı
kanıtı gösterir. Bozuk arşiv sessizce eksik başarıya dönüşmez.

En güncel olay korunur; plan, token, yedek, audit ve geri aç aynı mevcut
protokoldedir. Mantıksal sınırlar açılmış byte/olay üzerinden devam eder.
Bu karar purge, sınırsız takip kapasitesi veya 7/24 SLA sağlamaz.

## Kabul

Gerçek süreç core commit'ten sonra SIGKILL ile durdurulur; kuyruk recovery
ve explicit retry aynı olay/bildirimi bulmalıdır. Arşiv ve sonraki karar
bu sonucu değiştirmemelidir. İki firma, CLI/JSON, kısmi veri, iptal,
notification rollback, arşiv bozulması, özgün86 üretici/geçiş/rollback
ve kontrollü kapasite kabulü [teslim kaydında](../roadmap/GROUP_OPERATIONS_DELIVERY.md).
