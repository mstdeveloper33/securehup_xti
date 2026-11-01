# Karar 0004 — Kalıcı Arama İşleri ve Deneme Geçmişi

**28 Ekim 2026 · 0.4.0 içinde uygulandı.**

0.5'te kaynak başına ayrı işler ve yeni genel JSON sayım alanları [0005 ikinci kaynak kararı](0005-independent-archive-source.md) ile eklendi. Eski iş geçmişi okunmaya devam eder.

## Kullanıcı sonucu

Kullanıcı programı kapatıp açınca hangi aramanın tamamlandığını ve hangi sorgunun hata verdiğini görebilir. Kısmi, başarısız veya yarım kalmış işi yeniden deneyebilir. Yeni deneme önceki sorgu ve hata geçmişini silmez. İnternet araması varsayılan kullanıcı akışı olarak kalır; liste dosyası gerekmez.

`scan` ve her `watch` turu önce kalıcı iş oluşturur, sonra çalıştırır. `scan --queue` yalnız işi kaydeder; `worker --once` sıradaki tek işi çalıştırır. `jobs list/show` ve `sources` salt okumadır. `jobs retry` yeni denemeyle işi baştan arar. `jobs recover`, kapanmış çalıştırıcının yarım işini kaydeder; kendi başına ağ isteği veya yeniden deneme yapmaz.

## Model ve sınırlar

İş, hedef adresleri, ek yazım araması seçimini, sağlayıcıyı ve kural/PSL sürümünü saklar. Deneme ayrı kimlik ve sıra numarası taşır. Kural veya kaynak değişmişse eski iş güncel kurallarla sessizce çalıştırılmaz; yeni scan istenir. İzlenen adresler yeniden doğrulanır; o anda kayıtlı bütün sahip olunan kökler dış taklit kontrolünde elenir.

İş durumları: queued, running, complete, partial, failed, interrupted. İş/deneme durumları birlikte, kısa transaction içinde değişir. Etkin denemeye ilerleme ve tamamlanan sorgular eklenebilir; bitmiş denemeye geç güncelleme reddedilir. Her yeniden deneme ayrı kayıt oluşturur. Liste ve kuyruk sırası saat değişiminden bağımsız ekleme sırasını kullanır.

Her QueryResult, bir sonraki sorguya geçmeden kaydedilir. Başlangıç/bitiş, son adım, sorgu bağlantıları, sonuç sayıları, atlama/uyarılar ve hatalar geçmişte kalır. Ham HTTP yanıtları kalıcı değildir; her sorgu için ayrı bitiş zamanı veya bütün HTTP başlıkları tutulmaz. Sorgu, ait olduğu denemenin zamanı içinde yorumlanır.

Yeniden başlatma HTTP yanıtının kaldığı bayttan sürdürülmesi değildir. Tam arama yeniden yapılır; mevcut gözlem/bulgu kimlikleri tekrarları önler. İş kesildiğinde bazı gözlemler zaten kaydedilmiş olabilir. Deneme tamamlanmadıysa sonuç sayısı uydurulmaz; sonraki denemenin yeni kayıt sayısı yalnız o denemeye aittir. Bu model kaynak isteğinin birden çok kez yapılabileceğini kabul eder.

## Tek çalıştırıcı ve kesinti

Aynı yerel veritabanı için tek süreç arama çalıştırır. `LocalExecutionLock`, veritabanı yanındaki kalıcı `.worker.lock` dosyasında işletim sistemi kilidi tutar. HTTP beklerken veritabanı transaction'ı açık kalmaz. Kilit dosyası silinmez; silip yeniden oluşturmak ayrı inode'larda çift sahipliğe yol açabilir. Sembolik bağlantı ve normal dosya olmayan kilit hedefleri reddedilir. Yeni kilit dosyası 0600 izniyle oluşturulur.

İşlem ölünce işletim sistemi kilidi bırakır. Yeni çalıştırıcı kilidi almadan `running` kayıtları yarım saymaz. Kilit alındıktan sonra önceki running kayıtları interrupted yapılır. Sadece listeleme yapmak veya bir süre geçmiş olması kurtarma için yeterli değildir. Yaşayan bir çalıştırıcıyı süreye bakarak geçersiz kılan lease veya PID tahmini yoktur.

Ctrl+C normal yoldan kesinti durumunu yazar. SIGKILL/elektrik kesilmesi bunu yapamaz; kayıt yeni çalıştırıcı veya açık recover komutuna kadar running kalabilir. Kurtarma otomatik yeniden kuyruğa alma değildir; yarım iş için açık retry gerekir. Yeni scan başka, yeni bir iş oluşturur. Eşzamanlı scan oluşturduğu işi sırada bırakıp çıkış kodu 4 verir.

Bu kilit aynı makinede aynı yerel kayıt dosyası içindir. Dağıtık çalışan, ağ dosya sistemi veya farklı dosya adlarıyla hard-link edilmiş veritabanı için koordinasyon garantisi verilmez. macOS üzerinde doğrulandı; POSIX kilit kullanan bu sürüm Windows'u desteklemez. Bilgisayar kapalıyken işlem çalışmaz; otomatik başlayan sunucu hizmeti henüz yoktur.

## Kaynak durumu

`sources` her sağlayıcının en son başlatılan denemesini gösterir. Daha yeni sıraya alınmış bir iş bu kaydı örtmez. Duvar saati geri gitse de deneme ekleme sırası korunur. Son deneme sorgu tamamlamadan kesilirse durum unknown olur; eski bir başarı güncelmiş gibi gösterilmez. Bu bir anlık ağ sağlık ölçümü değildir; son denemenin başlangıç/bitiş ve iş durumu da gösterilir.

## Veri geçişi ve yedek

Şema 3, `scan_jobs` ve `scan_attempts` tablolarını ekler. Şema 1 ve 2 ayrı biçimleriyle doğrulanır. Açık migrate komutu özgün veritabanını önce yedekler; gereken tablolar ve sürüm değişikliği tek transaction içinde tamamlanır. Hata olursa şema geri alınır, kurtarma yedeği korunur. Şema 2'deki gözlem/bulgu/kararlar yeniden oluşturulmaz.

Yedekler bekleyen işleri ve denemeleri içerir. Restore, mevcut hedefi ezmez ve kaynağın sürümünü korur. Çalışırken alınmış yedekte running deneme varsa yeni konumda recover ile yarım olarak işaretlenebilir. İşletim sistemi kilidi yedek içeriği değildir. Eski sürümden gelen gözlemler için geriye dönük arama geçmişi üretilmez.

## Doğrulama

Sahte ağ kaynaklarıyla başarı, kısmi sonuç, kaynak hatası, karar koruma, tekrar, sıraya alma, sürüm uyuşmazlığı ve kalıcı geçmiş test edilir. İki gerçek süreçle kilit yarışı ve zorla kapatma doğrulanır. Uçtan uca süreç testinde ilk sorgu veritabanına yazılır, ikinci sorguda süreç öldürülür, başka süreç kurtarıp yeni deneme oluşturur; geçmiş ve önceki karar korunur.

Şema 1/2 geçişleri, DDL hatasında geri alma, özgün yedek ve job geçmişinin restore'u test edilir. Önceki sürümün gerçek kaynak verisi içeren geçici kopyasında 764 gözlem/26 bulgu korunarak terminal başlatıcısıyla geçiş, kuyruk ve yedekten dönüş de doğrulanmıştır. Bu sürümün testleri internet bağlantısı gerektirmez.
