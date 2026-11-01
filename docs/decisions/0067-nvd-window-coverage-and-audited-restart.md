# ADR 0067 — NVD pencere kapsamı ve denetlenebilir yeniden başlatma

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

Tek bir tarih penceresinin planı kaldığı sırayı gösterebiliyordu; kullanıcı bütün pencereleri hatırlamadan hangi dönemlerin tamamlandığını veya açık kaldığını göremiyordu. Ayrıca NVD'nin toplam sonuç sayısı sayfalar arasında değişirse güvenli davranış ilerlemeyi durduruyordu fakat aynı tam pencereyi baştan almak için SQL kullanmadan, eski kanıtı silmeyen açık bir yol yoktu.

Bir pencerenin birkaç sayfasının başarıyla alınmış olması bütün zaman aralığının kapsandığı anlamına gelmez. Benzer biçimde imleci sessizce sıfırlamak kaynak geçmişini ve operasyon kararını açıklanamaz hâle getirir.

## Karar

`vuln nvd-window-list` kalıcı pencereleri türetilmiş `ready/failed/complete` durumuyla listeler. `failed`, ilerleme satırının son kaynak hatasını taşımasıdır; ayrı ve yanıltıcı bir tamamlanma durumu değildir. `show`, tam başlangıç+bitiş+sayfa boyutu kimliğini ve yeniden başlatma olaylarını tek salt-okunur anlık görüntüde verir.

`vuln nvd-window-coverage` kullanıcının saat dilimli, en fazla 366 günlük inceleme aralığını alır. Yalnız `complete` pencereler kapsama aralığına katılır. Örtüşen veya uç uca gelen tamamlanmış aralıklar birleştirilir; istenen dönemle kesişen `ready/failed` pencereler ayrı sayılır. Birleşik tamamlanmış aralıkların dışında kalan süreler boşluk olarak gösterilir. Bu sonuç kaynak veya içerik kalitesi değil, yerel sayfalama tamamlanma kanıtıdır.

`vuln nvd-window-restart` yalnız var olan tam pencere kimliği ve 5–500 karakterlik açık gerekçeyle çalışır. Yerel çalıştırma kilidinden sonra yazma transaction'ı içinde:

1. güncel ilerleme yeniden okunur ve doğrulanır;
2. önceki sıra, toplam, hazır/tamamlanmış durum, son başarı, son hata ve son kaynak çalışma bağı eklemeli olaya yazılır;
3. imleç sıfıra, toplam bilinmeyene ve durum hazır hâline getirilir;
4. güncel başarı/hata bağı temizlenir.

CVE ana kayıtları, NVD değişiklik olayları ve `vulnerability_source_runs` silinmez veya değiştirilmez. Yeniden alınan aynı CVE değişmediyse yeni NVD değişiklik olayı oluşmaz; kaynak çalışması ve son görülme zamanı yine yeni alımı gösterir. Saat son pencere güncellemesinden gerideyse olay zamanı uydurmak yerine işlem reddedilir.

Şema 31 `nvd_window_restart_events` tablosunu ekler. Şema 30→31 geçişi mevcut pencere ilerlemesini olduğu gibi korur ve olay tablosunu boş oluşturur.

## Sonuçlar

- Kullanıcı SQL bilmeden tamamlanmış dönemleri ve gerçek toplama boşluklarını görebilir.
- Kısmen alınmış pencere yanlışlıkla kapsanmış görünmez.
- Kaynak sayfalaması değiştiğinde eski CVE ve çalışma kanıtını silmeden baştan doğrulama yapılabilir.
- Yeniden başlatılan tamamlanmış pencere, bütün sayfalar tekrar bitene kadar kapsamada boşluk oluşturur; bu bilinçli ve görünür bir güvenlik tercihidir.
- Komut yeni ağ isteği göndermez, insan maruziyet kararını değiştirmez ve otomatik tekrar başlatmaz.
- Takvim tabanlı otomatik pencere üretimi, boşluk doldurma işi ve arka plan zamanlayıcısı hâlâ ayrı bir sonraki karardır.
