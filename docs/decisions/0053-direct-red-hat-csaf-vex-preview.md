# 0053 — Doğrudan Red Hat CSAF VEX önizlemesi

## Durum

Kabul edildi — 29 Ekim 2026.

## Bağlam

OSV duyuru bağlantılarını toplar, ancak dağıtımın backport ve ürün-bileşen durumunu
tek başına üretici hükmüne dönüştürmez. Red Hat her CVE için üretim kullanımına hazır
CSAF VEX 2.0 belgesi yayımlar. Bu belgede Red Hat portföyündeki bileşenler düzeltilmiş,
etkilendiği bilinen, etkilenmediği bilinen veya inceleniyor olarak ayrı gösterilir.

## Karar

- Açık `vuln vendor-preview CVE-YIL-SAYI --provider redhat` komutu yalnız sabit
  `security.access.redhat.com` yıl/CVE HTTPS yolunu okur; gizli toplu iş yoktur.
- Taşıma yönlendirmesiz, kimlik kodlamalı, 30 saniye ve 16 MiB ile sınırlıdır.
  Yayımcı kimliği, CSAF sürümü, CVE bağı, zamanlar, sürüm geçmişi, ürün ağacı,
  durum üyeliği ve düzeltme hedefleri bütün önizleme kabul edilmeden doğrulanır.
- Aynı ürün/bileşen birden çok durumdaysa veya ürün ağacında bulunmuyorsa belge
  reddedilir. Gösterim kesilse bile bütün durum ve düzeltme hedefleri doğrulanır.
- Önizleme veritabanı/veri klasörü, maruziyet, insan kararı veya destek kanıtı oluşturmaz.
- Red Hat VEX beyanı yalnız Red Hat ürünleri için kaynak gerçeğidir; başka dağıtım,
  genel upstream sürümü veya yerel varlığa taşınmaz. `fixed` ve `known_not_affected`
  ancak tam ürün/bileşen kimliği ve kurulu paket bağlamıyla yorumlanabilir.
- Şema 22 korunur.

## Sonuçlar

Analist toplayıcı bağlantısından bağımsız, doğrudan dağıtım kaynağındaki backport ve
ürün durumunu görebilir. Red Hat paket kimliğini yerel envanterle güvenilir eşleştirme,
VEX kaydını kalıcı kanıta bağlama ve diğer dağıtım sağlayıcıları ayrı teslimlerdir.
