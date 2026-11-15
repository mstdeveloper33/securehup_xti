# theHarvester kurulumu ve kesintiden kurtarma

**Uygulama:** 0.140.2 · **Şema:** 64.

Bu rehber isteğe bağlı Common Crawl/Wayback aracının kurulumunu kapsar.
Normal XTI kurulumu ve SQLite kayıt alanı ayrı kalır. Araç kimliği ortak
`component_pins.py` kaydındaki incelenmiş commit'tir; otomatik olarak
upstream'in son sürümüne geçilmez.

## Komutlar

```sh
./scripts/setup-harvester
./scripts/setup-harvester --check
./scripts/setup-harvester --recover
./scripts/setup-harvester --force
```

| Komut | Ne yapar? |
|---|---|
| Seçeneksiz kurulum | Sağlıklı mevcut kurulumu yerel olarak kontrol edip çıkar. Eksik veya doğrulamadan geçmeyen ortam için yeni kurulum dener. |
| `--check` | Git kaynağı/commit'i, izlenen dosyalardaki değişiklikleri, çalıştırıcıyı ve `--help` çalışmasını kontrol eder; indirme veya yeniden kurulum yapmaz. |
| `--recover` | Yarım kalmış kurulumun günlüğüne göre önceki ortamı geri getirir. Yeni ortamın doğrulandığı zaten kaydedilmişse onu korur. Paket indirmez veya yeni kurulum başlatmaz. |
| `--force` | Sağlıklı kurulum olsa da eski klasörü koruyarak aynı sabit sürümü yeniden kurar. |

İlk kurulum ve yeniden kurulum için `git`, ücretsiz `uv` ve internet gerekir.
Önce PATH'teki `uv`, yoksa `.tools/uv/bin/uv` kullanılır; `uv` kendiliğinden
indirilmez. Sağlıklı kurulumun tekrarı ve `--check` için `uv` gerekmez.
`--recover` için Git veya `uv` gerekmez. Kontrol komutu bütün bağımlılıkların
bütünlüğünü veya canlı arşivlerin erişilebilirliğini kanıtlamaz.

Python 3.14 ortamı `.tools/theharvester/.venv` içinde oluşturulur. Önbellek
ve yönetilen Python varsayılan olarak `.tools` altındadır; açık `UV_CACHE_DIR`,
`UV_PYTHON_INSTALL_DIR` ve `UV_PYTHON_BIN_DIR` seçimleri korunur.

## Kurulum kesilirse

Yeni ortam doğrulanmadan eski ortam atılmaz. Kurulum eski klasörü benzersiz
bir yedeğe ayırır ve yeni ortamı kullanılacağı son konumunda oluşturur.
Normal hata veya yakalanabilen kesintide önceki klasör geri getirilir.
Alt süreçlerin durduğu doğrulanamazsa otomatik geri dönüş yapılmaz;
günlük ve yedek korunur, süreç bittikten sonra `--recover` kullanılır.
Ani süreç sonlandırma sonrası şu komut kurtarma işlemini tamamlar:

```sh
./scripts/setup-harvester --recover
./scripts/setup-harvester --check
```

Önceden kurulu araç yoksa kurtarma sonunda da kurulu araç bulunmaz;
ardından seçeneksiz kurulum yeniden denenir. Kurtarma, önceki ortamın
başlangıçta sağlıklı olduğunu varsaymaz; bu yüzden ayrıca `--check` yapılır.

Kurulum ve arşiv sorguları aynı kalıcı dosya kilidini kullanır. Sorgu
çalışırken kurulum; kurulum sürerken sorgu başlamaz. Üst süreç aniden
öldürülse bile çalışan alt süreç kilidi tutar. Böyle bir durumda alt süreç
bitmeden kurtarma başlamaz. Kilit dosyasını silerek zorlamayın.

Kurtarma gerektiren günlük veya meşgul kurulum, `components` ve kaynak
hazırlık görünümünde `invalid` açıklamasıyla gösterilir. Bu görünümler
araç çalıştırmaz, indirme yapmaz veya kilit dosyası oluşturmaz.

## Korunan dosyalar ve sınırlar

- Önceki ortamlar `.tools/.theharvester-backup-…`, başarısız adaylar
  `.tools/.theharvester-failed-…` altında tutulur. Kendiliğinden silinmezler;
  tekrar kurulumlar disk kullanır. Bu klasörler ve işlem günlüğü Git'e eklenmez.
- Taşınmış sanal ortam doğrudan çalıştırılacak ikinci kurulum değildir;
  çalıştırıcılar özgün klasör yoluna bağlı olabilir. Kurtarma eski ortamı
  özgün konumuna döndürür.
- Yabancı Git kaynağı, izlenen dosyalarda yerel değişiklik, sembolik bağlantı,
  bozuk günlük veya beklenmeyen klasör kimliği varsa işlem durur. Bilinmeyen
  dosyaların üzerine yazılmaz; elle inceleme gerekir.
- Günlük, klasör kimlikleri ve kilit yerel POSIX dosya sistemi içindir.
  Ağ dosya sistemi, Windows, donanım arızası veya tüm disk kaybı için kabul
  yapılmış değildir. Araç klasörü yedeği motor veritabanı yedeğinin yerine geçmez.

[Bileşen görünümü](COMPONENTS.md),
[mimari karar](decisions/0146-recoverable-harvester-installation.md) ve
[güncel kabul durumu](STATUS.md) ayrı doğrulama kapsamlarını açıklar.
