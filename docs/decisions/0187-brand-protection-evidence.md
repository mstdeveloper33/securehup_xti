# ADR 0187 — Marka taklidi için sürümlü kanıt ve çevrimdışı görüntüleme

21 Kasım 2026. Kabul edilen uygulama; canlı/işletim kapsamı P03 teslim
kartında ayrıca kayıtlıdır.

Marka kimliği ve izleme kapsamı sürümlenir. İsim, domain veya logo eşleşmesi
otomatik taklit kararı değildir. Resmî uygulama kimliği ve yayıncı farkı,
statik görünüm, logo, metin ve sayfa/form/script parmak izi ayrı ipuçlarıdır.
İnceleme kararı adayın gözlem/kanıt sürümüne bağlı kalır. Veri değişince
önceki insan kararı silinmez; güncel kararmış gibi gösterilmez.

`BrandProtectionService` küçük repository/source portlarına bağlıdır.
Domain katmanı tarayıcı, HTTP, SQLite veya terminal yüklemez. Terminal,
firma JSON ve kalıcı kaynak işi aynı servisi kullanır. Kaynak iş modeli10,
ortak kuyruk4, çekirdek91, dış sözleşme1; önceki kuyruk makbuzları okunur.

Kaynak adaptörü kamu HTTPS isteklerini DNS sonrası genel IP'ye sabitleyen
mevcut taşıyıcıdan geçirir. Apple Search API ve Google Play sayfaları
bölge/pencere sınırıyla değerlendirilir. google-play-scraper1.2.7'nin import
sırasında TLS varsayılanını değiştirmesi nedeniyle kitaplık yalnız ayrı,
ağa kapalı parser sürecinde kullanılır. Motorun TLS doğrulaması korunur.

Chromium'un ağ erişimi kapalıdır. İzinli taşıyıcıyla alınmış HTML/CSS/resim
haritası route üzerinden sunulur; JavaScript, form, frame ve servis worker
açılmaz. Yalnız statik görünüm kanıtlanır. SVG de bu ayrı görüntüleyicide
resim olarak rasterleştirilir; XML harici varlık çözücü eklenmez. Son PNG
Pillow ile piksel/boyut sınırından geçer; ImageHashpHash/dHash/colorhash ve
SHA256 oluşturulur. Boş görseller yüksek benzerlik kararı vermez.

Resmî sayfadan alınan her görsel marka logosu sayılmaz. Açıkça verilen
logo URL'leri önceliklidir; aksi halde site ikonu, marka adıyla etiketli
görsel veya genel logo dosya adı referans alınır. İş ortağı/ürün görselleri
sayfa görünümünde bulunabilir ama marka logo kümesine otomatik eklenmez.
Bu seçim de doğrulanmış logo sahipliği değil, açıklanabilir kaynak ipucudur.

Kit/aktör atfı veya APK/IPA analizi çıkarılmaz. Ekran görüntüsündeki yazı
OCR ile maskelenmiş sayılmaz. Metin/URL, Betterleaks kontrolünü geçmezse
saklanmaz. İndeks ve vaka kopyaları kaynak iddiası/analist kararı ayrımını
korur; hak/retention kararları N-046'dadır.

Aynı kanıt/görsel gövdesi SHA ile tekilleşir. İndeksli güncel adaylar,
değişmez gövdeler, incelemeler ve bildirimler ayrıdır. Değişiklik/inbox/çalışma
makbuzu tek işlemde kaydedilir. Kaynak hatası eski kanıtı silmez. Yeniden
kontrol cursor'u sadece tamamlanan kontrol dilimi için ilerler. Tek tur
bütçesi bütün geçmişe tavan konması anlamına gelmez. Liste yanıtlarında
kayıt ve bayt sınırı, devam için sequence cursor'u vardır.

Kaynak işi kimlik ve izleme sürümünü dondurur. Core commit sonrası kuyruk
kesilirse makbuz yeniden kullanılır; fazladan ağ oluşmaz. Belirsiz çalışan
kayıt için açık kurtarma gerekir. İptal sonraki adımı durdurur; gönderilmiş
isteği geri almaz. Maigret/Sherlock'un bütün HTTP iç trafiği ölçülmüş sayılmaz.

Bağımlılıklar PyPI wheel SHA256 ve tam sürümlerle kurulur. Playwright SDK
ve Chromium revision sabittir; tarayıcı arşivinin ayrı upstream SHA256
pini yoktur. Resmî TLS indirme sonrası yerel binary SHA256 ve çevrimdışı
smoke makbuzu saklanır. Mevcut journal/dizin-kimliği mekanizmasıyla tarayıcı
kurulumu geri alınabilir; önceki dizin silinmez. Linux sistem kitaplıkları
ve gerçek Linux kabulü ayrıca doğrulanır.

Şema90→91 geçişi eski vaka satır/rowid'lerini korur ve yedek üretir. Eski
üretici yeni şemayı reddeder; geri dönüş göç öncesi yedeğin boş hedefe
alınmasıyla olur. Fotoğraf kanıtı DB yedeğine dahildir.
