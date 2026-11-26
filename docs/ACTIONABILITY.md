# İnsan onaylı aksiyon, vaka paketi ve toplu IOC işlemleri

XTI 0.186.0 kanıtı dışarıya kendiliğinden göndermeden savunma işini
hazırlar ve izlenebilir kılar; 0.195.0 bu yaşam döngüsüne kanıta bağlı,
insan incelemeli abuse iletişim keşfini ekler. Güncel kapsam beş parçadır:

1. Vakanın o andaki tam görünümünden bütünlüğü doğrulanabilir kanıt paketi.
2. Kanıt türlerine göre sürümlü runbook planı ve atomik vaka görevleri.
3. İnsan onayı olmadan ilerlemeyen takedown kayıt ve sonuç yaşam döngüsü.
4. CSV, JSON ve güvenli STIX 2.1 alt kümesiyle toplu IOC önizleme,
   içe alma ve dışa aktarma.
5. Domain/IP RDAP, yardımcı `security.txt` ve isteğe bağlı WHOIS ile abuse
   iletişim adayını bulma, inceleme ve güncel adayı taslağa bağlama.

Haricî SIEM, SOAR, Jira/ServiceNow veya otomatik sağlayıcı başvurusu bu
pakete dahil değildir. Yalnız açık `action contact-refresh` iletişim
kaynaklarına pasif ağ çağrısı yapar; takedown işlemlerinin hiçbiri ağ çağrısı
yapmaz. Gerçek başvuru yetkili insan tarafından sağlayıcı portalında yapılır
ve yalnız dış başvuru referansı XTI'ya kaydedilir.

## Kurulum ve veri geçişi

Yeni kurulumda:

```sh
./setup
./xti init
```

Eski veri alanında önce kurtarma yedeği üreten açık geçiş gerekir:

```sh
./xti migrate
```

Güncel geçiş şema 101'e ulaşır. Eski vaka, IOC, kaynak ve P06 kayıtları
korunur; abuse iletişim tabloları yalnız yeni kayıtlar için eklenir.

## Runbook

Önce yazmasız plan alınır:

```sh
./xti action runbook-plan VAKA_KIMLIGI
```

Çıktıdaki `plan_sha256` görülüp onaylandıktan sonra aynı özetle görevler
tek transaction içinde oluşturulur:

```sh
./xti action runbook-apply VAKA_KIMLIGI \
  --expected-plan-sha256 PLAN_SHA256 \
  --idempotency-key vaka-123-runbook-1 \
  --reason "Savunma görevleri analist incelemesine açıldı."
```

- Vaka veya etkin kanıt plan sonrasında değişirse eski plan reddedilir.
- Aynı tekrar anahtarı aynı istekle yeniden verilirse yeni görev oluşmaz.
- Temel adımlara kanıt türüne uygun domain, marka, sosyal profil, kod
  maruziyeti, dark web/credential, ransomware veya CTI adımları eklenir.
- Runbook öneridir; otomatik engelleme, bildirim veya takedown yapmaz.

Uygulama makbuzu:

```sh
./xti action runbook-show RUNBOOK_KIMLIGI
```

## Kanıt ve rapor paketi

```sh
./xti action package-create VAKA_KIMLIGI ./case-package
./xti action package-verify ./case-package
```

Yeni ve boş bir hedef dizin zorunludur; mevcut dizinin üzerine yazılmaz.
Paket şunları içerir:

- `technical.json`: vaka, kanıt, görev ve zaman çizelgesinin tam donmuş görünümü
- `executive.html`: kısa yönetici özeti
- `evidence.csv`: teknik kanıt listesi; elektronik tablo formül enjeksiyonuna karşı kodlanır
- `manifest.json`: her dosyanın boyutu, türü ve SHA-256 özeti

İsteğe bağlı PDF:

```sh
./xti action package-create VAKA_KIMLIGI ./case-package --pdf
```

PDF mevcut sabit Playwright 1.65.2 / Chromium 1255 kurulumu ile ayrı,
JavaScript kapalı ve ağsız süreçte üretilir. `package-verify`, manifest veya
dosya değişmişse, beklenmeyen dosya/symlink varsa güvenli biçimde durur.
Manifest SHA-256 değeri paketten ayrı bir güvenilir kayıtta tutulursa daha
sonraki doğrulamada karşılaştırılabilir. Paket imzalı belge değildir.

Sınırlar: en fazla 50.000 kanıt, 50.000 görev, 100.000 zaman çizelgesi
kaydı; teknik JSON 32 MiB. Sınır aşımında kısmi paket üretilmez.

## İnsan onaylı takedown

Taslak yalnız etkin ve uygun vaka kanıtından oluşturulur:

```sh
./xti action takedown-create VAKA_KIMLIGI KANIT_BAGI_KIMLIGI \
  --target-kind registrar \
  --target example-login.test \
  --recipient abuse@example-registrar.test \
  --requested-action "Kötüye kullanım incelemesine alınsın." \
  --grounds "Marka yetkisi ve vaka kanıtı insan tarafından doğrulandı." \
  --actor analyst@example.test \
  --idempotency-key vaka-123-takedown-1
```

Yaşam döngüsü:

```text
draft -> approved -> submitted -> acknowledged -> resolved
                                  \-> rejected
draft/approved -> cancelled
```

Örnek:

```sh
./xti action takedown-approve TAKEDOWN_KIMLIGI \
  --expected-revision 0 --actor owner@example.test \
  --reason "Yetkili kişi kanıtı ve talebi onayladı."

# Başvuru dışarıda insan tarafından yapıldıktan sonra:
./xti action takedown-submit TAKEDOWN_KIMLIGI \
  --expected-revision 1 --actor owner@example.test \
  --reason "Sağlayıcı portalındaki insan başvurusu kaydedildi." \
  --external-reference registrar-ticket:12345
```

Her geçiş beklenen sürümü, aktörü, gerekçeyi ve değişmez olay anlık
görüntüsünü taşır; her olayın özeti önceki olay özetine bağlanır. Aynı
tekrar anahtarı başarılı taslağı vaka sonradan değişse de yeni kayıt
üretmeden döndürür. Buna karşılık yeni onay sırasında vakanın açık, bağlı
kanıtın hâlâ etkin ve aynı özetle güncel olması yeniden doğrulanır. Onaysız
`submit`, referanssız gönderim kaydı ve geçersiz durum sırası reddedilir.
`list` ve `show` bozuk olay zincirini sessizce göstermez.

### Adresi otomatik bulup insan onayıyla bağlama

Vaka kanıtındaki domain veya genel IP için önce iletişim izlemesi oluşturulup
yenilenir. RDAP açık abuse rolü ana kanıttır; `security.txt` yardımcıdır ve
yerel WHOIS yalnız RDAP boşsa isteğe bağlı fallback'tir. Aday insan tarafından
onaylandıktan sonra manuel `--recipient` yerine şu bağ kullanılabilir:

```sh
./xti action takedown-create VAKA_KIMLIGI KANIT_BAGI_KIMLIGI \
  --contact-candidate-id ADAY_KIMLIGI \
  --requested-action "Kötüye kullanım incelemesine alınsın." \
  --grounds "Kaynaklı iletişim adayı ve vaka kanıtı insan tarafından doğrulandı." \
  --actor analyst@example.test \
  --idempotency-key vaka-123-contact-1
```

Aday başka vakaya/kanıta aitse, etkin değilse, onaysızsa veya kaynak kanıtı
değiştiği için kararı bayatsa taslak oluşmaz. Aynı bağ hem
`takedown-approve` hem de `takedown-submit` öncesinde yeniden doğrulanır.
Tam kullanım ve kaynak sınırları [abuse iletişim rehberindedir](ABUSE_CONTACTS.md).

## Toplu IOC

Desteklenen türler: domain, IPv4, IPv6, URL, MD5, SHA-1 ve SHA-256.
Dosya sınırı 32 MiB ve 50.000 kayıttır.

Önizleme hiçbir kayıt yazmaz:

```sh
./xti ioc bulk-preview indicators.json --format json
```

Çıktıdaki `content_sha256` ile atomik içe alma:

```sh
./xti ioc bulk-import indicators.json --format json \
  --expected-content-sha256 DOSYA_SHA256 \
  --idempotency-key import-2026-11-22-1 \
  --import-source analyst-file \
  --import-reference indicators.json
```

Bütün satırlar yazmadan önce doğrulanır. Tek geçersiz/çelişkili satır tüm
işlemi durdurur. Aynı IOC farklı kaynak iddialarını ezmez. Aynı tekrar
anahtarı aynı dosyayla yeniden oynatıldığında yeni kayıt üretmez.

```sh
./xti ioc bulk-export indicators.csv --format csv
./xti ioc bulk-export indicators.json --format json
./xti ioc bulk-export indicators.stix.json --format stix
```

Çıktı mevcut dosyanın üzerine yazılmaz ve 0600 izinle oluşturulur. STIX
içe alma, XTI'nın ürettiği doğrulanabilir indicator alt kümesiyle sınırlıdır;
genel STIX/TAXII sunucusu değildir.

## JSON motor sınırı

Salt okunur engine ve firma kapsamlı platform işlemleri:

- `action.capabilities`
- `action.runbook.plan`, `action.runbook.show`, `action.runbook.apply`
- `action.takedown.list`, `action.takedown.show`
- `action.takedown.create`, `action.takedown.transition`
- `action.contact.capabilities`, `action.contact.plan`
- `action.contact.watches`, `action.contact.watch.show/events`, `action.contact.due`
- `action.contact.runs`, `action.contact.run.show`
- `action.contact.candidates`, `action.contact.candidate.show/events`, `action.contact.reviews`
- `action.contact.watch.add/update/disable`, `action.contact.refresh/review/recover`

Firma yazmaları `expected_workspace_id` çiti ister. Dosya yolu alan
`package-create`, IOC import ve export işlemleri keyfî sunucu dosyası
erişimi oluşturmaması için platform JSON yüzeyine açılmamıştır; güvenilen
operatör CLI'sı veya ileride platformun kendi güvenli dosya katmanı kullanır.

## Kabul

Hedefli testler:

```sh
PYTHONPYCACHEPREFIX=/tmp/xti-pyc ./scripts/python \
  scripts/check-test-shard.py -v \
  tests/test_actionability.py tests/test_actionability_cli.py \
  tests/test_actionability_contract.py tests/test_actionability_migration.py \
  tests/test_ioc_bulk.py tests/test_abuse_contacts_domain.py \
  tests/test_abuse_contact_sources.py tests/test_abuse_contacts.py \
  tests/test_abuse_contact_contract.py tests/test_abuse_contact_migration.py \
  tests/test_abuse_contact_capacity.py
```

Birikimli, ağsız kabul:

```sh
PYTHONPYCACHEPREFIX=/tmp/xti-pyc ./scripts/python \
  scripts/check-actionability-delivery.py
```

Ayrıntılı sonuç ve açık ortam doğrulamaları [P06 teslim kartında](roadmap/P06_DELIVERY.md)
ve [abuse iletişim ek teslim kartında](roadmap/P06_ABUSE_CONTACT_DELIVERY.md)
tutulur.
