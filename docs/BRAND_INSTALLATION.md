# Maigret ve Sherlock kurulumu, güncelleme ve kurtarma

**Uygulama:** 0.140.4 · **Şema:** 64.

Normal kullanım aynı kalır:

```sh
./setup
./xti --help
```

İlk kurulum için Git, Python 3.11+ ve internet gerekir. Paketler proje
içindeki `.venv` ortamına kurulur. Sağlıklı mevcut ortamın tekrar kontrolü
paket indirmez; araçlar incelenmiş sürüm ve commit'lerinde kalır.

Bağımlılıklar `constraints/brand.txt` içinde sabittir. Python 3.11 için
NumPy 2.4.6, Python 3.12 ve üstünde 2.5.4 seçilir; kurulum denetimi de
aynı koşulu kontrol eder. 2.5.4'ün Python alt sınırı 3.12 olduğundan tek
sürümü bütün ortamlara zorlamak 3.11 kurulumunu engelliyordu.
[2.4.6 resmî metadata](https://pypi.org/pypi/numpy/2.4.6/json),
[2.5.4 resmî metadata](https://pypi.org/pypi/numpy/2.5.4/json).
Maigret/Sherlock commit'leri ve site katalogları bu ayrımla değişmez.

## Kurulumu kontrol et veya kurtar

| Komut | Davranış |
|---|---|
| `./scripts/setup-brand` | Sağlıklı mevcut ortamı doğrular; gerekirse sabit araç ortamını kurar. |
| `./scripts/setup-brand --check` | Mevcut paket/sürüm, Git kaynak bilgisi, katalog özeti, profil ve çalıştırıcı kontrollerini yapar. Yeniden kurmaz. |
| `./scripts/verify-brand` | Aynı korumalı `--check` yolunu kullanır. |
| `./scripts/setup-brand --force` | Önceki ortamı koruyarak aynı sabit araç zincirini yeniden kurar. |
| `./scripts/setup-brand --recover` | Yalnız tanınan yarım kurulum günlüğünü kurtarır; paket indirmez. |

Kurulum eski ortamı benzersiz bir yedeğe ayırır; yeni ortamı kullanılacağı
`.venv` yolunda oluşturup doğrular. Normal başarısızlıkta önceki ortam
özgün konumuna döner. Ani kesintide:

```sh
./scripts/setup-brand --recover
./scripts/setup-brand --check
```

Alt sürecin durduğu kesinleşmemişse klasörler taşınmaz; günlük ve yedek
korunur. Çalışan alt süreç bittiğinde kurtarma tekrar denenebilir. Yeni
kurulumun doğrulandığı günlüğe yazılmışsa kurtarma o yeni ortamı korur.
Önceden ortam yoksa kurtarma onu varmış gibi üretmez; ardından normal
kurulum gerekir.

## XTI çalışırken güncelleme

XTI'ın kendisi de `.venv` ortamını kullanabilir. Bu yüzden desteklenen
`./xti` ve `scripts/python` başlatıcıları ortamı seçmeden önce ortak kilidi
alır ve komut tamamlanana kadar tutar. Bu sürümün başlatıcısıyla açılmış
komut çalışırken marka ortamı
değiştirilmez; aktif kurulum varken yeni XTI komutu açık meşgul hatasıyla
durabilir. Uzun izleme komutunu bitirdikten sonra güncellemeyi başlat.
Bu korumayı ilk kez alırken önce eski sürümle başlatılmış uzun komutları
bitir; yeni kilit eski süreçlere geriye dönük olarak eklenemez.

Yarım kurulum günlüğü kalmış ama kurulum artık çalışmıyorsa varsayılan
başlatıcı sağlam temel Python'ı kullanır; saklı kanıtları okumak mümkün
kalır. Sosyal kaynaklar kurtarma tamamlanana kadar çalışmaz. Açıkça seçilen
`XTI_PYTHON` yarım yönetilen ortama işaret ediyorsa seçim reddedilir.

Başlatıcı ve kurucu, yönetilen `.venv` dışında erişilebilir bir temel
Python 3.11+ gerektirir. Yalnız taşınabilir bir `.venv` klasörünü kopyalamak
desteklenen kurulum değildir. Doğrudan `.venv/bin/python`, Maigret veya
Sherlock komutlarını elle çalıştırmak XTI başlatıcısının korumasını atlar;
normal işlemler için `./xti` kullan.

## Korunan dosyalar

- Önceki ortamlar `.venv-backup-…`, başarısız adaylar `.venv-failed-…`
  klasörlerinde tutulur. Kendiliğinden silinmezler; yeniden kurulum disk
  kullanır. Taşınmış sanal ortamlar özgün yoluna dönmeden çalışır kabul edilmez.
  Günlük yayımlanmadan kesilmiş hazırlığın `.venv-candidate-…` klasörü de
  otomatik silinmez.
- `.brand-install.lock` kalıcı kilit dosyasıdır; meşgul hatasını aşmak için
  silinmez. `.brand-install.json` kurtarma günlüğüdür. Bu dosyalar ve ortam
  yedekleri Git'e eklenmez.
- Eski sürümden kalmış `.venv-install.lock`, `.venv-backup` veya
  `.venv/.xti-installing`, yeni günlüğün sahiplik kanıtı değildir. Betik
  bunları PID tahminiyle silmez veya otomatik taşımaya çalışmaz; açık
  açıklamayla durur. Bu durumda klasörleri ve çalışan süreçleri incelemek gerekir.
- Bozuk günlük, sembolik bağlantı veya beklenmeyen klasör kimliği varsa
  bilinmeyen dosyalara müdahale edilmez.

Araç kontrolü canlı sosyal platformların erişilebilirliğini kanıtlamaz.
Bu koruma yerel POSIX dosya sistemi ve desteklenen başlatıcılar içindir;
Windows, disk kaybı ve 7/24 hizmet kabulü ayrıca değerlendirilir. Araç
ortamı yedeği, SQLite kanıt veritabanının yedeği yerine geçmez.

[Bileşen görünümü](COMPONENTS.md), [güncel doğrulama](STATUS.md),
[mimari karar](decisions/0147-recoverable-brand-environment.md).
