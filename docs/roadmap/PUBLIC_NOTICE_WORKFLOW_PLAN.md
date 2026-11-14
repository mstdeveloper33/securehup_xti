# Kamu olaylarını günlük akışa bağlama

15 Kasım 2026. Kullanıcının kuruluş raporu sonrasındaki “Devam edelim”
yönlendirmeleriyle dört teslim uygulandı. Bu liste yeni ücretli servis
gerektirmeyen, mevcut kaynağı ve yerel uygulamayı kullanan devam sırasıdır.

| Adım | Kullanıcı sonucu | Durum |
| --- | --- | --- |
| 1. Toplama/profil/zamanlama | `notices-hibp` ile aynı günlük çalışmada katalog yenileme; kesintide tamamlanan kaydı koruma | 0.135.0'da uygulandı |
| 2. Kuruluş izleme/bildirim | Açık kapsamda yeni/değişen ilgili olay için yerel kutu; ilk tarihî katalog ve yeni domain sessiz | 0.136.0'da uygulandı |
| 3. Vaka kanıtı | Tam olay + kaynak çalışma kimliğiyle tarihî kaydı vakaya bağlama | 0.137.0'da uygulandı |
| 4. Okunabilir dosya raporu | Kaynak bağlantılı, çevrimdışı açılan HTML kuruluş raporu | 0.137.0'da uygulandı |

İlk adım kayıtlı domaini, mevcut profil formatını ve aynı Linux zamanlama
akışını kullanır. HIBP ortak katalogdur; her domain için ayrı istek veya
hesap sorgusu yapılmaz. Otomatik bildirim, vaka ekleme veya rapor dosyası
bu ilk adımın yan etkisi değildir. İkinci adımda ayrıca açık kuruluş izleme
seçimiyle bildirim üretilebilir; yenileme bütün açık izlemeleri ilerletir.
Profilin tam seçimi kullanıcı tarafından
kaydedilir; mevcut profillere görev eklenmez. Kaynak hatası, başarılı boş
eşleşme ve başlangıç farklı durumlardır.

Ücretli API veya yeni paket gerektirmez; dış kaynağın erişim/kota koşulları
korunur. React/API, LLM, geniş marka, e-posta/SMS ve TAXII ayrı gelecek
teslimlerdir. Common Crawl dış erişimi ve gerçek Linux hizmet kabulü açık
konulardır; zamanlama dosyası üretmek canlı hizmet doğrulaması değildir.

Uygulanmış davranış ve test sonucu [STATUS](../STATUS.md), kullanıcı
komutları [günlük kullanım](../DAILY_USE.md) belgesindedir.

Sonraki önerilen sıra: gerçek Linux üzerinde klonla–kur–çalıştır kabulü,
zamanlayıcı/kesinti/yedekten dönüş kontrolü; ardından gerçek kullanımda
kaynak katkısı ve erişim boşlukları. Common Crawl dış erişimi ayrı takip
edilir. Ücretli API, React/API veya LLM bu sıraya otomatik eklenmez.
