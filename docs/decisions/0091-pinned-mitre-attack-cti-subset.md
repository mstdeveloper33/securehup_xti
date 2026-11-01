# 0091 — Sürüme sabit MITRE ATT&CK CTI alt kümesi

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

Yerel CTI bilgi grafiği aktör, kampanya, malware, rapor ve ilişkileri kaynak iddiasıyla saklayabiliyordu; fakat dışarıdan ücretsiz ve tekrarlanabilir bir varlık/ilişki kaynağı almıyordu. İlk adaptörün API anahtarı istememesi, lisansının araştırma ve ileride ürün kullanımına engel olmaması, kaynak sürümünü sabitlemesi ve manuel kayıtları ezmemesi gerekiyor.

MITRE, Enterprise ATT&CK verisini sürüm başına STIX 2.1 koleksiyon paketi olarak yayımlar. ATT&CK v20.0 13 Ekim 2026 tarihlidir. MITRE lisansı ATT&CK verisinin araştırma, geliştirme ve ticari amaçla kullanımına bildirim/atıf koşullarıyla izin verir.

## Karar

- Kaynak `mitre-attack-enterprise` kimliğiyle yalnız resmî `enterprise-attack-20.0.json` dosyasıdır. Sürümsüz en-güncel dosya kullanılmaz; yeni sürüm kendiliğinden alınmaz.
- Sabit HTTPS adresi, yönlendirme reddi, `identity` aktarımı, `text/plain`, 60 saniye, 64 MiB ve 30.000 STIX nesnesi sınırı uygulanır.
- JSON yinelenen alanı ve sonlu olmayan sayıyı reddeder. Bundle/koleksiyon kimliği, Enterprise adı, v20.0 sürümü, STIX 2.1 biçimi, kanonik UUID ve UTC zamanları, koleksiyon içerik dizini ile resmî ATT&CK dış başvurusu doğrulanır.
- İlk alt küme yalnız etkin `intrusion-set`, `campaign` ve `malware` nesneleri ile bunlar arasındaki `uses` ve `attributed-to` ilişkileridir. Teknik, taktik, araç, veri kaynağı ve savunma nesneleri alınmaz.
- ATT&CK `intrusion-set` nesnesi yerel ortak modelde `threat-actor` araştırma etiketiyle tutulur. Bu eşleme kişi/grup kimliğinin doğrulandığı veya atfın XTI tarafından onaylandığı anlamına gelmez.
- Yerel güven 50/100 MITRE puanı değildir; kaynak puan vermediği için XTI'ın nötr yerel politikasıdır. Açıklamalar bütün kayıtları kaynak iddiası ve otomatik olmayan hüküm olarak etiketler.
- Kaynak adaptörü tam paketi bellekte doğrulayıp ortak `AttackSnapshot` modeline çevirir. Uygulama servisi ağdan önce yönetilen yerel geçmişi denetler. Depo ekleme, gözlem, güncelleme, yeniden etkinleştirme ve artık snapshot'ta olmayan iddiaları geri çekmeyi tek SQLite transaction'ında yapar; sonunda aynı geçmişi yeniden denetler.
- Kaynak adı manuel eklemeye kapalıdır. Aynı kanonik varlıktaki manuel veya başka kaynak iddiası korunur. Kaynak/biçim hatası boş paket sayılmaz ve yazma başlatmaz.
- İlk dilimde yeni tablo yoktur; şema 39 korunur. Başarılı değişiklikler mevcut iddia/olay geçmişinde görünür. Ayrı senkron çalışma tablosu olmadığı için kaynak indirme hatası kalıcı çalışma kaydı olarak saklanmaz; terminal hatası ve başarısız çıkış kodu verir. Kalıcı çalışma/sağlık geçmişi gerekirse ayrı şema kararıyla eklenir.
- Otomatik zamanlayıcı, arka plan yenileme, ATT&CK TAXII, STIX içe/dışa aktarma kapsamını genişletme ve otomatik tehdit/atıf kararı yoktur.

## Sonuçlar

Kullanıcı `./xti cti attack-sync` ile ücretsiz resmî CTI bağlamını tek komutta alabilir ve `cti search`, varlık listeleri ve ilişki listeleriyle ağsız araştırabilir. İlk v20.0 kabulünde 26.690 STIX nesnesinden 178 grup, 57 kampanya, 747 malware ve 809 seçili ilişki çıktı. Kaynakta silinen veya etkisizleşen kayıt geçmişten kaybolmaz; yalnız MITRE iddiası geri çekilir.

Tam dosya yaklaşık 55 MB olduğu için ilk çalıştırma internet ve disk kullanır. Bu veri bütün tehdit aktörlerini, kampanyaları, malware ailelerini veya güncel olayları kapsayan canlı bir besleme değildir. Sürüm güncellemesi veri modeli, sayı sınırları, ilişki türleri, lisans ve testler incelenmeden yapılmaz.

## Dayanaklar

- MITRE ATT&CK veri ve araçları: https://attack.mitre.org/resources/attack-data-and-tools/
- Resmî STIX veri deposu ve sürüm dizini: https://github.com/mitre-attack/attack-stix-data
- Sürümlü kullanım örneği: https://github.com/mitre-attack/attack-stix-data/blob/master/USAGE.md
- MITRE ATT&CK lisansı: https://github.com/mitre-attack/attack-stix-data/blob/master/LICENSE.txt
