# Yeni kaynak değerlendirme notu

**14 Kasım 2026 — yeni sağlayıcı/adaptör seçilmedi.**

Bu dilim kayıtlı domain için eldeki yerel kaynak kanıtını ölçer. Yeni kaynak
isteği, anahtar/kota/lisans araştırması veya aktif hedef bağlantısı yapılmaz.
Çalışan sürüme teslim durumu `docs/STATUS.md` üzerinden takip edilir.

## Ölçümün anlattığı

- Alt alan keşfinde açık `provider` alanına bağlı aday/kaynak kayıtları.
- Marka aramasında aynı domain + kural sürümü + typos grubundaki tek hedefli,
  sonucu saklanmış denemelerin aday domainleri.
- Kaynak başına farklı, ortak ve yalnız o kaynakta yerel kaydı bulunan adresler;
  gerçek aday/kanıt/deneme/iş kimlikleriyle ayrıntı sayfaları.
- Tamamlanma payı ve terminal deneme paydası. Çalışan/bekleyen işler paydaya
  girmez; çok hedefli denemeler ve sonucu olmayan denemeler açıkça ayrılır.

A={a,b}, B={b,c} test verisinde birleşim 3, her kaynağın farklı aday sayısı 2,
ortak 1 ve yalnız-kaynak katkısı 1 doğrulandı. Bu **sentetik kabul kanıtıdır**;
gerçek kullanıcı verisinde bir kaynağın daha başarılı olduğunun ölçümü değildir.
Tekrarlanan aynı kanıt adres sayısını artırmaz; insan kapsam kararları korunur.

## Neden yeni adaptör seçilmedi?

Kaynaklardan biri hiç tamamlanmamışsa karşılaştırma `insufficient_history`
kalır. Her ikisinde tam çalışma bulunsa da sonuç yalnız geçmiş yerel kümeleri
karşılaştırır. Çalıştırılma sayısı/zamanı ve kapsam farkları görünürdür;
ölçülen ground truth, kaçırılan gerçek tehdit sayısı veya bağımsız internet
kapsama oranı yoktur. Bu nedenle tekil yerel adres farkı otomatik üstünlük ya
da sağlayıcı değiştirme gerekçesi yapılmaz.

Common Crawl erişim eksikliği tamamlanmış boş sonuç değildir ve bu teslim
bu dış erişim sorununu giderdiğini iddia etmez. Aynı arşive farklı araçla
ulaşmak bağımsız bir veri kaynağı eklemek sayılmaz. theHarvester kaynak
başvuruları korunur; uyarı metni ayrıştırılarak Common Crawl/Wayback için
ayrı çalışma başarı oranı üretilmez.

## Sonraki adaptör için karar kapısı

Gerçek kullanımda somut bir bilgi boşluğu belirlendiğinde, aday sağlayıcının
bu boşluğa bağımsız katkısı küçük pasif örneklemle gösterilmeli. Ardından
resmî endpoint, güncel erişim/anahtar/kota koşulları, lisans ve veri kullanım
izni, pasif kapsam, makine-okunur hata/boş-sonuç ayrımı ve sürdürülebilir
kurulum sözleşmesi doğrulanmalı. Bu inceleme yapılmadan herhangi bir kaynak
"ücretsiz ve sınırsız" diye tanımlanmaz. Zorunlu ücretli API eklenmez.

Bu dilim mevcut theHarvester tekrar toplama düzeltmesini yeniden uygulamaz.
Kaynak katkısı testleri aynı sabit kanıtın tekrarında toplamın değişmediğini
kontrol eder; parser/erişim davranışının ayrı test ve kaynak durumu sürer.
