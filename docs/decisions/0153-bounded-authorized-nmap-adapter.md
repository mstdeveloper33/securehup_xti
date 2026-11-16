# 0153 — Sınırlandırılmış ve yetkili Nmap TCP adaptörü

**Tarih:** 16 Kasım 2026

**Karar:** Mevcut sabit 10 portluk yerleşik kontrol korunacak; Nmap ayrı bir aktif kanıt sağlayıcısı, ayrı kayıt tablosu ve açık kaynak sınırlarıyla eklenecek.

## Neden

Yerleşik TCP bağlantı kontrolü bağımlılıksız ve düşük trafiklidir; fakat profesyonel dış saldırı yüzeyi çalışmasında seçilebilir port kapsamı, süreç süresi ve trafik temposu gerekir. Nmap bu işi olgun bir tarama motoruyla yapabilir. Buna karşılık domain onayı tek başına CDN veya paylaşımlı IP üzerindeki geniş taramayı yetkili hale getirmez. Ham Nmap argümanı kabul etmek de XTI'nin güvenlik sınırlarını etkisiz bırakır.

## Karar

`surface nmap check` yalnız şu koşullarda çalışır:

- domain kayıtlı ve etkin dış yüzey kapsamındadır;
- kullanıcı her kesin genel IPv4/IPv6 adresini ayrı `--address` ile verir;
- görünür bir yetki gerekçesi bulunur;
- her IP güncel Google Public DNS A/AAAA cevabında yer alır;
- DNS cevabındaki bütün adresler genel IP'dir;
- yerel Nmap sürümü desteklenen 7.x ailesindedir.

Adaptör yalnız `-sT -Pn -n --unprivileged` kullanır. SYN/root taraması, UDP, NSE, işletim sistemi keşfi, traceroute, `-sV`, banner veya kullanıcıdan ham argüman yoktur. Alt süreç `shell=False` eşdeğeri argüman listesiyle, kapalı standart girişle ve kesin süreç süresiyle çalışır. XML 16 MiB ile sınırlanır; DTD/entity reddedilir; hedef IP, protokol, sayaçlar ve içerik biçimi doğrulanır. Ham XML saklanmaz, SHA-256 özeti saklanır.

## Ayarlanabilir sınırlar

- `--timeout-seconds`: hedef başına 10–3600 saniye;
- `--max-rate`: 1–1000 paket/saniye; kesin byte kotası değildir;
- `--max-retries`: 0–3;
- `--target-limit`: tek komutta 1–16 kesin IP;
- `--max-probes`: `port × hedef × (yeniden deneme + 1)` için plan kabul sınırı;
- `safe`, `extended`, `full`, `custom` port profilleri.

1024 porttan geniş kapsam `--confirm-wide-scan`, birden fazla IP `--confirm-multi-target` olmadan reddedilir. IP/CIDR aralığı ve hostname hedefi kabul edilmez. `full` profil 1–65535 TCP portudur; varsayılan değildir.

## Kanıt ve veri ayrımı

Her kesin IP ayrı `surface_nmap_checks` kaydıdır; aynı terminal çalışmasının kayıtları ortak `execution_id` taşır. Plan, bütün sınırlar, Nmap sürümü, DNS kanıtı, açık portlar, açık/kapalı/belirsiz toplamları, zamanlar ve XML özeti eklemeli saklanır. En çok 4096 açık port ayrıntısı tutulur; kesilme görünür kısmi sonuçtur.

Nmap kanıtı mevcut `surface_service_checks` tablosuna yazılmaz. Böylece geniş tarama, mevcut dış yüzey görünümü, teknoloji ipucu, bildirim ve zafiyet akışına kendiliğinden ürün/risk kararı olarak karışmaz. Bu ilişkiler ileride ayrı, kanıta dayalı bir kararla eklenebilir.

Şema 69→70 geçişi doğrulanmış yedek aldıktan sonra boş Nmap tablosunu oluşturur. Eski kanıtlardan Nmap sonucu uydurulmaz. Yedek/restore yeni tabloyu SQLite anlık görüntüsüyle birlikte taşır.

## Kurulum ve açık sınırlar

Nmap bir Python paketi değil, işletim sistemi aracıdır. `./scripts/setup-nmap` macOS'ta Homebrew; Linux'ta desteklenen sistem paket yöneticisi üzerinden açık kullanıcı çağrısıyla kurar. `./scripts/setup-nmap --check` ve `./xti surface nmap readiness` kurulum kontrolüdür. XTI Nmap'i repoya kopyalamaz veya gizlice kurmaz.

Paket hızı ağda kesin byte veya paket sayısı garantisi değildir. İşletim sistemi TCP davranışı, filtreler ve ağ kayıpları gerçek trafiği etkiler. Açık port yalnız tarama anındaki TCP erişilebilirlik kanıtıdır; çalışan ürün, sürüm, CVE, sahiplik veya güvenlik açığı değildir. Masscan, UDP ve banner/sürüm toplama bu kararla uygulanmış sayılmaz.
