# RansomLook bildirim kutusu planı — Aşama 7

**Durum: PLANLANDI — HENÜZ UYGULANMADI.**
**Tarih: 14 Kasım 2026.** Bu belge uygulanmış özellik beyanı değildir.
İnceleme dayanağı 0.130.0 kodudur; önceki aşamaların şema değişiklikleriyle
birlikte yeniden değerlendirilmelidir.

## Kullanıcıya sağlayacağı sonuç

RansomLook kuruluş izlemesinde ilk ölçümden sonra bulunan yeni veya değişen
eşleşmeler mevcut yerel `inbox` içinde görülecek. Kaynak adı, izleme,
çalışma kimliği ve fark sayıları gösterilecek; tüm kayıtların ayrıntısına
`ransomware watch-run-show ID --source ransomlook` ile ulaşılacak.

İlk ölçüm, tanım değişikliğinden sonraki ilk ölçüm, değişmeyen sonuç ve yalnız
kaynak penceresinden çıkan kayıtlar bildirim üretmeyecek. Çıkış, çözüm kanıtı
sayılmayacak. Okundu bilgisi iddianın doğruluğu veya insan kararı olmayacak.
ThreatCluster ve RansomLook ortak kutuda ayrı kaynak kayıtları olarak kalacak;
kuruluş adı benzerliğinden aynı olay veya doğrulanmış ihlal sonucu çıkarılmayacak.

## Uygulama sınırı

- Mevcut `attention_count` hesabı korunacak: sessiz başlangıç dışında
  `added_count + updated_count`. Bildirim bununla aynı koşulda üretilecek.
- Ayrı `ransomlook_watch_notifications` tablosunda global `sequence`, benzersiz
  `id`, benzersiz `run_id`, `watch_id`, sabit
  `event_type='ransomlook_watch_changed'`, `origin='new'`, `created_at` ve
  nullable `read_at` tutulacak. Run/watch ilişkileri doğrulanacak.
- Çalışma, sonuç öğeleri ve bildirim aynı SQLite transaction içinde yazılacak.
  Başarısız bildirim yazımı kısmi çalışma bırakmayacak.
- Ayrı `RansomLookWatchChangeEvidence` modeli ve inbox kaynak alanı eklenecek.
  Run raporuna sondan varsayılan `notification_id=None` eklenmesi mevcut
  positional kurucuların korunmasını sağlayabilir.
- Domain ve uygulama servisleri terminal, SQLite veya dış sağlayıcıya
  bağlanmayacak. Yeni dış kaynak veya ücretli hizmet gerekmeyecek.
- Yeni bildirimler mevcut açık webhook kuyruğa alma yoluyla paketlenebilir;
  kendiliğinden dışarı gönderim eklenmeyecek.

Başlıca değişiklik noktaları: `domain/ransomlook_watches.py`, `domain/inbox.py`,
`adapters/sqlite_ransomlook_watches.py`, `adapters/sqlite_inbox.py`,
`adapters/sqlite_notification_sequence.py`, `adapters/schema.py`,
`adapters/sqlite.py`, `interfaces/inbox.py`, `interfaces/ransomlook_watches.py`.
Kullanım, durum, mimari ve ayrı mimari karar belgesi de güncellenecek.

## Şema ve veri koruma koşulları

1. Yeni bildirim DDL'si mevcut `RANSOMLOOK_WATCH_DDL` içine eklenmeyecek.
   Eski sürümler mevcut DDL ile doğrulanıyor; ayrı DDL, oluşturma fonksiyonu ve
   migration sürüm kapısı kullanılacak. Sürüm önceki aşamalardan sonra seçilecek.
2. TABLES, kolon, unique, index, foreign key ve SQL düzeni denetimleri birlikte
   genişletilecek. `VERSION_TABLES` içinde yeni tablo bütün eski sürümlerden
   çıkarılacak. Eski şema fixture'ları da yeni tabloyu kaldıracak.
3. Geçiş mevcut doğrulanmış, benzersiz geri dönüş yedeği akışını kullanacak.
   Eski DB, bildirim sıraları ve okundu zamanları korunacak. Hata transaction'ı
   geri alacak; yedek silinmeyecek. Restore mevcut DB üzerine yapılmayacak.
4. Yeni tablo boş başlayacak; geçmiş sonuçlardan bildirim türetilmeyecek.
   Var olan dikkat sayıları değişmeyecek.
5. Global sıra için tek `next_notification_sequence` yardımcısının tablo listesi,
   inbox union/sıra çakışması denetimi ve `inspect` toplam/okunmamış sayaçları
   birlikte güncellenecek. Kaynak başına ayrı sıra verilerek çakışma yaratılmayacak.
6. Listeleme ve ayrıntı okuma bildirim oluşturmayacak, okundu işaretlemeyecek
   veya eski şemayı kendiliğinden yükseltmeyecek.

## Kabul ölçütleri

- Sessiz başlangıç sonrası eklenen/değişen sonuç bir okunmamış bildirim üretir.
  Tekrar çalışma, yeni sessiz başlangıç, yalnız çıkarılma ve kaynak hatası
  fazladan bildirim üretmez.
- Bildirim ekleme hatasında run ve öğeler de geri alınır; yanlış watch/run
  bağlantısı okumada reddedilir.
- Diğer bildirim türleriyle global sıra, saat geri gitse de kararlı sayfalama,
  idempotent okundu ve çoklu mark işleminin tümden geri alınması doğrulanır.
- Yedek/restore bildirim ve okundu zamanını korur. Migration geçmişe bildirim
  üretmez; DDL hatasında eski DB ve geçerli yedek korunur.
- Terminal kaynağı ve ayrıntı komutunu doğru gösterir; dış metin güvenli
  gösterilir. JSON, collect raporu ve açık webhook kuyruğu kaynak ayrımını korur.
- İlgili kalıcılık, migration, inbox ve CLI testleri ile `./scripts/check`
  tamamlanır. Linux'ta çalıştırılmayan bir kontrol yapılmış gibi raporlanmaz.

## Aşama 8 için kısa önkoşullar — Linux zamanlama

Bu bölüm de plan durumundadır. Kayıtlı toplama profilleri ve kalıcı çalışma
geçmişi tamamlandıktan sonra tek profil çalıştıran kullanıcı düzeyinde Linux
service/timer hazırlanabilir. Mevcut `./xti`, mutlak `--data-dir` ve ortak
`LocalExecutionLock` kullanılacak; ikinci bir paralellik kilidi gerekmiyor.

Mutlak proje/veri yolu ve açık profil kimliği kullanılmalı; shell komut
birleştirme yapılmamalı. Birim dosyalarında `%`, `$` ve tırnak kaçışları ayrıca
doğrulanmalı. Kurulum kendiliğinden tarama veya hizmet etkinleştirme yapmamalı.
Kısmi kaynak hatası, kilit doluluğu ve yapılandırma hatası ayrı görünmeli;
hızlı yeniden deneme döngüsü oluşmamalı.

Mevcut `backup`, `restore`, `doctor`, `storage readiness` ve kontrollü cleanup
yeniden kullanılabilir. Salt okunur hazırlık raporu otomatik yedek, disk kotası
veya restore tatbikatı sayılmayacak. Birimler Linux ortamında doğrulanmalı;
macOS üzerinden dosya üretmek gerçek Linux hizmet testi yerine geçmez.
