# 0174 — Yayıncı metni, değişen ilişki kanıtı ve kayıpsız günlük saklama

- Tarih: 19 Kasım 2026
- Durum: Uygulandı; yerel kabul sonuçları ayrı kayıtta.
- Sürüm: 0.169.0 / çekirdek 79. Önceki çekirdek 78; kuyruk 3 korunur.

## Karar

`ReportService` yayıncı alımını küçük `PublisherDocumentSource` portuyla
yapar. Yayıncı URL/lisans/çıkarım kuralları saf domain katmanında, HTTP,
HTML/PDF ve nesne saklama somut adaptörlerdedir. İzinli ilk kapsam CERT-FR
ve NCSC'dir. Ağ çağrısı engine okuma girişine taşınmaz. Kaynak işi v4'e
serbest URL çalıştırma adımı eklenmez; açık `reports.fetch` işletici/firma
yazması kullanılır.

HTML için stdlib `HTMLParser`, PDF için BSD-3-Clause pypdf 7.1.1 seçildi.
PDF parser'ı ayrı, süre/çıktı sınırları olan süreçte çalışır; Linux adres
alanı sınırı eklenir. Süreç ayrımı tek başına OS sandbox'ı değildir;
pypdf dış kaynak veya PDF JavaScript çalıştırmaz. İşletim ayrı yetkisiz
kullanıcı/container gibi platform kontrolleriyle güçlendirilebilir.

Yeni belge modeli 2, metinle birlikte alım politikası, yönlendirme zinciri,
MIME, özgün nesne hash'i, ayrıştırıcı ve atıf/lisans bilgisini korur.
Model 1 ve dondurulmuş araştırma kayıtları yeniden yorumlanmaz. Özgün
belgenin `publisher-text-v1` politikası sürümlü okuma kaydında korunur;
ileride kurulum pin'i veya aktif yayıncı allowlist'i değişse de eski
belge/makbuz okuması o tarihî politikayı kullanır. Yeni GET isteği yalnız
güncel kapsamdan geçer; tarihî kapsam yeni ağ erişimi yetkisi vermez. Özgün
HTML/PDF nesnesi ayrı hash anahtarıyla sıkıştırılır; başarılı belge,
nesne ve alım makbuzu tek transaction'da kaydedilir. Başarısız alım ayrı
makbuzdur; belgeye yazmaz. Tekrar anahtarı ağdan önce kontrol edilir.
İstek/nesne/makbuz ilişkileri okuma sırasında doğrulanır.

İlişki yeniden inceleme listesi kalıcı ikinci karar tablosu değildir.
Mevcut insan kararını aynı read transaction'daki güncel dayanakla
karşılaştıran projeksiyondur. Karar listesi üzerinde en fazla 20 kayıtlık
pencere ve kök başına paylaşılan araştırma hesabı vardır. Karar kesiti
sayfaları korur; her pencerenin kanıt kesiti ayrıca görünür. Kısmi
görünümde eksik aday kesin geri çekme sayılmaz. Çözüm önceki karar
servisine güncel kanıt hash'i ve revision ile yeni insan kararıdır.

Rapor/kanıt günlüklerindeki eski gövdeler aynı veritabanındaki sıkıştırılmış
nesnelere taşınır. Mantıksal günlük satırı, hash zinciri, sıra ve tekrar
anahtarları korunur. Okuma bütçesi özgün boyuttan hesaplanır. Arşiv
işleminin kendisi eklemeli, zincirli olay günlüğüdür; durum projeksiyonu
soğuk gövdelerle karşılaştırılır. Plan ilgili DB yoluna/günlük zincirlerine
bağlıdır. Uygulama/geri alma önce yedek alır, sonra tek transaction'da
taşır; kayıp/bozuk gövde ve eski plan reddedilir. Kaynak nesneleri ve
arşiv standart SQLite/platform yedeğinin içindedir.

Bu yaklaşım restore/taşınabilirlik ve tarihî başvuruları basit tutar.
Mantıksal satır kapasiteleri kaldırılmaz; disk dosyasının hemen küçülmesi,
otomatik backup silme, sınırsız kalıcı depolama veya PostgreSQL geçişi
iddia edilmez. Büyük hacim için ayrı arşiv deposu/indeks tasarımı sonraki
ölçülmüş gereksinime bağlıdır.

## Kaynaklar ve kabul

- [CERT-FR içerik koşulları](https://cert.cyber.gouv.fr/mentions-legales/)
- [NCSC içerik koşulları](https://www.ncsc.gov.uk/section/about-this-website/terms-and-conditions)
- [pypdf 7.1.1](https://pypi.org/project/pypdf/7.1.1/)
- [pypdf lisansı](https://github.com/py-pdf/pypdf/blob/7.1.1/LICENSE)
- [PDF metin çıkarımının sınırları](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
- [Kullanım/alanlar/sınırlar](../PUBLISHER_REVIEW_RETENTION.md)
- [Kabul kaydı](../ACCEPTANCE_REVIEW.md)
