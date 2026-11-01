# ADR 0072 — Canonical Ubuntu OSV tek-kayıt önizlemesi

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

Kaynak kapısı Canonical Ubuntu OSV'yi seçti. Genel OSV toplayıcı kaydı üreticinin Ubuntu yayın/paket hükmüyle aynı şey değildir. İlk entegrasyonun yerel paket eşleştirmesine veya kalıcı maruziyet kararına geçmeden önce taşıma, kimlik ve kapsam sınırlarını kanıtlaması gerekir.

## Karar

`vuln ubuntu-preview CVE-YIL-SAYI`, Canonical'ın resmî GitHub deposundaki şu sabit kalıptan yalnız bir dosya alır:

`https://raw.githubusercontent.com/canonical/ubuntu-security-notices/main/osv/cve/{yıl}/UBUNTU-{CVE}.json`

Yıl ve dosya kimliği doğrulanmış CVE'den türetilir. Kullanıcı URL veremez. TLS doğrulaması kullanılır, yönlendirme reddedilir, zaman aşımı 30 saniye, gövde sınırı 8 MiB ve içerik kodlaması `identity`dir. Raw GitHub JSON dosyaları için `application/json` ve `text/plain` kabul edilir; diğer türler reddedilir.

Ortak katı OSV ayrıştırması yinelenen alan, UTF-8, zaman, şema, URL, paket, sürüm, range/event ve liste sınırlarını doğrular. Ubuntu adaptörü ayrıca:

- kayıt kimliğinin tam `UBUNTU-{CVE}` olmasını;
- `upstream` içinde istenen CVE'nin bulunmasını;
- bütün etkilenen paket ekosistemlerinin `Ubuntu:` ile başlamasını zorunlu kılar.

Önizleme mevcut sınırlı OSV görünümünü kullanır; Ubuntu yayını/Pro bağlamı, kaynak paket, sürüm sayısı, fixed sınırı ve ADVISORY başvurularını gösterir. Yeni tablo yoktur, kayıt yazılmaz ve yerel paket/maruziyet hükmü üretilmez.

## Sonuçlar

- Genel toplayıcı verisi ile Canonical'ın Ubuntu üretici kaydı kaynak kimliği ve notlarıyla ayrılır.
- Sabit tek dosya yolu kişisel profilde tam feed indirmesini önler.
- `Ubuntu:Pro:*` ekosistemi görünür kalır; bu paket erişiminin aboneliksiz olduğu anlamına gelmez.
- Sonraki dilim ancak doğrulanmış yerel Ubuntu kaynak paket kimliği ve Debian sürüm karşılaştırma semantiği tasarlandıktan sonra eşleştirme yapabilir.
- 30 Ekim 2026 canlı kabulünde `CVE-2025-6491` kaydı 7 paket/yayın bağlamı ve 2 USN başvurusu verdi; ilk üç örnekte Ubuntu Pro 14.04/16.04/18.04 paketleri ve ilgili fixed sınırları görüldü.

Resmî kaynaklar: [Ubuntu OSV belgesi](https://documentation.ubuntu.com/security/security-updates/osv/), [Canonical veri deposu](https://github.com/canonical/ubuntu-security-notices).
