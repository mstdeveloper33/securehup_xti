# 0181 — Zamanlı ortak kanıt grupları

20 Kasım 2026 · 0.176.0 / çekirdek86 / kuyruk3 / dış JSONv1.

Kabul edilen kapsam, ilk sekiz motor işi ve iki kaynak değerlendirmesidir.
Yeni kaynak veya bağımlılık eklenmez; .NET/UI, LLM ve geniş STIX/TAXII
ertelenmiş kalır. Gruplar seçili çalışma alanındaki kayıtları kullanır.

- `research_query` varsayılan iki adımı korur, sınırı dörde çıkarır.
  Düğüm100/kenar200/yol2000 ve kaynak okuma bütçeleri korunur.
- Saf `research_groups`, DNS IP / gerçekten sunulan TLS sertifikası /
  rapor metni etrafındaki yıldızları kurar. Geçişli bileşenleri kampanya
  diye birleştirmez. Kopya metin SHA-256'sı kaynak metaverisinden ayrı;
  her özgün rapor/kenar kanıtı saklı kalır.
- Gözlem yakınlığı her üyeden en az bir gerçek gözlem içeren en dar
  pencereyle ölçülür. Belge/sensör/karar saatinin anlamı korunur. İlk-son
  gözlem aralığı üzerinden sürekli faaliyet veya eşzamanlılık türetilmez.
- `group_contract` kanonik parametreler; `group_ledger` saf replay,
  karar güncelliği ve fark kurallarıdır. Adapter aynı SQLite okuma kesitinde
  grafiği ve mevcut grupları alır. Mevcut `EvidenceService`/`EvidenceRepository`
  portu CLI, engine okumaları ve platform yazmalarını taşır.
- Journal yazması `BEGIN IMMEDIATE` içinde sürüm/kanıt ve tekrar anahtarını
  yeniden denetler. Yalnız ekleme yapılır. Payload özeti, zincir ve
  AUTOINCREMENT sonu doğrulanır. Bunlar dosyayı değiştirebilen yöneticiye
  karşı kriptografik imza değil, tutarlılık/bozulma denetimleridir.
- Kısmi yeniden kontrol önceki kanıtı korur. Görünümden çıkış gerçek
  dünyada silinme sayılmaz. Kısmi okuma sonrası tekrar görünmeme ikinci
  bir kayıp olayı üretmez. Aynı anahtar eski işlem makbuzunu verir.
- Kaydedilmiş grup özeti firma incelemesi ve kuruluş raporuna, donmuş
  grup/karar vaka kanıtına bağlanır. Vakadan gelen insan bağı kaynak
  gözlemi veya saldırı atfına dönüşmez. CLI monitor sınırlı tur çalıştırır,
  uyurken kilit tutmaz; ayrı ağ worker'ı veya zamanlayıcı eklemez.
- Boyut/kapsam sınırları istemciye bildirilir. Grup başına 50 üye/192KiB,
  geçmiş 1.000 olay/4MiB; workspace toplamı 10.000 olay/64MiB. Şimdilik
  otomatik günlük arşivi/purge yok; kapasite ölçümü sonsuz ölçek iddiası değil.
- Şema86, yeni journal ve `case_evidence` CHECK genişlemesidir. Eski tüm
  satır/rowid'ler açık yedekli transaction ile korunur. Gerçek şema85
  üreticisi, yeni okuyucu ve eski kodla eski yedeğin kurtarılması ölçülür.

Ticari kaynak kararları yazılımın lisansından ayrı [değerlendirmede](../COMMERCIAL_SOURCE_REVIEW.md)
saklanır. Belge eksikliği izin var sayılarak kapatılmaz; ticari profilde
hariç bırakma kararıyla kontrol altında tutulur. Güncel crt.sh erişimi
tarihî kesintinin kesin nedenini kanıtlamaz.
