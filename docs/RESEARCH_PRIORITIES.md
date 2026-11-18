# Gerekçeli inceleme önceliği

18 Kasım 2026 · 0.160.0 · politika `research-priority-v3` · model 2 · şema 75.

Seçtiğin domain, kesin IP, URL veya dosya kimliği için **hangi kaydı önce
incelemelisin ve neden?** Mevcut DNS/CNAME/TLS, tedarikçi, IOC/CTI, MISP listesi ve URL/hash
kayıtlarını kullanır. Her önerinin dayandığı kayıt ve kaynak korunur.

Bu bir inceleme sırasıdır. Kaynak iddiasının doğruluğunu, firmanın ihlal
edildiğini veya zararlılık olasılığını hesaplamaz. Mevcut analist kararları,
alarmlar ve vakalar değiştirilmez. Yeni internet sorgusu yapılmaz; anahtar,
ücretli API, LLM veya ek paket gerekmez.

## Kullanım

```sh
./xti research securehup.com --type domain --priorities
./xti research 93.184.216.34 --type ip --priorities --limit 10
./xti research 'https://example.com/' --type url --priorities
./xti --data-dir /path/to/data --json research securehup.com --type domain --priorities
```

Önce veriler mevcut toplama komutlarıyla saklanmış olmalıdır. Yeni bir
kökte yalnız “bu kapsamda kanıt yok” sonucu çıkabilir; bu güvenlik sonucu
değildir. Terminal özgün kayda geçiş komutlarını ve sayfa devam komutunu
seçili veri klasörüyle verir. `--priorities` kaldırılınca kanıt yolları görünür.

Liste **seçili kökün en fazla iki ilişki adımlı araştırmasını** kapsar.
Bütün firmanın varlıklarını veya bütün interneti sıraya koymaz. Aynı kaydın
birden fazla yolda görülmesi ayrı bir öncelik öğesi oluşturmaz. Düğüm ve
ilişki ayrı öğelerdir; örneğin bir IP'nin IOC iddiası ile domainin o IP'ye
eski DNS bağı ayrı nedenlerle incelenebilir. Bir komşunun önceliği diğer
komşuya otomatik taşınmaz.

## Sıralama politikası

| Sıra | Gösterim | Anlamı |
|---|---|---|
| `review_first` | Önce incele | Etkin ve güncel IOC iddiası, kaynak durum farkı, IOC ile birlikte liste bağlamı veya gelecekte görünen kanıt zamanı var |
| `verify` | Doğrula | Eski/eksik/sınırda kesilmiş kanıt, eski etkin IOC veya son başarısız kontrol var |
| `context` | Bağlam | Bu kurallar ek öncelik üretmedi; kayıtlı bağlam veya tarihî/etkin olmayan iddia var |

Bir öğe birden fazla gerekçe taşıyabilir. En öndeki sınıf seçilir; aynı
sınıfta aşağıdaki kural sırası, eşitlikte kararlı öğe kimliği kullanılır.
Kaynak sayısı veya kaynak güven puanı oy/puan olarak toplanmaz. Yüzdelik
tehdit puanı yoktur; `context` “güvenli” demek değildir.

| Kural kodu (aynı sınıfta sırasıyla) | Dayanak |
|---|---|
| `future_evidence_time` | Gösterilen kanıtın gözlem veya kayıt zamanı değerlendirme anından ileride |
| `source_status_difference` | Aynı öğede farklı kaynaklardan etkin ve geri çekilmiş iddia; süresi dolmuş iddia tek başına bu gerekçeyi üretmez |
| `indicator_with_list_context` | Etkin IOC iddiası ve bir MISP liste eşleşmesi; liste iddiayı geçersiz kılmaz |
| `active_indicator_claim` | Etkin IOC iddiasının son gözlemi güncellik eşiği içinde |
| `latest_check_failed` | Düğümdeki son kayıtlı DNS kontrolü başarısız |
| `latest_cname_check_failed` | Son CNAME veya son hedef DNS sorgusu başarısız; tarihî olumlu bağlar korunur |
| `latest_tls_check_failed` | Son kayıtlı web kontrolünde TLS başarısız |
| `certificate_expired` | Gösterilen sertifika kanıtının `valid_until` zamanı aşılmış; bugün hâlâ sunulduğu iddia edilmez |
| `certificate_not_yet_valid` | Sertifika kanıtının `valid_from` zamanı henüz gelmemiş |
| `supplier_review_pending` | Kayıtlı tedarikçi adayı pending/uncertain; teknik bağ insan onayı değildir |
| `supplier_dependency_historical` | Aday son yenilemede tarihî olmuş; insan onayı kendiliğinden silinmez |
| `supplier_inventory_inactive` | Son tedarikçi envanter kararı pasif; eski kanıt korunur |
| `source_lookup_failed` | Son URL/hash kaynak sorgusu başarısız; önceki geçerli yanıt ayrı korunur |
| `evidence_truncated` | Öğenin toplam kanıtı gösterilebilen kanıttan fazla |
| `stale_active_indicator` | Etkin IOC iddiasının son gözlemi eşikten eski |
| `stale_evidence` | Gösterilen ilgili son gözlem/yanıt eski; geri çekilmiş iddia yalnız eski diye yükseltilmez |
| `evidence_missing` | Öğeye ait veya ilişkili kayıtlı kanıt yok |
| `source_no_match` | Son geçerli kaynak yanıtında eşleşme yok |
| `inactive_claims_only` | Gösterilen kaynak iddialarının hiçbiri etkin değil |
| `supplier_link_withdrawn` | Tedarikçi bağı sonraki insan kararıyla kaldırılmış/değiştirilmiş; bağlamdır, yeni tehdit değildir |
| `listed_context` | Kaynak/üye/çalışma kimliğiyle MISP bağlamı |
| `recorded_context` | Diğer kurallar tetiklenmeden kalan gözlem/kaynak bağlamı |
| `relationship_context_only` | Düğüm yalnız ilişkili kanıtta geçiyor; ayrı düğüm iddiası yok; doğrudan kanıtlı bağlamdan sonra gelir |

Güncellik eşiği varsayılan 24 saat, `--stale-after-hours` 1–8760 saattir.
Tam eşik anı güncel; eşiği aşan gözlem eskidir. Aynı DNS bağında daha yeni
gözlem varsa eski tekrarlar sırayı yükseltmez; eski kanıtlar listede kalır.
Son DNS kontrolünün başarısız olması, önceki olumlu gözlemi yenilemez.
CNAME/TLS için de son başarısız deneme eski olumlu bağı güncellemez.
Sertifika geçerlilik gerekçeleri sertifika düğümü ve ilgili gözlemde kalır;
bir domainin güncel zafiyet kararı veya otomatik alarmı olmaz.

V2 bu dört yüzey gerekçesini ekler. Önceki v1 inceleme kayıtları özgün
değerlendirmeleriyle okunur. V2'nin ilk kaydı `policy_baseline` olur;
kural değişimi yeni kaynak kanıtı diye sayılmaz. Yeni DB şeması yoktur.

V3 tedarikçi adaylarını ve insan kararlarını ekler. Eski insan kararı
zamanı görünür ama ağ gözlemi eskimesi gibi sıralanmaz. İşletme önemi
(`criticality`) risk puanı veya IOC kaynak güveni değildir. Teknik adayın
güncelliği kaynak tarihine dayanır; insan kararının güncelliği son ilgili
karar oluşudur. `current=true` için `status` mutlaka okunur; son karar
`withdrawn`/`revoked` olabilir. İnsan kararlarının değişmesi kanıt değişimidir,
yalnız saat ilerlemesi veya IOC iddiası geri çekmesi değildir.

Kaynak iddialarının etkinliği, kaynak güveni (`confidence`) ve kanıt türü
(`evidence_basis`) ayrı alanlardır. Kanıt türleri `observation`,
`source_claim`, `source_context`, `candidate_context`, `human_decision`
olabilir; nicel “kanıt gücü” uydurulmaz. Son iki tür araştırma modeli 2'ye
aittir; eski model 1 altında kabul edilmez.
CIRCL gibi gözlem tarihi vermeyen kayıtta `time_basis=response_received_at`
korunur. Yeni indirilen eski URL taraması yeni gözlem sayılmaz.

Kaynak durum farkı, otomatik anlamsal çelişki tespiti değildir. İki farklı
aktör ilişkisi tek başına birbirini çürütmez; tarih, kaynak ve özgün iddia
ayrı kalır. Güncellik cihazın UTC saatine ve kayıtlı tarihlere dayanır.

## Engine ve firma platformu

`./xti engine` veya güvenilen başlatıcının seçtiği
`./xti platform request --root /srv/xti --company firma-a` için:

```json
{
  "contract_version": 1,
  "request_id": "inceleme-1",
  "operation": "research.priorities",
  "parameters": {
    "indicator_type": "domain",
    "value": "securehup.com",
    "max_hops": 2,
    "limit": 10
  }
}
```

Parametreler [araştırma sözleşmesiyle](RESEARCH.md#sürümlü-platform-işlemi)
aynıdır. `offset/limit` burada **öğe sayfası**dır; yol sayfası değildir.
JSON içinden firma, klasör, kaynak yenileme veya özel kural kodu seçilemez.

| Sonuç alanı | Anlamı |
|---|---|
| `policy_version`, `model_version` | Sıralama kuralı ve sonuç modeli sürümü |
| `checked_at`, `query` | Değerlendirme anı, kanonik kök ve sınırlar |
| `snapshot_id` | Öncelik sayfalarının kesit kimliği; kural, kanıt ve zaman sınıfı hesaba katılır |
| `evidence_snapshot_id` | Altındaki ilişkili kanıt araştırmasının kimliği |
| `scope`, `stored_data_only`, `consistency` | Sınırlı araştırma kapsamı, saklı veri, tek okuma kesiti |
| `status` | Araştırmanın `not_recorded/no_relationships/related_records/partial` durumu |
| `collected_item_count`, `priority_counts` | Sayfadan önce toplanan sınırlı öğeler ve sınıf sayıları |
| `items` | Sıralanmış bu sayfanın öğeleri |
| `items[].id`, `subject_kind`, `record_type`, `label`, `value` | Özgün araştırma kimliği, düğüm/ilişki türü ve değeri |
| `source_id`, `target_id`, `related_item_ids` | İlişkinin özgün yönü veya düğüme bağlı ilişki kimlikleri; başka sayfada olabilir |
| `references` | Desteklenen özgün düğüm kayıtları için `record.get` başvuruları |
| `priority`, `evidence_basis`, `reasons` | Öncelik, kanıt türleri, kural kodu/açıklaması/dayanakları |
| `reasons[].evidence_ids` | Aynı öğenin `evidence[].id` alanına başvuru; eksik veri/liste gerekçesinde boş olabilir |
| `evidence`, `evidence_total_count` | Kaynak/iddia/olay/çalışma kimlikleri, gözlem/kayıt zamanı, güven ve etkinlik; kesilen sayılar görünür |
| `enrichment`, `warninglist_matches`, `warninglists` | Kaynak yanıtı/son hata, liste eşleşmesi, kaynak/atıf ve liste güncelliği |
| `coverage_complete`, `limitations`, `coverage` | Araştırmanın okuma sınırları; internet kapsamı veya veri yeterliliği garantisi değil |
| `offset`, `limit`, `has_more`, `next_offset` | Öğelerde sayfalama |

Öncelik hesaplama bütün sınırlı araştırmadan **önce sıralayıp sonra sayfalar**.
Yalnız ilk yol sayfasındaki kayıtlara bakarak sıralama yapılmaz. En fazla
100 düğüm ve 200 ilişki; diğer DNS/geçmiş/kanıt sınırları
[araştırma sınırlarında](RESEARCH.md#sayfa-tutarlılığı-ve-sınırlar) aynen kalır.
Eksik warninglist durumu ayrı gösterilir; listeler kendiliğinden indirilmez.

Sonraki sayfada `next_offset` ve **bu işlemin** `snapshot_id` değerini
`expected_snapshot` olarak verin; diğer parametreleri koruyun. Kanıt,
etkinlik, kural veya güncellik sınıfı değiştiyse `snapshot_changed` / exit 1
döner. `research.show` ile öncelik sayfası kimlikleri birbirinin yerine
kullanılmaz. İlk sayfadan yeniden okuyun. Kesit tarihî bir depoya kaydedilmez.

Başarılı okuma exit 0; kısmi/kanıtsız durum da başarılı okumadır.
Hatalı parametre exit 2 / `invalid_parameters`, bozuk/kayıp veri exit 1 /
`storage_error`, boyut sınırı exit 1 / `response_too_large` üretir.

## Kabul ve kalan kapsam

Yerel testler gerçek SQLite kayıtlarıyla aynı kaynaktaki tekrar, kaynak
geri çekme, zaman eşiği, başarısız kaynak sonrası korunan yanıt, liste+IOC,
sayfalama, iki firma, eşzamanlı yazma ve yedekten dönüşü kapsar. Çalışma
sonuçları [kabul kaydında](ACCEPTANCE_REVIEW.md) ayrı tutulur.

Bu ilk MTR-04 dilimidir. 0.156.0 ayrıca açık [inceleme kaydı ve geçmişini](RESEARCH_HISTORY.md)
ekler; mevcut `research --priorities` okuması kendiliğinden kayıt almaz.
Firma geneli öncelik kuyruğu, otomatik bildirim, anlamsal çelişki çözümü,
özel müşteri kuralları ve geniş IOC yaşam döngüsü otomasyonu henüz eklenmedi. Ağsız okuma mevcut
Tavily/Nmap canlı kabulü veya kaynak kullanım hakkı notlarını kapatmaz.
0.155.0 bu özelliği şema 74'te ekledi; 0.156.0 geçmiş için şema 75'e
açık yedekli geçiş gerektirir. 0.160.0 şema 75'i korur; yeni değerlendirme
modeli 2'dir. Eski model 1 incelemeleri korunur ve özgün okunur.
