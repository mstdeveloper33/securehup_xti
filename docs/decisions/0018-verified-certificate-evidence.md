# 0018 — Doğrulanmış TLS oturumundan sertifika kimliği ve bitiş uyarısı

**Tarih:** 29 Ekim 2026 · **Durum:** 0.18.0'da uygulandı.

## Sorun

DNS/IP ve “TLS doğrulandı” durumu, sertifikanın hangisi olduğunu veya ne zaman biteceğini göstermez. Sertifika yenilenmesi, beklenmeyen veren kurum değişimi ya da yaklaşan bitiş dış yüzey yönetiminde incelenebilir olaylardır. Bunları ölçmek için ayrı ve doğrulamasız bir sertifika indirme yolu açmak mevcut güvenlik sınırını zayıflatır.

Ayrıca v0.17 dış yüzey kayıtları ile daha eski bulgu hedef kontrollerinde sertifika alanı yoktur. Yeni kanıt biçimi bu kayıtları geçersiz veya yapay olarak değişmiş hale getirmemelidir.

## Karar

`HttpsTargetProbe`, mevcut güvenli akıştaki hostname ve zincir doğrulaması başarıyla tamamlandıktan sonra aynı TLS soketinin eş sertifikasını okur. Yeni bağlantı, port, yönlendirme, GET isteği veya doğrulamasız TLS yolu açılmaz. Kontrol politika kimliği `https-head-public-v2` olur.

`CertificateEvidence` aşağıdaki kanonik alanları taşır:

- DER baytlarının küçük harf SHA-256 özeti;
- küçük harf hexadecimal seri numarası;
- UTC ISO-8601 geçerlilik başlangıcı ve bitişi;
- issuer için önce organization, sonra common name;
- subject için önce common name, sonra organization;
- tekilleştirilmiş ve sıralanmış kanonik DNS/SAN adları; SAN yoksa subject common name.

DER 64 KiB, taraf alanları ve her metin sınırlıdır. En fazla 128 DNS adı saklanır. Joker yalnız sol başta `*.` biçiminde kabul edilir; kalan ad üretimdeki domain normalleştirmesinden ve Unicode güvenlik profilinden geçer. Seri numarası, zaman aralığı, adlar veya taraf yapısı beklenen biçimde değilse TLS kanıtı tamamlanmış sayılmaz ve hedef HTTP isteğine geçilmez. Uzak hata içeriği terminale taşınmaz.

## Değişim ve geriye uyumluluk

Doğrulanmış sertifika kimliği dış yüzey kanonik durumuna eklenir. Aynı sertifika tekrar görülürse `unchanged`; parmak izi, tarih, issuer, subject veya DNS kapsamı değişirse `changed` ve `certificate` alan farkı oluşur. İlk sertifika bilgili kontrol, önceki sertifikasız temel kaydın ardından geliyorsa görünür bir sertifika değişimidir.

v0.17 durum hash'i sertifika alanı yokken hesaplanmıştı. Sertifikası `None` olan sonuçlarda eski hash girdisi aynen korunur; böylece mevcut kayıtlar yeniden yazılmaz ve doğrulanmaya devam eder. Sertifika alanı olmayan eski hedef kontrol JSON'u v1 biçimi olarak kabul edilir; yeni kayıtlar alanı açıkça taşır. Şema 10 değişmez ve migration gerekmez.

## Kullanıcı görünümü

`surface check/show`, issuer, subject, başlangıç/bitiş, seri, SHA-256 ve DNS kapsamını gösterir. Görüntüleme anında bitişe kalan süre hesaplanır; 30 gün veya azsa uyarı, tarih geçmişse süresi dolmuş uyarısı gösterilir. Bu hesap salt okunurdur ve saklanan kanıtı değiştirmez.

Sertifika bilgisi bulgu hedef kontrolü ve JSON raporunda da kaynak kanıtın parçasıdır. Sertifikanın geçerli olması sitenin güvenli, kötü amaçsız veya kullanıcıya ait olduğunu kanıtlamaz. Bitiş uyarısı operasyonel işarettir; tehdit kararı değildir.

## Sınırlar

- OCSP/CRL durumu, Certificate Transparency dahil olma kanıtı ve zincirin bütün sertifikalarını saklama yoktur.
- Sertifika pinleme veya otomatik engelleme yapılmaz.
- Otomatik zamanlama ve dış bildirim teslimi yoktur; uyarı açık kontrol ve salt okunur görünümde görülür.
- DNS ad kapsamı subdomain keşfi veya sahiplik onayı sayılmaz; yalnız doğrulanmış sertifikanın beyanıdır.
