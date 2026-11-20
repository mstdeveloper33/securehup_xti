# 0179 — Saklı sosyal adresler ve ortak kaynak kuyruğu

20 Kasım 2026 · Kabul edildi · 0.174.0 / çekirdek84 / kuyruk3.

## İhtiyaç

Önceki turda bulunan farklı kullanıcı adları, firma sayfasından veya
keşif araçlarından kaybolunca tekrar kontrol edilmiyordu. Ayrıca sosyal
takip, platformun mevcut kuyruk/worker yaşam döngüsüne bağlanmamıştı.

## Karar

- `social_retained` saf kuralları aynı izlemenin seed ve sonraki kaynak
  kanıtlarından adresleri türetir. Yalnız sayfayla bulunmuş veya kaynak
  destekli aday adresler kalır. Dış JSON yeni URL listesi kabul etmez.
- Her tur sayfa bütçesinin yarısı (en az bir) önceki adreslere ayrılır.
  Sıralı son-adres imleciyle dönüş yapılır; eklenen yeni adresler eski
  sayısal imleci kaydırmaz. Diğer sayfalar yeni keşfe açıktır. Bir sayfalık
  bütçede saklı adres varsa o tur yeni adres kontrolü yapılamayabilir.
- `retained_profile` yalnız keşif kökenidir; güncel sağlayıcı iddiası,
  firma sahipliği veya yeni güven puanı değildir. Eksik erişim son
  doğrulanabilir gözlemi silmez. Bu adresler inceleme listesinde de görünür.
- Yeni tur günlük isteği iç `_version=2` alanı taşır. Run, watch revision
  ve `tracking` kontrol penceresini dondurur; keşif scope/hash'ine bağlar.
  Eski günlük ve makbuzların JSON/hash'leri değişmez; eski tur replay'i
  önceki alanları/keşif kapsamını korur. Case snapshot eski/yeni kapsamı okur.
- Çekirdek **83 → 84** açık ve yedeklidir; tablo DDL veya eski satır değişmez.
  Yeni kayıt anlamını bilmeyen eski motorun bu alanı açmasını engeller.
  Geri dönüş yükseltme öncesi yedekten yeni alana yapılır.
- `social-tracking`, mevcut `sources.refresh` iş modeli **6** içindedir.
  `social_watch_id`, `social_watch_revision`, `social_force` plan/hash'e
  dahildir. Aynı firma/domain, sürüm ve etkinlik kabulde/worker öncesinde
  doğrulanır. Gerçek kapsam kayıtlı izlemededir; keyfî URL/komut yoktur.
- Queue→core kilit sırası korunur. `SocialTrackingStep` var olan izleme
  servisi ve kanıt depolarını kullanır. İş anahtarı `social-job-UUID`,
  keşif anahtarı özgün tur UUID'sidir. Ayrı kuyruk veya daemon eklenmez.
- İki veri tabanı arasındaki kesintide açık retry, soyundaki tamamlanmış
  core makbuzunu tekrar kullanır. Kesilmiş dış istek için önce mevcut
  `allow_uncertain` kabulü gerekir. Yeni istek gerekliyse güncel guard
  çalışır. Keşif rezervasyonu öncesinde duraklatılmış eski tur ağsız
  `interrupted` kapanır; izleme süresiz `busy` bırakılmaz.
- Tamamlanmış makbuzun okunması sonraki duraklatmadan etkilenmez. Worker'ın
  o anda gözlediği `not_due/busy/paused/revision_changed` olayı iş günlüğüne
  kaydedilir; geçmiş guard kararı güncel saatle yeniden hesaplanmaz.
- Kaynak modeli 1–5 okunur, eski istek/hash'ler korunur. Kuyruk3 ve dış
  JSONv1 değişmez. Eski kod model6 işi okuyamaz; platform yedeği core ve
  kuyruğu birlikte içerir.

## Ölçüm ve sınırlar

Maigret/Sherlock alt süreçlerinin iç istek sayısı bilinmiyor. Bu nedenle
sosyal işi `max_requests` ile sınırlandırılmış gibi göstermiyoruz.
Plan `maximum_external_requests=null` ve açık `request_limit_scope`
bildirir; diğer kaynakların istek tavanı korunur. Sosyal turun kendi
sayfa, süre, platform, aday ve alt süreç sınırları uygulanır.

Sosyal makbuz usage v2; bilinen sayfa HTTP denemesi ayrı, araç trafiği
`null` olur. Başlamamış/iptal edilmiş veya gerçekten ağsız tekrar işin
tüketimi sıfırdır; önceki işin belirsiz trafiği silinmez. Sayfa sayacı
özgün keşfe karşı doğrulanır. `max_seconds` ve iptal adımlar arasındadır;
başlamış sosyal turun kendi bütçesi devam eder. İş sonucunun `partial`
olması bütün hesapların bulunamadığı anlamına gelmez.

Ücretli Tavily/Bright Data otomatik çalışmaz. Zamanlayıcı ve firma genel
kotası tüketen platforma aittir. Yerel kuyruk dağıtık worker/SLA iddiası
değildir. Yeni bağımlılık yoktur.

## Dayanak

[Kullanım](../SOCIAL_TRACKING.md), [ortak kuyruk](../SOURCE_JOBS.md),
[kabul ve eski koddan veri geçişi](../ACCEPTANCE_REVIEW.md),
[altı yeni kuruluş ölçümü](../SOCIAL_TRACKING_ACCEPTANCE.md).
