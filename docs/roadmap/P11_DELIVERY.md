# P11 teslimi — yeraltı ve credential kaynak genişletme

24 Kasım 2026 · XTI 0.193.0 · çekirdek şema 100.

## Gereksinim kapsamı

| ID | Sonuç |
|---|---|
| A02 | AIL 7.x için minimize edilmiş, firma kapsamlı tracker zarfı ve mevcut dark-web inceleme yaşam döngüsü tamamlandı; gerçek AIL kurulumu/kaynağı ve canlı olay kabulü dış gereksinimdir. |
| A07 | Lunar ve AIL, P09 kataloğunu 55 kaynağa çıkaran sürümlü erişim, hak, kota, hata ve provenance manifestleriyle eklendi. |
| A10 | Lunar son 12 aylık employee/client ve breach/infostealer sayılarını bireysel credential almadan sağlar; ham stealer-log sağlayıcısı bilinçli olarak eklenmedi. |
| A13/I04 | AIL zarfı çok dilli kaynak metaverisini taşıyabilir; gerçek RU/ZH/AR/TR/PT yeraltı kapsamı canlı kaynak olmadan tamamlanmış sayılmaz. |
| C06-C07/E01-E03 | Toplu maruziyet ve yeraltı iddiası mevcut P05 firma eşleşmesi, sessiz başlangıç, değişiklik, insan kararı, inbox ve vaka akışına bağlandı. |
| I03/J01/J03 | Veri minimizasyonu, kaynak/commit/hash/tarih izi ve insan onayı zorunlu tutuldu; hukuk uygunluğu iddia edilmedi. |

## Teslim edilen yaşam döngüsü

1. Anahtarsız, kesin domain kapsamlı Lunar sorgusu ve toplu sonuç makbuzu.
2. `REPORT_READY`, `GENERATING_REPORT`, `NOT_AUTHORIZED`, kota ve kaynak
   hatalarının birbirinden ayrılması.
3. Son başarılı snapshot'ı pending/başarısız turda koruyan sürümlü kaynak
   çalışma geçmişi.
4. AIL 7.x için 2 MiB/1.000 kayıt sınırlı, tam alanlı `xti-ail-v1` zarfı.
5. Normal dosya/no-follow okuma, yazmasız önizleme ve beklenen içerik
   SHA-256 onaylı atomik/idempotent içe alma.
6. Güncel normalize kaynak kaydı, eklenen/değişen/kaldırılan değişiklik
   geçmişi ve hash-zincirli tur bütünlüğü.
7. Mevcut P05 analiz, bulgu, review, inbox, vaka ve kuruluş JSON görünümünün
   yeniden kullanılması.
8. Engine v1 salt okuma; firma platformunda workspace çitli okuma/yazma ve
   Lunar ağ operasyonunun açık biçimde ilan edilmesi.
9. Yarım kaynak turu için açık recovery; backup/restore ile yeni tabloların
   taşınması.
10. Şema99→100 yedekli, atomik ve eski kimlik/sequence koruyan geçiş.
11. Kaynak manifesti, kullanım, mimari, lisans, ticari not ve özellik
    kataloğunun güncellenmesi.

## Veri minimizasyonu

Lunar tarafında yalnız domain, rapor penceresi, beş toplu sayı ve ilk/son
tarih tutulur. AIL tarafında yalnız object/evidence hash'i, sınırlı nesne/ağ
türü, zaman, kuruluş kapsamındaki kesin eşleşme ve iddia türü tutulur. Ham
sayfa, alıntı, e-posta, parola, token, cookie, kullanıcı hesabı, kaynak/Tor
adresi, indirilen dosya ve oturum bilgisi kabul edilmez. Hiçbir sonuç otomatik
incident değildir.

## Kullanıcı sonucu

Örneğin kullanıcı `example.com` domainini izliyorsa Lunar “son 12 ayda kaç
toplu credential maruziyet olayı var?” sorusunu kişileri göstermeden
yanıtlar. Ayrı AIL sistemi firma domainini bir forum kaydında eşleştirirse
XTI ham forumu kopyalamaz; yalnız hash bağlı “data leak iddiası var” adayını
analiste getirir. Analist ilgili/ilgisiz/belirsiz kararını verir ve gerekirse
kanıtı vakaya bağlar.

## Kurulum ve yükseltme

Normal `./setup` yeterlidir; P11 yeni Python paketi, container veya otomatik
AIL kurulumu eklemez. Mevcut kayıt alanında önce `./xti migrate` çalıştırılır;
işlem şema99 verisini değiştirmeden önce yedekler ve şema100 tablolarını boş
başlatır. Lunar anahtar istemez. AIL kullanımı için bu repodan bağımsız,
yalıtılmış ve izinli bir AIL kurulumu ile zarfı üreten işletici connector'ü
gerekir; örnek dosya yalnız biçim kabulü içindir.

## Kabul kanıtı

- Lunar sınır, pending, scope, tutarlı toplamlar ve PII azaltma testleri geçti.
- AIL yanlış firma eşleşmesi, bilinmeyen/ham alan, yinelenen kayıt, symlink,
  boyut ve hash sapmasında yazmadan kapalı durur.
- Kaynak geçmişi, son başarılı kanıt koruma, idempotent tekrar, tek değişim,
  insan incelemesi, şirket görünümü, platform izolasyonu, recovery ve bozulma
  tespiti doğrulandı.
- Gerçek şema99→100 kesintisi byte düzeyinde geri alındı; başarılı geçiş eski
  profil kimliği/sequence değerini korudu.
- Hedefli P11/P05/platform/yönetişim paketi **49 test / 24,432 saniye** ile
  hatasız geçti.
- `scripts/check-darkweb-p11-delivery.py` iki ayrı firma alanında firma
  başına 1.000 AIL kaydını üç turda sınadı. İlk tur 1.000 ekleme, ikinci tur
  1.000 değişmeyen, üçüncü tur yalnız bir güncelleme üretti; idempotent replay
  yeni çalışma üretmedi. Kayıt ve bulgular 10'ar sayfada kayıpsız okundu.
- Son kapasite tekrarında toplam süre 7,913 saniyeydi. En yavaş içe alma
  0,677075 saniye, en yavaş analiz 0,484509 saniye, tepe RSS 67,12 MiB,
  iki veritabanı 11.362.304/11.354.112 bayt ve ağ isteği sıfırdı.
- Güncel hızlı repo kapısı **2.354 test / 2.048,506 saniye**, tam repo kapısı
  **3.699 test / 3.317,377 saniye** ile hatasız geçti. Her iki koşuda da
  yalnız Linux çalışma zamanı isteyen dört test macOS'ta beklendiği gibi
  atlandı; başarısız test yoktur.
- `securehup.com` gerçek Lunar çağrısı 24 Kasım 2026'da tamamlandı: dönem
  2025-11-01–2026-10-31, toplam/employee/client/infostealer/data-breach
  sayıları sıfır. Bu yalnız başarılı boş kaynak sonucudur.

## Açık dış gereksinimler

- Ayrı ve sertleştirilmiş AIL 7.x kurulumu.
- Açıkça seçilmiş, erişim yetkisi ve hukuk/veri işleme amacı doğrulanmış
  forum/pazar/Tor/kanal kaynağı.
- Gerçek AIL tracker olayıyla connector → zarf → XTI canlı kabulü.
- AIL AGPL dağıtım biçimi ile kaynağın saklama/müşteriye gösterim koşulunun
  ticari üretim öncesi onayı.
- XposedOrNot yeni kullanımda 0.195.1/ADR0201 ile kapatıldı; P11 için anahtar,
  doğrulanmış domain veya canlı kabul gereksinimi değildir.
- Push sonrası gerçek Linux kurulum/yükseltme ve Linux CI kabulü.

Bu gereksinimler tamamlanmadan “bütün dark web taranıyor”, “AIL canlı
üretimde” veya “credential sızıntısı doğrulandı” denmez.
