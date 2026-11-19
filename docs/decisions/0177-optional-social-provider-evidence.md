# 0177 — İsteğe bağlı, kalıcı sosyal sağlayıcı kanıtı

Tarih: 19 Kasım 2026 · Durum: Uygulandı, canlı kabul bekliyor · Sürüm: 0.172.0 / şema82.

Kullanıcı Bright Data bağlantısını seçti. İlk kapsam, mevcut sosyal keşfin
kaynak destekli LinkedIn şirket profillerine ek kanıttır. Provider API
başarısı açık sayfa doğrulaması veya marka sahipliği değildir; eski
`social-discovery-v1` makbuzları ve kararları değiştirilmez.

`SocialEnrichmentService` küçük depo/sağlayıcı portlarına bağlıdır. Domain
kuralları seçim, kimlik bağı ve kanıt durumunu doğrular. HTTP adaptörü
Bright Data'nın belgelenmiş tek şirket dataset'ine async POST başlatır;
sonraki açık refresh GET ile ilerleme ve sonuç alır. Otomatik POST tekrarı,
ürün/kapsam genişletme, callback veya ham endpoint parametresi yoktur.
Mevcut stdlib HTTP yaklaşımı yeterlidir; SDK/proxy/tarayıcı bağımlılığı
eklenmedi. Kaynak kodu alınmış bir Bright Data sunucusu kurulmaz.

Şema82, değişmez keşif makbuzuna foreign key ile bağlı ek kayıt ekler.
Gönderim anahtarı ve konservatif UTC günlük profil kotası ağdan önce tek
transaction içinde ayrılır. Kayıtlı snapshot ile kesinti sonrası GET
devamı mümkündür. Kimliği kaybolmuş gönderim tekrar edilmez. Tamamlanan
kanıt yeniden yazılamaz; kayıtlar ve bağlı keşif özeti okumada doğrulanır.
Limit çalışma alanına aittir; ortak sağlayıcı hesabının parasal bütçesi
üst platform/sağlayıcı panelinin sorumluluğunda kalır.

CLI/platform aynı servisi kullanır; platform yazmaları güncel workspace
kimliği ve yazıcı kilidi ister. Engine okumaları ağsızdır. Anahtar,
operatörün özel dosyası/ortamındadır; müşteri JSON'u anahtar veya API hedefi
seçemez. Eski veri açık/yedekli migration ile korunur.

[Kullanım, sözleşme ve doğrulama sınırı](../BRIGHTDATA_SOCIAL.md).
