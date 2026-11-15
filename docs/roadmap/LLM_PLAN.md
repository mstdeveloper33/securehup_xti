# Gelecekteki LLM desteği

**Karar tarihi:** 13 Kasım 2026. **Durum:** Kullanıcı isteğiyle gelecekteki plana alındı; henüz uygulanmadı. Bu belge model kurmaz, bir sağlayıcı seçmez veya ücretli hizmet açmaz.

**15 Kasım 2026 sınırı:** LLM bu repoda isteğe bağlı motor yeteneğidir;
kaynaklı taslak üretir. Sonuçların ürün ekranında sunumu, kullanıcı oturumu
ve rol kararı mevcut .NET platformundadır. Motorun doğrulanmış kapsam ve
kanıt kontrolü sürer. [Güncel motor planı](ENGINE_INTEGRATION_ROADMAP.md).

## Kullanıcıya sağlayacağı işler

LLM, platformun topladığı ve kaynağı belli kayıtları anlamayı kolaylaştıran isteğe bağlı analiz yardımcısı olacak. Yeni kaynakların yerine geçmeyecek; internet kapsamını kendiliğinden artırmayacak. Önce mevcut kayıtlarla başlayacağız.

| Kullanım | Kullanıcının isteği | Beklenen çıktı |
|---|---|---|
| Bulguyu açıklama | “Bu kayıt neden önemli?” | Dayanak, belirsizlik ve insanın kontrol edebileceği sonraki adım |
| Günlük özet | “Bugün neler değişti?” | Yeni/değişen kayıtlar, eski kanıtlar ve veri alınamayan kaynaklar |
| Vaka taslağı | “Bu vakayı anlaşılır özetle.” | Olay sırası, kaynaklı kanıtlar, açık sorular ve rapor taslağı |
| Sonraki teslim: yerel soru-cevap | “Bu domain için son hafta ne değişti?” | Seçilen kayıt aralığına dayanan yanıt ve özgün kayıtlara bağlantılar |
| Sonraki teslim: inceleme önerisi | “Önce hangilerine bakmalıyım?” | Açık gerekçeli öncelik önerileri; nihai insan kararı ayrı |
| Sonraki teslim: ilişki önerisi | “Bu olaylar bağlantılı olabilir mi?” | Ortak kanıtı gösteren aday ilişki; doğrulanmış aktör/kampanya atfı değil |

Örnek: benzer domain bulunduğu, sayfa içeriğinin kontrol edilmediği bir kayıtta beklenen açıklama “Marka adına benzerlik var; mevcut kanıt phishing kararı için yeterli değil” olur. Model eksik kontrolü yapılmış gibi anlatamaz. Ransomware kaynağındaki bir iddiayı doğrulanmış ihlale veya aynı kullanıcı adını kimlik/sahiplik kanıtına çeviremez.

## Uygulama sırası

1. **AIM-01 — Küçük deney:** Seçilmiş, insan tarafından değerlendirilmiş örneklerle mevcut LLM'siz çıktıyı temel al. Mevcut cihazda uygun yerel model adaylarını kalite, süre ve bellek kullanımıyla karşılaştır. Kaynakları az olan bir kişisel kurulumla başlayabilmeli.
2. **AIM-02 — Açıklama ve özet:** Terminalde isteğe bağlı bulgu/günlük/vaka açıklaması sun. Önce kararları etkilemeyen deneme çıktıları üret; yarar görüldüğünde kullanıma aç. Ham sonuçlar ve kaynak bağlantıları her zaman erişilebilir kalsın.
3. **AIM-03 — Yerel soru-cevap ve öneriler:** Önceden tanımlanmış salt okuma aramalarını kullan. İnceleme sırası, metinden varlık ve ilişki önerilerini ayrıca ölç; insanın onayı olmadan gerçek kayıt/karar oluşturma.
4. **AIM-05 — Her aşamada sürüm ve geri dönüş:** Kullanılan model, ayarlar, talimat şablonu, kanıt anlık görüntüsü ve değerlendirme sürümünü kaydet. Her değişiklikte aynı kontrolleri tekrar et; kalite gerilerse önceki sürüme dön.

AIM-04 kapsamındaki araç/MCP ve çok adımlı otomasyon ilk LLM teslimine dahil
değildir. LLM çalışması web paneli, REST API, TAXII, Linux arka plan hizmeti
veya bütün veri kaynaklarının tamamlanmasını beklemez. 15 Kasım 2026
[motor entegrasyon planı](ENGINE_INTEGRATION_ROADMAP.md) uygulama backend'i
ve oturumu .NET'e bırakır; LLM'nin kaynak, yetki ve kanıt sınırları değişmez.
Takım kullanımında model girdisi, arama ve saklanan taslak için müşteri
kapsamı ayrıca doğrulanır; dış platformun LLM özelliği kendiliğinden açılmaz.

## Mimari ve veri sınırı

Planlanan akış:

```text
Kayıtlı kanıt ve kaynak durumu
  → kapsam ve veri seçimi
  → isteğe bağlı analiz servisi
  → model sözleşmesi / değiştirilebilir sağlayıcı adaptörü
  → yanıt biçimi ve kanıt referansı kontrolü
  → terminalde kaynaklı taslak
  → insan değerlendirmesi
```

- Toplama, eşleştirme, kaynak sağlığı ve vaka yönetimi model kapalıyken de çalışır. Model hatası veya zaman aşımı mevcut bulguyu gizlemez ve toplama işini başarısız yapmaz.
- İlk sürüm serbest SQL, kabuk komutu, yeni internet sorgusu veya dış eylem çalıştırmaz. Sonraki yerel sorgu asistanı yalnız belirlenen okuma servislerine erişir; kapsam kontrolü modelin kararına bırakılmaz.
- Modele yalnız ilgili ve boyutu sınırlandırılmış kanıtlar verilir. Kaynak zamanı, kayıt kimliği ve iddia niteliği korunur. Bağlam sınırı nedeniyle dışarıda kalan bilgi belirtilir; kısmi özet tam kapsam gibi gösterilmez.
- Ham kanıt, model yorumu ve insan kararı ayrıdır. Taslak kaydedilecekse ayrı bir kayıt ve sürümlü şema değişikliği kullanılır; özgün kanıt ve insan inceleme geçmişi üzerine yazılmaz.
- Kaynak metinlerindeki “şunu çalıştır” türü ifadeler veri sayılır. Modelin kaynak metni görmesi ona komut çalıştırma yetkisi vermez.
- Kanıt referansının gerçekten varlığı ve doğru kapsama ait olması yazılım tarafından kontrol edilir. Referansın bulunması yorumun doğru olduğunu tek başına kanıtlamaz; içerik doğruluğu ayrıca değerlendirilir. Geçersiz referanslı yanıt kullanıcıya doğrulanmış açıklama gibi sunulmaz.
- Model yanıtları terminale güvenilmeyen metin olarak aktarılır; terminal kontrol karakterleri/biçimlendirme yoluyla işlem veya görünüm yanıltması önlenir.
- Model yeni CVE/sürüm tahmini yapmaz; çıkarılmış ürün/paket/zafiyet kapsamını tekrar açmaz. Alarmı kendiliğinden silmez, gizlemez veya kapatmaz; takedown, mesaj gönderme, engelleme ya da aktif test başlatmaz.

## Yerel model ve maliyet kararı

İlk değerlendirme mevcut cihazda çalışabilecek, lisans ve kullanım koşulları uygun bir yerel modelle yapılacak. Model adı, boyutu ve çalıştırıcısı donanım/Türkçe kalite ölçülmeden sabitlenmeyecek. Adayın sürümü ve indirilen dosyaların bütünlüğü sabitlenecek; değişiklik ayrı değerlendirmeden geçecek. Yerel çalıştırmada API ücreti olmayabilir; bellek, işlem süresi, disk ve elektrik ihtiyacı vardır. “Ücretsiz ve sınırsız performans” taahhüdü verilmez.

Model indirme ve çalıştırma standart kurulumdan ayrı, açık seçim olacak. Mevcut bağımlılıklar model paketlerine bağlanmayacak. Daha sonra harici API gerekirse hangi verinin gönderileceği, sağlayıcının saklama koşulları, süre ve harcama sınırı ayrıca kararlaştırılacak. Yerel model hatasında sessizce ücretli/dış sağlayıcıya geçilmeyecek. Parolalar, API anahtarları ve gereksiz kişisel veri model girdisinden çıkarılacak; kayıtlar bunları içermeyecek.

## Faydayı nasıl ölçeceğiz?

Ayarlama örnekleri ile kabul test örnekleri ayrılacak; aynı olayın kopyaları iki kümeye dağıtılmayacak. Türkçe ve İngilizce örneklerde normal haber, şüpheli aday, eski/tekrarlanan iddia, aynı isimli farklı kuruluş, eksik kanıt, çelişen kaynak ve kaynak kesintisi bulunacak. Dış metne gömülü yanıltıcı talimatlar da sınanacak.

| Ölçüm | Kontrol |
|---|---|
| Kanıta bağlılık | Maddi iddiaların doğru özgün kayda dayanması; uydurulmuş kaynak/kayıt olmaması |
| Eksik ve yanlış bilgi | Önemli bulguyu atlama, kesintiyi “sonuç yok” sayma, iddiayı kesinleştirme sayısı |
| Belirsizlik | Yeterli kanıt olmadığında bunu açık söylemesi; modelin kendi güven yüzdesini doğruluk saymaması |
| Kullanıcı faydası | Aynı işi LLM'siz ve LLM'li çıktıyla inceleme süresi ve doğru değerlendirme oranı |
| İşletim | Tipik ve yavaş yanıt süreleri, tepe bellek, disk, zaman aşımı ve varsa çağrı maliyeti |
| Dayanıklılık | Model yokken/hatalıyken çekirdeğin çalışması, kapsam dışı veriye/eyleme erişememesi |

İlk kabulden önce veri kümesi, ölçüm yöntemi ve sayısal eşikler kaydedilecek; sonuç görüldükten sonra eşiği düşürerek kabul verilmeyecek. Kabul kümesinde uydurma kaynak, insan kararının izinsiz değişmesi veya kapsam dışı eylem görülürse ilgili sürüm kabul edilmeyecek. Diğer kalite eşikleri LLM'siz başlangıç ölçümü ve gerçek kullanım ihtiyacına göre belirlenecek. Testlerin geçmesi gerçek kullanımda sıfır hata garantisi değildir.

LLM'li sürüm ölçülmüş yarar sağlamıyorsa deney olarak kalacak veya kapatılacak. Model/talimat güncellemesinde kalite ve kaynak kullanımı yeniden ölçülecek. Kullanıcı bir açıklamayı hatalı işaretleyebilecek; bu geri bildirim otomatik eğitim veya dışarı veri aktarımı başlatmayacak.

İlgili kayıtlar: [ana plan R12](MASTER_ROADMAP.md#r12--ai-destekli-analiz-ve-denetimli-iş-akışları), [AIM işleri](BACKLOG.md#r12-ai-ve-denetimli-otomasyon), [yetenek matrisi](CAPABILITY_MATRIX.md#11-ai-ve-araç-tabanlı-iş-akışları), [uygulanmış durum](../STATUS.md).
