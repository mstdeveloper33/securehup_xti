# 0129 — Birleşik toplamada açık izleme seçimi

**Durum:** Kabul edildi

**Tarih:** 14 Kasım 2026

**Uygulama:** 0.130.0; şema 54 değişmez.

## İhtiyaç

Kullanıcı mevcut sosyal ve ransomware izlemelerini domain toplamasıyla aynı
komuttan çalıştırmak ve ileride React arayüzüne bağlamak istiyor. Sosyal ve
kuruluş izlemelerinde kayıtlı domaine aitlik alanı bulunmuyor. Bu nedenle
tek domain girdisiyle bütün yerel izlemeleri çalıştırmak veya kullanıcı adı
türetmek kapsamı yanlış genişletir.

## Karar

- `collect` üç tekrarlanabilir kimlik seçeneği alır: `--username-watch`,
  `--ransomware-watch` (ThreatCluster), `--ransomlook-watch`. Bunlar mevcut
  temel işlere eklenir. `--task` temel altı işin seçimini değiştirir; hiç
  verilmezse önceki üç varsayılan domain işi korunur.
- Sosyal kaynak/platformlar değiştirilemez kaynak kimliği taşıyan mevcut
  izleme tanımından alınır. Aynı kimliği tekrar seçme, bozuk kimlik,
  bulunamayan veya geri çekilmiş izleme işlem başlamadan reddedilir.
  Seçilenlerin toplamı en fazla 50'dir; sessiz kırpma yapılmaz. Bu, kayıtlı
  izleme sayısına değil tek ön plan çalışmasına uygulanan sınırdır.
- Plan ağsız ve yazmasızdır; seçilen gerçek ad/tür/kaynak/platformları
  gösterir. Bütün seçili depolar önce doğrulanır, ortak çalışma kilidinin
  içinde tekrar okunur. Kaynakların canlı erişilebilirliği bu yerel ön
  kontrolden çıkarılmaz. Seçilmeyen izlemeler plana girmez/çalıştırılmaz.
- `CollectionWatchService` terminalden bağımsız uygulama bileşenidir.
  Sosyal görevler kanonik kimlik sırasıyla tek tek; ransomware görevleri
  ThreatCluster, ardından RansomLook olarak kaynak başına gruplanır.
  Ortak kilit `CollectionService` tarafından sahiplenilir; alt servisler
  ikinci kilit istemez.
- Her seçili ransomware kaynağı bir kez yenilenir. Başarılı yenilemenin
  kimliği her izleme çalışmasına bağlanır; ThreatCluster'ın mevcut beklenen
  kaynak kimliği kontrolü RansomLook'a da isteğe bağlı parametre olarak
  eklenir. Başka snapshot devreye girerse yazmadan durulur. İzleme tanımı
  yenileme sırasında değişirse seçili kapsam sessizce değiştirilmez.
- Yenileme hatasında atlanan izleme kimlikleri raporlanır; eski başarılı
  snapshot üzerinde yeni izleme çalışması oluşturulmaz. Diğer bağımsız
  kaynaklar devam eder. Depolama/bütünlük/program hatası ve kullanıcı
  kesintisi sonraki adımları durdurur; tamamlanan kayıtlar korunur.
- Mevcut sosyal ve ransomware servisleri saklama, başlangıç, değişim,
  inceleme kararı ve bildirim kurallarının tek sahibidir. Başlangıç kaydı
  yeni olay/alarm olarak yorumlanmaz. Raporlanmayan sosyal profil kesin
  yokluk, ransomware iddiası doğrulanmış ihlal olarak gösterilmez.
- `CollectionStep` özgün raporları kaynakları ve gerçek çalışma kimlikleriyle
  taşır. Domain analizi ayrı kalır; örtüşen izlemeler tekil toplam sayılmaz.
  İnsan kararı eklenmemiş rapordan “karar yok” çıkarımı yapılmaz; ayrıntı
  komutu mevcut inceleme ekranına yönlendirir.
- `--watch-item-limit` varsayılan 100, aralık 1–500'dür; sonuç görünümünü
  sınırlar. Kaynak yenilemesi ve izleme sonucu bütünüyle mevcut depoda
  tutulur; gösterilmeyen öğe sayısı ve ayrıntı komutu görünürdür.

Yeni kalıcı birleşik oturum, domain-izleme ilişkisi, zamanlayıcı, REST API,
React arayüzü veya bağımlılık eklenmez. Gelecekteki API aynı uygulama
servisini çağırabilir. Normal `analyze` ağsız/domain kapsamlı kalır.

## Doğrulama

Geçici SQLite ve sahte kaynaklarla seçilen kimlik/kaynak yalıtımı, planın
yazmasızlığı, ilk ağdan önce bütün ön kontroller, tek kaynak yenilemesi,
tam snapshot bağlama, kaynak kesintisi sonrası eski veriyi koruma, tekrar
ve insan kararı korunumu, başlangıç/değişim ayrımı, görüntüleme sınırı ve
terminal kaçışları sınanır. Tam test ve kabul sonuçları `STATUS.md` içinde
ayrıca kaydedilir; sahte kaynak testleri canlı erişim kanıtı sayılmaz.
