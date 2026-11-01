# 0008 — Yerel bildirim kutusu ve açık okundu takibi

**Tarih:** 29 Ekim 2026 · **Durum:** 0.8.0'da uygulandı.

> 0.20.0'da kutu pasif alt alan adı adaylarını da birleşik sırada gösterecek biçimde genişletildi. Ayrı tablo ve ortak sıra kararı için [0020](0020-passive-discovery-history-and-notices.md) geçerlidir; aşağıdaki bulgu bildirimi kuralları korunur.

## İhtiyaç

Yeni aday bulgular tarama çıktısında görülebilse de kullanıcı bunları sonradan tek yerde takip edebilmelidir. Aynı adayın tekrar görülmesi kutuyu doldurmamalı; bir bildirimin okunması bulgu hakkında güvenli veya şüpheli kararı vermemelidir. Kişisel kurulumda bunun için ücretli hizmet veya ayrı sunucu gerekmemelidir.

## Sorumluluklar

Ortak `Notification` modeli sıra, UUID kimliği, ilgili bulgu kimliği, olay türü, köken, kutuda oluşturulma zamanı ve isteğe bağlı okundu zamanını taşır. Liste/ayrıntı/işaretleme sonuçları da ortak modellerdir; terminal veya SQLite'a bağımlı değildir.

`InboxService` doğrulama ve zaman üretimini yapar; yalnız küçük `NotificationRepository` sözleşmesini kullanır. Somut `SQLiteInboxRepository`, kayıt okumayı ve okundu değişikliğini yürütür. Terminal adaptörü servisi bağlar, güvenli metin veya JSON üretir. Kutuyu açmak ağ isteği başlatmaz ve eksik veritabanı oluşturmaz.

Bildirim oluşturma, yeni bulguyu kaydeden `SQLiteFindingRepository.save_import` işleminin parçasıdır. Ayrı bir süreçten sonradan eklenmez. Böylece bulgu kaydedilip bildirimin eksik kalacağı iki aşamalı bir yazı yoktur. Gelecekte başka bir depo adaptörü yazılırsa aynı atomiklik sözleşmesini sağlaması gerekir.

## Tekilleştirme ve kayıt

Şema 6, `notifications` tablosunu ekler:

| Alan | Anlamı |
|---|---|
| `sequence` | SQLite `INTEGER PRIMARY KEY AUTOINCREMENT`; kalıcı ekleme sırası |
| `id` | Tekil UUID; kullanıcının seçtiği bildirim kimliği |
| `finding_id` | Mevcut bulguya yabancı anahtar; bağlı bulgunun silinmesi engellenir |
| `event_type` | Bu sürümde yalnız `finding_created` |
| `origin` | `new`: yeni bulgu yazısı; `existing`: önceki kayıttan geçiş |
| `created_at` | Bildirimin kutuda oluşturulduğu UTC zaman |
| `read_at` | Açık okundu işaretleme zamanı; `NULL` ise okunmadı |

`finding_id + event_type` tekildir. Okunmuş/okunmamış liste için `read_at, sequence` indeksi vardır. Bir gözlemin işlenmesinde yeni bulgu, bildirim ve kaynak bağlantısı aynı transaction içinde tamamlanır. Sonradan geçersiz bir aday, yazma hatası veya kesinti bütün ilgili importu geri alır. Tamamlanmış diğer importlar korunur.

Aynı bulguya yeni kaynak eklemek, aynı aramayı tekrarlamak, insan kararı veya hedef kontrolü kaydetmek yeni bildirim üretmez. Önceden okunmuş bildirim tekrar okunmamış yapılmaz. Bulgu tekilliği varlık, aday domain ve kural/referans sürümüne bağlı olduğundan ayrı varlık veya kural sürümünün ayrı bulgusu ayrı bildirim alabilir. `origin=new` yalnız yeni yerel bulgu kaydını belirtir; adayın yeni ortaya çıkmış veya zararlı olduğunu doğrulamaz.

## Açık okundu işlemi

`inbox` ve `inbox list` varsayılan olarak okunmamış kayıtları gösterir. `inbox show` ilgili bulguyu, kaynak ve karar bilgilerini okur. Bu işlemler okundu bilgisini değiştirmez.

`inbox read` ve `inbox unread` bir komutta 1–100 kimlik kabul eder. Tekrarlanan kimlikler tekilleştirilir. Adaptör kısa `BEGIN IMMEDIATE` işlemi içinde önce bütün kimlikleri ve kayıtları doğrular; sonra seçimi birlikte günceller. Bir kayıt bulunamazsa veya yazım başarısız olursa hiçbir seçimin durumu değişmez. Başka bir yazıcı bu doğrulama ile güncelleme arasına giremez.

Okunmuş kaydı tekrar okundu işaretlemek mevcut zamanı korur. Okunmadı işlemi zamanı temizler; yeniden okundu işaretlemek yeni zaman yazar. Saat gerilemesi nedeniyle okundu zamanı bildirim oluşturma zamanından önce görünse bile kullanıcı eylemi kaybolmaz. Tekrar eden, hiçbir durumu değiştirmeyen komut kayıt yazmadan tamamlanır.

Bu alan mevcut okundu durumudur; kullanıcı işlemlerinin ayrı denetim günlüğü değildir. Önceki okundu/okunmadı zamanları saklanmaz. Bulgunun inceleme kararı ve karar geçmişi bu alandan bağımsızdır. Bulgu kapatıldığında bildirim otomatik okunmuş olmaz; bildirim okunduğunda bulgu kapanmaz.

## Sayfalama ve tutarlılık

Sayfa boyutu varsayılan 20, izin verilen aralık 1–100'dür. Liste azalan `sequence` sırasıyla alınır; devam sınırı son gösterilen sıradır. Sonraki sorgu yalnız bu sıradan küçük kayıtları alır. Yeni gelen bildirimlerin daha büyük sıra numarası, önceki sayfaların sınırlarını değiştirmez. Saatin geriye alınması veya VACUUM sıra numaralarını yeniden üretmez. AUTOINCREMENT, gelecekte bir satır silinse bile tamamlanmış sıra numarasının yeniden kullanılmasını önler; bu sürümde bildirim silme komutu yoktur.

Şema doğrulaması sütun, tekil anahtar, yabancı anahtar ve indeks kontrollerine ek olarak `sqlite_schema.sql` içindeki bildirim tablosu tanımını uygulamanın boşlukları normalleştirilmiş tanımıyla karşılaştırır. Böylece yalnız `INTEGER PRIMARY KEY` bırakılarak AUTOINCREMENT'in kaldırılması reddedilir. `sqlite_sequence` tablosunun varlığı tek başına yeterli sayılmaz. Uygulamanın oluşturduğu şema, yedek ve VACUUM sonrası geçerli kalır.

Bir sayfanın toplam/okunmamış/filtreye uyan sayıları ve satırları aynı okuma transaction'ından gelir. Filtre sayısı kutunun tamamına aittir; sayfa sınırından sonra kalan kayıt sayısı değildir. Bildirim ayrıntısı da bildirim, bulgu, kaynaklar ve kararlar için tek okuma transaction'ı kullanır.

Sayfalar arasında transaction açık tutulmaz. Kullanıcı sonraki sayfaya geçtiğinde toplam sayılar, okundu durumu veya bulgu kararları değişmiş olabilir. Sonradan okunmamış yapılan ve geçilmiş sınırın üstünde kalan bildirim ilk sayfa yeniden açıldığında görünür. Bu sayfalama, bütün gezinme boyunca dondurulmuş bir liste veya kullanıcıya özel oturum kaydı değildir.

## Eski veriler ve kurtarma

Şema 1–5, açık `migrate` komutuyla şema 6'ya taşınır. Önce yazma kilidi altında özgün sürümün yedeği alınır. Eksik tablolar ve bütün eski bulguların bildirimleri aynı transaction içinde eklenir; ardından sürüm ve bütünlük doğrulanıp işlem tamamlanır. Eski sürümlerin tablo kümeleri sabittir. Şema 5'te bulunan bekleme/bakım tabloları yeniden oluşturulmaz.

Geçiş, kapatılmış olanlar dahil her eski bulguya `origin=existing`, `read_at=NULL` ve aynı UTC geçiş zamanı ile bildirim ekler. Eski bulguların ekleme sırası korunur. Bulgunun kimliği, ilk/son görülme zamanı, kaynakları, kararları, hedef kontrolleri ve iş geçmişi değiştirilmez. Kutunun oluşturulma zamanı geçmiş internet tespiti zamanı değildir. Eski karardan bildirim okundu sonucu çıkarılmaz; terminal "Önceki kayıttan" etiketiyle ayrımı gösterir.

Geçiş tamamlanamazsa yeni tablo, kısmi bildirimler ve sürüm değişikliği geri alınır. Başarıyla oluşturulmuş geçiş öncesi yedek korunur. Tamamlanmış geçişi tekrar çalıştırmak yeni bildirim veya yeni yedek üretmez.

Güncel yedekler bildirim kimliklerini, kökenlerini, okundu bilgisini ve sıra sayacını da içerir. Restore yalnız boş konuma yapılır; mevcut dosyaların üzerine yazılmaz. Eski sürüm yedeği geri yüklenirse kaynak şeması korunur ve güncel uygulamada kullanmadan önce açık geçiş gerekir. Eski uygulamaya dönüş geçiş öncesi yedekten yapılır. Bağlantısız gözlem temizliği bildirimleri veya bağlı bulgu kanıtlarını silmez.

## Kapsam ve doğrulama

Bu sürüm yerel terminal bildirim kutusudur. E-posta, SMS, webhook, işletim sistemi bildirimi, dış teslim kuyruğu veya teslim onayı yoktur. Terminal kapalıyken kendiliğinden başlayan arama hizmeti eklenmemiştir. Yeni bağımlılık veya harici hesap gerektirmez.

0.8.0 için toplam 427 otomatik test geçti. Bildirim testleri ortak yazının geri alınmasını, tekrar ve ikinci kaynak tekilleştirmesini, karar/kontrol bağımsızlığını, açık işaretlemeyi, kısmi hata/iptalde geri almayı, eşzamanlı okumayı/yazmayı, sayfalama sınırını, şema 1–5 geçişini, AUTOINCREMENT doğrulamasını ve yedek/restore davranışını kapsar.

Ağsız 30 tur doğrulamasında üç bulgu için üç bildirim oluştu; ikisi okunmamış kaldı. Zorla süreç kapatma (SIGKILL) sonrası tamamlanmış okundu/okunmadı kayıtlarının korunması doğrulandı. Bu deneyler sentetik kaynaklarla yerel tekrar ve kesinti davranışını gösterir; canlı kaynaklarda uzun çalışma, milyonlarca kayıt veya gerçek tehdit tespit başarısı ölçümü değildir. Güncel doğrulama kapsamı [STATUS.md](../STATUS.md) içinde tutulur.
