# 0112 — Etkin sosyal izlemeleri sınırlı toplu çalıştırma

**Tarih:** 31 Ekim 2026  
**Durum:** Kabul edildi  
**Sürüm:** 0.114.0

## Bağlam

Kalıcı sosyal kullanıcı adı izlemeleri tek tek çalıştırılabiliyordu. İzleme
sayısı arttığında her kimliği elle çağırmak hata ve unutma riski oluşturuyordu.
Ancak bütün kayıtları sessizce keserek çalıştırmak bazı markaları görünmez
bırakır; sınırsız yürütme ise dış platform çağrılarını ve çalışma süresini
öngörülemez yapardı.

## Karar

`brand watch-run-all`, yalnız etkin izlemeleri görünen adın kanonik anahtarı ve
kimlik sırasıyla bir kez çalıştırır. Varsayılan üst sınır 10, kullanıcının
açıkça seçebileceği en yüksek sınır 100'dür. Servis sınırdan bir fazla kayıt
okur; bütün etkin kapsam sığmıyorsa hiçbir kaynak çağrısı veya çalışma kaydı
başlatmadan durur. Geri çekilmiş tanımlar çalıştırılmaz.

Her izleme mevcut tekil `BrandUsernameWatchService.run` yolundan geçer. Böylece
Maigret taşıma sınırları, kaynak hatasının yokluktan ayrılması, son başarılı
temel, fark hesabı ve atomik kayıt davranışı yeniden yazılmaz. Bir `SourceError`
başarısız izleme çalışması olarak saklanır ve toplu akış sonraki tanıma geçer.
Depolama, bütünlük veya beklenmeyen uygulama hatası akışı durdurur; önce ayrı
transaction'da tamamlanan çalışmalar korunur ve sonraki izleme başlatılmaz.

CLI toplu yürütmenin tamamında ortak yerel çalışma kilidini tutar. İnsan çıktısı
ve JSON; planlanan, tamamlanan, başarılı ve kaynak hatalı izleme sayılarını ve
her çalışma kimliğini ayrı gösterir. En az bir kaynak hatası varsa komut çıkış
kodu 3, JSON `ok:false` üretir; tamamlanmış kayıtlar yine korunur.

## Sonuçlar

- Etkin izlemelerin hiçbiri sessizce atlanmaz.
- Kaynak kesintisi profil yokluğu veya hesap kaldırılması sayılmaz.
- Tek kaynak hatası bağımsız sonraki izlemeyi engellemez.
- Bütünlük hatası sonrasında yeni dış çağrı başlatılmaz.
- Bulunan profil otomatik taklit kararı veya bildirim oluşturmaz.
- Komut tek seferliktir; zamanlayıcı, daemon veya açılış görevi kurmaz.
- Yeni kalıcı toplu oturum modeli eklenmez; şema 49 değişmez.

## Doğrulama

Sabit sıra, geri çekilmiş tanımın dışlanması, boş kapsam, sınır taşmasında ağ ve
yazı öncesi durma, kaynak hatasından sonra devam, depolama hatasında önceki
kanıtı koruyup sonraki işi başlatmama, sınır doğrulaması ve terminal/JSON çıkış
sözleşmesi sahte kaynaklarla sınanır. Otomatik testler gerçek platformlara
bağlanmaz.

## Canlı kabul

31 Ekim 2026'da geçici şema 49 veritabanındaki tek etkin GitHub `octocat`
izlemesi `watch-run-all --watch-limit 10` ile çalıştırıldı. Komut kapsamı 1/1
olarak tamamladı ve ayrı çalışma kimliği kaydetti. Maigret bu turda profili
raporlamadığı için geçmişteki bulunan durum “artık raporlanmayan” olarak
ayrıldı; sistem bunu hesap yokluğu veya kaldırılma kararı yapmadı. Kullanıcının
ana veritabanı değiştirilmedi.
