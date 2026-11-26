# Abuse iletişim keşfi ve takedown yönlendirmesi

**Sürüm 0.195.0 · çekirdek şema 101.** Bu özellik, doğrulanmış bir vaka
kanıtındaki domain veya genel IP için doğru kötüye kullanım iletişim kanalını
pasif kaynaklardan bulur. Bulduğu adresi doğrudan kullanmaz: önce analiste
aday olarak gösterir, insan onayı ister ve yalnız güncel onaylı adayı takedown
taslağına bağlar. XTI e-posta göndermez, portala başvuru yapmaz ve hedefi
aktif olarak taramaz.

Basit örnek: `taklit-firma.example` vakaya kanıt olarak eklendiyse motor
domainin resmî RDAP kaydındaki açık abuse e-postasını, varsa standart
`security.txt` iletişimini ve isteğe bağlı WHOIS fallback sonucunu toplar.
Analist `abuse@registrar.example` adayını onaylarsa yeni takedown taslağı bu
adayın kanıt sürümüne bağlanır. Kaynak daha sonra adresi değiştirirse eski
onay bayat olur; taslak onaylanmadan veya dış başvuru kaydedilmeden önce yeni
adres tekrar incelenmelidir.

## Kaynaklar ve güven düzeyi

| Kaynak | Ne alınır? | Durum ve sınır |
|---|---|---|
| Domain RDAP | IANA bootstrap ile seçilen registrar RDAP kaydındaki yalnız açık `abuse` rolü | Ana kaynak; registrant/kişi verisi alınmaz. |
| IP RDAP | IANA bootstrap ile seçilen RIR RDAP kaydındaki yalnız açık `abuse` rolü | Ana kaynak; yalnız genel ve kanıtla aynı IP kabul edilir. |
| `security.txt` | `/.well-known/security.txt` içindeki geçerli `Contact` alanları | Yardımcı, düşük güvenli aday; 32 KiB çözülmüş içerik sınırı ve geçerlilik kontrolü vardır. |
| Yerel WHOIS | Yalnız sıkı allowlist içindeki açık abuse e-posta/telefon alanları | İsteğe bağlı düşük güvenli fallback; sadece RDAP iletişim vermediyse çalışır ve yerel `whois` komutu ister. |

RDAP ve `security.txt` için API anahtarı gerekmez. Anlık kaynak kesintisi
özelliği bozmaz: çalışma `partial` veya `failed` olur, hata kaydedilir ve son
başarılı aday silinmez. Başarılı boş yanıt, kaynak hatası ve hiç
çalıştırılmamış durum ayrı gösterilir.

## Ön koşul: vaka kanıtı

Arama serbest bir domain/IP kutusu değildir. Hedef, etkin bir vakadaki donmuş
`finding` veya `brand_protection` kanıtının içinde aynı domain ya da IP olarak
bulunmalıdır. Bu bağ, yanlış müşterinin veya ilgisiz hedefin iletişim
bilgisini takedown akışına karıştırmayı önler.

Önce ağsız planı görün:

```sh
./xti action contact-plan VAKA_KIMLIGI KANIT_BAGI_KIMLIGI \
  --subject-kind domain --subject taklit-firma.example
```

İzlemeyi kaydedin ve kaynakları yenileyin:

```sh
./xti action contact-watch-add VAKA_KIMLIGI KANIT_BAGI_KIMLIGI \
  --subject-kind domain --subject taklit-firma.example \
  --interval-seconds 86400 \
  --actor analyst@example.test \
  --reason "Taklit domainin resmî abuse rotası izlenecek."

./xti action contact-refresh IZLEME_KIMLIGI
./xti action contact-candidates IZLEME_KIMLIGI
./xti action contact-candidate-show ADAY_KIMLIGI
```

WHOIS aracını kullanmak istemiyorsanız izleme eklerken `--exclude-whois`
verin. Güncellemeyi beklemeden tekrar denemek için yalnız bilinçli operatör
işleminde `contact-refresh ... --force` kullanılmalıdır.

## İnsan incelemesi

```sh
./xti action contact-review ADAY_KIMLIGI \
  --decision approved \
  --actor analyst@example.test \
  --reason "RDAP kaydındaki açık abuse rolü ve hedef kapsamı doğrulandı."
```

Kararlar `approved`, `rejected` veya `uncertain` olabilir. Karar adayın o
andaki gözlem sürümüne bağlıdır. İletişim değeri, kaynak kanıtı veya aktiflik
değişirse önceki karar geçmişte kalır fakat takedown için artık geçerli
sayılmaz.

## İncelenmiş adayla takedown taslağı

Manuel alıcı yazmak yerine güncel onaylı adayı bağlayabilirsiniz:

```sh
./xti action takedown-create VAKA_KIMLIGI KANIT_BAGI_KIMLIGI \
  --contact-candidate-id ADAY_KIMLIGI \
  --requested-action "Kötüye kullanım incelemesine alınsın." \
  --grounds "Taklit ve marka yetkisi vaka kanıtıyla doğrulandı." \
  --actor analyst@example.test \
  --idempotency-key vaka-123-abuse-route-1
```

Motor adayın aynı vaka ve kanıta bağlı, etkin ve güncel `approved` durumda
olduğunu doğrular. `takedown-approve` ve `takedown-submit` sırasında bu bağ
yeniden kontrol edilir. Dış başvuru yine insan tarafından yapılır;
`takedown-submit` yalnız dışarıdaki başvurunun referansını kaydeder.

## Geçmiş, zamanlama ve kurtarma

```sh
./xti action contact-watches --case-id VAKA_KIMLIGI
./xti action contact-watch-show IZLEME_KIMLIGI
./xti action contact-watch-events IZLEME_KIMLIGI
./xti action contact-due
./xti action contact-runs --watch-id IZLEME_KIMLIGI
./xti action contact-run-show CALISMA_KIMLIGI
./xti action contact-candidate-events ADAY_KIMLIGI
./xti action contact-reviews ADAY_KIMLIGI
```

Terminal açıkken sınırlı kabul veya kişisel kullanım için:

```sh
./xti action contact-monitor IZLEME_KIMLIGI --max-cycles 3
```

Bu bir sunucu daemon'u değildir. Ticari platform, `action.contact.due`
sonucunu kendi güvenilen zamanlayıcısıyla işler. Kesilen bir `running` tur
yeni internet isteği yapılmadan kapatılır:

```sh
./xti action contact-recover CALISMA_KIMLIGI \
  --actor operator@example.test \
  --reason "Kesilen worker turu yeniden ağ isteği yapmadan kapatıldı."
```

## Engine ve firma platformu

Salt okunur `action.contact.*` işlemleri engine v1 üzerinden aynı yerel
kayıtları sayfalı ve ağsız döndürür. Firma platformu yazmaları güncel
`expected_workspace_id`, ilgili revision ve idempotency anahtarı ister.
Yalnız `action.contact.refresh` açık ağ operasyonudur. Müşteri UI'si kaynak
markası veya teknik provider durumunu ana ekran dili yapmak zorunda değildir;
“iletişim bulundu / inceleme gerekiyor / kaynak geçici olarak tamamlanamadı”
gibi ürün durumlarını gösterir, ayrıntılı provenance ise analist kanıtında
korunur.

## Saklama ve güvenlik

- Ham RDAP, WHOIS veya `security.txt` gövdesi veritabanında saklanmaz.
- Yalnız küçültülmüş iletişim, açık rol/alan kanıtı, kaynak başvurusu, zaman,
  durum, istek/bayt sayısı ve SHA-256 bağlı makbuz tutulur.
- Dış HTTPS istekleri genel IP'ye sabitlenir; proxy, kullanıcı bilgili URL,
  özel IP ve güvenilmeyen host yönlendirmesi reddedilir.
- WHOIS shell komutu oluşturmaz; doğrulanmış argv ile süre ve 1 MiB çıktı
  sınırında çalışır.
- Liste ve geçmişler sayfalıdır; aynı tekrar anahtarı çift kayıt veya gizli
  ikinci kaynak isteği üretmez.
- Şema 100→101 geçişi açık `./xti migrate` komutuyla önce yedek alır; mevcut
  kayıtları değiştirmeden yeni boş abuse-contact tablolarını ekler.

Ticari saklama/müşteriye gösterme hakları ve canlı Linux kabul durumu
[NOTES.md](../NOTES.md) içindeki ilgili açık notta tutulur. Kaynak sözleşmeleri
`./xti sources show action:domain-rdap` gibi komutlarla çevrimdışı okunabilir.
