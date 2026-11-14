# RansomLook bildirim kutusu — Aşama 7

**Durum: TAMAMLANDI — 0.133.0.**
**Tarih: 14 Kasım 2026.** Şema 59 ayrı RansomLook izleme bildirimini ekler.
Güncel kapsam [STATUS](../STATUS.md) dosyasındadır; uygulama sürümü 0.133.0’dır.

## Kullanıcının gördüğü sonuç

RansomLook kuruluş izlemesinde sessiz başlangıçtan sonra bulunan yeni veya
değişen eşleşmeler yerel `inbox` içinde çalışma başına tek bildirim oluşturur.
Kaynak adı, bugünkü izleme etiketi, tarihî tanım özeti, kaynak yenileme ve
izleme çalışması kimlikleri, fark sayıları gösterilir. Tam sonuç:

```sh
./xti inbox
./xti inbox show BILDIRIM_KIMLIGI
./xti ransomware watch-run-show CALISMA_KIMLIGI --source ransomlook
./xti inbox read BILDIRIM_KIMLIGI
```

İlk ölçüm, tanım değişikliğinden sonraki ilk ölçüm, değişmeyen sonuç, yalnız
kaynak penceresinden çıkış ve kaynak hatası bildirim üretmez. Çıkış çözüm
kanıtı değildir; okundu bilgisi de iddianın doğruluğu veya insan kararı
sayılmaz. ThreatCluster ve RansomLook ortak kutuda ayrı kaynaklar kalır;
aynen görünen kuruluş adı onları tek doğrulanmış olay yapmaz.

## Kalıcılık ve sınırlar

- `attention_count`, sessiz başlangıç dışında `added_count + updated_count`
  olarak korunur. Mevcut iddia kimliği alanları değişince ayrı iddia oluştuğu
  için güncel kaynak sözleşmesinde `updated_count` fiilen sıfır kalabilir.
- Ayrı `ransomlook_watch_notifications` tablosu global sıra, benzersiz
  bildirim ve çalışma kimliği, izleme bağı, sabit olay türü, oluşturma ve
  okundu zamanı tutar. Yanlış kaynak/izleme bağı okumada reddedilir.
- Çalışma, sonuç öğeleri, bildirim ve varsa toplama receipt'i aynı SQLite
  transaction içinde yazılır. Başarısız bildirim yazımı yarım sonuç bırakmaz.
  Üst toplama kesilse de kaydedilmiş sonuç ve bildirim tekrar oluşturulmaz.
- `RansomLookWatchChangeEvidence` ayrı modeldir. `notification_id` çalışma
  raporunda isteğe bağlı alandır; eski kurucu ve denetim sözleşmeleri korunur.
- Liste/ayrıntı okuma ağsız ve yazmasızdır; otomatik okundu veya migration
  yapmaz. Ortak sıra, toplam/okunmamış sayıları ve sayfalama diğer bildirim
  türleriyle birlikte çalışır.
- Yeni tablo boş başlar. Açık `./xti migrate` önce benzersiz geri dönüş
  yedeği alır; eski bildirim/okundu bilgileri korunur. Geçmiş sonuçlara
  bildirim eklenmez. Hatalı geçiş geri alınır; restore mevcut dosyanın üzerine
  yazmaz. Şema 58 ve önceki sürümlerin tablo kümeleri değişmez.
- Bu teslim yeni kaynak, ücretli hizmet, otomatik dış gönderim veya bağımsız
  RansomLook monitor komutu eklemez. `collect` içindeki açık seçim desteklenir.

## Doğrulanan kabul kapsamı

Sessiz başlangıç, fark bildirimi, kaynak hatası, tekrar ve yalnız çıkarılma;
bildirim/receipt sınırında rollback, yanlış kaynak bağının reddi, ortak sıra,
okundu işlemi, yedek/restore ve şema 58→59 geçişi testlidir. Çapraz özellik
CLI testi profil toplaması içinde değişen iddia ile bağımsız kaynak hatasını
birleştirir: devam yalnız eksik kaynağı çalıştırır, bildirim ve insan kararı
korunur. Ağ erişimi bu testlerde kapalıdır. Tam sürüm kontrolü ve yayın
ayrıca takip edilir; Linux'ta yapılmayan kontrol yapılmış sayılmaz.

## Aşama 8 — Linux zamanlaması

0.133.0, kayıtlı profil için dosya üretimi ve doğrulanmış yedek/kurtarma
bakımını ekler. Hizmet kendiliğinden etkinleştirilmez; macOS üzerinde gerçek
Linux çalışması yapılmış sayılmaz. Güncel kullanım [Linux rehberinde](../LINUX_SCHEDULING.md),
kesinti ve saklama sözleşmesi [0134 kararında](../decisions/0134-linux-scheduling-and-owned-backups.md) anlatılır.
