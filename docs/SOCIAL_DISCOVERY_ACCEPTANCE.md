# Sosyal keşif — on firma için canlı kabul

19 Kasım 2026. Varsayılan ücretsiz akış; macOS arm64 / Python 3.13.3.
İlk kod: `a5672d725a851f1543b268e6a17d9edad4bc7190` / 0.171.0.
Son kod: `1ead8300a25b72369f741fac66e26d94e88c5544` / 0.171.1.
Çekirdek81, kuyruk3; Tavily, API anahtarı ve Firecrawl kullanılmadı.

**Sonuç:** Önceden belirlenen 26 referans bağlantısının tamamı sonuçta yer
alıyor: 23 profil sayfa kanıtıyla doğrulandı, üç LinkedIn profili aday kaldı.
Bu 26 örneğin dışında kalan hesaplar ve tüm internet için doğruluk iddiası yoktur.

## Yöntem

1. On firma/domain, motor sonuçları görülmeden önce seçildi.
2. Resmî sitelerden bilinen hesap referansları toplandı. Sekiz sitede HTML
   bağlantıları, Cloudflare için kuruluşun `sameAs` kaydı, DuckDuckGo için
   `twitter:site` meta bilgisi kullanıldı. Firma ve ürün hesapları dahildir.
3. 26 referans donduruldu; motora hesap adı/adresi veya arama kaydı verilmedi.
   Her turda her firma için yeni, boş veri alanı oluşturuldu.
4. Motora yalnız domain ve firma adı verildi. 41 platformluk varsayılan
   Maigret/Sherlock kapsamı ve bağımsız sayfa kontrolü açık; ücretli arama kapalı.
5. Aynı 26 referansla ilk sonuç ve düzeltme sonrası sonuç ayrı saklandı.
   İkinci tur aynı örneklerde regresyon kabulüdür; yeni, bağımsız kör örneklem değildir.

Referans dosyası SHA-256:
`440697922801821c7590ce00f451e939a119f6264e085ab021f3060c6d874e99`.

## Firma bazında sonuç

“Doğrulandı”, profil sayfasında kimlik kanıtı bulunduğunu ifade eder.
Firmanın resmî hesabı veya taklit olduğuna otomatik karar verilmez.

| Firma ve resmî referans sayfası | Referans | İlk tur doğrulanan | Son tur doğrulanan | Son tur aday | Son tur kaçan | Son komut süresi |
|---|---:|---:|---:|---:|---:|---:|
| [Mozilla](https://www.mozilla.org/) | 3 | 3 | 3 | 0 | 0 | 15.296 sn |
| [Proton](https://proton.me/) | 2 | 0 | 1 | 1 | 0 | 12.716 sn |
| [Cloudflare](https://www.cloudflare.com/) | 3 | 3 | 3 | 0 | 0 | 12.676 sn |
| [Docker](https://www.docker.com/) | 4 | 4 | 4 | 0 | 0 | 10.499 sn |
| [Grafana](https://grafana.com/) | 3 | 3 | 3 | 0 | 0 | 9.976 sn |
| [Sentry](https://sentry.io/) | 3 | 3 | 3 | 0 | 0 | 11.833 sn |
| [Canonical](https://canonical.com/) | 2 | 1 | 1 | 1 | 0 | 11.713 sn |
| [JetBrains](https://www.jetbrains.com/) | 3 | 2 | 2 | 1 | 0 | 10.138 sn |
| [DuckDuckGo](https://duckduckgo.com/) | 1 | 1 | 1 | 0 | 0 | 10.564 sn |
| [GitLab](https://about.gitlab.com/) | 2 | 1 | 2 | 0 | 0 | 9.993 sn |

İlk tur: 21 doğrulanan, iki aday, üç kaçan. Son tur: 23 doğrulanan, üç aday,
sıfır kaçan. 26/26 bu referans kümesinde keşif kapsamıdır; genel doğruluk
veya kesinlik yüzdesi değildir. Son turdaki 248 toplam profil/aday satırının
referans dışındaki kısmı bağımsız etiketlenmedi; yanlış pozitif oranı hesaplanmadı.

## Referans hesapların tamamı

| Firma | Hesap bağlantısı | Son sonuç |
|---|---|---|
| Mozilla | [Instagram](https://instagram.com/firefox) | Sayfayla doğrulandı |
| Mozilla | [Instagram](https://instagram.com/mozilla) | Sayfayla doğrulandı |
| Mozilla | [LinkedIn](https://linkedin.com/company/mozilla-corporation) | Sayfayla doğrulandı |
| Proton | [Instagram](https://instagram.com/protonprivacy) | Sayfayla doğrulandı |
| Proton | [LinkedIn](https://linkedin.com/company/protonprivacy) | Aday; sayfa doğrulanamadı |
| Cloudflare | [GitHub](https://github.com/cloudflare) | Sayfayla doğrulandı |
| Cloudflare | [LinkedIn](https://linkedin.com/company/cloudflare) | Sayfayla doğrulandı |
| Cloudflare | [Twitter](https://x.com/cloudflare) | Sayfayla doğrulandı |
| Docker | [GitHub](https://github.com/docker) | Sayfayla doğrulandı |
| Docker | [Instagram](https://instagram.com/dockerinc) | Sayfayla doğrulandı |
| Docker | [LinkedIn](https://linkedin.com/company/docker) | Sayfayla doğrulandı |
| Docker | [Twitter](https://x.com/docker) | Sayfayla doğrulandı |
| Grafana | [GitHub](https://github.com/grafana) | Sayfayla doğrulandı |
| Grafana | [LinkedIn](https://linkedin.com/company/grafana-labs) | Sayfayla doğrulandı |
| Grafana | [Twitter](https://x.com/grafana) | Sayfayla doğrulandı |
| Sentry | [GitHub](https://github.com/getsentry) | Sayfayla doğrulandı |
| Sentry | [LinkedIn](https://linkedin.com/company/getsentry) | Sayfayla doğrulandı |
| Sentry | [Twitter](https://x.com/sentry) | Sayfayla doğrulandı |
| Canonical | [Instagram](https://instagram.com/ubuntu_os) | Sayfayla doğrulandı |
| Canonical | [LinkedIn](https://linkedin.com/company/234280) | Aday; sayfa doğrulanamadı |
| JetBrains | [Instagram](https://instagram.com/jetbrains) | Sayfayla doğrulandı |
| JetBrains | [LinkedIn](https://linkedin.com/company/jetbrains) | Aday; sayfa doğrulanamadı |
| JetBrains | [Twitter](https://x.com/jetbrains) | Sayfayla doğrulandı |
| DuckDuckGo | [Twitter](https://x.com/duckduckgo) | Sayfayla doğrulandı |
| GitLab | [LinkedIn](https://linkedin.com/company/gitlab-com) | Sayfayla doğrulandı |
| GitLab | [Twitter](https://x.com/gitlab) | Sayfayla doğrulandı |

Aday kalan üç hesabın ayrımı:

- Canonical LinkedIn `company/234280`: firma sitesinde bağlantı var; kontrol
  oturum açma sayfasına yönlendi (`non_profile_redirect`). Hesap yok denmedi.
- Proton LinkedIn `company/protonprivacy` ve JetBrains LinkedIn:
  bağlantı ve sayfa başlığı var; mevcut açık yanıt profil kimliğini yeterince
  kanıtlamadı (`insufficient_profile_evidence`). HTTP200 başarı sayılmadı.

## Kaynaklar ne katkı verdi?

| Yol | 26 referans içindeki katkısı |
|---|---:|
| Firma ana sayfasındaki bağlantı | 22 |
| Firma/domaininden üretilen kullanıcı adı adayı | 15 |
| Maigret'in bildirdiği hesap | 10 |
| Bağımsız açık sayfa kontrolüyle doğrulanan | 23 |

İlk üç satır örtüşür; sayılar toplanmaz. Kullanıcı adı üretimi hesap varlığı
kanıtı değildir. Firma sitesindeki farklı kullanıcı adlarını almak ve
bağımsız sayfa kontrolü yapmak, tek araca bağlı kalmamanın somut katkısıdır.
Bu 26 referans Sherlock'un seçili site kümesini temsil etmez; Sherlock'un
bu tabloda katkısının olmaması araçlar arasında genel başarı sıralaması değildir.

Referans dışındaki Maigret `vimeo.com/gitlab` adayı bu çalışmada HTTP404
verdi ve `not_found` olarak ayrıldı. Bu gözlem tüm Vimeo hesaplarının
yokluğu veya Maigret'in genel hata oranı olarak yorumlanmaz.

## Bulunan ve düzeltilen iki neden

- Proton, `Accept-Encoding: identity` isteğine rağmen gzip yanıtı verdi.
  İlk turda firma ana sayfasından `protonprivacy` bağlantıları çıkarılamadı.
  0.171.1 gzip açılımını aktarımda ve açılmış gövdede ayrı 2 MiB sınırıyla
  destekler. Bozuk/kesik, birden fazla üyeli ve limit aşan gzip kanıt sayılmaz.
- GitLab kökü `about.gitlab.com` adresine yönlenir. İlk sürümün kök/`www`
  listesi bu geçişi reddetti. 0.171.1 yalnız aynı domainin tam `about` hostunu
  ekler; genel alt alan gezintisi başlamaz. DNS pinning, genel IP, TLS ve
  üç HTTP adımı sınırı korunur. `gitlab-com` LinkedIn hesabı ikinci turda bulundu.

Şema, `social-discovery-v1` kararları ve önceki kayıtların biçimi değişmedi.
Önceki turdaki on gerçek makbuz yeni kodda toplama metodunu hata veren bir
kancayla kapatarak tekrar okundu; kayıt aynı kaldı, ağ çağrısı yapılmadı.
Yeni Proton sonucu ayrıca gerçek `backup`/`restore` CLI komutlarıyla ayrı,
boş bir veri alanına geri yüklendi. Özgün kayıt ve kanıt birebir korundu;
aynı anahtarın tekrarı toplama metoduna gitmeden döndü.

## Ölçülen süre ve trafik

| Ölçüm | İlk tur | Son tur |
|---|---:|---:|
| Toplam profil/aday satırı | 233 | 248 |
| Ek sayfa HTTP denemesi | 396 | 426 |
| Kaydedilen gövde baytı | 74862151 | 79220300 |
| Medyan komut süresi | 11.940 sn | 11.139 sn |
| En yakın sıra p95 (10 örnek) | 13.916 sn | 15.296 sn |
| Tavily araması/kredisi | 0 / 0 | 0 / 0 |

İstek/bayt sayaçları ek sayfa alımlarına aittir; Maigret/Sherlock iç trafiği,
HTTP başlıkları ve gövdesi kaydedilemeden kesilen yanıtlar dahil değildir.
Gzip gövde baytı aktarım boyutudur; SHA-256 açılmış gövdeye aittir.
On örnekte p95 en yavaş örneğe eşittir. Ağ/sağlayıcı değişkendir; bu kısa
ölçüm hızlanma garantisi veya 7/24 hizmet seviyesi değildir.

## Tekrar uygulama

Önce resmî sitelerdeki referansları bağımsız kaydedin; yeni veya değişmiş
hesapları önceki referanslarla karıştırmayın. Her firma için yeni veri alanı
kullanın. Örnek aşağıdadır; komut internette ücretsiz kaynaklara başvurur.

```sh
acceptance_dir=$(mktemp -d "${TMPDIR:-/tmp}/xti-social-acceptance.XXXXXX")
./xti --data-dir "$acceptance_dir/data" init
./xti --data-dir "$acceptance_dir/data" --json brand discover proton.me \
  --name Proton --idempotency-key acceptance-1
```

Aynı veri alanı ve anahtarı tekrar çalıştırmak yeni ölçüm değildir; saklanan
ilk sonucu döndürür. Canlı değişimi ölçmek için yeni veri alanı veya yeni
anahtar gerekir. Önceden bilinen hesapları keşif girdisi olarak eklemeyin.

## Kanıt ve kapsam

Özel ilk tur: `/private/tmp/xti-social-multicompany-n4woysv3`.
Özel son tur: `/private/tmp/xti-social-multicompany-0171p1-av6225h2`.
`references.json`, `run-manifest.json`, `results.json` ve firma başına
`result.json`/geçici DB vardır. Ham HTML, kullanıcı verisi ve DB Git’e alınmadı.
Geçici dosyalar kalıcı arşiv veya sunucu yedeği değildir.

Örneklem çoğunlukla teknoloji kuruluşlarıdır. Özel/giriş gerektiren hesaplar,
bütün ülke/dil seçenekleri, farklı zamanlardaki kaynak davranışı, bütün
sosyal platformlar ve firma sahipliği için genellenemez. Ücretli Tavily
orkestrasyonunun yeni canlı kabulü bu çalışmaya dahil değildir.

Linux teslimi ve otomatik testler [ayrı kabul kaydında](ACCEPTANCE_REVIEW.md);
kullanım ve JSON yüzeyi [sosyal keşif belgesinde](SOCIAL_DISCOVERY.md) tutulur.
