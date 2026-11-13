# 0124 — Pasif kaynak bütünlüğü ve adaptör kabul kapısı

**Durum:** Kabul edildi
**Tarih:** 13 Kasım 2026
**Sürüm:** 0.126.0

## Bağlam

XTI pasif alt alan adı keşfinde doğrudan crt.sh ile sınırlandırılmış
theHarvester Common Crawl/Wayback profilini kullanıyor. Yeni açık kaynak araç
eklemek yalnız daha çok sonuç getirme ihtimaliyle gerekçelendirilemez. Kaynak
hatası ile tamamlanmış boş sonucu ayıramayan bir entegrasyon mevcut kanıt
güvenilirliğini düşürür.

İnceleme sırasında ikinci bir bütünlük sorunu da bulundu: şema, yazma yolu ve
uygulama servisi `theharvester` sağlayıcısını kabul ettiği halde kayıt okuma
doğrulaması yalnız `crt.sh` değerine izin veriyordu. Bu nedenle theHarvester
keşfi kaydedilebiliyor, fakat aday veya ilgili bildirim ayrıntısı açılırken
güvenli biçimde hata veriyordu.

## Karar

- Desteklenen pasif keşif sağlayıcıları domain katmanındaki tek sıralı sözleşme
  olarak `crt.sh` ve `theharvester` biçiminde tanımlanır. Uygulama, SQLite
  okuma/yazma doğrulaması, sağlık görünümü ve kabul kapısı aynı sözleşmeyi
  kullanır.
- theHarvester kaynak kanıtı crt.sh ile aynı katı alan ve bütünlük
  doğrulamasından geçerek okunur. Kullanıcı metinlerindeki “sertifika kanıtı”
  ifadesi sağlayıcıdan bağımsız “pasif kaynak kanıtı” yapılır.
- `surface discovery-health KÖK`, her desteklenen sağlayıcının son kayıtlı
  sonucunu ayrı gösterir. Tamamlanmış, kısmi, başarısız, hiç çalışmamış,
  güncel, eski ve zaman tutarsızlığı durumları birbirine karıştırılmaz.
- `surface discovery-status KÖK --source SAĞLAYICI`, tek sağlayıcının son
  kaydını seçer. Seçim verilmezse önceki davranış korunur ve en son genel
  çalışma gösterilir.
- İki durum komutu da yalnız kayıtlı kanıtı okur. Ağ isteği, canlı sağlık
  yoklaması, veri yazımı veya migration başlatmaz. “Güncel kayıt”, kaynağın şu
  anda erişilebilir olduğu iddiası değildir.
- `surface source-evaluation`, sürümlü `passive-surface-source-gate-v2`
  kararını depolama açmadan ve internete çıkmadan üretir. Aktif adaptörlerin
  tamamı zorunlu kapılardan geçmeli ve aktif kimlikler çalışma zamanı sağlayıcı
  sözleşmesiyle birebir eşleşmelidir.
- Zorunlu kapılar doğrulanmış upstream, incelenmiş erişim/dağıtım koşulu,
  ücretsiz seçilmiş profil, hedefe temas etmeyen pasif kullanım, sınırlandırılmış
  çalışma, katı makine sözleşmesi, sağlayıcı bazlı tamamlanma/hata ayrımı,
  bağımsız veri katkısı ve sürdürülebilir kurulumdur.

## Subfinder kararı

ProjectDiscovery Subfinder v2.17.0, commit
`c97f25802892093060f0fc424bfc3f39e273693a` üzerinden yeniden incelendi.

- Kod MIT lisanslı ve resmî sürüm binary'si sabitlenebilir.
- Pasif kullanım süre, sonuç, hız ve okuma boyutu sınırlarıyla daraltılabilir.
- Buna karşılık runner, sağlayıcı hatalarını insan-okur warning'e dönüştürüp
  genel çalışmayı başarılı bitirebilir. JSONL yalnız bulunan hostları taşır;
  sağlayıcının tamamlandığı veya hata verdiği makine-okunur bir son kayıt
  içermez.
- Bu nedenle sıfır JSONL satırı “gerçekten sonuç yok” ile “sağlayıcı
  çalışmadı” durumunu güvenilir biçimde ayırmaz.
- Anahtarsız ve koşulları incelenmiş anlamlı kaynakların büyük bölümü mevcut
  crt.sh veya theHarvester Common Crawl/Wayback kapsamını tekrarlar; ölçülmüş
  bağımsız katkı gösterilmemiştir.

Normal Subfinder CLI adaptörü bu sürümde ertelendi; araç kurulmaz, çalıştırılmaz
ve XTI ile dağıtılmaz. Gerçek kullanım ölçümü belirli bir bağımsız kapsam açığı
gösterirse, Subfinder'ın Go paketindeki typed sonuç/hata akışını koruyan küçük
bir bridge ayrı mimari karar, paketleme planı ve sözleşme testleriyle yeniden
değerlendirilebilir.

İncelenen resmî kaynaklar:

- <https://github.com/projectdiscovery/subfinder/releases/tag/v2.17.0>
- <https://github.com/projectdiscovery/subfinder/blob/v2.17.0/pkg/runner/enumerate.go>
- <https://github.com/projectdiscovery/subfinder/blob/v2.17.0/pkg/runner/outputter.go>
- <https://github.com/projectdiscovery/subfinder/blob/v2.17.0/LICENSE.md>
- <https://github.com/projectdiscovery/subfinder/blob/v2.17.0/DISCLAIMER.md>

## Veri ve uyumluluk

Şema 54 değişmez. Mevcut crt.sh ve theHarvester kayıtları taşınmaz veya yeniden
yazılmaz. Sağlayıcı filtresi aynı eklemeli çalışma geçmişini okur. Eski
`surface discovery-status KÖK` ve JSON sözleşmesi seçim verilmediğinde korunur;
yeni birleşik görünüm ayrı `discovery-health` komutundadır.

## Kabul kanıtı

- theHarvester kanıtı depolama ve terminal aday ayrıntısından okunur.
- crt.sh başarısı ile theHarvester hatası aynı kökte birbirini gizlemeden
  gösterilir.
- Sağlık ve tek-sağlayıcı durum okumaları ağ çağrısı veya veritabanı değişikliği
  yapmaz.
- Kabul kapısındaki aktif kimlikler çalışma zamanı sağlayıcılarıyla birebir
  eşleşir; Subfinder'ın makine sözleşmesi, sonuç ayrımı ve bağımsız kapsam
  ölçütleri başarısızdır.
- Kabul kapısı terminal ve JSON biçiminde veri klasörü oluşturmadan çalışır.
