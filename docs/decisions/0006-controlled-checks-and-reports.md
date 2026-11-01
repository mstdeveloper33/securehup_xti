# 0006 — Sınırlı hedef kontrolü, inceleme sırası ve rapor

**Tarih:** 28 Ekim 2026 · **Durum:** 0.6.0'da uygulandı.

## İhtiyaç

Arşivde bir adın görülmesi, bugün yanıt verdiğini veya kötü amaçlı olduğunu kanıtlamaz. Kişisel kullanıcı bulgunun mevcut durumunu görebilmeli, önce inceleyeceği adayları ayırabilmeli ve kararının dayanağını dışarı alabilmeli. Yeni kanıt önceki kaynakları veya insan kararını değiştirmemeli.

## Ayrım

Pasif keşif adaptörleri değişmez. `TargetProbe` ayrı bir sınırdır; `HttpsTargetProbe` dış ağa erişir, `FindingEnrichmentService` kayıtlı bulgunun adresini kontrol ettirir ve sonucu `AssessmentRepository` ile saklar. Terminal `--check` veya `findings check` ile bu yolu seçer. `triage`, `findings show` ve `report` yalnız kayıtları okur.

`ProbeResult` başlangıç/bitiş, kontrol politikası, DNS adresleri/durumu, bağlanılan IP, TLS/HTTP durumu, hata ve kapsam notlarını taşır. `Assessment` bunu bulguya bağlar. Arşiv sorgu/iş geçmişi ile hedef kontrolü ayrı kayıtlardır. Hedef kontrolüne arşiv işi tamamlandı damgası verilmez.

## Ağ sınırı

1. ASCII alan adı normalleştirilir; IDNA/punycode desteklenmez.
2. Sabit Google Public DNS JSON hizmetine A ve AAAA sorguları yapılır. Bağlantı sayısal `8.8.8.8` adresine sabitlenir; TLS adı `dns.google` olarak doğrulanır. İstemci alt ağı paylaşımı kapatılır. Aday adını DNS sağlayıcısı öğrenir.
3. Sorgunun geri dönen adı/türü, DNS durumu, kesilme işareti ve CNAME zinciri doğrulanır. İki adres ailesi tamamlanmadan hedef bağlantısı başlamaz. Çelişki veya eksik yanıt hata olur.
4. Yerel, özel, link-local, multicast, dokümantasyon, çeviri/tünel ve diğer özel kullanım adresleri reddedilir. Herhangi bir adres uygun değilse bütün hedef bağlantısı engellenir. Python sürümleri arasındaki IP sınıflandırma farkları için açık ek aralıklar bulunur.
5. Yalnız ilk sıralı genel IP'ye doğrudan sayısal socket açılır; işletim sisteminde yeniden domain çözülmez. SNI ve Host asıl domaindir, sertifika doğrulaması zorunludur. Ortam proxy değişkenleri kullanılmaz.
6. Hedefe yalnız HTTPS 443 üzerinde `HEAD /` gönderilir. Yönlendirme izlenmez; Location saklanmaz veya açılmaz. Gövde, betik, resim, başka port/URL ve GET geçişi yoktur. TLS hatasında doğrulamasız veya HTTP bağlantısına geçilmez.

Her bağlantı en fazla 8 saniye, bütün kontrol en fazla 25 saniyelik monotonic bütçeyi kullanır. Başlıklar toplam 16 KiB; DNS JSON 64 KiB, yanıt başına 32 kayıt ve son adreste 16 IP sınırı vardır. DNS gövdesi ve parça çerçevelemesi ayrıca toplam ağ baytı sınırıyla okunur. Byte akışı sürekli gelse bile toplam süre aşımı uygulanır. HEAD okuması gövdeyi önden okumaz. Tekrar deneme veya başka IP'ye geçiş yoktur.

HTTP/1.0–1.1 son durum satırı sıkı doğrulanır; eksik parça sonu reddedilir. `100 Continue` işlenir; `103 Early Hints` gibi başka ara yanıtlar bu sürümde başarısız/belirsiz kontrol oluşturur. DNS HTTPS erişimi başka ağlarda engellenebilir. Bu sınırlamalar nedeniyle yanıt alınmaması sitenin kapalı veya güvenli olduğu anlamına gelmez.

## Kayıt ve eski veriler

Şema 4 `finding_assessments` tablosunu ekler. Sonuçlar append-only saklanır; kullanıcı kararı ve `last_seen_at` değişmez. Son kontrol zaman metnine göre değil, ekleme sırasına göre seçilir. Duvar saati gerilerse kontrol kaybolmaz; güncellik değerlendirmesi tutarsız zamanı gösterir. Kaydın biçimi, boyutu, alanları ve bulgunun adresiyle ilişkisi okuma ve yazmada doğrulanır.

Şema 1/2/3 geçişi açık `migrate` ile yapılır. Yazma kilidi altında eski sürüm yedeği alınır, yalnız eksik tablolar transaction içinde oluşturulur. Hata geri alınır. Eski şema tablo kümeleri açıkça tanımlıdır. Yedekler ve boş konuma restore kontrol geçmişini de içerir. Eski uygulamaya dönüş geçiş öncesi yedekten yapılır.

Kontrol sırasında SQLite yazma transaction'ı tutulmaz. Terminal tarayıcıyla aynı yerel yürütme kilidini kullanır. Tamamlanan her bulgu ayrı atomik kayıttır. Kesinti önceki tamamlananları korur; yarım hedef kontrolünün ayrı kalıcı iş/ilerleme kaydı yoktur. Yeniden çalıştırmada kayıtlı denemeler kullanılır.

## Tekrar ve öncelik

Toplu kontrol en fazla 20 bulgu işler; varsayılan 10'dur. İzlenen ad seçimi tam varlık değerine göredir. Kapatılmış bulgular atlanır; son altı saatteki denemeler, başarısız olanlar dahil, yeniden sorgulanmaz. Kullanıcı tek kimlikle hemen yeniden kontrol edebilir. Aynı turdaki aynı domain için tek ağ sonucu ilgili bulgulara ayrı bağlanır. Kalan aday sayısı görünürdür.

Öncelik her okumada hesaplanır: kullanıcı tarafından şüpheli seçilmiş veya güncel doğrulanmış HTTPS yanıtı olan aday `soon`; diğer açık aday `review`; kullanıcının kapattığı `archived`. Gerekçeler, güncellik ve `review-priority-v1` sürümü birlikte görünür. Bu bir olasılık, önem derecesi veya tehdit skoru değildir. Kaynak sayısı bağımsız tehdit teyidi sayılmaz. Eski/gelecek tarihli kanıt güncel erişim iddiası oluşturmaz. Kullanıcı kararı otomatik değiştirilmez.

## Rapor

`FindingReportService` bulguyu, kaynakları, kararları ve kontrolleri tek veritabanı okuma transaction'ından alır. Rapor formatı `xti-finding-report`, sürümü 1'dir; üretim zamanı, o andaki açıklamalı öncelik ve kapsam sınırlamaları içerir. JSON kontrol karakterleri kaçırılır. Dosya en fazla 8 MiB; aynı klasörde 0600 geçici dosyaya yazılır, fsync sonrası üzerine yazmayan hard-link ile yayımlanır. Başarısız yazı kısmi rapor yayımlamaz. Dosya imzası, dış teslim, bildirim veya STIX/TAXII iddiası yoktur.

## Doğrulama ve kaynaklar

Testler özel IP/DNS yeniden bağlama, iki adres ailesi, CNAME, TLS, yönlendirme/gövde, yavaş/bozuk HTTP, zaman/boyut sınırları, altı saatlik tekrar, karar koruma, eşzamanlı tutarlı rapor, migration rollback ve üzerine yazmama davranışını kapsar. Gerçek ağ doğrulaması kontrollü `example.com` ile ayrıca yapıldı; test adayının tehdit olduğu iddia edilmedi. Güncel sonuçlar [STATUS.md](../STATUS.md) içindedir.

- [Google Public DNS JSON API](https://developers.google.com/speed/public-dns/docs/doh/json)
- [Python 3.11 TLS](https://docs.python.org/3.11/library/ssl.html)
- [Python 3.11 HTTP istemcisi](https://docs.python.org/3.11/library/http.client.html)
- [RFC 9112 HTTP/1.1 mesaj biçimi](https://www.rfc-editor.org/rfc/rfc9112.html)
