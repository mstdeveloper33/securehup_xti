# 0052 — İnsan seçimiyle OSV duyurusunu destek kanıtına bağlama

## Durum

Kabul edildi — 29 Ekim 2026.

## Bağlam

OSV önizlemesi duyuru adaylarını gösterir; bağlantıyı kopyalayıp genel kanıt ekleme
komutuna vermek mümkündür. Ancak seçilen adresin gerçekten aynı CVE'nin güncel OSV
kaydında bulunup bulunmadığı bu iki ayrı adım arasında doğrulanmaz. Otomatik ilk
bağlantıyı seçmek de insan kararını ve kaynak sınıflamasını ortadan kaldırır.

## Karar

- Kullanıcı inceleme kimliğini, tam HTTPS adresini, `vendor_advisory` veya
  `distribution_advisory` türünü ve kendi açıklamasını açıkça verir.
- Geçersiz girdiler ağ ve yazmadan önce reddedilir. İnceleme yerelden okunur; onun CVE
  kimliği kullanılarak güncel OSV kaydı alınır. Ağ sırasında yazma transaction'ı yoktur.
- Adres güncel kaydın `ADVISORY` kümesinde tam eşleşmeyle bulunursa mevcut destek
  kanıtı portundan eklenir; bulunmazsa veya kaynak hata verirse hiçbir kanıt yazılmaz.
- OSV kayıt özeti ve kimliği komut sonucunda görünür, fakat ayrı bir veritabanı tablosu
  oluşturulmaz. Kanıtın mevcut ekleme/güncelleme/iptal geçmişi aynen kullanılır.
- OSV üyeliği bağlantı içeriğinin doğruluğunu, üretici sahipliğini, backport durumunu
  veya varlık maruziyetini kanıtlamaz; insan kararı ve öncelik değişmez.
- Şema 22 korunur. Gizli otomatik seçim, HTTP başvurusu veya OSV'den karar üretimi yoktur.

## Sonuçlar

Önizleme ile kalıcı destek kanıtı arasında doğrulanabilir ve açık bir insan adımı oluşur.
Doğrudan üretici/dağıtım kaynağını güvenilir biçimde alma, içerik özeti ve imza/köken
doğrulaması hâlâ ayrı teslimlerdir.
