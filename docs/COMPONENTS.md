# Bağlı açık kaynak araçlarını görme

**Uygulama:** 0.140.3 · **Bileşen kataloğu:** 1 · **Şema:** 64.

`components`, XTI'ın bağlı olduğu Maigret, Sherlock ve theHarvester için
beklenen sürümü, kullanım kapsamını ve bu projedeki kurulum durumunu gösterir:

```sh
./xti components
./xti --json components
```

Bu komut internete çıkmaz, araç çalıştırmaz veya kurulum başlatmaz.
Veritabanı kurulmamışken de kullanılabilir; kayıt dizini oluşturmaz.
İnternetten yeni bilgi toplamak için mevcut toplama komutları kullanılır.
Proje başlatıcısı çalışan Python ortamını korumak için ilk çağrıda kalıcı
`.brand-install.lock` dosyasını oluşturabilir; bu bir araç kurulumu değildir.

## Gösterilen araçlar

| Araç | XTI'daki görevi | Sabitlenen sürüm | Çalışma ortamı |
|---|---|---|---|
| Maigret | Seçili platformlarda herkese açık kullanıcı adı profili adayları | 0.6.6 / `b8747b98820f…` | Proje `.venv`, Python 3.11+ |
| Sherlock | Seçili platformlarda herkese açık kullanıcı adı profili adayları | 0.16.2 / `a38ba54fda79…` | Proje `.venv`, Python 3.11+ |
| theHarvester | Common Crawl ve Wayback arşivlerinden alt alan adı adayları | `6790b147f523…` commit'i | Ayrı `.tools/theharvester/.venv`, Python 3.14+ |

Tam commit, depo, lisans başvurusu ve bağlantı profili çıktıda bulunur.
Sosyal araçların `safe` ve `extended` platformları JSON'da adlarıyla yer alır;
özel seçim geniş profilin alt kümesidir. İstek süresi varsayılan 10, izinli
aralık 5–30 saniyedir. theHarvester sonucu varsayılan 250, en fazla 500
kayıttır; bu entegrasyon aktif hedef kontrolü yapmaz.

Bu liste yalnız mevcut üç harici araçtır. Bütün veri kaynakları, Python
paketleri veya ileride düşünülen RapidFuzz/feedparser gibi bileşenler için
kurulum envanteri değildir. Kayıt alanı hazırken `./xti sources` kaynak
listesini, kayıtlı son arama sonuçlarını ve bekleme bilgilerini gösterir.

## Kurulum durumunu nasıl okuyacağım?

| JSON durumu | Terminal karşılığı | Anlamı |
|---|---|---|
| `ready` | Kurulum bilgileri uyumlu | Bu proje için uygulanan yerel kurulum kontrolleri geçti |
| `missing` | Kurulu değil | Beklenen kurulum bulunamadı |
| `invalid` | Kurulum bilgileri geçersiz | Bulunan kurulumun incelenen bilgileri kabul edilmedi; açıklama gösterilir |

`expected` beklenen kimliktir; gözlenen sürüm gibi sunulmaz.
`installation.verification="metadata_only"` ve `execution_tested=false`
bu okumanın aracı çalıştırmadığını belirtir. `inspection_checks`, denetimin
kapsamıdır; her denetim için ayrı başarılı sonuç listesi değildir. Örneğin
eksik kurulumda sonraki kontrollerin tümü yürütülmez.

Maigret ve Sherlock için proje `.venv` içindeki paket sürümü, Git kaynak
kaydı, katalog boyutu/özeti ve çalıştırıcı dosyaları incelenir. `XTI_PYTHON`
veya `PATH` ile seçilmiş başka bir ortam bu gözlemle doğrulanmış olmaz.
Yarım marka kurulumu veya tanınmayan eski kurulum kalıntısı `invalid`
olarak görünür. Aktif marka kurulumu varsa `./xti` başlatıcısı görünüm
oluşmadan meşgul hatasıyla durabilir; bu durum kayıtların silindiği anlamına gelmez.
theHarvester denetimi yarım kurulum günlüğü, varsa kurulum kilidi, HEAD
işareti ile çalıştırıcı/interpreter konumunu inceler; bütün kaynak ağacının
veya bağımlılıkların bütünlüğünü kanıtlamaz. Bekleyen kurtarma veya meşgul
kurulum `invalid` açıklamasıyla görünür. Bu okuma kilit dosyası oluşturmaz.

Kurulumun uygun görünmesi kaynağın internette çalıştığı anlamına gelmez.
Son deneme, kaynak hatası ve saklanan verinin güncelliği için
`./xti sources status --details` kullanılır. Araç eksik olsa bile önceki
kanıtlar okunabilir. Eşzamanlı kurulum değişirken bütün araçları kapsayan
tek anlık kesit garantisi yoktur.

Çıktıdaki kurulum ve doğrulama komutları yalnız yol gösterir. Maigret ve
Sherlock için ayrı `./scripts/setup-brand --check` kontrolü vardır.
[Marka kurulum rehberi](BRAND_INSTALLATION.md) yeniden kurulum, kurtarma
ve çalışan XTI komutlarının korunmasını açıklar.
theHarvester için `./scripts/setup-harvester --check` Git kaynağını,
commit'i, izlenen yerel değişiklikleri ve `--help` çalışmasını kontrol eder.
Bu ayrı komut aracı çalıştırır; tüm bağımlılık bütünlüğünü veya canlı arşiv
erişimini kanıtlamaz. Katalog kurulumu onarmaz veya otomatik güncellemez.
[Kurulum ve kurtarma rehberi](HARVESTER_INSTALLATION.md).

## Başka uygulamadan okuma

Engine sözleşmesi v1, aynı kataloğu `components.list` işlemiyle sunar:

```sh
./xti engine <<'JSON'
{
  "contract_version": 1,
  "request_id": "araclar-1",
  "operation": "components.list",
  "parameters": {}
}
JSON
```

Parametre nesnesi boş olmalıdır. İşlem `--data-dir` ile seçilen kanıt alanı
yerine çalışan proje kurulumunu inceler. Ortak engine zarfının `data`
alanında `catalog_version`, `observed_at`, `scope`, `components` ve `notes`
bulunur. Katalog kapsamı `project-managed-tools` değeridir.
`source_status_ids` ilgili kaynak durumu kimliklerine bağlar; canlı sorgu
çalıştırmaz. Eski engine işlemlerinin biçimi ve sözleşme sürümü korunur.
[Engine rehberi](ENGINE_CONTRACT.md) hata ve taşıma sınırlarını açıklar.

## Yeni araç eklerken veya sürüm yükseltirken

1. Sağladığı somut katkıyı, kullanılacak işlevleri, lisansı ve çalışma
   ortamını belirle; araç sonuçlarını mevcut kaynak/kanıt modeline bağla.
2. İncelenen sürüm, commit ve varsa katalog özetini ortak
   `domain/component_pins.py` kaydına ekle. Kapsamı uygulama servisinde açık
   tanımla; tanımsız bir bileşen başka aracın ayarlarını devralmaz.
3. Küçük adaptörü ve yerel kurulum denetimini ekle; araç eksikken eski
   kanıtın okunmasını koru. CLI/engine alanlarında beklenen değer ile
   gözlenen durumu ayır.
4. Paketleme ve bağımsız kurulum/işçi dosyalarındaki zorunlu sabitleri
   güncelle; ortak kayıtla uyuşmalarını test et. Mevcut tekrarlar otomatik
   üretilmiyor, sürüm kayması testlerle yakalanıyor.
5. Gerçek sonuç sözleşmesini, hata/boş/kısmi yanıtı, kapsam sınırını ve eski
   kanıt uyumunu doğrula; değişen lisans/kurulum/kullanım belgelerini güncelle.

Bu teslim araç sürümlerini yükseltmez, bağımlılık eklemez veya şemayı
değiştirmez. Bütün geçişli bağımlılıkların tam bütünlük kabulü ayrı işletim
işidir. theHarvester kesinti sonrası geri dönüşü 0.140.3'de eklenmiştir;
doğrulama kapsamı [güncel durumda](STATUS.md) kayıtlıdır.
[Katalog kararı](decisions/0144-reviewed-component-catalog.md)
ve [motor yol haritası](roadmap/ENGINE_INTEGRATION_ROADMAP.md).
