# 0102 — İkinci açık ransomware kaynağı olarak RansomLook önizlemesi

- **Durum:** Kabul edildi
- **Tarih:** 30 Ekim 2026
- **Sürüm:** 0.104.0

## Bağlam

ThreatCluster ransomware iddiaları için çalışır bir açık akış sağlıyor; ancak tek
kaynağa dayanmak kapsam boşluğunu ve kaynak kesintisini ayırt etmeyi zorlaştırır.
İkinci kaynak ücretsiz, kişisel kullanıma uygun, bakımda, yapılandırılmış, dar ve
güvenli olmalıdır. Kaynak yalnız doğrulanmamış grup iddiaları taşır; çalınmış veri
veya ham leak-site içeriği toplanmamalıdır.

## Karar

Sürümlü `public-ransomware-source-gate-v1` kabul kapısı altı zorunlu ölçüt
kullanır: etkin bakım, anahtarsız ücretsiz erişim, yapılandırılmış dar çağrı,
açık yeniden kullanım koşulu, bağımsız toplama hattı ve güvenli asgari içerik.

30 Ekim 2026 değerlendirmesinde:

- RansomLook altı ölçütün tamamını geçti ve seçildi.
- RansomWatch deposu 3 Mart 2026'da arşivlendiği ve güncel dar uç nokta yerine
  tam üretilmiş dosya sunduğu için güncel akış olarak reddedildi.
- Darkfield açık gözlemevi olarak değerlidir; fakat geniş API anahtar/kota
  kullanır ve yöntemi birden çok üst kaynağı birleştirir. Anahtarsız dar sözleşme
  ile kaynak çakışması sabitlenene kadar ertelendi.

RansomLook yalnız `ransomware recent --source ransomlook` ile yazmasız son-yedi-
gün önizlemesi sağlar. Adaptör sabit açık HTTPS API adresine tek istek gönderir;
yönlendirme ve sıkıştırmayı kabul etmez, 30 saniye, 2 MiB ve 10.000 kayıt sınırı
uygular. Tam JSON alan kümesi, görünür metin, tekillik ve UTC zaman penceresi
bütün sonuç gösterilmeden doğrulanır.

Kaynak sadece grup adı, gönderi başlığı ve keşif zamanı verdiğinden ayrı domain
modeli ve port kullanılır. XTI ülke, sektör, domain, ilan durumu veya ihlal hükmü
uydurmaz. Veri ThreatCluster snapshot/izleme tablolarına yazılmaz ve kaynaklar
otomatik birleştirilmez. Tor/leak-site adresi, ham gönderi, ekran görüntüsü veya
çalınmış veri alınmaz.

RansomLook API yanıtları ve veri kümeleri CC BY 4.0 koşuluyla kullanılır ve
terminal/JSON çıktısında kaynak/lisans atfı korunur. XTI sağlayıcının yazılım
kodunu kopyalamaz; yalnız açık API'yi bağımsız adaptörle okur.

## Sonuçlar

İkinci bağımsız kaynak güvenle araştırılabilir, fakat henüz kalıcı geçmiş,
izleme, bildirim veya kaynaklar arası teyit sağlamaz. Bu sınırlama eksik alanları
tahmin ederek gizlenmez. 30 Ekim 2026 canlı kabulünde 266 kayıt doğrulandı, üç
sınırlı kayıt gösterildi ve veri dizini oluşturulmadı.

Sonraki dar teslim, RansomLook için kaynak kimliğini ThreatCluster'dan ayıran
kalıcı geçmiş ve kuruluş adı izleme tasarımıdır. Kaynaklar arası benzerlik ancak
iki özgün kayıt da korunarak, insan incelemesi için açıklanabilir aday şeklinde
sunulabilir.

## Resmî dayanaklar

- <https://github.com/RansomLook/RansomLook>
- <https://www.ransomlook.io/doc/>
- <https://github.com/RansomLook/RansomLook/releases>
- <https://github.com/joshhighet/ransomwatch>
- <https://darkfield.orizon.one/about>
- <https://darkfield.orizon.one/methodology>
- <https://darkfield.orizon.one/pricing>
