# ADR 0191 — Aksiyonlar kanıtlı, tekrar güvenli ve insan onaylıdır

22 Kasım 2026. P06 uygulanmadan önce kabul edildi.

XTI, dış platformlara otomatik takedown başvurusu göndermeyecek, IOC'yi
otomatik engelleme listesine basmayacak ve case paketini kendiliğinden
paylaşmayacaktır. Motor kanıtı dondurur, önerilen adımları vaka görevlerine
dönüştürür, başvuru taslağını hazırlar ve insanın dışarıda yaptığı işlemin
referansını/değişimini kaydeder.

Runbook planı vaka ve etkin kanıt özetine bağlıdır. Plan görüldükten sonra
vaka değişirse uygulama reddedilir; başarılı uygulama tek transaction ve
tekrar anahtarıyla yürür. Şablon kimliği ve sürümü geçmiş makbuzda korunur.

Takedown taslağı yalnız aynı vakadaki etkin, desteklenen kanıttan üretilebilir.
`draft`, `approved`, `submitted`, `acknowledged`, sonuç ve iptal durumları
katı geçişlerle ilerler. `submit` gerçek ağ işlemi değildir: dış başvurunun
insan tarafından yapıldığını ve sağlayıcı referansını kaydeder. Olay zinciri,
beklenen sürüm ve önceki olaya bağlı anlık görüntü hash'leri bozuk kaydı
güvenli biçimde durdurur. Başarılı oluşturma isteğinin tekrar anahtarı,
sonraki vaka değişikliklerinden bağımsız aynı makbuzu döndürür; yeni onay
ise açık vaka ile hâlâ etkin ve değişmemiş kanıtı yeniden doğrular.

Vaka paketi yeni dizine özel izinlerle atomik yayınlanır. Teknik JSON, HTML,
CSV ve isteğe bağlı ağsız PDF aynı donmuş vaka görünümünden gelir; manifest
dosya boyutları ve SHA-256 özetlerini taşır. Paket bir dijital imza değildir;
manifest özeti güvenilir ayrı kayıtta tutulursa sonradan karşılaştırılır.

Toplu IOC girişi önce yazmasız doğrulanır. Bütün kayıtlar doğrulanmadan
transaction başlamaz; çelişen tekrar tüm dosyayı reddeder. CSV elektronik
tablo formüllerine karşı geri döndürülebilir kodlanır. JSON kesin şemadır;
STIX yalnız XTI'nın desteklediği indicator alt kümesidir. Geniş STIX/TAXII
servisi bu kararın kapsamında değildir.

Dosya yolu alan paket/IOC işlemleri şirket platform JSON sözleşmesine
açılmaz. Güvenilen operatör CLI'sı kullanılır; ilerideki .NET katmanı kendi
yetkili yükleme/indirme alanını yönetir. Engine salt okunur ve ağsızdır;
firma yazmaları workspace çiti taşır.

Kullanıcı kararıyla P06'nın haricî SIEM/SOAR/ticket bağlayıcı maddesi
kapsamdan çıkarılmıştır. Bu dış bağlantılar yapılmış sayılmaz ve P06'nın
yerel aksiyon kabiliyetlerini dış sistemlere bağımlı kılmaz.
