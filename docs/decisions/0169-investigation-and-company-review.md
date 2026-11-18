# 0169 — Kanıtlı inceleme ve firma ölçeğinde ortak okuma

Tarih: 18 Kasım 2026. Durum: 0.164.0'da uygulandı; işletim sonuçları
[kabul kaydında](../ACCEPTANCE_REVIEW.md) ayrı tutulur.

## İhtiyaç ve karar

Mevcut vaka/sosyal/içerik kayıtları ayrı ekranlarda kalıyordu. Aynı firmada
kanıtı araştırma, ad eşleştirmesini inceleme ve toplama akışını yönetme
ihtiyacı yeni UI veya ikinci bir CTI platformu kurmadan karşılanır.

`StoredCaseContext`, `StoredContentContext`, `StoredInvestigationContext`
mevcut araştırma okuyucusunun tek SQLite okuma transaction'ını paylaşır.
Özgün depo replay/doğrulayıcıları kullanılır. Önce SQL ile satır ve saklı
byte bütçesi ölçülür; sınırlı kaynak kapsamı açıkça raporlanır. Domain
kuralları HTTP, SQLite ve terminal bilmez.

Kimlik ve rapor adayları küçük `InvestigationRepository` portu üzerinden
eklemeli günlükte tutulur. Şema 76 yalnız yeni `investigation_events`
tablosunu ve indeksini ekler. Eski kimlikler ve 75 şemasının tabloları
değişmez. Olay yükü, SHA-256 zinciri, sıra, beklenen önceki olay ve karar
sürümü denetlenir. Otomatik migration yoktur; explicit migration önce
eski şemanın yedeğini alır. Tekrar anahtarı parametrelerle birlikte özgün
sonuca bağlıdır. Firma yazma kapısı mevcut workspace/kilit düzenini kullanır.

Kimlik onayı fiziksel merge değildir. Aynı türde iki mevcut kayıt arasında
insan incelemesi bağlantısı oluşturulur; withdrawal geçmişi korur. Rapor
çıkarımı saklı metindeki kesin konumu korur; karar hiçbir aşamada otomatik
IOC veya saldırı atfına dönüşmez. Kaynak özeti kısaltılmışsa görünürdür.

Firma listesi aynı okuma kesitindeki sınırlı kök pencerelerini mevcut
öncelik kuralıyla değerlendirir. Genel kataloğun tamamını okuduğu iddiası
yoktur; kök ve sonuç sayfalaması ayrıdır. Kaynak iddialarının ayrı durumları
korunur; sistem otomatik anlamsal çelişki hükmü üretmez. Araştırma/frozen
model 3 korunur; öncelik politikası v7 yeni başlangıç oluşturur.

## Kaynak ve bileşen seçimi

Eksik IP/ağ bağlamı için RIPEstat `network-info` seçildi. IPv4/IPv6 için
sabit HTTPS uç, tek GET, 2 MiB sınırı, özgün yanıt/makbuz ve mevcut cooldown
kullanılır. ASN/prefix kayıtları RIPE RIS kaynak bağlamıdır; hedef taraması,
IP sahipliği veya zararlılık kararı değildir. Yanıttaki sorgu geri yansıtması
varsa doğrulanır; yokluğu resmî yanıt biçiminde geçerlidir. Prefix istenen
IP'yi kapsamalıdır. Canlı örnek bu davranışı doğruladı.

- [RIPEstat network-info](https://stat.ripe.net/docs/data-api/api-endpoints/network-info)
- [RIPEstat hizmet şartları](https://www.ripe.net/about-us/legal/ripestat-service-terms-and-conditions/)

18 Kasım incelemesinde ticari kullanım için yazılı izin gereksinimi bulundu;
bu teslim ticari veri izni vermez (NOTES N-022). Yeni paket/repo vendoring
gerekmedi. Mevcut sabit feedparser 6.0.14/sgmllib 2.1.0 yayıncı adaptörü,
haber deposu ve kaynak kanıtı okuyucuları yeniden kullanıldı. Dar, belirli
gösterge çıkarımı standart kütüphaneyle yapılır; serbest makale crawler'ı
veya LLM eklenmez.

## Yönetilen işler ve uyum

Yeni kaynak iş yükü/plan/sonuç sürümü 3; önceki 1/2 özgün okunur. Kuyruk
şeması 2 kalır. RIPEstat, seçili üç yayıncı ve yerel `reports` adımı mevcut
bütçe/iptal/kurtarma işçisine eklenir. En fazla beş kaynak; news başına bir
dış istek, report adımında sıfır istek. Makbuzlar özgün haber çalışması ve
rapor adayı hash'ine doğrulanır. En yeni 20 haber sınırı kısmi kapsam verir.

Bu değişiklik genel iş akışı editörü, ücretli abonelik, merkezi firma
kotası, .NET/React kullanıcı yönetimi veya LLM/TAXII sunucusu değildir.
Bunların sahipliği/sırası roadmap ve NOTES'ta korunur.

## Operasyonel kabul

`check-engine-soak.py` 1.000/5.000 varlıklı iki firmada gerçek süreçleri,
DNS/IOC/aktör bağlantılarını, kararları, vakaları, rapor ayrıştırmayı,
sayfalamayı, kuyruk/iptal ve saklama temizliği yedeğini ölçer.
`check-engine-upgrade.py` gerçek 0.163.0 kaynak kodu ile 75 → 76 geçişini,
eski v2 işin okunmasını ve önceki kodla birlikte yedekten dönüşü sınar.
Mevcut SIGTERM kabulü ayrı korunur. Eşikler test sonucuna göre gevşetilmez;
ölçüm geçerli olduğu ortam ve süreyle yayımlanır.
