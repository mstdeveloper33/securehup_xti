# 0011 — Sürümlü Unicode/IDNA benzer-harf adayları

**Tarih:** 29 Ekim 2026 · **Durum:** 0.11.0'da uygulandı.

## İhtiyaç ve karar

ASCII marka sorgusu, görünüşte aynı harfleri başka alfabelerden kullanan bir alan adını bulamaz. DNS ve kaynaklar bu adı çoğunlukla `xn--` ile başlayan Punycode A-label olarak verir. Bu değer düz ASCII metin gibi karşılaştırılırsa aday kaçırılır; çalışma ortamının değişken IDNA davranışına bırakılırsa aynı kanıt farklı sonuç verebilir.

Kanonik gözlem ve bulgu domaini ASCII A-label olarak kalır. Unicode görünüm yalnız doğrulama, UTS #39 iskelet karşılaştırması ve açıklama için kullanılır. Profil; değiştirilmemiş Unicode 18.0.0 `confusables.txt` ve `IdnaMappingTable.txt` dosyalarından çevrimdışı yüklenir. Sürüm ve SHA-256 beklenenden farklıysa çalışma durur. Ağdan çalışma anında kural indirilmez.

UTS #46 eşlemesi nontransitional işlenir ve STD3 karakter kısıtları uygulanır. NFC, tire, etiket ve 63 bayt sınırları kontrol edilir; A-label çözüldükten sonra yeniden kodlanıp kanonikliği doğrulanır. İlk güvenlik profili, tam bağlam kuralları uygulanmadan kabul edilmemesi gereken sağdan sola ve birleştirme denetimli etiketleri reddeder. Bu bilinçli olarak dar kapsamdadır.

## Arama ve aday üretimi

Kaynak yanıtındaki geçerli U-label veya A-label her zaman kanonik A-label'a dönüştürülür. İzlenen ASCII marka ile adayın kayıt kökü etiketi ve farklı kökteki alt etiketleri UTS #39 iskeletiyle karşılaştırılır. Eşit iskelet yalnız “inceleme adayı” üretir; kötü niyet, sahiplik veya phishing kararı üretmez.

Normal ASCII arama Punycode içinde marka metnini göremez. `--typos`, mevcut kalıcı iş/izleme ayarı olarak, ad başına en fazla dört deterministik A-label aramasını da açar. Varyantlar paketlenmiş confusables verisinden, geçerli Greek/Cyrillic harflerden; önce aynı yazı ailesiyle toplu, sonra tek konum değişimleri şeklinde üretilir. Bu bütün permütasyonları taramaz. crt.sh için gerekli ön ek/içerme sorguları, urlscan için yalnız ön ek sorguları kullanılır. Sınır, ücretsiz kaynak kotasını ve çalışma süresini korur.

İzlenen varlıkların Unicode/Punycode olması bu sürümde desteklenmez. Böyle bir özellik, varlık kimliği ve kullanıcı girdisi için ayrı geçiş sözleşmesi gerektirir. Public Suffix List'in Unicode kuralları üretimde aynı profile çevrilir; çok etiketli uluslararası kayıt sınırları düzleştirilmez.

## Sürüm ve geçmiş uyumluluğu

İş yürütme sözleşmesi `domain-rules-v2/.../unicode:18.0.0` olur. Böylece eski kuralla kaydedilmiş yarım iş yeni sorgu planıyla sessizce tekrar çalıştırılmaz.

Normal ASCII eşleşmelerin bulgu anahtarı bilinçli olarak önceki `domain-rules-v1/psl:...` değerini korur. Güncelleme, mevcut ASCII bulguyu ikinci bir yeni alarm olarak üretmez; karar ve bildirim kimliği korunur. Unicode iskelet adayı ayrı `idn-confusables-v1/psl:.../unicode:18.0.0` kural kimliği taşır. Referans veri değişirse eski değerlendirme üstüne yazılmaz.

Şema değişmez; sürüm 7 kullanılır. Yeni A-label gözlemler mevcut alanlara sığar. Ham kaynak değeri, kanonik A-label ve kaynak zamanı önceki kanıt sözleşmesiyle korunur. Hedef kontrolü A-label üzerinde DNS/TLS yapabilir; kullanıcıya gösterilen dinamik Unicode metin terminal kaçışından geçer.

## Sınırlar ve doğrulama

- UTS #39 iskelet eşitliği yanlış alarm üretebilir; tam adres istisnası 0.12.0'da, sentetik kalite ölçümü 0.13.0'da eklendi. Gerçek kullanım precision/recall ölçümü hâlâ açık iştir.
- Sağdan sola, ContextJ ve daha geniş IDNA bağlam desteği yoktur; atlanan ad görünür kaynak sayısına eklenir.
- Dört sorgu varyantı kapsama örneğidir; tam Unicode araması değildir.
- Kaynak indeksleri, geçmiş aralığı ve kotaları sonuç kapsamını sınırlar.
- Python'un Unicode karakter özellikleri çalışma ortamına aittir; paketlenmiş tabloda olup çalışma ortamınca tanınmayan karakter kabul edilmez.

Testler veri sürümü/özeti yükleme yolunu, U-label↔A-label dönüşümünü, bozuk/RTL/joiner reddini, iskelet pozitif-negatiflerini, uluslararası PSL sınırını, sınırlı sorgu planını, iki kaynak ayrıştırmasını, ayrı kural kimliğini, kalıcı bulgu tekilleştirmesini ve eski ASCII kimliğini kapsar. Sentetik homograf örnekleri gerçek internet doğruluk oranı değildir.
