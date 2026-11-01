# 0123 — Doğrulanmış marka araç kurulumu ve sürümlü kapsam profilleri

**Durum:** Kabul edildi

**Tarih:** 2 Kasım 2026

**Sürüm:** 0.125.0

## Bağlam

Maigret ve Sherlock daha önce ayrı bir komutla isteğe bağlı kuruluyor ve canlı
adaptörler dar platform listeleriyle çalışıyordu. Kullanıcı temiz klondan sonra
tek kurulum komutu, daha geniş ama denetlenebilir kapsam ve upstream sürüm
değişikliklerinin sessizce davranış değiştirmemesini istedi.

Upstream araçların bütün kataloglarını açmak uygun değildir. Kataloglarda HTTP,
NSFW, başka bir servise yönelen, kullanıcı profili yerine arama sonucu veren ve
XTI'ın incelemediği binlerce tanım bulunabilir. Yalnız paket sürümünü kontrol
etmek de aynı sürüm numaralı farklı commit veya değiştirilmiş katalog riskini
ayıramaz.

## Karar

- Normal `./setup`, çekirdekten önce `setup-brand` çalıştırır. Yalnız çekirdek
  isteyen kullanıcı `./setup --core-only` seçebilir.
- Maigret 0.6.6 ve Sherlock 0.16.2, `pyproject.toml` içinde resmî depolarının
  tam incelenmiş commit'lerine sabit kalır. Kurulum global Python'a değil proje
  `.venv` ortamına yapılır.
- Kurulum mevcut `.venv` ortamını önce sabit adlı proje-içi geri dönüş
  kopyasına taşır; yeni ortamı kararlı `.venv` yolunda oluşturur. `pip check`
  veya XTI doğrulayıcısı geçmezse kısmi ortam kaldırılır ve önceki ortam geri
  konur. PID kilidi eşzamanlı kurulumu durdurur; yetim işaretli yarım kurulum
  sonraki denemede güvenli biçimde geri alınır.
- Doğrulayıcı paket sürümünü, dağıtımın `direct_url.json` resmî depo adresini,
  Git türünü, istenen ve çözülen tam commit'i, dağıtım konumunu, katalog dosyası
  türünü/boyutunu/SHA-256 özetini, Maigret çalıştırıcısını ve bütün geniş profil
  tanımlarının izinli HTTPS hostlarını kapalı biçimde denetler.
- Geçişli Python bağımlılıkları `constraints/brand.txt` içinde incelenmiş tam
  sürümlere bağlanır ve doğrulayıcı kurulu sürümleri yeniden denetler. Pip
  kullanıcı yapılandırmasından yalıtılmış çalışır, resmî PyPI indeksini açıkça
  kullanır; Git sistem/global yapılandırması devre dışı bırakılarak iki resmî
  GitHub URL'sinin yeniden yazılması engellenir.
- Geçerli kurulum tekrar indirilmez. `setup-brand --check` yalnız denetler;
  `--force` aynı atomik yoldan bilinçli yeniden kurar.
- Kullanıcı adı komutları üç kapsam biçimi alır: seçenek verilmezse `safe`,
  açık `--profile extended` veya tekrarlı `--site` ile `custom`. Profil ve özel
  site seçimi birlikte kullanılamaz.
- `safe` mevcut davranışı korur. Maigret için GitHub, GitLab, Reddit,
  Instagram, TikTok ve YouTube; Sherlock için Carrd, CodeSandbox, GitBook,
  Rumble ve Weebly kullanılır.
- Maigret `extended` profili şu 30 tanımdır: Behance, BitBucket, Bluesky,
  BuyMeACoffee, Codepen, Facebook, Flickr, GitHub, GitLab, HackerNews,
  HuggingFace, Instagram, Kaggle, Keybase, LinkedIn, Medium, Patreon,
  Pinterest, ProductHunt, Reddit, Replit, SoundCloud, Steam, Telegram, Threads,
  TikTok, Twitter, Vimeo, WordPress ve YouTube.
- Sherlock `extended` profili şu 26 tanımdır: Behance, BitBucket, Bluesky,
  BuyMeACoffee, Carrd, CashApp, Codeberg, Codepen, CodeSandbox, Flickr,
  GitBook, HackerNews, Kaggle, Linktree, Medium, Patreon, Pinterest,
  ProductHunt, ResearchGate, Rumble, SoundCloud, Strava, Telegram, Twitch,
  Vimeo ve Weebly.
- Her tanım upstream sabit katalogdaki `url`, `urlMain`, `urlProbe` ve Sherlock
  için `errorUrl` alanlarıyla kontrol edilir. HTTP kullanan Gravatar, profil
  yerine arama sonucu veren StackOverflow, üçüncü taraf Twitch izleyicisi ve
  göreli `errorUrl` kullanan Sherlock WordPress bu profillere alınmaz.
- Upstream tam katalog, otomatik katalog güncellemesi, NSFW hedefler, proxy/Tor,
  kota aşma, toplu kullanıcı adı, kullanıcı adı türetme ve profil ayrıntısı
  çıkarımı kapalı kalır.
- Geniş profildeki süreyi karşılamak için bütün Maigret süreci en fazla 300,
  Sherlock işçisi en fazla 100 saniyeyle sınırlıdır. Platform başına açık
  5–30 saniye sınırı değişmez.
- Önizleme çıktısı `safe`, `extended` veya `custom` seçimini açıkça taşır.
  Kalıcı izleme profil adını değil oluşturma anında çözülen tam platform
  listesini saklar; böylece ileride profil sürümü değişse bile mevcut kapsam
  sessizce değişmez.

## Sonuçlar

Temiz klonda tek komut sosyal araçları da hazırlar; yarım indirme çalışan ortamı
bozmaz. Sürüm numarası doğru görünse bile farklı commit veya katalog kabul
edilmez. Kullanıcı dar ve daha hızlı kapsamı korur, isterse incelenmiş geniş
kapsamı açıkça seçer.

Geniş profil “sınırsız” veya bütün internet değildir. Platform erişilebilirliği,
oran sınırı ve kullanım koşulları XTI'ın kontrolünde değildir. Raporlanmayan
platform hesap yokluğunu; bulunan aynı kullanıcı adı da sahiplik, kişi özdeşliği
veya taklidi kanıtlamaz. İnsan incelemesi ve platform koşullarına uygun kullanım
zorunludur.

Şema 54 değişmez. Üçüncü taraf kaynak kodu ve kataloglar XTI Git deposuna
kopyalanmaz.

## Kabul kanıtı

Otomatik testler `safe`/`extended`/`custom` çözümünü, profil-site çakışmasını,
iki kaynak platform ayrımını, kalıcı tam listeyi, kaynak-sonuç doğrulamasını ve
varsayılan/çekirdek-only kurulum sırasını kapsar. Kurulum doğrulayıcısı iki tam
commit'i, katalog boyutu/özetini ve bütün geniş profillerin geçici kapsam
kataloğuna güvenle ayrılabildiğini denetler. GitHub Actions, ağsız tam testten
ayrı olarak temiz Python 3.11 ortamında varsayılan kurulumu ve ikinci ağsız
`--check` çalışmasını yürütür.
