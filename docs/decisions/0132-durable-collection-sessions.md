# 0132 — Kaynak kanıtına bağlı toplama oturumları

**Durum:** Kabul edildi · **Tarih:** 14 Kasım 2026 · **Uygulama:** 0.132.0

Toplama sırasında bir kaynak tamamlanıp sonraki kaynakta kesinti yaşanabilir.
Üst seviyede yalnız komut sonunda kayıt yazmak, tamamlanan bir izlemenin
yeniden çalışmasına yol açar. Kaynak sonucu ile tamamlanma bağlantısı aynı
SQLite transaction'ında yazılmalıdır.

Şema 56, `collection_sessions`, `collection_session_steps` ve
`collection_step_receipts` tablolarını ekler. İlk oturum tam seçim ve
çözümlenmiş hedefleri, çalıştırıcı/kaynak sözleşmelerini ve varsa kaynak profil
revizyonunu dondurur. Sonuç bağlantıları yabancı anahtarlarla gerçek kaynak
çalışmasına bağlanır. Sayaçlar kaynak kayıtlarından çıkarılır; üst seviyede
başarı veya kaynak kimliği uydurulmaz.

Kaynak servisleri isteğe bağlı bir `operation` kimliği geçirir. SQLite
adaptöründeki küçük ortak yardımcı, kaynak yazımıyla aynı işlemde oturum
adımını tamamlar. Kaynak veya bağlantı yazılamazsa ikisi de geri alınır.
Token yokken bağımsız komutların mevcut davranışı korunur. Domain/uygulama
katmanlarına SQLite bağlantısı taşınmaz. Toplamaya ait scan işleri genel
kuyruk işçisi tarafından sahiplenilemez; sahiplik enqueue ile atomiktir.

Her ransomware yenilemesi ve her izleme üyesi ayrı adımdır. Bir üye
tamamlandıktan sonra süreç kapanırsa tamamlanma bağı korunur. Devam komutu
yalnız eksik üyeleri çalıştırır ve onlar için yeni bir başarılı kaynak
yenilemesi ister. Tamamlanan üyeler yeni yenileme nedeniyle tekrar edilmez.
Kaynak yenilenemezse eksik üyeler atlanır; eski snapshot kullanılmaz.

`collections resume ID` eski sonucu değiştirmez; ona bağlı yeni bir yürütme
açar. Yalnız zincirin son halkası sürdürülebilir. Eski başarılı sonuçlar kendi
kimlik ve zamanlarıyla görünür. Eksik işin tanımı veya kaynak sözleşmesi ya da
kaynak profil revizyonu değişmişse çalışma başlamaz. Tamamlanmış üyenin eski
kanıtı güncel isim/tanıma göre yeniden yorumlanmaz.

Ortak çalışma kilidi alınmadan kurtarma/yazma yapılmaz. `collections recover`
kesilmiş oturumları ve onlara ait açık scan işlerini kanıtı koruyarak kapatır.
Kaynak sonucu var ama üst kapanış yoksa başarı bağlantısı kaybolmaz. Yarım
temel kaynak işi baştan alınabilir; ağ çağrıları için exactly-once garantisi
verilmez. Tamamlanmış sonuç bağı bulunan izleme tekrar edilmez.

`collections list/show` ve `resume --plan` ağsız/yazmasızdır. Geçmiş görünümü
yeni analiz üretmez. Devam sonunda gösterilen analiz güncel yerel kanıttan
oluşur ve eski oturum snapshot'ı olarak sunulmaz. Analiz hatasında kaynak
sonuçları korunur; yalnız analiz eksikse yeniden kaynak isteği yapılmaz.

Geçiş açık `migrate` komutuyla ve önce geri dönüş yedeği alınarak yapılır.
Eski bağımsız kaynak çalışmaları için geçmişe dönük toplama oturumu uydurulmaz.
Plan/özet/durum/bağlantı denetimleri, rollback, kesinti, profile değişimi,
kaynak hatası ve yedekten geri dönüş testleri kabul kapsamındadır.
