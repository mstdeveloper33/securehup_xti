# 0185 — Kod ve paste maruziyetinin kaynak sınırları

21 Kasım 2026; P01 / A03 uygulaması başladı. Bu karar tamamlanmış kabul değildir.

GitHub/GitLab depo keşfi, genel kod araması ve Pastebin akışı ayrı kaynaklardır.
Kamu deposu keşfi tüm kodun arandığı anlamına gelmez. Her tur sorgu, taranan
dosya, kalan kapsam, erişim ve kota durumunu saklar. Erişim hatası boş sonuç
değildir. Kullanıcının şu anda API erişimi yoktur; bağımsız geliştirme sürer.

Hassas bilgi adayı için Betterleaks 1.10.1 (MIT) seçildi. Gitleaks 8.30.1
karşılaştırıldı; Betterleaks'in sürdürülen kural seti ve açık kapatılabilen
doğrulama/config seçenekleri tercih edildi. Yerel sentetik denemede her iki
araç GitHub/Google/generic ve eşlenmiş AWS örneklerini buldu, üç temiz örneği
işaretlemedi. Betterleaks tek AWS kimliğinde yakın secret bileşeni arar;
Gitleaks aynı kimliği tek başına aday sayar. Bu küçük örnekler genel doğruluk
oranı değildir. Bulunan credential hiçbir hizmette denenmez.

Araç stdin ile, özel boş dizin ve temiz ortamda çalışır. Validation, otomatik
depo config'i, arşiv açma kapalıdır. Kaynak kod çalıştırılmaz. Ham dosya ve
secret saklanmaz; yalnız sınırlı kaynak metaverisi, içerik özeti SHA256,
eşleşme kuralı/satırı ve maskeli kanıt saklanır. Araç çıktısı doğrudan kullanıcıya
aktarılmaz. Kurulum sürümü ve arşiv SHA256'sı sabittir; yükseltme açıktır.

İş kuralları domain'de; uygulama küçük depo/kaynak/tarama portlarına bağlıdır.
SQLite aynı firma alanında indeksli son durum + değişmez kanıt + işlem makbuzu
tutar. Tekrar anahtarı ağdan önce ayrılır. Aynı istek yeniden ağ oluşturmaz;
yarım işlem açık kurtarma ve yeni tekrar ile ilerler. Sonuç/fark/bildirim aynı
transaction'dadır. Eski karar eski kanıta bağlı kalır. Görülmeyen dosya silinmiş
sayılmaz. Aynı dosya tam okunabildiyse eşleşmenin artık görülmediği söylenebilir.

Kapasite kabul hedefi: macOS arm64 / yerel Python; iki firma, firma başına
100 depo/dosya kapsamı, 10.000 aday, 30 değişmeyen tur. Seçili 100 kayıtlık
okumalarda p95 < 2 sn, ölçülen süreç RSS < 256 MiB, iki firma toplam DB <
256 MiB, değişmeyen turlarda yeni kanıt gövdesi 0. Tur özetleri büyüyebilir.
İstek sınırı varsayılan 30, en fazla 100; dosya 256 KiB, tur 32 MiB;
süre 120 sn varsayılan/600 sn tavan. Bunlar tek isteğin bütçeleridir,
saklı geçmişi kilitleyen toplam kayıt sınırı değildir. Linux kabulü ayrıca
raporlanır. Eşik değiştirilirse gerekçesi ve eski sonuç korunur.

Şema geçişi açık/yedekli olacak; eski kayıtlar/kimlikler değişmeyecek.
Firma JSON mevcut workspace çitini ve yazıcı kilidini kullanır. API anahtarları
JSON veya veritabanına konmaz. Yetkili işletici gizli yerel girişle tanımlar.

Kaynaklar: [GitHub arama](https://docs.github.com/en/rest/search/search),
[GitLab arama](https://docs.gitlab.com/api/search/),
[GitLab depolar](https://docs.gitlab.com/api/repositories/),
[Betterleaks](https://github.com/betterleaks/betterleaks),
[Gitleaks](https://github.com/gitleaks/gitleaks),
[Pastebin scraping](https://pastebin.com/doc_scraping_api).
Pastebin'in güncel erişim/koşul sayfası bu ortamda zaman aşımına uğradı;
canlı erişimi ve ticari veri hakları doğrulanmış sayılmaz.
