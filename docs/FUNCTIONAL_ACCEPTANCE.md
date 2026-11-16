# Tavily dışındaki işlevlerin kullanım kabulü

16 Kasım 2026. Başlangıç kodu 0.147.0 / `323c974`; kullanımda bulunan
TXT ayrıştırma hatası 0.147.1'de düzeltildi. Çekirdek şema 69 değişmedi.
Denemeler özel geçici kayıt alanlarında yapıldı; kullanıcının mevcut
veritabanı taşınmadı veya değiştirilmedi. Ham kaynak yanıtları, hedef
kanıtları, geçici veritabanları ve özel çalışma raporları repoya eklenmedi.

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
