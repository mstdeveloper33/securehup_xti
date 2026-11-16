# 0152 — Çok firmalı platform için motor sınırı

Tarih: 16 Kasım 2026. Durum: 0.147.0'da uygulandı; yerel genel test ve
gerçek süreç kabulü geçti. Linux doğrulaması aynı kabul betiğiyle sürüm
commit'inde çalışır; [kabul kaydı](../PLATFORM_ACCEPTANCE.md).

Kullanıcı motorun bir platform içinde farklı firmalara hizmet vereceğini
netleştirdi; geniş STIX/TAXII ve LLM dışındaki teslim işlerini onayladı.
Mevcut kuruluş etiketleri güvenlik sınırı değildir. Eski kişisel `engine`
okuma sözleşmesi korunur; platform için açık ayrı giriş eklenir.

## Kapsam

Platform kimlik ve yetkiyi doğrular. Güvenilen başlatıcı, özel izinli kayıt
kökünü ve firma kimliğini seçer. JSON isteği firma kimliği, dosya yolu,
shell komutu veya API anahtarıyla bu seçimi değiştiremez. Motor, kayıtlı
firma kimliğini ayrı veri alanına bağlar; bütün okuma, içerik, iş ve sonuç
işlemleri aynı doğrulanmış alanı kullanır. Ortak SQLite tablolarına firma
filtresi ekleyip var olan veriyi topluca dönüştürmeyiz.

Bu düzen aynı platformda birden fazla firmayı destekler. Uygulama kullanıcısı
doğrudan dosya sistemine veya güvenilen başlatıcı seçeneklerine erişemez.
Sunucu yöneticisine karşı bir yalıtım veya .NET kimlik sistemi değildir.
Servis hesabı, dizin izinleri ve kullanıcı–firma eşlemesi tüketici ekibin
dağıtım sorumluluğudur. Firma adı/kuruluş UUID'si tek başına yetki değildir.

Yeni firma alanı açık kurulumla oluşturulur; mevcut kişisel veritabanı
kendiliğinden bağlanmaz, taşınmaz veya değiştirilmez. Bilinmeyen, kapalı,
bağı yanlış, bağlantı/hardlink içeren veya güvensiz izinli alan reddedilir.
Çekirdek kayıtlar ve iş kuyruğu ayrı dosyalardır; platform yedeği ikisini
birlikte içermeli ve geri dönüş yalnız yeni alana yapılmalıdır.

## İş ve içerik sözleşmesi

Firma içerikleri mevcut kesin kuruluş/tedarikçi kapsamını kullanır;
başlık, mevcut açıklama, kaynak URL/tarih ve eşleşme gerekçesi döner.
Boş başarılı arama, hiç kontrol edilmemiş kapsam, eski kayıt ve kaynak
hatası ayrı kalır. Teknik toplamlar sayfalama/denetim içindir.

İlk kalıcı platform işi kayıtlı, sürümü seçilmiş toplama profilidir.
İstek anahtarı aynı firma içinde tekildir; aynı anahtar/farklı seçim
çatışmadır. Kuyruğa kabul kaynak isteği yapmaz. Ayrı kontrollü worker
işi alır; kayıtlı profil çalışma öncesi değişmişse işi başlatmaz.
Kesinti belirsiz işi otomatik tekrar çalıştırmaz. Kaynak kanıtı korunur;
iş geçmişi ve sonucu firma alanında okunur. Başarılı kaynak çağrısını
çift çalıştırmama, yanıt kaybı ve yeniden başlatma kabulünün parçasıdır.

## Kabul ölçütleri

- A bağlamında B'nin kayıt/kuruluş/iş kimliği sonuç vermez; aynı arama ve
  tekrar anahtarı farklı firmalarda bağımsızdır. B'deki hata A'ya taşınmaz.
- Bilinmeyen firma veya bozuk kapsam yerel varsayılana geri düşmez.
- Aynı iş iki worker tarafından başlatılmaz. Tekrar istek yeni iş/kaynak
  çağrısı oluşturmaz; belirsiz kesinti otomatik sorgu tekrarı yapmaz.
- Yeni/geçmiş firma içerikleri, hata/boş/eski durumlar ve sayfalama gerçek
  geçici SQLite ile sınanır; Tavily canlı kabulü anahtar gelene kadar açıktır.
- Platform yedek/geri dönüşü çekirdek kanıt ve iş tekrar anahtarlarını korur.
- Son kodda Linux kurulum, ilgili genel testler, firma ayrımı, eşzamanlılık
  ve ölçümlü kapasite kayıtları birlikte raporlanır. Bu kayıt tek başına
  kesintisiz 7/24 hizmet garantisi değildir.

Yeni kaynak ve daha esnek ad eşleştirmesi ancak ölçülmüş katkıyla eklenir.
Genel makale arşivi, LLM, geniş STIX/TAXII, web paneli veya .NET istemcisi
bu teslimde geliştirilmez.
