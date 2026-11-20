# İlişki grupları ve kaynak değerlendirmesi — teslim kaydı

20 Kasım 2026. Kullanıcı ilk sekiz motor işini, eksik kaynak hata kanıtlarını
ve ticari kaynak/bileşen değerlendirmesini birlikte yetkilendirdi.
Başlangıç: 0.175.0 / çekirdek85 / kuyruk3. Bu kayıt uygulama ile kabulü ayırır.

| İş | Sınır ve tamamlanma ölçütü | Durum |
| --- | --- | --- |
| 1. Araştırma derinliği | Varsayılan iki adım korunur; en fazla dört adım. Düğüm/kenar/yol ve okuma bütçeleri korunur, eksik kapsam açık kalır. | Uygulandı; döngü ve sınır testleri geçti |
| 2. Zamanlı bağlantı | Gerçek gözlem noktaları karşılaştırılır; yakın/farklı dönem/bilinmiyor ayrılır. İlk–son görülme kesintisiz kullanım, belge alınması olay zamanı sayılmaz. | Uygulandı; üç durum sınandı |
| 3. İnceleme grubu | Aynı kayıtlı IP, sunulmuş sertifika veya belge üzerinden açıklanabilir grup. Geçişli ortak saldırgan/kampanya atfı yok. | Uygulandı; üç dayanak sınandı |
| 4. Karar/geçmiş | Dondurulmuş grup kanıtı, gerekçeli karar, tekrar güvenliği, sürüm denetimi ve yeniden kontrol geçmişi. | Uygulandı; değişim/kısmi kontrol/tekrar testleri geçti |
| 5. Yanlış bağlantı | Paylaşımlı altyapı bağlamı, kopya belge ve aynı kanıt tekrarı ayrılır; kaynak sayısıyla güven oylaması yok. | Uygulandı; kopya belge, benzer ad ve geçişli bağ sınandı |
| 6. Akış bağlantısı | Mevcut araştırma, firma incelemesi, vaka, rapor ve kayıtlı yerel takip; CLI ve firma JSON aynı servis. | Uygulandı; gerçek CLI/JSON ve HTML sınandı |
| 7. Kalite/kapasite | Olumlu/olumsuz/belirsiz örnekler; bütçe, firma ayrımı, kesinti ve büyüyen veri için ölçülen kabul. | Yerel kabul geçti; ölçümler aşağıda |
| 8. Teslim | Açık yedekli geçiş, eski kayıt/karar uyumu, kurtarma, ilgili testler ve son kodda genel/Linux kabulü; kullanım belgeleri. | Yerel yükseltme geçti; genel koşu ve son Linux teslimi sürüyor |
| 9. Kaynak hata kanıtı | crt.sh yeni motor ve doğrudan HTTP denemesinde UTC zaman, süre, URL, durum/yanıt özeti; eski raporun eksik HTTP200 kanıtı tarihî kalır. | Tamam; iki HTTP200 yanıtı ayrı kaydedildi |
| 10. Ticari kaynak/bileşen | Kurulu sürümler ve resmî koşullar; sunucumuzdaki hizmet, saklama, müşteriye gösterme ve dağıtım için kaynak bazlı karar. Belgeyle kapanmayan izin, alınmış sayılmaz. | Değerlendirme/kararlar tamam; dış izin bekleyen kaynaklar ticari seçim dışında |

Yeni ücretli çağrı, sağlayıcıya mesaj, Bright Data anahtarı, aktif Nmap
hedefi, .NET/UI, LLM, geniş STIX/TAXII ve ertelenmiş diğer özellikler bu
teslimle açılmaz. Mevcut şahsi veri alanları üzerinde canlı deneme yapılmaz.
Geliştirmede etkilenen testler, paket sonunda bir genel kabul çalışır.
Yeni özellik fikirleri bu on maddelik teslimin bitiş şartını büyütmez.

## Yerel kabul — 20 Kasım 2026

- Son grup ve eski haber/arama geçiş modülleri: **39 test /15,805 sn**, hata yok.
  Grubun boyut nedeniyle elenmesi kalan kanıtı tam kapsam yapmaz; kabul kararı
  engellenir. Yeni grup modülü 21 test içerir.
- Önceki grup/geçiş demeti **42 test /34,977 sn**, araştırma/vaka/HTML
  demeti **74 test /37,900 sn**, kanıt/araştırma/firma demeti **83 test
  /64,258 sn** geçti. Bu demetler örtüşür; toplam benzersiz test sayısı değildir.
- Linux yükseltme denetimi ve workflow kuralları **32 test /14,065 sn**:
  hata yok; Linux'a özel iki kontrol macOS'ta atlandı.
- crt.sh/tanı/keşif durumu paketi **51 test /7,879 sn**, hata yok.
  Gerçek adaptörle kontrollü HTTP200, 429/Retry-After, DNS hatası,
  özel dosya izinleri, sır başlıklarını saklamama ve eski kanıtı koruma
  sınandı. İlk tanı testinin ortam mock'u düzeltildi; üretim kodu değişmedi.
- Son mimari, CI, engine sözleşmesi ve dondurulmuş araştırma geçmişi
  paketi **69 test /30,728 sn**, hata yok.
- İlk yerel genel koşu **3.384 test /1.644,784 sn**: 16 başarısız beklenti,
  bir hata, dört Linux/macOS atlaması. 16 sorun eski şema fixture/DDL
  beklentilerinde, biri eski `max_hops=3` ret beklentisindeydi. Tam koşu
  bu yardımcıları düzeltmeden önce yükledi; sonraki başarılı modüller
  ilk koşuyu temiz yapmaz. Son Linux sonucu ayrıca aşağıya kaydedilir.
- Kurtarma düzeltmesiyle firma/backup/CI/araştırma önceliği paketi
  **69 test /28,729 sn**, hata yok. Üç yeni test gerçek disk taşması ve
  süreç ölümünde çekirdek/kuyruk kurtarmasını; salt okumada değişiklik
  olmamasını ve busy/disabled firma reddini doğrular.
- Genel koşunun son tedarikçi eski-şema beklentilerini içeren modülün
  tamamı **5 test /1,706 sn** ile geçti. Genel koşudaki 17 hata/beklenti
  sorununun bulunduğu bütün modüller düzeltmelerden sonra ayrıca çalıştı.

`scripts/check-group-delivery.py` gerçek `d3fd773` /0.175.0 kodundan
üretilmiş şema85 verisini 86'ya geçirdi. **172 eski tablo, 14 dolu fixture
satırı ve rowid'leri** korundu. Eski kod yeni86'yı reddetti; geçiş öncesi
yedek eski kodda yeni/boş alana geri açıldı. İki firmada toplam 200 grup
ve 2.000 olaylık açıkça sentetik günlük kullanıldı. Gerçek platform JSON
çağrılarıyla sayfalama, firma ayrımı, workspace çiti, yedekten dönüş ve
commit öncesi süreç ölümü sınandı.

| Yerel ölçüm | Sonuç | Baştan belirlenmiş eşik |
| --- | --- | --- |
| 12 JSON okuması p95 | 0,6452 sn | ≤5 sn |
| En yüksek alt süreç RSS | 62.210.048 byte | ≤256 MiB |
| İki firmanın toplam veri boyutu | 13.902.107 byte | ≤128 MiB |
| Kabul betiği süresi | 16,870 sn | İş akışı 15 dakika |

Bu ölçüm kontrollü kapasite kabulüdür; bütün internet doğruluğu veya 7/24
hizmet garantisi değildir. İlk iki betik koşusu denetim/fixture hazırlık
hatasında durdu; üçüncü koşu geçti. Son ölçüm, aşağıdaki disk taşması
eksikliğini de zorlayan `/tmp/xti-0176-group-recovery-2.json` koşusudur.
Önceki yerel ölçüm `/tmp/xti-0176-group-delivery-3.json` içinde ayrı tutuldu;
çalışma veritabanları veya toplanan kaynak gövdeleri repoya konmadı.

## İlk Linux koşusu ve kurtarma düzeltmesi

`c159619` üzerindeki [grup kabulünde](https://github.com/mstdeveloper33/securehup_xti/actions/runs/44716040100)
Python3.11/3.13 işlev testleri geçti; son kapasite/kesinti adımı başarısızdı.
İş günlüğü indirme ucu normal GitHub oturumu olmadan HTTP403 döndü; ayrıntılı
Linux traceback'i elde edilmiş sayılmaz. Sonraki betik hataları check
annotation'a da yazılır; erişim için kimlik bilgisi çıkarılmadı.

Yerelde SQLite cache'i bir sayfaya indirerek gerçek disk taşması zorlandı.
Önce salt-okunur manifest `attempt to write a readonly database`, ardından
platform isteği `storage_error` verdi. Açık `platform recover` da salt-okunur
ön kontrolde duruyordu. Bu kurtarma eksiği giderildi: yalnız açık recover
komutu, mevcut firma kaydı ve kuyruk→çekirdek kilitleriyle iki mevcut veritabanını
yazılabilir açar; SQLite yarım işlemi geri alır. Normal okumalar onarım
yapmaz, iş yeniden çalıştırılmaz. Sonrasında aynı anahtar eski makbuzu
döndürür; olay/rowid/veri manifesti değişmez. Son betik iki firmada bu yolu
gerçekten çalıştırarak geçti; önceki hafızada kalan kesintiyle karıştırılmaz.

Tam CI, sürüm değişimine ek olarak çekirdek şema/araştırma sınırı
değişikliklerinde çalışır. Sıradan özellik düzenlemeleri hızlı paketi
kullanır; her küçük değişiklikte bütün testler tekrar başlatılmaz.

## Kaynak ve ticari karar kapanışı

[crt.sh kanıtı](../SOURCE_EVIDENCE_2026_11_20.md): motor isteği 09:34:25–30
UTC, bağımsız istek 09:34:30–36 UTC; HTTP200, aynı 7.095 byte/hash.
Eski 16 Kasım kesintisinin kesin sebebi bu yeni başarıdan çıkarılmadı.

[Ticari matris](../COMMERCIAL_SOURCE_REVIEW.md): kaynak ve kurulu bileşen
bazında kullanım/saklama/gösterme/dağıtım kararı verildi. Belirsiz izinler
NOTES içindeki N-001/N-002/N-022/N-034/N-039'da ticari seçim dışında kalır.
Bu karar kaydı runtime lisans kilidi veya sağlayıcı onay yazısı değildir.

[Kullanım](../RESEARCH_GROUPS.md), [mimari karar](../decisions/0181-evidence-backed-research-groups.md).
