# Kaynak ve feed yönetişimi

P09, XTI'daki kaynakların ne yaptığını ve hangi koşulda kullanılabileceğini
tek yerde gösterir. Örneğin kullanıcı `XposedOrNot` kaynağını açtığında motor;
bu kaynağın doğrulanmış domain ve anahtar istediğini, ücret/ticari koşulunun
ayrıca kararlaştırılacağını, yalnız maskeli credential maruziyeti ürettiğini
ve bunun doğrulanmış ihlal hükmü olmadığını aynı kayıtta açıklar.

Bu paket yeni bir feed satın almaz, internete istek göndermez ve mevcut
kaynak verilerini ortak bir tabloya taşımaz. Kaynakların **kontrol düzlemini**
standartlaştırır; veri toplama ve kalıcı kanıt mevcut özelliklerin kendi
adaptörlerinde kalır.

## Kullanım

```sh
./xti sources
./xti sources catalog
./xti sources catalog --state conditional --limit 20
./xti sources catalog --language fr --region FR
./xti sources history
./xti sources show credential:xposedornot-domain
./xti sources show content:bluesky-public-search
./xti sources show telemetry:xti-sensor-v1
./xti sources show telemetry:cowrie-jsonl
./xti sources show telemetry:cape-report-v1
./xti sources validate
```

Çıplak `sources`, `sources catalog` ile aynı çıktıyı ve JSON sözleşmesini
üreten bir kısayoldur; ikinci bir eski katalog değildir. `catalog` kaynakları
sayfalı listeler. `show` tek kaynağın bütün sözleşmesini,
`validate` ise kataloğun şema, kimlik tekilliği, sıralama ve zorunlu kanıt
alanlarını çevrimdışı doğrular.

Komutların görevleri birbirine karıştırılmaz:

| İhtiyaç | Komut |
|---|---|
| Kaynağın erişim, maliyet, hak ve sınırları | `sources` veya `sources catalog` |
| Tek kaynak manifesti | `sources show KIMLIK` |
| Kayıtlı son başarı, hata ve güncellik | `sources status` |
| Son pasif crt.sh/urlscan sorguları ve kayıtlı kota beklemeleri | `sources history` |
| crt.sh/urlscan pasif tarama işinin bütün sorguları | `jobs list` ve `jobs show IS_KIMLIGI` |
| Kaynakların bir domaine gerçek katkısı | `sources contribution DOMAIN` |

Bu ayrım katalog tanımı, çalışma sağlığı ve tekil tarama kanıtının aynı çıktı
içinde ikinci kez modellenmesini engeller.

### 0.189.1 terminal geçişi

0.189.0 ve öncesinde çıplak `sources --json` çıktısındaki `catalog`,
`sources` ve `cooldowns` alanlarını okuyan yerel betikler aşağıdaki açık
yüzeylere geçirilmelidir:

- `catalog` → `sources catalog --json` içindeki `data.sources`;
- son deneme/güncellik → `sources status --json`;
- tekil crt.sh/urlscan sorguları → `jobs list/show --json`;
- son pasif sorguların toplu özeti ve bekleme/kota durumu → `sources history --json`.

Engine/platform `sources.catalog/get/validate` v1 sözleşmesi değişmemiştir.
Veritabanında dönüşüm veya veri kaybı yoktur; değişen yalnız eski sürümsüz
terminal birleşimidir.

Kayıtlı çalışma geçmişi ayrıca istenebilir:

```sh
./xti sources catalog --include-health --domain example.com
./xti sources show crt.sh --include-health --domain example.com
```

Sağlık görünümü yeni ağ isteği yapmaz. Yalnız mevcut son deneme, son başarı,
güncellik ve hata kaydını manifestin yanında gösterir. Sağlık bilgisi olmayan
bir connector “çalışıyor” sayılmaz; kendi özellik geçmişine yönlendirilir.

## Durumlar

| Durum | Sade anlamı |
|---|---|
| `active` | Kod ve zorunlu yerel koşullar hazırdır; yine de kaynak erişimi anlık olarak başarısız olabilir. |
| `conditional` | Kod vardır fakat hesap, anahtar, araç, ticari karar veya yetkili hedef gibi açık bir gereksinim bekler. |
| `disabled` | Kaynak bilinçli ürün kararıyla yeni kullanımda kapalıdır; eski verinin korunması ayrı olabilir. |

0.191.0 kataloğu 53 manifest içerir: 32 aktif, 14 koşullu ve 7 kapalı.
Kapalı yedi kaynak, kullanıcı kararıyla aktif yeni geliştirme dışında tutulan
zafiyet kaynaklarıdır. Bu sınıflandırma kaynakların internette o an erişilebilir
olduğunu veya ticari kullanıma hukuk tarafından onaylandığını söylemez.
Örneğin `content:bluesky-public-search` teknik olarak anahtarsız ve canlı
doğrulanmış `active` kaynaktır; buna karşın kullanıcı içeriğinin ticari
saklama ve müşteriye gösterimi `review_required` kalır.
`telemetry:xti-sensor-v1` yerel ve ağsız teknik kaynak olarak aktiftir.
`telemetry:cowrie-jsonl` ile `telemetry:cape-report-v1` adaptörleri hazırdır
ancak gerçek ayrı altyapı ve canlı kaynak kabulü beklediği için koşulludur;
kontrollü parser fixture'ı canlı kaynak sağlığı sayılmaz.

## Her manifestte bulunan sözleşme

| Alan | Ne açıklar? |
|---|---|
| Kimlik ve sürüm | Connector'ün değişmeyen adı ve manifest biçimi. |
| Amaç ve tür | Kaynağın hangi kullanıcı ihtiyacına hizmet ettiği. |
| Toplama/erişim | Arama, snapshot, stream veya aktif kontrol; kamu, hesaplı ya da yetkili hedef ayrımı. |
| Maliyet ve secret | Ücretsiz/ücretli/yerel durum ile anahtar gereksinimi. |
| Dil ve bölge | Kaynağın ilan edilen dil/bölge kapsamı; gerçek kapsama dair canlı kabul değildir. |
| Kayıt türü | Connector sonucunun hangi ortak anlam ailesine girdiği. |
| Provenance | Kaynak kimliği/başvurusu, gözlem/kayıt zamanı, connector sürümü ve kanıt SHA-256 alanları. |
| Kota/tekrar/hata | Sınırlı kullanım, güvenli tekrar ve eski başarılı kanıtı koruma davranışı. |
| Veri hakları | Ticari kullanım, saklama, müşteriye gösterme ve yeniden dağıtım kararları. |
| Sağlık | Ortak kayıtlı durum veya ilgili özellik geçmişinin hangi komutla görüleceği. |
| Ön koşul ve sınır | Kaynağı açmak için gerekenler ve sonucun neyi kanıtlamadığı. |

`commercial_use=review_required` ya da `contract_required` olan bir kaynak,
teknik olarak çalışsa bile müşteriye sunulan ticari profilde otomatik açılmaz.
Araç kodunun açık kaynak lisansı, sağlayıcının verisini saklama veya yeniden
dağıtma hakkı yerine geçmez.

## Engine ve firma platformu

Aynı okuma sözleşmesi UI veya ilerideki .NET backend tarafından kullanılabilir:

```json
{
  "contract_version": 1,
  "request_id": "sources:1",
  "operation": "sources.catalog",
  "parameters": {"integration_state": "conditional", "offset": 0, "limit": 20}
}
```

Desteklenen işlemler:

- `sources.catalog`: filtreli ve sayfalı katalog;
- `sources.get`: tek manifest;
- `sources.validate`: çevrimdışı katalog doğrulaması.

Yerel `engine` cevabı `local-workspace`, `platform request` cevabı seçilmiş
`company-workspace` kapsamındadır. JSON isteği dosya yolu, firma kimliği veya
çalıştırılacak komut kabul etmez. En fazla 200 manifest tek sayfada döner.

## Yeni kaynak ekleme kuralı

Yeni bir connector teslim edilmeden önce:

1. Benzersiz ve sürümlü manifest eklenir.
2. Erişim, maliyet, secret, dil/bölge ve hedef temas modeli yazılır.
3. Ürettiği ortak kayıt türleri ve altı zorunlu provenance alanı tanımlanır.
4. Kota, retry, kısmi/başarısız sonuç ve eski başarılı kanıt davranışı yazılır.
5. Ticari saklama, müşteriye gösterim ve yeniden dağıtım kararı kaydedilir.
6. Kaynak adaptörü kendi canlı/fixture kabulünden geçer; manifest bunun yerine
   kullanılamaz.
7. İlgili özellik yaşam döngüsü insan incelemesi, izleme, vaka ve firma JSON
   kurallarını ayrıca tamamlar.

Bu yöntem connector tanımını çekirdek iş mantığından ayırır. Ancak 0.189.0,
mevcut kaynakların bütün veri tablolarını fiziksel olarak tek formata taşımaz
ve kaynak işlerinin mevcut güvenli adaptörlerini genel bir ağ yürütücüsüyle
değiştirmez.

## Kabul ve kapasite

P09 hedefli test; manifest doğrulaması, filtre/sayfalama, koşullu ve kapalı
kaynaklar, sağlık ayrımı, terminal, engine, firma platformu ve çevrimdışı
çalışmayı kapsar. Birikimli kabul 10.000 sentetik manifesti 200'lük 50 sayfada
kayıpsız ve tekrarsız okudu; ölçüm ağ ve veritabanı kullanmadı. Gerçek kaynak
kalitesi veya sağlayıcı kotası bu sentetik ölçümden çıkarılamaz.

Ayrıntılı kanıt [P09 teslim kartında](roadmap/P09_DELIVERY.md), ticari veri
kararları [ticari kaynak incelemesinde](COMMERCIAL_SOURCE_REVIEW.md) ve açık
bağımlılıklar [NOTES N-052](../NOTES.md#n-052--p09-kaynak-manifesti-ve-canlı-kabul-sınırı)
altındadır.
