# XTI kurulum ve dış gereksinimler

Bu sayfa, repoyu ilk kez alan ekip üyesinin **önceden ne hazırlaması
gerektiğini** kısa biçimde gösterir. Normal XTI kurulumu için ücretli API,
Tavily anahtarı, Docker, Kafka, PostgreSQL veya web paneli gerekmez.

## Zorunlu temel

| Gereken | Neden |
|---|---|
| Git | Repoyu klonlamak ve güncellemek için. |
| Python 3.11 veya daha yeni | XTI çekirdeğini ve proje içindeki yönetilen ortamı çalıştırmak için. |
| İlk kurulumda internet | Sabitlenmiş açık kaynak bağımlılıkları indirmek için; günlük yerel kayıt okuma her zaman internet istemez. |
| Proje klasörüne yazma izni | `.venv`, `.tools` ve Git'e girmeyen `.xti-data` alanını oluşturmak için. |
| Desteklenen Linux ortamı | Sunucu teslimi ve son kabul için; güncel sınanmış ortamlar `docs/STATUS.md` içindedir. |

İlk kurulum ve kabul dört komuttur:

```sh
git clone https://github.com/mstdeveloper33/securehup_xti.git
cd securehup_xti
./setup
./handoff
```

`./setup` sır istemez ve kullanıcı Python ortamına paket kurmaz. `./handoff`
ücretli istek veya aktif tarama yapmadan teslim durumunu açıklar.

## Yalnız ilgili özelliği açarken gerekenler

| İsteğe bağlı özellik | Dış gereksinim | Güvenli hazırlama komutu |
|---|---|---|
| Tavily firma içeriği araması | Tavily hesabı ve API anahtarı | `./xti mentions configure` |
| Bright Data LinkedIn ek kanıtı | Hesap, anahtar, uygun dataset erişimi ve ticari kullanım kararı | `./xti brand brightdata configure` |
| İsteğe bağlı WHOIS abuse fallback | RDAP açık abuse iletişimi vermediğinde yerel `whois` aracı ve ilgili kayıt servisinin kullanım koşulu kararı | `./xti action contact-capabilities` |
| GitHub hesaplı kod araması | İzinleri sınırlandırılmış GitHub token'ı | `./xti code configure github` |
| GitLab hesaplı kod araması | İzinleri sınırlandırılmış GitLab token'ı | `./xti code configure gitlab` |
| Telegram kanal izlemesi | Telegram API bilgileri, kullanıcı oturumu ve seçilmiş kamu kanalı | `./xti content configure`, ardından `./xti content telegram-login` |
| Discord kanal izlemesi | Bot token'ı ile erişim izni verilmiş sunucu/kanal | `./xti content configure` |
| Yönetilen Nmap | Nmap kurulumu ve yazılı olarak yetkilendirilmiş kesin hedef/port/trafik kapsamı | `./scripts/setup-nmap`, ardından `./xti surface nmap readiness` |
| AIL, Cowrie veya CAPE | XTI dışında ayrı, güvenli ve yasal işletilen altyapı | `docs/DARKWEB_MONITORING.md` ve `docs/TELEMETRY.md` |

Bu gereksinimlerden hiçbiri temel kurulumun ön koşulu değildir. Eksik olan
özellik `GEREKSİNİM BEKLİYOR` görünür; çalışan anahtarsız özellikler çalışmaya
devam eder. Bütün kaynakların ayrıntılı ve güncel durumu:

```sh
./handoff --plan --details
```

XposedOrNot domain/parola entegrasyonu yeni kullanımda kapalıdır; hesap,
anahtar veya domain doğrulaması hazırlamayın. Eski maskeli kayıtlar varsa
yalnız okunur korunur.

## Sır güvenliği

- Anahtarı sohbete, Git'e, komut argümanına, rapora veya veritabanına yazma.
- Yukarıdaki `configure` komutları gizli terminal girişi ve özel izinli dosya
  kullanır.
- Sohbette, logda veya ekran görüntüsünde daha önce açığa çıkan anahtarı canlı
  anahtar sayma; sağlayıcı panelinden iptal edip yenisini üret.
- `./handoff` yalnız yapılandırmanın varlığını gösterir; hesabın kotasını,
  sözleşmesini veya canlı kaynak doğruluğunu kendiliğinden onaylamaz.

Tam ekip teslim akışı [ekip rehberindedir](docs/TEAM_HANDOFF.md).
