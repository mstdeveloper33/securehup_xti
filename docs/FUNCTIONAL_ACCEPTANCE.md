# Tavily dışındaki işlevlerin kullanım kabulü

16 Kasım 2026. Başlangıç kodu 0.147.0 / `323c974`; kullanımda bulunan
TXT ayrıştırma hatası 0.147.1'de düzeltildi. Çekirdek şema 69 değişmedi.
Denemeler özel geçici kayıt alanlarında yapıldı; kullanıcının mevcut
veritabanı taşınmadı veya değiştirilmedi. Ham kaynak yanıtları, hedef
kanıtları, geçici veritabanları ve özel çalışma raporları repoya eklenmedi.

## Kullanıcı Linux raporu ve yerel regresyon düzeltmeleri

Kullanıcı 0.147.1 / şema 69 için 50 komut ailesine dokunan gerçek hedef ve
kontrollü örnek veri denemesi bildirdi. Bildirilen 2.603 testte tek hata,
zamanlı yedek testinin `umask 002` altında oluşturduğu geniş klasör izniydi.
Ham VM günlükleri burada doğrulanmadı; bu sonuç sonraki Nmap sürümlerine
ait değildir. [Bulgu değerlendirmesi ve kalan işler](ACCEPTANCE_REVIEW.md).

CTI izleme ekleme/listeleme hatası 10.001 kontrollü IOC ile yeniden
üretildi. Hata bütün ilgisiz kataloğa izleme sınırı uygulanmasıydı.
Düzeltme yalnız kaydedilmiş sonuç başvurularını doğrular; bozuk
entity/indicator bağlantıları ve tutarsız geçmiş hâlâ reddedilir.
Yeni klasör izinleri `000`, `002`, `022`, `077` maskelerinde; eski
geniş izinlerin salt okunur raporlanması ve zamanlı yedek koruması sınandı.
İlgili 44 test `umask 002` ile 12,473 saniyede geçti. Son kodun tam
`./scripts/check` turu da `umask 002` altında 2.665 testi 1.145,005
saniyede tamamladı: 2.661 başarılı, Linux'a özgü dört test macOS'ta
atlandı; hata yok. Ortam macOS 26.6.2 arm64 / Python 3.13.3'tür.
Bu sonuç kullanıcının Linux/Python 3.14 ortamındaki tekrar kabulün veya
gerçek Nmap taramasının yerine geçmez. Kod test turu sırasında değiştirilmedi.

## 0.150.0 yönetilen Nmap kabulü

Kalıcı plan işi, hedef başına ilerleme/kanıt, iptal, kesinti kurtarması ve
firma kapsamlı platform işlemleri eklendi. TCP connect/SYN/UDP, servis/sürüm,
OS ve seçili NSE seçenekleri plan/argv/XML sınırlarında yerel olarak sınandı.
Gerçek CLI, SQLite ve sahte Nmap alt süreçleri kullanıldı; test hedeflerine
ağ paketi gönderilmedi. İş kuyruğu, tekrar anahtarı, kapsam geri çekme,
kayıt alanı ayrımı, bozuk geçmiş reddi ve yedekten iş tekrarı engeli doğrulandı.
Şema 71→72 geçişi yedek alarak eski planları korudu.

Genel `check-fast` turu 1.311 testi 620,678 saniyede tamamladı: 1.307 başarılı,
Linux'a özel dört test macOS'ta atlandı, hata yok. Bu turdan sonraki XML ve
çocuk süreç kapanışı kontrolleri ayrıca hedefli testlerle doğrulandı;
genel tur son küçük değişikliklerden sonra tekrar çalıştırılmış sayılmaz.
Son dosya kümesinde 77 Nmap/platform testi 50,907 saniyede geçti. Bu tur,
iki çıktı akışını kapatıp çalışmaya devam eden çocuk sürecin de iptal
edilebildiğini, süre/çıktı sınırlarını ve UTF-16 DTD geçişinin reddini kapsar.

Bu ortamda gerçek Nmap kurulu değildir. Canlı TCP/SYN/UDP/OS/NSE kabulü,
Linux root çalışma düzeni ve kurumsal yük ölçümü bu yerel sonuçla doğrulanmış
sayılmaz. Kurulum ve kesin yetkili hedefle canlı kabul ayrıca gerekir.
[Seçenekler ve kullanım sınırları](NMAP_MANAGED.md).

## Önceki Nmap teslimleri

0.149.0 / çekirdek şema 71, ağ çalıştırmadan sürümlü genel IP/CIDR hedef
envanteri ve değiştirilemez Nmap dry-run planları ekledi. Kanonik hedef,
hariç tutma, gerçek hedef sayısı/hash, port/hız/süre/retry/gecikme/
paralellik/host-grubu ve toplam probe bütçesi; domain, uygulama, SQLite ve
terminal kabul testleriyle doğrulandı. Bu teslimde geniş CIDR üzerinde canlı
Nmap çalıştırılmadı; kalıcı kuyruk/worker sonraki teslimdir.
Son `check-fast` turu 1.287 testi 540,786 saniyede çalıştırdı; 1.283'ü geçti,
Linux'a özgü dört test macOS'ta atlandı ve hata olmadı. Canlı hedef trafiği
üretilmedi.

0.148.0 / çekirdek şema 70 sonradan ayrı Nmap TCP adaptörünü ekledi. Bu
belgedeki gerçek hedef kabulünde Nmap çalıştırılmadı; kesin yetkili IP olmadan
canlı port taraması yapılmadı. Nmap plan, XML ayrıştırma, DNS engeli, süre
aşımı, terminal, kalıcılık, bozuk kanıt, yedek/restore ve şema 69→70 geçişi
yerel sahte süreç/DNS kanıtlarıyla doğrulandı.
Son `check-fast` turu Nmap testleri dahil 1.278 test çalıştırdı; 1.274'ü
geçti, Linux'a özgü dört test macOS'ta atlandı ve hata olmadı.

## Gerçek internet bağlantıları

Hedef, kullanıcının daha önce yetki verdiği domain ve marka adıydı.
Aktif kontrol yalnız DNS, TLS, HTTPS HEAD, posta DNS ve CNAME kapsamındaydı;
port taraması ve aday sitelerin aktif kontrolü yapılmadı.

| Akış | Sonuç ve doğrulanan kapsam |
|---|---|
| crt.sh marka araması ve alt alan keşfi | Tamamlandı; kaynak kayıtları ve bir alt alan adayı kaydedildi. Sertifika sayısı farklı domain sayısı olarak gösterilmedi. |
| urlscan geçmiş araması | Tamamlandı; yeni tarama gönderilmedi. Sağlayıcının son 30 günlük kapsam notu korundu. |
| DNS / TLS / HTTPS | Tamamlandı; genel adresler, geçerli TLS ve HTTP 200 kaydedildi. Yalnız seçilen ilk genel IP ve HEAD isteği kontrol edildi. |
| MX / SPF / DMARC | İlk turda TXT biçimi hatası; düzeltmeden sonra tamamlandı. Eksik kayıtlar sorgu hatasından ayrı gösterildi. |
| CNAME | Tamamlandı; seçilen kökte CNAME bulunmaması başarılı boş sonuçtu. Kaynak sahiplenme denemesi yapılmadı. |
| Maigret | GitHub ve GitLab için iki doğrulanmamış profil adayı kaydedildi. Sahiplik veya taklit kararı verilmedi. |
| Sherlock | Carrd ve Codeberg sorguları tamamlandı; iki platform `unreported` kaldı. Bu durum hesap yokluğu veya kaynak erişim başarısı diye yorumlanmadı. |
| Common Crawl | `http-504` ile kısmi sonuç; başarılı keşif sayılmadı. |
| Wayback Archive | Zaman aşımı; başarılı boş arama sayılmadı. |

theHarvester kurulu ve çalıştırılabilir olsa da bu iki arşiv sorgusu
sonuç üretemedi. Bir adapterin hata kaydetmesi, dış kaynağın erişilebilir
olduğunu kanıtlamaz. Bu kabul bütün siteleri veya bütün interneti kapsamaz.

Dokuz genel kaynak ayrı geçici alanlarda birer kez yenilendi; 9/9 alım
ve ardından 29/29 yerel durum/liste/ayrıntı okuması başarılı oldu:

| Kaynak | Bu alımdaki katalog hacmi |
|---|---:|
| Feodo | 5 IOC |
| CERT Polska | 19.039 IOC |
| MITRE ATT&CK v20.0 | 26.690 kaynak nesnesi |
| ThreatCluster | 1.224 kamu iddiası |
| RansomLook | 333 kamu iddiası |
| HIBP kamu kataloğu | 1.052 kamu olayı |
| CISA RSS | 10 içerik |
| NCSC RSS | 20 içerik |
| CERT-FR RSS | 40 içerik |

Bu sayılar izlenen firmaya ait bulgu sayıları değildir. HIBP denemesi
e-posta/parola sorgusu; ransomware denemesi doğrudan leak-site/forum erişimi
değildir. MITRE nesnelerinin tümü aynı türde varlık olarak aktarılmaz;
ayrı CTI ve teknik/taktik modelleri kullanılır.

## Birleşik gerçek kullanım

İki IOC, iki ransomware ve kamu olay kaynağı, domain/yüzey kanıtlarının
bulunduğu aynı geçici kayıt alanında ayrıca yenilendi. Kuruluş ve kesin
domain/ad izlemeleri oluşturuldu; 32 komut tamamlandı. Birleşik analiz,
kuruluş raporu, HTML dışa aktarma, kaynak durumu ve olay adayı görünümü
birlikte doğrulandı.

Kontrol edilen beş domain/IP değerinde IOC eşleşmesi, seçilen domain için
HIBP/ransomware eşleşmesi ve kaynaklar arası olay adayı bulunmadı. Bu sonuç
yalnız o andaki kaynak kapsamıdır. Genel kataloğun tamamı firmaya ait
alarm olarak gösterilmedi. Tavily kullanılmadığından firma içerik görünümü
`not_checked` kaldı; RSS haberleri otomatik olarak Tavily kanıtına dönüşmez.

## Yerel iş akışları

Ağ erişimi kapalı çocuk süreçlerle, açıkça sentetik `.example` kayıtları
üzerinde 114 CLI çağrısı yapıldı: 108 başarılı işlem, dört beklenen koruma
reddi, düzeltilerek yeniden verilen iki geçersiz deneme girdisi. 28/28
sonuç kontrolü geçti; bu akışlarda uygulama hatası bulunmadı.

- Varlık/kuruluş/tedarikçi kaydı ve yaşam döngüsü; bağ ve değişiklik geçmişi.
- Vaka, not, görev, kanıt, açık görev varken kapanış reddi, kapanış ve yeniden açma.
- Arama, kayıtlı izleme, sessiz başlangıç, yeni eşleşmede tek bildirim,
  değişmeyen tekrar ve okundu/okunmadı işlemleri.
- İçe aktarımın tekrarında tekilleştirme, insan incelemesi, bulgu ve kuruluş raporları.
- Yerel IOC/CTI kaydı, ilişki ve mevcut sınırlı STIX Indicator çıktısı.
- Profil, toplama planı, durum/depolama görünümü ve zamanlama dosyası üretimi.
- Yeni dizine yedekten dönüş: yedi ailede sekiz tam motor kayıt yanıtı
  önceki yanıtlarla birebir aynı kaldı; mevcut hedefe yazma reddedildi.

Eşleştirme değerlendirmesinde 47 sentetik örneğin mevcut temel sonucu
değişmedi; üç bilinen yanlış pozitif açıkça raporlandı. Bulgu adayı
otomatik doğrulanmış tehdit olarak sunulmaz.

## Bulunan sorun ve düzeltme

Google DNS'in canlı JSON TXT yanıtındaki tırnaksız, SPF dışı kayıt bütün
SPF sorgusunu durduruyordu. 0.147.1 tırnaksız metni aynen korur; tırnaklı
parçaları, bitişik parçalar dahil, ayrıştırır. Eksik tırnak, metin/boyut
sınırı ve geçersiz sayısal kaçışlar kontrollü hata üretir.

Bitişik tırnaklı parça dayanağı [Google JSON API örneği](https://developers.google.com/speed/public-dns/docs/doh/json),
kaçış kuralları [RFC 1035 §5.1](https://www.rfc-editor.org/rfc/rfc1035.html#section-5.1)'dir.
Tırnaksız biçim bu canlı alımda gözlenmiştir; dokümanın bunu zorunlu
tuttuğu iddia edilmez. Testlerde gerçek doğrulama TXT değeri kullanılmadı.
Son kodda ilgili **103 test 21,178 saniyede geçti**. Önceki tam paket ve
Linux kabul kayıtları [STATUS](STATUS.md) içinde ayrıca korunur.

Bu bilgisayardaki eski araç ortamında RSS paketleri eksikti. Desteklenen
`./scripts/setup-brand` eski ortamı koruyarak onardı; `--check` geçti.
Normal `./xti` ile yeni geçici alanda NCSC'den 20 içerik alınabildi.
Kullanıcının eski veritabanına bu işlem bir şema geçişi uygulamadı.

## Canlı doğrulanmış sayılmayanlar

- Kesin yetkili IP verilmediğinden TCP port kontrolü yapılmadı.
- Gerçek dış webhook alıcısı verilmediğinden dış teslim yapılmadı;
  imza/teslim davranışının önceki kontrollü testleri canlı alıcı kabulü değildir.
- Tedarikçi adayını başarıyla kabul etme için gerekli gerçek CNAME kanıtı
  bu hedefte yoktu; boş aday ve geçersiz kimlik reddi denendi.
- Zamanlama dosyaları üretildi; kalıcı hizmet etkinleştirilmedi.
- Firma ayrımı ve platform iş/kurtarma kabulü önceki gerçek Linux
  süreçlerinde geçti; bu turda aynı kapasite testi tekrarlanmadı.
- Tavily, geniş STIX/TAXII, LLM ve aktif plan dışındaki ürün/paket/CVE
  işlevleri bu kullanım denemesinin dışındadır.
