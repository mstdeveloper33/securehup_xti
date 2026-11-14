# MITRE ATT&CK Teknik ve Taktik Kataloğu

**PLANLANDI — UYGULANMADI (PLANNED — NOT IMPLEMENTED).** 14 Kasım 2026.
Bu belge 5. aşamanın tasarım ve kaynak ölçümüdür; yeni komut, şema veya
çalışan özellik teslim edildiği anlamına gelmez. Önce 1–4. aşamalar
tamamlanacak. Çalışan kapsamın kaynağı [STATUS](../STATUS.md) dosyasıdır.

## Kullanıcıya sağlayacağı şey

Mevcut `cti attack-sync` indirmesinden teknik, alt teknik ve taktik
bilgisini de saklamak; ATT&CK kimliği veya adla çevrimdışı aratmak;
üst teknik, taktik ve kaynakta belirtilen grup/kampanya/malware kullanım
ilişkilerini kaynaklarıyla göstermek. Komut adları uygulama sırasında
kesinleştirilecek. Bu katalog bir domainin saldırıya uğradığını veya belli
bir gruba ait olduğunu söylemez; saldırı, istismar veya CVE eşlemesi yapmaz.

## Resmî paket üzerinde ölçülen kanıt

[Kodun kullandığı Enterprise v20.0 STIX 2.1 paketi](https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack-20.0.json)
14 Kasım 2026, 12:58 UTC'de indirildi ve bellekte ayrıştırıldı. Ham paket
yalnız geçici klasörde tutuldu; uygulama veritabanına yazılmadı.

- Boyut: **55.271.014 bayt**; toplam **26.690 nesne**.
- SHA-256: `2339a3c36353d5ee2c07e98af3fafbf00761e0e3979ede06402657445b7b4278`.
- Koleksiyon: `Enterprise ATT&CK`, sürüm `20.0`, STIX `2.1`.
- Mevcut parser aynı paketten **982 varlık / 809 ilişki** üretti.
- Aşağıdaki etkinlik sayımı `revoked` veya `x_mitre_deprecated` doğru
  olan nesneleri dışarıda bırakır. İlişkinin uçlarının etkinliği ayrıca
  kontrol edilmiştir; bütün ilişki sayısı seçili kapsam sayısı değildir.

| Paketteki STIX türü | Toplam | Etkin |
| --- | ---: | ---: |
| `attack-pattern` | 867 | 706 |
| `campaign` | 57 | 57 |
| `intrusion-set` | 193 | 178 |
| `malware` | 750 | 747 |
| `tool` | 95 | 95 |
| `x-mitre-tactic` | 15 | 15 |
| `relationship` | 21.819 | 21.819 |
| `course-of-action` | 268 | 44 |
| `x-mitre-analytic` | 1.770 | 1.770 |
| `x-mitre-data-component` | 109 | 106 |
| `x-mitre-data-source` | 38 | 0 |
| `x-mitre-detection-strategy` | 705 | 703 |
| `identity`, `marking-definition`, `x-mitre-collection`, `x-mitre-matrix` | Her biri 1 | Her biri 1 |

Dar kapsam mevcut üç varlık türüne `attack-pattern` ve `x-mitre-tactic`
eklediğinde **1.703 etkin varlık** ve uçları bu kapsamda olan **18.055
etkin STIX ilişkisi** oluşur. `tool`, savunma/analitik nesneleri ve diğer
STIX türleri bu teslimde içeri alınmayacak.

| İlişki yönü | Sayı |
| --- | ---: |
| campaign → attributed-to → intrusion-set | 26 |
| campaign → uses → malware | 92 |
| intrusion-set → uses → malware | 691 |
| campaign → uses → attack-pattern | 1.213 |
| intrusion-set → uses → attack-pattern | 4.815 |
| malware → uses → attack-pattern | 10.739 |
| attack-pattern → subtechnique-of → attack-pattern | 479 |

706 teknik kaydının **227'si ana teknik, 479'u alt tekniktir**. Etkin
alt tekniklerin her birinin tam bir etkin ana teknik bağı var; bu kapsamda
yinelenen kaynak/tür/hedef ilişki üçlüsü veya koleksiyon dizini uyuşmazlığı
bulunmadı. Bunlar yalnız ölçülen paketin özellikleridir; doğrulayıcıda
hatalı gelecek girdileri kabul etme gerekçesi değildir.

`kill_chain_phases` üzerinden **881 teknik–taktik bağı** ölçüldü. Hepsinin
`kill_chain_name` değeri `mitre-attack`; bütün `phase_name` değerleri 15
etkin taktiğin `x_mitre_shortname` alanıyla eşleşiyor. Bu bağlar yukarıdaki
18.055 STIX ilişkisinin içinde değildir; ayrı nesne ilişkisi gibi
uydurulmayacak, türetildikleri alanla birlikte gösterilecek.

Tüm etkin tekniklerde `x_mitre_is_subtechnique`, `x_mitre_platforms`,
`kill_chain_phases`, `x_mitre_domains`, `description` ve `spec_version`
alanları mevcut. Tüm etkin taktiklerde `x_mitre_shortname`,
`x_mitre_domains`, `description` ve `spec_version` mevcut.
Alt teknik `T1059.001` bağlantısı `/techniques/T1059/001`; taktik
`TA0002` bağlantısı `/tactics/TA0002` biçimindedir.

## Uygulamadan önce çözülmesi gerekenler

| Mevcut kanıt | Tasarıma etkisi |
| --- | --- |
| [schema.py](../../src/xti/adapters/schema.py), `CTI_KNOWLEDGE_DDL`: `UNIQUE(entity_type, name_key)`; [cti_attack.py](../../src/xti/domain/cti_attack.py), `validate_attack_snapshot`: tür/ad tekilliği | Teknikleri yalnız adla kimliklendirmek yanlış. Ölçümde **23 aynı-ad grubu, 48 teknik kaydı** var; örneğin `DNS`: `T1590.002` ve `T1071.004`. |
| [mitre_attack.py](../../src/xti/adapters/mitre_attack.py), `_TYPE_MAP`, `_external_reference`, ilişki seçimi | Yeni STIX türleri, `Txxxx.xxx`/`TAxxxx` kimlikleri, URL biçimleri ve `subtechnique-of` henüz desteklenmiyor. |
| [cti_attack.py](../../src/xti/domain/cti_attack.py), `ATTACK_RELATIONSHIP_LIMIT`; [sqlite_cti_knowledge.py](../../src/xti/adapters/sqlite_cti_knowledge.py), `_audit_attack_source` | **2.000 ilişki sınırı 18.055 kayda yetmiyor.** Sınırlar parser/domain/depo denetimlerinde birlikte gözden geçirilmeli; sınırsız yapılmamalı. |
| Aynı domain ve SQLite denetimlerinde sabit açıklama, URL ve ilişki yönü politikaları | Yalnız parser değişikliği mevcut geçmiş denetimini bozar. Eski iddiaların biçimi korunmalı. |
| `AttackEntityRecord.description` 2.000 karakter sınırı; mevcut açıklama gerçek kaynak metni değil | **118 teknik açıklaması 2.000 karakteri aşıyor**, en uzunu 4.680; ayrı katalog alanı ve açık uzunluk politikası gerekir. Taktik açıklaması en çok 769 karakter. |
| `ATTACK_SOURCE_URL` sürüm adlı dosyayı `master` üzerinden okuyor | Sürüm sabit, içerik commit'e sabit değil. Yukarıdaki hash ölçüm kanıtıdır; uygulama şu anda bu hash'i zorunlu tutmaz. Güncelleme ve içerik değişikliği politikası ayrıca karara bağlanmalı. |

## Önerilen mimari ve veri koruma

Genel CTI varlık türlerini doğrudan genişletmek yerine **STIX kimliğiyle
tanımlanan ek ATT&CK katalog tabloları** öneriliyor. Bu henüz mimari karar
olarak kabul edilmiş uygulama değildir. Mevcut CTI kaynak iddiaları ve
geçmişleri korunur; yeni katalog ad değişse de aynı kaynak kimliğini tutar.

- Nesne: STIX kimliği, dış ATT&CK kimliği, tür, ad, açıklama, kaynak URL'si,
  oluşturma/değişiklik zamanı, etkinlik ve türe özgü doğrulanmış alanlar.
- İlişki: upstream STIX ilişki kimliği, türü, iki kesin uç ve kaynak zamanı.
  Teknik–taktik üyeliği, nesne içindeki alan kaynaklı ayrı kayıt olarak kalır.
- Senkron üst bilgisi ve değişim geçmişi: sürüm, hash, zaman, tam kapsam,
  ekleme/değişme/geri çekilme. Eski ve yeni katalog aynı indirmeden üretilir;
  kalıcı yazma tek SQLite transaction içinde tamamlanır.
- Mevcut CTI ile bağ, ad benzerliğiyle kurulmaz; aynı resmî kaynak nesnesinin
  kesin kimliği/başvurusuyla kurulur. Salt okunur katalog servisi küçük bir
  port kullanır; domain ve uygulama katmanları SQLite/terminal bilmez.

Şema numarası 1–4. aşamalar bittikten sonra belirlenecek. Ek tablolar için
açık migration, mevcut benzersiz yedekleme ve rollback yolu kullanılacak.
Eski kullanıcı verileri yeniden adlandırılmayacak veya silinmeyecek;
salt okunur komut migration başlatmayacak. Normalleştirilmiş ad, arama alanı
olacak; kimlik yerine kullanılmayacak.

## Sıralı kabul kapıları

1. **Sözleşme ve örnekler:** Bu ölçümlerden küçük sentetik fixture'lar;
   ad çakışması/yeniden adlandırma, ana/alt teknik ve çok taktik bağı;
   parser/port/veri modeli sınırlarını anlatan ADR. Yeni sınırlar toplam
   26.690 nesne, 18.055 seçili ilişki ve 881 üyeliği karşılamalı.
2. **Depolama ve kurtarma:** Boş ek tablolarla yedekli migration;
   eski CTI kayıtları ve başka kaynak iddialarının korunması;
   yarıda kesilen migration/senkronun rollback'i; bozuk yerel geçmişte
   ağ öncesi ret; salt okunur komutun yazmaması.
3. **Ayrıştırma ve atomik senkron:** Kesin STIX/dış kimlik/URL, etkin uç,
   yön, ana-alt teknik ve faz doğrulaması; beklenmeyen veri durumunda
   eski snapshot'ın korunması. Aynı veri tekrarında çoğaltmama,
   geri çekme/yeniden etkinleşme ve kaynak zamanlarının korunması.
4. **Kullanıcı akışı:** `T1059`, `T1059.001`, `TA0002` ve ada göre arama;
   birden fazla aynı adı ayrı kimlikle gösterme; ilişkiler, kaynak ve
   görünümde atlanan satır sayısının terminal/JSON tutarlılığı.
   Başarılı resmî paket kabulü ve `./scripts/check` sonrasında kullanım,
   mimari ve STATUS güncellenir; ancak o zaman uygulanmış sayılır.

## Erişim ve lisans

Yeni ücretli API veya anahtar gerekmez; mevcut resmî JSON indirmesi
yeterlidir. Normal internet, yerel disk ve çalışma belleği yine gerekir.
STIX biçimi ve resmî dağıtım yolları
[MITRE veri sayfasında](https://attack.mitre.org/resources/attack-data-and-tools/)
doğrulandı; burada TAXII servisi eklemek planlanmıyor.

[Resmî ATT&CK lisansı](https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/LICENSE.txt)
14 Kasım 2026'da okundu: araştırma, geliştirme ve ticari kullanım için
telif ücreti istemeyen izin verir; kopyalarda MITRE telif bildirimi ve
lisansı korunmalıdır. Dağıtım biçimi değişirse mevcut
[üçüncü taraf bildirimi](../../THIRD_PARTY_NOTICES.md#mitre-attck)
yeniden gözden geçirilir. ATT&CK veri lisansı proje kodunun lisansı veya
eksiksiz tehdit kapsaması garantisi olarak sunulmaz.
