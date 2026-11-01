# Karar 0002 — Önce Çevrimdışı, Gerekçeli Domain Adayları

**28 Ekim 2026 · 0.2.0 içinde uygulandı.**

Bu belge ilk geliştirme diliminin tarihsel kararıdır. Güncel kullanıcı akışı, [0003 internet araması kararı](0003-public-certificate-search.md) ile dosya gerektirmeyen `scan` ve `watch` komutlarıdır.

## Karar ve kapsam

İlk tespit dilimi kayıtlı dosyadan çalışır. Ağ kaynağı sorununu, eşleştirme ve kayıt davranışından bağımsız doğrulayabilmek için TXT/JSONL kullanılır. Kullanıcı kendi izlediği adresi ve örnek listesini seçer; siteye bağlantı veya tarama yapılmaz.

Alan adını son iki parçaya bölmek co.uk ve özel barındırma gibi durumlarda hatalıdır. Resmî Public Suffix List'in değiştirilmemiş bir kopyası paketlendi. ICANN/PRIVATE, wildcard ve exception kuralları uygulanır. Bilinmeyen uzantıda PSL'nin varsayılan tek parçalı kuralı kullanılır; bunun gerçek bir kaydı doğruladığı iddia edilmez. Unicode/IDNA analizi ertelendi ve ilgili girdiler açık hata verir. [Resmî liste açıklaması](https://publicsuffix.org/list/), [veri/lisans bildirimi](../../THIRD_PARTY.md)

Uygulama dosyayı bütünüyle okur ve sınırlar; her satırı doğrular, bütün adayları hesaplar, ardından tek transaction içinde kaydeder. Boyut 2 MiB, satır 5000, satır baytı 8192 ve karşılaştırma 250.000 ile sınırlıdır. Bu bir küresel akış mimarisi değildir; canlı kaynak için kalıcı işler sonra eklenecek.

## Kural yaklaşımı

Farklı kayıt kökü şartıyla aynı marka etiketi, sınırları belirli ek sözcük, tek karakter farkı, bitişik harf değişimi veya izlenen adı yanıltıcı alt domain olarak kullanma incelenir. Kısa/genel adlarda bazı kurallar uygulanmaz. Bütün izlenen kökler bu taklit adaylarından çıkarılır. İzinli kökün ele geçirilmesi ayrı bir tespit ihtiyacıdır.

Sonuçlar yalnız adaydır. Olasılık yüzdesi veya kesin phishing etiketi verilmez. Her aday gerekçelerini taşır. Kural sürümü CLI'de tam PSL SHA-256 değeriyle birleştirilir; aynı dosya farklı referans sürümüyle analiz edilirse ayrı değerlendirme kimliği oluşur. Eski bulgu ve kararlar korunur. Referans güncellemesi yeni bir değerlendirme gerektirir.

## Kimlikler ve geçmiş

- Gözlem kimliği: dosya içeriği SHA-256 + fiziksel satır. Yeniden adlandırılmış dosya çoğalmaz; farklı içerik aynı adres için yeni gözlem olabilir.
- Bulgu kimliği: izlenen varlık + aday domain + kural/referans sürümü.
- Bulgu–gözlem bağlantısı tekildir. Yeni kaynak var olan bulguya bağlanır; karar sıfırlanmaz.
- Kaynak adı ilk kabul edilen dosya adıdır; bütün dosya kopyalanmaz. Asıl adres, kaynak zamanı varsa bu zaman ve sisteme alım zamanı saklanır.
- last_seen_at yeni kaynak bağlantısının sistemde kurulduğu zamandır; domain kayıt veya kaynağın son görülme tarihi olarak yorumlanmaz.
- Kararlar ekleme sırasıyla tutulur. Saatler eşit veya geri gitmiş olsa da karar sırası korunur.

Hash içerik kimliğini sağlar; iddianın doğru olduğunu veya verinin güvenilir kaynaktan geldiğini ispatlamaz.

## Veri geçişi

Şema 2 yeni gözlem/bulgu/bağlantı/karar tablolarını ekler. Mevcut v1 kullanımında komut açıkça migrate ister. Migration yazma kilidi altında önce ayrı okuyucu ile tutarlı v1 yedeğini oluşturur; DDL ve sürüm değişimi aynı transaction içinde tamamlanır. Hata olursa eski şema korunur ve oluşmuş yedek kalır. Bilinmeyen veya bozuk şema dönüştürülmez.

Restore eski yedeği eski biçimde açar; ardından açık migration gerekir. Böylece yedek içeriği sessizce değiştirilmez. Yeni sürüm yedeği tüm kayıt/karar tablolarını birlikte taşır.

## Doğrulama ve açık işler

36 sentetik örnek; gerçek veri üzerinde ölçülmüş doğruluk iddiası yoktur. İçe aktarma hataları, tekrarlar, yeni izlenen varlıkla yeniden analiz, karar geçmişi, yedek/restore ve migration rollback test edilir. Sıradaki işler kalıcı kuyruk, canlı kaynak, kaynak sağlığı ve ihtiyaç halinde kontrollü zenginleştirmedir.
