# 0060 — Süreli maruziyet bastırma ve insan onaylı kapanma/yeniden açılma

**Durum:** Kabul edildi · **Tarih:** 30 Ekim 2026

## Bağlam

Zafiyet düzeltme planı, uygulama kaydı ve yeniden kontrol sonucu ayrı tutuluyordu. Ancak geçici bakım penceresi gibi durumlarda bir incelemeyi süresiz gizlemek, unutulan risk oluşturabilir. Ayrıca `not_observed` sonucunun insan onaylı kapanma ve yeni kaynak kanıtıyla yeniden açılma davranışı uçtan uca kabul senaryosuyla sabitlenmemişti.

## Karar

- `exposure-suppress`, yalnız `investigating` veya `affected` durumundaki bir incelemeye gerekçe ve 1–3650 günlük bitiş bağlar.
- Güncel süreli bastırma ile olay geçmişi ayrı tablolardadır. Etkinleştirme, uzatma, yeniden etkinleştirme ve erken kaldırma silinmeden saklanır.
- Bitiş anı geldiğinde liste, kuyruk ve doctor görünümü kaydı kendiliğinden tekrar görünür sayar. Bu okuma hiçbir tabloyu güncellemez ve yapay “süresi doldu” olayı üretmez.
- `--include-suppressed`, süresiz insan bastırmasını ve henüz bitmemiş süreli bastırmayı açıkça dahil eder.
- Eski `exposure-review --suppress/--unsuppress` davranışı geriye dönük uyumluluk için süresiz insan kararı olarak kalır. Yeni geçici ertelemelerde süreli komut kullanılır; ikisi aynı anlam sayılmaz.
- `not_observed` yeniden kontrolü maruziyeti kapatmaz. `fixed` için ayrı gerekçeli insan kararı gerekir. Sonraki ürün/NVD kanıt değişikliği eski `fixed` kararını silmez; yeniden inceleme uyarısı üretir ve insan isterse durumu `investigating` olarak yeniden açar.

## Güvenlik ve bütünlük

- Yeni süreli bastırma, zaten süresiz bastırılmış veya kapanmış kayda eklenemez.
- Ana kayıt ve olay aynı `BEGIN IMMEDIATE` transaction içinde yazılır.
- Zamanlar UTC ve zaman dilimli olarak doğrulanır; bitiş kayıt zamanından ileride olmalıdır.
- Liste ve kuyruk ilgili bütün süreli bastırmaları doğrular. Bozuk kayıt, gizli bir incelemeyi sessizce saklamak yerine bütün görünümü güvenli biçimde durdurur.
- Şema 25→26 geçişi önce doğrulanmış kurtarma yedeği yayımlar, iki tabloyu boş oluşturur ve geçmiş kararlardan bastırma uydurmaz.

## Sınırlar

Bu özellik bir zafiyeti düzeltmez, risk kabulü vermez ve alarmı silmez. Yerel saat yanlışsa görünürlük zamanı da etkilenir. Dağıtık kullanıcı onayı, görev atama ve hizmet seviyesi politikası daha sonraki ürünleşme aşamasındadır.
