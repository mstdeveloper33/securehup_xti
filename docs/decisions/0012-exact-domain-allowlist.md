# 0012 — İzlenen varlığa bağlı tam alan adı istisnası

**Tarih:** 29 Ekim 2026 · **Durum:** 0.12.0'da uygulandı.

## Sorun

Benzer marka, ek sözcük ve Unicode kuralları meşru iş ortağı veya kampanya adreslerini de aday yapabilir. Kullanıcının aynı bilinen sonucu her aramada yeniden incelemesi gerekir. Yalnız bulguyu `dismissed` yapmak alarm geçmişini kapatır fakat sonraki kural sürümü veya ayrı bulgu kimliği için açık bir tespit politikası oluşturmaz. Geniş marka, suffix veya joker istisnası ise gerçek taklitleri sessizce kaçırabilir.

## Karar

İstisna yalnız `(asset_id, canonical_candidate_domain)` çiftidir. Tam adayın mevcut eşleştirme kurallarında seçilen kayıtlı varlık için gerçekten aday olması zorunludur. Joker, suffix, anahtar kelime, bütün marka veya ilgisiz adres istisnası kabul edilmez. Aynı aday başka bir varlıkla eşleşiyorsa o değerlendirme devam eder.

Unicode girdi paketlenmiş sürümlü UTS #46 profiliyle kanonik ASCII A-label'a çevrilir. Böylece U-label ve Punycode yazımı aynı politika kimliğine gider. İstisna kural sürümüne bağlanmaz; tam adres ve varlık çifti etkin kaldığı sürece sonraki eşleştirme sürümündeki aynı aday da bastırılır.

Her kayıt gerekçe, ilk oluşturma zamanı, güncel değişim zamanı ve etkinlik taşır. `added`, `revoked` ve `reactivated` olayları ayrı append-only geçmişte tutulur. Etkin kaydı tekrar eklemek yan etkisizdir. Geri alma kaydı silmez; yeniden etkinleştirme aynı kimliği kullanır. Kullanıcıya kalıcı silme komutu verilmez.

Arama ve içe aktarma servisleri etkin çiftleri aday listesinden çıkarır. SQLite bulgu adaptörü aynı kontrolü gözlem/bulgu transaction'ı içinde yeniden uygular. Bu ikinci savunma, uygulama kontrolü ile yazma arasındaki yarışı ve yeni bir çağrı yolunun filtreyi unutmasını kapsar. İstisna eşleşse bile ham gözlem kaydedilir; yeni bulgu, gözlem–bulgu bağlantısı ve bildirim oluşturulmaz.

İstisna geriye dönük silme veya düzenleme yapmaz. Önceden var olan bulgu, kaynak kanıtı, inceleme kararı, `last_seen_at` ve bildirim aynen kalır. İstisna sırasında gelen yeni gözlem bağlantısız kalır. Geri alma sonrasında kaynak yeniden işlendiğinde aynı gözlem tekilleştirilerek mevcut veya yeni bulguya bağlanabilir.

## Veri geçişi ve kurtarma

Şema 8, `allowlist_entries` ve `allowlist_events` tablolarını, tam çift tekilliğini, yabancı anahtarları ve arama indekslerini ekler. Şema 1–7 açık `migrate` gerektirir. Yazma kilidi altında önce özgün sürümde doğrulanabilir yedek alınır, DDL tek transaction içinde uygulanır ve bütünlük yeniden doğrulanır. Hata ana veritabanını önceki sürümde bırakır; alınmış kurtarma yedeği korunur. Eski bulgu kararlarından otomatik istisna çıkarılmaz. Güncel yedek ve boş hedefe restore iki tabloyu ve geçmişi kapsar.

## Sonuçlar ve sınırlar

- Yanlış alarmı dar ve açıklanabilir biçimde susturur; ham kaynak verisini kaybetmez.
- Politika kullanıcı doğrulamasına dayanır; adres sahipliği veya zararsızlık kanıtı değildir.
- Meşru adres ele geçirilirse etkin istisna yeni alarmı engelleyebilir. Bu nedenle gerekçe/geçmiş görünür ve geri alma açıktır.
- Süre bitimli istisna 0.16.0'da [ayrı kararla](0016-expiring-exact-domain-allowlist.md) eklendi; toplu içe aktarma, kullanıcı/tenant kapsamı ve onay iş akışı hâlâ yoktur.
- Mevcut bulguyu istisna yapmak onu otomatik kapatmaz veya bildirimini okundu yapmaz.
- Sürümlü sentetik precision/recall ve yanlış alarm kümesi 0.13.0'da eklendi; gerçek kullanım etiketleri ve istatistiksel ölçüm hâlâ ayrı iştir.
