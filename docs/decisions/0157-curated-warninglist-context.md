# 0157 — Seçilmiş MISP listelerinden kaynaklı bağlam

17 Kasım 2026 · 0.153.0 · çekirdek şema 73.

MTR-03'ün ilk dilimi, MISP warninglists verisinden dört listeyi araştırma
bağlamına katmaktır: Cloudflare, RFC1918, RFC3849, RFC6761. Resmî repo ve
seçili veri koşulları commit düzeyinde incelendi. README değişimi yeni
inceleme gerektirir; tüm depo veya sonraki listeler otomatik kabul edilmez.
[Kaynak kaydı ve sınırlar](../WARNINGLISTS.md#kaynak-maliyet-ve-işletim-sınırları).

[PyMISPWarningLists](https://github.com/MISP/PyMISPWarningLists/blob/main/LICENSE)
kütüphanesinin BSD-3-Clause koşulları ile warninglist
verisinin CC0-1.0 beyanı ayrı değerlendirildi. İlk dar kapsam için yeni
bağımlılık veya MISP sunucusu gerekmedi: upstream veriyi alan küçük HTTP
adaptörü, doğrulayan domain kuralları ve depolama portu kullanılır.
Bu, kaynak verisinin entegrasyonudur; geniş MISP işlevleri uygulanmış sayılmaz.

`WarninglistService` kaynak ve depo portlarına bağlıdır. HTTP katmanı
commit'i bir kez çözer, aynı sürümün seçili dosyalarını sınırlarla alır.
Domain parser CIDR ve hostname türlerini kesin kurallarla işler. Özgün
üyeler korunur, eşleşme için normalleştirilmiş değerler ayrıdır. İndirme
sağlayıcıya sorgulanan domain/IP'yi göndermez. Lookup ağ kullanmaz.

Şema 73 içerik SHA-256'sıyla tekilleşmiş özgün JSON ve eklemeli yenileme
makbuzlarını iki tabloda tutar. Kaynak kimliği çalışma kaydındadır; farklı
listelerde aynı byte'lar varsa içerik ortak saklanabilir, kaynak atfı
birleşmez. Liste başına başarılı içerik ve makbuzu tek transaction'dır.
Başarısız indirme/sürüm gerilemesi eski iyi içeriği korur. Dört liste tek
atomik işlem değildir; kısmi başarı ve önceki sürümden kalan liste görünür.
Sert süreç kesintisinde yazılmamış deneme için receipt garantisi verilmez.

Mevcut açık, yedekli migration yolu kullanılır. Önceki tablo/satır/rowid ve
kanıtlar korunur. Boş aşamalanmış yeni tabloların doğrulanması önceki şema
fixture'larıyla uyumludur; eski sürüm numarası altında dolu yeni tablo
reddedilir. Başarısız geçiş transaction'ı geri alınır, yedek tutulur.

Araştırma adaptörü listeleri DNS/IOC/CTI ile aynı read transaction'da alır.
Yeni alanlar `research.show` v1'e açıkça serileştirilir. Liste kesiti ve
güncelliği sayfa kimliğine katılır; var olan düğüm/bağ anlamı değişmez.
Liste eşleşmesi IOC, ilişki, güvenlik hükmü veya alarm kapatma üretmez.

`warninglists.status/lookup/run.get` firma kapsamlı salt okunur v1
işlemlerdir. CLI aynı servisi kullanır; yenileme işletici CLI'sındadır.
Başka/kayıtsız firma listesine otomatik dönüş yoktur. Kullanıcı/oturum,
.NET istemcisi ve PostgreSQL geçişi bu teslimin kapsamında değildir.
URL/hash kaynakları, otomatik orkestrasyon, LLM ve geniş STIX/TAXII sonraki işlerdir.
