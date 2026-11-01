# 0059 — Maruziyet kuyruğunda düzeltme ve kontrol vadesi bağlamı

## Durum

Kabul edildi — 30 Ekim 2026.

## Bağlam

Düzeltme planları ayrı komutla listelenebiliyordu; ancak analistin ana maruziyet
kuyruğunda hangi incelemenin planı olduğu ve kontrol tarihinin gelip gelmediği
görünmüyordu. İki ayrı ekran takibin atlanmasına yol açabilir.

## Karar

- Maruziyet kuyruğu seçili incelemeleri, kaynak bağlamını, etkin destek kanıtlarını
  ve ilgili bütün düzeltme planlarını aynı salt-okunur SQLite transaction'ında alır.
- İptal edilmemiş plan sayısı, plan durumları, son kontrol sonuç kümeleri ve kontrol
  tarihi gelmiş plan sayısı her kuyruk satırında gösterilir.
- Kontrol tarihi gelmiş plan `remediation_recheck_due` dikkat nedenini ekler ve kaydı
  en az `high` bandında tutar. Daha güçlü KEV/ransomware/insan kararı nedenleri
  `immediate` bandını koruyabilir.
- Planın veya kontrol sonucunun varlığı insan maruziyet durumunu değiştirmez.
  `not_observed` otomatik `fixed`, `still_present` otomatik `affected` olmaz.
- İptal planlar sayılara katılmaz fakat seçili incelemeye ait bütün plan satırları
  doğrulanır. Bozuk gizli/iptal kayıt kısmi kuyruk sonucuyla saklanmaz.
- Kuyruk en fazla 10.000 düzeltme planını doğrular. Ağ isteği veya yazma yapmaz;
  yeni tablo eklemez ve şema 25'i korur.

## Sonuçlar

Analist ana çalışma kuyruğunda kaynak riski ile düzeltme takibini birlikte görebilir.
Bu bağlam bir risk puanı, tarayıcı sonucu veya otomatik kapanma mekanizması değildir.
Laboratuvar kapanma/yeniden açılma kabulü ve süreli bastırma politikası ayrı kalır.
