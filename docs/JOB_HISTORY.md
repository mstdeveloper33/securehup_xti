# Ortak iş kuyruğunda kayıpsız geçmiş

0.179.0 · kuyruk şeması4; çekirdek88 ve kaynak işi7 korunur.

10.000 iş sınırı artık yalnız bekleyen ve çalışan profil/kaynak işlerine
uygulanır. Tamamlanan, kısmi, başarısız, iptal edilen veya kesilen iş aynı
işlemde arşiv durumuna alınır ve etkin kapasiteyi boşaltır. Sonucu,
özgün olayları, tekrar anahtarı ve retry bağı aynı veritabanında korunur.
Bu mantıksal ayırmadır; diskten silme veya sıkıştırma değildir.

```sh
./xti source-jobs capacity
./xti source-jobs history --limit 20
./xti source-jobs history --bucket active --limit 20
./xti source-jobs audit
```

`history` profil ve kaynak işlerini birlikte gösterir. Sonraki sayfada
`next_before_sequence` → `--before-sequence`, `snapshot_id` →
`--expected-snapshot` verilir. Arada bir iş değişirse ilk sayfadan başlama
istenir; sayfalar sessizce farklı kesitleri birleştirmez. Sayfa en fazla
100 kayıttır. Önceki `source-jobs list/status/result` ve platform
`jobs.status/result` okumaları arşivdeki kimlikle çalışır.

Firma JSON işlemleri: `jobs.capacity`, `jobs.history`, `jobs.audit`.
`jobs.history` seçenekleri `bucket=archive|active|all`, `limit`,
`before_sequence`, `expected_snapshot` alanlarıdır. Firma JSON üzerinden
seçilmez; güvenilen başlatıcının mevcut firma kapsamı kullanılır.

Arşivlenmiş işin aynı anahtarla gönderimi özgün işi döndürür; kaynak
tekrar çağrılmaz. Başarısız/kesilmiş kaynak işinin açık `retry` akışı
korunur. Belirsiz dış sonuç için `allow_uncertain` gerekir. Arşivlenme
işin başarılı olduğu veya dış isteğin güvenle tekrarlanabileceği anlamına
gelmez. Yeni kontrol yeni anahtarla kabul edilir.

## Bütünlük ve bakım

Güncel işlemler seçilen özgün iş/olay zincirini, sonucu ve indeks bağını
doğrular. Olağan işlem dışında SQL değişikliği olursa koruma kaydı kirlenir
ve normal kullanımı durdurur. `audit` bütün iş/olay/retry zincirlerini,
SQLite bütünlüğünü ve indeksi tek okuma kesitinde denetler; büyük geçmişte
sürer ve bakım zamanında çalıştırılmalıdır. Bozuk özgün kaydı düzeltmez;
doğrulanmış yedekten geri dönüş gerekir. Hash/tetikleyici koruması dosyaya
tam erişimli yöneticiye karşı kriptografik imza değildir.

`capacity` saklı işleri SQL indekslerinden sayar; toplam hacimden etkilenir.
Durum, anahtar tekrarı, worker seçimi ve geçmiş sayfası bütün eski
işleri yeniden doğrulamaz. Normal platform okumaları da tam kuyruk
denetimini başlatmaz. Kuyruk1–3 için eski sınırlı denetim korunur.

Her tamamlanan işin özgün gövdesi disk kullanmaya devam eder. Otomatik
silme yoktur; disk ve yedek kapasitesi işletimde izlenmelidir. Aynı anda
10.000 etkin iş sınırı ve tek ortak worker korunur. Nmap'in ayrı iş
deposu ve eski `jobs` tarama kuyruğu bu ortak kuyruk kapsamına girmez.

## Geçiş ve geri dönüş

Mevcut kişisel kuyruk için:

```sh
git pull --ff-only
./xti source-jobs migrate
./xti source-jobs audit
```

Firma kuyruğu için güvenilen işletim terminalinde:

```sh
./xti platform jobs-migrate --root PLATFORM_KOKU --company FIRMA
```

Geçiş çalışan/kurtarma bekleyen iş varken durur. Önce kuyruk yedeği alınır;
3→4 özgün iş/olay satırlarını ve rowid'leri değiştirmeden indeks ve koruma
tetikleyicileri ekler. Yeni kurulumlar doğrudan4 oluşturur. Eski motor4'ü
açmaz; geri dönüşte yükseltme öncesi firma yedeği eski kodla yeni/boş alana
açılır. Çekirdek ve kuyruk birlikte `platform backup/restore` ile korunur;
tek kuyruk migration yedeği tam firma yedeği değildir. Yedekten dönüş
eski sırada işleri yeniden göndermek yerine iptal eder ve yeni workspace
kimliği üretir; tamamlanmış geçmiş/sonuçlar korunur.

[Teslim ve ölçümler](roadmap/JOB_HISTORY_CONFLICT_DELIVERY.md).
