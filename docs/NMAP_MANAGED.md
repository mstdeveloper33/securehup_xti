# Yönetilen Nmap kullanımı

0.150.0 / çekirdek şema 72. Bu akış gerçek Nmap'i ayrı bir süreç olarak
çalıştırır. Plan oluşturmak ve kuyruğa almak yereldir; hedef trafiği yalnız
açık `jobs worker` veya `platform nmap-worker` çağrısıyla başlar.

## Hazırlık

Eski kayıt alanı için `./xti migrate` yedek alarak şema 72'ye geçer.
Nmap ayrı sistem aracıdır: `./scripts/setup-nmap`, ardından
`./xti surface nmap readiness`. Kurulumun hazır olması hedefe ulaşılacağını
veya gelişmiş tarama için sistem yetkisi bulunduğunu kanıtlamaz.

Domain önce `assets add` ve `surface approve` ile kaydedilir. Sonra yalnız
kontrol yetkin olan genel IP veya CIDR kapsamı tanımlanır. Aşağıdaki
`YETKILI_GENEL_IP_VEYA_CIDR`, `PLAN_KIMLIGI` ve `IS_KIMLIGI` yer tutucularını
kendi değerlerinle değiştir. Örnekte gerçek üçüncü taraf tarama hedefi yoktur.

```sh
./xti surface nmap targets save example.com production \
  --network "YETKILI_GENEL_IP_VEYA_CIDR" --reason "Bu adreslerin kontrol yetkisi bizde"

./xti surface nmap plans create example.com --target production \
  --profile custom --ports 22,80,443 \
  --service-detection --version-intensity 2 \
  --script banner --script ssh-hostkey --script ssl-cert \
  --max-rate 25 --max-retries 1 --timeout-seconds 120 \
  --script-timeout-seconds 15 --max-duration-seconds 900

./xti surface nmap jobs submit example.com PLAN_KIMLIGI --request-key kontrol-001
./xti surface nmap jobs worker example.com IS_KIMLIGI
./xti surface nmap jobs show example.com IS_KIMLIGI --limit 20 --offset 0
```

Hedef sayısı varsayılan 16'yı aşıyorsa `--max-targets` ve
`--confirm-range-scan` açık seçilir. Gerekirse `--max-probes` artırılır.
1024'ten geniş port seçimi `--confirm-wide-scan` ister. Hariç tutulacak
adresler hedef kaydında tekrarlanabilen `--exclude` ile verilir.
Kapsam üst sınırı 4096 genel adrestir; özel/yerel ağ taraması bu dış yüzey
sözleşmesinde bulunmaz. IP yetkisi domain DNS eşleşmesinden çıkarılmaz;
ayrı hedef envanterine yazılan yetki gerekçesine dayanır.

## Seçilebilir kontroller

| Seçim | Parametre | Sonuç |
|---|---|---|
| TCP bağlantı taraması | `--scan-type tcp_connect` | TCP port durumları; varsayılan |
| TCP SYN | `--scan-type tcp_syn` | SYN taramasından port durumları |
| UDP | `--scan-type udp --profile custom --ports 53,123` | UDP durumları; `open\|filtered` belirsizliği korunur |
| Servis ve sürüm | `--service-detection --version-intensity 0..9` | Nmap'in servis adı, ürün, sürüm, yöntem ve güven bilgisi |
| İşletim sistemi | `--os-detection` | OS tahminleri ve Nmap eşleşme yüzdeleri; doğrulanmış envanter değildir |
| Açılış metni | `--script banner` | Servisin gönderdiği sınırlı metin |
| SSH anahtarı | `--script ssh-hostkey` | Sunucu anahtarı parmak izi |
| TLS sertifikası | `--script ssl-cert` | Sertifika bilgisi |
| Seçilmiş zafiyet kontrolü | `--script smb-vuln-ms17-010`, TCP 445 seçili olmalı | Nmap'in MS17-010 kontrol çıktısı; istismar veya kesin risk kararı değildir |

SYN, UDP ve OS seçenekleri bu uygulamada etkin kullanıcı kimliği root olan
çalıştırıcı gerektirir. Motor `sudo` başlatmaz ve yetki yoksa başka tarama
türüne sessizce geçmez. İlerideki platform yetkili worker'ı ayrı işletim
süreci olarak sağlar; web uygulamasına root yetkisi verilmesi gerekmez.
Linux capabilities ile root olmayan ayrı bir worker bu sürümde desteklenmez.
Firma alanı sahiplik denetimi de korunur: normal kullanıcıyla hazırlanmış
alan `sudo platform nmap-worker` ile başka kullanıcıya açılamaz. Platformda
yetkili çalışma, kayıt alanı ve motor süreçlerinin işletim kimlikleri
birlikte planlanarak kurulmalıdır. Bu sürüm ayrı kullanıcılar arasında
yetki devreden bir servis sağlamaz; TCP connect normal kullanıcıyla çalışır.

NSE yalnız listelenen adlarla seçilir. `safe`, `vuln`, `all` gibi genel
kategoriler, özel script dosyası, serbest script argümanı, parola denemesi,
exploit, DoS ve ham komut metni kabul edilmez. Bu, XTI uygulama sözleşmesidir.
NSE kodu Nmap içinde çalışır ve ayrıca bir sandbox değildir; kurulu Nmap
paketi ve script dosyaları işletici tarafından güvenilir tutulmalıdır.
[NSE kullanım belgesi](https://nmap.org/book/nse-usage.html).

## Süre, trafik ve sonuçların anlamı

`--max-rate`, port taramasının hız seçeneğidir. Servis, OS ve NSE trafiğinin
tamamına kesin paket/byte kotası koymaz. `port × hedef × (retry+1)` değeri
port taraması için yaklaşık bir bütçedir; ölçülmüş trafik değildir.
[Nmap zamanlama belgesi](https://nmap.org/book/man-performance.html).

Worker bir seferde bir kesin IP çalıştırır. Planın kayıtlı `max-hostgroup`
değeri korunur; bu çalıştırıcının etkin değeri 1'dir. Böylece hedef başına
sonuç, iptal ve tekrar etmeme sınırı nettir. Nmap'in hedef içi probe
paralelliği ayarlanabilir. Toplam süre worker turu başına uygulanır;
açıkça devam ettirilen tur yeni süre penceresi alır.

Sonuçta kesin IP, tarama durumu, port durumlarının tamamının sayıları,
sınırlı port/servis ayrıntıları, OS tahminleri, seçili NSE çıktısı, araç
sürümü ve XML hash'i bulunur. Ham XML/stderr saklanmaz. Bir hedefin ayrıntı
bütçesi toplam hedef sayısına göre önceden ayrılır; iş kanıtı en çok 32 MiB,
tek hedef en çok 256 KiB, 1024 ayrıntılı port, 128 script çıktısı ve çıktı
başına 4096 karakterdir. Ayrıntı sınırında `partial` ve `truncated` görünür;
toplam port durumları korunur. Bu sınırlar kapasite ölçümü yapılmış hizmet
seviyesi veya her portun sınırsız ayrıntısının saklanacağı vaadi değildir.

`open|filtered` açık port değildir. Servis/sürüm ve OS, Nmap gözlemidir;
otomatik CVE eşleştirmesine veya doğrulanmış envantere dönüşmez.
NSE'den saklanan çıktı olmaması kontrolün geçtiği anlamına gelmez: script
uygunluk kuralı, timeout, hata veya çıktı sınırı etkili olabilir.
MS17-010 çıktısı insan incelemesi için saklanır; otomatik exploit, bulgu
kararı veya risk puanı üretilmez.
[UDP durumu](https://nmap.org/book/man-port-scanning-techniques.html),
[MS17-010 kontrolü](https://nmap.org/nsedoc/scripts/smb-vuln-ms17-010.html).

## İlerleme, iptal ve kesinti

Başka terminalden `jobs list` veya `jobs show` tamamlanan ve başlanmamış
hedefleri gösterir. İlerleme hedef düzeyindedir; port başına canlı yüzde yoktur.

```sh
./xti surface nmap jobs cancel example.com IS_KIMLIGI
./xti surface nmap jobs recover example.com IS_KIMLIGI
./xti surface nmap jobs resume example.com IS_KIMLIGI
./xti surface nmap jobs worker example.com IS_KIMLIGI
```

Kuyruktaki iş doğrudan iptal edilir. Çalışan işin iptal isteği kalıcıdır;
worker yaklaşık yarım saniyelik kontrollerle kendi Nmap süreç grubunu
durdurur. Tamamlanmış hedeflerin kanıtı korunur. İşletim sistemi/SQLite
gecikmeleri nedeniyle kesin iptal gecikmesi garantisi verilmez.

Her hedef ağdan önce `target_started` olayıyla ayrılır. SIGTERM/Ctrl-C normal
temizliği tetikler; SIGKILL'de hâlâ yaşayan çocuk süreç ortak kilidi taşır.
Bu çocuk bitmeden başka worker veya recovery çalışamaz. `recover` belirsiz
hedefi `interrupted` kaydeder. `resume` yalnız kesilmiş işte hiç başlanmamış
adresleri kuyruğa alır; belirsiz veya başarısız hedefleri tekrar taramaz.
Tam tekrar istenirse açıkça yeni istek anahtarıyla yeni iş oluşturulur.

Aynı anahtar/plan tekrarında aynı iş döner; başka planla aynı anahtar
reddedilir. Güncellenmiş/geri çekilmiş hedef planı worker öncesinde reddedilir.
Ortak kilit tarama süresince normal hedef güncellemelerini engeller;
önce işi iptal edip ardından kapsamı değiştir. Yedekten yeni kayıt yoluna
taşınmış kuyruk otomatik tekrar çalıştırılamaz; eski kanıt okunabilir.

## Arayüz ve platform bağlantısı

`./xti --json surface nmap capabilities` ağsız seçenek kataloğudur.
Bütün terminal komutlarında mevcut `--json` zarfı desteklenir.
Firma kapsamlı `xti-platform` v1 ayrıca şu işlemleri sunar:

- `nmap.capabilities`, `nmap.targets.list`
- `nmap.plans.create`, `nmap.plans.show`
- `nmap.jobs.submit`, `nmap.jobs.list`, `nmap.jobs.status`, `nmap.jobs.result`
- `nmap.jobs.cancel`, `nmap.jobs.resume`

Firma seçimi güvenilen başlatıcıdadır; JSON dosya yolu/firma değiştiremez.
Plan oluşturma, iş kabulü ve devam `expected_workspace_id` ister.
Hedef envanteri ve domain yetkisi işletici tarafından önceden hazırlanır.
İstek yolu ağ çalıştırmaz; açık `platform nmap-worker` ayrı çalışır.
[Platform örneği](PLATFORM_ENGINE.md#nmap-işleri-ve-arayüz-seçenekleri).

Yerel sahte süreç/XML ve SQLite kabulü canlı Nmap/UDP/SYN/OS kabulü değildir.
Canlı deneme için Nmap kurulumu, kesin yetkili hedef ve uygun işletim
yetkileri ayrıca gerekir. .NET/React bağlantısı tüketici ekibin işidir.
