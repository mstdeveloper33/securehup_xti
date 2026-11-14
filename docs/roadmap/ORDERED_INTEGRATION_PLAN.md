# Sıradaki sekiz teslim

14 Kasım 2026 tarihli kullanıcı onayıyla uygulanacak sıra. Bu belge çalışan
özellik listesi değildir; çalışan kapsam `docs/STATUS.md` içindedir.

| Sıra | Teslim | Durum | Kabul sonucu |
| --- | --- | --- | --- |
| 1 | Kayıtlı toplama profilleri | Tamamlandı (0.131.0) | Adla kaydetme, ağsız önizleme, çalıştırma; sürümlü tanım ve yedekli geçiş |
| 2 | Birleşik çalışma geçmişi ve eksik adımları yeniden deneme | Tamamlandı (0.132.0) | Kaynak çalışmalarıyla bağlı oturum; kesinti ve kısmi sonucun korunması |
| 3 | Açık kuruluş/marka bağlantıları | Ayrı ortamda doğrulandı; ana projeye birleşim bekliyor | Kullanıcının domain ve izlemeleri bağlaması; otomatik sahiplik çıkarımı olmaması |
| 4 | Günlük/haftalık değişim raporu | Bekliyor | Kaynaklı yeni/değişen kayıtlar ve kapsam boşlukları; tekrar sayımın açıklanması |
| 5 | ATT&CK teknik/taktik kataloğu | Bekliyor | Resmî kimliklerle arama, ayrıntı ve kaynaklı ilişkiler |
| 6 | Kaynak katkısını ölçme ve ücretsiz kaynak genişlemesi | Bekliyor | Ölçülen kapsam farkı, erişim sınırı ve hata ayrımı; doğrulanmış adaptör seçimi |
| 7 | RansomLook değişimlerini yerel bildirim kutusuna ekleme | Bekliyor | Sessiz başlangıç, yeni/değişen iddiada tek bildirim; kaynakların ayrı kalması |
| 8 | Linux zamanlaması ve bakım | Bekliyor | Kayıtlı profil, çakışma koruması, yedekleme ve kurtarma; açık etkinleştirme |

Her teslim mevcut veriyi koruyacak; kalıcı veri değişikliklerinde açık geçiş
ve geri dönüş yedeği, anlamlı hata/kesinti testleri ve güncel kullanım örneği
bulunacak. Ücretli dış API zorunluluğu getirilmeyecek. Ücretsiz kaynakların
erişim kotası veya kesintisi sınırsız kapsama dönüştürülerek sunulmayacak.

Web paneli, REST API, TAXII, e-posta, geniş marka modülleri ve LLM bu sekiz
teslimin dışında önceki plana göre bekliyor. Ürün/sürüm/paket/CVE eşleştirmesi
aktif kapsam dışında. Common Crawl indekslerinin dış erişim sorunu ayrı açık
konudur; yeni özelliklerin tamamlanması bu erişimin düzeldiği anlamına gelmez.
