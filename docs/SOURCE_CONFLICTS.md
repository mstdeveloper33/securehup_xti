# Kaynak uyuşmazlığını kanıtıyla değerlendirme

0.179.0 · `source-conflict-v1` · inceleme önceliği `research-priority-v10`.

```sh
./xti research securehup.com --type domain --conflicts
./xti research securehup.com --type domain --priorities
```

Salt okunur engine ve firma platformunda `research.conflicts` aynı
seçenekleri kullanır: `indicator_type`, `value`, araştırma sınırları,
`offset`, `limit`, `stale_after_hours`, `expected_snapshot`. Kayıtlı
veriyi okur; internet araması veya ücretli sorgu başlatmaz. Yeni kanıt
gerekirse mevcut toplama/izleme işlemi ayrıca çalıştırılır.

| Durum | Kullanıcıya anlamı |
| --- | --- |
| `conflict_candidate` | Aynı tam profil adresi hakkında bir saat içinde karşıt varlık iddiaları var; kanıtları incele. |
| `identity_mismatch` | Sağlayıcı farklı bir profil döndürmüş; adres/kimlik bağı uyuşmuyor. |
| `verification_gap` | Kontrol kesin sonuç verememiş; timeout/engellenme profil yokluğu değildir. |
| `time_separated` | Karşıt gözlemler bir saatten uzak; değişen durum olabilir. |
| `historical_only` | Yalnız eski veya tarihî kayıt var. |
| `insufficient_evidence` | Seçilen pencere bütün kanıtı içermiyor. |
| `future_time` | Gelecekte görünen tarih doğrulanmalı. |
| `same_source_ambiguity` | Aynı kaynak aynı anda karşıt sonuçlar saklamış. |
| `single_source` / `compatible` | Tek kaynak veya karşıtlığı görülmeyen ifadeler; doğruluk/güvenlik onayı değil. |
| `lifecycle_difference` / `same_lifecycle` | CTI iddialarının yaşam döngüleri karşılaştırılır; geri çekme olumsuz tehdit iddiası değildir. |

Her değerlendirmede kaynak, tam adres, özgün kayıt kimliği, gözlem/kayıt
zamanı, kanıt SHA'sı, karşılaştırılan çift ve dışarıda bırakma gerekçesi
görünür. Aynı kaynağın en yeni kaydı esas alınır; son kontrol belirsizse
eski olumlu gözlem güncelmiş gibi canlandırılmaz. Kaynak sayısı oy değildir;
bağımsızlık bilinmiyorsa `independent_source_count=null` kalır.

Bir saatlik pencere eşzamanlılık kanıtı değildir; sonuç **inceleme adayıdır**.
Sosyal profilin varlığı resmî hesap/sahiplik/taklit kararı oluşturmaz.
İnsan kararları ve eski vaka/inceleme kayıtları değiştirilmez. Güncel
inceleme sırası ilgili karşıt kanıta gerekçeli öncelik verir; yeni
politika eski donmuş raporu yeniden hesaplamaz.

Bu sürüm sosyal profil varlığı/kimlik uyuşmazlığı ve CTI yaşam döngüsünün
açık alanlarını destekler. Serbest rapor metninin anlamını, aktör
kimliğini veya bütün tehdit türlerini otomatik çözmez. Ortak IP, kaynakta
listelenmeme veya IOC geri çekilmesi otomatik karşıt iddia değildir.

Araştırma en fazla100 düğüm/200 ilişki; değerlendirme başına en fazla64
kanıt alır. Eksik pencere başarılı tam karşılaştırma sayılmaz. Sonuç
sayfaları aynı kesit kimliğine bağlıdır; veri veya güncellik sınıfı
değişirse ilk sayfadan başlanır. Kaynakların yeniden indirilmesi ve
otomatik alarm/insan kararı değişikliği bu okumanın davranışı değildir.

[Teslim ve kabul](roadmap/JOB_HISTORY_CONFLICT_DELIVERY.md).
