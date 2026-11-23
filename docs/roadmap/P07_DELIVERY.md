# P07 — Birleşik izleme ve alarm politikası teslim kartı

22 Kasım 2026. **Durum: E01 ve E03'ün yerel motor kapsamı uygulandı;
E05 için zamanlanabilir/due sözleşmesi ve birleşik rapor hazır. Gerçek
platform zamanlayıcısı ve haricî teslim kanalları tüketici platform işidir.
J01 provenance ile J03 insan incelemesi aynı zincirde desteklenir.**

## Kullanıcı sonucu ve gereksinimler

- **E01:** Domain, marka, IP, kelime, kişi ve tedarikçi hedeflerini tek
  kuruluş politikasında, seçilmiş saklı kayıt aileleri üzerinde izleme.
- **E03:** Eklenen/değişen/kaybolan kayıt seçimi, minimum değişiklik eşiği,
  alarm önceliği, sessiz ilk tur ve gerekçeli insan geri bildirimi.
- **E05 motor desteği:** Politika aralığı, zamanı gelenler listesi, normal
  çalışma zaman çiti ve kuruluş birleşik raporu. Motor kendi daemon'unu
  başlatmaz ve haricî alıcıya göndermez.
- **J01:** Alarmdan değişmez snapshot, kaynak/kayıt kimliği, kaynak çalışma
  kimliği ve hash zincirine izlenebilirlik.
- **J03:** `useful`, `not_useful`, `uncertain` karar geçmişi; okundu
  durumundan ayrı; vakaya dondurulabilir kanıt.

E02 haricî bildirim kanalları ve E04 gerçek zamanlı streaming bu paketle
açılmadı. LLM, geniş STIX/TAXII ve yeni ücretli veri kaynağı eklenmedi.

## Bileşen kararı

| Bileşen | Durum | Rol |
|---|---|---|
| XTI global saklı arama | Seçili ve entegre | 12 kayıt ailesinden tek transaction snapshot |
| XTI kuruluş bağları | Seçili ve entegre | Domain hedeflerinin firma kapsamını doğrulama |
| SQLite şema 96 | Seçili ve entegre | Sürümlü politika, çalışma, alarm, karar ve idempotency |
| XTI inbox/vaka | Seçili ve entegre | Ortak okunma, inceleme ve dondurulmuş vaka kanıtı |
| Engine/platform JSON v1 | Seçili ve entegre | UI/.NET için salt okuma ve firma çitli yazma |
| Yeni repo/ücretli API | Yok | P07 yalnız saklı kanıtı değerlendirir |
| E-posta/SMS/Slack/Teams | Seçilmedi | E02 ayrı ürün/işletim kararı |
| Kafka/streaming | Seçilmedi | E04 ayrı ölçek ve gecikme kabulü |

## Uygulanan yaşam döngüsü

1. Politika kuruluş, hedefler, kayıt türleri, eşleşme biçimleri, eşik,
   öncelik ve aralıkla sürümlenir; aktör/gerekçe olay kaydında kalır.
2. Domain hedefi etkin kuruluş bağı olmadan kaydedilemez ve çalışma anında
   bağ yeniden doğrulanır.
3. Tek SQLite okuma transaction'ı saklı eşleşme ve kaynak kapsamını dondurur;
   ağ isteği veya araç süreci başlatılmaz.
4. İlk tur sessiz baseline'dır. Sonraki tur added/updated/removed farkını
   hash ile açıklar; yalnız seçilmiş türler eşik hesabına girer. Özet bütün
   sayıları ve ilk 100 ayrıntıyı taşır; tam fark `run.changes` ile sayfalanır.
5. Eşik alarmı ortak global notification sequence ile inbox'a girer.
   İnsan kararı revision ve idempotency ile eklenir; karar okundu durumundan
   bağımsızdır.
6. Alarm/run hash'i, kuruluş kapsamı, bütün sayılar ve ilk100 fark ayrıntısı
   kompakt vaka kanıtına bağlanabilir; sonraki tarama eski kanıtı değiştirmez.
   Tam kanıt özgün run'ın sayfalı yüzeyinde kalır.
7. Değişmeyen tur büyük snapshot JSON'unu kopyalamaz; önceki aynı hash'li
   kanıtı doğrulanabilir referansla kullanır. Yeni kaynak kapsamı veya kayıt
   durumu yeni snapshot üretir. Snapshot, iç arama nesnesinin ağır semantic/
   navigation gövdesi yerine kimlik/durum hash'i ve sınırlı provenance taşır.
8. Yarım `running` kayıt yalnız açık recover ile `interrupted` olur.
   Şema 95→96 önce yedeklenir; restore boş hedef ister.

## Güvenlik ve doğruluk sınırları

- Alarm metin/kimlik değişikliğidir; otomatik tehdit, olay, sahiplik veya
  zararlılık hükmü değildir.
- Öncelik politika seçeneğidir; olasılık veya CVSS benzeri risk puanı değildir.
- Kaynak yenileme P07 dışında collector/source-job sorumluluğudur. Başarısız
  veya eski kaynak durumu snapshot kapsamından gizlenmez.
- Tüm JSON alanları katı/boyut sınırlıdır. Bilinmeyen alanlar, farklı
  workspace, eski revision, idempotency çatışması ve bozuk hash güvenli
  biçimde reddedilir.
- Kapasite dolunca otomatik silme yoktur. Retention/arsiv politikası ileride
  açık veri yönetimi kararıyla eklenmelidir.

## Yerel kabul sonucu

| Alan | Sonuç |
|---|---|
| P07 hedefli testler | 13 test: politika, fark/sayfalama, alarm, review, inbox, vaka, CLI, engine/platform, izolasyon, migration, tamper, kompakt kanıt ve dedupe |
| Şema geçişi | 95→96 yedekli/atomik; eski vaka düzeni ve asset korunuyor |
| Firma sınırı | Yanlış workspace reddediliyor; başka firma kayıt kimliği `not_found` |
| Ağ sınırı | Engine, platform ve birikimli kabulde ağ isteği 0 |
| Değişmeyen tur | Aynı snapshot gövdesi tekrar yazılmıyor; run/report geçmişi korunuyor |
| Yakın regresyon | Inbox, vaka, kuruluş, engine, platform, migration ve backup/storage dahil 192 test, 151,840 sn; hata yok |
| Kapasite | İki ayrı firma × 5.000 eşleşme × 32 çalışma; 30 değişmeyen tur/firma, 2 snapshot/firma, 1 gerçek değişiklik→1 alarm; ağ 0; tepe RSS 115,02 MiB; en yavaş run 1,401029 sn; toplam 81,081 sn |
| Hızlı repo kapısı | CI ile aynı iki shard: 1.182 test / 810,786 sn ve 1.112 test / 969,958 sn; toplam 2.294 test, hata yok; macOS'ta Linux'a özgü toplam 4 test beklendiği gibi atlandı |
| Tam repo kapısı | 3.635 test / 2.719,142 sn; hata yok; macOS'ta Linux'a özgü 4 test beklendiği gibi atlandı |
| Linux CI | Push ve gerçek Linux kabulü kullanıcı kararıyla ayrıca yapılır |

Kapasite komutu:

```sh
PYTHONPYCACHEPREFIX=/tmp/xti-pyc ./scripts/python \
  scripts/check-unified-monitoring-delivery.py
```

Bu ölçüm iki izole firma alanında ayrı süreçlerle gerçek saklı arama yolunu
kullanır; 512 MiB kapısının altında kalmıştır. Bütün internet, 7/24 SLA, dış
collector veya platform scheduler kabulü değildir.

## Açık doğrulamalar

1. Push sonrasında gerçek Linux yükseltme/servis sonucu ayrı kaydedilecek.
2. .NET platformunun scheduler, kullanıcı/RBAC/audit ve haricî kanal teslimi
   bu motor paketinin içinde değildir; çağıracağı JSON işlemleri hazırdır.
3. Retention kararı olmadan P07 geçmişi otomatik silinmez. 128 MiB kanıt
   gövdesi sınırı aşıldığında açık kapasite hatası alınır.

Kullanım: [UNIFIED_MONITORING](../UNIFIED_MONITORING.md).
