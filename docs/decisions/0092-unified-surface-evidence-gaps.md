# 0092 — Birleşik dış yüzey kanıt boşlukları

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

Pasif alt alan adı keşfi ile web, e-posta, sınırlı servis ve CNAME kontrolleri ayrı komutlarda görülebiliyordu. `surface exposures` aktif kanıt ailelerinin bazı boşluklarını gösterse de pasif kaynağın çalışıp çalışmadığını aynı yerde göstermiyor ve eksik kanıtı nasıl tamamlayacağını doğrudan söylemiyordu. Sıfır aday sayısı da tamamlanmış boş yanıt, kısmi yanıt ve kaynak kesintisinde aynı görünebilir.

## Karar

- Mevcut `SurfaceFreshnessRepository` anlık görüntüsü son pasif keşif çalışmasını da taşır. SQLite adaptörü kapsamı ve son pasif/web/e-posta/servis/CNAME kayıtlarını tek salt-okunur transaction içinde alır.
- `surface exposures DOMAIN` kapsam sırasını pasif keşif, web, e-posta, sınırlı servis, CNAME ve desteklenmeyen panel kimliği olarak sunar.
- Her aile `current`, `stale`, `partial`, `failed`, `not_checked`, `clock_error` veya `unsupported` durumlarından biri olur. Güncel, ilgilenilmeli ve desteklenmeyen sayıları ayrıca verilir.
- Pasif `complete+0` yalnız crt.sh sorgusunun o yanıtında aday görülmediğini anlatır. `partial+0` boş sonuç sayılmaz; `failed` aday varlığı hakkında hüküm vermez.
- Güncel olmayan veya tamamlanmamış her desteklenen aile çalıştırılabilir tam `next_command` taşır. Etkin aktif kontrol kapsamı yoksa ayrı `scope_next_command` önce gösterilir. Kesin IP yerine konacak `GENEL_IP` kullanıcı tarafından yetkili hedefle değiştirilmelidir.
- Görünüm önerilen komutları çalıştırmaz. Ağ, DNS, hedef bağlantısı, yazma, onarım veya otomatik zamanlama yapmaz.
- Mevcut eklemeli kanıt tabloları kaynak gerçek olarak kalır. Yeni tablo ve migration yoktur; şema 39 korunur. Bozuk son pasif çalışma kısmi görünüm üretmeden güvenli biçimde durur.

## Sonuçlar

Kullanıcı tek ekranda hangi bilginin güncel, hiç alınmamış, eski, eksik veya kaynak hatalı olduğunu ve sıradaki açık terminal adımını görür. Aday olmaması güvenli sonuç sayılmaz; açık panel kimliği veri toplanmadığı için desteklenmeyen olarak kalır. `surface freshness` önceki sabit web/e-posta/servis sözleşmesini korur; geniş birleşik görünüm `surface exposures` içindedir.
