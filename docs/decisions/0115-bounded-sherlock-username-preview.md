# 0115 — Sınırlı ve yazmasız Sherlock kullanıcı adı önizlemesi

**Durum:** Kabul edildi  
**Tarih:** 31 Ekim 2026  
**Sürüm:** 0.117.0

## Bağlam

0.116.0 kapsam kapısı, Sherlock'un mevcut Maigret platformlarını çoğaltmak
yerine 101 ayrı kayıt kökünde ek kapsam taşıdığını ölçtü ve sekiz platformluk
elle incelenmiş kısa listeyi kabul etti. Kullanıcının gerçek internet sonucu
görebilmesi için kaynak çalıştırılmalıdır; ancak geniş katalog gereksiz trafik
üretir. Sherlock 0.16.2 komut satırı ayrıca yerel katalog seçilmiş olsa bile
GitHub sürüm sayfasını kontrol eder. Bu gizli ek istek, yalnız seçilen profil
sitelerine gitme sınırıyla uyumlu değildir.

## Karar

- `sherlock-project` 0.16.2, resmî deponun tam
  `a38ba54fda799cd786a2ab67a50143e1a63169e6` commit'inden yalnız `brand`
  isteğe bağlı bağımlılığı olarak kurulur. Çekirdek kurulum Sherlock almaz.
- Kurulu site kataloğu her çalışmada 104.039 baytlık beklenen dosya ve
  `3fdfc6694c5cd99798881215554b09e617c6d5284a6219fae309882566a9fb30`
  SHA-256 özetiyle doğrulanır. Yinelenen JSON alanı veya farklı dosya tüm
  sonucu durdurur.
- Yalnız Carrd, CashApp, CodeSandbox, GitBook, ResearchGate, Rumble, Strava ve
  Weebly seçilebilir. Varsayılan küçük küme Carrd, CodeSandbox, GitBook, Rumble
  ve Weebly'dir. Başlangıç HTTPS hostları ayrı izin listesiyle doğrulanır.
- Sherlock CLI kullanılmaz. Ayrı ve geçici bir Python işçisi, sabit paketin
  `sherlock()` kütüphane işlevini yalnız seçilen katalog nesneleriyle çağırır.
  Böylece CLI sürüm kontrolü ve canlı katalog/exclusion yolu çalışmaz.
- İşçi upstream çıktı dosyalarını kullanmaz. Her seçili platform için yalnız
  kullanıcı adı, platform, profil adresi ve durum taşıyan XTI NDJSON raporu
  oluşturur. Ana süreç alan kümesini, tekrarları, UTF-8'i, satır/dosya boyutunu,
  kullanıcı adı ve platform bağını, durum değerini ve HTTPS profil hostunu
  yeniden doğrular.
- `Claimed`, yalnız `found_unverified` olarak gösterilir. `Available`,
  `Unknown`, `Illegal` ve `WAF` ayrı bir kesin hükme çevrilmeden “raporlanmadı”
  grubunda kalır. Bulunan aynı kullanıcı adı sahiplik veya taklit kanıtı
  değildir.
- Her platform isteği 5–30 saniye; bütün alt süreç en fazla istek süresi + 20
  saniye ve mutlak 60 saniyeyle sınırlıdır. Süreç/kayıt çıktısı ve geçici dosya
  boyutları sınırlıdır. Kabuk, kullanıcı proxy'si, OpenAI anahtarı, Tor, I2P,
  toplu kullanıcı adı, türetme, profil ayrıntısı çıkarımı ve ham yanıt saklama
  kullanılmaz.
- `brand username-preview ... --source sherlock` veritabanını açmaz veya
  yazmaz. Geçici katalog ve rapor işlem sonunda kaldırılır. Kalıcı Maigret
  izleme yaşam döngüsü bu teslimde Sherlock'a genişletilmez.

## Sonuçlar

Kullanıcı, ücretsiz ikinci kaynakta gerçek sonuç görebilir ve her ağ işi açık
komuta, tam kullanıcı adına ve küçük platform listesine bağlıdır. Upstream
CLI'ın görünmeyen sürüm isteği ortadan kalkar; yalnız seçilen platformların ilk
adreslerine istek başlatılır. Hedef platformların kendi HTTPS yönlendirmeleri,
oran sınırları ve erişilebilirliği XTI'nin kontrolünde değildir.

Kurulu paket veya katalog incelenen sürümden saparsa uyumluluk tahmini yapılmaz;
komut güvenli biçimde durur. Bir platformun raporlanmaması hesap yokluğu,
silinme veya güvenlik hükmü değildir. Sonraki kalıcı çok-kaynak izleme teslimi,
Maigret ve Sherlock sonuçlarını kaynak kimliğini kaybetmeden ayrı başlangıç
çizgileriyle saklamalıdır.

## Kabul kanıtı

Otomatik testler platform/süre doğrulamasını, tam katalog özetini, seçili katalog
daraltmasını, HTTPS/443 host sınırını, ayrı işçi komutunu, güvenli ortamı, katı
NDJSON şemasını, eksik/tekrarlı/bozuk sonuçları, süre aşımını, yanlış sürümü ve
yazmasız terminal/JSON yolunu kapsar. Ayrı canlı kabulde yalnız Carrd seçilerek
Sherlock'un kendi katalog örneği `blue`, `https://blue.carrd.co/` adresinde
“bulundu, doğrulanmadı” olarak raporlandı; XTI kullanıcı veritabanına yazılmadı.
