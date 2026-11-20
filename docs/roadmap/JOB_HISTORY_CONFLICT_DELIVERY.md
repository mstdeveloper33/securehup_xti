# İş geçmişi ve kaynak çelişkileri — sabit teslim

20 Kasım 2026. Başlangıç 0.178.0 / çekirdek88 / kuyruk3.
Durum: uygulama ve yerel kabul tamam; Linux teslimi bekleniyor.
Kullanıcının seçtiği 1 ve 3. Hedef 0.179.0 / çekirdek88 / kuyruk4.

1. Ortak profil/kaynak kuyruğunun tamamlanan geçmişini etkin kapasiteden
   ayır. Özgün iş, olay, sonuç, anahtar ve retry bağlarını değiştirme.
   Güncel işlemleri indeksle; geçmişi SQL'de sayfala, bütünlük denetimini
   açık bakım olarak sun. Yeni kuyruk biçimine yedekli açık geçiş ve
   eski üreticiyle geri dönüşü doğrula.
2. Aynı özne/yüklemdeki kayıtlı kaynak kanıtlarını zaman, güncellik ve
   kaynak anlamıyla değerlendir. Karşıt sosyal profil varlık iddiasını,
   farklı profil kimliğini, zaman farkını ve doğrulama eksikliğini ayır.
   CTI etkin/geri çekilmiş durumlarını olumsuz tehdit hükmü sayma.
   Gerekçe/kanıt/tarih CLI, firma JSON ve inceleme önceliğinde görünsün.

Bu teslim çok günlük canlı pilotu, yeni ağ kaynağını, ücretli çağrıyı,
LLM'yi veya tüketici .NET/UI uygulamasını içermez.

Kabul: iki firmada en az 10.000'i aşan tamamlanmış iş geçmişi, aynı
anahtarla eski sonucu okuma, yeni işe devam, kayıtlı retry, platform
sayfalama ve restore. Gerçek platform alt süreç okuma bütçesi p95 ≤5 sn,
tepe RSS ≤128 MiB; ölçüm kapsamı ve bakım süresi ayrıca kaydedilir.
Çelişki kabulü: aynı kaynak tekrarı, tarih farkı, gelecek zaman, eski veya
eksik kanıt, erişim engeli, farklı adres/kapsam, yakın zamanlı karşıt
iddia, firma ayrımı ve eski donmuş incelemenin korunması. Aynı kanıtın
çok kez görülmesi bağımsız doğrulama sayılmaz.

## Uygulanan davranış

- Terminal işler aynı transaction'da arşive ayrılır; özgün satır, anahtar,
  sonuç ve retry korunur. 10.000 sınırı etkin işleredir.
- `source-jobs capacity/history/audit` ve firma `jobs.capacity/history/audit`
  seçili okuma, kesite bağlı sayfalama ve açık tam denetim sağlar.
- `research --conflicts` ve engine/firma `research.conflicts` mevcut
  sınırlı araştırmayı okur. Açık profil varlığı/kimlik ve CTI yaşam döngüsü
  desteklenir; serbest metin yorumlanmaz. İnceleme önceliği v10;
  eski donmuş raporlar özgün politikasıyla okunur.
- Kuyruk3→4 özgün tabloları değiştirmeyen, önce yedek alan geçiştir.
  SQL değişiklik koruması transaction içinde yeniden doğrulanır;
  iki eşzamanlı kabul etkin iş kotasını aşamaz.

## Yerel son kod kabulü

Ortam: macOS26.6.2 arm64, Python3.13.3. İzole sentetik veri, dış istek yok.

| Kontrol | Sonuç |
| --- | --- |
| Kuyruk/çelişki/firma/yedek/öncelik/geçmiş/CI yapılandırması | 173 test, 63,541 sn, başarılı |
| Yayıncı/grup/sosyal/engine/mimari | 45 test, 36,907 sn, başarılı |
| İş kullanım ölçümü/yayıncı iş yürütmesi | 26 test, 14,682 sn, başarılı |
| Kuyruk3 gerçek eski üretici | `d385f59b6012be173576b4aaa4f1c89a4a537095`; 4 iş/19 olay ve rowid'leri korunur |
| Eski sonuç/retry/tekrar/geri dönüş | Başarılı; eski kod4'ü reddeder, önceki yedek3'ü açar |
| Eski inceleme | Gerçek eski kodun ürettiği iki v9 donmuş rapor yeni kodda aynen okunur; çekirdek byte'ları değişmez |
| Daha eski motor geçişi | Gerçek `dbee4ab`: çekirdek75→88, kuyruk2→4 ve eski kodla geri dönüş; 1,717 sn |
| Birikimli kuyruk yükü | İki firma ×50.000 sentetik iptal edilmiş iş; her birine yeni gerçek iş kabul/claim/kesinti eklenir |
| Seçili platform okumaları | 36 alt süreç; p95 **0,396655 sn**, tepe RSS **49.577.984 byte** |
| Saklanan kuyruk dosyaları | 105.336.832 / 105.304.064 byte; firma başına50.001 iş |
| Açık tam audit | 13,5209 / 13,802323 sn; maliyeti toplam geçmişe bağlı |
| Birleşik yedek/restore | 90,696872 sn; eski arşiv ve sonuçlar korunur, yeni workspace çiti üretilir |
| Toplam kapasite/geçiş kabulü | 169,014781 sn, başarılı |

Kaynaklar: `scripts/check-job-history.py`, `scripts/check-engine-upgrade.py`,
`tests/test_job_history.py`, `tests/test_source_conflicts.py`,
`tests/test_job_history_conflict_platform.py` ve ilgili mevcut testler.
Geçici ölçümler `/tmp/xti-0179-job-history-final.json`,
`/tmp/xti-0179-engine-upgrade.json`; kullanıcı DB'si kullanılmadı.
Test keşfi 3.438; bu envanterdir, yerel tam paket koşusu değildir.

İlk denemeler ayrı tutulur: ilk 45 testte yeni guard'ın eski bozma
fixture'ına etkisi ve migration test kancasının yeni imza/sürüm beklentisi
düzeltildi. İlk çapraz özellik çağrısındaki var olmayan test modülü adı
çıkarıldı; son 45 test temiz geçti. Manifest testi yeni kuyruk4'e
güncellendi. İlk 140 ve 77 testlik ara kontroller ile ilk 100.000 geçmiş
kabulü başarılıydı; yukarıdaki ölçümler son değişikliklerden sonradır.

## Linux teslimi

`.github/workflows/job-history.yml` Python3.11/3.13'te aynı eski üretici,
50.000'er geçmiş iş ve ilgili regresyonları çalıştırır. Ortak kuyruk
şeması/platform kabulü değiştiğinden bu sürümde tam Linux paketi bir kez
gerekir; her küçük değişiklikte tam paketi tekrar çalıştırma kuralı yoktur.
Son commit ve koşu bağlantıları sonuç alınınca buraya işlenecek.

## Ölçümün sınırı

Bu yük kontrollü iptal geçmişidir; üretim trafiği veya çok günlük canlı
pilot değildir. Büyük kuyrukta `research.conflicts` boş araştırma kesiti
üzerinden ölçülür; gerçek sosyal kanıt davranışı ayrı entegrasyon ve
alan testleriyle doğrulanır. Tam audit/yedek maliyeti büyümeye devam eder;
arşiv disk silmez. Nmap'in ayrı kuyruğu bu kapsamda değiştirilmedi.
Kaynakta çelişki görülmemesi doğruluk/güvenlik garantisi değildir.
