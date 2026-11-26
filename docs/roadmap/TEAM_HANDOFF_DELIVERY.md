# 0.194.0 ekip teslim paketi

**Tarih:** 25 Kasım 2026 · **Not:** N-057 · **Şema değişikliği:** Yok.

Bu paket yeni bir A–K toplama özelliği değildir. Mevcut 76 gereksinimin ekip
tarafından kurulabilir ve dürüst durumlarla doğrulanabilir olmasını sağlayan
yatay teslim kapısıdır.

## Teslim edilen

- `./handoff --plan` ile ağsız gereksinim ve kaynak görünümü.
- `core` ve normal `full` kabul profilleri.
- Seçilen veri alanında salt-okunur şema/bütünlük kontrolü.
- Geçici alanda init, kayıt, manifest, yedek, boş geri dönüş ve tekrar okuma.
- Yönetilen araç, sabit paket ve marka capability doğrulaması.
- Secret değeri göstermeyen Tavily, Bright Data, GitHub, GitLab ve
  XposedOrNot yeni kullanımda kapalıdır ve teslim gereksinimi değildir; eski
  maskeli kayıtlar yalnız okunur korunur.
- Nmap yetkisi, kanal hesapları ve AIL/Cowrie/CAPE dış altyapısını ayrı
  gereksinim olarak gösterme.
- Sürümlü JSON raporu, yeni dosya/`0600`/üzerine yazmama koruması.
- `REQUIREMENTS.md` ve `docs/TEAM_HANDOFF.md` ekip rehberleri.

## Yerel kanıt

- Tam profil geçici kurulum, kayıt, 55 manifest, yedek/restore ve marka
  capability kontrollerini geçti.
- Yönetilen Maigret, Sherlock ve Betterleaks ile dört sabit Python bağımlılığı
  hazır görüldü.
- Mevcut `.xti-data` önce eski şemada veri değiştirilmeden doğru biçimde
  `blocked_requirement` ve `./xti migrate` sonucu üretti; açık onaydan sonra
  doğrulanmış yedekle şema64→100 taşındı. Ana dosya ve yedek bütünlükten geçti,
  klasör izinleri `0700` oldu ve tam handoff seçilen alanda `PASS` verdi. Yedek
  boş geçici alana aynı SHA-256 ile geri yüklendi, yeniden şema100'e taşındı ve
  `ready / integrity=ok` olarak açıldı.
- `./scripts/check-fast` 2.366 testi 2.026,504 saniyede, `./scripts/check`
  3.711 testi 3.041,750 saniyede hatasız tamamladı. Her ikisinde yalnız gerçek
  Linux çalışma zamanı isteyen dört test macOS'ta beklendiği gibi atlandı.
- Tavily önce eksik, sonra özel `0600` anahtar dosyasıyla yapılandırılmış
  durumda görüldü. İzole güncel şemada SecureHup için tek canlı istek 1 kredi,
  5 saklanan kayıt ve ağsız tekrar okuma ile tamamlandı; anahtar değeri hiçbir
  rapora yazılmadı. Aynı kabul yedekli geçişten sonra kalıcı `.xti-data`
  alanında da 1 kredi, 5 saklanan kayıt ve kalıcı tekrar okuma ile geçti.

## Açık kabul kapıları

- Temiz desteklenen Linux klonu ve normal `./setup`.
- Sohbet içinde paylaşılmış geçici Tavily kabul anahtarının sağlayıcı panelinde
  yenilenip yeni değerinin yalnız gizli `mentions configure` ile kaydedilmesi.

Bu kapılar geçmeden N-057 kapatılmaz ve sürüm tam Linux teslimi olarak
sunulmaz.
