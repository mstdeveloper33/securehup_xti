# Açık Kuruluş ve Marka Bağlantıları

**PLANLANDI — UYGULANMADI (PLANNED — NOT IMPLEMENTED).** 14 Kasım 2026.
Bu belge 3. aşamanın önerilen sözleşmesidir. Çekirdek domain/port/uygulama
taslağı ayrı geçici çalışma alanında hazırlanmıştır; ana projeye CLI,
veritabanı veya çalışan özellik olarak entegre edilmemiştir. Önce 2. aşama
tamamlanır. Gerçek çalışan kapsam [STATUS](../STATUS.md) dosyasındadır.

## Kullanıcının yapacağı şey

Bir kuruluş adı kaydetmek ve mevcut domain/sosyal/ransomware izlemelerini
o kuruluşun altında açıkça gruplamak. Örneğin kullanıcı `Örnek Kuruluş`
kaydı açar, kayıtlı `example.com` domainini ve ayrı ayrı seçtiği izleme
kimliklerini bağlar. Başlık benzerliği, aynı kullanıcı adı veya domain
metninden kendiliğinden bağlantı oluşturulmaz.

Bu işlem sahiplik, kişi kimliği, sızıntı doğrulaması veya aktif kontrol
yetkisi üretmez. Yeni izleme tanımı oluşturmaz; var olan kaydı işaret eder.
Aynı kayıt, kullanıcı seçerse birden çok kuruluşta yer alabilir.

## Küçük ve açık kapsam

| Bağlantı türü | Kullanıcı girdisi | Kalıcı hedef |
| --- | --- | --- |
| `domain` | Önceden kaydedilmiş kanonik domain | `assets` kaydı |
| `username-watch` | Mevcut izleme UUID'si | Kaynak kimliği korunmuş Maigret/Sherlock izlemesi |
| `ransomware-watch` | Mevcut izleme UUID'si | ThreatCluster izlemesi |
| `ransomlook-watch` | Mevcut izleme UUID'si | RansomLook izlemesi |

Telefon, kişi, çalışan listesi, müşteri yetkisi/rolü ve kullanıcı hesabı bu
teslimde yoktur. Kuruluş kimliği ilerideki tenant izolasyonunun yerine
kullanılmaz. `collect`, kayıtlı profil ve mevcut domain analizi bu aşamada
kendiliğinden kuruluş kapsamına genişletilmez; toplama seçimi açık kalır.

## Kimlik ve yaşam döngüsü

- Kuruluşun değişmeyen UUID'si, adı için kanonik anahtarı, görünen adı,
  revision numarası, etkinlik ve oluşturma/güncelleme zamanı bulunur.
- Ekleme, ad değiştirme, geri çekme ve yeniden etkinleştirme açık işlemlerdir.
  Aynı etkin adı tekrar eklemek ikinci kuruluş üretmez. Geri çekilmiş kaydı
  tekrar `add` ile açmak reddedilir; `reactivate` açıkça seçilir.
- Yeniden adlandırmada UUID ve bağlantılar korunur. Başka etkin veya geri
  çekilmiş kuruluşun güncel ad anahtarıyla çakışma reddedilir. Geri çekilmiş
  kuruluşun adı değiştirilebilir; etkinliği değişmez.
- Bağlantı kimliği kuruluş + tür + kesin hedefe aittir. Hedef değiştirilemez;
  yanlış bağlantı geri çekilir, doğru hedefe ayrı bağlantı kurulur.
- Bağlantı ve gerekçe aynıysa tekrar işlem yeni olay üretmez. Gerekçe
  değiştirilirse `updated`, geri çekilmiş aynı bağlantı yeniden seçilirse
  `reactivated` olayı ve yeni revision oluşur. Eski olaylar değiştirilmez.
- Ekleme/bağlama, yeniden etkinleştirme ve geri çekme gibi yazımlar gerekçe
  taşır; isimler ve gerekçeler terminal kontrol karakterlerini reddeder.
- Kuruluşu geri çekmek bağlantıları veya kaynak izlemelerini silmez ya da
  onların etkinlik bayraklarını değiştirmez. Etkin gruplama için kuruluş,
  bağlantı ve hedef kayıt birlikte etkin olmalıdır.
- Kuruluş geri açıldığında daha önce açık bırakılan bağlantılar, hedefleri
  de etkinse tekrar etkin gruplamada yer alır. Bu hiçbir tarama başlatmaz.
  Kullanıcının ayrıca geri çektiği bağlantı otomatik açılmaz.
- Kaynak izlemesi geri çekilince bağlantı geçmişte okunabilir kalır;
  hedefin durumu ayrıca gösterilir. Kuruluş veya hedef kapalıyken de
  bağlantıyı geri çekmek mümkündür. Kopuk hedef kaydı sessizce yok sayılmaz.

## Domain, port ve uygulama sınırı

Taslak `domain/organizations.py`, donmuş kuruluş/bağlantı/olay/görünüm
modellerini ve iki saf yaşam döngüsü kuralını içerir:
`decide_organization_change`, `decide_organization_link_change`.
`organization_link_effective` üç etkinlik durumunu ve kesin kimlik
eşleşmesini birlikte değerlendirir. Bu kurallar SQLite veya terminal
import etmez.

`OrganizationRepository` küçük bir yerel depolama sözleşmesidir:
`add`, `rename`, `revoke`, `reactivate`, `link`, `unlink`, `list`, `show`,
`show_link`. Bağlantı hedefinin güncel etiketi/kaynağı/durumu görünümde
asıl kayıttan okunur; sorgu, platformlar veya izleme tanımı kopyalanmaz.
Kuruluş ve bağlantı geçmişi, toplam kayıt sayısı ve görünüm sınırı ayrı
alanlardır. Liste ve bağlantı ayrıntılarında offset/limit bulunur.

`OrganizationService` girdi normalleştirmesi, saat ve ortak `ExecutionLock`
sınırını yönetir. Bütün yazımlar kilit altında ilgili repository işlemini
çağırır; liste/ayrıntı okumaları kilit almaz. SQLite adaptörü **aynı yazma
transaction'ı içinde** geçmişi, kuruluş/hedef etkinliğini ve tekilliği tekrar
doğrulamak zorundadır. Servisin önceden okuduğu duruma güvenerek yazamaz.
Terminal kökü somut adaptörü/kilidi bağlar; gelecekte React aynı uygulama
servisinden yararlanabilir. Yeni REST endpoint bu taslağın parçası değildir.

## Önerilen kalıcılık ve şema geçişi

2. aşama şema 56'yı tamamladığında sonraki şema 57 için dört ek tablo
öngörülür: `organizations`, `organization_events`, `organization_links`,
`organization_link_events`. Kesin DDL ve audit uygulaması ayrı teslimdir.

Bağlantının mevcut tabloya gerçek yabancı anahtarı olmalı: domain için
`asset_id`, diğer türlerde ilgili watch ID'si. Tür kontrolüyle tam bir hedef
kolonu dolu olmalı; domain değerini yalnız serbest metinle saklayıp kayıt
bağını kaybetmekten kaçınılır. Modeldeki kanonik domain değeri hedef
kaydından okunur. Kuruluş + tür + hedef tekilliği veritabanında da korunur.

Olaylar değişmez tam ilişki/ad snapshot'ı, gerekçe, revision ve zaman taşır.
Güncel durum olay zinciriyle doğrulanır. Ad değişikliği etkinlik durumunu
korur; bu yüzden audit her olayı yalnız adından etkin/pasif diye yorumlamaz.
Revision artışı ve zaman sırası denetlenir. Silme/cascade ile geçmiş veya
mevcut kullanıcı kaydı kaldırılmaz. Ad çakışması ve işlem ortası hata bütün
mutation'ı geri alır.

Geçiş açık `storage migrate`, benzersiz yedek ve rollback kullanır.
Mevcut domain, izleme, profil ve çalışma verileri değiştirilmez. Yeni
kuruluş veya bağlantılar mevcut kayıtlardan otomatik üretilmez. Salt okunur
görünümler şemayı kendiliğinden yükseltmez; tek SQLite snapshot içinde
kuruluş, bağlantı ve hedef durumunu tutarlı okur.

## Kabul ve teslim sırası

1. **İzole çekirdek:** Normalleştirme, kuruluş/bağlantı yaşam döngüsü,
   açık yeniden etkinleştirme, üçlü etkinlik ve servis kilit sınırının
   küçük birim testleri. Bu taslakta 9 test geçmiştir; kalıcılık kabulü
   veya özelliğin uygulandığı iddiası değildir.
2. **Kalıcılık:** Şema 56→57 yedekli geçiş; eski verinin korunması; aynı
   hedefin iki kuruluşa bağlanması; aynı kuruluşta tekrarsız bağ; gerekçe
   güncelleme; isim çakışması ve tam revision/olay zinciri denetimi.
3. **Hata/kesinti:** Bağlamadan hemen önce hedef/kuruluşun geri çekilmesi,
   bilinmeyen hedef, yanlış türde UUID, bağlantıyı başka kuruluş üzerinden
   değiştirme, transaction ortasında hata, bozuk olay ve kopuk yabancı
   anahtar durumlarında hiçbir kısmi yazım olmaması.
4. **Okuma ve kurtarma:** Geri çekilmiş hedefin okunabilmesi; hedef yeniden
   açılınca durumun asıl kayıttan gelmesi; veri kopyalanmaması; sayfalama
   toplamları; salt okunur/tek-snapshot davranışı; yedekten yeni dosyaya
   dönüşte aynı kuruluş ve bağlantı geçmişinin korunması.
5. **Terminal:** Ana çalışma tamamlandığında açık add/rename/link/unlink/
   revoke/reactivate ve liste/ayrıntı komutları; domain ve kaynak/izleme
   kimliklerinin tek tek gösterilmesi; JSON tutarlılığı; ağ veya toplama
   çağrısı yapılmaması. Kullanım, mimari ve STATUS ancak bütün kabul
   kontrolleri tamamlanınca güncellenir.
