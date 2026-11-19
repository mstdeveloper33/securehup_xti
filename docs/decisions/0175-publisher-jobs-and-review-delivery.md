# 0175 — Seçilmiş yayın işleri ve ilişki değişikliği teslimi

Tarih: 19 Kasım 2026. Durum: uygulandı ve tanımlı Linux kabulü tamamlandı.
[Kabul sonuçları](../ACCEPTANCE_REVIEW.md#01700--yayın-işleri-ilişki-bildirimi-ve-birikimli-kapasite):
3.211 testlik tam paket, kurulum/yükseltme, firma izolasyonu ve iki firmada
80 belge/160 sürümlük kapasite/kurtarma geçti. Bu ölçümün süre ve hacim
sınırları kabul kaydında korunur.

Kullanıcının onayladığı üç iş: HTML/PDF alımını mevcut kuyruğa bağlamak,
ilişki kanıtındaki değişikliği gelen kutusu ve vakaya taşımak, biriken
belgelerle kapasite ve kurtarma davranışını ölçmek.

- Ayrı kuyruk kurulmaz. Kaynak işi modeli 5, en fazla beş açıkça seçilmiş
  yayıncı belgesini ayrı adımlar halinde çalıştırır. Önceki modellerin
  planları ve sonuçları değişmeden okunur. Bir işin toplam altı adım sınırı
  korunur; belge genişlemesi bu sınıra plan aşamasında dahil edilir. Belge başına dört HTTP denemesi
  (ilk istek ve en fazla üç yönlendirme) ayrılır; toplam plan sınırı 32'dir.
  Mevcut kaynak planlarının 7 istek sınırı korunur. Süre/iptal adımlar
  arasında, taşıma ve PDF sınırları belgenin içinde uygulanır.
- Kalıcı yayıncı makbuzu ile kuyruk ilerlemesi farklı işlemlerdir. İkisi
  arasında kesinti olursa açık kurtarma/tekrar, aynı iş soyundaki başarılı
  makbuzu bulur. Başarısız makbuz yeni tekrar işinde yeniden denenebilir.
  Eski denemenin bilinmeyen istek sayısı sıfırmış gibi gösterilmez.
- İlişki bildirimi özgün insan kararı ve değişen kanıtın donmuş kopyasını
  taşır. Aynı karar sürümü ve aynı değişiklik tek bildirim üretir. Karar
  değiştirilmez; vakaya bağlantı kullanıcının açık işlemidir. Eksik kapsam
  nedeniyle kaybolmuş gibi görünen kanıt, kesin değişiklik diye bildirilmez.
- Çekirdek 80 geçişi yedekli/açık yapılır. Yeni bildirim kayıtları ve yeni
  vaka kanıt türü eski kanıt, günlük, kimlik ve hash'leri korur.
- Kapasite kabulü kontrollü HTML/PDF ile iki ayrı firma alanında yapılır.
  Ölçülen ortam, miktar, süre, bellek, disk, arşiv ve geri yükleme sonuçları
  yayımlanır. Kaynakların internetteki kapasitesi bu testten çıkarılmaz.

Mevcut yayıncı izin listeleri, lisans/atıf bilgileri ve veri sınırları
korunur; yeni ücretli bağımlılık eklenmez.
