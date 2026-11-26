# ADR0201 — XposedOrNot yeni kullanımını kapat, tarihî kanıtı koru

**Tarih:** 26 Kasım 2026
**Durum:** Kabul edildi; ADR0190'ın yeni toplama kararını yürürlükten kaldırır.

## Bağlam

XposedOrNot verified-domain uç noktası sağlayıcı hesabında domain doğrulaması
ve API anahtarı ister. Tek sağlayıcı hesabı altında birden fazla müşterinin
domainini yönetmek, sağlayıcı hesabını müşteriler arasında ortak güven
sınırına dönüştürür. Her müşteriden ayrı hesap ve anahtar istemek ise müşteri
ürününü gereksiz yapılandırmaya bağlar; kullanıcı aynı tekil kontrolü doğrudan
sağlayıcının sitesinde de yapabilir. Parola önek kontrolü de merkezi,
çok-firmalı bir OSINT motorunda gerekli bir sürekli izleme yeteneği değildir.

## Karar

- `xposedornot_domain` yeni profil kaynağı değildir.
- Terminaldeki configure/status/identity, credential refresh ve parola kontrol
  komutları kaldırılır.
- Firma Platform v1 içindeki `darkweb.credential.refresh` işlemi ve ağ işlemi
  bildirimi kaldırılır.
- Üretim composition'ı XposedOrNot ağ, parola veya secret adaptörlerini kurmaz.
- Ekip teslimi XposedOrNot anahtarı aramaz ve eksikliğini gereksinim saymaz.
- Kaynak manifestleri silinmez; `disabled` ve tarihî/salt-okunur olarak kalır.
- Eski profil, maskeli credential turu, karar, vaka ve bütünlük zinciri
  okunabilir; eski `running` tur yalnız açık `darkweb recover` ile kesilmiş
  duruma getirilebilir.
- Veritabanı tablosu, eski provider kimliği ve tarihî adaptör ayrıştırma kodu
  silinmez. Bu değişiklik şema yükseltmesi veya veri dönüşümü yapmaz.
- Var olan özel config dosyaları otomatik silinmez. İşletici, artık kullanılmayan
  anahtarı sağlayıcıda iptal ettikten ve gerekli yedeği aldıktan sonra kendi
  secret yönetimiyle kaldırabilir.

## Güvenlik ve ürün sonucu

Yeni bir XposedOrNot isteğinin CLI, uygulama servisi veya Platform sözleşmesi
üzerinden başlatılabileceği desteklenen yol kalmaz. Müşteri XposedOrNot hesabı,
anahtarı veya domain doğrulamasıyla uğraşmaz. Geçmiş kanıt silinmediği için
rapor, vaka ve denetim izi doğrulanabilir kalır; ancak eski kanıt güncel durum
veya güvenlik hükmü olarak sunulmaz.

Aktif credential/domain maruziyeti ihtiyacında XTI'nın anahtarsız ve toplu
Lunar görünümü ile seçilmiş AIL metadata akışı kullanılabilir. Bunlar bireysel
credential doğrulaması değildir. Gelecekte yeni bir credential sağlayıcısı
seçilirse çok-firmalı yetki, veri minimizasyonu, ticari kullanım, saklama,
müşteri gösterimi ve canlı kabul ayrı bir ADR ve tam teslim paketi gerektirir.

## Geri dönüş

Bu karar sıradan bir feature flag ile geri çevrilmez. Yeniden etkinleştirme;
sağlayıcı sözleşmesi, tenant başına secret/yetki modeli, canlı kabul, kapasite,
kurtarma, katalog ve dokümantasyonun yeniden onaylandığı yeni bir sürüm ister.
Eski kodun repoda bulunması tek başına yeniden etkinleştirme yetkisi değildir.
