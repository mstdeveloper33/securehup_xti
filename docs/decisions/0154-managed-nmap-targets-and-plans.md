# 0154 — Yönetilen Nmap hedef kapsamları ve değiştirilemez planlar

**Tarih:** 16 Kasım 2026

**Karar:** Kesin IP/CIDR hedefleri sürümlü bir yetki envanterinde tutulacak; tarama ayarları çalıştırmadan önce değiştirilemez bir dry-run planında dondurulacak. Geniş kapsam doğrudan eşzamanlı terminal döngüsüne bağlanmayacak.

## Neden

Tek tek `--address` vermek küçük kontroller için güvenlidir ancak kurumsal kullanımda hedef kümeleri, hariç tutmalar, trafik sınırları ve değişiklik geçmişi gerekir. Ham `--nmap-args` kullanmak motorun güvenlik politikasını geçersiz kılar. CIDR'yi mevcut eşzamanlı komutta hemen çalıştırmak ise ilerleme, iptal, kesinti kurtarması ve kısmi kanıt için kalıcı iş modeli olmadan güvenilir değildir.

## Karar

`surface nmap targets` şu bilgileri sürümlü ve eklemeli geçmişle yönetir:

- kayıtlı ve etkin domain kapsamı;
- adlandırılmış kesin genel IPv4/IPv6 veya kanonik CIDR;
- ana kapsam içindeki kanonik hariç tutmalar;
- gerçek hedef sayısı ve hedef listesinin SHA-256 özeti;
- görünür yetki gerekçesi, sürüm, etkinlik ve zamanlar.

Tek kapsam en çok 4096 adres ve 128 hariç tutma kabul eder. Kapsamdaki her adres genel IP politikasından geçer; özel, yerel, ayrılmış, multicast veya belirsiz adres içeren bütün kapsam reddedilir. Hariç tutmalar kapsamın tamamını kaldıramaz.

`surface nmap plans create` ağ bağlantısı kurmadan hedef kapsamının o anki sürümünü ve şu seçenekleri dondurur:

- yalnız TCP connect ve atlanan host discovery;
- `safe`, `extended`, `full` veya kanonik sayısal `custom` TCP port kapsamı;
- hedef başına süre, azami paket hızı, yeniden deneme ve tarama gecikmesi;
- paralel probe ve host grubu sınırı;
- azami hedef ve toplam `port × hedef × (tekrar + 1)` probe bütçesi;
- geniş port ve 16'dan geniş hedef kapsamı için açık onaylar.

Plan kimliği ve kanonik JSON SHA-256 özetiyle eklemeli saklanır. Aynı hedef sürümü ve aynı seçenekler yeniden verilirse yeni kayıt üretilmez. Plan, bağlı hedef yaşam döngüsü olayına yabancı anahtar ve uygulama düzeyi bütünlük denetimiyle bağlanır. Hedef sonradan güncellense veya geri çekilse eski plan değişmez.

## Güvenlik sınırı

Bu aşama plan oluşturur; CIDR üzerinde Nmap çalıştırmaz. Ham argüman, hostname hedefi, SYN/root, UDP, NSE, `-sV`, banner, işletim sistemi, parola, exploit veya zafiyet taraması eklenmedi. Mevcut `surface nmap check` yalnız en fazla 16 kesin IP ve güncel domain DNS eşleşmesiyle çalışmaya devam eder.

Geniş plan çalıştırması ancak ayrı kalıcı iş/attempt modeli, güvenli worker, ilerleme, iptal, kesinti kurtarması ve hedef başına eklemeli sonuç teslimi tamamlandığında açılacak. Böylece terminal sürecinin kapanması tamamlanmamış geniş çalışmayı başarı gibi gösteremez.

## Veri ve geçiş

Şema 71 üç yeni kayıt alanı ekler: güncel hedef kapsamları, eklemeli hedef olayları ve değiştirilemez planlar. Şema 70→71 geçişi önce doğrulanmış yedek alır; yeni tablolar boş başlar. Mevcut `surface_nmap_checks` kanıtı korunur ve yeni hedef/plan kaydına kendiliğinden bağlanmaz. Eski kanıttan yetki kapsamı veya plan uydurulmaz.
