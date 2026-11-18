# 0161 — Kaynak yenilemesini ortak motor kuyruğunda yürütme

- Tarih: 18 Kasım 2026
- Durum: Uygulandı; 0.157.0, çekirdek şema 75, iş kuyruğu şeması 2

## İhtiyaç ve karar

CIRCL/urlscan ve MISP zaten kanıtı ve hata geçmişini saklıyordu. Platform
yenilemeyi kalıcı iş olarak başlatamıyordu. Mevcut kuyruk, worker kilidi,
firma ayrımı ve iki dosyalı yedek genişletildi; ayrı kuyruk eklenmedi.

`sources.refresh` v1 planı normalize kökü, açık kaynak/liste seçimlerini,
bütçeyi ve isteğe bağlı araştırma kapsamını sabitler. Kabul ağ çağırmaz.
Kurallar domain/application, SQLite ve mevcut HTTP servislerinin bileşimi
adaptör/arayüz sınırındadır. Yeni işlem sürümünün anlamı gelecekte sessizce
değiştirilmez; farklı yürütme yeni sürüm ve eski kaydı okuma kararı ister.

Şema 2 yeni olay türlerini ekler. Profil payload/request/result ve üç
olaylı geçmişi korunur; kaynak olayları profil işinde açıkça reddedilir.
Kaynak işi en fazla üç adım, 12 olaydır. Başlangıç dış çağrıdan önce,
özgün kanıt makbuzu sonra commit edilir. Core/queue commit arası kesinti
belirsizdir; dış istek için atomiklik veya exactly-once iddiası yoktur.

Kilit sırası kuyruk → çekirdek; firma yedeğiyle aynıdır. İptal kısa kuyruk
transaction'ıdır, worker kilidini beklemez. Adım başlangıcı ve son sonuç
öncesi iptal yarışları kalıcı ilerleme üzerinden çözülür. Zaman bütçesi
devam eden HTTP çağrısını zorla kesmez. MISP grup adımı tek commit altında
seçili listeleri alır; mevcut sağlayıcı sınırlarını korur.

Retry yeni iş/anahtar oluşturur; terminal ve tamamlanmamış ebeveyn aynı
kuyrukta doğrulanır. Tamamlanmış kaynak kanıtları yeniden kullanılır;
diğer kaynaklar ve inceleme tekrar yürür. Ebeveyn, plan, makbuz listesi ve
kesinti seçimi geçmiş okunurken doğrulanır. Döngü/kayıp ebeveyn reddedilir,
32 tekrar sınırı vardır. Belirsiz istek açık seçim olmadan tekrarlanmaz.

## Geçiş ve kurtarma

Yeni kurulum şema 2; şema 1 okuması ve profil yürütmesi korunur. Kaynak
işi kabulü şema 1'i reddeder. Açık geçiş worker kilidi ve yazma transaction'ı
altında benzersiz doğrulanmış yedek alır, yalnız events DDL'ini değiştirir,
eski satır/hash'leri korur. Hata rollback yapar, yedek silinmez.

Platform backup/restore iki şemayı okuyabilir; iki dosyanın birlikte
yedeği kaynak makbuzlarını korur. Restore sırada işleri tekrar çalıştırmaz
ve yeni workspace kimliğiyle eski istekleri reddeder. Kişisel çekirdek
backup sidecar'ı kapsamaz; kullanım rehberi bu ayrımı açıklar.

## Sınırlar ve kabul

Genel akış kurucusu, dağıtık worker, firmalar arası ortak kota ve sınırsız
saklama yoktur. İnsan kararı, alarm, kaynak lisansı ve tüketici ekibin
.NET/oturum sorumluluğu değişmez. Hash bağımsız imza değildir.

Gerçek SQLite ve CLI/JSON testleri kontrollü kaynaklarla başarı, kaynak
hatası, iptal yarışları, kesinti, açık tekrar, firma ayrımı, geçiş/rollback,
restore ve eski profil uyumunu sınar. Kesin test/canlı sonuçları
[kabul kaydında](../ACCEPTANCE_REVIEW.md) tutulur; protokol başarısı kaynak
başarısı sayılmaz. [Kullanım ve sözleşme](../SOURCE_JOBS.md).
