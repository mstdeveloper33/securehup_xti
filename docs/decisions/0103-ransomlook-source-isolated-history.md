# 0103 — RansomLook için kaynak-yalıtımlı snapshot geçmişi

- **Durum:** Kabul edildi
- **Tarih:** 30 Ekim 2026
- **Sürüm:** 0.105.0

## Bağlam

RansomLook yalnız grup adı, gönderi/kuruluş başlığı ve keşif zamanı sağlar. ThreatCluster ise farklı kimlik ve durum alanları taşır. İki kaynağı ortak tabloya zorlamak eksik alanları uydurma, aynı olayı kanıtsız birleştirme ve izleme geçmişini yanlış kaynağa bağlama riski doğurur.

## Karar

RansomLook tam snapshot çalışmaları ve fark öğeleri iki ayrı SQLite tablosunda tutulur. İlk başarılı snapshot başlangıç çizgisidir; sonraki çalışmalar yeni, aynı ve yedi günlük pencereden çıkan kayıtları ayırır. Değişmeyen kayıtlar her çalışmada yeniden yazılmaz; sayaç ve yeniden kurulabilir fark zinciri korunur. Kaynak hatası ayrı başarısız çalışma olarak yazılır ve son başarılı snapshot değiştirilmez.

Bu tablolar ThreatCluster çalışma, izleme, bildirim, monitor veya kimlik tablolarına bağlanmaz. Kaynağın vermediği ülke, sektör, domain, ilan durumu ve ihlal sonucu üretilmez. Pencereden çıkış silinme, çözüm veya yanlış iddia anlamına gelmez.

Şema 43 yalnız açık `./xti migrate` çağrısıyla şema 44'e çıkar. Önce doğrulanmış yedek alınır; yeni tablolar boş başlar. DDL veya doğrulama hatasında işlem geri alınır ve geçiş öncesi yedek korunur.

## Sonuçlar

RansomLook geçmişi çevrimdışı incelenebilir, yedeklenebilir ve tam fark zincirinden yeniden kurulabilir. Kaynaklar arası karşılaştırma için özgün kayıtlar korunur, fakat otomatik olay birleştirme yapılmaz. Sonraki dar teslim, bu ayrı snapshot üzerinde kuruluş-adı izlemesidir.
