# 0168 — Tedarikçi izleme ve inceleme bağlamını ortak araştırmada kullanmak

Tarih: 18 Kasım 2026. Uygulama: 0.163.0. Durum: uygulandı; kabul sonucu
[kabul belgesinde](../ACCEPTANCE_REVIEW.md) ayrıca kaydedilir.

## İhtiyaç

Tedarikçi envanteri ve insan onaylı bağımlılık araştırmada vardı; kaynak
iddiası adayları, yerel izleme karşılaştırmaları ve inceleme kartı ayrı
komutlarda kalıyordu. Bunları aynı kökten erişilebilir yapmak gerekiyor.
İddia ile doğrulanmış ihlal ve yerel bildirim ile kaynak olayı ayrı kalmalı.

## Karar

- Domain → insan tarafından bağlı tedarikçi → kaynak iddiası / izleme /
  hesaplanan inceleme kartı, mevcut iki adımlık araştırmaya eklenir.
  Tedarikçinin kayıtlı ana domaininden de aynı bağlama ulaşılır.
- `StoredSupplierContext` mevcut araştırmanın tek salt okunur SQLite
  transaction'ını kullanır. Yeni bağlantı, veri toplama, yazma, bildirim
  veya tablo yoktur. Her firma kendi veritabanıyla sınırlıdır.
- ThreatCluster/RansomLook tam ad/domain eşleştirmesi ile kart kuralları
  domain katmanında ortak fonksiyonlardır; mevcut komutlar da bunları
  kullanır. Tek tedarikçi filtresi aynı isimli diğer etkin tedarikçilerin
  belirsizlik sayısını düşürmez. HIBP kamu metaverisi yalnız izleme
  bağlamıdır; ransomware iddiası veya kişisel hesap sızıntısı yapılmaz.
- Kaynak başına son deneme ve son başarılı yanıt ayrılır. Başarısız
  yenileme eski kanıtı silmez. Kaynak kayıtları ve run kimlikleri korunur;
  kart hesaplanır, ayrı kalıcı risk kaydıymış gibi sunulmaz.
- İzleme denetleyicisi isteğe bağlı seçili tedarikçi okuması kazanır.
  Kaynak/kimlik/sonuç/atomik bildirim denetimleri korunur; yazma yolları
  eskisi gibi bütün izleme geçmişini denetler. Küresel olay sırası boşluğu
  seçili okumada da tespit edilir.
- Tarihî izleme kimliği ve aynı-ad sayısı, özgün tedarikçi olay sınırından
  yeniden kurulur. Bu nedenle aynı firma içindeki tam tedarikçi kimlik
  geçmişi gerekir. Diğer tedarikçilerin izleme payload'ları yüklenmez.
- Kaynak katalogları kendi denetleyicileriyle bir kez doğrulanır ve
  paylaşılır. Yüklemeden önce bütün sütunların byte/satır ölçümü yapılır.
  İstek başına 20.000 bağlam satırı, 16 MiB saklı içerik ve 2.000.000
  muhafazakâr yeniden oynatma iş birimi vardır. Sonuncusu CPU süresi
  garantisi değildir. Sınırda doğrulanmamış/tamamlanmamış kart sunulmaz;
  mevcut envanter/karar kanıtı ve kısmi kapsam görünür kalır.
- Tedarikçi başına 150 iddia adayı ve her düğümde en fazla 52 kanıt
  gösterilir. Kart toplamı gösterimden önce hesaplanır. Bütün araştırmanın
  100 düğüm / 200 bağlantı sınırı ayrıca geçerlidir. Detay komutları
  özgün izleme çalışmasına ve bağımsız modüle gider.
- İzleme kapalı, tedarikçi pasif veya kimlik dönemi değişmişse eski sonuç
  `historical_scope` olur. İlk/yeniden açılmış karşılaştırma, eşleşme sıfır
  olsa bile sessiz başlangıçtır. Kaynaktan çıkarılma ihlalin çözüldüğü
  anlamına gelmez. Aynı adlı kurumlar otomatik birleştirilmez.

## Sözleşme ve uyum

JSON biçimi değişmez; yeni düğüm/ilişki/kanıt türleri mevcut model 3
alanlarını kullanır. Öncelik politikası v6 olur; eski politika/model
incelemeleri yeniden hesaplanmadan okunur. İlk v6 kaydı politika
başlangıcıdır. DB 75, kuyruk 2, engine/platform zarfı v1 korunur.

Bu değişiklik LLM, geniş STIX/TAXII, merkezi kota, kullanıcı/rol yönetimi
veya yeni harici kaynak eklemez. Kaynak koşullarının ticari kullanım
değerlendirmesi mevcut [NOTES.md](../../NOTES.md) kayıtlarında sürer.
