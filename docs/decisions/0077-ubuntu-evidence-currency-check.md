# ADR 0077 — Ubuntu destek kanıtı güncellik kontrolü

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

0.76 seçilen Ubuntu sonucu için yerel paket anlık görüntüsü ve Canonical belge özetini sakladı. Paket kanıtı yeniden doğrulanabilir, Canonical kaydı değişebilir, fixed sınırı farklılaşabilir, yayın+paket bağı kaldırılabilir veya kayıt geri çekilebilir. Eski kanıtı sessizce güncellemek denetim izini bozar; yalnız özetlerin farklı olduğunu söylemek de değişikliğin anlamını açıklamaz.

Yapılandırılmış `ubuntu-osv-v1` biçimi genel `package_inventory` serbest metin alanında bulunur. Genel ekleme komutunun aynı öneki taklit edebilmesi, doğrulamalı özel seçim ile serbest kullanıcı başvurusu arasındaki sınırı belirsizleştirir.

## Karar

`vuln ubuntu-evidence-check KANIT_KIMLIGI`, kanıtı ve bütün olay geçmişini okur; türün `package_inventory` ve başvurunun tam kanonik `ubuntu-osv-v1` biçiminde olmasını zorunlu kılar. CVE, paket UUID'si, paket SHA-256, Canonical SHA-256 ve kayıtlı karşılaştırma durumu ayrıştırılır. Maruziyet CVE'si ile paket-varlık bağı yeniden doğrulanır.

Etkisiz kanıt veya paket için dış kaynak çağrılmaz. Etkin kayıtta paket okunur, Canonical tek-CVE kaydıyla yeniden karşılaştırılır ve kaynak dönüşünden sonra paket tekrar okunur. Kontrol sırasındaki paket değişimi kesin güncel hüküm yerine ayrı `package_changed_during_check` durumudur.

Diğer durumlar `current`, `source_document_changed_same_result`, `package_snapshot_changed_same_result`, `result_changed`, `selected_relation_missing`, `record_withdrawn`, `package_inactive` ve `evidence_inactive` olarak ayrılır. Alanlar ayrıca kaynak/paket değişimini, güncel sonucu, fixed sınırını ve seçilen bağın varlığını taşır.

Genel `VulnerabilityExposureEvidenceService.add`, `package_inventory` için ayrılmış `ubuntu-osv-v1:` önekini reddeder. Özel seçim servisi doğrudan atomik depo portunu kullandığı için doğrulanmış kayıt üretmeye devam eder; mevcut kayıtların okunması etkilenmez.

## Sonuçlar

- Kontrol veritabanı yazmaz, kanıtı yenilemez, yeni olay oluşturmaz ve insan kararını değiştirmez.
- Değişmiş güncel durum ancak kullanıcının yeniden `ubuntu-evidence-add` seçimiyle ayrı kanıta dönüşür.
- Belge değişip aynı sürüm sonucu korunuyorsa kaynak değişimi ile hüküm değişimi birbirine karıştırılmaz.
- `not_listed` güvenli sayılmaz; yalnız seçilen bağın güncel belgede bulunmadığı raporlanır.
- Kaynak dönüşünden sonraki paket okuması kontrol içi değişimi yakalar; sürekli eşzamanlı yazım altında atomik çoklu-sistem anlık görüntüsü iddiası yoktur.
- Yeni tablo veya migration yoktur; şema 32 korunur.

Resmî kaynak: [Ubuntu OSV verisi](https://documentation.ubuntu.com/security/security-updates/osv/).
