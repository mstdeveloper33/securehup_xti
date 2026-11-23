# ADR 0195 — Bluesky genel aramasını mevcut içerik yaşam döngüsüne ekleme

**Durum:** Kabul edildi · **Tarih:** 23 Kasım 2026 · **Sürüm:** 0.190.0

## Bağlam

P02 zaten firma/tedarikçi hedefi, kaynak, kanıt, inceleme, değişiklik,
bildirim, vaka, kuyruk, kurtarma ve firma JSON yaşam döngüsünü sağlıyor.
P10 için eksik olan yeni bir izleme motoru değil, hukuken ve teknik olarak
sınırlandırılabilen gerçek bir genel sosyal gönderi kaynağıydı.

## Karar

Bluesky `app.bsky.feed.searchPosts`, `ContentSources` portunun yeni bir
adaptörü olarak eklenir. Adaptör yalnız resmî `public.api.bsky.app` ve
`api.bsky.app` alanlarını kullanır. Donmuş hedef bağları uygulama servisinden
porta verilir; hedef adı/domain/alias sorguları adaptörde bütçeli yürütülür.
Yeni tablo, servis, CLI ailesi veya genel crawler açılmaz.

Yalnız genel gönderi metni, URI ve zamanlar normalleştirilir. Medya, profil,
özel veri, DM ve bütün ağ akışı alınmaz. İlk tamamlanmış sorgu döngüsü sessiz
baseline'dır. Sorgu kapsamı hedef kimlikleriyle hash'lendiği için aynı ada
sahip farklı bir hedef eski baseline'ı devralmaz.

## Sonuçlar

- Mevcut P02 veri bütünlüğü, inceleme ve kurtarma güvenceleri yeniden kullanılır.
- Anahtar, SDK ve yeni Python bağımlılığı yoktur.
- Türkiye'deki önbellekli alan 403 verirse yalnız diğer resmî AppView'e
  failover yapılır; üçüncü taraf proxy eklenmez.
- Arama en güncel sayfalarla sınırlıdır; tam tarihçe veya bütün Bluesky
  kapsaması iddia edilmez.
- Teknik entegrasyon aktiftir; ticari saklama/gösterim ayrı onay bekler.
