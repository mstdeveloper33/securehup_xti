# 0173 — Kaynak işi v4 ve ayrı görülme/ilişki günlüğü

19 Kasım 2026. Kullanıcının birlikte yetkilendirdiği sekiz maddelik motor
paketi; önceki 0.165–0.167 çalışma değişikliklerini korur.

İş modeli 4 açık kaynak sırası, hata davranışı ve sürümlü rapor yakalamayı
ekler. Kuyruk şeması 3'ün altı adım/16 olay sınırları değişmez; eski iş
modeli 1/2/3 kendi makbuzlarıyla okunur. Yeni alanlar eski iş sürümüne
sonradan eklenemez. Serbest komut veya genel amaçlı DAG çalıştırıcısı yoktur.

Rapor adımı salt okunur kaynak kesitinden sınırlı seçim yapar ve her
yakalamayı beklenen içerik özetiyle yazar. Worker tek yazıcı kilidini tutar.
Makbuz belge UUID/sürüm/hash üçlüsüdür. Adımlar arası kesinti, haber kaydı
veya rapor yazımını geri almaz; açık tekrar özgün sürümleri doğrular.
Tekrarlanan haber adımı bağlı rapor yakalamayı geçersiz kılar; bu kural
yazmada ve kuyruk replay denetiminde ortak domain fonksiyonundadır.
Makbuz, seçilen haber sağlayıcısı ile de eşleşmelidir.
Yerel rapor yakalama ağ tüketimi sıfırdır. Günlük haberler otomatik olarak
işin kök firmasıyla eşleşmiş sayılmaz.

Yeni çekirdek 78 yalnız `evidence_journal` ekler. Domain sözleşmesi,
aday kuralları ve günlük replay'i IO'dan bağımsızdır. `EvidenceService`
küçük workspace portunu kullanır. SQLite adaptörü, yazma sırasında aday
dayanağını aynı `BEGIN IMMEDIATE` kesitinde okur ve tekrar/sürüm denetimini
atomik yapar. CLI ve firma JSON aynı uygulama servisini kullanır.
Kişisel engine salt okumadır; firma yazması mevcut workspace çitini ve
tek yazıcı kilidini kullanır.

Günlük 20.000 olay/64 MiB, tek kayıt 1.000 olay/2 MiB ile sınırlandırılır;
büyük geçmiş ayrıntıyı okunamaz hale getirmeden yazma reddedilir.
Sensör kaydının doğal kimliği kaynak/sensör/olaydır. Kaynak olayının farklı
içerikle tekrar kullanılması reddedilir. Kayıt/revoke/ilişki-review
istekleri kanonik JSON, sıra, SHA ve zincirle saklanır; son satır silinmesi
de tespit edilir. Bu bozulma denetimidir; imzalı dış güven kökü veya
veritabanı yöneticisine karşı kriptografik inkâr edilemezlik değildir.

İlişki adayı sınırlı iki adımlı mevcut kanıttan hesaplanır. Kabul edilen
karar ayrı kalır; CTI assertion veya saldırgan atfı yazılmaz. Aynı geometrik
yolun dayanağı değişirse önceki karar korunur ve eski işaretlenir. Adaylar
kendi kararlarından yeni aday türetmez. Birleşik kimlik yalnız kabul edilmiş
mevcut kimlik bağlarını okuyan görünüm olup özgün kaydı değiştirmez.

Sensör görülmeleri ortak araştırmaya `observation` olarak taşınır; kaynak
liste üyeliği veya metinde geçme ile karıştırılmaz. Araştırma modeli 3,
öncelik v8 ve eski dondurulmuş incelemeler korunur. Firma incelemesi yerel
görülmesi olan kökleri de pencereli olarak alır. Karşılaştırma iddia
geçerliliği ve tarih temelini ayırır; puan toplamı veya otomatik hüküm yoktur.

RIPEstat WHOIS sabit, anahtarsız pasif uçtur. Seçilmiş kayıt alanlarının
ayrıştırılması domain'de, HTTP ve kalıcı kaynak makbuzu adaptörlerdedir.
Mevcut RIPEstat cooldown'u paylaşılır. Kaynak sorgu/aralık uyumu denetlenir;
kapsam dışı yanıt görünürde sahiplik bağına çevrilmez. Ticari kullanım
N-022 kapsamında ayrıca çözülmelidir.

Geçiş önce mevcut çekirdeğin yedeğini alır; eski tablolar yeniden yazılmaz.
Geri dönüş eski kod + yükseltme öncesi yedeğin boş hedefe geri yüklenmesidir.
Yeni iş v4 veya şema78 eski kodda okunabilir diye sunulmaz.
Kabul; tekrar/çakışma, eski dayanak, firma izolasyonu, kaynak hata koruması,
gerçek wrapper süreçleri, eşzamanlı okuma/yazma, yedekten dönüş ve ölçülü
veri hacmini kapsar. Sonuçlar ve dış girdi eksikleri kabul kaydı/NOTES'tadır.
