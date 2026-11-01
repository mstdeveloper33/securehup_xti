# ADR 0045 — Tek CVE bütün doğrulanmış ürün envanterinde sınırlı taranacak

- **Durum:** Kabul edildi
- **Tarih:** 29 Ekim 2026

## Bağlam

Tek ürün incelemesi kanıt modelini doğrular; ancak yeni bir CVE geldiğinde kullanıcı hangi kayıtlı ürünlerin inceleme adayı olduğunu topluca görmelidir. Her ürün için bütün NVD CPE listesini yeniden taramak, ürün ve koşul sayısı büyüdükçe gereksiz maliyet yaratır.

## Karar

`vuln match-products CVE`, yerel NVD kaydını ve en fazla 10.000 etkin doğrulanmış ürünü tek salt-okunur anlık görüntüden alır. Bütün ürün satırları doğrulanır. CPE koşulları bir kez tür+üretici+ürün kimliğine ve yapı numarasına göre indekslenir; her ürün yalnız kendi koşulları ve ilgili `AND` bağlamıyla değerlendirilir.

Varsayılan görünüm kesin koşul ve elle inceleme adaylarını gösterir. `--all`, ürün koşulu veya kesin sürümü eşleşmeyenleri de ekler. Sonuç 1–500 ürünle, JSON'daki ürün başı koşul 1–20 ile sınırlıdır; toplam sayaçlar bütün doğrulanmış envantere aittir. Komut ağ, alarm, risk veya kalıcı maruziyet kaydı oluşturmaz.

## Sonuçlar

- Yeni CVE için yerel ürün envanterindeki inceleme kapsamı hızlıca görülebilir.
- Gizli/limit dışı bozuk satır sessizce atlanmaz.
- Aynı ürün kimliği için CPE ayrıştırma tekrarları azaltılır.
- Bu çıktı aday kuyruğudur; vaka yaşam döngüsü ve otomatik bildirim değildir.
