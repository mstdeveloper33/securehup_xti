# Karar 0003 — Gerçek İnternet Araması ve Düzenli Kontrol

**28 Ekim 2026 · 0.3.0 içinde uygulandı.**

Bu belge 0.3 kaynak entegrasyonunu açıklar. Kalıcı arama geçmişi ve iş çalıştırma, 0.4'te [0004 kalıcı işler kararı](0004-durable-scan-jobs.md) ile eklendi; aşağıdaki geçmiş/kuyruk eksikleri bu eski sürümün sınırlarıdır.

## Kullanıcı ihtiyacı ve karar

Kullanıcı yalnız izlenecek alan adını verir; aday adres listesini sistem bulur. Birinci kaynak, crt.sh'nin herkese açık sertifika aramasıdır. `scan` bir tur arar; `watch` aynı akışı belirli aralıklarla çalıştırır. Dosya içe aktarma isteğe bağlı yardımcı özelliktir. Ayrı ağ adaptörü ve kaynak sözleşmesi sayesinde sonraki sağlayıcılar eşleştirme ve kayıt kurallarından bağımsız eklenebilir.

## Kaynak ve arama kapsamı

İstek biçimi `https://crt.sh/?dNSName=...&match=ILIKE&output=json`. Marka etiketinden `%marka%` ve `marka%` sorguları üretilir. Yalnız `%.marka.com` aramak dış taklitleri bulmadığı için bu yöntem kullanılmaz. İsteğe bağlı `--typos` en fazla altı farklı bitişik harf değişimini ayrıca arar. Dört karakterden kısa etiketler bu dilimde desteklenmez. Her tur en fazla beş izlenen ad içerir; ortak sorgular tekilleştirilir.

crt.sh, metin filtresinden önce bir sözcük indeksi kullanır. Bu nedenle `%marka%` keyfi alt dizilerde tam kapsama garantisi vermez. Sonuçlar geçmiş sertifikaları da içerir. Kaynak veritabanında mevcut olmayan veya arama ifadesine uymayan adlar bulunamaz. Kaynağın güncel uygulaması grup oluşturmadan önce 10.000 sonuç sınırı kullanır; `result_count` toplamı bu sınıra ulaşınca eksiklik uyarısı verilir. Daha az sonuç alınması eksiksizliği kanıtlamaz. [Sağlayıcının resmî kodu](https://github.com/crtsh/certwatch_db/blob/master/fnc/web_apis.fnc)

Sertifika kaydı, sitenin çalıştığı, hâlen var olduğu veya zararlı olduğu anlamına gelmez. `entry_timestamp` CT kayıt zamanıdır; domain kayıt zamanı değildir. [Certificate Transparency açıklaması](https://certificate.transparency.dev/howctworks/)

## Gözlem ve veri koruma

Bir gözlemin içerik kimliği sağlayıcı + sertifika kimliği + asıl ad + normalize kaynak zamanından türetilir. `name_value` bütün sertifika adlarını içermeyebilir; farklı sorgular aynı sertifikanın farklı adlarını döndürebilir. Bu yüzden bütün yanıtı tek sertifika olarak tekilleştirmeyiz. Her kaynak adı ayrı, tek kayıtlı belge olur; var olan gözlem/bulgu depolama sözleşmesi kullanılır. Wildcard asıl metinde korunur; eşleştirme için yalnız baştaki `*.` kaldırılır.

Kaynak URL'si sertifikanın `https://crt.sh/?id=...` bağlantısıdır. Asıl ad, CT zamanı ve sisteme alınma zamanı saklanır. Sorgu URL'leri ve turun başlangıç/bitişi terminalin JSON raporunda bulunur; ayrı kalıcı arama geçmişi henüz yoktur. Ham HTTP yanıtının bütünü arşivlenmez. Hash, saklanan kimliğin özetidir; ham yanıtın imzası değildir.

Sorgular arasında aynı kaynak kaydı tekilleştirilir. Aynı izlenen kökün altındaki adresler dış taklit bulgusu oluşturmaz. Sadece bu turda seçilen izlenen varlıklar için aday üretilir; bütün kayıtlı kökler sahip olunan alan olarak elenir. Yeni kanıt önceki kararı sıfırlamaz. Şema 2 değişmez; 0.1 verisi için mevcut yedekli `migrate` süreci geçerlidir.

## Sınırlar ve başarısızlık

Kaynak HTTPS ile sabittir; yönlendirmeler reddedilir, TLS doğrulaması açıktır. API anahtarı gerekmez. Yanıt 8 MiB, satır 5000, satırdaki ad 1000, toplam ad 50.000 ile sınırlıdır. Turda en fazla 10.000 belge ve 250.000 karşılaştırma yapılır. Bütün kaynak yanıtları ve adaylar yazımdan önce doğrulanır. Gözlemler tek tek atomik kaydedilir; yazım sırasında kesinti olursa önceki tamamlananlar kalır, yeniden arama kayıtları çoğaltmaz.

İsteklerde 20 saniye socket zaman aşımı ve okuma sırasında süre denetimi vardır; bu bütün turun tam 20 saniyede biteceği garantisi değildir. Uygun geçici hatalarda en fazla iki deneme yapılır. İstekler aynı kaynak nesnesinde en az bir saniye aralıklıdır. Sağlayıcının uzun bekleme isteği komutu uyutmak yerine sonraki sorguları da engelleyen bekleme durumu oluşturur. Bu durum aynı `watch` işlemi boyunca korunur; süreçler arasında kalıcı değildir.

HTML, bozuk/kesilmiş JSON, bağlantı veya sınır hatası boş başarı sayılmaz. Başarılı diğer sorguların verisi saklanabilir; tur kısmi gösterilir. Desteklenmeyen adlar sayılarak atlanır ve eksik kapsam görünür kalır. Arama JSON'u `complete`, `partial` veya `failed` durumunu içerir. Son ikisinde çıkış kodu 3'tür. Sonlu `watch` içinde bir tur başarısızsa sonraki tur başarılı olsa da çıkış kodu 3 kalır.

`watch` bir arka plan sunucusu değildir; terminal/işlem açık kalmalıdır. Varsayılan aralık, turun bitişinden sonraki 3600 saniyedir; alt sınır 300 saniyedir. Kopunca arayı yakalayan kalıcı iş kuyruğu veya kesintisiz CT akışı yoktur. Bunlar sonraki dilimlerdir.

## Doğrulama

Ağdan bağımsız testler sahte HTTP/kaynak yanıtlarını kullanır. Gerçek kaynak denemeleri geçici veritabanlarında ayrıca yapılır. Kaynak kesintileri ve büyük sorguların başarısız olabilmesi kullanıcıya açıkça gösterilir; sentetik veya gerçek kaynak örnekleri internet genelinde doğruluk oranı olarak sunulmaz.
