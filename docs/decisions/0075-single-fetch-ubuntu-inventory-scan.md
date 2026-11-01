# ADR 0075 — Tek kaynak çağrılı Ubuntu envanter taraması

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

0.74 bir Ubuntu paketini seçilen CVE ile güvenli biçimde karşılaştırabiliyordu. Çok paketli envanterde aynı CVE için komutu tek tek çalıştırmak aynı Canonical dosyasını tekrar indirmek, durum toplamlarını görememek ve görünüm limitinin arkasındaki bozuk kanıtı kaçırmak anlamına gelirdi.

## Karar

`vuln ubuntu-inventory-scan CVE [--domain ALAN_ADI]`, seçilen kapsamdaki bütün etkin Ubuntu paketlerini tek çalışma içinde karşılaştırır. CVE, varlık, 1–500 görünüm ve 1–200 duyuru sınırları ağdan önce doğrulanır. Kayıtlı olmayan varlık boş sonuç sayılmaz.

Depo en fazla 10.000 etkin ana kayıt ile bunlara bağlı en fazla 100.000 yaşam döngüsü olayını tek salt-okunur SQLite anında alır. Bütün ana kayıtlar ve olaylar görünüm sınırından bağımsız doğrulanır; eksik veya bozuk geçmiş kısmi tarama üretmez. Etkin kayıt yoksa Canonical kaynağı çağrılmaz.

Dolu kapsamda tek `UBUNTU-CVE` anlık görüntüsü alınır. Her paket yalnız doğrulanmış `ecosystem + source_name + source_version` alanlarıyla ortak Debian karşılaştırıcısına verilir. Durum sayaçları bütün kapsamdan hesaplanır. Gösterim sırası `before_fixed_boundary`, `listed_without_fixed_boundary`, `at_fixed_boundary`, `after_fixed_boundary`, `not_listed`, `record_withdrawn` önceliğini ve ardından kararlı paket kimliğini kullanır. `--limit` yalnız terminal/JSON satırlarını keser.

## Sonuçlar

- Aynı CVE için paket sayısından bağımsız olarak yalnız bir Canonical dosyası alınır.
- Dikkat gerektiren önce/fixed-yok kayıtları görünümde öne çıkar; bütün durumlar ve toplamlar kaybolmaz.
- `not_listed`, `after_fixed_boundary` veya diğer sonuçlar otomatik insan kararı değildir.
- Tarama veritabanı yazmaz, paket kanıtını güncellemez, maruziyet açmaz ve zamanlayıcı başlatmaz.
- Şema 32 değişmez; sonraki açık dilim seçilmiş güncel Ubuntu sonucunu mevcut insan maruziyetine yapılandırılmış kanıt olarak bağlamaktır.

Resmî kaynaklar: [Ubuntu OSV verisi](https://documentation.ubuntu.com/security/security-updates/osv/), [Debian Policy sürüm alanı](https://www.debian.org/doc/debian-policy/ch-controlfields#version).
