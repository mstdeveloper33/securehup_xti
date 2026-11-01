# ADR-0020 — Pasif keşif geçmişi ve birleşik yerel bildirim kutusu

**Tarih:** 29 Ekim 2026 · **Durum:** 0.20.0'da uygulandı.

## Karar

Her `surface discover` çağrısı tamamlandı, kısmi veya başarısız sonucuyla kalıcı bir çalışma kaydı oluşturur. Kayıt; kök varlığı, crt.sh kaynak adresini, başlangıç/bitiş zamanını, kaynak kapsam sayaçlarını, uyarı veya hatayı ve aday/kanıt sonuçlarını taşır. Kaynak hatası başarılı boş sonuç sayılmaz.

İlk kez oluşturulan her pasif alt alan adı adayı için yerel kutuya tam bir bildirim eklenir. Aynı adayın yeniden görülmesi veya yeni sertifika kanıtı alması ikinci bildirim üretmez ve mevcut okundu bilgisini değiştirmez. Aday kararı ile bildirim okundu durumu birbirinden bağımsızdır.

Mevcut bulgu bildirim tablosu değiştirilmez. Pasif aday bildirimleri ayrı `surface_candidate_notifications` tablosunda tutulur; terminal adaptörü iki tabloyu tek kutu olarak okur. İki yazma yolu, her iki tablonun en büyük değerini dikkate alan ortak ve artan sıra numarası ayırır. Böylece eski bulgu bildirimlerinin kimliği ve okundu zamanı korunur; farklı kayıt türleri kararlı biçimde birlikte sayfalanır.

Başarılı/kısmi keşifte aday, kaynak kanıtı, ilk bildirim ve `surface_discovery_runs` özeti aynı `BEGIN IMMEDIATE` işlemi içinde yazılır. Geç doğrulama veya kayıt hatası bütün değişiklikleri geri alır. Başarısız kaynak çağrısı yalnız başarısız çalışma kaydı üretir; aday veya bildirim üretmez.

`surface runs KÖK` ve `surface run KİMLİK` salt okunurdur. `inbox list/show` bulgu ya da aday ayrıntısını aynı okuma anlık görüntüsünden getirir; yalnız açık `inbox read/unread` komutu okundu bilgisini değiştirir.

## Sınırlar

Bu bildirim yalnız yerel terminal kutusundadır; e-posta, SMS veya masaüstü teslimi değildir. Başarısız keşif için kutu bildirimi gönderilmez, ancak çalışma geçmişindeki hata korunur. Aday bildirimi sahiplik veya tehdit kararı vermez ve aktif hedef bağlantısına izin sağlamaz.

## Geçiş ve kurtarma

Şema 12, `surface_discovery_runs` ve `surface_candidate_notifications` tablolarını ekler. Şema 11 ve öncesi açık `migrate` komutuyla, yazma kilidi altında ve özgün sürüm yedeği alındıktan sonra yükseltilir. Eski adaylardan geriye dönük çalışma veya bildirim uydurulmaz. DDL ya da bütünlük hatası işlemi geri alır; kurtarma yedeği eski, doğrulanabilir düzende kalır.
