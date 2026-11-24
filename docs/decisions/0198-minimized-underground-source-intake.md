# 0198 — Minimize edilmiş yeraltı kaynağı ve toplu domain maruziyeti

Tarih: 24 Kasım 2026 · Durum: kabul edildi · Paket: P11 · Şema: 100.

## Bağlam

P05, ransomware iddiaları ile XposedOrNot verified-domain sonucunu güvenli
bir inceleme yaşam döngüsüne bağladı; ancak genel forum/pazar/Tor kapsamı ve
anahtarsız toplu credential maruziyeti yoktu. XTI'nın kendi Tor crawler'ını
yazması; giriş, CAPTCHA, oturum, kaynak hukuku, yüksek riskli ham içerik ve
işletim güvenliği sorunlarını aynı sürece taşırdı. Bireysel credential veya
ham yeraltı sayfasını merkez veritabanında tutmak da mevcut veri minimizasyonu
kararına aykırıydı.

## Karar

- Anahtarsız toplu domain maruziyeti için Webz.io/Lunar Domain Exposure API
  seçildi. Yalnız kesin kuruluş domaini sorgulanır; son 12 aya ait toplam,
  breach/infostealer, employee/client sayıları ile ilk/son tarih tutulur.
- Lunar'ın bireysel credential, PII, login URL listesi ve ayrıntılı kırılımı
  XTI sınırını geçmez. `GENERATING_REPORT` başarılı boş sonuç değildir;
  `pending` olarak saklanır. Başarısız tur son başarılı kanıtı silmez.
- Yeraltı toplaması için AIL Framework 7.x ayrı ve sertleştirilmiş sistem
  adayıdır. XTI AIL'i kurmaz, başlatmaz, içine kod kopyalamaz veya Tor'a
  kendisi bağlanmaz.
- AIL ile XTI arasındaki sınır kesin `xti-ail-v1` zarfıdır. Zarfta yalnız
  hash bağlı nesne/kanıt kimliği, nesne türü, ağ sınıfı, zaman, kuruluş
  adı/domain eşleşmesi ve iddia türü bulunabilir.
- Ham sayfa, kaynak/Tor/I2P adresi, credential, kullanıcı hesabı, cookie,
  session, indirilen dosya ve ekran görüntüsü kabul edilmez veya saklanmaz.
- AIL kaydı `underground_mention` adlı kaynak iddiasıdır; doğrulanmış sızıntı
  ya da incident değildir. Mevcut P05 inceleme, değişiklik, inbox, vaka ve
  kuruluş görünümü yeniden kullanılır.
- Engine salt okur. Firma platformu workspace-çitli önizleme/içe alma yapar;
  platform JSON zarfı genel 65.536 bayt sınırına tabidir. Güvenilen yerel CLI
  en çok 2 MiB ve 1.000 kaydı no-follow normal dosyadan alır.

## Seçilen dış bileşenler

- [Webz.io/Lunar Domain Exposure API](https://docs.webz.io/docs/webz/dea-introduction)
  ücretsiz ve anahtarsız toplu veri kaynağıdır; XTI sağlayıcı kodu kullanmaz.
- [AIL Framework v7.1](https://github.com/ail-project/ail-framework/releases/tag/v7.1)
  ayrı yeraltı toplama/analiz sistemidir. İncelenen commit
  `4b94304bcd4d3d08b9e0c0772be4773e6bbbd350`, kök lisans AGPL-3.0'dır.
  XTI yalnız sürümlü metadata zarfını alır; AIL dağıtımı bu repoya dahil
  değildir.

Yazılım lisansı, AIL'e bağlanan forum/pazar/kanal içeriğinin toplanma,
saklanma veya müşteriye gösterilme hakkını sağlamaz. Her gerçek kaynak ayrı
yetki, hukuk, minimizasyon ve canlı kabul gerektirir.

## Sonuçlar

Şema100 kaynak turu, güncel normalize kayıt ve değişiklik zincirini ekler.
Şema99→100 geçişi önce yedek alır; mevcut profil/satır/sequence değerlerini
korur ve yeni tabloları boş başlatır. Kaynak turları idempotenttir; aynı
kanıt çoğalmaz, değişen kanıt sürümü ve insan incelemesi korunur. Yarım tur
açık `recover` ile kesilmiş duruma alınır.

Lunar `securehup.com` canlı kabulü başarıyla tamamlandı ve 1 Kasım 2025–31
Ekim 2026 penceresinde sıfır toplu olay döndürdü. Bu, yalnız o kaynak ve
pencerede başarılı sıfır sonuçtur; güvenlik kanıtı değildir. Gerçek AIL
kurulumu, seçilmiş yasal kaynak ve gerçek AIL olayı bulunmadığından AIL canlı
kabulü açık dış gereksinim olarak kalır.
