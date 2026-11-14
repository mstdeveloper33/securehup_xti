# 0137 — HIBP yenilemesinin kalıcı toplama oturumuna bağlanması

Durum: kabul edildi, 0.135.0. Tarih: 14 Kasım 2026.

Kamu olay kataloğu 0.134.0'da tek başına yenileniyordu. Kullanıcı bunu aynı
günlük çalışma, profil ve zamanlama içinde kullanmak istedi. Yeni zamanlayıcı
veya ikinci indirme yolu eklemek mevcut kaynak/oturum garantilerini bölerdi.

## Karar

- `notices-hibp`, `public_notice` türünde, `hibp` kaynaklı açık temel toplama
  görevidir. Varsayılan üç iş aynıdır. Profil v1 tanımında yalnız açık seçilen
  görev listesi değişir; önceki tanım/özetler yeniden yazılmaz.
- `CollectionService` isteğe bağlı `PublicNoticeService` alır. Seçilmemiş
  HIBP istemcisi oluşturulmaz. Önizleme yalnız yerel doğrulama yapar.
  Bütün seçili kaynaklar ilk ağ işi öncesinde ve ortak kilit altında denetlenir.
- Kaynak servis/depo sözleşmesi isteğe bağlı `CollectionOperationToken`
  taşır. Token açık oturuma, running adıma, kayıtlı domaine, geçerli profile
  ve `hibp-public-notices-v1` sözleşmesine bağlı olmalıdır. Kaynak isteğinden
  önce ve yazma transaction'ında yeniden doğrulanır.
- Kaynak run/farkları, gerçek `public_notice_run_id` yabancı anahtarlı
  makbuz ve adımın tamamlanması aynı transaction'da yazılır. Kaynak hatası
  da gerçek başarısız run'a bağlıdır; önceki başarılı katalog kalır.
- Kesintide tamamlanan makbuz korunur. Devam yalnız eksik birimleri yeni
  yürütmede çalıştırır; başarılı HIBP indirmesini tekrar etmez. Yerel analiz
  hatası kaynak başarısını silmez. Hatalı kaynak genel başarıya dönüştürülmez.
- Makbuz kamu katalog geçmişiyle tekrar doğrulanır. Kaynak atfı, lisans ve
  ortak kapsam JSON/terminal/korunmuş sonuçlarda taşınır. İlk başarılı alım
  `is_baseline=1` olarak ayrılır; sayaçlar domain bulgusu sayılmaz.

## Şema ve geçiş

Şema 61 mevcut `collection_session_steps` tür/kaynak/59 birim sınırını ve
`collection_step_receipts` doğrudan HIBP sonucunu genişletir. Tam bir kaynak
FK'sı bulunması, kaynak sonucunun tekilliği ve referans bütünlüğü korunur.
Eski şema 56–60 DDL/kolon/FK kısıtları ayrı sürüm tanımıyla doğrulanır.

Yedekli tek transaction'da iki tablonun SQL geçici kopyası tutulur; kaynak
tablolara dokunulmaz. Makbuz tablosu kaldırıldıktan sonra adım tablosunun
öz-bağları yalnız bu işlem içinde temizlenir; yeniden kurmada özgün
alanlarla aynen geri gelir. Rowid, kimlik, durum, zaman, JSON ve özetler
korunur. Eski makbuzlarda yeni alan NULL'dır. Yabancı anahtarlar kapatılmaz;
hata bütün işlemi geri alır. Yedekten dönüş yeni dosyaya yapılır.

## Kabul ve sınırlar

Ağsız kabul: seçilmeyen kaynağa çağrı yok; plan/profil/zamanlama hazırlığı
yazma/toplama sınırlarına uyar; başarısız karışık çalışma, yalnız eksik işin
tekrarı, commit sonrası kesinti, korunmuş atıf/lisans, eski profil özeti,
kuruluş kapsamında yabancı domain dışlama ve gerçek yedek hazırlığı sınanır.
Dolu 56–60 geçmiş, bağımlı adımlar, eski kaynak makbuzları, geçiş hatasında
geri alma, eşsiz yedek ve geri yükleme ayrıca sınanır.

Bu teslim HIBP kişi/hesap araması, bildirim, vaka kanıt türü veya HTML
rapor eklemez. Kaynak erişim sınırlarını değiştirmez. Gerçek Linux hizmet
çalıştırması macOS'taki dosya üretme/hazırlık testinden ayrı kabul gerektirir.
