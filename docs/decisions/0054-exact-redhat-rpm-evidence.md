# 0054 — Dağıtım bağlamlı kesin Red Hat RPM kanıtı

**Durum:** Kabul edildi · **Tarih:** 29 Ekim 2026 · **Sürüm:** 0.54.0

## Karar

Red Hat VEX beyanlarını yerel varlıkla ilişkilendirmeden önce paket kimliği ayrı, kullanıcı doğrulamalı ve eklemeli geçmişi olan bir envanterde tutulur. Kimlik; varlık, sağlayıcı/ekosistem, paket adı, epoch, sürüm, release, mimari ve kesin Red Hat Enterprise Linux CPE bağlamından oluşur. Kaynak RPM biliniyorsa kanıtın parçasıdır; bilinmiyorsa boş kalır.

PURL kullanıcıdan alınmaz. Doğrulanmış paket adı, sürüm, release ve mimariden Red Hat RPM biçiminde üretilir; epoch ayrıca kaybolmadan saklanır. Genel `asset_products` kayıtları yeni tabloya dönüştürülmez, çünkü bu kayıtlarda RPM release, mimari ve dağıtım bağlamı yoktur.

## Güvenlik ve veri sınırı

- Yalnız `redhat`/`rpm` ve dar Red Hat Enterprise Linux CPE biçimi kabul edilir.
- Başka dağıtım, genel ürün sürümü veya port ipucu RPM kanıtına çevrilmez.
- Ekleme, güncelleme, yeniden etkinleştirme ve iptal ana kayıt ile olay kaydını aynı transaction'da tutar.
- Liste/ayrıntı ağsız ve yazmasızdır; bozuk PURL, kimlik, zaman veya olayda kısmi sonuç verilmez.
- Paket varlığı zafiyet, düzeltme veya etkilenmeme kararı değildir.

## Geçiş ve kurtarma

Şema 22→23 geçişi önce üzerine yazmayan doğrulanmış yedek alır, iki yeni tabloyu boş oluşturur ve bütün eski kayıtları korur. DDL hatası ana veritabanını şema 22'de bırakır. Güncel yedek/restore paket ana kaydını ve geçmişini birlikte taşır.

## Sonraki adım

CSAF ürün ağacındaki PURL, CPE ve ilişki bağları katı biçimde ayrıştırılacak; yerel paket yalnız aynı dağıtım bağlamındaki ürünle salt okunur eşleştirilecektir. Bu eşleşme de insan maruziyet kararını kendiliğinden değiştirmeyecektir.
