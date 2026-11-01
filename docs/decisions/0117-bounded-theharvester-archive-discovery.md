# 0117 — Sınırlı theHarvester arşiv keşfi

**Durum:** Kabul edildi  
**Tarih:** 31 Ekim 2026

## Bağlam

crt.sh yalnız yayımlanmış sertifika kayıtlarını görür. Common Crawl ve Wayback
Archive, geçmiş web adreslerinden farklı pasif alt alan adı kanıtları
sağlayabilir. theHarvester bu kaynakları ortak bir sonuç sözleşmesiyle
çalıştırabiliyor; fakat aynı araç API anahtarı isteyen kaynakları, DNS
etkileşimlerini ve doğrudan hedef işlemlerini de destekliyor. XTI bütün aracı
serbest biçimde çalıştıramaz.

Güncel upstream Python 3.14 ve `uv` ister. Otomasyon için JSONL sonuç verir ve
kaynak çalışmalarını ayrı durum/sayaçlarla açıklar. Kod GPL-2.0-only
lisanslıdır. XTI bu kodu çekirdeğe kopyalamaz veya kendi Python bağımlılığı
olarak dağıtmaz.

## Karar

- Upstream tam `6790b147f52309e4eee22ed941db1d285ab2ec23` commit'ine sabitlenir.
- Kullanıcı aracı açıkça `./scripts/setup-harvester` ile proje içindeki
  `.tools/theharvester` alanına kurar. Kurulum için önceden `git` ve `uv`
  bulunmalıdır; XTI kurulum betiği uzaktan kabuk betiği çalıştırmaz.
- Adaptör yalnız `commoncrawl,waybackarchive`, sonuç sınırı 250, kaynak işçisi 1,
  sessiz çalışma ve JSONL raporu içeren sabit argüman listesini kullanır.
- DNS çözümleme, DNS brute force, ekran görüntüsü, takeover, API scan, sanal
  host, port/servis kontrolü, proxy/Tor, e-posta ve kişi sonuçları açılmaz.
- Ayrı süreç geçici `HOME` ve veri klasörüyle çalışır. Kullanıcının
  theHarvester ayarı veya çalışma veritabanı okunmaz; işlem bitince geçici alan
  kaldırılır.
- Ana süreç JSONL'nin tam alan kümesini, tekrar alanlarını, UTC zamanlarını,
  kaynak kimlik/durum/sayaçlarını, boş aktif işlem listesini ve yalnız kayıtlı
  kökün kanonik kesin alt alan adlarını doğrular. Beklenmeyen alan, sonuç türü,
  aktif işlem, kapsam dışı ad veya sayaç uyuşmazlığı bütün çalışmayı reddeder.
- Common Crawl ve Wayback Archive gözlemleri aynı hostname için ayrı kaynak
  kanıtlarıdır. Sonuç mevcut `surface_candidates`, kaynak kanıtı, çalışma
  geçmişi ve tekil yerel bildirim akışını kullanır.
- Aday, sahiplik veya güncel erişilebilirlik kararı değildir. Hedef hostname'e
  DNS, TLS veya HTTP isteği gönderilmez.

## Veri ve geçiş

Şema 50→51 yalnız `surface_candidate_sources.provider` ve
`surface_discovery_runs.provider` denetimlerine `theharvester` değerini ekler.
Mevcut crt.sh satırları ve çalışma sıra numaraları işlemsel olarak kopyalanır.
Geçişten önce doğrulanmış şema 50 yedeği alınır; hata halinde canlı veritabanı
şema 50'de kalır. Eski veriden theHarvester çalışması uydurulmaz.

## Sonuçlar

İkinci pasif kanıt ailesi mevcut aday/karar modelini çoğaltmadan kullanılabilir.
Bunun karşılığında ayrı Python 3.14 araç ortamı ve upstream JSONL sözleşmesi
bakım yükü oluşur. Commit veya sözleşme değişikliği kendiliğinden kabul edilmez;
yeni inceleme, test ve sabitleme gerekir. Arşiv sağlayıcılarının erişilebilirliği
ve kullanım koşulları XTI'ın kontrolünde değildir.
