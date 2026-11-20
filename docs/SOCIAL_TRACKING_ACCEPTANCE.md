# Sosyal takip 0.174.0 — yeni kuruluşlar ve ortak kuyruk kabulü

20 Kasım 2026 · macOS arm64 / Python 3.13.3 · çekirdek84 / kuyruk3.
Temel commit `f85097d92af67cba510b664f5d426f95ef7d0d61` üzerine 0.174.0
değişiklikleriyle çalışıldı. Maigret0.6.6 / Sherlock0.16.2 incelenmiş
kurulumları kullanıldı. Tavily ve Bright Data çağrısı yapılmadı.

## Yöntem

Altı yeni kuruluş iki ayrı parti halinde seçildi. Her partide motor
çalıştırılmadan önce kuruluşların resmî ana sayfalarındaki Instagram,
X, LinkedIn ve GitHub hesap bağlantıları bağımsız HTML `a/href` çıkarımıyla
kaydedildi. Referanslar zaman damgası/hash ile donduruldu. Motora bu hesap
adresleri verilmedi; yeni boş veri alanında yalnız domain ve kuruluş adı
ile varsayılan 41 platform / 40 profil sayfası / 90 saniye bütçesi kullanıldı.

Bu, bütün hesapların veya resmî sahipliğin doğruluk testi değildir.
Kullanıcı adı aynı olan farklı hesaplar bulunabilir; `found` profil sayfası
kimliğinin doğrulandığını anlatır. İnsan sahiplik/taklit kararı ayrı kalır.

## Yeni kuruluş sonuçları

| Kuruluş / referans sayfası | Dondurulmuş referans | Sayfayla doğrulanan | Aday | Kaçan | Keşif süresi |
|---|---:|---:|---:|---:|---:|
| [Blender](https://blender.org/) | Ölçülemedi; referans alımı HTTP hatası | — | — | — | 11,855 sn |
| [Python Software Foundation](https://python.org/) | 2 | 1 | 1 | 0 | 12,528 sn |
| [Patagonia](https://patagonia.com/) | Seçili dört platform için href referansı yok | — | — | — | 10,273 sn |
| [Doctors Without Borders / MSF](https://msf.org/) | 3 | 2 | 1 | 0 | 14,106 sn |
| [NASA](https://nasa.gov/) | 2 | 2 | 0 | 0 | 11,316 sn |
| [WWF](https://worldwildlife.org/) | Ölçülemedi; referans alımı HTTP hatası | — | — | — | 9,871 sn |

**Yedi dondurulmuş referansın beşi sayfayla doğrulandı, ikisi aday kaldı;
sonuç dışında kalan referans yok.** Diğer üç kuruluştaki referans eksikliği
başarı veya sıfır kaçırma sayılmaz; onlarda kaynak davranışı/süre ölçüldü.
HTTP hata kodu bağımsız referans betiğinde saklanmadığından 403/429 veya
kesin sağlayıcı kök nedeni iddiası yoktur. Patagonia için çıkarımın boş
olması kuruluşun sosyal hesabı olmadığı anlamına gelmez.

| Referans hesabı | Sonuç / köken |
|---|---|
| [PSF X / thepsf](https://x.com/thepsf) | Bulundu; firma sayfasındaki farklı kullanıcı adı |
| [PSF LinkedIn](https://linkedin.com/company/python-software-foundation) | Aday; başka profil adresine yönlendirme yeterli kimlik kanıtı sayılmadı |
| [MSF Instagram](https://instagram.com/doctorswithoutborders) | Bulundu; firma sayfası ve ad türetimi |
| [MSF X](https://x.com/msf) | Bulundu; firma sayfası, türetim ve Maigret |
| [MSF LinkedIn](https://linkedin.com/company/m-decins-sans-fronti-res-msf-) | Aday; farklı profil adresine yönlendirme |
| [NASA Instagram](https://instagram.com/nasa) | Bulundu; firma sayfası ve türetim |
| [NASA X](https://x.com/nasa) | Bulundu; firma sayfası, türetim ve Maigret |

Altı kuruluşta toplam 180 profil/aday/yokluk/belirsiz satırı üretildi.
Referans dışındaki satırlar bağımsız sahiplik etiketi almadı; yanlış
pozitif oranı veya genel doğruluk yüzdesi hesaplanmadı. Bu yeni örneklem
[önceki on kuruluş / 26 referans](SOCIAL_DISCOVERY_ACCEPTANCE.md) ile
farklı zamana aittir; tek bir birleşik güncel başarı yüzdesi sayılmaz.

Medyan keşif süresi **11,586 saniye**, en yavaşı **14,106 saniye**.
Ek sayfa HTTP denemesi **305**, kaydedilen gövde baytı **56.910.651**.
Maigret/Sherlock iç trafiği bu sayılara dahil değildir; genel trafik veya
sunucu kapasitesi sonucu çıkarılamaz. Altı örnekte en yakın sıra p95 en
yavaş örneğe eşittir; SLA veya her ağda hız garantisi değildir.

## Gerçek ortak worker ile iki takip turu

MSF keşfinden izleme oluşturuldu. Yerel **mevcut engine-jobs kuyruğu**
başlatılıp `social-tracking` planı iki ayrı anahtarla kabul edildi. Her
iş ortak worker tarafından çalıştırıldı. Canlı ölçümde interval beklenmesin
diye `social_force=true` açıkça seçildi; platform/ücret sınırları değişmedi.

| Ölçüm | İlk tur | İkinci tur |
|---|---:|---:|
| Worker süresi | 13,189 sn | 12,654 sn |
| Saklı adres / bu tur seçilen | 35 / 20 | 37 / 20 |
| Seçilen saklı adresten kontrol edilen | 20 | 20 |
| Toplam profil sayfası kontrolü | 40 | 40 |
| Ek sayfa HTTP denemesi | 68 | 70 |
| Değişiklik | 0; sessiz başlangıç | 1 |
| Tamamlanamayan kontrol | 2 | 30 |
| Kaynak durumu | partial | partial |

İkinci turdaki tek fark `https://vimeo.com/msf` için `profile_found`:
ilk tur sayfa bütçesi nedeniyle kaynak adayıydı, sonraki tur sayfada
profil kimliği bulundu. Hesap yeni açıldı veya firma sahibi otomatik
doğrulandı denmedi. Bütçeye sığmayan ve erişimi doğrulanamayan diğer
kontroller açık kaldı; bütün hesaplar kontrol edildi sayılmadı.

İki işte de aynı anahtarla submit tekrarında aynı kayıt döndü. Bitmiş işi
worker tekrar almadı. Toplama metodu hata veren bir kancayla kapatılarak
bu tekrarların ağsız olduğu ayrıca doğrulandı. Tool iç trafiği bilinmediği
için toplam HTTP sayacı `null`, sayfa denemeleri ayrı kaldı.

## Kontrollü senaryolar ve canlı ölçüm ayrımı

Kaynak sayfasından kaybolan farklı kullanıcı adı, küçük bütçede dönüşümlü
kontrol, timeout/429/challenge, yanlış profile yönlendirme, soft404,
pause/revision değişimi, iki firma ayrımı, kesintiden toparlanma ve
ücretli çağrı yapılmaması otomatik kontrollü testlerde sınanır. Bunlar
ek canlı referans sayısı değildir. Eski makbuz/satır/rowid koruması ve
test koşuları [kabul kaydında](ACCEPTANCE_REVIEW.md) ayrı tutulur.

## Tekrar üretme ve kanıt

Referanslar motor sonuçlarına bakılmadan önce dondurulmalıdır. Önceki
sonucu yeniden okumak yeni canlı ölçüm değildir. Yeni kuruluş için:

```sh
acceptance_dir=$(mktemp -d "${TMPDIR:-/tmp}/xti-social-acceptance.XXXXXX")
./xti --data-dir "$acceptance_dir/data" init
./xti --data-dir "$acceptance_dir/data" --json brand discover python.org \
  --name 'Python Software Foundation' --idempotency-key acceptance-1
```

Birinci referans SHA-256:
`16b7c504e77096bb4b79f5854cd2d4b1fa3b76cf9d5e21e169859296c07a70c9`.
İkinci referans SHA-256:
`20fe107158dc75366bd3545a2281f464a48c61e818670960f3904b08f4527f9f`.

Özel geçici alanlar `/private/var/folders/jm/lvrm0h653sb692bmcp431j580000gn/T/`
altındaki `xti-social-0174-0nz233ya` ve `xti-social-0174-g9nujys6`.
`references.json`, `run-manifest.json`, domain başına `result.json`/DB ve
ilk alandaki `queue-acceptance.json` korunuyor. Ham yanıt/DB Git'e alınmadı.
Geçici alanlar kalıcı yedek değildir; bu belgede ölçüm özeti saklanır.
