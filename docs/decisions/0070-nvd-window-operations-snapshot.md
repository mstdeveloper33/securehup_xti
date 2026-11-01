# ADR 0070 — NVD pencere operasyon anlık görüntüsü

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

Liste, kapsama, ayrıntı ve boşluk komutları ayrı soruları yanıtlıyordu. Kullanıcı bir dönem için veri toplamanın sağlıklı olup olmadığını anlamak üzere birkaç komutun sayılarını zihninde birleştirmek zorundaydı. Ayrı okuma anları arasında bir çalışma ilerlerse bu sonuçlar birbirleriyle tutarsız da görünebilirdi.

## Karar

`vuln nvd-window-operations`, saat dilimli ve en fazla 366 günlük istekle kesişen bütün kalıcı pencere ilerlemelerini tek salt-okunur SQLite transaction'ında okur. Aynı anlık görüntüde ilgili yeniden başlatma olaylarını sayar. En fazla 10.000 kesişen pencere güvenli sınırdır.

Her pencere mevcut doğrulamadan geçirilir ve `complete`, `ready` veya `failed` olarak sınıflandırılır. `ready` ve `failed` birlikte dikkat bekleyen iş sayısını oluşturur fakat ayrı gösterilir. Son güncellenen pencere doğrulanmış UTC `updated_at` zamanı, eşitlikte kimlik sırasıyla seçilir; 1–100 son pencere aynı kuralla listelenir.

Kapsama aynı satır kümesinden hesaplanır; ikinci bir veritabanı okuması yapılmaz. Yalnız tamamlanmış pencereler zaman kapsamına girer. Operasyon durumu şu öncelikle türetilir:

1. en az bir hatalı pencere varsa `attention`;
2. dönem tamamen kapsanmışsa `covered`;
3. hazır pencere varsa `in_progress`;
4. kayıt var fakat açık zaman kalmışsa `gaps`;
5. hiç pencere yoksa `no_activity`.

Komut kaynak adaptörünü çağırmaz, imleç veya hata bilgisini değiştirmez ve onarım yapmaz. Yeni tablo yoktur; şema 31 korunur.

## Sonuçlar

- Kullanıcı pencere sağlığı ve zaman kapsamını tek ekranda, aynı veri anından görür.
- Örtüşen tamamlanmış pencere zamanı kapatsa bile ayrı hatalı çalışma gizlenmez.
- “Hiç çalışma yok” ile “çalışmalar var fakat zaman boşluğu kaldı” ayrılır.
- Bu görünüm kaynak erişiminin şu anda çalıştığını, NVD'nin eksiksiz olduğunu veya zamanlayıcının bulunduğunu kanıtlamaz.
