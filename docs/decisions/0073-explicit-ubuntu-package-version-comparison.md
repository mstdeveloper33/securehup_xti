# ADR 0073 — Açık Ubuntu paket sürümü karşılaştırması

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

Canonical Ubuntu OSV önizlemesi yayın, kaynak paket, etkilenen sürümler ve `fixed` sınırını gösteriyordu; fakat kullanıcının verdiği yerel sürümle karşılaştırmıyordu. Basit metin veya genel semantik sürüm karşılaştırması Debian paket sürümlerinde epoch, Debian revision, sayısal parçalar ve `~` nedeniyle yanlış sonuç üretir. Ayrıca Ubuntu OSV'de bir yayın+paketin hiç listelenmemesi hem “o yayında yok” hem de “etkilenmiyor” kaynak durumlarından gelebilir.

## Karar

`vuln ubuntu-match CVE --ecosystem ... --source-package ... --version ...` yalnız kullanıcının açıkça verdiği üç paket bağlamını Canonical'ın mevcut tek-CVE kaydıyla karşılaştırır. Girdiler ve `--reference-limit 1..200` ağdan önce doğrulanır. Komut yerel paket yöneticisini okumaz ve kalıcı kayıt kullanmaz.

Debian sürüm karşılaştırıcısı domain katmanındadır ve haricî `dpkg` çalıştırmaz. Debian Policy 5.6.12 sırasıyla:

1. epoch'u sayısal;
2. upstream sürümü;
3. Debian revision bölümünü karşılaştırır.

Son iki bölüm soldan sağa, dönüşümlü rakam dışı/rakam parçalarıyla değerlendirilir. Harfler diğer rakam dışı işaretlerden önce, `~` her şeyden ve parça sonundan önce sıralanır; sayısal parçalardaki baştaki sıfırlar sonucu değiştirmez.

Kaynak kaydı için tam `UBUNTU-{CVE}`, upstream CVE, kanonik `Ubuntu:*` ekosistemi ve kanonik Debian kaynak paket adı zorunludur. Seçilen yayın+paket bağı:

- hiç yoksa `not_listed`;
- birden fazlaysa kaynak tutarsızlığı hatası;
- tek ve `fixed` yoksa `listed_without_fixed_boundary`;
- tek bir `fixed` varsa `before_fixed_boundary`, `at_fixed_boundary` veya `after_fixed_boundary`;
- kayıt geri çekilmişse `record_withdrawn` olur.

Karşılaştırılabilir aralık tam bir `ECOSYSTEM` aralığı, yalnız `introduced: 0`, en fazla bir `fixed` ve hiç `last_affected` olmalıdır. Beklenmeyen aralık güvenli biçimde durdurulur.

## Sonuçlar

- Ubuntu backport sürümleri doğru Debian semantiğiyle karşılaştırılır.
- `not_listed` güvenli sayılmaz; Canonical durumlarının hangisi olduğu bu görünümde uydurulmaz.
- Fixed sınırı olmayan kayıtlar tek bir “etkilenmiş” hükmüne indirgenmez; üretici durum ayrıntısı için sonraki veri dilimi gerekir.
- Kullanıcı girdisi bağımsız doğrulanmadığı için sonuç yalnız inceleme adayıdır. Veritabanı yazılmaz, maruziyet açılmaz ve insan kararı değişmez.
- Sonraki kalıcı dilim, kullanıcı tarafından doğrulanmış Ubuntu paket envanterini varlığa bağlamalı; binary→source paket ilişkisini açık kanıtla kurmalıdır.
- 30 Ekim 2026 canlı kabulünde `CVE-2025-6491`, `Ubuntu:24.04:LTS/php8.3` ve `8.3.6-0ubuntu0.24.04.4`, Canonical'ın `8.3.6-0ubuntu0.24.04.5` sınırından önce sınıflandı; 9 etkilenen sürüm ve 2 USN gösterildi.

Resmî kaynaklar: [Ubuntu OSV verisi](https://documentation.ubuntu.com/security/security-updates/osv/), [Debian Policy sürüm alanı ve karşılaştırma algoritması](https://www.debian.org/doc/debian-policy/ch-controlfields#version), [dpkg karşılaştırma komutu](https://manpages.debian.org/testing/dpkg/dpkg.1.en.html#--compare-versions).
