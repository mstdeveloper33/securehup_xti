# 0151 — RSS toplama geçmişi ve kuruluş içerik raporu

Tarih: 16 Kasım 2026. Durum: uygulandı, 0.146.0 / şema 69.

## İhtiyaç

RSS yenilemesi, kayıtlı haber araması ve zamanlama ayrı komutlardı.
Birleşik kuruluş raporu ise saklanan Tavily firma/tedarikçi içeriklerini
göstermiyordu. Yeni toplayıcı veya bildirim sistemi yazmadan mevcut
akışları birleştirmek gerekiyor.

## Karar

1. Mevcut koleksiyon profiline açık `news_sources` ve `search_watch_ids`
   seçimleri eklenir. `--only-news` yalnız haber işi sağlar; eski varsayılan
   üç domain görevi değişmez. Seçim olmayan profil v1 canonical metnini
   korur; yeni seçim v2 tanımı/planı kullanır. Yürütme protokolü sürüm 1 kalır.
2. Mevcut haber araması bütün yerel haber kataloğunu kapsar. İlk otomasyon
   tesliminde bu arama için üç kaynak da açıkça seçilmeli ve başarılı
   yenilenmelidir. Alt küme yenilemesi tek başına mümkündür. Kaynak hatası
   bağlı aramayı atlar; başarılı boş yanıt hata sayılmaz.
3. Haber kaydı/projeksiyonu ve toplama makbuzu tek transaction'da yazılır.
   `CollectionNewsSearches` küçük portu üzerinden kayıtlı arama, fark,
   inbox ve makbuz da tek transaction'da yazılır. İş kimliği adımdan
   deterministik türetilir; ikinci bildirim yoktur.
4. Arama, oturum zincirindeki başarılı kaynak makbuzlarından belirlenen
   kaynak başına tarihî kesiti kullanır. Sonradan alınan haberler eski
   işe eklenmez. Aynı arama daha yeni kaynak kesitine ilerlemişse eski
   kesitten geriye dönük fark üretilmez. Aramanın kesin tanım olayı
   dondurulur; ad/sorgunun A→B→A veya kapat/aç döngüsü eski plan sayılmaz.
5. Şema 69 iki toplama geçmişi tablosunu genişletir. Yedekli açık migration
   eski sütun değerleri, rowid, JSON ve hash'leri aynen taşır. Yeni haber ve
   arama bağlantıları tekil yabancı anahtarlardır. Eski şema DDL'si eski
   migration adımları ve kabul senaryoları için korunur.
6. Kuruluş içeriği mevcut rapor transaction'ında salt okunur üretilir.
   Kuruluş için kesin hedef ID; tedarikçi için etkin gruptaki açık etkin
   supplier ID kullanılır. Aynı adlı bağımsız şirket veya metinsel ad
   eşleşmesi kapsam kurmaz. Eski ilişkide yalnız kuruluşun tarihî grup
   kaynak kanıtları okunur. Kaynak çalışma geçmişi yeniden yazılmaz.
7. Eski ad/domain/sorgu ve kapanmış ilişki tarihî bölümde kalır. Son deneme,
   son başarı, boş/hata/güncellik ve gerçek sayfalama toplamları ayrı
   gösterilir. Mevcut HTML dışa aktarımı tamlık kontrolüyle genişler.

## Sınırlar ve doğrulama

Yeni bağımlılık, ücretli servis çağrısı, arama motoru, scheduler veya
bildirim kanalı eklenmez. Engine v1'in dört işlemi ve tüketici ekibin .NET
sorumluluğu korunur. Linux zamanlama dosyası üretimi hizmeti etkinleştirmez.

Kabul senaryoları: eski canonical kayıtların değişmemesi, migration ve
rollback; kaynak/makbuz ile arama/inbox/makbuz atomikliği; kaynak hatası ve
boş yanıt; ilk sessiz başlangıç ve değişmeyen tekrar; kesinti/retained
kaynak/historical cutoff; tanım değişimi ve daha yeni arama uyuşmazlığı;
kuruluş/tedarikçi kesin kapsamı, eski ilişki, sayfalama ve tam HTML ihracı.
Ölçülen test sonuçları [güncel durum kaydındadır](../STATUS.md).

[Haber kullanım rehberi](../NEWS_COLLECTION.md),
[kuruluş raporu](../ORGANIZATION_REPORT.md).
