# 0029 — Pasif aday, varlık kaydı ve aktif kapsamı ayrı katmanlarda gösterme

**Durum:** Kabul edildi  
**Tarih:** 29 Ekim 2026

## Bağlam

Pasif sertifika keşfi bir alt alan adını aday olarak bulabilir. Kullanıcı bu adayı `owned` ile kendisine ait olarak sınıflandırabilir; ancak bu karar adresi kayıtlı varlık yapmaz ve hedefe bağlantı izni vermez. Ayrı `assets add` kaydı da tek başına aktif kontrol izni değildir; bunun için görünür gerekçeli `surface approve` gerekir.

Bu katmanlar farklı komutlarda görüldüğünde kullanıcı bir sahiplik kararının kayıt veya kontrol iznine dönüştüğünü sanabilir. Buna karşılık katmanları otomatik birleştirmek pasif keşiften izinsiz aktif bağlantıya giden tehlikeli bir yol oluşturur.

## Karar

`surface inventory KÖK`, köke bağlı pasif adayları tek SQLite salt-okunur anlık görüntüsünde üç bağımsız katmanla gösterir:

1. Aday kararı: `pending`, `owned` veya `rejected`.
2. Varlık kaydı: aday domaininin `assets` içinde ayrıca bulunup bulunmadığı.
3. Aktif kapsam: kayıtlı varlık için gerekçeli kapsamın etkin, kaldırılmış veya hiç verilmemiş olması.

Kök adresin kapsamı ayrıca gösterilir; adayların kayıtlı ve aktif kapsamlı toplamları filtre dışındaki bütün kök adayları üzerinden hesaplanır. `--status` yalnız gösterilen aday kararlarını, `--limit` yalnız gösterilen satır sayısını sınırlar. Genel katman sayaçları böylece filtrenin ardındaki durumu gizlemez.

Uygulama katmanı her satıra bir sonraki güvenli adımı önerir: adayı incele, varlık olarak kaydet, kapsamı açıkça onayla, izle veya işlem yapma. Bu değer yalnız açıklamadır. Görünüm karar vermez, varlık/kapsam oluşturmaz, ağ isteği yapmaz, onarım çalıştırmaz ve kayıt değiştirmez.

Depo portu aday, olası kayıtlı varlık ve olası kapsamı tek read-only transaction içinde verir. Mevcut eklemeli aday karar geçmişi ve kapsam modeli kaynak gerçek olarak kalır. Yeni tablo veya migration yoktur; şema 15 değişmez.

## Sınırlar

- `owned` kullanıcının sınıflandırmasıdır; teknik DNS veya kuruluş sahipliği doğrulaması değildir.
- Bir adresin kayıtlı olması aktif kontrol izni anlamına gelmez.
- Aktif kapsam kullanıcı yetki beyanıdır; platformun bağımsız hukuki/teknik doğrulaması değildir.
- `pending` adayın ayrıca etkin kapsamlı olması olası bir süreç tutarsızlığını görünür kılar; komut bunu sessizce düzeltmez.
- Görünüm yalnız pasif keşifte köke bağlanmış alt alan adı adaylarını kapsar; genel varlık grafiği değildir.

## Sonuçlar

Kullanıcı hangi adresin yalnız aday, hangisinin kendisine ait seçilmiş, hangisinin kayda alınmış ve hangisinin aktif kontrol için açıkça onaylanmış olduğunu tek yerde ayırt eder. Güvenlik sınırı korunur: bu katmanların hiçbiri diğerine otomatik dönüşmez. Küçük uygulama portu ve SQLite adaptörü ileride API veya web arayüzü eklendiğinde aynı ayrımı yeniden kullanabilir.
