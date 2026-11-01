# 0088 — Sınırlı ve salt-okunur STIX 2.1 IOC dışa aktarma

## Durum

30 Ekim 2026 tarihinde kabul edildi.

## Bağlam

Yerel katalog domain, IP, URL ve hash IOC'lerini bağımsız kaynak iddialarıyla saklıyordu; fakat kayıtları başka tehdit istihbaratı araçlarının anlayabileceği açık bir standartta paylaşamıyordu. İlk paylaşım diliminin ücretsiz, ağsız, mevcut veriyi değiştirmeyen ve IOC'yi otomatik zararlı saymayan bir sınırda kalması gerekiyor. STIX'in tamamını veya TAXII taşımayı tek adımda ilan etmek, henüz desteklenmeyen varlık, ilişki, işaretleme, içe aktarma ve servis davranışlarını gizlerdi.

## Karar

`cti stix-export DOSYA [--indicator-type ...]`, yalnız dışa aktarma anında en az bir etkin ve geçerli kaynak iddiası bulunan yerel IOC'leri STIX 2.1 Bundle içindeki `Indicator` nesnelerine dönüştürür. Domain, IPv4, IPv6, URL, MD5, SHA-1 ve SHA-256 için kanonik STIX pattern üretilir. Yerel IOC UUID'si kararlı Indicator kimliği olur; oluşturma/güncelleme/geçerlilik zamanları, en yüksek güncel kaynak güveni ve bütün güncel kaynak başvuruları standart alanlarda korunur. `indicator_types` otomatik zararlılık sınıfı uydurmamak için `unknown` kalır ve açıklama kaynak iddiasının hüküm olmadığını belirtir.

Depo en fazla 50.000 güncel IOC ve bunlara bağlı 50.000 kaynak iddiasını tek salt-okunur SQLite anlık görüntüsünde doğrular. İlk 10.000 sınırı 0.92.0'da CERT Polska'nın sınırlı son-ay akışını kapsamak için [çok kaynaklı IOC kararıyla](0090-bounded-multi-source-ioc-feeds.md) yükseltilmiştir. Sınır aşımı, bozuk ana kayıt, bozuk iddia, eksik bağ veya tutarsız zaman bütün çıktıyı durdurur. İsteğe bağlı tür filtresi tam bir IOC türüne uygulanır; sessiz kesme yoktur.

JSON adaptörü `allow_nan=False` ile en fazla 32 MiB UTF-8 çıktı üretir. Hedefin varlığı sembolik bağlantı dahil reddedilir. Veri aynı klasörde `0600` geçici dosyaya yazılır, `fsync` edilir ve üzerine yazmayan atomik bağlantıyla yayımlanır; hata kısmi hedef bırakmaz. Komut internete çıkmaz ve veritabanını yazmaz.

## Sonuçlar

Kullanıcı güncel IOC kataloğunu ücretsiz ve makinece okunabilir standart dosya olarak paylaşabilir. İlk kapsam yalnız IOC Indicator nesneleridir. CTI aktör/kampanya/malware/rapor nesneleri ve ilişkileri, TLP/marking, içe aktarma, geri çekme sürümlerinin alıcıya taşınması, TAXII ve lisans politikası sonraki ayrı kararlardır. Yeni tablo veya migration yoktur; şema 38 korunur.
