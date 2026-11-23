# 0186 — Firma ve tedarikçi içerik/kanal izlemesi

21 Kasım 2026. P02 / A01, A04, A12; A13/I04 için açık metin/dil kapsamı.

Mevcut haber, Tavily ve incelenmiş yayın metinleri korunur. Yeni modül,
kaynak tanımı ve kayıtlı firma kapsamı üzerinden bunları ve seçilmiş
kanalları birleştirir. Kimlik/yetki UI/backend tarafından sağlanır;
motor firma sınırı, kaynak kapsamı, kanıt/karar sürümü, tekrar ve kuyruk
kurtarmasından sorumludur. SQLite adaptörü iş kurallarından ayrıdır.

Kalıcı model: kaynak tanımı ve sürümü; izleme tanımı ve firma/tedarikçi
anlık kapsamı; kaynak başına cursor/erişim durumu; değişmez ilgili içerik
kanıtı; indeksli güncel eşleşme; insan kararı ve fark bildirimi. Ham HTTP
cevabı, oturum veya token kanıt/iş kayıtlarına yazılmaz. Aynı içerik yeniden kopyalanmaz;
aynı metnin farklı kaynaklarda olması tek başına bağımsız doğrulama değildir.
Kanal veya akıştan görünmez olmak silinme/giderilme anlamına gelmez.

Toplama kontrollü portlardan yapılır. Kamu HTTPS hedefleri DNS sonrası
sabitlenir, özel adresler ve kapsam dışı yönlendirmeler reddedilir.
Telegram/Discord girişleri yalnız gizli işletici yapılandırmasındadır.
IRC'de yalnız protokol kaydı/kanala katılma ve okuma vardır; sohbet mesajı
gönderme, dosya alma, kanal davetini aşma veya otomatik hesap açma yoktur.

Şema90 açık yedekli geçişle eklendi; eski kanıt ve vaka satırları
korunur. Sayfalama/kapasite/geri dönüş eşikleri uygulamadan önce
[P02 teslim kartında](../roadmap/P02_DELIVERY.md) belirlendi.
Kontrollü kanal testleri, gerçek hesapla kaynak kabulü değildir.

Telethon1.46.0 ve irctokens2.0.2 seçildi; sürümler ve resmî PyPI dosya
hash'leri kurulum listelerindedir. Kaynak paketli pyaes1.6.1, sabit
setuptools84.2.1 ile hazırlanır. Proje wheel'i temiz geçici kaynak ağacında
üretilir; önceki `build/egg-info` dosyaları yeni kurulum girdisi değildir.
Mevcut sanal ortam transaction yedeğinde korunur; hata/kesintide geri alınır.

Kaynak kimliği hash'lenir, metin ve URL aynı maskeleme kontrolünden geçer.
Araç yoksa URL/metin yayımlanmaz. Telegram/Discord her tur güncel pencereyi
önce okur; ayrı geçmiş cursor'u yeni mesajı bekletmez. Yeni tarihî kayıt
alarmı bastırılır; eski kanıttaki değişiklik yeniden inceleme üretir.
Firma yedeği kanıtları ve iş kayıtlarını içerir; erişim profilleri ayrıca
yapılandırılır ve yedekle başka alana taşınmaz.

Bildirim sırası ve genel toplamlar aynı sabit tablo kataloğunu kullanır;
yeni içerik/kod bildirimleri durum özetinden düşmez. Yalnız izlemeyi
kapatma işlemi saklı kapsamı korur ve güncel kaynağın erişilebilirliğine
bağımlı değildir; sürüm, devam eden çalışma ve tekrar anahtarı denetimi
korunur. Yeniden açma güncel kaynak/hedef bağlarını doğrular.
