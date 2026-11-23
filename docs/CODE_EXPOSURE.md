# Kod deposu ve paste izleme — P01 / A03

0.180.0, çekirdek şema 89, kaynak işi 8, dış JSON sözleşmesi1.
Motor firma/domain ile ilgili açık depo içeriklerini internetten bulur;
marka geçişlerini ve hassas bilgi **adaylarını** ayrı kaydeder. Sonuçta
hangi kaynak, depo, dosya, sürüm ve satırın ilgili olduğu görülebilir.
Ham dosya, eşleşen anahtar veya parola kaydedilmez. Bulunan değerle giriş
yapılmaz; biçim eşleşmesi çalışır anahtar veya firma sahipliği kanıtı değildir.

Paketin gerçek kabul durumu [P01 teslim kaydında](roadmap/P01_DELIVERY.md).
GitHub/GitLab genel kod araması ve Pastebin için canlı erişim henüz yoktur;
bu bağlantılar kontrollü yanıtlarla sınandı. Kamu deposu keşfi canlı denendi.

## Anahtar gerektirmeyen başlangıç

Yeni kurulumda `./setup` Betterleaks'i de kurar. Mevcut kurulumda:

```sh
./scripts/setup-code
./xti migrate
./xti code sources
./xti code watch-add securehup.com --name SecureHup
```

`watch-add` çıktısındaki izleme kimliğini sonraki komutlarda `IZLEME_ID`
yerine yaz. `plan` ağ isteği yapmaz; `run` internetten okur ve sonuç kaydeder:

```sh
./xti code plan IZLEME_ID
./xti code run IZLEME_ID --idempotency-key securehup-ilk-tur
./xti code findings --domain securehup.com
./xti code show BULGU_ID
./xti code report securehup.com
```

Bir API anahtarı şu an zorunlu değildir. Varsayılan kaynaklar kamu GitHub
depo keşfi ve kamu GitLab proje keşfidir. Kaynakların anonim kotası ve arama
kapsamı sınırlıdır; genel kod aramasıyla aynı kapsamı vermezler.

Bilinen depo ayrıca eklenebilir; bu internetten keşfin yerine geçmez:

```sh
./xti code watch-add example.com --name 'Örnek Şirket' \
  --alias 'Example Company' --repository https://github.com/example/project \
  --max-requests 30 --max-files 20 --budget-seconds 120
```

Depo tanımlamak sahiplik doğrulaması değildir. Bir firma adına benzeyen
deponun gerçekten firmaya ait olduğu varsayılmaz.

## Kaynakların gerçek kapsamı

| Kaynak | Erişim | Aradığı/okuduğu kapsam | Canlı kabul |
| --- | --- | --- | --- |
| `github-repositories` | Anahtarsız kullanılabilir | Firma terimi README aramasında geçen kamu depoları + tanımlanan depolar; güncel ağaçtaki sınırlı metin dosyaları | SecureHup denemesi yapıldı; dosya bütçesi nedeniyle kısmi |
| `gitlab-projects` | Anahtarsız kullanılabilir | Kamu proje araması + tanımlanan depolar; güncel sürümde sayfalı dosya ağacı | SecureHup sorgusunda HTTP 200 ve boş liste |
| `github-code` | GitHub anahtarı | Sağlayıcının kod arama indeksindeki kamu sonuçları | Anahtar yok; canlı başarı yolu açık |
| `gitlab-code` | GitLab anahtarı ve hesabın arama kapsamı | Sağlayıcının genel kod araması; kaynak planı/indeksi sonucu etkiler | Anahtar yok; canlı başarı yolu açık |
| `pastebin` | Sağlayıcının scraping erişimi | Son kamu paste penceresi; tam geçmiş araması değildir | Erişim ve güncel koşullar doğrulanmadı |

Pastebin varsayılan açık değildir; `--source pastebin` açıkça seçilir.
Erişim reddi atlatılmaz. Özel depolar kapsam dışıdır. Dosya içeriği alınırken
hesap anahtarı gönderilmez; içerik kamu erişimiyle okunabilmelidir.
GitLab genel kod aramasının mevcut olması, tüm hesaplarda kullanılabildiği
anlamına gelmez. Kaynağın koşulları [N-044](../NOTES.md#n-044--p01--a03-kaynak-erişimi-ve-secret-inceleme-aracı)
altında açık tutulur.

Her tur domain, ad ve alternatif adlar arasında dönüşümlü sorgu seçer.
Arama sayfaları, depo sırası, dosya konumu ve GitLab ağaç sayfaları sonraki
tura taşınır. Sağlayıcı arama penceresi en fazla 33 × 30 sonuçtur; keşif tüm
depoları veya geçmiş commit'leri kapsamaz. Tek büyük depo diğer depoları
sürekli ilk sırada tutmaz. Çok sık değişen indeksler yine sonuç atlayabilir.
Silinen/özel yapılan dosya otomatik “giderildi” sayılmaz; erişilemediği
kaydedilir. Yalnız aynı dosya başarıyla okunup eşleşme görülmezse
`not_observed_in_file` durumu oluşur.

## Kullanıcıya gösterilen kayıt

`brand_mention` firma teriminin metinde geçtiğini, `secret_candidate`
Betterleaks kuralının hassas değer biçimi bulduğunu anlatır. İkisi de insan
incelemesine açıktır. Dosya metni ve secret değeri yerine kaynak URL'si,
depo/dosya yolu, sürüm/blob kimliği, içerik SHA256, kural ve satır saklanır.
Dosya yolu ve kaynak metaverisi korunur; bütün üçüncü taraf metaverisinin
her türlü kişisel veriden arındırıldığı iddia edilmez.

Aynı kaynağın aynı içerik gözlemi yeniden kanıt gövdesi oluşturmaz. Farklı
kaynaklardaki aynı içerik `content_group` ile gruplanır; kaynak bağlantıları
ayrı kalır. Aynı grubun iki yerde görünmesi iki bağımsız doğrulama değildir.

```sh
./xti code findings --domain example.com --kind secret_candidate --limit 100
./xti code findings --domain example.com --after SONRAKI_SIRA --limit 100
./xti code evidence KANIT_ID
./xti code reviews BULGU_ID --limit 100
```

Liste sonucu `next_after` verir. Detay son 20 kararı içerir; bütün geçmiş
`reviews` ile sayfalanır. `evidence` eski değişmez kanıtı kimliğiyle açar.
`code sources` yalnız yerel kurulum/yapılandırma kontrolüdür; kaynaklara
o an bağlandığını veya hesabın yetkili olduğunu göstermez.

## İnsan incelemesi ve vaka

Kararlar: `relevant`, `unrelated`, `example`, `uncertain`, `remediated`.
Önce `show` çıktısındaki kanıt, gözlem sürümü ve inceleme sürümünü incele:

```sh
./xti code review BULGU_ID --evidence-id KANIT_ID \
  --observation-revision 1 --expected-revision 0 \
  --decision uncertain --reason 'Firma sahipliği henüz doğrulanmadı.' \
  --idempotency-key inceleme-1
./xti cases create 'Kod maruziyeti incelemesi' --summary 'Firma bağı ve kaynak kanıtı' \
  --reason 'Adayı insan incelemesine al.'
./xti cases evidence-add VAKA_ID --type code_exposure --evidence-id BULGU_ID \
  --reason 'İncelenen kaynak kanıtını vakaya bağla.'
```

CLI'da sürümler verilmezse yazıcı kilidi altında güncel sürüm alınır;
eski bir ekran/çıktı üzerinden karar veriyorsan sürümleri açıkça gönder.
Firma JSON yazmasında iki sürüm ve kanıt kimliği zorunludur.
Yeni kanıt veya yokolma/yeniden görünme gözlem sürümünü artırır. Önceki
insan kararı silinmez; yeni gözlem için `needs_review=true` olur. Böylece
aynı içerik geri geldiğinde eski “giderildi” kararı güncel onay sayılmaz.
Vaka kopyası sonraki kontrol veya kararla değişmez.

Domain kuruluşun varlığına bağlanmışsa `organizations report` içinde
kod/paste adayları ve kaynak çalışma durumu görünür. Son deneme kısmi veya
başarısız olduğunda eski kanıt korunur; eski başarılı tur ayrıca gösterilir.

```sh
./xti assets add example.com
./xti organizations add 'Örnek Şirket'
./xti organizations link KURULUS_ID --kind domain --value example.com
./xti organizations report KURULUS_ID
```

`VAKA_ID` ve `KURULUS_ID`, oluşturma komutlarının döndürdüğü kimliklerdir.

## İzleme, kesinti ve tekrar

İlk kullanılabilir ölçüm kaynak başına başlangıçtır; toplu eski içerik için
bildirim yağdırmaz. Başlangıçtan sonraki yeni aday/değişiklik/yokluk aynı
transaction içinde değişiklik geçmişine ve ortak `inbox` kutusuna yazılır.
Kapsam değişirse yeni başlangıç oluşturulur; eski kanıt ve karar korunur.

```sh
./xti code changes --watch-id IZLEME_ID
./xti inbox list
./xti code monitor IZLEME_ID --cycles 3
./xti code watch-update IZLEME_ID --disable
./xti code watch-update IZLEME_ID --enable --interval-seconds 86400
./xti code runs --watch-id IZLEME_ID
./xti code run-show CALISMA_ID
```

`monitor` açık kaldığı sürece seçilen sayıda tur yapar, tur aralarında
izleme aralığını bekler. Kendi başına 7/24 sunucu hizmeti kurmaz.
`--force` yalnız yerel tur zamanını atlar, sağlayıcı kota beklemesini atlamaz.
Yeni tarama yeni `--idempotency-key` kullanır. Aynı anahtar aynı kaydı
döndürür ve yeni ağ isteği yapmaz. Farklı parametreyle aynı anahtar reddedilir.

Kesilen çalışma için `code recover CALISMA_ID` eski sonucu koruyup
kesildi kaydı oluşturur; ağ isteğini tekrar etmez. Ardından yeni tekrar
anahtarıyla yeni tur açıkça istenir. İş kuyrukta yürüdüyse kaynak işi
`retry --allow-uncertain` akışı kullanılır. Çekirdek sonucu tamamlanıp
kuyruk makbuzu yazılamamışsa bu sonuç bulunarak kullanılır; ağ tekrarlanmaz.

## Ortak iş kuyruğu ve firma JSON

Yerel örnek; plan süresi/istek bütçesi kayıtlı izlemeden küçük olmamalı:

```sh
./xti source-jobs init
./xti source-jobs plan example.com --type domain --source code-monitor \
  --code-watch IZLEME_ID --code-revision 1 --max-requests 30 --max-seconds 180
./xti source-jobs submit example.com --type domain --source code-monitor \
  --code-watch IZLEME_ID --code-revision 1 --max-requests 30 --max-seconds 180 \
  --idempotency-key kod-isi-1
./xti source-jobs worker --job-id IS_ID
./xti source-jobs result IS_ID
./xti source-jobs cancel IS_ID
```

Plan/submit ağ isteği yapmaz; worker yapar. `code-monitor` kendi bütçesiyle
tek kaynak adımıdır; seçili GitHub/GitLab/Pastebin bağlantılarını içerir.
İptal ağ istekleri arasında kontrol edilir; devam eden istek en fazla 15 sn,
dosya analizi en fazla 10 sn sınırında tamamlanır. Ani süreç ölümünde yeni
ağ isteği kendiliğinden tekrarlanmaz.

Firma alanını hazırlama ve dış süreç protokolü [PLATFORM_ENGINE](PLATFORM_ENGINE.md)
belgesindedir. `platform request --describe` güncel işlemleri listeler.
Örnek JSON; UUID yerlerine gerçek firma/izleme/kanıt kimlikleri yazılmalıdır:

```json
{"contract_version":1,"request_id":"watch-1","operation":"code.watch.add","parameters":{"expected_workspace_id":"00000000-0000-0000-0000-000000000000","domain":"example.com","name":"Example","sources":["github-repositories","gitlab-projects"],"idempotency_key":"watch-1"}}
```

```json
{"contract_version":1,"request_id":"run-1","operation":"code.run","parameters":{"expected_workspace_id":"00000000-0000-0000-0000-000000000000","identifier":"00000000-0000-0000-0000-000000000001","expected_revision":1,"idempotency_key":"run-1"}}
```

```json
{"contract_version":1,"request_id":"review-1","operation":"code.review","parameters":{"expected_workspace_id":"00000000-0000-0000-0000-000000000000","identifier":"00000000-0000-0000-0000-000000000002","evidence_id":"00000000-0000-0000-0000-000000000003","expected_revision":0,"expected_observation_revision":1,"decision":"uncertain","reason":"Firma bağı incelenecek.","idempotency_key":"review-1"}}
```

Okumalar: `code.sources`, `code.watch.list/show`, `code.plan`, `code.runs`,
`code.run.show`, `code.findings`, `code.finding.show`, `code.reviews`,
`code.evidence.show`, `code.changes`, `code.report`. Ağsız `engine`
ile de kullanılabilir. Yazmalar: `code.watch.add/update`, `code.run`,
`code.recover`, `code.review`; firma yazmaları `expected_workspace_id`
gerektirir. UI uzun süren taramayı `sources.plan → sources.jobs.submit →
worker → sources.jobs.result` zinciriyle çağırabilir.

Anahtarlar JSON'a verilmez. HTTP değil mevcut süreç tabanlı JSON sözleşmesi
kullanılır; REST/oturum yönetimi bu paketle eklenmedi. `code.run` sonucunda
CLI tam tur için 0, kısmi/başarısız tur için 3 döndürür; platform başarılı
işlem zarfında iç `data.status` da okunmalıdır. Sözleşme hatalarında
[platform çıkış tablosu](PLATFORM_ENGINE.md#hata-ve-süreç-çıkış-kodları) geçerlidir.

## Sınırlar, kurulum ve güncelleme

Varsayılan 30, en fazla 100 HTTP isteği/dosya; süre varsayılan 120 sn,
en fazla 600 sn. Dosya 256 KiB, toplam alınan veri 32 MiB, tek tur en fazla1.000
aday. Kaynaklar bütçeyi paylaşır. Bunlar tek tur sınırıdır; saklanan geçmişe
toplam aday sınırı konmaz. İkili/büyük dosyalar ve sağlayıcının kırptığı
ağaçlar eksik kapsamda görünür. `complete` yalnız seçilmiş kaynak penceresi
tamamlandı demektir; internette başka sızıntı bulunmadığı iddiası değildir.

Betterleaks 1.10.1 ayrı süreçtir; pin ve platform arşiv SHA256'ları
[betterleaks_pin.py](../src/xti/domain/betterleaks_pin.py) içindedir.
Linux/macOS x86_64 ve arm64 arşivleri tanımlıdır. Yerel macOS çalışması
doğrulandı; bu sürümün Linux CI kabulü ayrıca takip edilir.
`./scripts/setup-code --check` kurulu ikili/izin/kurulum kaydını kontrol eder.
`./setup --core-only` aracı kurmaz; marka geçişi kaydedilebilir ama secret
incelemesi eksik/kısmi gösterilir. Sürüm güncellemesi yeni pin, hash,
örnek kümesi ve kabul gerektirir; otomatik `latest` yoktur. Geçersiz mevcut
kurulumun üzerine yazılmaz. `./xti components` bileşeni gösterir.

Saklama şeması88→89 açık `migrate` ile, önce yedek alarak geçer. Eski
kayıt kimlikleri, vaka satırları, bildirim okunma durumu korunur. Yeni
şemayı eski motorla açmak yerine yükseltme yedeğini boş bir hedefe
`restore` et; kullanıcı verisinin üstüne geri dönüş yapılmaz. Firma için
`platform backup/restore` çekirdek ve kuyruğu birlikte korur. Ayrıntı
[platform yedek/dönüş rehberinde](PLATFORM_ENGINE.md#birlikte-yedek-ve-yeni-alana-dönüş).

İleride hesap hazır olduğunda isteğe bağlı `./xti code configure github`
veya `./xti code configure gitlab` gizli terminal girişi kullanır. Sırlar
sohbete, komut argümanına veya repoya yazılmaz. Alternatif işletici ortamı
`XTI_GITHUB_TOKEN` / `XTI_GITLAB_TOKEN`; şirket JSON'una anahtar aktarılmaz.
Kaynak erişimi ve müşteri verisi gösterme koşulları ayrıca doğrulanmalıdır.
