# 0172 — Rapor sürümlerini ortak araştırmada göstermek

19 Kasım 2026 · 0.167.0 · Kabul edildi.

## İhtiyaç

0.166.0 raporu ve insan bağlantısını saklar; analist bir IP/domain
araştırırken bu metni ve bağlantının hangi sürüme ait olduğunu birlikte
görebilmelidir. Önceki metin veya geri çekilmiş bağlantı kaybolmamalıdır.

## Karar

- Her belge `report_document` düğümüdür; kimliği `RAPOR_UUID:SURUM`.
  Metinde geçen aday, özgün aramanın domain kapsamı ve insanın kurduğu
  bağlantı üç ayrı ilişki türüdür. Aktör → IOC ilişkisi türetilmez.
- `domain/research_reports.py` saf kanıt/düğüm/ilişki projeksiyonudur.
  `StoredReportContext` mevcut `SQLiteResearchRepository` transaction'ını
  kullanır; ayrı bağlantı, kaynak çağrısı veya yazma açmaz.
- Rapor günlüğünün mevcut zincir/replay denetimi yeniden kullanılır.
  Araştırma ön okuması 10.000 makbuz/16 MiB, her düğüm en fazla 200 ilişki,
  istek boyunca 50.000 bağlantı incelemesidir. Tüm raporların geniş grafı
  önceden kurulmaz. Sınırda `partial` ve açık kapsam gerekçesi verilir.
- Belge kaynak kanıtı ve insan kararları ayrıdır. Kararlarda `current`
  son ilgili karardır; `linked/withdrawn` ayrıca okunur. Eski belgeye
  verilen karar yeni sürüme taşınmaz. Karar geçmişi en yeni önce gösterilir;
  52 kanıt sınırında gerçek toplam ve eksiklik korunur.
- Araştırma modeli 3 ve zarf v1 alanları korunur. `observed_at`, rapor
  bağlamında `time_basis=response_received_at` ile **kaynak alınma**
  zamanıdır; bilinmeyen olay zamanı uydurulmaz. Yayın hassasiyeti, metin
  aralığı ve belge tamamı `reports.show` / `record.get` ile açılır.
- `record.get` için `report/report_document/local-reports` başvurusu
  eklendi. Aynı firma alanında seçilmiş belgeyi açar; yanlış kimlik/sürüm
  `not_found` verir. Metin sabit, kararlar ve rapor geçmişi günceldir.
- Öncelik v8 rapor metni/eski belge/bağlama/geri çekme gerekçeleri ekler.
  Bunlar bağlam gerekçeleridir; otomatik tehdit puanı veya kaynak oyu
  üretmez. Eski model 1–3/v7 incelemeler yeniden yazılmaz; ilk v8 inceleme
  `policy_baseline`, sonraki değişimler özgün kanıtlarla karşılaştırılır.

## Sınır ve sonuç

Şema 77 ve kuyruk 3 değişmez; 0.166.0'dan ek migration gerekmez.
Rapor yakalama hâlâ açıktır. Eski investigation adayları ile aynı metnin
raporu yan yana bulunabilir; bağımsız doğrulama sayılmaz. Kaynak işi
otomasyonu, genel ilişki çıkarımı, gerçek müşteri sighting günlüğü, tam
makale/PDF, geniş STIX/TAXII ve LLM bu değişikliğin kapsamı değildir.

[Davranış ve kabul](../ACCEPTANCE_REVIEW.md),
[kullanım](../REPORTS_OBSERVATIONS.md), [takip notları](../../NOTES.md).
