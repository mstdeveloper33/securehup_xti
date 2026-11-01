# 0113 — Sınırlı ön plan sosyal kullanıcı adı izlemesi

**Tarih:** 31 Ekim 2026  
**Durum:** Kabul edildi  
**Sürüm:** 0.115.0

## Bağlam

Tekil ve toplu sosyal kullanıcı adı çalışmaları açık komutla bir kez
çalışıyordu. Kişisel kullanımda kısa süreli değişiklik takibi için komutu elle
tekrarlamak gerekiyordu. Kalıcı daemon veya sık kontrol ise dış platformlara
öngörülemez trafik, gizli çalışma ve kişisel bilgisayarda yönetim yükü
getirebilirdi.

## Karar

`brand watch-monitor IZLEME_KIMLIGI`, yalnız tek etkin izlemeyi terminal açıkken
tekrarlar. Varsayılan üç tur, 3600 saniye aralık ve 86400 saniyelik yeni-tur
başlatma bütçesidir. Kabul edilen sınırlar 1–1000 tur, 300–86400 saniye aralık,
1–604800 saniye bütçe ve platform başına 5–30 saniye istek süresidir. Bütün
sınırlar ve izleme durumu ilk kaynak çağrısından önce doğrulanır.

Süre bütçesi monoton saatle ölçülür. Saat sonlu değilse veya gerilerse işlem
güvenli biçimde durur. Süre dolması başlamış Maigret sürecini başarılı ya da
başarısız diye zorla yeniden sınıflandırmaz; yalnız yeni tur başlatmayı engeller.
Bekleme en fazla bir saniyelik parçalara bölünür, böylece `Ctrl+C` gecikmeden
işlenebilir.

Her tur mevcut `BrandUsernameWatchService.run` yolundan geçer ve ayrı atomik
çalışma kaydıdır. Kaynak hatası boş sonuç veya hesap kaldırılması sayılmaz;
başarısız çalışma olarak saklanır ve bütçe kalırsa sonraki tur denenir.
Depolama/bütünlük hatası akışı durdurur, tamamlanan önceki turları geri almaz.

CLI monitor ömrünün tamamında ortak yerel çalışma kilidini tutar. En az bir
kaynak hatası içeren tamamlanmış rapor çıkış kodu 3 ve JSON `ok:false` üretir.
`Ctrl+C` komut düzeyinde 130 ile çıkar; önceden tamamlanan tur kayıtları kalır.

## Sonuçlar

- Kullanıcı terminal açıkken sınırlı süreli değişiklik takibi yapabilir.
- Kaynak kesintisi hesap yokluğu veya güvenlik hükmüne dönüşmez.
- İlk başarılı çalışma ve sonraki fark kuralları tekil akışla aynı kalır.
- Tamamlanan turlar kesinti ve süre bitiminde korunur.
- Bulunan profil otomatik taklit kararı veya bildirim oluşturmaz.
- Kalıcı monitor oturumu, zamanlayıcı, daemon veya açılış görevi kurulmaz.
- Yeni tablo eklenmez; şema 49 değişmez.

## Doğrulama

İki turlu profil değişimi, kaynak hatasından sonraki başarılı tur, süre
bütçesinde yeni turun engellenmesi, `Ctrl+C` sırasında tamamlanan kanıtın
korunması, geri çekilmiş tanım, geçersiz sınırlar, bozuk monoton saat ve
terminal/JSON çıkış sözleşmesi sahte kaynaklarla sınanır. Otomatik testler
gerçek platformlara bağlanmaz. Tam kontrolde 1.276 test 221,261 saniyede
geçmiştir. Ayrı geçici canlı kabulde etkin GitHub `octocat` izlemesi bir tur
çalışmış, kaynak hatası olmadan ayrı çalışma kimliği üretmiştir. Kaynak o turda
profil bildirmediği için sıfır bulgu gösterilmiş; hesap yokluğu veya kaldırılma
hükmü üretilmemiştir. Kullanıcının ana veritabanı değiştirilmemiştir.
