# 0013 — Sürümlü ve başlangıç davranışlı eşleştirme değerlendirmesi

**Tarih:** 29 Ekim 2026 · **Durum:** 0.13.0'da uygulandı.

## Sorun

Alan adı kurallarının birkaç pozitif örnekte çalışması, yanlış alarm ve kaçırma oranını göstermez. Kurala yeni sözcük veya benzerlik eşiği eklemek bazı adayları yakalarken ilgisiz adresleri de incelemeye taşıyabilir. Yalnız bütün testlerin geçmesi kalite açığını görünmez yapabilir; yalnız toplam başarı oranı ise hangi davranışın değiştiğini açıklamaz. Gerçek olay etiketi bulunmadan sentetik sayıları ürün doğruluğu gibi sunmak da yanıltıcıdır.

## Karar

Uygulamayla birlikte `domain-evaluation-v1` adlı, SHA-256 özeti sabitlenmiş sentetik veri kümesi dağıtılır. Her örnek tekil kimlik, kategori, izlenen adres, aday adres, açıklama, istenen sonuç ve kayıtlı başlangıç sonucu taşır. İstenen sonuçlar:

- `review`: sözcüksel kuralların insan incelemesine göndermesi beklenir.
- `ignore`: sözcüksel kuralların bu örneği gereksiz alarma çevirmemesi beklenir.

Bu etiketler kötü niyet, phishing, sahiplik veya erişilebilirlik kararı değildir. Kümede gerçek kişi sırrı veya özel kaynak verisi yoktur.

Değerlendirme üretimdeki `DomainMatcher`, paketlenmiş Public Suffix List ve Unicode profilini kullanır. Ayrı bir test eşleştiricisi yazılmaz. Servis doğru yakalama, doğru eleme, yanlış pozitif ve yanlış negatif sayılarından precision, recall, yanlış alarm oranı ve toplam doğruluğu hesaplar. Kategori özetleri ve hatalı örnek kimlikleri rapora eklenir.

Her örneğin `baseline` alanı 0.13.0 kuralının beklenen fiili çıktısını sabitler. Tahmin istenen etiketten farklı fakat baseline ile aynıysa bilinen kalite açığı görünür kalır. Tahmin baseline'dan farklıysa sonuç kalite beklentisine yaklaşmış olsa bile davranış değişimi ayrıca raporlanır. Otomatik test başlangıç davranışından habersiz sapmayı engeller; bilinçli kural değişiminde ilgili örnekler, kural kimliği, veri kümesi sürümü ve özeti açıkça değerlendirilir.

## Veri ve hata sınırı

Paketli JSON en fazla 256 KiB/1000 örnektir. Kök ve örnek alanları tam eşleşmeyle doğrulanır; bilinmeyen alan, etiket, tekrarlı kimlik, kontrol karakteri, bozuk UTF-8/JSON veya SHA-256 farkı tüm raporu durdurur. Kısmi metrik verilmez. `evaluate` internet bağlantısı, veritabanı, kayıt klasörü veya worker kilidi kullanmaz. İnsan ve JSON çıktısı aynı rapor modelinden gelir.

## İlk ölçüm

44 örnekte 27 `review`, 17 `ignore` beklentisi vardır. 0.13.0 başlangıç kuralı 25 doğru pozitif, 14 doğru negatif, 3 yanlış pozitif ve 2 yanlış negatif üretir. Etiket kümesi precision `%89,29`, recall `%92,59`, yanlış alarm oranı `%17,65` ve toplam doğruluk `%88,64` verir. Beş hata bilinen açık olarak kimlikleriyle korunur; baseline değişimi yoktur.

## Sonuçlar ve sınırlar

- Kural değişikliğinin kazanç ve kaybı tekrarlanabilir biçimde görünür.
- Bilinen açıklar testi geçirmek için beklentiden silinmez.
- Küme küçük ve sentetiktir; canlı internet, kaynak recall'ı veya gerçek tehdit prevalansı hakkında istatistiksel sonuç vermez.
- Veri kümesine aşırı uyum, gerçek yanlış alarmı azaltmayı garanti etmez. Canlı kullanım geri bildirimi ayrı kaynak/provenance ve sürümle eklenmelidir.
- Precision/recall yalnız mevcut etiket kümesine aittir; pazarlama veya ürün performansı iddiasında kullanılamaz.
- Şema değişmez; 0.12.0 şema 8 kayıtları migration olmadan kullanılabilir.

## Sonraki karar

0.14.0'da iki bilinen kaçırma dar kurallarla giderildi, üç negatif koruma eklendi ve güncel paket `domain-evaluation-v2` olarak sürümlendi. Bu belgedeki v1 ölçümü tarihsel başlangıç noktasıdır; yeni karar ve sonuçlar [0014 — Ölçümlü dar kural genişletmesi](0014-bounded-rule-expansion.md) içinde tutulur.
