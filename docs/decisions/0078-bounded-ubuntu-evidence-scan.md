# ADR 0078 — Ağsız plan ve sınırlı toplu Ubuntu kanıt denetimi

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

0.77 tek bir seçilmiş Ubuntu kanıtını güncel paket ve Canonical kaydıyla denetliyordu. Kanıt sayısı arttığında kimlikleri tek tek kopyalamak yerel paket değişikliklerini topluca görememeye ve aynı CVE dosyasını tekrar tekrar indirmeye yol açar. Doğrudan sınırsız toplu ağ işlemi ise ücretsiz kaynak ve kişisel bilgisayar için kontrolsüz yük oluşturur.

## Karar

`vuln ubuntu-evidence-plan [--domain ALAN_ADI] [--limit 1..500]`, etkin ve ayrılmış `ubuntu-osv-v1` kanıtlarını tek salt-okunur SQLite anında alır. Depo en fazla 10.000 ana kayıt ve bunlara bağlı 100.000 olayı görünüm sınırından bağımsız doğrular. Kayıtlı olmayan varlık hata verir; bozuk başvuru, yanlış CVE/varlık bağı, eksik paket veya eksik geçmiş bütün planı durdurur.

Plan her kanıtta kayıtlı tam paket özeti ile güncel paket özetini karşılaştırır; `package_inactive`, `package_snapshot_changed` ve `local_current` durumlarını sayar. Sıra dikkat durumlarını öne alır. Plan Canonical kaynağını çağırmaz ve yerel güncelliği kaynak güncelliliği gibi sunmaz.

`vuln ubuntu-evidence-scan [--domain ALAN_ADI] [--limit 1..20]`, aynı planın ilk sınırlı grubunu tekil güncellik servisiyle kontrol eder. Komut ömründeki küçük kaynak adaptörü başarılı Canonical anlık görüntülerini CVE kimliğiyle önbelleğe alır. Böylece seçili birden çok kanıt aynı CVE'ye bağlıysa tek HTTPS çağrısı yapılır. Boş planda kaynak çağrısı yoktur; ilk kaynak hatası komutu güvenli biçimde durdurur.

## Sonuçlar

- Toplam, seçilen, kalan, gerçek kaynak çağrısı, güncel/değişmiş ve kaynak atlanan sayıları ayrı görünür.
- `--limit` yalnız ağla kontrol edilecek ve gösterilecek grubu sınırlar; planın bütün yerel kayıt doğrulaması ve toplamları korunur.
- Toplu tarama yeni kanıt veya olay yazmaz, eski kaydı yenilemez ve insan kararını değiştirmez.
- Değişen sonuç ancak ayrı açık `ubuntu-evidence-add` komutuyla kalıcı kanıta dönüşür.
- Bellek içi önbellek süreçler arası kaynak aynası veya zamanlayıcı değildir.
- Yeni tablo veya migration yoktur; şema 32 korunur.

Resmî kaynak: [Ubuntu OSV verisi](https://documentation.ubuntu.com/security/security-updates/osv/).
