# 0131 — Arşiv gözleminin tutarlı kimliği

**Durum:** Kabul edildi · **Tarih:** 14 Kasım 2026 · **Uygulama:** 0.131.0

theHarvester adaptörü bir ham HTTP belgesinin hash'ini kullanmaz; kaynak,
hostname ve çalışma bilgileri üzerinden kanonik bir kanıt özeti üretir.
Gözlem zamanı toplama bitişiyken bu zaman özette bulunmuyordu. Aynı hostname
sonraki çalışmada yeniden geldiğinde aynı özet farklı zaman taşıyor, SQLite
haklı olarak çelişen kaynak kanıtını reddediyordu.

Kanonik özet artık normalleştirilmiş `completed_at` içerir. Aynı gözlem aynı
kimliği korur; sonraki gözlem ayrı kanıttır. Adayın domain kimliği ve insan
kararı aynı kalır. Genel çakışma doğrulaması gevşetilmez, eski kayıtların
özeti veya zamanı değiştirilmez ve şema geçişi gerekmez.

Eski özetle kayıtlı tarihsel çıktı yeni adaptörle aynen yeniden ayrıştırılırsa
bir yeni türetilmiş kanıt satırı oluşabilir; aday/bildirim çoğalmaz. Bu sınırlı
uyumluluk etkisi, kanıt geçmişini geriye dönük yeniden yazmaya tercih edildi.
Regresyonlar farklı-zaman tekrarı, aynı gözlemin normalize tekrarı, eski kanıt
ve insan kararının korunması ile genel çakışmada transaction rollback'i kapsar.
