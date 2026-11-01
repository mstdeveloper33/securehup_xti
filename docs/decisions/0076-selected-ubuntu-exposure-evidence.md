# ADR 0076 — İnsan seçimiyle Ubuntu maruziyet destek kanıtı

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

0.75, doğrulanmış Ubuntu paket envanterinin tamamını Canonical'ın tek-CVE OSV kaydıyla karşılaştırabiliyor fakat sonucu bilerek yazmıyordu. Analistin belirli bir sonucu mevcut insan maruziyet incelemesine bağlayabilmesi için kaynağın ve kullanılan yerel paket kaydının sonradan ayırt edilebilir olması gerekir. Salt serbest metin başvurusu, ağ isteği sırasında değişen paket kaydını veya yeni Canonical içeriğini eski seçimden ayıramaz.

## Karar

`vuln ubuntu-evidence-add INCELEME_KIMLIGI UBUNTU_PAKET_KIMLIGI --summary ACIKLAMA`, yalnız açık kullanıcı işlemiyle çalışır. İnceleme, paket, açıklama ve aynı varlık bağı kaynak çağrısından önce doğrulanır. CVE serbest kullanıcı girdisinden değil, mevcut insan maruziyet kaydından alınır.

Servis Canonical'ın güncel tek-CVE kaydını yeniden alır ve paketin doğrulanmış `ecosystem + source_name + source_version` alanlarıyla karşılaştırır. Yalnız tek bir `affected` bağına dayanan `listed_without_fixed_boundary`, `before_fixed_boundary`, `at_fixed_boundary` veya `after_fixed_boundary` sonucu seçilebilir. `not_listed` ve `record_withdrawn` kalıcı destek kanıtı değildir.

Tam Ubuntu paket kaydı kanonik JSON olarak SHA-256 ile özetlenir. Genel `package_inventory` kanıtının kaynak başvurusu sürümlü `ubuntu-osv-v1` önekiyle CVE, paket UUID'si, paket anlık görüntüsü özeti, Canonical içerik özeti ve karşılaştırma durumunu taşır. Aynı başvuru ve açıklama tekrarında olay çoğalmaz; paket veya Canonical içeriği değişirse yeni başvuru ve ayrı kanıt oluşur.

SQLite adaptörü yazma transaction'ında maruziyetin CVE/varlık bağını, paketin etkinliğini ve paket özetini tekrar doğrular. Ağ isteği sırasında paket değişmiş veya kaldırılmışsa yazımın tamamı geri alınır. Mevcut `vulnerability_exposure_evidence` ve olay tabloları kullanılır; yeni tablo veya migration eklenmez.

## Sonuçlar

- Seçim mevcut genel kanıt liste/ayrıntı/kaldırma, maruziyet kuyruğu, yedek ve restore davranışını kullanır.
- İnsan `investigating/affected/not_affected/fixed` kararı, gerekçesi, önceliği ve karar geçmişi değişmez.
- `after_fixed_boundary` dâhil seçilebilir durumlar yalnız kaynaklı destek içeriğidir; otomatik “düzeltildi” veya “etkilenmiyor” hükmü değildir.
- Paket yeniden doğrulanırsa aynı sürüm alanları korunsa bile tam anlık görüntü özeti değişir ve yeni seçim ayrı kanıt olur.
- Kanıt, Canonical adresinin içeriğini yerelde kopyalamaz; alınan içeriğin SHA-256 özetini ve yapılandırılmış karşılaştırma bağlamını saklar.
- Sonraki dar dilim, saklanan Ubuntu kanıtının güncel paket ve Canonical kaydı karşısında salt-okunur güncellik kontrolüdür.

Resmî kaynaklar: [Ubuntu OSV verisi](https://documentation.ubuntu.com/security/security-updates/osv/), [Debian Policy sürüm alanı](https://www.debian.org/doc/debian-policy/ch-controlfields#version).
