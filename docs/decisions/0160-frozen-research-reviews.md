# 0160 — Kaynaklı incelemeyi dondurma ve sınırlı değişim geçmişi

- Tarih: 17 Kasım 2026
- Durum: Uygulandı, 0.156.0 / şema 75

## Sorun

Güncel `research.priorities` okuması geçmişte analistin ne gördüğünü
saklamaz. Aynı kökü daha sonra yeniden hesaplayıp önceki sonuç gibi sunmak
zaman, kaynak güncellemesi ve kural değişimini birbirine karıştırır.

## Karar

Küçük `ResearchHistoryRepository` portuna bağlı ayrı uygulama servisi,
mevcut araştırmanın tek okuma kesitinden bütün sınırlı öncelik öğelerini
alır. Domain katmanı saf karşılaştırmayı yapar. Açık `record` işlemi
özgün kanıt kimliklerini, kaynak durumunu, tarihleri, kural gerekçelerini
ve eksik kapsamı şema 75'te eklemeli saklar. Normal araştırma salt okunur.

Normalize kök + sınırlar + güncellik eşiği aynı zinciri seçer. İlk kayıt
ve politika sürümü değişimi başlangıçtır. Görünmeyen öğe çözüldü sayılmaz;
geri çekme aynı assertion'ın açık `revoked` geçişini gerektirir. Değişim
yalnız türetilmiş güncellik/geçerlilik alanlarından geliyorsa `time_only`,
diğer değişimlerde `evidence_or_mixed` denir. Sadece zaman geçmiş olması
başlı başına değişim değildir. URL ilişkileri makbuz kimliğinden bağımsız
yönlü bağla karşılaştırılır, özgün öğe kimlikleri de sonuçta tutulur.

Tekrar anahtarı aynı firma + normalize kapsam için özgün sonucu döndürür.
Kısa yazma transaction'ı önceki kimliği denetler; eşzamanlı kayıtla yarışan
istek sessizce başka başlangıca bağlanmaz. Okuma ve ekleme ayrı işlemlerdir;
özet `checked_at` anındaki kaynak kesitine aittir. Kesilen yazma rollback,
commit sonrası kaybolan yanıt ise idempotent tekrar ile karşılanır.

Kişisel CLI kayıt alabilir. Engine iki salt okuma işlemi sunar; platform
aynı okumaları ve kimlik doğrulaması tüketiciye ait kayıt işlemini sunar.
Platform yazımı güncel `expected_workspace_id` ister; restore sonrası
önceki alan kimliğiyle tekrar bile reddedilir. JSON kapsam seçemez.

## Sonuçlar

- Yedekli açık şema geçişi gerekir; yeni bağımlılık/servis yoktur.
- Bir kayıt en fazla 300 öğe ve 8 MiB gövde, farkı en fazla 4 MiB'dir.
- Liste metadata/ebeveyn bağını, ayrıntı gövde/farkı doğrular. Bütün
  geçmişe ait tek okumalık tarama veya toplam kayıt sayısı kapısı yoktur.
- Tam kaynak kanıtını saklamak disk tüketir. Otomatik saklama süresi,
  zamanlayıcı ve bildirim eklenmedi; tekrar anahtarları silinmez.
- İçerik hash'i yerel bozulmayı yakalar; yetkili makine sahibine karşı
  kurcalanamaz kayıt iddiası yapılmaz.
- Politika değişiminde eski kayıt özgün haliyle okunur; model yükseltmesi
  eski okuyucuyu/karşılaştırıcıyı korumalıdır.

Kabul, zaman/süre dolumu, açık geri çekme, kısmi görünüm, arşiv yenileme,
kalıcı tekrar, yarış/kesinti, bozuk içerik, yedek/restore, şema geçişi,
firmalar arası sınır ve gerçek CLI/protokol testleriyle doğrulanır.
