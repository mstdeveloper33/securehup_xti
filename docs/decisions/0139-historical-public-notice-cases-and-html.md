# 0139 — Tarihî kamu olay kanıtı ve tam çevrimdışı kuruluş raporu

Tarih: 15 Kasım 2026. Durum: kabul edildi, 0.137.0.

Kamu olayını güncel katalog kimliğiyle bağlamak kaynak değiştiğinde seçilen
kanıtı belirsiz kılar. Terminalin sayfalı raporunu HTML'e çevirmek de eksik
kayıtları tam rapormuş gibi sunabilir. Bu iki ihtiyaç mevcut vaka ve
kuruluş modellerinin üzerinde ayrı sözleşmelerle karşılanır.

## Karar

- Vaka türleri `public_notice` ve `public_notice_watch`; kimlik kanonik
  `RUN_UUID:Name`. Kaynak/izleme tarihçesi doğrulanır, tam önce/sonra kayıt
  yeniden oluşturulur. Değişmeyen ve çıkarılmış olay da seçilebilir; hata
  çalışması kanıt olamaz. Seçim terminal sayfasından bağımsızdır.
- Aynı izleme çalışmasında olay bir domainden diğerine geçerse bütün ilgili
  etkiler tek snapshot'a girer. Watch kuruluş kimliği ve tarihî üyelik
  olayları korunur; güncel üyelikten eski kapsam çıkarılmaz. Vaka payload'ı
  ilgili domain üyeleriyle sınırlıdır; tam kapsam SHA-256/üye sayısı ve
  azaltılmış olma bilgisi açık kalır.
- Yazma transaction'ında kaynak tekrar çözülür; gelen snapshot ile birebir
  karşılaştırılır. Mevcut vaka aktivite zinciri ortak yardımcıyla okuma ve
  değişim öncesinde doğrulanır. Yeni tarih ayrı kanıttır; eski snapshot ve
  insan kararı otomatik güncellenmez. `evidence-show` tam donmuş kaydı açar.
- Şema 63 yalnız `case_evidence` CHECK kısıtını iki türle genişletir.
  54–62 eski tanımları ayrı doğrulanır. Yedekli geçiş tek tabloyu transaction
  içinde yeniden kurar; rowid, alanlar, hash, FK ve tekillik korunur.
- `OrganizationExportService` okuma, render ve dosya portlarına dayanır.
  SQLite adaptörü tek readonly snapshot'ta bütün etkin hedefleri, bütün
  bölüm satırlarını ve kuruluşun tam kamu olay izleme geçmişini alır.
  Hedef/öğe/dosya sınırı aşıldığında hata verir; sessiz kesme yapılmaz.
- HTML renderer arayüz katmanındadır. Metin kaçırılır; dış betik, font,
  görsel veya JavaScript gerekmez. Kaynak URL'leri güvenli bağlantı olarak,
  terminal komutları yalnız metin olarak gösterilir. Yüzey kartları son
  kontrolü taşır; tüm eski yüzey kontrol serisi olduğu iddia edilmez.
- Dosya adaptörü özel izinli geçici dosyayı aynı klasörde oluşturur;
  fsync ve atomik no-overwrite yayın kullanır. Symlink yol ve mevcut hedef
  reddedilir; başarısızlıkta kendi özel geçici adı için temizlik denenir.
  Yayınlanmış son dosya hata temizliğinde silinmez. Yayından sonraki klasör
  fsync hatası tam dosya bırakabilir; kullanıcıya dosya yolu ve kalıcılık
  doğrulanamadığı açıkça bildirilir. Başka yazıcının son dosyasına dokunulmaz.

## Sonuç

Yeni servis/paket/API gerekmez. Kaynak sınıfları ve lisans korunur; kaynak
iddiası doğrulanmış ihlale dönüşmez. Kuruluş raporu ortak vakadan yalnız
ilgili kimlik/durum/kanıt bağlantısını taşır, özel notları ve diğer kuruluş
kanıtlarını kopyalamaz. React/API, LLM, gönderim ve gerçek Linux hizmet
kabulü bu teslimin kapsamı değildir.
