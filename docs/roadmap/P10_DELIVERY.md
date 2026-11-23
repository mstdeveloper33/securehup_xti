# P10 — Bluesky genel gönderi kaynağı teslimi

**Durum:** Teknik teslim ve canlı kabul tamamlandı · **Sürüm:** 0.190.0 ·
**Tarih:** 23 Kasım 2026 · **Şema:** 97 (değişmedi)

## Kullanıcı sonucu

Kullanıcı artık bir firma, kayıtlı kuruluş veya tedarikçi için herkese açık
Bluesky metin gönderilerinde ad, domain ve açık alternatif ad eşleşmelerini
mevcut `content` akışında görebilir. Örneğin bir genel gönderide
`securehup.com` geçerse bağlantı, zaman, kaynak ve eşleşme nedeni kaydedilir;
analist bunu ilgili, ilgisiz, normal haber, tehdit iddiası veya belirsiz diye
inceleyebilir. Eşleşme kendi başına tehdit, resmî hesap veya doğru iddia
değildir.

## Bağlanan gereksinimler

| ID | Bu pakette tamamlanan parça |
|---|---|
| A01 | Seçilmiş bir genel sosyal gönderi kaynağı gerçek toplama akışına eklendi. |
| A07 | Kaynak; erişim, maliyet, dil/bölge, kota, hata, provenance ve veri hakkı manifestine eklendi. |
| A12 | Aynı kaynak kayıtlı tedarikçi kimlikleriyle de çalışır. |
| A13 | Unicode hedefler korunur; kaynakta seçilen gerçek dil `lang` filtresine aktarılır. |
| E01 | Firma/domain/alternatif ad hedefleri mevcut sürümlü watch kapsamını kullanır. |
| E03 | İlk sessiz ölçüm, yeni/değişmiş kayıt ve insan incelemesi korunur. |
| I04 | Kaynak tanımındaki dil ve bölge görünürdür; `und`/`mul` bütün diller olarak filtresiz çalışır. |
| J01 | Kaynak, URI özeti, bağlantı, zaman, içerik hash'i ve çalışma kanıtı saklanır. |
| J03 | Kanıt ve gözlem sürümüne bağlı mevcut insan kararı/vaka akışı kullanılır. |

A01'in “bütün sosyal medya ve forumlar” gibi sınırsız yorumu tamamlanmış
sayılmaz. P10'un seçilmiş kaynak teslimi tamamdır; yeni platformlar kendi
erişim ve veri hakkı kabulünü gerektirir.

## Kaynak seçimi

| Aday | Karar | Gerekçe |
|---|---|---|
| Bluesky public AppView `searchPosts` | **Seçildi ve canlı doğrulandı** | Resmî genel okuma API'si, anahtarsız erişim, sınırlandırılabilir sorgu ve kararlı gönderi URI'si sağlar. |
| Mastodon durum araması | Bu paket için seçilmedi | Tam metin araması instance, hesap ve Elasticsearch yapılandırmasına bağlıdır; tek bir küresel kapsam sunmaz. |
| Bluesky firehose/Jetstream | Seçilmedi | P10 firma hedefli sınırlı aramadır; tüm ağ akışı gereksiz veri, işletim ve saklama yükü doğurur. |
| Üçüncü taraf sosyal proxy/crawler | Seçilmedi | Resmî API çalışırken ilave hesap, ücret ve veri hakkı bağımlılığı eklenmedi. |

XTI dış repo veya SDK kodu kopyalamaz. Python standart kütüphanesiyle mevcut
güvenli HTTPS taşıyıcısını ve Bluesky'nin iki resmî AppView alanını kullanır:

- `https://public.api.bsky.app` — resmî, önbellekli kamu alanı;
- `https://api.bsky.app` — resmî AppView ve kontrollü yedek uç.

Resmî belgeler: [arama sözleşmesi](https://docs.bsky.app/docs/api/app-bsky-feed-search-posts),
[API hostları](https://docs.bsky.app/docs/advanced-guides/api-directory),
[kota açıklaması](https://docs.bsky.app/docs/advanced-guides/rate-limits),
[Bluesky koşulları](https://bsky.social/about/support/tos).

## Uçtan uca teslim

1. `content source-add --provider bluesky` sabit resmî kaynağı sürümlü kaydeder.
2. Mevcut watch, donmuş firma/kuruluş/tedarikçi kimliklerini adaptöre verir.
3. Adlar, domainler ve alias'lar hedefler arasında adil sırada tekil sorgulara çevrilir.
4. Her sorgu en güncel genel sayfayı, toplam işlem/öğe/süre bütçesi içinde okur.
5. Bütçe biterse sorgu indexi kaydedilir; kapsam değişirse hash değişir ve sessiz baseline yeniden başlar.
6. Yalnız gönderi URI'si, metni, oluşturulma/indeks zamanı ve kanonik bağlantısı normalleştirilir.
7. Mevcut Betterleaks kontrolü metni kalıcı kayıttan önce maskeler; tarayıcı çalışmazsa yalnız metaveri kalır.
8. SQLite kanıt/eşleşme/değişiklik/inbox işlemi atomik ve idempotent kalır.
9. `content list/show/review/changes/report`, kuruluş görünümü, vaka, kuyruk ve firma JSON aynı kaydı kullanır.
10. `recover`, yedek/restore ve workspace sınırı mevcut P02 akışıyla değişmeden çalışır.

Yeni tablo, şema geçişi, bağımlılık veya paralel izleme servisi eklenmedi.

## Güvenlik ve dürüst kapsam

- Uç nokta kullanıcıdan alınmaz; yalnız iki resmî HTTPS hostu kullanılabilir.
- DNS her istekte genel IP'ye doğrulanır; özel IP ve tehlikeli yönlendirme kabul edilmez.
- Token, cookie ve hesap yoktur; özel hesap, DM veya giriş yapılmış sayfa okunmaz.
- Görsel, video, profil biyografisi, takipçi/beğeni listesi ve embed gövdesi alınmaz.
- Ham sağlayıcı yanıtı, arama terimi veya gönderi kimliği log/kanıta yazılmaz; kimlik hash'lenir.
- Sağlayıcının cursor vermesi yalnız daha fazla sonuç olabileceğini gösterir; tam tarihsel arşiv denmez.
- 401/403/429, timeout ve bozuk JSON başarılı boş sonuçtan ayrıdır.
- Bir resmî uç 403/veri erişim hatası verirse kalan bütçe içinde yalnız diğer resmî uç denenir; çalışan uç checkpoint'e yazılır.

## Test ve canlı kabul kanıtı

Hedefli otomasyon:

- içerik adaptörü, yaşam döngüsü, platform ve kaynak yönetişimi toplam **56 test**;
- bozuk JSON, medya-only cevap, 429/cooldown, keyfî URL reddi, iki resmî uç failover'u;
- adil sorgu sırası, bütçe sonrası devam, scope değişiminde baseline, tekrar ayıklama;
- firma platform JSON'u, workspace çiti, yedek/restore ve kuyruk komşuları.

Son kodla tam regresyon paketi **3.671 testi 2.921,269 saniyede** hatasız
tamamladı; macOS'ta yalnız Linux çalışma zamanı isteyen **4 test** beklendiği
gibi atlandı. İlk tam koşunun açığa çıkardığı P09 komut uyumluluğu da ikinci
bir katalog oluşturmadan açık `sources history` komutuyla kapatıldı; ilgili
37 test ayrıca geçti.

Canlı kabul geçici `/tmp/xti-p10-acceptance.Njtv7P` alanında yapıldı; veri
repoya eklenmedi:

| Senaryo | Sonuç |
|---|---|
| SecureHup adı + `securehup.com` | 2 sorgu tamamlandı; o an 0 eşleşme. Bu güvenlik hükmü değildir. |
| Türkiye'den önbellekli kamu alanı | `public.api.bsky.app` CDN 403; ham gövde saklanmadan hata ayrıştırıldı. |
| Resmî AppView failover | `api.bsky.app` HTTP 200; aynı çalışma tamamlandı. |
| Pozitif gerçek yanıt | Genel `Bluesky` etiketiyle 10/10 metin normalleştirildi ve sessiz baseline'a kaydedildi. |
| İkinci tur | Checkpoint doğrudan `api` ucunu seçti; 1 istek, o sırada gerçekten yeni 1 kayıt/1 değişiklik. |

Pozitif örnek yalnız parser ve yaşam döngüsü kabulüdür; üçüncü kişilerin
metni dokümana veya kaynak depoya kopyalanmadı.

## Açık dış karar

Teknik kişisel kullanım hazırdır. Bluesky kullanıcı içeriğinin müşteriye
sunulan ticari üründe ne kadar süre saklanacağı, hangi alıntının gösterileceği
ve kullanım koşullarının bunu hangi kapsamda desteklediği henüz hukuk/ürün
onayı almamıştır. Bu yüzden `content:bluesky-public-search` teknik olarak
`active`, fakat `commercial_use`, `retention_policy` ve `customer_display`
alanlarında `review_required` kalır. Yeniden dağıtım kapalıdır.

Bu açık karar [N-054](../../NOTES.md) ve
[ticari kaynak değerlendirmesinde](../COMMERCIAL_SOURCE_REVIEW.md) izlenir.
