# 0022 — Onaylı kökte sınırlı e-posta DNS temel kaydı

**Durum:** Kabul edildi · **Tarih:** 29 Ekim 2026 · **Sürüm:** 0.22.0

## Bağlam

Kullanıcı kendi kök alan adının e-posta yönlendirmesi ve yayımlanmış SPF/DMARC politikası değiştiğinde bunu terminalden görmek istiyor. Bütçesiz kişisel aşamada ücretli e-posta güvenliği servisi veya ayrı arama kümesi kurmak uygun değil. DNS'te DKIM kaydı ise seçici adı bilinmeden güvenli ve sonlu biçimde bulunamaz.

## Karar

Özellik mevcut açık `surface approve` kapsamını kullanır. `surface mail check KÖK` yalnız etkin, kayıtlı ve tam kök için Google Public DNS'in doğrulanmış HTTPS JSON uç noktasına üç sorgu gönderir:

- kök ad için MX;
- kök ad için TXT, sonuçtan yalnız `v=spf1` kaydı;
- `_dmarc.KÖK` için TXT, sonuçtan yalnız `v=DMARC1` kaydı.

DKIM seçicisi tahmin edilmez. Alt alan adı taraması, zone transferi, e-posta gönderimi, SMTP bağlantısı ve teslim testi yapılmaz. Her sorgu ayrı sonuç verir; birinin ağ/yanıt hatası diğer iki kanıtı silmez. `missing` ve `nxdomain` tamamlanmış gözlemdir; yalnız `failed` kısmi/başarısız komut sonucudur.

İlk sonuç `baseline`, aynı kanonik kayıt kümesi `unchanged`, MX/SPF/DMARC durum veya kayıt farkı `changed` olur. Zaman, açıklama ve geçici hata metni durum özetine katılmaz. Birden fazla SPF/DMARC kaydı saklanıp gösterilir ancak otomatik yanlış yapılandırma veya güvenlik hükmüne çevrilmez.

Ağdan önce kapsam doğrulanır ve bütün kontrol ortak yerel çalıştırıcı kilidi içinde yürür. Sonuç yazılırken etkin kapsam aynı SQLite transaction'ında yeniden doğrulanır. Kapsam arada kaldırılmışsa sonuç kaydedilmez. Sonuçlar eklemeli, sınırlandırılmış JSON ve durum SHA-256 özetiyle `surface_mail_checks` tablosunda tutulur. `surface mail show` salt okunurdur.

## Veri geçişi

Şema 13 yeni e-posta DNS kontrol tablosunu ve kapsam indeksini ekler. Şema 12 ve öncesi açık `./xti migrate` ister. Geçiş yazma kilidi altında önce özgün sürümün doğrulanmış yedeğini alır; eski bütün satırları korur ve yeni tabloyu boş başlatır. DDL, doğrulama veya bütünlük hatası ana veritabanını eski sürümde bırakır. Geçmiş veriden e-posta DNS kontrolü uydurulmaz.

## Sonuçlar ve sınırlar

Bu dilim ücretli API anahtarı ve ek Python paketi gerektirmez; kamu DNS hizmetinin erişilebilirlik ve koşulları dış bağımlılıktır. Kullanıcı komutu olmadan otomatik kontrol yoktur. Sonuç; e-posta teslim garantisi, teknik sahiplik doğrulaması, spoofing'in bütünüyle engellendiği, DMARC raporlarının işlendiği veya alanın güvenli olduğu anlamına gelmez. DKIM, MTA-STS, TLS-RPT, BIMI, SMTP/TLS teslim gözlemi ve DMARC toplu rapor analizi ayrı, açıkça kapsamlandırılacak dilimlerdir.
