# Grup işletimi — sabit teslim kapsamı

20 Kasım 2026. Başlangıç: 0.176.0 / çekirdek86 / kuyruk3.
Kullanıcı önerilen ilk iki işi birlikte onayladı.

| İş | Tamamlanma ölçütü | Durum |
| --- | --- | --- |
| Yönetilen grup kontrolü | Saklı, açıkça seçilmiş grup aynı firma/kök kapsamında planlanır. Mevcut kaynak kuyruğu, worker, iptal ve kurtarma kullanılır. Kalıcı kontrol sonrası kuyruk ilerlemesi kesilirse özgün sonuç bulunur. CLI ve firma JSON aynı servisi kullanır. | Uygulandı; yerel kabul geçti |
| Değişiklik bildirimi | İlk kayıt/aynı kanıt sessizdir. Tam kontroldeki üye/dayanak/zaman veya görünürlük farkı tekil inbox kaydı üretir. Kısmi kanıt kaybolma sayılmaz; insan kararı korunur, okundu ayrı kalır. | Uygulandı; yerel kabul geçti |
| Kayıpsız grup arşivi | Eski grup gövdeleri mevcut plan/uygula/geri aç düzeniyle sıkıştırılır. Kimlik, sıra, hash, işlem makbuzu ve donmuş vaka değişmez. Yedek ve arşiv aynı veri alanındadır. Açılmış boyut/satır sınırı korunur. | Uygulandı; yerel kabul geçti |
| Teslim | Gerçek eski kodla geçiş/geri dönüş, firma ayrımı, kuyruk–çekirdek kesintisi, arşiv bozulması ve ilgili regresyon testleri; Linux kabulü ve kullanım belgeleri. | Belgeler/yerel kabul tamam; Linux bekliyor |

Periyodik yürütmeyi güvenilir sunucu zamanlayıcısı veya sınırlı terminal
monitor'ü başlatır. Yeni daemon, .NET/UI, ücretli kaynak, çelişki motoru
ve uzun süreli canlı pilot bu teslimin bitiş koşulu değildir.

Arşiv sıkıştırmadır: 1.000 olay/4 MiB grup ve 10.000 olay/64 MiB çalışma
alanı mantıksal sınırları kendiliğinden büyümez. En güncel grup olayı açık
kalır; eski kayıtlar ve tekrar anahtarları silinmez. Daha büyük veri için
ayrı kapasite tasarımı gerekir; bu çalışmada sınırsız işletim iddiası yoktur.

## Yerel kabul — 20 Kasım 2026

macOS arm64 / Python3.13.3. Sentetik izole alanlar; ağ ve ücretli kaynak
isteği yok. Gruplar gerçek firma/hedef tehdit bulgusu değildir.

| Kontrol | Sonuç |
| --- | --- |
| Son grup işletimi/firma/CLI paketi | 14 test / 13,551 sn; hata/atlama yok |
| Inbox, platform, geçiş, yedek ve engine sözleşmesi | 136 test / 57,611 sn; hata yok, Linux `/proc` gerektiren iki test macOS'ta atlandı |
| Gerçek86 üreticisi →87 | `3f0366d97cef763aec4f899cfe91f8a7f372ecb1` eski koduyla173 tablo/16 satır/rowid korundu; 3,930 sn |
| Arşivli geçmiş ve geri dönüş | Eski grup/insan kararı/vaka/makbuz aynı; arşivli yedek açıldı, gövde geri açıldı, eski yedek86 koduyla okundu; eski kod87'yi reddetti |
| Önceki85 üreticisi →87 / kapasite | İki firma; her birinde100 grup/1.000 olay; 17,951 sn toplam; 172 eski tablo/14 satır korundu |
| Ölçülen okuma yükü | 12 firma JSON okuması; p95 0,9555 sn, tepe RSS62.308.352 byte, toplam firma verisi13.934.875 byte; eşikler5 sn/256 MiB/128 MiB |
| Gerçek süreç ölümü | Core commit sonrası SIGKILL; recovery ve explicit retry özgün olayı/bildirimi buldu; sonraki kontrol ve arşiv makbuzu değiştirmedi |
| Sınırlar | Kısmi veri sessiz; bildirimi yazamama tüm kontrolü geri alır; silinen bildirim sonu/bozuk arşiv hatadır; başka firma reddedilir |

Tekrar üretilebilir kabul betikleri `scripts/check-group-operations.py`
ve `scripts/check-group-delivery.py`; çıktılar yeni, repo dışı JSON dosyası
ister. Kullanım [GROUP_OPERATIONS](../GROUP_OPERATIONS.md), karar
[0182](../decisions/0182-managed-group-checks-and-lossless-history.md).

### İlk denemeler ile son kabul ayrımı

- İlk mevcut82 testlik koşuda altı eski şema/iş modeli/journal sayısı
  beklentisi yeni sürüme güncellendi; bu koşu başarılı sayılmadı.
- İlk10 özellik testinde iki hata vardı: bildirim sunucusuna donmuş
  kanıtın dış grup kimliği geçirilmediği düzeltildi; URL sağlayıcısına
  yanlışlıkla domain veren test fixture'ı düzeltildi. Son14 test geçti.
- Geniş regresyon çağrısında136 gerçek test geçti; olmayan `tests.test_inbox`
  modülü nedeniyle toplam137'lik çağrı hata verdi. Doğru inbox modülleri
  sonraki136 testlik pakette çalıştı; başarısız çağrı tam başarı sayılmadı.
- İlk86 yükseltme betiği, bilinçli arşiv/geri aç audit olaylarını migration
  değişikliği sayıyordu. Son karşılaştırma yalnız bu beklenen iki audit
  olayını ayrıca doğrulayacak şekilde düzeltildi. Migration anında bütün
  eski tablo/sıra karşılaştırması hâlâ tamdır; ikinci koşu geçti.

## GitHub / Linux

Son kodun gönderimi ve otomatik hızlı/tam paket, Python3.11/3.13 grup
kabulü ile firma izolasyonu sonuçları bekliyor. Yerel sonuçlar Linux
kabulü veya uzun süreli canlı hizmet ölçümü yerine geçmez.
