# 0086 — Etkin CTI aramalarını sınırlı toplu yenileme

## Durum

30 Ekim 2026 tarihinde kabul edildi.

## Bağlam

Tek bir kayıtlı CTI araması açıkça veya ön planda tekrar çalıştırılabiliyordu. Kişisel kullanımda birden çok aramayı düzenli yenilemek için her kimliği ayrı ayrı komuta vermek gerekiyordu. Kalıcı işletim sistemi zamanlamasına geçmeden önce bütün etkin aramaları güvenli, görünür ve tek seferlik bir giriş noktasından çalıştırmak gerekiyor.

## Karar

`CtiSavedSearchBatchService`, etkin aramaları ad ve kimlikten oluşan mevcut kararlı sırayla alır. `max_searches + 1` kayıt okuyarak açık sınırın bütün etkin kapsamı içerdiğini yazmadan önce doğrular. Taşma varsa hiçbir arama başlatılmaz; böylece “tümü” komutu sessizce ilk sayfaya dönüşmez.

Her arama mevcut `CtiSavedSearchService.run` yoluyla ayrı çalıştırılır. Tanım tabanı, tam sonuç farkı, bildirim ve atomik depolama kuralları bu serviste yeniden uygulanmaz. Bir sonraki arama başarısız olursa önce tamamlanan bağımsız çalışma korunur. CLI toplu yürütmenin tamamında ortak yerel çalışma kilidini tutar.

Komut ağ erişimi, paralel yürütme, görünmez daemon, işletim sistemi görevi veya dış bildirim kanalı kurmaz. Geri çekilmiş aramalar kapsam dışıdır. Etkin arama olmaması başarılı sıfır çalışma raporudur. Şema 37 değişmez.

## Sonuçlar

Kullanıcı bütün etkin yerel CTI aramalarını `cti watch-run-all` ile tek sefer yenileyebilir. Komut kalıcı zamanlayıcının ileride çağırabileceği sınırlı ve tekrarlanabilir bir giriş noktasıdır. Kalıcı zamanlama, kaçırılmış çalışma telafisi, dış kanal teslimi, etiket ve avcılık notları ayrı teslimlerdir.
