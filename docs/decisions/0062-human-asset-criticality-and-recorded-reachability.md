# ADR 0062 — İnsan beyanlı varlık önemi ve kayıtlı erişilebilirlik bağlamı

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

KEV, EPSS, CVSS, insan maruziyet kararı ve düzeltme takibi teknik zafiyet bağlamını açıklıyordu. Aynı zafiyetin kişisel bir deneme sistemiyle ana üretim hizmetinde aynı sırada değerlendirilmesi ise doğru değildi. İş önemi otomatik keşiften çıkarılamaz. İnternete erişilebilirlik de ürün kaydından veya DNS adının varlığından varsayılamaz.

## Karar

- Kayıtlı varlığa `low`, `medium`, `high` veya `critical` iş önemi yalnız açık kullanıcı komutuyla ve gerekçeyle bağlanır.
- Güncel kayıt ile `set/updated/reactivated/cleared` karar olayları ayrı tutulur; idempotent tekrar yeni olay üretmez.
- İnternet bağlamı yeni bir kullanıcı beyanı değildir. Etkin dış yüzey kapsamındaki son web ve izinli sabit-port servis kanıtından salt okunur olarak hesaplanır.
- Güncel doğrulanmış HTTPS yanıtı veya güncel açık TCP servis kanıtı `confirmed`; yalnız güncel DNS çözümü `dns_only`; güncel kanıtta bunların görülmemesi `not_confirmed` olur.
- Kapsam yokluğu, kontrol edilmemiş durum, eski kanıt, kaldırılmış kapsam ve saat hatası `unknown` altında ayrı nedenlerle gösterilir. `not_confirmed` veya `unknown`, internete kapalı ya da güvenli anlamına gelmez.
- Maruziyet kuyruğu iş önemini ve erişilebilirliği ayrı alan/neden olarak gösterir. Yüksek/kritik önem veya doğrulanmış erişim açık incelemenin çalışma bandını yükseltebilir; insanın `investigating/affected/not_affected/fixed` kararını değiştiremez.
- Kuyruk bütün ilgili maruziyet, kaynak, karar, iş önemi ve son yüzey kanıtlarını tek salt-okunur SQLite transaction anında alır. Ağ isteği veya otomatik kontrol yapmaz.

## Veri ve geçiş

Şema 27, `asset_criticalities` güncel durumunu ve `asset_criticality_events` eklemeli geçmişini ekler. Şema 1–26 yalnız açık `migrate` komutuyla ve geçiş öncesi doğrulanmış yedekle yükseltilir. Yeni tablolar boş başlar; eski varlık, ürün veya zafiyet kayıtlarından iş önemi uydurulmaz.

## Sınırlar

Bu özellik teknik sahiplik, internet genelinde erişim, güvenlik veya zafiyet kanıtı değildir. Kanıt yalnız seçilmiş web kontrolü ve sabit on portluk izinli TCP planını kapsar. CDN, başka IP'ler, UDP, özel ağ görünümü ve kontrol dışındaki zamanlar hakkında hüküm vermez. Dağıtık politika, varlık grubu kalıtımı, müşteri SLA'sı ve otomatik toplu yeniden değerlendirme sonraki dilimlerdir.
