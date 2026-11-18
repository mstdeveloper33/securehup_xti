# 0164 — Tedarikçi adayını ve insan kararını ortak araştırmada ayırma

18 Kasım 2026 · 0.160.0 · Uygulandı.

## İhtiyaç

CNAME araştırması dış hizmeti gösterebiliyordu. Ancak bu bağı kullanıcının
hangi tedarikçiyle ilişkilendirdiği, reddettiği veya sonradan değiştirdiği
ayrı komutlarda kalıyordu. Teknik gözlem ile insan kararının aynı gerçek
gibi sunulması yanlış sahiplik ve güncellik yorumlarına yol açabilir.

## Karar

- Mevcut aday, kaynak kanıtı, karar olayı ve tedarikçi envanteri okunur.
  `research_suppliers` domain katmanı dönüşümleri üretir; SQLite adaptörü
  araştırmanın tek okuma transaction'ını kullanır. Yeni kaynak/karar
  oluşturulmaz; ağ, yeni paket, tablo veya migration yoktur.
- Domain → aday → aday domaini yolları `candidate_context` türündedir.
  Kaydedilmiş PSL sürümü/özeti ve özgün CNAME kontrol başvurusu korunur;
  güncel PSL ile tarihî aday yeniden türetilmez. Adayın `current` alanı
  son yenilemenin kayıtlı durumudur; bugünkü DNS veya canlı sözleşme değildir.
- Domain → tedarikçi ve tedarikçi → envanter domaini `human_decision`
  türündedir. Geçmiş onaylar silinmez. Yeni sağlayıcıya geçiş, ret veya
  yeniden inceleme kararı, eski bağ için özgün yeni olayla `withdrawn`
  gösterilir. Yeni bir karar kaydı uydurulmaz; türetilmiş bağlantı durumu
  açıkça asıl karar metniyle birlikte sunulur.
- İnsan kanıtında `current` gösterilen aday, envanter veya bağlantı için
  son ilgili kararı belirtir. Durum ayrıca okunur: son karar `withdrawn`
  veya `revoked` olabilir. Teknik bağın kaybolması insan onayını silmez;
  tedarikçinin pasifleştirilmesi aday kararını kendiliğinden değiştirmez.
- Envanter kimliği korunur, benzer isimler birleştirilmez. Kullanıcının
  seçtiği tedarikçi domaini, adayın teknik hizmet domaininden farklı olabilir.
  Ters araştırma yalnız aynı firmanın kayıtlı onaylarından genişler.
- Seçilen adayın tam kanıt/karar zinciri mevcut doğrulayıcıyla kontrol edilir.
  Ortak tedarikçi geçmişi okuyucusu tek tedarikçiyle sınırlı okunabilir;
  olaylar aynı kuralla yeniden oynatılır. Küresel sıra boşluğu sayısal
  olarak kontrol edilir; ilgisiz kayıt içerikleri yüklenmez. Dar geçmiş
  bütün firma için tarihî watermark gibi kullanılamaz.
- Ön doğrulama bütçesi istekte 10.000 bağlı satır/16 MiB'dır. CNAME
  başvuruları, kararlar, envanter ve onun olayları hesaba katılır. Bütçeyi
  aşan aday/tedarikçi doğrulanmış gibi gösterilmez; `supplier_read_budget`
  ve doğrulanmış kapsam görünür. Bozuk kimlik/kanıt/yaşam döngüsü ise
  `storage_error` olur. Düğüm başına 200 tedarikçi bağı sınırı vardır.
- Kanıt görünümü en fazla 50; aday düğümü en fazla 52 öğedir. Aday durumu,
  son karar ve en az bir teknik kanıt önce tutulur. Kesilen geçmiş sayısı
  korunur. Araştırmanın iki adım/100 düğüm/200 bağ sınırları aynı kalır.

## Sürüm ve uyum

Yeni kanıt türleri gözlem gibi etiketlenmez. Araştırma ve yeni dondurulmuş
değerlendirme modeli **2**, öncelik politikası **v3** olur. Engine/platform
isteği ve zarfı v1, çekirdek 75, kuyruk 2 ve karşılaştırma modeli 1 kalır.
Doğrulayıcı eski model 1'i özgün okur; yeni türleri model 1 altında kabul
etmez. İlk yeni model/kural kaydı yeni başlangıçtır. Model kimliği sayfa
kesitine dahildir. Eski kod model 2 incelemeyi okuyamaz; geri dönüş için
yükseltme öncesi yedek gerekir. Otomatik downgrade veya veri dönüşümü yoktur.

Kararın yaşı gösterilir ancak eski insan kararları ağ kanıtı eskimesi
gibi sıralanmaz. Bekleyen/belirsiz aday, tarihî aday ve pasif envanter
doğrulama gerekçesidir. İşletme önemi ve insan onayı tehdit puanı olmaz.
Alarm, vaka, risk kartı, izleme veya abonelik davranışı değiştirilmez.

## Kabul

Kontrollü SQLite/CLI/platform testleri ret/yeniden açma/sağlayıcı değişimi,
teknik kayıp ile insan kararı ayrımı, kaynak kimlikleri, dar okuma sınırları,
eski/yeni inceleme, tek okuma kesiti, firma ayrımı ve yedeği kapsar.
Sonuçlar [kabul kaydında](../ACCEPTANCE_REVIEW.md) tutulur. Bu dilim genel
kimlik birleştirme, yeni tedarikçi keşfi veya canlı Nmap/Tavily kabulü değildir.
