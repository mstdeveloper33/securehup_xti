# 0150 — Bütçeli kuruluş/tedarikçi izleme ve mevcut inbox bağlantısı

Tarih: 15 Kasım 2026. Durum: uygulandı, 0.145.0 / şema 68.

Kullanıcı, seçilen kuruluş ve tedarikçileri bir kez tanımlayıp sorgu sınırı
ve aralıkla toplamak, yeni/değişen içerikleri mevcut kutuda görmek istedi.
Tekil Tavily kaynağı ve bağımlılıkları değiştirilmedi.

Mevcut collection profile sözleşmesi tek domain ve sabit kaynak görevlerine
bağlıdır. Yeni grup tanımı bu eski kanıta zorla eklenmez. Küçük grup
portu/servisi, ortak yazıcı kilidi, mevcut MentionRequest ve Tavily adaptörü,
kanıt deposu, doğrulanmış yedek ve systemd dosya üretim yardımcılarını kullanır.

Şema 68'de eklemeli grup olayları tanımı, dondurulmuş hedefleri, HTTP öncesi
rezervasyonları ve sonuç/bildirim bağlantılarını tutar. Güncel görünüm
geçmişten denetlenir. Sorgu bütçesi grup kimliği ve UTC gününe aittir;
tanım değişikliği ve yeniden etkinleştirme tüketimi sıfırlamaz. Kaynak
sonucu ve grup bağlantısı aynı SQLite işlemindedir. Kesilmiş rezervasyon
bilinmeyen sonuçtur, yeniden kaynak çağrısı izni değildir. Açık kalan
çalışma yeni turu engeller; devam işlemi yalnız güvenli aşamaları yürütür.

Bildirim için ikinci altyapı kurulmaz. Kayıtlı genel aramaya opsiyonel
kesin mention request-key kapsamı eklenir; eski v1 tanım JSON/hash ve
somut tür seçimi korunur. Yeni kapsam v2 tanımdır. Köprü source run'ın
tarihî kesitini doğrular; aynı işlemde izleme, fark, mevcut inbox bildirimi
ve idempotent işlem bağını yazar. Tekrarda aynı donmuş sonuç döner.
Grup receipt'i kesilse bile ikinci kaynak isteği veya bildirim oluşmaz.

İlk başarılı kapsam sessiz başlangıçtır. Hata/unknown kapsamı izleme
çalıştırmaz; başarılı boş yanıt geçmişi silmez. İşlem kimliği başka
grup/kapsam/kaynak kanıtıyla tekrar kullanılamaz. Anahtar uygulama
tanımı/veritabanı/zamanlayıcı dosyasına yazılmaz; özel dosya yolu ayrıdır.

Zamanlama ve sınırlı ön plan monitor'ü aynı uygulama servisinin bütçe/aralık
kurallarını kullanır. Zamanlayıcı üretilir, otomatik etkinleştirilmez.
Kaynak hatasında kalan HTTP çağrıları atlanır. Bu sınırlı kişisel veri
alanı bütçesidir; sağlayıcı hesabı toplam harcaması veya 7/24 hizmet
garantisi değildir. RSS, .NET, müşteri yetkisi ve LLM kapsamı değişmez.

[Kullanım](../MENTION_GROUPS.md), [önceki Tavily kararı](0149-tavily-company-mentions.md).
