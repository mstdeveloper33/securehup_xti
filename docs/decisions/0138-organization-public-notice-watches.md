# 0138 — Kuruluş kapsamlı kamu olay izlemesi ve yerel bildirim

Durum: kabul edildi, 0.136.0. Tarih: 15 Kasım 2026.

## İhtiyaç

Ortak HIBP kataloğunun yenilenmesi tek başına belirli bir kuruluş için
bildirim isteği değildir. Kullanıcı izlemeyi açıkça açabilmeli, ilgili
kayıtların neden değiştiğini görebilmeli ve eski katalog kayıtları yeni
olay gibi sunulmamalıdır.

## Karar

- Kuruluş başına tek yerel izleme tanımı bulunur. Açma/kapatma açık kullanıcı
  işlemidir; geçmişi korunur, kaynak sorgusu başlatmaz. Kapalı tanımlar ve
  geçmiş bildirimler silinmez.
- Etkin izlemeler mevcut HIBP yenilemesiyle ilerler. Bağımsız yenileme,
  `collect DOMAIN --task notices-hibp` ve zamanlanan profil aynı kayıt yolunu kullanır.
  Tek katalog isteği bütün açık kuruluş izlemelerine hizmet eder.
- Kapsam, etkin kuruluşun etkin domain bağlantılarıdır. Kaynak domainiyle
  tam eşleşme kullanılır; isim, benzer yazım veya alt alan üzerinden örtük
  sahiplik/ihlal çıkarılmaz. Sosyal ve ransomware izlemeleri domain yerine
  kullanılmaz.
- Her çalışma kuruluş ve bağlantı olaylarına bağlı tarihî kapsam taşır.
  Yeniden etkinleştirme dönemleri domain başına izlenir. Yeni kapsam ilk
  ölçümde sessizdir; başka bir domaine ait devam eden izleme susturulmaz.
  Salt isim veya bağlantı açıklaması değişikliği başlangıcı sıfırlamaz.
- Başlangıçtan sonra yeni/değişen ilgili kayıtlarda çalışma başına tek yerel
  bildirim oluşur. Tekrar, kaynak hatası ve yalnız kayıttan çıkma bildirim
  üretmez. Çıkma tarihî sonuçta görünür; sorunun çözüldüğü anlamına gelmez.
- Kaynak çalışması, farklar, bütün izleme sonuçları, yerel bildirimler ve
  varsa toplama tamamlanma bağı tek veritabanı işleminde kaydedilir. Bir
  bölüm başarısızsa tamamı geri alınır. Başarılı commit sonrasındaki kesinti
  önceki toplama devam sözleşmesiyle korunur.
- Bildirim kanıtı güncel katalogdan tahmin edilmez. Kesin kaynak çalışması,
  önceki sonuç ve dondurulmuş kapsam üzerinden before/after metadata yeniden
  doğrulanır. HIBP atfı, lisansı ve kaynak sınıfları bütün görünümlerde korunur.
- Inbox okuma durumu insanın tehdit değerlendirmesinden ayrıdır. Liste ve
  ayrıntı salt okunur; yalnız açık `inbox read` / `inbox unread` seçimi okundu durumunu değiştirir.
  İlk sayfa sınırlıdır; izleme çalışma ayrıntısının devam sayfaları vardır.
- Değişmeyen kayıtlar da aynı sıralı sayfalarda bulunur. Eski çalışma ve
  tanım olayları ayrı offset'lerle gezilir. Aynı kaynak olayının domaini
  sürekli izlenen A'dan yeni kapsam B'ye geçerse A çıkışı ve B başlangıcı
  ayrı etiketlenir; mevcut eşleşme toplamı tek kayıt kalır, bildirim oluşmaz.
- Silinmez izleme olay/çalışma sıraları kalıcı SQLite sayacıyla karşılaştırılır;
  son çalışma ve bildirimin birlikte eksilmesi sessizce kabul edilmez.
  İç işleme yolu eski kaynak kimliğini, gerileyen kaynak sırasını ve
  etkinleştirmeden önceye düşen çalışma zamanını reddeder.

## Yapı ve veri korunumu

İş kuralları domain modellerinde, kullanıcı işlemleri küçük depo/kilit
portları üzerinden application katmanındadır. CLI yalnız bağlama ve
gösterimi yapar. SQLite adaptörü kaynak ve kuruluş kanıtlarını aynı okuma
kesitinde doğrular. Kuruluş raporunda bu tarihî bildirim akışı güncel domain
bulgularından ayrı gösterilir ve kesin kuruluş kimliğiyle sınırlandırılır.

Şema 62 eklemelidir. Açık migration önce benzersiz geri dönüş yedeği alır;
eski veriden izleme veya bildirim üretilmez. Eski 1–61 sürümleri kendi
tanımlarıyla doğrulanır; geri yükleme yalnız yeni dosyaya yapılır.

## Kabul

Başlangıç, tekrar, kaynak hatası, domain ekleme/çıkarma/yeniden bağlama,
kuruluş ve izleme kapatma/açma, aynı domaini kullanan iki kuruluş, önce/sonra
kanıtı, sayfalama, global bildirim sırası, okundu durumu, bozuk kanıtta
durma, atomik geri alma ve toplama kesintisinden devam sınanır. Mevcut
verinin kopyasıyla geçiş/yedekten dönüş ve gerçek ağ kapalı CLI kabulü yapılır.

Bu teslim vaka kanıtı ekleme, HTML rapor, e-posta/SMS, React/API veya LLM
uygulamaz. Yeni ücretli servis ve paket bağımlılığı getirmez.
