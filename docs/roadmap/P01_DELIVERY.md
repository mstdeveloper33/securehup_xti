# P01 / A03 — Kod deposu ve paste maruziyeti teslim kaydı

21 Kasım 2026 — **0.180.0: akış uygulandı; paket bütünü tamamlanmadı.**

Kapsam ve kapanış ölçütleri [ana planda](MASTER_ROADMAP.md#6-ilk-önerilen-paket-p01in-somut-teslimi),
uygulama kararı [0185](../decisions/0185-code-and-paste-exposure.md).

| Adım | Durum / kanıt |
| --- | --- |
| Erişim ve araç ön incelemesi | Tamamlandı; erişimsiz kaynaklar açık |
| Kaynaklar, Betterleaks, maskeleme | Uygulandı; sabit Betterleaks 1.10.1 gerçek ikilisiyle ve kaynak fixture'larıyla sınandı |
| Kalıcı sonuç, insan incelemesi, değişiklik/izleme | Uygulandı; aynı içerik tekrar saklanmıyor, yeniden görünme yeni inceleme istiyor |
| Firma JSON, kuruluş raporu, vaka, inbox | Uygulandı; firma çiti, eski kanıt ve karar, atomik fark/bildirim kontrol edildi |
| Kurulum, geçiş, kurtarma, yedek | macOS kurulumu ve gerçek 88 üreticisinden89'a geçiş/geri dönüş geçti; Linux ayrı açık |
| Birikimli kapasite | İki firma ×10.000 aday ×30 tekrar ve 40 platform okuması geçti; aşağıdaki ölçüm |
| Kalite kabulü | Sentetik pozitif/negatif, Unicode, kopya içerik, erişilemeyen kaynak, kota ve tekrar senaryoları; gerçek dünya yüzde doğruluk iddiası yok |
| Tam yerel regresyon | 3.472 test: 3.468 başarılı, 0 hata, Linux'a özgü 4 atlama; bütün test kimlikleri ayrık ve envanterle eşit |
| Canlı kaynak | Kamu GitHub/GitLab sorgusu denendi. Genel kod araması/Pastebin erişimi eksik |
| Linux ve ticari kaynak kararı | CI dosyası hazır; bu çalışma için Linux yürütmesi ve kaynak hakları henüz doğrulanmadı |

Asıl gereksinim **A03**. Bu paket B02'nin kesin içerik tekilleştirmesini,
E01/E05'in kod izleme parçasını, G02/J01/J03'ün vaka/kanıt/insan kararı
akışını ve mevcut H01 firma sınırını kullanır. Bu destek, ilgili 76 maddelik
gereksinimlerin tamamının ayrıca kapatıldığı anlamına gelmez.

## Kullanılan bileşen ve XTI'ın sorumluluğu

[Betterleaks 1.10.1](https://github.com/betterleaks/betterleaks/tree/v1.10.1),
MIT; commit `39d5bdcf34db54e944facac5cf6e8b03db5e2b99`. Sürüm/platform
SHA256'ları sabit. Gitleaks 8.30.1 ile aynı küçük örnek kümesi karşılaştırıldı;
bakımı sürdürülen kurallar ve doğrulama/config seçeneklerinin açıkça
kapatılabilmesi nedeniyle Betterleaks seçildi. İki araçta GitHub/Google/
generic/eşlenmiş AWS örnekleri pozitif, üç temiz örnek negatifti. Tek başına
AWS kimliği iki araçta farklı politika üretir; bu genel doğruluk oranı değildir.

XTI kaynak keşfini, istek/süre/dosya bütçesini, maskeleme sözleşmesini,
kalıcı kanıt/insan kararını, tekrar izlemeyi ve firma bağlantılarını sağlar.
Üçüncü taraf kaynak kodu depoya kopyalanmadı. Native araç stdin ile çalışır;
aktif credential validation, otomatik kaynak config'i, arşiv açma kapalı.
Ham dosya veya eşleşen credential değeri rapor/DB/log'a taşınmaz. Kaynak
URL/depo/dosya/sürüm, içerik SHA256, kural/satır ve maskeleme açıklaması kalır.

## Son canlı deneme — kamu kaynakları

Çalıştırma: `scripts/check-code-live.py --domain securehup.com`.
21 Kasım yerel saat; başlangıç/bitiş UTC zamanları çalışma makbuzunda.
Anahtar yükleyicisi bu betikte özellikle kapalıdır; ücretli çağrı yok.

| Kaynak | Gerçek sonuç | Kapsam anlamı |
| --- | --- | --- |
| GitHub kamu depo keşfi | 9 HTTP denemesi/9 yanıt, son HTTP 200; 5 metin dosyası; 1 marka geçişi | Kaynağa ayrılan 5 dosya bütçesi doldu; 6 büyük/uygun olmayan dosya atlandı; kısmi |
| GitLab kamu proje keşfi | 1 HTTP denemesi/1 yanıt; HTTP 200, boş liste | Yalnız bu kamu proje sorgusu başarılı ve boş |
| GitHub/GitLab genel kod araması | Çalıştırılmadı | Hesap/anahtar yok; fixture canlı kabul yerine geçmez |
| Pastebin | Çalıştırılmadı | Scraping erişimi ve güncel koşullar doğrulanmadı |

Bulunan kayıt: `mstdeveloper33/securehup_xti`, `README.md`,
`securehup.com` terimi, tür `brand_mention`. Kaynak:
[depo](https://github.com/mstdeveloper33/securehup_xti),
[gözlenen değişmez blob](https://api.github.com/repos/mstdeveloper33/securehup_xti/git/blobs/830739fcc32930ed17b5e327f4def86c42d6f986).
Bu bir sızıntı hükmü veya otomatik sahiplik kararı değildir.
Secret adayı 0; tekrar anahtarı aynı makbuzu yeni istek olmadan döndürdü.
Toplam durum **partial**. Dosya bütçesi artırılmadan bütün depo tarandı
denmez; sağlayıcının bütün kod indeksi de bu yöntemle kapsanmaz.

Son kaynak özeti çalışma kodu SHA256:
`41363b9a6e5a2772976e7cd307d7b55343e44459d1f3b1a064e92f5a7914efd0`.
Bu Git commit SHA'sı değildir; `code_acceptance_identity.py` 794 kaynak/
kabul dosyasından üretir. Taban commit `2000b2bc12843b12c44bff72282966d8c00333eb`;
değişiklikler çalışma ağacındadır.

## Geçiş ve birikmiş kullanım kabulü

`scripts/check-code-delivery.py`, gerçek eski commit'ten ayrı Python
üreticisi açar. 177 eski tablo/26 kontrollü satır ve rowid değerleri
korundu; şema 88→89 yükseltildi, yedek eski motorla açıldı, yeni kod
kayıtlarının backup/restore akışı geçti. Bu kişisel üretim verisinin
üzerinde yapılmadı. Şema 89 DDL sonrası kontrollü kesinti ayrıca test edildi;
eski veritabanı değişmedi, iki ayrı kurtarma yedeği korundu.

Son ölçüm: macOS 26.6.2 arm64, Python 3.13.3; yukarıdaki aynı kaynak SHA256.

| Ölçüt | Önceden belirlenen sınır | Ölçülen |
| --- | --- | --- |
| Firma/aday | 2 ayrı firma, her birinde 10.000 | Geçti |
| Kapsam/tekrar | Firma başına 100 depo/dosya kapsamı, 30 değişmeyen tur | Geçti; tur başına 10 sınırlı batch |
| Değişmeyen ek kanıt | 0 yeni gövde | 0 |
| 100 kayıtlık platform okuması | 40 okuma, p95 < 2 sn | 0,176364 sn |
| Ölçülen süreç tepe RSS | < 256 MiB | 108.593.152 byte |
| İki firma toplam DB | < 256 MiB | 68.984.832 byte |
| Ağ isteği | Sentetik yükte 0 | 0 |

Bu depolama ve süreç içi firma JSON ölçümüdür; Betterleaks alt sürecinin
toplam sunucu maliyeti, yüzlerce eşzamanlı müşteri, çok günlük pilot veya
gerçek internet doğruluk oranı ölçülmüş sayılmaz.

## Test kapsamı ve ilk denemeler

Son tam yerel koşu dört ayrık parçayla tamamlandı. Toplam **3.472 test**;
**3.468 başarılı, 0 başarısızlık, 0 hata, 4 atlama**. Parçalar sırasıyla
843 / 841 / 891 / 897 test; süreler 591,058 / 471,565 / 442,200 / 444,363
saniye. Paralel süreler toplam çalışma süresi olarak toplanmaz. Testlerin
kimlik birleşimi `unittest discover` envanterinin tamamına eşittir; aynı
test iki parçada sayılmadı. Dört parçada da motor/kabul kodu değişmedi;
yukarıdaki kaynak SHA256 canlı deneme ve kapasite kabulüyle aynıdır.

Atlananlar gerçek Linux `/proc` süreç sahipliği gerektiren iki yükseltme
kontrolü ve `systemd-analyze` gerektiren iki zamanlama kontrolüdür. Bu
ortamda test edilmeleri Linux kabulü olarak sunulmaz. Yeni kurulu gerçek
Betterleaks ikilisinin pozitif/negatif örnek testi geçti, atlanmadı.
Tüm envanteri normal çalıştırıcıyla yeniden yürütmek için `./scripts/check`
kullanılır; bu kontrol hesap anahtarı veya canlı kaynak taraması istemez.

Yeni paket; marka/secret ayrımı, ham değerlerin kalıcı veriye çıkmaması,
aynı anahtarın ağsız tekrarı, dosya yokluğu ile kaynak kesintisinin ayrımı,
gözlem/karar sürümü, geri gelen içeriğin yeniden incelemesi, sayfalı geçmiş,
firma izolasyonu, donmuş vaka, inbox okunma durumu, süreç çıktısı/süre
sınırları, kaynak kota/iptal/sayfalama ve makbuz sonrası kesintiyi sınar.

Temiz, geçici veri alanında gerçek `./xti` süreçleriyle yedi komut ayrıca
geçti: `init`, `code watch-add`, `code plan`, `engine` üzerinden izleme
okuması, `code report`, `source-jobs init` ve `source-jobs plan`.
Bu ağsız başlangıç kontrolünde aynı izleme kimliği komutlar arasında
korundu; kaynaklar anahtarsız iki kamu kaynağıydı. İlk denemede geçici
kontrol betiği engine zarfını CLI zarfıyla karıştırdı; engine'in mevcut
`status=complete`/`error=null` sözleşmesine göre düzeltilip yeniden geçti.
Ürün sözleşmesi değiştirilmedi.

İlk odaklı çalışmalarda kuruluş raporu bölüm etiketi, bileşen sayısı ve
kaynak işi sürümünü sabit bekleyen testler düzeltildi. İlk kapasite betiği
iki kez kendi yedek alan/ad beklentisinde durdu; gerçek `backup` sonucu
kullanılarak düzeltildi. İlk tam koşuda eski veritabanını taklit eden
fixture'lar yeni vaka CHECK düzenini taşıyordu; gerçek eski düzeni yeniden
kuran yardımcı düzeltildi. Eski içerik silinmesine izin veren guard
gevşetilmedi. Linux yükseltme doğrulayıcısı tam 89 CHECK genişlemesini ve
eski satırların birebir korunmasını kontrol edecek şekilde güncellendi.
İlk tam koşu geliştirmenin son kodunu temiz koşmak için durduruldu;
başarılı tam kabul olarak kaydedilmez. İlk dört parçalı turda eski platform
testinin ağ işlemleri listesine `code.run` eklenmesi gerektiği görüldü.
Ayrıca geçici test betiğindeki eksik `__main__` koruması, macOS `spawn`
alt sürecinin testleri tekrar başlatmasına ve süreç ölüm testinin zaman
sınırını aşmasına neden oldu. Test beklentisi ve geçici betik düzeltildi;
bu iki düzeltme motor kodunu değiştirmedi. Düzeltilmiş dört parçalı tam
koşu yukarıdaki sonuçla geçti; ilk başarısız tur kabul sayılmıyor.

## Açık bağımlılıklar

Ön inceleme (21 Kasım yerel saat): anahtarsız GitHub depo araması HTTP 200,
1 depo; genel kod araması HTTP 401. GitLab proje araması zaman aşımı,
genel kod araması HTTP 401. Pastebin doküman isteği zaman aşımı.
Bu kayıtlar toplama özelliğinin canlı kabulü değildir.

Kullanıcı API erişimi olmadığını belirtti. GitHub kod araması, GitLab genel
kod aramasının hesap/plan kapsamı ve Pastebin scraping erişimi canlı kabul
için açık. Bunlar için kullanıcıdan şimdi hesap açması beklenmiyor.
Kamu kaynaklarıyla yapılabilen iş akışı ve kontrollü adaptör testleri ilerler.
A03 bu kaynaklar yok sayılarak veya fixture canlı sonuç diye sunularak kapanmaz.

Linux/macOS x64/ARM64 için kurulum pinleri hazır; bu ortamda gerçek
macOS arm64 kuruldu. Linux Python 3.11/3.13 için
[CI kabul dosyası](../../.github/workflows/code-exposure.yml) hazırdır;
yürütülmüş GitHub/Linux sonucu henüz yoktur. GitHub'a gönderim bu
çalışmada yapılmadı. Ticari saklama/gösterim kararları [N-044](../../NOTES.md#n-044--p01--a03-kaynak-erişimi-ve-secret-inceleme-aracı)
altında açık; MIT araç lisansı kaynak verisine izin vermez.

Kullanım ve JSON alanları [CODE_EXPOSURE](../CODE_EXPOSURE.md) belgesindedir.
