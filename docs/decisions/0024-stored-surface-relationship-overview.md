# 0024 — Saklanmış dış yüzey kanıtlarının ilişki görünümü

**Tarih:** 29 Ekim 2026  
**Karar:** İlk varlık ilişkisi görünümü, yeni grafik deposu yerine mevcut kanıtlardan tek okuma anında hesaplanacak.

## Neden

Kök domain, pasif bulunan alt alan adları, son DNS/IP sonucu, doğrulanmış sertifika ve posta sunucusu farklı komutlarda görünüyordu. Kullanıcı dış yüzeyin genel resmini görmek için bu kayıtları zihninde birleştirmek zorunda kalıyordu. Bununla birlikte henüz genel amaçlı grafik sorgusu, çok kuruluşlu ölçek veya ayrı ilişki yaşam döngüsü gereksinimi ölçülmedi. Bu aşamada yeni bir grafik veritabanı ya da aynı kanıtı tekrar saklayan ilişki tablosu işletim yükü ve tutarsızlık riski oluşturur.

## Karar

`surface overview KÖK`, yalnız önceden kaydedilmiş kanıtı okuyacak. SQLite adaptörü aşağıdaki verileri tek salt okunur transaction anlık görüntüsünden alacak:

- kayıtlı kök ve güncel aktif kapsam durumu;
- son kök DNS/TLS kontrolü;
- son MX/SPF/DMARC kontrolü;
- son pasif keşif çalışması;
- alt alan adı adaylarının durum toplamları ve sınırlı örneği.

Uygulama servisi bu verilerden beş açıklanabilir ilişki üretir:

- `discovered_subdomain`: kök → pasif alt alan adı adayı;
- `resolves_to`: kök → son kontrolde görülen IP;
- `presents_certificate`: kök → doğrulanmış sertifika parmak izi;
- `certificate_covers`: sertifika → sertifikadaki DNS adı/deseni;
- `uses_mail_exchange`: kök → son MX kaydındaki posta sunucusu.

Her ilişki kanıt türünü, kanıt kimliğini ve gözlem zamanını taşır. Kaynak gerçek mevcut eklemeli kontrol, aday ve keşif kayıtlarıdır. Görünüm bunları kopyalamaz ve şema 13'ü değiştirmez.

Aday örneği varsayılan 20, en fazla 100 kayıtla sınırlıdır. Toplam ve `pending/owned/rejected` sayıları örnekten bağımsız gösterilir. Sınır, kişisel aşamada terminal ve JSON çıktısının denetimsiz büyümesini engeller.

## Güvenlik ve anlam sınırı

Komut internete bağlanmaz, yeni tarama başlatmaz, kapsamı değiştirmez, onarım yapmaz ve veritabanına yazmaz. Hiç kanıtı olmayan kayıtlı kök geçerli boş görünüm verir. Seçilen son kanıtlardan biri bozuksa sağlıklı parçaları birleştirip yanıltıcı sonuç vermek yerine işlem güvenli biçimde durur.

İlişki sahiplik doğrulaması veya risk kararı değildir. Paylaşımlı/CDN IP kuruma ait sayılmaz; sertifikanın kapsadığı bir adın sahipliği kanıtlanmaz; geçerli TLS güvenli site anlamına gelmez; pasif aday otomatik aktif kapsama alınmaz. Geçmişteki bütün ilişki durumları, servis/port grafiği ve genel kuruluş grafiği bu teslimin dışında kalır.

## Sonuç ve ilerideki kapı

Clean Architecture sınırı korunur: domain modelleri depoyu bilmez, uygulama ilişkileri hesaplar, port tek anlık görüntü sözleşmesini tanımlar, SQLite adaptörü tutarlı okumayı yapar ve terminal yalnız gösterir. Başka bir depo gerektiğinde aynı sözleşmeye adaptör yazılabilir.

Kalıcı genel ilişki modeli veya grafik veritabanı ancak çok adımlı grafik sorguları, ilişki sürümü üzerinde bağımsız kararlar, performans ölçümü ya da birden çok veri deposu arasında tekrar kullanım somut gereksinim olduğunda değerlendirilecek. O durumda kanıt kökeni, migration, yedek/restore, tekilleştirme ve bozuk ilişki testleri ayrı kabul kapıları olacaktır.
