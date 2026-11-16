# 0155 — Yönetilen Nmap işleri ve tipli gelişmiş seçenekler

16 Kasım 2026 · 0.150.0 · çekirdek şema 72.

Kullanıcı hedefi, ileride arayüzden özelleştirilebilen Nmap çalıştırmasıdır.
`NmapExecutionService` küçük depo/çalıştırıcı portlarıyla aynı iş akışını
terminal ve firma kapsamlı platform girişinde sunar. Kimlik doğrulama ve
UI tüketici platforma aittir. Ağ işlemi yalnız açık worker'da başlar.

V1 plan JSON/hash'i aynen korunur. Gelişmiş seçenekler V2 plan tanımına
eklenir: TCP connect/SYN/UDP, servis/sürüm yoğunluğu, OS tahmini, incelenmiş
NSE adları, script süresi ve worker turunun süre sınırı. Root gerektiren
işler sistem yetkisi yoksa reddedilir; motor yetki yükseltmez.

Ham argümanlar uygulamanın hedef, dosya, ağ ve script sınırlarını aşabildiği
için sözleşmeye girmez. Kullanıcı özelleştirmesi tanımlı alanlarla yapılır.
Seçili NSE kataloğu banner, ssh-hostkey, ssl-cert ve smb-vuln-ms17-010'dur.
Sonuncu yalnız seçili TCP 445'e bağlı, yanıt temelli bir kontroldür.
Kategori ifadeleri, harici script, kullanıcı script argümanı, brute-force,
exploit ve DoS iş akışı yoktur. Kurulu sistem Nmap paketine güvenilir;
NSE için ek sandbox veya tüm geçişli script kodunun pinlenmesi iddia edilmez.
Resmî açıklama/kaynak incelemesi:
[NSE](https://nmap.org/book/nse-usage.html),
[MS17-010 kaynak kodu](https://svn.nmap.org/nmap/scripts/smb-vuln-ms17-010.nse).

Şema 72 iki boş tablo ekler. İstek anahtarı domain içinde tekildir; plan,
istek ve kayıt yolu bağı ilk olay hash'ine girer. Olay sayacı ve son hash
kuyruk durumunu doğrular. Her hedef başlangıcı ağdan önce commit edilir;
sonuç ve ilerleme aynı olayda commit edilir. İptal ortak worker kilidini
beklemeden kısa SQLite işlemiyle kaydedilir. Diğer bütün çalışma/yeniden
başlatma yolları ortak kilidi alır; child descriptor'ı devralır.

Worker yalnız bir hedef süreci çalıştırır; `max-hostgroup` etkin 1 olarak
sunulur. Süre, stdout/stderr byte sınırı, süreç grubu temizliği, temiz
çalışma dizini/ortam ve dış varlıksız XML ayrıştırması uygulanır.
`--max-rate` ve hesaplanan probe bütçesi tüm ek trafik için kesin kota
olarak sunulmaz. Veri saklama sınırı plan hedef sayısından önce ayrılır;
kesilen ayrıntı `partial` olur. UDP belirsizliği ve OS/servis iddiaları
aynen kaynak türleriyle kalır; otomatik risk veya CVE kararı yoktur.

Kesinti belirsizliği tekrar izni değildir. `recover` ağ kullanmaz;
`resume` yalnız hiç başlanmamış adresleri seçer. Yeni yola restore edilmiş
işler yol bağıyla tekrar çalıştırılamaz. Yönetici dosyaları doğrudan
değiştirirse güvenlik yalıtımı iddiası yoktur. Çok makineye dağıtık worker,
root olmayan Linux capabilities, özel ağ hedefleri, canlı port yüzdesi ve
yüksek hacim hizmet seviyesi bu teslimin dışında kalır.

71→72 açık geçiş önce yedek alır. Önceki plan/sonuç byte'ları değiştirilmez.
Eski sürüm numarası altında yeni tablolarda veri varsa geçiş reddedilir.
Kullanım ve kabul sınırları [Nmap rehberinde](../NMAP_MANAGED.md) açıklanır.
