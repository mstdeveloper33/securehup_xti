# 0108 — Sınırlı Maigret kullanıcı adı önizlemesi

**Tarih:** 31 Ekim 2026  
**Durum:** Kabul edildi  
**Sürüm:** 0.110.0

## Bağlam

0107 numaralı kabul kapısı, ücretsiz sosyal kullanıcı adı kaynağı olarak
Maigret'in dar bir ayrı-süreç adaptörünü seçti. Yalnız aracı değerlendirmek
kullanıcıya sonuç vermiyordu; resmî repodaki işimize yarayan profil kontrolü
gerçekten çalıştırılmalıydı. Bununla birlikte Maigret'in kişi profilleme, Tor,
proxy, yapay zekâ, domain arama ve otomatik site-veritabanı güncelleme gibi XTI
kapsamı dışındaki özellikleri açılmamalıydı.

## Karar

Maigret 0.6.6, resmî `soxoj/maigret` reposunun
`b8747b98820f4df9d1baf23235db7b2cb55d0198` commit'inden isteğe bağlı bağımlılık
olarak `.venv` içine kurulur. XTI kaynak kodunu çatallamaz veya kendi deposuna
kopyalamaz. `brand username-preview`, Maigret'i kabuk kullanmadan ayrı süreçte
çalıştırır ve yalnız satır bazlı NDJSON sonucu kabul eder.

Kullanıcı tek bir kullanıcı adı ve en fazla on izinli platform verir. Varsayılan
liste GitHub, GitLab, Reddit, Instagram, TikTok ve YouTube'dur. Facebook,
Keybase, LinkedIn ve Twitter açıkça seçilebilir. Her istek için 5–30 saniye,
süreç ve çıktı için ayrıca üst sınırlar uygulanır.

Maigret'in incelenen paketli site veritabanı SHA-256 özetiyle doğrulanır. Her
çalışmada yalnız tam seçilen platform tanımlarını içeren geçici bir veritabanı
üretilir. Böylece upstream `source`/ayna davranışı seçilmeyen yan sitelere istek
gönderemez. Seçilen tanımların HTTPS adresleri platforma özgü host allowlist'iyle
yeniden doğrulanır. Beklenmeyen sürüm, veritabanı, host, çıktı, yönlendirilmiş
profil adresi, yinelenen alan veya boyut güvenli hata üretir.

Tor/I2P, proxy, Cloudflare aşma, otomatik güncelleme, yapay zekâ, permütasyon,
domain arama, özyinelemeli arama ve profil alanı çıkarımı kapalıdır. Ortamdan
proxy ve OpenAI anahtarı aktarılmaz. Geçici çalışma klasörü sonuçtan sonra
kaldırılır.

XTI yalnız platform adı, profil HTTPS adresi ve `found_unverified` durumunu
dönüştürür. Ham yanıt, çıkarılmış profil alanları ve üçüncü taraf kimlikleri
atılır. Sonuç veritabanına yazılmaz. Raporlanmayan platform “hesap yok”;
bulunan profil de sahiplik, marka ilişkisi veya taklit hükmü değildir.

## Sonuçlar

- Kullanıcı, açık kaynak reponun gerçek kodunu terminalden ücretsiz kullanır.
- Çekirdek XTI kurulumu Maigret ve onun geniş bağımlılık ağacını zorunlu almaz.
- Upstream davranışı sabit sürüm, commit, veri özeti ve dar komut profiliyle
  tekrarlanabilir kalır.
- Şema 46 değişmez; migration ve kullanıcı veri klasörü gerekmez.
- Kalıcı marka izlemesi, sessiz başlangıç, değişiklik farkı ve gerekçeli insan
  kararı sonraki ayrı teslimdir.

## Canlı kabul

31 Ekim 2026'da geçici veri yolu kullanılarak yalnız GitHub seçildi ve herkese
açık `octocat` hesabı bulundu. Komut başarılı tamamlandı; XTI veri klasörü
oluşturmadı. Bu kabul hesabın sahipliğine ilişkin bir doğrulama değildir.
