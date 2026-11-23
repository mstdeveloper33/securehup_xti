# P04 — CTI analiz derinliği

21 Kasım 2026. **Durum: P04 uygulaması ile yerel
işlev/geçiş/firma/kuyruk/yedek, birikimli kapasite ve tam repo regresyonu
tamamlandı. Push kullanıcı kararıyla sonraya bırakıldığı için gerçek Linux
CI/release kabulü açık.** Bu teslim kartı koddan önce sabitlenen kapsamı,
güven sınırlarını ve birikimli kabul ölçütlerini sonuçlarla birlikte korur.

## Kullanıcı sonucu ve bağlı gereksinimler

P04; B02, B03, B04, B05, B08, C02, C03, C05, D04, D05, E01, E03,
J01, J02 ve J03 satırlarının LLM gerektirmeyen motor bölümünü teslim eder.
A07/C01/C06/J04'ün mevcut yerel kanıtla uygulanabilen parçalarını kullanır;
genel STIX/TAXII, LLM, credential doğrulama, etkileşimli web grafiği ve yeni
ücretli feed bu paketin parçası değildir.

Kullanıcı bir kuruluş için sürümlü analiz profili oluşturur. Motor yalnız
saklı CTI iddiaları, IOC ilişkileri, kuruluş domainleri ve yerel MITRE ATT&CK
kataloğunu kullanarak:

- aynı varlığın farklı adları için birleştirme adayı üretir;
- kanıt metninden veya insan tarafından kabul edilmiş ATT&CK kimliğinden TTP
  önerir;
- açık atıf ya da birden fazla bağımsız kanıt üzerinden atıf adayı gösterir;
- coğrafya/sektör ifadelerini `kaynak iddiası` olarak etiket önerisine çevirir;
- kuruluşa ait domain/URL IOC bağları için açıklanabilir inceleme önceliği
  oluşturur;
- değişmez analiz turları üzerinden kampanya/trend farkını, kaynak kapsamı
  değişiminden ayrı gösterir;
- kanıtlı, sınırlı ve sayfalanabilir graf, zaman çizelgesi ve firma JSON'u
  döndürür.

Hiçbir aday otomatik kimlik birleştirme, ATT&CK gerçeği, aktör atfı, ülke
kökeni, sektör hedefi veya zararlılık hükmü değildir. Ortak tek IP atıf için
yeterli değildir. İnsan kararı gözlem ve kanıt sürümüne bağlıdır.

## Seçilen yapı ve araçlar

- Yeni dış araç veya ücretli API yoktur.
- Mevcut kaynak-korumalı `cti_entities`, `cti_relationships` ve IOC kayıtları
  özgün kaynak, zaman ve confidence alanlarıyla kullanılır.
- Yerel, sabit sürümlü MITRE ATT&CK kataloğu teknik, taktik, grup, kampanya ve
  malware kimlikleri için kullanılır. Katalog bulunmazsa boş başarı değil,
  açık kapsam eksikliği gösterilir.
- Ad/alias benzerliği standart kitaplığın sınırlı metin karşılaştırmasıyla
  yapılır. Eşik yalnız aday üretir; fiziksel kayıt birleştirme yapılmaz.
- SQLite değişmez kanıt/tur/karar geçmişini tutar. Terminal, engine ve firma
  platform sözleşmesi aynı uygulama servisini kullanır.

## Kalıcı yaşam döngüsü

1. Firma kapsamlı profil; kaynak güven kuralları, eşikler, kritik önem ve
   bütçeleri sürümlü saklar. Eski tur eski profil tanımını korur.
2. Çalışma kabulü bütün girdi kimliklerini ve kaynak kapsamını dondurur. Aynı
   idempotency anahtarı aynı makbuzu döndürür.
3. Kanıt gövdeleri SHA256 ile tekilleşir; güncel aday indeksi, değişmez gövde,
   değişiklik, karar ve bildirim ayrıdır.
4. Karar `accepted`, `rejected`, `uncertain`; kimlik adayında ayrıca
   `same_entity` ve `different_entity` olabilir. Kanıt değişirse eski karar
   korunur ama güncel sayılmaz.
5. İlk tamamlanan tur sessiz başlangıçtır. Sonraki turda sinyal artışı ile
   kaynak/ATT&CK kapsam değişimi birbirinden ayrılır; eşik geçmiş turları
   yeniden yorumlamaz.
6. Kesilmiş `running` tur otomatik tekrarlanmaz. Açık recovery işlemi onu
   `interrupted` yapar; yeni çalışma yeni idempotency anahtarı ister.
7. Vaka kopyası özgün aday/kanıt/tur başvurusunu dondurur. Ortak inbox yalnız
   ilk başlangıç sonrası eşik üstü yeni/değişmiş adayları gösterir.

## Koddan önce belirlenen kabul ölçütleri

- İki firma, firma başına 10.000 saklı aday ve en az 30 değişmeyen tur.
  Değişmeyen turda yeni kanıt, değişiklik ve bildirim sayısı sıfır olmalı.
- Tek bir kanıt değişiminde tam bir yeni kanıt/değişiklik oluşmalı; önceki
  karar silinmemeli ve `needs_review=true` olmalı.
- 40 adet 100 kayıtlık firma JSON/aday okumasında p95 <2 saniye; sentetik ana
  süreç tepe RSS <256 MiB. Graf en çok 100 düğüm/200 kenar ve devam cursor'u
  ile sınırlandırılmalı.
- Etiketli karşılaştırma kümesi; aynı alias, benzer ama ayrı ad, farklı tür,
  Unicode, ortak tek IP, iki bağımsız IOC, açık ATT&CK kimliği, olumsuz cümle,
  kaynak kapsamı değişimi ve eski karar durumlarını içermeli. Bu küme gerçek
  internet doğruluk yüzdesi olarak sunulmamalı.
- Firma yalıtımı, büyük/bozuk JSON, sayfalama snapshot'ı, aynı istek,
  kesinti/kurtarma, şema91→92 geçişi, yedek/geri dönüş, vaka kanıtı ve kaynak
  provenance ayrı test edilmelidir.
- Gerçek yerel ATT&CK kataloğu ve kontrollü CTI fixture ile kabul yapılmalıdır.
  Gerçek bir saldırı/aktör bulunmaması başarısızlık değildir.

## Teslim edilen akış — 0.183.0

- Terminalde `cti analysis-*` altında profil, plan, doğrudan tur, sınırlı
  monitor, aday/kanıt/karar/değişiklik, graf, zaman çizelgesi, trend, kaynak
  kalite görünümü, rapor ve açık recovery vardır.
- Engine v1 bütün ağsız okumaları; firma platformu v1 aynı okumaları ve
  workspace çitli yazmaları aynı uygulama servisiyle sunar.
- `organization.content.cti_analysis`, kuruluşun profil/son tur/kapsam/trend
  durumunu ve100 kayıt/2MiB sınırlı aday sayfasını verir.
- `cti-analysis` kaynak işi modeli11 içinde tek kaynaklıdır. Profil kapsam
  hash'i kabul ve worker'da doğrulanır; dış HTTP tavanı/denemesi sıfırdır.
- Şema92 profil, tur, değişmez kanıt, güncel aday, son gözlem turu, inceleme,
  değişiklik, ortak bildirim ve idempotency makbuzunu ayrı tutar.
- Karar kanıt+gözlem sürümüne bağlıdır. Kanıt değişirse eski karar silinmez,
  güncel sayılmaz. Son turda görülmeyen aday geçmişten kaldırılmaz.
- CTI analiz adayı ortak inbox'a ve `cti_analysis` vaka kanıtına bağlanır;
  vaka kopyası sonraki turdan etkilenmez.
- Platform backup/restore özgün tur/kanıt/kararı korur ve workspace kimliğini
  döndürmede yeniler. Başka firmanın kimliği `not_found` kalır.
- Yeni bağımlılık, ücretli API, anahtar veya ağ kaynağı eklenmedi.

## Uygulanan güven ve kapasite sınırları

- Profil: en fazla10.000 CTI varlığı,50.000 ilişki,10.000 aday; assertion,
  isim-karşılaştırma ve ATT&CK karşılaştırma bütçeleri ayrıca sınırlıdır.
- Dondurulmuş girdi64MiB; aday kanıtı200KiB; liste sayfası100 kayıt/2MiB;
  graph100 düğüm/200 kenar; timeline1.000 kayıt.
- ATT&CK yerel okuması50.000 varlık,100.000 ilişki ve100.000 faz tavanlıdır.
- Firma ve aday sayfaları büyük dondurulmuş snapshot'ı her kayıt için açmaz;
  yalnız bütünlüğü doğrulanmış küçük run state/rapor alanlarını okur.
- Kaynak kapsam hash'i gözlenen kaynak adlarını, sürümlü kaynak politikasını,
  ATT&CK snapshot'ını, kuruluş domainlerini ve analiz limitlerini kapsar.
  Aynı kaynaktaki içerik değişimi tehdit sinyali; kaynak seti değişimi
  `coverage_changed` olarak ayrı kalır.
- Tazelik gün düzeyindedir. Saatlik worker zaman farkı değişmez kanıtı
  çoğaltmaz; gerçek yaşlanma görünür kalır.

## Yerel kabul sonuçları

`tests.test_cti_analysis` ve `tests.test_cti_analysis_platform` içindeki19
test aşağıdakileri doğruladı:

- etiketli kurallar, farklı tür/tek IP/olumsuz cümle yanlış pozitif guard'ı;
- kaynak iddiası + aday grafı, kabul edilmiş ATT&CK kimliği ve TTP zinciri;
- kaynak-kapsam hash'i ve saatlik tazelik kararlılığı;
- gerçek saklı CTI/IOC girdisi, ilgisiz assertion starvation koruması;
- baseline/replay/değişmez tur, kararın kanıta bağlanması, görünmeyen adayın
  korunması, inbox ve gerçek vaka kopyası;
- açık kesinti recovery'si, tekrar anahtarı çatışması ve bozuk veri fail-closed;
- şema91→92 atomik geçişi;
- iki firma yalıtımı, workspace çiti, sıfır-ağ ortak worker;
- platform yedek/geri dönüşü ve eski workspace kimliğinin reddi.

Birikimli kabul komutu:

```sh
.venv/bin/python scripts/check-cti-analysis-delivery.py
```

Ölçülen sonuç:

| Ölçüm | company-alpha | company-beta | Kabul |
|---|---:|---:|---:|
| Saklı aday | 10.000 | 10.000 | 10.000/firma |
| Toplam / değişmeyen tur | 31 / 30 | 31 / 30 | 30 değişmeyen/firma |
| Tur medyanı | 1,863055 sn | 1,888858 sn | Bilgi |
| Tur maksimumu | 1,922331 sn | 2,126803 sn | Bilgi |
| 100 kayıt okuma p95 | 0,142063 sn | 0,164618 sn | <2 sn |
| 100 kayıt okuma maksimumu | 0,153676 sn | 0,176562 sn | Bilgi |

İki firma birlikte tepe RSS **204,95 MiB**; kabul tavanı **256 MiB**.
Değişmeyen60 turda yeni kanıt, aday değişikliği ve bildirim sayısı sıfırdır.
Bu sentetik birikimli kapasite kabulüdür; internet doğruluk yüzdesi veya
petabyte ölçek iddiası değildir.

## Tam repo regresyonu

İlk tam koşu **3.577 test / 2.196,593 saniye** çalıştırdı. P04 ürün
davranışında hata göstermedi; şema92 ile güncel vaka DDL'ini hesaba katmayan
üç eski migration test beklentisi başarısız oldu ve macOS'ta Linux'a özgü
dört kontrol atlandı. Eski beklentiler güncellendikten sonra üç test tek
başına tekrar geçti.

Aynı çalışma ağacında sıfırdan başlatılan son tam koşu:

```text
Ran 3577 tests in 2183.963s
OK (skipped=4)
```

Sonuç **0 hata / 0 başarısızlık / 4 beklenen atlama**dır. Atlamalar gerçek
Linux veya Linux süreç/hizmet ortamı isteyen kontrollerdir; dolayısıyla bu
macOS sonucu gerçek Linux kabulü olarak sunulmaz. Push ertelendiği için bu
çalışma ağacı üzerinde GitHub Actions/Linux işi henüz çalıştırılmadı.

## Sürüm ve yükseltme sözleşmesi

- XTI0.183.0, çekirdek şema92, kaynak işi11, kuyruk4, engine/platform JSONv1.
- Mevcut veri alanı yalnız `./xti migrate` ile, önce doğrulanmış yedek
  alınarak yükseltilir; normal okumalar otomatik migration yapmaz.
- Kaynak işi1–10 kendi saklı payload/makbuz biçimiyle okunur; yeni P04 işi
  yalnız model11'de kabul edilir.
- Geri dönüş, çalışan veritabanını eski kodla açmak değil; yükseltme öncesi
  birlikte alınmış yedeği yeni alana geri yüklemektir.
- Kullanım ve operasyon sözleşmesi [CTI_ANALYSIS](../CTI_ANALYSIS.md), tasarım
  kararı [ADR0188](../decisions/0188-cti-analysis-candidates.md) içindedir.

## Açık sınırlar

LLM özeti/çevirisi/atfı, genel STIX/TAXII alışverişi, credential doğrulama,
harita veya graf web bileşeni, bütün ticari feed'ler, bütün dillerde semantik
çıkarım ve otomatik engelleme/takedown sonraki paket/kararlarda kalır. Motor
UI için konum/ilişki verisi sağlar; görselleştirmeyi kendisi çizmez.

P04 kod ve yerel kabul kapsamında kapanmıştır. Gerçek Linux CI/release kapısı
push sonrasında ayrıca kaydedilecek; bu dış kapı P04'ün yerel test sonucu gibi
gösterilmeyecektir.
