# 0051 — Açık ve yazmasız OSV duyuru önizlemesi

## Durum

Kabul edildi — 29 Ekim 2026.

## Bağlam

Bir maruziyet incelemesinde NVD koşullarına ek olarak üretici veya dağıtım duyurusu
bulmak gerekir. Ücretsiz OSV API'si paket, sürüm aralığı ve duyuru başvurularını tek
CVE bağlamında toplayabilir. Ancak OSV bir toplayıcıdır; kaydı doğrudan üretici kararı
veya yerel varlıkta zafiyet kanıtı saymak yanlış otomasyona yol açar.

## Karar

- Yalnız açık `vuln advisory-preview CVE-YIL-SAYI` komutu sabit OSV.dev HTTPS
  uç noktasına bağlanır; gizli toplu iş, arka plan sorgusu veya otomatik tekrar yoktur.
- Yanıt yönlendirmesiz, kimlik kodlamalı, 30 saniye ve 8 MiB sınırında alınır. JSON
  alanları, CVE bağı, zamanlar, paket/aralık olayları ve başvurular bütünüyle doğrulanır.
- Gösterim paket ve `ADVISORY` başvurularını ayrı 1–200 sınırlarıyla kesebilir; fakat
  alınan kaydın tamamı önce doğrulanır.
- Önizleme veri klasörü veya veritabanı oluşturmaz; OSV kaydı, paket aralığı ve bağlantı
  otomatik maruziyet kararı, öncelik veya destek kanıtı üretmez.
- OSV'de paket bağlamının olmaması “etkilenmiyor” demek değildir. HTTP başvuruları
  yalnız araştırma bağlamıdır; kalıcı duyuru kanıtı mevcut politika gereği HTTPS ister.
- Kaynak hatası sınırlı kullanıcı mesajıyla durur; uzak hata içeriği ve traceback
  terminal/JSON çıktısına taşınmaz. Güncel şema 22 korunur.

## Sonuçlar

Analist ücretsiz internet kaynağından duyuru adaylarını doğrudan terminalde görebilir,
ancak karar ve kalıcı kanıt için açık insan adımı gerekir. Güvenilir üretici/dağıtım
adaptörü, başvuru seçimi, içerik özeti ve backport politikası ayrı teslimlerdir.
