# ADR 0039 — NVD zenginleştirmesi önce çevrimdışı ve sınırlı planlanacak

- **Durum:** Kabul edildi
- **Tarih:** 29 Ekim 2026

## Bağlam

KEV ve EPSS katalogları yüz binlerce CVE içerebilir. NVD'nin anahtarsız API'sine bu kayıtların tamamı için kontrolsüz istek göndermek yavaş, kesintiye açık ve sağlayıcı hız sınırlarına karşı sorumsuz olur. Kullanıcı hangi kayıtların neden seçileceğini ve toplam iş büyüklüğünü ağ işlemi başlamadan görmelidir.

## Karar

`vuln plan`, NVD kaydı olmayan iki yerel kümeyi birleştirir:

- güncel CISA KEV kayıtları;
- kullanıcının `0–1` arasındaki eşiğine eşit veya daha yüksek güncel EPSS kayıtları.

Aynı CVE tek satır olur ve iki seçim nedeni de korunur. Güncel KEV adayları önce, kendi içlerinde EPSS değeri ve CVE kimliğiyle kararlı biçimde sıralanır; sonra yalnız EPSS nedeniyle seçilenler gelir. Sonuç sayısı en fazla 100'dür. Ondalık eşik 18 basamağa kadar tam metin anahtarıyla karşılaştırılır; kayan nokta yuvarlaması kullanılmaz.

Plan tek salt-okunur SQLite transaction içinde üretilir. İnternete bağlanmaz, NVD indirmez, iş kuyruğu oluşturmaz ve veritabanını değiştirmez. Seçilen KEV/EPSS kayıtları mevcut özet kontrolleriyle doğrulanır. Plan yalnız hangi CVE'lerin NVD bağlamının alınabileceğini söyler; kayıtlı varlıklarda ürün, sürüm veya zafiyet bulunduğunu söylemez.

## Sonuçlar

- Kullanıcı toplu ağ işi başlamadan kapsamı ve seçim nedenini görebilir.
- NVD'si zaten bulunan CVE'ler gereksiz yere yeniden planlanmaz.
- Bir sonraki kontrollü yürütme dilimi aynı seçim sözleşmesini kullanabilir.
- Kaynakların tamamını her planlamada yeniden özet doğrulamasından geçirmek yerine yalnız seçilen satırlar doğrulanır; bozuk fakat seçime girmeyen kayıt kaynak kataloğunun kendi okuma/inceleme kontrollerinde ele alınır.
- Şema 19 değişmez; planın kendisi kalıcı kayıt değildir.
