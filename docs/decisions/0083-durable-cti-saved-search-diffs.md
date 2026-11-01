# 0083 — Kayıtlı CTI aramaları ve tam fark geçmişi

**Durum:** Kabul edildi · **Tarih:** 30 Ekim 2026 · **Sürüm:** 0.83.0

## Bağlam

Birleşik yerel CTI araması tek anın görünümünü veriyordu. Aynı sorgunun zaman içinde hangi yeni sonucu bulduğunu, hangi kaydın değiştiğini veya artık eşleşmediğini kanıtlayan kalıcı bir çalışma geçmişi yoktu. Yalnız görünen ilk sayfayı saklamak eksik fark üretir; arama ile kayıt yazımını ayrı yapmak da eşzamanlı değişiklikte hangi anlık görüntünün kaydedildiğini belirsiz bırakır.

## Karar

- Sorgu, kapsam ve tür filtreleri adlandırılmış bir tanım olarak saklanır; ekleme, güncelleme, yeniden etkinleştirme ve geri çekme olayları silinmez.
- Çalışma yalnız açık `cti watch-run` komutuyla başlar. Otomatik zamanlayıcı ve ağ çağrısı yoktur.
- SQLite adaptörü `BEGIN IMMEDIATE` ile yazma rezervasyonu aldıktan sonra ayrı salt-okunur bağlantıyla en fazla 50.000 CTI varlığı ve 50.000 IOC kapsamını doğrular. Tam eşleşme kümesi 20.000 sonucu aşıyorsa kesilmiş sonucu çalışma saymadan durur. İlk kapsam sınırı 0.92.0'da [çok kaynaklı IOC kararıyla](0090-bounded-multi-source-ioc-feeds.md) yükseltilmiştir.
- Çalışma başlığı ve bütün güncel sonuçlar ile önceki çalışmada bulunup artık eşleşmeyen öğeler aynı transaction'da yazılır.
- Aynı tanımın doğrudan önceki çalışması varsa kimlik ve durum SHA-256 özetiyle `added`, `updated`, `unchanged`, `removed` ayrılır. Son çalışma başka tanıma aitse taban sıfırlanır.
- Okumalar görünüm limitinden bağımsız bütün tanım, olay, çalışma ve öğe zincirini güvenli üst sınırlarda doğrular; bozulmada kısmi çıktı vermez.

## Şema ve kurtarma

Şema 36; `cti_saved_searches`, `cti_saved_search_events`, `cti_saved_search_runs` ve `cti_saved_search_run_items` tablolarını ekler. Şema 35→36 geçişi önce doğrulanmış yedek alır; tablolar ve sürüm tek transaction'da oluşturulur. Hata geri alınır. Eski arama kullanımından tanım veya çalışma uydurulmaz.

## Sonuçlar

Kullanıcı aynı istihbarat sorusunu tekrarlanabilir biçimde izleyebilir ve değişimi kanıtıyla görebilir. Sonuç durumu, tehdidin doğrulandığı anlamına gelmez. Kişisel ölçekte tam doğrulama güvenilirliği performansın önüne koyar; daha büyük ölçekte aynı port korunarak indeksli adaptör eklenebilir.
