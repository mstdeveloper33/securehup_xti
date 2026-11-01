# ADR 0074 — Doğrulanmış Ubuntu binary→source paket envanteri

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

Canonical Ubuntu OSV kayıtları binary paketleri değil kaynak paket ve yayın bağlamını kullanır. Kullanıcının makinede gördüğü `php8.3-cli` gibi binary paket adı ile OSV'deki `php8.3` kaynak paketini yalnız ada bakarak eşitlemek yanlış sonuç üretebilir. Ayrıca binary paket sürümü ile kaynak sürümü her zaman aynı biçimde görünmek zorunda değildir. Kalıcı eşleştirme için bu ilişkinin kullanıcı tarafından kanıtlanması, değişiklik ve kaldırma geçmişinin korunması gerekir.

## Karar

`ubuntu-packages add` yalnız önceden kayıtlı bir varlığa şu alanları birlikte bağlar:

- tam Canonical OSV ekosistemi;
- binary paket adı, tam Debian sürümü ve mimari;
- kaynak paket adı ve tam Debian sürümü;
- ilişkinin nasıl doğrulandığını açıklayan kullanıcı kanıtı.

Alanlar domain katmanında kanonik biçimde doğrulanır. Binary→source ilişkisi otomatik ad benzerliğinden, porttan, banner'dan veya genel ürün kaydından türetilmez. Aynı tam kimlik ikinci kayıt oluşturmaz; kanıt değişikliği, kaldırma ve yeniden etkinleştirme güncel kayıt ile eklemeli olay geçmişinde atomik tutulur. Silme komutu yoktur.

`vuln ubuntu-inventory-match PAKET_KIMLIGI CVE`, etkin kaydı salt okunur alır ve yalnız `ecosystem + source_name + source_version` alanlarını ADR 0073'teki Canonical karşılaştırmasına verir. Binary sürüm sonuçta kanıt olarak gösterilir fakat OSV fixed sınırıyla karşılaştırılmaz. Kaldırılmış kayıt ağdan önce reddedilir.

Şema 32 `ubuntu_asset_packages` ve `ubuntu_asset_package_events` tablolarını ekler. Şema 1–31 geçişinde önce doğrulanmış yedek yayımlanır, tablolar tek transaction içinde boş oluşturulur ve hata halinde sürüm/DDL geri alınır. Eski varlıklardan veya ürünlerden Ubuntu paketi uydurulmaz. Güncel yedek/restore iki tabloyu birlikte taşır.

## Sonuçlar

- Canonical'ın kaynak paket sınırı, kullanıcının açıkça doğruladığı source sürümüyle karşılaştırılır.
- Binary ve source kimlikleri ayrı kaldığı için aynı görünen fakat farklı paket bağlamları sessizce birleşmez.
- Liste, ayrıntı ve eşleştirme bozuk kayıt veya gizli olay geçmişinde güvenli biçimde durur.
- Envanter kanıtı ve Canonical sonucu otomatik maruziyet, etkilenmiyor, güvenli veya düzeltildi kararı değildir; insan inceleme yaşam döngüsü ayrı kalır.
- Bu dilim paketi makineden otomatik toplamaz, SSH yapmaz, zamanlanmış yenileme veya Ubuntu Pro yetkisi üretmez.

Resmî kaynaklar: [Ubuntu OSV verisi](https://documentation.ubuntu.com/security/security-updates/osv/), [Debian Policy sürüm alanı](https://www.debian.org/doc/debian-policy/ch-controlfields#version).
