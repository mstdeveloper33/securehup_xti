# 0156 — Kayıtlı kanıt üzerinden sınırlı ilişki araştırması

17 Kasım 2026 · 0.152.0 · şema 72 korunur.

Kendi platformumuzda domain/IP, DNS ve IOC/CTI ilişkilerini kaynaklarıyla
incelemek için yeni veri kopyası yerine salt okunur araştırma portu seçildi.
`ResearchService`, `ResearchRepository` üzerinden tek kesitte düğüm ve
komşularını alır. `domain.research` genişlik öncelikli, en fazla iki adımlı
gezinti ile döngüsüz yolları ve açık düğüm/bağ/yol bütçelerini uygular.

SQLite adaptörü mevcut DNS decoder/hash denetimini ve CTI iddia geçmişi
tekrarını kullanır. Firma seçimi aynı platform girişindedir; adaptör başka
veritabanını veya ortak kataloğu kendiliğinden eklemez. Domain/IP gözlemi ve
aynı değerin IOC kaydı araştırma düğümünü paylaşır, özgün kayıtlar değişmez.
CTI ilişkileri kaynak iddiası kalır. Başarısız son DNS kontrolü, eski olumlu
gözlemi ortadan kaldırmaz. Kaynakların çelişkileri oy sayımıyla çözülmez.

İlk ters IP okuması indekssiz JSON geçmişinin tamamını taramaz: seçili
çalışma alanındaki en yeni 1.000 DNS kontrolünden sınırlı pencere kullanır.
Pencere, byte, düğüm, bağ veya kaynak gösterim sınırı kapsamı kısmi yapar.
Bütünlük denetimi eksikse sonuç verilmez. Daha geniş ölçekte indeks veya
projeksiyon gereksinimi ölçülerek ayrı şema geçişiyle ele alınacaktır.

İçeriğe bağlı `snapshot_id` ve isteğe bağlı `expected_snapshot` değişen
sayfaları reddeder; geçmiş kesit saklama iddiası yoktur. Alanlar açıkça
serileştirilir. `research.show` engine ve firma platformu v1'e eklenen bir
okuma işlemidir; mevcut işlemler değişmez. CLI aynı uygulama servisini kullanır.

Graph veritabanı/NetworkX için bu dar kapsamda ihtiyaç yoktur; bağımlılık
eklenmedi. Başlangıç mevcut ücretsiz kaynaklardır. Gelecekte ücretli
sağlayıcı adaptörü kullanılabilir; araştırma salt okuma kalır ve ücretli
istekler ayrıca seçilip bütçelenir. Paket/veri koşulları ayrı değerlendirilir.

[Kullanım, protokol ve sınırlar](../RESEARCH.md).
