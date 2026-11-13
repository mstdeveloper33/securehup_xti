# 0127 — Seçilen pasif kaynakları tek çalışmada toplama

**Durum:** Kabul edildi

**Tarih:** 13 Kasım 2026

**Uygulama:** 0.129.0; şema 54 değişmez.

## İhtiyaç

Marka araması, pasif alt alan adı keşfi ve IOC yenilemesi ayrı komutlarla
çalışıyordu. Kullanıcı özellik geliştirmeye devam etmek ve ileride React
arayüzünü bağlamak istiyor. Toplama sırasının terminal veya gelecekteki
arayüzde yeniden yazılması yerine ortak uygulama davranışı gerekiyor.

## Karar

`CollectionService` kayıtlı tek domain için seçilen mevcut servisleri seri
çağırır. Varsayılan işler crt.sh marka araması, urlscan marka araması ve
crt.sh alt alan adı keşfidir. theHarvester ve iki IOC beslemesi yalnız açık
seçimle çalışır. `--task` varsayılan listeyi değiştirir; yinelenen/bilinmeyen
iş, boş seçim ve geçersiz seçenekler reddedilir. Sıra komut argümanlarından
bağımsız sabittir; en fazla altı iş vardır.

- `plan` kayıtlı hedefi ve seçili depoları doğrular; ağ, kilit veya yazı
  oluşturmaz. `run` da ilk mutasyondan önce ön doğrulama yapar.
- Çalışma tüm adımlar boyunca mevcut `JobService.lock` kilidini tutar.
  Tarama `run_owned` kullanır; aynı kilidi ikinci kez almaya çalışmaz.
- Her iş çalışacağı zaman oluşturulur. Kaynak başarısızlığı mevcut
  sonuç modellerinde ayrı kaydedilir; sonraki bağımsız kaynağa geçilir.
  Bütünlük/depolama/program hatası ve kullanıcı kesintisi yeni işi durdurur.
- Başarılı önceki adımlar geri alınmaz. Mevcut kaynak kayıtları, tekrar
  tekilleştirmesi, insan kararları ve bildirim kuralları kullanılır.
- Son birleşik analiz toplama bittikten sonra mevcut kayıtları okur.
  Toplama durumu yalnız seçili kaynak adımlarından hesaplanır. Eski veriyle
  analiz üretilebilmesi eksik toplamayı başarılı hale getirmez.
- Donmuş modeller gerçek iş/deneme/keşif/IOC kimliklerini ve özgün sayaçları
  taşır. Farklı kaynakların kayıt sayıları benzersiz toplam diye toplanmaz;
  IOC katalog sayısı domain bulgusu sayılmaz.
- CLI yalnız servisleri bağlar ve sonucu sunar. Uygulama/domain katmanları
  terminal, HTTP veya SQLite bilmez. İlerideki API aynı servisi kullanabilir.

Bu bir defalık ön plan toplama işlemidir. Birleşik oturum tablosu, otomatik
devam, zamanlayıcı ve yeni genel iş akışı motoru oluşturulmaz. Her kaynağın
geçmişi mevcut komutlarıyla açılır. `--plan` gelecekteki kaynağın erişilebilir
olduğunu garanti etmez; ağ başlamadan alınan yerel kapsam görünümüdür.

## Kapsam

Aktif DNS/TLS/HTTPS/port kontrolü, sosyal/ransomware izlemesi, ATT&CK senkronu,
dış bildirim ve hedef kaydı oluşturma otomatik eklenmez. Bu işlerin kapsamı
veya yetkisi tek domain girdisinden türetilmez. Yeni kaynak/dependency yoktur;
mevcut adaptörlerin kota, boyut ve süre sınırları korunur. Normal `analyze`
davranışı ağsız kalır. Yeni bir şema geçişi veya kullanıcı verisi taşıması yoktur.

## Doğrulama

Geçici veride seçili kaynak sırası/izolasyonu, planın yazmasızlığı, ağ öncesi
ret, kaynak hatası sonrası devam, tüm kaynakların hatası, depolama/kesinti
sonrası önceki kanıt, tek kilit, tekrar ve insan kararı korunumu sınanır.
Terminal/JSON aynı sonucu gösterir; kısmi/başarısız çalışmada çıkış 3 ve
`ok:false` korunur. Tamamlanmış canlı kabul ayrıca `STATUS.md` içinde yazılır.
