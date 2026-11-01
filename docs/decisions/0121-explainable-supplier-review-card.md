# 0121 — Açıklanabilir tedarikçi inceleme kartı

**Durum:** Kabul edildi · **Tarih:** 31 Ekim 2026 · **Sürüm:** 0.123.0

## Karar

Tedarikçi çekirdeğinin birleşik görünümü; insan onaylı envanteri, kabul edilmiş
güncel CNAME bağımlılıklarını, ThreatCluster/RansomLook kaynak kapsamını ve son
yerel iddia adaylarını salt okunur bir kartta toplar. Kanıt kayıtları kopyalanmaz
veya birleştirilmez; özgün kimliklerine başvurulur.

Kart sayısal bir risk skoru üretmez. Beş açıklanabilir inceleme durumu vardır:

- açıklanabilir kaynak adayı ve yüksek/kritik iş önemi varsa öncelikli inceleme,
- açıklanabilir kaynak adayı varsa inceleme,
- yalnız aynı isimli kuruluşları ayıramayan eşleşme varsa kimlik incelemesi,
- başarılı yerel kaynak snapshot'ı yoksa yetersiz veri,
- başarılı snapshot var fakat eşleşme yoksa güncel eşleşme yok.

Hiçbir durum doğrulanmış ihlal, tedarikçi etkisi veya kullanıcının etkilendiği
sonucunu vermez. İş önemi kullanıcı beyanıdır; tek başına tehdit kanıtı değildir.

## Eksik veri ve aksiyon

Kaynak hiç toplanmadı, başarılı snapshot yok, son deneme hatasından sonra eski
başarılı veri kullanılıyor ve RansomLook'un domain sağlamaması kartta görünür.
Kart yalnız insan inceleme adımları önerir; alarm, dış mesaj, engelleme veya
otomatik müdahale başlatmaz.

## Veri ve geri alma

Uygulama mevcut şema 53 kayıtlarını salt okunur kullanır. Yeni tablo, migration
veya geriye dönük veri üretimi yoktur. Özelliğin geri alınması kalıcı veri
dönüşümü gerektirmez.

## Sonuç

Tedarikçi çekirdek akışı envanter → teknik bağımlılık → kaynak iddiası →
açıklanabilir insan incelemesi olarak tamamlanır. Otomatik değişiklik aboneliği,
kontrol çerçevesi eşlemesi ve markalı dönemsel çıktı, ortak vaka/raporlama
altyapısıyla birlikte ileride genişletilebilir; çekirdek tedarikçi kullanımını
bekletmez.
