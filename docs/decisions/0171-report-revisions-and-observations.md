# 0171 — Kaynak raporu sürümleri ve gözlem anlamları

Tarih: 18 Kasım 2026. Uygulama hedefi: 0.166.0, çekirdek şema 77.

## Karar

Haber ve firma aramasıyla zaten toplanan başlık/özetler, açık `reports
capture` işlemiyle sürümlü rapora alınır. Sayfa/PDF indirilmez. Kaynak
kimliği sabittir; içerik değişikliği yeni belge sürümüdür. Aynı içerik
tekrarında belge/gözlem çoğalmaz. Farklı tekrar anahtarı için yalnız işlem
makbuzu tutulur. Aynı anahtarın tekrarı ilk sonucu döndürür.

İnsan bağlantısı raporun belirli belge sürümüne ve aynı çalışma alanındaki
CTI aktör/kampanya/malware veya IOC kaydına bağlıdır. Geri çekilebilir;
yeni metne otomatik taşınmaz. Kaynak güven puanı veya IOC kararı değişmez.

Metinde geçme, yönetilen liste üyeliği ve sağlayıcının bildirdiği gözlem
ayrı türlerdir. Eski elle girilmiş IOC zamanı gerçek olay zamanı sayılmaz.
Yayın zamanı, kaynak toplama zamanı ve yerel kayıt zamanı ayrıdır;
bilinmeyen zaman null kalır. Mevcut IOC geçmişi yeniden kopyalanmaz;
denetlenmiş geçmişten okuma görünümü üretilir. Müşteri ağında gerçek
sighting toplama veya otomatik saldırı atfı bu paket değildir.

Yeni belgeler `report-document-candidates-v2` ile cümle sonundaki IP
noktalamasını işler. Eski investigation önerilerinin `report-candidates-v1`
çıktıları ve doğrulaması değişmez; saklı geçmiş yeniden yorumlanmaz.

## Kalıcılık ve sınırlar

Şema 77 eklemeli `report_journal` tablosunu ekler. Özgün kaynak tabloları,
eski investigation önerileri/kararları ve kimlikleri değişmez. Migration
açıktır, önce eski DB yedeği alınır. Geri dönüş eski kod + geçiş öncesi
yedeğin boş hedefe restore edilmesidir; yeni kaydı eski koda okutmak değildir.

Journal payload/hash/zincir/sıra/son kayıt ve domain replay ile denetlenir.
Kaynak okuması ve yazma tek transaction içindedir. Okuma hacmi önceden
sınırlandırılır; aşım kısmi başarı diye sunulmaz. Yazmalarda tekrar anahtarı,
bağlantıda beklenen kayıt sürümü; platformda ayrıca workspace fence ve
ortak writer kilidi vardır. Terminal ve JSON aynı uygulama servisini kullanır.

Araştırma grafiği/frozen model 3, öncelik v7, kaynak işi v3 ve mevcut
`reports` iş adımının eski aday makbuzları değişmez. Yeni model ayrı
`reports.*` / `observations.list` işlemleriyle okunur. Genel çıkarım, geniş
STIX/TAXII, LLM ve web paneli ayrı kalır.

## Kabul

İçerik tekrar/değişim/geri dönüşü, tarih belirsizliği, eski sürüme bağlı
insan kararı, kaynak hatası sonrası eski belge, IOC zaman anlamları,
eşzamanlı yazma/sayfalama, bozuk journal, firma sınırı, migration/yedek ve
CLI/JSON eşliği doğrulanmadan teslim tamamlanmış sayılmaz.
