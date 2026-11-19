# Sekiz maddelik motor geliştirme paketi

19 Kasım 2026 — kullanıcı sekiz maddeyi birlikte yetkilendirdi.
Başlangıç: 0.167.0 / çekirdek 77 / kuyruk 3. Aşağıdaki kapsam uygulama
ve kabul ile ayrı kapatılır; plan yazılması tamamlanma değildir.

| Madde | Somut teslim | Kabul | Durum |
| --- | --- | --- | --- |
| 1. Otomatik rapor | Yönetilen kaynak işinde ayrı sürümlü rapor yakalama adımı; kaynak seçimi, sınır, değişmez belge başvurusu | Aynı içerik çoğalmaz; değişen metin sürümlenir; kesinti/tekrar önceki kanıtı bozmaz | Uygulandı; ilgili testler geçti |
| 2. İlişki önerileri | İki adımlı kayıtlı kanıttan kurallı aday; dayanak kimlikleri/hashleri, güncel/eski kapsam, gerekçeli geri alınabilir insan kararı | Ortak altyapı veya rapor bağı saldırı atfına dönüşmez; kaynak değişince eski karar güncel sayılmaz | Uygulandı; ilgili testler geçti |
| 3. Birleşik kimlik | Kabul edilmiş kimlik bağları üzerinden tek görünüm; özgün kayıtlar, alternatif adlar, kaynaklar ve bağlantı kararları | Aynı tür, firma sınırı, çevrim/sayfa sınırı, geri çekmede ayrılma; fiziksel birleştirme yok | Uygulandı; ilgili testler geçti |
| 4. Kaynak kapsamı | Mevcut RIPEstat adaptörüne ayrı WHOIS kayıt bağlamı; sabit endpoint, seçilmiş ağ/kuruluş alanları | Hatalı/kapsam dışı yanıt reddi; eski başarı korunur; canlı sonuç ayrı | Uygulandı; ilgili testler geçti |
| 5. Gerçek görülme | Kaynak olay kimliği, gösterge, gözlem zamanı, yerel sensör başvurusu ile firma kapsamlı kalıcı giriş/geri çekme/listeme | Tekrar, çakışma, eski saat, firma ayrımı; gerçek müşteri logu olmadan fixture canlı sayılmaz | Uygulandı; ilgili testler geçti |
| 6. Esnek akış | Açık adım sırası, rapor seçimi/sınırı, hata sonrası devam/durdurma seçimi | Plan özeti, iptal/kurtarma, eski iş modelleri ve makbuzları korunur; serbest komut yok | Uygulandı; ilgili testler geçti |
| 7. Kaynak karşılaştırması | Aynı IOC'nin kaynaklarını etkinlik, geçerlilik, yaş, gözlem ve referanslarıyla karşılaştırma; firma inceleme bağlamına ekleme | Kaynak sayısı oy değildir; iddia farkı otomatik anlamsal çelişki sayılmaz | Uygulandı; ilgili testler geçti |
| 8. Kapasite | İki firma, daha büyük kontrollü veri, gerçek CLI/JSON süreçleri, eşzamanlı okuma, disk/bellek/süre, yedek/restore ve eski sürümden geçiş | Ölçüm ortamı/veri hacmi/süre yazılır; ölçülmeyen Linux/SLA/canlı kaynak kapsamı açık kalır | Tanımlı yerel kabul tamamlandı; aşağıdaki test kapsamı geçerli |

**Yerel kabul sonucu:** 31 yeni test, 15 gerçek CLI/engine işlemi, iki
firmalı 120 saniye / 922 ölçülen süreç, yedek/restore ve eski kodla geçiş
geçti. Tam paket 3.151 testte iki eski test beklentisi hatası ve dört Linux
atlamasıyla tamamlandı; beklentiler düzeltildi ve ilgili 23 + 7 test
yeniden geçti. Çalışma kodu değişmedi; düzeltmeler yalnız testlerdeydi.
Tam paket tekrar edilmedi. [Tam kanıt ve sınırlar](../ACCEPTANCE_REVIEW.md).

Öncelik ücretsiz çekirdektir. WHOIS için RIPEstat'ın mevcut ticari kullanım
takibi N-022 geçerlidir; kaynak eklenmesi veri hakkı sağlamaz. Tavily anahtarı,
yetkili Nmap hedefi ve ticari koşulların dış doğrulaması bu paketten ayrı
kalır. Geniş STIX/TAXII, LLM ve platformun kullanıcı/UI/.NET işleri kapsamda
değildir. Yeni engine işlemleri terminal ve firma JSON üzerinden sunulur.

Güncel uygulama: **0.168.0 / çekirdek78 / kuyruk3 / kaynak işi4**.
[Komutlar ve JSON](../EVIDENCE_WORKFLOWS.md),
[kabul sonuçları](../ACCEPTANCE_REVIEW.md). Modelin okunabilir olması
gelecekteki bütün ölçeklerin veya OpenCTI özellik eşitliğinin kabulü değildir.
