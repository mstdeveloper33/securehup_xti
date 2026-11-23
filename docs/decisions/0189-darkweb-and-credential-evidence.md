# ADR 0189 — Yeraltı ve kimlik maruziyeti kaynak iddiası olarak kalır

21 Kasım 2026. P05 uygulanmadan önce kabul edildi.

> **22 Kasım 2026 güncellemesi:** Aşağıdaki HIBP verified-domain seçimi
> [ADR0190](0190-xposedornot-credential-source.md) ile değiştirilmiştir.
> Güvenlik/veri minimizasyonu ilkeleri geçerlidir; yeni çalışma XposedOrNot
> kullanır, eski şema93 HIBP kayıtları yalnız denetlenebilir geçmiş olarak okunur.

XTI genel amaçlı Tor gezgini, çalınmış veri arşivi veya kimlik bilgisi
doğrulama aracı olmayacaktır. Dark/deep web kapsamı yalnız kaynağı, erişim
hakkı, saklama hakkı ve veri sözleşmesi açıkça seçilmiş adaptörlerden gelir.
Kamu ransomware kayıtları bütün dark web kapsamı sayılmaz; forum, pazar,
paste ve kapalı kanal kapsamı ancak ayrı kaynak kabulünden sonra eklenir.

Ransomware ilanı, ihlal kataloğu, forum yazısı ve credential eşleşmesi
kaynağın iddiasıdır. XTI bunları gerçekleşmiş ihlal, çalınmış hesabın hâlâ
aktif olduğu veya parolanın geçerli olduğu hükmüne dönüştürmez. Kaynak
kimliği, kaynak çalışma zamanı, özgün kayıt kimliği, kanıt özeti ve eşleşme
gerekçesi korunur. İlk tur sessiz başlangıçtır; değişmeyen kaynak kanıtı yeni
bildirim üretmez. İnsan kararı kanıt ve gözlem sürümüne bağlıdır.

HIBP domain araması yalnız HIBP hesabında önceden doğrulanmış, XTI kuruluş
kapsamında kayıtlı kesin domain için kullanılabilir. API anahtarı ve kuruluş
pseudonym anahtarı kullanıcı yapılandırma dizininde, yalnız sahibine açık
dosyalarda tutulur; şirket JSON'una, SQLite'a, terminal çıktısına veya git'e
girmez. HIBP'nin döndürdüğü alias yalnız bellekte normalleştirilir. Veritabanı
yalnız maskeli hesap görünümü, kuruluş anahtarıyla HMAC kimliği, domain ve
ihlal adlarını saklar. Parola, cookie, token, stealer-log secret değeri veya
ham e-posta saklanmaz ve hiçbir hesapta denenmez.

Kuruluş pseudonym anahtarının yedeği operatör sorumluluğundadır. SQLite
yedeği tek başına eski maskeli kanıtı okumaya yeter; yeni kaynak turunda aynı
kimliklerle değişim hesaplamak için aynı özel anahtar gerekir. Anahtar yoksa
motor eski kayıtları değiştirmez, canlı credential kaynağını açıkça
`missing_credentials` durumunda bırakır.

Mevcut ThreatCluster, RansomLook ve HIBP kamu katalog geçmişleri yeniden
kopyalanmaz. P05 dondurulmuş tek okuma kesitinde bu kaynaklara başvurur;
credential geçmişini ayrı hassas tabloda tutar. Sağlayıcılar arası aynı olay
çıkarımı otomatik birleştirme değildir. Firma ve tedarikçi adı/domain bağı
tam, açıklanabilir kurallarla kurulur; benzer ad tek başına alarm değildir.

Terminal, engine ve company platform aynı uygulama servisini kullanır.
Anahtar isteyen kaynak çağrısı güvenilen operatör/worker bileşimindedir;
salt-okunur engine hiçbir ağ veya credential dosyası açmaz. Platform firma
seçimini güvenilen başlatıcı yapar ve yazmalar workspace çitiyle korunur.
