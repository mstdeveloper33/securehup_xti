# P09 — Kaynak ve feed yönetişimi teslim kartı

**Tarih:** 23 Kasım 2026
**Sürüm:** 0.189.0 · **Çekirdek şema:** 97 (değişmedi)
**Ana gereksinim:** A07 — ticari/üçüncü taraf feed ve normalizasyon
**Desteklenen gereksinimler:** A13, I04, J01 ve yeni kaynaklarda J03
**Durum:** Yerel motor uygulaması, hedefli kabul ve macOS hızlı repo kapısı
tamam; tam repo/Linux CI kabulü ile kaynakların kendi canlı erişim kabulleri
ayrı açık.

## Kullanıcı sonucu

Kullanıcı artık XTI'daki her kaynak için şunları tek kayıtta görebilir:

- kaynak ne toplar ve hangi ortak kayıt türünü üretir;
- ücretsiz, ücretli veya yerel olup olmadığı;
- hesap, API anahtarı, araç ya da yetkili hedef gereksinimi;
- dil ve bölge kapsamı;
- kota, tekrar ve kaynak hatasında kanıtı koruma davranışı;
- ticari kullanım, saklama, müşteriye gösterme ve yeniden dağıtım kararı;
- zorunlu kaynak izi alanları, sağlık görünümü ve bilinçli sınırlar.

Terminal, yerel engine JSON'u ve firma platform JSON'u aynı uygulama servisini
kullanır. Katalog salt okunur ve çevrimdışıdır.

## Uygulanan parçalar

| Parça | Teslim |
|---|---|
| Sürüm ve şema | `source-governance` sözleşme v1; çekirdek veritabanı şeması değişmedi. |
| Manifest modeli | 49 kaynak için kimlik/sürüm, erişim, maliyet, secret, dil/bölge, kayıt türü, provenance, kota, retry, hata ve veri hakkı politikası. |
| Durum ayrımı | 30 aktif, 12 açık gereksinim bekleyen, 7 kullanıcı kararıyla kapalı kaynak. |
| Sağlık ayrımı | Manifest canlı erişimden ayrıdır; isteğe bağlı sağlık yalnız kayıtlı geçmişi okur ve ağ başlatmaz. |
| Terminal | `sources catalog`, `sources show`, `sources validate`; filtre ve en fazla 200'lük sayfalama. |
| Engine | `sources.catalog`, `sources.get`, `sources.validate`; katı JSON alan/tip/sınır doğrulaması. |
| Firma platformu | Aynı işlemler yalnız seçilmiş company workspace içinde çalışır. |
| Genişleme | İncelenmiş yeni manifest servis mantığını değiştirmeden kayıt defterine eklenebilir. |
| Dokümantasyon | Kullanım, ADR, STATUS, özellik kataloğu, ticari/yasal not ve ana yol haritası güncellendi. |

## Kullanılan repo, araç ve sağlayıcı

P09 yeni repo, Python paketi, ücretli API veya canlı veri sağlayıcısı eklemez.
Manifestler mevcut XTI kaynak/adaptör envanterini tarif eder. Yalnız Python
standart kütüphanesi ve mevcut XTI katmanları kullanılır. Bu nedenle “49
manifest doğrulandı” ifadesi 49 kaynağın aynı anda canlı çalıştığı anlamına
gelmez.

## Güvenlik ve doğruluk sınırları

- Engine ve katalog doğrulaması internet, alt süreç veya kaynak yenileme
  çalıştırmaz.
- JSON isteği veri klasörü, firma kimliği, shell komutu veya keyfî dosya yolu
  seçemez.
- Manifestte `active`, connector'ün teknik ürün kapsamını ifade eder; anlık
  erişilebilirlik veya ticari izin değildir.
- `conditional`, gereksinim sağlanmadan aktifmiş gibi gösterilmez.
- Zafiyet kaynakları kodda korunsa da kullanıcı kararı gereği yeni aktif
  kapsamda `disabled` görünür.
- Ortak kayıt türü ve provenance sözleşmesi vardır; mevcut kaynak tabloları
  fiziksel olarak birleştirilmemiştir.
- İnsan incelemesi gerektiren kaynak sonucu otomatik tehdit veya doğrulanmış
  ihlal hükmüne dönüşmez.

## Kabul kanıtı

| Kontrol | Sonuç |
|---|---|
| P09 hedefli davranış/sözleşme testi | 12 test geçti. |
| Yakın katalog + sağlık + engine + platform + mimari regresyonu | Toplam 71 test geçti; 28,206 saniye. |
| Hızlı repo kapısı | 2.314 test 1.817,137 saniyede hatasız geçti; macOS'ta yalnız Linux çalışma zamanı isteyen 4 test beklendiği gibi atlandı. Bu geniş kapı son tarih/URL/provenance girdi sertleştirmesinden önce, 71 testlik yakın paket ise sonrasında çalıştırıldı. |
| Sözdizimi ve smoke | Python derleme, üç terminal komutu ve engine katalog okuması geçti. |
| Birikimli katalog | 10.000 manifest, 200'lük 50 sayfa, kayıp/tekrar yok. |
| Birikimli süre | Kurulum 4,841745 sn; bütün sayfalar 2,935852 sn. |
| Birikimli tepe Python tahsisi | 90.762.580 byte (`tracemalloc`). |
| Ağ/veritabanı | Kapasite kabulünde ikisi de kullanılmadı. |
| Tam repo / Linux CI | Tam repo kapısı ve gerçek Linux CI bu çalışma ağacında henüz çalıştırılmadı/gönderilmedi; açık kabul. |

Kapasite komutu:

```sh
PYTHONPATH=src ./scripts/python scripts/check-source-governance-delivery.py
```

Sentetik kapasite sonucu gerçek sağlayıcı gecikmesini, ticari kotayı veya veri
kalitesini ölçmez.

## Gereksinim kapanış değerlendirmesi

- **A07:** P09 kontrol düzlemi tamamlandı; mevcut ve yeni connector'ler için
  ortak manifest/kanıt/hak/hata sözleşmesi hazırdır. Ancak seçilecek her yeni
  ticari feed'in canlı toplama, saklama, inceleme ve müşteri gösterim kabulü
  ayrıca gerekir; bu yüzden 76 maddelik geniş A07 satırı bütünüyle kapalı
  sayılmaz.
- **A13 / I04:** Dil ve bölge alanları bütün kaynaklarda zorunludur; bu,
  RU/ZH/AR/TR/PT kaynaklarının canlı kapsandığı veya çeviri yapıldığı anlamına
  gelmez.
- **J01:** Altı kaynak izi alanı bütün manifestlerde zorunludur; mevcut kanıt
  depolarının daha güçlü alanları korunur.
- **J03:** Manifest sonucu insan kararı yerine geçmez; ilgili özellik akışları
  kendi review yaşam döngüsünü kullanmaya devam eder.

## Açık dış bağımlılıklar

1. Hesap/anahtar isteyen kaynakların gerçek hesapla canlı kabulü.
2. `review_required` ve `contract_required` kaynaklarda hukuk/ticari karar.
3. Yeni bölgesel ve çok dilli kaynakların seçimi ve etiketli canlı kabulü.
4. Tam Linux kurulum/yükseltme ve GitHub CI kabulü.
5. Gelecekte kaynak işi dispatch'ini genel connector registry'ye taşıma kararı;
   P09 mevcut güvenli ve kaynak-özel adaptörleri değiştirmez.

[Kullanım belgesi](../SOURCE_GOVERNANCE.md) ·
[ADR0194](../decisions/0194-source-governance-manifests.md) ·
[Açık not N-052](../../NOTES.md#n-052--p09-kaynak-manifesti-ve-canlı-kabul-sınırı)
