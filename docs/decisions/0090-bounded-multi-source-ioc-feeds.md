# 0090 — Sınırlı çok kaynaklı IOC beslemeleri

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

İlk otomatik IOC kaynağı Feodo Tracker yalnız botnet C2 IP'leri sağlıyordu. Domain tarafında ikinci, bağımsız, anahtarsız ve ileride ürünleşmeyi hukuken engellemeyen bir kaynak gerekiyordu.

OpenPhish Community Feed ücretsizdir ancak kullanım koşulları kişisel/bağımsız araştırmayla sınırlıdır ve izinsiz ürün geliştirme ile kurumsal operasyon kullanımını yasaklar. URLhaus toplu indirmeleri ücretsiz Auth-Key gerektirir. Spamhaus DROP serbesttir ancak tek IP değil ağ aralığı taşır; mevcut kesin IOC modeliyle anlam kaybı olmadan birleştirilemez.

CERT Polska Warning List herkes tarafından, ticari amaç dahil kullanılabilir. Resmî v2 arayüzü etkin domainlerin tam metin listelerini ve son bir ayda eklenen etkin domainler için daha küçük uBlock listesini sunar. Tam etkin liste inceleme sırasında yaklaşık 125 bin, son-ay listesi yaklaşık 18 bin domain içeriyordu.

## Karar

- İkinci kaynak `certpl-warning-list` kimliğiyle CERT Polska'nın `domains_ublock.txt` son-ay etkin domain akışıdır.
- Bu dilim küresel veya tarihsel tam phishing kapsamı diye sunulmaz; Polonya odaklı ve son-ay sınırlı olduğu her çıktıda belgelenir.
- Yalnız açık `ioc sync --source certpl` veya `analyze DOMAIN --refresh-ioc certpl` komutu ağ kullanır. Arka plan zamanlaması yoktur.
- Sabit HTTPS adresi, yönlendirme reddi, kimlik sıkıştırması, `text/plain`, 30 saniye, 8 MiB ve 50 bin domain sınırı uygulanır.
- Başlık, sürüm, sona erme ve ana sayfa satırları; UTF-8/LF biçimi; her domainin kanonik değeri; tekrarlar ve liste zamanının en fazla 48 saat eski olması bütün snapshot kabulünden önce doğrulanır.
- Kaynak hatası veya bozuk biçim geçerli boş liste sayılmaz. Önceki etkin iddialar korunur. Yalnız başarılı tam snapshot üyeliği ekleme, yeniden etkinleştirme ve geri çekme üretir.
- Feodo'ya özel SQLite kodu, sabit `CtiFeedPolicy` nesneleriyle kaynak kimliği, URL, güven, tür, kayıt sınırı, başvuru biçimi, zaman ve geçmiş politikasını ayıracak şekilde genelleştirilir.
- Kaynaklar aynı kanonik IOC ana kaydını paylaşabilir fakat bağımsız kaynak iddiaları ve çalışma geçmişleri birbirini ezmez.
- CERT snapshot'ında değişmeyen binlerce üyelik için öğe satırı tekrar yazılmaz. Tam içerik SHA-256 özeti, toplam/değişmeyen sayısı ve çalışma kaydı korunur; öğe geçmişi yalnız değişiklikleri taşır. Feodo'nun mevcut ayrıntılı davranışı korunur.
- IOC/CTI salt-okunur kapsam sınırı 50 bin kayda yükseltilir. STIX dosyasında ayrıca 32 MiB son çıktı sınırı korunur.

## Sonuçlar

Kişisel kurulum, ayrı bir domain kaynağını anahtar veya ücret olmadan kullanabilir. İzlenen kök domain, bu köke bağlı kayıtlı marka/domain adayları ve kayıtlı IP'lerde kesin eşleşme aynı birleşik analizde görünür. Aday görünüm sınırı IOC kapsamını daraltmaz. Bir listede yer almak otomatik zararlılık, etkilenme veya engelleme kararı değildir.

Son-ay diliminden yaş nedeniyle çıkan bir domain, CERT kaynağı açısından geri çekilir; bu, domainin güvenli olduğuna dair hüküm değildir. Başka kaynak iddiaları etkilenmez. Tam CERT arşivi, OpenPhish, URLhaus, ağ aralığı IOC'leri ve otomatik zamanlama bu kararın kapsamında değildir.

## Dayanaklar

- CERT Polska liste açıklaması ve kullanım kuralları: https://cert.pl/lista-ostrzezen/
- CERT Polska API v2 biçimi: https://hole.cert.pl/schema/certpl_lista_ostrzezen_api_v2.pdf
- OpenPhish kullanım koşulları: https://openphish.com/terms.html
- URLhaus Community API kimlik doğrulama koşulu: https://urlhaus.abuse.ch/api/
- Spamhaus DROP veri biçimi: https://www.spamhaus.org/blocklists/do-not-route-or-peer/
