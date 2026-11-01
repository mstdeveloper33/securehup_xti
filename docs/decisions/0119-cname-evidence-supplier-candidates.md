# 0119 — CNAME kanıtlı tedarikçi adayı ve insan çözümleme kararı

**Durum:** Kabul edildi · **Tarih:** 31 Ekim 2026 · **Sürüm:** 0.121.0

## Karar

İlk otomatik tedarikçi önerisi yalnız etkin, açıkça onaylanmış dış yüzey
kapsamının kayıtlı son CNAME kanıtından üretilir. Komut yeni DNS veya internet
isteği yapmaz. Kaynak ve son CNAME hedefinin sürümlü Public Suffix List kayıt
kökleri farklıysa hedef kök yalnız “olası dış hizmet domaini” olarak kaydedilir.
Kuruluş adı, sahiplik, sözleşme, güven veya risk sonucu çıkarılmaz.

Aday, kaynak varlık ve dış hizmet kayıt köküyle tekilleştirilir. Her farklı
CNAME kanıtı ve kullanılan PSL sürüm/özeti eklemeli kanıt zincirinde korunur.
Son kanıt artık bu bağı göstermiyorsa aday silinmez, tarihsel olur.

Kabul kararı yalnız önceden insan tarafından kaydedilmiş etkin bir tedarikçi
kimliğine bağlanabilir. Bekleyen, kabul, belirsiz ve ret kararları gerekçelidir;
karar değişebilir ve eski kararlar silinmez. Böylece CDN veya ortak altyapı
yanlışlıkla kuruluş sayılmaz ve aynı teknik domain farklı bir kuruluşa sessizce
taşınmaz.

## Veri ve geri alma

Şema 53 `supplier_candidates`, `supplier_candidate_evidence` ve
`supplier_candidate_resolution_events` tablolarını ekler. Şema 52 geçişi önce
doğrulanmış, üzerine yazılmayan yedek üretir ve tabloları tek transaction içinde
boş oluşturur. Migration eski CNAME kayıtlarından aday uydurmaz. Hata halinde
canlı veritabanı şema 52 olarak kalır.

## Sınır

CNAME bir teknik yönlendirme kanıtıdır; ticari ilişki veya kuruluş kimliği
kanıtı değildir. Bu dilim tedarikçi olayı, risk kartı, bildirim, otomatik
birleştirme, ağ isteği ya da dış aksiyon üretmez. Sonraki dilim yalnız kaynaklı
olayları insan onaylı tedarikçi ilişkisine bağlayacak ve eksik veriyi açıkça
gösterecektir.
