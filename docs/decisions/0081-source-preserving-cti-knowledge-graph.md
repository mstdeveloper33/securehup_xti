# 0081 — Kaynakları koruyan yerel CTI bilgi grafiği

**Durum:** Kabul edildi · **Tarih:** 30 Ekim 2026 · **Sürüm:** 0.81.0

## Bağlam

Yerel IOC kataloğu göstergeleri ve kaynak iddialarını saklıyordu fakat bir rapordaki aktör, kampanya veya malware bağlamını ifade edemiyordu. Tek bir “doğru” profil ya da atıf satırı kullanmak, farklı kaynakların alternatif adlarını ve çelişen aktör atıflarını ezme riski taşıyordu. Kişisel/ücretsiz profil için önce ağsız, denetlenebilir ve geri alınabilir bir çekirdek gerekiyordu.

## Karar

- İlk varlık türleri `threat-actor`, `campaign`, `malware` ve `report` ile sınırlıdır. Ad NFKC ve boşluk kurallarıyla tekilleştirilir; alternatif adlar kaynak iddiasında kalır ve otomatik birleşim anahtarı olmaz.
- İlk ilişki türleri `attributed-to`, `uses`, `targets`, `delivers`, `communicates-with`, `indicates`, `related-to` ve `reports-on` ile sınırlıdır. Kaynak bir CTI varlığıdır; hedef tam olarak bir CTI varlığı veya yerel IOC'dir. Öz ilişki ve bulunmayan hedef reddedilir.
- Her varlık ve ilişki için `source_name + source_reference` ayrı iddiadır. Güven, açıklama, alternatif adlar ve ilk/son gözlem kaynak bazında tutulur. Bir iddianın geri çekilmesi başka iddiayı değiştirmez.
- `added`, `observed`, `updated`, `reactivated` ve `revoked` olayları eklemelidir. Güncel satır ile olay aynı SQLite transaction'ında yazılır; aynı gözlem tekrarı yeni olay üretmez.
- Çelişen atıflar farklı ilişkiler olarak gösterilir. Güven puanı kaynak iddiasının bağlamıdır; otomatik doğruluk, zararlılık veya nedensellik kararı değildir.
- Liste, ayrıntı ve adla arama ağsız/salt okunurdur. Görünüm sınırının arkasındaki bağlı kayıt ve olaylar da güvenli üst sınıra kadar doğrulanır; bozuk gizli geçmişte kısmi sonuç verilmez.

## Veri ve geri alma

Şema 35, `cti_entities`, `cti_entity_assertions`, `cti_entity_assertion_events`, `cti_relationships`, `cti_relationship_assertions` ve `cti_relationship_assertion_events` tablolarını ekler. Şema 34→35 geçişi önce doğrulanmış yedek alır; DDL ve sürüm tek transaction'da uygulanır, hata halinde geri alınır. Eski IOC, bulgu veya raporlardan CTI varlığı ya da ilişkisi uydurulmaz. Eski uygulamaya dönüşte geçiş öncesi yedek kullanılır.

## Sonuçlar ve açık işler

Kaynaklı aktör/kampanya/malware/rapor profilleri ve varlık–IOC ilişkileri terminalden araştırılabilir. Bu ilk dilim tam grafik motoru değildir: açık birleştirme/ayırma kararları, zamanlı kampanya alanları, etiket/notlar, kaydedilmiş sorgular, abonelikler, ATT&CK eşlemeleri, STIX aktarımı ve vaka ilişkileri ayrı iş paketleridir.
