# 0140 — Yerel arama, kaynağa özel tedarikçi izlemesi ve ilişki geçmişi

**Tarih:** 15 Kasım 2026 · **Durum:** Kabul edildi · **Sürüm:** 0.138.0

Kullanıcı mevcut kanıtları tek yerden bulmak, tedarikçiyle ilgili yeni kaynak
kayıtlarını kaçırmamak ve bir domainin önceki bağlantılarını incelemek istiyor.
Yeni ücretli servis veya toplama altyapısı bu iş için gerekli değil.

## Karar

- Üç ayrı domain/application/port ve SQLite/terminal adaptörü kullanılır.
  Arama ve ilişki raporu kendi içinde tek readonly transaction alır. Ortak
  okuyucular bağlantı kabul eder; farklı anlarda açılan depolar bir raporda
  birleştirilmez. Mevcut CTI araması aynı bağlantıdan okuma yardımcısını
  paylaşır; eski dış arayüzünü korur.
- Arama on kayıt ailesini kapsar. Global sıralama ve sayfalama bütün
  eşleşmelerden hesaplanır. Kapsam ve son kaynak durumu sonuçlarla taşınır.
  `--all` son bilinen pasif/tarihî kayıtları ekler; tam sürüm arşivi değildir.
- Tedarikçi izlemesi `(supplier_id, source_key)` ile açıkça seçilir.
  ThreatCluster/RansomLook iddiaları ve HIBP metadata birbirine karıştırılmaz.
  İsim eşleşmesi kimlik doğrulaması değildir; domain dayanağı ve aynı isim
  belirsizliği görünür kalır.
- Tedarikçi olayları tekrar yürütülerek güncel ve tarihî kimlik doğrulanır.
  İzleme sonucu gerçek kaynak çalışma yabancı anahtarına, tedarikçi olay
  sıra sınırına, izleme açma olayına, önceki sonuca ve kapsam/sonuç özetlerine
  bağlıdır. Sonraki değişiklik eski bildirim içeriğini yeniden yazmaz.
- Başlangıç, yeniden açılan izleme veya değişen tedarikçi kimliği sessizdir.
  Önceki ve yeni kaynak eşleşmelerindeki ekleme/değişme yerel bildirim üretir;
  çıkarılma, hata veya tekrar üretmez. Bildirim kaynağın kesin yeni ihlal
  duyurduğu veya müşterinin etkilendiği anlamına gelmez.
- Kaynak uygulanırken izleme ve bildirim aynı transaction içinde yazılır;
  collection receipt bu işlemden sonra aynı commit'e katılır. Herhangi bir
  kayıt aşaması hata verirse hepsi geri alınır. Kaynak hatası son başarılı
  karşılaştırmayı ilerletmez. Bozuk geçmiş ağ isteğinden önce denetlenir.
- İlişki raporu bütün kayıtlı kontrol serisini okur. Kontrol hatası ilişki
  kaybı sayılmaz; ilk/son gözlem kesintisiz geçerlilik süresi değildir.
  Eski insan kararlarının saklamadığı CNAME çalışma bağı sonradan üretilmez.
- Şema 64 dört tablo ekler. Geçiş açık komutla, benzersiz yedekle yapılır;
  eski satırlar, rowid, SQL tanımları ve sıra sayaçları korunur. Kurtarma
  yalnız yeni hedefe yapılır. Şema doğrulaması statik kolon/anahtar/indeks/FK
  beklentileriyle ve yeni DDL kısıtlarıyla karşılaştırılır.

## Sonuçlar

Yeni bağımlılık ve dış servis yoktur. Kaynak yenilemeleri mevcut erişim
koşullarına tabidir. Açık kapasite sınırları eksik sonuç döndürmek yerine
hata verir. Bu ilk sürüm kişisel SQLite kullanımına uygundur; büyük hacimde
okuma maliyetleri ölçülerek ayrı arama deposu değerlendirilebilir. Bugünden
Kafka/OpenSearch zorunluluğu oluşturulmaz.

Otomatik HTML rapor arşivi başlangıçta bu teslimin dışında bırakılmıştır.
15 Kasım 2026 kullanıcı kararıyla gelecek plandan da çıkarılmıştır; mevcut
komutla HTML dışa aktarımı korunur. Web paneli, LLM ve dış bildirim kanalı
bu teslimde eklenmez; sonraki arayüzler aynı application sözleşmelerini
kullanabilir.
