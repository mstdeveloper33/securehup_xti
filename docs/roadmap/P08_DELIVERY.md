# P08 — Kuruluş saklama, koruma ve audit teslim kartı

23 Kasım 2026. **Durum: H05'in P07 izleme ve P12 telemetri gövdeleri için
iki güvenli ailesi,
H07'nin retention yazma audit'i, I03'ün teknik amaç/dayanak/koruma desteği ve
J01'in kayıpsız provenance zinciri uygulandı. Tüm veri aileleri, okuma audit'i,
mevzuat uygunluğu ve haricî soğuk depo tamamlandı sayılmaz.**

## Kullanıcı sonucu ve gereksinimler

- **H05:** Kuruluş bazlı yaş/parti politikası; yazmasız plan; yedekli,
  kayıpsız ve geri alınabilir P07 izleme/P12 telemetri gövde arşivi.
- **H07 desteği:** Politika, hold, archive, restore, recovery ve hata
  mutasyonları için zincirli aktör/gerekçe audit'i. Güvenilir kullanıcı
  kimliği ve okuma audit'i platform katmanında kalır.
- **I03 desteği:** İşleme amacı, saklama dayanağı, açık legal/case/
  investigation/contractual hold ve kapalı otomatik silme. Uygunluk iddiası yok.
- **J01:** Run/alert/review/vaka/provenance kimliği ve hash'i korunurken
  yalnız büyük gövde sıkıştırılır; okuma ve restore hash doğrulamalıdır.

## Bileşen kararı

| Bileşen | Durum | Rol |
|---|---|---|
| XTI P07 run kayıtları | Entegre | Yönetilen kuruluş kapsamlı izleme kanıtı ailesi |
| XTI P12 telemetri kayıtları | Entegre | Güncel gövde ve değişmez sürümler için çok kuşaklı arşiv |
| SQLite şema 99 | Entegre | Politika, olay, hold, run, arşiv, audit ve tekrar makbuzu |
| Python stdlib `zlib` | Entegre | Boyut sınırlı kayıpsız sıkıştırma |
| Engine/platform JSON v1 | Entegre | Salt okuma ve workspace çitli yazma |
| Haricî repo/API/paket | Yok | P08 ağsızdır |
| S3/Blob/soğuk depo | Seçilmedi | Ayrı işletim ve veri yerleşimi kararı gerekir |

## Uygulanan yaşam döngüsü

1. Politika kuruluş, aile, yaş, parti, amaç ve dayanakla sürümlenir.
2. Plan eski tamamlanmış run'ları seçer; yakın kayıt, açık hold, aktif vaka
   kanıtı, mevcut arşiv, eksik gövde ve gerçek kazanç sağlamayan gövdeyi ayırır.
3. Plan token'ı politika/aday/hash kapsamına bağlıdır. Değişiklikte uygulama
   yazmadan durur; aynı idempotency anahtarı aynı makbuzu döndürür.
4. Uygulama tam yedek alır; gövdeyi sıkıştırır; sıcak satırda arşiv kimliği
   ve checksum'a bağlı işaretçi bırakır. Mantıksal kayıt silinmez.
5. P07 ve P12 normal okumaları arşivi şeffaf açar; kanonik JSON, boyut, binding ve
   hash bozuksa fail-closed durur.
6. Restore yine yedek alır ve sıcak gövdeyi geri koyar. Yarım çalışmalar
   yalnız açık recovery ile `interrupted` olur.
7. Mutasyonlar zincirli audit olayıdır. Liste yüzeyleri cursor ile sayfalanır.
8. P12 güncellemesi yeni sıcak sürümü ve yeni arşiv kuşağını oluşturabilir;
   eski kuşağı geri yüklemek yeni güncel gövdeyi ezmez.
9. Şema96→97 ve 98→99 açık migrate, değişmemiş eski verinin kurtarma
   yedeğiyle geçer.

## Güvenlik ve doğruluk sınırları

- P08 otomatik mantıksal silme, `VACUUM`, dış dosya taşıma veya zamanlayıcı
  çalıştırmaz.
- P07 `unified_monitoring_runs` ve P12 `telemetry_records` gövdeleri yönetilir.
  Vaka kanıtı, review, alarm ve karar kayıtları daima korunur.
- Cowrie/CAPE kurulmaz, başlatılmaz ve zararlı örnek çalıştırılmaz; P12
  saklama yalnız önceden normalize edilip XTI'ya alınmış kayıtları işler.
- Audit hash zinciri bütünlük kontrolüdür; dijital imza veya kimlik doğrulama
  değildir. Backend `actor` alanını güvenilir oturumdan üretmelidir.
- Legal hold türü teknik korumadır; hukuk prosedürünün yeterliliğini kanıtlamaz.
- Amaç/dayanak ve süre alanları GDPR/KVKK/CCPA uygunluk sertifikası değildir.

## Yerel kabul sonucu

| Alan | Sonuç |
|---|---|
| P08 hedefli testler | 9 test: politika yaşam döngüsü, hold, plan, arşiv, tamper, şeffaf okuma, restore, recovery, pagination, CLI, engine/platform, tenant ve migration |
| Yakın regresyon | P07/P08, engine/platform, vaka, storage, backup ve şema62→97 envanteri: 124 test; macOS'ta 2 beklenen Linux atlaması; hata yok |
| Şema geçişi | 96→97 yedekli; asset/P07/vaka şeması korunuyor; 95→97 zinciri geçti |
| Firma sınırı | Yanlış workspace reddediliyor; başka firma kimliği `not_found` |
| Bozuk kanıt | Audit zinciri ve sıkıştırılmış gövde bozulması fail-closed |
| Kapasite | İki ayrı firma × 13 değişen run; firma başına 2 archive + 1 restore; replay yeni çalışma üretmedi |
| Sıkıştırma | Alpha 8.956.764→2.072.927 bayt (%23,1437); beta 8.930.571→2.074.699 bayt (%23,2314) |
| Süre/bellek/ağ | En yavaş parti 2,403419 sn; tepe RSS 89,86 MiB; ağ isteği 0 |
| Hızlı repo kapısı | 2.303 test / 1.763,154 sn; hata yok; macOS'ta 4 beklenen Linux atlaması |
| Tam repo kapısı | 3.644 test / 2.673,083 sn; hata yok; macOS'ta 4 beklenen Linux atlaması |
| P12 retention hedefli kabul | 3 yaşam döngüsü/migration/tamper testi; güncelleme ve iki kuşaklı restore dahil, hata yok |
| P12 retention kapasite | İki firma × 1.000 kayıt; firma başına 4×250 arşiv + 250 restore; ağ isteği 0 |
| P12 sıkıştırma/süre | Alpha %5,1747; beta %5,1751; en yavaş parti 4,419557 sn; tepe RSS 106,42 MiB |

Kapasite komutu:

```sh
PYTHONPYCACHEPREFIX=/tmp/xti-pyc ./scripts/python \
  scripts/check-data-retention-delivery.py

PYTHONPYCACHEPREFIX=/tmp/xti-pyc ./scripts/python \
  scripts/check-telemetry-retention-delivery.py
```

## Açık doğrulamalar

Bu sınırlar kalıcı olarak [NOTES N-051](../../NOTES.md#n-051--p08-retention-audit-ve-mevzuat-sınırı)
altında sahipleri ve kapanış koşullarıyla izlenir.

1. Push sonrasında gerçek Linux kurulum/yükseltme sonucu ayrı kaydedilecek.
2. Okuma erişim audit'i, güvenilir kullanıcı/RBAC, scheduler ve bölgesel
   depolama tüketici platform/işletim kapsamındadır.
3. P07 ve P12 dışındaki yeni veri ailesi kendi silme/koruma/provenance/
   restore kabulü olmadan P08 kataloğuna eklenmeyecektir.

Kullanım: [DATA_RETENTION](../DATA_RETENTION.md). Mimari karar:
[ADR0193](../decisions/0193-organization-retention-and-audit.md) ve P12
genişletmesi [ADR0197](../decisions/0197-telemetry-retention-generations.md).
