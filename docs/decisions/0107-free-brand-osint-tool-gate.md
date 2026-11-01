# 0107 — Ücretsiz marka OSINT aracı kabul kapısı

**Durum:** Kabul edildi  
**Tarih:** 31 Ekim 2026  
**Sürüm:** 0.109.0

> Sonraki durum: theHarvester'ın ertelenen P0 seçeneği 0.119.0'da yalnız
> Common Crawl ve Wayback Archive için kabul edilmiştir. Güncel sınırlar
> [0117 numaralı karardadır](0117-bounded-theharvester-archive-discovery.md).

## Problem

Sosyal kullanıcı adı, e-posta, telefon ve domain keşfi için birden fazla açık kaynak araç vardır. Bunların tamamını XTI içine kopyalamak tekrar eden ağ trafiği, farklı lisans yükümlülükleri, kişisel veri birikimi ve çekirdeğin dış araçların değişken çıktısına bağlanması riskini oluşturur. İlk geniş marka dilimi için tek, ücretsiz ve sınırlanabilir bir kaynak seçilmelidir.

## Karar

`free-brand-osint-tool-gate-v1`, adayları doğrulanmış upstream, etkin bakım, ücretsiz/hesapsız temel kullanım, kararlı JSON/NDJSON sonucu, sınırlı çalışma, açık kod lisansı, hesap-kurtarma yoklaması kullanmama ve güncel marka kapsamına uyum ölçütleriyle çevrimdışı karşılaştırır.

Maigret'in yalnız açıkça verilen marka kullanıcı adlarını seçili sitelerde arayan ayrı CLI adaptörü seçilmiştir. Adaptör sabit sürüm kullanacak, yalnız `simple` veya NDJSON sonucu kabul edecek ve harici çıktıyı XTI modeline girmeden doğrulayacaktır. Maigret kaynak kodu XTI deposuna kopyalanmayacaktır.

Sherlock aynı veri ailesinde ikinci trafik ve tekrar sonuç üreteceği, ayrıca seçilen sonuç JSON sözleşmesini sağlamadığı için ertelenmiştir. theHarvester mevcut domain keşfinin çoğuyla çakışır; ancak ileride kanıtlanmış bir pasif kaynak boşluğu için yalnız P0 kaynaklarıyla ayrı değerlendirilebilir. Web-Check'in tamamı mevcut dış yüzey kontrollerini ve ertelenmiş web panelini tekrar ettiği için eklenmez.

Holehe ve telefon hesabı yoklayan Ignorant mevcut pasif OSINT profiline alınmaz. Bu araçlar üçüncü taraf hesap/kurtarma davranışlarından yararlanır ve e-posta/telefon gibi kişisel veriler üzerinde hizmet koşulu, oran sınırı ve olası yan etki oluşturur. Kullanıcının belirttiği `Ignis` adıyla kesin upstream doğrulanamadığı için başka bir proje varsayılıp entegre edilmez.

## Güvenlik ve veri sınırı

İlk canlı adaptörde Tor/I2P, proxy, Cloudflare aşma, yapay zekâ, özyinelemeli kişi profilleme ve NSFW arama kapalıdır. Yalnız küçük sabit site listesi, süre sınırı ve kayıt sınırı kullanılır. Sonuç önce yazmasız gösterilir. Aynı kullanıcı adına sahip profil aynı kişi, marka veya taklit hesabı sayılmaz; insan incelemesi gerekir.

## Sonuç

0.109.0 yalnız kabul raporunu ekler; internet isteği, araç kurulumu, canlı kullanıcı adı araması, veri yazımı veya şema değişikliği yapmaz. Sonraki dilim, harici aracın yokluğunu ve sürüm/çıktı uyumsuzluğunu güvenli hata olarak veren yazmasız Maigret önizlemesidir.
