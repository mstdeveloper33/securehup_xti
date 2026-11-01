# ADR 0068 — Salt-okunur NVD boşluk planı

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

Kapsama görünümü hangi zamanların açık kaldığını gösteriyordu fakat kullanıcı her boşluğu elle en fazla yedi günlük NVD pencerelerine bölmek zorundaydı. Geniş dönemlerde bu işlem hata üretmeye, arada zaman bırakmaya veya aynı dönemi gereksiz yere yeniden seçmeye açıktı. Buna karşılık doğrudan çok sayıda ağ isteği başlatmak, kişisel ve ücretsiz kullanım için görünmez maliyet ve uzun süren işlem yaratırdı.

## Karar

`vuln nvd-window-gap-plan` en fazla 366 günlük mevcut kapsama raporunu kullanır. Her açık yarı-açık zaman aralığını başlangıçtan itibaren kronolojik olarak en fazla yedi günlük parçalara böler; son parça daha kısa olabilir. Tamamlanmış zamanlar hiçbir adaya girmez.

Her parça mevcut `NvdWindowRepository.plan` okumasından geçirilir. Böylece aynı başlangıç, bitiş ve sayfa boyutuyla daha önce yarım kalmış veya hata almış pencerenin kalıcı imleci, toplamı ve hata bilgisi yeni bir iş gibi gizlenmez. Başka sınırlarla örtüşen kısmi pencereler otomatik olarak birleştirilmez veya yeniden yazılmaz.

Sayfa boyutu 1–100, gösterim sınırı 1–100 arasındadır. Sonuç bütün aday sayısını, gösterilen sayıyı ve kesilme durumunu ayrı taşır. Tam kapsanmış dönem sıfır adaylı geçerli plandır.

Komut yalnız salt-okunur kapsama ve plan işlemleri yapar. Ağ isteği göndermez, pencere satırı oluşturmaz, imleç ilerletmez, CVE yazmaz ve adayları çalıştırmaz. Çalıştırma için kullanıcı bir adayı açıkça `nvd-window-fetch` komutuna verir. Yeni tablo yoktur; şema 31 korunur.

## Sonuçlar

- Kullanıcı tarih hesabı yapmadan eksik dönemleri güvenli ve tekrarlanabilir parçalara ayırabilir.
- Planın büyüklüğü ağdan önce görünür olur ve `--limit` nedeniyle gizlenen aday sayısı kaybolmaz.
- Aynı tam kimlikteki başarısız/yarım pencere kaldığı yerle görünür.
- Farklı sınırlarla örtüşen kısmi pencereleri en az çağrıyla uzlaştırma bu dilimin kapsamı değildir; CVE yazımı zaten tekilleştirilse de kaynak çalışması tekrarı oluşabilir.
- Çoklu pencere yürütmesi, hata durdurma politikası ve zamanlama ayrı bir sonraki karardır.
