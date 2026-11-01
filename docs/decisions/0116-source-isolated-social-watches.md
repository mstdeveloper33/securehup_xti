# 0116 — Kaynak-yalıtımlı kalıcı sosyal kullanıcı adı izlemeleri

**Durum:** Kabul edildi  
**Tarih:** 31 Ekim 2026  
**Sürüm:** 0.118.0

## Bağlam

Maigret kalıcı izlemeleri sessiz başlangıç, fark, kaynak hatası ve tam profile
bağlı insan kararı taşıyordu. Sherlock ise 0.117.0'da aynı veri-minimizasyon
sözleşmesiyle yazmasız önizlemeye ulaştı. İki kaynağın sonucu aynı izleme
zincirine yazılırsa bir kaynağın kapsamadığı platform diğer kaynakta “artık
raporlanmadı” gibi görünebilir ve yanlış fark üretebilir.

## Karar

- Her kalıcı sosyal izleme `maigret` veya `sherlock` kaynak anahtarına
  oluşturulurken bağlanır. Kaynak aynı yerel izleme adı altında değiştirilemez;
  ikinci kaynak için farklı izleme adı gerekir.
- Kaynak, mevcut tanım özetine eklenmez. İzleme kimliği içinde değiştirilemez
  ayrı alan olarak tutulur. Böylece mevcut Maigret tanım özetleri, çalışma
  zincirleri, profil aday kimlikleri ve insan kararları yeniden yazılmaz.
- Her kaynak yalnız kendi incelenmiş platform listesini kabul eder. Maigret ve
  Sherlock platformları aynı izleme içinde karıştırılamaz. Profil adresi,
  platforma ait HTTPS host listesiyle doğrulanır.
- Tekil, toplu ve ön plan izleme kayıtlı kaynak kimliğini okuyup yalnız ilgili
  adaptörü çalıştırır. Kaynak üst bilgisi izlemeyle uyuşmazsa çalışma atomik
  olarak reddedilir.
- Aynı kullanıcı adı iki kaynakta iki ayrı izlemeyle çalışabilir. İlk başarılı
  sonuçların ikisi de kendi sessiz başlangıcıdır; başarılı/başarısız geçmiş ve
  fark zincirleri birbirine bağlanmaz.
- Sherlock sonuçları mevcut tam-profil insan kararı ve yalnız
  `possible_impersonation` kararından bildirim üretme kurallarını değiştirmeden
  kullanır. Bir kaynakta verilen karar diğer kaynağın profiline taşınmaz.
- Şema 49→50 geçişi mevcut bütün izlemelere `maigret` kaynak anahtarını ekler.
  Çalışma, öğe, karar ve bildirim satırları değiştirilmez. Geçiş önce şema 49
  yedeğini yayımlar ve hata halinde transaction'ı geri alır.

## Sonuçlar

Kullanıcı Sherlock'u yalnız geçici önizleme olarak değil, kalıcı ve
karşılaştırılabilir izleme olarak kullanabilir. Karma `watch-run-all` her
izlemeyi doğru adaptöre yollar. Kaynak kesintisi yine hesap yokluğu değildir;
ilk çalışma yine alarm değildir; bulunan profil yine sahiplik veya taklit
kanıtı sayılmaz.

Kaynak değişimi için yeni izleme adı zorunluluğu kullanıcıya küçük bir ek adım
getirir. Buna karşılık geçmişin anlamı sabit kalır ve iki aracın farklı ağ
davranışları tek bir fark zincirinde karışmaz.

## Kabul kanıtı

Otomatik testler aynı kullanıcı adının iki kaynakta bağımsız başlangıcını,
kaynak değiştirme reddini, kaynağa göre platform doğrulamasını, karma toplu
yönlendirmeyi, Sherlock çalışma/terminal/JSON yolunu, Sherlock tam-profil insan
kararını ve veri içeren şema 49 izleme/karar geçmişinin yedekli şema 50
geçişini kapsar. Testlerde internet ve kullanıcı veritabanı kullanılmaz.
