# 0133 — Kuruluş, değişim, katalog ve kaynak katkısını ayrı kanıtlarla birleştirme

**Durum:** Kabul edildi · **Tarih:** 14 Kasım 2026 · **Uygulama:** 0.133.0

Kullanıcının onayladığı sekiz teslimin 3–7. bölümleri, mevcut toplama ve
inceleme kayıtlarını yeniden yorumlamadan ortak kullanım akışına eklenir.
Yeni ücretli API veya Python bağımlılığı gerektirmez. Uygulama servisleri
küçük portlara bağlıdır; SQLite, HTTP ve terminal ayrı adaptörlerdir.

## Açık kuruluş bağlantıları ve dönem raporu

Şema 57 kuruluş, bağlantı ve her ikisinin eklemeli karar geçmişini ekler.
Yalnız kayıtlı domainler ve açık kimlikle seçilmiş sosyal/ThreatCluster/
RansomLook izlemeleri bağlanabilir. Aynı hedef birden fazla grupta bulunabilir.
Grup, bağlantı veya hedefin geri çekilmesi eski kanıtı silmez; etkinlik ayrı
gösterilir. Bu bağlantı sahiplik, kimlik veya ihlal doğrulaması değildir.

`changes --days 1|7` tek SQLite okuma anlık görüntüsünden kayan UTC aralığını
raporlar. Başlangıç ölçümü, gerçek fark, kaynak hatası ve kapsama boşluğu
ayrılır. Kaynak zamanı ile yerel kayıt zamanı birbirinin yerine geçmez.
`--domain` yalnız marka ve dış yüzey kayıtlarını süzer; sosyal hesap veya
kuruluş iddiası domain adına bakılarak ilişkilendirilmez. Her bölümün gerçek
sayısı, gösterilmeyen kayıt sayısı ve kanıt kimlikleri korunur. Kaynaklar
arasında kanıtlanmamış benzersiz tehdit toplamı üretilmez.

## ATT&CK kataloğu

Şema 58, resmî STIX kimliğine bağlı teknik/alt teknik/taktik kataloğunu ve
ilişkilerini tutar. Mevcut sabit MITRE Enterprise v20 indirmesi bir kez
ayrıştırılır; eski CTI görünümüyle katalog aynı transaction'da güncellenir.
Ad değişikliği kimliği değiştirmez; aynı adlı teknikler birleştirilmez.
Kaynak ilişkileri ile kill-chain alanından türetilen teknik/taktik bağları
açıkça ayrıdır. Kaynak açıklaması ve URL korunur; `tool` malware sayılmaz.
İlişkiler sayfalıdır; görünüm sınırı kalıcı veriyi kesmez.

Eski CTI bağlantısı olan katalog kaydı okunurken bağlantı aynı veritabanı
anlık görüntüsünde doğrulanır. Eski kayıtlardan teknik geçmişi uydurulmaz;
katalog ilk başarılı yeni `cti attack-sync` ile dolar. Resmî bundle üzerinde
1.703 katalog nesnesi, 18.055 kaynak ilişkisi ve 881 türetilmiş taktik bağı
ayrıştırılarak sınanmıştır. Bunlar izlenen kuruluşa saldırı atfı değildir.

## Kaynak katkısı ve RansomLook bildirimleri

`sources contribution` gerçek ortak/ayrı domainleri, kanıt ve deneme
kimliklerini gösterir. Marka kuralları ve pasif keşif aileleri karıştırılmaz.
Tam/kısmi/hatalı/kesilmiş denemeler ve oranların pay/paydasına hangi
kayıtların girdiği görünür. Yetersiz geçmiş kalite sıralamasına çevrilmez.
Yeni ücretsiz sağlayıcı ancak ölçülmüş ek kapsam, erişim koşulları ve doğru
hata bildirimiyle kabul edilir; bu sürümde yeni sağlayıcı eklenmedi.
Common Crawl dış indeks erişim sorunu ayrı açık kalır.

Şema 59 RansomLook izleme değişimlerini mevcut yerel bildirim kutusuna bağlar.
Başlangıç, değişen tanımın yeni başlangıcı, tekrar, yalnız kaybolma ve hata
bildirim üretmez. Yeni/değişen iddiada tek bildirim; izleme sonucu ve varsa
toplama tamamlanma bağı ile aynı transaction'da yazılır. Eski geçmişten
bildirim türetilmez. Kaynak iddiası doğrulanmış ihlal diye sunulmaz; dış
mesaj gönderimi otomatik başlamaz.

## Geçiş ve doğrulama

Şema 56→59 geçişi açık `migrate` ve önce geri dönüş yedeği gerektirir.
Yeni tablolar boş başlar; önceki kanıt/insan kararı/okundu durumu korunur.
Kabul testleri gerçek SQLite ve CLI üzerinde sahte kaynaklarla kesinti,
eksik işi tekrar etme, tek bildirim, salt okunur rapor ve sayfalama zincirini
birlikte sınar. Ağ bağlantısı testte engellenir. Tam kontrol mevcut özellikleri
de kapsar; artan paket için kısa CI sınırı 10, tam paket sınırı 30 dakikadır.

Linux zamanlama ve bakım kararı [0134](0134-linux-scheduling-and-owned-backups.md)
belgesindedir.
