# 0149 — Tavily ile firma ve tedarikçi içerik keşfi

Tarih: 15 Kasım 2026. Durum: uygulandı, 0.144.0 / şema 67.

## İhtiyaç

Kullanıcı genel yayın akışlarını okumaya ek olarak kendi firmasının ve
kayıtlı tedarikçilerinin adını internette aramak istiyor. Ücretli kaynaklar
da değerlendirildi; kullanıcı ücretsiz kredili Tavily ile başlamayı seçti.

## Karar

Tavily, `MentionSource` arkasında isteğe bağlı tek HTTP kaynak adaptörüdür.
Resmî `/search` protokolü stdlib HTTPS/JSON ile kullanılır; tek endpoint
için ilave SDK bağımlılığı gerekmiyor. Dış arama motoru yeniden yazılmaz.
Aynı Tavily protokolü için SDK/HTTP uygulaması portun arkasında değiştirilebilir.
Başka sağlayıcı eklemek kaynak kimliği, sorgu kapsamı ve engine namespace'i
için açık sözleşme ve uyumluluk çalışması gerektirir; mevcut kanıt değiştirilmez.

Her açık komut tek hedef ve tek `basic` isteği gönderir. `auto_parameters`,
LLM cevabı, tam içerik ve görsel çıktıları kapalıdır. Tekrar denemesi yoktur;
cevapsız istek bile kredi tüketmiş olabilir. Kaynak beyanı olmayan kredi
sıfır sayılmaz. Kuruluş/tedarikçi tanımı denetlenmiş yerel kayıt alanından,
yazıcı kilidi altında okunur. Firma adına doğrudan arama ayrıca mümkündür.

Anahtar özel kullanıcı konumuna görünmez girişle kaydedilir veya ortamdan
alınır. Kaynak, veritabanı ve engine çıktı alanlarında anahtar yoktur.
Yönlendirme, kontrolsüz proxy ve uzak hata gövdesi aktarımı engellenir.
Toplanan sonuç URL'lerine otomatik istek yapılmaz.

Şema 67 tek eklemeli `mentions_runs` tablosu ekler. Sorgu/hedef ve tam sınırlı
sonuç görüntüsü, SHA-256 ve zincir özetiyle atomik yazılır. Görünüm geçmişten
yeniden kurulur; ayrı güncel projeksiyon tablosu tutulmaz. Kimlik sorgu
kapsamı + URL'dir; kapsam adı/domain/konu/sınır değişimini içerir. Kaynak
puanı anlamlı değişim özetine girmez. Önceki başarılı sonuçlar hata veya
arama penceresinden çıkma nedeniyle silinmez. Tarihî kanıt güncel firma
tanımıyla yeniden yazılmaz. Sınırlar ve açık yedekli geçiş veri kaybını
önler; hash zinciri imzalı/adli doğrulama iddiası değildir.

Genel aramaya `mention` on ikinci tür olarak eklenir. Eski kayıtlı aramaların
somut 10/11 tür kapsamı korunur. `record.get` kaynak namespace'i `tavily`
olan `company_mention` kanıtını salt okunur açar. Dört v1 işlem korunur.

## Sınırlar ve kabul

Sonuç adaydır; görünür ad/domain eşleşmesi gerekçesi gösterilir, ihlal
kararı verilmez. Firma domaini yayıncı filtresi olarak kullanılmaz;
üçüncü taraf haberlerini aramaya dahil eden sorgu terimidir.
Kuruluş–tedarikçi otomatik bağlama, müşteri yetki ayrımı, zamanlanmış
toplu toplama, makale indirme ve LLM değerlendirmesi eklenmez.

Kabul testleri tek istek/payload, anahtar gizliliği, yönlendirme, kaynak
hataları/boş başarı, tekrar/diff, hedef tanımı değişimi, salt okunur
arama/engine, eski izleme kapsamı ve şema66→67 yedekten dönüşü kapsar.
Gerçek anahtar olmadan canlı hizmet başarısı iddia edilmez.

[Kullanım](../MENTIONS.md), [API](https://docs.tavily.com/documentation/api-reference/endpoint/search),
[kredi modeli](https://docs.tavily.com/documentation/api-credits),
[saklama koşulları](https://help.tavily.com/articles/1612400809-storing-caching-retaining-output).
