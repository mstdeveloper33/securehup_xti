# 0192 — Birleşik saklı-kanıt izleme ve snapshot tekilleştirme

Tarih: 22 Kasım 2026. Durum: kabul edildi.

## Bağlam

XTI'da domain, marka, sosyal, ransomware, haber, CTI ve IOC gibi farklı
kanıt aileleri zaten kendi kaynak ve doğrulama kurallarıyla saklanmaktadır.
Platformun tek bir kuruluş watchlist'i, ortak eşik ve insan geri bildirimi
istemesi bu kaynak kurallarını ikinci kez yazmayı gerektirmemelidir. Aynı
zamanda sık çalışan ve değişmeyen politikaların binlerce eşleşmelik aynı
JSON gövdesini her tur kopyalaması uzun süreli kullanımda kabul edilemez.

## Karar

- Birleşik izleme dış kaynağa bağlanmaz. Tek SQLite read transaction içinde
  mevcut global arama projeksiyonunu dondurur.
- Politika kuruluş kapsamlı ve sürümlüdür. Domain hedefi etkin kuruluş
  bağlantısıdır; diğer hedefler açık tür/değer çiftidir.
- İlk çalışma sessiz baseline'dır. Sonraki çalışmalar kayıt kimliği ve durum
  SHA-256 özetiyle added/updated/removed farkı üretir.
- Eşik alarmı tehdit hükmü değildir. Öncelik politika yönlendirmesidir;
  insan kararı ayrı revision geçmişidir.
- Snapshot gövdesi capture zamanını içermez; zaman çalışma kaydında tutulur.
  Aynı politika sürümünde snapshot hash'i değişmediyse yeni run gövdeyi
  yeniden saklamaz. Doğrudan önceki run aynı hash'i taşımalı ve daha eski
  kalıcı kaynak gövdesi hash/kanonik JSON doğrulamasından geçmelidir.
- Fark raporu kaynak kapsamı gövdesini tekrar taşımaz; sayısını ve hash'ini
  taşır. Snapshot ağır iç arama semantic/navigation gövdesi yerine kayıt
  kimliği, durum hash'i ve sınırlı provenance taşır. Özet en fazla ilk100
  farkı içerir; bütün eşleşme, kapsam ve fark kanıtı ayrı sayfalanır.
- Kalıcı geçmiş otomatik silinmez. Açık kapasite sınırı aşılırsa yazma
  fail-closed durur; retention ayrı bir ürün kararıdır.
- Engine yalnız okur. Firma platformu yazmaları workspace/revision/
  idempotency çitlidir. Scheduler ve dış kanal teslimi tüketici platforma
  aittir.

## Sonuçlar

Bir kaynak adaptörü değişse bile P07 kaynak mantığını kopyalamaz. Birleşik
alarm mevcut saklı kanıtın durumunu açıklar; kaynağın o anda yenilendiğini
iddia etmez. Değişmeyen çalışma geçmişi ve zamanı korunurken disk maliyeti
büyük snapshot başına değil gerçek kanıt değişimi başına büyür. Referans
zinciri veya hash bozulursa run okunmaz ve vaka kopyası üretilmez.

Bu karar gerçek zamanlı streaming, Kafka, e-posta/SMS/Slack/Teams, LLM veya
otomatik tehdit sınıflandırması eklemez.
