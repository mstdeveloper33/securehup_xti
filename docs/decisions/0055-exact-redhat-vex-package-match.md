# 0055 — Kesin Red Hat RPM ile VEX ilişki eşleştirmesi

**Durum:** Kabul edildi · **Tarih:** 29 Ekim 2026 · **Sürüm:** 0.55.0

## Karar

Etkin yerel Red Hat RPM kanıtı, açıkça seçilen CVE'nin doğrudan Red Hat CSAF VEX belgesiyle salt okunur karşılaştırılır. Ayrıştırıcı ürün kimliğinin adı yanında PURL/CPE yardımcılarını ve tam ürünün `default_component_of` ilişkisini korur.

Tam ikili paket eşleşmesi aynı anda şunları gerektirir:

- yerel ad+epoch+sürüm+release+mimari ile VEX bileşen kimliğinin aynı NEVRA olması;
- yerel türetilmiş PURL ile VEX bileşen PURL'sinin aynı olması;
- yerel dağıtım CPE'si ile ilişkinin ürün CPE'sinin aynı olması.

Kaynak paket bağlamı yalnız yerel kaynak RPM biliniyorsa; kaynak paket adı, `arch=src` PURL ve dağıtım CPE birlikte aynıysa gösterilir.

## Sonuç sınırı

Eşleşen durum Red Hat'in kaynak beyanıdır. Servis insan maruziyet kararını, destek kanıtını, öncelik bandını veya yeniden inceleme durumunu yazmaz. Farklı bağlam eşleşmez; eşleşme yokluğu güvenlik hükmü değildir. Birden çok kesin bağ farklı durumlara çıkarsa tek sonuç seçilmez ve çelişki görünür tutulur.

Kaldırılmış paket ve geçersiz sınır ağ isteğinden önce reddedilir. Paket okuması kapanmadan VEX alınmaz; ağ beklerken SQLite transaction'ı tutulmaz. Komutun şema değişikliği yoktur; şema 23 korunur.

## Doğrulama

Sentetik testler tam ikili/source-package eşleşmesini, farklı dağıtım/epoch/release/mimariyi, kaynak RPM yokluğunu, kaldırılmış kaydı, katı yardımcı/ilişki ayrıştırmasını ve yazmasız CLI'yi kapsar. Canlı resmî Heartbleed VEX belgesinde RHEL 6 Client OpenSSL paketi tek `fixed` bağına eşleşmiştir.
